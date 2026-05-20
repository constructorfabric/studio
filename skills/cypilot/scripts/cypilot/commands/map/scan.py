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
    nodes.extend(_scan_markdown(root, opts.source_name, skip_dirs))

    if not opts.no_source:
        nodes.extend(_scan_sources(root, opts.source_name, skip_dirs))

    return nodes


# ---------------------------------------------------------------------------
# Markdown scanning
# ---------------------------------------------------------------------------

def _scan_markdown(root: Path, source_name: str, skip_dirs: Set[str]) -> List[Node]:
    """Walk .md files under root and return markdown Nodes.

    @cpt-algo:cpt-cypilot-algo-map-scan-walker:p1
    """
    from cypilot.utils.document import iter_text_files, to_relative_posix

    nodes: List[Node] = []
    # Use both patterns: "*.md" for root-level files and "**/*.md" for subdirs.
    # fnmatch "**/*.md" does not match files at the root level (no directory separator).
    md_files_set: Set[Path] = set()
    md_files_set.update(iter_text_files(root, includes=["*.md"]))
    md_files_set.update(iter_text_files(root, includes=["**/*.md"]))
    md_files = sorted(md_files_set)

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
        snippet = lines_raw[line_no - 1].rstrip() if (0 < line_no <= len(lines_raw)) else ""
        hit_type = h.get("type", "reference")

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

def _scan_sources(root: Path, source_name: str, skip_dirs: Set[str]) -> List[Node]:
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

        for path in _walk_source_dir(cb_dir, ext_set, skip_dirs):
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


def _walk_source_dir(cb_dir: Path, ext_set: Set[str], skip_dirs: Set[str]) -> List[Path]:
    """Walk a codebase directory, yielding files matching the given extensions."""
    result: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(cb_dir):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
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

    if cf is not None:
        # Scope markers → marker_kind="scope"
        # Build phase-qualified cpt_id: "{id}:p{phase}"
        for sm in cf.scope_markers:
            cpt_id = f"{sm.id}:p{sm.phase}"
            cpt_uses.append(CptUse(
                cpt_id=cpt_id,
                line=sm.line,
                snippet=sm.raw.rstrip(),
                marker_kind="scope",
            ))
        # Block markers → one block-begin + one block-end per pair
        # Build phase-qualified cpt_id: "{id}:p{phase}"
        for bm in cf.block_markers:
            cpt_id = f"{bm.id}:p{bm.phase}"
            # begin entry
            cpt_uses.append(CptUse(
                cpt_id=cpt_id,
                line=bm.start_line,
                snippet=f"@cpt-begin:{bm.id}:p{bm.phase}:inst-{bm.inst}",
                marker_kind="block-begin",
            ))
            # end entry
            cpt_uses.append(CptUse(
                cpt_id=cpt_id,
                line=bm.end_line,
                snippet=f"@cpt-end:{bm.id}:p{bm.phase}:inst-{bm.inst}",
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
