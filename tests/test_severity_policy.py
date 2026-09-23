"""Configured severity: resolution, suppression, reporting and the exit contract.

The unit tests here pin the resolver's precedence and the raise/lower rule
directly, because those are the parts a golden comparison cannot see: a rule
resolved to the wrong layer still produces a finding with a plausible message,
and a whole-output diff stays green while the policy is wrong.

The end-to-end tests then exercise the same rules through the real CLI on a
real project, so that "the resolver is correct" and "the command uses the
resolver" are two separate claims with two separate proofs.
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

from studio.utils import constraints as C  # noqa: E402
from studio.utils import severity as S  # noqa: E402
from studio.utils import toml_utils  # noqa: E402


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _policy(**kwargs) -> S.SeverityPolicy:
    return S.SeverityPolicy(
        kit=kwargs.get("kit", S.SeverityTables()),
        project=kwargs.get("project", S.SeverityTables()),
        entries=kwargs.get("entries", {}),
    )


def test_an_unconfigured_policy_returns_the_built_in_default():
    policy = _policy()
    assert policy.resolve("heading-missing", "PRD") == S.SeverityDecision(
        severity="error", source=S.SOURCE_DEFAULT)
    assert policy.resolve("toc-stale", "PRD").severity == "warning"
    assert policy.is_configured() is False


def test_an_unknown_code_resolves_to_error_even_under_a_configured_policy():
    """The unknown must not become non-blocking just because a policy exists."""
    policy = _policy(kit=S.SeverityTables(by_code={"toc-missing": "warning"}))
    decision = policy.resolve("a-rule-this-engine-has-never-heard-of", "PRD")
    assert decision == S.SeverityDecision(severity="error", source=S.SOURCE_DEFAULT)


@pytest.mark.parametrize(
    ("kwargs", "expected_severity", "expected_source"),
    [
        (
            {"kit": S.SeverityTables(by_code={"heading-missing": "warning"})},
            "warning", S.SOURCE_KIT,
        ),
        (
            {"kit": S.SeverityTables(
                by_code={"heading-missing": "off"},
                by_kind={"PRD": {"heading-missing": "warning"}},
            )},
            "warning", S.SOURCE_KIT_KIND,
        ),
        (
            {
                "kit": S.SeverityTables(by_kind={"PRD": {"heading-missing": "off"}}),
                "entries": {"PRD": {("heading", "prd-metrics"): S.EntrySeverity("warning")}},
            },
            "warning", S.SOURCE_ENTRY,
        ),
        (
            {"project": S.SeverityTables(by_code={"heading-missing": "warning"})},
            "warning", S.SOURCE_PROJECT,
        ),
        (
            {"project": S.SeverityTables(
                by_code={"heading-missing": "off"},
                by_kind={"PRD": {"heading-missing": "warning"}},
            )},
            "warning", S.SOURCE_PROJECT_KIND,
        ),
    ],
)
def test_each_layer_wins_over_the_ones_below_it(kwargs, expected_severity, expected_source):
    decision = _policy(**kwargs).resolve("heading-missing", "PRD", ("heading", "prd-metrics"))
    assert (decision.severity, decision.source) == (expected_severity, expected_source)


def test_a_kind_scoped_setting_does_not_reach_another_kind():
    """#140 AC1: warning for PRD while FEATURE stays error."""
    policy = _policy(project=S.SeverityTables(by_kind={"PRD": {"heading-missing": "warning"}}))
    assert policy.resolve("heading-missing", "PRD").severity == "warning"
    assert policy.resolve("heading-missing", "FEATURE").severity == "error"
    assert policy.resolve("heading-missing", None).severity == "error"


def test_an_entry_scoped_setting_does_not_reach_another_entry():
    policy = _policy(entries={"PRD": {("heading", "prd-metrics"): S.EntrySeverity("warning")}})
    assert policy.resolve("heading-missing", "PRD", ("heading", "prd-metrics")).severity == "warning"
    assert policy.resolve("heading-missing", "PRD", ("heading", "prd-overview")).severity == "error"
    assert policy.resolve("heading-missing", "PRD", None).severity == "error"


# ---------------------------------------------------------------------------
# The raise/lower rule
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("kit_value", "project_value"),
    [("warning", "error"), ("off", "warning"), ("off", "error")],
)
def test_a_project_may_always_raise(kit_value, project_value):
    policy = _policy(
        kit=S.SeverityTables(by_code={"toc-missing": kit_value}),
        project=S.SeverityTables(by_code={"toc-missing": project_value}),
    )
    decision = policy.resolve("toc-missing")
    assert decision.severity == project_value
    assert decision.source == S.SOURCE_PROJECT
    assert decision.lowered_from is None


def test_a_project_may_lower_an_unlocked_rule_and_the_lowering_is_recorded():
    policy = _policy(project=S.SeverityTables(by_code={"heading-missing": "warning"}))
    decision = policy.resolve("heading-missing", "PRD")
    assert decision.severity == "warning"
    assert decision.lowered_from == "error"
    assert decision.refused_from is None


def test_a_project_may_not_lower_a_locked_entry_and_the_refusal_is_reported():
    """#140 AC8: the attempt is refused, and the refusal is not silent."""
    policy = _policy(
        project=S.SeverityTables(by_kind={"PRD": {"heading-missing": "off"}}),
        entries={"PRD": {("heading", "prd-metrics"): S.EntrySeverity("error", locked=True)}},
    )
    decision = policy.resolve("heading-missing", "PRD", ("heading", "prd-metrics"))
    assert decision.severity == "error"
    assert decision.source == S.SOURCE_ENTRY
    assert decision.refused_from == "off"
    assert decision.lowered_from is None


def test_a_lock_without_a_severity_protects_the_built_in_default():
    """`locked` alone is meaningful: it pins whatever already applies."""
    policy = _policy(
        project=S.SeverityTables(by_code={"heading-missing": "warning"}),
        entries={"PRD": {("heading", "prd-metrics"): S.EntrySeverity(None, locked=True)}},
    )
    decision = policy.resolve("heading-missing", "PRD", ("heading", "prd-metrics"))
    assert decision.severity == "error"
    assert decision.source == S.SOURCE_DEFAULT
    assert decision.refused_from == "warning"


def test_a_locked_entry_still_accepts_a_raise():
    policy = _policy(
        kit=S.SeverityTables(by_code={"toc-missing": "warning"}),
        project=S.SeverityTables(by_code={"toc-missing": "error"}),
        entries={"PRD": {("heading", "prd-metrics"): S.EntrySeverity("warning", locked=True)}},
    )
    decision = policy.resolve("toc-missing", "PRD", ("heading", "prd-metrics"))
    assert decision.severity == "error"
    assert decision.refused_from is None


def test_declared_overrides_lists_lowerings_from_configuration_not_occurrences():
    """A rule lowered to `off` emits nothing; that is exactly when naming it matters."""
    policy = _policy(project=S.SeverityTables(
        by_code={"heading-missing": "off"},
        by_kind={"FEATURE": {"toc-missing": "error"}},
    ))
    rows = S.declared_overrides(policy)
    assert rows == [{
        "code": "heading-missing",
        "kind": None,
        "entry": None,
        "from": "error",
        "to": "off",
        "applied": True,
        "source": S.SOURCE_PROJECT,
    }]


def test_declared_overrides_is_sorted_by_kind_then_code():
    policy = _policy(project=S.SeverityTables(by_kind={
        "PRD": {"toc-missing": "off", "heading-missing": "off"},
        "FEATURE": {"heading-missing": "off"},
    }))
    rows = S.declared_overrides(policy)
    assert [(row["kind"], row["code"]) for row in rows] == [
        ("FEATURE", "heading-missing"),
        ("PRD", "heading-missing"),
        ("PRD", "toc-missing"),
    ]


# ---------------------------------------------------------------------------
# Applying the policy to findings
# ---------------------------------------------------------------------------

def _finding(code: str, **extra) -> dict:
    return {"type": "constraints", "message": code, "code": code,
            "severity": S.default_severity(code), **extra}


def test_apply_drops_off_findings_and_counts_them():
    policy = _policy(project=S.SeverityTables(by_code={"heading-missing": "off"}))
    outcome = S.apply_policy(policy, [_finding("heading-missing"), _finding("ref-no-definition")])
    assert outcome.suppressed == 1
    assert [f["code"] for f in outcome.errors] == ["ref-no-definition"]
    assert outcome.warnings == []


def test_apply_restamps_and_repartitions():
    policy = _policy(project=S.SeverityTables(by_code={
        "heading-missing": "warning", "toc-stale": "error",
    }))
    outcome = S.apply_policy(policy, [_finding("heading-missing"), _finding("toc-stale")])
    assert [f["code"] for f in outcome.warnings] == ["heading-missing"]
    assert [f["code"] for f in outcome.errors] == ["toc-stale"]
    assert outcome.warnings[0]["severity"] == "warning"
    assert outcome.errors[0]["severity"] == "error"


