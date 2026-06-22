"""Rectpack-based category layout for cfs map.

Ported from md-fabric.py (lines 687–1310) with adaptations for the Node/Edge
model (no buckets/views — each category is a single bucket).

@cpt-algo:cpt-studio-algo-map-layout:p1
"""
from __future__ import annotations

import hashlib
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from studio.vendor import rectpack

from .model import Edge, Node

# ---------------------------------------------------------------------------
# Layout constants (from md-fabric.py)
# ---------------------------------------------------------------------------

CATEGORY_GAP: int = 60
BUCKET_GAP: int = 80
CATEGORY_HEADER_H: int = 68
CAT_PAD_TOP: int = 20
CAT_PAD_BOTTOM: int = 40
CAT_PAD_SIDE: int = 30
CATEGORY_REPACK_GAP: int = 40
MAX_ROW_W: int = 12000
TARGET_ASPECT: float = 16 / 9

_RECTPACK_ALGOS: tuple[Any, ...] = (
    rectpack.MaxRectsBssf,
    rectpack.MaxRectsBaf,
    rectpack.MaxRectsBl,
    rectpack.MaxRectsBlsf,
)

# Node spacing inside a bucket
_SPACING: int = 80
_PAD_H: int = 40
_PAD_TOP: int = 55
_PAD_BOTTOM: int = 40


@dataclass(frozen=True)
class _AffinityLayoutInput:
    best_choices: list[Any]
    category_inputs: list[dict[str, Any]]
    stacked_metrics: Any
    chosen_positions: dict[str, tuple[int, int]]
    chosen_metrics: Any
    category_links: dict[tuple[str, str], int]
    category_link_totals: dict[str, int]
    choice_by_cat: dict[str, Any]
    verbose: bool


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def _deterministic_style(name: str) -> dict[str, str]:
    """Derive hsl colours deterministically from category name (sha256)."""
    # @cpt-begin:cpt-studio-algo-map-layout:p1:inst-deterministic-style
    hue = int(hashlib.sha256(name.encode()).hexdigest()[:6], 16) % 360
    return {
        "color": f"hsl({hue}, 60%, 30%)",
        "background": f"hsl({hue}, 60%, 95%)",
    }
    # @cpt-end:cpt-studio-algo-map-layout:p1:inst-deterministic-style


def _node_colors(category: str, category_style: dict[str, dict[str, str]] | None) -> dict[str, str]:
    """Return {background, border} for a markdown/source node."""
    # @cpt-begin:cpt-studio-algo-map-layout:p1:inst-node-colors
    if category_style and category in category_style:
        s = category_style[category]
        return {"background": s.get("background", "#ffffff"), "border": s.get("color", "#555555")}
    s = _deterministic_style(category)
    return {"background": s["background"], "border": s["color"]}
    # @cpt-end:cpt-studio-algo-map-layout:p1:inst-node-colors


def _category_band_style(
    category: str,
    category_style: dict[str, dict[str, str]] | None,
) -> dict[str, str]:
    """Return fill/stroke/title_color for the band rectangle."""
    # @cpt-begin:cpt-studio-algo-map-layout:p1:inst-category-band-style
    if category_style and category in category_style:
        s = category_style[category]
        color = s.get("color", _deterministic_style(category)["color"])
        bg = s.get("background", _deterministic_style(category)["background"])
    else:
        ds = _deterministic_style(category)
        color = ds["color"]
        bg = ds["background"]

    # Derive rgba variants (approximate — just use the raw color with transparency)
    fill = f"color-mix(in srgb, {bg} 8%, transparent)"
    stroke = f"color-mix(in srgb, {color} 30%, transparent)"
    title_c = color
    return {"fill": fill, "stroke": stroke, "title_color": title_c}
    # @cpt-end:cpt-studio-algo-map-layout:p1:inst-category-band-style


# ---------------------------------------------------------------------------
# Dimension helpers
# ---------------------------------------------------------------------------

