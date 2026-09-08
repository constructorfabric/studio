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

Schema contract: adding a new top-level key to the index dict is always
additive and does not require bumping ``_SCHEMA_VERSION`` -- an older
build of this module simply never wrote that key, which
``_has_schema_current_index``'s required-field check already treats as
"predates the current schema" and rebuilds. ``_SCHEMA_VERSION`` exists for
the other kind of change: an existing key's *meaning* or *shape* changing
incompatibly (e.g. what ``retrieval_sections`` entries contain), which a
field-presence check alone can't detect since the field is still there,
just holding something a new reader would misinterpret. Bump
``_SCHEMA_VERSION`` for that kind of change; a plain new field needs only
listing in ``_REQUIRED_INDEX_FIELDS`` if a consumer reads it unconditionally.

See constructorfabric/studio#104.

@cpt-algo:cpt-studio-algo-traceability-validation-doc-index:p1
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .atomic_io import atomic_write_text, with_file_lock
from .toc import parse_headings_with_lines

logger = logging.getLogger(__name__)

_CACHE_SUBDIR = ".cache"
_INDEX_CACHE_DIR = "doc-index"

#: Bumped whenever the index's own shape changes incompatibly. Checked
#: alongside the etag so a future schema change invalidates an
#: old-format cache instead of silently returning old-shape data past a
#: matching etag.
_SCHEMA_VERSION = 1

#: Schema version for the standalone Tier-2-escalation counter file (see
#: ``_escalation_cache_path``) -- tracked separately from ``_SCHEMA_VERSION``
#: above since the two files are independent artifacts with independent
#: lifecycles (the counter is never rebuilt or reset the way the structural
#: cache is). Bump this if the counter file's shape ever changes
#: incompatibly (e.g. what a key inside it holds); a reader that finds a
#: version newer than this logs a warning and reads the fields it knows
#: about best-effort, rather than failing closed on a file a future build
#: wrote in a compatible-but-unrecognized way.
_ESCALATION_SCHEMA_VERSION = 1

#: Caps how many recent idempotency keys (see ``record_tier2_escalation``'s
#: ``escalation_key``) a counter file remembers, so a long-lived document's
#: sidecar file can't grow without bound across its lifetime -- a stale key
#: aging out of this window and being "forgotten" only means a very old
#: retry could double-count again, not that the mechanism is unsound for
#: its actual purpose (a caller retrying within the same request/session).
_MAX_RECENT_ESCALATION_KEYS = 200

#: Caps how long a single caller-supplied ``escalation_key`` (see
#: ``record_tier2_escalation``) may be before it is persisted verbatim
#: into ``recent_escalation_keys``. ``_MAX_RECENT_ESCALATION_KEYS`` above
#: only bounds the counter file's growth by key *count* -- a caller
#: passing one pathologically oversized key (e.g. a multi-megabyte
#: string) would still make the file grow far beyond what 200 short IDs
#: produce, defeating that bound via key *size* instead. This key is
#: meant to be an opaque request-correlation ID (a UUID is 36
#: characters), not arbitrary data, so 200 characters is deliberately
#: generous headroom while still keeping worst-case growth from a single
#: key in the same ballpark as the count cap.
_MAX_ESCALATION_KEY_LENGTH = 200

