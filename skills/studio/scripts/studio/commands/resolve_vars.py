"""
Resolve Variables Command — resolve template variables to absolute paths.

Reads kit resource bindings through the normalized KitModel service and resolves all template
variables (``{adr_template}``, ``{scripts}``, ``{cf-studio-path}``, etc.)
to absolute file paths.  Output is a flat dict suitable for
``str.format_map()`` substitution in Markdown files.

@cpt-flow:cpt-studio-flow-developer-experience-resolve-vars:p1
@cpt-dod:cpt-studio-dod-developer-experience-resolve-vars:p1
@cpt-algo:cpt-studio-algo-project-extensibility-resolve-layer-variables:p1
@cpt-algo:cpt-studio-algo-project-extensibility-deterministic-assembly:p1
"""

import argparse
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils._tomllib_compat import tomllib
from ..utils.files import (
    find_studio_directory,
    find_project_root,
)
from ..utils.manifest import (
    ComponentEntry,
    ManifestLayer,
    ManifestLayerState,
    apply_section_appends,
    resolve_resource_bindings_with_errors,
)
from ..utils.ui import ui

logger = logging.getLogger(__name__)


def _binding_rel_path_and_aliases(binding: object) -> Tuple[str | None, list[str]]:
    """Return a normalized binding path plus any aliases."""
    if isinstance(binding, dict):
        raw_path = binding.get("path")
        if not isinstance(raw_path, str):
            return None, []
        aliases = [
            alias.strip()
            for alias in binding.get("aliases", [])
            if isinstance(alias, str) and alias.strip()
        ] if isinstance(binding.get("aliases", []), list) else []
        return raw_path.strip() or None, aliases
    if isinstance(binding, str):
        return binding.strip() or None, []
    return None, []


def _binding_error_detail(binding_errors: list[object]) -> str:
    """Flatten binding resolution errors into a single message."""
    messages = [
        err.strip()
        for err in binding_errors
        if isinstance(err, str) and err.strip()
    ]
    messages.extend(
        str(err.get("message", "")).strip()
        for err in binding_errors
        if isinstance(err, dict) and str(err.get("message", "")).strip()
    )
    return "; ".join(msg for msg in messages if msg) or "unknown binding resolution error"


def _resolve_registered_kit_bindings(
    adapter_dir: Path,
    kit_slug: str,
) -> Dict[str, str]:
    """Resolve register-mode bindings and raise a readable error on failure."""
    bindings, binding_errors = resolve_resource_bindings_with_errors(
        adapter_dir / "config",
        kit_slug,
        adapter_dir,
    )
    if binding_errors:
        detail = _binding_error_detail(binding_errors)
        raise ValueError(f"Kit '{kit_slug}' resource binding resolution failed: {detail}")
    return {
        identifier: resolved_path.resolve().as_posix()
        for identifier, resolved_path in bindings.items()
    }


def _apply_binding_aliases(result: Dict[str, str], aliases: list[str], resolved_path: str) -> None:
    """Attach aliases for a resolved binding path."""
    for alias in aliases:
        result[alias] = resolved_path


def _merge_model_kit_variables(
    result: Dict[str, str],
    adapter_dir: Path,
    core_kit: dict,
    kit_slug: str,
) -> None:
    """Merge model-derived variables and aliases into the resolved map."""
    model_vars = _resolve_kit_variables_from_model(adapter_dir, core_kit, kit_slug)
    for var_name, var_path in model_vars.items():
        result.setdefault(var_name, var_path)

    model_aliases = _resolve_kit_aliases_from_model(adapter_dir, core_kit, kit_slug)
    for alias, resource_id in model_aliases.items():
        if resource_id in result:
            result.setdefault(alias, result[resource_id])


def _load_core_data_with_error(adapter_dir: Path) -> Tuple[Optional[dict], Optional[str], Optional[str]]:
    """Load core.toml from the modern or legacy location."""
    for core_path in (adapter_dir / "config" / "core.toml", adapter_dir / "core.toml"):
        if not core_path.is_file():
            continue
        try:
            with open(core_path, "rb") as handle:
                return tomllib.load(handle), None, str(core_path)
        except (tomllib.TOMLDecodeError, OSError) as exc:
            return None, f"{type(exc).__name__}: {exc}", str(core_path)
    return None, None, None


