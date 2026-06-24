"""Category resolution: override → registry → parent-dir.

@cpt-algo:cpt-studio-algo-map-categorize:p1
@cpt-algo:cpt-studio-algo-map-categorize-chain:p1
"""
from __future__ import annotations

import fnmatch
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from .model import Node

def _emit_warning(message: str) -> None:
    """Emit a warning to stderr via a dedicated logger handler."""
    # @cpt-begin:cpt-studio-algo-map-categorize:p1:inst-emit-warning
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(logging.Formatter("%(message)s"))
    category_logger = logging.getLogger(f"{__name__}.category_warning")
    category_logger.handlers = [stderr_handler]
    category_logger.setLevel(logging.WARNING)
    category_logger.propagate = False
    try:
        category_logger.warning("%s", message.rstrip("\n"))
    finally:
        stderr_handler.close()
    # @cpt-end:cpt-studio-algo-map-categorize:p1:inst-emit-warning


@dataclass(frozen=True)
class OverrideCategory:
    """Category override loaded from map configuration."""

    name: str
    paths: List[str]
    color: Optional[str]
    background: Optional[str]


@dataclass(frozen=True)
class OverrideConfig:
    """Collection of category overrides."""

    categories: List[OverrideCategory] = field(default_factory=list)
    show_uncategorized: bool = False


@dataclass(frozen=True)
class CategorizeOptions:
    """Inputs for resolving node categories."""

    project_root: Path
    override: Optional[OverrideConfig]
    # Per-source project roots for federation: source_name → absolute root Path.
    # When a node's source is found here, its source-specific artifacts.toml is
    # used for registry lookup instead of the primary project_root.
    source_roots: Optional[dict] = None  # Dict[str, Path]


def categorize_nodes(nodes: Sequence[Node], opts: CategorizeOptions) -> None:
    """Mutate nodes in place, filling .category and .category_origin."""
    # Build per-source registry indices (primary + any federated sources).
    source_roots: dict = dict(opts.source_roots or {})
    # Always include primary root under "local" (and as default).
    primary_index = _build_registry_index(opts.project_root)
    per_source_index: dict = {"local": primary_index}
    for src_name, src_root in source_roots.items():
        if src_name != "local":
            per_source_index[src_name] = _build_registry_index(src_root)

    # @cpt-begin:cpt-studio-algo-map-categorize:p1:inst-categorize-nodes
    for node in nodes:
        if node.kind == "phantom-cpt":
            node.category = "_undefined"
            node.category_origin = "phantom"
            continue
        rel_path = node.rel_path or ""
        override_category = _match_override(rel_path, opts.override) if opts.override is not None else None
        if override_category is not None:
            node.category = override_category
            node.category_origin = "override"
            continue
        registry_index = per_source_index.get(node.source or "local", primary_index)
        registry_category = _match_registry(rel_path, registry_index) if rel_path else None
        if registry_category is not None:
            node.category = registry_category
            node.category_origin = "registry"
            continue
        node.category = _parent_dir_category(rel_path)
        node.category_origin = "parent-dir"
    # @cpt-end:cpt-studio-algo-map-categorize:p1:inst-categorize-nodes


def _match_override(rel_path: str, override: OverrideConfig) -> Optional[str]:
    # @cpt-begin:cpt-studio-algo-map-categorize:p1:inst-match-override
    for cat in override.categories:
        for pat in cat.paths:
            if _glob_match(pat, rel_path):
                return cat.name
    return None
    # @cpt-end:cpt-studio-algo-map-categorize:p1:inst-match-override


def _glob_match(pattern: str, rel_path: str) -> bool:
    """Gitignore-style glob match: supports ** (multi-segment) and * (single-segment)."""
    # @cpt-begin:cpt-studio-algo-map-categorize:p1:inst-glob-match
    if "**" in pattern:
        regex_parts: List[str] = []
        i = 0
        while i < len(pattern):
            if pattern[i:i + 2] == "**":
                regex_parts.append(".*")
                i += 2
            elif pattern[i] == "*":
                regex_parts.append("[^/]*")
                i += 1
            elif pattern[i] == "?":
                regex_parts.append("[^/]")
                i += 1
            else:
                regex_parts.append(re.escape(pattern[i]))
                i += 1
        regex = "^" + "".join(regex_parts) + "$"
        return re.match(regex, rel_path) is not None
    return fnmatch.fnmatch(rel_path, pattern)
    # @cpt-end:cpt-studio-algo-map-categorize:p1:inst-glob-match