def test_apply_reads_the_kind_from_the_finding_before_the_caller_default():
    policy = _policy(project=S.SeverityTables(by_kind={"PRD": {"heading-missing": "warning"}}))
    outcome = S.apply_policy(
        policy,
        [_finding("heading-missing", artifact_kind="PRD"), _finding("heading-missing")],
        kind="FEATURE",
    )
    assert len(outcome.warnings) == 1
    assert len(outcome.errors) == 1


def test_apply_is_idempotent():
    """Both the artifact pass and the command pass run it; neither may double-count."""
    policy = _policy(project=S.SeverityTables(by_code={
        "heading-missing": "off", "ref-no-definition": "warning",
    }))
    findings = [_finding("heading-missing"), _finding("ref-no-definition"), _finding("toc-stale")]
    first = S.apply_policy(policy, findings)
    second = S.apply_policy(policy, first.errors + first.warnings)
    assert (first.suppressed, second.suppressed) == (1, 0)
    assert [f["code"] for f in second.errors] == [f["code"] for f in first.errors]
    assert [f["code"] for f in second.warnings] == [f["code"] for f in first.warnings]


def test_apply_records_a_refusal_once_per_rule_not_once_per_finding():
    policy = _policy(
        project=S.SeverityTables(by_kind={"PRD": {"heading-missing": "off"}}),
        entries={"PRD": {("heading", "prd-metrics"): S.EntrySeverity("error", locked=True)}},
    )
    findings = [
        _finding("heading-missing", artifact_kind="PRD", heading_id="prd-metrics"),
        _finding("heading-missing", artifact_kind="PRD", heading_id="prd-metrics"),
    ]
    outcome = S.apply_policy(policy, findings)
    assert len(outcome.errors) == 2
    assert len(outcome.refusals) == 1
    assert outcome.refusals[0]["applied"] is False


def test_apply_with_no_policy_leaves_the_stamped_severity_alone():
    findings = [_finding("heading-missing"), _finding("toc-stale")]
    outcome = S.apply_policy(None, findings)
    assert outcome.suppressed == 0
    assert [f["code"] for f in outcome.errors] == ["heading-missing"]
    assert [f["code"] for f in outcome.warnings] == ["toc-stale"]


def test_an_identifier_finding_is_matched_to_its_entry_by_id_kind():
    policy = _policy(entries={"PRD": {("identifier", "fr"): S.EntrySeverity("warning")}})
    outcome = S.apply_policy(
        policy, [_finding("required-id-kind-missing", artifact_kind="PRD", id_kind="fr")])
    assert len(outcome.warnings) == 1


# ---------------------------------------------------------------------------
# The exit contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("errors", "warnings", "fail_on_warnings", "status", "code", "failed_on"),
    [
        (0, 0, False, "PASS", 0, None),
        (0, 5, False, "PASS", 0, None),
        (3, 0, False, "FAIL", 2, None),
        (3, 5, False, "FAIL", 2, None),
        (0, 5, True, "FAIL", 2, "warnings"),
        (0, 0, True, "PASS", 0, None),
        (3, 5, True, "FAIL", 2, None),
    ],
)
def test_run_verdict_truth_table(errors, warnings, fail_on_warnings, status, code, failed_on):
    verdict = S.run_verdict(errors, warnings, fail_on_warnings=fail_on_warnings)
    assert (verdict.status, verdict.exit_code, verdict.failed_on) == (status, code, failed_on)


@pytest.mark.parametrize("warnings", [0, 1, 271])
def test_without_fail_on_warnings_the_exit_code_ignores_warnings_entirely(warnings):
    """The invariant the whole model rests on, asserted rather than sampled."""
    assert S.run_verdict(0, warnings).exit_code == 0
    assert S.run_verdict(1, warnings).exit_code == 2


def test_validate_toc_keeps_its_third_status():
    assert S.run_verdict(0, 2, warn_status="WARN").status == "WARN"
    assert S.run_verdict(0, 2, warn_status="WARN").exit_code == 0
    assert S.run_verdict(0, 0, warn_status="WARN").status == "PASS"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _load(tmp_path: Path, data: dict):
    path = tmp_path / "constraints.toml"
    path.write_text(toml_utils.dumps(data), encoding="utf-8")
    return C.load_constraints_file(path)


_MINIMAL_KIND = {"identifiers": {"fr": {"required": True}}}


def test_a_kit_validation_table_is_lifted_before_the_artifacts_unwrap(tmp_path):
    kit, errors = _load(tmp_path, {
        "validation": {"severity": {"toc-missing": "warning"}},
        "artifacts": {"PRD": _MINIMAL_KIND},
    })
    assert errors == []
    assert kit.validation.by_code == {"toc-missing": "warning"}
    assert "VALIDATION" not in kit.by_kind


def test_a_validation_table_survives_the_legacy_unwrapped_layout(tmp_path):
    """Without the lift this file fails to load, reading VALIDATION as a kind."""
    kit, errors = _load(tmp_path, {
        "validation": {"severity": {"toc-missing": "warning"}},
        "PRD": _MINIMAL_KIND,
    })
    assert errors == []
    assert kit.validation.by_code == {"toc-missing": "warning"}
    assert set(kit.by_kind) == {"PRD"}


def test_a_per_kind_validation_table_is_parsed(tmp_path):
    kit, errors = _load(tmp_path, {"artifacts": {"PRD": {
        **_MINIMAL_KIND,
        "validation": {"severity": {"heading-number-not-consecutive": "off"}},
    }}})
    assert errors == []
    assert kit.by_kind["PRD"].validation.by_code == {"heading-number-not-consecutive": "off"}


def test_a_kind_inside_a_per_kind_validation_table_is_refused(tmp_path):
    kit, errors = _load(tmp_path, {"artifacts": {"PRD": {
        **_MINIMAL_KIND,
        "validation": {"severity": {"FEATURE": {"toc-missing": "off"}}},
    }}})
    assert kit is None
    assert any("not artifact kinds" in message for message in errors)


def test_a_root_validation_table_may_scope_by_kind(tmp_path):
    kit, errors = _load(tmp_path, {
        "validation": {"severity": {"PRD": {"toc-missing": "off"}}},
        "artifacts": {"PRD": _MINIMAL_KIND},
    })
    assert errors == []
    assert kit.validation.by_kind == {"PRD": {"toc-missing": "off"}}


@pytest.mark.parametrize("bad", ["warn", "ERROR!", "", 3, True])
def test_an_unrecognised_severity_value_fails_the_load(tmp_path, bad):
    """It disables a check, so it must not resolve to 'no opinion'."""
    kit, errors = _load(tmp_path, {
        "validation": {"severity": {"toc-missing": bad}},
        "artifacts": {"PRD": _MINIMAL_KIND},
    })
    assert kit is None
    assert errors and "toc-missing" in errors[0]


def test_an_unknown_validation_key_is_carried_rather_than_dropped(tmp_path):
    kit, errors = _load(tmp_path, {
        "validation": {"severty": {"toc-missing": "off"}},
        "artifacts": {"PRD": _MINIMAL_KIND},
    })
    assert errors == []
    # Fully qualified, so the reported warning names where to look rather than
    # just which word was wrong.
    assert kit.validation.unknown_keys == ("[validation].severty",)
    assert kit.validation.by_code == {}


def test_entry_severity_and_lock_round_trip_on_a_heading(tmp_path):
    kit, errors = _load(tmp_path, {"artifacts": {"PRD": {
        **_MINIMAL_KIND,
        "headings": [{"id": "prd-metrics", "level": 2, "pattern": "Metrics",
                      "severity": "warning", "locked": True}],
    }}})
    assert errors == []
    heading = kit.by_kind["PRD"].headings[0]
    assert (heading.severity, heading.locked) == ("warning", True)


def test_entry_severity_and_lock_round_trip_on_an_id_kind(tmp_path):
    kit, errors = _load(tmp_path, {"artifacts": {"PRD": {
        "identifiers": {"fr": {"required": True, "severity": "warning", "locked": True}},
    }}})
    assert errors == []
    identifier = kit.by_kind["PRD"].defined_id[0]
    assert (identifier.severity, identifier.locked) == ("warning", True)


def test_a_non_boolean_lock_fails_the_load(tmp_path):
    kit, errors = _load(tmp_path, {"artifacts": {"PRD": {
        **_MINIMAL_KIND,
        "headings": [{"id": "x", "level": 2, "pattern": "X", "locked": "yes"}],
    }}})
    assert kit is None
    assert any("locked" in message for message in errors)


