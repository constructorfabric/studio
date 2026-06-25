"""Markdown→markdown file-link edges.

@cpt-algo:cpt-studio-algo-map-file-links:p1
@cpt-algo:cpt-studio-algo-map-resolve-link:p1
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from .model import Edge, Node, Ref


# Matches markdown links: [label](target) — captures the bare target before any '#' fragment.
_LINK_RE = re.compile(r"\[(?P<label>[^\]]*?)\]\((?P<target>[^)\s#]+)(?:#[^)]*)?\)")

# Matches prose path references of the form `{var}/path/to/file.md`. Required
# trailing `.md` keeps us from matching bare `{var}` placeholders.
_VAR_PATH_RE = re.compile(
    r"\{(?P<var>[a-zA-Z_][a-zA-Z0-9_.\-]*)\}"
    r"(?P<rest>/[^\s`)\]\"]*?\.md)\b"
)


def _link_edge_targets(content: str, src: Node, known: set[str], template_vars: Dict[str, str]):
    # @cpt-begin:cpt-studio-algo-map-file-links:p1:inst-link-edge-targets
    for match in _LINK_RE.finditer(content):
        target = match.group("target").strip()
        yield match, _resolve(src.rel_path, _expand_vars(target, template_vars), known)
    for match in _VAR_PATH_RE.finditer(content):
        expanded = _expand_vars(match.group(0), template_vars)
        yield match, _resolve(src.rel_path, "/" + expanded.lstrip("/"), known)
    # @cpt-end:cpt-studio-algo-map-file-links:p1:inst-link-edge-targets


# pylint: disable-next=too-many-locals
def extract_file_links(nodes: Sequence[Node],
                       project_root: Optional[Union[Path, str]] = None,
                       project_root_by_source: Optional[Dict[str, Union[Path, str]]] = None,
                       template_vars: Optional[Dict[str, str]] = None) -> List[Edge]:
    """Return markdown→markdown file-link edges. Source nodes are ignored.

    Args:
        nodes: Sequence of Node objects from scan_repo.
        project_root: Project root path. If not provided, returns empty list.
        project_root_by_source: Optional per-source project roots. When set, markdown
            content is loaded from the node source's own root and same-source link
            resolution is preferred before falling back to a unique cross-source match.
        template_vars: Optional map of template variable names to project-root-relative
            paths (e.g. {"cf-path": ".bootstrap/config",
            "adr_template": ".bootstrap/config/config/kits/sdlc/artifacts/ADR/template.md"}).
            When set, `{var}` references in link targets AND in prose path patterns
            are expanded before resolution.
    """
    if project_root is None:
        return []

    project_root = Path(project_root)
    source_roots = {
        source: Path(root)
        for source, root in (project_root_by_source or {}).items()
    }
    template_vars = template_vars or {}
    md_nodes = [n for n in nodes if n.kind == "markdown"]
    by_source_rel: Dict[Tuple[Optional[str], str], Node] = {}
    by_rel: Dict[str, List[Node]] = {}
    for node in md_nodes:
        if not node.rel_path:
            continue
        by_source_rel[(node.source, node.rel_path)] = node
        by_rel.setdefault(node.rel_path, []).append(node)
    known = set(by_rel.keys())

    # @cpt-begin:cpt-studio-algo-map-file-links:p1:inst-extract-file-links
    edges: List[Edge] = []
    edge_id = 0
    for src in md_nodes:
        if not src.rel_path:
            continue

        content_root = source_roots.get(src.source or "", project_root)
        content = _load_markdown_content(content_root, src.rel_path)
        if not content:
            continue

        targets_seen: set[str] = set()

        for match, resolved in _link_edge_targets(content, src, known, template_vars):
            edge_id = _append_file_link_edge(
                edges,
                edge_id,
                by_source_rel,
                by_rel,
                src,
                resolved,
                targets_seen,
                content,
                match.start(),
            )

    return edges
    # @cpt-end:cpt-studio-algo-map-file-links:p1:inst-extract-file-links


# pylint: disable-next=too-many-arguments
def _append_file_link_edge(
    edges: List[Edge],
    edge_id: int,
    by_source_rel: Dict[Tuple[Optional[str], str], Node],
    by_rel: Dict[str, List[Node]],
    src: Node,
    resolved: Optional[str],
    targets_seen: set[str],
    content: str,
    match_start: int,
) -> int:
    """Append one resolved file-link edge and return the next edge id."""
    # @cpt-begin:cpt-studio-algo-map-file-links:p1:inst-append-file-link-edge
    if resolved is None or resolved == src.rel_path or resolved in targets_seen:
        return edge_id
    tgt = by_source_rel.get((src.source, resolved))
    if tgt is None:
        candidates = by_rel.get(resolved, [])
        tgt = candidates[0] if len(candidates) == 1 else None
    if tgt is None:
        return edge_id
    targets_seen.add(resolved)
    line_no = content[:match_start].count("\n") + 1
    snippet = _line_at(content, match_start)
    edges.append(Edge(
        id=f"fl-{edge_id}",
        from_id=src.id,
        to_id=tgt.id,
        type="file-link",
        refs=[Ref(cpt_id=None, line=line_no, snippet=snippet,
                  def_line=None, def_snippet=None)],
        cross_repo=(src.source != tgt.source),
        dangling=False,
    ))
    return edge_id + 1
    # @cpt-end:cpt-studio-algo-map-file-links:p1:inst-append-file-link-edge


def _expand_vars(target: str, template_vars: Dict[str, str]) -> str:
    """Substitute every `{var}` occurrence in ``target`` with its mapped value.

    Variables that are not in ``template_vars`` are left alone (so `_resolve`
    can later decide they don't match any known node).
    """
    # @cpt-begin:cpt-studio-algo-map-file-links:p1:inst-expand-vars
    if "{" not in target or not template_vars:
        return target

    def repl(m):
        key = m.group(1)
        return template_vars.get(key, m.group(0))

    return re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_.\-]*)\}", repl, target)
    # @cpt-end:cpt-studio-algo-map-file-links:p1:inst-expand-vars


def _load_markdown_content(project_root: Path, rel_path: str) -> Optional[str]:
    """Load markdown content from disk."""
    # @cpt-begin:cpt-studio-algo-map-file-links:p1:inst-load-markdown-content
    from studio.utils.document import read_text_safe

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
    # @cpt-end:cpt-studio-algo-map-file-links:p1:inst-load-markdown-content


def _resolve(source_rel: str, target: str, known: set[str]) -> Optional[str]:
    """Resolve a markdown link target to a known rel_path. Returns None if not found."""
    # @cpt-begin:cpt-studio-algo-map-file-links:p1:inst-resolve
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
    # @cpt-end:cpt-studio-algo-map-file-links:p1:inst-resolve


def _slug_candidates(source_rel: str, target: str) -> List[str]:
    # @cpt-begin:cpt-studio-algo-map-file-links:p1:inst-slug-candidates
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
    # @cpt-end:cpt-studio-algo-map-file-links:p1:inst-slug-candidates


def _posix_normpath(path: str) -> str:
    # @cpt-begin:cpt-studio-algo-map-file-links:p1:inst-posix-normpath
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
    # @cpt-end:cpt-studio-algo-map-file-links:p1:inst-posix-normpath


def _line_at(content: str, offset: int) -> str:
    # @cpt-begin:cpt-studio-algo-map-file-links:p1:inst-line-at
    line_start = content.rfind("\n", 0, offset) + 1
    line_end = content.find("\n", offset)
    if line_end == -1:
        line_end = len(content)
    return content[line_start:line_end]
    # @cpt-end:cpt-studio-algo-map-file-links:p1:inst-line-at
