"""Spec coverage command — measure CDSL marker coverage in code.

@cpt-flow:cpt-studio-flow-spec-coverage-report:p1
@cpt-dod:cpt-studio-dod-spec-coverage-percentage:p1
@cpt-dod:cpt-studio-dod-spec-coverage-granularity:p1
@cpt-state:cpt-studio-state-spec-coverage-report:p1
@cpt-dod:cpt-studio-dod-spec-coverage-report:p1
"""
# @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-coverage-imports
import argparse
import json
import sys
from pathlib import Path
from typing import List

from ..utils.coverage import (
    FileCoverage,
    calculate_metrics,
    generate_report,
    scan_file_coverage,
)
from ..utils.ui import ui
# @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-coverage-imports


def _warn_spec_coverage(message: str) -> None:
    sys.stderr.write(f"spec-coverage: warning: {message}\n")


def _build_spec_coverage_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spec-coverage",
        description="Measure CDSL marker coverage in codebase files",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=None,
        help="Minimum coverage percentage (0-100). Exit 2 if below.",
    )
    parser.add_argument(
        "--min-file-coverage",
        type=float,
        default=None,
        help="Minimum per-file coverage percentage (0-100). Exit 2 if any file is below.",
    )
    parser.add_argument(
        "--min-granularity",
        type=float,
        default=None,
        help="Minimum granularity score (0-1). Exit 2 if below.",
    )
    parser.add_argument(
        "--min-file-granularity",
        type=float,
        default=None,
        help="Minimum per-file granularity score (0-1). Exit 2 if any covered file is below.",
    )
    parser.add_argument(
        "--system",
        action="append",
        default=None,
        dest="systems",
        help="Limit to system slug(s). Can be repeated. Default: all systems.",
    )
    parser.add_argument("--verbose", action="store_true", help="Include per-file marker details and covered ranges")
    parser.add_argument("--output", default=None, help="Write report to file instead of stdout")
    return parser


def _collect_system_slugs(nodes: List[object]) -> set[str]:
    """Return all known system slugs, including nested children."""
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-user-spec-coverage
    slugs: set[str] = set()
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-user-spec-coverage

    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-load-context
    def _visit(node: object) -> None:
        slug = getattr(node, "slug", "")
        if slug:
            slugs.add(slug)
        for child in getattr(node, "children", []):
            _visit(child)
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-load-context

    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-coverage-helpers
    for node in nodes:
        _visit(node)
    return slugs
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-coverage-helpers


def _resolve_code_path(project_root: Path, path_str: str) -> Path:
    return (project_root / path_str).resolve()


def _collect_codebase_files(
    system_node: object,
    project_root: Path,
    code_files_to_scan: List[Path],
) -> None:
    for cb_entry in getattr(system_node, "codebase", []):
        path_str = (
            getattr(cb_entry, "path", "")
            if not isinstance(cb_entry, dict)
            else cb_entry.get("path", "")
        )
        extensions = (
            getattr(cb_entry, "extensions", None)
            if not isinstance(cb_entry, dict)
            else cb_entry.get("extensions", None)
        ) or [".py"]
        code_path = _resolve_code_path(project_root, path_str)
        if not code_path.exists():
            continue
        if code_path.is_file():
            code_files_to_scan.append(code_path)
            continue
        for ext in extensions:
            code_files_to_scan.extend(code_path.rglob(f"*{ext}"))
    for child in getattr(system_node, "children", []):
        _collect_codebase_files(child, project_root, code_files_to_scan)


def _validate_selected_systems(args, meta) -> tuple[set[str] | None, dict | None]:
    system_slugs = set(args.systems) if args.systems else None
    if system_slugs is None:
        return None, None
    unknown_systems = sorted(system_slugs - _collect_system_slugs(list(meta.systems)))
    if unknown_systems:
        return set(), {
            "status": "FAIL",
            "message": "Unknown system selector(s)",
            "unknown_systems": unknown_systems,
        }
    return system_slugs, None


def _collect_selected_system_files(meta, project_root: Path, system_slugs: set[str] | None) -> List[Path]:
    code_files_to_scan: List[Path] = []

    def visit(node: object) -> None:
        if system_slugs is None:
            _collect_codebase_files(node, project_root, code_files_to_scan)
            return
        slug = getattr(node, "slug", "")
        if slug in system_slugs:
            _collect_codebase_files(node, project_root, code_files_to_scan)
            return
        for child in getattr(node, "children", []):
            visit(child)

    for system_node in meta.systems:
        visit(system_node)
    return code_files_to_scan


