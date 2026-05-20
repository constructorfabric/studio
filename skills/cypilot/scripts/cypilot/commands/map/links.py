"""Markdown→markdown file-link edges.

@cpt-flow:cpt-cypilot-flow-map-file-links:p1
@cpt-algo:cpt-cypilot-algo-map-resolve-link:p1
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

from .model import Edge, Node, Ref


# Matches markdown links: [label](target) — captures the bare target before any '#' fragment.
_LINK_RE = re.compile(r"\[(?P<label>[^\]]*?)\]\((?P<target>[^)\s#]+)(?:#[^)]*)?\)")


def extract_file_links(nodes: Sequence[Node], project_root: Optional[Union[Path, str]] = None) -> List[Edge]:
    """Return markdown→markdown file-link edges. Source nodes are ignored.

    Args:
        nodes: Sequence of Node objects from scan_repo
        project_root: Optional project root path. If not provided, returns empty list.
    """
    if project_root is None:
        return []

    project_root = Path(project_root)
    md_nodes = [n for n in nodes if n.kind == "markdown"]
    by_rel: Dict[str, Node] = {n.rel_path: n for n in md_nodes if n.rel_path}

    edges: List[Edge] = []
    edge_id = 0
    for src in md_nodes:
        if not src.rel_path:
            continue

        # Load markdown content from disk since scan layer sets content=None
        content = _load_markdown_content(project_root, src.rel_path)
        if not content:
            continue

        targets_seen: set[str] = set()
        for m in _LINK_RE.finditer(content):
            target = m.group("target").strip()
            resolved = _resolve(src.rel_path, target, set(by_rel.keys()))
            if resolved is None:
                continue
            if resolved == src.rel_path:
                continue  # no self-links
            if resolved in targets_seen:
                continue  # dedupe per (src, target)
            targets_seen.add(resolved)
            tgt = by_rel.get(resolved)
            if tgt is None:
                continue
            line_no = content[: m.start()].count("\n") + 1
            snippet = _line_at(content, m.start())
            edges.append(Edge(
                id=f"fl-{edge_id}",
                from_id=src.id,
                to_id=tgt.id,
                type="file-link",
                refs=[Ref(cpt_id=None, line=line_no, snippet=snippet, def_line=None, def_snippet=None)],
                cross_repo=(src.source != tgt.source),
                dangling=False,
            ))
            edge_id += 1
    return edges


def _load_markdown_content(project_root: Path, rel_path: str) -> Optional[str]:
    """Load markdown content from disk."""
    from cypilot.utils.document import read_text_safe

    file_path = project_root / rel_path
    if not file_path.is_file():
        return None

    content = read_text_safe(file_path)
    if not content:
        return None

    # Handle both list and string returns from read_text_safe
    if isinstance(content, list):
        return "\n".join(content)
    return content


def _resolve(source_rel: str, target: str, known: set[str]) -> Optional[str]:
    """Resolve a markdown link target to a known rel_path. Returns None if not found."""
    target = target.strip()
    if not target or target.startswith(("http://", "https://", "mailto:")):
        return None
    target = target.split("?", 1)[0].split("#", 1)[0]
    if not target:
        return None

    candidates = _slug_candidates(source_rel, target)
    for cand in candidates:
        if cand in known:
            return cand
    return None


def _slug_candidates(source_rel: str, target: str) -> List[str]:
    parts = source_rel.split("/")
    source_dir = "/".join(parts[:-1])
    candidates: List[str] = []

    if target.startswith("/"):
        base = target.lstrip("/")
        candidates.append(base)
        if not base.endswith(".md"):
            candidates.append(base + ".md")
        return candidates

    joined = _posix_normpath(f"{source_dir}/{target}" if source_dir else target)
    candidates.append(joined)
    if not joined.endswith(".md"):
        candidates.append(joined + ".md")
    return candidates


def _posix_normpath(path: str) -> str:
    parts: List[str] = []
    for seg in path.split("/"):
        if not seg or seg == ".":
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts)


def _line_at(content: str, offset: int) -> str:
    line_start = content.rfind("\n", 0, offset) + 1
    line_end = content.find("\n", offset)
    if line_end == -1:
        line_end = len(content)
    return content[line_start:line_end]
