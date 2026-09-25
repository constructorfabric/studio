"""A traceability identifier written as a markdown link.

A reference may be spelled bare or as ``[`cpt-id`](target)``; both name the same
node, because the node is the id string. A *definition* may only be spelled bare,
and a link-form one is reported rather than quietly filed as a reference to itself.

Pins issue #177 AC1-AC3 and the narrowness of the accepted form.
"""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.commands.where_used import cmd_where_used
from studio.utils import error_codes as EC
from studio.utils import toml_utils
from studio.utils.constraints import (
    ArtifactRecord,
    _validate_cdsl_structure,
    build_severity_policy,
    cross_validate_artifacts,
    load_constraints_file,
    parse_kit_constraints,
    validate_artifact_file,
)
from studio.utils.document import LINK_FORM_DEFINITION, scan_cpt_id_lines
from studio.utils.fixing import enrich_issues
from studio.utils.ui import is_json_mode, set_json_mode

TARGET = "cpt-myapp-flow-login"


# --------------------------------------------------------------- the scan (AC2)
@pytest.mark.parametrize("bare, linked", [
    ("`{id}`", "[`{id}`](spec.md)"),
    ("[x] `p1` - `{id}`", "[x] `p1` - [`{id}`](spec.md#login)"),
    ("[ ] `p2` - `{id}`", "[ ] `p2` - [`{id}`](../other/spec.md)"),
    ("`p1` - `{id}`", "`p1` - [`{id}`](spec.md 'Login flow')"),
])
def test_a_link_form_reference_carries_what_the_bare_form_carries(bare, linked):
    """AC2: task marker, priority and checkbox survive the link.

    They were lost before, because a link-form reference only ever matched the
    inline backtick scan, which stamps an unconditional ``checked=False``.
    """
    bare_hits = scan_cpt_id_lines([bare.format(id=TARGET)])
    linked_hits = scan_cpt_id_lines([linked.format(id=TARGET)])
    assert linked_hits == bare_hits


def test_both_spellings_resolve_to_the_same_node():
    hits = scan_cpt_id_lines([f"`{TARGET}`", "", f"[`{TARGET}`](spec.md#login)"])
    assert [h["id"] for h in hits] == [TARGET, TARGET]
    assert [h["type"] for h in hits] == ["reference", "reference"]
    assert [h["line"] for h in hits] == [1, 3]


@pytest.mark.parametrize("line", [
    f"[the login flow](spec.md#{TARGET})",
    f"[the login flow]({TARGET}.md)",
])
def test_only_the_backticked_form_is_a_reference(line):
    """The accepted form is narrow on purpose: the id has to be marked up as an id.

    Any link whose *target* merely contains the string stays prose — inferring a
    reference from a URL would make every path that names an id a reference to it.
    """
    assert scan_cpt_id_lines([line]) == []


# ---------------------------------------------------- link-form definition (AC3)
def test_a_link_form_definition_is_neither_a_definition_nor_a_reference():
    hits = scan_cpt_id_lines([f"**ID**: [`{TARGET}`](spec.md)"])
    assert [h["type"] for h in hits] == [LINK_FORM_DEFINITION]
    assert hits[0]["id"] == TARGET


@pytest.mark.parametrize("line", [
    "**ID**: [`{id}`](spec.md)",
    "`p1` - **ID**: [`{id}`](spec.md)",
    "- [x] `p1` - **ID**: [`{id}`](spec.md#login)",
    # No target may escape the definition pattern: one the reference pattern rejects
    # would reach the inline scan and be misclassified as a reference to the very id
    # it means to declare, which is the defect this code removes.
    "**ID**: [`{id}`](API_(v2).md)",
    "**ID**: [`{id}`](spec.md 'Login (v2)')",
    # Nor may any link *syntax*: an empty destination, a reference-style label, a
    # collapsed reference and a shortcut link all reached the inline scan before.
    "**ID**: [`{id}`]()",
    "**ID**: [`{id}`][login]",
    "**ID**: [`{id}`][]",
    "**ID**: [`{id}`]",
])
def test_every_definition_shape_is_recognised_in_link_form(line):
    hits = scan_cpt_id_lines([line.format(id=TARGET)])
    assert [h["type"] for h in hits] == [LINK_FORM_DEFINITION]


OTHER = "cpt-myapp-flow-logout"