def _filter_ignored_files(code_files_to_scan: List[Path], project_root: Path, meta) -> List[Path]:
    filtered_files: List[Path] = []
    for file_path in code_files_to_scan:
        try:
            rel = file_path.resolve().relative_to(project_root).as_posix()
        except ValueError as exc:
            _warn_spec_coverage(f"code file {file_path} is outside project root {project_root}: {exc}")
            rel = None
        if rel and meta.is_ignored(rel):
            continue
        filtered_files.append(file_path)
    return filtered_files


def _empty_coverage_result() -> dict:
    return {
        "status": "PASS",
        "summary": {
            "total_files": 0,
            "covered_files": 0,
            "coverage_pct": 0.0,
            "granularity_score": 0.0,
        },
        "message": "No codebase files found in registry",
    }


def _scan_file_coverages(filtered_files: List[Path]) -> List[FileCoverage]:
    file_coverages: List[FileCoverage] = []
    for file_path in sorted(set(filtered_files)):
        file_coverage = scan_file_coverage(file_path)
        if file_coverage is not None:
            file_coverages.append(file_coverage)
    return file_coverages


def _check_min_coverage(report, args, threshold_failures: List[str]) -> bool:
    if args.min_coverage is None or report.coverage_pct >= args.min_coverage:
        return False
    threshold_failures.append(f"coverage {report.coverage_pct:.2f}% < {args.min_coverage:.2f}%")
    return True


def _check_min_file_coverage(
    report,
    args,
    project_root: Path,
    threshold_failures: List[str],
) -> bool:
    failed = False
    if args.min_file_coverage is None:
        return failed
    for file_coverage in report.per_file:
        if not file_coverage.total_lines or file_coverage.coverage_pct >= args.min_file_coverage:
            continue
        failed = True
        rel = _rel_path(file_coverage.path, project_root)
        threshold_failures.append(
            f"file {rel} coverage {file_coverage.coverage_pct:.2f}% < "
            f"{args.min_file_coverage:.2f}%"
        )
    return failed


def _check_min_granularity(report, args, threshold_failures: List[str]) -> bool:
    if args.min_granularity is None or report.granularity_score >= args.min_granularity:
        return False
    threshold_failures.append(f"granularity {report.granularity_score:.4f} < {args.min_granularity:.4f}")
    return True


def _check_min_file_granularity(
    report,
    args,
    project_root: Path,
    threshold_failures: List[str],
) -> bool:
    failed = False
    if args.min_file_granularity is None:
        return failed
    for file_coverage in report.per_file:
        if not file_coverage.effective_lines or not file_coverage.covered_lines:
            continue
        if file_coverage.granularity >= args.min_file_granularity:
            continue
        failed = True
        rel = _rel_path(file_coverage.path, project_root)
        threshold_failures.append(
            f"file {rel} granularity {file_coverage.granularity:.4f} < "
            f"{args.min_file_granularity:.4f}"
        )
    return failed


def _apply_thresholds(report, args, project_root: Path, json_report: dict) -> str:
    threshold_failures: List[str] = []
    failed = any((
        _check_min_coverage(report, args, threshold_failures),
        _check_min_file_coverage(report, args, project_root, threshold_failures),
        _check_min_granularity(report, args, threshold_failures),
        _check_min_file_granularity(report, args, project_root, threshold_failures),
    ))
    status = "FAIL" if failed else "PASS"
    json_report["status"] = status
    if threshold_failures:
        json_report["threshold_failures"] = threshold_failures
    return status


def _load_spec_coverage_context():
    from ..utils.context import get_context

    ctx = get_context()
    if not ctx:
        ui.result({"status": "ERROR", "message": "Constructor Studio not initialized. Run 'cfs init' first."})
        return None
    return ctx.meta, ctx.project_root


