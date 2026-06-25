"""
Validate Kits Command — validate kit structure, templates, and examples.

Kits are direct file packages — validation checks kit directory presence,
conf.toml readability, constraints.toml schema, and template/example
consistency against constraints.
"""

# @cpt-begin:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-imports
import argparse
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple

from ..utils.constraints import error as constraints_error
from ..utils.ui import ui
# @cpt-end:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-imports


@dataclass(frozen=True)
class _PathValidationContext:
    slug: str
    has_model_input: bool
    model: Any
    model_error: Optional[Exception]
    constraints: Any
    constraint_errors: List[Any]
    constraints_error_path: Path

# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
def _constraint_artifact_bindings(loaded_kit: Any) -> Dict[str, Dict[str, str]]:
    """Return explicit artifact-kind bindings declared on constraints resources."""
    entries = getattr(loaded_kit, "resource_entries", None)
    if not isinstance(entries, dict):
        return {}
    artifact_bindings: Dict[str, Dict[str, str]] = {}
    for _resource_id, raw_entry in sorted(entries.items()):
        if not isinstance(raw_entry, dict):
            continue
        if str(raw_entry.get("kind", "") or "").strip().lower() != "constraints":
            continue
        raw_artifacts = raw_entry.get("artifacts")
        if not isinstance(raw_artifacts, dict):
            continue
        for kind, raw_spec in raw_artifacts.items():
            if not isinstance(raw_spec, dict):
                continue
            kind_s = str(kind or "").strip().upper()
            if not kind_s:
                continue
            spec = artifact_bindings.setdefault(kind_s, {})
            for role in ("template", "rules", "checklist", "examples", "example"):
                raw_ref = raw_spec.get(role)
                if isinstance(raw_ref, str) and raw_ref.strip():
                    spec["examples" if role == "example" else role] = raw_ref.strip()
    return artifact_bindings
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
def _constraints_binding_path(loaded_kit: Any, resource_bindings: Dict[str, str]) -> str:
    entries = getattr(loaded_kit, "resource_entries", None)
    if isinstance(entries, dict):
        for resource_id, raw_entry in sorted(entries.items()):
            if not isinstance(raw_entry, dict):
                continue
            if str(raw_entry.get("kind", "") or "").strip().lower() == "constraints":
                path = _resource_binding_path(resource_bindings, str(resource_id))
                if path:
                    return path
    return _resource_binding_path(resource_bindings, "constraints")
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
def _known_constraint_kinds(loaded_kit: Any) -> Set[str]:
    constraints = getattr(loaded_kit, "constraints", None)
    return {
        str(kind).strip().upper()
        for kind in (getattr(constraints, "by_kind", {}) or {}).keys()
        if str(kind).strip()
    }
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map

# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
def _resource_binding_path(resource_bindings: Dict[str, str], resource_id: str) -> str:
    return str(resource_bindings.get(resource_id, "") or "").strip()
# @cpt-end:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
def _missing_bound_artifact_warnings(
    *,
    kit_id: str,
    known_kinds: Set[str],
    artifacts: Dict[str, Dict[str, str]],
) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []
    for kind in sorted(known_kinds):
        spec = artifacts.get(kind, {})
        if str(spec.get("template", "") or "").strip() or str(spec.get("examples", "") or "").strip():
            continue
        warning = constraints_error(
            "template",
            (
                "Constraints declare artifact kind but no manifest resource "
                "binding is available for template/example self-check"
            ),
            path=None,
            line=1,
            kit_id=str(kit_id),
            artifact_kind=kind,
            missing_bindings=["template", "examples"],
        )
        results.append({
            "kit": str(kit_id),
            "kind": kind,
            "example_path": None,
            "example_paths": [],
            "examples_checked": 0,
            "status": "PASS",
            "error_count": 0,
            "warning_count": 1,
            "warnings": [warning],
        })
    return results
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
def _constraints_binding_paths(
    loaded_kit: Any,
    resource_bindings: Dict[str, str],
) -> List[Path]:
    paths: List[Path] = []
    loaded_paths = getattr(loaded_kit, "constraints_paths", None)
    if isinstance(loaded_paths, list):
        for path in loaded_paths:
            if isinstance(path, Path):
                paths.append(path)
            elif isinstance(path, str) and path.strip():
                paths.append(Path(path))

    entries = getattr(loaded_kit, "resource_entries", None)
    if isinstance(entries, dict):
        for resource_id, raw_entry in sorted(entries.items()):
            if not isinstance(raw_entry, dict):
                continue
            if str(raw_entry.get("kind", "") or "").strip().lower() != "constraints":
                continue
            path = _resource_binding_path(resource_bindings, str(resource_id))
            if path:
                paths.append(Path(path))

    fallback = _resource_binding_path(resource_bindings, "constraints")
    if fallback:
        paths.append(Path(fallback))

    unique: List[Path] = []
    seen: Set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
