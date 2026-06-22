"""Spec coverage analysis for CDSL markers in code.

Measures two metrics:
1. Coverage percentage: ratio of lines within @cpt-begin/@cpt-end blocks
   to total effective lines (non-blank, non-comment).
2. Granularity score: instruction density — ideally 1 block marker pair
   per 10 lines of code. Files with only scope markers get granularity 0.

@cpt-algo:cpt-studio-algo-spec-coverage-scan:p1
@cpt-algo:cpt-studio-algo-spec-coverage-metrics:p1
@cpt-algo:cpt-studio-algo-spec-coverage-granularity:p1
@cpt-algo:cpt-studio-algo-spec-coverage-report:p1
"""
# @cpt-begin:cpt-studio-algo-spec-coverage-scan:p1:inst-scan-datamodel
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .codebase import _SCOPE_MARKER_RE, _BLOCK_BEGIN_RE, _BLOCK_END_RE
from .language_config import EXTENSION_COMMENT_DEFAULTS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FileCoverage:
    """Coverage record for a single code file."""
    path: str
    total_lines: int  # all lines in file
    effective_lines: int  # non-blank, non-comment
    covered_lines: int  # lines within marker scope
    covered_ranges: List[Tuple[int, int]]  # (start, end) 1-indexed inclusive
    uncovered_ranges: List[Tuple[int, int]]
    scope_marker_count: int
    block_marker_count: int  # number of begin/end pairs
    has_scope_only: bool  # has scope markers but no block markers
    coverage_pct: float
    granularity: float

@dataclass
class CoverageReport:
    """Aggregated coverage report."""
    total_files: int
    covered_files: int
    uncovered_files: int
    total_lines: int
    covered_lines: int
    coverage_pct: float
    granularity_score: float
    per_file: List[FileCoverage]
    flagged_files: List[str]  # files with granularity < 0.5
# @cpt-end:cpt-studio-algo-spec-coverage-scan:p1:inst-scan-datamodel


@dataclass(frozen=True)
class _CoverageScanSummary:
    """Intermediate coverage metrics for a single file."""

    effective_lines: int
    covered_lines: int
    covered_ranges: List[Tuple[int, int]]
    uncovered_ranges: List[Tuple[int, int]]
    granularity: float

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-algo-spec-coverage-scan:p1:inst-scan-helpers
def _is_blank_or_comment(line: str, ext: str, state: Optional[Dict[str, Any]] = None) -> bool:
    """Check if a line is blank or a comment for the given file extension.

    When *state* is provided it must be a dict (e.g. ``{"in_block": False,
    "end_marker": ""}``).  The function uses it to track whether the current
    line is inside a multi-line comment block so that continuation lines are
    correctly classified as comments.
    """
    stripped = line.strip()
    if not stripped:
        return True

    if _consume_multiline_comment_state(stripped, state):
        return True

    comment_info = EXTENSION_COMMENT_DEFAULTS.get(ext)
    if not comment_info:
        return False

    single_line, multi_line, block_prefixes = comment_info
    if any(stripped.startswith(prefix) for prefix in single_line):
        return True
    if any(stripped.startswith(prefix) for prefix in block_prefixes):
        return True
    return _starts_multiline_comment(stripped, multi_line, state)

def _build_ranges(sorted_lines: List[int]) -> List[Tuple[int, int]]:
    """Build contiguous ranges from sorted line numbers."""
    if not sorted_lines:
        return []
    ranges: List[Tuple[int, int]] = []
    start = sorted_lines[0]
    end = start
    for ln in sorted_lines[1:]:
        if ln == end + 1:
            end = ln
        else:
            ranges.append((start, end))
            start = ln
            end = ln
    ranges.append((start, end))
    return ranges


def _consume_multiline_comment_state(stripped: str, state: Optional[Dict[str, Any]]) -> bool:
    """Return True when the current line is inside an active multiline comment."""
    if state is None or not state.get("in_block"):
        return False
    end_marker = state["end_marker"]
    if end_marker in stripped:
        state["in_block"] = False
        state["end_marker"] = ""
    return True


def _starts_multiline_comment(
    stripped: str,
    multi_line: List[Dict[str, str]],
    state: Optional[Dict[str, Any]],
) -> bool:
    """Return True when the line starts a multiline comment block."""
    for comment_block in multi_line:
        start_marker = comment_block["start"]
        if not stripped.startswith(start_marker):
            continue
        rest = stripped[len(start_marker):]
        if comment_block["end"] not in rest and state is not None:
            state["in_block"] = True
            state["end_marker"] = comment_block["end"]
        return True
    return False


