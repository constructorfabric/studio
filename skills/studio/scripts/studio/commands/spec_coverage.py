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
import logging
from pathlib import Path
from typing import List, Tuple

from ..utils import decision_log
from ..utils.codebase import resolve_entry_code_files
from ..utils.coverage import (
    FileCoverage,
    calculate_metrics,
    generate_report,
    scan_file_coverage,
)
from ..utils.ui import ui
logger = logging.getLogger(__name__)
# @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-coverage-imports


# @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-human-report-helpers
def _warn_spec_coverage(message: str) -> None:
    logger.warning("spec-coverage: %s", message)
# @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-human-report-helpers


def _build_spec_coverage_parser() -> argparse.ArgumentParser:
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-build-parser
    parser = argparse.ArgumentParser(
        prog="spec-coverage",
        description="Measure CDSL marker coverage in codebase files",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=None,
        help="Minimum coverage percentage (0-100). Exit 2 if below; a positive value also "
             "exits 2 if nothing was assessed.",
    )
    parser.add_argument(
        "--min-file-coverage",
        type=float,
        default=None,
        help="Minimum per-file coverage percentage (0-100). Exit 2 if any file is below; "
             "a positive value also exits 2 if nothing was assessed.",
    )
    parser.add_argument(
        "--min-granularity",
        type=float,
        default=None,
        help="Minimum granularity score (0-1). Exit 2 if below; a positive value also "
             "exits 2 if nothing was assessed.",
    )
    parser.add_argument(
        "--min-file-granularity",
        type=float,
        default=None,
        help="Minimum per-file granularity score (0-1). Exit 2 if any covered file is below; "
             "a positive value also exits 2 if nothing was assessed.",
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
    parser.add_argument("--semantic", action="store_true",
                        help="Attach the advisory semantic-coverage pass — assesses covered/partial/"
                             "wrong/unjudgeable per marked block; never gates status/exit "
                             "(see architecture/features/spec-coverage.md)")
    return parser
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-build-parser


# @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-collect-system-slugs
def _collect_system_slugs(nodes: List[object]) -> set[str]:
    """Return all known system slugs, including nested children."""
    slugs: set[str] = set()
    def _visit(node: object) -> None:
        slug = getattr(node, "slug", "")
        if slug:
            slugs.add(slug)
        for child in getattr(node, "children", []):
            _visit(child)
    for node in nodes:
        _visit(node)
    return slugs
# @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-collect-system-slugs


# @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-collect-codebase-files
def _resolve_code_path(project_root: Path, path_str: str) -> Path:
    return (project_root / path_str).resolve()
# @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-collect-codebase-files


def _collect_codebase_files(
    system_node: object,
    project_root: Path,
    code_files_to_scan: List[Path],
) -> int:
    """Collect this node's code files, returning how many candidates were excluded.

    The count is returned rather than dropped because switching to the shared
    policy changes the population the coverage percentage is computed over: a
    registered root holding a vendored subtree contributes fewer files than it
    used to. A metric whose denominator moves has to say so, or a percentage
    change looks like the code changed.
    """
    excluded = 0
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-collect-codebase-files
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
        # Resolved through the shared policy rather than a bare rglob, so this
        # command and `validate` cannot disagree about which files one entry
        # covers -- and so a registered parent root does not re-admit the
        # vendored trees that registration itself refuses.
        entry_files, entry_excluded = resolve_entry_code_files(
            code_path, extensions, project_root=project_root
        )
        excluded += entry_excluded
        code_files_to_scan.extend(entry_files)
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-collect-codebase-files
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-collect-codebase-files
    for child in getattr(system_node, "children", []):
        excluded += _collect_codebase_files(child, project_root, code_files_to_scan)
    return excluded
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-collect-codebase-files


def _validate_selected_systems(args, meta) -> tuple[set[str] | None, dict | None]:
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-validate-systems
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
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-validate-systems


def _collect_selected_system_files(
    meta, project_root: Path, system_slugs: set[str] | None
) -> Tuple[List[Path], int]:
    """Files the selected systems register, and how many candidates were excluded."""
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-resolve-code-files
    code_files_to_scan: List[Path] = []
    excluded = 0

    def visit(node: object) -> None:
        nonlocal excluded
        if system_slugs is None:
            excluded += _collect_codebase_files(node, project_root, code_files_to_scan)
            return
        slug = getattr(node, "slug", "")
        if slug in system_slugs:
            excluded += _collect_codebase_files(node, project_root, code_files_to_scan)
            return
        for child in getattr(node, "children", []):
            visit(child)

    for system_node in meta.systems:
        visit(system_node)
    return code_files_to_scan, excluded
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-resolve-code-files


def _filter_ignored_files(code_files_to_scan: List[Path], project_root: Path, meta) -> List[Path]:
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-filter-ignored-files
    filtered_files: List[Path] = []
    root = project_root.resolve()   # resolve both sides so a symlinked/unresolved root
    for file_path in code_files_to_scan:   # (e.g. macOS /var -> /private/var) still matches
        try:
            rel = file_path.resolve().relative_to(root).as_posix()
        except ValueError as exc:
            _warn_spec_coverage(f"code file {file_path} is outside project root {project_root}: {exc}")
            rel = None
        if rel and meta.is_ignored(rel):
            continue
        filtered_files.append(file_path)
    return filtered_files
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-filter-ignored-files


def _count_selected_codebase_entries(meta, system_slugs: set[str] | None) -> int:
    """Count codebase entries registered by the selected systems.

    Distinguishes "nothing is registered" from "what is registered resolves to
    no files" -- two different mistakes that otherwise produce identical output.
    """
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-count-registered-entries
    def count_subtree(node: object) -> int:
        """Entries registered by ``node`` and every descendant of it."""
        return len(getattr(node, "codebase", None) or []) + sum(
            count_subtree(child) for child in getattr(node, "children", [])
        )

    def visit(node: object) -> int:
        """Count ``node``'s subtree once it is in scope, mirroring file collection."""
        if system_slugs is None or getattr(node, "slug", "") in system_slugs:
            return count_subtree(node)
        return sum(visit(child) for child in getattr(node, "children", []))

    return sum(visit(system_node) for system_node in meta.systems)
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-count-registered-entries


def _requested_thresholds(args) -> List[str]:
    """Names of the thresholds whose satisfaction the caller actually demanded.

    A non-positive threshold is met by any scope, empty or not, so it demands no
    guarantee and is not counted as one. Without that, ``--min-coverage 0`` would
    fail an empty scope while passing a populated one sitting at 0.0% -- and the
    exit code has to keep answering a single question: was a guarantee demanded
    that cannot be given?
    """
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-detect-requested-thresholds
    requested = []
    for flag, attr in (
        ("--min-coverage", "min_coverage"),
        ("--min-file-coverage", "min_file_coverage"),
        ("--min-granularity", "min_granularity"),
        ("--min-file-granularity", "min_file_granularity"),
    ):
        value = getattr(args, attr, None)
        if value is not None and value > 0:
            requested.append(flag)
    return requested
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-detect-requested-thresholds


def _empty_coverage_result(registered_entries: int = 0, requested_thresholds=None) -> dict:
    """Report for a scan that completed with nothing in scope.

    The check ran and found nothing to cover, so nothing failed -- unless the
    caller demanded a guarantee, which cannot be given over an empty scope.
    Either way ``applicable`` records that there was nothing to assess, so an
    empty result is no longer indistinguishable from a fully covered one.
    """
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-empty-report
    requested_thresholds = requested_thresholds or []
    if registered_entries:
        message = (
            f"No code files found: {registered_entries} registered codebase "
            f"{'entry' if registered_entries == 1 else 'entries'} resolved to 0 files"
        )
    else:
        message = "No codebase entries are registered, so no code files were scanned"
    result = {
        "status": "FAIL" if requested_thresholds else "PASS",
        "applicable": False,
        "summary": {
            "total_files": 0,
            "covered_files": 0,
            "coverage_pct": 0.0,
            "granularity_score": 0.0,
        },
        "message": message,
    }
    if requested_thresholds:
        result["threshold_failures"] = [
            f"cannot assess {flag}: 0 files from {registered_entries} registered "
            f"codebase {'entry' if registered_entries == 1 else 'entries'}"
            for flag in requested_thresholds
        ]
    return result
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-empty-report


def _scan_file_coverages(filtered_files: List[Path]) -> List[FileCoverage]:
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-foreach-file
    file_coverages: List[FileCoverage] = []
    for file_path in sorted(set(filtered_files)):
        file_coverage = scan_file_coverage(file_path)
        if file_coverage is not None:
            file_coverages.append(file_coverage)
    return file_coverages
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-foreach-file


def _check_min_coverage(report, args, threshold_failures: List[str]) -> bool:
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-apply-thresholds
    if args.min_coverage is None or report.coverage_pct >= args.min_coverage:
        return False
    threshold_failures.append(f"coverage {report.coverage_pct:.2f}% < {args.min_coverage:.2f}%")
    return True
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-apply-thresholds


def _check_min_file_coverage(
    report,
    args,
    project_root: Path,
    threshold_failures: List[str],
) -> bool:
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-apply-thresholds
    failed = False
    if args.min_file_coverage is None:
        return failed
    for file_coverage in report.per_file:
        if not file_coverage.effective_lines or file_coverage.coverage_pct >= args.min_file_coverage:
            continue
        failed = True
        rel = _rel_path(file_coverage.path, project_root)
        threshold_failures.append(
            f"file {rel} coverage {file_coverage.coverage_pct:.2f}% < "
            f"{args.min_file_coverage:.2f}%"
        )
    return failed
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-apply-thresholds


def _check_min_granularity(report, args, threshold_failures: List[str]) -> bool:
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-apply-thresholds
    if args.min_granularity is None or report.granularity_score >= args.min_granularity:
        return False
    threshold_failures.append(f"granularity {report.granularity_score:.4f} < {args.min_granularity:.4f}")
    return True
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-apply-thresholds


def _check_min_file_granularity(
    report,
    args,
    project_root: Path,
    threshold_failures: List[str],
) -> bool:
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-apply-thresholds
    failed = False
    if args.min_file_granularity is None:
        return failed
    for file_coverage in report.per_file:
        if not file_coverage.effective_lines or not file_coverage.covered_lines:
            continue
        # A scope-only file scores 0.0 by definition rather than by measurement:
        # the metric deliberately refuses to credit a whole-file claim. Reading
        # that sentinel as a low score makes any positive floor reject every
        # re-export module and entry point in the tree, which is why this
        # threshold is currently unusable as a gate. Those files are reported
        # under their own heading instead, so exempting them here hides nothing.
        if file_coverage.has_scope_only:
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
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-apply-thresholds


def _apply_thresholds(report, args, project_root: Path, json_report: dict) -> str:
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-if-threshold
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
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-if-threshold


def _load_spec_coverage_context():
    from ..utils.context import get_context

    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-load-context
    ctx = get_context()
    if not ctx:
        ui.result({"status": "ERROR", "message": "Constructor Studio not initialized. Run 'cfs init' first."})
        return None
    return ctx.meta, ctx.project_root
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-load-context


# @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-attach-semantic
def _attach_semantic_section(args, filtered_files, json_report) -> None:
    """Attach the advisory semantic pass AFTER status/exit are set, so a verdict can never gate."""
    if not getattr(args, "semantic", False):
        return
    try:
        # Everything advisory lives inside the guard — imports, context resolution, and the pass
        # itself — so NOTHING (an import failure included) can change the structural status/exit
        # already computed above. A failure is recorded as an advisory error rather than crashing.
        from ..utils.context import get_context
        from ..utils.semantic_coverage import run_semantic_pass
        ctx = get_context()
        if ctx is None:
            return
        json_report["semantic"] = run_semantic_pass(ctx, filtered_files, json_report)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("semantic pass failed (advisory, ignored): %s", exc)
        json_report["semantic"] = {"advisory": True, "error": str(exc)}
# @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-attach-semantic


def _generate_spec_coverage_report(args, meta, project_root: Path) -> tuple[dict, int]:
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-validate-systems
    system_slugs, validation_error = _validate_selected_systems(args, meta)
    if validation_error is not None:
        return validation_error, 2
    if system_slugs == set():
        return {}, 2
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-validate-systems
    collected_files, files_excluded = _collect_selected_system_files(
        meta, project_root, system_slugs
    )
    filtered_files = _filter_ignored_files(collected_files, project_root, meta)
    # @cpt-begin:cpt-studio-state-spec-coverage-report:p1:inst-state-uncovered
    if not filtered_files:
        requested = _requested_thresholds(args)
        json_report = _empty_coverage_result(
            _count_selected_codebase_entries(meta, system_slugs), requested)
        # --semantic still attaches its (empty) advisory section here, so the flag's presence
        # is consistent whether or not the codebase resolved to any files.
        _attach_semantic_section(args, filtered_files, json_report)
        return json_report, 2 if requested else 0
    # @cpt-end:cpt-studio-state-spec-coverage-report:p1:inst-state-uncovered
    report = calculate_metrics(_scan_file_coverages(filtered_files))
    json_report = generate_report(report, verbose=args.verbose, project_root=project_root)
    # The population this percentage is computed over, so a shift in it is
    # attributable rather than looking like a change in the code.
    json_report["summary"]["files_excluded"] = files_excluded
    status = _apply_thresholds(report, args, project_root, json_report)
    _attach_semantic_section(args, filtered_files, json_report)
    # @cpt-begin:cpt-studio-state-spec-coverage-report:p1:inst-state-covered
    if status == "PASS" and report.covered_lines > 0:
        return json_report, 0
    # @cpt-end:cpt-studio-state-spec-coverage-report:p1:inst-state-covered
    # @cpt-begin:cpt-studio-state-spec-coverage-report:p1:inst-state-partial
    if report.covered_lines > 0:
        return json_report, 2
    # @cpt-end:cpt-studio-state-spec-coverage-report:p1:inst-state-partial
    return json_report, 0 if status == "PASS" else 2


# @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-user-spec-coverage
def cmd_spec_coverage(argv: List[str]) -> int:
    """Run spec coverage analysis on registered codebase files."""
    args = _build_spec_coverage_parser().parse_args(argv)

    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-load-context
    context = _load_spec_coverage_context()
    if context is None:
        return 1
    meta, project_root = context
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-load-context
    json_report, exit_code = _generate_spec_coverage_report(args, meta, project_root)

    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-return-report
    # Telemetry: authoritative final coverage verdict (the report's own status, so an
    # input error isn't recorded as a coverage FAIL), correlated via the run's id.
    decision_log.record_validation(
        "spec-coverage", json_report.get("status") or ("FAIL" if exit_code else "PASS"))
    _output(json_report, args)
    return exit_code
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-return-report
# @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-user-spec-coverage


def _rel_path(p: str, project_root: Path) -> str:
    """Return path relative to project_root, or original if not possible."""
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-rel-path
    try:
        return Path(p).resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError as exc:
        _warn_spec_coverage(f"path {p} is outside project root {project_root}: {exc}")
        return p
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-rel-path


def _output(data: dict, args: argparse.Namespace) -> None:
    """Output report to stdout (JSON or human) or file."""
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-output-report
    if getattr(args, "output", None):
        text = json.dumps(data, indent=2, ensure_ascii=False)
        Path(args.output).write_text(text, encoding="utf-8")
        return
    ui.result(data, human_fn=_human_spec_coverage)
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-output-report


def _format_ranges(ranges: list) -> str:
    """Format [[start, end], ...] as 'start-end, start-end, ...'."""
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-human-report-helpers
    parts = []
    for r in ranges:
        if isinstance(r, (list, tuple)) and len(r) == 2:
            s, e = r
            parts.append(str(s) if s == e else f"{s}-{e}")
    return ", ".join(parts)
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-human-report-helpers


def _show_spec_coverage_files(files: dict) -> None:
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-human-report-helpers
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
    _show_whole_file_claims(files)
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-human-report-helpers


def _show_whole_file_claims(files: dict) -> None:
    """Name the files whose coverage rests on a whole-file scope marker.

    These are counted as covered but carry no instruction block, so they raise
    the coverage percentage without being traced to anything. Some are
    structurally unmarkable -- an entry point, a re-export module -- and some are
    implementations that were never traced, and the two are indistinguishable
    from the summary line alone. Listing them by size puts the largest claims in
    front of the reader instead of leaving them inside an average.
    """
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-human-report-claims
    claims = {
        path: entry for path, entry in files.items()
        if entry.get("scope_only") and entry.get("covered_lines", 0)
    }
    if not claims:
        return
    lines_claimed = sum(entry.get("total_lines", 0) for entry in claims.values())
    ui.blank()
    ui.step(f"Whole-file scope claims ({len(claims)} files, {lines_claimed} lines, no instruction tracing)")
    for path, entry in sorted(claims.items(), key=lambda kv: -kv[1].get("total_lines", 0)):
        ui.substep(f"  {path}  ({entry.get('total_lines', 0)} lines)")
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-human-report-claims


def _show_spec_coverage_status(status: str, failures: list, assessed: bool = True) -> None:
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-human-report-helpers
    if failures:
        ui.blank()
        for failure in failures:
            ui.warn(failure)
    if status == "PASS":
        if assessed:
            ui.success("All thresholds met.")
    elif status == "FAIL":
        ui.error("Threshold check failed.")
    else:
        ui.info(f"Status: {status}")
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-human-report-helpers


def _human_spec_coverage(data: dict) -> None:
    # @cpt-begin:cpt-studio-flow-spec-coverage-report:p1:inst-human-report-helpers
    status = data.get("status", "")
    unknown_systems = data.get("unknown_systems", [])
    ui.header("Spec Coverage")
    if unknown_systems:
        ui.error(data.get("message", "Unknown system selector(s)"))
        for slug in unknown_systems:
            ui.substep(f"  unknown system: {slug}")
        ui.blank()
        return

    # Say up front when nothing was assessed, so the zeroes below are read as the
    # denominator they are and not as a measured result.
    applicable = data.get("applicable", True)
    if applicable is False:
        ui.warn(data.get("message", "Nothing was assessed"))
        ui.blank()

    summary = data.get("summary", {})
    files_line = f"{summary.get('covered_files', 0)}/{summary.get('total_files', 0)} covered"
    excluded = summary.get("files_excluded") or 0
    ui.detail("Files", f"{files_line} ({excluded} excluded)" if excluded else files_line)
    ui.detail("Coverage", f"{summary.get('coverage_pct', 0):.1f}%")
    ui.detail("Granularity", f"{summary.get('granularity_score', 0):.4f}")

    # Advisory semantic line — never part of the gate; only shown when --semantic ran.
    semantic = data.get("semantic")
    if semantic and semantic.get("error"):
        # The advisory pass recorded a failure (possibly an import failure of semantic_coverage
        # itself) — render it WITHOUT importing summary_line, which could re-raise here, after the
        # structural status/exit are already set.
        ui.info(f"semantic (advisory, never gates): pass errored, skipped — {semantic['error']}")
    elif semantic:
        from ..utils.semantic_coverage import summary_line
        ui.info(summary_line(semantic))

    # Per-file details — files is a dict {path: entry_dict}
    files = data.get("files", {})
    if files and isinstance(files, dict):
        ui.blank()
        _show_spec_coverage_files(files)

    failures = data.get("threshold_failures", [])
    _show_spec_coverage_status(status, failures, assessed=applicable is not False)
    ui.blank()
    # @cpt-end:cpt-studio-flow-spec-coverage-report:p1:inst-human-report-helpers
