"""
Studio validate-toc command — validate Table of Contents in Markdown files.

Checks that TOC exists, anchors point to real headings, all headings are
covered, and the TOC is not stale.  Thin CLI wrapper around
``studio.utils.toc.validate_toc``.

@cpt-flow:cpt-studio-flow-traceability-validation-validate:p1
@cpt-dod:cpt-studio-dod-traceability-validation-structure:p1
"""

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-imports
import argparse
import fnmatch
import logging
from pathlib import Path
from typing import List, Optional

from ._validation_config import add_ignore_argument, load_current_validation_config
from ..utils.toc import add_toc_max_level_argument, validate_toc
from ..utils.ui import ui
# @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-imports

_DIAGNOSTIC_LOGGER = logging.getLogger(f"{__name__}.diagnostics")
_DIAGNOSTIC_LOGGER.addHandler(logging.NullHandler())
_DIAGNOSTIC_LOGGER.propagate = False


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-parse-args
def _build_validate_toc_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cfs validate-toc",
        description="Validate Table of Contents in Markdown files",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Markdown file path(s) to validate",
    )
    add_toc_max_level_argument(parser)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include full error details in output",
    )
    add_ignore_argument(parser, "Glob pattern of files to skip. Can be repeated.")
    parser.add_argument(
        "--no-require-toc",
        action="store_true",
        help="Do not fail when a document has headings but no TOC.",
    )
    parser.add_argument(
        "--min-headings",
        type=int,
        default=None,
        metavar="N",
        help="Only require a TOC when a document has at least N headings.",
    )
    return parser
# @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-parse-args


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-resolve-files
def _resolve_validate_toc_policy(args) -> tuple[bool, int, List[str]]:
    config_require_toc = _read_config_require_toc()
    config_min_headings = _read_config_toc_min_headings()
    ignore_patterns = list(args.ignore)
    ignore_patterns.extend(_read_config_toc_ignore_patterns())
    require_toc = False if args.no_require_toc else (
        config_require_toc if config_require_toc is not None else True
    )
    min_headings = args.min_headings if args.min_headings is not None else (
        config_min_headings if config_min_headings is not None else 1
    )
    return require_toc, min_headings, ignore_patterns
# @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-resolve-files


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-foreach-file
def _validate_toc_file(filepath: Path, *, max_level: int, require_toc: bool, min_headings: int) -> dict:
    content = filepath.read_text(encoding="utf-8")
    report = validate_toc(
        content,
        artifact_path=filepath,
        max_heading_level=max_level,
        require_toc=require_toc,
        min_toc_headings=min_headings,
    )
    errors = report.get("errors", [])
    warnings = report.get("warnings", [])
    file_result: dict = {
        "file": str(filepath),
        "status": "FAIL" if errors else ("WARN" if warnings else "PASS"),
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
    return file_result | {"errors": errors, "warnings": warnings}
# @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-foreach-file

def cmd_validate_toc(argv: List[str]) -> int:  # pylint: disable=too-many-locals
    """Validate Table of Contents in markdown files."""
    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-parse-args
    parser = _build_validate_toc_parser()
    args = parser.parse_args(argv)
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-parse-args

    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-resolve-files
    results = []
    total_errors = 0
    total_warnings = 0
    files_to_validate = [Path(f).resolve() for f in args.files]
    try:
        require_toc, min_headings, ignore_patterns = _resolve_validate_toc_policy(args)
    except ValueError as exc:  # pylint: disable=user-facing-error-without-log
        _DIAGNOSTIC_LOGGER.warning("validate-toc config load failed: %s", exc, exc_info=True)
        ui.result({"status": "ERROR", "message": str(exc)})
        return 1
    if min_headings < 1:
        ui.result({"status": "ERROR", "message": "--min-headings must be >= 1"})
        return 1
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-resolve-files

    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-foreach-file
    for filepath in files_to_validate:
        if any(fnmatch.fnmatch(str(filepath), pattern) for pattern in ignore_patterns):
            results.append({
                "file": str(filepath),
                "status": "SKIP",
                "message": "Skipped by ignore pattern",
            })
            continue

        if not filepath.is_file():
            results.append({
                "file": str(filepath),
                "status": "ERROR",
                "message": "File not found",
            })
            total_errors += 1
            continue

        file_result = _validate_toc_file(
            filepath,
            max_level=args.max_level,
            require_toc=require_toc,
            min_headings=min_headings,
        )
        errors = file_result["errors"]
        warnings = file_result["warnings"]
        total_errors += len(errors)
        total_warnings += len(warnings)

        if args.verbose or errors:
            file_result["errors"] = errors
        if args.verbose or warnings:
            file_result["warnings"] = warnings

        results.append(file_result)
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-foreach-file

    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-return
    overall = "PASS"
    if total_errors:
        overall = "FAIL"
    elif total_warnings:
        overall = "WARN"

    output = {
        "status": overall,
        "files_validated": len(results),
        "error_count": total_errors,
        "warning_count": total_warnings,
        "results": results,
    }

    ui.result(output, human_fn=_human_validate_toc)

    if total_errors:
        return 2
    return 0
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-return

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-format
def _human_validate_toc(data: dict) -> None:
    ui.header("Validate TOC")
    for r in data.get("results", []):
        path = r.get("file", "?")
        status = r.get("status", "?")
        errs = r.get("error_count", 0)
        warns = r.get("warning_count", 0)
        if status == "PASS":
            ui.file_action(path, "unchanged")
        elif status == "FAIL":
            ui.warn(f"{path}: {errs} error(s), {warns} warning(s)")
            for e in r.get("errors", []):
                ui.substep(f"  ✗ {e}")
            for w in r.get("warnings", []):
                ui.substep(f"  ⚠ {w}")
        else:
            ui.substep(f"{path}: {status}")
    overall = data.get("status", "")
    n = data.get("files_validated", 0)
    if overall == "PASS":
        ui.success(f"{n} file(s) validated, all TOCs correct.")
    elif overall == "FAIL":
        ui.error(f"{n} file(s) validated, {data.get('error_count', 0)} error(s) found.")
    else:
        ui.warn(f"{n} file(s) validated ({overall}).")
    ui.blank()
# @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-format


def _read_validation_config():
    return load_current_validation_config()


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-resolve-files
def _read_config_require_toc() -> Optional[bool]:
    validation = _read_validation_config()
    if validation is None:
        return None
    return getattr(validation, "require_toc", None)


def _read_config_toc_min_headings() -> Optional[int]:
    validation = _read_validation_config()
    if validation is None:
        return None
    return getattr(validation, "toc_min_headings", None)


def _read_config_toc_ignore_patterns() -> List[str]:
    validation = _read_validation_config()
    if validation is None:
        return []
    patterns = getattr(validation, "toc_ignore_paths", None)
    return list(patterns) if patterns else []
# @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-resolve-files
