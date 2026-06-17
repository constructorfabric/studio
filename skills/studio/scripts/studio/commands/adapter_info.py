"""
Adapter Info Command — discover and display Constructor Studio project configuration.

Shows project root, studio directory, rules, systems, and registry status.

@cpt-flow:cpt-studio-flow-core-infra-cli-invocation:p1
@cpt-dod:cpt-studio-dod-core-infra-init-config:p1
"""

import argparse
import json
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

def _load_json_file(path: Path) -> Optional[dict]:
    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-load-json
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError, IOError):
        return None
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-load-json


def _show_system_artifacts(sys_info: dict) -> None:
    """Render artifacts for one system."""
    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-show-system-artifacts
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
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-show-system-artifacts


def _show_system_codebase(sys_info: dict, *, indent: str = "      ") -> None:
    """Render codebase entries for one system."""
    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-show-system-codebase
    for code_entry in sys_info.get("codebase") or []:
        if not isinstance(code_entry, dict):
            continue
        cpath = code_entry.get("path", "?")
        exts = code_entry.get("extensions") or []
        ext_str = f"  [{', '.join(exts)}]" if exts else ""
        ui.substep(f"{indent}{cpath}{ext_str}")
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-show-system-codebase


def _show_child_systems(sys_info: dict) -> None:
    """Render child system summaries."""
    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-show-child-systems
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
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-show-child-systems


def _show_system_info(sys_info: dict) -> None:
    """Render one system registry entry."""
    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-show-system-info
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
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-show-system-info


def _read_kit_conf(conf_path: Path) -> dict:
    """Read kit conf.toml and return key fields."""
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-read-kit-conf
    try:
        with open(conf_path, "rb") as f:
            data = tomllib.load(f)
        out: dict = {}
        for k in ("version", "slug", "name"):
            if k in data:
                out[k] = data[k]
        return out
    except (OSError, ValueError):
        return {}
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-read-kit-conf


def _resolve_info_kit_root(adapter_dir: Path, slug: str, core_kit: dict) -> Path:
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-resolve-kit-root
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

    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-collect-resources
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
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-collect-resources


def _kit_resource_to_info(resource: object, binding: object) -> dict:
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-resource-to-info
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


def _resolve_info_binding_path(adapter_dir: Path, raw_path: object) -> Optional[Path]:
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-resolve-binding-path
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    if os.name != "nt" and PureWindowsPath(raw_path).is_absolute():
        return None
    path = Path(raw_path)
    return path if path.is_absolute() else adapter_dir / path
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-resolve-binding-path


def _is_relative_to(path: Path, parent: Path) -> bool:
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-is-relative-to
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-is-relative-to


def _frontmatter_type(path: Path) -> str:
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-frontmatter-type
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
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


def _is_workflow_frontmatter_file(path: Path) -> bool:
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-is-workflow-frontmatter
    return path.is_file() and path.suffix.lower() == ".md" and _frontmatter_type(path) == "workflow"
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-is-workflow-frontmatter


def _legacy_workflow_names_from_component(kit_root: Path, component: object) -> list[str]:
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-workflows-deprecated
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

    missing_resources = []
    containment_violations = []
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

    stale_resources = sorted(bound_resource_ids - model_resource_ids)
    disabled_public_components = sorted(
        str(getattr(component, "id", ""))
        for component in getattr(model, "public_components", [])
        if str(getattr(component, "id", "")) in set(missing_resources)
    )
    drift_flags = [
        bool(missing_resources),
        bool(stale_resources),
        bool(containment_violations),
    ]
    status = "drifted" if any(drift_flags) else "unknown"
    containment_status = "contained"
    if containment_violations:
        containment_status = "external" if len(containment_violations) == len(model_resource_ids) else "mixed"
    return {
        "status": status,
        "install_mode": install_mode,
        "containment": {
            "status": containment_status,
            "violations": containment_violations,
        },
        "missing_resources": missing_resources,
        "stale_resources": stale_resources,
        "disabled_public_components": disabled_public_components,
    }
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-drift