def _warn_optional_resolution(context: str, exc: Exception) -> None:
    """Report a best-effort resolve-vars fallback without aborting the command."""
    logger.warning("%s: %s: %s", context, type(exc).__name__, exc)


def _project_context_result(start_path: Path) -> Tuple[Optional[Path], Optional[Path], Optional[dict]]:
    """Discover the project root and Constructor Studio directory."""
    project_root = find_project_root(start_path)
    if project_root is None:
        return None, None, {
            "status": "ERROR",
            "message": "No project root found",
            "searched_from": start_path.as_posix(),
        }

    adapter_dir = find_studio_directory(start_path)
    if adapter_dir is None:
        return None, None, {
            "status": "ERROR",
            "message": "Constructor Studio not initialized in project",
            "project_root": project_root.as_posix(),
        }
    return project_root, adapter_dir, None


def _add_discovered_layer_variables(
    result: Dict[str, Any],
    project_root: Path,
    adapter_dir: Path,
) -> None:
    """Merge layer-discovery variables when available."""
    try:
        from ..utils.layer_discovery import discover_layers
        layers = discover_layers(project_root, adapter_dir)
        result["variables"] = add_layer_variables(result["variables"], layers, project_root)
    except (ValueError, OSError) as exc:
        logger.warning("layer discovery failed for %s: %s", project_root, exc)


def _filter_result_to_kit(result: Dict[str, Any], slug: str) -> Dict[str, Any]:
    """Return only the requested kit plus system and layer variables."""
    kit_section = result["kits"].get(slug)
    if kit_section is None:
        raise KeyError(slug)

    filtered_flat = dict(result["system"])
    for key, value in kit_section.items():
        filtered_flat.setdefault(key, value)

    all_kit_var_names = {
        key
        for kit_vars in result["kits"].values()
        for key in kit_vars
    }
    for key, value in result["variables"].items():
        if key not in filtered_flat and key not in all_kit_var_names:
            filtered_flat[key] = value
    return {
        "system": result["system"],
        "kits": {slug: kit_section},
        "variables": filtered_flat,
    }


def _emit_resolve_vars_output(result: Dict[str, Any], *, flat: bool) -> None:
    """Render resolve-vars output in either flat or structured mode."""
    if flat:
        flat_output: Dict[str, Any] = {"variables": result["variables"]}
        if result.get("collisions"):
            flat_output["collisions"] = result["collisions"]
        if result.get("core_load_error"):
            flat_output["core_load_error"] = result["core_load_error"]
        ui.result(flat_output, human_fn=_human_flat)
        return

    output = {
        "status": "OK",
        **result,
        "counts": _variable_counts(result),
    }
    ui.result(output, human_fn=_human_structured)


# @cpt-begin:cpt-studio-algo-developer-experience-resolve-vars:p1:inst-merge-flat-dict
def _merge_with_collision_tracking(
    system_vars: Dict[str, str],
    kit_vars: Dict[str, Dict[str, str]],
) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
    """Merge system and kit variables with unqualified names and collision tracking.

    Returns (flat_dict, collisions_list).
    """
    # @cpt-begin:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-no-kit-qualified
    flat: Dict[str, str] = dict(system_vars)
    # Kit slugs remain available in the structured `kits` output, but are not
    # valid placeholder prefixes in the flat variable map.
    # @cpt-end:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-no-kit-qualified

    # @cpt-begin:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-unqualified-unique
    collisions: List[Dict[str, str]] = []
    owners: Dict[str, str] = {k: "system" for k in system_vars}
    omitted: set[str] = set()
    for slug, kvars in kit_vars.items():
        for var_name, var_path in kvars.items():
            if var_name in omitted:
                continue
            if var_name in flat and flat[var_name] != var_path:
                collisions.append({
                    "variable": var_name,
                    "kit": slug,
                    "path": var_path,
                    "previous_kit": owners[var_name],
                    "previous_path": flat[var_name],
                })
                if owners[var_name] != "system":
                    flat.pop(var_name, None)
                omitted.add(var_name)
                continue
            flat[var_name] = var_path
            owners[var_name] = slug
    # @cpt-end:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-unqualified-unique
    return flat, collisions
