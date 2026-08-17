"""Per-rule fixtures for CDSL.md FAIL rule enforcement (OLE-03).

Missing-token findings (S.3/S.4/S.5/CO.4) are asserted as *warnings*, not
errors: this repo has pre-existing FEATURE docs authored before the inst-id
convention (see architecture/features/dependency-mapping.md), so promoting
that family straight to FAIL would break `make validate` for unrelated files.
Everything else (prohibited syntax, duplicate inst-ids, placeholders) is
asserted as a hard error, since those have ~no pre-existing hits.
"""

from __future__ import annotations

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
