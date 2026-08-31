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
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-infer-level
def infer_section_level(headings_with_lines: List[Tuple[int, str, int]]) -> Optional[int]:
    """Infer which heading level represents one retrievable section.

    PDF-to-Markdown conversion assigns heading levels by font-size/style
    heuristics, not semantic depth -- a document's real top-level chapters
    can land on any level. A real document converted during this feature's
    own development put all 8 of its actual chapters on H5, while a single
    stray H3 subsection appeared once in the middle; a fixed-level
    assumption (e.g. "H1-H3 is the chapter level") silently turned the back
    half of that real document into one fake 6,601-line "section" bounded
    by that one stray heading (see constructorfabric/studio#104).

    Heuristic: a document's real recurring structure shows up as the
    heading level used *most often* -- real chapters repeat throughout a
    document precisely because they're structure, not noise. A level used
    only once is excluded as a candidate outright: a single occurrence
    can't be "the" recurring section boundary by definition, and treating
    it as one produces exactly the degenerate failure above. Ties (and the
    all-singletons fallback) prefer the shallowest level, on the
    conservative assumption that a coarser grouping beats fragmenting a
    document into many tiny sections.

    Returns ``None`` for a headingless document.
    """
    if not headings_with_lines:
        return None
    counts = Counter(level for level, _text, _line in headings_with_lines)
    recurring = {level: count for level, count in counts.items() if count >= 2}
    if not recurring:
        return min(counts)
    max_count = max(recurring.values())
    return min(level for level, count in recurring.items() if count == max_count)
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-infer-level


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-retrieval-sections
def _build_retrieval_sections(
    headings_with_lines: List[Tuple[int, str, int]],
    lines: List[str],
    section_level: Optional[int],
) -> List[Dict[str, Any]]:
    """Group headings at exactly ``section_level`` into retrieval sections.

    Deliberately an *exact* level match, not "level <= section_level": the
    same unreliable level-assignment this whole mechanism exists to work
    around means a stray heading numerically shallower than the real
    chapter level (like the H3 in the docstring above, sitting inside what
    is structurally an H5 chapter) is not a trustworthy higher-level
    boundary -- it's noise. Content under an off-level heading stays inside
    whichever ``section_level`` section it falls under, rather than
    splitting a real section apart.

    Each section's ``hash`` is a SHA-256 of its own text slice -- the
    per-section granularity :func:`diff_stale_sections` needs to tell "this
    one section changed" from "the whole file changed", which a whole-file
    fingerprint structurally cannot do.
    """
    if section_level is None:
        return []
    line_count = len(lines)
    marks = [(text, line_start) for level, text, line_start in headings_with_lines if level == section_level]
    sections: List[Dict[str, Any]] = []
    for i, (text, line_start) in enumerate(marks):
        line_end = marks[i + 1][1] - 1 if i + 1 < len(marks) else line_count
        section_text = "\n".join(lines[line_start - 1:line_end])
        sections.append({
            "heading": text,
            "line_start": line_start,
            "line_end": line_end,
            "hash": hashlib.sha256(section_text.encode("utf-8")).hexdigest(),
            "summary": None,
        })
    return sections
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-retrieval-sections


_MAX_READ_ATTEMPTS = 3


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-stable-read
def _read_with_stable_etag(path: Path) -> Tuple[str, str]:
    """Read a file's content together with an etag proven to match it.

    A write landing between reading the content and computing the etag
    could otherwise save headings parsed from the *old* content stamped
    with the *new* file's etag -- :func:`load_doc_index` would then treat
    that stale index as valid until a later edit changes the etag again,
    since nothing about the fingerprint itself would look wrong.

    Fixed by bracketing the read with a stat snapshot on each side: if they
    match, the file didn't change during the read, so the etag genuinely
    describes the content just read. If they don't, retry. After
    ``_MAX_READ_ATTEMPTS`` under sustained contention, return the last read
    anyway, stamped with its own trailing etag -- the safe direction to
    fail in, since a file still being rewritten that fast will simply look
    stale again on the very next check, never silently wrong.
    """
    etag_after = _compute_etag(path)
    for _ in range(_MAX_READ_ATTEMPTS):
        etag_before = etag_after
        content = path.read_text(encoding="utf-8")
        etag_after = _compute_etag(path)
        if etag_before == etag_after:
            return content, etag_after
    return content, etag_after
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-stable-read


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-build
def build_doc_index(path: Path) -> Dict[str, Any]:
    """Build a fresh structural index for a Markdown file.

    Purely deterministic -- headings, section line ranges, and an etag.
    Contains no LLM-generated content; per-section ``summary`` fields start
    as ``None`` and are filled in later via :func:`annotate_section_summary`.

    ``sections`` lists *every* heading, any level (unchanged from before --
    still what :func:`annotate_section_summary` matches against by
    ``line_start``). ``retrieval_sections`` is the coarser, inferred
    "one chunk per real chapter" grouping a future TF-IDF/cascade/OKF
    caller should read against instead -- see :func:`infer_section_level`
    for why a fixed heading level can't be assumed.
    """
    canonical_path = path.resolve()
    content, etag = _read_with_stable_etag(canonical_path)
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

    section_level = infer_section_level(headings)

    return {
        "schema_version": _SCHEMA_VERSION,
        "path": str(canonical_path),
        "etag": etag,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_lines": line_count,
        "sections": sections,
        "section_level": section_level,
        "retrieval_sections": _build_retrieval_sections(headings, lines, section_level),
    }
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-build


