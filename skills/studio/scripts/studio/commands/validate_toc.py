"""
Studio validate-toc command — validate Table of Contents in Markdown files.

Checks that TOC exists, anchors point to real headings, all headings are
covered, and the TOC is not stale.  Thin CLI wrapper around
``studio.utils.toc.validate_toc``.

Inside a Studio project the run is governed by the same severity policy
``cfs validate`` uses, and each registered artifact is checked to the depth
its own kind configures.  Outside one, nothing is loaded and the command
behaves exactly as it always has.

@cpt-flow:cpt-studio-flow-traceability-validation-validate:p1
@cpt-dod:cpt-studio-dod-traceability-validation-structure:p1
"""

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-imports
import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..utils import error_codes as EC
from ..utils.constraints import TocOptions
from ..utils.severity import SeverityPolicy, apply_policy, declared_overrides, run_verdict
from ..utils.toc import (
    DEFAULT_MAX_SECTION_LINES,
    DEFAULT_TOC_MAX_LEVEL,
    add_toc_max_level_argument,
    toc_max_section_lines,
    validate_toc,
)
from ..utils.ui import ui
from .validate import (
    _build_severity_policy,
    _emit_policy_config_error,
    _show_severity_overrides,
)
# @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-imports


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-load-project
@dataclass(frozen=True)
class _TocTarget:
    """One registered artifact, as this command needs to see it."""

    kind: str
    options: TocOptions
    #: The kind's `toc` switch. False means the kind has no TOC contract at
    #: all, which `cfs validate` honours by skipping the phase entirely.
    enabled: bool = True


@dataclass
class _TocProject:
    """What a surrounding Studio project contributes to the run.

    Absent (``None`` at the call sites below) when the command runs outside a
    project, which is the case this command has always served and must keep
    serving unchanged: no configuration to read, no kinds to map to.
    """

    policy: SeverityPolicy
    targets: Dict[str, _TocTarget]
    root: Path


def _path_key(path: Path) -> str:
    """The lookup key for one absolute path.

    Case-folded through `os.path.normcase`, which is identity on POSIX and
    lowercases on Windows. `Path.resolve()` does not correct the case of a
    path typed differently from the file on disk, so on a case-insensitive
    filesystem a plain string comparison misses and the file is silently
    treated as unregistered — losing its kind, its configured depth and its
    kind-scoped severity with nothing said.
    """
    return os.path.normcase(str(path))


def _artifact_abs_path(ctx: object, artifact_meta: object) -> Optional[Path]:
    """Resolve one registered artifact to the absolute path the CLI would see."""
    from ..utils.context import WorkspaceContext

    project_root = ctx.project_root
    if isinstance(ctx, WorkspaceContext):
        resolved = ctx.resolve_artifact_path(artifact_meta, project_root)
    else:
        resolved = project_root / artifact_meta.path
    return Path(resolved).resolve() if resolved is not None else None


def _collect_toc_targets(ctx: object) -> Dict[str, _TocTarget]:
    """Index every registered artifact by absolute path, with its kind's options.

    Indexed by path rather than looked up per file because the answer this
    command needs is the reverse of the registry's: it is handed paths and must
    find the kind, and a path may be spelled several ways on the command line
    while only one of them is what the registry resolves to.
    """
    targets: Dict[str, _TocTarget] = {}
    for artifact_meta, system_node in ctx.meta.iter_all_artifacts():
        artifact_path = _artifact_abs_path(ctx, artifact_meta)
        if artifact_path is None:
            continue
        kind = str(artifact_meta.kind)
        loaded_kit = (getattr(ctx, "kits", None) or {}).get(str(system_node.kit))
        by_kind = getattr(getattr(loaded_kit, "constraints", None), "by_kind", None) or {}
        # `by_kind` is keyed by the upper-cased kind the loader normalised to,
        # while the registry stores the kind as the author spelled it. Every
        # other kind boundary in the policy folds the case; not folding it here
        # would silently drop a kind's whole TOC configuration for a registry
        # that spelled `prd` in lower case, while its severities kept working.
        kind_constraints = by_kind.get(kind.strip().upper())
        targets[_path_key(artifact_path)] = _TocTarget(
            kind=kind,
            options=getattr(kind_constraints, "toc_options", None) or TocOptions(),
            enabled=bool(getattr(kind_constraints, "toc", True)),
        )
    return targets