@dataclass(frozen=True)
class _RegistryEntry:
    path_prefix: str
    category: str


def _node_slug_path(system_node) -> str:
    """Build slash-joined slug from root to this node using parent chain."""
    # @cpt-begin:cpt-studio-algo-map-categorize:p1:inst-node-slug-path
    parts: List[str] = []
    node = system_node
    while node is not None:
        if node.slug:
            parts.append(node.slug)
        node = node.parent
    parts.reverse()
    return "/".join(parts)
    # @cpt-end:cpt-studio-algo-map-categorize:p1:inst-node-slug-path


def _load_registry_meta(project_root: Path):
    # @cpt-begin:cpt-studio-algo-map-categorize-chain:p1:inst-load-registry-meta
    from studio.utils.files import find_studio_directory, find_project_root, load_artifacts_registry
    from studio.utils.artifacts_meta import ArtifactsMeta

    detected_root = find_project_root(project_root)
    adapter_dir = (
        find_studio_directory(project_root) or project_root
        if detected_root is not None and detected_root.resolve() == project_root.resolve()
        else project_root
    )
    cfg, _err = load_artifacts_registry(adapter_dir)
    if cfg is None:
        return None
    return ArtifactsMeta.from_dict(cfg)
    # @cpt-end:cpt-studio-algo-map-categorize-chain:p1:inst-load-registry-meta


def _build_registry_index(project_root: Path) -> List[_RegistryEntry]:
    """Walk artifacts.toml and emit (path_prefix → category) entries, longest-first."""
    # @cpt-begin:cpt-studio-algo-map-categorize:p1:inst-build-registry-index
    # Guard: use adapter-resolution only when project_root is the actual VCS
    # root; fall back to the flat layout for fixture sub-directories so the
    # parent project's adapter is not picked up.
    try:
        meta = _load_registry_meta(project_root)
        if meta is None:
            return []
    except Exception as exc:  # pylint: disable=broad-exception-caught  # registry is optional; categorize must not raise
        _emit_warning(
            f"map: warning: registry category discovery failed for {project_root}: "
            f"{type(exc).__name__}: {exc}"
        )
        return []

    entries: List[_RegistryEntry] = []
    for collection in (meta.iter_all_artifacts(), meta.iter_all_codebase()):
        for item, sys_node in collection:
            item_path = getattr(item, "path", "")
            if not item_path:
                continue
            path = item_path.lstrip("./") if item_path.startswith("./") else item_path
            entries.append(_RegistryEntry(path_prefix=path, category=_node_slug_path(sys_node)))

    # Longest prefix first so more-specific entries win
    entries.sort(key=lambda e: -len(e.path_prefix))
    return entries
    # @cpt-end:cpt-studio-algo-map-categorize:p1:inst-build-registry-index


def _match_registry(rel_path: str, index: List[_RegistryEntry]) -> Optional[str]:
    # @cpt-begin:cpt-studio-algo-map-categorize:p1:inst-match-registry
    for e in index:
        prefix = e.path_prefix.rstrip("/")
        if rel_path == prefix or rel_path.startswith(prefix + "/"):
            return e.category
    return None
    # @cpt-end:cpt-studio-algo-map-categorize:p1:inst-match-registry


def _parent_dir_category(rel_path: str) -> str:
    # @cpt-begin:cpt-studio-algo-map-categorize:p1:inst-parent-dir-category
    parts = rel_path.split("/")
    if len(parts) <= 1:
        return "_root"
    return parts[-2]
    # @cpt-end:cpt-studio-algo-map-categorize:p1:inst-parent-dir-category