def test_an_invalid_entry_severity_fails_the_load(tmp_path):
    kit, errors = _load(tmp_path, {"artifacts": {"PRD": {
        **_MINIMAL_KIND,
        "headings": [{"id": "x", "level": 2, "pattern": "X", "severity": "loud"}],
    }}})
    assert kit is None
    assert any("severity" in message for message in errors)


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------

def test_kit_severity_tables_merge_strictest_wins():
    merged = S.merge_severity_tables([
        S.SeverityTables(by_code={"toc-missing": "off"}, by_kind={"PRD": {"a": "warning"}}),
        S.SeverityTables(by_code={"toc-missing": "warning"}, by_kind={"PRD": {"a": "error"}}),
    ])
    assert merged.by_code == {"toc-missing": "warning"}
    assert merged.by_kind == {"PRD": {"a": "error"}}


def test_strictest_wins_does_not_depend_on_merge_order():
    layers = [
        S.SeverityTables(by_code={"toc-missing": "error"}),
        S.SeverityTables(by_code={"toc-missing": "off"}),
    ]
    assert S.merge_severity_tables(layers).by_code == {"toc-missing": "error"}
    assert S.merge_severity_tables(list(reversed(layers))).by_code == {"toc-missing": "error"}


def test_entry_severities_merge_strictest_and_locks_merge_as_or(tmp_path):
    first = tmp_path / "a.toml"
    second = tmp_path / "b.toml"
    for path, severity, locked in ((first, "warning", True), (second, "error", False)):
        path.write_text(toml_utils.dumps({"artifacts": {"PRD": {
            **_MINIMAL_KIND,
            "headings": [{"id": "prd-metrics", "level": 2, "pattern": "Metrics",
                          "severity": severity, "locked": locked}],
        }}}), encoding="utf-8")
    kit, errors = C.load_constraints_files([first, second])
    assert errors == []
    entries = C.collect_entry_severities([kit])
    assert entries["PRD"][("heading", "prd-metrics")] == S.EntrySeverity(severity="error", locked=True)


def test_build_severity_policy_folds_per_kind_tables_into_the_kit_layer(tmp_path):
    kit, errors = _load(tmp_path, {
        "validation": {"severity": {"toc-missing": "warning"}},
        "artifacts": {"PRD": {
            **_MINIMAL_KIND,
            "validation": {"severity": {"toc-missing": "off"}},
            "headings": [{"id": "prd-metrics", "level": 2, "pattern": "Metrics",
                          "severity": "warning"}],
        }},
    })
    assert errors == []
    policy = C.build_severity_policy([kit])
    assert policy.resolve("toc-missing").source == S.SOURCE_KIT
    assert policy.resolve("toc-missing", "PRD").severity == "off"
    assert policy.resolve("heading-missing", "PRD", ("heading", "prd-metrics")).severity == "warning"


def test_build_severity_policy_tolerates_a_kit_that_declares_nothing():
    """Contexts hand this whatever they loaded, including partial stand-ins."""
    from types import SimpleNamespace

    policy = C.build_severity_policy([SimpleNamespace(by_kind={"PRD": SimpleNamespace()})])
    assert policy.is_configured() is False
    assert policy.resolve("heading-missing", "PRD").severity == "error"


# ---------------------------------------------------------------------------
# End to end, through the real CLI
# ---------------------------------------------------------------------------

_REQUIRED_HEADINGS = [
    {"id": "h1-title", "level": 1, "required": True, "pattern": ".+"},
    {"id": "metrics", "level": 2, "required": True, "pattern": "Metrics"},
]