# @cpt-end:cpt-studio-algo-developer-experience-resolve-vars:p1:inst-merge-flat-dict


# @cpt-begin:cpt-studio-algo-developer-experience-resolve-vars:p1:inst-resolve-binding-path
def _resolve_kit_variables(
    adapter_dir: Path,
    core_kit: dict,
    kit_slug: str = "",
) -> Dict[str, str]:
    """Resolve resource bindings for a single kit to absolute paths."""
    result: Dict[str, str] = {}
    resources = core_kit.get("resources")
    install_mode = str(core_kit.get("install_mode", "") or "").strip()
    if isinstance(resources, dict) and resources:
        for identifier, binding in resources.items():
            # @cpt-begin:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-resolve-binding
            rel_path, aliases = _binding_rel_path_and_aliases(binding)
            if rel_path is None:
                continue
            # @cpt-begin:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-effective-bindings
            resolved_path = (adapter_dir / rel_path).resolve().as_posix()
            result[identifier] = resolved_path
            # @cpt-end:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-effective-bindings
            # @cpt-begin:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-aliases
            _apply_binding_aliases(result, aliases, resolved_path)
            # @cpt-end:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-aliases
            # @cpt-end:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-resolve-binding
    elif kit_slug and install_mode == "register":
        # @cpt-begin:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-effective-bindings
        result.update(_resolve_registered_kit_bindings(adapter_dir, kit_slug))
        # @cpt-end:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-effective-bindings

    # @cpt-begin:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-effective-bindings
    _merge_model_kit_variables(result, adapter_dir, core_kit, kit_slug)
    # @cpt-end:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-effective-bindings
    # @cpt-begin:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-aliases
    # Alias merging is handled by _merge_model_kit_variables.
    # @cpt-end:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-aliases
    return result
# @cpt-end:cpt-studio-algo-developer-experience-resolve-vars:p1:inst-resolve-binding-path


# @cpt-begin:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-effective-bindings
def _resolve_core_kit_root(
    adapter_dir: Path,
    core_kit: dict,
    kit_slug: str,
) -> Optional[Path]:
    from ..commands.kit import _resolve_registered_kit_root_dir

    raw_path = core_kit.get("path") if isinstance(core_kit, dict) else ""
    if not isinstance(raw_path, str) or not raw_path.strip():
        if not kit_slug:
            return None
        raw_path = f"config/kits/{kit_slug}"
    return _resolve_registered_kit_root_dir(adapter_dir, raw_path.strip())
# @cpt-end:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-effective-bindings


# @cpt-begin:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-effective-bindings
def _resolve_kit_variables_from_model(
    adapter_dir: Path,
    core_kit: dict,
    kit_slug: str,
) -> Dict[str, str]:
    """Resolve kit variables through KitModel when an installed kit root exists."""
    kit_root = _resolve_core_kit_root(adapter_dir, core_kit, kit_slug)
    if kit_root is None or not kit_root.exists():
        return {}
    try:
        from ..utils.kit_model import load_installed_kit_model
        model = load_installed_kit_model(kit_root, core_kit, kit_slug=kit_slug)
    except (OSError, ValueError, KeyError) as exc:
        _warn_optional_resolution(
            f"failed to load kit model variables for kit '{kit_slug or '<unknown>'}' at {kit_root}",
            exc,
        )
        return {}

    result: Dict[str, str] = {}
    for resource in getattr(model, "resources", []):
        resource_id = str(getattr(resource, "id", "") or "").strip()
        source = str(getattr(resource, "source", "") or "").strip()
        if not resource_id or not source:
            continue
        resolved_path = (kit_root / source).resolve().as_posix()
        result[resource_id] = resolved_path
        for alias in getattr(resource, "aliases", []) or []:
            if isinstance(alias, str) and alias.strip():
                result[alias.strip()] = resolved_path
    return result
