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


def _slugify(heading: str) -> str:
    """Kebab-case a heading for a concept-file name. Collisions between two
    headings that slugify identically (e.g. duplicate titles, or titles
    differing only in punctuation) are resolved by the caller prefixing
    each filename with the section's document position, which is already
    guaranteed unique -- this function doesn't need to be collision-free on
    its own."""
    slug = _SLUG_RE.sub("-", heading.strip().lower()).strip("-")
    return slug or "section"


def _concept_filename(position: int, heading: str) -> str:
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
    """Persist the OKF bundle manifest. No-ops (returns ``False``) outside a Studio project."""
    bundle_dir = _okf_bundle_dir(path)
    if bundle_dir is None:
        return False
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / _MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
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
      pass -- see :func:`studio.utils.doc_index.diff_stale_sections`).
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
        if manifest_entry is None:
            status = "missing"
        elif manifest_entry.get("built_from_hash") != section["hash"]:
            status = "stale"
        else:
            status = "current"
        entries.append({
            "heading": section["heading"],
            "line_start": section["line_start"],
            "line_end": section["line_end"],
            "concept_file": _concept_filename(position, section["heading"]),
            "status": status,
        })

    return {"available": True, "bundle_dir": str(bundle_dir), "entries": entries}
# @cpt-end:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-status


# @cpt-begin:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-render-index
def _render_index_md(source_path: Path, entries: List[Dict[str, Any]]) -> str:
    """Deterministic template, not an LLM call: the same bullet-list-of-
    files-with-descriptions shape as the real OKF bundle this design was
    validated against (``experiments/okf-full-166-pages/index.md``)."""
    lines = [
        f"# OKF Bundle — {source_path.name}",
        "",
        f"Local, regenerable bundle for `{source_path}`. Not committed -- see `.gitignore`.",
        "",
    ]
    for entry in entries:
        description = entry.get("description") or "(no summary yet)"
        lines.append(f"* [{entry['heading']}]({entry['concept_file']}) - {description}")
    lines.append("")
    return "\n".join(lines)
# @cpt-end:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-render-index


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
    bundle_dir.mkdir(parents=True, exist_ok=True)
    frontmatter = (
        "---\n"
        f"title: {matched['heading']}\n"
        f"description: {description}\n"
        f"resource: {index['path']}#L{matched['line_start']}-L{matched['line_end']}\n"
        f"generated: {{ by: {generated_by}, at: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} }}\n"
        "---\n\n"
    )
    (bundle_dir / concept_filename).write_text(frontmatter + body, encoding="utf-8")

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

    (bundle_dir / _INDEX_NAME).write_text(
        _render_index_md(Path(index["path"]), manifest["entries"]), encoding="utf-8"
    )
    return True
# @cpt-end:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-write-concept