def _write_project(
    root: Path,
    *,
    kind_constraints: dict,
    core_validation: dict | None = None,
    prd_template: str | None = None,
    prd_body: str | None = None,
):
    """A two-kind project whose PRD and FEATURE are both missing `## Metrics`."""
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
        # The templates satisfy the constraints; only the artifacts below do
        # not. Otherwise the validate-kits gate fails first and `validate`
        # never reaches the policy at all.
        body = prd_template if (kind == "PRD" and prd_template) else f"# {kind}\n\n## Metrics\n"
        (template / "template.md").write_text(body, encoding="utf-8")
    (kit / "constraints.toml").write_text(
        toml_utils.dumps({"artifacts": kind_constraints}), encoding="utf-8")

    core: dict = {"version": "1.0", "project_root": "..",
                  "kits": {"test": {"format": "CFS", "path": "kits/test"}}}
    if core_validation is not None:
        core["validation"] = core_validation
    toml_utils.dump(core, config / "core.toml")
    toml_utils.dump({
        "version": "1.0",
        "project_root": "..",
        "kits": {"test": {"format": "CFS", "path": "kits/test"}},
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
    (architecture / "PRD.md").write_text(prd_body or "# PRD\n\ncontent\n", encoding="utf-8")
    (architecture / "FEATURE.md").write_text("# FEATURE\n\ncontent\n", encoding="utf-8")


def _both_kinds(**extra) -> dict:
    return {
        kind: {"identifiers": {}, "headings": list(_REQUIRED_HEADINGS), **extra.get(kind, {})}
        for kind in ("PRD", "FEATURE")
    }


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


def test_e2e_without_configuration_a_missing_required_heading_fails(tmp_path):
    """#140 AC6: with no severity configuration nothing moves."""
    _write_project(tmp_path, kind_constraints=_both_kinds())
    exit_code, report = _run(tmp_path, ["--json", "validate", "--skip-code"])
    assert exit_code == 2
    assert report["status"] == "FAIL"
    assert report["error_count"] == 2
    assert "suppressed_count" not in report
    assert "severity_overrides" not in report


def test_e2e_a_kind_scoped_project_override_relaxes_one_kind_only(tmp_path):
    """#140 AC1 and AC2: PRD reports a warning, FEATURE still fails."""
    _write_project(
        tmp_path,
        kind_constraints=_both_kinds(),
        core_validation={"severity": {"PRD": {"heading-missing": "warning"}}},
    )
    exit_code, report = _run(tmp_path, ["--json", "validate", "--skip-code"])
    assert exit_code == 2
    assert [w["artifact_kind"] for w in report["warnings"]
            if w["code"] == "heading-missing"] == ["PRD"]
    assert [e["artifact_kind"] for e in report["errors"]
            if e["code"] == "heading-missing"] == ["FEATURE"]


def test_e2e_an_advisory_heading_is_reported_not_silenced(tmp_path):
    """#140 AC3: `severity = "warning"` on the entry, absent section, one warning."""
    _write_project(tmp_path, kind_constraints=_both_kinds(
        PRD={"headings": [
            _REQUIRED_HEADINGS[0],
            {**_REQUIRED_HEADINGS[1], "severity": "warning"},
        ]},
    ))
    exit_code, report = _run(tmp_path, ["--json", "validate", "--skip-code"])
    assert exit_code == 2  # FEATURE still fails
    warnings = [w for w in report["warnings"] if w["code"] == "heading-missing"]
    assert len(warnings) == 1
    assert warnings[0]["severity"] == "warning"
    assert warnings[0]["heading_id"] == "metrics"


def test_e2e_a_warning_only_run_succeeds_and_still_reports_the_warnings(tmp_path):
    """#140 AC3 and AC4: success with warnings, and the list is present on a PASS."""
    _write_project(
        tmp_path,
        kind_constraints=_both_kinds(),
        core_validation={"severity": {"heading-missing": "warning"}},
    )
    exit_code, report = _run(tmp_path, ["--json", "validate", "--skip-code"])
    assert exit_code == 0
    assert report["status"] == "PASS"
    assert report["error_count"] == 0
    assert report["warning_count"] == 2
    assert len(report["warnings"]) == 2
    assert all(w["severity"] == "warning" for w in report["warnings"])


def test_e2e_a_rule_set_to_off_is_counted_not_hidden(tmp_path):
    _write_project(
        tmp_path,
        kind_constraints=_both_kinds(),
        core_validation={"severity": {"heading-missing": "off"}},
    )
    exit_code, report = _run(tmp_path, ["--json", "validate", "--skip-code"])
    assert exit_code == 0
    assert report["error_count"] == 0
    assert report["suppressed_count"] == 2
    assert report["severity_overrides"] == [{
        "code": "heading-missing", "kind": None, "entry": None,
        "from": "error", "to": "off", "applied": True, "source": S.SOURCE_PROJECT,
    }]


@pytest.mark.parametrize(
    ("argv", "core_validation"),
    [
        (["--json", "validate", "--skip-code", "--fail-on-warnings"],
         {"severity": {"heading-missing": "warning"}}),
        (["--json", "validate", "--skip-code"],
         {"fail_on_warnings": True, "severity": {"heading-missing": "warning"}}),
    ],
)
def test_e2e_both_the_flag_and_the_setting_make_warnings_fail(tmp_path, argv, core_validation):
    """#140 AC5."""
    _write_project(tmp_path, kind_constraints=_both_kinds(), core_validation=core_validation)
    exit_code, report = _run(tmp_path, argv)
    assert exit_code == 2
    assert report["status"] == "FAIL"
    assert report["failed_on"] == "warnings"
    assert report["error_count"] == 0


def test_e2e_a_locked_entry_refuses_the_lowering_and_says_so(tmp_path):
    """#140 AC8."""
    _write_project(
        tmp_path,
        kind_constraints=_both_kinds(PRD={"headings": [
            _REQUIRED_HEADINGS[0],
            {**_REQUIRED_HEADINGS[1], "locked": True},
        ]}),
        core_validation={"severity": {"heading-missing": "off"}},
    )
    exit_code, report = _run(tmp_path, ["--json", "validate", "--skip-code"])
    assert exit_code == 2
    assert report["error_count"] == 1
    assert report["suppressed_count"] == 1
    refusals = [row for row in report["severity_overrides"] if row["applied"] is False]
    assert refusals == [{
        "code": "heading-missing", "kind": "PRD", "entry": "heading:metrics",
        "from": "error", "to": "off", "applied": False, "source": S.SOURCE_DEFAULT,
    }]


def test_e2e_explain_severity_names_the_layer(tmp_path):
    """#140 AC7."""
    _write_project(
        tmp_path,
        kind_constraints=_both_kinds(),
        core_validation={"severity": {"PRD": {"heading-missing": "warning"}}},
    )
    exit_code, report = _run(
        tmp_path,
        ["--json", "validate", "--explain-severity", "--kind", "PRD", "--rule", "heading-missing"],
    )
    assert exit_code == 0
    assert report["rules"] == [{
        "code": "heading-missing", "kind": "PRD",
        "severity": "warning", "source": S.SOURCE_PROJECT_KIND,
    }]
    assert report["configured"] is True


def test_e2e_explain_severity_rejects_a_rule_code_that_does_not_exist(tmp_path):
    _write_project(tmp_path, kind_constraints=_both_kinds())
    exit_code, report = _run(
        tmp_path, ["--json", "validate", "--explain-severity", "--rule", "no-such-rule"])
    assert exit_code == 1
    assert report["status"] == "ERROR"


def test_e2e_an_unreadable_severity_setting_stops_the_run(tmp_path):
    _write_project(
        tmp_path,
        kind_constraints=_both_kinds(),
        core_validation={"severity": {"heading-missing": "quiet"}},
    )
    exit_code, report = _run(tmp_path, ["--json", "validate", "--skip-code"])
    assert exit_code == 1
    assert report["status"] == "ERROR"
    assert any("quiet" in message for message in report["errors"])


def test_e2e_a_lowered_heading_rule_no_longer_hides_the_later_phases(tmp_path):
    """The fail-fast gate counts error-severity findings, not findings.

    The PRD here is missing its required `## Metrics` *and* has no TOC. With
    the heading rule at `error` the TOC phase never runs, so `toc-missing` is
    invisible. Lowering the heading rule to `warning` has to reveal it —
    otherwise a relaxation would silently switch a whole phase off, which is
    the failure this model exists to prevent, reappearing one level down.
    """
    constraints = {
        "PRD": {"identifiers": {}, "headings": list(_REQUIRED_HEADINGS)},
        "FEATURE": {"identifiers": {}, "headings": []},
    }
    # Two sections and no `<!-- toc -->`, which is what `toc-missing` needs.
    prd_body = "# PRD\n\n## Alpha\n\ntext\n\n## Beta\n\ntext\n"

    _write_project(tmp_path, kind_constraints=constraints, prd_body=prd_body)
    _, strict = _run(tmp_path, ["--json", "validate", "--skip-code"])
    assert {e["code"] for e in strict["errors"]} == {"heading-missing"}
    assert "toc-missing" not in {e["code"] for e in strict["errors"]}

    _write_project(
        tmp_path,
        kind_constraints=constraints,
        core_validation={"severity": {"heading-missing": "warning"}},
        prd_body=prd_body,
    )
    _, relaxed = _run(tmp_path, ["--json", "validate", "--skip-code"])
    assert {w["code"] for w in relaxed["warnings"]} == {"heading-missing"}
    assert "toc-missing" in {e["code"] for e in relaxed["errors"]}


def test_e2e_validate_kits_reports_unknown_validation_keys_and_a_warning_count(tmp_path):
    constraints = _both_kinds()
    _write_project(tmp_path, kind_constraints=constraints)
    kit_constraints = tmp_path / "kits" / "test" / "constraints.toml"
    kit_constraints.write_text(
        toml_utils.dumps({
            "validation": {"severty": {"toc-missing": "off"}},
            "artifacts": constraints,
        }),
        encoding="utf-8",
    )
    exit_code, report = _run(tmp_path, ["--json", "validate-kits", "--verbose"])
    assert exit_code == 0
    assert report["status"] == "PASS"
    assert report["warning_count"] >= 1
    codes = {
        warning.get("code")
        for result in report["self_check_results"]
        for warning in (result.get("warnings") or [])
    }
    assert "constraints-unknown-key" in codes


# ---------------------------------------------------------------------------
# Review round 1: entry identity, unknown codes, and the passes that were
# settling findings in the wrong order
# ---------------------------------------------------------------------------

def test_a_heading_and_an_id_kind_with_the_same_name_are_different_entries(tmp_path):
    """Sharing a namespace would let one inherit the other's lock."""
    kit, errors = _load(tmp_path, {"artifacts": {"PRD": {
        "identifiers": {"metrics": {"required": True, "severity": "off"}},
        "headings": [{"id": "metrics", "level": 2, "pattern": "Metrics",
                      "severity": "warning", "locked": True}],
    }}})
    assert errors == []
    policy = C.build_severity_policy([kit])
    heading = policy.resolve("heading-missing", "PRD", ("heading", "metrics"))
    identifier = policy.resolve("required-id-kind-missing", "PRD", ("identifier", "metrics"))
    assert (heading.severity, identifier.severity) == ("warning", "off")
    assert policy.entries["PRD"][("heading", "metrics")].locked is True
    assert policy.entries["PRD"][("identifier", "metrics")].locked is False


def test_an_identifier_entry_declared_in_capitals_still_matches_its_findings(tmp_path):
    """Entries are stored as authored; findings lowercase the kind before emitting."""
    kit, errors = _load(tmp_path, {"artifacts": {"PRD": {
        "identifiers": {"FR": {"required": True, "severity": "warning"}},
    }}})
    assert errors == []
    policy = C.build_severity_policy([kit])
    outcome = S.apply_policy(
        policy, [_finding("required-id-kind-missing", artifact_kind="PRD", id_kind="fr")])
    assert len(outcome.warnings) == 1


@pytest.mark.parametrize("table", ["validation", "artifacts"])
def test_a_misspelled_rule_code_is_reported_not_accepted(tmp_path, table):
    """The registry is closed, so a code that is not in it is knowable here."""
    data = {"artifacts": {"PRD": _MINIMAL_KIND}}
    if table == "validation":
        data["validation"] = {"severity": {"headng-missing": "off"}}
    else:
        data["artifacts"]["PRD"] = {
            **_MINIMAL_KIND, "validation": {"severity": {"headng-missing": "off"}}}
    kit, errors = _load(tmp_path, data)
    assert errors == []
    tables = kit.validation if table == "validation" else kit.by_kind["PRD"].validation
    assert tables.by_code == {}
    assert any("headng-missing" in key for key in tables.unknown_keys)


def test_a_blank_key_under_severity_fails_the_load(tmp_path):
    kit, errors = _load(tmp_path, {
        "validation": {"severity": {"   ": "off"}},
        "artifacts": {"PRD": _MINIMAL_KIND},
    })
    assert kit is None
    assert any("blank key" in message for message in errors)


def test_strictest_wins_compares_a_whole_kit_rule_against_another_kits_kind_rule():
    """Merging the two dicts independently never compares them against each other."""
    merged = S.merge_severity_tables([
        S.SeverityTables(by_code={"toc-missing": "error"}),
        S.SeverityTables(by_kind={"PRD": {"toc-missing": "off"}}),
    ])
    assert merged.by_kind["PRD"]["toc-missing"] == "error"


def test_fail_on_warnings_alone_counts_as_configured():
    policy = _policy(project=S.SeverityTables(fail_on_warnings=True))
    assert policy.is_configured() is True
    assert policy.fail_on_warnings is True


def test_e2e_a_lowered_context_finding_no_longer_takes_the_early_exit(tmp_path):
    """Context and language findings arrive after the per-artifact pass.

    Testing the raw list before the policy ran would fail the run on a finding
    the project had configured away — the relaxation making the run stop
    sooner rather than not at all.
    """
    _write_project(
        tmp_path,
        kind_constraints=_both_kinds(),
        core_validation={"severity": {"heading-missing": "warning"}},
        prd_body="# PRD\n\n## Alpha\n\ntext\n\n## Beta\n\ntext\n",
    )
    exit_code, report = _run(tmp_path, ["--json", "validate", "--skip-code"])
    # `toc-missing` is only reachable once the heading gate opens, and the run
    # only reaches the TOC phase because the early exit no longer fires.
    assert "toc-missing" in {e["code"] for e in report["errors"]}
    assert exit_code == 2


def test_e2e_artifact_reports_are_recounted_after_the_policy_settles(tmp_path):
    """A top-level PASS must not contain an artifact still marked FAIL."""
    _write_project(
        tmp_path,
        kind_constraints=_both_kinds(),
        core_validation={"severity": {"heading-missing": "warning"}},
    )
    exit_code, report = _run(tmp_path, ["--json", "validate", "--skip-code", "--verbose"])
    assert exit_code == 0
    assert report["status"] == "PASS"
    statuses = {item["status"] for item in report.get("artifacts", report.get("artifact_reports", []))} \
        if ("artifacts" in report or "artifact_reports" in report) else set()
    assert "FAIL" not in statuses
    assert report["warning_count"] == 2


def test_e2e_a_refusal_is_reported_once_across_both_policy_passes(tmp_path):
    """Both passes meet the same surviving finding; the reader sees one line."""
    _write_project(
        tmp_path,
        kind_constraints=_both_kinds(PRD={"headings": [
            _REQUIRED_HEADINGS[0],
            {**_REQUIRED_HEADINGS[1], "locked": True},
        ]}),
        core_validation={"severity": {"heading-missing": "off"}},
    )
    _, report = _run(tmp_path, ["--json", "validate", "--skip-code"])
    refusals = [row for row in report["severity_overrides"] if row["applied"] is False]
    assert len(refusals) == 1


def test_e2e_explain_severity_runs_while_the_kit_gate_would_fail(tmp_path):
    """Asking which severity applies must not require a healthy kit."""
    _write_project(tmp_path, kind_constraints=_both_kinds())
    # Break the kit's own template so the validate-kits gate fails.
    (tmp_path / "kits" / "test" / "artifacts" / "PRD" / "template.md").write_text(
        "# PRD\n", encoding="utf-8")
    gate_code, _ = _run(tmp_path, ["--json", "validate", "--skip-code"])
    assert gate_code == 2

    exit_code, report = _run(
        tmp_path, ["--json", "validate", "--explain-severity", "--rule", "heading-missing"])
    assert exit_code == 0
    assert report["status"] == "PASS"


def test_e2e_explain_severity_reports_entry_level_overrides(tmp_path):
    _write_project(tmp_path, kind_constraints=_both_kinds(PRD={"headings": [
        _REQUIRED_HEADINGS[0],
        {**_REQUIRED_HEADINGS[1], "severity": "warning"},
    ]}))
    exit_code, report = _run(
        tmp_path,
        ["--json", "validate", "--explain-severity", "--kind", "PRD", "--rule", "heading-missing"],
    )
    assert exit_code == 0
    entry_rows = [row for row in report["rules"] if row.get("entry")]
    assert entry_rows == [{
        "code": "heading-missing", "kind": "PRD", "entry": "heading:metrics",
        "severity": "warning", "source": S.SOURCE_ENTRY,
    }]


def test_e2e_a_project_severity_for_an_unknown_kind_is_refused(tmp_path):
    """A misspelled kind is inert, and the usual direction is a raise.

    It is not a rule code, so it resolves to nothing and appears in no
    override report — leaving the author believing a rule now blocks when it
    does not. Refused rather than merely surfaced, matching the rule for
    everything else in `core.toml`.
    """
    _write_project(
        tmp_path,
        kind_constraints=_both_kinds(),
        core_validation={"severity": {"PRDD": {"heading-missing": "error"}}},
    )
    exit_code, report = _run(tmp_path, ["--json", "validate", "--skip-code"])
    assert exit_code == 1
    assert report["status"] == "ERROR"
    assert any("PRDD" in message for message in report["errors"])


def test_e2e_explain_severity_includes_a_registered_kind_no_kit_constrains(tmp_path):
    """Registered but unconstrained is legitimate, and must not be refused."""
    _write_project(
        tmp_path,
        kind_constraints=_both_kinds(),
        core_validation={"severity": {"GLOSSARY": {"heading-missing": "warning"}}},
    )
    config = tmp_path / "adapter" / "config"
    registry = toml_utils.load(config / "artifacts.toml")
    registry["systems"][0]["artifacts"].append(
        {"path": "architecture/GLOSSARY.md", "kind": "GLOSSARY"})
    toml_utils.dump(registry, config / "artifacts.toml")
    (tmp_path / "architecture" / "GLOSSARY.md").write_text("# GLOSSARY\n", encoding="utf-8")

    exit_code, report = _run(
        tmp_path, ["--json", "validate", "--explain-severity", "--rule", "heading-missing"])
    assert exit_code == 0
    assert "GLOSSARY" in {row["kind"] for row in report["rules"]}


@pytest.mark.parametrize("flag", ["--kind", "--rule"])
def test_e2e_kind_and_rule_are_refused_without_explain_severity(tmp_path, flag):
    """They narrow an explanation; they have never filtered what is validated."""
    _write_project(tmp_path, kind_constraints=_both_kinds())
    with pytest.raises(SystemExit) as excinfo:
        _run(tmp_path, ["--json", "validate", "--skip-code", flag, "PRD"])
    assert excinfo.value.code == 2


def test_e2e_an_empty_registry_still_reports_a_project_lowering(tmp_path):
    """A lowering is a property of the configuration, not of what was found."""
    _write_project(
        tmp_path,
        kind_constraints=_both_kinds(),
        core_validation={"severity": {"heading-missing": "off"}},
    )
    artifacts = tmp_path / "adapter" / "config" / "artifacts.toml"
    artifacts.write_text(
        toml_utils.dumps({
            "version": "1.0", "project_root": "..",
            "kits": {"test": {"format": "CFS", "path": "kits/test"}},
            "systems": [{"name": "Test", "slug": "test", "kit": "test", "artifacts": []}],
        }),
        encoding="utf-8",
    )
    exit_code, report = _run(tmp_path, ["--json", "validate", "--skip-code"])
    assert exit_code == 0
    assert report["artifacts_validated"] == 0
    assert report["severity_overrides"] == [{
        "code": "heading-missing", "kind": None, "entry": None,
        "from": "error", "to": "off", "applied": True, "source": S.SOURCE_PROJECT,
    }]


def test_e2e_a_kit_honours_its_own_severity_when_checking_its_own_examples(tmp_path):
    """A kit that declares a rule advisory means it for its examples too."""
    constraints = _both_kinds()
    _write_project(tmp_path, kind_constraints=constraints)
    kit_dir = tmp_path / "kits" / "test"
    # The example is missing the required section the kit declares advisory.
    example = kit_dir / "artifacts" / "PRD" / "examples"
    example.mkdir(parents=True, exist_ok=True)
    (example / "example.md").write_text("# PRD\n", encoding="utf-8")
    constraints["PRD"] = {
        **constraints["PRD"],
        "validation": {"severity": {"heading-missing": "warning"}},
    }
    (kit_dir / "constraints.toml").write_text(
        toml_utils.dumps({"artifacts": constraints}), encoding="utf-8")

    exit_code, report = _run(tmp_path, ["--json", "validate-kits", "--verbose"])
    assert exit_code == 0
    assert report["status"] == "PASS"
    assert report["warning_count"] >= 1


def test_e2e_validate_surfaces_a_kit_warning_from_the_passing_gate(tmp_path):
    """A gate that lets the run proceed still has something to report."""
    constraints = _both_kinds()
    _write_project(tmp_path, kind_constraints=constraints)
    (tmp_path / "kits" / "test" / "constraints.toml").write_text(
        toml_utils.dumps({
            "validation": {"severty": {"toc-missing": "off"}},
            "artifacts": constraints,
        }),
        encoding="utf-8",
    )
    _, report = _run(tmp_path, ["--json", "validate", "--skip-code"])
    assert "constraints-unknown-key" in {w["code"] for w in report["warnings"]}


def test_e2e_validate_kits_by_path_reports_unknown_keys_too(tmp_path):
    """Path mode is a separate entry point converging on the same builder."""
    constraints = _both_kinds()
    _write_project(tmp_path, kind_constraints=constraints)
    (tmp_path / "kits" / "test" / "constraints.toml").write_text(
        toml_utils.dumps({
            "validation": {"severty": {"toc-missing": "off"}},
            "artifacts": constraints,
        }),
        encoding="utf-8",
    )
    exit_code, report = _run(tmp_path, ["--json", "validate-kits", "kits/test", "--verbose"])
    assert exit_code == 0
    assert report["warning_count"] >= 1
    codes = {
        warning.get("code")
        for result in report.get("self_check_results", [])
        for warning in (result.get("warnings") or [])
    }
    assert "constraints-unknown-key" in codes


def test_e2e_validate_toc_fail_on_warnings_marks_the_file_too(tmp_path):
    """An aggregate FAIL with every file still reading WARN is unreadable."""
    doc = tmp_path / "doc.md"
    doc.write_text("# Title\n\n## Alpha\n\n<!-- toc -->\n\n- [Alpha](#alpha)\n\n<!-- /toc -->\n"
                   + "\n".join(f"line {i}" for i in range(400)) + "\n", encoding="utf-8")
    passing, before = _run(tmp_path, ["--json", "validate-toc", str(doc)])
    assert passing == 0
    assert before["warning_count"] >= 1
    assert before["status"] == "WARN"

    exit_code, report = _run(
        tmp_path, ["--json", "validate-toc", str(doc), "--fail-on-warnings"])
    assert exit_code == 2
    assert report["status"] == "FAIL"
    assert report["failed_on"] == "warnings"
    assert [r["status"] for r in report["results"]] == ["FAIL"]


# ---------------------------------------------------------------------------
# Review round 2
# ---------------------------------------------------------------------------

def test_declared_overrides_finds_an_entry_refusal_under_a_whole_project_setting():
    """The entry's own kind has to travel with its key.

    A whole-project setting has no kind of its own. Resolving its entries
    without one made every entry-specific override invisible, because the
    lookup needs the kind to find the entry at all — so a locked entry's
    refusal went unreported for exactly the settings that reach furthest.
    """
    policy = _policy(
        project=S.SeverityTables(by_code={"heading-missing": "off"}),
        entries={"PRD": {("heading", "prd-metrics"): S.EntrySeverity("error", locked=True)}},
    )
    rows = S.declared_overrides(policy)
    assert [(r["kind"], r["entry"], r["applied"]) for r in rows] == [
        (None, None, True),
        ("PRD", "heading:prd-metrics", False),
    ]


def test_declared_overrides_still_collapses_entries_that_merely_inherit():
    policy = _policy(
        project=S.SeverityTables(by_code={"heading-missing": "warning"}),
        entries={"PRD": {
            ("heading", "a"): S.EntrySeverity(None, locked=False),
            ("heading", "b"): S.EntrySeverity(None, locked=False),
        }},
    )
    rows = S.declared_overrides(policy)
    assert [(r["kind"], r["entry"]) for r in rows] == [(None, None)]


def test_e2e_a_suppressed_finding_in_a_kit_example_is_counted_per_kind(tmp_path):
    """The kit's own policy can switch a rule off; the count must not vanish."""
    constraints = _both_kinds()
    _write_project(tmp_path, kind_constraints=constraints)
    kit_dir = tmp_path / "kits" / "test"
    examples = kit_dir / "artifacts" / "PRD" / "examples"
    examples.mkdir(parents=True, exist_ok=True)
    (examples / "example.md").write_text("# PRD\n", encoding="utf-8")
    constraints["PRD"] = {
        **constraints["PRD"],
        "validation": {"severity": {"heading-missing": "off"}},
    }
    (kit_dir / "constraints.toml").write_text(
        toml_utils.dumps({"artifacts": constraints}), encoding="utf-8")

    exit_code, report = _run(tmp_path, ["--json", "validate-kits", "--verbose"])
    assert exit_code == 0
    prd = [r for r in report["self_check_results"] if r.get("kind") == "PRD"]
    assert [r.get("suppressed_count") for r in prd] == [1]
    # Deliberately per-kind only: `suppressed_count` at the top level is part
    # of `validate`'s report contract, not `validate-kits`'.
    assert "suppressed_count" not in report


def test_e2e_an_empty_registry_still_reports_a_kit_warning(tmp_path):
    """The run where nothing else would mention it."""
    constraints = _both_kinds()
    _write_project(tmp_path, kind_constraints=constraints)
    (tmp_path / "kits" / "test" / "constraints.toml").write_text(
        toml_utils.dumps({
            "validation": {"severty": {"toc-missing": "off"}},
            "artifacts": constraints,
        }),
        encoding="utf-8",
    )
    toml_utils.dump({
        "version": "1.0", "project_root": "..",
        "kits": {"test": {"format": "CFS", "path": "kits/test"}},
        "systems": [{"name": "Test", "slug": "test", "kit": "test", "artifacts": []}],
    }, tmp_path / "adapter" / "config" / "artifacts.toml")

    exit_code, report = _run(tmp_path, ["--json", "validate", "--skip-code"])
    assert exit_code == 0
    assert report["artifacts_validated"] == 0
    assert "constraints-unknown-key" in {w["code"] for w in report["warnings"]}


def test_e2e_an_empty_registry_honours_fail_on_warnings(tmp_path):
    constraints = _both_kinds()
    _write_project(tmp_path, kind_constraints=constraints)
    (tmp_path / "kits" / "test" / "constraints.toml").write_text(
        toml_utils.dumps({
            "validation": {"severty": {"toc-missing": "off"}},
            "artifacts": constraints,
        }),
        encoding="utf-8",
    )
    toml_utils.dump({
        "version": "1.0", "project_root": "..",
        "kits": {"test": {"format": "CFS", "path": "kits/test"}},
        "systems": [{"name": "Test", "slug": "test", "kit": "test", "artifacts": []}],
    }, tmp_path / "adapter" / "config" / "artifacts.toml")

    exit_code, report = _run(
        tmp_path, ["--json", "validate", "--skip-code", "--fail-on-warnings"])
    assert exit_code == 2
    assert report["failed_on"] == "warnings"


def test_e2e_the_kit_gate_runs_after_the_artifact_resolves_its_context(tmp_path):
    """The gate must judge the kits of the source actually being validated."""
    _write_project(tmp_path, kind_constraints=_both_kinds())
    # Break the kit so the gate has something to say, and confirm it still
    # fires on the resolved context rather than being skipped or run early.
    (tmp_path / "kits" / "test" / "artifacts" / "PRD" / "template.md").write_text(
        "# PRD\n", encoding="utf-8")
    exit_code, report = _run(
        tmp_path, ["--json", "validate", "--skip-code", "--artifact", "architecture/PRD.md"])
    assert exit_code == 2
    assert "validate-kits failed" in str(report.get("message", ""))


# ---------------------------------------------------------------------------
# Review round 3: specificity within a kit, strictness between kits
# ---------------------------------------------------------------------------

def _severity_kit(whole: dict | None = None, per_kind: dict | None = None) -> C.KitConstraints:
    by_kind = {
        kind: C.ArtifactKindConstraints(
            name=None, description=None, defined_id=[],
            validation=S.SeverityTables(by_code=table))
        for kind, table in (per_kind or {}).items()
    }
    return C.KitConstraints(
        by_kind=by_kind, validation=S.SeverityTables(by_code=whole or {}))


@pytest.mark.parametrize(
    ("label", "kits", "expected"),
    [
        (
            "one kit: its own per-kind table overrides its own whole-kit table",
            [_severity_kit(whole={"toc-missing": "warning"},
                           per_kind={"PRD": {"toc-missing": "off"}})],
            "off",
        ),
        (
            "two kits: a whole-kit error is not relaxed by another kit's PRD off",
            [_severity_kit(whole={"toc-missing": "error"}),
             _severity_kit(per_kind={"PRD": {"toc-missing": "off"}})],
            "error",
        ),
        (
            "and the answer does not depend on which kit loaded first",
            [_severity_kit(per_kind={"PRD": {"toc-missing": "off"}}),
             _severity_kit(whole={"toc-missing": "error"})],
            "error",
        ),
        (
            "two kits, both kind-scoped: the stricter wins",
            [_severity_kit(per_kind={"PRD": {"toc-missing": "off"}}),
             _severity_kit(per_kind={"PRD": {"toc-missing": "warning"}})],
            "warning",
        ),
        (
            "a kind-scoped rule with no rival applies as written",
            [_severity_kit(per_kind={"PRD": {"toc-missing": "warning"}})],
            "warning",
        ),
    ],
)
def test_specificity_decides_within_a_kit_and_strictness_between_kits(label, kits, expected):
    """Two different questions that a single strictest-wins merge conflates.

    Within one kit, a per-kind table is the author's more specific instruction
    and must win — otherwise declaring `warning` generally and `off` for PRD
    silently yields `warning` for PRD, and per-kind tables are pointless.

    Between kits, nobody has agreed to be overruled, so the stricter opinion
    wins even across the whole-kit/per-kind boundary.
    """
    assert C.build_severity_policy(kits).resolve("toc-missing", "PRD").severity == expected


# ---------------------------------------------------------------------------
# Review round 4: what a terminal reader actually sees
# ---------------------------------------------------------------------------

def _run_human(root: Path, argv: list[str]) -> tuple[int, str]:
    """Drive the CLI in human mode and capture what a terminal would show."""
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


def test_e2e_explain_severity_renders_its_table_in_human_mode(tmp_path):
    """Without a human formatter the whole answer collapses to `Done (PASS)`."""
    _write_project(
        tmp_path,
        kind_constraints=_both_kinds(),
        core_validation={"severity": {"PRD": {"heading-missing": "warning"}}},
    )
    exit_code, out = _run_human(
        tmp_path,
        ["validate", "--explain-severity", "--kind", "PRD", "--rule", "heading-missing"],
    )
    assert exit_code == 0
    assert "heading-missing" in out
    assert "warning" in out
    assert S.SOURCE_PROJECT_KIND in out
    assert out.strip() != "✓ Done (PASS)"


def test_e2e_explain_severity_human_mode_names_a_lowering(tmp_path):
    _write_project(
        tmp_path,
        kind_constraints=_both_kinds(),
        core_validation={"severity": {"heading-missing": "off"}},
    )
    _, out = _run_human(tmp_path, ["validate", "--explain-severity", "--rule", "heading-missing"])
    assert "error -> off" in out
    assert "lowered" in out


def test_e2e_validate_kits_human_mode_names_a_suppression(tmp_path):
    """A kit that switched a rule off must not read like a clean one."""
    constraints = _both_kinds()
    _write_project(tmp_path, kind_constraints=constraints)
    kit_dir = tmp_path / "kits" / "test"
    examples = kit_dir / "artifacts" / "PRD" / "examples"
    examples.mkdir(parents=True, exist_ok=True)
    (examples / "example.md").write_text("# PRD\n", encoding="utf-8")
    constraints["PRD"] = {
        **constraints["PRD"],
        "validation": {"severity": {"heading-missing": "off"}},
    }
    (kit_dir / "constraints.toml").write_text(
        toml_utils.dumps({"artifacts": constraints}), encoding="utf-8")

    exit_code, out = _run_human(tmp_path, ["validate-kits", "--verbose"])
    assert exit_code == 0
    assert "suppressed" in out


def test_e2e_a_lowered_reference_rule_keeps_its_target_path(tmp_path):
    """The migration path has to stay actionable, not just non-blocking."""
    constraints = {
        "PRD": {
            "identifiers": {"fr": {
                "required": True,
                "template": "cpt-{system}-fr-{slug}",
                "to_code": False,
                "references": {"FEATURE": {"coverage": True}},
            }},
        },
        "FEATURE": {"identifiers": {}},
    }
    # The definition is checked, or the coverage rule skips it. FEATURE carries
    # an unrelated reference so its kind counts as present in scope — without
    # one the rule reports `ref-target-not-in-scope` instead.
    prd = ("# PRD\n\n<!-- toc -->\n\n- [Metrics](#metrics)\n\n<!-- /toc -->\n\n"
           "## Metrics\n\n- [x] `p1` - **ID**: `cpt-test-fr-alpha`\n")
    feature = ("# FEATURE\n\n<!-- toc -->\n\n- [Metrics](#metrics)\n\n<!-- /toc -->\n\n"
               "## Metrics\n\nrefs `cpt-test-fr-beta`\n")
    for core_validation, bucket in (
        (None, "errors"),
        ({"severity": {"ref-missing-from-kind": "warning"}}, "warnings"),
    ):
        _write_project(
            tmp_path,
            kind_constraints=constraints,
            core_validation=core_validation,
            prd_template="# PRD\n\n## Metrics\n\n**ID**: `cpt-{system}-fr-{slug}`\n",
            prd_body=prd,
        )
        # `coverage = true` means the FEATURE template must give authors a
        # place to write the reference, or the kit gate fails before validate
        # ever reaches the policy.
        (tmp_path / "kits" / "test" / "artifacts" / "FEATURE" / "template.md").write_text(
            "# FEATURE\n\n## Metrics\n\nrefs `cpt-{system}-fr-{slug}`\n", encoding="utf-8")
        (tmp_path / "architecture" / "FEATURE.md").write_text(feature, encoding="utf-8")
        _, report = _run(tmp_path, ["--json", "validate", "--skip-code", "--verbose"])
        findings = [f for f in report[bucket] if f.get("code") == "ref-missing-from-kind"]
        assert findings, f"expected a ref-missing-from-kind finding in {bucket}"
        # Whichever list policy put it in, the remediation hint travels with it.
        assert all(
            "target_artifact_path" in f or "target_artifact_suggested_path" in f
            for f in findings
        ), f"{bucket} finding lost its target path"


def _write_two_kit_project(root: Path) -> None:
    """A project with two registered kits holding conflicting severity opinions.

    Kit `alpha` says `heading-missing` is a warning everywhere. Kit `beta`
    says it is an error for PRD. Both are registered, so both contribute to one
    merged policy regardless of which kit a system names.
    """
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / "AGENTS.md").write_text(
        '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "adapter"\n```\n'
        "<!-- /@cf:root-agents -->\n",
        encoding="utf-8",
    )
    config = root / "adapter" / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "AGENTS.md").write_text("# Test adapter\n", encoding="utf-8")

    for slug, extra in (("alpha", "whole-kit"), ("beta", "per-kind")):
        kit = root / "kits" / slug
        for kind in ("PRD", "FEATURE"):
            template = kit / "artifacts" / kind
            template.mkdir(parents=True, exist_ok=True)
            (template / "template.md").write_text(f"# {kind}\n\n## Metrics\n", encoding="utf-8")
        kinds: dict = {
            kind: {"identifiers": {}, "headings": list(_REQUIRED_HEADINGS)}
            for kind in ("PRD", "FEATURE")
        }
        data: dict = {"artifacts": kinds}
        if extra == "whole-kit":
            data["validation"] = {"severity": {"heading-missing": "warning"}}
        else:
            kinds["PRD"]["validation"] = {"severity": {"heading-missing": "error"}}
        (kit / "constraints.toml").write_text(toml_utils.dumps(data), encoding="utf-8")

    kits = {slug: {"format": "CFS", "path": f"kits/{slug}"} for slug in ("alpha", "beta")}
    toml_utils.dump(
        {"version": "1.0", "project_root": "..", "kits": kits}, config / "core.toml")
    toml_utils.dump({
        "version": "1.0",
        "project_root": "..",
        "kits": kits,
        "systems": [{
            "name": "Test", "slug": "test", "kit": "alpha",
            "artifacts": [
                {"path": "architecture/PRD.md", "kind": "PRD"},
                {"path": "architecture/FEATURE.md", "kind": "FEATURE"},
            ],
        }],
    }, config / "artifacts.toml")

    architecture = root / "architecture"
    architecture.mkdir(parents=True, exist_ok=True)
    (architecture / "PRD.md").write_text("# PRD\n\ncontent\n", encoding="utf-8")
    (architecture / "FEATURE.md").write_text("# FEATURE\n\ncontent\n", encoding="utf-8")


