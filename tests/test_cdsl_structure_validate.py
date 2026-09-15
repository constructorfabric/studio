"""Per-rule fixtures for CDSL.md FAIL rule enforcement (OLE-03).

Missing-token findings (S.3/S.4/S.5/CO.4) are asserted as *warnings*, not
errors: this repo has pre-existing FEATURE docs authored before the inst-id
convention (see architecture/features/dependency-mapping.md), so promoting
that family straight to FAIL would break `make validate` for unrelated files.
Everything else (prohibited syntax, duplicate inst-ids, placeholders) is
asserted as a hard error, since those have ~no pre-existing hits.

The missing-token backlog itself is tracked in issue #85 and enforced by
`test_cdsl_missing_token_warnings_match_known_backlog_allowlist` below,
mirroring `tests/test_pdsl_keywords.py`'s `KNOWN_PDSL_CAP_VIOLATIONS`
allowlist for the analogous PDSL backlog (issue #87): a fixed, visible list
of (file, code) pairs that still fails on any NEW/untracked violation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

from studio.utils import error_codes as EC
from studio.utils.constraints import _validate_cdsl_structure
from studio.utils.document import scan_cdsl_instructions


def _run(tmp_path: Path, text: str) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    artifact = tmp_path / "feature.md"
    artifact.write_text(text, encoding="utf-8")
    errors: List[Dict[str, object]] = []
    warnings: List[Dict[str, object]] = []
    cdsl_hits = scan_cdsl_instructions(artifact)
    _validate_cdsl_structure(artifact_path=artifact, cdsl_hits=cdsl_hits, errors=errors, warnings=warnings)
    return errors, warnings


def _codes(items: List[Dict[str, object]]) -> set:
    return {i["code"] for i in items}


def _steps(body: str) -> str:
    """Wrap step lines in a real `**Steps**:` block, as CDSL.md requires for scope."""
    return f"**Steps**:\n{body}"


def test_well_formed_step_has_no_findings(tmp_path: Path) -> None:
    text = _steps("1. [x] - `p1` - Load entity from registry - `inst-load-entity`\n")
    errors, warnings = _run(tmp_path, text)
    assert errors == [] and warnings == []


def test_missing_checkbox_warns_s3_and_co4(tmp_path: Path) -> None:
    text = _steps("1. - `p1` - Load entity from registry - `inst-load-entity`\n")
    errors, warnings = _run(tmp_path, text)
    assert errors == []
    codes = _codes(warnings)
    assert EC.CDSL_MISSING_CHECKBOX in codes
    assert EC.CDSL_INCOMPLETE_STEP_LINE in codes


def test_missing_phase_warns_s4_and_co4(tmp_path: Path) -> None:
    text = _steps("1. [ ] - Load entity from registry - `inst-load-entity`\n")
    errors, warnings = _run(tmp_path, text)
    assert errors == []
    codes = _codes(warnings)
    assert EC.CDSL_MISSING_PHASE_TOKEN in codes
    assert EC.CDSL_INCOMPLETE_STEP_LINE in codes


def test_missing_inst_id_warns_s5_and_co4(tmp_path: Path) -> None:
    text = _steps("1. [ ] - `p1` - Load entity from registry\n")
    errors, warnings = _run(tmp_path, text)
    assert errors == []
    codes = _codes(warnings)
    assert EC.CDSL_MISSING_INST_ID in codes
    assert EC.CDSL_INCOMPLETE_STEP_LINE in codes


def test_function_syntax_fails_s6_and_cl3(tmp_path: Path) -> None:
    text = _steps("1. [ ] - `p1` - async function validateInput() - `inst-validate-input`\n")
    errors, _warnings = _run(tmp_path, text)
    codes = _codes(errors)
    assert EC.CDSL_CODE_SYNTAX in codes
    assert EC.CDSL_NOT_PLAIN_ENGLISH in codes


def test_type_annotation_fails_s7(tmp_path: Path) -> None:
    text = _steps("1. [ ] - `p1` - Declare result: string for the response - `inst-declare-result`\n")
    errors, _warnings = _run(tmp_path, text)
    codes = _codes(errors)
    assert EC.CDSL_TYPE_ANNOTATION in codes
    assert EC.CDSL_NOT_PLAIN_ENGLISH in codes


def test_operator_fails_cl2(tmp_path: Path) -> None:
    text = _steps("1. [ ] - `p1` - **IF** a == b **THEN** continue - `inst-if-a-equals-b`\n")
    errors, _warnings = _run(tmp_path, text)
    codes = _codes(errors)
    assert EC.CDSL_LANGUAGE_OPERATOR in codes
    assert EC.CDSL_NOT_PLAIN_ENGLISH in codes


def test_plain_colon_apposition_is_not_flagged(tmp_path: Path) -> None:
    """CDSL.md's own example style ('label: value') must not misfire as a type annotation."""
    text = _steps("1. [x] - `p1` - Initialize empty list: enabled_entities - `inst-init-enabled-entities`\n")
    errors, warnings = _run(tmp_path, text)
    assert errors == [] and warnings == []


