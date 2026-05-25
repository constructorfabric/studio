from __future__ import annotations

import math
import itertools
import operator
from dataclasses import dataclass
from typing import Any


class Rectangle:
    __slots__ = ("width", "height", "x", "y", "rid")

    def __init__(self, x: int, y: int, width: int, height: int, rid: Any = None):
        self.width = width
        self.height = height
        self.x = x
        self.y = y
        self.rid = rid

    @property
    def bottom(self) -> int:
        return self.y

    @property
    def top(self) -> int:
        return self.y + self.height

    @property
    def left(self) -> int:
        return self.x

    @property
    def right(self) -> int:
        return self.x + self.width

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Rectangle):
            return False
        return (
            self.width == other.width
            and self.height == other.height
            and self.x == other.x
            and self.y == other.y
        )

    def __hash__(self) -> int:
        return hash((self.x, self.y, self.width, self.height))

    def area(self) -> int:
        return self.width * self.height

    def contains(self, rect: "Rectangle") -> bool:
        return (
            rect.y >= self.y
            and rect.x >= self.x
            and rect.y + rect.height <= self.y + self.height
            and rect.x + rect.width <= self.x + self.width
        )

    def intersects(self, rect: "Rectangle", edges: bool = False) -> bool:
        if edges:
            if (
                self.bottom > rect.top
                or self.top < rect.bottom
                or self.left > rect.right
                or self.right < rect.left
            ):
                return False
        else:
            if (
                self.bottom >= rect.top
                or self.top <= rect.bottom
                or self.left >= rect.right
                or self.right <= rect.left
            ):
                return False
        return True


class PackingAlgorithm:
    def __init__(self, width: int, height: int, rot: bool = True, bid: Any = None, *args: Any, **kwargs: Any):
        self.width = width
        self.height = height
        self.rot = rot
        self.bid = bid
        self._surface = Rectangle(0, 0, width, height)
        self.reset()

    def __len__(self) -> int:
        return len(self.rectangles)

    def __iter__(self):
        return iter(self.rectangles)

    def _fits_surface(self, width: int, height: int) -> bool:
        if self.rot and (width > self.width or height > self.height):
            width, height = height, width
        return width <= self.width and height <= self.height

    def reset(self) -> None:
        self.rectangles: list[Rectangle] = []

    def rect_list(self) -> list[tuple[int, int, int, int, Any]]:
        return [(r.x, r.y, r.width, r.height, r.rid) for r in self.rectangles]


_FIRST_ITEM = operator.itemgetter(0)


class MaxRects(PackingAlgorithm):
    def __init__(self, width: int, height: int, rot: bool = True, *args: Any, **kwargs: Any):
        super().__init__(width, height, rot, *args, **kwargs)

    def _rect_fitness(self, max_rect: Rectangle, width: int, height: int) -> int | None:
        if width <= max_rect.width and height <= max_rect.height:
            return 0
        return None

    def _select_position(self, w: int, h: int) -> tuple[Rectangle | None, Rectangle | None]:
        if not self._max_rects:
            return None, None

        fitn = (
            (self._rect_fitness(m, w, h), w, h, m)
            for m in self._max_rects
            if self._rect_fitness(m, w, h) is not None
        )
        fitr = (
            (self._rect_fitness(m, h, w), h, w, m)
            for m in self._max_rects
            if self._rect_fitness(m, h, w) is not None
        )
        fit = itertools.chain(fitn, [] if not self.rot else fitr)

        try:
            _, w2, h2, m = min(fit, key=_FIRST_ITEM)
        except ValueError:
            return None, None

        return Rectangle(m.x, m.y, w2, h2), m

    def _generate_splits(self, m: Rectangle, r: Rectangle) -> list[Rectangle]:
        new_rects: list[Rectangle] = []
        if r.left > m.left:
            new_rects.append(Rectangle(m.left, m.bottom, r.left - m.left, m.height))
        if r.right < m.right:
            new_rects.append(Rectangle(r.right, m.bottom, m.right - r.right, m.height))
        if r.top < m.top:
            new_rects.append(Rectangle(m.left, r.top, m.width, m.top - r.top))
        if r.bottom > m.bottom:
            new_rects.append(Rectangle(m.left, m.bottom, m.width, r.bottom - m.bottom))
        return new_rects

    def _split(self, rect: Rectangle) -> None:
        max_rects: list[Rectangle] = []
        for r in self._max_rects:
            if r.intersects(rect):
                max_rects.extend(self._generate_splits(r, rect))
            else:
                max_rects.append(r)
        self._max_rects = max_rects

    def _remove_duplicates(self) -> None:
        contained: set[Rectangle] = set()
        for m1, m2 in itertools.combinations(self._max_rects, 2):
            if m1.contains(m2):
                contained.add(m2)
            elif m2.contains(m1):
                contained.add(m1)
        self._max_rects = [m for m in self._max_rects if m not in contained]

    def fitness(self, width: int, height: int) -> int | None:
        rect, max_rect = self._select_position(width, height)
        if rect is None or max_rect is None:
            return None
        return self._rect_fitness(max_rect, rect.width, rect.height)

    def add_rect(self, width: int, height: int, rid: Any = None) -> Rectangle | None:
        rect, _ = self._select_position(width, height)
        if not rect:
            return None
        self._split(rect)
        self._remove_duplicates()
        rect.rid = rid
        self.rectangles.append(rect)
        return rect

    def reset(self) -> None:
        super().reset()
        self._max_rects = [Rectangle(0, 0, self.width, self.height)]


