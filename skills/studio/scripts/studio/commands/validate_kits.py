"""
Validate Kits Command — validate kit structure, templates, and examples.

Kits are direct file packages — validation checks kit directory presence,
conf.toml readability, constraints.toml schema, and template/example
consistency against constraints.
"""

# @cpt-begin:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-imports
import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple

from ..utils.constraints import error as constraints_error
from ..utils.ui import ui
# @cpt-end:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-imports

def _constraint_artifact_bindings(loaded_kit: Any) -> Dict[str, Dict[str, str]]:
    """Return explicit artifact-kind bindings declared on constraints resources."""
    # @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
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


def _constraints_binding_path(loaded_kit: Any, resource_bindings: Dict[str, str]) -> str:
    # @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
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


def _known_constraint_kinds(loaded_kit: Any) -> Set[str]:
    # @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
    constraints = getattr(loaded_kit, "constraints", None)
    return {str(kind).strip().upper() for kind in (getattr(constraints, "by_kind", {}) or {}).keys() if str(kind).strip()}
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map


def _resource_binding_path(resource_bindings: Dict[str, str], resource_id: str) -> str:
    # @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
    return str(resource_bindings.get(resource_id, "") or "").strip()
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map


def _missing_bound_artifact_warnings(
    *,
    kit_id: str,
    known_kinds: Set[str],
    artifacts: Dict[str, Dict[str, str]],
) -> List[Dict[str, object]]:
    # @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
    results: List[Dict[str, object]] = []
    for kind in sorted(known_kinds):
        spec = artifacts.get(kind, {})
        if str(spec.get("template", "") or "").strip() or str(spec.get("examples", "") or "").strip():
            continue
        warning = constraints_error(
            "template",
            "Constraints declare artifact kind but no manifest resource binding is available for template/example self-check",
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


def _constraints_binding_paths(
    loaded_kit: Any,
    resource_bindings: Dict[str, str],
) -> List[Path]:
    # @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
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


def _synthesized_meta_from_resource_bindings(
    *,
    base_meta: Any,
    adapter_dir: Path,
    kit_id: str,
    loaded_kit: Any,
) -> Tuple[Optional[Any], List[Dict[str, object]]]:
    """Build self-check metadata from loaded manifest resource bindings."""
    # @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
    from ..utils.artifacts_meta import ArtifactsMeta, Kit

    rb = getattr(loaded_kit, "resource_bindings", None)
    if not isinstance(rb, dict) or not rb:
        return None, []

    artifact_bindings = _constraint_artifact_bindings(loaded_kit)
    artifacts: Dict[str, Dict[str, str]] = {}
    for kind, binding_spec in sorted(artifact_bindings.items()):
        spec: Dict[str, str] = {}
        template = _resource_binding_path(rb, str(binding_spec.get("template", "") or ""))
        if not template:
            template = ""
        if template:
            spec["template"] = template
        example_path = _resource_binding_path(rb, str(binding_spec.get("examples", "") or ""))
        if example_path:
            spec["examples"] = example_path
        if spec:
            artifacts[kind] = spec

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
    if constraints_path:
        kit_base = Path(constraints_path).parent
    else:
        kit_root = getattr(loaded_kit, "kit_root", None)
        kit_base = kit_root if isinstance(kit_root, Path) else adapter_dir

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


def _synthesized_meta_from_kit_model(
    *,
    base_meta: Any,
    kit_dir: Path,
    kit_id: str,
    model: Any,
    constraints: Any,
) -> Tuple[Optional[Any], List[Dict[str, object]]]:
    """Build self-check metadata from a standalone canonical KitModel."""
    # @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-build-artifacts-meta
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
    # @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map
    if not source:
        return
    target.setdefault("results", [])
    target["templates_checked"] = int(target.get("templates_checked", 0) or 0) + int(source.get("templates_checked", 0) or 0)
    target["kits_checked"] = int(target.get("kits_checked", 0) or 0) + int(source.get("kits_checked", 0) or 0)
    if source.get("status") == "FAIL":
        target["status"] = "FAIL"
    elif "status" not in target:
        target["status"] = source.get("status", "PASS")
    results = source.get("results", [])
    if isinstance(results, list):
        target["results"].extend(results)  # type: ignore[union-attr]
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-manifest-bound-artifact-map


# @cpt-dod:cpt-studio-dod-kit-validate:p1
# @cpt-algo:cpt-studio-algo-kit-validate:p1
def run_validate_kits(
    *,
    project_root: Path,
    adapter_dir: Path,
    kit_filter: Optional[str] = None,
    verbose: bool = False,
) -> Tuple[int, Dict[str, Any]]:
    """Run full kit validation (structural + template/example checks).

    Returns (return_code, report_dict).  rc=0 means PASS, rc=2 means FAIL.
    This is the reusable engine called by both the CLI and ``cmd_update``.
    """
    # @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-init-context
    from ..utils.context import get_context
    from ..utils.artifacts_meta import load_artifacts_meta

    ctx = get_context()
    if not ctx:
        return 1, {"status": "ERROR", "message": "Constructor Studio not initialized. Run 'cfs init' first."}
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-init-context

    # @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-structural-check
    # ── Phase 1: Structural validation ────────────────────────────────
    kit_reports: List[Dict[str, object]] = []
    kit_reports_by_id: Dict[str, Dict[str, object]] = {}
    kit_errors_by_id: Dict[str, List[Dict[str, object]]] = {}
    all_errors: List[Dict[str, object]] = []
    context_kit_errors: Dict[str, List[Dict[str, object]]] = {}

    def _sync_kit_report(kit_id: str) -> None:
        rep = kit_reports_by_id.get(kit_id)
        if rep is None:
            return
        rep_errors = list(kit_errors_by_id.get(kit_id, []))
        rep["status"] = "FAIL" if rep_errors else "PASS"
        rep["error_count"] = len(rep_errors)
        if verbose:
            if rep_errors:
                rep["errors"] = rep_errors
            else:
                rep.pop("errors", None)

    for err in (getattr(ctx, "_errors", []) or []):
        if not isinstance(err, dict) or err.get("type") not in {"resources", "constraints"}:
            continue
        err_kit = str(err.get("kit", "") or "")
        if kit_filter and err_kit != str(kit_filter):
            continue
        if err_kit:
            context_kit_errors.setdefault(err_kit, []).append(err)
        all_errors.append(err)

    for kit_id, loaded_kit in (ctx.kits or {}).items():
        if kit_filter and str(kit_id) != str(kit_filter):
            continue

        kit_root = getattr(loaded_kit, "kit_root", None)
        kit_path_value = str(getattr(getattr(loaded_kit, "kit", None), "path", "") or "")
        reported_kit_path = str(kit_root) if isinstance(kit_root, Path) else kit_path_value
        kit_id_str = str(kit_id)
        kit_context_errors = context_kit_errors.get(kit_id_str, [])
        rep_errors: List[Dict[str, object]] = list(kit_context_errors)

        rep: Dict[str, object] = {
            "kit": kit_id_str,
            "path": reported_kit_path,
            "status": "PASS",
            "error_count": 0,
        }
        _kc = getattr(loaded_kit, "constraints", None)
        if verbose and _kc is not None and getattr(_kc, "by_kind", None):
            rep["kinds"] = sorted(_kc.by_kind.keys())

        kit_reports.append(rep)
        kit_reports_by_id[kit_id_str] = rep
        if rep_errors:
            kit_errors_by_id[kit_id_str] = rep_errors
        _sync_kit_report(kit_id_str)
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-structural-check

    # @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-resolve-resource-paths
    # ── Phase 1b: Resource path verification (manifest-driven kits) ───
    for kit_id, loaded_kit in (ctx.kits or {}).items():
        if kit_filter and str(kit_id) != str(kit_filter):
            continue
        kit_id_str = str(kit_id)
        rb = getattr(loaded_kit, "resource_bindings", None)
        if not rb:
            continue
        for res_id, res_path_str in rb.items():
            abs_path = Path(res_path_str)
            if not abs_path.exists():
                err = constraints_error(
                    "resources",
                    f"Resource '{res_id}' path not found: {res_path_str}",
                    path=str(abs_path),
                    line=1,
                    kit=kit_id_str,
                )
                all_errors.append(err)
                kit_errors_by_id.setdefault(kit_id_str, []).append(err)
        _sync_kit_report(kit_id_str)
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-resolve-resource-paths

    # @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-template-check
    # ── Phase 2: Template & example validation ────────────────────────
    # @cpt-begin:cpt-studio-flow-developer-experience-self-check:p1:inst-load-registry
    self_check_report: Dict[str, object] = {}
    artifacts_meta, meta_err = load_artifacts_meta(adapter_dir)
    # @cpt-end:cpt-studio-flow-developer-experience-self-check:p1:inst-load-registry
    if artifacts_meta is not None and not meta_err:
        from .self_check import run_self_check_from_meta
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
            if binding_warnings:
                self_check_report.setdefault("results", [])
                self_check_report["results"].extend(binding_warnings)  # type: ignore[union-attr]
                self_check_report.setdefault("status", "PASS")
                self_check_report.setdefault("templates_checked", 0)
                self_check_report.setdefault("kits_checked", 0)
            if getattr(loaded_kit, "resource_bindings", None):
                manifest_checked_kits.add(kit_id_str)
            if bound_meta is None:
                continue
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

        for r in self_check_report.get("results", []):
            if isinstance(r, dict) and r.get("status") == "FAIL":
                sc_errs = r.get("errors", [])
                if isinstance(sc_errs, list):
                    all_errors.extend(sc_errs)
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-template-check

    # @cpt-begin:cpt-studio-algo-kit-validate:p1:inst-build-result
    # ── Build result ──────────────────────────────────────────────────
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
    # @cpt-end:cpt-studio-algo-kit-validate:p1:inst-build-result


# @cpt-flow:cpt-studio-flow-kit-validate-cli:p1
def cmd_validate_kits(argv: List[str]) -> int:
    """Validate Studio kit packages (CLI entry point)."""
    # @cpt-begin:cpt-studio-flow-kit-validate-cli:p1:inst-parse-args
    p = argparse.ArgumentParser(prog="validate-kits", description="Validate kit structure, templates, and examples")
    p.add_argument("path", nargs="?", default=None, help="Path to a kit directory to validate (e.g. kits/sdlc). If omitted, validates registered kits.")
    p.add_argument("--kit", "--rule", dest="kit", default=None, help="Kit ID to validate (if omitted, validates all kits)")
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
    )
    # @cpt-end:cpt-studio-flow-kit-validate-cli:p1:inst-registered-mode

    # @cpt-begin:cpt-studio-flow-kit-validate-cli:p1:inst-output-result
    ui.result(result, human_fn=_human_validate_kits)
    return rc
    # @cpt-end:cpt-studio-flow-kit-validate-cli:p1:inst-output-result


