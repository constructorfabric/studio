"""`validate-toc` under a project's severity policy and per-kind TOC options.

Two claims are proved separately here, because either can hold while the other
fails: that the constraint loader reads and merges `[validation.toc]`, and that
the command actually consults what was read. The first is unit-tested against
the parser, the second end-to-end through the real CLI on a real project — a
resolver that is correct and a command that ignores it would otherwise look
exactly like a feature that works.
"""

from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.commands import validate_toc as VT  # noqa: E402
from studio.utils import constraints as C  # noqa: E402
from studio.utils import toml_utils  # noqa: E402
from studio.utils.toc import DEFAULT_MAX_SECTION_LINES, DEFAULT_TOC_MAX_LEVEL, insert_toc_markers  # noqa: E402


# ---------------------------------------------------------------------------
# Parsing `[artifacts.<KIND>.validation.toc]`
# ---------------------------------------------------------------------------

def _load_kind(tmp_path: Path, kind_table: dict) -> tuple[object, list[str]]:
    """Load a one-kind constraints file, returning that kind and any errors."""
    path = tmp_path / "constraints.toml"
    toml_utils.dump({"artifacts": {"PRD": {"identifiers": {}, **kind_table}}}, path)
    loaded, errors = C.load_constraints_file(path)
    if loaded is None:
        return None, errors
    return loaded.by_kind.get("PRD"), errors


def test_toc_options_round_trip_from_the_kind_table(tmp_path):
    kind, errors = _load_kind(
        tmp_path, {"validation": {"toc": {"max_level": 4, "max_section_lines": 120}}})
    assert errors == []
    assert kind.toc_options == C.TocOptions(max_level=4, max_section_lines=120)
    # And `toc` is a key this engine knows here, not one it tolerates: left out
    # of the per-kind key set it would load correctly and warn about itself.
    assert kind.validation.unknown_keys == ()


def test_a_kind_saying_nothing_about_toc_has_no_opinion(tmp_path):
    """Not the engine default: "unset" is what lets a flag and a kit be told apart."""
    kind, errors = _load_kind(tmp_path, {"validation": {"severity": {"toc-missing": "warning"}}})
    assert errors == []
    assert kind.toc_options == C.TocOptions(max_level=None, max_section_lines=None)


def test_each_option_can_be_set_without_the_other(tmp_path):
    kind, errors = _load_kind(tmp_path, {"validation": {"toc": {"max_level": 2}}})
    assert errors == []
    assert kind.toc_options == C.TocOptions(max_level=2, max_section_lines=None)


@pytest.mark.parametrize(
    ("toc_table", "expected_fragment"),
    [
        ({"max_level": 7}, "max_level must be an integer between 1 and 6"),
        ({"max_level": 0}, "max_level must be an integer between 1 and 6"),
        # `bool` is an `int` in Python: unguarded, this would be read as depth 1.
        ({"max_level": True}, "max_level must be an integer between 1 and 6"),
        ({"max_level": "3"}, "max_level must be an integer between 1 and 6"),
        ({"max_section_lines": 0}, "max_section_lines must be an integer of 1 or more"),
        ({"max_section_lines": "many"}, "max_section_lines must be an integer of 1 or more"),
    ],
)
def test_an_unreadable_toc_option_fails_the_load(tmp_path, toc_table, expected_fragment):
    """Fail closed: an unreadable bound leaves the check running to an unknown depth."""
    kind, errors = _load_kind(tmp_path, {"validation": {"toc": toc_table}})
    assert kind is None
    assert any(expected_fragment in message for message in errors), errors


def test_a_toc_option_table_that_is_not_a_table_fails_the_load(tmp_path):
    kind, errors = _load_kind(tmp_path, {"validation": {"toc": 3}})
    assert kind is None
    assert any("toc must be a table of TOC options" in message for message in errors), errors


def test_a_misspelled_toc_option_is_reported_not_ignored(tmp_path):
    """The same channel a misspelled rule code uses — a warning, not silence."""
    kind, errors = _load_kind(
        tmp_path, {"validation": {"toc": {"max_levl": 2, "max_level": 2}}})
    assert errors == []
    assert kind.toc_options == C.TocOptions(max_level=2)
    assert "[artifacts.PRD.validation].toc.max_levl" in kind.validation.unknown_keys


def test_toc_options_are_per_kind_and_not_a_whole_kit_setting(tmp_path):
    """A whole-kit `[validation.toc]` is reported rather than quietly obeyed."""
    path = tmp_path / "constraints.toml"
    toml_utils.dump(
        {"validation": {"toc": {"max_level": 2}}, "artifacts": {"PRD": {"identifiers": {}}}},
        path,
    )
    loaded, errors = C.load_constraints_file(path)
    assert errors == []
    assert loaded.by_kind["PRD"].toc_options == C.TocOptions()
    assert "[validation].toc" in loaded.validation.unknown_keys


# ---------------------------------------------------------------------------
# Merging two kits' options for one kind
# ---------------------------------------------------------------------------