def _dims(n: int, _total_files_in_category: int) -> tuple[int, int, int]:
    """Return (width, height, cols) for a category's single bucket.

    Targets a roughly-square arrangement to keep each band readable.
    The second parameter is retained for API stability
    but no longer affects the column count.
    """
    # @cpt-begin:cpt-studio-algo-map-layout:p1:inst-dims
    cols = max(1, math.ceil(math.sqrt(n * 1.3)))
    rows = math.ceil(n / cols)
    w = max(180, 2 * _PAD_H + 18 + (cols - 1) * _SPACING)
    h = max(130, _PAD_TOP + _PAD_BOTTOM + 36 + (rows - 1) * _SPACING)
    return w, h, cols
    # @cpt-end:cpt-studio-algo-map-layout:p1:inst-dims


# ---------------------------------------------------------------------------
# Vis-node builder helpers
# ---------------------------------------------------------------------------

def _make_vis_node(
    node: Node,
    x: int,
    y: int,
    category_style: dict[str, dict[str, str]] | None,
    degrees: dict[str, int],
) -> dict[str, Any]:
    """Build a vis-network node dict from a Node."""
    # @cpt-begin:cpt-studio-algo-map-layout:p1:inst-make-vis-node
    if node.kind == "phantom-cpt":
        label = node.id.replace("phantom:", "⚠ ")
        return {
            "id": node.id,
            "label": label,
            "x": x,
            "y": y,
            "shape": "diamond",
            "color": {
                "background": "#ffeaea",
                "border": "#c41212",
                "highlight": {"background": "#ffd0d0", "border": "#c41212"},
            },
            "font": {"color": "#c41212"},
            "mass": max(1, degrees.get(node.id, 1)),
            "category": node.category,
            "group": node.category,
        }

    rel = node.rel_path or ""
    label = Path(rel).name if rel else node.id

    if node.kind == "source":
        color = {
            "background": "#fff5e6",
            "border": "#c07000",
            "highlight": {"background": "#fff0cc", "border": "#c07000"},
        }
        font: dict[str, Any] = {"face": "monospace"}
        shape = "box"
    else:
        # markdown
        c = _node_colors(node.category, category_style)
        color = {**c, "highlight": {"background": "#fff7cc", "border": "#d99a00"}}
        font = {}
        shape = "box"

    entry: dict[str, Any] = {
        "id": node.id,
        "label": label,
        "x": x,
        "y": y,
        "shape": shape,
        "color": color,
        "mass": max(1, degrees.get(node.id, 1)),
        "category": node.category,
        "group": node.category,
        "loc": node.loc,
    }
    if node.rel_path:
        entry["rel_path"] = node.rel_path
    if font:
        entry["font"] = font
    return entry
    # @cpt-end:cpt-studio-algo-map-layout:p1:inst-make-vis-node


# ---------------------------------------------------------------------------
# Metrics helpers (adapted from md-fabric.py)
# ---------------------------------------------------------------------------

def _layout_metrics(
    choices: list[rectpack.LayoutCandidate],
    positions: dict[str, tuple[int, int]],
    category_inputs: list[dict[str, Any]],
) -> rectpack.StackedLayoutMetrics:
    # @cpt-begin:cpt-studio-algo-map-layout:p1:inst-layout-metrics
    if not choices:
        return rectpack.StackedLayoutMetrics(0, 0, 0.0, 0.0, 0.0, 0.0)
    total_width = max(
        positions[entry["cat_id"]][0] + choice.width
        for entry, choice in zip(category_inputs, choices)
    )
    total_height = max(
        positions[entry["cat_id"]][1] + choice.height
        for entry, choice in zip(category_inputs, choices)
    )
    total_used_area = sum(choice.used_area for choice in choices)
    total_category_area = sum(choice.width * choice.height for choice in choices)
    total_aspect = total_width / max(1, total_height)
    total_density = total_used_area / max(1, total_width * total_height)
    total_category_density = total_category_area / max(1, total_width * total_height)
    aspect_error = abs(total_aspect - TARGET_ASPECT) / max(TARGET_ASPECT, 1e-9)
    return rectpack.StackedLayoutMetrics(
        total_width=total_width,
        total_height=total_height,
        total_aspect=total_aspect,
        total_density=total_density,
        total_category_density=total_category_density,
        aspect_error=aspect_error,
    )
    # @cpt-end:cpt-studio-algo-map-layout:p1:inst-layout-metrics


