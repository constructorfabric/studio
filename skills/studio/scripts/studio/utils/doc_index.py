"""Cached, read-once-per-file document index for Markdown JIT retrieval.

Builds a structural index (headings + section line ranges) for a Markdown
file exactly once, persists it keyed by an etag of the file's own state, and
reuses that cached index on every subsequent call against the same file --
until the file actually changes. This is the "read once per file, not once
per query" mechanism: parsing/etag work never repeats across queries, and
optional per-section summaries (written by an LLM caller, not by this
module) accumulate in the same cached artifact instead of being
re-derived each time.

Scope: Markdown only. PDF/DOCX conversion is a separate concern (Layer 1);
this module operates purely on already-plain-text content (Layer 2).

See constructorfabric/studio#104.

@cpt-algo:cpt-studio-algo-traceability-validation-doc-index:p1
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .toc import parse_headings_with_lines

logger = logging.getLogger(__name__)

_CACHE_SUBDIR = ".cache"
_INDEX_CACHE_DIR = "doc-index"

#: Bumped whenever the index's own shape changes incompatibly. Checked
#: alongside the etag so a future schema change invalidates an
#: old-format cache instead of silently returning old-shape data past a
#: matching etag.
_SCHEMA_VERSION = 1


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-etag
def _compute_etag(path: Path) -> str:
    """Compute a cheap cache-validity fingerprint from filesystem metadata.

    Deliberately *not* a content hash: ``Path.stat()`` is metadata-only (no
    file read), which is what lets a cache *hit* stay free of a full read --
    the whole point of a read-once-per-file index. mtime + size changes on
    a same-size, same-line-count text swap too, since a write ordinarily
    advances mtime -- a byte-count/line-count-only fingerprint would miss
    that edit outright, and computing either requires reading the entire
    file this check exists to avoid reading.

    Known, accepted limitation: on a filesystem with coarse mtime
    resolution (e.g. some FAT32/older-HFS+/NFS configurations), two
    same-size edits landing within one mtime tick can share an identical
    etag, and a cache hit would then return the first edit's stale data.
    Trading that narrow, filesystem-dependent risk for never reading the
    file on a cache hit is this module's whole reason to exist; closing it
    fully would mean a content hash, which defeats the point.
    """
    st = path.stat()
    return f"{st.st_mtime_ns}:{st.st_size}"
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-etag


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-cache-path
def _index_cache_path(path: Path) -> Optional[Path]:
    """Resolve ``<studio-dir>/.cache/doc-index/<slug>.json`` for a file.

    Resolved from ``path`` itself (not the process's current working
    directory), so indexing a file outside the caller's cwd still resolves
    -- and always resolves -- the Studio directory that actually owns it.

    Returns ``None`` when no Studio directory can be found (e.g. outside a
    Studio-adapted project) -- callers should fall back to an uncached build.
    """
    from .files import find_studio_directory

    try:
        studio_dir = find_studio_directory(path.resolve().parent)
    except OSError as exc:
        # A file whose parent can't be stat'd (permissions, a race) is not a
        # reason to fail the caller -- just an uncached build, like "no
        # Studio directory found".
        logger.debug("doc-index cache path lookup skipped for %s: %s", path, exc)
        studio_dir = None
    if studio_dir is None:
        return None

    slug = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
    return studio_dir / _CACHE_SUBDIR / _INDEX_CACHE_DIR / f"{slug}.json"
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-cache-path


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-build
def build_doc_index(path: Path) -> Dict[str, Any]:
    """Build a fresh structural index for a Markdown file.

    Purely deterministic -- headings, section line ranges, and an etag.
    Contains no LLM-generated content; per-section ``summary`` fields start
    as ``None`` and are filled in later via :func:`annotate_section_summary`.
    """
    canonical_path = path.resolve()
    # Fingerprint before read: if a write lands between the two, the stored
    # etag describes content older than (never newer than) what got parsed,
    # so a mismatch is always detected on the next load -- computing it
    # after the read could instead capture a fingerprint newer than the
    # content actually parsed, which a later stat comparison can't catch.
    etag = _compute_etag(canonical_path)
    content = canonical_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    line_count = len(lines)

    headings = parse_headings_with_lines(lines)
    sections: List[Dict[str, Any]] = []
    for i, (level, text, line_start) in enumerate(headings):
        line_end = headings[i + 1][2] - 1 if i + 1 < len(headings) else line_count
        sections.append({
            "level": level,
            "heading": text,
            "line_start": line_start,
            "line_end": line_end,
            "summary": None,
        })

    return {
        "schema_version": _SCHEMA_VERSION,
        "path": str(canonical_path),
        "etag": etag,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_lines": line_count,
        "sections": sections,
    }
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-build


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-load
_REQUIRED_INDEX_FIELDS = ("total_lines", "sections")


def _has_schema_current_index(cached: Dict[str, Any]) -> bool:
    """``True`` only if ``cached`` carries every field a consumer
    (``commands/doc_index.py``, :func:`annotate_section_summary`) reads by
    subscript, at the schema version this module currently writes --
    treated the same as a stale/corrupt cache otherwise, so a partially
    written, hand-edited, or pre-schema-bump cache triggers a clean rebuild
    instead of a ``KeyError`` deep in a consumer.
    """
    if cached.get("schema_version") != _SCHEMA_VERSION:
        return False
    return all(field in cached for field in _REQUIRED_INDEX_FIELDS)


def load_doc_index(path: Path) -> Optional[Dict[str, Any]]:
    """Load a cached index for ``path``, or ``None`` if missing/stale/absent.

    Staleness is detected from cheap ``Path.stat()`` metadata alone -- this
    never reads the file's content, so a cache *hit* stays free of a full
    read (the property the whole cache exists to provide). Only a stale or
    absent cache falls through to :func:`build_doc_index`, which does the
    one real read.
    """
    cache_path = _index_cache_path(path)
    if cache_path is None or not cache_path.is_file():
        return None

    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("doc-index cache unreadable for %s: %s", path, exc)
        return None

    canonical_path = path.resolve()
    try:
        current_etag = _compute_etag(canonical_path)
    except OSError as exc:
        logger.debug("doc-index staleness check failed for %s: %s", path, exc)
        return None

    if cached.get("etag") != current_etag:
        return None
    if not _has_schema_current_index(cached):
        logger.debug("doc-index cache for %s is malformed or predates the current schema; rebuilding", path)
        return None
    return cached
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-load


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-save
def save_doc_index(path: Path, index: Dict[str, Any]) -> None:
    """Persist an index to its cache location. No-ops outside a Studio project.

    Written atomically (temp file + ``os.replace``): a reader racing a
    concurrent writer sees either the old complete file or the new complete
    one, never a torn/partial write.
    """
    cache_path = _index_cache_path(path)
    if cache_path is None:
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_name(f"{cache_path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    os.replace(tmp_path, cache_path)
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-save


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-get-or-build
def get_or_build_doc_index(path: Path, *, force_rebuild: bool = False) -> Dict[str, Any]:
    """Return the cached index for ``path``, building and caching it if needed.

    This is the "read once per file" entrypoint: the first call for a given
    file (or the first call after it changes) pays the parse cost and writes
    the cache; every subsequent call against an unchanged file returns the
    cached result directly. ``index["cache_hit"]`` reports which happened,
    for benchmarking.
    """
    if not force_rebuild:
        cached = load_doc_index(path)
        if cached is not None:
            cached["cache_hit"] = True
            return cached

    fresh = build_doc_index(path)
    save_doc_index(path, fresh)
    fresh["cache_hit"] = False
    return fresh
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-get-or-build


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-annotate
def annotate_section_summary(path: Path, line_start: int, summary: str) -> bool:
    """Attach a one-line summary to a cached section, keyed by its line_start.

    Summaries are written by an LLM caller during a one-time enrichment
    pass, never generated inside this module. Returns ``False`` when no
    valid (non-stale) cached index exists or no section matches
    ``line_start`` -- callers should build the index first.
    """
    index = load_doc_index(path)
    if index is None:
        return False

    matched = False
    for section in index["sections"]:
        if section["line_start"] == line_start:
            section["summary"] = summary
            matched = True
            break
    if not matched:
        return False

    save_doc_index(path, index)
    return True
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-annotate