def _merged(base: C.TocOptions, incoming: C.TocOptions) -> C.TocOptions:
    def kind(options):
        return C.ArtifactKindConstraints(
            name=None, description=None, defined_id=[], toc_options=options)

    merged = C.merge_kit_constraints_all_of([
        C.KitConstraints(by_kind={"PRD": kind(base)}),
        C.KitConstraints(by_kind={"PRD": kind(incoming)}),
    ])
    return merged.by_kind["PRD"].toc_options


@pytest.mark.parametrize(
    ("base", "incoming", "expected"),
    [
        # Deeper wins: more headings fall under the completeness check.
        (C.TocOptions(max_level=2), C.TocOptions(max_level=4), C.TocOptions(max_level=4)),
        (C.TocOptions(max_level=4), C.TocOptions(max_level=2), C.TocOptions(max_level=4)),
        # Smaller wins: more sections get flagged as oversized.
        (C.TocOptions(max_section_lines=300), C.TocOptions(max_section_lines=100),
         C.TocOptions(max_section_lines=100)),
        # A kit with no opinion never loosens one that has one.
        (C.TocOptions(), C.TocOptions(max_level=5), C.TocOptions(max_level=5)),
        (C.TocOptions(max_level=5), C.TocOptions(), C.TocOptions(max_level=5)),
        (C.TocOptions(), C.TocOptions(), C.TocOptions()),
    ],
)
def test_two_kits_merge_toc_options_strictest_wins(base, incoming, expected):
    assert _merged(base, incoming) == expected


# ---------------------------------------------------------------------------
# Flag / configuration / default precedence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("flag", "configured", "expected"),
    [
        (2, 5, 2),      # an explicit flag is the most specific statement
        (None, 5, 5),   # else the artifact kind's configured value
        (None, None, 3),  # else the engine default
        (3, None, 3),   # an explicit 3 is a choice, not a fallback
    ],
)
def test_the_flag_outranks_configuration_which_outranks_the_default(flag, configured, expected):
    assert VT._resolve_toc_option(flag, configured, 3) == expected


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------

_RAW_PRD = """# PRD

Intro line.

## Context

Text.

## Requirements

Text.

### Detail

Text.
"""

#: A PRD whose TOC covers its two level-2 headings and not the level-3 one, so
#: it is complete at depth 2 and incomplete at depth 3.
_PRD_WITH_SHALLOW_TOC = insert_toc_markers(_RAW_PRD, max_level=2)

#: The same document with no TOC at all — the `toc-missing` case from #53.
_PRD_WITHOUT_TOC = _RAW_PRD


def _write_toc_project(
    root: Path,
    *,
    prd_body: str,
    kind_tables: dict | None = None,
    core_validation: dict | None = None,
) -> None:
    """A two-kind project (PRD, FEATURE) whose PRD is the file under test."""
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / "AGENTS.md").write_text(
        '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "adapter"\n```\n'
        "<!-- /@cf:root-agents -->\n",
        encoding="utf-8",
    )
    config = root / "adapter" / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "AGENTS.md").write_text("# Test adapter\n", encoding="utf-8")

    kit = root / "kits" / "test"
    for kind in ("PRD", "FEATURE"):
        template = kit / "artifacts" / kind
        template.mkdir(parents=True, exist_ok=True)
        (template / "template.md").write_text(f"# {kind}\n", encoding="utf-8")
    artifacts: dict = {
        kind: {"identifiers": {}, **(kind_tables or {}).get(kind, {})}
        for kind in ("PRD", "FEATURE")
    }
    (kit / "constraints.toml").write_text(
        toml_utils.dumps({"artifacts": artifacts}), encoding="utf-8")

    kits = {"test": {"format": "CFS", "path": "kits/test"}}
    core: dict = {"version": "1.0", "project_root": "..", "kits": kits}
    if core_validation is not None:
        core["validation"] = core_validation
    toml_utils.dump(core, config / "core.toml")
    toml_utils.dump({
        "version": "1.0",
        "project_root": "..",
        "kits": kits,
        "systems": [{
            "name": "Test", "slug": "test", "kit": "test",
            "artifacts": [
                {"path": "architecture/PRD.md", "kind": "PRD"},
                {"path": "architecture/FEATURE.md", "kind": "FEATURE"},
            ],
        }],
    }, config / "artifacts.toml")

    architecture = root / "architecture"
    architecture.mkdir(parents=True, exist_ok=True)
    (architecture / "PRD.md").write_text(prd_body, encoding="utf-8")
    (architecture / "FEATURE.md").write_text(_PRD_WITHOUT_TOC, encoding="utf-8")


def _run(root: Path, argv: list[str]) -> tuple[int, dict]:
    from studio.cli import main
    from studio.utils.ui import is_json_mode, set_json_mode

    old_cwd = Path.cwd()
    saved = is_json_mode()
    stdout = io.StringIO()
    try:
        os.chdir(root)
        with redirect_stdout(stdout):
            exit_code = main(argv)
        return exit_code, json.loads(stdout.getvalue())
    finally:
        set_json_mode(saved)
        os.chdir(old_cwd)