def _synthesized_meta_from_resource_bindings(
    *,
    base_meta: Any,
    adapter_dir: Path,
    kit_id: str,
    loaded_kit: Any,
) -> Tuple[Optional[Any], List[Dict[str, object]]]:
    """Build self-check metadata from loaded manifest resource bindings."""
    from ..utils.artifacts_meta import ArtifactsMeta, Kit

    rb = getattr(loaded_kit, "resource_bindings", None)
    if not isinstance(rb, dict) or not rb:
        return None, []

    artifacts = _bound_artifacts_from_resources(rb, loaded_kit)

    known_kinds = _known_constraint_kinds(loaded_kit)
    for kind in sorted(known_kinds):
        artifacts.setdefault(kind, {})

    warnings = _missing_bound_artifact_warnings(
        kit_id=kit_id,
        known_kinds=known_kinds,
        artifacts=artifacts,
    )
    if not artifacts:
        return None, warnings

    constraints_path = _constraints_binding_path(loaded_kit, rb)
    kit_base = _resolve_bound_kit_base(
        adapter_dir=adapter_dir,
        loaded_kit=loaded_kit,
        constraints_path=constraints_path,
    )

    kit = Kit(
        kit_id=kit_id,
        format="CFS",
        path=str(kit_base),
        artifacts=artifacts,
    )
    constraints_paths = _constraints_binding_paths(loaded_kit, rb)
    if constraints_path:
        setattr(kit, "constraints_path", Path(constraints_path))
    if constraints_paths:
        setattr(kit, "constraints_paths", constraints_paths)

    return ArtifactsMeta(
        version=str(getattr(base_meta, "version", "1.0") or "1.0"),
        project_root=str(getattr(base_meta, "project_root", "..") or ".."),
        kits={kit_id: kit},
        systems=list(getattr(base_meta, "systems", []) or []),
        ignore=list(getattr(base_meta, "ignore", []) or []),
    ), warnings
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
def _bound_artifacts_from_resources(
    resource_bindings: Dict[str, str],
    loaded_kit: Any,
) -> Dict[str, Dict[str, str]]:
    artifact_bindings = _constraint_artifact_bindings(loaded_kit)
    artifacts: Dict[str, Dict[str, str]] = {}
    for kind, binding_spec in sorted(artifact_bindings.items()):
        spec = _bound_artifact_spec(resource_bindings, binding_spec)
        if spec:
            artifacts[kind] = spec
    return artifacts
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
def _bound_artifact_spec(
    resource_bindings: Dict[str, str],
    binding_spec: Dict[str, str],
) -> Dict[str, str]:
    spec: Dict[str, str] = {}
    template = _resource_binding_path(
        resource_bindings,
        str(binding_spec.get("template", "") or ""),
    )
    if template:
        spec["template"] = template
    example_path = _resource_binding_path(
        resource_bindings,
        str(binding_spec.get("examples", "") or ""),
    )
    if example_path:
        spec["examples"] = example_path
    return spec
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
def _resolve_bound_kit_base(
    *,
    adapter_dir: Path,
    loaded_kit: Any,
    constraints_path: str,
) -> Path:
    if constraints_path:
        return Path(constraints_path).parent
    kit_root = getattr(loaded_kit, "kit_root", None)
    return kit_root if isinstance(kit_root, Path) else adapter_dir
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map


# @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-build-artifacts-meta
def _synthesized_meta_from_kit_model(
    *,
    base_meta: Any,
    kit_dir: Path,
    kit_id: str,
    model: Any,
    constraints: Any,
) -> Tuple[Optional[Any], List[Dict[str, object]]]:
    """Build self-check metadata from a standalone canonical KitModel."""
    resource_bindings: Dict[str, str] = {}
    resource_entries: Dict[str, Dict[str, object]] = {}
    constraints_paths: List[Path] = []
    for resource in getattr(model, "resources", []) or []:
        resource_id = str(getattr(resource, "id", "") or "").strip()
        source = str(getattr(resource, "source", "") or "").strip()
        if not resource_id or not source:
            continue
        resource_path = (kit_dir / source).resolve()
        resource_bindings[resource_id] = str(resource_path)
        entry: Dict[str, object] = {
            "kind": str(getattr(resource, "kind", "") or "").strip(),
        }
        if entry["kind"].lower() == "constraints":
            constraints_paths.append(resource_path)
        artifact_bindings = getattr(resource, "artifact_bindings", None)
        if isinstance(artifact_bindings, dict) and artifact_bindings:
            entry["artifacts"] = artifact_bindings
        resource_entries[resource_id] = entry

    loaded_kit = SimpleNamespace(
        resource_bindings=resource_bindings,
        resource_entries=resource_entries,
        constraints=constraints,
        constraints_paths=constraints_paths,
        kit_root=kit_dir,
    )
    return _synthesized_meta_from_resource_bindings(
        base_meta=base_meta,
        adapter_dir=kit_dir.parent,
        kit_id=kit_id,
        loaded_kit=loaded_kit,
    )
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-build-artifacts-meta