def _collect_effective_line_numbers(lines: List[str], ext: str) -> Set[int]:
    """Return all non-blank, non-comment line numbers for a file."""
    effective_lines: Set[int] = set()
    comment_state: Dict[str, Any] = {"in_block": False, "end_marker": ""}
    for idx, line in enumerate(lines, start=1):
        if not _is_blank_or_comment(line, ext, comment_state):
            effective_lines.add(idx)
    return effective_lines


def _collect_marker_data(lines: List[str]) -> Tuple[List[int], List[Tuple[int, int]]]:
    """Collect scope markers and closed block ranges from a file."""
    scope_markers: List[int] = []
    block_ranges: List[Tuple[int, int]] = []
    open_blocks: Dict[str, int] = {}
    for line_no, line in enumerate(lines, start=1):
        for marker in _SCOPE_MARKER_RE.finditer(line):
            del marker
            scope_markers.append(line_no)
        for marker in _BLOCK_BEGIN_RE.finditer(line):
            key = f"{marker.group('id')}:{marker.group('phase')}:{marker.group('inst')}"
            open_blocks.setdefault(key, line_no)
        for marker in _BLOCK_END_RE.finditer(line):
            key = f"{marker.group('id')}:{marker.group('phase')}:{marker.group('inst')}"
            start = open_blocks.pop(key, None)
            if start is not None:
                block_ranges.append((start, line_no))
    return scope_markers, block_ranges


def _build_coverage_set(
    effective_line_set: Set[int],
    scope_markers: List[int],
    block_ranges: List[Tuple[int, int]],
) -> Set[int]:
    """Build the set of covered effective lines."""
    if scope_markers and not block_ranges:
        return set(effective_line_set)

    covered_set: Set[int] = set()
    for start, end in block_ranges:
        for line_no in range(start, end + 1):
            if line_no in effective_line_set:
                covered_set.add(line_no)
    covered_set.update(line_no for line_no in scope_markers if line_no in effective_line_set)
    return covered_set


def _calculate_granularity(effective_lines: int, block_count: int, has_scope_only: bool) -> float:
    """Calculate the instruction-density granularity score."""
    if has_scope_only or not block_count:
        return 0.0
    ideal_blocks = max(1.0, effective_lines / 10.0)
    return min(1.0, block_count / ideal_blocks)


def _empty_file_coverage(path: Path, total_lines: int) -> FileCoverage:
    """Build a zero-coverage record for files with no effective lines."""
    return FileCoverage(
        path=str(path),
        total_lines=total_lines,
        effective_lines=0,
        covered_lines=0,
        covered_ranges=[],
        uncovered_ranges=[],
        scope_marker_count=0,
        block_marker_count=0,
        has_scope_only=False,
        coverage_pct=0.0,
        granularity=0.0,
    )


def _summarize_file_coverage(
    effective_line_set: Set[int],
    scope_markers: List[int],
    block_ranges: List[Tuple[int, int]],
) -> _CoverageScanSummary:
    """Calculate aggregate coverage values from parsed marker data."""
    covered_set = _build_coverage_set(effective_line_set, scope_markers, block_ranges)
    effective_lines = len(effective_line_set)
    block_count = len(block_ranges)
    has_scope_only = bool(scope_markers) and not block_count
    return _CoverageScanSummary(
        effective_lines=effective_lines,
        covered_lines=len(covered_set),
        covered_ranges=_build_ranges(sorted(covered_set)),
        uncovered_ranges=_build_ranges(sorted(effective_line_set - covered_set)),
        granularity=_calculate_granularity(effective_lines, block_count, has_scope_only),
    )
# @cpt-end:cpt-studio-algo-spec-coverage-scan:p1:inst-scan-helpers