def _run_human(root: Path, argv: list[str]) -> tuple[int, str]:
    from studio.cli import main
    from studio.utils.ui import is_json_mode, set_json_mode

    old_cwd = Path.cwd()
    saved = is_json_mode()
    stdout = io.StringIO()
    try:
        os.chdir(root)
        set_json_mode(False)
        with redirect_stdout(stdout):
            exit_code = main(argv)
        return exit_code, stdout.getvalue()
    finally:
        set_json_mode(saved)
        os.chdir(old_cwd)


def _codes(report: dict, bucket: str = "errors") -> list[str]:
    return [
        str(finding.get("code"))
        for result in report.get("results", [])
        for finding in result.get(bucket, [])
    ]


def test_e2e_without_configuration_a_missing_toc_still_fails(tmp_path):
    """#140 AC7: with nothing configured, nothing moves."""
    _write_toc_project(tmp_path, prd_body=_PRD_WITHOUT_TOC)
    exit_code, report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert exit_code == 2
    assert report["status"] == "FAIL"
    assert "toc-missing" in _codes(report)


def test_e2e_a_project_can_lower_a_toc_rule_to_a_warning(tmp_path):
    """#53 / #140 AC1: the rule stays visible and stops gating the run."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        core_validation={"severity": {"toc-missing": "warning"}},
    )
    exit_code, report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert exit_code == 0
    assert report["status"] == "WARN"
    assert report["error_count"] == 0
    assert "toc-missing" in _codes(report, "warnings")
    assert report["results"][0]["warnings"][0]["severity"] == "warning"


def test_e2e_a_lowering_names_itself_in_the_report(tmp_path):
    """The passive reader is told, rather than having to ask."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        core_validation={"severity": {"toc-missing": "warning"}},
    )
    _, report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    overrides = report["severity_overrides"]
    assert [(row["code"], row["from"], row["to"]) for row in overrides] == [
        ("toc-missing", "error", "warning")]


def test_e2e_a_rule_switched_off_is_counted_not_silently_dropped(tmp_path):
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        core_validation={"severity": {"toc-missing": "off"}},
    )
    exit_code, report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert exit_code == 0
    assert report["status"] == "PASS"
    assert report["suppressed_count"] == 1
    assert report["results"][0]["suppressed_count"] == 1


def test_e2e_the_human_report_says_what_it_suppressed(tmp_path):
    """At a terminal, a suppressed run must not read like a clean one."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        core_validation={"severity": {"toc-missing": "off"}},
    )
    exit_code, text = _run_human(tmp_path, ["validate-toc", "architecture/PRD.md"])
    assert exit_code == 0
    assert "1 finding(s) at severity off" in text
    assert "toc-missing" in text


def test_e2e_a_per_kind_severity_reaches_only_that_kind(tmp_path):
    """#140 AC2: the PRD warns while the FEATURE, same finding, still fails."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        core_validation={"severity": {"PRD": {"toc-missing": "warning"}}},
    )
    prd_code, prd_report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert (prd_code, prd_report["status"]) == (0, "WARN")

    feature_code, feature_report = _run(
        tmp_path, ["--json", "validate-toc", "architecture/FEATURE.md"])
    assert (feature_code, feature_report["status"]) == (2, "FAIL")
    assert "toc-missing" in _codes(feature_report)


def test_e2e_a_finding_records_the_kind_whose_policy_settled_it(tmp_path):
    _write_toc_project(tmp_path, prd_body=_PRD_WITHOUT_TOC)
    _, report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert report["results"][0]["artifact_kind"] == "PRD"
    assert report["results"][0]["errors"][0]["artifact_kind"] == "PRD"


def test_e2e_an_unregistered_file_still_gets_the_project_wide_policy(tmp_path):
    """A file no system registers has no kind, and a whole-project rule still applies."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        core_validation={"severity": {"toc-missing": "warning"}},
    )
    (tmp_path / "loose.md").write_text(_PRD_WITHOUT_TOC, encoding="utf-8")
    exit_code, report = _run(tmp_path, ["--json", "validate-toc", "loose.md"])
    assert exit_code == 0
    assert "artifact_kind" not in report["results"][0]
    assert "toc-missing" in _codes(report, "warnings")


def test_e2e_a_kind_can_configure_how_deep_its_toc_is_checked(tmp_path):
    """The level-3 heading is out of scope for a kind that stops at 2."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITH_SHALLOW_TOC,
        kind_tables={"PRD": {"validation": {"toc": {"max_level": 2}}}},
    )
    exit_code, report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert (exit_code, report["status"]) == (0, "PASS")

    # Same document, same command, without the configured depth.
    _write_toc_project(tmp_path, prd_body=_PRD_WITH_SHALLOW_TOC)
    exit_code, report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert (exit_code, report["status"]) == (2, "FAIL")
    assert "toc-heading-not-in-toc" in _codes(report)


def test_e2e_an_explicit_flag_overrides_the_kinds_configured_depth(tmp_path):
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITH_SHALLOW_TOC,
        kind_tables={"PRD": {"validation": {"toc": {"max_level": 2}}}},
    )
    exit_code, report = _run(
        tmp_path, ["--json", "validate-toc", "--max-level", "3", "architecture/PRD.md"])
    assert exit_code == 2
    assert "toc-heading-not-in-toc" in _codes(report)