def test_duplicate_inst_id_under_one_parent_fails_co5(tmp_path: Path) -> None:
    text = (
        "**ID**: `cpt-example-feature-x-algo-y`\n"
        "\n"
        + _steps(
            "1. [x] - `p1` - Load entity - `inst-load-entity`\n"
            "2. [x] - `p1` - Load entity again - `inst-load-entity`\n"
        )
    )
    errors, _warnings = _run(tmp_path, text)
    assert EC.CDSL_DUPLICATE_INST_ID in _codes(errors)


def test_different_parents_reuse_of_inst_id_is_not_flagged(tmp_path: Path) -> None:
    text = (
        "**ID**: `cpt-example-feature-x-algo-a`\n"
        "\n"
        + _steps("1. [x] - `p1` - Load entity - `inst-load-entity`\n")
        + "\n**ID**: `cpt-example-feature-x-algo-b`\n"
        "\n"
        + _steps("1. [x] - `p1` - Load entity - `inst-load-entity`\n")
    )
    errors, warnings = _run(tmp_path, text)
    assert errors == [] and warnings == []


def test_placeholder_fails_co6(tmp_path: Path) -> None:
    text = _steps("1. [ ] - `p1` - TODO figure out the retry policy - `inst-retry-policy`\n")
    errors, _warnings = _run(tmp_path, text)
    assert EC.CDSL_PLACEHOLDER in _codes(errors)


def test_ordinary_task_list_is_not_treated_as_cdsl(tmp_path: Path) -> None:
    """A plain '- [ ] task' item with no phase/inst token is not a CDSL step."""
    text = "- [ ] Ship the release notes\n"
    errors, warnings = _run(tmp_path, text)
    assert errors == [] and warnings == []


def test_task_tracked_id_definition_is_not_treated_as_cdsl(tmp_path: Path) -> None:
    """A priority-tagged, task-tracked ID definition reuses the `pN` token shape but is not CDSL."""
    text = _steps("- [ ] `p1` - **ID**: `cpt-ex-task-flow-status-overall`\n")
    errors, warnings = _run(tmp_path, text)
    assert errors == [] and warnings == []


def test_fenced_code_examples_are_excluded(tmp_path: Path) -> None:
    text = _steps(
        "```rust\n"
        "1. [ ] - async function example() - broken\n"
        "```\n"
    )
    errors, warnings = _run(tmp_path, text)
    assert errors == [] and warnings == []


def test_multiline_step_joins_continuation_before_inst_token(tmp_path: Path) -> None:
    """A long description may wrap onto continuation lines before its `inst-id` token."""
    text = _steps(
        "6. [ ] - `p1` - Agent selects phase execution isolation policy: use\n"
        "   `cf-phase-runner` when plan state is main-checkout-local; use\n"
        "   `cf-phase-runner-isolated` otherwise -\n"
        "   `inst-select-phase-runner-isolation`\n"
    )
    errors, warnings = _run(tmp_path, text)
    assert errors == [] and warnings == []


