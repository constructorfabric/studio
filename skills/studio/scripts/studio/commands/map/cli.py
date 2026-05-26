"""cfs map CLI entry point.

@cpt-flow:cpt-studio-flow-map-cli:p1
@cpt-dod:cpt-studio-dod-dependency-mapping-graph:p1
@cpt-state:cpt-studio-state-dependency-map:p1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .categorize import (
    CategorizeOptions, OverrideCategory, OverrideConfig, categorize_nodes,
)
from .cpt_edges import build_cpt_edges
from .enrich import enrich_edges
from .layout import compute_layout
from .links import extract_file_links
from .render_html import RenderHtmlInput, render_html
from .render_json import RenderJsonInput, render_json
from .scan import ScanOptions, scan_repo
from studio.utils._tomllib_compat import tomllib


def cmd_map(argv: List[str]) -> int:
    # @cpt-begin:cpt-studio-flow-map-cli:p1:inst-cmd-map
    p = argparse.ArgumentParser(
        prog="cfs map",
        description="Build an interactive markdown↔source map via cpt identifiers.",
    )
    p.add_argument("--out", default=None)
    p.add_argument("--format", choices=["html", "json"], default="html")
    p.add_argument("--config", default=None)
    p.add_argument("--no-source", action="store_true")
    p.add_argument("--local-only", action="store_true")
    p.add_argument("--inline-data", action="store_true")
    p.add_argument(
        "--include-adapter",
        action="store_true",
        help="Scan inside the cf / studio adapter directory too. "
             "Useful when markdown references {cf-studio-path}/... paths that "
             "should resolve to nodes in the graph.",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    cwd = Path.cwd().resolve()
    primary_root = cwd
    out_path = Path(args.out).resolve() if args.out else cwd / f"md-map.{args.format}"

    sources = _discover_sources(primary_root, local_only=args.local_only)
    override = _load_override(primary_root, args.config)

    # @cpt-begin:cpt-studio-flow-map-cli:p1:inst-collect-nodes
    all_nodes = []
    project_root_by_source: Dict[str, Path] = {}
    for src in sources:
        if not src["reachable"]:
            continue
        src_root = Path(src["path"]).resolve()
        opts = ScanOptions(
            project_root=src_root,
            source_name=src["name"],
            no_source=args.no_source,
            include_adapter=args.include_adapter,
        )
        all_nodes.extend(scan_repo(opts))
        project_root_by_source[src["name"]] = src_root

    categorize_nodes(all_nodes, CategorizeOptions(
        project_root=primary_root,
        override=override,
        source_roots=project_root_by_source,
    ))
    # @cpt-end:cpt-studio-flow-map-cli:p1:inst-collect-nodes

    # @cpt-begin:cpt-studio-flow-map-cli:p1:inst-filter-override
    # Apply override filtering: when an override config is loaded, only nodes
    # that matched an override category are kept by default.  When
    # show_uncategorized=true, non-matched nodes are bucketed instead.
    if override is not None:
        if override.show_uncategorized:
            for n in all_nodes:
                if n.category_origin != "override":
                    n.category = "_uncategorized"
                    n.category_origin = "uncategorized-bucket"
        else:
            if not override.categories:
                print(
                    "map: override config has zero categories and show_uncategorized=false;"
                    " result will be empty",
                    file=sys.stderr,
                )
            all_nodes = [n for n in all_nodes if n.category_origin == "override"]
    # @cpt-end:cpt-studio-flow-map-cli:p1:inst-filter-override

    # @cpt-begin:cpt-studio-flow-map-cli:p1:inst-build-edges
    template_vars = _load_template_vars(primary_root)
    file_edges = extract_file_links(
        all_nodes, project_root=primary_root, template_vars=template_vars,
    )
    cpt_edges, phantoms = build_cpt_edges(all_nodes)
    edges = list(file_edges) + list(cpt_edges)
    nodes_all = list(all_nodes) + list(phantoms)

    # Apply phantom handling for override paths: phantoms are generated after
    # the earlier bucketing/filter step so they need a second pass here.
    if override is not None:
        if override.show_uncategorized:
            # Bucket phantoms into _uncategorized (same rule as non-override nodes).
            for n in nodes_all:
                if n.category_origin == "phantom":
                    n.category = "_uncategorized"
                    n.category_origin = "uncategorized-bucket"
        else:
            # Drop phantoms and any edges that reference removed nodes.
            nodes_all = [n for n in nodes_all if n.category_origin == "override"]
            _node_ids = {n.id for n in nodes_all}
            edges = [e for e in edges if e.from_id in _node_ids and e.to_id in _node_ids]

    enrich_edges(edges, nodes_all, project_root_by_source=project_root_by_source)
    # @cpt-end:cpt-studio-flow-map-cli:p1:inst-build-edges

    # @cpt-begin:cpt-studio-flow-map-cli:p1:inst-layout-render
    vis_nodes, bucket_rects, category_bands = compute_layout(
        nodes_all, edges, category_style=None, verbose=args.verbose,
    )

    art_toml, adapter_dir = _resolve_artifacts_toml(primary_root)
    if art_toml is None:
        print(
            "map: no artifacts.toml found via adapter resolution; source scanning disabled",
            file=sys.stderr,
        )
    scan_meta = {
        "artifacts_toml": str(art_toml.relative_to(primary_root)) if art_toml is not None else None,
        "systems_scanned": _count_systems(adapter_dir),
        "systems_docs_only": _count_systems(adapter_dir, docs_only=True),
        "skip_dirs": sorted(skip_dirs_for_meta(primary_root)),
    }

    # Build per-category style dict from the override config so the JSON legend
    # reflects user-defined colors from md-map.toml [categories.style].
    category_styles = {}
    if override is not None:
        for oc in override.categories:
            if oc.color is not None:
                entry: dict = {"color": oc.color}
                if oc.background is not None:
                    entry["background"] = oc.background
                category_styles[oc.name] = entry

    json_payload = render_json(RenderJsonInput(
        nodes=nodes_all,
        edges=edges,
        workspace={"primary": "local", "sources": sources},
        scan=scan_meta,
        vis_nodes=vis_nodes,
        bucket_rects=bucket_rects,
        category_bands=category_bands,
        category_styles=category_styles or None,
    ))

    sidecar_path = None
    if args.format == "json":
        out_path.write_text(json_payload, encoding="utf-8")
    else:
        html, sidecar_js = render_html(RenderHtmlInput(
            json_payload=json_payload,
            inline_data=args.inline_data,
            sidecar_basename=out_path.name + ".js",
        ))
        out_path.write_text(html, encoding="utf-8")
        if sidecar_js is not None:
            sidecar_path = out_path.with_name(out_path.name + ".js")
            sidecar_path.write_text(sidecar_js, encoding="utf-8")

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
    except Exception:  # pylint: disable=broad-exception-caught  # federation discovery is best-effort
        pass
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
    except Exception as exc:  # pylint: disable=broad-exception-caught  # override config validation
        print(f"map: invalid {path}: {exc}", file=sys.stderr)
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
    paths. We surface three lookup keys per kit resource:
    ``adr_template``, ``sdlc.adr_template`` and ``kits.sdlc.adr_template``.
    System variables (``cf-path``, ``project_root``, ``studio_path``)
    are exposed at the top level.
    """
    # @cpt-begin:cpt-studio-flow-map-cli:p1:inst-load-template-vars
    import json
    import subprocess

    candidates = [
        ["cfs", "--json", "resolve-vars"],
        [sys.executable, "-m", "studio.cli", "--json", "resolve-vars"],
    ]
    data = None
    for cmd in candidates:
        try:
            out = subprocess.run(
                cmd, cwd=primary_root, capture_output=True, text=True, check=False, timeout=15,
            )
        except Exception:  # pylint: disable=broad-exception-caught
            continue
        if out.returncode != 0 or not out.stdout.strip():
            continue
        try:
            data = json.loads(out.stdout)
            break
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    if data is None:
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

    kits = (data or {}).get("kits") or {}
    if isinstance(kits, dict):
        for kit_slug, resources in kits.items():
            if not isinstance(resources, dict):
                continue
            for name, val in resources.items():
                if not isinstance(val, str):
                    continue
                store(str(name), val)                    # bare:  adr_template
                store(f"{kit_slug}.{name}", val)         # qualified: sdlc.adr_template
                store(f"kits.{kit_slug}.{name}", val)    # fully qualified
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
        from studio.utils.files import find_studio_directory, find_project_root, load_artifacts_registry
        detected_root = find_project_root(primary_root)
        if detected_root is not None and detected_root.resolve() == primary_root.resolve():
            # primary_root IS the VCS project root — use full adapter resolution.
            adapter_dir = find_studio_directory(primary_root) or primary_root
            cfg, _err = load_artifacts_registry(adapter_dir)
            if cfg is None:
                return None, adapter_dir
            # Reconstruct the resolved file path for scan_meta reporting.
            # Mirror the fallback chain from load_artifacts_registry.
            for candidate in (
                adapter_dir / "artifacts.toml",
                adapter_dir / "config" / "artifacts.toml",
                adapter_dir / "artifacts.json",
            ):
                if candidate.is_file():
                    return candidate, adapter_dir
            return None, adapter_dir
        # primary_root is a sub-directory — use flat layout only.
        flat = primary_root / "artifacts.toml"
        if flat.is_file():
            return flat, primary_root
        return None, primary_root
    except Exception:  # pylint: disable=broad-exception-caught  # registry resolution is best-effort
        return None, primary_root


def _count_systems(adapter_dir: Optional[Path], docs_only: bool = False) -> int:
    if adapter_dir is None:
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
    except Exception:  # pylint: disable=broad-exception-caught  # system counting fallback
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
    print(f"Config       : {config_path or '(none)'}")
    print(
        f"Mode         : {'federated' if reachable > 1 else 'single-repo'} "
        f"({reachable} reachable, {unreachable} unreachable)"
    )
    print(
        f"Source scan  : artifacts.toml: {scan_meta['systems_scanned']} systems, "
        f"{scan_meta['systems_docs_only']} DOCS-ONLY"
    )
    print(f"Scanned      : {md} markdown, {src} source files")
    print(f"Edges        : {file_edges} file-link, {cpt_doc} cpt-doc, {cpt_impl} cpt-impl")
    print(f"Phantom IDs  : {phantom} dangling cpt uses")
    print(f"Wrote        : {out_path}")
    if sidecar_path is not None:
        print(f"               {sidecar_path}")
    # @cpt-end:cpt-studio-flow-map-cli:p1:inst-print-summary