def _layout_score(
    metrics: rectpack.StackedLayoutMetrics,
    positions: dict[str, tuple[int, int]],
    category_links: dict[tuple[str, str], int],
    choice_by_cat: dict[str, rectpack.LayoutCandidate],
) -> tuple[float, float, float, float, float, float]:
    # @cpt-begin:cpt-studio-algo-map-layout:p1:inst-layout-score
    density_loss = 1.0 - metrics.total_density
    category_loss = 1.0 - metrics.total_category_density
    affinity_loss = _affinity_loss(metrics, positions, category_links, choice_by_cat)

    return (
        0.45 * density_loss + 0.30 * metrics.aspect_error + 0.15 * category_loss + 0.10 * affinity_loss,
        density_loss,
        metrics.aspect_error,
        category_loss,
        affinity_loss,
        float(metrics.total_height),
    )
    # @cpt-end:cpt-studio-algo-map-layout:p1:inst-layout-score


def _affinity_loss(
    metrics: rectpack.StackedLayoutMetrics,
    positions: dict[str, tuple[int, int]],
    category_links: dict[tuple[str, str], int],
    choice_by_cat: dict[str, rectpack.LayoutCandidate],
) -> float:
    total_weight = sum(category_links.values())
    if total_weight <= 0:
        return 0.0
    normalizer = max(1.0, math.hypot(metrics.total_width, metrics.total_height))
    weighted_distance = 0.0
    for (left, right), weight in category_links.items():
        if left not in choice_by_cat or right not in choice_by_cat:
            continue
        left_center_x, left_center_y = _choice_center(left, positions, choice_by_cat)
        right_center_x, right_center_y = _choice_center(right, positions, choice_by_cat)
        weighted_distance += weight * (
            abs(left_center_x - right_center_x) + abs(left_center_y - right_center_y)
        ) / normalizer
    return weighted_distance / total_weight


def _choice_center(
    cat_id: str,
    positions: dict[str, tuple[int, int]],
    choice_by_cat: dict[str, rectpack.LayoutCandidate],
) -> tuple[float, float]:
    choice = choice_by_cat[cat_id]
    pos_x, pos_y = positions[cat_id]
    return pos_x + choice.width / 2.0, pos_y + choice.height / 2.0


def _layout_improves(
    baseline: rectpack.StackedLayoutMetrics,
    candidate: rectpack.StackedLayoutMetrics,
) -> bool:
    # @cpt-begin:cpt-studio-algo-map-layout:p1:inst-layout-improves
    eps = 1e-9
    return (
        candidate.total_density + eps >= baseline.total_density
        and candidate.total_category_density + eps >= baseline.total_category_density
        and (
            candidate.total_density > baseline.total_density + eps
            or candidate.total_category_density > baseline.total_category_density + eps
            or candidate.aspect_error < baseline.aspect_error - eps
        )
    )
    # @cpt-end:cpt-studio-algo-map-layout:p1:inst-layout-improves


def _greedy_affinity_order(
    seed: str,
    choice_by_cat: dict[str, rectpack.LayoutCandidate],
    category_links: dict[tuple[str, str], int],
    category_link_totals: dict[str, int],
) -> tuple[str, ...]:
    # @cpt-begin:cpt-studio-algo-map-layout:p1:inst-greedy-affinity-order
    def _affinity(left: str, right: str) -> int:
        if left == right:
            return 0
        key = (left, right) if left < right else (right, left)
        return category_links.get(key, 0)

    remaining = [cat_id for cat_id in choice_by_cat if cat_id != seed]
    order = [seed]
    while remaining:
        next_cat = max(
            remaining,
            key=lambda cat_id: (
                sum(_affinity(cat_id, existing) for existing in order),
                _affinity(cat_id, order[-1]),
                category_link_totals.get(cat_id, 0),
                choice_by_cat[cat_id].used_area,
                choice_by_cat[cat_id].width * choice_by_cat[cat_id].height,
            ),
        )
        order.append(next_cat)
        remaining.remove(next_cat)
    return tuple(order)
    # @cpt-end:cpt-studio-algo-map-layout:p1:inst-greedy-affinity-order


