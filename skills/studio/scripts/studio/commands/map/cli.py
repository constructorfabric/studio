"""cfs map CLI entry point.

@cpt-flow:cpt-studio-flow-map-cli:p1
@cpt-dod:cpt-studio-dod-dependency-mapping-graph:p1
@cpt-state:cpt-studio-state-dependency-map:p1
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from studio.utils._tomllib_compat import tomllib

from .categorize import (
    CategorizeOptions, OverrideCategory, OverrideConfig, categorize_nodes,
)
from .cpt_edges import build_cpt_edges
from .enrich import enrich_edges
from .layout import compute_layout
from .links import extract_file_links
from .render_html import RenderHtmlInput, render_html
from .render_json import RenderJsonInput, render_json
from .scan import ScanOptions, _OPTIONAL_MAP_DISCOVERY_ERRORS, scan_repo

def _emit_stdout(message: str) -> None:
    """Emit user-facing map output to stdout without altering existing text."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    emit_logger = logging.getLogger(f"{__name__}.summary")
    emit_logger.handlers = [handler]
    emit_logger.setLevel(logging.INFO)
    emit_logger.propagate = False
    try:
        emit_logger.log(logging.INFO, "%s", message.rstrip("\n"))
    finally:
        handler.close()


def _emit_stderr(message: str, level: int = logging.WARNING) -> None:
    """Emit diagnostics to stderr via a dedicated logger handler."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    emit_logger = logging.getLogger(f"{__name__}.stderr")
    emit_logger.handlers = [handler]
    emit_logger.setLevel(level)
    emit_logger.propagate = False
    try:
        emit_logger.log(level, "%s", message.rstrip("\n"))
    finally:
        handler.close()


def _build_map_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cfs map",
        description="Build an interactive markdown↔source map via cpt identifiers.",
    )
    parser.add_argument("--out", default=None)
    parser.add_argument("--format", choices=["html", "json"], default="html")
    parser.add_argument("--config", default=None)
    parser.add_argument("--no-source", action="store_true")
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--inline-data", action="store_true")
    parser.add_argument(
        "--include-adapter",
        action="store_true",
        help="Scan inside the cf / studio adapter directory too. "
             "Useful when markdown references {cf-studio-path}/... paths that "
             "should resolve to nodes in the graph.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def _collect_nodes_for_sources(sources: List[dict], args) -> tuple[list, Dict[str, Path]]:
    all_nodes = []
    project_root_by_source: Dict[str, Path] = {}
    for source in sources:
        if not source["reachable"]:
            continue
        src_root = Path(source["path"]).resolve()
        opts = ScanOptions(
            project_root=src_root,
            source_name=source["name"],
            no_source=args.no_source,
            include_adapter=args.include_adapter,
        )
        all_nodes.extend(scan_repo(opts))
        project_root_by_source[source["name"]] = src_root
    return all_nodes, project_root_by_source


def _apply_override_filter(all_nodes, override) -> list:
    if override is None:
        return all_nodes
    if override.show_uncategorized:
        for node in all_nodes:
            if node.category_origin != "override":
                node.category = "_uncategorized"
                node.category_origin = "uncategorized-bucket"
        return all_nodes
    if not override.categories:
        _emit_stderr(
            "map: override config has zero categories and show_uncategorized=false;"
            " result will be empty"
        )
    return [node for node in all_nodes if node.category_origin == "override"]


def _apply_phantom_override(nodes_all, edges, override):
    if override is None:
        return nodes_all, edges
    if override.show_uncategorized:
        for node in nodes_all:
            if node.category_origin == "phantom":
                node.category = "_uncategorized"
                node.category_origin = "uncategorized-bucket"
        return nodes_all, edges
    filtered_nodes = [node for node in nodes_all if node.category_origin == "override"]
    node_ids = {node.id for node in filtered_nodes}
    filtered_edges = [edge for edge in edges if edge.from_id in node_ids and edge.to_id in node_ids]
    return filtered_nodes, filtered_edges


def _category_styles_from_override(override: Optional[OverrideConfig]) -> dict:
    category_styles = {}
    if override is None:
        return category_styles
    for category in override.categories:
        if category.color is None:
            continue
        entry: dict = {"color": category.color}
        if category.background is not None:
            entry["background"] = category.background
        category_styles[category.name] = entry
    return category_styles


def _write_map_output(args, out_path: Path, json_payload: str):
    sidecar_path = None
    if args.format == "json":
        out_path.write_text(json_payload, encoding="utf-8")
        return sidecar_path
    html, sidecar_js = render_html(RenderHtmlInput(
        json_payload=json_payload,
        inline_data=args.inline_data,
        sidecar_basename=out_path.name + ".js",
    ))
    out_path.write_text(html, encoding="utf-8")
    if sidecar_js is not None:
        sidecar_path = out_path.with_name(out_path.name + ".js")
        sidecar_path.write_text(sidecar_js, encoding="utf-8")
    return sidecar_path


def _build_map_graph(primary_root: Path, args, sources: List[dict], override):
    all_nodes, project_root_by_source = _collect_nodes_for_sources(sources, args)
    categorize_nodes(all_nodes, CategorizeOptions(
        project_root=primary_root,
        override=override,
        source_roots=project_root_by_source,
    ))
    filtered_nodes = _apply_override_filter(all_nodes, override)
    template_vars = _load_template_vars(primary_root)
    file_edges = extract_file_links(
        filtered_nodes, project_root=primary_root, template_vars=template_vars,
    )
    cpt_edges, phantoms = build_cpt_edges(filtered_nodes)
    nodes_all, edges = _apply_phantom_override(
        list(filtered_nodes) + list(phantoms),
        list(file_edges) + list(cpt_edges),
        override,
    )
    enrich_edges(edges, nodes_all, project_root_by_source=project_root_by_source)
    return nodes_all, edges, project_root_by_source


def _build_scan_meta(primary_root: Path, art_toml: Optional[Path], adapter_dir: Optional[Path]) -> dict:
    return {
        "artifacts_toml": str(art_toml.relative_to(primary_root)) if art_toml is not None else None,
        "systems_scanned": _count_systems(adapter_dir),
        "systems_docs_only": _count_systems(adapter_dir, docs_only=True),
        "skip_dirs": sorted(skip_dirs_for_meta(primary_root)),
    }


def _render_map_json_payload(
    nodes_all,
    edges,
    sources,
    scan_meta,
    vis_nodes,
    bucket_rects,
    category_bands,
    override,
) -> str:
    category_styles = _category_styles_from_override(override)
    return render_json(RenderJsonInput(
        nodes=nodes_all,
        edges=edges,
        workspace={"primary": "local", "sources": sources},
        scan=scan_meta,
        vis_nodes=vis_nodes,
        bucket_rects=bucket_rects,
        category_bands=category_bands,
        category_styles=category_styles or None,
    ))


def _resolve_map_paths(args) -> tuple[Path, Path]:
    cwd = Path.cwd().resolve()
    out_path = Path(args.out).resolve() if args.out else cwd / f"md-map.{args.format}"
    return cwd, out_path


def _resolve_map_scan_meta(primary_root: Path) -> dict:
    art_toml, adapter_dir = _resolve_artifacts_toml(primary_root)
    if art_toml is None:
        _emit_stderr(
            "map: no artifacts.toml found via adapter resolution; source scanning disabled"
        )
    return _build_scan_meta(primary_root, art_toml, adapter_dir)


def _warn_optional_discovery(context: str, exc: Exception) -> None:
    """Report a best-effort map discovery failure without aborting the command."""
    _emit_stderr(f"map: warning: {context}: {type(exc).__name__}: {exc}")


def cmd_map(argv: List[str]) -> int:
    """Run the map command."""
    # @cpt-begin:cpt-studio-flow-map-cli:p1:inst-cmd-map
    args = _build_map_parser().parse_args(argv)

    primary_root, out_path = _resolve_map_paths(args)

    sources = _discover_sources(primary_root, local_only=args.local_only)
    override = _load_override(primary_root, args.config)

    # @cpt-begin:cpt-studio-flow-map-cli:p1:inst-collect-nodes
    nodes_all, edges, _project_root_by_source = _build_map_graph(primary_root, args, sources, override)
    # @cpt-end:cpt-studio-flow-map-cli:p1:inst-collect-nodes

    # @cpt-begin:cpt-studio-flow-map-cli:p1:inst-layout-render
    vis_nodes, bucket_rects, category_bands = compute_layout(
        nodes_all, edges, category_style=None, verbose=args.verbose,
    )

    scan_meta = _resolve_map_scan_meta(primary_root)
    json_payload = _render_map_json_payload(
        nodes_all, edges, sources, scan_meta, vis_nodes, bucket_rects, category_bands, override,
    )

    sidecar_path = _write_map_output(args, out_path, json_payload)

    _print_summary(scan_meta, sources, nodes_all, edges, out_path, sidecar_path, args.config)
    # @cpt-end:cpt-studio-flow-map-cli:p1:inst-layout-render
    return 0
    # @cpt-end:cpt-studio-flow-map-cli:p1:inst-cmd-map


def _discover_sources(primary_root: Path, local_only: bool) -> List[dict]:
    # @cpt-begin:cpt-studio-flow-map-cli:p1:inst-discover-sources
    sources: List[dict] = [
        {"name": "local", "path": str(primary_root), "reachable": True, "role": "full"}
    ]
    if local_only:
        return sources
    # Best-effort federation discovery via find_workspace_config.
    # Federation is fully exercised in Task 14; here we just do a graceful attempt.
    try:
        from studio.utils.workspace import find_workspace_config
        ws, _err = find_workspace_config(primary_root)
        if ws is None:
            return sources
        for name, src_entry in ws.sources.items():
            resolved = ws.resolve_source_path(name)
            if resolved is None:
                continue
            reachable = resolved.is_dir()
            sources.append({
                "name": name,
                "path": str(resolved),
                "reachable": reachable,
                "role": src_entry.role,
            })
    except _OPTIONAL_MAP_DISCOVERY_ERRORS as exc:  # pragma: no cover
        _warn_optional_discovery("workspace source discovery failed", exc)
    return sources
    # @cpt-end:cpt-studio-flow-map-cli:p1:inst-discover-sources


def _load_override(primary_root: Path, explicit: Optional[str]) -> Optional[OverrideConfig]:
    # @cpt-begin:cpt-studio-flow-map-cli:p1:inst-load-override
    if explicit:
        path = Path(explicit).resolve()
    else:
        candidate = primary_root / "md-map.toml"
        if not candidate.exists():
            return None
        path = candidate
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, ValueError) as exc:  # override config validation
        _emit_stderr(f"map: invalid {path}: {exc}", level=logging.ERROR)
        sys.exit(2)
    show_uncategorized = bool(data.get("show_uncategorized", False))
    cats = []
    for entry in data.get("categories", []):
        style = entry.get("style", {}) or {}
        cats.append(OverrideCategory(
            name=str(entry["name"]),
            paths=list(entry.get("paths", [])),
            color=style.get("color"),
            background=style.get("background"),
        ))
    return OverrideConfig(categories=cats, show_uncategorized=show_uncategorized)
    # @cpt-end:cpt-studio-flow-map-cli:p1:inst-load-override


def _load_template_vars(primary_root: Path) -> Dict[str, str]:
    """Flatten ``resolve-vars`` output into a {name: project-root-relative-path} map.

    Calls the studio CLI in JSON mode. Returns an empty dict on any failure —
    template-variable expansion is best-effort enrichment, never a hard dep.

    Output shape: ``{"system": {...}, "kits": {<slug>: {...}}}`` with absolute
    paths. Kit resources are surfaced as unqualified lookup keys such as
    ``adr_template``. System variables (``cf-path``, ``project_root``,
    ``studio_path``) are exposed at the top level.
    """
    # @cpt-begin:cpt-studio-flow-map-cli:p1:inst-load-template-vars
    candidates = [
        ["cfs", "--json", "resolve-vars"],
        [sys.executable, "-m", "studio.cli", "--json", "resolve-vars"],
    ]
    data = None
    errors: list[str] = []
    for cmd in candidates:
        try:
            out = subprocess.run(
                cmd, cwd=primary_root, capture_output=True, text=True, check=False, timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"{' '.join(cmd)} failed to run ({type(exc).__name__}: {exc})")
            continue
        if out.returncode:
            stderr = out.stderr.strip()
            detail = f"exit {out.returncode}"
            if stderr:
                detail = f"{detail}: {stderr}"
            errors.append(f"{' '.join(cmd)} {detail}")
            continue
        if not out.stdout.strip():
            errors.append(f"{' '.join(cmd)} returned no output")
            continue
        try:
            data = json.loads(out.stdout)
            break
        except json.JSONDecodeError as exc:
            errors.append(f"{' '.join(cmd)} returned invalid JSON ({exc})")
            continue
    if data is None:
        if errors:
            _emit_stderr(
                "map: warning: template variable discovery failed; continuing without template vars: "
                + "; ".join(errors)
            )
        return {}
    return _flatten_vars(data, primary_root)
    # @cpt-end:cpt-studio-flow-map-cli:p1:inst-load-template-vars


def _flatten_vars(data, primary_root: Path) -> Dict[str, str]:
    # @cpt-begin:cpt-studio-flow-map-cli:p1:inst-flatten-vars
    flat: Dict[str, str] = {}

    def store(key: str, val: str) -> None:
        if not isinstance(val, str) or not val:
            return
        rel = _relativize(val, primary_root)
        flat[key] = rel

    system = (data or {}).get("system") or {}
    if isinstance(system, dict):
        for k, v in system.items():
            store(str(k), v)
    # Legacy aliases for backward compatibility with older markdown.
    # Canonical key is `cf-studio-path`; older docs may use `cf-path`,
    # `studio_path`, or `studio-path`. Populate all forms as aliases when
    # only one is set so markdown references resolve regardless of vintage.
    aliases = ("cf-studio-path", "cf-path", "studio_path", "studio-path")
    canonical = next((flat[k] for k in aliases if k in flat), None)
    if canonical is not None:
        for k in aliases:
            flat.setdefault(k, canonical)

    variables = (data or {}).get("variables") or {}
    if isinstance(variables, dict):
        for name, val in variables.items():
            if not isinstance(val, str):
                continue
            store(str(name), val)
    return flat
    # @cpt-end:cpt-studio-flow-map-cli:p1:inst-flatten-vars


def _relativize(abs_path: str, project_root: Path) -> str:
    try:
        rel = Path(abs_path).resolve().relative_to(project_root.resolve())
        return str(rel)
    except (ValueError, OSError):
        return abs_path


def skip_dirs_for_meta(primary_root: Path):
    """Surface the effective skip-dir set for the stdout summary."""
    # @cpt-begin:cpt-studio-flow-map-cli:p1:inst-skip-dirs-for-meta
    from .scan import DEFAULT_SKIP_DIRS, _detect_adapter_dir
    skips = set(DEFAULT_SKIP_DIRS)
    adapter = _detect_adapter_dir(primary_root)
    if adapter:
        skips.add(adapter)
    return skips
    # @cpt-end:cpt-studio-flow-map-cli:p1:inst-skip-dirs-for-meta


def _resolve_artifacts_toml(primary_root: Path):
    """Resolve the artifacts registry path via the canonical adapter_dir helper.

    Returns (resolved_path_or_None, adapter_dir_or_primary_root).
    adapter_dir falls back to primary_root when studio discovery fails.

    Guard: adapter resolution is only used when primary_root is the actual VCS
    project root.  When primary_root is a fixture sub-directory (e.g. during
    tests), the flat ``primary_root/artifacts.toml`` layout is used instead to
    prevent picking up the parent project's adapter.
    """
    try:
        from .scan import _adapter_dir_for_scan_root, _resolve_registry_path_for_root

        adapter_dir = _adapter_dir_for_scan_root(primary_root)
        registry_path = _resolve_registry_path_for_root(primary_root)
        if registry_path is None:
            return None, adapter_dir
        return registry_path, adapter_dir
    except _OPTIONAL_MAP_DISCOVERY_ERRORS as exc:  # pragma: no cover
        _warn_optional_discovery("artifacts registry resolution failed", exc)
        return None, primary_root


def _count_systems(adapter_dir: Optional[Path], docs_only: bool = False) -> int:
    if adapter_dir is None:  # pragma: no cover
        return 0
    try:
        from studio.utils.artifacts_meta import ArtifactsMeta
        from studio.utils.files import load_artifacts_registry
        cfg, _err = load_artifacts_registry(adapter_dir)
        if cfg is None:
            return 0
        meta = ArtifactsMeta.from_dict(cfg)
        if docs_only:
            return sum(
                1 for s in meta.systems
                if getattr(s, "traceability_mode", "FULL") == "DOCS-ONLY"
            )
        return len(meta.systems)
    except _OPTIONAL_MAP_DISCOVERY_ERRORS as exc:  # pragma: no cover
        _warn_optional_discovery("system counting failed", exc)
        return 0


def _print_summary(
    scan_meta: dict,
    sources: List[dict],
    nodes: List,
    edges: List,
    out_path: Path,
    sidecar_path: Optional[Path],
    config_path: Optional[str],
) -> None:
    # @cpt-begin:cpt-studio-flow-map-cli:p1:inst-print-summary
    md = sum(1 for n in nodes if n.kind == "markdown")
    src = sum(1 for n in nodes if n.kind == "source")
    phantom = sum(1 for n in nodes if n.kind == "phantom-cpt")
    file_edges = sum(1 for e in edges if e.type == "file-link")
    cpt_doc = sum(1 for e in edges if e.type == "cpt-doc")
    cpt_impl = sum(1 for e in edges if e.type == "cpt-impl")
    reachable = sum(1 for s in sources if s["reachable"])
    unreachable = sum(1 for s in sources if not s["reachable"])
    _emit_stdout(f"Config       : {config_path or '(none)'}")
    _emit_stdout(
        f"Mode         : {'federated' if reachable > 1 else 'single-repo'} "
        f"({reachable} reachable, {unreachable} unreachable)"
    )
    _emit_stdout(
        f"Source scan  : artifacts.toml: {scan_meta['systems_scanned']} systems, "
        f"{scan_meta['systems_docs_only']} DOCS-ONLY"
    )
    _emit_stdout(f"Scanned      : {md} markdown, {src} source files")
    _emit_stdout(f"Edges        : {file_edges} file-link, {cpt_doc} cpt-doc, {cpt_impl} cpt-impl")
    _emit_stdout(f"Phantom IDs  : {phantom} dangling cpt uses")
    _emit_stdout(f"Wrote        : {out_path}")
    if sidecar_path is not None:
        _emit_stdout(f"               {sidecar_path}")
    # @cpt-end:cpt-studio-flow-map-cli:p1:inst-print-summary