def _load_toc_project(args: argparse.Namespace) -> Tuple[Optional[_TocProject], Optional[int]]:
    """Load the surrounding project's severity policy and artifact kinds.

    A configuration that cannot be read stops the run rather than being
    skipped: continuing would report a verdict under a policy that was never
    in force, and the direction people configure most often is a *raise*, so
    the silent outcome is the one that looks clean and is not.
    """
    from ..utils.context import get_context

    ctx = get_context()
    if ctx is None:
        return None, None
    # The one builder `validate` uses, so a project cannot have its severity
    # read one way by one command and another way by the next.
    policy, policy_errors = _build_severity_policy(ctx, ctx.project_root, args)
    if policy_errors:
        return None, _emit_policy_config_error(policy_errors)
    return _TocProject(
        policy=policy,
        targets=_collect_toc_targets(ctx),
        root=Path(ctx.project_root).resolve(),
    ), None


def resolve_toc_targets() -> Dict[str, _TocTarget]:
    """Index the surrounding project's artifacts, or return nothing outside one.

    Exists so `cfs toc` can regenerate a TOC to the same depth the checks will
    judge it at. It deliberately does not build a severity policy: regenerating
    a table of contents is not a verdict, and a project whose `[validation]`
    table cannot be read should not lose the command that fixes documents.
    """
    from ..utils.context import get_context

    ctx = get_context()
    if ctx is None:
        return {}
    return _collect_toc_targets(ctx)


@dataclass(frozen=True)
class TocResolution:
    """What a per-file TOC command needs to know about one path.

    ``checked`` is False when the file's artifact kind declares ``toc =
    false``. That switch says the kind has no table-of-contents *contract* —
    it is a two-state field defaulting to true, so unlike the three-state
    `multiple` / `numbered` / `task` fields it has no way to express
    "prohibited" and does not try to. A caller asked to write a table should
    still write one; a caller about to judge one should not.
    """

    max_level: int
    max_section_lines: int = DEFAULT_MAX_SECTION_LINES
    kind: Optional[str] = None
    checked: bool = True


def resolve_toc(
    targets: Dict[str, _TocTarget],
    path: Path,
    flag: Optional[int],
) -> TocResolution:
    """Settle a file's TOC bounds, and whether anything validates it.

    Both bounds, not just the depth. A caller that checks its own output at
    one section size while `validate-toc` checks it at another disagrees with
    the validator for the same reason generating at the wrong depth did.
    """
    target = targets.get(_path_key(path))
    options = target.options if target is not None else TocOptions()
    return TocResolution(
        max_level=_resolve_toc_option(flag, options.max_level, DEFAULT_TOC_MAX_LEVEL),
        max_section_lines=_resolve_toc_option(
            None, options.max_section_lines, DEFAULT_MAX_SECTION_LINES),
        kind=target.kind if target is not None else None,
        checked=target.enabled if target is not None else True,
    )
# @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-load-project


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-resolve-options
def _resolve_toc_option(
    flag_value: Optional[int],
    configured: Optional[int],
    fallback: int,
) -> int:
    """Settle one TOC bound: an explicit flag, else the kind's, else the default.

    The flag wins because it is the more specific statement of the two and the
    one a reader can see in the command they just typed. It can only be told
    from silence because its argparse default is ``None``.
    """
    if flag_value is not None:
        return flag_value
    if configured is not None:
        return configured
    return fallback