def _row_pack_positions(
    order: tuple[str, ...],
    width_limit: int,
    choice_by_cat: dict[str, rectpack.LayoutCandidate],
) -> dict[str, tuple[int, int]]:
    # @cpt-begin:cpt-studio-algo-map-layout:p1:inst-row-pack-positions
    positions: dict[str, tuple[int, int]] = {}
    cur_x = 0
    cur_y = 0
    row_height = 0
    for cat_id in order:
        choice = choice_by_cat[cat_id]
        if cur_x > 0 and cur_x + choice.width > width_limit:
            cur_x = 0
            cur_y += row_height + CATEGORY_REPACK_GAP
            row_height = 0
        positions[cat_id] = (cur_x, cur_y)
        cur_x += choice.width + CATEGORY_REPACK_GAP
        row_height = max(row_height, choice.height)
    return positions
    # @cpt-end:cpt-studio-algo-map-layout:p1:inst-row-pack-positions


def _group_layout_inputs(
    nodes: list[Node],
    edges: list[Edge],
) -> tuple[list[Node], dict[str, int], dict[str, list[Node]], dict[tuple[str, str], int], dict[str, int]]:
    sorted_nodes = sorted(nodes, key=lambda node: node.id)
    degrees: dict[str, int] = {}
    for edge in edges:
        degrees[edge.from_id] = degrees.get(edge.from_id, 0) + 1
        degrees[edge.to_id] = degrees.get(edge.to_id, 0) + 1
    grouped: dict[str, list[Node]] = {}
    for node in sorted_nodes:
        grouped.setdefault(node.category, []).append(node)
    node_to_cat = {node.id: node.category for node in sorted_nodes}
    present_cats = set(grouped)
    category_links: dict[tuple[str, str], int] = {}
    category_link_totals: dict[str, int] = {category: 0 for category in present_cats}
    for edge in edges:
        left = node_to_cat.get(edge.from_id)
        right = node_to_cat.get(edge.to_id)
        if left not in present_cats or right not in present_cats or left == right:
            continue
        key = (left, right) if left < right else (right, left)
        category_links[key] = category_links.get(key, 0) + 1
        category_link_totals[left] = category_link_totals.get(left, 0) + 1
        category_link_totals[right] = category_link_totals.get(right, 0) + 1
    return sorted_nodes, degrees, grouped, category_links, category_link_totals


def _category_input(cat_id: str, cat_nodes: list[Node], verbose: bool) -> dict[str, Any]:
    node_count = len(cat_nodes)
    width, height, _cols = _dims(node_count, node_count)
    sorted_items = [(cat_id, width, height)]
    try:
        candidates = rectpack.generate_layout_candidates(
            sorted_items,
            gap=BUCKET_GAP,
            target_aspect=TARGET_ASPECT,
            pad_side=CAT_PAD_SIDE,
            pad_top=CAT_PAD_TOP,
            pad_bottom=CAT_PAD_BOTTOM,
            header_height=CATEGORY_HEADER_H,
            pack_algos=_RECTPACK_ALGOS,
            limit=16,
        )
    except RuntimeError as exc:
        print(
            f"map: warning: rectpack candidate generation failed for category {cat_id}: {exc}; "
            "falling back to single-bucket layout",
            file=sys.stderr,
        )
        bucket_width = width + 2 * CAT_PAD_SIDE
        bucket_height = CATEGORY_HEADER_H + CAT_PAD_TOP + height + CAT_PAD_BOTTOM
        candidates = [
            rectpack.LayoutCandidate(
                positions={cat_id: (CAT_PAD_SIDE, CATEGORY_HEADER_H + CAT_PAD_TOP)},
                width=bucket_width,
                height=bucket_height,
                used_area=width * height,
                density=(width * height) / max(1, bucket_width * bucket_height),
                aspect=bucket_width / max(1, bucket_height),
                row_count=1,
            )
        ]
    if verbose:
        print(
            f"[layout] category {cat_id}: nodes={node_count} candidates={len(candidates)} "
            f"best={candidates[0].width}x{candidates[0].height} "
            f"aspect={candidates[0].aspect:.3f} density={candidates[0].density:.3f}"
        )
    return {"cat_id": cat_id, "nodes": cat_nodes, "candidates": candidates}