def test_e2e_a_kind_can_configure_its_section_size(tmp_path):
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITH_SHALLOW_TOC,
        kind_tables={"PRD": {"validation": {"toc": {"max_level": 2, "max_section_lines": 1}}}},
    )
    exit_code, report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert exit_code == 0
    assert "toc-section-too-long" in _codes(report, "warnings")


def test_e2e_a_project_can_make_warnings_fail_the_run(tmp_path):
    """#140 AC6, reaching validate-toc through the configuration rather than a flag."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        core_validation={"severity": {"toc-missing": "warning"}, "fail_on_warnings": True},
    )
    exit_code, report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert exit_code == 2
    assert report["status"] == "FAIL"
    assert report["failed_on"] == "warnings"
    assert report["results"][0]["failed_on"] == "warnings"


def test_e2e_a_kit_can_lower_a_toc_rule_for_its_own_kind(tmp_path):
    """The kit layer reaches this command too, with no project override in sight."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        kind_tables={"PRD": {"validation": {"severity": {"toc-missing": "warning"}}}},
    )
    prd_code, prd_report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert (prd_code, prd_report["status"]) == (0, "WARN")
    # Scoped to the kind the kit named, not to the kit's documents at large.
    feature_code, _ = _run(tmp_path, ["--json", "validate-toc", "architecture/FEATURE.md"])
    assert feature_code == 2


def test_e2e_a_project_may_raise_what_a_kit_lowered(tmp_path):
    """Raising is always allowed, and is the direction a lowering is measured from."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        kind_tables={"PRD": {"validation": {"severity": {"toc-missing": "warning"}}}},
        core_validation={"severity": {"toc-missing": "error"}},
    )
    exit_code, report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert exit_code == 2
    assert "toc-missing" in _codes(report)
    # A raise is not an override to report: nothing was weakened.
    assert "severity_overrides" not in report


def test_e2e_an_unreadable_severity_configuration_refuses_the_run(tmp_path):
    """Fail closed: a verdict under a policy nobody can predict is worse than none."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        core_validation={"severity": {"toc-missing": "advisory"}},
    )
    exit_code, report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert exit_code == 1
    assert report["status"] == "ERROR"
    assert any("advisory" in message for message in report["errors"])


def test_e2e_structure_validation_honours_the_same_per_kind_depth(tmp_path):
    """`cfs validate` runs the TOC phase too, and checked every kind at depth 3.

    Without this the options could be read, reported and merged correctly and
    still reach only one of the two commands that run TOC checking.
    """
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITH_SHALLOW_TOC,
        kind_tables={"PRD": {"validation": {"toc": {"max_level": 2}}}},
    )
    exit_code, report = _run(
        tmp_path, ["--json", "validate", "--artifact", "architecture/PRD.md", "--skip-code"])
    assert exit_code == 0, report
    assert "toc-heading-not-in-toc" not in [e.get("code") for e in report.get("errors", [])]

    _write_toc_project(tmp_path, prd_body=_PRD_WITH_SHALLOW_TOC)
    exit_code, report = _run(
        tmp_path, ["--json", "validate", "--artifact", "architecture/PRD.md", "--skip-code"])
    assert exit_code == 2
    assert "toc-heading-not-in-toc" in [e.get("code") for e in report.get("errors", [])]


def test_e2e_outside_a_project_nothing_is_loaded_and_nothing_changes(tmp_path):
    """The command's oldest contract: a bare directory of Markdown still works."""
    (tmp_path / "loose.md").write_text(_PRD_WITHOUT_TOC, encoding="utf-8")
    exit_code, report = _run(tmp_path, ["--json", "validate-toc", "loose.md"])
    assert exit_code == 2
    assert report["status"] == "FAIL"
    assert "toc-missing" in _codes(report)
    assert "severity_overrides" not in report
    assert "artifact_kind" not in report["results"][0]


def test_the_defaults_this_command_falls_back_to_are_the_documented_ones(tmp_path):
    """Pinned by value: a changed fallback is invisible to every test above."""
    assert (DEFAULT_TOC_MAX_LEVEL, DEFAULT_MAX_SECTION_LINES) == (3, 300)


def test_the_parser_and_the_schema_agree_on_which_toc_options_exist(tmp_path):
    """Two hand-maintained lists of the same set drift silently otherwise."""
    schema = json.loads(
        (Path(__file__).parent.parent / "schemas" / "kit-constraints.schema.json").read_text(
            encoding="utf-8"))
    documented = set(schema["$defs"]["toc_options"]["properties"])
    assert documented == set(C._TOC_OPTION_KEYS)


# ---------------------------------------------------------------------------
# `toc = false`, scope, and the bounds on the flags
# ---------------------------------------------------------------------------

