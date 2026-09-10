from __future__ import annotations

import io
import random
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from studio.cli import main
from studio.utils.pdsl import (
    PdslError,
    PdslFinding,
    PdslSource,
    build_envelope,
    error_result,
    exit_code_for_results,
    read_source_file,
    scan_blocks,
    validate_source,
)
from studio.utils.pdsl import _edit_distance
from studio.utils.ui import set_json_mode


VALID_PDSL = """UNIT Demo

PURPOSE:
  Validate a small block.

DO:
  - RUN Do something deterministic

RULES:
  - ALWAYS keep output stable

MENU Pick:
  OPTIONS:
    1 one -> RETURN done
    2 two -> RETURN done
"""


INVALID_PDSL = """UNIT Demo
UNIT Demo

DO:
  - EXECUTE unsupported action

MENU Pick:
  OPTIONS:
    - 1 one -> RETURN done
    - 3 three -> RETURN done

WHEN:
  - REQUIRE matches(reply, missing-pattern)
"""


def _run(argv: list[str], *, stdin: str = "") -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch.object(sys, "stdin", io.StringIO(stdin)):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = main(argv)
    return rc, stdout.getvalue(), stderr.getvalue()


def test_pdsl_validate_text_json_pass() -> None:
    set_json_mode(False)
    rc, stdout, stderr = _run(["pdsl", "validate", "--text", VALID_PDSL, "--json"])

    assert rc == 0
    assert stderr == ""
    payload = json.loads(stdout)
    assert payload["command"] == "pdsl validate"
    assert payload["ok"] is True
    assert payload["summary"] == {
        "pass_count": 1,
        "fail_count": 0,
        "error_count": 0,
        "finding_count": 0,
    }
    assert payload["results"][0]["source"] == "<text>"
    assert payload["results"][0]["status"] == "PASS"


def test_pdsl_validate_text_human_fail_without_json() -> None:
    set_json_mode(False)
    rc, stdout, stderr = _run(["pdsl", "validate", "--text", INVALID_PDSL])

    assert rc == 2
    assert stderr == ""
    assert "PDSL validation did not pass" in stdout
    assert "PDSL200" in stdout
    assert "PDSL300" in stdout
    assert "PDSL400" in stdout
    assert "PDSL500" in stdout


def test_pdsl_validate_stdin_json() -> None:
    set_json_mode(False)
    rc, stdout, _stderr = _run(["pdsl", "validate", "-", "--json"], stdin=VALID_PDSL)

    assert rc == 0
    payload = json.loads(stdout)
    assert payload["results"][0]["source"] == "<stdin>"


def test_pdsl_validate_multi_file_preserves_order_and_read_error() -> None:
    set_json_mode(False)
    with TemporaryDirectory() as td:
        root = Path(td)
        first = root / "first.md"
        second = root / "second.md"
        missing = root / "missing.md"
        first.write_text("```pdsl\n" + VALID_PDSL + "\n```\n", encoding="utf-8")
        second.write_text(INVALID_PDSL, encoding="utf-8")

        rc, stdout, _stderr = _run(["pdsl", "validate", str(first), str(second), str(missing), "--json"])

    assert rc == 1
    payload = json.loads(stdout)
    assert [result["source"] for result in payload["results"]] == [str(first), str(second), str(missing)]
    assert [result["status"] for result in payload["results"]] == ["PASS", "FAIL", "ERROR"]
    assert payload["summary"]["pass_count"] == 1
    assert payload["summary"]["fail_count"] == 1
    assert payload["summary"]["error_count"] == 1


def test_pdsl_validate_rejects_mixed_selectors() -> None:
    set_json_mode(False)
    rc, stdout, _stderr = _run(["pdsl", "validate", "--text", VALID_PDSL, "-", "--json"], stdin=VALID_PDSL)

    assert rc == 1
    payload = json.loads(stdout)
    assert payload["results"][0]["status"] == "ERROR"
    assert payload["results"][0]["errors"][0]["kind"] == "INVOCATION_ERROR"


def test_pdsl_help_is_validate_only_and_no_scaffold_output() -> None:
    set_json_mode(False)
    rc, stdout, stderr = _run(["pdsl", "--help"])

    assert rc == 0
    assert stderr == ""
    assert "validate" in stdout
    assert "Scaffold generation" in stdout
    assert "scaffold text" not in stdout


def test_pdsl_unsupported_scaffold_is_error() -> None:
    set_json_mode(False)
    rc, stdout, _stderr = _run(["pdsl", "scaffold", "--json"])

    assert rc == 1
    payload = json.loads(stdout)
    assert payload["status"] == "ERROR"
    assert payload["supported"] == ["validate"]


# Migration note (legacy multi-phase workflow removal + routing update):
# test_cf_pdsl_workflow_reuses_pdsl_validate_command previously opened
# workflows/pdsl.md (deleted; there is no standalone pdsl workflow) and
# asserted a UNIT PdslCommandValidationReuse that no longer exists. The
# `cfs pdsl validate` command now lives in the deterministic prompt-validation
# workflow, workflows/prompting-ci.md, so this test is grounded there.
def test_cf_pdsl_workflow_reuses_pdsl_validate_command() -> None:
    workflow = Path(__file__).resolve().parents[1] / "workflows" / "prompting-ci.md"
    text = workflow.read_text(encoding="utf-8")

    assert "UNIT PromptingCiPreset" in text
    assert "{cfs_cmd} pdsl validate" in text


def test_pdsl_result_serialization_verbose_and_error_locations() -> None:
    finding = PdslFinding(
        rule_id="PDSL200",
        severity="error",
        message="bad starter",
        source_path="sample.md",
        block_index=0,
        line=2,
        column=3,
        end_line=2,
        end_column=12,
        hint="Use RUN.",
        context="- BAD action",
    )
    error = PdslError("cannot read", "missing.md", line=4, column=5, kind="READ_ERROR")
    result = error_result("missing.md", error)
    envelope = build_envelope([result], command="pdsl validate", verbose=True)

    assert "context" not in finding.to_dict()
    assert finding.to_dict(verbose=True)["context"] == "- BAD action"
    assert error.to_dict()["line"] == 4
    assert error.to_dict()["column"] == 5
    assert result.status == "ERROR"
    assert envelope["ok"] is False
    assert envelope["results"][0]["errors"][0]["kind"] == "READ_ERROR"
    assert exit_code_for_results([result]) == 1


def test_pdsl_read_source_file_reports_utf8_decode_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe")

    text, error = read_source_file(bad)

    assert text is None
    assert error is not None
    assert error.kind == "DECODE_ERROR"


def test_pdsl_scan_flags_wrong_and_unclosed_fences() -> None:
    text = """```text
UNIT WrongFence
```
```pdsl
UNIT OpenFence
"""

    blocks, findings = scan_blocks("sample.md", text)

    assert blocks == []
    assert [finding.rule_id for finding in findings] == ["PDSL100", "PDSL100"]
    assert findings[0].message == "PDSL-shaped instruction block must use a ```pdsl fence"
    assert findings[1].message == "Unclosed ```pdsl fence"


def test_pdsl_validate_source_covers_structural_edge_cases() -> None:
    text = """MENU Pick
TITLE:
  Pick one.
OPTIONS:
  1 one -> RETURN ok
  - two -> RETURN bad
  - 3 three -> RETURN bad
UNIT Dup
UNIT Dup
IGNORED_LABEL:
  - This is prompt-adjacent metadata
PATTERNS:
  known: /ok/
  known: /again/
DO:
      - RUN deeply indented ignored
  - RUN matches(reply, missing)
STATE:
  - LOAD invalid state starter
WHEN:
  - SET invalid when starter
RULES:
  - RUN invalid rule starter
"""

    result = validate_source(PdslSource("edge.md", text))

    assert result.status == "FAIL"
    messages = [finding.message for finding in result.findings]
    assert "MENU OPTIONS item must start with a decimal number and contain ->" in messages
    assert "MENU option number must be 2, got 3" in messages
    assert "Duplicate UNIT name `Dup` in source" in messages
    assert "Duplicate PATTERNS name `known`" in messages
    assert "Undefined local matches() pattern `missing`" in messages
    assert any("STATE item must start with one of: SET; got LOAD" in msg for msg in messages)
    assert any("WHEN item must start with one of:" in msg and "got SET" in msg for msg in messages)
    assert any("RULES item must start with one of:" in msg and "got RUN" in msg for msg in messages)


