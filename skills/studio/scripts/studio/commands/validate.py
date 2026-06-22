"""Validate Studio traceability artifacts and code references."""

# @cpt-begin:cpt-studio-flow-traceability-validation-validate:p1:inst-validate-imports
import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..utils import error_codes as EC
from ..utils.codebase import CodeFile, cross_validate_code
from ..utils.constraints import (
    ArtifactRecord,
    cross_validate_artifacts,
    error as constraints_error,
    validate_artifact_file,
)
from ..utils.document import scan_cdsl_instructions, scan_cpt_ids
from ..utils.fixing import enrich_issues
from ..utils.ui import ui
# @cpt-end:cpt-studio-flow-traceability-validation-validate:p1:inst-validate-imports


@dataclass
class _ValidateSession:
    """Mutable validation session state shared across helper phases."""

    args: argparse.Namespace
    ctx: object
    ws_ctx: Optional[object]
    meta: object
    project_root: Path
    registered_systems: Set[str]
    known_kinds: Set[str]
    ctx_errors: List[Dict[str, object]]
    artifacts_to_validate: List[Tuple[Path, Path, str, str, str]] = field(default_factory=list)


@dataclass
class _ValidateResults:
    """Aggregated validation outputs shared across phases."""

    all_errors: List[Dict[str, object]] = field(default_factory=list)
    all_warnings: List[Dict[str, object]] = field(default_factory=list)
    artifact_reports: List[Dict[str, object]] = field(default_factory=list)
    artifact_report_by_path: Dict[str, Dict[str, object]] = field(default_factory=dict)
    artifact_records: List[ArtifactRecord] = field(default_factory=list)
    code_files_scanned: List[Dict[str, object]] = field(default_factory=list)
    parsed_code_files_full: List[CodeFile] = field(default_factory=list)
    code_ids_found: Set[str] = field(default_factory=set)
    to_code_ids: Set[str] = field(default_factory=set)

# @cpt-begin:cpt-studio-algo-workspace-determine-target:p1:inst-validate-source-flag
def _resolve_source_context(source_name: str, ws_ctx: Optional["WorkspaceContext"]) -> Optional["StudioContext"]:
    """Resolve a workspace source name to its adapter StudioContext.

    Returns the adapter context on success, or None after emitting an error.
    """
    from ..utils.context import WorkspaceContext, resolve_adapter_context

    if ws_ctx is None:
        ui.result({"status": "ERROR", "message": "--source requires a workspace context. Run 'workspace-init' first."})
        return None
    sc = ws_ctx.sources.get(source_name)
    if sc is None:
        ui.result({"status": "ERROR", "message": f"Source '{source_name}' not found in workspace"})
        return None
    if not sc.reachable:
        ui.result({"status": "ERROR", "message": f"Source '{source_name}' is not reachable"})
        return None
    adapter_ctx = resolve_adapter_context(sc)
    if adapter_ctx is None:
        ui.result({"status": "ERROR", "message": f"Cannot resolve adapter context for source '{source_name}'"})
        return None
    return adapter_ctx
# @cpt-end:cpt-studio-algo-workspace-determine-target:p1:inst-validate-source-flag


# @cpt-dod:cpt-studio-dod-workspace-cross-repo:p1
def _collect_cross_repo_artifacts(
    ws_ctx: "WorkspaceContext",
    already_seen: Set[str],
) -> List[ArtifactRecord]:
    """Collect artifacts from remote workspace sources for cross-reference context.

    Remote artifacts are NOT validated themselves — only used so that
    cross-references FROM validated (local) artifacts can be resolved.
    """
    from ..utils.context import get_expanded_meta as _get_expanded_meta

    result: List[ArtifactRecord] = []
    seen = set(already_seen)
    for sc in ws_ctx.sources.values():
        if not sc.reachable or sc.meta is None or sc.path is None or sc.role not in ("artifacts", "full"):
            continue
        expanded = _get_expanded_meta(sc)
        if expanded is None:
            continue
        for art, _sys in expanded.iter_all_artifacts():
            art_path = (sc.path / art.path).resolve()
            if not art_path.exists() or str(art_path) in seen:
                continue
            seen.add(str(art_path))
            result.append(ArtifactRecord(
                path=art_path,
                artifact_kind=str(art.kind),
                constraints=None,
            ))
    return result


# @cpt-begin:cpt-studio-flow-traceability-validation-validate:p1:inst-if-code
def _collect_artifact_code_expectations(
    artifacts: List[ArtifactRecord],
    traceability_by_path: Dict[str, str],
    registered_systems: Optional[Set[str]] = None,
) -> Tuple[Set[str], Set[str], Set[str]]:
    """Collect artifact IDs and to-code expectations for strict validation."""
    artifact_ids: Set[str] = set()
    to_code_ids: Set[str] = set()
    to_code_ids_task_unchecked: Set[str] = set()
    for art in artifacts:
        art_traceability = traceability_by_path.get(str(art.path), "FULL")
        for hit in scan_cpt_ids(art.path):
            if hit.get("type") != "definition" or not hit.get("id"):
                continue
            did = str(hit["id"])
            artifact_ids.add(did)
            if art_traceability != "FULL":
                continue
            constraints_for_kind = getattr(art, "constraints", None)
            if constraints_for_kind is None:
                continue
            for id_constraint in getattr(constraints_for_kind, "defined_id", []) or []:
                kind = str(getattr(id_constraint, "kind", "") or "").strip().lower()
                if (
                    not kind
                    or not _cpt_definition_matches_kind(did, kind, registered_systems)
                    or not bool(getattr(id_constraint, "to_code", False))
                ):
                    continue
                if bool(hit.get("has_task", False)) and not bool(hit.get("checked", False)):
                    to_code_ids_task_unchecked.add(did)
                else:
                    to_code_ids_task_unchecked.discard(did)
                    to_code_ids.add(did)
                break
    return artifact_ids, to_code_ids, to_code_ids_task_unchecked