def _merge_self_check_report(
    target: Dict[str, object],
    source: Dict[str, object],
) -> None:
    """Merge one self-check report into an aggregate report."""
    # @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-template-check
    if not source:
        return
    target.setdefault("results", [])
    target["templates_checked"] = int(target.get("templates_checked", 0) or 0) + int(
        source.get("templates_checked", 0) or 0
    )
    target["kits_checked"] = int(target.get("kits_checked", 0) or 0) + int(source.get("kits_checked", 0) or 0)
    if source.get("status") == "FAIL":
        target["status"] = "FAIL"
    elif "status" not in target:
        target["status"] = source.get("status", "PASS")
    results = source.get("results", [])
    if isinstance(results, list):
        target["results"].extend(results)  # type: ignore[union-attr]
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-template-check


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-init-context
def _collect_context_kit_errors(
    ctx: Any,
    kit_filter: Optional[str],
) -> Tuple[List[Dict[str, object]], Dict[str, List[Dict[str, object]]]]:
    all_errors: List[Dict[str, object]] = []
    context_kit_errors: Dict[str, List[Dict[str, object]]] = {}
    for err in (getattr(ctx, "_errors", []) or []):
        if not isinstance(err, dict) or err.get("type") not in {"resources", "constraints"}:
            continue
        err_kit = str(err.get("kit", "") or "")
        if kit_filter and err_kit != str(kit_filter):
            continue
        if err_kit:
            context_kit_errors.setdefault(err_kit, []).append(err)
        all_errors.append(err)
    return all_errors, context_kit_errors
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-init-context


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-structural-check
def _append_loaded_kit_reports(
    *,
    ctx: Any,
    kit_filter: Optional[str],
    verbose: bool,
    kit_reports: List[Dict[str, object]],
    kit_reports_by_id: Dict[str, Dict[str, object]],
    kit_errors_by_id: Dict[str, List[Dict[str, object]]],
    context_kit_errors: Dict[str, List[Dict[str, object]]],
) -> None:
    for kit_id, loaded_kit in (ctx.kits or {}).items():
        kit_id_str = str(kit_id)
        if kit_filter and kit_id_str != str(kit_filter):
            continue
        rep = _new_loaded_kit_report(kit_id_str, loaded_kit, verbose)
        rep_errors = list(context_kit_errors.get(kit_id_str, []))
        kit_reports.append(rep)
        kit_reports_by_id[kit_id_str] = rep
        if rep_errors:
            kit_errors_by_id[kit_id_str] = rep_errors
        _sync_kit_report(rep, kit_errors_by_id.get(kit_id_str, []), verbose)
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-structural-check


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-structural-check
def _new_loaded_kit_report(kit_id: str, loaded_kit: Any, verbose: bool) -> Dict[str, object]:
    kit_root = getattr(loaded_kit, "kit_root", None)
    kit_path_value = str(getattr(getattr(loaded_kit, "kit", None), "path", "") or "")
    reported_kit_path = str(kit_root) if isinstance(kit_root, Path) else kit_path_value
    rep: Dict[str, object] = {
        "kit": kit_id,
        "path": reported_kit_path,
        "status": "PASS",
        "error_count": 0,
    }
    constraints = getattr(loaded_kit, "constraints", None)
    if verbose and constraints is not None and getattr(constraints, "by_kind", None):
        rep["kinds"] = sorted(constraints.by_kind.keys())
    return rep
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-structural-check


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-build-result
def _sync_kit_report(rep: Dict[str, object], rep_errors: List[Dict[str, object]], verbose: bool) -> None:
    rep["status"] = "FAIL" if rep_errors else "PASS"
    rep["error_count"] = len(rep_errors)
    if not verbose:
        return
    if rep_errors:
        rep["errors"] = rep_errors
    else:
        rep.pop("errors", None)
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-build-result


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-resolve-resource-paths
def _verify_loaded_kit_resource_paths(
    *,
    ctx: Any,
    kit_filter: Optional[str],
    all_errors: List[Dict[str, object]],
    kit_reports_by_id: Dict[str, Dict[str, object]],
    kit_errors_by_id: Dict[str, List[Dict[str, object]]],
    verbose: bool,
) -> None:
    for kit_id, loaded_kit in (ctx.kits or {}).items():
        kit_id_str = str(kit_id)
        if kit_filter and kit_id_str != str(kit_filter):
            continue
        resource_bindings = getattr(loaded_kit, "resource_bindings", None)
        if not resource_bindings:
            continue
        for err in _missing_resource_binding_errors(kit_id_str, resource_bindings):
            all_errors.append(err)
            kit_errors_by_id.setdefault(kit_id_str, []).append(err)
        rep = kit_reports_by_id.get(kit_id_str)
        if rep is not None:
            _sync_kit_report(rep, kit_errors_by_id.get(kit_id_str, []), verbose)
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-resolve-resource-paths


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-resolve-resource-paths
def _missing_resource_binding_errors(
    kit_id: str,
    resource_bindings: Dict[str, str],
) -> List[Dict[str, object]]:
    errors: List[Dict[str, object]] = []
    for res_id, res_path_str in resource_bindings.items():
        abs_path = Path(res_path_str)
        if abs_path.exists():
            continue
        errors.append(
            constraints_error(
                "resources",
                f"Resource '{res_id}' path not found: {res_path_str}",
                path=str(abs_path),
                line=1,
                kit=kit_id,
            )
        )
    return errors
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-resolve-resource-paths


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-template-check
def _run_registered_self_check(
    *,
    project_root: Path,
    adapter_dir: Path,
    kit_filter: Optional[str],
    verbose: bool,
    ctx: Any,
    artifacts_meta: Any,
) -> Dict[str, object]:
    from .self_check import run_self_check_from_meta

    self_check_report: Dict[str, object] = {}
    manifest_checked_kits: Set[str] = set()
    for kit_id, loaded_kit in (ctx.kits or {}).items():
        kit_id_str = str(kit_id)
        if kit_filter and kit_id_str != str(kit_filter):
            continue
        bound_meta, binding_warnings = _synthesized_meta_from_resource_bindings(
            base_meta=artifacts_meta,
            adapter_dir=adapter_dir,
            kit_id=kit_id_str,
            loaded_kit=loaded_kit,
        )
        _record_binding_warnings(self_check_report, binding_warnings)
        if bound_meta is None:
            continue
        if getattr(loaded_kit, "resource_bindings", None):
            manifest_checked_kits.add(kit_id_str)
        _, sc_out = run_self_check_from_meta(
            project_root=project_root,
            adapter_dir=adapter_dir,
            artifacts_meta=bound_meta,
            kit_filter=kit_id_str,
            verbose=verbose,
        )
        _merge_self_check_report(self_check_report, sc_out)
    for kit_id in (artifacts_meta.kits or {}).keys():
        kit_id_str = str(kit_id)
        if kit_filter and kit_id_str != str(kit_filter):
            continue
        if kit_id_str in manifest_checked_kits:
            continue
        _, sc_out = run_self_check_from_meta(
            project_root=project_root,
            adapter_dir=adapter_dir,
            artifacts_meta=artifacts_meta,
            kit_filter=kit_id_str,
            verbose=verbose,
        )
        _merge_self_check_report(self_check_report, sc_out)
    return self_check_report
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-template-check


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-template-check
def _record_binding_warnings(
    self_check_report: Dict[str, object],
    binding_warnings: List[Dict[str, object]],
) -> None:
    if not binding_warnings:
        return
    self_check_report.setdefault("results", [])
    self_check_report["results"].extend(binding_warnings)  # type: ignore[union-attr]
    self_check_report.setdefault("status", "PASS")
    self_check_report.setdefault("templates_checked", 0)
    self_check_report.setdefault("kits_checked", 0)
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-template-check


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-template-check
def _collect_self_check_failures(
    self_check_report: Dict[str, object],
    all_errors: List[Dict[str, object]],
) -> None:
    def _error_key(err: Dict[str, object]) -> Tuple[str, str, str]:
        err_type = str(err.get("type", "") or "")
        err_path = str(err.get("path", "") or "")
        if err_type == "constraints" and err_path:
            return (err_type, err_path, "")
        return (
            err_type,
            err_path,
            str(err.get("message", "") or ""),
        )

    seen = {
        _error_key(err)
        for err in all_errors
        if isinstance(err, dict)
    }
    for result in self_check_report.get("results", []):
        if isinstance(result, dict) and result.get("status") == "FAIL":
            errors = result.get("errors", [])
            if isinstance(errors, list):
                for err in errors:
                    if not isinstance(err, dict):
                        all_errors.append(err)
                        continue
                    key = _error_key(err)
                    if key in seen:
                        continue
                    seen.add(key)
                    all_errors.append(err)
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-template-check


# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-build-result
# @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-build-result
def _build_validate_kits_result(
    *,
    verbose: bool,
    kit_reports: List[Dict[str, object]],
    all_errors: List[Dict[str, object]],
    self_check_report: Dict[str, object],
) -> Tuple[int, Dict[str, Any]]:
    overall_status = "PASS" if not all_errors else "FAIL"
    result: Dict[str, Any] = {
        "status": overall_status,
        "kits_validated": len(kit_reports),
        "error_count": len(all_errors),
    }
    if self_check_report:
        result["templates_checked"] = self_check_report.get("templates_checked", 0)
        result["self_check_results"] = self_check_report.get("results", [])
    if verbose:
        result["kits"] = kit_reports
        if all_errors:
            result["errors"] = all_errors
    else:
        failed = [r for r in kit_reports if r.get("status") == "FAIL"]
        if failed:
            result["failed_kits"] = [{"kit": r.get("kit"), "error_count": r.get("error_count")} for r in failed]
        if all_errors:
            result["errors"] = all_errors[:10]
            if len(all_errors) > 10:
                result["errors_truncated"] = len(all_errors) - 10
    return (0 if overall_status == "PASS" else 2), result
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-build-result
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-build-result


# @cpt-dod:cpt-studio-dod-kit-validate:p1
# @cpt-algo:cpt-studio-algo-kit-validate:p1
# @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-init-context
def run_validate_kits(
    *,
    project_root: Path,
    adapter_dir: Path,
    kit_filter: Optional[str] = None,
    verbose: bool = False,
    ctx: Optional[Any] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Run full kit validation (structural + template/example checks).

    Returns (return_code, report_dict).  rc=0 means PASS, rc=2 means FAIL.
    This is the reusable engine called by both the CLI and ``cmd_update``.
    """
    from ..utils.context import StudioContext

    if ctx is None:
        ctx = StudioContext.load_from_dir(adapter_dir)
    if not ctx:
        return 1, {"status": "ERROR", "message": "Constructor Studio not initialized. Run 'cfs init' first."}
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-init-context

    # @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-structural-check
    # ── Phase 1: Structural validation ────────────────────────────────
    kit_reports: List[Dict[str, object]] = []
    kit_reports_by_id: Dict[str, Dict[str, object]] = {}
    kit_errors_by_id: Dict[str, List[Dict[str, object]]] = {}
    all_errors, context_kit_errors = _collect_context_kit_errors(ctx, kit_filter)
    _append_loaded_kit_reports(
        ctx=ctx,
        kit_filter=kit_filter,
        verbose=verbose,
        kit_reports=kit_reports,
        kit_reports_by_id=kit_reports_by_id,
        kit_errors_by_id=kit_errors_by_id,
        context_kit_errors=context_kit_errors,
    )
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-structural-check

    # ── Phase 1b: Resource path verification (manifest-driven kits) ───
    _verify_loaded_kit_resource_paths(
        ctx=ctx,
        kit_filter=kit_filter,
        all_errors=all_errors,
        kit_reports_by_id=kit_reports_by_id,
        kit_errors_by_id=kit_errors_by_id,
        verbose=verbose,
    )

    # @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-template-check
    # ── Phase 2: Template & example validation ────────────────────────
    # @cpt-begin:cpt-studio-flow-developer-experience-self-check:p1:inst-load-registry
    self_check_report: Dict[str, object] = {}
    artifacts_meta = getattr(ctx, "meta", None)
    meta_err = None if artifacts_meta is not None else "missing"
    # @cpt-end:cpt-studio-flow-developer-experience-self-check:p1:inst-load-registry
    if artifacts_meta is not None and not meta_err:
        self_check_report = _run_registered_self_check(
            project_root=project_root,
            adapter_dir=adapter_dir,
            kit_filter=kit_filter,
            verbose=verbose,
            ctx=ctx,
            artifacts_meta=artifacts_meta,
        )
        _collect_self_check_failures(self_check_report, all_errors)
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-template-check

    # ── Build result ──────────────────────────────────────────────────
    return _build_validate_kits_result(
        verbose=verbose,
        kit_reports=kit_reports,
        all_errors=all_errors,
        self_check_report=self_check_report,
    )


# @cpt-flow:cpt-studio-flow-kit-validate-cli:p1
def cmd_validate_kits(argv: List[str]) -> int:
    """Validate Studio kit packages (CLI entry point)."""
    # @cpt-begin:cpt-studio-flow-developer-experience-self-check:p1:inst-user-self-check
    # @cpt-begin:cpt-studio-flow-kit-validate-cli:p1:inst-parse-args
    p = argparse.ArgumentParser(
        prog="validate-kits",
        description="Validate kit structure, templates, and examples",
    )
    p.add_argument(
        "path",
        nargs="?",
        default=None,
        help=(
            "Path to a kit directory to validate (e.g. kits/sdlc). "
            "If omitted, validates registered kits."
        ),
    )
    p.add_argument(
        "--kit",
        "--rule",
        dest="kit",
        default=None,
        help="Kit ID to validate (if omitted, validates all kits)",
    )
    p.add_argument("--verbose", action="store_true", help="Print full validation report")
    args = p.parse_args(argv)
    # @cpt-end:cpt-studio-flow-kit-validate-cli:p1:inst-parse-args

    # @cpt-begin:cpt-studio-flow-kit-validate-cli:p1:inst-path-mode
    if args.path:
        rc, result = _validate_kit_by_path(Path(args.path), verbose=bool(args.verbose))
        ui.result(result, human_fn=_human_validate_kits)
        return rc
    # @cpt-end:cpt-studio-flow-kit-validate-cli:p1:inst-path-mode

    # @cpt-begin:cpt-studio-flow-kit-validate-cli:p1:inst-registered-mode
    from ..utils.context import get_context
    ctx = get_context()
    if not ctx:
        ui.result({"status": "ERROR", "message": "Constructor Studio not initialized. Run 'cfs init' first."})
        return 1

    rc, result = run_validate_kits(
        project_root=ctx.project_root,
        adapter_dir=ctx.adapter_dir,
        kit_filter=str(args.kit) if args.kit else None,
        verbose=bool(args.verbose),
        ctx=ctx,
    )
    # @cpt-end:cpt-studio-flow-kit-validate-cli:p1:inst-registered-mode

    # @cpt-begin:cpt-studio-flow-kit-validate-cli:p1:inst-output-result
    ui.result(result, human_fn=_human_validate_kits)
    return rc
    # @cpt-end:cpt-studio-flow-kit-validate-cli:p1:inst-output-result
    # @cpt-end:cpt-studio-flow-developer-experience-self-check:p1:inst-user-self-check


# @cpt-algo:cpt-studio-algo-kit-validate-by-path:p1
# @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-resolve-dir
def _validate_kit_by_path(kit_path: Path, *, verbose: bool = False) -> Tuple[int, Dict[str, Any]]:
    """Validate a standalone kit directory (not necessarily registered in config)."""
    from ..utils.constraints import load_constraints_files, load_constraints_toml
    from ..utils.artifacts_meta import ArtifactsMeta

    kit_dir = Path(kit_path).resolve()
    if not kit_dir.is_dir():
        return 1, {"status": "ERROR", "message": f"Kit directory not found: {kit_dir}"}

    validation = _prepare_path_validation(
        kit_dir=kit_dir,
        load_constraints_files=load_constraints_files,
        load_constraints_toml=load_constraints_toml,
    )
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-resolve-dir

    # @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-structural-check
    # ── Phase 1: Structural — KitModel constraints resources ──────────
    all_errors: List[Dict[str, object]] = []
    kit_report = _new_path_kit_report(
        slug=validation.slug,
        kit_dir=kit_dir,
        verbose=verbose,
        constraints=validation.constraints,
        kc_errs=validation.constraint_errors,
        constraints_error_path=validation.constraints_error_path,
        all_errors=all_errors,
    )
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-structural-check

    # ── Phase 1b: KitModel resource verification ─────────────────────
    _apply_path_model_info(
        model=validation.model,
        model_error=validation.model_error,
        has_model_input=validation.has_model_input,
        kit_dir=kit_dir,
        slug=validation.slug,
        verbose=verbose,
        kit_report=kit_report,
        all_errors=all_errors,
    )

    # @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-build-artifacts-meta
    # ── Phase 2: Template & example validation ────────────────────────
    base_meta = ArtifactsMeta.from_dict({
        "version": "1.1",
        "project_root": str(kit_dir.parent),
        "kits": {validation.slug: {"format": "CFS", "path": str(kit_dir)}},
    })
    meta, binding_warnings = _build_path_validation_meta(
        ArtifactsMeta=ArtifactsMeta,
        base_meta=base_meta,
        kit_dir=kit_dir,
        slug=validation.slug,
        model=validation.model,
        constraints=validation.constraints,
    )
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-build-artifacts-meta

    self_check_report = _run_path_self_check(
        kc_errs=validation.constraint_errors,
        binding_warnings=binding_warnings,
        meta=meta,
        kit_dir=kit_dir,
        slug=validation.slug,
        verbose=verbose,
        all_errors=all_errors,
    )

    # ── Build result ──────────────────────────────────────────────────
    return _build_validate_kits_result(
        verbose=verbose,
        kit_reports=[kit_report],
        all_errors=all_errors,
        self_check_report=self_check_report,
    )


# @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-structural-check
def _prepare_path_validation(
    *,
    kit_dir: Path,
    load_constraints_files: Any,
    load_constraints_toml: Any,
) -> _PathValidationContext:
    slug = kit_dir.name
    has_model_input = (
        (kit_dir / ".cf-studio-kit.toml").is_file()
        or (kit_dir / "manifest.toml").is_file()
        or (kit_dir / "conf.toml").is_file()
        or any((kit_dir / dirname).exists() for dirname in ("artifacts", "codebase", "scripts", "workflows"))
    )
    model = None
    model_error: Optional[Exception] = None
    try:
        from ..utils.kit_model import load_kit_model
        model = load_kit_model(kit_dir)
    except (ValueError, OSError, KeyError) as exc:
        model_error = exc
    constraints, constraint_errors, _constraint_paths, constraints_error_path = _load_path_validation_constraints(
        kit_dir=kit_dir,
        model=model,
        load_constraints_files=load_constraints_files,
        load_constraints_toml=load_constraints_toml,
    )
    return _PathValidationContext(
        slug=slug,
        has_model_input=has_model_input,
        model=model,
        model_error=model_error,
        constraints=constraints,
        constraint_errors=constraint_errors,
        constraints_error_path=constraints_error_path,
    )
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-structural-check


# @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-structural-check
def _load_path_validation_constraints(
    *,
    kit_dir: Path,
    model: Any,
    load_constraints_files: Any,
    load_constraints_toml: Any,
) -> Tuple[Any, List[Any], List[Path], Path]:
    constraint_paths: List[Path] = []
    if model is not None:
        constraint_paths = [
            (kit_dir / str(resource.source)).resolve()
            for resource in getattr(model, "resources", [])
            if str(getattr(resource, "kind", "") or "").strip().lower() == "constraints"
        ]
    if constraint_paths:
        constraints, errors = load_constraints_files(constraint_paths)
        return constraints, errors, constraint_paths, constraint_paths[0]
    constraints, errors = load_constraints_toml(kit_dir)
    return constraints, errors, constraint_paths, kit_dir / "constraints.toml"
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-structural-check


# @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-build-result
def _new_path_kit_report(
    *,
    slug: str,
    kit_dir: Path,
    verbose: bool,
    constraints: Any,
    kc_errs: List[Any],
    constraints_error_path: Path,
    all_errors: List[Dict[str, object]],
) -> Dict[str, object]:
    kit_report: Dict[str, object] = {
        "kit": slug,
        "path": str(kit_dir),
        "status": "PASS" if not kc_errs else "FAIL",
        "error_count": len(kc_errs),
    }
    if kc_errs:
        errs = [
            constraints_error(
                "constraints",
                "Invalid constraints",
                path=constraints_error_path,
                line=1,
                errors=list(kc_errs),
                kit=slug,
            )
        ]
        if verbose:
            kit_report["errors"] = errs
        all_errors.extend(errs)
        return kit_report
    if verbose and constraints is not None and getattr(constraints, "by_kind", None):
        kit_report["kinds"] = sorted(constraints.by_kind.keys())
    return kit_report
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-build-result


# @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-verify-resource-paths
def _apply_path_model_info(
    *,
    model: Any,
    model_error: Optional[Exception],
    has_model_input: bool,
    kit_dir: Path,
    slug: str,
    verbose: bool,
    kit_report: Dict[str, object],
    all_errors: List[Dict[str, object]],
) -> None:
    if model is not None:
        if verbose:
            kit_report["manifest_source"] = model.manifest_source
            kit_report["resource_count"] = len(model.resources)
            kit_report["public_components"] = [
                component.generated_name
                for component in model.public_components
            ]
        return
    if not isinstance(model_error, ValueError) or not has_model_input:
        return
    err = constraints_error(
        "resources",
        str(model_error),
        path=kit_dir,
        line=1,
        kit=slug,
    )
    all_errors.append(err)
    kit_report["status"] = "FAIL"
    kit_report["error_count"] = int(kit_report.get("error_count", 0)) + 1
    if verbose:
        kit_report.setdefault("errors", []).append(err)
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-verify-resource-paths


# @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-build-artifacts-meta
def _build_path_validation_meta(
    *,
    ArtifactsMeta: Any,
    base_meta: Any,
    kit_dir: Path,
    slug: str,
    model: Any,
    constraints: Any,
) -> Tuple[Optional[Any], List[Dict[str, object]]]:
    model_source = str(getattr(model, "manifest_source", "") or "") if model is not None else ""
    if model is not None and model_source in {"canonical", "core"}:
        return _synthesized_meta_from_kit_model(
            base_meta=base_meta,
            kit_dir=kit_dir,
            kit_id=slug,
            model=model,
            constraints=constraints,
        )
    return _legacy_path_validation_meta(ArtifactsMeta, kit_dir, slug), []
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-build-artifacts-meta


# @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-build-artifacts-meta
def _legacy_path_validation_meta(artifacts_meta_cls: Any, kit_dir: Path, slug: str) -> Any:
    artifacts_dict: Dict[str, Dict[str, str]] = {}
    artifacts_dir = kit_dir / "artifacts"
    if artifacts_dir.is_dir():
        for kind_dir in sorted(artifacts_dir.iterdir()):
            if not kind_dir.is_dir():
                continue
            template = kind_dir / "template.md"
            if not template.is_file():
                continue
            artifacts_dict[kind_dir.name] = {
                "template": str(template),
                "examples": str(kind_dir / "examples"),
            }
    return artifacts_meta_cls.from_dict({
        "version": "1.1",
        "project_root": str(kit_dir.parent),
        "kits": {slug: {"format": "CFS", "path": str(kit_dir), "artifacts": artifacts_dict}},
    })
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-build-artifacts-meta


# @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-template-check
def _run_path_self_check(
    *,
    kc_errs: List[Any],
    binding_warnings: List[Dict[str, object]],
    meta: Optional[Any],
    kit_dir: Path,
    slug: str,
    verbose: bool,
    all_errors: List[Dict[str, object]],
) -> Dict[str, object]:
    if kc_errs:
        return {}
    from .self_check import run_self_check_from_meta

    self_check_report: Dict[str, object] = {}
    if binding_warnings:
        self_check_report = {
            "status": "PASS",
            "project_root": kit_dir.parent.as_posix(),
            "studio_dir": kit_dir.parent.as_posix(),
            "kits_checked": 0,
            "templates_checked": 0,
            "results": list(binding_warnings),
        }
    if meta is not None:
        _, sc_out = run_self_check_from_meta(
            project_root=kit_dir.parent,
            adapter_dir=kit_dir.parent,
            artifacts_meta=meta,
            kit_filter=slug,
            verbose=verbose,
        )
        _merge_self_check_report(self_check_report, sc_out)
    _collect_self_check_failures(self_check_report, all_errors)
    return self_check_report
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-template-check

# @cpt-begin:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-format
def _show_error(e: object, *, prefix: str = "\u2717") -> None:
    """Display a single error/warning dict with nested details."""
    if not isinstance(e, dict):
        ui.substep(f"  {prefix} {e}")
        return
    msg = e.get("message", "")
    path = ui.relpath(str(e.get("path", ""))) if e.get("path") else ""
    line = e.get("line", "")
    loc = f"{path}:{line}" if path and line else (path or "")
    # Add context fields when available (id_kind, artifact_kind)
    ctx_parts: List[str] = []
    if e.get("artifact_kind"):
        ctx_parts.append(str(e["artifact_kind"]))
    if e.get("id_kind"):
        ctx_parts.append(f"id={e['id_kind']}")
    if e.get("id_kind_template"):
        ctx_parts.append(f"tpl={e['id_kind_template']}")
    ctx = f" [{', '.join(ctx_parts)}]" if ctx_parts else ""
    # Show the main message
    if loc:
        ui.substep(f"  {prefix} {loc}  {msg}{ctx}")
    else:
        ui.substep(f"  {prefix} {msg}{ctx}")
    # Show nested error details (e.g. from constraints parsing)
    for detail in (e.get("errors") or []):
        ui.substep(f"      {detail}")


def _human_validate_kits(data: dict) -> None:
    ui.header("Validate Kits")
    n = data.get("kits_validated", 0)
    n_err = data.get("error_count", 0)
    n_tpl = data.get("templates_checked", 0)
    ui.detail("Kits validated", str(n))
    if n_tpl:
        ui.detail("Templates checked", str(n_tpl))
    ui.detail("Errors", str(n_err))

    _render_verbose_kit_reports(data.get("kits", []))
    sc_results = data.get("self_check_results", [])
    _render_self_check_results(sc_results, show_verbose=bool(data.get("kits")))
    _render_non_verbose_validate_errors(data, sc_results)

    overall = data.get("status", "")
    ui.blank()
    if overall == "PASS":
        ui.success(f"{n} kit(s) validated, all passed.")
    else:
        ui.error(f"{n} kit(s) validated, {n_err} error(s).")
    ui.blank()
# @cpt-end:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-format


# @cpt-begin:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-format
def _render_verbose_kit_reports(kits: List[dict]) -> None:
    for kit_report in kits:
        kit_id = kit_report.get("kit", "?")
        status = kit_report.get("status", "?")
        kinds = kit_report.get("kinds", [])
        if status == "PASS":
            kind_str = f"  ({', '.join(kinds)})" if kinds else ""
            ui.step(f"{kit_id}: PASS{kind_str}")
            continue
        ui.warn(f"{kit_id}: {status} ({kit_report.get('error_count', 0)} errors)")
        for error in kit_report.get("errors", [])[:10]:
            _show_error(error)
    # @cpt-end:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-format


# @cpt-begin:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-format
def _render_self_check_results(sc_results: List[dict], *, show_verbose: bool) -> None:
    if not sc_results:
        return
    ui.blank()
    ui.substep("Templates & examples:")
    for result in sc_results:
        _render_self_check_result(result, show_verbose=show_verbose)
    # @cpt-end:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-format


# @cpt-begin:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-format
def _render_self_check_result(result: dict, *, show_verbose: bool) -> None:
    kit_id = result.get("kit") or "?"
    kind = result.get("kind") or "?"
    status = result.get("status", "?")
    error_count = result.get("error_count", 0)
    warning_count = result.get("warning_count", 0)
    if status == "PASS":
        suffix = ""
        if warning_count:
            suffix = f" ({warning_count} warning(s))"
            if not show_verbose:
                suffix += " - use --verbose for details"
        ui.step(f"{kit_id}/{kind}: PASS{suffix}")
    else:
        ui.warn(f"{kit_id}/{kind}: {status} - {error_count} error(s), {warning_count} warning(s)")
    for error in result.get("errors", [])[:10]:
        _show_error(error)
    for warning in result.get("warnings", [])[:10]:
        _show_error(warning, prefix="!")
    # @cpt-end:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-format


# @cpt-begin:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-format
def _render_non_verbose_validate_errors(data: dict, sc_results: List[dict]) -> None:
    if data.get("kits"):
        return
    if not sc_results:
        failed = data.get("failed_kits", [])
        if failed:
            ui.blank()
            for failed_kit in failed:
                ui.warn(f"{failed_kit.get('kit', '?')}: {failed_kit.get('error_count', 0)} error(s)")
    shown_msgs = _shown_self_check_messages(sc_results)
    top_errors = (data.get("errors") or [])[:10]
    unseen = [
        error for error in top_errors
        if not isinstance(error, dict) or error.get("message", "") not in shown_msgs
    ]
    for error in unseen:
        _show_error(error)
    truncated = data.get("errors_truncated", 0)
    if truncated:
        ui.substep(f"  ... and {truncated} more error(s)")
    # @cpt-end:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-format


# @cpt-begin:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-format
def _shown_self_check_messages(sc_results: List[dict]) -> Set[str]:
    shown_msgs: Set[str] = set()
    for result in sc_results:
        for error in result.get("errors", []):
            if isinstance(error, dict):
                shown_msgs.add(str(error.get("message", "")))
    return shown_msgs
    # @cpt-end:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-format