def test_pdsl_validate_starter_keyword_check_applies_to_dashless_items() -> None:
    """TK-02: PDSL200 (starter keyword validation) applies to dashless items too."""
    text = """UNIT DashlessStarters
DO:
      RUN deeply indented ignored
  RUN a valid action
STATE:
  LOAD invalid state starter
WHEN:
  SET invalid when starter
RULES:
  RUN invalid rule starter
"""

    result = validate_source(PdslSource("dashless-starters.md", text))

    assert result.status == "FAIL"
    messages = [finding.message for finding in result.findings]
    assert any("STATE item must start with one of: SET; got LOAD" in msg for msg in messages)
    assert any("WHEN item must start with one of:" in msg and "got SET" in msg for msg in messages)
    assert any("RULES item must start with one of:" in msg and "got RUN" in msg for msg in messages)


def test_pdsl_validate_dashless_menu_placeholder_is_not_a_do_item() -> None:
    """A `MENU <name>:` illustrative placeholder inside DO must not be read as a dashless action.

    Regression: PDSL.md's own "Core Shape" example shows an unrecognized (non-
    identifier) `MENU <name>:` block nested under DO; UNIT/MENU are reserved
    block-starter keywords and must never be misread as a DO/RULES/etc. item.
    """
    text = """UNIT <name>

DO:
  - RUN <ordered actions>

MENU <name>:
  TITLE: <menu title>
  OPTIONS:
    1 <choice> -> <actions>
"""

    result = validate_source(PdslSource("menu-placeholder.md", text))
    assert result.status == "PASS"


def _do_unit(action_count: int) -> str:
    actions = "\n".join(f"  - SET STEP_{i} = true" for i in range(1, action_count + 1))
    return f"UNIT DoCapUnit\nDO:\n{actions}\n"


def _rules_unit(rule_count: int) -> str:
    rules = "\n".join(f"  - ALWAYS rule {i}" for i in range(1, rule_count + 1))
    return f"UNIT RulesCapUnit\nRULES:\n{rules}\n"


def test_pdsl_validate_enforces_do_and_rules_caps() -> None:
    at_cap = validate_source(PdslSource("do-7.md", _do_unit(7)))
    over_cap = validate_source(PdslSource("do-9.md", _do_unit(9)))
    rules_at_cap = validate_source(PdslSource("rules-5.md", _rules_unit(5)))
    rules_over_cap = validate_source(PdslSource("rules-6.md", _rules_unit(6)))

    assert at_cap.status == "PASS"
    assert over_cap.status == "FAIL"
    assert [f.rule_id for f in over_cap.findings] == ["PDSL600"]
    assert "exceeds the 7-action DO cap" in over_cap.findings[0].message
    assert over_cap.findings[0].line == 10  # the 8th action line, where the cap is first crossed

    assert rules_at_cap.status == "PASS"
    assert rules_over_cap.status == "FAIL"
    assert [f.rule_id for f in rules_over_cap.findings] == ["PDSL601"]
    assert "exceeds the 5-rule cap" in rules_over_cap.findings[0].message


def test_pdsl_validate_do_cap_accumulates_across_multiple_do_sections() -> None:
    """A UNIT must not bypass PDSL600 by splitting actions across two DO: sections."""
    text = """UNIT SplitDoUnit
DO:
  - RUN action one
  - RUN action two
  - RUN action three
  - RUN action four
DO:
  - RUN action five
  - RUN action six
  - RUN action seven
  - RUN action eight
"""
    result = validate_source(PdslSource("split-do.md", text))
    assert result.status == "FAIL"
    assert [f.rule_id for f in result.findings] == ["PDSL600"]


def test_pdsl_validate_do_cap_applies_to_dashless_units() -> None:
    """TK-02: the DO cap applies uniformly whether or not actions use a leading `- `."""
    at_cap = """UNIT NoDashAtCap
DO:
  SET STEP_1 = true
  SET STEP_2 = true
  SET STEP_3 = true
  SET STEP_4 = true
  SET STEP_5 = true
  SET STEP_6 = true
  SET STEP_7 = true
"""
    over_cap = """UNIT NoDashOverCap
DO:
  SET STEP_1 = true
  SET STEP_2 = true
  SET STEP_3 = true
  SET STEP_4 = true
  SET STEP_5 = true
  SET STEP_6 = true
  SET STEP_7 = true
  SET STEP_8 = true
  SET STEP_9 = true
"""

    at_cap_result = validate_source(PdslSource("dashless-at-cap.md", at_cap))
    over_cap_result = validate_source(PdslSource("dashless-over-cap.md", over_cap))

    assert at_cap_result.status == "PASS"
    assert over_cap_result.status == "FAIL"
    assert [f.rule_id for f in over_cap_result.findings] == ["PDSL600"]
    assert "exceeds the 7-action DO cap" in over_cap_result.findings[0].message


def test_pdsl_validate_do_cap_ignores_continuation_lines_dashed_and_dashless() -> None:
    """Continuation lines never count toward the cap, regardless of dash usage."""
    continuation = """UNIT ContinuationUnit
DO:
  - RUN one action
    with a continuation line that must not be counted
    and another one
  - RUN second action
"""
    dashless_continuation = """UNIT DashlessContinuationUnit
DO:
  RUN one action
    with a continuation line that must not be counted
    and another one
  RUN second action
"""

    continuation_result = validate_source(PdslSource("continuation.md", continuation))
    dashless_continuation_result = validate_source(PdslSource("dashless-continuation.md", dashless_continuation))

    assert continuation_result.status == "PASS"
    assert dashless_continuation_result.status == "PASS"


def test_pdsl_validate_do_cap_does_not_misread_capitalized_prose_as_an_action() -> None:
    """A capitalized continuation line that isn't a known DO keyword must not count."""
    text = """UNIT ProseContinuationUnit
DO:
  - RUN one action
    Important: this note starts with a capital letter but is not a new action
  - RUN second action
"""
    result = validate_source(PdslSource("prose-continuation.md", text))
    assert result.status == "PASS"


def _gate_menu(
    *,
    declared: str = "",
    extra: str = "",
    tail: str = "",
    indent: str = "  ",
    name: str = "GateMenu",
) -> str:
    """Build a well-formed MENU, optionally carrying a gate risk declaration.

    `indent` is a parameter because both shapes occur in shipped PDSL: the spec's
    grammar indents MENU sub-headers, and some modules write them at column 0.
    The rules must not depend on which.
    """
    lines = [f"MENU {name}:", f"{indent}TITLE: Pick one"]
    if declared:
        lines.append(f"{indent}TYPE: {declared}")
    if extra:
        lines.append(f"{indent}{extra}")
    lines += [
        f"{indent}OPTIONS:",
        f"{indent}  1 yes -> CONTINUE CurrentWorkflow",
        f"{indent}  2 no -> CONTINUE CurrentWorkflow",
        f"{indent}INVALID:",
        f'{indent}  EMIT "Reply with 1 or 2."',
        f"{indent}  WAIT user.reply",
        f"{indent}  STOP_TURN",
    ]
    return "\n".join(lines) + "\n" + tail


def _rule_ids(text: str, source: str = "gate.md") -> list[str]:
    return [f.rule_id for f in validate_source(PdslSource(source, text)).findings]