@pytest.mark.parametrize("line, expected_refs", [
    # Text after the complete link construct still references other ids…
    ("**ID**: [`{id}`](spec.md) related: `{other}`", ["{other}"]),
    ("**ID**: [`{id}`][login] related: `{other}`", ["{other}"]),
    ("**ID**: [`{id}`] related: `{other}`", ["{other}"]),
    ("**ID**: [`{id}`](spec.md) see [`{other}`](b.md#{other})", ["{other}"]),
    # …but neither the linked id nor its destination is a reference.
    ("**ID**: [`{id}`](spec.md) closing (note)", []),
])
def test_only_text_after_the_link_can_reference_other_ids(line, expected_refs):
    hits = scan_cpt_id_lines([line.format(id=TARGET, other=OTHER)])
    assert hits[0]["type"] == LINK_FORM_DEFINITION
    assert hits[0]["id"] == TARGET
    assert [h["id"] for h in hits[1:]] == [r.format(other=OTHER) for r in expected_refs]
    assert all(h["type"] == "reference" for h in hits[1:])


@pytest.mark.parametrize("construct", [
    # The only shapes that could leak: a *backticked* id inside the link construct.
    # An unbackticked one never reaches the backtick scan, so it could not test this.
    "(spec-`{other}`.md)",
    "(spec.md#`{other}`)",
    '(spec.md "supersedes `{other}`")',
    "(API_(`{other}`).md)",
    "[`{other}`]",
])
def test_nothing_inside_the_link_construct_is_a_reference(construct):
    """A destination, title or label says where the link goes; it names no reference.
    The linked definition's own construct is consumed before the rest of the line is
    scanned."""
    hits = scan_cpt_id_lines([f"**ID**: [`{TARGET}`]{construct.format(other=OTHER)}"])
    assert [(h["id"], h["type"]) for h in hits] == [(TARGET, LINK_FORM_DEFINITION)]


def test_text_after_a_consumed_construct_is_still_scanned():
    hits = scan_cpt_id_lines([f"**ID**: [`{TARGET}`](spec-`{OTHER}`.md) related: `cpt-myapp-flow-reset`"])
    assert [h["id"] for h in hits] == [TARGET, "cpt-myapp-flow-reset"]


def test_no_destination_shape_can_hide_the_definition():
    """The match keys on the link text and never parses the destination, so even a
    doubly nested one — past anything a destination regex would handle — is reported."""
    hits = scan_cpt_id_lines([f"**ID**: [`{TARGET}`](a((b)).md)"])
    assert [h["type"] for h in hits] == [LINK_FORM_DEFINITION]


def test_a_reference_target_with_parentheses_falls_back_to_the_inline_scan():
    """Deliberate, and the other half of the asymmetry above.

    The narrow reference target keeps a link's *target* from ever being read as an id.
    A rejected one still reaches the inline scan, so the reference is recorded — it
    loses only its task marker and priority, which is a documented limit, not silence.
    """
    hits = scan_cpt_id_lines([f"[`{TARGET}`](API_(v2).md)"])
    assert [h["type"] for h in hits] == ["reference"]
    assert "has_task" not in hits[0]


def _prd_constraints():
    kit, errors = parse_kit_constraints({"PRD": {"identifiers": {"flow": {}}}})
    assert errors == []
    return kit.by_kind["PRD"]


def test_validate_reports_a_link_form_definition(tmp_path: Path):
    """AC3 end to end: one finding naming the line, not silence."""
    artifact = tmp_path / "PRD.md"
    artifact.write_text(f"# PRD\n\n**ID**: [`{TARGET}`](spec.md)\n", encoding="utf-8")

    report = validate_artifact_file(
        artifact_path=artifact,
        artifact_kind="PRD",
        constraints=_prd_constraints(),
        registered_systems={"myapp"},
    )
    findings = [e for e in report["errors"] if e.get("code") == EC.DEF_LINK_FORM_NOT_ALLOWED]
    assert len(findings) == 1
    assert findings[0]["line"] == 3
    assert TARGET in str(findings[0]["message"])


def test_validate_leaves_a_bare_definition_alone(tmp_path: Path):
    artifact = tmp_path / "PRD.md"
    artifact.write_text(f"# PRD\n\n**ID**: `{TARGET}`\n", encoding="utf-8")

    report = validate_artifact_file(
        artifact_path=artifact,
        artifact_kind="PRD",
        constraints=_prd_constraints(),
        registered_systems={"myapp"},
    )
    assert [e for e in report["errors"] if e.get("code") == EC.DEF_LINK_FORM_NOT_ALLOWED] == []


def test_the_fix_prompt_unwraps_in_place_and_keeps_the_decoration(tmp_path: Path):
    """A definition may carry a checkbox and a priority. A prompt that modelled the
    bare line would have an agent drop both and trade this finding for
    `def-missing-task` / `def-missing-priority`."""
    artifact = tmp_path / "PRD.md"
    artifact.write_text(f"# PRD\n\n- [x] `p1` - **ID**: [`{TARGET}`](spec.md)\n", encoding="utf-8")
    report = validate_artifact_file(
        artifact_path=artifact,
        artifact_kind="PRD",
        constraints=_prd_constraints(),
        registered_systems={"myapp"},
    )
    findings = [e for e in report["errors"] if e.get("code") == EC.DEF_LINK_FORM_NOT_ALLOWED]
    enrich_issues(findings, project_root=tmp_path)

    prompt = str(findings[0]["fixing_prompt"])
    assert TARGET in prompt
    assert "leave any checkbox and priority marker" in prompt
    assert f"**ID**: `{TARGET}`" not in prompt  # no undecorated line to copy


