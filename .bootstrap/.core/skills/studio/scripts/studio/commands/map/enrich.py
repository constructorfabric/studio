"""Per-edge content baking via utils.document.get_content_scoped.

For every cpt-edge with a real (non-phantom) target, look up the content block
defining the cpt-id at the target node and embed it into edge.refs[*].def_line /
def_snippet. File-link and dangling edges are skipped.

@cpt-algo:cpt-studio-algo-map-enrich:p1
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

from studio.utils.document import get_content_scoped, read_text_safe

from .model import Edge, Node, Ref


def enrich_edges(
    edges: Sequence[Edge],
    nodes: Sequence[Node],
    project_root_by_source: Dict[str, Path],
) -> None:
    """Mutate edges in place: replace each ref with one carrying def_line/def_snippet."""
    # @cpt-begin:cpt-studio-algo-map-enrich:p1:inst-enrich-edges
    by_id: Dict[str, Node] = {n.id: n for n in nodes}

    for e in edges:
        # File-link edges have no cpt-ID — skip entirely.
        if e.type == "file-link":
            continue
        # Dangling edges point at phantom nodes — no real file to look up.
        if e.dangling:
            continue

        target = by_id.get(e.to_id)
        if (
            target is None
            or target.kind != "markdown"
            or target.rel_path is None
            or target.source is None
        ):
            continue

        root = project_root_by_source.get(target.source)
        if root is None:
            continue

        target_path = root / target.rel_path

        new_refs = []
        for r in e.refs:
            if r.cpt_id is None:
                new_refs.append(r)
                continue
            line, snippet = _resolve_def(target_path, r.cpt_id)
            new_refs.append(
                Ref(
                    cpt_id=r.cpt_id,
                    line=r.line,
                    snippet=r.snippet,
                    def_line=line,
                    def_snippet=snippet,
                )
            )
        e.refs = new_refs
    # @cpt-end:cpt-studio-algo-map-enrich:p1:inst-enrich-edges


def _resolve_def(
    path: Path, cpt_id: str
) -> Tuple[Optional[int], Optional[str]]:
    """Return (def_line, def_snippet) for cpt_id defined in path, or (None, None).

    Uses get_content_scoped (real API: keyword arg id_value, base id only) to locate
    the content block.  We derive def_line by finding the **ID** definition line in
    the file directly, then use the content block as def_snippet.

    The stored cpt_id is phase-qualified (e.g. "cpt-foo:p1"); the markdown definition
    format uses the base id ("cpt-foo"), so we strip the phase suffix before matching.
    """
    # @cpt-begin:cpt-studio-algo-map-enrich:p1:inst-resolve-def
    base_id = cpt_id.split(":")[0]

    # Ask get_content_scoped for the content block associated with this id.
    # It returns (text, start_line, end_line) with 1-based line numbers, or None.
    result = get_content_scoped(path, id_value=base_id)

    # Whether or not get_content_scoped succeeded, find the actual definition line
    # by scanning for the **ID** marker line directly.
    def_line = _find_def_line(path, base_id)

    if def_line is None:
        return None, None

    if result is not None:
        text, _start, _end = result
        # Prepend the definition line itself to give fuller context in the snippet.
        lines = read_text_safe(path)
        if lines and def_line <= len(lines):
            id_line_text = lines[def_line - 1].rstrip()
            snippet = f"{id_line_text}\n{text}" if text else id_line_text
        else:
            snippet = text
    else:
        # Fallback: use a few lines around the definition line as the snippet.
        snippet = _lines_around(path, def_line, context=3)

    if not snippet:
        return def_line, None

    return def_line, snippet
    # @cpt-end:cpt-studio-algo-map-enrich:p1:inst-resolve-def


def _find_def_line(path: Path, base_id: str) -> Optional[int]:
    """Scan the file for the **ID**: `<base_id>` definition line.

    Returns the 1-based line number, or None if not found.
    """
    # @cpt-begin:cpt-studio-algo-map-enrich:p1:inst-find-def-line
    from studio.utils.document import scan_cpt_ids

    hits = scan_cpt_ids(path)
    for h in hits:
        if h.get("type") == "definition" and h.get("id") == base_id:
            return int(h["line"])
    return None
    # @cpt-end:cpt-studio-algo-map-enrich:p1:inst-find-def-line


def _lines_around(path: Path, center_line: int, context: int = 3) -> Optional[str]:
    """Return a few lines surrounding center_line (1-based) from path."""
    # @cpt-begin:cpt-studio-algo-map-enrich:p1:inst-lines-around
    lines = read_text_safe(path)
    if lines is None:
        return None
    start = max(0, center_line - 1)
    end = min(len(lines), center_line - 1 + context)
    selected = lines[start:end]
    return "\n".join(l.rstrip() for l in selected) or None
    # @cpt-end:cpt-studio-algo-map-enrich:p1:inst-lines-around