def test_gate_type_accepts_each_declared_risk_in_both_menu_shapes() -> None:
    """All three risk types are recognized, indented or at column 0."""
    for indent in ("  ", ""):
        for declared in ("confirmation", "decision", "blocking"):
            assert _rule_ids(_gate_menu(declared=declared, indent=indent)) == [], (indent, declared)


def test_gate_type_absent_is_valid() -> None:
    """Absence is never an error: an undeclared gate is treated as `blocking`.

    This is what lets the existing menu surface migrate gate by gate instead of
    in one change, so it is asserted for both menu shapes and with prose present.
    """
    for indent in ("  ", ""):
        assert _rule_ids(_gate_menu(indent=indent)) == [], indent
    assert _rule_ids(_gate_menu(extra="NOTE: choose 1 to keep going")) == []


def test_gate_type_must_be_one_literal_enum_token() -> None:
    """Each probe that passed silently before must now fail exactly once.

    A variable, an interpolation, a trailing condition and an unknown word are
    all runtime decisions wearing a declaration's clothes.
    """
    for value in (
        "urgent",
        "{GATE_TYPE}",
        "confirmation WHEN SIMPLE_MODE == normal",
        "Confirmation",
        "<confirmation | decision | blocking>",
    ):
        assert _rule_ids(_gate_menu(declared=value)) == ["PDSL700"], value

    # A bare `TYPE:` with no value declares nothing but is still a declaration.
    assert _rule_ids(_gate_menu(extra="TYPE:")) == ["PDSL700"]


def test_gate_type_message_is_bounded() -> None:
    """A finding interpolates author text, so its length must not follow the input."""
    findings = validate_source(PdslSource("long.md", _gate_menu(declared="x" * 100_000))).findings
    assert [f.rule_id for f in findings] == ["PDSL700"]
    assert len(findings[0].message) < 200


def test_the_elision_boundary_is_exact() -> None:
    """A value at the limit is kept whole; one character more is shortened."""
    at_limit = validate_source(PdslSource("a.md", _gate_menu(declared="x" * 60))).findings
    assert "x" * 60 in at_limit[0].message
    over = validate_source(PdslSource("b.md", _gate_menu(declared="x" * 61))).findings
    assert "..." in over[0].message
    assert "x" * 61 not in over[0].message


def test_gate_type_is_rejected_twice_in_one_menu() -> None:
    """Two declarations make the effective risk depend on read order."""
    text = _gate_menu(declared="decision").replace(
        "  TYPE: decision", "  TYPE: decision\n  TYPE: confirmation", 1)
    findings = validate_source(PdslSource("double.md", text)).findings
    assert [f.rule_id for f in findings] == ["PDSL701"]
    assert "more than once" in findings[0].message


def test_gate_type_is_reported_where_nothing_reads_it() -> None:
    """A declaration outside a MENU, or nested in its body, is inert."""
    outside = "UNIT Demo\n\nPURPOSE:\n  Do a thing.\n\nTYPE: blocking\n\nDO:\n  - RUN Something\n"
    assert _rule_ids(outside) == ["PDSL702"]

    # Trailing prose after a menu is not part of it.
    assert _rule_ids(_gate_menu(tail="NOTES:\n  TYPE: confirmation\n")) == ["PDSL702"]

    # Nested inside an option's action body.
    nested = (
        "MENU G:\n  TITLE: t\n  OPTIONS:\n"
        "    1 x -> CONTINUE CurrentWorkflow\n      TYPE: blocking\n"
    )
    assert _rule_ids(nested) == ["PDSL702"]


def test_the_declaration_region_ends_at_a_section_that_is_not_title_or_type() -> None:
    """A near-miss outside the declaration region is prose, not a botched declaration.

    This is the observable consequence of the region rule. An earlier version
    of this test used prose without a colon in the tail, which no gate rule can
    read either way -- so the entire region mechanism could be deleted with the
    suite still green.
    """
    for section in ("NOTES", "RULES", "INVARIANTS", "ON_ERROR"):
        tail = f"{section}:\n  TYP: blocking\n"
        assert _rule_ids(_gate_menu(tail=tail)) == [], section

    # Inside the region the same header is reported.
    assert _rule_ids(_gate_menu(extra="TYP: blocking")) == ["PDSL703"]


def test_the_declaration_region_does_not_suppress_pre_existing_menu_checks() -> None:
    """A section between the MENU header and OPTIONS must not disable PDSL400.

    An earlier attempt tracked menu *extent* by clearing `in_menu`, which left
    `menu_expected` unset and silently switched off option numbering for the
    rest of the block.
    """
    text = (
        "MENU M:\nTITLE: t\nNOTES:\n  Suggested: pick 1.\n"
        "OPTIONS:\n7 a -> RUN X\n9 b\n"
    )
    assert _rule_ids(text) == ["PDSL400", "PDSL400"]


def test_a_declaration_nested_in_the_menu_body_is_inert() -> None:
    """The region, not indentation, is what decides whether a declaration is read.

    An indent rule was tried and removed: it protected nothing the region rule
    does not already cover -- a declaration in the body is past the region
    either way -- while adding false positives on tabs and unusual spacing, and
    it did not apply at all when `TYPE` came first, which is the canonical
    ordering.
    """
    nested_invalid = (
        "MENU G:\n  OPTIONS:\n    1 a -> CONTINUE X\n"
        "  INVALID:\n    TITLE: retry?\n    TYPE: confirmation\n"
    )
    assert _rule_ids(nested_invalid) == ["PDSL702"]

    after_options = "MENU G:\n  OPTIONS:\n    1 a -> CONTINUE X\n  TYPE: blocking\n"
    assert _rule_ids(after_options) == ["PDSL702"]

    # Indentation alone is not a defect: the declaration is still in the region.
    deep_but_in_region = (
        "MENU G:\n  TITLE: t\n              TYPE: blocking\n  OPTIONS:\n    1 a -> CONTINUE X\n"
    )
    assert _rule_ids(deep_but_in_region) == []


def test_a_declaration_before_title_is_the_canonical_shape() -> None:
    """The spec puts TYPE directly under the MENU header; TITLE need not precede it."""
    text = "MENU G:\n  TYPE: blocking\n  TITLE: t\n  OPTIONS:\n    1 a -> CONTINUE X\n"
    assert _rule_ids(text) == []


def test_a_declaration_outside_any_menu_is_reported_with_no_preceding_section() -> None:
    """`state.section` is None straight after a UNIT header; the menu check must still bite."""
    assert _rule_ids("UNIT Demo\n\nTYPE: blocking\n\nDO:\n  - RUN Something\n") == ["PDSL702"]


def test_a_declaration_needs_no_space_after_the_colon() -> None:
    """`TYPE:blocking` is the same declaration; the value offset must not be off by one."""
    text = "MENU G:\n  TITLE: t\n  TYPE:blocking\n  OPTIONS:\n    1 a -> CONTINUE X\n"
    assert _rule_ids(text) == []


def test_gate_findings_point_at_the_declaring_line() -> None:
    """A finding that names the wrong line sends the reader to the wrong place."""
    bad_value = validate_source(PdslSource("v.md", _gate_menu(declared="urgent"))).findings
    assert [(f.rule_id, f.line) for f in bad_value] == [("PDSL700", 3)]

    duplicate = validate_source(
        PdslSource("d.md", _gate_menu(declared="blocking", extra="TYPE: decision"))).findings
    assert [(f.rule_id, f.line) for f in duplicate] == [("PDSL701", 4)]
    assert "at line 3" in duplicate[0].hint

    misplaced = validate_source(
        PdslSource("m.md", _gate_menu(tail="NOTES:\n  TYPE: confirmation\n"))).findings
    assert [(f.rule_id, f.line) for f in misplaced] == [("PDSL702", 11)]

    near_miss = validate_source(PdslSource("n.md", _gate_menu(extra="TYP: blocking"))).findings
    assert [(f.rule_id, f.line) for f in near_miss] == [("PDSL703", 3)]


