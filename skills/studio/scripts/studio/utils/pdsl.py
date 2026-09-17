"""PDSL block extraction and deterministic validation helpers."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-validate-source-of-truth
@dataclass(frozen=True)
class PdslBlock:
    """Extracted fenced PDSL block with source coordinates."""

    source: str
    block_index: int
    text: str
    line: int
    column: int
    end_line: int
    end_column: int


@dataclass(frozen=True)
class PdslFinding:
    """Deterministic validation finding for a PDSL block."""

    rule_id: str
    severity: str
    message: str
    source_path: str
    block_index: int
    line: int
    column: int
    end_line: int
    end_column: int
    hint: Optional[str] = None
    context: Optional[str] = None

    def to_dict(self, *, verbose: bool = False) -> Dict[str, object]:
        """Return a serializable dictionary representation."""
        out: Dict[str, object] = {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "source_path": self.source_path,
            "block_index": self.block_index,
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
        }
        if self.hint:
            out["hint"] = self.hint
        if verbose and self.context:
            out["context"] = self.context
        return out


@dataclass(frozen=True)
class PdslError:
    """PDSL extraction or parsing error."""

    message: str
    source_path: str
    line: Optional[int] = None
    column: Optional[int] = None
    kind: str = "ERROR"

    def to_dict(self) -> Dict[str, object]:
        """Return a serializable dictionary representation."""
        out: Dict[str, object] = {
            "message": self.message,
            "source_path": self.source_path,
            "kind": self.kind,
        }
        if self.line is not None:
            out["line"] = self.line
        if self.column is not None:
            out["column"] = self.column
        return out


@dataclass(frozen=True)
class PdslSourceResult:
    """Validation result for one PDSL source."""

    source: str
    status: str
    findings: Tuple[PdslFinding, ...]
    errors: Tuple[PdslError, ...]

    def to_dict(self, *, verbose: bool = False) -> Dict[str, object]:
        """Return a serializable dictionary representation."""
        return {
            "source": self.source,
            "status": self.status,
            "findings": [finding.to_dict(verbose=verbose) for finding in self.findings],
            "errors": [error.to_dict() for error in self.errors],
        }


@dataclass(frozen=True)
class PdslSource:
    """Named PDSL text source."""

    source: str
    text: str


@dataclass
class _BlockValidationState:
    """Mutable validation state while scanning a PDSL block."""

    section: Optional[str] = None
    menu_expected: Optional[int] = None
    in_menu: bool = False
    do_count: int = 0
    rules_count: int = 0
    menu_name: Optional[str] = None
    menu_type_line: int = 0
    menu_shape_line: int = 0
    gate_scope: bool = False
    sub_header_indent: Optional[int] = None


FENCE_RE = re.compile(r"^```(?P<lang>[A-Za-z0-9_-]+)?\s*$")
UNIT_OR_MENU_RE = re.compile(r"^(UNIT|MENU)\s+(?P<name>[A-Za-z][A-Za-z0-9_-]*)\b")
PATTERN_DEF_RE = re.compile(r"^\s{2}(?P<name>[A-Za-z][A-Za-z0-9_-]*)\s*:\s*/")
MATCHES_RE = re.compile(r"\bmatches\(\s*[^,]+,\s*(?P<quote>['\"]?)(?P<name>[A-Za-z][A-Za-z0-9_-]*)\1\s*\)")
SECTION_HEAD_RE = re.compile(r"^(?P<section>[A-Z][A-Z0-9_-]*):")
ACTION_HEAD_RE = re.compile(r"^(?:-\s+)?(?P<token>[A-Z][A-Z0-9_-]*)(?=\b|\s|$)")
MENU_OPTION_RE = re.compile(r"^(?:-\s+)?(?P<number>\d+)\b.*->")

# A declared gate type is one of these bare tokens and nothing else: an
# interpolation, a variable or a trailing WHEN is a runtime decision in
# disguise and fails membership here.
GATE_TYPES = ("confirmation", "decision", "blocking")
GATE_HEADER = "TYPE"
# A declared menu shape is one of these bare tokens and nothing else (issue
# #186): `fixed-choice` is a closed set of numbered OPTIONS a native dialog can
# render faithfully; `free-form` is anything whose real reply is an open-ended
# list, a multi-select, or a value embedded in prose rather than a single pick
# among the listed entries -- never native-dialog-routed regardless of option
# count. Mirrors GATE_TYPES/GATE_HEADER exactly (added in #153), including how
# an absent declaration is handled: see MENU_SHAPE_HEADER's own docstring.
MENU_SHAPE_TYPES = ("fixed-choice", "free-form")
MENU_SHAPE_HEADER = "SHAPE"
# The headers that keep a MENU's declaration region open rather than ending it
# (`_handle_section_header_line`'s `gate_scope` check). Exported as one tuple,
# not re-derived, so a test-side guard that needs to walk the same region
# (e.g. `_menu_declaration_scan` in tests/test_pdsl_keywords.py) cannot drift
# out of sync with the validator's own list the way an earlier, TITLE-only
# copy of this check did before `SHAPE` existed.
DECLARED_HEADER_NON_TERMINATORS = ("TITLE", GATE_HEADER, MENU_SHAPE_HEADER)
# Sub-headers permitted at an indent inside a MENU. `TYPE`/`SHAPE` are absent on
# purpose: both are dispatched before the indent guard, so listing them here
# would be dead.
MENU_SUB_HEADERS = frozenset({"TITLE", "OPTIONS", "INVALID"})
# Keywords considered for this declaration and rejected. Someone reaching for
# one has written an inert header, so it is reported rather than ignored.
GATE_HEADER_ALIASES = frozenset({
    "RISK", "RISK_TYPE", "GATE_RISK", "GATE_TYPE", "MENU_TYPE", "RISK_LEVEL",
})
MENU_SHAPE_HEADER_ALIASES = frozenset({
    "ARITY", "MENU_SHAPE", "REPLY_SHAPE", "SELECTION_SHAPE", "ANSWER_SHAPE",
})
# MENU blocks legitimately carry prose and control-flow headers (NOTE:, ELSE:),
# so an unrecognized one is reported only when it is a near-miss of a
# declaration keyword. Distance 1 keeps ordinary words (TIME:, TIPS:, NOTE:,
# SHARE:) out while still catching TYP:/TYPO:/TYPES: and SHAPE:'s own
# near-misses (SHAP:, SHAPES:).
GATE_HEADER_TYPO_DISTANCE = 1
MENU_SHAPE_HEADER_TYPO_DISTANCE = 1
# A declaration is recognized by discarding decoration rather than by listing
# the forms it can take: enumerating them is unbounded, and three review passes
# each found more (backticks, brackets, quotes, an arrow, a zero-width space).
# Only non-alphanumerics may precede the name, and only a separator or a literal
# gate type may follow it -- so `Tape recorder notes` stays prose.
GATE_DECORATION_RE = re.compile(r"^[^A-Za-z0-9]*")
GATE_NAME_RE = re.compile(r"[^\W\d][\w-]*")
GATE_SEPARATOR_RE = re.compile(r"^[^A-Za-z0-9]*(?:->|=>|[:=])")
# Invisible characters are removed by Unicode category rather than by listing
# them: `Cf` covers zero-width spaces, joiners and bidi controls, `Mn` covers
# combining marks, and `Cc` covers stray control characters.
GATE_INVISIBLE_CATEGORIES = frozenset({"Cc", "Cf", "Mn"})
# Cyrillic and Greek capitals that render like Latin ones, so `TYPE` typed with
# any of them is still read as an attempt at a declaration. NFKC folding handles
# the fullwidth and mathematical alphabets before this map is applied.
GATE_NAME_CONFUSABLES = {
    "\u0410": "A", "\u0415": "E", "\u041a": "K", "\u041c": "M", "\u041e": "O",
    "\u0420": "P", "\u0421": "C", "\u0422": "T", "\u0423": "Y", "\u0425": "X",
    "\u0391": "A", "\u0392": "B", "\u0395": "E", "\u0396": "Z", "\u0397": "H",
    "\u0399": "I", "\u039a": "K", "\u039c": "M", "\u039d": "N", "\u039f": "O",
    "\u03a1": "P", "\u03a4": "T", "\u03a5": "Y", "\u03a7": "X",
}
GATE_VALUE_ELLIPSIS = 60

# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-load-rule-registry
SECTION_HEADERS = {
    "PURPOSE",
    "INPUT",
    "OUTPUT",
    "STATE",
    "WHEN",
    "DO",
    "RULES",
    "ON_ERROR",
    "INVARIANTS",
    "NOTES",
    "PATTERNS",
    "TITLE",
    "TYPE",
    "SHAPE",
    "OPTIONS",
    "INVALID",
}
STATE_KEYWORDS = {"SET"}
WHEN_KEYWORDS = {"REQUIRE", "AND", "OR", "NOT"}
DO_KEYWORDS = {
    "SET",
    "LOAD",
    "RUN",
    "EMIT",
    "EMIT_MENU",
    "WAIT",
    "STOP_TURN",
    "CONTINUE",
    "DISPATCH",
    "RETURN",
    "REQUIRE",
    "NEVER",
}
RULE_KEYWORDS = {"ALWAYS", "NEVER"}
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-load-rule-registry

# PDSL.md Authoring Rules #6/#7: max 7 top-level DO actions per UNIT, max 5 RULES per block.
DO_ACTION_CAP = 7
RULES_CAP = 5


def read_source_file(path: Path) -> Tuple[Optional[str], Optional[PdslError]]:
    """Read a PDSL input file as text, reporting normalized operational errors."""
    try:
        return path.read_text(encoding="utf-8"), None
    except OSError as exc:
        return None, PdslError(
            message=f"Cannot read source: {exc}",
            source_path=str(path),
            kind="READ_ERROR",
        )
    except UnicodeDecodeError as exc:
        return None, PdslError(
            message=f"Cannot decode source as UTF-8: {exc}",
            source_path=str(path),
            kind="DECODE_ERROR",
        )


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-scan-input
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-scan-reuse
def scan_blocks(source: str, text: str) -> Tuple[List[PdslBlock], List[PdslFinding]]:
    """Extract PDSL fences in source order, or use the whole text as one block."""
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-scan-input
    lines = text.splitlines()
    blocks: List[PdslBlock] = []
    findings: List[PdslFinding] = []
    in_pdsl = False
    in_other_fence = False
    start_line = 1
    current: List[str] = []

# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-scan-blocks
    for idx, line in enumerate(lines, start=1):
        fence = FENCE_RE.match(line.strip())
        if not fence:
            if in_pdsl:
                current.append(line)
            continue
        lang = (fence.group("lang") or "").lower()
        if in_pdsl:
            block_text = "\n".join(current)
            blocks.append(PdslBlock(
                source=source,
                block_index=len(blocks),
                text=block_text,
                line=start_line,
                column=1,
                end_line=max(start_line, idx - 1),
                end_column=len(current[-1]) + 1 if current else 1,
            ))
            in_pdsl = False
            current = []
            continue
        if in_other_fence:
            in_other_fence = False
            continue
        if lang == "pdsl":
            in_pdsl = True
            start_line = idx + 1
            current = []
        else:
            in_other_fence = True
            if _looks_like_pdsl_after_fence(lines[idx:]):
                findings.append(PdslFinding(
                    rule_id="PDSL100",
                    severity="error",
                    message="PDSL-shaped instruction block must use a ```pdsl fence",
                    source_path=source,
                    block_index=len(blocks),
                    line=idx,
                    column=1,
                    end_line=idx,
                    end_column=len(line) + 1,
                    hint="Change the fence language to pdsl.",
                    context=line,
                ))

    if in_pdsl:
        findings.append(PdslFinding(
            rule_id="PDSL100",
            severity="error",
            message="Unclosed ```pdsl fence",
            source_path=source,
            block_index=len(blocks),
            line=start_line - 1,
            column=1,
            end_line=len(lines) or 1,
            end_column=(len(lines[-1]) + 1) if lines else 1,
            hint="Add a closing ``` fence.",
        ))

# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-scan-blocks

    if not blocks and not findings:
        # @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-if-no-delimiters
        # @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-use-whole-source
        block_text = text
        # @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-use-whole-source
        # @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-assign-block-index
        block_index = 0
        # @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-assign-block-index
        blocks.append(PdslBlock(
            source=source,
            block_index=block_index,
            text=block_text,
            line=1,
            column=1,
            end_line=max(1, len(lines)),
            end_column=(len(lines[-1]) + 1) if lines else 1,
        ))
        # @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-if-no-delimiters
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-scan-return
    return blocks, findings
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-scan-return
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-scan-reuse


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-foreach-block
def validate_source(source: PdslSource, *, verbose: bool = False) -> PdslSourceResult:
    """Validate one PDSL source and return normalized status/findings/errors."""
    del verbose  # Reserved for compatibility with callers; rendering applies verbosity.
    blocks, scan_findings = scan_blocks(source.source, source.text)
    findings: List[PdslFinding] = list(scan_findings)
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-parse-block
    for block in blocks:
        findings.extend(_validate_block(block))
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-parse-block
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-foreach-block
    errors: Tuple[PdslError, ...] = ()
    # @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-sort-findings
    findings.sort(key=lambda f: (f.source_path, f.block_index, f.line, f.column, f.rule_id, f.message))
    status = "FAIL" if findings else "PASS"
    # @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-sort-findings
    # @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-if-source-error
    # @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-if-findings
    if findings:
        fail_findings = tuple(findings)
        # @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-return-source-fail
        fail_result = PdslSourceResult(source.source, status, fail_findings, errors)
        return fail_result
        # @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-return-source-fail
    # @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-if-findings
    # @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-else-source-pass
    pass_findings = tuple(findings)
    # @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-return-source-pass
    pass_result = PdslSourceResult(source.source, status, pass_findings, errors)
    return pass_result
    # @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-return-source-pass
    # @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-else-source-pass
    # @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-if-source-error


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-return-source-error
def error_result(source: str, error: PdslError) -> PdslSourceResult:
    """Build a PDSL source result for a validation error."""
    return PdslSourceResult(source=source, status="ERROR", findings=(), errors=(error,))
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-return-source-error


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-summary:p1:inst-build-summary-object
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-summary:p1:inst-preserve-input-order
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-summary:p1:inst-count-statuses
def build_envelope(results: Sequence[PdslSourceResult], *, command: str, verbose: bool = False) -> Dict[str, object]:
    """Build envelope."""
    pass_count = sum(1 for r in results if r.status == "PASS")
    fail_count = sum(1 for r in results if r.status == "FAIL")
    error_count = sum(1 for r in results if r.status == "ERROR")
    finding_count = sum(len(r.findings) for r in results)
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-summary:p1:inst-count-statuses
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-summary:p1:inst-build-summary-object
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-summary:p1:inst-return-envelope
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-summary:p1:inst-apply-verbose
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-summary:p1:inst-summary-cf-pdsl-reuse
    return {
        "command": command,
        "ok": not error_count and not fail_count,
        "summary": {
            "pass_count": pass_count,
            "fail_count": fail_count,
            "error_count": error_count,
            "finding_count": finding_count,
        },
        "results": [r.to_dict(verbose=verbose) for r in results],
    }
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-summary:p1:inst-summary-cf-pdsl-reuse
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-summary:p1:inst-apply-verbose
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-summary:p1:inst-return-envelope
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-summary:p1:inst-preserve-input-order


# @cpt-begin:cpt-studio-state-pdsl-validation-cli-result-status:p1:inst-state-error
def exit_code_for_results(results: Sequence[PdslSourceResult]) -> int:
    """Return the process exit code for PDSL validation results."""
    if any(r.status == "ERROR" for r in results):
        return 1
# @cpt-begin:cpt-studio-state-pdsl-validation-cli-result-status:p1:inst-state-fail
    if any(r.status == "FAIL" for r in results):
        return 2
# @cpt-end:cpt-studio-state-pdsl-validation-cli-result-status:p1:inst-state-fail
# @cpt-begin:cpt-studio-state-pdsl-validation-cli-result-status:p1:inst-state-pass
    return 0
# @cpt-end:cpt-studio-state-pdsl-validation-cli-result-status:p1:inst-state-pass
# @cpt-end:cpt-studio-state-pdsl-validation-cli-result-status:p1:inst-state-error


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-run-structural-checks
def _looks_like_pdsl_after_fence(lines: Sequence[str]) -> bool:
    for line in lines[:8]:
        stripped = line.strip()
        if stripped == "```":
            return False
        if UNIT_OR_MENU_RE.match(stripped) or stripped in {"PURPOSE:", "DO:", "RULES:", "WHEN:"}:
            return True
    return False


def _validate_block(block: PdslBlock) -> List[PdslFinding]:
    findings: List[PdslFinding] = []
    names: Dict[Tuple[str, str], int] = {}
    local_patterns: Dict[str, int] = {}
    state = _BlockValidationState()

    for offset, raw_line in enumerate(block.text.splitlines(), start=0):
        line_no = block.line + offset
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("//"):
            continue

        if _handle_unit_or_menu_line(
            block,
            line_no,
            raw_line,
            stripped,
            names,
            findings,
            state,
        ):
            continue

        if _handle_section_header_line(block, line_no, stripped, raw_line, findings, state):
            continue

        _report_malformed_gate_header(block, line_no, raw_line, stripped, findings, state)

        if _handle_pattern_line(
            block,
            line_no,
            raw_line,
            local_patterns,
            findings,
            state.section,
        ):
            continue

        findings.extend(_validate_section_item(block, state.section, state.menu_expected, line_no, raw_line))
        findings.extend(_check_section_cap(block, state, line_no, raw_line))
        _advance_menu_option_counter(stripped, state)

        _append_missing_match_pattern_findings(
            block,
            line_no,
            raw_line,
            local_patterns,
            findings,
        )
    return findings


def _handle_unit_or_menu_line(
    block: PdslBlock,
    line_no: int,
    raw_line: str,
    stripped: str,
    names: Dict[Tuple[str, str], int],
    findings: List[PdslFinding],
    state: _BlockValidationState,
) -> bool:
    """Process UNIT/MENU headers and update parser state."""
    unit_menu = UNIT_OR_MENU_RE.match(stripped)
    if not unit_menu:
        return False
    kind = unit_menu.group(1)
    name = unit_menu.group("name")
    key = (kind, name)
    if key in names:
        findings.append(_finding(
            block, "PDSL300", line_no, raw_line,
            f"Duplicate {kind} name `{name}` in source",
            hint=f"Rename this {kind} or remove the earlier duplicate at line {names[key]}.",
        ))
    else:
        names[key] = line_no
    state.section = None
    state.menu_expected = None
    state.in_menu = kind == "MENU"
    # @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-declaration-literal
    # These two resets are what make the one-declaration-per-menu rule per-menu,
    # and what lets its finding name the menu.
    state.menu_name = name
    state.menu_type_line = 0
    state.menu_shape_line = 0
    # Reset per MENU, not per block: a later menu may indent its sub-headers
    # differently, and a stale level would read that menu's whole body as
    # continuation text -- suppressing its declaration *and* the pre-existing
    # option-numbering checks.
    state.sub_header_indent = None
    # @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-declaration-literal
    # @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-declaration-region
    state.gate_scope = state.in_menu
    # @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-declaration-region
    state.do_count = 0
    state.rules_count = 0
    return True


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-declaration-region
def _is_header_continuation(indent_len: int, state: _BlockValidationState) -> bool:
    """True when a line is continuation text of the sub-header above it.

    A MENU's sub-headers share one indent; a line deeper than that is the
    previous header's own text. Without this, a title running onto a second
    line was read as a header in its own right -- reported as a misspelled
    declaration if it resembled one, and worse, *accepted* as the menu's
    declaration if it began with `TYPE:`.

    The level is learned from the first sub-header rather than compared against
    a remembered one, so there is no value to bootstrap and no ordering in which
    the check fails to apply.
    """
    return (
        state.in_menu
        # Only inside the declaration region. Past it a deeper line is an
        # action body, where a `TYPE:` is a misplaced declaration worth
        # reporting rather than prose to be ignored.
        and state.gate_scope
        and state.sub_header_indent is not None
        and indent_len > state.sub_header_indent
    )
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-declaration-region


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-header-near-miss
def _report_unrecognized_sub_header(
    block: PdslBlock,
    line_no: int,
    raw_line: str,
    section_name: str,
    findings: List[PdslFinding],
    state: _BlockValidationState,
) -> None:
    """Report an unrecognized header that is a near-miss of a declaration keyword."""
    # `gate_scope` is only ever assigned from `in_menu`, so it implies it.
    if not state.gate_scope:
        return
    if _is_gate_header_typo(section_name):
        findings.append(_gate_header_finding(block, line_no, raw_line, section_name))
    elif _is_menu_shape_header_typo(section_name):
        findings.append(_menu_shape_header_finding(block, line_no, raw_line, section_name))
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-header-near-miss


def _handle_section_header_line(  # pylint: disable=too-many-return-statements
    block: PdslBlock,
    line_no: int,
    stripped: str,
    raw_line: str,
    findings: List[PdslFinding],
    state: _BlockValidationState,
) -> bool:
    """Process section headers, and track where a gate/shape declaration is read.

    `in_menu` is deliberately left alone. A MENU's *declaration region* is
    tracked separately in `gate_scope`: it runs from the MENU header to the
    first section that is not `TITLE`, `TYPE`, or `SHAPE` (issue #186). Nothing
    outside that region is read as a declaration, so there is no need to decide
    where a MENU "ends" -- an earlier attempt to do that suppressed the
    pre-existing menu numbering checks for the rest of the block.
    """
    section_head = SECTION_HEAD_RE.match(stripped)
    if not section_head:
        return False
    section_name = section_head.group("section")
    indent_len = len(raw_line) - len(raw_line.lstrip(" "))
    # @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-declaration-region
    if state.in_menu and state.sub_header_indent is None:
        state.sub_header_indent = indent_len
    # A recognized sub-header is a header wherever it sits: exempting it keeps
    # an indented `OPTIONS:` opening its section, so the pre-existing option
    # checks still run. Only non-sub-header lines can be continuation text.
    if section_name not in MENU_SUB_HEADERS and _is_header_continuation(indent_len, state):
        return True
    # @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-declaration-region
    if section_name not in SECTION_HEADERS:
        _report_unrecognized_sub_header(block, line_no, raw_line, section_name, findings, state)
        return True
    # @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-declaration-region
    if section_name not in DECLARED_HEADER_NON_TERMINATORS:
        state.gate_scope = False
    # @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-declaration-region
    # @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-declaration-literal
    if section_name == GATE_HEADER:
        _handle_gate_type_header(block, line_no, raw_line, stripped, findings, state)
        return True
    if section_name == MENU_SHAPE_HEADER:
        _handle_menu_shape_header(block, line_no, raw_line, stripped, findings, state)
        return True
    # @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-declaration-literal
    if indent_len > 0 and not (state.in_menu and section_name in MENU_SUB_HEADERS):
        return True
    state.section = section_name
    state.menu_expected = 1 if state.in_menu and section_name == "OPTIONS" else None
    return True


# The only `_BlockValidationState` fields `_handle_declared_menu_header` may
# target via `state_line_attr`. See that function's own comment on why this
# exists.
_DECLARED_MENU_HEADER_STATE_LINE_ATTRS = frozenset({"menu_type_line", "menu_shape_line"})


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-declaration-literal
def _handle_declared_menu_header(  # pylint: disable=too-many-arguments,too-many-locals
    block: PdslBlock,
    line_no: int,
    raw_line: str,
    stripped: str,
    findings: List[PdslFinding],
    state: _BlockValidationState,
    *,
    header: str,
    valid_tokens: Tuple[str, ...],
    state_line_attr: str,
    outside_scope_noun: str,
    rule_outside_scope: str,
    rule_duplicate: str,
    rule_bad_value: str,
    bad_value_hint: str,
) -> None:
    """Validate one declaration of *header* and record that this MENU carries one.

    Shared by `_handle_gate_type_header` (`TYPE`) and `_handle_menu_shape_header`
    (`SHAPE`, issue #186): both validate a single-token MENU declaration
    against the same declaration-region/one-per-menu rules, differing only in
    the header keyword, its valid tokens, which `_BlockValidationState` field
    latches the first declaration's line, and each one's own rule IDs/wording.
    An absent declaration is always valid -- an undeclared MENU falls back to
    today's default behavior, so the existing surface migrates one
    declaration at a time. Only a declaration the block cannot support is
    reported here.
    """
    # A typo'd *state_line_attr* landing on an unrelated-but-real field (e.g.
    # "do_count") would otherwise have `getattr`/`setattr` silently succeed
    # and corrupt that field instead of raising -- this closed allow-list
    # turns that into an immediate, loud failure.
    assert state_line_attr in _DECLARED_MENU_HEADER_STATE_LINE_ATTRS, state_line_attr
    if not state.gate_scope:
        # Outside a MENU, or past its declaration region. `gate_scope` is only
        # ever set from `in_menu`, so it implies it.
        findings.append(_finding(
            block, rule_outside_scope, line_no, raw_line,
            f"`{header}:` declares {outside_scope_noun} where nothing reads it",
            hint=f"Put {header} directly under its MENU header, before OPTIONS.",
        ))
        return
    earlier_line = getattr(state, state_line_attr)
    if earlier_line:
        findings.append(_finding(
            block, rule_duplicate, line_no, raw_line,
            f"MENU `{_elide(state.menu_name or '')}` declares {header} more than once",
            hint=f"Keep one {header}; the earlier declaration is at line {earlier_line}.",
        ))
        return
    setattr(state, state_line_attr, line_no)
    value = stripped[len(header) + 1:].strip()
    if value not in valid_tokens:
        findings.append(_finding(
            block, rule_bad_value, line_no, raw_line,
            f"MENU {header} must be one literal token of {', '.join(valid_tokens)} "
            f"(found `{_elide(value)}`)",
            hint=bad_value_hint,
        ))


def _handle_gate_type_header(
    block: PdslBlock,
    line_no: int,
    raw_line: str,
    stripped: str,
    findings: List[PdslFinding],
    state: _BlockValidationState,
) -> None:
    """Validate one `TYPE:` declaration and record that this MENU carries one.

    An absent declaration is valid: an undeclared gate is treated as `blocking`
    at runtime, so the existing surface migrates gate by gate.
    """
    _handle_declared_menu_header(
        block, line_no, raw_line, stripped, findings, state,
        header=GATE_HEADER, valid_tokens=GATE_TYPES, state_line_attr="menu_type_line",
        outside_scope_noun="gate risk", rule_outside_scope="PDSL702",
        rule_duplicate="PDSL701", rule_bad_value="PDSL700",
        bad_value_hint="Declare risk statically; where it varies, emit two differently-typed gates.",
    )


def _handle_menu_shape_header(
    block: PdslBlock,
    line_no: int,
    raw_line: str,
    stripped: str,
    findings: List[PdslFinding],
    state: _BlockValidationState,
) -> None:
    """Validate one `SHAPE:` declaration and record that this MENU carries one (issue #186).

    An absent declaration is valid: an undeclared menu falls back to the
    existing prose-based shape-compatibility heuristic.
    """
    _handle_declared_menu_header(
        block, line_no, raw_line, stripped, findings, state,
        header=MENU_SHAPE_HEADER, valid_tokens=MENU_SHAPE_TYPES, state_line_attr="menu_shape_line",
        outside_scope_noun="menu shape", rule_outside_scope="PDSL712",
        rule_duplicate="PDSL711", rule_bad_value="PDSL710",
        bad_value_hint="Declare shape statically; a free-form/multi-select reply is never native-dialog-routed.",
    )
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-declaration-literal


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-header-near-miss
def _report_malformed_gate_header(
    block: PdslBlock,
    line_no: int,
    raw_line: str,
    stripped: str,
    findings: List[PdslFinding],
    state: _BlockValidationState,
) -> None:
    """Report a declaration written in a form PDSL does not accept.

    Decoration is discarded rather than enumerated: only non-alphanumerics may
    precede the name, and a trailing run of them is skipped before looking for
    the separator. So a bullet, backticks, brackets, quotes, an arrow or a
    zero-width space all reduce to the same candidate, and no list of forms has
    to be kept current.

    Tries the gate (`TYPE`) reading first and the shape (`SHAPE`, issue #186)
    reading second -- the two keywords differ enough (4 vs 5 letters) that a
    distance-1 near-miss of one is never also a near-miss of the other, so at
    most one of these ever fires per line.

    Adds a finding only. The line is still offered to the other checks, so a
    malformed declaration does not mask an unrelated finding on the same line.
    """
    # Reached only when `_handle_section_header_line` returned False, so this
    # line is not a recognized header and needs no second check for one.
    if not state.gate_scope:
        return
    if _is_header_continuation(len(raw_line) - len(raw_line.lstrip(" ")), state):
        return
    candidate = _gate_header_candidate(stripped)
    if candidate is None:
        return
    name, has_separator, value = candidate
    if _is_gate_header_typo(name) and _looks_like_declaration_attempt(name, has_separator, value, GATE_TYPES):
        findings.append(_gate_header_finding(block, line_no, raw_line, name))
        return
    if _is_menu_shape_header_typo(name) and _looks_like_declaration_attempt(
        name, has_separator, value, MENU_SHAPE_TYPES
    ):
        findings.append(_menu_shape_header_finding(block, line_no, raw_line, name))


def _looks_like_declaration_attempt(
    name: str, has_separator: bool, value: str, valid_tokens: Tuple[str, ...],
) -> bool:
    """True when a near-miss header candidate is plausibly a declaration attempt.

    PDSL headers are upper-case. A lower- or mixed-case candidate is usually
    prose or front matter (`type: skill`, `**Type**: CLI`), so it is reported
    only when its value is one of the target's own valid tokens -- which is
    the miscasing #152 names. Without a separator this is only a declaration
    attempt when the value's first word is a valid token -- so `TYPE |
    blocking` and `TYPE (blocking)` are reported while `Tape recorder notes`
    stays prose.
    """
    if not name.isupper() and value and value.lower() not in valid_tokens:
        return False
    if not has_separator:
        first_word = GATE_NAME_RE.search(value)
        if first_word is None or first_word.group().lower() not in valid_tokens:
            return False
    return True


def _gate_header_candidate(stripped: str) -> Optional[Tuple[str, bool, str]]:
    """Return `(name, has_separator, value)` for a line that may be a declaration.

    Invisible characters are removed and the rest folded per character before
    the name is located, so a lookalike in the middle of `TYPE` cannot truncate
    it. Folding may drop a character, so the reported name is recovered through
    a per-character source map rather than by reusing a folded offset.
    """
    visible = "".join(
        char for char in stripped
        if unicodedata.category(char) not in GATE_INVISIBLE_CATEGORIES
    )
    # Folding can drop a character, so it is not length-preserving and an offset
    # into the folded string is not an offset into the original. Carry each
    # folded character's source index so the reported name stays a real slice of
    # the author's own spelling.
    folded: List[str] = []
    origin: List[int] = []
    for index, char in enumerate(visible):
        piece = _fold_char(char)
        if piece:
            folded.append(piece)
            origin.append(index)
    line = "".join(folded)
    name_match = GATE_NAME_RE.match(line, GATE_DECORATION_RE.match(line).end())
    if name_match is None:
        return None
    rest = line[name_match.end():]
    reported = visible[origin[name_match.start()]:origin[name_match.end() - 1] + 1]
    separator = GATE_SEPARATOR_RE.match(rest)
    if separator is None:
        return reported, False, rest.strip()
    return reported, True, rest[separator.end():].strip()
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-header-near-miss


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-header-near-miss
def _gate_header_finding(
    block: PdslBlock,
    line_no: int,
    raw_line: str,
    name: str,
) -> PdslFinding:
    """Build the finding for a header that is not a usable gate declaration."""
    return _finding(
        block, "PDSL703", line_no, raw_line,
        f"MENU sub-header `{_elide(name)}:` is not a gate declaration and is ignored",
        hint=f"Write `{GATE_HEADER}: <{' | '.join(GATE_TYPES)}>`; a near-miss leaves the gate undeclared.",
    )


def _menu_shape_header_finding(
    block: PdslBlock,
    line_no: int,
    raw_line: str,
    name: str,
) -> PdslFinding:
    """Build the finding for a header that is not a usable shape declaration."""
    return _finding(
        block, "PDSL713", line_no, raw_line,
        f"MENU sub-header `{_elide(name)}:` is not a shape declaration and is ignored",
        hint=(
            f"Write `{MENU_SHAPE_HEADER}: <{' | '.join(MENU_SHAPE_TYPES)}>`; "
            "a near-miss leaves the shape undeclared."
        ),
    )
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-header-near-miss


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-declaration-literal
def _elide(value: str) -> str:
    """Shorten an author-supplied value so a finding message stays bounded."""
    if len(value) <= GATE_VALUE_ELLIPSIS:
        return value
    return value[:GATE_VALUE_ELLIPSIS - 3] + "..."
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-declaration-literal


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-header-near-miss
def _fold_char(char: str) -> str:
    """Fold one character towards ASCII, but only when it stays one character.

    Offsets must survive folding, because the reported header name is sliced
    from the author's own spelling. NFKC is not length-preserving -- `\u203c`
    becomes `!!` -- so a multi-character result is left alone and simply reads
    as decoration.
    """
    folded = unicodedata.normalize("NFKC", char).upper()
    if len(folded) != 1:
        # NFKC expands it (`\u203c` -> `!!`). Dropped rather than kept, so it
        # cannot truncate a name it sits inside; the caller's source map keeps
        # the reported spelling correct despite the length change.
        return ""
    return GATE_NAME_CONFUSABLES.get(folded, folded)


def _normalize_header_name(name: str) -> str:
    """Fold a header name to ASCII capitals for the near-miss test.

    Per-character folding collapses the fullwidth and mathematical alphabets
    and maps Cyrillic or Greek lookalikes to their Latin twin, so a name that
    *renders* as `TYPE` is read as an attempt at a declaration however it was
    typed -- while every offset is preserved.
    """
    return "".join(
        _fold_char(char)
        for char in name
        if unicodedata.category(char) not in GATE_INVISIBLE_CATEGORIES
    )


def _edit_distance(left: str, right: str) -> int:
    """Optimal string alignment distance, counting an adjacent transposition as one.

    Plain Levenshtein scores a swap as two edits, which would let the commonest
    typo class -- `TPYE`, `TYEP` -- past a distance-1 threshold.
    """
    rows, columns = len(left) + 1, len(right) + 1
    grid = [[0] * columns for _ in range(rows)]
    for row in range(rows):
        grid[row][0] = row
    for column in range(columns):
        grid[0][column] = column
    for row in range(1, rows):
        for column in range(1, columns):
            cost = left[row - 1] != right[column - 1]
            grid[row][column] = min(
                grid[row - 1][column] + 1,
                grid[row][column - 1] + 1,
                grid[row - 1][column - 1] + cost,
            )
            if (
                row > 1
                and column > 1
                and left[row - 1] == right[column - 2]
                and left[row - 2] == right[column - 1]
            ):
                grid[row][column] = min(grid[row][column], grid[row - 2][column - 2] + 1)
    return grid[-1][-1]


def _is_declared_header_typo(
    raw_name: str, target: str, aliases: FrozenSet[str], distance: int,
) -> bool:
    """True when a header looks like a botched declaration of *target*.

    Normalization happens here so every caller sees the same rule: confusable
    letters are mapped, case is folded, and `_`/`-` are trimmed at the ends
    where they are decoration but kept inside a name like `RISK_TYPE`.

    The length check is a pure short-circuit -- a name whose length differs by
    more than the threshold can never be within it -- but it is load-bearing for
    cost, not correctness: without it a long unrecognized header runs the
    quadratic grid on every line of a large file to no possible effect.
    """
    name = _normalize_header_name(raw_name).strip("_-")
    if name.replace("-", "_") in aliases:
        return True
    if abs(len(name) - len(target)) > distance:
        return False
    return _edit_distance(name, target) <= distance


def _is_gate_header_typo(raw_name: str) -> bool:
    """True when a header looks like a botched gate (`TYPE`) declaration."""
    return _is_declared_header_typo(raw_name, GATE_HEADER, GATE_HEADER_ALIASES, GATE_HEADER_TYPO_DISTANCE)


def _is_menu_shape_header_typo(raw_name: str) -> bool:
    """True when a header looks like a botched shape (`SHAPE`) declaration (issue #186)."""
    return _is_declared_header_typo(
        raw_name, MENU_SHAPE_HEADER, MENU_SHAPE_HEADER_ALIASES, MENU_SHAPE_HEADER_TYPO_DISTANCE,
    )
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-gate-header-near-miss


def _handle_pattern_line(
    block: PdslBlock,
    line_no: int,
    raw_line: str,
    local_patterns: Dict[str, int],
    findings: List[PdslFinding],
    section: Optional[str],
) -> bool:
    """Process PATTERNS entries and collect duplicate-definition findings."""
    if section != "PATTERNS":
        return False
    pattern_def = PATTERN_DEF_RE.match(raw_line)
    if pattern_def:
        pattern_name = pattern_def.group("name")
        if pattern_name in local_patterns:
            findings.append(_finding(
                block, "PDSL300", line_no, raw_line,
                f"Duplicate PATTERNS name `{pattern_name}`",
                hint=f"Keep one definition for `{pattern_name}`.",
            ))
        else:
            local_patterns[pattern_name] = line_no
    return True


def _check_section_cap(
    block: PdslBlock,
    state: _BlockValidationState,
    line_no: int,
    raw_line: str,
) -> List[PdslFinding]:
    """Flag the point where top-level DO actions or RULES items exceed the spec's compactness cap.

    Applies uniformly regardless of dash usage — a dashless top-level action
    or rule (see _is_top_level_item_start) counts toward the cap exactly like
    a dash-prefixed one.
    """
    stripped = raw_line.strip()
    if not _is_top_level_item_start(stripped, state.section):
        return []
    indent_len = len(raw_line) - len(raw_line.lstrip(" "))
    if indent_len > 2:
        return []
    if state.section == "DO":
        state.do_count += 1
        if state.do_count == DO_ACTION_CAP + 1:
            return [_finding(
                block, "PDSL600", line_no, raw_line,
                f"UNIT exceeds the {DO_ACTION_CAP}-action DO cap ({state.do_count} top-level actions so far)",
                hint="Refactor into narrower UNITs, or move reusable behavior into a RUN target.",
            )]
    elif state.section == "RULES":
        state.rules_count += 1
        if state.rules_count == RULES_CAP + 1:
            return [_finding(
                block, "PDSL601", line_no, raw_line,
                f"RULES block exceeds the {RULES_CAP}-rule cap ({state.rules_count} rules so far)",
                hint="Refactor into narrower units, or elevate cross-cutting constraints to INVARIANTS.",
            )]
    return []


def _advance_menu_option_counter(
    stripped: str,
    state: _BlockValidationState,
) -> None:
    """Advance expected MENU option numbering when a valid option is seen."""
    option = MENU_OPTION_RE.match(stripped)
    if state.section == "OPTIONS" and option and state.menu_expected is not None:
        number = int(option.group("number"))
        if number == state.menu_expected:
            state.menu_expected += 1


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-run-local-semantics
def _append_missing_match_pattern_findings(
    block: PdslBlock,
    line_no: int,
    raw_line: str,
    local_patterns: Dict[str, int],
    findings: List[PdslFinding],
) -> None:
    """Append findings for matches() references to undefined local patterns."""
    for match in MATCHES_RE.finditer(raw_line):
        pattern_name = match.group("name")
        if pattern_name not in local_patterns:
            findings.append(PdslFinding(
                rule_id="PDSL500",
                severity="error",
                message=f"Undefined local matches() pattern `{pattern_name}`",
                source_path=block.source,
                block_index=block.block_index,
                line=line_no,
                column=match.start("name") + 1,
                end_line=line_no,
                end_column=match.end("name") + 1,
                hint=f"Declare `{pattern_name}` in a local PATTERNS block.",
                context=raw_line,
            ))
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-run-local-semantics


def _validate_section_item(
    block: PdslBlock,
    section: Optional[str],
    menu_expected: Optional[int],
    line_no: int,
    raw_line: str,
) -> List[PdslFinding]:
    stripped = raw_line.strip()
    if not _is_valid_section_item_start(stripped, section, menu_expected):
        return []
    indent_len = len(raw_line) - len(raw_line.lstrip(" "))
    if indent_len > 2 and not (section == "OPTIONS" and menu_expected is not None):
        return []
    starter_rules = {
        "STATE": (STATE_KEYWORDS, "STATE"),
        "WHEN": (WHEN_KEYWORDS, "WHEN"),
        "DO": (DO_KEYWORDS, "DO"),
        "RULES": (RULE_KEYWORDS, "RULES"),
        "INVARIANTS": (RULE_KEYWORDS, "INVARIANTS"),
    }
    if section in starter_rules:
        allowed, section_name = starter_rules[section]
        return _validate_starter(block, allowed, section_name, line_no, raw_line)
    if section == "OPTIONS":
        return _validate_menu_option_item(block, menu_expected, line_no, raw_line, stripped)
    return []


def _validate_menu_option_item(
    block: PdslBlock,
    menu_expected: Optional[int],
    line_no: int,
    raw_line: str,
    stripped: str,
) -> List[PdslFinding]:
    """Validate one MENU OPTIONS line."""
    if menu_expected is None:
        return []
    option = MENU_OPTION_RE.match(stripped)
    if not option:
        return [_finding(
            block, "PDSL400", line_no, raw_line,
            "MENU OPTIONS item must start with a decimal number and contain ->",
            hint="Use `1 label -> ACTION ...` format.",
        )]
    number = int(option.group("number"))
    if number != menu_expected:
        return [_finding(
            block, "PDSL400", line_no, raw_line,
            f"MENU option number must be {menu_expected}, got {number}",
            hint="Number menu options consecutively from 1.",
        )]
    return []


# Sections whose top-level items are single KEYWORD-led lines (PDSL.md's own
# "allowed starter keywords" taxonomy). OPTIONS uses a distinct numbered-item
# grammar (handled separately below); free-form sections (PURPOSE, NOTES, ...)
# have no item concept at all — dashless recognition must not reach into them.
_DASHLESS_ITEM_SECTIONS = {"STATE", "WHEN", "DO", "RULES", "INVARIANTS"}


def _is_top_level_item_start(stripped: str, section: Optional[str]) -> bool:
    """Return whether *stripped* starts a new top-level PDSL item, dash or dashless.

    Dash-prefixed items are always recognized (PDSL.md's documented form). A
    dashless item is recognized by a bare `KEYWORD`-shaped leading token, but
    only within a section that actually has keyword-led items — whether that
    keyword is *valid* for the section is PDSL200's job (_validate_starter),
    not this check's. Indent depth, checked separately by callers, is what
    tells a genuine top-level item apart from a deeper-indented continuation.
    """
    if stripped.startswith("- "):
        return True
    if section not in _DASHLESS_ITEM_SECTIONS:
        return False
    match = re.match(r"^[A-Z][A-Z0-9_-]*\b", stripped)
    if not match:
        return False
    # UNIT/MENU are reserved block-starter keywords, never a valid action/rule
    # keyword in any section. A line like "MENU <name>:" whose name doesn't
    # parse as an identifier (e.g. a placeholder in illustrative docs) isn't
    # a real MENU declaration, but it's still not a dashless DO/RULES item.
    return match.group(0) not in ("UNIT", "MENU")


def _is_valid_section_item_start(
    stripped: str,
    section: Optional[str],
    menu_expected: Optional[int],
) -> bool:
    """Return whether a line is eligible for section-item validation."""
    if _is_top_level_item_start(stripped, section):
        return True
    return bool(section == "OPTIONS" and menu_expected is not None and re.match(r"^\d+\b", stripped))


def _validate_starter(
    block: PdslBlock,
    allowed: Iterable[str],
    section: str,
    line_no: int,
    raw_line: str,
) -> List[PdslFinding]:
    match = ACTION_HEAD_RE.match(raw_line.strip())
    token = match.group("token") if match else None
    if token in set(allowed):
        return []
    allowed_text = ", ".join(sorted(allowed))
    got = token or "<missing>"
    return [_finding(
        block, "PDSL200", line_no, raw_line,
        f"{section} item must start with one of: {allowed_text}; got {got}",
        hint=f"Use a valid {section} starter keyword.",
    )]


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-normalize-findings
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-no-scaffold-output
def _finding(block: PdslBlock, rule_id: str, line_no: int, raw_line: str, message: str, *, hint: str) -> PdslFinding:
    return PdslFinding(
        rule_id=rule_id,
        severity="error",
        message=message,
        source_path=block.source,
        block_index=block.block_index,
        line=line_no,
        column=1,
        end_line=line_no,
        end_column=len(raw_line) + 1,
        hint=hint,
        context=raw_line,
    )

# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-no-scaffold-output
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-normalize-findings
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-run-structural-checks
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-validate-source-of-truth
