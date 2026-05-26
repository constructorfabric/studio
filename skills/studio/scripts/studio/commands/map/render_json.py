"""Canonical JSON output for cfs map.

@cpt-algo:cpt-studio-algo-map-render-json:p1
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from .model import Edge, Node


@dataclass(frozen=True)
class RenderJsonInput:
    nodes: Sequence[Node]
    edges: Sequence[Edge]
    workspace: dict
    scan: dict
    # Layout outputs (optional — None means "no positions; viewer uses physics")
    vis_nodes: Optional[list] = None
    bucket_rects: Optional[dict] = None
    category_bands: Optional[dict] = None
    # Per-category style overrides from md-map.toml [categories.style].
    # Maps category name → {"color": str, "background": str}.
    # When present and the name matches, overrides _deterministic_style.
    category_styles: Optional[Dict[str, dict]] = None


def render_json(inp: RenderJsonInput) -> str:
    # @cpt-begin:cpt-studio-algo-map-render-json:p1:inst-render-json
    nodes_sorted = sorted([n.to_dict() for n in inp.nodes], key=lambda d: d["id"])
    edges_sorted = sorted([e.to_dict() for e in inp.edges], key=lambda d: d["id"])
    dangling = _dangling_section(inp.nodes, inp.edges)
    categories = _categories_section(inp.nodes, inp.category_styles)
    payload = {
        "version": "1.0",
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workspace": inp.workspace,
        "scan": inp.scan,
        "nodes": nodes_sorted,
        "edges": edges_sorted,
        "dangling_cpt_uses": dangling,
        "categories": categories,
        "layout": {
            "vis_nodes": inp.vis_nodes or [],
            "bucket_rects": inp.bucket_rects or {},
            "category_bands": inp.category_bands or {},
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False)
    # @cpt-end:cpt-studio-algo-map-render-json:p1:inst-render-json


def _dangling_section(nodes: Sequence[Node], edges: Sequence[Edge]) -> List[dict]:
    # @cpt-begin:cpt-studio-algo-map-render-json:p1:inst-dangling-section
    by_id: Dict[str, Node] = {n.id: n for n in nodes}
    out: List[dict] = []
    seen: set[tuple] = set()
    for e in edges:
        if not e.dangling:
            continue
        src = by_id.get(e.from_id)
        if src is None:
            continue
        for r in e.refs:
            if not r.cpt_id:
                continue
            key = (r.cpt_id, e.from_id, r.line)
            if key in seen:
                continue
            seen.add(key)
            out.append({"cpt_id": r.cpt_id, "node_id": e.from_id, "line": r.line, "snippet": r.snippet})
    out.sort(key=lambda d: (d["cpt_id"], d["node_id"], d["line"]))
    return out
    # @cpt-end:cpt-studio-algo-map-render-json:p1:inst-dangling-section


def _categories_section(
    nodes: Sequence[Node],
    category_styles: Optional[Dict[str, dict]] = None,
) -> Dict[str, dict]:
    # @cpt-begin:cpt-studio-algo-map-render-json:p1:inst-categories-section
    cats: Dict[str, Dict[str, int]] = {}
    origins: Dict[str, Counter] = {}
    for n in nodes:
        cats.setdefault(n.category, {"count": 0})
        cats[n.category]["count"] += 1
        origins.setdefault(n.category, Counter())[n.category_origin] += 1
    out: Dict[str, dict] = {}
    for cat, info in cats.items():
        # Fixed gray style for the _uncategorized bucket — never call
        # _deterministic_style for it and ignore any user-defined style entry.
        if cat == "_uncategorized":
            style: Dict[str, str] = {"color": "#6b7280", "background": "#f3f4f6"}
        else:
            # Prefer user-defined style from md-map.toml [categories.style] when
            # the override entry has a color set; fall back to _deterministic_style.
            override_style = (category_styles or {}).get(cat)
            if override_style and override_style.get("color"):
                style = dict(override_style)
                # When background is absent, omit the key and let CSS handle it.
                style = {k: v for k, v in style.items() if v is not None}
            else:
                style = _deterministic_style(cat)
        out[cat] = {
            "node_count": info["count"],
            "origin_counts": {
                "override": origins[cat].get("override", 0),
                "registry": origins[cat].get("registry", 0),
                "parent-dir": origins[cat].get("parent-dir", 0),
                "phantom": origins[cat].get("phantom", 0),
                "uncategorized-bucket": origins[cat].get("uncategorized-bucket", 0),
            },
            "style": style,
        }
    return out
    # @cpt-end:cpt-studio-algo-map-render-json:p1:inst-categories-section


def _deterministic_style(name: str) -> Dict[str, str]:
    # @cpt-begin:cpt-studio-algo-map-render-json:p1:inst-deterministic-style
    h = hashlib.sha256(name.encode("utf-8")).hexdigest()
    hue = int(h[:6], 16) % 360
    return {
        "color": f"hsl({hue}, 60%, 30%)",
        "background": f"hsl({hue}, 60%, 95%)",
    }
    # @cpt-end:cpt-studio-algo-map-render-json:p1:inst-deterministic-style
