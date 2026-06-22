"""cpt-doc and cpt-impl edges, plus phantom-cpt nodes for undefined ids.

@cpt-algo:cpt-studio-algo-map-cpt-edges:p1
@cpt-algo:cpt-studio-algo-map-build-cpt-edges:p1
@cpt-dod:cpt-studio-dod-dependency-mapping-phantoms:p1
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from .model import Edge, Node, Ref, phantom_id


def _definition_maps(nodes: Sequence[Node]) -> Tuple[Dict[str, Node], Dict[str, Node]]:
    def_map: Dict[str, Node] = {}
    base_def_map: Dict[str, Node] = {}
    for node in nodes:
        if node.kind != "markdown":
            continue
        for definition in node.cpt_defs:
            def_map.setdefault(definition, node)
            base_def_map.setdefault(definition.split(":")[0], node)
    return def_map, base_def_map


def _resolve_cpt_target(src: Node, use, def_map: Dict[str, Node], base_def_map: Dict[str, Node], phantoms: Dict[str, Node]):
    target = def_map.get(use.cpt_id) or base_def_map.get(use.cpt_id.split(":")[0])
    if target is None:
        phantom = phantoms.get(use.cpt_id)
        if phantom is None:
            phantom = Node(
                id=phantom_id(use.cpt_id),
                rel_path=None,
                source=None,
                kind="phantom-cpt",
                language=None,
                category="_undefined",
                category_origin="phantom",
                content=None,
                loc=0,
                cpt_defs=[],
                cpt_uses=[],
            )
            phantoms[use.cpt_id] = phantom
        return phantom.id, True, False
    if target.id == src.id:
        return None, False, False
    return target.id, False, src.source != target.source


def _append_cpt_edge(edges: List[Edge], by_key: Dict[Tuple[str, str, str], Edge], edge_id: int, src: Node, use, to_id: str, dangling: bool, cross_repo: bool) -> int:
    edge_type = "cpt-doc" if src.kind == "markdown" else "cpt-impl"
    key = (src.id, to_id, use.cpt_id)
    ref = Ref(
        cpt_id=use.cpt_id,
        line=use.line,
        snippet=use.snippet,
        def_line=None,
        def_snippet=None,
    )
    existing = by_key.get(key)
    if existing is not None:
        existing.refs.append(ref)
        return edge_id
    new_edge = Edge(
        id=f"cpt-{edge_id}",
        from_id=src.id,
        to_id=to_id,
        type=edge_type,
        refs=[ref],
        cross_repo=cross_repo,
        dangling=dangling,
    )
    edges.append(new_edge)
    by_key[key] = new_edge
    return edge_id + 1


def build_cpt_edges(nodes: Sequence[Node]) -> Tuple[List[Edge], List[Node]]:
    """Return (edges, phantom_nodes).

    For each cpt-use on any node, find the markdown node that defines that cpt-id
    and emit an edge:
      - cpt-doc  when from-node is markdown
      - cpt-impl when from-node is source

    Self-edges (definer using its own id) are dropped. Markdown md-def entries in
    cpt_uses are ignored as "uses" — they are definitions, not consumers.

    A cpt-id used somewhere but defined nowhere produces a phantom-cpt node and
    a dangling=True edge into it.

    Multiple uses of the same cpt-id from a single source node toward the same
    target are collapsed into one Edge with multiple Refs.
    """
    # Index: cpt-id → defining markdown node (first wins).
    # Two entries per def: phase-qualified ("cpt-foo:p1") and base ("cpt-foo").
    # Phase-qualified takes priority; base-id serves as fallback for md-refs that
    # omit the phase annotation.
    # @cpt-begin:cpt-studio-algo-map-cpt-edges:p1:inst-build-cpt-edges
    def_map, base_def_map = _definition_maps(nodes)

    phantoms: Dict[str, Node] = {}
    edges: List[Edge] = []
    edge_id = 0
    by_key: Dict[Tuple[str, str, str], Edge] = {}

    # @cpt-begin:cpt-studio-algo-map-cpt-edges:p1:inst-iterate-uses
    for src in nodes:
        if src.kind == "phantom-cpt":
            continue
        for use in src.cpt_uses:
            if use.marker_kind == "md-def":
                continue  # definitions are not uses
            resolved = _resolve_cpt_target(src, use, def_map, base_def_map, phantoms)
            if resolved[0] is None:
                continue
            to_id, dangling, cross_repo = resolved
            edge_id = _append_cpt_edge(
                edges, by_key, edge_id, src, use, to_id, dangling, cross_repo
            )
    # @cpt-end:cpt-studio-algo-map-cpt-edges:p1:inst-iterate-uses
    return edges, list(phantoms.values())
    # @cpt-end:cpt-studio-algo-map-cpt-edges:p1:inst-build-cpt-edges