def _kit_model_to_info(adapter_dir: Path, kit_slug: str, kit_root: Path, core_kit: dict) -> tuple[dict, dict]:
    """Return canonical kit model info plus legacy kit_details compatibility."""
    # @cpt-begin:cpt-studio-algo-kit-manifest-normalize:p1:inst-rollout-info
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-kitmodel-source
    from ..utils.kit_model import load_kit_model

    resource_bindings = _effective_info_resource_bindings(adapter_dir, kit_slug, core_kit)
    model = load_kit_model(kit_root)
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-kitmodel-source

    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-kitmodels-shape
    drift = _kit_model_drift(adapter_dir, model, core_kit, resource_bindings)
    # @cpt-begin:cpt-studio-algo-kit-update-drift-prune:p1:inst-update-disable-missing-public
    disabled_public_components = set(drift.get("disabled_public_components", []))
    # @cpt-end:cpt-studio-algo-kit-update-drift-prune:p1:inst-update-disable-missing-public
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
            {
                "id": component.id,
                "kind": component.kind,
                "source": component.source,
                "generated_name": component.generated_name,
                "generated_targets": component.generated_targets,
                "aliases": component.aliases,
                "origin": component.origin,
                "disabled": component.id in disabled_public_components,
            }
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
    content_dirs = sorted(
        d.name for d in kit_root.iterdir()
        if d.is_dir() and d.name in ("artifacts", "codebase", "scripts", "workflows")
    ) if kit_root.is_dir() else []
    if content_dirs:
        kd["content_dirs"] = content_dirs
    art_dir = kit_root / "artifacts"
    if art_dir.is_dir():
        kd["artifact_kinds"] = sorted(d.name for d in art_dir.iterdir() if d.is_dir())
    wf_dir = kit_root / "workflows"
    if wf_dir.is_dir():
        kd["workflows"] = sorted(f.stem for f in wf_dir.iterdir() if _is_workflow_frontmatter_file(f))
    resource_bindings = _effective_info_resource_bindings(adapter_dir, slug, core_kit)
    if resource_bindings:
        kd["resources"] = resource_bindings
    return kd