def test_e2e_a_kind_with_no_toc_contract_is_reported_as_not_applicable(tmp_path):
    """`cfs validate` skips the phase for `toc = false`; this must agree.

    And it must say so: a file nobody examined and a file that came back clean
    are different answers, and only one of them means the TOC is correct.
    """
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        kind_tables={"PRD": {"toc": False}},
    )
    exit_code, report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert exit_code == 0
    result = report["results"][0]
    assert result["status"] == "PASS"
    assert result["applicable"] is False
    assert result["artifact_kind"] == "PRD"
    assert "toc = false" in result["message"]
    # The same file under a kind that keeps its TOC contract does fail.
    feature_code, _ = _run(tmp_path, ["--json", "validate-toc", "architecture/FEATURE.md"])
    assert feature_code == 2


def test_e2e_a_skipped_file_does_not_read_as_clean_at_a_terminal(tmp_path):
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        kind_tables={"PRD": {"toc": False}},
    )
    exit_code, text = _run_human(tmp_path, ["validate-toc", "architecture/PRD.md"])
    assert exit_code == 0
    assert "skipped" in text


def test_e2e_the_human_report_attributes_kind_and_suppression_per_file(tmp_path):
    """With several files, a run-level count cannot say which one was quietened."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        core_validation={"severity": {"PRD": {"toc-missing": "off"}}},
    )
    exit_code, text = _run_human(
        tmp_path, ["validate-toc", "architecture/PRD.md", "architecture/FEATURE.md"])
    assert exit_code == 2
    assert "(kind PRD, 1 finding(s) suppressed)" in text
    assert "(kind FEATURE)" in text


def test_e2e_an_unregistered_file_outside_the_project_is_not_judged_by_it(tmp_path):
    """Another repository's document is not this project's to grade."""
    project = tmp_path / "project"
    project.mkdir()
    _write_toc_project(
        project,
        prd_body=_PRD_WITHOUT_TOC,
        core_validation={"severity": {"toc-missing": "off"}},
    )
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "doc.md").write_text(_PRD_WITHOUT_TOC, encoding="utf-8")

    exit_code, report = _run(project, ["--json", "validate-toc", "../elsewhere/doc.md"])
    # Inside the tree the same rule is `off`; outside it, engine defaults apply.
    assert exit_code == 2
    assert "toc-missing" in _codes(report)
    assert "suppressed_count" not in report["results"][0]


def test_e2e_a_registered_artifact_is_judged_by_the_project_wherever_it_resolves(tmp_path):
    """The containment rule must not reach registered artifacts — see workspaces."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        core_validation={"severity": {"toc-missing": "warning"}},
    )
    exit_code, report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert (exit_code, report["status"]) == (0, "WARN")