def _all_findings(tmp_path: Path, design_line: str) -> list:
    """A PRD holding the real definition of TARGET, and a DESIGN glossary line about it."""
    kit, errors = parse_kit_constraints({"PRD": {"identifiers": {"flow": {}}},
                                         "DESIGN": {"identifiers": {"flow": {}}}})
    assert errors == []
    prd, design = tmp_path / "PRD.md", tmp_path / "DESIGN.md"
    prd.write_text(f"# PRD\n\n**ID**: `{TARGET}`\n", encoding="utf-8")
    design.write_text(f"# Design\n\n## Glossary\n\n{design_line}\n", encoding="utf-8")
    found = []
    for path, kind in ((prd, "PRD"), (design, "DESIGN")):
        found += validate_artifact_file(artifact_path=path, artifact_kind=kind,
                                        constraints=kit.by_kind[kind], registered_systems={"myapp"})["errors"]
    found += cross_validate_artifacts(
        [ArtifactRecord(path=prd, artifact_kind="PRD", constraints=kit.by_kind["PRD"]),
         ArtifactRecord(path=design, artifact_kind="DESIGN", constraints=kit.by_kind["DESIGN"])],
        registered_systems={"myapp"}, known_kinds={"flow"},
    )["errors"]
    return [f for f in found if f.get("code") not in (EC.REQUIRED_ID_KIND_MISSING, EC.TOC_MISSING)]


def test_a_glossary_line_pointing_at_a_real_definition_gets_the_right_advice(tmp_path: Path):
    """An index re-listing an id defined elsewhere, in definition markup. Unwrapping it —
    the advice for a definition — would create a second definition. The finding and its
    prompt name the other edit, and that edit leaves both artifacts clean."""
    glossary = f"**ID**: [`{TARGET}`](PRD.md#login)"
    findings = _all_findings(tmp_path, glossary)
    assert [f.get("code") for f in findings] == [EC.DEF_LINK_FORM_NOT_ALLOWED]
    enrich_issues(findings, project_root=tmp_path)
    for text in (str(findings[0]["message"]), str(findings[0]["fixing_prompt"])):
        assert "defined elsewhere" in text and "**ID**:" in text

    # The edit the prompt names for this case, applied as written: no findings at all.
    assert _all_findings(tmp_path, f"[`{TARGET}`](PRD.md#login)") == []
    # The other branch's edit, applied to this line, is exactly what must be avoided.
    unwrapped = _all_findings(tmp_path, f"**ID**: `{TARGET}`")
    assert {f.get("code") for f in unwrapped} == {EC.DUPLICATE_DEFINITION}


def test_lowering_the_rule_is_never_silent(tmp_path: Path):
    """The rule is lowerable like any other, and what that leaves behind is the answer
    to "does muting it reopen the hole": the suppression is counted in the report."""
    constraints_path = tmp_path / "constraints.toml"
    constraints_path.write_text(toml_utils.dumps({
        "validation": {"severity": {EC.DEF_LINK_FORM_NOT_ALLOWED: "off"}},
        "artifacts": {"PRD": {"identifiers": {"flow": {}}}},
    }), encoding="utf-8")
    kit, errors = load_constraints_file(constraints_path)
    assert errors == []

    artifact = tmp_path / "PRD.md"
    artifact.write_text(f"# PRD\n\n**ID**: [`{TARGET}`](spec.md)\n", encoding="utf-8")
    report = validate_artifact_file(
        artifact_path=artifact,
        artifact_kind="PRD",
        constraints=kit.by_kind["PRD"],
        registered_systems={"myapp"},
        policy=build_severity_policy([kit]),
    )
    codes = [e.get("code") for e in report["errors"] + report["warnings"]]
    assert EC.DEF_LINK_FORM_NOT_ALLOWED not in codes
    assert report["suppressed"] == 1