def cmd_adapter_info(argv: list[str]) -> int:
    """Discover and display Constructor Studio project configuration."""
    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-parse-args
    p = argparse.ArgumentParser(prog="info", description="Discover Constructor Studio project configuration")
    p.add_argument("--root", default=".", help="Project root to search from (default: current directory)")
    p.add_argument(
        "--cf-studio-root",
        "--cf-root",
        "--cf-constructor-root",
        dest="cf_studio_root",
        default=None,
        help="Constructor Studio core location (if agent knows it). Legacy aliases: --cf-root, --cf-constructor-root.",
    )
    args = p.parse_args(argv)

    start_path = Path(args.root).resolve()
    studio_root_path = Path(args.cf_studio_root).resolve() if args.cf_studio_root else None
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-parse-args

    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-find-root
    project_root = find_project_root(start_path)
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-find-root
    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-if-no-root
    if project_root is None:
        # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-return-no-root
        ui.result({
            "status": "NOT_FOUND",
            "message": "No project root found (no AGENTS.md with @cf:root-agents or .git)",
            "searched_from": start_path.as_posix(),
            "hint": "Run 'cfs init' in your project root",
        })
        return 1
        # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-return-no-root
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-if-no-root

    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-find-studio
    adapter_dir = find_studio_directory(start_path, studio_root=studio_root_path)
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-find-studio
    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-if-no-studio
    if adapter_dir is None:
        # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-return-no-studio
        ui.result({
            "status": "NOT_FOUND",
            "message": "Constructor Studio not initialized in project",
            "project_root": project_root.as_posix(),
            "hint": "Run 'cfs init' to initialize Constructor Studio for this project",
        })
        return 1
        # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-return-no-studio
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-if-no-studio

    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-load-config
    config = load_studio_config(adapter_dir)
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-load-config
    config["status"] = "FOUND"
    config["project_root"] = project_root.as_posix()

    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-locate-registry
    registry_path = (adapter_dir / "config" / "artifacts.toml").resolve()
    # Fallback: legacy flat layout
    if not registry_path.is_file():
        registry_path = (adapter_dir / "artifacts.toml").resolve()
    if not registry_path.is_file():
        legacy = adapter_dir / "artifacts.json"
        if legacy.is_file():
            registry_path = legacy.resolve()
    config["artifacts_registry_path"] = registry_path.as_posix()
    registry = _load_json_file(registry_path) if registry_path.suffix == ".json" else None
    if registry is None and registry_path.suffix == ".toml" and registry_path.is_file():
        try:
            with open(registry_path, "rb") as f:
                registry = tomllib.load(f)
        except (OSError, ValueError):
            registry = None
    # Load core.toml for version/project_root/kits (authoritative source)
    core_data: Optional[dict] = None
    core_load_error: Optional[str] = None
    for cp in [(adapter_dir / "config" / "core.toml"), (adapter_dir / "core.toml")]:
        if cp.is_file():
            try:
                with open(cp, "rb") as f:
                    core_data = tomllib.load(f)
            except (tomllib.TOMLDecodeError, OSError) as exc:
                core_load_error = f"{type(exc).__name__}: {exc}"
            break

    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-locate-registry
    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-registry-missing
    if registry is None:
        config["artifacts_registry"] = None
        config["artifacts_registry_error"] = "MISSING_OR_INVALID_JSON" if registry_path.exists() else "MISSING"
        config["autodetect_registry"] = None
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-registry-missing
    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-expand-registry
    else:
        def _extract_autodetect_registry(raw: object, core: Optional[dict]) -> Optional[dict]:
            if not isinstance(raw, dict):
                return None
            if "systems" not in raw:
                return None

            def _extract_system(s: object) -> dict:
                if not isinstance(s, dict):
                    return {}
                out: dict = {}
                for k in ("name", "slug", "kit"):
                    v = s.get(k)
                    if isinstance(v, str):
                        out[k] = v
                if isinstance(s.get("autodetect"), list):
                    out["autodetect"] = s.get("autodetect")
                if isinstance(s.get("children"), list):
                    out["children"] = [_extract_system(ch) for ch in (s.get("children") or [])]
                else:
                    out["children"] = []
                return out

            # version/project_root/kits: prefer core.toml, fallback to registry
            version = raw.get("version")
            p_root = raw.get("project_root")
            kits = raw.get("kits")
            if isinstance(core, dict):
                if version is None and isinstance(core.get("version"), str):
                    version = core["version"]
                if p_root is None and isinstance(core.get("project_root"), str):
                    p_root = core["project_root"]
                if (not kits) and isinstance(core.get("kits"), dict):
                    kits = core["kits"]

            return {
                "version": version,
                "project_root": p_root,
                "kits": kits,
                "ignore": raw.get("ignore"),
                "systems": [_extract_system(s) for s in (raw.get("systems") or [])],
            }

        config["autodetect_registry"] = _extract_autodetect_registry(registry, core_data)

        expanded: object = registry
        if isinstance(registry, dict) and "systems" in registry:
            try:
                from ..utils.context import StudioContext

                ctx = StudioContext.load(adapter_dir)
                if ctx is not None:
                    meta = ctx.meta

                    def _artifact_to_dict(a: object) -> dict:
                        return {
                            "path": str(getattr(a, "path", "")),
                            "kind": str(getattr(a, "kind", getattr(a, "type", ""))),
                            "traceability": str(getattr(a, "traceability", "DOCS-ONLY")),
                        }

                    def _codebase_to_dict(c: object) -> dict:
                        d = {
                            "path": str(getattr(c, "path", "")),
                        }
                        exts = getattr(c, "extensions", None)
                        if isinstance(exts, list) and exts:
                            d["extensions"] = [str(x) for x in exts if isinstance(x, str)]
                        nm = getattr(c, "name", None)
                        if isinstance(nm, str) and nm.strip():
                            d["name"] = nm
                        slc = getattr(c, "single_line_comments", None)
                        if isinstance(slc, list) and slc:
                            d["singleLineComments"] = slc
                        mlc = getattr(c, "multi_line_comments", None)
                        if isinstance(mlc, list) and mlc:
                            d["multiLineComments"] = mlc
                        return d

                    def _system_to_dict(s: object) -> dict:
                        out = {
                            "name": str(getattr(s, "name", "")),
                            "slug": str(getattr(s, "slug", "")),
                            "kit": str(getattr(s, "kit", "")),
                            "artifacts": [_artifact_to_dict(a) for a in (getattr(s, "artifacts", []) or [])],
                            "codebase": [_codebase_to_dict(c) for c in (getattr(s, "codebase", []) or [])],
                            "children": [],
                        }
                        out["children"] = [_system_to_dict(ch) for ch in (getattr(s, "children", []) or [])]
                        return out

                    expanded = {
                        "version": str(getattr(meta, "version", "")),
                        "project_root": str(getattr(meta, "project_root", "..")),
                        "kits": {
                            str(kid): {
                                "format": str(getattr(k, "format", "")),
                                "path": str(getattr(k, "path", "")),
                            }
                            for kid, k in (getattr(meta, "kits", {}) or {}).items()
                        },
                        "ignore": [
                            {
                                "reason": str(getattr(blk, "reason", "")),
                                "patterns": list(getattr(blk, "patterns", []) or []),
                            }
                            for blk in (getattr(meta, "ignore", []) or [])
                        ],
                        "systems": [_system_to_dict(s) for s in (getattr(meta, "systems", []) or [])],
                    }
            except (OSError, ValueError, KeyError):
                expanded = registry

        config["artifacts_registry"] = expanded
        config["artifacts_registry_error"] = None
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-expand-registry

    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-compute-metadata
    try:
        relative_path = adapter_dir.relative_to(project_root).as_posix()
    except ValueError:
        relative_path = adapter_dir.as_posix()
    config["relative_path"] = relative_path

    core_toml = adapter_dir / "config" / "core.toml"
    if not core_toml.is_file():
        core_toml = adapter_dir / "core.toml"
    config["has_config"] = core_toml.exists()

    # Core config version
    if core_data and isinstance(core_data.get("version"), str):
        config["config_version"] = core_data["version"]

    # Kit details: canonical model output plus legacy compatibility.
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-kitmodel-source
    kit_models = {}
    # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-kitdetails-derived
    kit_details = {}
    kit_entries: dict = {}
    if core_data and isinstance(core_data.get("kits"), dict):
        kit_entries.update({
            str(slug): entry if isinstance(entry, dict) else {}
            for slug, entry in core_data["kits"].items()
        })

    for slug in sorted(kit_entries):
        core_kit = kit_entries[slug]
        kit_dir = _resolve_info_kit_root(adapter_dir, slug, core_kit)
        try:
            model_info, kit_detail = _kit_model_to_info(adapter_dir, slug, kit_dir, core_kit)
            kit_models[slug] = model_info
            kit_details[slug] = kit_detail
        except (OSError, ValueError) as exc:
            kit_details[slug] = _legacy_kit_detail(adapter_dir, slug, kit_dir, core_kit)
            if kit_details[slug]:
                kit_details[slug]["model_error"] = str(exc)
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-kitdetails-derived
    # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-kitmodel-source
    config["kit_models"] = kit_models
    config["kit_details"] = kit_details

    # Agent integrations — detect via shared _is_agent_installed() which checks
    # Constructor Studio-specific markers and legacy fallbacks per agent.
    from .agents import _ALL_RECOGNIZED_AGENTS, _is_agent_installed
    agents_found = [
        agent for agent in _ALL_RECOGNIZED_AGENTS
        if _is_agent_installed(agent, project_root)
    ]
    config["agent_integrations"] = agents_found

    # Directory structure health
    dirs_status = {}
    for subdir in [".core", ".gen", "config"]:
        d = adapter_dir / subdir
        dirs_status[subdir] = d.is_dir()
    config["directories"] = dirs_status

    # Resolved template variables (flat dict for format_map substitution)
    if core_load_error is not None:
        config["variables"] = None
        config["variables_error"] = f"core.toml load failed: {core_load_error}"
        config["variables_degraded"] = True
    else:
        try:
            from .resolve_vars import _collect_all_variables
            vars_result = _collect_all_variables(project_root, adapter_dir, core_data)
            config["variables_by_kit"] = vars_result.get("kits", {})
            if vars_result.get("collisions"):
                config["variables_collisions"] = vars_result["collisions"]
        except (ImportError, OSError, ValueError) as exc:
            config["variables"] = None
            config["variables_error"] = str(exc)
            config["variables_degraded"] = True
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-compute-metadata

    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-workspace-section
    # Add workspace section when workspace detected
    try:
        from ..utils.workspace import find_workspace_config

        ws_cfg, ws_err = find_workspace_config(project_root)
        if ws_cfg is not None:
            ws_info: dict = {
                "active": True,
                "version": ws_cfg.version,
                "is_inline": ws_cfg.is_inline,
                "location": "inline (core.toml)" if ws_cfg.is_inline else str(ws_cfg.workspace_file),
                "sources_count": len(ws_cfg.sources),
                "sources": {},
            }
            for name, src in ws_cfg.sources.items():
                if src.url:
                    # For URL sources, peek at expected cache path without cloning
                    from ..utils.git_utils import peek_git_source_path
                    from ..utils.workspace import ResolveConfig
                    base = ws_cfg.resolution_base or (ws_cfg.workspace_file.parent if ws_cfg.workspace_file else None)
                    resolved = peek_git_source_path(src, ws_cfg.resolve or ResolveConfig(), base) if base else None
                    reachable = resolved is not None and resolved.is_dir()
                else:
                    resolved = ws_cfg.resolve_source_path(name)
                    reachable = resolved is not None and resolved.is_dir()
                ws_info["sources"][name] = {
                    "path": src.path or (_redact_url(src.url) if src.url else None),
                    "role": src.role,
                    "reachable": reachable,
                }
            config["workspace"] = ws_info
        else:
            ws_data: dict = {"active": False}
            if ws_err:
                ws_data["error"] = ws_err
            config["workspace"] = ws_data
    except (OSError, ValueError, KeyError) as exc:
        config["workspace"] = {"active": False, "error": str(exc)}
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-workspace-section

    # @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-return-ok
    ui.result(config, human_fn=_human_info)
    return 0
    # @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-return-ok

# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-info-human-fmt
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

    # Kit details
    kit_details = data.get("kit_details", {})
    if kit_details:
        ui.blank()
        ui.step(f"Kits ({len(kit_details)})")
        for slug, kd in kit_details.items():
            name = kd.get("name", slug)
            ver = kd.get("version", "?")
            ui.substep(f"  {name}  v{ver}")

            cdirs = kd.get("content_dirs", [])
            if cdirs:
                ui.substep(f"    Content: {', '.join(cdirs)}")

            kinds = kd.get("artifact_kinds", [])
            if kinds:
                ui.substep(f"    Artifact kinds ({len(kinds)}): {', '.join(kinds)}")

            wfs = kd.get("workflows", [])
            if wfs:
                ui.substep(f"    Workflows: {', '.join(wfs)}")

            res = kd.get("resources", {})
            if res:
                ui.substep(f"    Resources ({len(res)}):")
                for rid, rbind in res.items():
                    rpath = rbind.get("path", "?") if isinstance(rbind, dict) else str(rbind)
                    ui.substep(f"      {rid}: {rpath}")

    # Systems with artifacts
    auto_reg = data.get("autodetect_registry") or {}
    systems = auto_reg.get("systems") or []
    reg = data.get("artifacts_registry")
    reg_systems = (reg.get("systems") or []) if isinstance(reg, dict) else []

    if systems or reg_systems:
        ui.blank()
        display_systems = reg_systems if reg_systems else systems
        ui.step(f"Systems ({len(display_systems)})")
        for sys_info in display_systems:
            if not isinstance(sys_info, dict):
                continue
            _show_system_info(sys_info)

    # Rules
    rules = data.get("rules", [])
    if rules:
        ui.blank()
        ui.step(f"Rules ({len(rules)})")
        for r in rules:
            ui.substep(f"  {r}")

    # Agent integrations
    agents = data.get("agent_integrations", [])
    if agents:
        ui.blank()
        ui.step(f"Agent integrations ({len(agents)})")
        ui.substep(f"  {', '.join(agents)}")

    # @cpt-begin:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-info-render-variables
    # Resolved variables
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

    # Workspace
    ws = data.get("workspace", {})
    if ws.get("active"):
        ui.blank()
        ui.step("Workspace")
        ui.substep(f"  Location: {ws.get('location', '?')}")
        ui.substep(f"  Sources: {ws.get('sources_count', 0)}")
    elif ws.get("error"):
        ui.blank()
        ui.warn(f"Workspace: {ws['error']}")

    # Registry errors
    reg_err = data.get("artifacts_registry_error")
    if reg_err:
        ui.blank()
        ui.warn(f"Registry: {reg_err}")

    ui.blank()
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-info-human-fmt
