"""PDSL block extraction and deterministic validation helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-validate-source-of-truth
@dataclass(frozen=True)
class PdslBlock:
    source: str
    block_index: int
    text: str
    line: int
    column: int
    end_line: int
    end_column: int


@dataclass(frozen=True)
class PdslFinding:
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
    message: str
    source_path: str
    line: Optional[int] = None
    column: Optional[int] = None
    kind: str = "ERROR"

    def to_dict(self) -> Dict[str, object]:
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
    source: str
    status: str
    findings: Tuple[PdslFinding, ...]
    errors: Tuple[PdslError, ...]

    def to_dict(self, *, verbose: bool = False) -> Dict[str, object]:
        return {
            "source": self.source,
            "status": self.status,
            "findings": [finding.to_dict(verbose=verbose) for finding in self.findings],
            "errors": [error.to_dict() for error in self.errors],
        }


@dataclass(frozen=True)
class PdslSource:
    source: str
    text: str


FENCE_RE = re.compile(r"^```(?P<lang>[A-Za-z0-9_-]+)?\s*$")
UNIT_OR_MENU_RE = re.compile(r"^(UNIT|MENU)\s+(?P<name>[A-Za-z][A-Za-z0-9_-]*)\b")
PATTERN_DEF_RE = re.compile(r"^\s{2}(?P<name>[A-Za-z][A-Za-z0-9_-]*)\s*:\s*/")
MATCHES_RE = re.compile(r"\bmatches\(\s*[^,]+,\s*(?P<quote>['\"]?)(?P<name>[A-Za-z][A-Za-z0-9_-]*)\1\s*\)")
SECTION_HEAD_RE = re.compile(r"^(?P<section>[A-Z][A-Z0-9_-]*):")
ACTION_HEAD_RE = re.compile(r"^-\s+(?P<token>[A-Z][A-Z0-9_-]*)(?=\b|\s|$)")
MENU_OPTION_RE = re.compile(r"^(?:-\s+)?(?P<number>\d+)\b.*->")

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
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-assign-block-index
            blocks.append(PdslBlock(
                source=source,
                block_index=len(blocks),
                text=block_text,
                line=start_line,
                column=1,
                end_line=max(start_line, idx - 1),
                end_column=len(current[-1]) + 1 if current else 1,
            ))
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-assign-block-index
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
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-assign-block-index
        blocks.append(PdslBlock(
            source=source,
            block_index=0,
            text=text,
            line=1,
            column=1,
            end_line=max(1, len(lines)),
            end_column=(len(lines[-1]) + 1) if lines else 1,
        ))
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-assign-block-index
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-scan:p1:inst-use-whole-source
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
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-sort-findings
    findings.sort(key=lambda f: (f.source_path, f.block_index, f.line, f.column, f.rule_id, f.message))
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-sort-findings
    errors: Tuple[PdslError, ...] = ()
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-if-source-error
    status = "FAIL" if findings else "PASS"
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-if-source-error
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-if-findings
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-return-source-fail
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-else-source-pass
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-return-source-pass
    return PdslSourceResult(source.source, status, tuple(findings), errors)
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-return-source-pass
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-else-source-pass
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-return-source-fail
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-if-findings


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-return-source-error
def error_result(source: str, error: PdslError) -> PdslSourceResult:
    return PdslSourceResult(source=source, status="ERROR", findings=(), errors=(error,))
# @cpt-end:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-return-source-error


# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-summary:p1:inst-build-summary-object
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-summary:p1:inst-preserve-input-order
# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-summary:p1:inst-count-statuses
def build_envelope(results: Sequence[PdslSourceResult], *, command: str, verbose: bool = False) -> Dict[str, object]:
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
        "ok": error_count == 0 and fail_count == 0,
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
    section: Optional[str] = None
    menu_expected: Optional[int] = None
    in_menu = False

    for offset, raw_line in enumerate(block.text.splitlines(), start=0):
        line_no = block.line + offset
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        indent_len = len(raw_line) - len(raw_line.lstrip(" "))

        unit_menu = UNIT_OR_MENU_RE.match(stripped)
        if unit_menu:
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
            section = None
            menu_expected = None
            in_menu = kind == "MENU"
            continue

        section_head = SECTION_HEAD_RE.match(stripped)
        if section_head:
            section_name = section_head.group("section")
            if section_name not in SECTION_HEADERS:
                # Some prompt-adjacent DSLs and explanatory blocks use
                # ALL-CAPS labels inside pdsl fences. They are not executable
                # PDSL sections unless the keyword is known by the spec.
                continue
            if indent_len > 0 and not (in_menu and section_name in {"TITLE", "OPTIONS", "INVALID"}):
                continue
            section = section_name
            menu_expected = 1 if in_menu and section == "OPTIONS" else None
            continue

        if section == "PATTERNS":
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
            continue

        findings.extend(_validate_section_item(block, section, menu_expected, line_no, raw_line))
        if section == "OPTIONS" and MENU_OPTION_RE.match(stripped) and menu_expected is not None:
            number = int(MENU_OPTION_RE.match(stripped).group("number"))  # type: ignore[union-attr]
            if number == menu_expected:
                menu_expected += 1

# @cpt-begin:cpt-studio-algo-pdsl-validation-cli-helper-validate:p1:inst-run-local-semantics
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
    return findings


def _validate_section_item(
    block: PdslBlock,
    section: Optional[str],
    menu_expected: Optional[int],
    line_no: int,
    raw_line: str,
) -> List[PdslFinding]:
    stripped = raw_line.strip()
    if not stripped.startswith("- "):
        if section == "OPTIONS" and menu_expected is not None and re.match(r"^\d+\b", stripped):
            pass
        else:
            return []
    indent_len = len(raw_line) - len(raw_line.lstrip(" "))
    if indent_len > 2 and not (section == "OPTIONS" and menu_expected is not None):
        return []
    if section == "STATE":
        return _validate_starter(block, STATE_KEYWORDS, "STATE", line_no, raw_line)
    if section == "WHEN":
        return _validate_starter(block, WHEN_KEYWORDS, "WHEN", line_no, raw_line)
    if section == "DO":
        return _validate_starter(block, DO_KEYWORDS, "DO", line_no, raw_line)
    if section in {"RULES", "INVARIANTS"}:
        return _validate_starter(block, RULE_KEYWORDS, section, line_no, raw_line)
    if section == "OPTIONS":
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
        if menu_expected is not None and number != menu_expected:
            return [_finding(
                block, "PDSL400", line_no, raw_line,
                f"MENU option number must be {menu_expected}, got {number}",
                hint="Number menu options consecutively from 1.",
            )]
    return []


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