#: Bound (seconds) on how long ``record_tier2_escalation`` will wait to
#: acquire the counter file's lock before giving up and returning ``None``
#: (constructorfabric/studio#136, round-4 review, Major: the lock helper's
#: original always-blocking ``flock`` meant a live process holding this
#: lock indefinitely -- hung, deadlocked, or just very slow -- would block
#: the entire ``route_query``/``cfs retrieve`` call forever before Tier 2
#: could return anything). ``5`` seconds is three orders of magnitude
#: above this lock's normal hold time (one small JSON read + one
#: ``atomic_write_text``, typically low-single-digit milliseconds on
#: local disk), so two near-simultaneous real callers -- ordinary
#: contention -- comfortably both succeed well inside it; only a
#: genuinely stuck/abandoned lock ever trips this bound. It is
#: deliberately not larger: this call sits directly in a synchronous CLI
#: request path (``cfs retrieve``), so any bound here is a user-visible
#: worst-case latency, not just an internal safety margin.
_ESCALATION_LOCK_TIMEOUT_SECONDS = 5.0


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
def _cache_dir_for(path: Path) -> Optional[Path]:
    """Resolve ``<studio-dir>/.cache/doc-index/`` for the Studio project
    owning ``path``, or ``None`` outside one (e.g. no Studio directory can
    be found) -- the shared lookup every per-document cache file under this
    directory reuses (the structural index itself, and any sidecar file
    like :func:`_escalation_cache_path`'s), so a future addition doesn't
    re-implement this resolution.

    Resolved from ``path`` itself (not the process's current working
    directory), so indexing a file outside the caller's cwd still resolves
    -- and always resolves -- the Studio directory that actually owns it.
    """
    from .files import find_studio_directory

    try:
        studio_dir = find_studio_directory(path.resolve().parent)
    except OSError as exc:
        # A file whose parent can't be stat'd (permissions, a race) is not a
        # reason to fail the caller -- just an uncached build, like "no
        # Studio directory found". Warning, not debug: this is a genuine
        # anomaly (unlike the ordinary, unlogged "no Studio directory"
        # case below), and should be visible at the CLI's default log
        # level rather than indistinguishable from a routine cache miss.
        logger.warning("doc-index cache dir lookup failed for %s: %s", path, exc)
        return None
    if studio_dir is None:
        return None
    return studio_dir / _CACHE_SUBDIR / _INDEX_CACHE_DIR


def _cache_slug(path: Path) -> str:
    """The filename-safe identity a per-document cache file is keyed by."""
    return hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]


