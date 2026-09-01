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
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        logger.debug("okf bundle dir lookup skipped for %s: %s", path, exc)
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
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("okf manifest unreadable for %s: %s", path, exc)
        return None


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
      manifest entry exists but its concept file was deleted out from under
      it (a manual cleanup, say) -- the manifest's hash alone doesn't prove
      the file it points at still exists.
    - ``"stale"`` -- a manifest entry exists, but its recorded
      ``built_from_hash`` no longer matches the section's current hash
      (the source changed since the summary was written).
    - ``"current"`` -- the manifest's recorded hash matches; the concept
      file is trustworthy as-is.

    ``available`` is ``False`` when there's no Studio directory to hold a
    bundle at all (outside a Studio-adapted project) -- distinct from an
    empty/all-missing bundle inside one.
    """
    bundle_dir = _okf_bundle_dir(path)
    if bundle_dir is None:
        return {"available": False, "bundle_dir": None, "entries": []}

    index = get_or_build_doc_index(path)
    manifest = load_okf_manifest(path) or {"entries": []}
    by_line_start = {entry["line_start"]: entry for entry in manifest.get("entries", [])}

    entries = []
    for position, section in enumerate(index["retrieval_sections"], start=1):
        manifest_entry = by_line_start.get(section["line_start"])
        concept_file = _concept_filename(position, section["heading"])
        if manifest_entry is None or not (bundle_dir / concept_file).is_file():
            status = "missing"
        elif manifest_entry.get("built_from_hash") != section["hash"]:
            status = "stale"
        else:
            status = "current"
        entries.append({
            "heading": section["heading"],
            "line_start": section["line_start"],
            "line_end": section["line_end"],
            "concept_file": concept_file,
            "status": status,
        })

    return {"available": True, "bundle_dir": str(bundle_dir), "entries": entries}
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
    descriptions_by_line_start: Dict[int, str],
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
        description = descriptions_by_line_start.get(entry["line_start"]) or "(no summary yet)"
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
    concept_filename = _concept_filename(position, matched["heading"])
    frontmatter = _build_frontmatter(matched, index["path"], description, generated_by)

    def _read_modify_write() -> bool:
        atomic_write_text(bundle_dir / concept_filename, frontmatter + body)

        manifest = load_okf_manifest(path) or {"source_path": index["path"], "entries": []}
        entries_by_line_start = {e["line_start"]: e for e in manifest.get("entries", [])}
        entries_by_line_start[line_start] = {
            "heading": matched["heading"],
            "line_start": line_start,
            "concept_file": concept_filename,
            "description": description,
            "built_from_hash": matched["hash"],
        }
        manifest["entries"] = sorted(entries_by_line_start.values(), key=lambda e: e["line_start"])
        save_okf_manifest(path, manifest)

        status = get_okf_status(path)
        descriptions_by_line_start = {e["line_start"]: e.get("description") for e in manifest["entries"]}
        atomic_write_text(
            bundle_dir / _INDEX_NAME,
            _render_index_md(Path(index["path"]), status["entries"], descriptions_by_line_start),
        )
        return True

    return with_file_lock(bundle_dir / f"{_MANIFEST_NAME}.lock", _read_modify_write)
# @cpt-end:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-write-concept