@pytest.mark.parametrize("argv_flag", [["--max-level", "0"], ["--max-level", "7"]])
def test_e2e_an_out_of_range_max_level_is_rejected_not_silently_obeyed(tmp_path, argv_flag):
    """`--max-level 0` empties the heading list, so every check returns early.

    Unbounded, that is a silent PASS on a document with a genuinely broken
    table of contents — the worst shape a validation bug can take.
    """
    (tmp_path / "loose.md").write_text(_PRD_WITHOUT_TOC, encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        _run(tmp_path, ["--json", "validate-toc", *argv_flag, "loose.md"])
    assert excinfo.value.code == 2


def test_e2e_a_non_positive_max_section_lines_is_rejected(tmp_path):
    (tmp_path / "loose.md").write_text(_PRD_WITHOUT_TOC, encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        _run(tmp_path, ["--json", "validate-toc", "--max-section-lines", "0", "loose.md"])
    assert excinfo.value.code == 2


def test_e2e_the_fail_on_warnings_flag_reaches_this_command(tmp_path):
    """The flag's own wiring, with nothing set in the project configuration."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        core_validation={"severity": {"toc-missing": "warning"}},
    )
    passing, _ = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert passing == 0

    exit_code, report = _run(
        tmp_path, ["--json", "validate-toc", "--fail-on-warnings", "architecture/PRD.md"])
    assert exit_code == 2
    assert report["failed_on"] == "warnings"


def test_e2e_the_max_section_lines_flag_overrides_the_kinds_configured_value(tmp_path):
    """The twin of the `--max-level` override; same code path, separate wiring."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITH_SHALLOW_TOC,
        kind_tables={"PRD": {"validation": {"toc": {"max_level": 2, "max_section_lines": 500}}}},
    )
    quiet, report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert (quiet, "toc-section-too-long" in _codes(report, "warnings")) == (0, False)

    exit_code, report = _run(
        tmp_path,
        ["--json", "validate-toc", "--max-section-lines", "1", "architecture/PRD.md"],
    )
    assert exit_code == 0
    assert "toc-section-too-long" in _codes(report, "warnings")


def test_e2e_one_lowered_rule_hit_by_two_files_is_reported_once(tmp_path):
    """Refusals and overrides accumulate across files under one dedupe rule."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        core_validation={"severity": {"toc-missing": "warning"}},
    )
    exit_code, report = _run(
        tmp_path,
        ["--json", "validate-toc", "architecture/PRD.md", "architecture/FEATURE.md"],
    )
    assert exit_code == 0
    assert report["warning_count"] == 2
    assert [row["code"] for row in report["severity_overrides"]] == ["toc-missing"]


def test_e2e_a_lower_cased_registry_kind_still_finds_its_configured_depth(tmp_path):
    """`by_kind` is upper-cased by the loader; the registry keeps what was typed.

    Without folding the case here the kind's whole TOC configuration is
    dropped while its severities keep working, which is close to invisible.
    """
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITH_SHALLOW_TOC,
        kind_tables={"PRD": {"validation": {"toc": {"max_level": 2}}}},
    )
    config = tmp_path / "adapter" / "config" / "artifacts.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace('kind = "PRD"', 'kind = "prd"'),
        encoding="utf-8",
    )
    exit_code, report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert (exit_code, report["status"]) == (0, "PASS")
    assert report["results"][0]["artifact_kind"] == "prd"


def test_the_path_index_folds_case_the_way_the_filesystem_might(tmp_path, monkeypatch):
    """Proved by simulation: on Linux `normcase` is identity, so a real run
    on this machine can never tell a folded index from an unfolded one.

    `Path.resolve()` does not correct the case of a path typed differently
    from the file on disk. Without folding, a macOS or Windows user naming the
    same file in another case gets it treated as unregistered — losing its
    kind, its configured depth and its kind-scoped severity, silently.
    """
    monkeypatch.setattr(os.path, "normcase", str.lower)
    targets = {VT._path_key(Path("/Project/Architecture/PRD.md")): "sentinel"}
    assert targets.get(VT._path_key(Path("/project/architecture/prd.md"))) == "sentinel"


def test_e2e_cfs_toc_still_writes_a_table_for_a_kind_that_does_not_require_one(tmp_path):
    """`toc = false` says a table is not required, not that one is forbidden.

    It is a two-state field defaulting to true, so — unlike the three-state
    `multiple` / `numbered` / `task` fields — it has no way to express
    "prohibited". Refusing to generate would leave someone who typed the
    command with no table and no flag to override the refusal.
    """
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        kind_tables={"PRD": {"toc": False}},
    )
    exit_code, report = _run(tmp_path, ["--json", "toc", "architecture/PRD.md"])
    assert exit_code == 0
    assert "<!-- toc -->" in (tmp_path / "architecture" / "PRD.md").read_text(encoding="utf-8")
    # ... but nothing in the toolchain judges it, and this command says so
    # rather than being the only one that does.
    validation = report["results"][0]["validation"]
    assert validation["status"] == "SKIPPED"
    assert "toc = false" in validation["reason"]


@pytest.mark.parametrize(
    ("validation", "expected"),
    [
        # A check that could not run counts as a failure, not as zero.
        ({"status": "ERROR", "message": "Could not re-read the file"}, 1),
        ({"status": "FAIL", "errors": 3, "warnings": 0}, 3),
        ({"status": "WARN", "errors": 0, "warnings": 2}, 0),
        ({"status": "PASS"}, 0),
        ({"status": "SKIPPED", "reason": "PRD declares toc = false"}, 0),
        ({"status": "FAIL", "errors": None}, 0),
        ({}, 0),
    ],
)
def test_the_failure_count_contract_of_one_validation_result(validation, expected):
    """Pinned directly, because every other test reaches it through file I/O.

    That indirection is what hides a regression: the ERROR result carries no
    `errors` key, so a refactor that checked `errors` before `status` would
    return 0 for an unreadable file and the run would exit 0 having verified
    nothing.
    """
    from studio.commands.toc import _unverified_count

    assert _unverified_count(validation) == expected


def test_post_generation_validation_never_raises(tmp_path):
    """The contract stated in the docstring, tested directly.

    `cli.main` special-cases only `SystemExit`, so anything else escaping a
    command handler crashes the process.
    """
    from studio.commands.toc import _post_generation_validation
    from studio.commands.validate_toc import TocResolution

    vanished = tmp_path / "written-then-deleted.md"
    result = _post_generation_validation(vanished, TocResolution(max_level=3))
    assert result["status"] == "ERROR"
    assert "Could not re-read" in result["message"]


def test_e2e_an_unreadable_file_does_not_abort_the_rest_of_a_toc_batch(tmp_path, monkeypatch):
    """One racy file must not take the whole invocation down with a traceback.

    The file has just been written, so a failure here is a permission change,
    an unmount or a TOCTOU race. `cli.main` special-cases only `SystemExit`,
    so anything else escaping the handler crashes the process and discards the
    results already collected for every earlier file in the batch.
    """
    _write_toc_project(tmp_path, prd_body=_PRD_WITHOUT_TOC)
    (tmp_path / "architecture" / "FEATURE.md").write_text(_PRD_WITHOUT_TOC, encoding="utf-8")

    real_read_text, real_write_text = Path.read_text, Path.write_text
    written: set[str] = set()

    def track_write(self, *args, **kwargs):
        written.add(self.name)
        return real_write_text(self, *args, **kwargs)

    def fail_reading_back_the_feature(self, *args, **kwargs):
        # Precisely the reviewer's window: readable while being generated,
        # unreadable by the time the post-generation check reads it back.
        if self.name == "FEATURE.md" and self.name in written:
            raise OSError(13, "Permission denied")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", track_write)
    monkeypatch.setattr(Path, "read_text", fail_reading_back_the_feature)
    exit_code, report = _run(
        tmp_path, ["--json", "toc", "architecture/PRD.md", "architecture/FEATURE.md"])

    # The good file's result survived rather than being lost to a crash.
    assert report["files_processed"] == 2
    by_file = {Path(r["file"]).name: r for r in report["results"]}
    assert by_file["PRD.md"]["validation"]["status"] in ("PASS", "WARN")
    # And the bad one is reported, not silently passed: the check never ran.
    assert by_file["FEATURE.md"]["validation"]["status"] == "ERROR"
    assert "Permission denied" in by_file["FEATURE.md"]["validation"]["message"]
    assert exit_code == 2


def test_e2e_cfs_toc_checks_its_output_at_the_kinds_configured_section_size(tmp_path):
    """The other bound drifts the same way the depth did.

    Checking its own output at 300 lines while `validate-toc` checks the same
    file at the kind's configured size makes the two commands disagree about
    a file neither of them changed in between.
    """
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        kind_tables={"PRD": {"validation": {"toc": {"max_section_lines": 1}}}},
    )
    exit_code, report = _run(tmp_path, ["--json", "toc", "architecture/PRD.md"])
    assert exit_code == 0
    validation = report["results"][0]["validation"]
    assert validation["status"] == "WARN"
    assert any("toc-section-too-long" in str(d) for d in validation["details"]), validation

    # And `validate-toc` reaches the same verdict on the file just written.
    _, checked = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert "toc-section-too-long" in _codes(checked, "warnings")


def test_e2e_cfs_toc_shows_warning_details_at_a_terminal_not_only_failures(tmp_path):
    """A WARN result builds `details` exactly as FAIL does, and was rendered
    as nothing at all — the finding reached the JSON and stopped there."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        kind_tables={"PRD": {"validation": {"toc": {"max_section_lines": 1}}}},
    )
    exit_code, text = _run_human(tmp_path, ["toc", "architecture/PRD.md"])
    assert exit_code == 0
    assert "toc-section-too-long" in text