def _build_category_inputs(grouped: dict[str, list[Node]], verbose: bool) -> list[dict[str, Any]]:
    return [_category_input(cat_id, grouped[cat_id], verbose) for cat_id in sorted(grouped)]


def _optimize_stacked_layout(category_inputs: list[dict[str, Any]], verbose: bool):
    best_choices, _chosen_indexes, _snapshots = rectpack.optimize_stacked_categories(
        [(entry["cat_id"], entry["candidates"]) for entry in category_inputs],
        category_gap=CATEGORY_GAP,
        target_aspect=TARGET_ASPECT,
        aspect_tolerance=0.10,
        max_iterations=10,
    )
    if verbose:
        final_metrics = rectpack.compute_stacked_metrics(
            best_choices,
            category_gap=CATEGORY_GAP,
            target_aspect=TARGET_ASPECT,
        )
        print(
            f"[layout] final: total={final_metrics.total_width}x{final_metrics.total_height} "
            f"aspect={final_metrics.total_aspect:.3f} density={final_metrics.total_density:.3f}"
        )
    choice_by_cat: dict[str, rectpack.LayoutCandidate] = {
        entry["cat_id"]: choice
        for entry, choice in zip(category_inputs, best_choices)
    }
    stacked_positions: dict[str, tuple[int, int]] = {}
    cur_y = 0
    for entry, candidate in zip(category_inputs, best_choices):
        stacked_positions[entry["cat_id"]] = (0, cur_y)
        cur_y += candidate.height + CATEGORY_GAP
    stacked_metrics = _layout_metrics(best_choices, stacked_positions, category_inputs)
    return best_choices, choice_by_cat, stacked_positions, stacked_metrics


def _try_repacked_layout(
    best_choices,
    category_inputs,
    stacked_metrics,
    chosen_positions,
    chosen_metrics,
    category_links,
    choice_by_cat,
    verbose,
):
    repacked = rectpack.try_repack_rectangles(
        [
            (entry["cat_id"], candidate.width, candidate.height)
            for entry, candidate in zip(category_inputs, best_choices)
        ],
        target_aspect=TARGET_ASPECT,
        gap=CATEGORY_REPACK_GAP,
        pack_algos=_RECTPACK_ALGOS,
    )
    if repacked is None:
        return chosen_positions, chosen_metrics
    repacked_positions, _ = repacked
    repacked_metrics = _layout_metrics(best_choices, repacked_positions, category_inputs)
    improves = _layout_improves(stacked_metrics, repacked_metrics)
    better_score = _layout_score(
        repacked_metrics,
        repacked_positions,
        category_links,
        choice_by_cat,
    ) < _layout_score(
        chosen_metrics,
        chosen_positions,
        category_links,
        choice_by_cat,
    )
    if improves and better_score:
        if verbose:
            print("[layout] category repack kept")
        return repacked_positions, repacked_metrics
    if verbose:
        print("[layout] category repack rolled back")
    return chosen_positions, chosen_metrics


def _affinity_order_candidates(layout_input: _AffinityLayoutInput) -> set[tuple[str, ...]]:
    order_candidates: set[tuple[str, ...]] = {
        tuple(cat_id for cat_id in layout_input.choice_by_cat),
        tuple(
            sorted(
                layout_input.choice_by_cat,
                key=lambda cat_id: layout_input.choice_by_cat[cat_id].width * layout_input.choice_by_cat[cat_id].height,
                reverse=True,
            )
        ),
    }
    seed_categories = sorted(
        layout_input.choice_by_cat,
        key=lambda cat_id: (
            layout_input.category_link_totals.get(cat_id, 0),
            layout_input.choice_by_cat[cat_id].used_area,
            layout_input.choice_by_cat[cat_id].width * layout_input.choice_by_cat[cat_id].height,
        ),
        reverse=True,
    )[:5]
    for seed in seed_categories:
        order = _greedy_affinity_order(
            seed,
            layout_input.choice_by_cat,
            layout_input.category_links,
            layout_input.category_link_totals,
        )
        order_candidates.add(order)
        order_candidates.add(tuple(reversed(order)))
    return order_candidates