def test_nested_step_under_if_is_its_own_candidate(tmp_path: Path) -> None:
    """A nested numbered item under an IF is itself a full CDSL step, not a continuation."""
    text = _steps(
        "3. [x] - `p1` - **IF** entity not found: - `inst-if-not-found`\n"
        "   1. [x] - `p1` - **RETURN** 404 error - `inst-return-404`\n"
    )
    errors, warnings = _run(tmp_path, text)
    assert errors == [] and warnings == []


def test_content_outside_steps_block_is_not_scanned(tmp_path: Path) -> None:
    """Loose ID-reference bullets and DoD-style checklists outside Steps:/Transitions: are ignored."""
    text = (
        "### Design Components\n"
        "\n"
        "- `p1` - `cpt-studio-component-skill-engine` (delegation command routing)\n"
        "\n"
        "### Definitions of Done\n"
        "\n"
        "- [x] `p1` - **ID**: `cpt-studio-dod-example`\n"
        "\n"
        "1. [x] - `p2` - Each implemented check reports pass/fail/warn\n"
        "2. [x] - `p2` - Exit code 0 if all checks pass, 2 if any fail\n"
    )
    errors, warnings = _run(tmp_path, text)
    assert errors == [] and warnings == []


def test_supporting_label_ends_the_steps_block(tmp_path: Path) -> None:
    """`**Supporting**:` bullets are implementation notes, not CDSL steps, even with a `pN` tag."""
    text = (
        "**Steps**:\n"
        "1. [x] - `p1` - Load entity - `inst-load-entity`\n"
        "\n"
        "**Supporting**:\n"
        "- [x] - `p1` - Some component note without full CDSL shape\n"
    )
    errors, warnings = _run(tmp_path, text)
    assert errors == [] and warnings == []


def test_prose_mentioning_phase_markers_is_not_scanned(tmp_path: Path) -> None:
    """Narrative prose that just describes the `pN` convention isn't inside a Steps: block."""
    text = (
        "### Consequences\n"
        "\n"
        "- Priorities use backtick markers: `p1`, `p2`\n"
    )
    errors, warnings = _run(tmp_path, text)
    assert errors == [] and warnings == []


def test_trailing_prose_after_steps_block_is_not_folded_into_last_step(tmp_path: Path) -> None:
    """A blank line closes the current step; trailing prose isn't a continuation."""
    text = (
        "**Steps**:\n"
        "1. [x] - `p1` - Load entity - `inst-load-entity`\n"
        "\n"
        "Some trailing note that mentions TODO and == and -> in passing.\n"
        "\n"
        "## Next Section\n"
    )
    errors, warnings = _run(tmp_path, text)
    assert errors == [] and warnings == []


def test_duplicate_inst_id_in_supporting_block_is_not_flagged(tmp_path: Path) -> None:
    """CO.5 only checks Steps:/Transitions: content — Supporting: reuse isn't in scope."""
    text = (
        "**ID**: `cpt-example-feature-x-algo-z`\n"
        "\n"
        "**Steps**:\n"
        "1. [x] - `p1` - Load entity - `inst-load-entity`\n"
        "\n"
        "**Supporting**:\n"
        "- [x] - `p1` - Some note - `inst-load-entity`\n"
    )
    errors, warnings = _run(tmp_path, text)
    assert errors == [] and warnings == []


def test_cdsl_md_algorithm_example_is_scanned_without_a_steps_label(tmp_path: Path) -> None:
    """CDSL.md's own worked examples use '**Algorithm: Name**' + Input/Output, no 'Steps:' label."""
    text = (
        "## Example: Algorithm\n"
        "\n"
        "**Algorithm: Enable Entity with Dependencies**\n"
        "\n"
        "Input: entity_id, tenants, security_context  \n"
        "Output: List of enabled entity IDs\n"
        "\n"
        "1. [x] - `p1` - Initialize empty list: enabled_entities - `inst-init-enabled-entities`\n"
        "2. [ ] - `p1` - Load entity from registry\n"
    )
    _errors, warnings = _run(tmp_path, text)
    # The well-formed first step proves scope opened; the second step (missing
    # its inst-id) proves it's actually being *checked*, not just skipped.
    assert EC.CDSL_MISSING_INST_ID in _codes(warnings)