def _read_cache_file(cache_path: Path) -> Optional[Dict[str, Any]]:
    """Read and parse a cache file, or ``None`` if missing/corrupt.

    No staleness check -- just "can this be read as JSON at all". Shared by
    :func:`load_doc_index` (which layers the etag check on top) and
    :func:`diff_stale_sections` (which deliberately reads a cache the
    whole-file etag already considers stale, to compare it section by
    section instead of discarding it outright).
    """
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("doc-index cache unreadable at %s: %s", cache_path, exc)
        return None


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

    cached = _read_cache_file(cache_path)
    if cached is None:
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


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-diff-stale-helpers
def _compute_fresh_retrieval_sections(path: Path) -> Optional[List[Dict[str, Any]]]:
    """Re-parse a file's current content into retrieval sections, for
    comparison against a cached build. ``None`` on a read failure (e.g. the
    file was deleted after it was cached)."""
    canonical_path = path.resolve()
    try:
        content = canonical_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("doc-index section diff failed for %s: %s", path, exc)
        return None

    lines = content.split("\n")
    headings = parse_headings_with_lines(lines)
    section_level = infer_section_level(headings)
    return _build_retrieval_sections(headings, lines, section_level)


def _position_entry(section: Dict[str, Any]) -> Dict[str, Any]:
    """The (heading, line_start) pair identifying one retrieval section in
    a :func:`diff_stale_sections` result -- ``line_start`` is what actually
    disambiguates two sections sharing a duplicate heading title."""
    return {"heading": section["heading"], "line_start": section["line_start"]}
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-diff-stale-helpers


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-diff-stale
def diff_stale_sections(path: Path) -> Optional[Dict[str, Any]]:
    """Compare the current file against its last cached build at *section*
    granularity, not just "is the whole file's cache stale".

    This is what makes a real partial rebuild possible: :func:`load_doc_index`
    answers "did anything change" (whole-file, via the etag); this answers
    "which retrieval sections actually changed", so a caller doing expensive
    per-section work (e.g. an LLM re-summarizing one section) can skip the
    ones that didn't.

    Returns ``None`` when there's nothing to diff against -- never built, no
    Studio directory, or the cached build predates ``retrieval_sections``
    (an older index format) -- callers should treat that as "everything is
    new" and do a full build instead.

    Otherwise returns ``{"structural_change": bool, "unchanged": [...],
    "changed": [...]}``, where each entry is ``{"heading": str, "line_start":
    int}`` -- the *current* (fresh) position, in document order. Sections
    are matched by *position*, not heading text: duplicate heading titles
    are real (see the ``toc-heading-duplicate`` check), so heading text
    alone can't tell two same-named sections apart -- ``line_start`` is
    what a caller should actually use to address "this specific section"
    afterwards (e.g. to call :func:`annotate_section_summary`), with the
    heading text included only for human-readable logging. When the
    section *count* itself differs, ``structural_change`` is ``True`` and
    ``changed``/``unchanged`` aren't populated -- a position-based diff
    across a changed count can't be safely narrowed to "which ones
    changed" without guessing, so the caller should fall back to a full
    rebuild rather than have this function guess for it.
    """
    cache_path = _index_cache_path(path)
    if cache_path is None or not cache_path.is_file():
        return None

    cached = _read_cache_file(cache_path)
    if cached is None or "retrieval_sections" not in cached:
        return None

    fresh_sections = _compute_fresh_retrieval_sections(path)
    if fresh_sections is None:
        return None

    old_sections = cached["retrieval_sections"]
    if len(old_sections) != len(fresh_sections):
        return {
            "structural_change": True,
            "unchanged": [],
            "changed": [_position_entry(s) for s in fresh_sections],
        }

    unchanged: List[Dict[str, Any]] = []
    changed: List[Dict[str, Any]] = []
    for old, new in zip(old_sections, fresh_sections, strict=True):
        (unchanged if old["hash"] == new["hash"] else changed).append(_position_entry(new))
    return {"structural_change": False, "unchanged": unchanged, "changed": changed}
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-diff-stale


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-annotate
def annotate_section_summary(path: Path, line_start: int, summary: str) -> bool:
    """Attach a one-line summary to a cached section, keyed by its line_start.

    Summaries are written by an LLM caller during a one-time enrichment
    pass, never generated inside this module. Returns ``False`` when no
    valid (non-stale) cached index exists or no section matches
    ``line_start`` -- callers should build the index first.

    Updates the matching entry in both ``sections`` (any heading level) and
    ``retrieval_sections`` (the coarser grouping) when both have a section
    starting at ``line_start`` -- a retriever reading ``retrieval_sections``
    needs the summary to show up there too, not just in the finer-grained
    list. A ``line_start`` that only matches ``sections`` (an off-level
    heading that isn't itself a retrieval section's start) updates only
    that list, which is correct: there is no corresponding retrieval
    section to update.
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

    for retrieval_section in index.get("retrieval_sections", []):
        if retrieval_section["line_start"] == line_start:
            retrieval_section["summary"] = summary
            break

    save_doc_index(path, index)
    return True
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-annotate