# @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-resolve-options


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-apply-policy
def _settle_file_findings(
    project: Optional[_TocProject],
    kind: Optional[str],
    errors: List[dict],
    warnings: List[dict],
) -> Tuple[List[dict], List[dict], int]:
    """Re-partition one file's findings at their configured severity.

    Outside a project there is no policy and the two lists are returned as the
    validator built them, so the command's long-standing behaviour survives
    untouched rather than travelling through a policy that configures nothing.

    `outcome.refusals` is deliberately dropped. A refusal only arises where a
    `locked` constraint entry blocks a lowering, and no TOC finding names an
    entry — they carry neither a heading id nor an ID kind — so the list is
    empty by construction here. Carrying it anyway would be plumbing no test
    could ever exercise, standing in for a guarantee this command cannot make.
    """
    if project is None:
        return errors, warnings, 0
    if kind:
        # Recorded on the finding, not just used for resolution: a reader of
        # the JSON otherwise cannot tell which kind's policy settled it.
        for finding in list(errors) + list(warnings):
            finding.setdefault("artifact_kind", kind)
    outcome = apply_policy(project.policy, list(errors) + list(warnings), kind=kind)
    return outcome.errors, outcome.warnings, outcome.suppressed
# @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-apply-policy


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-validate-one
def _validate_one_file(
    filepath: Path,
    args: argparse.Namespace,
    project: Optional[_TocProject] = None,
) -> dict:
    """Validate a single file, returning its result dict. Never raises --
    a missing file or a read failure (permission denied, binary/non-UTF-8
    content, a TOCTOU race) is reported as an ERROR result instead, so one
    bad file in a batch can't abort validation of the rest.
    """
    if not filepath.is_file():
        return {
            "file": str(filepath),
            "status": "ERROR",
            "message": "File not found",
            "code": EC.FILE_LOAD_ERROR,
        }

    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {
            "file": str(filepath),
            "status": "ERROR",
            "message": f"Could not read file: {exc}",
            "code": EC.FILE_READ_ERROR,
        }

    target = project.targets.get(_path_key(filepath)) if project is not None else None
    if target is not None and not target.enabled:
        return _not_applicable_result(filepath, target)
    options = target.options if target is not None else TocOptions()
    report = validate_toc(
        content,
        artifact_path=filepath,
        max_heading_level=_resolve_toc_option(
            args.max_level, options.max_level, DEFAULT_TOC_MAX_LEVEL),
        max_section_lines=_resolve_toc_option(
            args.max_section_lines, options.max_section_lines, DEFAULT_MAX_SECTION_LINES),
    )
    kind = target.kind if target is not None else None
    errors, warnings, suppressed = _settle_file_findings(
        _policy_for(project, target, filepath),
        kind,
        report.get("errors", []),
        report.get("warnings", []),
    )
    return _build_file_result(filepath, args, project, kind, errors, warnings, suppressed)


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-not-applicable
def _not_applicable_result(filepath: Path, target: _TocTarget) -> dict:
    """Report a kind that declared it has no table of contents.

    `cfs validate` skips the whole TOC phase for `toc = false`, so running the
    checks here would report findings for a contract the kit says does not
    exist. Said out loud rather than passed in silence: a file reported as
    clean and a file never examined are different answers, and `applicable`
    is the field this codebase already uses to tell them apart.
    """
    return {
        "file": str(filepath),
        "status": "PASS",
        "applicable": False,
        "artifact_kind": target.kind,
        "error_count": 0,
        "warning_count": 0,
        "message": f"{target.kind} declares toc = false; no table of contents is expected",
    }
# @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-not-applicable


def _policy_for(
    project: Optional[_TocProject],
    target: Optional[_TocTarget],
    filepath: Path,
) -> Optional[_TocProject]:
    """Decide whether this project's policy governs this particular file.

    A registered artifact always belongs to the project, wherever on disk it
    resolves — workspace sources live outside the project root by design. An
    *unregistered* file outside the tree does not: judging someone else's
    document by the severity of whichever project the shell happened to be in
    is an answer about the wrong configuration, and a silent one.
    """
    if project is None or target is not None:
        return project
    root = _path_key(project.root)
    candidate = _path_key(filepath)
    inside = candidate == root or candidate.startswith(root.rstrip(os.sep) + os.sep)
    return project if inside else None