def test_cdsl_md_actor_flow_example_is_scanned_without_a_steps_label(tmp_path: Path) -> None:
    """CDSL.md's Actor Flow example uses '**Flow: Name**' + Actor/Goal, no 'Steps:' label."""
    text = (
        "## Example: Actor Flow\n"
        "\n"
        "**Flow: Admin Creates Dashboard**\n"
        "\n"
        "Actor: Admin  \n"
        "Goal: Create new dashboard\n"
        "\n"
        "1. [x] - `p1` - User opens Dashboard page - `inst-open-dashboard-page`\n"
        "2. [ ] - `p1` - User clicks Save\n"
    )
    _errors, warnings = _run(tmp_path, text)
    assert EC.CDSL_MISSING_INST_ID in _codes(warnings)


def test_bare_heading_with_id_and_actors_then_steps_is_scanned(tmp_path: Path) -> None:
    """The bundled SDLC kit's FEATURE example style: heading + ID-def + **Actors**: + steps directly."""
    text = (
        "### Create Task\n"
        "\n"
        "- [ ] `p1` - **ID**: `cpt-ex-task-flow-flow-create-task`\n"
        "\n"
        "**Actors**:\n"
        "- `cpt-ex-task-flow-actor-member`\n"
        "- `cpt-ex-task-flow-actor-lead`\n"
        "\n"
        "1. [x] - `p1` - User fills task form - `inst-fill-form`\n"
        "2. [ ] - `p2` - User optionally assigns task to team member\n"
    )
    _errors, warnings = _run(tmp_path, text)
    assert EC.CDSL_MISSING_INST_ID in _codes(warnings)


def test_bare_heading_without_a_wellformed_first_step_is_not_scanned(tmp_path: Path) -> None:
    """A heading section whose first real item isn't fully well-formed CDSL stays out of scope."""
    text = (
        "### Doctor Command\n"
        "\n"
        "- [x] `p2` - **ID**: `cpt-studio-dod-developer-experience-doctor`\n"
        "\n"
        "1. [x] - `p2` - Each implemented check reports pass/fail/warn\n"
        "2. [x] - `p2` - Exit code 0 if all checks pass, 2 if any fail\n"
    )
    errors, warnings = _run(tmp_path, text)
    assert errors == [] and warnings == []


def test_cdsl_structure_validation_runs_through_real_cmd_validate_call_path(tmp_path: Path) -> None:
    """End-to-end: cmd_validate -> validate_artifact_file -> _validate_cdsl_structure.

    Every other test in this file calls `_validate_cdsl_structure` directly,
    so none of them would notice a regression in the wiring between
    `cmd_validate`/`validate_artifact_file` and this validator: a mutation
    that dropped the call inside `_validate_artifact_identifier_phase` would
    still pass the rest of this suite. This test drives the real CLI entry
    point against a fixture artifact with a deliberately malformed CDSL step
    (a placeholder marker, `CDSL_PLACEHOLDER`) and asserts the finding
    surfaces in `cfs validate`'s own JSON output.
    """
    import io
    import json
    import os
    from contextlib import redirect_stdout

    sys.path.insert(0, str(Path(__file__).parent))
    from _test_helpers import write_constraints_toml

    from studio.cli import main
    from studio.utils import toml_utils
    from studio.utils.ui import set_json_mode

    kit_root = tmp_path / "kits" / "sdlc"
    kit_dir = kit_root / "artifacts" / "FEATURE"
    kit_dir.mkdir(parents=True)
    (kit_dir / "template.md").write_text(
        "---\ncypilot-template:\n  version:\n    major: 1\n    minor: 0\n  kind: FEATURE\n---\ntext\n",
        encoding="utf-8",
    )
    write_constraints_toml(
        kit_root,
        {"FEATURE": {"identifiers": {"cpt": {"required": False, "template": "cpt-{system}-cpt-{slug}"}}}},
    )

    feature_path = tmp_path / "architecture" / "features" / "widget.md"
    feature_path.parent.mkdir(parents=True)
    feature_path.write_text(
        "**ID**: `cpt-test-cpt-widget`\n\n" + _steps("1. [x] `p1` - TODO fill this in - `inst-step-one`\n"),
        encoding="utf-8",
    )

    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text(
        '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "adapter"\n```\n', encoding="utf-8"
    )
    adapter_dir = tmp_path / "adapter"
    (adapter_dir / "config").mkdir(parents=True)
    (adapter_dir / "config" / "AGENTS.md").write_text("# Test adapter\n", encoding="utf-8")
    toml_utils.dump(
        {
            "version": "1.0",
            "project_root": "..",
            "kits": {"cypilot": {"format": "CFS", "path": "kits/sdlc"}},
            "systems": [{
                "name": "Test",
                "kits": "cypilot",
                "artifacts": [{"path": "architecture/features/widget.md", "kind": "FEATURE"}],
            }],
        },
        adapter_dir / "config" / "artifacts.toml",
    )

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        set_json_mode(True)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["validate", "--artifact", str(feature_path), "--skip-code", "--verbose"])
        out = json.loads(stdout.getvalue())
    finally:
        os.chdir(cwd)
        set_json_mode(False)

    assert out.get("status") == "FAIL", out
    error_codes = {e.get("code") for e in out.get("errors", [])}
    assert EC.CDSL_PLACEHOLDER in error_codes
    assert exit_code != 0