def test_e2e_two_registered_kits_merge_their_conflicting_severities(tmp_path):
    """Cross-kit merging through the whole pipeline, not just the merge function.

    The unit matrix proves the rule; this proves `validate` reaches it —
    registration, constraints loading, policy assembly and the report. Those
    are the steps a merge-level test cannot see, and they are where this PR
    has needed the most correction.
    """
    _write_two_kit_project(tmp_path)
    exit_code, report = _run(tmp_path, ["--json", "validate", "--skip-code", "--verbose"])

    # PRD: kit beta's per-kind `error` beats kit alpha's whole-kit `warning`,
    # because between kits the stricter opinion wins.
    assert [(f["code"], f["artifact_kind"]) for f in report["errors"]] == [
        ("heading-missing", "PRD")]
    # FEATURE: only kit alpha has an opinion, so its `warning` applies as written.
    assert [(f["code"], f["artifact_kind"]) for f in report["warnings"]] == [
        ("heading-missing", "FEATURE")]
    assert (report["status"], report["error_count"], report["warning_count"]) == ("FAIL", 1, 1)
    assert exit_code == 2


def test_e2e_explain_severity_shows_both_kits_contributions(tmp_path):
    """The same merge, read back through the command that reports it."""
    _write_two_kit_project(tmp_path)
    exit_code, report = _run(
        tmp_path, ["--json", "validate", "--explain-severity", "--rule", "heading-missing"])
    assert exit_code == 0
    assert [(r["kind"], r["severity"], r["source"]) for r in report["rules"]] == [
        ("FEATURE", "warning", S.SOURCE_KIT),
        ("PRD", "error", S.SOURCE_KIT_KIND),
    ]