# @cpt-end:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-effective-bindings


# @cpt-begin:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-aliases
def _resolve_kit_aliases_from_model(
    adapter_dir: Path,
    core_kit: dict,
    kit_slug: str,
) -> Dict[str, str]:
    """Return alias -> resource_id mappings from KitModel metadata."""
    kit_root = _resolve_core_kit_root(adapter_dir, core_kit, kit_slug)
    if kit_root is None or not kit_root.exists():
        return {}
    try:
        from ..utils.kit_model import load_installed_kit_model
        model = load_installed_kit_model(kit_root, core_kit, kit_slug=kit_slug)
    except (OSError, ValueError, KeyError) as exc:
        _warn_optional_resolution(
            f"failed to load kit model aliases for kit '{kit_slug or '<unknown>'}' at {kit_root}",
            exc,
        )
        return {}

    aliases: Dict[str, str] = {}
    for resource in getattr(model, "resources", []):
        resource_id = str(getattr(resource, "id", "") or "").strip()
        if not resource_id:
            continue
        for alias in getattr(resource, "aliases", []) or []:
            if isinstance(alias, str) and alias.strip():
                aliases[alias.strip()] = resource_id
    return aliases
# @cpt-end:cpt-studio-algo-kit-variable-resolution:p1:inst-vars-aliases


def _collect_all_variables(
    project_root: Path,
    adapter_dir: Path,
    core_data: Optional[dict],
) -> Dict[str, Any]:
    """Collect all template variables from system config and kit resources.

    Returns a dict with:
    - ``system``: system-level variables (cf-path, project_root, etc.)
    - ``kits``: per-kit resource variables {slug: {var: path}}
    - ``variables``: flat merged dict of all variables for format_map()
    """
    # @cpt-begin:cpt-studio-algo-developer-experience-resolve-vars:p1:inst-collect-system-vars
    # @cpt-begin:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-system
    # -- System variables --
    # Canonical key is `cf-studio-path`; legacy aliases (`cf-path`,
    # `studio_path`, `studio-path`) point at the same value so older
    # markdown templates still resolve cleanly.
    adapter_posix = adapter_dir.resolve().as_posix()
    system_vars: Dict[str, str] = {
        "cf-studio-path": adapter_posix,
        "cf-path": adapter_posix,
        "studio_path": adapter_posix,
        "studio-path": adapter_posix,
        "project_root": project_root.resolve().as_posix(),
    }
    # @cpt-end:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-system
    # @cpt-end:cpt-studio-algo-developer-experience-resolve-vars:p1:inst-collect-system-vars

    # @cpt-begin:cpt-studio-algo-developer-experience-resolve-vars:p1:inst-extract-kit-resources
    # @cpt-begin:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-foreach-kit
    # -- Kit resource variables --
    kit_vars: Dict[str, Dict[str, str]] = {}
    if core_data and isinstance(core_data.get("kits"), dict):
        for slug, kit_entry in core_data["kits"].items():
            if not isinstance(kit_entry, dict):
                continue
            resolved = _resolve_kit_variables(
                adapter_dir, kit_entry, str(slug),
            )
            if resolved:
                kit_vars[slug] = resolved
    # @cpt-end:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-foreach-kit
    # @cpt-end:cpt-studio-algo-developer-experience-resolve-vars:p1:inst-extract-kit-resources

    # -- Flat merged dict (system + all kits) --
    flat, collisions = _merge_with_collision_tracking(system_vars, kit_vars)

    # @cpt-begin:cpt-studio-algo-developer-experience-resolve-vars:p1:inst-return-structured
    result: Dict[str, Any] = {
        "system": system_vars,
        "kits": kit_vars,
        "variables": flat,
    }
    if collisions:
        result["collisions"] = collisions
    return result
    # @cpt-end:cpt-studio-algo-developer-experience-resolve-vars:p1:inst-return-structured