def test_lowering_it_for_an_unregistered_system_leaves_only_the_count(tmp_path: Path):
    """The other branch of ADR-0024's claim. References to an id whose system is not
    registered are skipped as external, so with the rule lowered no `ref-no-definition`
    stands behind it: the suppression count is the only signal, and it is there."""
    constraints_path = tmp_path / "constraints.toml"
    constraints_path.write_text(toml_utils.dumps({
        "validation": {"severity": {EC.DEF_LINK_FORM_NOT_ALLOWED: "off"}},
        "artifacts": {"PRD": {"identifiers": {"flow": {}}},
                      "DESIGN": {"identifiers": {"comp": {}}}},
    }), encoding="utf-8")
    kit, errors = load_constraints_file(constraints_path)
    assert errors == []

    prd, design = tmp_path / "PRD.md", tmp_path / "DESIGN.md"
    prd.write_text(f"# PRD\n\n**ID**: [`{TARGET}`](spec.md)\n", encoding="utf-8")
    design.write_text(f"# Design\n\n`{TARGET}`\n", encoding="utf-8")
    unregistered = {"elsewhere"}  # TARGET's system is `myapp`

    per_artifact = validate_artifact_file(
        artifact_path=prd, artifact_kind="PRD", constraints=kit.by_kind["PRD"],
        registered_systems=unregistered, policy=build_severity_policy([kit]),
    )
    cross = cross_validate_artifacts(
        [ArtifactRecord(path=prd, artifact_kind="PRD", constraints=kit.by_kind["PRD"]),
         ArtifactRecord(path=design, artifact_kind="DESIGN", constraints=kit.by_kind["DESIGN"])],
        registered_systems=unregistered, known_kinds={"flow", "comp"},
    )
    about_target = [e for e in per_artifact["errors"] + per_artifact["warnings"] + cross["errors"]
                    if e.get("id") == TARGET]
    assert about_target == []
    assert per_artifact["suppressed"] == 1


def test_a_link_form_definition_is_not_mistaken_for_a_cdsl_step(tmp_path: Path):
    """It shares a decorated step's `- [x] `p1` -` prefix. The CDSL checks step around
    every line the ID scan classifies, and the scan now classifies this one."""
    artifact = tmp_path / "FEATURE.md"
    artifact.write_text(
        "# Feature\n\n### Login\n\n**Steps**:\n"
        "1. [x] - `p1` - Read the input - `inst-read`\n"
        f"- [x] `p1` - **ID**: [`{TARGET}`](spec.md)\n",
        encoding="utf-8",
    )
    errors: list = []
    warnings: list = []
    _validate_cdsl_structure(artifact_path=artifact, cdsl_hits=[], errors=errors, warnings=warnings)
    assert [f for f in errors + warnings if f.get("line") == 7] == []


def test_a_link_form_definition_does_not_define_the_id(tmp_path: Path):
    """The id really is undefined — that is why the line is worth reporting."""
    artifact = tmp_path / "PRD.md"
    artifact.write_text(f"# PRD\n\n**ID**: [`{TARGET}`](spec.md)\n", encoding="utf-8")

    hits = scan_cpt_id_lines(artifact.read_text(encoding="utf-8").splitlines())
    assert [h for h in hits if h["type"] == "definition"] == []


# ------------------------------------------------------------- where-used (AC1)
def _where_used(artifact: Path, argv: list[str]) -> dict:
    saved = is_json_mode()
    stdout = io.StringIO()
    try:
        set_json_mode(True)
        with patch(
            "studio.commands.where_used.resolve_target_and_artifacts",
            return_value=(TARGET, object(), [(artifact, "FEATURE")], {}, None),
        ), redirect_stdout(stdout):
            assert cmd_where_used(argv) == 0
        return json.loads(stdout.getvalue())
    finally:
        set_json_mode(saved)


def test_where_used_lists_the_bare_and_the_link_form_once_each(tmp_path: Path):
    """AC1: two spellings of one reference, two places to look, one record each."""
    artifact = tmp_path / "FEATURE.md"
    artifact.write_text(
        f"# Feature\n\n`{TARGET}`\n\n[`{TARGET}`](../prd/PRD.md#login)\n",
        encoding="utf-8",
    )
    data = _where_used(artifact, [TARGET])
    assert data["count"] == 2
    assert [r["line"] for r in data["references"]] == [3, 5]


def test_where_used_counts_one_line_once_however_often_it_names_the_id(tmp_path: Path):
    artifact = tmp_path / "FEATURE.md"
    artifact.write_text(
        f"# Feature\n\nThe `{TARGET}` flow supersedes `{TARGET}` in the old plan.\n",
        encoding="utf-8",
    )
    data = _where_used(artifact, [TARGET])
    assert data["count"] == 1
    assert data["references"][0]["line"] == 3


def test_where_used_does_not_count_a_link_form_definition_as_a_use(tmp_path: Path):
    artifact = tmp_path / "FEATURE.md"
    artifact.write_text(f"# Feature\n\n**ID**: [`{TARGET}`](spec.md)\n", encoding="utf-8")
    data = _where_used(artifact, [TARGET, "--include-definitions"])
    assert data["count"] == 0