# ---------------------------------------------------------------------------
# Review round 5
# ---------------------------------------------------------------------------

def test_parsing_one_kit_does_not_judge_an_artifact_kind_it_cannot_see(tmp_path):
    """A kit file is parsed alone, and alone it cannot tell scoping from a typo.

    In a multi-kit project one kit may legitimately scope a severity to a kind
    a companion kit declares. Judging that here would strip a working setting
    and call it a mistake, so the check lives where every kit is in view.
    """
    kit, errors = _load(tmp_path, {
        "validation": {"severity": {"FEATURE": {"heading-missing": "error"}}},
        "artifacts": {"PRD": _MINIMAL_KIND},
    })
    assert errors == []
    assert kit.validation.by_kind == {"FEATURE": {"heading-missing": "error"}}
    assert kit.validation.unknown_keys == ()


def test_one_kit_may_scope_a_severity_to_a_kind_another_kit_declares(tmp_path):
    """The composition resolves it, and nothing reports it as unknown."""
    alpha = tmp_path / "alpha.toml"
    beta = tmp_path / "beta.toml"
    alpha.write_text(toml_utils.dumps({
        "validation": {"severity": {"FEATURE": {"heading-missing": "warning"}}},
        "artifacts": {"PRD": _MINIMAL_KIND},
    }), encoding="utf-8")
    beta.write_text(toml_utils.dumps({"artifacts": {"FEATURE": _MINIMAL_KIND}}), encoding="utf-8")

    kit_a, errors_a = C.load_constraints_file(alpha)
    kit_b, errors_b = C.load_constraints_file(beta)
    assert (errors_a, errors_b) == ([], [])
    policy = C.build_severity_policy([kit_a, kit_b])
    assert policy.resolve("heading-missing", "FEATURE").severity == "warning"