def _build_file_result(
    filepath: Path,
    args: argparse.Namespace,
    project: Optional[_TocProject],
    kind: Optional[str],
    errors: List[dict],
    warnings: List[dict],
    suppressed: int,
) -> dict:
    """Assemble one file's entry in the report."""
    # Per-file status is decided by the same rule as the run's. Leaving it out
    # of `--fail-on-warnings` would report every file as WARN under an overall
    # FAIL, so a reader scanning the list could not find the file that failed.
    file_verdict = run_verdict(
        len(errors),
        len(warnings),
        fail_on_warnings=_fail_on_warnings(args, project),
        warn_status="WARN",
    )
    file_result: dict = {
        "file": str(filepath),
        "status": file_verdict.status,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
    if kind:
        file_result["artifact_kind"] = kind
    if suppressed:
        file_result["suppressed_count"] = suppressed
    if file_verdict.failed_on:
        file_result["failed_on"] = file_verdict.failed_on
    if args.verbose or errors:
        file_result["errors"] = errors
    if args.verbose or warnings:
        file_result["warnings"] = warnings
    return file_result
# @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-validate-one


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-fail-on-warnings
def _fail_on_warnings(args: argparse.Namespace, project: Optional[_TocProject]) -> bool:
    """Whether warnings fail this run — the flag, or the project's setting.

    The flag is already folded into the policy when a project is loaded, so
    asking the policy answers both at once and there is no second place for
    the two sources to disagree.
    """
    if project is not None:
        return project.policy.fail_on_warnings
    return bool(getattr(args, "fail_on_warnings", False))
# @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-fail-on-warnings


def cmd_validate_toc(argv: List[str]) -> int:
    """Validate Table of Contents in markdown files."""
    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-parse-args
    p = argparse.ArgumentParser(
        prog="cfs validate-toc",
        description=(
            "Validate Table of Contents in Markdown files. Run inside a Studio "
            "project, each registered artifact is checked at its kind's configured "
            "depth and every finding is reported at its configured severity; an "
            "explicit flag below overrides both."
        ),
    )
    p.add_argument(
        "files",
        nargs="+",
        help="Markdown file path(s) to validate",
    )
    add_toc_max_level_argument(p, default=None)
    p.add_argument(
        "--max-section-lines",
        type=toc_max_section_lines,
        default=None,
        help=(
            "Warn when a section exceeds this many lines (default: the artifact "
            f"kind's configured size, else {DEFAULT_MAX_SECTION_LINES})"
        ),
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Include full error details in output",
    )
    p.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Fail the run when there are warnings but no errors (exit 2)",
    )
    args = p.parse_args(argv)
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-parse-args

    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-load-project
    project, config_error = _load_toc_project(args)
    if config_error is not None:
        return config_error
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-load-project

    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-resolve-files
    files_to_validate = [Path(f).resolve() for f in args.files]
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-resolve-files

    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-foreach-file
    results = [_validate_one_file(filepath, args, project) for filepath in files_to_validate]
    total_errors = 0
    total_warnings = 0
    total_suppressed = 0
    for file_result in results:
        total_suppressed += int(file_result.get("suppressed_count") or 0)
        if file_result["status"] == "ERROR":
            total_errors += 1
        else:
            total_errors += file_result["error_count"]
            total_warnings += file_result["warning_count"]
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-foreach-file

    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-return
    # The same verdict helper the other two commands use. `validate-toc` keeps
    # its third status: it is the one command whose WARN nothing keys off, and
    # `--fail-on-warnings` reaches it through the same parameter rather than
    # through a second copy of the rule.
    verdict = run_verdict(
        total_errors,
        total_warnings,
        fail_on_warnings=_fail_on_warnings(args, project),
        warn_status="WARN",
    )

    output: dict = {
        "status": verdict.status,
        "files_validated": len(results),
        "error_count": total_errors,
        "warning_count": total_warnings,
        "results": results,
    }
    if verdict.failed_on:
        output["failed_on"] = verdict.failed_on
    _attach_toc_policy_report(output, project, total_suppressed)

    ui.result(output, human_fn=_human_validate_toc)

    return verdict.exit_code
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-return


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-policy-report
def _attach_toc_policy_report(
    output: dict,
    project: Optional[_TocProject],
    suppressed: int,
) -> None:
    """Name what the policy changed, without waiting to be asked.

    The reader who most needs to know a TOC rule was switched off is the one
    who does not know to ask, and a run whose every finding was suppressed is
    otherwise indistinguishable from a run that found nothing.
    """
    if suppressed:
        output["suppressed_count"] = suppressed
    if project is None:
        return
    # Configuration-derived, which is the whole list for this command: a rule
    # lowered to `off` emits nothing at all, and that is exactly the setting a
    # reader most needs named.
    overrides = declared_overrides(project.policy)
    if overrides:
        output["severity_overrides"] = overrides