def _affinity_width_candidates(best_choices, stacked_metrics) -> tuple[int, list[int]]:
    max_cat_width = max(choice.width for choice in best_choices)
    natural_cat_width = sum(
        choice.width for choice in best_choices
    ) + CATEGORY_REPACK_GAP * max(0, len(best_choices) - 1)
    width_candidates = sorted(
        {
            max_cat_width,
            stacked_metrics.total_width,
            max_cat_width + CATEGORY_REPACK_GAP + min(choice.width for choice in best_choices),
            int(math.ceil(math.sqrt(sum(choice.width * choice.height for choice in best_choices) * TARGET_ASPECT))),
            natural_cat_width,
        }
    )
    return max_cat_width, width_candidates


def _try_affinity_layout(layout_input: _AffinityLayoutInput):
    order_candidates = _affinity_order_candidates(layout_input)
    max_cat_width, width_candidates = _affinity_width_candidates(
        layout_input.best_choices,
        layout_input.stacked_metrics,
    )
    best_affinity_positions: dict[str, tuple[int, int]] | None = None
    best_affinity_metrics: rectpack.StackedLayoutMetrics | None = None
    for order in order_candidates:
        for width_limit in width_candidates:
            if width_limit < max_cat_width:
                continue
            positions = _row_pack_positions(order, width_limit, layout_input.choice_by_cat)
            metrics = _layout_metrics(layout_input.best_choices, positions, layout_input.category_inputs)
            if not _layout_improves(layout_input.stacked_metrics, metrics):
                continue
            if best_affinity_metrics is None or _layout_score(
                metrics,
                positions,
                layout_input.category_links,
                layout_input.choice_by_cat,
            ) < _layout_score(
                best_affinity_metrics,
                best_affinity_positions,
                layout_input.category_links,
                layout_input.choice_by_cat,  # type: ignore[arg-type]
            ):
                best_affinity_positions = positions
                best_affinity_metrics = metrics
    if best_affinity_positions is not None and best_affinity_metrics is not None:
        if _layout_score(
            best_affinity_metrics,
            best_affinity_positions,
            layout_input.category_links,
            layout_input.choice_by_cat,
        ) < _layout_score(
            layout_input.chosen_metrics,
            layout_input.chosen_positions,
            layout_input.category_links,
            layout_input.choice_by_cat,
        ):
            if layout_input.verbose:
                print("[layout] affinity layout kept")
            return best_affinity_positions, best_affinity_metrics
        if layout_input.verbose:
            print("[layout] affinity layout rolled back")
    return layout_input.chosen_positions, layout_input.chosen_metrics


def _category_band(candidate, cat_id: str, cat_x: int, cat_y: int, category_style) -> dict[str, Any]:
    return {
        "x": cat_x,
        "y": cat_y,
        "w": candidate.width,
        "h": candidate.height,
        "label": cat_id,
        **_category_band_style(cat_id, category_style),
    }


def _bucket_layout(
    candidate,
    cat_id: str,
    cat_nodes: list[Node],
    cat_x: int,
    cat_y: int,
) -> tuple[dict[str, Any], int, int, int]:
    width, height, cols = _dims(len(cat_nodes), len(cat_nodes))
    bx_local, by_local = candidate.positions.get(cat_id, (CAT_PAD_SIDE, CATEGORY_HEADER_H + CAT_PAD_TOP))
    return {
        "id": cat_id,
        "x": bx_local + cat_x,
        "y": by_local + cat_y,
        "w": width,
        "h": height,
        "label": cat_id,
    }, bx_local, by_local, cols