def test_a_kit_severity_for_a_declared_kind_survives(tmp_path):
    kit, errors = _load(tmp_path, {
        "validation": {"severity": {"PRD": {"heading-missing": "warning"}}},
        "artifacts": {"PRD": _MINIMAL_KIND},
    })
    assert errors == []
    assert kit.validation.by_kind == {"PRD": {"heading-missing": "warning"}}
    assert kit.validation.unknown_keys == ()


def test_e2e_a_kit_naming_an_unknown_kind_warns_through_validate_kits(tmp_path):
    constraints = _both_kinds()
    _write_project(tmp_path, kind_constraints=constraints)
    (tmp_path / "kits" / "test" / "constraints.toml").write_text(
        toml_utils.dumps({
            "validation": {"severity": {"PRDD": {"heading-missing": "error"}}},
            "artifacts": constraints,
        }),
        encoding="utf-8",
    )
    exit_code, report = _run(tmp_path, ["--json", "validate-kits", "--verbose"])
    assert exit_code == 0
    codes = {
        warning.get("code")
        for result in report["self_check_results"]
        for warning in (result.get("warnings") or [])
    }
    assert "constraints-unknown-key" in codes


def test_e2e_explain_severity_human_table_is_capped(tmp_path):
    """Every other listing this command prints truncates; so does this one."""
    _write_project(tmp_path, kind_constraints=_both_kinds())
    exit_code, out = _run_human(tmp_path, ["validate", "--explain-severity"])
    assert exit_code == 0
    # Two kinds over 85 rule codes is far past the cap.
    assert "more rule(s)" in out
    assert "--kind/--rule" in out