# @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-policy-report


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-format
def _human_validate_toc_file(r: dict) -> None:
    """Render one file's line in the human report."""
    path = r.get("file", "?")
    status = r.get("status", "?")
    warns = r.get("warning_count", 0)
    if r.get("applicable") is False:
        # Not "unchanged": a file nobody checked must not read like a clean one.
        ui.substep(f"{path}: skipped — {r.get('message', 'not applicable')}")
        return
    if status == "PASS":
        ui.file_action(path, "unchanged")
        _show_file_policy_note(r)
        return
    if status == "ERROR":
        ui.error(f"{path}: {r.get('message', 'unknown error')}")
        return
    if status not in ("FAIL", "WARN"):
        ui.substep(f"{path}: {status}")
        return
    if status == "FAIL" and not r.get("failed_on"):
        ui.warn(f"{path}: {r.get('error_count', 0)} error(s), {warns} warning(s)")
    else:
        ui.warn(f"{path}: {warns} warning(s)")
    _show_file_policy_note(r)
    for e in r.get("errors", []):
        ui.substep(f"  ✗ {e}")
    for w in r.get("warnings", []):
        ui.substep(f"  ⚠ {w}")


def _show_file_policy_note(r: dict) -> None:
    """Attribute this file's kind and its own suppressions, when there are any.

    The run-level suppressed count cannot say *which* file was quietened, so
    over several files a terminal reader could see that something was
    suppressed and have no way to find out where.
    """
    kind = r.get("artifact_kind")
    suppressed = int(r.get("suppressed_count") or 0)
    if not kind and not suppressed:
        return
    note = f"kind {kind}" if kind else "no registered kind"
    if suppressed:
        note += f", {suppressed} finding(s) suppressed"
    ui.substep(f"  ({note})")


def _human_validate_toc_summary(data: dict) -> None:
    """Render the run's closing line."""
    overall = data.get("status", "")
    n = data.get("files_validated", 0)
    if overall == "PASS":
        ui.success(f"{n} file(s) validated, all TOCs correct.")
    elif overall == "FAIL" and data.get("failed_on") == "warnings":
        # Without this the reader of a `--fail-on-warnings` run is told
        # "0 error(s) found" by a run that just failed, and is given no reason.
        ui.error(
            f"{n} file(s) validated, {data.get('warning_count', 0)} warning(s) "
            "— failing because --fail-on-warnings is set."
        )
    elif overall == "FAIL":
        ui.error(f"{n} file(s) validated, {data.get('error_count', 0)} error(s) found.")
    else:
        ui.warn(f"{n} file(s) validated ({overall}).")


def _human_validate_toc(data: dict) -> None:
    ui.header("Validate TOC")
    for r in data.get("results", []):
        _human_validate_toc_file(r)
    _human_validate_toc_summary(data)
    suppressed = int(data.get("suppressed_count") or 0)
    if suppressed:
        # At a terminal a run with rules switched off otherwise reads exactly
        # like a run with none, and `--explain-severity` only reaches the
        # reader who already suspects something was suppressed.
        ui.detail("Suppressed", f"{suppressed} finding(s) at severity off")
    _show_severity_overrides(data.get("severity_overrides", []))
    ui.blank()
# @cpt-end:cpt-studio-algo-traceability-validation-validate-toc:p1:inst-toc-format