def _variable_counts(result: Dict[str, Any]) -> Dict[str, Any]:
    system = result.get("system", {})
    kits = result.get("kits", {})
    flat = result.get("variables", {})
    system_names = set(system) if isinstance(system, dict) else set()
    kit_counts = {
        str(slug): len(kvars)
        for slug, kvars in kits.items()
        if isinstance(kvars, dict)
    }
    kit_variable_names = {
        key
        for kvars in kits.values()
        if isinstance(kvars, dict)
        for key in kvars
    }
    derived_count = sum(
        1
        for key in flat
        if key not in system_names and key not in kit_variable_names
    ) if isinstance(flat, dict) else 0
    total_resolved = (
        (len(system) if isinstance(system, dict) else 0)
        + sum(kit_counts.values())
        + derived_count
    )
    counts: Dict[str, Any] = {
        "system": len(system) if isinstance(system, dict) else 0,
        "kits": kit_counts,
        "derived": derived_count,
        "total_resolved": total_resolved,
    }
    return counts


# ---------------------------------------------------------------------------
# Layer Variables Assembly
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-project-extensibility-resolve-layer-variables:p1:inst-step1-start
def add_layer_variables(
    variables: Dict[str, str],
    layers: List[ManifestLayer],
    repo_root: Path,
) -> Dict[str, str]:
    """Extend *variables* with layer path variables derived from walk-up discovery.

    Layer variables:
    - ``base_dir``: outermost discovered layer root (master repo if found, else repo root)
    - ``master_repo``: master repo root path (empty string if no master repo)
    - ``repo``: current repo root path

    Layer variables do NOT override existing system/kit variables.

    Args:
        variables:  Existing flat variable dict from ``_collect_all_variables()``.
        layers:     Discovered ``ManifestLayer`` list (resolution order).
        repo_root:  Absolute path to the current repo root.

    Returns:
        New dict with layer path variables merged in (first-writer-wins).
    """
    # @cpt-begin:cpt-studio-algo-project-extensibility-resolve-layer-variables:p1:inst-step2-extract-paths
    # Derive master_repo and base_dir from the layer list.
    # A "master" scope layer carries the master repo root (its path is the
    # manifest file, so its parent is the master repo root directory).
    master_repo_path: str = ""
    for layer in layers:
        if layer.scope == "master" and layer.state == ManifestLayerState.LOADED:
            # layer.path is the manifest file; parent is the master repo root
            master_repo_path = layer.path.parent.as_posix()
            break
    # @cpt-end:cpt-studio-algo-project-extensibility-resolve-layer-variables:p1:inst-step2-extract-paths

    # @cpt-begin:cpt-studio-algo-project-extensibility-resolve-layer-variables:p1:inst-step3-resolve-paths
    repo_path = repo_root.resolve().as_posix()
    # base_dir is the outermost layer: master repo if present, else repo root
    base_dir_path = master_repo_path if master_repo_path else repo_path
    # @cpt-end:cpt-studio-algo-project-extensibility-resolve-layer-variables:p1:inst-step3-resolve-paths

    # @cpt-begin:cpt-studio-algo-project-extensibility-resolve-layer-variables:p1:inst-step4-merge
    # Build layer vars — use first-writer-wins: do NOT override existing vars
    layer_vars: Dict[str, str] = {
        "base_dir": base_dir_path,
        "master_repo": master_repo_path,
        "repo": repo_path,
    }
    result: Dict[str, str] = dict(variables)
    for key, val in layer_vars.items():
        if key not in result:
            result[key] = val
    # @cpt-end:cpt-studio-algo-project-extensibility-resolve-layer-variables:p1:inst-step4-merge

    # @cpt-begin:cpt-studio-algo-project-extensibility-resolve-layer-variables:p1:inst-step5-return
    return result
    # @cpt-end:cpt-studio-algo-project-extensibility-resolve-layer-variables:p1:inst-step5-return
# @cpt-end:cpt-studio-algo-project-extensibility-resolve-layer-variables:p1:inst-step1-start


