"""OKF (hierarchical summary) bundle: local, regenerable concept files and an
index for JIT retrieval's semantic fallback.

Deterministic infrastructure only, matching this module's siblings
(``doc_index.py``, ``tfidf.py``): no LLM call happens here. Writing an
actual section summary is an external caller's job (an agent, dispatched
outside this codebase) -- this module tracks which concept files should
exist, detects when one is stale relative to its source section, and
persists whatever the caller writes.

The whole bundle is local-only and gitignored (``.cache/okf/`` -- see
``.gitignore``): unlike the *content* of a summary, which is expensive to
regenerate (real LLM tokens), the fact that the bundle isn't checked in
just means a fresh clone rebuilds it from scratch the same way
``doc_index.py``'s own cache does. Nothing about this module assumes the
bundle survives across clones; it assumes only that it survives across
calls on the same machine, which is what makes the "only re-summarize what
changed" property of :func:`studio.utils.doc_index.diff_stale_sections`
actually save something.

See constructorfabric/studio#104.

@cpt-algo:cpt-studio-algo-traceability-validation-okf:p1
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .atomic_io import atomic_write_text, with_file_lock
from .doc_index import get_or_build_doc_index

logger = logging.getLogger(__name__)

_CACHE_SUBDIR = ".cache"
_BUNDLE_SUBDIR = "okf"
_MANIFEST_NAME = "manifest.json"
_INDEX_NAME = "index.md"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


# @cpt-begin:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-bundle-dir
def _okf_bundle_dir(path: Path) -> Optional[Path]:
    """Resolve ``<studio-dir>/.cache/okf/<slug>/`` for a source file.

    Same shape as ``doc_index._index_cache_path``: resolved from ``path``
    itself, not the process's working directory, so a bundle for a file
    outside the caller's cwd still resolves the Studio directory that
    actually owns it. Returns ``None`` outside a Studio-adapted project --
    callers should treat OKF as unavailable, not fail.
    """
    from .files import find_studio_directory

    try:
        studio_dir = find_studio_directory(path.resolve().parent)
    except OSError as exc:
        # A file whose parent can't be stat'd (permissions, a race) is not a
        # reason to fail the caller -- just an unavailable bundle, like "no
        # Studio directory found". Warning, not debug: this is a genuine
        # anomaly, mirroring doc_index._index_cache_path's identical check.
        logger.warning("okf bundle dir lookup failed for %s: %s", path, exc)
        studio_dir = None
    if studio_dir is None:
        return None

    slug = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
    return studio_dir / _CACHE_SUBDIR / _BUNDLE_SUBDIR / slug
# @cpt-end:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-bundle-dir


def _slugify(heading: Optional[str]) -> str:
    """Kebab-case a heading for a concept-file name. Collisions between two
    headings that slugify identically (e.g. duplicate titles, or titles
    differing only in punctuation) are resolved by the caller prefixing
    each filename with the section's document position, which is already
    guaranteed unique -- this function doesn't need to be collision-free on
    its own. ``None`` (the synthetic preamble section -- content before a
    document's first real heading, see doc_index.py's
    ``_build_retrieval_sections``) slugifies to a fixed, readable label
    rather than crashing on a heading that was never a real string."""
    if heading is None:
        return "preamble"
    slug = _SLUG_RE.sub("-", heading.strip().lower()).strip("-")
    return slug or "section"


def _concept_filename(position: int, heading: Optional[str]) -> str:
    return f"{position:02d}-{_slugify(heading)}.md"


def _allocate_concept_filename(position: int, heading: Optional[str], manifest: Dict[str, Any]) -> str:
    """Choose a concept filename for a genuinely new (never-before-written)
    section, guaranteed not to collide with any filename already recorded
    in the manifest. A naive position/heading-derived name alone could
    otherwise coincide with a different, already-written section's own
    file (e.g. duplicate headings after a reorder), letting
    :func:`write_concept_file` silently overwrite that section's summary.
    """
    existing = {e["concept_file"] for e in manifest.get("entries", [])}
    base = _concept_filename(position, heading)
    if base not in existing:
        return base
    stem, _, ext = base.rpartition(".")
    suffix = 2
    while f"{stem}-{suffix}.{ext}" in existing:
        suffix += 1
    return f"{stem}-{suffix}.{ext}"


_REQUIRED_MANIFEST_ENTRY_FIELDS = ("line_start", "concept_file", "built_from_hash")


def _is_valid_manifest_entry(entry: Any) -> bool:
    """``True`` only if *entry* has every required field, of the type every
    reader assumes. Presence alone isn't enough: ``line_start`` is used as
    a dict key (``by_line_start``/hash-pool matching in
    :func:`get_okf_status`) -- an unhashable value there (a list, a dict)
    raises ``TypeError`` before this module's own malformed-manifest
    fallback ever gets a chance to apply.
    """
    if not isinstance(entry, dict) or not all(field in entry for field in _REQUIRED_MANIFEST_ENTRY_FIELDS):
        return False
    return (
        isinstance(entry["line_start"], int) and not isinstance(entry["line_start"], bool)
        and isinstance(entry["concept_file"], str)
        and isinstance(entry["built_from_hash"], str)
    )


def _is_valid_manifest_shape(manifest: Any) -> bool:
    """``True`` only if *manifest* has the shape every reader assumes: a
    dict with an ``entries`` list, each entry a dict carrying every field
    :func:`get_okf_status`/:func:`write_concept_file` dereference by key, of
    the type each is actually used as. A hand-edited or partially-written
    manifest missing or mistyping one of these would otherwise surface as
    an unhandled ``KeyError``/``TypeError`` deep inside a reader, instead of
    the clean "treat this bundle as absent, rebuild" fallback every other
    malformed-cache case in this codebase already gets.
    """
    if not isinstance(manifest, dict):
        return False
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        return False
    return all(_is_valid_manifest_entry(entry) for entry in entries)


# @cpt-begin:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-manifest-io
def load_okf_manifest(path: Path) -> Optional[Dict[str, Any]]:
    """Load the OKF bundle manifest for ``path``, or ``None`` if absent/corrupt/unavailable."""
    bundle_dir = _okf_bundle_dir(path)
    if bundle_dir is None:
        return None
    manifest_path = bundle_dir / _MANIFEST_NAME
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        # Reached only once the caller has already confirmed the manifest
        # file exists, so a failure here is real corruption or a
        # permissions problem, not a routine miss -- warning, not debug,
        # mirroring doc_index._read_cache_file's identical check.
        logger.warning("okf manifest unreadable for %s: %s", path, exc)
        return None
    if not _is_valid_manifest_shape(manifest):
        logger.warning("okf manifest for %s has an invalid/incomplete shape; treating as absent", path)
        return None
    return manifest


def save_okf_manifest(path: Path, manifest: Dict[str, Any]) -> bool:
    """Persist the OKF bundle manifest atomically. No-ops (returns
    ``False``) outside a Studio project.

    Atomic (temp file + ``os.replace``) so a crash mid-write leaves the
    previous valid manifest in place instead of a torn/corrupt file --
    without this, a corrupt manifest is treated as "no manifest" by
    :func:`load_okf_manifest`, collapsing every previously-current
    section's status back to "missing" over a single interrupted write to
    one section.
    """
    bundle_dir = _okf_bundle_dir(path)
    if bundle_dir is None:
        return False
    atomic_write_text(bundle_dir / _MANIFEST_NAME, json.dumps(manifest, indent=2))
    return True
# @cpt-end:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-manifest-io


# @cpt-begin:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-status
def get_okf_status(path: Path) -> Dict[str, Any]:
    """Report the OKF bundle's state against the document's *current*
    retrieval sections -- not the manifest's own idea of what once existed.

    Returns ``{"available": bool, "bundle_dir": str | None, "entries":
    [...]}`` . Each entry is ``{"heading", "line_start", "line_end",
    "concept_file", "status"}``, where ``status`` is:

    - ``"missing"`` -- no manifest entry exists for this section yet (never
      summarized, or a structural change added it since the last summary
      pass -- see :func:`studio.utils.doc_index.diff_stale_sections`), or a
      manifest entry exists but its concept file was deleted, truncated, or
      corrupted out from under it (a manual edit, a crash mid-write outside
      this module's own atomic write path) -- the manifest's hash alone
      doesn't prove the file it points at still exists or holds real
      content (see :func:`_concept_file_is_valid`).
    - ``"stale"`` -- a manifest entry exists, but its recorded
      ``built_from_hash`` no longer matches the section's current hash
      (the source changed since the summary was written).
    - ``"current"`` -- the manifest's recorded hash matches; the concept
      file is trustworthy as-is.

    A section is matched to a manifest entry primarily by content hash, not
    position: if inserting or reordering *other* sections shifted this
    one's line numbers without touching its own text, its hash is
    unchanged, and it's matched to the entry that recorded that hash
    wherever that entry's own ``line_start`` now points -- preserving that
    entry's stored ``concept_file`` rather than recomputing one from the
    new position, so a reorder never claims a file that was never written.
    Entries are consumed one at a time per hash (ties broken toward the
    entry already at this exact ``line_start``, for stable pairing when
    duplicate-content sections exist), so each moved section claims a
    distinct entry rather than all collapsing onto the first. Only when no
    entry's hash matches does an entry already recorded at this exact
    ``line_start`` mark the section ``"stale"`` instead of ``"missing"``.

    ``available`` is ``False`` when there's no Studio directory to hold a
    bundle at all (outside a Studio-adapted project) -- distinct from an
    empty/all-missing bundle inside one.
    """
    bundle_dir = _okf_bundle_dir(path)
    if bundle_dir is None:
        return {"available": False, "bundle_dir": None, "entries": []}

    index = get_or_build_doc_index(path)
    sections = index["retrieval_sections"]
    manifest_entries = (load_okf_manifest(path) or {"entries": []}).get("entries", [])
    by_line_start = {entry["line_start"]: entry for entry in manifest_entries}
    pool: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for entry in manifest_entries:
        pool[entry["built_from_hash"]].append(entry)

    # Hash matching runs to completion for every section *before* any
    # stale/missing fallback lookup -- interleaving them would let a
    # section that moves *away* from a line_start (still unconsumed in
    # `by_line_start` at that point in document order) leak its entry to
    # a completely different, newly-added section that later happens to
    # occupy that same old line_start.
    matched_by_position = _match_sections_by_hash(sections, pool)
    consumed_ids = {id(entry) for entry in matched_by_position.values()}

    entries = [
        _resolve_section_status(
            section, position, matched_by_position.get(position), by_line_start, consumed_ids, bundle_dir,
        )
        for position, section in enumerate(sections, start=1)
    ]
    return {"available": True, "bundle_dir": str(bundle_dir), "entries": entries}


def _match_sections_by_hash(
    sections: List[Dict[str, Any]], pool: Dict[str, List[Dict[str, Any]]],
) -> Dict[int, Dict[str, Any]]:
    """Pass 1 of :func:`get_okf_status`'s matching: resolve every section's
    hash match (consuming ``pool`` as it goes) before any section's stale
    fallback runs, so consumption never depends on document-order timing
    between a moved section and whatever unrelated section now occupies
    its old line_start. Returns matched entries keyed by position (1-based).
    """
    matched_by_position: Dict[int, Dict[str, Any]] = {}
    for position, section in enumerate(sections, start=1):
        candidates = pool.get(section["hash"])
        if not candidates:
            continue
        same_slot = next(
            (c for c in candidates if c["line_start"] == section["line_start"]),
            candidates[0],
        )
        candidates.remove(same_slot)
        matched_by_position[position] = same_slot
    return matched_by_position


def _concept_file_is_valid(concept_path: Path) -> bool:
    """Minimal content-validity check for a concept file already confirmed
    to exist on disk: real content always opens *and closes* the YAML
    frontmatter block :func:`_build_frontmatter` writes. A physical-presence
    check alone (``is_file()``) can't tell a genuine concept file from one
    truncated, emptied, or corrupted after the fact -- checking only the
    opening ``---`` doesn't either, since a file truncated right after it
    still passes that alone; requiring the closing delimiter too catches
    that without needing full YAML parsing, which is more than this check
    needs to answer "is there real content here at all".
    """
    try:
        content = concept_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("okf concept file unreadable at %s: %s", concept_path, exc)
        return False
    return content.startswith("---\n") and "\n---\n" in content[4:]


def _resolve_section_status(
    section: Dict[str, Any],
    position: int,
    matched_entry: Optional[Dict[str, Any]],
    by_line_start: Dict[int, Dict[str, Any]],
    consumed_ids: Set[int],
    bundle_dir: Path,
) -> Dict[str, Any]:
    """Resolve one retrieval section's OKF entry -- the per-section half of
    :func:`get_okf_status`'s hash-primary matching, extracted so that
    function's own local-variable count doesn't grow with each new
    matching rule."""
    if matched_entry is not None:
        concept_file = matched_entry["concept_file"]
        status = "current" if _concept_file_is_valid(bundle_dir / concept_file) else "missing"
    else:
        stale_entry = by_line_start.get(section["line_start"])
        # An entry already claimed by a different section during hash
        # matching (id() tracked in consumed_ids) "belongs" to whichever
        # section moved away with it, not to whatever unrelated section
        # now sits at its old line_start -- reusing it here would link
        # this section to a concept file that was actually written for
        # the moved one.
        if stale_entry is not None and id(stale_entry) not in consumed_ids:
            # The section at this line_start was actually summarized before
            # (e.g. a heading rename with the body otherwise untouched) --
            # its real, already-written concept_file, not a filename
            # freshly derived from the *current* heading/position that was
            # never actually written to disk.
            concept_file = stale_entry["concept_file"]
            status = "stale" if _concept_file_is_valid(bundle_dir / concept_file) else "missing"
        else:
            concept_file = _concept_filename(position, section["heading"])
            status = "missing"
    return {
        "heading": section["heading"],
        "line_start": section["line_start"],
        "line_end": section["line_end"],
        "concept_file": concept_file,
        "status": status,
    }
# @cpt-end:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-status


# @cpt-begin:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-yaml-quote
def _yaml_quote(value: str) -> str:
    """Render ``value`` as a YAML double-quoted scalar, safe against
    embedded colons, quotes, backslashes, or newlines. Unescaped
    interpolation would let any of those turn a frontmatter value into
    invalid YAML, or -- for an embedded ``\\n---\\n`` -- prematurely close
    the frontmatter block and let the rest of the value inject new
    top-level keys. ``description`` is external-caller-supplied content
    (an LLM's own summary text), so it can't be assumed free of any of
    these.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return f'"{escaped}"'
# @cpt-end:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-yaml-quote


# @cpt-begin:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-render-index
def _render_index_md(
    source_path: Path,
    status_entries: List[Dict[str, Any]],
    descriptions_by_concept_file: Dict[str, str],
) -> str:
    """Deterministic template, not an LLM call: the same bullet-list-of-
    files-with-descriptions shape as the real OKF bundle this design was
    validated against (``experiments/okf-full-166-pages/index.md``).

    Takes :func:`get_okf_status`'s own status entries -- the single
    authoritative source for missing/stale/current -- rather than the raw
    manifest, so this listing can't disagree with what ``cfs okf-status``
    reports: every current retrieval section appears (not just ones ever
    written), a section whose concept file was deleted out from under it
    shows as missing rather than a dead link, and a stale entry is
    visibly marked rather than rendered identically to a current one.

    ``descriptions_by_concept_file`` is keyed by ``concept_file``, not
    ``line_start``: a section resolved by content hash after a move keeps
    its *original* manifest entry's ``concept_file`` (see
    :func:`_resolve_section_status`), but reports its *current* line_start
    -- keying by the current line_start would miss that entry's
    description entirely and render "(no summary yet)" for a section that
    genuinely has one.
    """
    lines = [
        f"# OKF Bundle — {source_path.name}",
        "",
        f"Local, regenerable bundle for `{source_path}`. Not committed -- see `.gitignore`.",
        "",
    ]
    for entry in status_entries:
        heading = entry["heading"] if entry["heading"] is not None else "(preamble)"
        if entry["status"] == "missing":
            lines.append(f"* {heading} - not yet summarized")
            continue
        description = descriptions_by_concept_file.get(entry["concept_file"]) or "(no summary yet)"
        marker = " _(stale -- source changed since written)_" if entry["status"] == "stale" else ""
        lines.append(f"* [{heading}]({entry['concept_file']}) - {description}{marker}")
    lines.append("")
    return "\n".join(lines)
# @cpt-end:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-render-index


# @cpt-begin:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-build-frontmatter
def _build_frontmatter(matched: Dict[str, Any], source_path: str, description: str, generated_by: str) -> str:
    """Build a concept file's YAML frontmatter block, every value safely
    quoted (see :func:`_yaml_quote`)."""
    title = matched["heading"] if matched["heading"] is not None else "(preamble)"
    resource = f"{source_path}#L{matched['line_start']}-L{matched['line_end']}"
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return (
        "---\n"
        f"title: {_yaml_quote(title)}\n"
        f"description: {_yaml_quote(description)}\n"
        f"resource: {_yaml_quote(resource)}\n"
        f"generated: {{ by: {_yaml_quote(generated_by)}, at: {_yaml_quote(generated_at)} }}\n"
        "---\n\n"
    )
# @cpt-end:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-build-frontmatter


# @cpt-begin:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-write-concept
def write_concept_file(
    path: Path,
    line_start: int,
    *,
    description: str,
    body: str,
    generated_by: str = "unknown",
) -> bool:
    """Write (or overwrite) one section's concept file and refresh the index.

    This is the external-caller hook -- called by an agent after it has
    actually produced a summary, never generated inside this module (same
    role as :func:`studio.utils.doc_index.annotate_section_summary`, one
    layer up). Returns ``False`` when ``line_start`` doesn't match a
    *current* retrieval section (the caller should re-check
    :func:`get_okf_status` -- the document may have changed structurally
    since it was queried) or when there's no Studio directory to hold a
    bundle in.

    Records the section's *current* hash as ``built_from_hash`` in the
    manifest -- this is what lets :func:`get_okf_status` later tell
    "current" from "stale" without re-reading the summary itself.

    The manifest's read-modify-write cycle, the concept-file write, and
    the index.md regeneration all run under one exclusive lock (mirroring
    :func:`studio.utils.doc_index.annotate_section_summary`'s own use of
    the same primitive), so two concurrent calls writing different
    sections of the same document's bundle can't each load the same base
    manifest and have whichever saves last silently discard the other's
    entry. Both file writes are atomic (temp file + ``os.replace``), so a
    crash mid-write leaves the previous valid file in place instead of a
    torn one.
    """
    bundle_dir = _okf_bundle_dir(path)
    if bundle_dir is None:
        return False

    index = get_or_build_doc_index(path)
    sections = index["retrieval_sections"]
    matched = next((s for s in sections if s["line_start"] == line_start), None)
    if matched is None:
        return False

    position = sections.index(matched) + 1
    frontmatter = _build_frontmatter(matched, index["path"], description, generated_by)

    def _read_modify_write() -> bool:
        manifest = load_okf_manifest(path) or {"source_path": index["path"], "entries": []}
        manifest_entries = manifest.get("entries", [])

        # Reuse the resolved manifest entry's own concept_file when one
        # already exists for this section's identity (matched by content
        # hash, so a reorder/rename resolves to the same entry it always
        # has) -- a filename freshly derived from just this section's
        # *current* position/heading could otherwise collide with a
        # different, already-written section's own file after a reorder,
        # letting this write silently replace that section's summary.
        current_status = get_okf_status(path)
        existing_entry = next(
            (e for e in current_status["entries"] if e["line_start"] == line_start and e["status"] != "missing"),
            None,
        )
        concept_filename = (
            existing_entry["concept_file"] if existing_entry is not None
            else _allocate_concept_filename(position, matched["heading"], manifest)
        )
        atomic_write_text(bundle_dir / concept_filename, frontmatter + body)

        new_entry = {
            "heading": matched["heading"],
            "line_start": line_start,
            "concept_file": concept_filename,
            "description": description,
            "built_from_hash": matched["hash"],
        }
        # Replace by concept_file identity, not by raw line_start: a
        # section resolved via hash match keeps its concept_file across a
        # move even though the manifest's own recorded line_start for it
        # is now stale. Keying the update by *this write's* line_start
        # alone would silently orphan that entry whenever a different,
        # newly-added section legitimately lands on that same line_start.
        manifest["entries"] = sorted(
            [e for e in manifest_entries if e["concept_file"] != concept_filename] + [new_entry],
            key=lambda e: e["line_start"],
        )
        manifest_saved = save_okf_manifest(path, manifest)

        status = get_okf_status(path)
        descriptions_by_concept_file = {e["concept_file"]: e.get("description") for e in manifest["entries"]}
        atomic_write_text(
            bundle_dir / _INDEX_NAME,
            _render_index_md(Path(index["path"]), status["entries"], descriptions_by_concept_file),
        )
        return manifest_saved

    return with_file_lock(bundle_dir / f"{_MANIFEST_NAME}.lock", _read_modify_write)
# @cpt-end:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-write-concept