def test_duplicate_finding_message_is_bounded() -> None:
    """PDSL701 interpolates the menu name, so it must be elided like the value is."""
    long_name = "M" * 100_000
    findings = validate_source(PdslSource(
        "long.md", _gate_menu(declared="blocking", extra="TYPE: decision", name=long_name))).findings
    assert [f.rule_id for f in findings] == ["PDSL701"]
    assert len(findings[0].message) < 200


def test_a_malformed_gate_header_is_reported() -> None:
    """A near-miss must not silently leave a gate undeclared."""
    for variant in (
        "TYP: blocking",
        "TYPO: blocking",
        "TYPES: blocking",
        "Type: blocking",
        "type: blocking",
        "tYpE: blocking",
        "TYPE : blocking",
        "- TYPE: blocking",
        "RISK: blocking",
        "GATE_TYPE: blocking",
        # transpositions: plain Levenshtein scores these 2 and would let them past
        "TPYE: blocking",
        "TYEP: blocking",
        # decorated or bulleted forms, which are not headers at all
        "* TYPE: blocking",
        "+ TYPE: blocking",
        "`TYPE: blocking`",
        "**TYPE:** blocking",
        "(TYPE: blocking)",
        # a separator PDSL does not use, and none at all
        "TYPE = blocking",
        "TYPE blocking",
        # a hyphenated alias, and a Cyrillic lookalike of the leading T
        "RISK-TYPE: blocking",
        "\u0422YPE: blocking",
    ):
        assert _rule_ids(_gate_menu(extra=variant)) == ["PDSL703"], variant


def test_prose_and_control_flow_headers_are_not_gate_declarations() -> None:
    """MENU blocks legitimately carry prose and control flow; those must pass.

    `ELSE:` inside an INVALID body is real PDSL (requirements/storytelling-modes.md),
    and banning every unrecognized header would only grow an exemption list.
    """
    for benign in (
        "NOTE: choose 1",
        "NOTES: choose 1",
        "ELSE: fall back to option 2",
        "TIME: 30s",
        "TIPS: read the plan first",
        "IMPORTANT: this is prose",
        "STYLE: terse",
        # near-miss name, but no separator and no gate-type value: ordinary prose
        "Tape recorder notes",
        "Types of plan we support",
    ):
        assert _rule_ids(_gate_menu(extra=benign)) == [], benign


def test_gate_rules_apply_to_every_menu_in_a_block_not_only_the_last() -> None:
    """Per-menu state must reset at each MENU boundary and not leak across it."""
    good_then_bad = _gate_menu(declared="blocking", name="First") + "\n" + _gate_menu(
        declared="urgent", name="Second")
    assert _rule_ids(good_then_bad) == ["PDSL700"]

    bad_then_good = _gate_menu(declared="urgent", name="First") + "\n" + _gate_menu(
        declared="blocking", name="Second")
    assert _rule_ids(bad_then_good) == ["PDSL700"]

    # A declaration in the first menu must not count as the second's.
    both = _gate_menu(declared="blocking", name="First") + "\n" + _gate_menu(
        declared="decision", name="Second")
    assert _rule_ids(both) == []


def test_gate_rules_leave_the_shipped_tree_byte_identical() -> None:
    """This change must be inert on shipped PDSL, and the counts are pinned.

    Filtering to the new band only would miss a regression in the shared parsing
    this change touches, so the whole tally is asserted.
    """
    repo_root = Path(__file__).resolve().parents[1]
    # The corpus is the four authored-prompt roots the repo's PDSL CI already
    # validates (`PROMPT_ROOTS` in tests/test_pdsl_keywords.py), collected in
    # sorted order so the scan is deterministic. It is deliberately the whole
    # authored surface rather than a sample: the point is that this change is
    # inert on everything shipped, which a sample cannot establish.
    #
    # Generated and vendored trees are excluded by directory name, and the
    # count is tripwired, so a generated tree landing under one of the roots
    # fails with an explanation. Indentation is measured in spaces throughout;
    # no authored PDSL block line uses tab indentation.
    roots = tuple(repo_root / name
                  for name in ("skills", "workflows", "requirements", "architecture"))
    sources = sorted(
        path for root in roots for path in root.rglob("*.md")
        if not GENERATED_DIRECTORIES & set(path.relative_to(repo_root).parts)
    )
    assert sources, "expected shipped PDSL sources to scan"
    assert len(sources) <= AUTHORED_CORPUS_CEILING, (
        f"{len(sources)} authored sources exceeds the expected ceiling of "
        f"{AUTHORED_CORPUS_CEILING}; if the surface has genuinely grown, raise it "
        f"deliberately, and if a generated tree has landed under one of the roots, "
        f"add its directory to GENERATED_DIRECTORIES instead."
    )
    counts: dict[str, int] = {}
    for path in sources:
        text, error = read_source_file(path)
        if error or text is None:
            continue
        for finding in validate_source(PdslSource(source=str(path), text=text)).findings:
            counts[finding.rule_id] = counts.get(finding.rule_id, 0) + 1
    assert counts == {"PDSL200": 23, "PDSL600": 85, "PDSL601": 148}, counts


# --- property-based checks over generated input -----------------------------
# Stdlib only: random.Random(seed) keeps them deterministic without adding a
# dependency. These assert invariants over inputs nobody hand-picked, which is
# how the trailing-prose defect in _handle_section_header_line was found.

PROPERTY_ITERATIONS = 400
# Directory names that never hold authored PDSL. Excluded from the whole-tree
# scan so a generated or vendored subtree cannot grow a unit test's cost.
GENERATED_DIRECTORIES = frozenset({
    "node_modules", "vendor", "dist", "build", "__pycache__", "htmlcov",
    ".cache", ".venv", "site-packages",
})
# A tripwire, not a cost bound — measured, the whole-tree scan is ~0.13s for
# ~354 sources, so this fires at roughly 0.22s. Its value is the error message:
# a generated tree landing under a root whose directory name is not in
# GENERATED_DIRECTORIES fails here with an explanation rather than as an
# unexplained tally change.
AUTHORED_CORPUS_CEILING = 600
_GATE_FINDINGS = ("PDSL700", "PDSL701", "PDSL702", "PDSL703")


def _gate_rule_ids(text: str) -> list[str]:
    return [r for r in _rule_ids(text, "prop.md") if r in _GATE_FINDINGS]


def test_property_edit_distance_obeys_the_properties_it_actually_has() -> None:
    """Optimal string alignment is NOT a metric -- it violates the triangle inequality.

    `d("CA","ABC")` is 3 while `d("CA","AC") + d("AC","ABC")` is 2. An earlier
    version of this test asserted the inequality anyway and passed only because
    the generator rarely produced a violating triple. The rule does not need a
    metric: it compares one fixed target against a fixed threshold, so what has
    to hold is identity, symmetry and the length bounds.
    """
    rng = random.Random(20260907)
    alphabet = "TYPERECOMNDABZ_-0123"
    for _ in range(PROPERTY_ITERATIONS):
        left = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 12)))
        right = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 12)))

        assert _edit_distance(left, left) == 0
        assert (_edit_distance(left, right) == 0) == (left == right)
        assert _edit_distance(left, right) == _edit_distance(right, left)
        assert abs(len(left) - len(right)) <= _edit_distance(left, right)
        assert _edit_distance(left, right) <= max(len(left), len(right))