# @cpt-algo:cpt-studio-algo-kit-validate-by-path:p1
def _validate_kit_by_path(kit_path: Path, *, verbose: bool = False) -> Tuple[int, Dict[str, Any]]:
    """Validate a standalone kit directory (not necessarily registered in config)."""
    # @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-resolve-dir
    from ..utils.constraints import load_constraints_files, load_constraints_toml
    from ..utils.artifacts_meta import ArtifactsMeta

    kit_dir = Path(kit_path).resolve()
    if not kit_dir.is_dir():
        return 1, {"status": "ERROR", "message": f"Kit directory not found: {kit_dir}"}

    # Derive slug from directory name
    slug = kit_dir.name
    has_model_input = (
        (kit_dir / ".cf-studio-kit.toml").is_file()
        or (kit_dir / "manifest.toml").is_file()
        or (kit_dir / "conf.toml").is_file()
        or any((kit_dir / dirname).exists() for dirname in ("artifacts", "codebase", "scripts", "workflows"))
    )
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-resolve-dir

    # @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-structural-check
    # ── Phase 1: Structural — KitModel constraints resources ──────────
    all_errors: List[Dict[str, object]] = []
    model = None
    model_error: Optional[Exception] = None
    try:
        from ..utils.kit_model import load_kit_model
        model = load_kit_model(kit_dir)
    except ValueError as exc:
        model_error = exc
    except (OSError, KeyError) as exc:
        model_error = exc

    constraint_paths: List[Path] = []
    if model is not None:
        constraint_paths = [
            (kit_dir / str(resource.source)).resolve()
            for resource in getattr(model, "resources", [])
            if str(getattr(resource, "kind", "") or "").strip().lower() == "constraints"
        ]
    if constraint_paths:
        _kc, kc_errs = load_constraints_files(constraint_paths)
        constraints_error_path = constraint_paths[0]
    else:
        _kc, kc_errs = load_constraints_toml(kit_dir)
        constraints_error_path = kit_dir / "constraints.toml"

    kit_report: Dict[str, object] = {
        "kit": slug,
        "path": str(kit_dir),
        "status": "PASS" if not kc_errs else "FAIL",
        "error_count": len(kc_errs),
    }
    if kc_errs:
        errs = [constraints_error("constraints", "Invalid constraints", path=constraints_error_path, line=1, errors=list(kc_errs), kit=slug)]
        if verbose:
            kit_report["errors"] = errs
        all_errors.extend(errs)
    else:
        if verbose and _kc is not None and getattr(_kc, "by_kind", None):
            kit_report["kinds"] = sorted(_kc.by_kind.keys())
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-structural-check

    # @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-verify-resource-paths
    # ── Phase 1b: KitModel resource verification ─────────────────────
    if model is not None:
        if verbose:
            kit_report["manifest_source"] = model.manifest_source
            kit_report["resource_count"] = len(model.resources)
            kit_report["public_components"] = [
                component.generated_name
                for component in model.public_components
            ]
    elif isinstance(model_error, ValueError) and has_model_input:
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
    # ── Phase 2: Template & example validation ────────────────────────
    base_meta = ArtifactsMeta.from_dict({
        "version": "1.1",
        "project_root": str(kit_dir.parent),
        "kits": {slug: {"format": "CFS", "path": str(kit_dir)}},
    })
    meta = base_meta
    binding_warnings: List[Dict[str, object]] = []
    model_source = str(getattr(model, "manifest_source", "") or "") if model is not None else ""
    if model is not None and model_source in {"canonical", "core"}:
        bound_meta, binding_warnings = _synthesized_meta_from_kit_model(
            base_meta=base_meta,
            kit_dir=kit_dir,
            kit_id=slug,
            model=model,
            constraints=_kc,
        )
        meta = bound_meta
    else:
        # Legacy package-layout fallback. Canonical manifests must use explicit
        # constraints artifact bindings instead of this directory convention.
        artifacts_dict: Dict[str, Dict[str, str]] = {}
        artifacts_dir = kit_dir / "artifacts"
        if artifacts_dir.is_dir():
            for kind_dir in sorted(artifacts_dir.iterdir()):
                if not kind_dir.is_dir():
                    continue
                kind = kind_dir.name
                tpl = kind_dir / "template.md"
                examples = kind_dir / "examples"
                if tpl.is_file():
                    artifacts_dict[kind] = {
                        "template": str(tpl),
                        "examples": str(examples),  # path may not exist; self_check handles that
                    }

        meta = ArtifactsMeta.from_dict({
            "version": "1.1",
            "project_root": str(kit_dir.parent),
            "kits": {slug: {"format": "CFS", "path": str(kit_dir), "artifacts": artifacts_dict}},
        })
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-build-artifacts-meta

    # @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-template-check
    self_check_report: Dict[str, object] = {}
    if not kc_errs:  # Only run template checks if constraints parsed OK
        from .self_check import run_self_check_from_meta
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
        for r in self_check_report.get("results", []):
            if r.get("status") == "FAIL":
                all_errors.extend(r.get("errors", []))
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-template-check

    # @cpt-begin:cpt-studio-algo-kit-validate-by-path:p1:inst-build-result
    # ── Build result ──────────────────────────────────────────────────
    overall_status = "PASS" if not all_errors else "FAIL"
    result: Dict[str, Any] = {
        "status": overall_status,
        "kits_validated": 1,
        "error_count": len(all_errors),
    }
    if self_check_report:
        result["templates_checked"] = self_check_report.get("templates_checked", 0)
        result["self_check_results"] = self_check_report.get("results", [])
    if verbose:
        result["kits"] = [kit_report]
        if all_errors:
            result["errors"] = all_errors
    else:
        if all_errors:
            result["errors"] = all_errors[:10]
            if len(all_errors) > 10:
                result["errors_truncated"] = len(all_errors) - 10

    return (0 if overall_status == "PASS" else 2), result
    # @cpt-end:cpt-studio-algo-kit-validate-by-path:p1:inst-build-result

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

    # Verbose mode: full kit reports (structural)
    for k in data.get("kits", []):
        kit_id = k.get("kit", "?")
        status = k.get("status", "?")
        kinds = k.get("kinds", [])
        if status == "PASS":
            kind_str = f"  ({', '.join(kinds)})" if kinds else ""
            ui.step(f"{kit_id}: PASS{kind_str}")
        else:
            ui.warn(f"{kit_id}: {status} ({k.get('error_count', 0)} errors)")
            for e in k.get("errors", [])[:10]:
                _show_error(e)

    # Template/example validation results (self-check)
    sc_results = data.get("self_check_results", [])
    if sc_results:
        ui.blank()
        ui.substep("Templates & examples:")
        for r in sc_results:
            kit_id = r.get("kit") or "?"
            kind = r.get("kind") or "?"
            rs = r.get("status", "?")
            n_r_err = r.get("error_count", 0)
            n_r_warn = r.get("warning_count", 0)
            if rs == "PASS":
                suffix = ""
                if n_r_warn:
                    suffix = f" ({n_r_warn} warning(s))"
                    if not data.get("kits"):  # non-verbose
                        suffix += " — use --verbose for details"
                ui.step(f"{kit_id}/{kind}: PASS{suffix}")
            else:
                ui.warn(f"{kit_id}/{kind}: {rs} — {n_r_err} error(s), {n_r_warn} warning(s)")
            for e in r.get("errors", [])[:10]:
                _show_error(e)
            for w in r.get("warnings", [])[:10]:
                _show_error(w, prefix="⚠")

    # Non-verbose mode: show errors not already displayed via sc_results
    if not data.get("kits"):
        if not sc_results:
            failed = data.get("failed_kits", [])
            if failed:
                ui.blank()
                for fk in failed:
                    ui.warn(f"{fk.get('kit', '?')}: {fk.get('error_count', 0)} error(s)")
        # Deduplicate: skip messages already shown inline in sc_results
        _shown_msgs: set = set()
        for r in sc_results:
            for e in r.get("errors", []):
                if isinstance(e, dict):
                    _shown_msgs.add(e.get("message", ""))
        _top = (data.get("errors") or [])[:10]
        _unseen = [e for e in _top
                   if not isinstance(e, dict) or e.get("message", "") not in _shown_msgs]
        for e in _unseen:
            _show_error(e)
        truncated = data.get("errors_truncated", 0)
        if truncated:
            ui.substep(f"  ... and {truncated} more error(s)")

    overall = data.get("status", "")
    ui.blank()
    if overall == "PASS":
        ui.success(f"{n} kit(s) validated, all passed.")
    else:
        ui.error(f"{n} kit(s) validated, {n_err} error(s).")
    ui.blank()
# @cpt-end:cpt-studio-flow-kit-validate-cli:p1:inst-validate-kits-format