def test_e2e_explain_severity_human_table_is_not_capped_when_it_fits(tmp_path):
    _write_project(tmp_path, kind_constraints=_both_kinds())
    exit_code, out = _run_human(
        tmp_path, ["validate", "--explain-severity", "--rule", "heading-missing"])
    assert exit_code == 0
    assert "more rule(s)" not in out


# ---------------------------------------------------------------------------
# Review round 6
# ---------------------------------------------------------------------------

def test_e2e_a_cross_kit_severity_scope_is_not_reported_as_unknown(tmp_path):
    """The case the per-kit check used to strip and misreport as a typo."""
    _write_two_kit_project(tmp_path)
    # Kit `alpha` declares PRD and FEATURE itself, so scope to a kind only a
    # companion could provide by removing it from alpha's own artifacts.
    alpha = tmp_path / "kits" / "alpha" / "constraints.toml"
    data = toml_utils.load(alpha)
    data["artifacts"].pop("FEATURE")
    data["validation"] = {"severity": {"FEATURE": {"heading-missing": "warning"}}}
    alpha.write_text(toml_utils.dumps(data), encoding="utf-8")

    exit_code, report = _run(tmp_path, ["--json", "validate-kits", "--verbose"])
    assert exit_code == 0
    codes = {
        warning.get("code")
        for result in report["self_check_results"]
        for warning in (result.get("warnings") or [])
    }
    assert "constraints-unknown-key" not in codes


def test_e2e_validate_kits_by_path_does_not_judge_artifact_kinds(tmp_path):
    """Standalone validation cannot see siblings, so it does not guess."""
    constraints = _both_kinds()
    _write_project(tmp_path, kind_constraints=constraints)
    (tmp_path / "kits" / "test" / "constraints.toml").write_text(
        toml_utils.dumps({
            "validation": {"severity": {"GLOSSARY": {"heading-missing": "warning"}}},
            "artifacts": constraints,
        }),
        encoding="utf-8",
    )
    exit_code, report = _run(tmp_path, ["--json", "validate-kits", "kits/test", "--verbose"])
    assert exit_code == 0
    codes = {
        warning.get("code")
        for result in report.get("self_check_results", [])
        for warning in (result.get("warnings") or [])
    }
    assert "constraints-unknown-key" not in codes


def test_human_explain_severity_prints_overrides_with_no_matching_rules(capsys):
    """The empty-rules path must still say what the project lowered."""
    from studio.commands import validate as validate_cmd
    from studio.utils.ui import is_json_mode, set_json_mode

    saved = is_json_mode()
    try:
        set_json_mode(False)
        validate_cmd._human_explain_severity({
            "status": "PASS",
            "configured": True,
            "fail_on_warnings": False,
            "rules": [],
            "severity_overrides": [{
                "code": "heading-missing", "kind": "PRD", "entry": None,
                "from": "error", "to": "off", "applied": True, "source": "project-kind",
            }],
        })
    finally:
        set_json_mode(saved)
    out = capsys.readouterr().out
    assert "No rules matched." in out
    assert "heading-missing" in out
    assert "error -> off" in out


# ---------------------------------------------------------------------------
# Review round 7
# ---------------------------------------------------------------------------

def _scope_alpha_to_a_companion_kind(root: Path) -> None:
    """Make kit `alpha` scope a severity to FEATURE, which only `beta` declares."""
    alpha = root / "kits" / "alpha" / "constraints.toml"
    data = toml_utils.load(alpha)
    data["artifacts"].pop("FEATURE")
    data["validation"] = {"severity": {"FEATURE": {"heading-missing": "warning"}}}
    alpha.write_text(toml_utils.dumps(data), encoding="utf-8")


def _unknown_key_codes(report: dict) -> set:
    return {
        warning.get("code")
        for result in report.get("self_check_results", [])
        for warning in (result.get("warnings") or [])
    }


def test_e2e_a_kit_filtered_run_does_not_judge_artifact_kinds(tmp_path):
    """`--kit` hides the sibling a kind comes from, so it must not guess.

    A third path through the check, distinct from both the unfiltered run and
    path mode: registered mode with the kit list narrowed. Narrowing makes the
    companion invisible, and judging on a partial view would report a working
    cross-kit scope as a typo.
    """
    _write_two_kit_project(tmp_path)
    _scope_alpha_to_a_companion_kind(tmp_path)
    exit_code, report = _run(tmp_path, ["--json", "validate-kits", "--kit", "alpha", "--verbose"])
    assert exit_code == 0
    assert "constraints-unknown-key" not in _unknown_key_codes(report)


def test_e2e_an_unfiltered_run_still_reports_a_kind_no_kit_declares(tmp_path):
    """The other side of the same condition, so neither can drift alone."""
    _write_two_kit_project(tmp_path)
    alpha = tmp_path / "kits" / "alpha" / "constraints.toml"
    data = toml_utils.load(alpha)
    data["validation"] = {"severity": {"GLOSSARY": {"heading-missing": "warning"}}}
    alpha.write_text(toml_utils.dumps(data), encoding="utf-8")

    exit_code, report = _run(tmp_path, ["--json", "validate-kits", "--verbose"])
    assert exit_code == 0
    assert "constraints-unknown-key" in _unknown_key_codes(report)
