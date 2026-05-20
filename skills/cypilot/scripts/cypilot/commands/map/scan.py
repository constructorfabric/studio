"""Scan layer for cfc map: walks the project root and produces a flat list of Node objects.

@cpt-flow:cpt-cypilot-flow-map-scan:p1
@cpt-algo:cpt-cypilot-algo-map-scan-walker:p1
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

from .model import CptUse, Node, node_id

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SKIP_DIRS: Tuple[str, ...] = (
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "target",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".bootstrap",
    ".idea",
    ".vscode",
    ".ruff_cache",
)

# Snippet caps. The viewer shows the first ~4 lines by default and lets the
# user expand to the full snippet, so the backend can afford to bake a
# generous slice of context for each cpt-use site.
_MAX_SNIPPET_LINES = 80
_MAX_SNIPPET_CHARS = 6000


def _section_around(lines_raw, line_no: int) -> str:
    """Return the markdown section containing ``line_no``.

    Walks back to the nearest line that starts with ``#`` and forward to the
    line before the next ``#``. Used for cpt definitions, where the surrounding
    section gives meaningful context (the bare definition line alone is just
    a checkbox bullet without prose).
    """
    n = len(lines_raw)
    if not (1 <= line_no <= n):
        return ""
    target_idx = line_no - 1

    heading_idx = 0
    for i in range(target_idx, -1, -1):
        if lines_raw[i].lstrip().startswith("#"):
            heading_idx = i
            break

    section_end = n - 1
    for i in range(target_idx + 1, n):
        if lines_raw[i].lstrip().startswith("#"):
            section_end = i - 1
            break

    # Cap at _MAX_SNIPPET_LINES from the heading to avoid huge sections.
    section_end = min(section_end, heading_idx + _MAX_SNIPPET_LINES - 1)

    # Trim trailing blank lines.
    while section_end > heading_idx and not lines_raw[section_end].strip():
        section_end -= 1

    text = "\n".join(line.rstrip() for line in lines_raw[heading_idx:section_end + 1])
    if len(text) > _MAX_SNIPPET_CHARS:
        text = text[:_MAX_SNIPPET_CHARS].rstrip() + "\n…"
    return text




_EXT_TO_LANG = {
    ".py": "python",
    ".rs": "rust",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".sh": "bash",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
}


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------

@dataclass
class ScanOptions:
    project_root: Path
    source_name: str
    no_source: bool = False
    extra_skip_dirs: Sequence[str] = field(default_factory=list)
    # When True, walk into dot-prefixed directories (.github, .windsurf, etc).
    # DEFAULT_SKIP_DIRS still wins — entries listed there are skipped regardless.
    include_hidden: bool = False


# ---------------------------------------------------------------------------
# File walker
# ---------------------------------------------------------------------------

def _walk_files(root: Path, extensions: Sequence[str], skip_dirs: Set[str],
                include_hidden: bool, max_bytes: int = 1_000_000) -> List[Path]:
    """Iterate text files under ``root`` matching ``extensions``.

    Walker logic:
      * Directories whose basename matches ``skip_dirs`` are never traversed.
      * Directories whose basename starts with ``.`` are skipped unless
        ``include_hidden=True``.
      * Files larger than ``max_bytes`` are skipped (safety against binaries).

    Returns a sorted, deduplicated list of absolute paths.
    """
    import os

    ext_set = {e.lower() for e in extensions}
    out: List[Path] = []
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in skip_dirs and (include_hidden or not d.startswith("."))
        )
        for fn in sorted(filenames):
            suffix = os.path.splitext(fn)[1].lower()
            if suffix not in ext_set:
                continue
            fp = Path(dirpath) / fn
            try:
                if fp.stat().st_size > max_bytes:
                    continue
            except OSError:
                continue
            out.append(fp)
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scan_repo(opts: ScanOptions) -> List[Node]:
    """Walk the project root and return a flat list of Node objects.

    @cpt-flow:cpt-cypilot-flow-map-scan:p1
    """
    root = opts.project_root.resolve()
    skip_dirs: Set[str] = set(DEFAULT_SKIP_DIRS) | set(opts.extra_skip_dirs)

    nodes: List[Node] = []
    nodes.extend(_scan_markdown(root, opts.source_name, skip_dirs, opts.include_hidden))

    if not opts.no_source:
        nodes.extend(_scan_sources(root, opts.source_name, skip_dirs, opts.include_hidden))

    return nodes


# ---------------------------------------------------------------------------
# Markdown scanning
# ---------------------------------------------------------------------------

def _scan_markdown(root: Path, source_name: str, skip_dirs: Set[str],
                   include_hidden: bool) -> List[Node]:
    """Walk .md files under root and return markdown Nodes.

    @cpt-algo:cpt-cypilot-algo-map-scan-walker:p1
    """
    from cypilot.utils.document import to_relative_posix

    nodes: List[Node] = []
    md_files = _walk_files(root, [".md"], skip_dirs, include_hidden)

    for path in md_files:
        # Skip dirs — iter_text_files already filters most; add our extras.
        rel = to_relative_posix(path, root)
        parts = rel.split("/")
        if any(p in skip_dirs for p in parts[:-1]):
            continue

        cpt_defs, cpt_uses = _split_md_cpt(path)
        lines = _count_lines(path)

        n = Node(
            id=node_id(source_name, rel),
            rel_path=rel,
            source=source_name,
            kind="markdown",
            language=None,
            category="",
            category_origin="parent-dir",
            content=None,
            loc=lines,
            cpt_defs=cpt_defs,
            cpt_uses=cpt_uses,
        )
        nodes.append(n)

    return nodes


def _split_md_cpt(path: Path) -> Tuple[List[str], List[CptUse]]:
    """Use scan_cpt_ids to split into cpt_defs and cpt_uses for a markdown file.

    When a definition hit carries a ``priority`` (e.g. ``p1``), the canonical
    cpt_id is formed as ``{id}:{priority}`` so it matches the phase-qualified
    IDs used in source markers (``@cpt-flow:cpt-...:p1``).
    """
    from cypilot.utils.document import read_text_safe, scan_cpt_ids

    hits = scan_cpt_ids(path)
    lines_raw = read_text_safe(path) or []

    cpt_defs: List[str] = []
    cpt_uses: List[CptUse] = []

    seen_defs: Set[str] = set()

    for h in hits:
        base_id = str(h.get("id", ""))
        if not base_id:
            continue
        priority = h.get("priority")
        # Build phase-qualified id when a priority tag is present.
        cpt_id = f"{base_id}:{priority}" if priority else base_id

        line_no = int(h.get("line", 0))
        hit_type = h.get("type", "reference")
        # Both definitions and references use the whole containing section
        # (nearest heading → next heading). For lone reference bullets between
        # blank lines, this is the only way to surface useful context — the
        # paragraph-only algorithm collapses to a single bullet line.
        snippet = _section_around(lines_raw, line_no) if line_no > 0 else ""

        if hit_type == "definition":
            if cpt_id not in seen_defs:
                cpt_defs.append(cpt_id)
                seen_defs.add(cpt_id)
            # Definitions are also surfaced as CptUse with marker_kind="md-def"
            cpt_uses.append(CptUse(
                cpt_id=cpt_id,
                line=line_no,
                snippet=snippet,
                marker_kind="md-def",
            ))
        else:
            cpt_uses.append(CptUse(
                cpt_id=cpt_id,
                line=line_no,
                snippet=snippet,
                marker_kind="md-ref",
            ))

    return cpt_defs, cpt_uses


# ---------------------------------------------------------------------------
# Source scanning
# ---------------------------------------------------------------------------

def _scan_sources(root: Path, source_name: str, skip_dirs: Set[str],
                  include_hidden: bool) -> List[Node]:
    """Scan source files driven by [[systems.codebase]] entries in artifacts.toml.

    @cpt-algo:cpt-cypilot-algo-map-scan-walker:p1

    Returns empty list if artifacts.toml is absent or broken (defensive).
    DOCS-ONLY systems contribute no source nodes.
    """
    registry_path = root / "artifacts.toml"
    if not registry_path.is_file():
        return []

    try:
        meta = _load_registry(registry_path)
    except Exception:  # pylint: disable=broad-exception-caught  # registry is best-effort; never fail scan
        return []

    if meta is None:
        return []

    nodes: List[Node] = []
    seen: Set[Path] = set()

    for cb, _system in meta.iter_all_codebase():
        # Check traceability_mode on the raw system node
        cb_path = cb.path.lstrip("./")
        cb_dir = root / cb_path
        if not cb_dir.is_dir():
            continue

        ext_set: Set[str] = set(cb.extensions)
        if not ext_set:
            continue

        for path in _walk_source_dir(cb_dir, ext_set, skip_dirs, include_hidden):
            if path in seen:
                continue
            seen.add(path)
            node = _make_source_node(path, root, source_name)
            if node is not None:
                nodes.append(node)

    return nodes


def _load_registry(registry_path: Path):
    """Load ArtifactsMeta directly from an artifacts.toml at the given path."""
    from cypilot.utils._tomllib_compat import tomllib
    from cypilot.utils.artifacts_meta import ArtifactsMeta

    with open(registry_path, "rb") as f:
        data = tomllib.load(f)
    if not isinstance(data, dict):
        return None
    return ArtifactsMeta.from_dict(data)


def _walk_source_dir(cb_dir: Path, ext_set: Set[str], skip_dirs: Set[str],
                     include_hidden: bool) -> List[Path]:
    """Walk a codebase directory, yielding files matching the given extensions."""
    result: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(cb_dir):
        dirnames[:] = [
            d for d in dirnames
            if d not in skip_dirs and (include_hidden or not d.startswith("."))
        ]
        for fn in filenames:
            suffix = Path(fn).suffix
            if suffix in ext_set:
                result.append(Path(dirpath) / fn)
    return result


def _make_source_node(path: Path, root: Path, source_name: str) -> Optional[Node]:
    """Parse a source file with CodeFile.from_path and build a Node."""
    from cypilot.utils.codebase import CodeFile
    from cypilot.utils.document import to_relative_posix

    rel = to_relative_posix(path, root)
    lang = _language_from_ext(path.suffix)
    lines = _count_lines(path)

    cf, _errors = CodeFile.from_path(path)

    cpt_uses: List[CptUse] = []
    # Read raw lines once for snippet extraction.
    try:
        src_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        src_lines = []

    def _code_snippet(lo: int, hi: int) -> str:
        if not src_lines:
            return ""
        lo = max(1, lo)
        hi = min(len(src_lines), hi)
        if lo > hi:
            return ""
        return "\n".join(src_lines[lo - 1:hi])

    if cf is not None:
        # Scope markers → marker_kind="scope"; embed 3 lines after the marker
        # so the surrounding code is visible.
        for sm in cf.scope_markers:
            cpt_id = f"{sm.id}:p{sm.phase}"
            cpt_uses.append(CptUse(
                cpt_id=cpt_id,
                line=sm.line,
                snippet=_code_snippet(sm.line, sm.line + 4) or sm.raw.rstrip(),
                marker_kind="scope",
            ))
        # Block markers → begin + end with the inner body included for begin.
        for bm in cf.block_markers:
            cpt_id = f"{bm.id}:p{bm.phase}"
            inner_hi = min(bm.start_line + _MAX_SNIPPET_LINES, bm.end_line)
            cpt_uses.append(CptUse(
                cpt_id=cpt_id,
                line=bm.start_line,
                snippet=_code_snippet(bm.start_line, inner_hi)
                        or f"@cpt-begin:{bm.id}:p{bm.phase}:inst-{bm.inst}",
                marker_kind="block-begin",
            ))
            # end entry — show last few lines of the block leading up to the @cpt-end
            cpt_uses.append(CptUse(
                cpt_id=cpt_id,
                line=bm.end_line,
                snippet=_code_snippet(max(bm.start_line, bm.end_line - 4), bm.end_line)
                        or f"@cpt-end:{bm.id}:p{bm.phase}:inst-{bm.inst}",
                marker_kind="block-end",
            ))

    return Node(
        id=node_id(source_name, rel),
        rel_path=rel,
        source=source_name,
        kind="source",
        language=lang,
        category="",
        category_origin="parent-dir",
        content=None,
        loc=lines,
        cpt_defs=[],
        cpt_uses=cpt_uses,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _language_from_ext(suffix: str) -> Optional[str]:
    return _EXT_TO_LANG.get(suffix.lower())


def _count_lines(path: Path) -> int:
    try:
        return sum(1 for _ in path.open("rb"))
    except OSError:
        return 0