def test_property_validation_never_raises_on_arbitrary_text() -> None:
    """The validator runs over hundreds of files in CI; one odd file must not abort it."""
    rng = random.Random(20260908)
    fragments = [
        "MENU G:", "UNIT U", "TITLE: t", "TYPE:", "TYPE: blocking", "TYPE : x", "- TYPE: x",
        "Type: x", "OPTIONS:", "  1 a -> DO x", "INVALID:", '  EMIT "no"', "STOP_TURN",
        "NOTES:", "RULES:", "```pdsl", "```", "", "   ", "\t", "<name>", "9" * 4400,
        "TYPE: \u202e x", "TYPE: \x00", "MENU :", "MENU <unclosed", "PURPOSE:", "??:",
        "A" * 300 + ":", "\u0661" * 4400,
    ]
    for _ in range(PROPERTY_ITERATIONS):
        text = "\n".join(rng.choice(fragments) for _ in range(rng.randint(1, 25))) + "\n"
        validate_source(PdslSource("fuzz.md", text))


def _generated_menu(rng: random.Random, *, declared: str | None, slot: str) -> str:
    """Assemble a menu placing a declaration in one named slot.

    Placement, not content, is the axis that matters: the read slots are the
    menu's own sub-header level before OPTIONS; everything else is unread.
    """
    indent = rng.choice(("  ", "    ", ""))
    name = f"Menu{rng.randint(1, 9999)}"
    declaration = f"TYPE: {declared}" if declared else None
    prose = rng.choice(("NOTE: prose", "NOTES: prose", "ELSE: fall back", "TIME: 30s", None))

    head = [f"MENU {name}:"]
    if declaration and slot == "before-title":
        head.append(f"{indent}{declaration}")
    head.append(f"{indent}TITLE: Pick one")
    if declaration and slot == "after-title":
        head.append(f"{indent}{declaration}")
    if prose:
        head.append(f"{indent}{prose}")
    head.append(f"{indent}OPTIONS:")
    head.append(f"{indent}  1 yes -> CONTINUE CurrentWorkflow")
    if declaration and slot == "in-options":
        head.append(f"{indent}    {declaration}")
    head.append(f"{indent}  2 no -> CONTINUE CurrentWorkflow")
    head.append(f"{indent}INVALID:")
    head.append(f'{indent}  EMIT "Reply with 1 or 2."')
    if declaration and slot == "in-invalid":
        head.append(f"{indent}    {declaration}")
    head.append(f"{indent}  WAIT user.reply")
    head.append(f"{indent}  STOP_TURN")
    text = "\n".join(head) + "\n"
    if declaration and slot == "in-tail":
        text += f"NOTES:\n  {declaration}\n"
    return text


READ_SLOTS = ("before-title", "after-title")
UNREAD_SLOTS = ("in-options", "in-invalid", "in-tail")


BENIGN_HEADERS = (
    "NOTE: prose", "NOTES: prose", "ELSE: fall back", "TIME: 30s", "TIPS: read it",
    "IMPORTANT: prose mentioning TYPE and RUN", "STYLE: terse", "Tape recorder notes",
    "Types of plan we support", "GATE: blocking",
)


def test_property_an_undeclared_menu_never_yields_a_gate_finding() -> None:
    """Absence is valid whatever surrounds it -- the migration depends on this.

    Varies the prose that surrounds the menu, at both column 0 and indented,
    since a `declared=None` menu has no declaration slot to vary.
    """
    rng = random.Random(20260909)
    for _ in range(PROPERTY_ITERATIONS):
        indent = rng.choice(("  ", "    ", ""))
        prose = [
            f"{rng.choice((indent, ''))}{rng.choice(BENIGN_HEADERS)}"
            for _ in range(rng.randint(0, 3))
        ]
        lines = [f"MENU Menu{rng.randint(1, 9999)}:", f"{indent}TITLE: Pick one"]
        lines += prose
        lines += [
            f"{indent}OPTIONS:",
            f"{indent}  1 yes -> CONTINUE CurrentWorkflow",
            f"{indent}INVALID:",
            f'{indent}  EMIT "Reply with 1."',
            # A prompt is followed by a wait before the stop, as every example in
            # the spec is: a fixture must not model a stop the user cannot answer.
            f"{indent}  WAIT user.reply",
            f"{indent}  STOP_TURN",
        ]
        tail = rng.choice(("", "NOTES:\n  Prose about TYPE and RUN.\n", "RULES:\n  ALWAYS x\n"))
        text = "\n".join(lines) + "\n" + tail
        assert _gate_rule_ids(text) == [], text


def test_property_a_declaration_in_a_read_slot_is_accepted() -> None:
    """A valid declaration at the menu's own sub-header level must validate clean."""
    rng = random.Random(20260910)
    for _ in range(PROPERTY_ITERATIONS):
        text = _generated_menu(
            rng,
            declared=rng.choice(("confirmation", "decision", "blocking")),
            slot=rng.choice(READ_SLOTS),
        )
        assert _gate_rule_ids(text) == [], text


def test_property_a_declaration_in_an_unread_slot_is_reported() -> None:
    """Nothing reads a declaration nested in the body or trailing the menu.

    Accepting one there is how a gate would gain authority its author did not
    put where the runtime looks for it.
    """
    rng = random.Random(20260912)
    for _ in range(PROPERTY_ITERATIONS):
        text = _generated_menu(
            rng,
            declared=rng.choice(("confirmation", "decision", "blocking")),
            slot=rng.choice(UNREAD_SLOTS),
        )
        assert _gate_rule_ids(text) == ["PDSL702"], text