def _apply_safe_vars(text: str, variables: dict) -> str:
    """Replace {key} placeholders without consuming literal {{ or }}.

    Unlike ``str.format_map()``, this only replaces known variable keys and
    leaves double-braces (used in JSON / template content) untouched.
    """
    if not variables:
        return text

    keys = [k for k in variables if k]
    if not keys:
        return text

    def _repl(m: re.Match) -> str:
        key = m.group(1)
        return variables.get(key, m.group(0))

    pattern = r"\{(" + "|".join(re.escape(k) for k in keys) + r")\}"
    return re.sub(pattern, _repl, text)


# @cpt-begin:cpt-studio-algo-project-extensibility-deterministic-assembly:p1:inst-step1-foreach
def assemble_component(
    component_id: str,
    source_content: str,
    layers: List[ComponentEntry],
    variables: Dict[str, str],
    _target: str,
    component_type: Optional[str] = None,
) -> str:
    """Deterministically assemble a component from merged data.

    Steps:
    1. Apply section appends from the pre-merged components list.
    2. Substitute ``{variable}`` references using ``str.format_map()``.

    The result is a pure function of inputs — no I/O, no timestamps,
    no randomness.

    Args:
        component_id:   ID of the component to assemble.
        source_content: Base source content (e.g. prompt file body).
        layers:         Already-merged ``ComponentEntry`` instances (from
                        ``MergedComponents``).  Each entry's ``.append`` field
                        contains accumulated layer appends.
        variables:      Flat variable dict for ``{var}`` substitution.
        target:         Target agent identifier (reserved for future filtering).
        component_type: Optional type hint (e.g. ``"agents"``, ``"skills"``) passed
                        to ``apply_section_appends()`` to avoid cross-type ID collisions.

    Returns:
        Assembled content string with appends applied and variables substituted.
    """
    # @cpt-begin:cpt-studio-algo-project-extensibility-deterministic-assembly:p1:inst-step1.1-load-source
    # Step 1.1: Start with source content
    composed = source_content
    # @cpt-end:cpt-studio-algo-project-extensibility-deterministic-assembly:p1:inst-step1.1-load-source

    # @cpt-begin:cpt-studio-algo-project-extensibility-deterministic-assembly:p1:inst-step1.2-apply-appends
    # Step 1.2: Apply section appends from pre-merged components
    composed = apply_section_appends(composed, layers, component_id, component_type=component_type)
    # @cpt-end:cpt-studio-algo-project-extensibility-deterministic-assembly:p1:inst-step1.2-apply-appends

    # @cpt-begin:cpt-studio-algo-project-extensibility-deterministic-assembly:p1:inst-step1.4-substitute
    # Step 1.4: Substitute {variable} references — use a regex-based replacer
    # that only touches known keys, leaving unknown keys and literal {{ / }}
    # (e.g. JSON or template content) intact.
    composed = _apply_safe_vars(composed, variables)
    # @cpt-end:cpt-studio-algo-project-extensibility-deterministic-assembly:p1:inst-step1.4-substitute

    # @cpt-begin:cpt-studio-algo-project-extensibility-deterministic-assembly:p1:inst-step1.6-return
    # Step 1.6: Return assembled content — caller handles I/O
    return composed
    # @cpt-end:cpt-studio-algo-project-extensibility-deterministic-assembly:p1:inst-step1.6-return
# @cpt-end:cpt-studio-algo-project-extensibility-deterministic-assembly:p1:inst-step1-foreach