class MaxRectsBl(MaxRects):
    def _select_position(self, w: int, h: int) -> tuple[Rectangle | None, Rectangle | None]:
        fitn = (
            (m.y + h, m.x, w, h, m)
            for m in self._max_rects
            if self._rect_fitness(m, w, h) is not None
        )
        fitr = (
            (m.y + w, m.x, h, w, m)
            for m in self._max_rects
            if self._rect_fitness(m, h, w) is not None
        )
        fit = itertools.chain(fitn, [] if not self.rot else fitr)
        try:
            _, _, w2, h2, m = min(fit, key=_FIRST_ITEM)
        except ValueError:
            return None, None
        return Rectangle(m.x, m.y, w2, h2), m


class MaxRectsBssf(MaxRects):
    def _rect_fitness(self, max_rect: Rectangle, width: int, height: int) -> int | None:
        if width > max_rect.width or height > max_rect.height:
            return None
        return min(max_rect.width - width, max_rect.height - height)


class MaxRectsBaf(MaxRects):
    def _rect_fitness(self, max_rect: Rectangle, width: int, height: int) -> int | None:
        if width > max_rect.width or height > max_rect.height:
            return None
        return (max_rect.width * max_rect.height) - (width * height)


class MaxRectsBlsf(MaxRects):
    def _rect_fitness(self, max_rect: Rectangle, width: int, height: int) -> int | None:
        if width > max_rect.width or height > max_rect.height:
            return None
        return max(max_rect.width - width, max_rect.height - height)


SORT_AREA = lambda rectlist: sorted(rectlist, reverse=True, key=lambda r: r[0] * r[1])
SORT_WIDTH = lambda rectlist: sorted(rectlist, reverse=True, key=lambda r: (r[0], r[1], r[0] * r[1]))
SORT_HEIGHT = lambda rectlist: sorted(rectlist, reverse=True, key=lambda r: (r[1], r[0], r[0] * r[1]))
SORT_PERIMETER = lambda rectlist: sorted(rectlist, reverse=True, key=lambda r: (r[0] + r[1], r[0] * r[1]))
SORT_MAXSIDE = lambda rectlist: sorted(rectlist, reverse=True, key=lambda r: (max(r[0], r[1]), r[0] * r[1]))


@dataclass(frozen=True)
class LayoutCandidate:
    positions: dict[Any, tuple[int, int]]
    width: int
    height: int
    used_area: int
    density: float
    aspect: float
    row_count: int


@dataclass(frozen=True)
class CategoryIterationStats:
    category_id: Any
    width: int
    height: int
    density: float
    row_count: int
    candidate_index: int