# ---------------------------------------------------------------------------
# Scan a single file
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-algo-spec-coverage-scan:p1:inst-scan-init
def scan_file_coverage(path: Path) -> Optional[FileCoverage]:
    """Scan a code file and calculate its coverage metrics.

    Returns None if the file cannot be read.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to scan coverage for %s: %s", path, exc)
        return None

    lines = text.splitlines()
    total_lines = len(lines)
    ext = path.suffix.lower()
    # @cpt-end:cpt-studio-algo-spec-coverage-scan:p1:inst-scan-init

    # @cpt-begin:cpt-studio-algo-spec-coverage-scan:p1:inst-scan-count-lines
    effective_line_set = _collect_effective_line_numbers(lines, ext)
    effective_lines = len(effective_line_set)
    # @cpt-end:cpt-studio-algo-spec-coverage-scan:p1:inst-scan-count-lines

    if not effective_lines:
        return _empty_file_coverage(path, total_lines)

    # @cpt-begin:cpt-studio-algo-spec-coverage-scan:p1:inst-scan-scope-markers
    scope_markers, block_ranges = _collect_marker_data(lines)
    # @cpt-end:cpt-studio-algo-spec-coverage-scan:p1:inst-scan-scope-markers
    # @cpt-begin:cpt-studio-algo-spec-coverage-scan:p1:inst-scan-block-markers
    # Marker data is collected above so block ranges and scope markers stay in sync.
    # @cpt-end:cpt-studio-algo-spec-coverage-scan:p1:inst-scan-block-markers

    scope_count = len(scope_markers)
    block_count = len(block_ranges)
    has_scope_only = scope_count > 0 and not block_count

    # @cpt-begin:cpt-studio-algo-spec-coverage-scan:p1:inst-scan-calc-ranges
    summary = _summarize_file_coverage(
        effective_line_set,
        scope_markers,
        block_ranges,
    )
    coverage_pct = summary.covered_lines / summary.effective_lines * 100.0
    # @cpt-end:cpt-studio-algo-spec-coverage-scan:p1:inst-scan-calc-ranges

    # @cpt-begin:cpt-studio-algo-spec-coverage-scan:p1:inst-scan-return
    return FileCoverage(
        path=str(path),
        total_lines=total_lines,
        effective_lines=summary.effective_lines,
        covered_lines=summary.covered_lines,
        covered_ranges=summary.covered_ranges,
        uncovered_ranges=summary.uncovered_ranges,
        scope_marker_count=scope_count,
        block_marker_count=block_count,
        has_scope_only=has_scope_only,
        coverage_pct=round(coverage_pct, 2),
        granularity=round(summary.granularity, 4),
    )
    # @cpt-end:cpt-studio-algo-spec-coverage-scan:p1:inst-scan-return

# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------

def calculate_metrics(file_coverages: List[FileCoverage]) -> CoverageReport:
    """Calculate aggregate coverage metrics from per-file data."""
    # @cpt-begin:cpt-studio-algo-spec-coverage-metrics:p1:inst-metrics-sum-total
    total_files = len(file_coverages)
    covered_files = sum(1 for fc in file_coverages if fc.covered_lines > 0)
    uncovered_files = total_files - covered_files
    total_lines = sum(fc.effective_lines for fc in file_coverages)
    # @cpt-end:cpt-studio-algo-spec-coverage-metrics:p1:inst-metrics-sum-total

    # @cpt-begin:cpt-studio-algo-spec-coverage-metrics:p1:inst-metrics-sum-covered
    covered_lines = sum(fc.covered_lines for fc in file_coverages)
    # @cpt-end:cpt-studio-algo-spec-coverage-metrics:p1:inst-metrics-sum-covered

    # @cpt-begin:cpt-studio-algo-spec-coverage-metrics:p1:inst-metrics-calc-pct
    coverage_pct = (covered_lines / total_lines * 100.0) if total_lines > 0 else 0.0
    # @cpt-end:cpt-studio-algo-spec-coverage-metrics:p1:inst-metrics-calc-pct

    # @cpt-begin:cpt-studio-algo-spec-coverage-granularity:p1:inst-gran-foreach
    gran_num = 0.0
    gran_den = 0
    flagged_files: List[str] = []
    # @cpt-end:cpt-studio-algo-spec-coverage-granularity:p1:inst-gran-foreach

    for fc in file_coverages:
        if fc.covered_lines > 0:
            # @cpt-begin:cpt-studio-algo-spec-coverage-granularity:p1:inst-gran-count-blocks
            gran_num += fc.granularity * fc.effective_lines
            gran_den += fc.effective_lines
            # @cpt-end:cpt-studio-algo-spec-coverage-granularity:p1:inst-gran-count-blocks

            # @cpt-begin:cpt-studio-algo-spec-coverage-granularity:p1:inst-gran-ideal
            # ideal is effective_lines / 10 — already computed in per-file granularity
            # @cpt-end:cpt-studio-algo-spec-coverage-granularity:p1:inst-gran-ideal

            # @cpt-begin:cpt-studio-algo-spec-coverage-granularity:p1:inst-gran-calc
            # per-file granularity = min(1.0, actual_blocks / ideal_blocks) — already in fc.granularity
            # @cpt-end:cpt-studio-algo-spec-coverage-granularity:p1:inst-gran-calc

            # @cpt-begin:cpt-studio-algo-spec-coverage-granularity:p1:inst-gran-flag
            if fc.granularity < 0.5:
                flagged_files.append(fc.path)
            # @cpt-end:cpt-studio-algo-spec-coverage-granularity:p1:inst-gran-flag

    # @cpt-begin:cpt-studio-algo-spec-coverage-granularity:p1:inst-gran-overall
    granularity_score = (gran_num / gran_den) if gran_den > 0 else 0.0
    # @cpt-end:cpt-studio-algo-spec-coverage-granularity:p1:inst-gran-overall
    # @cpt-begin:cpt-studio-algo-spec-coverage-granularity:p1:inst-gran-return
    # granularity_score returned as part of CoverageReport below
    # @cpt-end:cpt-studio-algo-spec-coverage-granularity:p1:inst-gran-return

    # @cpt-begin:cpt-studio-algo-spec-coverage-metrics:p1:inst-metrics-return
    return CoverageReport(
        total_files=total_files,
        covered_files=covered_files,
        uncovered_files=uncovered_files,
        total_lines=total_lines,
        covered_lines=covered_lines,
        coverage_pct=round(coverage_pct, 2),
        granularity_score=round(granularity_score, 4),
        per_file=file_coverages,
        flagged_files=flagged_files,
    )
    # @cpt-end:cpt-studio-algo-spec-coverage-metrics:p1:inst-metrics-return

# ---------------------------------------------------------------------------
# Report generation (coverage.py JSON format)
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-spec-coverage-report:p1:inst-report-datamodel
def generate_report(report: CoverageReport, *, verbose: bool = False, project_root: Optional[Path] = None) -> Dict:
    """Generate JSON report matching coverage.py structure."""
    def _rel(p: str) -> str:
        if project_root is not None:
            candidate = Path(p)
            if candidate.is_relative_to(project_root):
                return str(candidate.relative_to(project_root))
        return p
    # @cpt-end:cpt-studio-algo-spec-coverage-report:p1:inst-report-datamodel

    # @cpt-begin:cpt-studio-algo-spec-coverage-report:p1:inst-report-summary
    summary = {
        "total_files": report.total_files,
        "covered_files": report.covered_files,
        "uncovered_files": report.uncovered_files,
        "total_lines": report.total_lines,
        "covered_lines": report.covered_lines,
        "coverage_pct": report.coverage_pct,
        "granularity_score": report.granularity_score,
    }

    if report.flagged_files:
        summary["flagged_files_count"] = len(report.flagged_files)
    # @cpt-end:cpt-studio-algo-spec-coverage-report:p1:inst-report-summary

    # @cpt-begin:cpt-studio-algo-spec-coverage-report:p1:inst-report-per-file
    files: Dict[str, Dict] = {}
    uncovered_file_list: List[str] = []

    for fc in report.per_file:
        entry: Dict = {
            "total_lines": fc.effective_lines,
            "covered_lines": fc.covered_lines,
            "coverage_pct": fc.coverage_pct,
            "granularity": fc.granularity,
        }

        if not fc.covered_lines:
            uncovered_file_list.append(_rel(fc.path))

        if fc.has_scope_only:
            entry["scope_only"] = True

        if fc.uncovered_ranges:
            entry["uncovered_ranges"] = [[s, e] for s, e in fc.uncovered_ranges]

        # @cpt-begin:cpt-studio-algo-spec-coverage-report:p1:inst-report-verbose
        if verbose:
            entry["scope_markers"] = fc.scope_marker_count
            entry["block_markers"] = fc.block_marker_count
            if fc.covered_ranges:
                entry["covered_ranges"] = [[s, e] for s, e in fc.covered_ranges]
        # @cpt-end:cpt-studio-algo-spec-coverage-report:p1:inst-report-verbose

        files[_rel(fc.path)] = entry
    # @cpt-end:cpt-studio-algo-spec-coverage-report:p1:inst-report-per-file

    # @cpt-begin:cpt-studio-algo-spec-coverage-report:p1:inst-report-return
    result: Dict = {
        "summary": summary,
        "files": files,
    }

    if uncovered_file_list:
        result["uncovered_files"] = uncovered_file_list

    if report.flagged_files:
        result["flagged_files"] = [_rel(f) for f in report.flagged_files]

    return result
    # @cpt-end:cpt-studio-algo-spec-coverage-report:p1:inst-report-return