def _index_cache_path(path: Path) -> Optional[Path]:
    """Resolve ``<studio-dir>/.cache/doc-index/<slug>.json`` for a file.

    Returns ``None`` when no Studio directory can be found (e.g. outside a
    Studio-adapted project) -- callers should fall back to an uncached build.
    """
    cache_dir = _cache_dir_for(path)
    if cache_dir is None:
        return None
    return cache_dir / f"{_cache_slug(path)}.json"
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

    Each section's ``hash`` is a SHA-256 of its own text slice, with each
    line's trailing whitespace stripped before hashing -- a harmless
    "trim trailing whitespace on save" edit (a common editor/IDE default)
    changes no meaningful content and must not look like a real edit to
    :func:`diff_stale_sections`, which is the whole point of hashing at
    section granularity in the first place. The per-section granularity
    :func:`diff_stale_sections` needs to tell "this one section changed"
    from "the whole file changed", which a whole-file fingerprint
    structurally cannot do.

    Content before the first ``section_level`` heading (a document title,
    an intro paragraph) is otherwise invisible to every entry here, since
    each entry starts at a heading line -- a real gap, since that region is
    exactly where a title or one-line summary usually lives. When such
    content exists and isn't just blank lines, it's captured as a leading
    synthetic entry with ``heading=None`` (never a real heading's value,
    so a caller can tell it apart from actual sections) spanning lines 1
    through the line before the first real section heading.

    ``empty`` flags a section whose slice is only its own heading line --
    two same-level headings with nothing between them -- so a caller can
    skip summarizing content that doesn't exist rather than treating it
    the same as a genuinely short section.
    """
    if section_level is None:
        return []
    line_count = len(lines)
    marks = [(text, line_start) for level, text, line_start in headings_with_lines if level == section_level]
    sections: List[Dict[str, Any]] = []
    if marks and marks[0][1] > 1 and any(line.strip() for line in lines[:marks[0][1] - 1]):
        # Not "heading line + body": the whole span is body/title content,
        # already confirmed non-blank above, so never flagged empty.
        sections.append(_make_section(None, 1, marks[0][1] - 1, lines, empty=False))
    for i, (text, line_start) in enumerate(marks):
        line_end = marks[i + 1][1] - 1 if i + 1 < len(marks) else line_count
        # A real section's line_start is the heading line itself, so
        # line_end <= line_start means no body lines followed it at all.
        sections.append(_make_section(text, line_start, line_end, lines, empty=line_end <= line_start))
    return sections


def _make_section(
    heading: Optional[str], line_start: int, line_end: int, lines: List[str], *, empty: bool,
) -> Dict[str, Any]:
    hash_text = "\n".join(line.rstrip() for line in lines[line_start - 1:line_end])
    return {
        "heading": heading,
        "line_start": line_start,
        "line_end": line_end,
        "hash": hashlib.sha256(hash_text.encode("utf-8")).hexdigest(),
        "empty": empty,
        "summary": None,
    }
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-retrieval-sections


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-section-text
def section_text(lines: List[str], section: Dict[str, Any]) -> str:
    """Slice a retrieval section's own raw text out of the file's lines.

    Shared by every consumer that needs a section's actual content rather
    than just its boundaries (TF-IDF scoring, heading-nav search) -- one
    implementation of the ``line_start``/``line_end`` slicing convention
    instead of each consumer re-deriving it slightly differently.
    """
    return "\n".join(lines[section["line_start"] - 1:section["line_end"]])
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-section-text


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

    Deliberately does *not* carry any real-usage counters (e.g. Tier-2
    escalation volume, see :func:`record_tier2_escalation`): this index is
    the "read once per file" *structural* cache, rebuilt wholesale on any
    content edit -- a counter tracking usage of the *document* (which
    outlives any one edit) has no business living inside a cache keyed by
    the exact bytes currently on disk, and doing so would mean every
    single-counter increment pays to re-serialize this entire dict just to
    change one integer.
    """
    canonical_path = path.resolve()
    content, etag = _read_with_stable_etag(canonical_path)
    lines = content.split("\n")
    line_count = len(lines)

    headings = parse_headings_with_lines(lines)
    sections: List[Dict[str, Any]] = []
    for i, (level, text, line_start) in enumerate(headings):
        line_end = headings[i + 1][2] - 1 if i + 1 < len(headings) else line_count
        hash_text = "\n".join(line.rstrip() for line in lines[line_start - 1:line_end])
        sections.append({
            "level": level,
            "heading": text,
            "line_start": line_start,
            "line_end": line_end,
            "hash": hashlib.sha256(hash_text.encode("utf-8")).hexdigest(),
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
        # Reached only once the caller has already confirmed the cache file
        # exists, so a failure here is real corruption or a permissions
        # problem, not a routine cache miss -- warning, not debug, so it's
        # visible at the CLI's default log level instead of masquerading
        # as an ordinary first-time build.
        logger.warning("doc-index cache unreadable at %s: %s", cache_path, exc)
        return None


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-load
_REQUIRED_INDEX_FIELDS = ("total_lines", "sections", "section_level", "retrieval_sections")


def _has_schema_current_index(cached: Dict[str, Any]) -> bool:
    """``True`` only if ``cached`` carries every field a consumer
    (``commands/doc_index.py``, :func:`annotate_section_summary`,
    :func:`diff_stale_sections`) reads by subscript, at the schema version
    this module currently writes -- treated the same as a stale/corrupt
    cache otherwise, so a partially written, hand-edited, or pre-schema
    cache triggers a clean rebuild instead of a ``KeyError`` deep in a
    consumer. Also checks every ``retrieval_sections`` and ``sections``
    entry carries a ``hash``: both fields were added after their
    containers already existed, so a cache from one of those intermediate
    schemas would otherwise pass the top-level field-presence check and
    still raise on ``entry["hash"]``.
    """
    if cached.get("schema_version") != _SCHEMA_VERSION:
        return False
    if any(field not in cached for field in _REQUIRED_INDEX_FIELDS):
        return False
    if not all("hash" in section for section in cached["retrieval_sections"]):
        return False
    return all("hash" in section for section in cached["sections"])


def load_doc_index(path: Path) -> Optional[Dict[str, Any]]:
    """Load a cached index for ``path``, or ``None`` if missing/stale/absent.

    Staleness is detected from cheap ``Path.stat()`` metadata alone -- this
    never reads the file's content, so a cache *hit* stays free of a full
    read (the property the whole cache exists to provide). Only a stale or
    absent cache falls through to :func:`build_doc_index`, which does the
    one real read.

    A matching etag alone isn't enough: a cache written by an older version
    of this module (before ``section_level``/``retrieval_sections``
    existed) can have a matching etag if the file hasn't changed since, but
    a caller reading those fields on it would hit a ``KeyError`` rather
    than a clean rebuild. Treated the same as a stale cache -- rebuilt,
    not crashed on.
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
        # The cache file was just confirmed to exist, so a stat() failure
        # on the *source* file here means it vanished or became unreadable
        # since -- a real anomaly, not a routine miss.
        logger.warning("doc-index staleness check failed for %s: %s", path, exc)
        return None

    if cached.get("etag") != current_etag:
        return None
    if not _has_schema_current_index(cached):
        # A matching etag but a stale/malformed shape means a hand-edited
        # or pre-schema-bump cache slipped past the etag check -- a real
        # anomaly, not a routine miss, so warning rather than debug.
        logger.warning("doc-index cache for %s is malformed or predates the current schema; rebuilding", path)
        return None
    return cached
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-load


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-save
def save_doc_index(path: Path, index: Dict[str, Any]) -> bool:
    """Persist an index to its cache location. No-ops (returns ``False``)
    outside a Studio project, so a caller can tell an actual write from a
    silent no-op instead of assuming success unconditionally.

    Written atomically (temp file + ``os.replace``): a reader racing a
    concurrent writer sees either the old complete file or the new complete
    one, never a torn/partial write.
    """
    cache_path = _index_cache_path(path)
    if cache_path is None:
        return False
    atomic_write_text(cache_path, json.dumps(index, indent=2))
    return True
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
    except (OSError, UnicodeDecodeError) as exc:
        # Deliberately still debug, unlike this module's other fallback
        # logs: this one path has a genuinely expected trigger ("the file
        # was deleted after it was cached", per this function's own
        # contract) alongside the anomalous ones, so promoting it would
        # make a normal outcome noisy rather than making a real anomaly
        # visible.
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
    int}`` -- the *current* (fresh) position, in document order. Matched
    primarily by *content hash*, not position: a section's hash appearing
    in both the cached and fresh section lists is content that survived
    unedited, however it moved, so a pure reorder with zero text changes
    reports every section unchanged instead of misreporting the whole
    document as edited. Matching is multiset-based (:class:`Counter`), so
    genuine duplicate-content sections are paired up to the smaller of the
    two counts, with only the surplus falling to ``changed`` -- correct
    even when the same text legitimately appears more than once. Heading
    text alone still can't identify a specific section (duplicate heading
    titles are real -- see the ``toc-heading-duplicate`` check), so a
    caller addressing "this specific section" afterwards (e.g. to call
    :func:`annotate_section_summary`) uses the *current* ``line_start`` in
    a returned entry, not a hash. When the section *count* itself differs,
    ``structural_change`` is ``True`` and ``changed``/``unchanged`` aren't
    populated -- a diff across a changed count can't be safely narrowed to
    "which ones changed" without guessing, so the caller should fall back
    to a full rebuild rather than have this function guess for it.
    """
    cache_path = _index_cache_path(path)
    if cache_path is None or not cache_path.is_file():
        return None

    cached = _read_cache_file(cache_path)
    if cached is None or not _has_schema_current_index(cached):
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

    remaining_old_hashes = Counter(s["hash"] for s in old_sections)
    unchanged: List[Dict[str, Any]] = []
    changed: List[Dict[str, Any]] = []
    for new in fresh_sections:
        if remaining_old_hashes[new["hash"]] > 0:
            remaining_old_hashes[new["hash"]] -= 1
            unchanged.append(_position_entry(new))
        else:
            changed.append(_position_entry(new))
    return {"structural_change": False, "unchanged": unchanged, "changed": changed}
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-diff-stale



# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-annotate
def annotate_section_summary(path: Path, line_start: int, expected_hash: str, summary: str) -> bool:
    """Attach a one-line summary to a cached section, keyed by its line_start.

    Summaries are written by an LLM caller during a one-time enrichment
    pass, never generated inside this module. Returns ``False`` when no
    valid (non-stale) cached index exists, no section matches
    ``line_start``, or ``expected_hash`` doesn't match that section's
    current hash -- callers should build the index first, and re-resolve
    on a hash mismatch rather than retry blindly.

    ``expected_hash`` must be the hash of the ``sections`` entry the
    caller actually read and summarized (from a prior
    :func:`get_or_build_doc_index`/:func:`build_doc_index` call). Without
    this check, a document edited between that read and this write can
    shift a *different* section into the same ``line_start`` (e.g. content
    inserted above it), and matching by position alone would silently
    attach one section's summary to another section's content -- a
    caller can't tell the difference from the return value alone unless
    the write is rejected outright.

    Updates the matching entry in both ``sections`` (any heading level) and
    ``retrieval_sections`` (the coarser grouping) when both have a section
    starting at ``line_start`` -- a retriever reading ``retrieval_sections``
    needs the summary to show up there too, not just in the finer-grained
    list. A ``line_start`` that only matches ``sections`` (an off-level
    heading that isn't itself a retrieval section's start) updates only
    that list, which is correct: there is no corresponding retrieval
    section to update. The retrieval_sections match is only reached once
    the ``sections``-level hash check above has already confirmed this
    document position still holds the content the caller expects, so it
    doesn't need (and can't reuse -- its hash covers a different span) a
    second hash check of its own.

    The read-modify-write cycle (load, mutate one section, save) runs
    under :func:`studio.utils.atomic_io.with_file_lock`, so two concurrent
    calls annotating different sections of the same document don't race
    and silently drop one side's update.
    """
    cache_path = _index_cache_path(path)
    if cache_path is None:
        return False

    def _read_modify_write() -> bool:
        index = load_doc_index(path)
        if index is None:
            return False

        matched_section = None
        for section in index["sections"]:
            if section["line_start"] == line_start:
                matched_section = section
                break
        if matched_section is None:
            return False
        if matched_section["hash"] != expected_hash:
            return False

        matched_section["summary"] = summary
        for retrieval_section in index.get("retrieval_sections", []):
            if retrieval_section["line_start"] == line_start:
                retrieval_section["summary"] = summary
                break

        return save_doc_index(path, index)

    return with_file_lock(cache_path.with_name(f"{cache_path.name}.lock"), _read_modify_write)
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-annotate


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-escalation-cache-path
def _escalation_cache_path(path: Path) -> Optional[Path]:
    """Resolve ``<studio-dir>/.cache/doc-index/<slug>.escalations.json`` --
    a tiny, standalone counter file, deliberately *not* a field inside the
    structural ``doc_index.json`` cache (see :func:`record_tier2_escalation`
    for why): incrementing it must never require rewriting a document's
    full section/summary payload, and it must never share a lock (and
    therefore never race) with that cache's own build-and-save path -- a
    real bug caught in review (constructorfabric/studio#136), since
    :func:`get_or_build_doc_index`'s cache-miss rebuild took no lock at
    all, while a counter living inside that same file did.
    """
    cache_dir = _cache_dir_for(path)
    if cache_dir is None:
        return None
    return cache_dir / f"{_cache_slug(path)}.escalations.json"
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-escalation-cache-path


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-load-escalation-file
def _load_escalation_file(cache_path: Path) -> Dict[str, Any]:
    """Best-effort read of the raw escalation-counter JSON object at
    ``cache_path``, returning ``{}`` for a missing, corrupt, or
    non-object file -- the same "nothing usable here" fallback every
    caller below already treats as "never escalated."

    Each failure mode below logs its own, differently-worded message
    (missing file logs nothing at all -- it's the routine, expected shape
    of a document never escalated, not an anomaly) so a log reader can
    tell a genuinely corrupt/unreadable file apart from a merely
    not-yet-created one, or one holding the wrong JSON shape entirely --
    see :func:`get_tier2_escalations`'s docstring for why this
    ambiguity can't be fully eliminated from the *return value* itself
    without a bigger API change.
    """
    if not cache_path.is_file():
        return {}
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        # UnicodeDecodeError is a ValueError subclass, not an OSError, so it
        # is NOT caught by the (json.JSONDecodeError, OSError) clause below
        # -- without this clause it would propagate unhandled out of every
        # caller (cfs doc-index, cfs retrieve, ...) on a sidecar file
        # containing invalid UTF-8 (disk corruption, a bad manual edit).
        logger.warning(
            "doc-index escalation counter at %s is not valid UTF-8 (%s); treating as never-escalated",
            cache_path, exc,
        )
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "doc-index escalation counter at %s is corrupt/unreadable (%s); treating as never-escalated",
            cache_path, exc,
        )
        return {}
    if not isinstance(data, dict):
        logger.warning(
            "doc-index escalation counter at %s did not contain a JSON object (got %s); "
            "treating as never-escalated",
            cache_path, type(data).__name__,
        )
        return {}
    return data
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-load-escalation-file


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-escalation-count-from
def _escalation_count_from(data: Dict[str, Any], cache_path: Path) -> int:
    """Extract a valid ``tier2_escalations`` count from an already-parsed
    escalation-file object, clamping anything that isn't a real
    non-negative count (missing, wrong type, or negative -- e.g. a
    hand-edited or truncated-write file containing ``{"tier2_escalations":
    -5}``) down to ``0`` rather than letting it propagate into
    :func:`record_tier2_escalation`'s ``+ 1``, which would otherwise keep
    the counter negative (or worse, let it climb back through 0) forever.
    """
    schema_version = data.get("schema_version")
    if isinstance(schema_version, int) and schema_version > _ESCALATION_SCHEMA_VERSION:
        logger.warning(
            "doc-index escalation counter at %s declares schema_version %r, newer than this "
            "build understands (%d); reading tier2_escalations best-effort",
            cache_path, schema_version, _ESCALATION_SCHEMA_VERSION,
        )
    count = data.get("tier2_escalations", 0)
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        logger.warning(
            "doc-index escalation counter at %s has an invalid tier2_escalations value (%r); "
            "treating as never-escalated",
            cache_path, count,
        )
        return 0
    return count
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-escalation-count-from


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-get-escalations
def get_tier2_escalations(path: Path) -> int:
    """Read ``path``'s persisted Tier-2-escalation count without
    incrementing it -- ``0`` for a document never escalated, outside a
    Studio project, or whose counter file is missing/corrupt/holding an
    invalid (e.g. negative) count.

    Read-only, so this never takes the counter's lock: a concurrent
    increment mid-read is, at worst, a one-query-stale read of a
    monotonically increasing count -- never a wrong *kind* of answer, just
    possibly one behind, and resolved by whichever caller reads next.

    Known, accepted limitation: a healthy "never escalated yet" document
    and a corrupt/unreadable counter file both return ``0`` here -- the
    ``logger.warning`` calls in :func:`_load_escalation_file` and
    :func:`_escalation_count_from` are the only place those two cases are
    distinguishable (each fires a differently-worded message, and the
    routine "no file yet" case logs nothing at all). Exposing that
    distinction in this function's return value would mean changing its
    contract from "a count" to something callers would have to unwrap
    everywhere `should_build_okf` reasons about it; not worth it unless a
    real caller shows up that needs to react differently to "never
    escalated" vs. "counter broken."
    """
    cache_path = _escalation_cache_path(path)
    if cache_path is None:
        return 0
    data = _load_escalation_file(cache_path)
    return _escalation_count_from(data, cache_path)
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-get-escalations


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-normalize-escalation-key
def _normalize_escalation_key(escalation_key: Optional[str], path: Path) -> Optional[str]:
    """Reduce a caller-supplied ``escalation_key`` to either a real,
    matchable idempotency token or ``None`` ("no key, always increment").

    An empty string is normalized to ``None`` -- it was never a
    meaningful caller-supplied identity, so matching on it by exact
    string equality would let two unrelated callers that both happen to
    pass ``""`` silently collide (constructorfabric/studio#136, round-4
    review). A key over :data:`_MAX_ESCALATION_KEY_LENGTH` is likewise
    normalized to ``None`` (with a warning): this is meant to be a short,
    opaque request-correlation ID, not arbitrary data, and persisting an
    oversized one verbatim would defeat :data:`_MAX_RECENT_ESCALATION_KEYS`'s
    file-growth bound via key *size* instead of key *count*.
    """
    if escalation_key and len(escalation_key) > _MAX_ESCALATION_KEY_LENGTH:
        logger.warning(
            "doc-index escalation_key for %s is %d characters, over the %d-character cap; "
            "treating this call as if no key were given (the escalation is still recorded, "
            "just not deduplicated against a future retry)",
            path, len(escalation_key), _MAX_ESCALATION_KEY_LENGTH,
        )
        return None
    return escalation_key or None
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-normalize-escalation-key


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-record-escalation
def record_tier2_escalation(path: Path, escalation_key: Optional[str] = None) -> Optional[int]:
    """Increment and persist ``path``'s Tier-2-escalation counter, returning
    the new count (``None`` outside a Studio project -- nowhere to
    persist to at all -- when persisting the increment itself fails, the
    same "can't confirm this was really saved" contract
    :func:`annotate_section_summary` already uses, rather than reporting a
    fabricated success count; when the counter file's lock could not be
    acquired within :data:`_ESCALATION_LOCK_TIMEOUT_SECONDS`
    (constructorfabric/studio#136, round-4 review, Major); or when
    acquiring that lock raised some other ``OSError`` before it was even
    held -- e.g. creating the lock directory or opening the lock file
    itself failed (constructorfabric/studio#136, round-4 review, Major,
    a distinct follow-up finding from the timeout one) -- each of those
    four ``None`` cases logs its own distinct message so they're
    distinguishable in a log, even though all four surface identically to
    the caller).

    This is the real, observed-usage signal
    :func:`studio.utils.cascade.route_tier2` needs to decide whether
    building an OKF bundle for a document has crossed the point where it
    pays for itself, without a human supplying an ``expected_future_queries``
    guess -- see constructorfabric/studio#134. Counts Tier-1 *escalations*
    specifically (calls where heading-nav/TF-IDF couldn't resolve
    confidently on their own), not every query against the document: the
    OKF-vs-baseline choice this counter feeds is only ever made for the
    queries that actually reach Tier 2, so that is the population its
    break-even math (and this counter) needs to describe.

    Kept in its own tiny file (see :func:`_escalation_cache_path`) rather
    than as a field inside the structural ``doc_index.json`` cache: a
    document's real usage history outlives any one content edit, so it
    can't be reset on rebuild the way the structural cache correctly is --
    and it must never require rewriting that cache's full section/summary
    payload just to change one integer. Its own lock, on its own file,
    means it also never races :func:`get_or_build_doc_index`'s unlocked
    cache-miss rebuild, the way a shared file would.

    That lock is acquired through :func:`studio.utils.atomic_io.with_file_lock`
    with a bounded ``timeout`` (:data:`_ESCALATION_LOCK_TIMEOUT_SECONDS`),
    not the shared helper's default block-forever wait
    (constructorfabric/studio#136, round-4 review, Major): this call sits
    directly in the synchronous ``route_query``/``cfs retrieve`` request
    path, so an unbounded wait on a lock held by a hung, deadlocked, or
    merely very slow process would hang that entire CLI call forever
    before Tier 2 could return anything at all. On a timeout, this
    degrades to the same ``None`` "could not persist" contract as the
    other two cases above, logging its own distinctly-worded warning so a
    log reader can tell "gave up waiting for the lock" apart from "wrote
    successfully-guarded state, but the write itself failed" or "no
    project to persist to". This does not change behavior for the
    ordinary uncontended (or briefly contended) case: the timeout is
    generously sized against this lock's real, millisecond-scale normal
    hold time (see :data:`_ESCALATION_LOCK_TIMEOUT_SECONDS`'s own
    docstring), so two near-simultaneous genuine callers still both
    succeed well within it.

    ``escalation_key``, when given, is an opaque idempotency token
    identifying one *logical* Tier-2 escalation attempt (a caller mints one
    per query and passes the same value again on a retry of that same
    query, e.g. after a transient failure or timeout). This function has
    no other way to tell a genuine second escalation apart from a caller
    re-invoking it for the same one (constructorfabric/studio#136): every
    call looks identical from here (same path, same lock, no request
    context), so without a caller-supplied correlation token, a retry and
    a real repeat query are indistinguishable by construction, and any
    "detect the retry" heuristic risks the opposite bug -- silently
    dropping a real second escalation. A bounded window of recently-seen
    keys (see ``_MAX_RECENT_ESCALATION_KEYS``) is persisted alongside the
    count, under the same lock as the increment itself, so a key already
    seen returns the current count unchanged instead of incrementing
    again. Passing no key (the default, and every existing caller's
    current behaviour) preserves the original always-increment contract --
    there is nothing to deduplicate against without one.

    An empty string is treated the same as no key at all (always
    increments, nothing to deduplicate against): it was never a
    meaningful caller-supplied identity, so letting it match by exact
    string equality against ``recent_keys`` would make two unrelated
    callers that both happen to pass ``""`` silently collide -- the
    second call's real escalation would go uncounted, mistaken for a
    retry of the first. A key longer than ``_MAX_ESCALATION_KEY_LENGTH``
    is likewise treated as no key (with a warning): this is meant to be a
    short, opaque request-correlation ID, not arbitrary data, and
    persisting an oversized one verbatim would defeat
    ``_MAX_RECENT_ESCALATION_KEYS``'s file-growth bound via key *size*
    instead of key *count*.
    """
    cache_path = _escalation_cache_path(path)
    if cache_path is None:
        logger.warning(
            "doc-index escalation for %s has no Studio project to persist to; "
            "the escalation is not recorded and should_build_okf stays untracked (None)",
            path,
        )
        return None

    escalation_key = _normalize_escalation_key(escalation_key, path)

    def _read_modify_write() -> Optional[int]:
        data = _load_escalation_file(cache_path)
        current_count = _escalation_count_from(data, cache_path)

        recent_keys_raw = data.get("recent_escalation_keys")
        recent_keys = [k for k in recent_keys_raw if isinstance(k, str)] if isinstance(recent_keys_raw, list) else []

        if escalation_key is not None and escalation_key in recent_keys:
            # Same logical escalation attempt already recorded (a caller
            # retry after a transient failure/timeout, per this function's
            # own docstring) -- returning the already-persisted count
            # instead of incrementing again is what actually closes the
            # double-count hole; nothing else here can tell a retry apart
            # from a genuinely new escalation.
            return current_count

        new_count = current_count + 1
        payload: Dict[str, Any] = {
            "schema_version": _ESCALATION_SCHEMA_VERSION,
            "tier2_escalations": new_count,
        }
        if escalation_key is not None:
            payload["recent_escalation_keys"] = (recent_keys + [escalation_key])[-_MAX_RECENT_ESCALATION_KEYS:]
        elif recent_keys:
            # No key on *this* call, but earlier calls recorded some --
            # carry them forward unchanged rather than silently dropping
            # a mix of keyed and unkeyed callers' history.
            payload["recent_escalation_keys"] = recent_keys

        try:
            atomic_write_text(cache_path, json.dumps(payload))
        except OSError as exc:
            logger.warning(
                "doc-index escalation counter write failed for %s (persisting count %d): %s",
                cache_path, new_count, exc,
            )
            return None
        return new_count

    lock_path = cache_path.with_name(f"{cache_path.name}.lock")
    try:
        return with_file_lock(
            lock_path, _read_modify_write, timeout=_ESCALATION_LOCK_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.warning(
            "doc-index escalation counter lock for %s timed out after %.1fs "
            "(another process appears to be holding it); the escalation is not recorded and "
            "should_build_okf stays untracked (None)",
            path, _ESCALATION_LOCK_TIMEOUT_SECONDS,
        )
        return None
    except OSError as exc:
        # TimeoutError is itself an OSError subclass, so this only ever
        # catches something the specific clause above didn't: with_file_lock
        # creates the lock directory and opens the lock file *before* it
        # ever attempts to acquire the lock (constructorfabric/studio#136,
        # round-4 review) -- an OSError from either of those (e.g. a
        # permissions problem, a full disk, a missing parent on a broken
        # mount) would otherwise propagate uncaught through route_tier2
        # and crash `cfs retrieve` outright, instead of degrading to the
        # same "could not persist" None contract as every other failure
        # mode this function already handles.
        logger.warning(
            "doc-index escalation counter lock for %s could not be acquired (%s); "
            "the escalation is not recorded and should_build_okf stays untracked (None)",
            path, exc,
        )
        return None
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-record-escalation
