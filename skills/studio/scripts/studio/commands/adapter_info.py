"""
Adapter Info Command — discover and display Constructor Studio project configuration.

Shows project root, studio directory, rules, systems, and registry status.

@cpt-flow:cpt-studio-flow-core-infra-cli-invocation:p1
@cpt-dod:cpt-studio-dod-core-infra-init-config:p1
"""

import argparse
import json
import logging
import os
from pathlib import Path, PureWindowsPath
from typing import Optional

from ..utils._tomllib_compat import tomllib
from ..utils.files import (
    find_studio_directory,
    find_project_root,
    load_studio_config,
)
from ..utils.git_utils import _redact_url
from ..utils.manifest import resolve_resource_bindings_with_errors
from ..utils.ui import ui
from .resolve_vars import _load_core_data_with_error

logger = logging.getLogger(__name__)


def _warn_adapter_info(message: str) -> None:
    logger.warning("info: %s", message)


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-parse-args
def _parse_adapter_info_args(argv: list[str]) -> tuple[Path, Optional[Path]]:
    parser = argparse.ArgumentParser(prog="info", description="Discover Constructor Studio project configuration")
    parser.add_argument("--root", default=".", help="Project root to search from (default: current directory)")
    parser.add_argument(
        "--cf-studio-root",
        "--cf-root",
        "--cf-constructor-root",
        dest="cf_studio_root",
        default=None,
        help="Constructor Studio core location (if agent knows it). Legacy aliases: --cf-root, --cf-constructor-root.",
    )
    args = parser.parse_args(argv)
    start_path = Path(args.root).resolve()
    studio_root_path = Path(args.cf_studio_root).resolve() if args.cf_studio_root else None
    return start_path, studio_root_path
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-parse-args


def _discover_info_context(
    start_path: Path,
    studio_root_path: Optional[Path],
) -> tuple[Optional[Path], Optional[Path]]:
    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-find-root
    project_root = find_project_root(start_path)
    if project_root is None:
        return None, None
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-find-root

    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-find-studio
    adapter_dir = find_studio_directory(start_path, studio_root=studio_root_path)
    return project_root, adapter_dir
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-find-studio


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-load-config
def _initialize_info_config(adapter_dir: Path, project_root: Path) -> dict:
    config = load_studio_config(adapter_dir)
    config["status"] = "FOUND"
    config["project_root"] = project_root.as_posix()
    return config
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-load-config


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-return-no-root
def _emit_info_project_not_found(start_path: Path) -> int:
    ui.result({
        "status": "NOT_FOUND",
        "message": "No project root found (no AGENTS.md with @cf:root-agents or .git)",
        "searched_from": start_path.as_posix(),
        "hint": "Run 'cfs init' in your project root",
    })
    return 1
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-return-no-root


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-return-no-studio
def _emit_info_studio_not_found(project_root: Path) -> int:
    ui.result({
        "status": "NOT_FOUND",
        "message": "Constructor Studio not initialized in project",
        "project_root": project_root.as_posix(),
        "hint": "Run 'cfs init' to initialize Constructor Studio for this project",
    })
    return 1
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-return-no-studio


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-load-json
def _load_json_file(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError, IOError) as exc:
        _warn_adapter_info(f"failed to load JSON file {path}: {exc}")
        return None
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-load-json


# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-show-system-artifacts
def _show_system_artifacts(sys_info: dict) -> None:
    """Render artifacts for one system."""
    for artifact in sys_info.get("artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        path = artifact.get("path", "?")
        kind = artifact.get("kind", "")
        trace = artifact.get("traceability", "")
        parts = [path]
        if kind:
            parts.append(kind)
        if trace and trace != "DOCS-ONLY":
            parts.append(trace)
        ui.substep(f"      {parts[0]}  ({', '.join(parts[1:])})" if len(parts) > 1 else f"      {parts[0]}")
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-show-system-artifacts


# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-show-system-codebase
def _show_system_codebase(sys_info: dict, *, indent: str = "      ") -> None:
    """Render codebase entries for one system."""
    for code_entry in sys_info.get("codebase") or []:
        if not isinstance(code_entry, dict):
            continue
        cpath = code_entry.get("path", "?")
        exts = code_entry.get("extensions") or []
        ext_str = f"  [{', '.join(exts)}]" if exts else ""
        ui.substep(f"{indent}{cpath}{ext_str}")
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-show-system-codebase


# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-show-child-systems
def _show_child_systems(sys_info: dict) -> None:
    """Render child system summaries."""
    for child in sys_info.get("children") or []:
        if not isinstance(child, dict):
            continue
        ch_name = child.get("name", "?")
        ch_slug = child.get("slug", "")
        ui.substep(f"    └ {ch_name} ({ch_slug})")
        for artifact in child.get("artifacts") or []:
            if isinstance(artifact, dict):
                ui.substep(f"        {artifact.get('path', '?')}  ({artifact.get('kind', '')})")
        _show_system_codebase(child, indent="        ")
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-show-child-systems


# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-show-system-info
def _show_system_info(sys_info: dict) -> None:
    """Render one system registry entry."""
    name = sys_info.get("name", "?")
    slug = sys_info.get("slug", "")
    kit = sys_info.get("kit", "")
    label = f"{name} ({slug})" if slug else name
    if kit:
        label += f"  kit={kit}"
    ui.substep(f"  {label}")
    _show_system_artifacts(sys_info)
    _show_system_codebase(sys_info)
    _show_child_systems(sys_info)
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-show-system-info


# @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-read-kit-conf
def _read_kit_conf(conf_path: Path) -> dict:
    """Read kit conf.toml and return key fields."""
    try:
        with open(conf_path, "rb") as f:
            data = tomllib.load(f)
        out: dict = {}
        for k in ("version", "slug", "name"):
            if k in data:
                out[k] = data[k]
        return out
    except (OSError, ValueError) as exc:
        _warn_adapter_info(f"failed to read kit metadata from {conf_path}: {exc}")
        return {}
# @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-read-kit-conf


# @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-resolve-kit-root
def _resolve_info_kit_root(adapter_dir: Path, slug: str, core_kit: dict) -> Path:
    from .kit import _resolve_registered_kit_root_dir

    registered_path = core_kit.get("path") if isinstance(core_kit, dict) else None
    if isinstance(registered_path, str) and registered_path.strip():
        resolved = _resolve_registered_kit_root_dir(adapter_dir, registered_path)
        if resolved is not None:
            return resolved
        path = Path(registered_path)
        return path if path.is_absolute() else adapter_dir / path
    return adapter_dir / "config" / "kits" / slug
# @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-resolve-kit-root


def _effective_info_resource_bindings(adapter_dir: Path, slug: str, core_kit: dict) -> dict:
    resources = core_kit.get("resources") if isinstance(core_kit, dict) else {}
    if isinstance(resources, dict) and resources:
        return resources

    install_mode = str(core_kit.get("install_mode", "") or "").strip() if isinstance(core_kit, dict) else ""
    if install_mode != "register":
        return {}

    from .kit import _serialize_manifest_binding_path

    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-load-variables
    bindings, _binding_errors = resolve_resource_bindings_with_errors(
        adapter_dir / "config",
        slug,
        adapter_dir,
    )
    result = {}
    for resource_id, path in bindings.items():
        result[str(resource_id)] = {
            "path": _serialize_manifest_binding_path(path, adapter_dir),
        }
    return result
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-load-variables


# @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-resource-to-info
def _kit_resource_to_info(resource: object, binding: object) -> dict:
    data = {
        "id": str(getattr(resource, "id", "")),
        "kind": str(getattr(resource, "kind", "")),
        "source": str(getattr(resource, "source", "")),
        "install_path": str(getattr(resource, "install_path", "")),
        "type": str(getattr(resource, "type", "")),
        "public": bool(getattr(resource, "public", False)),
        "generated_name": str(getattr(resource, "generated_name", "")),
        "generated_targets": list(getattr(resource, "generated_targets", []) or []),
        "origin": str(getattr(resource, "origin", "")),
        "content_hash": str(getattr(resource, "content_hash", "")),
    }
    if isinstance(binding, dict) and "path" in binding:
        data["binding_path"] = binding["path"]
    return data
# @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-resource-to-info


# @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-resolve-binding-path
def _resolve_info_binding_path(adapter_dir: Path, raw_path: object) -> Optional[Path]:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    if os.name != "nt" and PureWindowsPath(raw_path).is_absolute():
        return None
    path = Path(raw_path)
    return path if path.is_absolute() else adapter_dir / path
# @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-resolve-binding-path


# @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-is-relative-to
def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError as exc:
        _warn_adapter_info(f"path {path} is not relative to {parent}: {exc}")
        return False
# @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-is-relative-to


# @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-frontmatter-type
def _frontmatter_type(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        _warn_adapter_info(f"failed to read frontmatter from {path}: {exc}")
        return ""
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:80]:
        stripped = line.strip()
        if stripped == "---":
            return ""
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        if key.strip() == "type":
            return value.strip().strip('"\'')
    return ""
# @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-frontmatter-type


# @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-is-workflow-frontmatter
def _is_workflow_frontmatter_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".md" and _frontmatter_type(path) == "workflow"
# @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-is-workflow-frontmatter


# @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-workflows-deprecated
def _legacy_workflow_names_from_component(kit_root: Path, component: object) -> list[str]:
    if str(getattr(component, "origin", "")) != "legacy-workflow":
        return []
    source = str(getattr(component, "source", ""))
    if not source:
        return []
    path = (kit_root / source).resolve()
    if not _is_relative_to(path, kit_root):
        return []
    if path.is_dir():
        return sorted(p.stem for p in path.iterdir() if _is_workflow_frontmatter_file(p))
    if path.is_file() and path.suffix.lower() == ".md":
        return [path.stem]
    return []
# @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-workflows-deprecated


# @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-workflows-deprecated
def _public_workflow_ids_from_resource(resource: object) -> list[str]:
    kind = str(getattr(resource, "kind", "") or "")
    if kind not in {"skill", "workflow"} or not bool(getattr(resource, "public", False)):
        return []
    resource_id = str(getattr(resource, "id", "") or "").strip()
    if not resource_id:
        return []
    return [resource_id]
# @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-workflows-deprecated


def _kit_resource_drift(
    adapter_dir: Path,
    model_resource_ids: set[str],
    resource_bindings: dict,
) -> tuple[list[str], list[str]]:
    missing_resources: list[str] = []
    containment_violations: list[str] = []
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-drift-resource-scan
    for resource_id in sorted(model_resource_ids):
        binding = resource_bindings.get(resource_id)
        binding_path = binding.get("path") if isinstance(binding, dict) else None
        resolved = _resolve_info_binding_path(adapter_dir, binding_path)
        if resolved is None:
            continue
        if not _is_relative_to(resolved, adapter_dir):
            containment_violations.append(resource_id)
        if not resolved.exists():
            missing_resources.append(resource_id)
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-drift-resource-scan
    return missing_resources, containment_violations


# @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-drift-containment-status
def _drift_containment_status(
    containment_violations: list[str],
    resource_count: int,
) -> str:
    if not containment_violations:
        return "contained"
    if len(containment_violations) == resource_count:
        return "external"
    return "mixed"
# @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-drift-containment-status


def _kit_model_drift(
    adapter_dir: Path,
    model: object,
    core_kit: dict,
    resource_bindings: dict,
) -> dict:
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-drift
    install_mode = str(core_kit.get("install_mode", "copy")) if isinstance(core_kit, dict) else "copy"
    model_resource_ids = {str(getattr(resource, "id", "")) for resource in getattr(model, "resources", [])}
    bound_resource_ids = {str(resource_id) for resource_id in resource_bindings}
    missing_resources, containment_violations = _kit_resource_drift(
        adapter_dir,
        model_resource_ids,
        resource_bindings,
    )
    stale_resources = sorted(bound_resource_ids - model_resource_ids)
    disabled_public_components = sorted(
        str(getattr(component, "id", ""))
        for component in getattr(model, "public_components", [])
        if str(getattr(component, "id", "")) in set(missing_resources)
    )
    return {
        "status": "drifted" if any((missing_resources, stale_resources, containment_violations)) else "unknown",
        "install_mode": install_mode,
        "containment": {
            "status": _drift_containment_status(containment_violations, len(model_resource_ids)),
            "violations": containment_violations,
        },
        "missing_resources": missing_resources,
        "stale_resources": stale_resources,
        "disabled_public_components": disabled_public_components,
    }
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-drift


def _kit_model_to_info(  # pylint: disable=too-many-locals
    adapter_dir: Path,
    kit_slug: str,
    kit_root: Path,
    core_kit: dict,
) -> tuple[dict, dict]:
    """Return canonical kit model info plus legacy kit_details compatibility."""
    # @cpt-begin:cpt-studio-algo-kit-manifest-normalize:p1:inst-rollout-info
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-installed-source-truth
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-kitmodel-source
    from .kit import _serialize_public_component
    from ..utils.kit_model import load_installed_kit_model

    resource_bindings = _effective_info_resource_bindings(adapter_dir, kit_slug, core_kit)
    model = load_installed_kit_model(kit_root, core_kit, kit_slug=kit_slug)
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-kitmodel-source
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-installed-source-truth

    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-kitmodels-shape
    drift = _kit_model_drift(adapter_dir, model, core_kit, resource_bindings)
    disabled_public_components = _disabled_public_component_ids(drift)
    active_targets = sorted({
        target
        for component in model.public_components
        if component.id not in disabled_public_components
        for target in component.generated_targets
    })
    model_info = {
        "slug": model.slug,
        "name": model.name,
        "version": core_kit.get("version", model.version) if isinstance(core_kit, dict) else model.version,
        "source_root": kit_root.as_posix(),
        "manifest_source": model.manifest_source,
        "install_mode": str(core_kit.get("install_mode", "copy")) if isinstance(core_kit, dict) else "copy",
        "resource_count": len(model.resources),
        "resources": {
            resource.id: _kit_resource_to_info(resource, resource_bindings.get(resource.id))
            for resource in model.resources
        },
        "public_components": [
            _serialize_public_component(
                component,
                disabled=component.id in disabled_public_components,
            )
            for component in model.public_components
        ],
        "active_targets": active_targets,
        "risk": {
            "tool_fingerprint": model.tool_risk_fingerprint,
            "summary": model.tool_risk_summary,
        },
        "provenance": {
            "source": core_kit.get("source", "") if isinstance(core_kit, dict) else "",
            "registered_path": core_kit.get("path", "") if isinstance(core_kit, dict) else "",
        },
        "legacy_compatibility": {
            "kit_details": True,
            "manifest_source": model.manifest_source,
        },
        "warnings": model.warnings,
        "drift": drift,
    }
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-kitmodels-shape

    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-kitdetails-derived
    kit_detail = {
        "slug": model.slug,
        "name": model.name,
        "version": model_info["version"],
    }
    content_dirs = sorted({
        resource.source.split("/", 1)[0]
        for resource in model.resources
        if "/" in resource.source
        and resource.source.split("/", 1)[0] in ("artifacts", "codebase", "scripts", "workflows")
    })
    if content_dirs:
        kit_detail["content_dirs"] = content_dirs
    artifact_kinds = sorted({
        parts[1]
        for resource in model.resources
        for parts in [resource.source.split("/")]
        if len(parts) >= 2 and parts[0] == "artifacts"
    })
    if artifact_kinds:
        kit_detail["artifact_kinds"] = artifact_kinds
    workflows = sorted({
        workflow
        for component in model.public_components
        for workflow in _legacy_workflow_names_from_component(kit_root, component)
    } | {
        workflow
        for resource in model.resources
        for workflow in _public_workflow_ids_from_resource(resource)
    })
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-workflows-deprecated
    if workflows:
        kit_detail["workflows"] = workflows
        kit_detail["workflows_deprecated"] = True
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-workflows-deprecated
    if resource_bindings:
        kit_detail["resources"] = resource_bindings
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-kitdetails-derived

    # @cpt-end:cpt-studio-algo-kit-manifest-normalize:p1:inst-rollout-info
    return model_info, kit_detail


def _disabled_public_component_ids(drift: dict) -> set[str]:
    # @cpt-begin:cpt-studio-algo-kit-update-drift-prune:p1:inst-update-disable-missing-public
    component_ids = set(drift.get("disabled_public_components", []))
    return component_ids
    # @cpt-end:cpt-studio-algo-kit-update-drift-prune:p1:inst-update-disable-missing-public


# @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-legacy-content-shape
def _legacy_kit_content_dirs(kit_root: Path) -> list[str]:
    if not kit_root.is_dir():
        return []
    return sorted(
        directory.name
        for directory in kit_root.iterdir()
        if directory.is_dir() and directory.name in ("artifacts", "codebase", "scripts", "workflows")
    )
# @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-legacy-content-shape


# @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-legacy-content-shape
def _legacy_kit_artifact_kinds(kit_root: Path) -> list[str]:
    art_dir = kit_root / "artifacts"
    if not art_dir.is_dir():
        return []
    return sorted(directory.name for directory in art_dir.iterdir() if directory.is_dir())
# @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-legacy-content-shape


def _legacy_workflows_from_resources(core_kit: dict) -> set[str]:
    workflows: set[str] = set()
    resources = core_kit.get("resources") if isinstance(core_kit, dict) else {}
    if not isinstance(resources, dict):
        return workflows
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-legacy-workflows
    for resource_id, binding in resources.items():
        if not isinstance(binding, dict):
            continue
        kind = str(binding.get("kind", "") or "")
        if bool(binding.get("public", False)) and kind in {"skill", "workflow"}:
            workflows.add(str(resource_id))
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-legacy-workflows
    return workflows


# @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-legacy-workflows
def _legacy_kit_workflows(kit_root: Path, core_kit: dict) -> list[str]:
    wf_dir = kit_root / "workflows"
    workflows = _legacy_workflows_from_resources(core_kit)
    if wf_dir.is_dir():
        workflows.update(
            path.stem for path in wf_dir.iterdir() if _is_workflow_frontmatter_file(path)
        )
    return sorted(workflows)
# @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-legacy-workflows


# @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-legacy-detail-build
def _legacy_kit_detail(adapter_dir: Path, slug: str, kit_root: Path, core_kit: dict) -> dict:
    kd: dict = {"slug": slug}
    if "version" in core_kit:
        kd["version"] = core_kit["version"]
    kit_conf = kit_root / "conf.toml"
    if kit_conf.is_file():
        conf_info = _read_kit_conf(kit_conf)
        if "name" in conf_info:
            kd["name"] = conf_info["name"]
        if "slug" in conf_info and "slug" not in kd:
            kd["slug"] = conf_info["slug"]
    content_dirs = _legacy_kit_content_dirs(kit_root)
    if content_dirs:
        kd["content_dirs"] = content_dirs
    artifact_kinds = _legacy_kit_artifact_kinds(kit_root)
    if artifact_kinds:
        kd["artifact_kinds"] = artifact_kinds
    workflows = _legacy_kit_workflows(kit_root, core_kit)
    if workflows:
        kd["workflows"] = workflows
        kd["workflows_deprecated"] = True
    resource_bindings = _effective_info_resource_bindings(adapter_dir, slug, core_kit)
    if resource_bindings:
        kd["resources"] = resource_bindings
    return kd
# @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-legacy-detail-build


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-resolve-registry-path
def _resolve_registry_path(adapter_dir: Path) -> Path:
    registry_path = (adapter_dir / "artifacts.toml").resolve()
    if registry_path.is_file():
        return registry_path
    config_toml = (adapter_dir / "config" / "artifacts.toml").resolve()
    if config_toml.is_file():
        return config_toml
    legacy_json = adapter_dir / "artifacts.json"
    if legacy_json.is_file():
        return legacy_json.resolve()
    return registry_path
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-resolve-registry-path


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-load-registry-payload
def _load_registry_data(registry_path: Path) -> Optional[dict]:
    registry = _load_json_file(registry_path) if registry_path.suffix == ".json" else None
    if registry is not None or registry_path.suffix != ".toml" or not registry_path.is_file():
        return registry
    try:
        with open(registry_path, "rb") as handle:
            loaded = tomllib.load(handle)
    except (OSError, ValueError) as exc:
        _warn_adapter_info(f"failed to read registry data from {registry_path}: {exc}")
        return None
    return loaded if isinstance(loaded, dict) else None
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-load-registry-payload


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-extract-autodetect-system
def _extract_autodetect_system(system_data: object) -> dict:
    if not isinstance(system_data, dict):
        return {}
    out: dict = {}
    for key in ("name", "slug", "kit"):
        value = system_data.get(key)
        if isinstance(value, str):
            out[key] = value
    if isinstance(system_data.get("autodetect"), list):
        out["autodetect"] = system_data.get("autodetect")
    children = system_data.get("children")
    out["children"] = (
        [_extract_autodetect_system(child) for child in (children or [])]
        if isinstance(children, list)
        else []
    )
    return out
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-extract-autodetect-system


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-build-autodetect-registry
def _extract_autodetect_registry(raw: object, core_data: Optional[dict]) -> Optional[dict]:
    if not isinstance(raw, dict) or "systems" not in raw:
        return None
    version = raw.get("version")
    project_root = raw.get("project_root")
    kits = raw.get("kits")
    if isinstance(core_data, dict):
        if version is None and isinstance(core_data.get("version"), str):
            version = core_data["version"]
        if project_root is None and isinstance(core_data.get("project_root"), str):
            project_root = core_data["project_root"]
        if not kits and isinstance(core_data.get("kits"), dict):
            kits = core_data["kits"]
    return {
        "version": version,
        "project_root": project_root,
        "kits": kits,
        "ignore": raw.get("ignore"),
        "systems": [
            _extract_autodetect_system(system_data)
            for system_data in (raw.get("systems") or [])
        ],
    }
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-build-autodetect-registry


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-serialize-artifact
def _artifact_to_registry_dict(artifact: object) -> dict:
    return {
        "path": str(getattr(artifact, "path", "")),
        "kind": str(getattr(artifact, "kind", getattr(artifact, "type", ""))),
        "traceability": str(getattr(artifact, "traceability", "DOCS-ONLY")),
    }
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-serialize-artifact


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-serialize-codebase
def _codebase_to_registry_dict(codebase: object) -> dict:
    data = {"path": str(getattr(codebase, "path", ""))}
    exts = getattr(codebase, "extensions", None)
    if isinstance(exts, list) and exts:
        data["extensions"] = [str(ext) for ext in exts if isinstance(ext, str)]
    name = getattr(codebase, "name", None)
    if isinstance(name, str) and name.strip():
        data["name"] = name
    single_line_comments = getattr(codebase, "single_line_comments", None)
    if isinstance(single_line_comments, list) and single_line_comments:
        data["singleLineComments"] = single_line_comments
    multi_line_comments = getattr(codebase, "multi_line_comments", None)
    if isinstance(multi_line_comments, list) and multi_line_comments:
        data["multiLineComments"] = multi_line_comments
    return data
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-serialize-codebase


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-serialize-system
def _system_to_registry_dict(system: object) -> dict:
    return {
        "name": str(getattr(system, "name", "")),
        "slug": str(getattr(system, "slug", "")),
        "kit": str(getattr(system, "kit", "")),
        "artifacts": [_artifact_to_registry_dict(artifact) for artifact in (getattr(system, "artifacts", []) or [])],
        "codebase": [_codebase_to_registry_dict(codebase) for codebase in (getattr(system, "codebase", []) or [])],
        "children": [_system_to_registry_dict(child) for child in (getattr(system, "children", []) or [])],
    }
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-serialize-system


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-expand-registry-context
def _expand_registry_with_context(adapter_dir: Path, registry: dict) -> dict:
    if "systems" not in registry:
        return registry
    try:
        from ..utils.context import StudioContext

        ctx = StudioContext.load(adapter_dir)
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("failed to expand registry with context from %s: %s", adapter_dir, exc)
        return registry
    if ctx is None:
        return registry
    meta = ctx.meta
    return {
        "version": str(getattr(meta, "version", "")),
        "project_root": str(getattr(meta, "project_root", "..")),
        "kits": {
            str(kid): {
                "format": str(getattr(kit, "format", "")),
                "path": str(getattr(kit, "path", "")),
            }
            for kid, kit in (getattr(meta, "kits", {}) or {}).items()
        },
        "ignore": [
            {
                "reason": str(getattr(block, "reason", "")),
                "patterns": list(getattr(block, "patterns", []) or []),
            }
            for block in (getattr(meta, "ignore", []) or [])
        ],
        "systems": [_system_to_registry_dict(system) for system in (getattr(meta, "systems", []) or [])],
    }
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-expand-registry-context


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-relative-adapter-path
def _relative_adapter_path(adapter_dir: Path, project_root: Path) -> str:
    try:
        return adapter_dir.relative_to(project_root).as_posix()
    except ValueError as exc:
        logger.warning("adapter dir %s is outside project root %s: %s", adapter_dir, project_root, exc)
        return adapter_dir.as_posix()
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-relative-adapter-path


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-has-config
def _has_config_file(adapter_dir: Path) -> bool:
    core_toml = adapter_dir / "config" / "core.toml"
    if not core_toml.is_file():
        core_toml = adapter_dir / "core.toml"
    return core_toml.exists()
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-has-config


# @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-collect-kit-entries
def _collect_kit_entries(core_data: Optional[dict]) -> dict:
    if not core_data or not isinstance(core_data.get("kits"), dict):
        return {}
    return {
        str(slug): entry if isinstance(entry, dict) else {}
        for slug, entry in core_data["kits"].items()
    }
# @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-collect-kit-entries


def _collect_kit_info(adapter_dir: Path, core_data: Optional[dict]) -> tuple[dict, dict]:
    kit_models: dict = {}
    kit_details: dict = {}
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-collect-kit-info
    for slug, core_kit in sorted(_collect_kit_entries(core_data).items()):
        kit_dir = _resolve_info_kit_root(adapter_dir, slug, core_kit)
        try:
            model_info, kit_detail = _kit_model_to_info(adapter_dir, slug, kit_dir, core_kit)
            kit_models[slug] = model_info
            kit_details[slug] = kit_detail
        except (OSError, ValueError) as exc:
            logger.warning("falling back to legacy kit info for %s at %s: %s", slug, kit_dir, exc)
            kit_details[slug] = _legacy_kit_detail(adapter_dir, slug, kit_dir, core_kit)
            if kit_details[slug]:
                kit_details[slug]["model_error"] = str(exc)
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-collect-kit-info
    return kit_models, kit_details


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-agent-integrations
def _collect_agent_integrations(project_root: Path) -> list[str]:
    from .agents import _ALL_RECOGNIZED_AGENTS, _is_agent_installed

    return [
        agent for agent in _ALL_RECOGNIZED_AGENTS
        if _is_agent_installed(agent, project_root)
    ]
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-agent-integrations


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-directory-status
def _collect_directory_status(adapter_dir: Path) -> dict:
    return {
        subdir: (adapter_dir / subdir).is_dir()
        for subdir in (".core", ".gen", "config")
    }
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-directory-status


def _apply_variables_metadata(
    config: dict,
    *,
    project_root: Path,
    adapter_dir: Path,
    core_data: Optional[dict],
    core_load_error: Optional[str],
) -> None:
    # @cpt-begin:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-info-load-variables
    if core_load_error is not None:
        config["variables"] = None
        config["variables_error"] = f"core.toml load failed: {core_load_error}"
        config["variables_degraded"] = True
        return
    try:
        from .resolve_vars import _collect_all_variables

        vars_result = _collect_all_variables(project_root, adapter_dir, core_data)
    except (ImportError, OSError, ValueError) as exc:
        logger.warning("failed to collect adapter info variables for %s: %s", adapter_dir, exc)
        config["variables"] = None
        config["variables_error"] = str(exc)
        config["variables_degraded"] = True
        return
    # @cpt-end:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-info-load-variables
    # @cpt-begin:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-info-store-variables
    config["variables"] = vars_result.get("variables", {})
    config["variables_by_kit"] = vars_result.get("kits", {})
    if vars_result.get("collisions"):
        config["variables_collisions"] = vars_result["collisions"]
    # @cpt-end:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-info-store-variables


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-workspace-source-details
def _workspace_source_details(ws_cfg: object, name: str, src: object) -> dict:
    if getattr(src, "url", None):
        from ..utils.git_utils import peek_git_source_path
        from ..utils.workspace import ResolveConfig

        workspace_file = getattr(ws_cfg, "workspace_file", None)
        base = getattr(ws_cfg, "resolution_base", None) or (workspace_file.parent if workspace_file else None)
        resolved = (
            peek_git_source_path(
                src,
                getattr(ws_cfg, "resolve", None) or ResolveConfig(),
                base,
            )
            if base
            else None
        )
    else:
        resolved = ws_cfg.resolve_source_path(name)
    return {
        "path": getattr(src, "path", None) or (_redact_url(getattr(src, "url")) if getattr(src, "url", None) else None),
        "role": getattr(src, "role", None),
        "reachable": resolved is not None and resolved.is_dir(),
    }
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-workspace-source-details


# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-load-workspace
def _load_workspace_info(project_root: Path) -> dict:
    try:
        from ..utils.workspace import find_workspace_config

        ws_cfg, ws_err = find_workspace_config(project_root)
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("failed to load workspace info for %s: %s", project_root, exc)
        return {"active": False, "error": str(exc)}
    if ws_cfg is None:
        workspace_info: dict = {"active": False}
        if ws_err:
            workspace_info["error"] = ws_err
        return workspace_info
    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-workspace-section
    return {
        "active": True,
        "version": ws_cfg.version,
        "is_inline": ws_cfg.is_inline,
        "location": "inline (core.toml)" if ws_cfg.is_inline else str(ws_cfg.workspace_file),
        "sources_count": len(ws_cfg.sources),
        "sources": {
            name: _workspace_source_details(ws_cfg, name, src)
            for name, src in ws_cfg.sources.items()
        },
    }
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-workspace-section
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-load-workspace


# @cpt-begin:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-info-render-variables
def _render_info_variables(data: dict) -> None:
    variables_by_kit = data.get("variables_by_kit") or {}
    if variables_by_kit:
        ui.blank()
        ui.step(f"Variables By Kit ({len(variables_by_kit)})")
        for slug, variables in sorted(variables_by_kit.items()):
            if not isinstance(variables, dict) or not variables:
                continue
            ui.substep(f"  {slug}:")
            for name, path in sorted(variables.items()):
                ui.substep(f"    {{{name}}}: {ui.relpath(path)}")
    if data.get("variables_degraded"):
        ui.blank()
        ui.warn(f"Variables: {data.get('variables_error', 'unknown error')}")
# @cpt-end:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-info-render-variables

def cmd_adapter_info(argv: list[str]) -> int:
    """Discover and display Constructor Studio project configuration."""
    start_path, studio_root_path = _parse_adapter_info_args(argv)

    project_root, adapter_dir = _discover_info_context(start_path, studio_root_path)
    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-if-no-root
    if project_root is None:
        return _emit_info_project_not_found(start_path)
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-if-no-root

    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-if-no-studio
    if adapter_dir is None:
        return _emit_info_studio_not_found(project_root)
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-if-no-studio

    config = _initialize_info_config(adapter_dir, project_root)

    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-load-registry-payload
    registry_path = _resolve_registry_path(adapter_dir)
    config["artifacts_registry_path"] = registry_path.as_posix()
    registry = _load_registry_data(registry_path)
    core_data, core_load_error, _core_path = _load_core_data_with_error(adapter_dir)
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-load-registry-payload
    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-registry-missing
    if registry is None:
        config["artifacts_registry"] = None
        if registry_path.exists():
            config["artifacts_registry_error"] = (
                "MISSING_OR_INVALID_TOML" if registry_path.suffix == ".toml" else "MISSING_OR_INVALID_JSON"
            )
        else:
            config["artifacts_registry_error"] = "MISSING"
        config["autodetect_registry"] = None
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-registry-missing
    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-expand-registry
    else:
        config["autodetect_registry"] = _extract_autodetect_registry(registry, core_data)
        config["artifacts_registry"] = _expand_registry_with_context(adapter_dir, registry)
        config["artifacts_registry_error"] = None
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-expand-registry

    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-compute-metadata
    config["relative_path"] = _relative_adapter_path(adapter_dir, project_root)
    config["has_config"] = _has_config_file(adapter_dir)
    if core_data and isinstance(core_data.get("version"), str):
        config["config_version"] = core_data["version"]
    config["kit_models"], config["kit_details"] = _collect_kit_info(adapter_dir, core_data)
    config["agent_integrations"] = _collect_agent_integrations(project_root)
    config["directories"] = _collect_directory_status(adapter_dir)
    _apply_variables_metadata(
        config,
        project_root=project_root,
        adapter_dir=adapter_dir,
        core_data=core_data,
        core_load_error=core_load_error,
    )
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-compute-metadata

    config["workspace"] = _load_workspace_info(project_root)

    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-return-ok
    ui.result(config, human_fn=_human_info)
    return 0
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-return-ok

# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-human-fmt
# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-render-kit-details
def _render_info_kit_details(kit_details: dict) -> None:
    if not kit_details:
        return
    ui.blank()
    ui.step(f"Kits ({len(kit_details)})")
    for slug, kit_detail in kit_details.items():
        name = kit_detail.get("name", slug)
        version = kit_detail.get("version", "?")
        ui.substep(f"  {name}  v{version}")

        content_dirs = kit_detail.get("content_dirs", [])
        if content_dirs:
            ui.substep(f"    Content: {', '.join(content_dirs)}")

        artifact_kinds = kit_detail.get("artifact_kinds", [])
        if artifact_kinds:
            ui.substep(f"    Artifact kinds ({len(artifact_kinds)}): {', '.join(artifact_kinds)}")

        workflows = kit_detail.get("workflows", [])
        if workflows:
            ui.substep(f"    Workflows: {', '.join(workflows)}")

        resources = kit_detail.get("resources", {})
        if resources:
            ui.substep(f"    Resources ({len(resources)}):")
            for resource_id, binding in resources.items():
                resource_path = binding.get("path", "?") if isinstance(binding, dict) else str(binding)
                ui.substep(f"      {resource_id}: {resource_path}")
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-render-kit-details


# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-render-systems
def _render_info_systems(data: dict) -> None:
    auto_reg = data.get("autodetect_registry") or {}
    systems = auto_reg.get("systems") or []
    registry = data.get("artifacts_registry")
    registry_systems = (registry.get("systems") or []) if isinstance(registry, dict) else []
    display_systems = registry_systems if registry_systems else systems
    if not display_systems:
        return
    ui.blank()
    ui.step(f"Systems ({len(display_systems)})")
    for sys_info in display_systems:
        if isinstance(sys_info, dict):
            _show_system_info(sys_info)
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-render-systems


# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-render-list
def _render_info_list(label: str, values: list) -> None:
    if not values:
        return
    ui.blank()
    ui.step(f"{label} ({len(values)})")
    for value in values:
        ui.substep(f"  {value}")
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-render-list


# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-render-workspace
def _render_info_workspace(workspace: dict) -> None:
    if workspace.get("active"):
        ui.blank()
        ui.step("Workspace")
        ui.substep(f"  Location: {workspace.get('location', '?')}")
        ui.substep(f"  Sources: {workspace.get('sources_count', 0)}")
        return
    if workspace.get("error"):
        ui.blank()
        ui.warn(f"Workspace: {workspace['error']}")
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-render-workspace


def _human_info(data: dict) -> None:
    """Human-friendly formatter for the info command."""
    ui.header("Constructor Studio Project Info")

    # Basic info
    if data.get("project_name"):
        ui.detail("Project", str(data["project_name"]))
    ui.detail("Project root", str(data.get("project_root", "?")))
    ui.detail("Adapter dir", str(data.get("relative_path", data.get("studio_dir", "?"))))
    if data.get("config_version"):
        ui.detail("Config version", str(data["config_version"]))

    # Directory structure health
    dirs = data.get("directories", {})
    if dirs:
        missing = [d for d, ok in dirs.items() if not ok]
        if missing:
            ui.warn(f"Missing directories: {', '.join(missing)}")

    _render_info_kit_details(data.get("kit_details", {}))
    _render_info_systems(data)
    _render_info_list("Rules", data.get("rules", []))
    agents = data.get("agent_integrations", [])
    if agents:
        ui.blank()
        ui.step(f"Agent integrations ({len(agents)})")
        ui.substep(f"  {', '.join(agents)}")

    _render_info_variables(data)

    _render_info_workspace(data.get("workspace", {}))

    reg_err = data.get("artifacts_registry_error")
    # @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-render-registry-warning
    if reg_err:
        ui.blank()
        ui.warn(f"Registry: {reg_err}")
    # @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-info-render-registry-warning

    ui.blank()
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-human-fmt