def test_all_ten_cdsl_codes_cite_their_cdsl_md_rule_id_in_the_message(tmp_path: Path) -> None:
    """Every CDSL finding should let a reader spot its CDSL.md rule without a lookup table."""
    rule_id_by_code = {
        EC.CDSL_MISSING_CHECKBOX: "S.3",
        EC.CDSL_MISSING_PHASE_TOKEN: "S.4",
        EC.CDSL_MISSING_INST_ID: "S.5",
        EC.CDSL_CODE_SYNTAX: "S.6",
        EC.CDSL_TYPE_ANNOTATION: "S.7",
        EC.CDSL_LANGUAGE_OPERATOR: "CL.2",
        EC.CDSL_NOT_PLAIN_ENGLISH: "CL.1",
        EC.CDSL_DUPLICATE_INST_ID: "CO.5",
        EC.CDSL_PLACEHOLDER: "CO.6",
    }

    missing_checkbox_text = _steps("1. - `p1` - Load entity from registry - `inst-load-entity`\n")
    missing_phase_text = _steps("1. [ ] - Load entity from registry - `inst-load-entity`\n")
    missing_inst_text = _steps("1. [ ] - `p1` - Load entity from registry\n")
    prohibited_text = _steps("1. [ ] - `p1` - async function validateInput() - `inst-validate-input`\n")
    type_annotation_text = _steps("1. [ ] - `p1` - Declare result: string for the response - `inst-declare-result`\n")
    operator_text = _steps("1. [ ] - `p1` - **IF** a == b **THEN** continue - `inst-if-a-equals-b`\n")
    duplicate_text = (
        "**ID**: `cpt-example-feature-x-algo-y`\n\n"
        + _steps(
            "1. [x] - `p1` - Load entity - `inst-load-entity`\n"
            "2. [x] - `p1` - Load entity again - `inst-load-entity`\n"
        )
    )
    placeholder_text = _steps("1. [x] - `p1` - TODO fill this in - `inst-fill-in`\n")

    findings_by_text = [
        missing_checkbox_text,
        missing_phase_text,
        missing_inst_text,
        prohibited_text,
        type_annotation_text,
        operator_text,
        duplicate_text,
        placeholder_text,
    ]
    all_findings: List[Dict[str, object]] = []
    for text in findings_by_text:
        errs, warns = _run(tmp_path, text)
        all_findings.extend(errs)
        all_findings.extend(warns)

    by_code: Dict[str, List[Dict[str, object]]] = {}
    for finding in all_findings:
        by_code.setdefault(str(finding["code"]), []).append(finding)

    for code, rule_id in rule_id_by_code.items():
        matches = by_code.get(code.value if hasattr(code, "value") else code)
        assert matches, f"no finding produced for {code}"
        assert any(rule_id in str(m["message"]) for m in matches), (
            f"{code} message(s) missing rule id {rule_id}: {[m['message'] for m in matches]}"
        )