def cmd_resolve_vars(argv: list[str]) -> int:
    """Resolve template variables to absolute paths."""
    # @cpt-begin:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-parse-args
    p = argparse.ArgumentParser(
        prog="resolve-vars",
        description="Resolve template variables to absolute paths",
    )
    p.add_argument(
        "--root", default=".",
        help="Project root to search from (default: current directory)",
    )
    p.add_argument(
        "--kit", default=None,
        help="Filter to a specific kit slug",
    )
    p.add_argument(
        "--flat", action="store_true",
        help="Output only the flat variables dict (default: structured output)",
    )
    args = p.parse_args(argv)

    start_path = Path(args.root).resolve()
    # @cpt-end:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-parse-args

    # @cpt-begin:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-discover
    # -- Discover project --
    project_root, adapter_dir, context_error = _project_context_result(start_path)
    if context_error is not None:
        ui.result(context_error)
        return 1
    # @cpt-end:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-discover

    # @cpt-begin:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-load-core
    # -- Load core.toml --
    core_data, core_load_error, core_path = _load_core_data_with_error(adapter_dir)
    if core_load_error and core_path:
        logger.warning("failed to parse %s: %s", core_path, core_load_error)
    # @cpt-end:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-load-core

    # @cpt-begin:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-merge
    # -- Resolve variables --
    try:
        result = _collect_all_variables(project_root, adapter_dir, core_data)
    except ValueError as exc:
        logger.exception("failed to resolve variables for %s", adapter_dir)
        # @cpt-begin:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-return
        ui.result({
            "status": "ERROR",
            "message": str(exc),
        })
        return 1
        # @cpt-end:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-return
    if core_load_error:
        result["core_load_error"] = core_load_error

    # -- Enrich with layer variables (base_dir, master_repo, repo) --
    _add_discovered_layer_variables(result, project_root, adapter_dir)
    # @cpt-end:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-merge

    # @cpt-begin:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-filter-kit
    # -- Filter by kit if requested --
    if args.kit:
        slug = args.kit
        try:
            result = _filter_result_to_kit(result, slug)
        except KeyError:
            logger.warning(
                "requested unknown kit '%s'; available kits: %s",
                slug,
                sorted(result["kits"].keys()),
            )
            ui.result({
                "status": "ERROR",
                "message": f"Kit '{slug}' not found or has no resource bindings",
                "available_kits": list(result["kits"].keys()),
            })
            return 1
    # @cpt-end:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-filter-kit

    # @cpt-begin:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-return
    # -- Output --
    _emit_resolve_vars_output(result, flat=args.flat)
    return 0
    # @cpt-end:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-return


# @cpt-begin:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-human-flat
def _human_flat(data: dict) -> None:
    """Human-friendly flat variable listing."""
    ui.header("Resolved Variables")
    variables = data.get("variables", data)
    for name, path in sorted(variables.items()):
        ui.detail(f"{{{name}}}", ui.relpath(path))
    ui.blank()
# @cpt-end:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-human-flat


# @cpt-begin:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-human-structured
def _human_structured(data: dict) -> None:
    """Human-friendly structured variable listing."""
    ui.header("Resolved Variables")

    # System variables
    system = data.get("system", {})
    counts = data.get("counts", {})
    if system:
        system_count = counts.get("system")
        if isinstance(system_count, int):
            ui.step(f"System ({system_count} variables)")
        else:
            ui.step("System")
        for name, path in sorted(system.items()):
            ui.detail(f"  {{{name}}}", ui.relpath(path))

    # Per-kit variables
    kits = data.get("kits", {})
    if kits:
        ui.blank()
        kit_counts = counts.get("kits", {}) if isinstance(counts, dict) else {}
        for slug, kvars in sorted(kits.items()):
            kit_count = kit_counts.get(slug) if isinstance(kit_counts, dict) else None
            if isinstance(kit_count, int):
                ui.step(f"Kit: {slug} ({kit_count} variables)")
            else:
                ui.step(f"Kit: {slug} ({len(kvars)} variables)")
            for name, path in sorted(kvars.items()):
                ui.detail(f"  {{{name}}}", ui.relpath(path))

    # Summary
    total_resolved = counts.get("total_resolved")
    ui.blank()
    if isinstance(total_resolved, int):
        ui.info(f"Total: {total_resolved} variables resolved")
    else:
        flat = data.get("variables", {})
        ui.info(f"Total: {len(flat)} variables resolved")
    ui.blank()
# @cpt-end:cpt-studio-flow-developer-experience-resolve-vars:p1:inst-resolve-vars-human-structured
