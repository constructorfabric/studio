"""
Studio TOC Command — Generate Table of Contents for Markdown files.

Thin CLI wrapper around the unified ``studio.utils.toc`` module.

@cpt-flow:cpt-studio-flow-developer-experience-toc:p1
"""

# @cpt-begin:cpt-studio-flow-developer-experience-toc:p1:inst-toc-gen-imports
import argparse
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from studio.utils.toc import (
    add_toc_max_level_argument,
    process_file as _process_file,
    validate_toc as _validate_toc,
)
from ..utils.severity import RunVerdict, SeverityPolicy, apply_policy, run_verdict
from ..utils.ui import ui

if TYPE_CHECKING:  # pragma: no cover - for the annotation only
    # Imported lazily inside `cmd_toc` at runtime: `cfs toc` should not pull
    # the whole validate command tree in just to resolve a heading depth.
    from .validate_toc import TocResolution
# @cpt-end:cpt-studio-flow-developer-experience-toc:p1:inst-toc-gen-imports


def _process_toc_file(
    filepath_str: str,
    *,
    max_level: int,
    dry_run: bool,
    indent_size: int,
) -> dict:
    # @cpt-begin:cpt-studio-flow-developer-experience-toc:p1:inst-toc-gen-process
    filepath = Path(filepath_str).resolve()
    return _process_file(
        filepath,
        max_level=max_level,
        dry_run=dry_run,
        indent_size=indent_size,
    )
    # @cpt-end:cpt-studio-flow-developer-experience-toc:p1:inst-toc-gen-process

# @cpt-begin:cpt-studio-flow-developer-experience-toc:p1:inst-toc-gen-validate
def _post_generation_validation(
    filepath: Path,
    resolution: "TocResolution",
    policy: "Optional[SeverityPolicy]" = None,
) -> dict:
    """Check what was just written — unless nothing validates this kind's TOC.

    Graded through the project's severity policy, like every other TOC check.
    The question this answers is "will the validators accept what I wrote",
    and that is the graded verdict, not the raw one: reporting a rule the
    project switched off would describe a failure that is not going to happen.

    A kind declaring `toc = false` is skipped by `cfs validate` and reported
    as not applicable by `cfs validate-toc`. Writing the table is still the
    right answer to an explicit request — that switch says a table is not
    required, and has no way to say one is forbidden — but this command should
    not be the only one in the toolchain that judges it.

    Never raises, matching the contract `validate-toc` states for its own
    read: the file has just been written, so a failure here is a permission
    change, an unmount or a TOCTOU race, and none of those are a reason to
    abort a batch and discard the results already collected for other files.
    """
    if not resolution.checked:
        return {
            "status": "SKIPPED",
            "reason": (
                f"{resolution.kind} declares toc = false; "
                "no command validates a table of contents for this kind"
            ),
        }
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # Not PASS. The table was written and then could not be read back, so
        # this run has no idea whether what it produced is correct — and a
        # verdict of "fine" on a check that never ran is the one answer that
        # cannot be right.
        return {"status": "ERROR", "message": f"Could not re-read the file to validate it: {exc}"}
    report = _validate_toc(
        content,
        artifact_path=filepath,
        max_heading_level=resolution.max_level,
        max_section_lines=resolution.max_section_lines,
    )
    outcome = apply_policy(
        policy,
        list(report.get("errors", [])) + list(report.get("warnings", [])),
        kind=resolution.kind,
    )
    errs, warns = outcome.errors, outcome.warnings
    result: dict = {"status": "PASS"} if not errs and not warns else {
        "status": "FAIL" if errs else "WARN",
        "errors": len(errs),
        "warnings": len(warns),
        "details": errs + warns,
    }
    if outcome.suppressed:
        result["suppressed"] = outcome.suppressed
    return result


def _unverified_count(validation: dict) -> int:
    """How much this file contributes to the run's failure count.

    A check that could not run counts as one, rather than as zero. Exiting 0
    after writing a file nobody could read back would report success for a
    result this command never saw.
    """
    if validation.get("status") == "ERROR":
        return 1
    return int(validation.get("errors") or 0)