def test_property_findings_are_deterministic_and_ordered() -> None:
    """Sorted, repeatable findings are promised by the CDSL contract."""
    rng = random.Random(20260911)
    # Only the repeatability half of this can fail: `validate_source` sorts
    # before returning, so asserting its output is sorted is tautological.
    # Several findings per variant still matter -- a single finding is trivially
    # repeatable and would not exercise the comparison at all.
    variants = [
        _gate_menu(extra="TYP: x", name="A") + _gate_menu(declared="urgent", name="B"),
        _gate_menu(extra='TYPE = matches(x, "nope")', name="C"),
        _gate_menu(declared="urgent", name="D") + _gate_menu(extra="RISK: x", name="E"),
        _gate_menu(declared="blocking", extra="TYPE: decision", name="F")
        + _gate_menu(extra="Type: blocking", name="G"),
        # Two fenced blocks, so gate findings come from more than one block.
        # Both fences are closed and both menus carry a gate defect on purpose:
        # leaving the second fence open made its finding PDSL100 -- about fence
        # syntax rather than a gate -- so the variant said nothing the others
        # did not already cover.
        "```pdsl\n" + _gate_menu(extra="TYP: blocking", name="H") + "```\n\n```pdsl\n"
        + _gate_menu(declared="urgent", name="I") + "```\n",
    ]
    for _ in range(PROPERTY_ITERATIONS // 4):
        text = rng.choice(variants)
        # The documented order is source order, then line, column, rule id.
        runs = [
            [(f.block_index, f.line, f.column, f.rule_id)
             for f in validate_source(PdslSource("d.md", text)).findings]
            for _ in range(3)
        ]
        assert len(runs[0]) >= 2, f"variant must yield several findings: {runs[0]}"
        assert runs[0] == runs[1] == runs[2], text


def test_every_rejected_alias_is_reported_in_both_spellings() -> None:
    """Each alias earns its place, and hyphen and underscore are equivalent."""
    for alias in ("RISK", "RISK_TYPE", "GATE_RISK", "GATE_TYPE", "MENU_TYPE", "RISK_LEVEL"):
        for spelling in (alias, alias.replace("_", "-")):
            assert _rule_ids(_gate_menu(extra=f"{spelling}: blocking")) == ["PDSL703"], spelling


def test_gate_is_not_an_alias() -> None:
    """`GATE:` is plausible as a sub-header in a codebase about gates.

    Treating it as a typo of `TYPE` would annoy more often than it would help.
    """
    assert _rule_ids(_gate_menu(extra="GATE: blocking")) == []


def test_a_short_value_is_never_elided() -> None:
    """The elision boundary is inclusive, so an ordinary value is quoted whole."""
    findings = validate_source(PdslSource("s.md", _gate_menu(declared="urgent"))).findings
    assert "`urgent`" in findings[0].message


def test_an_elided_value_is_exactly_the_cap_in_length() -> None:
    """The shortened value must not exceed the cap it is shortened to."""
    findings = validate_source(PdslSource("e.md", _gate_menu(declared="x" * 500))).findings
    quoted = findings[0].message.split("`")[1]
    assert len(quoted) == 60
    assert quoted.endswith("...")


def test_a_malformed_gate_header_line_is_still_offered_to_the_other_checks() -> None:
    """Reporting a botched declaration must not mask an unrelated finding on it."""
    text = (
        'MENU G:\n  TITLE: t\n  TYPE = matches(x, "nope")\n'
        "  OPTIONS:\n    1 a -> CONTINUE CurrentWorkflow\n"
    )
    assert _rule_ids(text) == ["PDSL703", "PDSL500"]


def test_confusable_lookalikes_are_normalized_before_the_near_miss_test() -> None:
    """A Cyrillic letter that renders identically must not hide a declaration."""
    for variant in ("\u0422YPE: blocking", "T\u0423PE: blocking", "TYP\u0415: blocking"):
        assert _rule_ids(_gate_menu(extra=variant)) == ["PDSL703"], repr(variant)


def test_a_zero_width_character_cannot_hide_a_gate_declaration() -> None:
    """An invisible character reads as a declaration and must not pass as prose."""
    for variant in (
        "TYPE\u200b: blocking",
        "TYP\u200bE: blocking",
        "\u200bTYPE: blocking",
        "TYPE\ufeff: blocking",
        "TYPE\u2060: blocking",
    ):
        assert _rule_ids(_gate_menu(extra=variant)) == ["PDSL703"], repr(variant)


def test_decoration_is_discarded_rather_than_enumerated() -> None:
    """Any decoration around the name reduces to the same candidate.

    Three review passes each found forms an enumerating pattern had missed, so
    the rule discards non-alphanumerics instead of listing what they can be.
    """
    for variant in (
        "`TYPE`: blocking", "``TYPE``: blocking", "[TYPE]: blocking", "(TYPE): blocking",
        "{TYPE}: blocking", "<TYPE>: blocking", '"TYPE": blocking', "'TYPE': blocking",
        "_TYPE_: blocking", "__TYPE__: blocking", "TYPE__: blocking", "#TYPE: blocking",
        "> TYPE: blocking", "TYPE -> blocking", "TYPE => blocking",
    ):
        assert _rule_ids(_gate_menu(extra=variant)) == ["PDSL703"], variant


def test_edit_distance_returns_the_documented_values() -> None:
    """Pinned values, because the axioms alone are satisfied by broken variants."""
    assert _edit_distance("", "") == 0
    assert _edit_distance("TYPE", "TYPE") == 0
    assert _edit_distance("TYP", "TYPE") == 1
    assert _edit_distance("TYPES", "TYPE") == 1
    assert _edit_distance("TY", "YT") == 1, "an adjacent transposition costs one"
    assert _edit_distance("TPYE", "TYPE") == 1
    assert _edit_distance("TTT", "T") == 2
    assert _edit_distance("TIME", "TYPE") == 2, "distance 2 is outside the threshold"


def test_gate_findings_pin_their_column() -> None:
    """A finding's column is part of its address and of the sort order."""
    for text, rule in (
        (_gate_menu(declared="urgent"), "PDSL700"),
        (_gate_menu(extra="TYP: blocking"), "PDSL703"),
    ):
        findings = validate_source(PdslSource("c.md", text)).findings
        assert [(f.rule_id, f.column) for f in findings] == [(rule, 1)], rule


def test_a_reported_header_keeps_the_authors_own_spelling() -> None:
    """The finding must echo what was written, not the normalized form.

    Normalization exists to recognize the attempt; showing the folded name back
    would tell an author their correct-looking line is wrong without saying why.
    """
    findings = validate_source(PdslSource(
        "sp.md", _gate_menu(extra="ТYPE: blocking"))).findings
    assert [f.rule_id for f in findings] == ["PDSL703"]
    assert "ТYPE" in findings[0].message


def test_aliases_are_reported_on_the_prose_path_too() -> None:
    """An alias containing `_` must survive the candidate scan, not just the header one.

    The header path reaches these through SECTION_HEAD_RE; a decorated one only
    reaches them through the candidate scan, which must keep `_` inside a name.
    """
    for variant in ("- GATE_TYPE: blocking", "`MENU_TYPE`: blocking", "* RISK_LEVEL: blocking"):
        assert _rule_ids(_gate_menu(extra=variant)) == ["PDSL703"], variant


def test_more_than_one_confusable_is_still_recognized() -> None:
    """A single lookalike survives on distance alone; two need the mapping."""
    assert _rule_ids(_gate_menu(extra="ТУPE: blocking")) == ["PDSL703"]
    assert _rule_ids(_gate_menu(extra="ΤΥΡΕ: blocking")) == ["PDSL703"]


def test_the_duplicate_finding_names_the_offending_menu() -> None:
    """`menu_name` must be set at the boundary, not merely non-empty.

    Dropping it would make the bounded-message test pass trivially, since an
    absent name is also a short one.
    """
    findings = validate_source(PdslSource("nm.md", _gate_menu(
        declared="blocking", extra="TYPE: decision", name="MyGate"))).findings
    assert [f.rule_id for f in findings] == ["PDSL701"]
    assert "`MyGate`" in findings[0].message


def test_lower_and_mixed_case_prose_is_not_a_declaration_attempt() -> None:
    """PDSL headers are upper-case, so front matter and prose must stay quiet.

    Reported only when the value is a gate type, which is the miscasing the
    reported gap names (`Type: blocking`).
    """
    for benign in (
        '{"type":"VALIDATION_REPORT","status":"PASS|FAIL"}',
        "**Type**: CLI (command-line interface)",
        "- Type: `<type>` (required)",
        "type: skill",
        'type = "file"',
    ):
        assert _rule_ids(_gate_menu(extra=benign)) == [], benign

    for miscased in ("Type: blocking", "type: blocking", "tYpE: confirmation"):
        assert _rule_ids(_gate_menu(extra=miscased)) == ["PDSL703"], miscased


def test_a_reported_header_name_is_bounded() -> None:
    """PDSL703 interpolates the header name, so it must be elided like the others.

    The trailing run keeps the name a near-miss after end-trimming, so this
    reaches the message rather than being rejected first.
    """
    findings = validate_source(PdslSource(
        "ln.md", _gate_menu(extra="TYPE" + "_" * 200_000 + ": blocking"))).findings
    assert [f.rule_id for f in findings] == ["PDSL703"]
    assert len(findings[0].message) < 200


def test_alternate_alphabets_are_folded_to_ascii() -> None:
    """Fullwidth, mathematical and superscript letters render as `TYPE`.

    Folding is per character and only accepts a one-to-one result, so a
    character that expands (`\u203c` -> `!!`) stays decoration and the reported
    name keeps the author's offsets.
    """
    math_bold = "".join(chr(0x1D400 + ord(char) - ord("A")) for char in "TYPE")
    for variant in ("\uff34\uff39\uff30\uff25", math_bold, "\u1d40YPE"):
        assert _rule_ids(_gate_menu(extra=f"{variant}: blocking")) == ["PDSL703"], repr(variant)

    # An expanding character must not shift the reported name.
    findings = validate_source(PdslSource(
        "ex.md", _gate_menu(extra="\u203cTTYPE: blocking"))).findings
    assert [f.rule_id for f in findings] == ["PDSL703"]
    assert "TTYPE" in findings[0].message, findings[0].message


def test_an_all_caps_prose_line_without_a_separator_is_not_a_declaration() -> None:
    """The no-separator rule needs a probe the case rule cannot also suppress."""
    assert _rule_ids(_gate_menu(extra="TYPES OF PLAN WE SUPPORT")) == []
    assert _rule_ids(_gate_menu(extra="TYPE OF PLAN IS UNCLEAR")) == []
    # ...while a colon-less line whose value *is* a gate type is reported.
    assert _rule_ids(_gate_menu(extra="TYPE blocking")) == ["PDSL703"]


def test_a_miscased_header_with_no_value_is_reported() -> None:
    """A bare `Type:` declares nothing and is not prose either."""
    for variant in ("Type:", "type:", "Types:"):
        assert _rule_ids(_gate_menu(extra=variant)) == ["PDSL703"], variant


def test_pdsl_validate_cli_reports_gate_findings_end_to_end() -> None:
    """Gate rules must survive the real command, not just the in-process helper.

    Every other gate test calls `validate_source` directly, so a regression in
    argument handling, exit status or result formatting would leave them green.
    """
    set_json_mode(False)
    rc, stdout, stderr = _run(
        ["pdsl", "validate", "--text", _gate_menu(declared="urgent"), "--json"])

    assert rc != 0
    assert stderr == ""
    payload = json.loads(stdout)
    assert payload["command"] == "pdsl validate"
    assert payload["ok"] is False
    assert payload["summary"]["fail_count"] == 1
    assert payload["summary"]["finding_count"] == 1
    finding = payload["results"][0]["findings"][0]
    assert finding["rule_id"] == "PDSL700"
    assert finding["severity"] == "error"
    assert "confirmation, decision, blocking" in finding["message"]


def test_pdsl_validate_cli_passes_a_valid_and_an_undeclared_gate() -> None:
    """A declared gate and an omitted one both exit zero through the CLI."""
    for text in (_gate_menu(declared="blocking"), _gate_menu()):
        set_json_mode(False)
        rc, stdout, stderr = _run(["pdsl", "validate", "--text", text, "--json"])

        assert rc == 0, stderr
        payload = json.loads(stdout)
        assert payload["ok"] is True
        assert payload["summary"]["finding_count"] == 0


def test_pdsl_validate_cli_reports_a_malformed_gate_header_in_human_output() -> None:
    """The human-readable path must name the rule too, not only `--json`."""
    set_json_mode(False)
    rc, stdout, _ = _run(["pdsl", "validate", "--text", _gate_menu(extra="TYP: blocking")])

    assert rc != 0
    assert "PDSL703" in stdout


def test_a_sub_header_continuation_is_not_a_declaration_or_a_near_miss() -> None:
    """A title running onto a second line is that title's text, not a header.

    Both directions matter and both were wrong. A continuation resembling the
    keyword was reported as a misspelled declaration, and — worse, and
    unreported — one beginning `TYPE:` was *accepted* as the menu's declaration,
    so prose inside a title could become the gate's declared risk.
    """
    near_miss_continuation = (
        "MENU G:\n  TITLE: Heading\n    TYP: blocking\n  OPTIONS:\n    1 a -> RUN X\n"
    )
    assert _rule_ids(near_miss_continuation) == []

    declaration_continuation = (
        "MENU G:\n  TITLE: Heading\n    TYPE: blocking\n  OPTIONS:\n    1 a -> RUN X\n"
    )
    assert _rule_ids(declaration_continuation) == []

    deeply_indented = (
        "MENU G:\n  TITLE: t\n              TYPE: blocking\n  OPTIONS:\n    1 a -> RUN X\n"
    )
    assert _rule_ids(deeply_indented) == []


def test_the_sub_header_level_is_learned_not_assumed() -> None:
    """The level comes from the first sub-header, whichever one that is.

    An earlier attempt compared against a remembered indent seeded from the
    declaration itself, so the check never applied when `TYPE` came first —
    the canonical ordering. Learning the level removes the value to bootstrap.
    """
    for text, expected in (
        # `TYPE` first sets the level; a later sub-header at that level is fine.
        ("MENU G:\n  TYPE: blocking\n  TITLE: t\n  OPTIONS:\n    1 a -> RUN X\n", []),
        ("MENU G:\n  TYPE: urgent\n  TITLE: t\n  OPTIONS:\n    1 a -> RUN X\n", ["PDSL700"]),
        # Column-zero menus keep working in both directions.
        ("MENU G:\nTITLE: t\nTYPE: blocking\nOPTIONS:\n  1 a -> RUN X\n", []),
        ("MENU G:\nTITLE: t\nTYP: blocking\nOPTIONS:\n  1 a -> RUN X\n", ["PDSL703"]),
    ):
        assert _rule_ids(text) == expected, text


def test_the_sub_header_level_is_measured_per_menu_not_per_block() -> None:
    """A later menu may indent differently; a stale level suppresses its checks.

    This is the failure the continuation rule was written to avoid, arriving by
    another route: with the level held per block, a second menu indented deeper
    than the first had its whole body read as continuation text — losing its own
    declaration *and* the pre-existing option-numbering findings.
    """
    shallow_then_deep = (
        "MENU First:\nTITLE: t\nOPTIONS:\n  1 a -> RUN X\n\n"
        "MENU Second:\n  TITLE: t\n  TYPE: urgent\n  OPTIONS:\n    2 a -> RUN X\n    5 b -> RUN Y\n"
    )
    deep_then_shallow = (
        "MENU First:\n    TITLE: t\n    OPTIONS:\n      1 a -> RUN X\n\n"
        "MENU Second:\nTITLE: t\nTYPE: urgent\nOPTIONS:\n2 a -> RUN X\n5 b -> RUN Y\n"
    )
    for text in (shallow_then_deep, deep_then_shallow):
        rules = _rule_ids(text)
        assert "PDSL700" in rules, text
        assert rules.count("PDSL400") == 2, f"pre-existing numbering checks lost: {rules}"


def test_a_continuation_is_ignored_rather_than_accepted_as_a_declaration() -> None:
    """Asserting "no findings" cannot tell *ignored* from *silently accepted*.

    A duplicate probe can: `PDSL701` fires only if the first deep `TYPE` was
    latched as this menu's declaration. Without this, a rule that exempted
    recognized `TYPE` headers from the continuation check — so prose in a title
    became the gate's declared risk again — passed the whole suite.
    """
    deep_duplicate = (
        "MENU G:\n  TITLE: Heading\n    TYPE: blocking\n    TYPE: decision\n"
        "  OPTIONS:\n    1 a -> RUN X\n"
    )
    assert _rule_ids(deep_duplicate) == []


def test_an_indented_sub_header_still_opens_its_section() -> None:
    """A recognized sub-header is a header wherever it sits.

    Treating a deeper `OPTIONS:` as continuation text left its whole body
    unvalidated, losing the pre-existing option-numbering checks — the same
    suppression this rule was written to avoid, by another route.
    """
    options_deeper_than_title = (
        "MENU G:\n  TITLE: t\n    OPTIONS:\n      1 a -> RUN X\n      3 b -> RUN Y\n"
    )
    assert _rule_ids(options_deeper_than_title) == ["PDSL400"]


def test_a_deeper_non_exempt_header_is_continuation_so_a_later_type_is_read() -> None:
    """The other half of the indentation rule: only three headers are exempt.

    `TITLE:`, `OPTIONS:` and `INVALID:` keep section status at any indentation,
    so a deeper `OPTIONS:` still ends the declaration region (covered above).
    Every other recognized header is subject to the continuation rule instead,
    so a deeper `NOTES:` is continuation text, the region has *not* ended, and a
    `TYPE:` after it *is* the declaration.

    Only the exempt half was pinned. The three fixtures below separate the two
    conditions that a first draft of this test ran together: whether the deeper
    header ended the region, and whether the `TYPE:` was itself at the level.
    A valid `TYPE:` cannot tell those apart, because an omitted declaration is
    legal and yields no finding either way -- so each fixture uses an invalid
    value, which is reported only when the declaration is actually read.
    """
    # An *invalid* value, because a valid one is indistinguishable: an omitted
    # declaration is legal, so `TYPE: blocking` yields no finding whether it was
    # read or ignored as continuation text. `urgent` is reported only if read.
    deeper_notes_then_type_at_level = (
        "MENU G:\n  TITLE: t\n    NOTES: prose\n  TYPE: urgent\n  OPTIONS:\n    1 a -> RUN X\n"
    )
    assert _rule_ids(deeper_notes_then_type_at_level) == ["PDSL700"]

    # The `TYPE:` must sit at the level to be read. Indented deeper it is
    # continuation text by the same rule, so its invalid value is never reached.
    deeper_notes_then_deeper_type = (
        "MENU G:\n  TITLE: t\n    NOTES: prose\n    TYPE: urgent\n  OPTIONS:\n    1 a -> RUN X\n"
    )
    assert _rule_ids(deeper_notes_then_deeper_type) == []

    # At the learned level, `NOTES:` ends the region, so a later `TYPE:` is inert
    # and reported as a declaration nothing reads.
    notes_at_level_then_type = (
        "MENU G:\n  TITLE: t\n  NOTES: prose\n  TYPE: urgent\n  OPTIONS:\n    1 a -> RUN X\n"
    )
    assert _rule_ids(notes_at_level_then_type) == ["PDSL702"]


def test_the_indentation_rule_is_reported_through_the_real_cli() -> None:
    """The same three fixtures, driven end-to-end rather than through the validator.

    Every other test for this rule calls `_rule_ids`, which reaches
    `validate_source` in-process and so never exercises argument parsing, the
    exit-code mapping or the JSON rendering. A review of #153 raised that gap on
    this module and it was extended rather than closed, so one fixture per
    outcome now goes through `main()`: a read declaration, an ignored one, and a
    declaration nothing reads.

    Exit codes are asserted because they are the part `_rule_ids` cannot see: a
    finding must map to 2, not 1, and a clean source to 0.
    """
    for text, expected_ids, expected_rc in (
            ("MENU G:\n  TITLE: t\n    NOTES: prose\n  TYPE: urgent\n"
             "  OPTIONS:\n    1 a -> RUN X\n", ["PDSL700"], 2),
            ("MENU G:\n  TITLE: t\n    NOTES: prose\n    TYPE: urgent\n"
             "  OPTIONS:\n    1 a -> RUN X\n", [], 0),
            ("MENU G:\n  TITLE: t\n  NOTES: prose\n  TYPE: urgent\n"
             "  OPTIONS:\n    1 a -> RUN X\n", ["PDSL702"], 2),
    ):
        set_json_mode(False)
        rc, stdout, stderr = _run(["pdsl", "validate", "--text", text, "--json"])

        assert rc == expected_rc, (text, stdout, stderr)
        assert stderr == ""
        payload = json.loads(stdout)
        assert payload["command"] == "pdsl validate"
        assert payload["ok"] is not bool(expected_ids)
        assert payload["summary"]["finding_count"] == len(expected_ids)
        found = [f["rule_id"] for f in payload["results"][0]["findings"]]
        assert found == expected_ids, (text, found)


def test_an_unrecognized_first_sub_header_sets_the_level() -> None:
    """`NOTE:` and `ELSE:` are legitimate menu headers, so they set it too.

    With the level captured only for recognized headers, a menu opening with
    prose left it unset — so a deeper `TYPE:` was read as the declaration and a
    deeper near-miss was falsely reported.
    """
    for text in (
        "MENU G:\n  NOTE: n\n    TYP: blocking\n  OPTIONS:\n    1 a -> RUN X\n",
        "MENU G:\n  ELSE: e\n    TYPE: nonsense\n  OPTIONS:\n    1 a -> RUN X\n",
    ):
        assert _rule_ids(text) == [], text


def test_a_malformed_gate_header_needs_no_recognized_header_shape() -> None:
    """The prose path must be reachable: `TYPE = blocking` is not `^[A-Z]+:`.

    Every other near-miss test uses `TYP:`, which reaches the rule through the
    recognized-header path, so the guard on the prose path was unpinned.
    """
    assert _rule_ids("MENU G:\n  TITLE: t\n    TYPE = blocking\n  OPTIONS:\n    1 a -> RUN X\n") == []
    assert _rule_ids("MENU G:\n  TITLE: t\n  TYPE = blocking\n  OPTIONS:\n    1 a -> RUN X\n") == ["PDSL703"]


def test_an_unmapped_lookalike_inside_the_name_is_still_recognized() -> None:
    """The confusable map was an enumeration, so anything absent from it escaped.

    A lookalike or an NFKC-expanding character *inside* the word truncated the
    name capture to `T`, which is too far from `TYPE` to report — so the line
    fell through as prose. Expanding characters are now dropped rather than
    kept, the capture spans Unicode letters, and the near-miss test discards
    whatever is still non-ASCII. No map to keep current.
    """
    for variant in (
        "TҮPE: blocking",   # Cyrillic capital straight U, absent from the map
        "T‼YPE: blocking",  # double exclamation, expands under NFKC
        "TYԀE: blocking",   # Komi De, also absent
    ):
        assert _rule_ids(_gate_menu(extra=variant)) == ["PDSL703"], repr(variant)


def test_an_abandoned_declaration_is_reported_whatever_its_casing() -> None:
    """A separator with nothing after it is an attempt, not front matter.

    The miscasing guard suppresses a lower-case candidate whose value is some
    other token, which is what keeps `type: skill` prose. An *empty* value is
    the one case where that suppression must not apply: the author wrote the
    header and the separator and stopped, which is an abandoned declaration in
    any casing. Pinned because the spec asserts it and the guard's truthiness
    test is what implements it.
    """
    for variant in ("type:", "Type:", "TYPE:"):
        assert _rule_ids(_gate_menu(extra=variant)) != [], variant
    # ...while a value that is merely some other token stays prose.
    for benign in ("type: skill", "Type: CLI", "type: workflow"):
        assert _rule_ids(_gate_menu(extra=benign)) == [], benign


def test_a_reported_name_survives_non_length_preserving_folding() -> None:
    """The reported name must come through a source map, not a folded offset.

    U+203C is dropped by folding, so an offset into the folded string is not an
    offset into the original: reusing one truncates the name. An earlier version
    of this test used a character NFKC leaves unchanged, so it passed on the very
    mechanism it was written to replace.
    """
    findings = validate_source(PdslSource(
        "sp.md", _gate_menu(extra="T\u203cYPE: blocking"))).findings
    assert [f.rule_id for f in findings] == ["PDSL703"]
    assert "T\u203cYPE" in findings[0].message, findings[0].message


def test_the_name_capture_spans_a_non_ascii_letter() -> None:
    """Widening the capture past ASCII is what stops a lookalike truncating it.

    With an ASCII-only capture, `T\u00c9PE` yields the stub `T`, too far from
    `TYPE` to report; spanning the letter keeps it at distance 1. Probing with
    unrelated non-ASCII prose instead would pass whatever the capture does,
    since the distance guard rejects such prose either way.
    """
    assert _rule_ids(_gate_menu(extra="T\u00c9PE: blocking")) == ["PDSL703"]

    # Non-ASCII that is not standing in for a letter of the keyword stays prose,
    # and arbitrarily many do not collapse into a near-miss.
    for benign in ("Caf\u00e9: something", "\u4f60\u597d: hello", "TYPE\u04ae\u04ae: blocking"):
        assert _rule_ids(_gate_menu(extra=benign)) == [], repr(benign)