def _cpt_definition_matches_kind(
    cpt_id: str,
    kind: str,
    registered_systems: Optional[Set[str]] = None,
) -> bool:
    """Return whether a CPT definition ID has *kind* in its structural kind slot."""
    normalized_id = cpt_id.strip().lower()
    normalized_kind = kind.strip().lower()
    if not normalized_id.startswith("cpt-") or not normalized_kind:
        return False

    for system_name in sorted(registered_systems or set(), key=len, reverse=True):
        prefix = f"cpt-{system_name.lower()}-"
        if normalized_id.startswith(prefix):
            remainder = normalized_id[len(prefix):]
            return remainder.split("-", 1)[0] == normalized_kind

    parts = normalized_id.split("-")
    return len(parts) >= 3 and parts[2] == normalized_kind


def _collect_full_artifact_instances(
    artifacts: List[ArtifactRecord],
    traceability_by_path: Dict[str, str],
) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """Collect checked and all CDSL instruction instances from FULL artifacts."""
    artifact_instances: Dict[str, Set[str]] = {}
    artifact_instances_all: Dict[str, Set[str]] = {}
    for art in artifacts:
        art_traceability = traceability_by_path.get(str(art.path), "FULL")
        if art_traceability != "FULL":
            continue
        try:
            steps = scan_cdsl_instructions(art.path)
        except (OSError, ValueError):
            continue
        for step in steps:
            pid = str(step.get("parent_id") or "")
            inst = str(step.get("inst") or "")
            if not pid or not inst:
                continue
            artifact_instances_all.setdefault(pid, set()).add(inst)
            if bool(step.get("checked", False)):
                artifact_instances.setdefault(pid, set()).add(inst)
    return artifact_instances, artifact_instances_all
# @cpt-end:cpt-studio-flow-traceability-validation-validate:p1:inst-if-code


def _parse_validate_args(argv: List[str]) -> argparse.Namespace:
    """Parse CLI args for the validate command."""
    parser = argparse.ArgumentParser(
        prog="validate",
        description=(
            "Validate Constructor Studio artifacts and code traceability "
            "(structure + cross-references + traceability)"
        ),
    )
    parser.add_argument(
        "--artifact",
        default=None,
        help=(
            "Path to specific Constructor Studio artifact "
            "(if omitted, validates all registered artifacts)"
        ),
    )
    parser.add_argument("--skip-code", action="store_true", help="Skip code traceability validation")
    parser.add_argument("--verbose", action="store_true", help="Print full validation report")
    parser.add_argument("--output", default=None, help="Write report to file instead of stdout")
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Skip cross-repo workspace validation (validate local repo only)",
    )
    parser.add_argument(
        "--source",
        default=None,
        help=(
            "Target a specific workspace source for validation "
            "(uses that source's adapter context)"
        ),
    )
    return parser.parse_args(argv)


def _extend_known_kinds(ctx: object, known_kinds: Set[str]) -> None:
    """Merge kit-defined ID kinds into the known-kinds set."""
    from ..utils.context import collect_known_id_kinds

    known_kinds.update(collect_known_id_kinds(ctx))


def _run_validate_kits_gate(project_root: Path, ctx: object, verbose: bool) -> Optional[int]:
    """Run validate-kits fail-fast gate when kits are present."""
    meta = getattr(ctx, "meta", None)
    if not getattr(meta, "kits", None):
        return None
    try:
        from .validate_kits import run_validate_kits

        rc, report = run_validate_kits(
            project_root=project_root,
            adapter_dir=ctx.adapter_dir,
            kit_filter=None,
            verbose=bool(verbose),
        )
    except (OSError, ValueError, KeyError) as exc:
        ui.result({
            "status": "ERROR",
            "message": "self-check failed to run",
            "error": str(exc),
        })
        return 1
    if not rc and str(report.get("status")) == "PASS":
        return None
    ui.result({
        "status": "FAIL" if rc == 2 else "ERROR",
        "message": "validate-kits failed (kit structure or templates are inconsistent)",
        "validate_kits": report,
    })
    return 2 if rc == 2 else 1


def _build_validate_session(args: argparse.Namespace) -> Tuple[Optional[_ValidateSession], Optional[int]]:
    """Load context, workspace state, and static validation metadata."""
    from ..utils.context import WorkspaceContext, get_context

    ctx = get_context()
    if not ctx:
        ui.result({"status": "ERROR", "message": "Constructor Studio not initialized. Run 'cfs init' first."})
        return None, 1

    ws_ctx = ctx if isinstance(ctx, WorkspaceContext) else None
    if args.source:
        ctx = _resolve_source_context(args.source, ws_ctx)
        if ctx is None:
            return None, 1

    ctx_errors = list(getattr(ctx, "_errors", []) or [])
    if ws_ctx is not None:
        from ..utils.workspace import find_workspace_config as _find_ws

        workspace_config, _ = _find_ws(ws_ctx.project_root)
        if workspace_config is not None:
            for ws_err in workspace_config.validate():
                ctx_errors.append(constraints_error("workspace", ws_err, path=str(workspace_config.workspace_file)))

    project_root = ctx.project_root
    gate_code = _run_validate_kits_gate(project_root, ctx, bool(args.verbose))
    if gate_code is not None:
        return None, gate_code

    known_kinds = ctx.get_known_id_kinds()
    _extend_known_kinds(ctx, known_kinds)
    return _ValidateSession(
        args=args,
        ctx=ctx,
        ws_ctx=ws_ctx,
        meta=ctx.meta,
        project_root=project_root,
        registered_systems=ctx.registered_systems,
        known_kinds=known_kinds,
        ctx_errors=ctx_errors,
    ), None


def _emit_validate_output(data: Dict[str, object], *, output_path: Optional[str], human: bool, pretty: bool) -> None:
    """Emit validate output to stdout or a JSON file."""
    if output_path:
        text = json.dumps(data, indent=2 if pretty else None, ensure_ascii=False)
        if pretty:
            text += "\n"
        Path(output_path).write_text(text, encoding="utf-8")
        return
    ui.result(data, human_fn=_human_validate if human else None)


def _emit_no_artifacts_result(session: _ValidateSession) -> int:
    """Emit the empty-registry result, preserving context load errors."""
    if session.ctx_errors:
        enrich_issues(session.ctx_errors, project_root=session.project_root)
        ui.result({
            "status": "FAIL",
            "project_root": session.project_root.as_posix(),
            "artifacts_validated": 0,
            "error_count": len(session.ctx_errors),
            "warning_count": 0,
            "errors": session.ctx_errors,
        }, human_fn=_human_validate)
        return 2
    ui.result({
        "status": "PASS",
        "artifacts_validated": 0,
        "error_count": 0,
        "warning_count": 0,
        "message": "No artifacts found in registry",
    })
    return 0