# @cpt-end:cpt-studio-flow-developer-experience-toc:p1:inst-toc-gen-validate


def _generate_and_check(
    filepath_str: str,
    args: argparse.Namespace,
    toc_targets: dict,
    policy: Optional[SeverityPolicy],
) -> "tuple[dict, int, int]":
    """Regenerate one file, then check what was written.

    Returns the result plus how much it contributes to the run's error and
    warning counts, so the caller stays a loop over files rather than a
    second copy of the validation rules.
    """
    from .validate_toc import resolve_toc

    filepath = Path(filepath_str).resolve()
    resolution = resolve_toc(toc_targets, filepath, args.max_level)
    result = _process_toc_file(
        filepath_str,
        max_level=resolution.max_level,
        dry_run=args.dry_run,
        indent_size=args.indent,
    )
    # Auto-validate after generation (unless skipped or dry-run)
    if (args.skip_validate
            or args.dry_run
            or not filepath.is_file()
            or result.get("status") in ("ERROR", "SKIP")):
        return result, 0, 0
    validation = _post_generation_validation(filepath, resolution, policy)
    result["validation"] = validation
    return result, _unverified_count(validation), int(validation.get("warnings") or 0)


# @cpt-begin:cpt-studio-flow-developer-experience-toc:p1:inst-toc-gen-foreach-file
def _run_over_files(
    args: argparse.Namespace,
    toc_targets: dict,
    policy: Optional[SeverityPolicy],
) -> "tuple[List[dict], int, int]":
    """Regenerate and check every requested file, totalling what they found."""
    results: List[dict] = []
    validation_errors = 0
    validation_warnings = 0
    for filepath_str in args.files:
        result, errs, warns = _generate_and_check(filepath_str, args, toc_targets, policy)
        validation_errors += errs
        validation_warnings += warns
        results.append(result)
    return results, validation_errors, validation_warnings
# @cpt-end:cpt-studio-flow-developer-experience-toc:p1:inst-toc-gen-foreach-file


# @cpt-begin:cpt-studio-flow-developer-experience-toc:p1:inst-toc-gen-parse-args
def _build_toc_parser() -> argparse.ArgumentParser:
    """The `cfs toc` argument surface."""
    p = argparse.ArgumentParser(
        prog="cfs toc",
        description="Generate or update Table of Contents in Markdown files",
    )
    p.add_argument(
        "files",
        nargs="+",
        help="Markdown file path(s) to process",
    )
    add_toc_max_level_argument(p, default=None)
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indent spaces per nesting level (default: 2)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files",
    )
    p.add_argument(
        "--skip-validate",
        action="store_true",
        help="Skip post-generation validation",
    )
    return p
# @cpt-end:cpt-studio-flow-developer-experience-toc:p1:inst-toc-gen-parse-args


def cmd_toc(argv: List[str]) -> int:
    """Generate/update Table of Contents in markdown files."""
    args = _build_toc_parser().parse_args(argv)

    # @cpt-begin:cpt-studio-flow-developer-experience-toc:p1:inst-toc-gen-kind-depth
    # Generate to the depth the checks will judge the result at. Regenerating
    # at this command's own default in a project where a kind configures a
    # shallower one produces a TOC listing headings that `validate-toc` then
    # reports as anchors to nothing — the documented way to fix a stale TOC
    # would hand back a file that fails validation.
    from .validate_toc import resolve_toc_project_lenient

    project, policy_errors = resolve_toc_project_lenient()
    toc_targets = project.targets if project is not None else {}
    policy = project.policy if project is not None else None
    # @cpt-end:cpt-studio-flow-developer-experience-toc:p1:inst-toc-gen-kind-depth

    results, validation_errors, validation_warnings = _run_over_files(args, toc_targets, policy)

    # @cpt-begin:cpt-studio-flow-developer-experience-toc:p1:inst-toc-gen-return
    # The shared verdict helper the validators use. Having adopted the
    # project's severity, this command adopts the rule the project stated
    # about warnings too — honouring one half of a policy and not the other
    # is the inconsistency that reading the policy at all was meant to end.
    verdict = run_verdict(
        validation_errors,
        validation_warnings,
        fail_on_warnings=bool(policy is not None and policy.fail_on_warnings),
    )
    output = _toc_output(results, validation_warnings, policy_errors, verdict)
    ui.result(output, human_fn=_human_toc)

    if verdict.exit_code:
        return verdict.exit_code
    # @cpt-end:cpt-studio-flow-developer-experience-toc:p1:inst-toc-gen-return
    return 1 if output["status"] == "ERROR" else 0


