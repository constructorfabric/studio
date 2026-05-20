"""cfc map CLI entry point.

@cpt-flow:cpt-cypilot-flow-map-cli:p1
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
from .links import extract_file_links
from .render_html import RenderHtmlInput, render_html
from .render_json import RenderJsonInput, render_json
from .scan import ScanOptions, scan_repo
from cypilot.utils._tomllib_compat import tomllib


def cmd_map(argv: List[str]) -> int:
    p = argparse.ArgumentParser(
        prog="cfc map",
        description="Build an interactive markdown↔source map via cpt identifiers.",
    )
    p.add_argument("--out", default=None)
    p.add_argument("--format", choices=["html", "json"], default="html")
    p.add_argument("--config", default=None)
    p.add_argument("--no-source", action="store_true")
    p.add_argument("--local-only", action="store_true")
    p.add_argument("--inline-data", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    cwd = Path.cwd().resolve()
    primary_root = cwd
    out_path = Path(args.out).resolve() if args.out else cwd / f"md-map.{args.format}"

    sources = _discover_sources(primary_root, local_only=args.local_only)
    override = _load_override(primary_root, args.config)

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
        )
        all_nodes.extend(scan_repo(opts))
        project_root_by_source[src["name"]] = src_root

    categorize_nodes(all_nodes, CategorizeOptions(project_root=primary_root, override=override))

    file_edges = extract_file_links(all_nodes, project_root=primary_root)
    cpt_edges, phantoms = build_cpt_edges(all_nodes)
    edges = list(file_edges) + list(cpt_edges)
    nodes_all = list(all_nodes) + list(phantoms)

    enrich_edges(edges, nodes_all, project_root_by_source=project_root_by_source)

    art_toml = primary_root / "artifacts.toml"
    if not art_toml.exists():
        print(
            "map: no artifacts.toml found at project root; source scanning disabled",
            file=sys.stderr,
        )
    scan_meta = {
        "artifacts_toml": "artifacts.toml" if art_toml.exists() else None,
        "systems_scanned": _count_systems(primary_root),
        "systems_docs_only": _count_systems(primary_root, docs_only=True),
        "skip_dirs": ["target", "node_modules", ".git", ".bootstrap"],
    }

    json_payload = render_json(RenderJsonInput(
        nodes=nodes_all,
        edges=edges,
        workspace={"primary": "local", "sources": sources},
        scan=scan_meta,
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
    return 0


def _discover_sources(primary_root: Path, local_only: bool) -> List[dict]:
    sources: List[dict] = [
        {"name": "local", "path": str(primary_root), "reachable": True, "role": "full"}
    ]
    if local_only:
        return sources
    # Best-effort federation discovery via find_workspace_config.
    # Federation is fully exercised in Task 14; here we just do a graceful attempt.
    try:
        from cypilot.utils.workspace import find_workspace_config
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
    except Exception:
        pass
    return sources


def _load_override(primary_root: Path, explicit: Optional[str]) -> Optional[OverrideConfig]:
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
    except Exception as exc:
        print(f"map: invalid {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    cats = []
    for entry in data.get("categories", []):
        style = entry.get("style", {}) or {}
        cats.append(OverrideCategory(
            name=str(entry["name"]),
            paths=list(entry.get("paths", [])),
            color=style.get("color"),
            background=style.get("background"),
        ))
    return OverrideConfig(categories=cats)


def _count_systems(primary_root: Path, docs_only: bool = False) -> int:
    try:
        from cypilot.utils.artifacts_meta import ArtifactsMeta
        art_toml = primary_root / "artifacts.toml"
        if not art_toml.exists():
            return 0
        with art_toml.open("rb") as f:
            data = tomllib.load(f)
        meta = ArtifactsMeta.from_dict(data)
        if docs_only:
            return sum(
                1 for s in meta.systems
                if getattr(s, "traceability_mode", "FULL") == "DOCS-ONLY"
            )
        return len(meta.systems)
    except Exception:
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