def test_e2e_cfs_toc_grades_its_own_output_through_the_project_policy(tmp_path):
    """Same rule, same file, same kind — one verdict, whichever command asks.

    `cfs toc` asks "will the validators accept what I wrote", and that is the
    graded answer. Reporting a rule the project switched off would describe a
    failure that is never going to happen at the gate.
    """
    kind_tables = {"PRD": {"validation": {"toc": {"max_section_lines": 1}}}}
    _write_toc_project(tmp_path, prd_body=_PRD_WITHOUT_TOC, kind_tables=kind_tables)
    warned, report = _run(tmp_path, ["--json", "toc", "architecture/PRD.md"])
    assert (warned, report["results"][0]["validation"]["status"]) == (0, "WARN")
    raw_warnings = report["results"][0]["validation"]["warnings"]
    assert raw_warnings >= 1

    # The same project, with that one rule switched off.
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        kind_tables=kind_tables,
        core_validation={"severity": {"toc-section-too-long": "off"}},
    )
    quiet_code, quiet = _run(tmp_path, ["--json", "toc", "architecture/PRD.md"])
    assert quiet_code == 0
    validation = quiet["results"][0]["validation"]
    assert validation["status"] == "PASS"
    # Everything that warned a moment ago is now accounted for as suppressed,
    # rather than having quietly disappeared from the report.
    assert validation["suppressed"] == raw_warnings
    assert quiet["status"] == "OK"
    # And `validate-toc` agrees on the same file, which is the whole point.
    _, checked = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert "toc-section-too-long" not in _codes(checked, "warnings")


def test_e2e_a_broken_severity_config_does_not_take_away_cfs_toc(tmp_path):
    """`validate-toc` refuses the run; the command that repairs files must not.

    But it says so, rather than quietly reporting a run as graded when the
    configuration it would have been graded by could not be read.
    """
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        kind_tables={"PRD": {"validation": {"toc": {"max_level": 2}}}},
        core_validation={"severity": {"toc-missing": "advisory"}},
    )
    refused, _ = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert refused == 1

    exit_code, report = _run(tmp_path, ["--json", "toc", "architecture/PRD.md"])
    assert exit_code == 0
    body = (tmp_path / "architecture" / "PRD.md").read_text(encoding="utf-8")
    assert "<!-- toc -->" in body
    # The kind's structural configuration is not collateral damage: depth
    # comes from `constraints.toml`, and an unreadable `[validation]` table in
    # `core.toml` is no reason to regenerate at the wrong one.
    assert "(#detail)" not in body
    assert any("advisory" in message for message in report["policy_errors"])