def _generate_spec_coverage_report(args, meta, project_root: Path) -> tuple[dict, int]:
    system_slugs, validation_error = _validate_selected_systems(args, meta)
    if validation_error is not None:
        return validation_error, 2
    if system_slugs == set():
        return {}, 2
    filtered_files = _filter_ignored_files(
        _collect_selected_system_files(meta, project_root, system_slugs),
        project_root,
        meta,
    )
    if not filtered_files:
        return _empty_coverage_result(), 0
    file_coverages = _scan_file_coverages(filtered_files)
    report = calculate_metrics(file_coverages)
    json_report = generate_report(report, verbose=args.verbose, project_root=project_root)
    status = _apply_thresholds(report, args, project_root, json_report)
    return json_report, 0 if status == "PASS" else 2

def cmd_spec_coverage(argv: List[str]) -> int:
    """Run spec coverage analysis on registered codebase files."""
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-user-spec-coverage
    args = _build_spec_coverage_parser().parse_args(argv)
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-user-spec-coverage

    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-load-context
    context = _load_spec_coverage_context()
    if context is None:
        return 1
    meta, project_root = context
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-load-context
    json_report, exit_code = _generate_spec_coverage_report(args, meta, project_root)

    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-return-report
    _output(json_report, args)
    return exit_code
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-return-report

# @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-coverage-helpers
def _rel_path(p: str, project_root: Path) -> str:
    """Return path relative to project_root, or original if not possible."""
    try:
        return str(Path(p).relative_to(project_root))
    except ValueError as exc:
        _warn_spec_coverage(f"path {p} is outside project root {project_root}: {exc}")
        return p

def _output(data: dict, args: argparse.Namespace) -> None:
    """Output report to stdout (JSON or human) or file."""
    if getattr(args, "output", None):
        text = json.dumps(data, indent=2, ensure_ascii=False)
        Path(args.output).write_text(text, encoding="utf-8")
        return
    ui.result(data, human_fn=_human_spec_coverage)

def _format_ranges(ranges: list) -> str:
    """Format [[start, end], ...] as 'start-end, start-end, ...'."""
    parts = []
    for r in ranges:
        if isinstance(r, (list, tuple)) and len(r) == 2:
            s, e = r
            parts.append(str(s) if s == e else f"{s}-{e}")
    return ", ".join(parts)


def _show_spec_coverage_files(files: dict) -> None:
    covered = {path: entry for path, entry in files.items() if entry.get("covered_lines", 0) > 0}
    uncovered = {path: entry for path, entry in files.items() if not entry.get("covered_lines", 0)}
    if covered:
        ui.step(f"Covered files ({len(covered)})")
        for path, entry in covered.items():
            lines = entry.get("total_lines", 0)
            cov = entry.get("coverage_pct", 0)
            gran = entry.get("granularity", 0)
            ui.substep(f"  {path}  {cov:.0f}% g={gran:.2f} ({lines} lines)")
            uncov_ranges = entry.get("uncovered_ranges", [])
            if uncov_ranges:
                ui.substep(f"    uncovered: {_format_ranges(uncov_ranges)}")
    if uncovered:
        ui.blank()
        ui.step(f"Uncovered files ({len(uncovered)})")
        for path, entry in uncovered.items():
            ui.substep(f"  {path}  ({entry.get('total_lines', 0)} lines)")


def _show_spec_coverage_status(status: str, failures: list) -> None:
    if failures:
        ui.blank()
        for failure in failures:
            ui.warn(failure)
    if status == "PASS":
        ui.success("All thresholds met.")
    elif status == "FAIL":
        ui.error("Threshold check failed.")
    else:
        ui.info(f"Status: {status}")

def _human_spec_coverage(data: dict) -> None:
    status = data.get("status", "")
    unknown_systems = data.get("unknown_systems", [])
    ui.header("Spec Coverage")
    if unknown_systems:
        ui.error(data.get("message", "Unknown system selector(s)"))
        for slug in unknown_systems:
            ui.substep(f"  unknown system: {slug}")
        ui.blank()
        return

    summary = data.get("summary", {})
    ui.detail("Files", f"{summary.get('covered_files', 0)}/{summary.get('total_files', 0)} covered")
    ui.detail("Coverage", f"{summary.get('coverage_pct', 0):.1f}%")
    ui.detail("Granularity", f"{summary.get('granularity_score', 0):.4f}")

    # Per-file details — files is a dict {path: entry_dict}
    files = data.get("files", {})
    if files and isinstance(files, dict):
        ui.blank()
        _show_spec_coverage_files(files)

    failures = data.get("threshold_failures", [])
    _show_spec_coverage_status(status, failures)
    ui.blank()
# @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-coverage-helpers