def _append_registered_artifact(
    session: _ValidateSession,
    artifact_path: Path,
    artifact_meta: object,
    system_node: object,
) -> None:
    """Append one resolved registry artifact to the validation target list."""
    pkg = session.meta.get_kit(system_node.kit)
    if not pkg or not pkg.is_cfs_format():
        return
    template_path = (session.project_root / pkg.get_template_path(artifact_meta.kind)).resolve()
    session.artifacts_to_validate.append((
        artifact_path,
        template_path,
        artifact_meta.kind,
        artifact_meta.traceability,
        system_node.kit,
    ))


def _resolve_explicit_artifact(session: _ValidateSession, artifact_path: Path) -> Optional[int]:
    """Resolve one explicit artifact path against the registry and active context."""
    from ..utils.context import StudioContext, determine_target_source

    if not artifact_path.exists():
        ui.result({"status": "ERROR", "message": f"Artifact not found: {artifact_path}"})
        return 1

    if session.ws_ctx is not None:
        matched_sc, matched_ctx = determine_target_source(artifact_path, session.ws_ctx)
        if matched_ctx is None:
            ui.result({"status": "ERROR", "message": f"Cannot resolve context for artifact: {artifact_path}"})
            return 1
        if session.args.source and matched_sc is not None and matched_sc.name != session.args.source:
            ui.result({"status": "ERROR", "message": (
                f"Artifact '{session.args.artifact}' belongs to source '{matched_sc.name}', "
                f"not '{session.args.source}'."
            )})
            return 1
        session.ctx = matched_ctx
    else:
        session.ctx = StudioContext.load(artifact_path.parent)
        if not session.ctx:
            ui.result({"status": "ERROR", "message": "Constructor Studio not initialized"})
            return 1

    session.ctx_errors.extend(getattr(session.ctx, "_errors", []) or [])
    session.meta = session.ctx.meta
    session.project_root = session.ctx.project_root
    session.registered_systems = session.ctx.registered_systems
    session.known_kinds = session.ctx.get_known_id_kinds()
    _extend_known_kinds(session.ctx, session.known_kinds)
    try:
        rel_path = artifact_path.relative_to(session.project_root).as_posix()
    except ValueError:
        rel_path = None
    result = session.meta.get_artifact_by_path(rel_path) if rel_path else None
    if result is None:
        ui.result({"status": "ERROR", "message": f"Artifact not in registry: {session.args.artifact}"})
        return 1
    artifact_meta, system_node = result
    _append_registered_artifact(session, artifact_path, artifact_meta, system_node)
    return None


def _collect_all_registered_artifacts(session: _ValidateSession) -> None:
    """Resolve all registered artifacts for the active context."""
    for artifact_meta, system_node in session.meta.iter_all_artifacts():
        if session.ws_ctx is not None:
            artifact_path = session.ws_ctx.resolve_artifact_path(artifact_meta, session.project_root)
        else:
            artifact_path = (session.project_root / artifact_meta.path).resolve()
        if artifact_path is None or not artifact_path.exists():
            continue
        _append_registered_artifact(session, artifact_path, artifact_meta, system_node)


def _resolve_artifacts_to_validate(session: _ValidateSession) -> Optional[int]:
    """Populate the validation target list from args or registry state."""
    if session.args.artifact:
        exit_code = _resolve_explicit_artifact(session, Path(session.args.artifact).resolve())
        if exit_code is not None:
            return exit_code
    else:
        _collect_all_registered_artifacts(session)
    if session.artifacts_to_validate:
        return None
    return _emit_no_artifacts_result(session)


def _maybe_emit_registry_failure(session: _ValidateSession, results: _ValidateResults) -> Optional[int]:
    """Stop early when registry-level errors make later checks unreliable."""
    if session.ctx_errors:
        results.all_errors.extend(session.ctx_errors)
    if not any(str(issue.get("type", "")) == "registry" for issue in results.all_errors):
        return None
    enrich_issues(results.all_errors, project_root=session.project_root)
    _emit_validate_output({
        "status": "FAIL",
        "project_root": session.project_root.as_posix(),
        "artifact_count": len(session.artifacts_to_validate),
        "error_count": len(results.all_errors),
        "warning_count": 0,
        "errors": results.all_errors,
    }, output_path=session.args.output, human=True, pretty=True)
    return 2


def _resolve_constraints_for_artifact(
    session: _ValidateSession,
    artifact_type: str,
    kit_id: str,
) -> Tuple[object, Optional[Path]]:
    """Resolve artifact-kind constraints and the originating constraints path."""
    from ..utils.context import _resolve_loaded_kit_constraints_path

    constraints_for_kind = None
    loaded_kit = (session.ctx.kits or {}).get(str(kit_id))
    if loaded_kit and loaded_kit.constraints and str(artifact_type) in loaded_kit.constraints.by_kind:
        constraints_for_kind = loaded_kit.constraints.by_kind[str(artifact_type)]
    if not loaded_kit:
        return constraints_for_kind, None
    try:
        adapter_dir = getattr(session.ctx, "adapter_dir", None)
        if not isinstance(adapter_dir, Path):
            adapter_dir = session.project_root
        constraints_path = _resolve_loaded_kit_constraints_path(adapter_dir, session.project_root, loaded_kit)
    except (OSError, ValueError, KeyError):
        constraints_path = None
    return constraints_for_kind, constraints_path