def _emit_category_layout(  # pylint: disable=too-many-locals
    *,
    entry: dict[str, Any],
    candidate: Any,
    chosen_positions: dict[str, tuple[int, int]],
    category_style: dict[str, dict[str, str]] | None,
    degrees: dict[str, int],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Build all rendered output structures for one category bucket."""
    vis_nodes: list[dict[str, Any]] = []
    cat_id = entry["cat_id"]
    cat_nodes = entry["nodes"]
    cat_x, cat_y = chosen_positions[cat_id]
    cat_band = _category_band(candidate, cat_id, cat_x, cat_y, category_style)
    bucket_rect, bx_local, by_local, cols = _bucket_layout(candidate, cat_id, cat_nodes, cat_x, cat_y)
    for index, node in enumerate(cat_nodes):
        node_x = int(bx_local + cat_x + _PAD_H + (index % cols) * _SPACING)
        node_y = int(by_local + cat_y + _PAD_TOP + (index // cols) * _SPACING)
        vis_nodes.append(_make_vis_node(node, node_x, node_y, category_style, degrees))
    return vis_nodes, bucket_rect, cat_band


def _emit_layout_output(category_inputs, best_choices, chosen_positions, category_style, degrees):
    vis_nodes: list[dict[str, Any]] = []
    bucket_rects: dict[str, dict[str, Any]] = {}
    cat_bands: dict[str, dict[str, Any]] = {}
    for entry, candidate in zip(category_inputs, best_choices):
        cat_id = entry["cat_id"]
        category_nodes, bucket_rects[cat_id], cat_bands[cat_id] = _emit_category_layout(
            entry=entry,
            candidate=candidate,
            chosen_positions=chosen_positions,
            category_style=category_style,
            degrees=degrees,
        )
        vis_nodes.extend(category_nodes)
    return vis_nodes, bucket_rects, cat_bands


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_layout(
    nodes: list[Node],
    edges: list[Edge],
    category_style: dict[str, dict[str, str]] | None = None,
    verbose: bool = False,
) -> tuple[list[dict], dict[str, dict], dict[str, dict]]:
    """Return (vis_nodes, bucket_rects, category_bands).

    vis_nodes:
        list of dicts shaped for vis-network.

    bucket_rects:
        keyed by category name; each value {id, x, y, w, h, label}.
        One entry per category (id == category name).

    category_bands:
        keyed by category name; each value {x, y, w, h, label, style}.
    """
    # Sort nodes by id for determinism
    # @cpt-begin:cpt-studio-algo-map-layout:p1:inst-compute-layout
    _sorted_nodes, degrees, grouped, category_links, category_link_totals = _group_layout_inputs(nodes, edges)

    # Build rectpack layout candidates per category
    # @cpt-begin:cpt-studio-algo-map-layout:p1:inst-build-candidates
    category_inputs = _build_category_inputs(grouped, verbose)
    if not category_inputs:
        return [], {}, {}
    # @cpt-end:cpt-studio-algo-map-layout:p1:inst-build-candidates

    # Optimize stacked arrangement
    # @cpt-begin:cpt-studio-algo-map-layout:p1:inst-optimize-stacked
    best_choices, choice_by_cat, chosen_positions, stacked_metrics = _optimize_stacked_layout(
        category_inputs, verbose
    )
    chosen_metrics = stacked_metrics
    # @cpt-end:cpt-studio-algo-map-layout:p1:inst-optimize-stacked

    # --- Try rectpack repack across categories ---
    # @cpt-begin:cpt-studio-algo-map-layout:p1:inst-repack-across
    chosen_positions, chosen_metrics = _try_repacked_layout(
        best_choices,
        category_inputs,
        stacked_metrics,
        chosen_positions,
        chosen_metrics,
        category_links,
        choice_by_cat,
        verbose,
    )
    # @cpt-end:cpt-studio-algo-map-layout:p1:inst-repack-across

    # --- Try affinity-ordered row-packs ---
    # @cpt-begin:cpt-studio-algo-map-layout:p1:inst-affinity-row-pack
    chosen_positions, chosen_metrics = _try_affinity_layout(_AffinityLayoutInput(
        best_choices=best_choices,
        category_inputs=category_inputs,
        stacked_metrics=stacked_metrics,
        chosen_positions=chosen_positions,
        chosen_metrics=chosen_metrics,
        category_links=category_links,
        category_link_totals=category_link_totals,
        choice_by_cat=choice_by_cat,
        verbose=verbose,
    ))
    # @cpt-end:cpt-studio-algo-map-layout:p1:inst-affinity-row-pack

    # --- Build output ---
    # @cpt-begin:cpt-studio-algo-map-layout:p1:inst-build-output
    return _emit_layout_output(category_inputs, best_choices, chosen_positions, category_style, degrees)
    # @cpt-end:cpt-studio-algo-map-layout:p1:inst-build-output
    # @cpt-end:cpt-studio-algo-map-layout:p1:inst-compute-layout
