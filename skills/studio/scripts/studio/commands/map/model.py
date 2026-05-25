"""Data model for cfs map graph.

@cpt-algo:cpt-studio-algo-map-data-model:p1
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional


NodeKind = Literal["markdown", "source", "phantom-cpt"]
EdgeType = Literal["file-link", "cpt-doc", "cpt-impl"]
CategoryOrigin = Literal["override", "registry", "parent-dir", "phantom"]
MarkerKind = Literal["scope", "block-begin", "block-end", "md-ref", "md-def"]


def node_id(source: str, rel_path: str) -> str:
    """Canonical node id: '<source>:<rel-path>'."""
    # @cpt-begin:cpt-studio-algo-map-data-model:p1:inst-node-id
    return f"{source}:{rel_path}"
    # @cpt-end:cpt-studio-algo-map-data-model:p1:inst-node-id


def phantom_id(cpt_id: str) -> str:
    """Canonical phantom node id for an undefined cpt-ID."""
    # @cpt-begin:cpt-studio-algo-map-data-model:p1:inst-phantom-id
    return f"phantom:{cpt_id}"
    # @cpt-end:cpt-studio-algo-map-data-model:p1:inst-phantom-id


# @cpt-begin:cpt-studio-algo-map-data-model:p1:inst-cpt-use
@dataclass(frozen=True)
class CptUse:
    cpt_id: str
    line: int
    snippet: str
    marker_kind: MarkerKind

    def to_dict(self) -> dict:
        return {
            "cpt_id": self.cpt_id,
            "line": self.line,
            "snippet": self.snippet,
            "marker_kind": self.marker_kind,
        }
# @cpt-end:cpt-studio-algo-map-data-model:p1:inst-cpt-use


# @cpt-begin:cpt-studio-algo-map-data-model:p1:inst-ref
@dataclass(frozen=True)
class Ref:
    cpt_id: Optional[str]
    line: int
    snippet: str
    def_line: Optional[int]
    def_snippet: Optional[str]

    def to_dict(self) -> dict:
        return {
            "cpt_id": self.cpt_id,
            "line": self.line,
            "snippet": self.snippet,
            "def_line": self.def_line,
            "def_snippet": self.def_snippet,
        }
# @cpt-end:cpt-studio-algo-map-data-model:p1:inst-ref


# @cpt-begin:cpt-studio-algo-map-data-model:p1:inst-node
@dataclass
class Node:
    id: str
    rel_path: Optional[str]
    source: Optional[str]
    kind: NodeKind
    language: Optional[str]
    category: str
    category_origin: CategoryOrigin
    content: Optional[str]
    loc: int
    cpt_defs: List[str] = field(default_factory=list)
    cpt_uses: List[CptUse] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "rel_path": self.rel_path,
            "source": self.source,
            "kind": self.kind,
            "language": self.language,
            "category": self.category,
            "category_origin": self.category_origin,
            "content": self.content,
            "loc": self.loc,
            "cpt_defs": list(self.cpt_defs),
            "cpt_uses": [u.to_dict() for u in self.cpt_uses],
        }
# @cpt-end:cpt-studio-algo-map-data-model:p1:inst-node


# @cpt-begin:cpt-studio-algo-map-data-model:p1:inst-edge
@dataclass
class Edge:
    id: str
    from_id: str
    to_id: str
    type: EdgeType
    refs: List[Ref]
    cross_repo: bool
    dangling: bool

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from": self.from_id,
            "to": self.to_id,
            "type": self.type,
            "refs": [r.to_dict() for r in self.refs],
            "cross_repo": self.cross_repo,
            "dangling": self.dangling,
        }
# @cpt-end:cpt-studio-algo-map-data-model:p1:inst-edge