def _validate_one_artifact(
    session: _ValidateSession,
    results: _ValidateResults,
    artifact_entry: Tuple[Path, Path, str, str, str],
) -> None:
    """Run structure validation for one artifact and record its report."""
    artifact_path, _template_path, artifact_type, traceability, kit_id = artifact_entry
    constraints_for_kind, constraints_path = _resolve_constraints_for_artifact(session, artifact_type, kit_id)
    results.artifact_records.append(ArtifactRecord(
        path=artifact_path,
        artifact_kind=str(artifact_type),
        constraints=constraints_for_kind,
    ))
    report = validate_artifact_file(
        artifact_path=artifact_path,
        artifact_kind=str(artifact_type),
        constraints=constraints_for_kind,
        registered_systems=session.registered_systems,
        constraints_path=constraints_path,
        kit_id=str(kit_id),
    )
    errors = report.get("errors", [])
    warnings = report.get("warnings", [])
    artifact_report: Dict[str, object] = {
        "artifact": str(artifact_path),
        "artifact_type": artifact_type,
        "traceability": traceability,
        "status": "PASS" if not errors else "FAIL",
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
    if session.args.verbose or errors:
        artifact_report["errors"] = errors
    if session.args.verbose or warnings:
        artifact_report["warnings"] = warnings
        try:
            hits = scan_cpt_ids(artifact_path)
            artifact_report["id_definitions"] = len([hit for hit in hits if hit.get("type") == "definition"])
            artifact_report["id_references"] = len([hit for hit in hits if hit.get("type") == "reference"])
        except (OSError, ValueError):
            artifact_report["id_definitions"] = 0
            artifact_report["id_references"] = 0
    results.artifact_reports.append(artifact_report)
    results.artifact_report_by_path[str(artifact_path)] = artifact_report
    results.all_errors.extend(errors)
    results.all_warnings.extend(warnings)


def _attach_issue_to_artifact_report(
    issue: Dict[str, object],
    *,
    results: _ValidateResults,
    verbose: bool,
    is_error: bool,
) -> None:
    """Increment per-artifact counters for a later validation issue."""
    report = results.artifact_report_by_path.get(str(issue.get("path", "") or ""))
    if report is None:
        return
    if is_error:
        report["status"] = "FAIL"
        report["error_count"] = int(report.get("error_count", 0) or 0) + 1
        if verbose and isinstance(report.get("errors"), list):
            report["errors"].append(issue)
        return
    report["warning_count"] = int(report.get("warning_count", 0) or 0) + 1
    if verbose and isinstance(report.get("warnings"), list):
        report["warnings"].append(issue)


def _run_initial_artifact_validation(session: _ValidateSession) -> Tuple[_ValidateResults, Optional[int]]:
    """Run per-artifact structure checks and stop on early failures."""
    results = _ValidateResults()
    exit_code = _maybe_emit_registry_failure(session, results)
    if exit_code is not None:
        return results, exit_code
    for artifact_entry in session.artifacts_to_validate:
        _validate_one_artifact(session, results, artifact_entry)
    if not results.all_errors:
        for language_error in _run_content_language_check(session.artifacts_to_validate, session.project_root):
            results.all_errors.append(language_error)
            _attach_issue_to_artifact_report(
                language_error,
                results=results,
                verbose=bool(session.args.verbose),
                is_error=True,
            )
    if not results.all_errors:
        return results, None
    enrich_issues(results.all_errors, project_root=session.project_root)
    enrich_issues(results.all_warnings, project_root=session.project_root)
    out = {
        "status": "FAIL",
        "project_root": session.project_root.as_posix(),
        "artifact_count": len(session.artifacts_to_validate),
        "error_count": len(results.all_errors),
        "warning_count": len(results.all_warnings),
        "errors": results.all_errors,
    }
    if results.all_warnings:
        out["warnings"] = results.all_warnings
    _emit_validate_output(out, output_path=session.args.output, human=True, pretty=True)
    return results, 2


def _build_cross_validation_context(session: _ValidateSession, results: _ValidateResults) -> List[ArtifactRecord]:
    """Load all artifacts needed for cross-reference and code validation context."""
    all_artifacts = list(results.artifact_records)
    validated_paths = {str(path) for path, _, _, _, _ in session.artifacts_to_validate}
    for artifact_meta, system_node in session.meta.iter_all_artifacts():
        if session.ws_ctx is not None:
            artifact_path = session.ws_ctx.resolve_artifact_path(artifact_meta, session.project_root)
        else:
            artifact_path = (session.project_root / artifact_meta.path).resolve()
        if artifact_path is None or not artifact_path.exists() or str(artifact_path) in validated_paths:
            continue
        constraints_for_kind, _ = _resolve_constraints_for_artifact(
            session,
            str(artifact_meta.kind),
            str(system_node.kit),
        )
        all_artifacts.append(ArtifactRecord(
            path=artifact_path,
            artifact_kind=str(artifact_meta.kind),
            constraints=constraints_for_kind,
        ))
    if (
        not session.args.local_only
        and session.ws_ctx is not None
        and session.ws_ctx.cross_repo
        and session.ws_ctx.resolve_remote_ids
    ):
        seen_paths = {str(record.path) for record in all_artifacts}
        all_artifacts.extend(_collect_cross_repo_artifacts(session.ws_ctx, seen_paths))
    return all_artifacts


def _run_cross_validation(
    session: _ValidateSession,
    results: _ValidateResults,
    all_artifacts_for_cross: List[ArtifactRecord],
) -> None:
    """Apply cross-artifact reference validation to the selected artifacts."""
    if not all_artifacts_for_cross:
        return
    validated_paths = {str(path) for path, _, _, _, _ in session.artifacts_to_validate}
    cross_result = cross_validate_artifacts(
        all_artifacts_for_cross,
        registered_systems=session.registered_systems,
        known_kinds=session.known_kinds,
    )
    for issue in cross_result.get("errors", []):
        if issue.get("path", "") not in validated_paths:
            continue
        results.all_errors.append(issue)
        _attach_issue_to_artifact_report(issue, results=results, verbose=bool(session.args.verbose), is_error=True)
    for issue in cross_result.get("warnings", []):
        if issue.get("path", "") not in validated_paths:
            continue
        results.all_warnings.append(issue)
        _attach_issue_to_artifact_report(issue, results=results, verbose=bool(session.args.verbose), is_error=False)


def _scan_codebase_entry(
    *,
    entry: object,
    traceability: str,
    session: _ValidateSession,
    results: _ValidateResults,
    strict_code_validation: bool,
) -> None:
    """Scan one configured codebase entry and collect code traceability state."""
    for file_path in _resolve_code_scan_targets(session, entry):
        try:
            rel_path = file_path.resolve().relative_to(session.project_root).as_posix()
        except ValueError:
            rel_path = None
        if rel_path and session.meta.is_ignored(rel_path):
            continue
        code_file, errors = CodeFile.from_path(file_path)
        if errors or code_file is None:
            if strict_code_validation and errors:
                results.all_errors.extend(errors)
            continue
        if traceability == "FULL":
            results.parsed_code_files_full.append(code_file)
        if strict_code_validation:
            code_report = code_file.validate()
            results.all_errors.extend(code_report.get("errors", []))
            results.all_warnings.extend(code_report.get("warnings", []))
        file_ids = code_file.list_ids()
        results.code_ids_found.update(file_ids)
        if file_ids or code_file.scope_markers or code_file.block_markers:
            results.code_files_scanned.append({
                "path": str(file_path),
                "scope_markers": len(code_file.scope_markers),
                "block_markers": len(code_file.block_markers),
                "ids_referenced": len(file_ids),
            })


def _resolve_code_scan_targets(session: _ValidateSession, entry: object) -> List[Path]:
    """Resolve concrete files for one codebase entry."""
    src_name = getattr(entry, "source", None)
    if src_name and session.ws_ctx is not None:
        code_path = session.ws_ctx.resolve_artifact_path(entry, session.project_root)
    else:
        entry_path = getattr(entry, "path", "") if not isinstance(entry, dict) else entry.get("path", "")
        code_path = (session.project_root / entry_path).resolve()
    if code_path is None or not code_path.exists():
        return []
    if code_path.is_file():
        return [code_path]
    extensions = (
        getattr(entry, "extensions", None)
        if not isinstance(entry, dict)
        else entry.get("extensions", None)
    ) or [".py"]
    return [candidate for ext in extensions for candidate in code_path.rglob(f"*{ext}")]


def _scan_system_codebase(
    system_node: object,
    *,
    session: _ValidateSession,
    results: _ValidateResults,
    strict_code_validation: bool,
) -> None:
    """Recursively scan a system node's configured codebase entries."""
    traceability = "FULL" if any(art.traceability == "FULL" for art in system_node.artifacts) else "DOCS-ONLY"
    for codebase_entry in system_node.codebase:
        _scan_codebase_entry(
            entry=codebase_entry,
            traceability=traceability,
            session=session,
            results=results,
            strict_code_validation=strict_code_validation,
        )
    for child in system_node.children:
        _scan_system_codebase(
            child,
            session=session,
            results=results,
            strict_code_validation=strict_code_validation,
        )


def _run_code_validation(
    session: _ValidateSession,
    results: _ValidateResults,
    all_artifacts_for_cross: List[ArtifactRecord],
) -> None:
    """Run code traceability validation unless disabled by CLI flags."""
    traceability_by_path = _build_traceability_by_path(session.artifacts_to_validate)
    full_ids_to_check = _collect_full_traceability_ids(session.artifacts_to_validate)
    strict_code_validation = not session.args.artifact
    should_scan_code = (not session.args.skip_code) and (strict_code_validation or bool(full_ids_to_check))
    to_code_ids_task_unchecked: Set[str] = set()
    artifact_ids: Set[str] = set()
    if strict_code_validation and all_artifacts_for_cross:
        artifact_ids, results.to_code_ids, to_code_ids_task_unchecked = _collect_artifact_code_expectations(
            all_artifacts_for_cross,
            traceability_by_path,
            session.registered_systems,
        )
    if not session.args.local_only and session.ws_ctx is not None:
        artifact_ids.update(session.ws_ctx.get_all_artifact_ids())
    if not should_scan_code:
        return
    for system_node in session.meta.systems:
        _scan_system_codebase(
            system_node,
            session=session,
            results=results,
            strict_code_validation=strict_code_validation,
        )
    if not strict_code_validation or not results.parsed_code_files_full:
        return
    artifact_instances, artifact_instances_all = _collect_full_artifact_instances(
        all_artifacts_for_cross,
        traceability_by_path,
    )
    code_validation = cross_validate_code(
        results.parsed_code_files_full,
        artifact_ids,
        results.to_code_ids,
        forbidden_code_ids=to_code_ids_task_unchecked,
        traceability="FULL",
        artifact_instances=artifact_instances,
        artifact_instances_all=artifact_instances_all,
    )
    results.all_errors.extend(code_validation.get("errors", []))
    results.all_warnings.extend(code_validation.get("warnings", []))


def _build_traceability_by_path(
    artifacts_to_validate: List[Tuple[Path, Path, str, str, str]],
) -> Dict[str, str]:
    """Build a quick artifact-path to traceability lookup."""
    return {
        str(artifact_path): traceability
        for artifact_path, _template_path, _artifact_type, traceability, _kit_id in artifacts_to_validate
    }


def _collect_full_traceability_ids(
    artifacts_to_validate: List[Tuple[Path, Path, str, str, str]],
) -> Set[str]:
    """Collect definition IDs from FULL-traceability artifacts."""
    full_ids_to_check: Set[str] = set()
    for artifact_path, _template_path, _artifact_kind, traceability, _kit_id in artifacts_to_validate:
        if traceability != "FULL":
            continue
        try:
            for hit in scan_cpt_ids(artifact_path):
                if hit.get("type") == "definition" and hit.get("id"):
                    full_ids_to_check.add(str(hit["id"]))
        except (OSError, ValueError):
            continue
    return full_ids_to_check


def _run_reference_coverage(
    session: _ValidateSession,
    results: _ValidateResults,
    all_artifacts_for_cross: List[ArtifactRecord],
) -> None:
    """Enforce fallback cross-reference coverage for unconstrained artifact kinds."""
    if not all_artifacts_for_cross:
        return
    present_kinds, refs_by_id = _build_reference_index(all_artifacts_for_cross)
    validated_paths = {str(path) for path, _, _, _, _ in session.artifacts_to_validate}
    traceability_by_path = _build_traceability_by_path(session.artifacts_to_validate)
    for artifact in all_artifacts_for_cross:
        _apply_reference_coverage_for_artifact(
            artifact,
            present_kinds=present_kinds,
            refs_by_id=refs_by_id,
            validated_paths=validated_paths,
            traceability_by_path=traceability_by_path,
            code_ids_found=results.code_ids_found,
            results=results,
            verbose=bool(session.args.verbose),
        )


def _build_reference_index(
    all_artifacts_for_cross: List[ArtifactRecord],
) -> Tuple[Set[str], Dict[str, Set[str]]]:
    """Build present-kind and reference indices across all artifacts."""
    present_kinds: Set[str] = set()
    refs_by_id: Dict[str, Set[str]] = {}
    for artifact in all_artifacts_for_cross:
        kind = str(getattr(artifact, "artifact_kind", "") or "")
        present_kinds.add(kind)
        try:
            for hit in scan_cpt_ids(artifact.path):
                if hit.get("type") != "reference":
                    continue
                ref_id = str(hit.get("id") or "").strip()
                if ref_id:
                    refs_by_id.setdefault(ref_id, set()).add(kind)
        except (OSError, ValueError):
            continue
    return present_kinds, refs_by_id


def _apply_reference_coverage_for_artifact(
    artifact: ArtifactRecord,
    *,
    present_kinds: Set[str],
    refs_by_id: Dict[str, Set[str]],
    validated_paths: Set[str],
    traceability_by_path: Dict[str, str],
    code_ids_found: Set[str],
    results: _ValidateResults,
    verbose: bool,
) -> None:
    """Apply fallback coverage rules to one artifact without explicit constraints."""
    artifact_path_str = str(artifact.path)
    if artifact_path_str not in validated_paths or getattr(artifact, "constraints", None) is not None:
        return
    kind = str(getattr(artifact, "artifact_kind", "") or "")
    other_kinds = sorted(candidate for candidate in present_kinds if candidate != kind)
    art_traceability = traceability_by_path.get(artifact_path_str, "FULL")
    try:
        definitions = [hit for hit in scan_cpt_ids(artifact.path) if hit.get("type") == "definition" and hit.get("id")]
    except (OSError, ValueError):
        definitions = []
    for definition in definitions:
        _apply_reference_coverage_for_definition(
            artifact=artifact,
            definition=definition,
            other_kinds=other_kinds,
            refs_by_id=refs_by_id,
            art_traceability=art_traceability,
            code_ids_found=code_ids_found,
            results=results,
            verbose=verbose,
        )


def _apply_reference_coverage_for_definition(
    *,
    artifact: ArtifactRecord,
    definition: Dict[str, object],
    other_kinds: List[str],
    refs_by_id: Dict[str, Set[str]],
    art_traceability: str,
    code_ids_found: Set[str],
    results: _ValidateResults,
    verbose: bool,
) -> None:
    """Apply fallback coverage rules to one definition hit."""
    defined_id = str(definition.get("id") or "").strip()
    if not defined_id:
        return
    line = int(definition.get("line", 1) or 1)
    if not other_kinds:
        warning = constraints_error(
            "structure",
            f"`{defined_id}` is not referenced — no other artifact kinds exist in scope for cross-referencing",
            code=EC.ID_NOT_REFERENCED_NO_SCOPE,
            path=artifact.path,
            line=line,
            id=defined_id,
        )
        results.all_warnings.append(warning)
        _attach_issue_to_artifact_report(warning, results=results, verbose=verbose, is_error=False)
        return
    kind = str(getattr(artifact, "artifact_kind", "") or "")
    referenced_kinds = sorted(candidate for candidate in refs_by_id.get(defined_id, set()) if candidate != kind)
    if referenced_kinds or (art_traceability == "FULL" and defined_id in code_ids_found):
        return
    error = constraints_error(
        "structure",
        f"`{defined_id}` (defined in {kind}) is not referenced from any of {other_kinds}",
        code=EC.ID_NOT_REFERENCED,
        path=artifact.path,
        line=line,
        id=defined_id,
        other_kinds=other_kinds,
    )
    results.all_errors.append(error)
    _attach_issue_to_artifact_report(error, results=results, verbose=verbose, is_error=True)


def _emit_final_validate_report(session: _ValidateSession, results: _ValidateResults) -> int:
    """Enrich issues and emit the final validate report."""
    _enrich_target_artifact_paths(results.all_errors, meta=session.meta, project_root=session.project_root)
    enrich_issues(results.all_errors, project_root=session.project_root)
    enrich_issues(results.all_warnings, project_root=session.project_root)
    overall_status = "PASS" if not results.all_errors else "FAIL"
    report: Dict[str, object] = {
        "status": overall_status,
        "artifacts_validated": len(results.artifact_reports),
        "error_count": len(results.all_errors),
        "warning_count": len(results.all_warnings),
    }
    if not session.args.skip_code and not session.args.artifact:
        report["code_files_scanned"] = len(results.code_files_scanned)
        report["to_code_ids_total"] = len(results.to_code_ids)
        report["code_ids_found"] = len(results.code_ids_found)
        if results.to_code_ids:
            report["coverage"] = f"{len(results.code_ids_found & results.to_code_ids)}/{len(results.to_code_ids)}"
    if overall_status == "PASS":
        report["next_step"] = (
            "Deterministic validation passed. Now perform semantic validation: "
            "review content quality against checklist.md criteria."
        )
    if session.args.verbose:
        report["errors"] = results.all_errors
        report["warnings"] = results.all_warnings
    elif overall_status != "PASS":
        report["errors"] = results.all_errors
        if results.all_warnings:
            report["warnings"] = results.all_warnings
    else:
        failed_artifacts = [item for item in results.artifact_reports if item.get("status") == "FAIL"]
        if failed_artifacts:
            report["failed_artifacts"] = [
                {"artifact": item.get("artifact"), "error_count": item.get("error_count")}
                for item in failed_artifacts
            ]
    _emit_validate_output(
        report,
        output_path=session.args.output,
        human=True,
        pretty=bool(session.args.verbose) or (overall_status != "PASS"),
    )
    return 0 if overall_status == "PASS" else 2


# @cpt-flow:cpt-studio-flow-traceability-validation-validate:p1
# @cpt-dod:cpt-studio-dod-traceability-validation-cross-refs:p1
# @cpt-dod:cpt-studio-dod-traceability-validation-cdsl:p1
def cmd_validate(argv: List[str]) -> int:
    """Validate Constructor Studio artifacts and code traceability.

    Performs deterministic validation checks (structure, cross-references,
    task statuses, traceability markers) and produces a machine-readable report.
    """
    session, exit_code = _build_validate_session(_parse_validate_args(argv))
    if exit_code is not None or session is None:
        return 1 if exit_code is None else exit_code
    exit_code = _resolve_artifacts_to_validate(session)
    if exit_code is not None:
        return exit_code
    results, exit_code = _run_initial_artifact_validation(session)
    if exit_code is not None:
        return exit_code
    all_artifacts_for_cross = _build_cross_validation_context(session, results)
    _run_cross_validation(session, results, all_artifacts_for_cross)
    _run_code_validation(session, results, all_artifacts_for_cross)
    _run_reference_coverage(session, results, all_artifacts_for_cross)
    return _emit_final_validate_report(session, results)

# @cpt-begin:cpt-studio-flow-traceability-validation-validate:p1:inst-validate-helpers
def _enrich_target_artifact_paths(
    issues: List[Dict[str, object]],
    *,
    meta: object,
    project_root: Path,
) -> None:
    """Add ``target_artifact_path`` to 'ID not referenced from required artifact kind' errors.

    Three outcomes per error:
    - ``target_artifact_path`` set  → artifact exists, prompt says "in `path`"
    - ``target_artifact_suggested_path`` set → artifact missing, autodetect knows where → "create `path`"
    - neither set → no autodetect rule → prompt asks LLM to request path from user
    """
    from ..utils.artifacts_meta import ArtifactsMeta

    if not isinstance(meta, ArtifactsMeta):
        return

    for issue in issues:
        if str(issue.get("code") or "") != EC.REF_MISSING_FROM_KIND:
            continue

        target_kind = str(issue.get("target_kind") or "").upper()
        if not target_kind:
            continue

        # Find the system node that owns the source artifact
        src_path = str(issue.get("path") or "")
        try:
            rel_src = Path(src_path).relative_to(project_root).as_posix()
        except (ValueError, TypeError):
            continue

        result = meta.get_artifact_by_path(rel_src)
        if not result:
            continue
        _, system_node = result

        # Search system's artifacts for an existing artifact of target_kind
        target_path = _find_artifact_in_system(system_node, target_kind, project_root)
        if target_path:
            issue["target_artifact_path"] = target_path
            continue

        # No existing artifact — check autodetect rules for suggested path
        suggested = _suggest_path_from_autodetect(system_node, target_kind)
        if suggested:
            issue["target_artifact_suggested_path"] = suggested
        # else: neither set → fixing.py will ask user

def _find_artifact_in_system(node: object, target_kind: str, project_root: Path) -> Optional[str]:
    """Search system node and its children for an existing artifact of target_kind.

    Returns relative path string if found, else None.
    """
    from ..utils.artifacts_meta import SystemNode

    if not isinstance(node, SystemNode):
        return None
    for art in (node.artifacts or []):
        if str(art.kind).upper() == target_kind:
            full = (project_root / art.path).resolve()
            if full.exists():
                return str(full)
    for child in (node.children or []):
        found = _find_artifact_in_system(child, target_kind, project_root)
        if found:
            return found
    return None

def _suggest_path_from_autodetect(node: object, target_kind: str) -> Optional[str]:
    """Derive a suggested file path from autodetect rules for a missing artifact.

    Returns a project-root-relative path like ``architecture/DESIGN.md``, or None.
    """
    from ..utils.artifacts_meta import SystemNode

    if not isinstance(node, SystemNode):
        return None

    for rule in (node.autodetect or []):
        arts = rule.artifacts or {}
        kind_upper = {str(k).upper(): k for k in arts}
        orig_key = kind_upper.get(target_kind)
        if not orig_key:
            continue
        ap = arts[orig_key]
        pattern = str(ap.pattern or "")
        if not pattern:
            continue

        # Compute artifacts_root with simple substitution
        system_root = str(rule.system_root or "{project_root}")
        system_root = system_root.replace("{project_root}", ".")
        system_root = system_root.replace("{system}", node.slug or "")

        arts_root = str(rule.artifacts_root or "{system_root}")
        arts_root = arts_root.replace("{system_root}", system_root)
        arts_root = arts_root.replace("{project_root}", ".")
        arts_root = arts_root.replace("{system}", node.slug or "")

        # If pattern is a simple filename (no glob chars), use it directly
        if "*" not in pattern and "?" not in pattern:
            suggested = f"{arts_root}/{pattern}"
        else:
            # Glob pattern — suggest conventional {KIND}.md
            suggested = f"{arts_root}/{target_kind}.md"

        # Normalize: strip leading "./"
        suggested = suggested.lstrip("./")
        if suggested.startswith("/"):
            suggested = suggested.lstrip("/")
        return suggested

    return None
# @cpt-end:cpt-studio-flow-traceability-validation-validate:p1:inst-validate-helpers

# ---------------------------------------------------------------------------
# Content language check helper
# ---------------------------------------------------------------------------


def _load_language_validation_settings(project_root: "Path") -> Tuple[Optional[List[str]], list]:
    """Load configured allowed content languages and any config-load errors."""
    from ..utils.constraints import error as _error
    from ..utils import error_codes as _EC

    try:
        from ..utils.workspace import find_workspace_config as _find_ws
        ws_cfg, ws_err = _find_ws(project_root)
    except (ImportError, OSError, AttributeError) as exc:
        return None, [_error(
            "language",
            f"Cannot load workspace config for language check: {exc}",
            path=project_root,
            line=1,
            code=_EC.FILE_LOAD_ERROR,
        )]

    if ws_err:
        return None, [_error(
            "language",
            f"Workspace config error, language validation skipped: {ws_err}",
            path=project_root,
            line=1,
            code=_EC.FILE_LOAD_ERROR,
        )]

    validation = getattr(ws_cfg, "validation", None) if ws_cfg is not None else None
    return getattr(validation, "allowed_content_languages", None), []


def _scan_artifact_language_violations(
    artifact_path: Path,
    allowed_langs: List[str],
    allowed_ranges: object,
) -> list:
    """Scan one artifact for language violations."""
    from ..utils.constraints import error as _error
    from ..utils import error_codes as _EC
    from ..utils.content_language import LangScanError as _LangScanError, scan_file as _scan_file

    results = []
    try:
        for violation in _scan_file(artifact_path, allowed_ranges):
            results.append(_error(
                "language",
                f"Non-allowed characters [{violation.bad_chars_preview()}] -- {violation.line_preview()}",
                path=artifact_path,
                line=violation.lineno,
                code=_EC.CONTENT_LANGUAGE_VIOLATION,
                allowed_languages=allowed_langs,
            ))
    except _LangScanError as exc:
        results.append(_error(
            "language",
            f"Cannot read file for language check: {exc.cause}",
            path=artifact_path,
            line=1,
            code=_EC.FILE_READ_ERROR,
        ))
    return results

def _run_content_language_check(
    artifacts_to_validate: list,
    project_root: "Path",
) -> list:
    """Return language-violation error dicts for all validated .md artifacts.

    Uses project_root to discover the workspace config so the check works in
    both workspace mode and single-repo mode.  Returns an empty list when
    allowed_content_languages is not configured.

    Config failures (malformed .cf-workspace.toml) are surfaced as
    FILE_LOAD_ERROR entries rather than silently disabling validation.
    """
    try:
        from ..utils.content_language import build_allowed_ranges
    except ImportError:
        return []

    allowed_langs, config_errors = _load_language_validation_settings(project_root)
    if config_errors:
        return config_errors
    if not allowed_langs:
        return []

    allowed_ranges = build_allowed_ranges(allowed_langs)
    results = []
    for artifact_path, _template_path, _artifact_type, _traceability, _kit_id in artifacts_to_validate:
        if artifact_path.suffix.lower() != ".md":
            continue
        results.extend(_scan_artifact_language_violations(artifact_path, allowed_langs, allowed_ranges))
    return results


# ---------------------------------------------------------------------------
# Human-friendly formatter
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-flow-traceability-validation-validate:p1:inst-validate-format
def _human_validate(data: dict) -> None:
    status = data.get("status", "")
    n_art = data.get("artifacts_validated", data.get("artifact_count", 0))
    n_err = data.get("error_count", 0)
    n_warn = data.get("warning_count", 0)

    ui.header("Validate")
    ui.detail("Artifacts", str(n_art))
    ui.detail("Errors", str(n_err))
    ui.detail("Warnings", str(n_warn))

    if data.get("code_files_scanned") is not None:
        ui.detail("Code files", str(data["code_files_scanned"]))
    if data.get("coverage"):
        ui.detail("Code coverage", str(data["coverage"]))

    errors = data.get("errors", [])
    if errors:
        ui.blank()
        for e in errors[:30]:
            _format_issue(e, is_error=True)
        if len(errors) > 30:
            ui.substep(f"  ... and {len(errors) - 30} more error(s)")

    warnings = data.get("warnings", [])
    if warnings:
        ui.blank()
        for w in warnings[:15]:
            _format_issue(w, is_error=False)
        if len(warnings) > 15:
            ui.substep(f"  ... and {len(warnings) - 15} more warning(s)")

    ui.blank()
    if status == "PASS":
        ui.success("All checks passed.")
        if data.get("next_step"):
            ui.hint(str(data["next_step"]))
    elif status == "FAIL":
        ui.error(f"Validation failed — {n_err} error(s).")
    else:
        ui.info(f"Status: {status}")
    ui.blank()

def _issue_location(issue: dict) -> str:
    """Extract display location from an issue dict, relative to cwd."""
    loc = str(issue.get("location") or "")
    if not loc:
        path = str(issue.get("path") or "")
        line = issue.get("line", "")
        if path:
            loc = f"{path}:{line}" if line else path
    if not loc:
        return ""
    if ":" in loc:
        parts = loc.rsplit(":", 1)
        if parts[1].isdigit():
            return f"{ui.relpath(parts[0])}:{parts[1]}"
    return ui.relpath(loc)


def _emit_issue_header(loc: str, code: str, msg: str, *, is_error: bool) -> None:
    """Emit the main issue heading and message."""
    header_parts = []
    if loc:
        header_parts.append(loc)
    if code:
        header_parts.append(f"[{code}]")

    if header_parts:
        header_text = " ".join(header_parts)
        if is_error:
            ui.warn(header_text)
        else:
            ui.substep(f"  > {header_text}")
        if msg:
            ui.substep(f"    {msg}")
        return

    if is_error:
        ui.warn(msg)
    else:
        ui.substep(f"  > {msg}")


def _emit_issue_extras(issue: dict) -> bool:
    """Emit structured extra fields for an issue."""
    has_extra = False
    reasons = issue.get("reasons")
    if isinstance(reasons, list) and reasons:
        for reason in reasons:
            ui.substep(f"    -> {reason}")
        has_extra = True

    fixing = issue.get("fixing_prompt")
    if fixing:
        ui.substep(f"    Fix: {fixing}")
        has_extra = True

    handled_keys = {
        "type", "message", "code", "line", "path", "location",
        "reasons", "fixing_prompt",
    }
    for key, value in issue.items():
        if key in handled_keys or value is None or not value or value == []:
            continue
        if isinstance(value, list):
            ui.substep(f"    {key}: {', '.join(str(item) for item in value)}")
        else:
            ui.substep(f"    {key}: {value}")
        has_extra = True
    return has_extra


def _format_issue(issue: object, *, is_error: bool) -> None:
    """Format a single error/warning with all available fields.

    Generic: iterates ALL keys in the dict so no information is ever lost.
    Special formatting for known structural keys (location, message, code,
    reasons, fixing_prompt); everything else auto-formatted as key: value.
    """
    if not isinstance(issue, dict):
        if is_error:
            ui.warn(str(issue))
        else:
            ui.substep(f"  \u25b8 {issue}")
        return

    msg = issue.get("message", "")
    code = issue.get("code", "")
    loc = _issue_location(issue)
    _emit_issue_header(loc, str(code), str(msg), is_error=is_error)
    has_extra = _emit_issue_extras(issue)

    if has_extra:
        ui.blank()
# @cpt-end:cpt-studio-flow-traceability-validation-validate:p1:inst-validate-format