def test_screaming_snake_case_placeholder_in_angle_brackets_is_not_a_type_annotation(tmp_path: Path) -> None:
    """`<ARTIFACT_KIND>`-style doc placeholders must not misfire as a generic type param.

    Found via a real-corpus check (architecture/features/kit-management.md)
    where `artifacts.<ARTIFACT_KIND>` was misread as a `<T>`-style generic
    and flagged as S.7/CL.1, even though it's a placeholder token, not code.
    """
    text = _steps(
        "1. [x] - `p1` - A resource MAY declare nested `artifacts.<ARTIFACT_KIND>` bindings - `inst-canonical-bindings`\n"
    )
    errors, warnings = _run(tmp_path, text)
    assert errors == [] and warnings == []


def test_real_generic_type_param_in_angle_brackets_still_flagged(tmp_path: Path) -> None:
    """A genuine PascalCase/single-letter generic (`<T>`, `<Response>`) still trips S.7."""
    text = _steps("1. [x] - `p1` - Return a `List<Response>` - `inst-return-list`\n")
    errors, _warnings = _run(tmp_path, text)
    assert EC.CDSL_TYPE_ANNOTATION in _codes(errors)


# Tracked in issue #85 (CDSL inst-id retrofit backlog). Each entry is the
# exact set of missing-token warning codes currently produced for that real
# artifact — any NEW file, or any NEW code for an already-listed file, must
# still fail this test rather than being silently absorbed.
KNOWN_CDSL_MISSING_TOKEN_VIOLATIONS: Dict[str, set] = {
    "architecture/features/agent-integration.md": {
        EC.CDSL_MISSING_CHECKBOX,
        EC.CDSL_INCOMPLETE_STEP_LINE,
    },
    "architecture/features/dependency-mapping.md": {
        EC.CDSL_MISSING_INST_ID,
        EC.CDSL_INCOMPLETE_STEP_LINE,
    },
    "architecture/features/developer-experience.md": {
        EC.CDSL_MISSING_CHECKBOX,
        EC.CDSL_MISSING_INST_ID,
        EC.CDSL_INCOMPLETE_STEP_LINE,
    },
    "architecture/features/workspace.md": {
        EC.CDSL_MISSING_CHECKBOX,
        EC.CDSL_MISSING_INST_ID,
        EC.CDSL_MISSING_PHASE_TOKEN,
        EC.CDSL_INCOMPLETE_STEP_LINE,
    },
}


def test_cdsl_missing_token_warnings_match_known_backlog_allowlist() -> None:
    """`cfs validate`'s CDSL structure check, run against every registered artifact
    in this repo, must produce only the tracked missing-token warnings (issue #85)
    and zero hard errors — any new/untracked finding must fail this test.
    """
    from studio.utils.context import StudioContext

    repo_root = Path(__file__).parent.parent
    ctx = StudioContext.load(repo_root)
    assert ctx is not None, "Constructor Studio context failed to load for this repo"

    unexpected: List[str] = []
    seen_files: set = set()
    for artifact_meta, _system_node in ctx.meta.iter_all_artifacts():
        artifact_path = (ctx.project_root / artifact_meta.path).resolve()
        if not artifact_path.exists():
            continue
        errors: List[Dict[str, object]] = []
        warnings: List[Dict[str, object]] = []
        _validate_cdsl_structure(artifact_path=artifact_path, cdsl_hits=[], errors=errors, warnings=warnings)
        for e in errors:
            unexpected.append(f"{artifact_meta.path}:{e['line']} {e['code']} (unexpected ERROR) {e['message']}")
        allowed = KNOWN_CDSL_MISSING_TOKEN_VIOLATIONS.get(artifact_meta.path, set())
        if allowed:
            seen_files.add(artifact_meta.path)
        for w in warnings:
            if w["code"] not in allowed:
                unexpected.append(f"{artifact_meta.path}:{w['line']} {w['code']} (untracked WARNING) {w['message']}")

    assert not unexpected, (
        "New/unexpected CDSL structure findings not tracked in issue #85:\n" + "\n".join(unexpected)
    )