@dataclass(frozen=True)
class StackedLayoutMetrics:
    total_width: int
    total_height: int
    total_aspect: float
    total_density: float
    total_category_density: float
    aspect_error: float


@dataclass(frozen=True)
class StackedLayoutSnapshot:
    iteration: int
    metrics: StackedLayoutMetrics
    categories: tuple[CategoryIterationStats, ...]


def _pack_extent(pos: dict[Any, tuple[int, int]], dims_map: dict[Any, tuple[int, int]]) -> tuple[int, int]:
    mx = max(px + dims_map[rid][0] for rid, (px, _) in pos.items())
    my = max(py + dims_map[rid][1] for rid, (_, py) in pos.items())
    return mx, my


def _candidate_score(candidate: LayoutCandidate, target_aspect: float) -> tuple[float, float, float, int, int]:
    aspect_loss = abs(math.log(max(candidate.aspect, 1e-9) / target_aspect))
    density_loss = 1.0 - candidate.density
    balanced_loss = 0.5 * aspect_loss + 0.5 * density_loss
    return (balanced_loss, aspect_loss, density_loss, candidate.height, candidate.width)


def _prune_layout_candidates(candidates: list[LayoutCandidate], target_aspect: float, limit: int) -> list[LayoutCandidate]:
    by_size: dict[tuple[int, int], LayoutCandidate] = {}
    for candidate in candidates:
        key = (candidate.width, candidate.height)
        current = by_size.get(key)
        if current is None or _candidate_score(candidate, target_aspect) < _candidate_score(current, target_aspect):
            by_size[key] = candidate

    deduped = list(by_size.values())
    pruned = [
        candidate
        for candidate in deduped
        if not any(
            other.width <= candidate.width
            and other.height <= candidate.height
            and (other.width < candidate.width or other.height < candidate.height)
            for other in deduped
            if other is not candidate
        )
    ]

    ranked = sorted(pruned or deduped, key=lambda candidate: _candidate_score(candidate, target_aspect))
    if len(ranked) <= limit:
        return ranked

    keep = ranked[: max(8, limit // 2)]
    by_width = sorted(ranked, key=lambda candidate: (candidate.width, candidate.height))
    sample_indexes = {0, len(by_width) - 1}
    sample_count = max(2, limit - len(keep))
    for idx in range(1, sample_count + 1):
        sample_indexes.add(round(idx * (len(by_width) - 1) / (sample_count + 1)))
    for idx in sorted(sample_indexes):
        keep.append(by_width[idx])

    final: dict[tuple[int, int], LayoutCandidate] = {}
    for candidate in keep:
        key = (candidate.width, candidate.height)
        current = final.get(key)
        if current is None or _candidate_score(candidate, target_aspect) < _candidate_score(current, target_aspect):
            final[key] = candidate
    return sorted(final.values(), key=lambda candidate: _candidate_score(candidate, target_aspect))[:limit]


def generate_layout_candidates(
    items: list[tuple[Any, int, int]],
    *,
    gap: int,
    target_aspect: float = 16 / 9,
    pad_side: int = 0,
    pad_top: int = 0,
    pad_bottom: int = 0,
    header_height: int = 0,
    pack_algos: tuple[type[PackingAlgorithm], ...] | None = None,
    limit: int = 16,
) -> list[LayoutCandidate]:
    padded_items = [(rid, width + gap, height + gap) for rid, width, height in items]
    dims_map = {rid: (width, height) for rid, width, height in items}
    used_area = sum(width * height for _, width, height in items)
    padded_area = sum(width * height for _, width, height in padded_items)
    natural_width = sum(width for _, width, _ in padded_items)
    max_width = max(width for _, width, _ in padded_items)
    bin_height = sum(height for _, _, height in padded_items)
    width_floor = max(max_width, int(math.ceil(math.sqrt(padded_area * target_aspect))))
    width_cap = min(natural_width, max(width_floor, int(math.ceil(math.sqrt(padded_area) * 3.0))))
    if len(items) <= 8:
        width_cap = natural_width

    width_candidates = {max_width, width_floor, width_cap, natural_width}
    if width_cap > max_width:
        steps = max(8, min(20, len(items) * 2))
        for idx in range(steps):
            ratio = idx / max(1, steps - 1)
            width_candidates.add(int(round(max_width + (width_cap - max_width) * ratio)))

    algo_list = pack_algos or (MaxRectsBssf, MaxRectsBaf, MaxRectsBl, MaxRectsBlsf)
    candidates: list[LayoutCandidate] = []
    for pack_algo in algo_list:
        for bin_width in sorted(width for width in width_candidates if max_width <= width <= natural_width):
            packer = newPacker(pack_algo=pack_algo, sort_algo=SORT_AREA, rotation=False)
            packer.add_bin(bin_width, bin_height, 1)
            for rid, width, height in padded_items:
                packer.add_rect(width, height, rid)
            packer.pack()
            rects = packer.rect_list()
            if len(rects) != len(items):
                continue

            pos = {
                rid: (pad_side + x, header_height + pad_top + y)
                for _, x, y, _, _, rid in rects
            }
            mx, my = _pack_extent(pos, dims_map)
            band_width = mx + pad_side
            band_height = my + pad_bottom
            aspect = band_width / max(1, band_height)
            density = used_area / max(1, band_width * band_height)
            row_count = len({y for _, _, y, _, _, _ in rects})
            candidates.append(
                LayoutCandidate(
                    positions=pos,
                    width=band_width,
                    height=band_height,
                    used_area=used_area,
                    density=density,
                    aspect=aspect,
                    row_count=row_count,
                )
            )

    if not candidates:
        raise RuntimeError("rectpack could not place all rectangles")

    return _prune_layout_candidates(candidates, target_aspect, limit)


def compute_stacked_metrics(
    choices: list[LayoutCandidate],
    *,
    category_gap: int,
    target_aspect: float = 16 / 9,
) -> StackedLayoutMetrics:
    if not choices:
        return StackedLayoutMetrics(
            total_width=0,
            total_height=0,
            total_aspect=0.0,
            total_density=0.0,
            total_category_density=0.0,
            aspect_error=0.0,
        )

    total_width = max(choice.width for choice in choices)
    total_height = sum(choice.height for choice in choices) + category_gap * max(0, len(choices) - 1)
    total_used_area = sum(choice.used_area for choice in choices)
    total_category_area = sum(choice.width * choice.height for choice in choices)
    total_aspect = total_width / max(1, total_height)
    total_density = total_used_area / max(1, total_width * total_height)
    total_category_density = total_category_area / max(1, total_width * total_height)
    aspect_error = abs(total_aspect - target_aspect) / max(target_aspect, 1e-9)
    return StackedLayoutMetrics(
        total_width=total_width,
        total_height=total_height,
        total_aspect=total_aspect,
        total_density=total_density,
        total_category_density=total_category_density,
        aspect_error=aspect_error,
    )


def try_repack_rectangles(
    items: list[tuple[Any, int, int]],
    *,
    target_aspect: float = 16 / 9,
    gap: int = 0,
    pack_algos: tuple[type[PackingAlgorithm], ...] | None = None,
) -> tuple[dict[Any, tuple[int, int]], StackedLayoutMetrics] | None:
    if not items:
        return None

    used_area = sum(width * height for _, width, height in items)
    padded_items = [(rid, width + gap, height + gap) for rid, width, height in items]
    total_area = max(1, used_area)
    natural_width = sum(width for _, width, _ in padded_items)
    max_width = max(width for _, width, _ in padded_items)
    bin_height = sum(height for _, _, height in padded_items)
    width_floor = max(max_width, int(math.ceil(math.sqrt(total_area * target_aspect))))
    width_cap = min(natural_width, max(width_floor, int(math.ceil(math.sqrt(total_area) * 2.5))))
    width_candidates = {max_width, width_floor, width_cap, natural_width}
    if width_cap > max_width:
        steps = max(6, min(16, len(items) * 2))
        for idx in range(steps):
            ratio = idx / max(1, steps - 1)
            width_candidates.add(int(round(max_width + (width_cap - max_width) * ratio)))

    dims_map = {rid: (width, height) for rid, width, height in items}
    algo_list = pack_algos or (MaxRectsBssf, MaxRectsBaf, MaxRectsBl, MaxRectsBlsf)
    sort_variants = (
        SORT_AREA,
        SORT_WIDTH,
        SORT_HEIGHT,
        SORT_PERIMETER,
        SORT_MAXSIDE,
    )
    best_positions: dict[Any, tuple[int, int]] | None = None
    best_metrics: StackedLayoutMetrics | None = None
    best_score: tuple[float, float, float, int, int] | None = None

    for sort_algo in sort_variants:
        for pack_algo in algo_list:
            for bin_width in sorted(width for width in width_candidates if max_width <= width <= natural_width):
                packer = newPacker(pack_algo=pack_algo, sort_algo=sort_algo, rotation=False)
                packer.add_bin(bin_width, bin_height, 1)
                for rid, width, height in padded_items:
                    packer.add_rect(width, height, rid)
                packer.pack()
                rects = packer.rect_list()
                if len(rects) != len(items):
                    continue

                positions = {rid: (x + gap // 2, y + gap // 2) for _, x, y, _, _, rid in rects}
                mx, my = _pack_extent(positions, dims_map)
                metrics = StackedLayoutMetrics(
                    total_width=mx,
                    total_height=my,
                    total_aspect=mx / max(1, my),
                    total_density=used_area / max(1, mx * my),
                    total_category_density=1.0,
                    aspect_error=abs(mx / max(1, my) - target_aspect) / max(target_aspect, 1e-9),
                )
                score = (
                    0.5 * metrics.aspect_error + 0.5 * (1.0 - metrics.total_density),
                    metrics.aspect_error,
                    1.0 - metrics.total_density,
                    metrics.total_height,
                    metrics.total_width,
                )
                if best_score is None or score < best_score:
                    best_score = score
                    best_positions = positions
                    best_metrics = metrics

    if best_positions is None or best_metrics is None:
        return None

    return best_positions, best_metrics


def optimize_stacked_categories(
    category_candidates: list[tuple[Any, list[LayoutCandidate]]],
    *,
    category_gap: int,
    target_aspect: float = 16 / 9,
    aspect_tolerance: float = 0.10,
    max_iterations: int = 10,
) -> tuple[list[LayoutCandidate], list[int], tuple[StackedLayoutSnapshot, ...]]:
    if not category_candidates:
        return [], [], ()

    indexes = [0 for _ in category_candidates]
    snapshots: list[StackedLayoutSnapshot] = []

    def current_choices(current_indexes: list[int]) -> list[LayoutCandidate]:
        return [candidates[idx] for (_, candidates), idx in zip(category_candidates, current_indexes)]

    for iteration in range(1, max_iterations + 1):
        choices = current_choices(indexes)
        metrics = compute_stacked_metrics(choices, category_gap=category_gap, target_aspect=target_aspect)
        snapshots.append(
            StackedLayoutSnapshot(
                iteration=iteration,
                metrics=metrics,
                categories=tuple(
                    CategoryIterationStats(
                        category_id=category_id,
                        width=choice.width,
                        height=choice.height,
                        density=choice.density,
                        row_count=choice.row_count,
                        candidate_index=indexes[idx],
                    )
                    for idx, ((category_id, _), choice) in enumerate(zip(category_candidates, choices))
                ),
            )
        )

        if metrics.aspect_error <= aspect_tolerance:
            break

        need_wider = metrics.total_aspect < target_aspect
        if need_wider:
            category_order = sorted(
                (idx for idx, choice in enumerate(choices) if choice.row_count >= 2),
                key=lambda idx: (choices[idx].width, choices[idx].height),
            )
        else:
            category_order = sorted(
                range(len(choices)),
                key=lambda idx: (choices[idx].width, choices[idx].height),
                reverse=True,
            )

        changed = False
        for category_index in category_order:
            current = choices[category_index]
            _, candidates = category_candidates[category_index]
            if need_wider:
                candidate_indexes = [
                    idx for idx, candidate in enumerate(candidates)
                    if candidate.width > current.width
                ]
                candidate_indexes.sort(key=lambda idx: (candidates[idx].width, _candidate_score(candidates[idx], target_aspect)))
            else:
                candidate_indexes = [
                    idx for idx, candidate in enumerate(candidates)
                    if candidate.width < current.width
                ]
                candidate_indexes.sort(key=lambda idx: (-candidates[idx].width, _candidate_score(candidates[idx], target_aspect)))

            best_next_index: int | None = None
            best_next_metrics: StackedLayoutMetrics | None = None
            for next_index in candidate_indexes:
                trial_indexes = list(indexes)
                trial_indexes[category_index] = next_index
                trial_choices = current_choices(trial_indexes)
                trial_metrics = compute_stacked_metrics(trial_choices, category_gap=category_gap, target_aspect=target_aspect)
                if trial_metrics.total_density + 1e-9 < metrics.total_density:
                    continue
                if trial_metrics.aspect_error > metrics.aspect_error + 1e-9:
                    continue
                if trial_metrics.total_category_density + 1e-9 < metrics.total_category_density:
                    continue

                if best_next_metrics is None or (
                    trial_metrics.aspect_error,
                    -trial_metrics.total_density,
                    -trial_metrics.total_category_density,
                    abs(trial_choices[category_index].width - current.width),
                ) < (
                    best_next_metrics.aspect_error,
                    -best_next_metrics.total_density,
                    -best_next_metrics.total_category_density,
                    abs(candidates[best_next_index].width - current.width) if best_next_index is not None else 0,
                ):
                    best_next_index = next_index
                    best_next_metrics = trial_metrics

            if best_next_index is not None:
                indexes[category_index] = best_next_index
                changed = True
                break

        if not changed:
            break

    return current_choices(indexes), indexes, tuple(snapshots)


class _OfflinePacker:
    def __init__(self, pack_algo: type[PackingAlgorithm] = MaxRectsBssf, sort_algo = SORT_AREA, rotation: bool = True):
        self._pack_algo = pack_algo
        self._sort_algo = sort_algo
        self._rotation = rotation
        self._bins: list[tuple[int, int, Any]] = []
        self._avail_rect: list[tuple[int, int, Any]] = []
        self._packed_bins: list[PackingAlgorithm] = []

    def add_bin(self, width: int, height: int, count: int = 1, bid: Any = None) -> None:
        for _ in range(count):
            self._bins.append((width, height, bid))

    def add_rect(self, width: int, height: int, rid: Any = None) -> None:
        self._avail_rect.append((width, height, rid))

    def pack(self) -> None:
        pending = self._sort_algo(self._avail_rect) if self._sort_algo else list(self._avail_rect)
        self._packed_bins = []
        for width, height, bid in self._bins:
            if not pending:
                break
            pbin = self._pack_algo(width, height, rot=self._rotation, bid=bid)
            remaining: list[tuple[int, int, Any]] = []
            for rw, rh, rid in pending:
                if pbin.add_rect(rw, rh, rid=rid) is None:
                    remaining.append((rw, rh, rid))
            self._packed_bins.append(pbin)
            pending = remaining

    def rect_list(self) -> list[tuple[int, int, int, int, int, Any]]:
        packed: list[tuple[int, int, int, int, int, Any]] = []
        for bidx, pbin in enumerate(self._packed_bins):
            for x, y, w, h, rid in pbin.rect_list():
                packed.append((bidx, x, y, w, h, rid))
        return packed

    def __len__(self) -> int:
        return len(self._packed_bins)

    def __getitem__(self, key: int) -> PackingAlgorithm:
        return self._packed_bins[key]

    def __iter__(self):
        return iter(self._packed_bins)


def newPacker(*, pack_algo: type[PackingAlgorithm] = MaxRectsBssf, sort_algo = SORT_AREA, rotation: bool = True, **kwargs: Any) -> _OfflinePacker:
    return _OfflinePacker(pack_algo=pack_algo, sort_algo=sort_algo, rotation=rotation)
