"""Scan layer for cfs map: walks the project root and produces a flat list of Node objects.

@cpt-algo:cpt-studio-algo-map-scan:p1
@cpt-algo:cpt-studio-algo-map-scan-walker:p1
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

# Minimal default skip-list: only the VCS metadata. The adapter directory
# (resolved from CLAUDE.md / AGENTS.md → cf-path / studio_path)
# is added per-project at scan time. Everything else — including dot-prefixed
# tooling dirs like .claude, .agents, .codex, .windsurf, etc — is walked.
DEFAULT_SKIP_DIRS: Tuple[str, ...] = (".git",)


def _detect_adapter_dir(project_root: Path) -> Optional[str]:
    """Read CLAUDE.md (or AGENTS.md) at the project root and extract the
    adapter directory name from a `cf-path` or `studio_path`
    assignment. Returns the basename (e.g. ".bootstrap" or ".cf")
    or None when not found.
    """
    # @cpt-begin:cpt-studio-algo-map-scan:p1:inst-detect-adapter-dir
    import re
    for name in ("CLAUDE.md", "AGENTS.md"):
        path = project_root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:  # pragma: no cover
            continue
        m = re.search(
            r'^\s*(?:cf-path|studio_path)\s*=\s*"([^"]+)"',
            text,
            re.MULTILINE,
        )
        if m:
            value = m.group(1).strip().rstrip("/")
            # Take just the basename — adapter is a single dir at project root.
            return Path(value).name or None
    return None
    # @cpt-end:cpt-studio-algo-map-scan:p1:inst-detect-adapter-dir

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
    # @cpt-begin:cpt-studio-algo-map-scan:p1:inst-section-around
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
    # @cpt-end:cpt-studio-algo-map-scan:p1:inst-section-around




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
    # When True, the adapter directory (.bootstrap / .cf) is
    # walked too. Default skip is still `.git` plus any extras.
    include_adapter: bool = False


# ---------------------------------------------------------------------------
# File walker
# ---------------------------------------------------------------------------

def _walk_files(root: Path, extensions: Sequence[str], skip_dirs: Set[str],
                max_bytes: int = 1_000_000) -> List[Path]:
    """Iterate text files under ``root`` matching ``extensions``.

    Skip rule: only directories whose basename matches ``skip_dirs`` are pruned.
    Dot-prefixed directories are NOT filtered automatically — the caller must
    add them to ``skip_dirs`` explicitly. This lets ``.claude``, ``.windsurf``,
    ``.codex`` etc. show up in the map by default.
    """
    # @cpt-begin:cpt-studio-algo-map-scan:p1:inst-walk-files
    ext_set = {e.lower() for e in extensions}
    out: List[Path] = []
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs)
        for fn in sorted(filenames):
            suffix = os.path.splitext(fn)[1].lower()
            if suffix not in ext_set:
                continue
            fp = Path(dirpath) / fn
            try:
                if fp.stat().st_size > max_bytes:
                    continue
            except OSError:  # pragma: no cover
                continue
            out.append(fp)
    return out
    # @cpt-end:cpt-studio-algo-map-scan:p1:inst-walk-files


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scan_repo(opts: ScanOptions) -> List[Node]:
    """Walk the project root and return a flat list of Node objects."""
    # @cpt-begin:cpt-studio-algo-map-scan:p1:inst-scan-repo
    root = opts.project_root.resolve()
    skip_dirs: Set[str] = set(DEFAULT_SKIP_DIRS) | set(opts.extra_skip_dirs)
    if not opts.include_adapter:
        adapter = _detect_adapter_dir(root)
        if adapter:
            skip_dirs.add(adapter)

    nodes: List[Node] = []
    nodes.extend(_scan_markdown(root, opts.source_name, skip_dirs))

    if not opts.no_source:
        nodes.extend(_scan_sources(root, opts.source_name, skip_dirs))

    return nodes
    # @cpt-end:cpt-studio-algo-map-scan:p1:inst-scan-repo


# ---------------------------------------------------------------------------
# Markdown scanning
# ---------------------------------------------------------------------------

def _scan_markdown(root: Path, source_name: str, skip_dirs: Set[str]) -> List[Node]:
    """Walk .md files under root and return markdown Nodes."""
    # @cpt-begin:cpt-studio-algo-map-scan:p1:inst-scan-markdown
    from studio.utils.document import to_relative_posix

    nodes: List[Node] = []
    md_files = _walk_files(root, [".md"], skip_dirs)

    # @cpt-begin:cpt-studio-algo-map-scan:p1:inst-build-md-nodes
    for path in md_files:
        # Skip dirs — iter_text_files already filters most; add our extras.
        rel = to_relative_posix(path, root)
        parts = rel.split("/")
        if any(p in skip_dirs for p in parts[:-1]):  # pragma: no cover
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
    # @cpt-end:cpt-studio-algo-map-scan:p1:inst-build-md-nodes

    return nodes
    # @cpt-end:cpt-studio-algo-map-scan:p1:inst-scan-markdown


def _split_md_cpt(path: Path) -> Tuple[List[str], List[CptUse]]:
    """Use scan_cpt_ids to split into cpt_defs and cpt_uses for a markdown file.

    When a definition hit carries a ``priority`` (e.g. ``p1``), the canonical
    cpt_id is formed as ``{id}:{priority}`` so it matches the phase-qualified
    IDs used in source markers (``@cpt-flow:cpt-...:p1``).
    """
    # @cpt-begin:cpt-studio-algo-map-scan:p1:inst-split-md-cpt
    from studio.utils.document import read_text_safe, scan_cpt_ids

    hits = scan_cpt_ids(path)
    lines_raw = read_text_safe(path) or []

    cpt_defs: List[str] = []
    cpt_uses: List[CptUse] = []

    seen_defs: Set[str] = set()

    for h in hits:
        base_id = str(h.get("id", ""))
        if not base_id:  # pragma: no cover
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
    # @cpt-end:cpt-studio-algo-map-scan:p1:inst-split-md-cpt


# ---------------------------------------------------------------------------
# Source scanning
# ---------------------------------------------------------------------------

def _resolve_registry_path_for_root(root: Path) -> Optional[Path]:
    """Resolve the artifacts registry path via the canonical adapter_dir helper.

    Uses find_studio_directory / load_artifacts_registry so that the registry
    at <adapter_dir>/config/artifacts.toml is found even when it is not at the
    project root.  Only applies adapter resolution when ``root`` is the actual
    project root (i.e. find_project_root returns the same path); otherwise falls
    back to the flat ``root / artifacts.toml`` layout.  This prevents test
    fixtures nested inside a larger repo from picking up the repo-level adapter.
    Returns None when no registry file can be located.
    """
    try:
        from studio.utils.files import find_studio_directory, find_project_root, load_artifacts_registry
        project_root = find_project_root(root)
        if project_root is not None and project_root.resolve() == root.resolve():  # pragma: no cover
            # root IS the project root — use full adapter resolution.
            adapter_dir = find_studio_directory(root) or root
            cfg, _err = load_artifacts_registry(adapter_dir)
            if cfg is None:
                return None
            # Mirror the fallback chain from load_artifacts_registry to get the path.
            for candidate in (
                adapter_dir / "artifacts.toml",
                adapter_dir / "config" / "artifacts.toml",
                adapter_dir / "artifacts.json",
            ):
                if candidate.is_file():
                    return candidate
            return None
        # root is a sub-directory — use flat layout only.
        flat = root / "artifacts.toml"
        return flat if flat.is_file() else None
    except Exception:  # pylint: disable=broad-exception-caught  # pragma: no cover
        pass
    # Final fallback: flat layout at root.
    flat = root / "artifacts.toml"
    return flat if flat.is_file() else None  # pragma: no cover


def _scan_sources(root: Path, source_name: str, skip_dirs: Set[str]) -> List[Node]:
    """Scan source files driven by [[systems.codebase]] entries in artifacts.toml.

    Returns empty list if artifacts.toml is absent or broken (defensive).
    DOCS-ONLY systems contribute no source nodes.
    """
    # @cpt-begin:cpt-studio-algo-map-scan:p1:inst-scan-sources
    registry_path = _resolve_registry_path_for_root(root)
    if registry_path is None:
        return []

    try:
        meta = _load_registry(registry_path)
    except Exception:  # pylint: disable=broad-exception-caught  # pragma: no cover
        return []

    if meta is None:  # pragma: no cover
        return []

    # Expand autodetect rules so that [[systems.autodetect.codebase]] entries
    # are promoted into SystemNode.codebase before iter_all_codebase() is called.
    # adapter_dir is the studio directory that owns the registry; project_root is
    # the scan root (i.e. the git repo root passed as ``root``).
    # Guard: only use adapter resolution when root == project_root to avoid
    # picking up the parent project's adapter when scanning a fixture sub-dir.
    try:
        from studio.utils.files import find_studio_directory, find_project_root
        detected_root = find_project_root(root)
        if detected_root is not None and detected_root.resolve() == root.resolve():  # pragma: no cover
            adapter_dir = find_studio_directory(root) or root
        else:
            adapter_dir = root
        meta.expand_autodetect(adapter_dir=adapter_dir, project_root=root)
    except Exception:  # pylint: disable=broad-exception-caught  # pragma: no cover
        pass

    nodes: List[Node] = []
    seen: Set[Path] = set()

    for cb, _system in meta.iter_all_codebase():
        # cb.path is project_root-relative after expand_autodetect resolves it.
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
    # @cpt-end:cpt-studio-algo-map-scan:p1:inst-scan-sources


def _load_registry(registry_path: Path):
    """Load ArtifactsMeta directly from an artifacts.toml at the given path."""
    # @cpt-begin:cpt-studio-algo-map-scan:p1:inst-load-registry
    from studio.utils._tomllib_compat import tomllib
    from studio.utils.artifacts_meta import ArtifactsMeta

    with open(registry_path, "rb") as f:
        data = tomllib.load(f)
    if not isinstance(data, dict):  # pragma: no cover
        return None
    return ArtifactsMeta.from_dict(data)
    # @cpt-end:cpt-studio-algo-map-scan:p1:inst-load-registry


def _walk_source_dir(cb_dir: Path, ext_set: Set[str], skip_dirs: Set[str]) -> List[Path]:
    """Walk a codebase directory, yielding files matching the given extensions."""
    # @cpt-begin:cpt-studio-algo-map-scan:p1:inst-walk-source-dir
    result: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(cb_dir):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fn in filenames:
            suffix = Path(fn).suffix
            if suffix in ext_set:
                result.append(Path(dirpath) / fn)
    return result
    # @cpt-end:cpt-studio-algo-map-scan:p1:inst-walk-source-dir


def _make_source_node(path: Path, root: Path, source_name: str) -> Optional[Node]:
    """Parse a source file with CodeFile.from_path and build a Node."""
    # @cpt-begin:cpt-studio-algo-map-scan:p1:inst-make-source-node
    from studio.utils.codebase import CodeFile
    from studio.utils.document import to_relative_posix

    rel = to_relative_posix(path, root)
    lang = _language_from_ext(path.suffix)
    lines = _count_lines(path)

    cf, _errors = CodeFile.from_path(path)

    cpt_uses: List[CptUse] = []
    # Read raw lines once for snippet extraction.
    try:
        src_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:  # pragma: no cover
        src_lines = []

    def _code_snippet(lo: int, hi: int) -> str:
        if not src_lines:  # pragma: no cover
            return ""
        lo = max(1, lo)
        hi = min(len(src_lines), hi)
        if lo > hi:
            return ""
        return "\n".join(src_lines[lo - 1:hi])

    if cf is not None:
        # Scope markers → marker_kind="scope"; embed 3 lines after the marker
        # so the surrounding code is visible.
        # @cpt-begin:cpt-studio-algo-map-scan:p1:inst-extract-scope-markers
        for sm in cf.scope_markers:
            cpt_id = f"{sm.id}:p{sm.phase}"
            cpt_uses.append(CptUse(
                cpt_id=cpt_id,
                line=sm.line,
                snippet=_code_snippet(sm.line, sm.line + 4) or sm.raw.rstrip(),
                marker_kind="scope",
            ))
        # @cpt-end:cpt-studio-algo-map-scan:p1:inst-extract-scope-markers
        # Block markers → begin + end with the inner body included for begin.
        # @cpt-begin:cpt-studio-algo-map-scan:p1:inst-extract-block-markers
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
        # @cpt-end:cpt-studio-algo-map-scan:p1:inst-extract-block-markers

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
    # @cpt-end:cpt-studio-algo-map-scan:p1:inst-make-source-node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _language_from_ext(suffix: str) -> Optional[str]:
    return _EXT_TO_LANG.get(suffix.lower())


def _count_lines(path: Path) -> int:
    try:
        return sum(1 for _ in path.open("rb"))
    except OSError:  # pragma: no cover
        return 0