def _toc_output(
    results: List[dict],
    validation_warnings: int,
    policy_errors: List[str],
    verdict: RunVerdict,
) -> dict:
    """Assemble the run's report and settle its overall status."""
    output: dict = {
        "status": "OK",
        "files_processed": len(results),
        "results": results,
    }
    if validation_warnings:
        output["warning_count"] = validation_warnings
    if policy_errors:
        # Generation went ahead unguided by the policy rather than being
        # refused, so the reader is told which is which.
        output["policy_errors"] = policy_errors
    if verdict.failed_on:
        output["failed_on"] = verdict.failed_on

    if verdict.exit_code == 2:
        output["status"] = "VALIDATION_FAIL"
    elif any(r["status"] == "ERROR" for r in results):
        output["status"] = "PARTIAL" if len(results) > 1 else "ERROR"
    elif validation_warnings:
        # Not "OK". The renderer has just listed these warnings line by line;
        # closing with an unqualified success contradicts what it printed.
        output["status"] = "VALIDATION_WARN"
    return output

# @cpt-begin:cpt-studio-flow-developer-experience-toc:p1:inst-toc-gen-format
def _human_toc_file(r: dict) -> None:
    """Render what happened to one file."""
    path = r.get("file", "?")
    status = r.get("status", "?")
    if status == "UPDATED":
        ui.file_action(path, "updated")
    elif status == "CREATED":
        ui.file_action(path, "created")
    elif status == "UNCHANGED":
        ui.file_action(path, "unchanged")
    elif status == "ERROR":
        ui.warn(f"{path}: {r.get('message', 'error')}")
    else:
        ui.substep(f"{path}: {status}")
    _human_toc_validation(r.get("validation", {}))


def _human_toc_validation(val: dict) -> None:
    """Render the post-generation check, including the case where it did not run."""
    status = val.get("status")
    if status == "SKIPPED":
        ui.substep(f"  (not validated: {val.get('reason', 'not applicable')})")
    elif status == "ERROR":
        ui.error(f"  {val.get('message', 'could not validate the generated file')}")
    elif status in ("FAIL", "WARN"):
        # WARN carries `details` exactly as FAIL does. Rendering only FAIL
        # meant a warning-only result was built, returned, counted in the
        # JSON — and then shown to a terminal reader as nothing at all.
        for detail in val.get("details", []):
            ui.warn(f"  {detail}")


def _human_toc_summary(data: dict) -> None:
    """Render the run's closing line."""
    n = data.get("files_processed", 0)
    overall = data.get("status", "")
    if overall in ("OK", "PASS"):
        ui.success(f"{n} file(s) processed.")
    elif data.get("failed_on") == "warnings":
        # Otherwise a run that failed on warnings is told "validation errors
        # found" and given no reason, having reported zero errors.
        ui.error(
            f"{n} file(s) processed, {data.get('warning_count', 0)} warning(s) "
            "— failing because the project sets fail_on_warnings."
        )
    elif overall == "VALIDATION_FAIL":
        ui.error(f"{n} file(s) processed, validation errors found.")
    elif overall == "VALIDATION_WARN":
        ui.warn(f"{n} file(s) processed, {data.get('warning_count', 0)} warning(s).")
    else:
        ui.warn(f"{n} file(s) processed ({overall}).")
    for message in data.get("policy_errors", []):
        ui.warn(f"  severity configuration ignored: {message}")


def _human_toc(data: dict) -> None:
    ui.header("Table of Contents")
    for r in data.get("results", []):
        _human_toc_file(r)
    _human_toc_summary(data)
    ui.blank()
# @cpt-end:cpt-studio-flow-developer-experience-toc:p1:inst-toc-gen-format