def test_e2e_a_warning_only_toc_run_does_not_close_with_an_unqualified_success(tmp_path):
    """The renderer has just listed the warnings; the summary must not contradict it."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        kind_tables={"PRD": {"validation": {"toc": {"max_section_lines": 1}}}},
    )
    exit_code, report = _run(tmp_path, ["--json", "toc", "architecture/PRD.md"])
    assert exit_code == 0
    assert report["status"] == "VALIDATION_WARN"
    assert report["warning_count"] >= 1

    _, text = _run_human(tmp_path, ["toc", "architecture/PRD.md"])
    assert "warning(s)" in text
    assert "file(s) processed." not in text


def test_e2e_a_project_that_fails_on_warnings_fails_cfs_toc_too(tmp_path):
    """Having adopted the project's severity, this command adopts its gate.

    Honouring half a policy — which rules are warnings, but not the rule
    about what warnings mean — is the inconsistency reading the policy at
    all was meant to end.
    """
    kind_tables = {"PRD": {"validation": {"toc": {"max_section_lines": 1}}}}
    _write_toc_project(tmp_path, prd_body=_PRD_WITHOUT_TOC, kind_tables=kind_tables)
    lenient, report = _run(tmp_path, ["--json", "toc", "architecture/PRD.md"])
    assert (lenient, report["status"]) == (0, "VALIDATION_WARN")
    assert "failed_on" not in report

    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        kind_tables=kind_tables,
        core_validation={"fail_on_warnings": True},
    )
    exit_code, strict = _run(tmp_path, ["--json", "toc", "architecture/PRD.md"])
    assert exit_code == 2
    assert strict["status"] == "VALIDATION_FAIL"
    assert strict["failed_on"] == "warnings"
    # The file was still written: the gate is about the verdict, not the work.
    assert "<!-- toc -->" in (tmp_path / "architecture" / "PRD.md").read_text(encoding="utf-8")

    _, text = _run_human(tmp_path, ["toc", "architecture/PRD.md"])
    assert "fail_on_warnings" in text


def test_e2e_cfs_toc_attributes_a_warning_to_the_file_that_produced_it(tmp_path):
    """Two files, one noisy: the detail must sit under the right header.

    A single-file "is the string anywhere in the buffer" assertion cannot
    tell a correct renderer from one that prints every file's findings under
    the first file, or under all of them.
    """
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        kind_tables={"PRD": {"validation": {"toc": {"max_section_lines": 1}}}},
    )
    # FEATURE keeps the default section size, so only the PRD warns.
    exit_code, text = _run_human(
        tmp_path, ["toc", "architecture/PRD.md", "architecture/FEATURE.md"])
    assert exit_code == 0

    lines = text.splitlines()
    prd_at = next(i for i, line in enumerate(lines) if "PRD.md" in line)
    feature_at = next(i for i, line in enumerate(lines) if "FEATURE.md" in line)
    warned_at = [i for i, line in enumerate(lines) if "toc-section-too-long" in line]
    assert warned_at, text
    # Every warning line falls between the PRD's header and the FEATURE's.
    assert all(prd_at < i < feature_at for i in warned_at), text


def test_e2e_cfs_toc_says_at_a_terminal_that_it_did_not_check_its_own_output(tmp_path):
    """The JSON carries `validation.status`; a terminal reader sees neither key."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        kind_tables={"PRD": {"toc": False}},
    )
    exit_code, text = _run_human(tmp_path, ["toc", "architecture/PRD.md"])
    assert exit_code == 0
    assert "not validated" in text
    assert "toc = false" in text


def test_e2e_a_file_that_was_never_processed_carries_no_verdict(tmp_path):
    """A document with no headings is skipped, and must not report a PASS.

    The short-circuit ordering matters and nothing else pins it: without it
    the check runs on a file that was never written, finds nothing to object
    to in a heading-less document, and stamps `validation: PASS` on a result
    whose own status says SKIP. A check that never ran is not a pass.
    """
    _write_toc_project(tmp_path, prd_body="# PRD\n\nJust a paragraph.\n")
    exit_code, report = _run(tmp_path, ["--json", "toc", "architecture/PRD.md"])
    assert exit_code == 0
    result = report["results"][0]
    assert result["status"] == "SKIP"
    assert "validation" not in result


def test_e2e_a_kind_that_keeps_its_toc_contract_is_still_checked_after_generating(tmp_path):
    """The control for the test above: the skip must be the kind's doing."""
    _write_toc_project(tmp_path, prd_body=_PRD_WITHOUT_TOC)
    exit_code, report = _run(tmp_path, ["--json", "toc", "architecture/PRD.md"])
    assert exit_code == 0
    assert report["results"][0]["validation"]["status"] in ("PASS", "WARN")


def test_e2e_cfs_toc_regenerates_to_the_depth_the_check_will_judge(tmp_path):
    """The documented fix-it workflow must not hand back a failing file."""
    _write_toc_project(
        tmp_path,
        prd_body=_PRD_WITHOUT_TOC,
        kind_tables={"PRD": {"validation": {"toc": {"max_level": 2}}}},
    )
    generated, _ = _run(tmp_path, ["--json", "toc", "architecture/PRD.md"])
    assert generated == 0
    body = (tmp_path / "architecture" / "PRD.md").read_text(encoding="utf-8")
    # Regenerated at the kind's depth of 2, so the level-3 section is absent.
    assert "(#context)" in body
    assert "(#detail)" not in body

    exit_code, report = _run(tmp_path, ["--json", "validate-toc", "architecture/PRD.md"])
    assert (exit_code, report["status"]) == (0, "PASS"), report
