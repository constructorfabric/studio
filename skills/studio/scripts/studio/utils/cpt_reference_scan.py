"""Shared cpt-id reference scan.

The one ``scan_cpt_ids`` traversal that ``where_used``, ``where_defined``,
``list_ids`` and ``list_id_kinds`` each re-implemented, plus the def↔ref view the
artifact-quality gap / traceability / contradiction detectors build on. cpt-id
scoped — prose / ``PRD-NNN`` requirements are out of scope (a documented v1 limit).

Read-only, stdlib-only. Behaviour is identical to the loops it replaces; the
callers keep their own projections.

@cpt-algo:cpt-studio-algo-cpt-reference-scan:p1
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from .document import scan_cpt_ids


# @cpt-begin:cpt-studio-algo-cpt-reference-scan:p1:inst-scan-records
def scan_records(
    artifacts_to_scan: List[Tuple[Path, str]],
) -> Iterator[Tuple[Path, str, Dict[str, object]]]:
    """Yield ``(artifact_path, artifact_type, hit)`` for every ``scan_cpt_ids``
    hit across *artifacts_to_scan* — the doubled loop the callers shared.

    The raw hit is passed through untouched so each caller keeps its exact
    projection (id-strip, line coercion, kind inference, def/ref filtering).
    """
    for artifact_path, artifact_type in artifacts_to_scan:
        for hit in scan_cpt_ids(artifact_path):
            yield artifact_path, artifact_type, hit
# @cpt-end:cpt-studio-algo-cpt-reference-scan:p1:inst-scan-records


# @cpt-begin:cpt-studio-algo-cpt-reference-scan:p1:inst-record
def _record(
    artifact_path: Path,
    artifact_type: str,
    hit: Dict[str, object],
    path_to_source: Dict[str, str],
    *,
    include_type: bool,
) -> Dict[str, object]:
    """One locus record, shared by the reference and definition projections.

    ``include_type`` adds the ``type`` key (references carry it; definitions omit
    it) in its historical position — between ``kind`` and ``checked`` — so the
    emitted dict is byte-for-byte what the commands produced before this util.
    """
    rec: Dict[str, object] = {
        "artifact": str(artifact_path),
        "artifact_type": artifact_type,
        "line": int(hit.get("line", 1) or 1),
        "kind": None,
    }
    if include_type:
        rec["type"] = str(hit.get("type"))
    rec["checked"] = bool(hit.get("checked", False))
    src = path_to_source.get(str(artifact_path))
    if src:
        rec["source"] = src
    return rec
# @cpt-end:cpt-studio-algo-cpt-reference-scan:p1:inst-record


# @cpt-begin:cpt-studio-algo-cpt-reference-scan:p1:inst-references
def references(
    target_id: str,
    artifacts_to_scan: List[Tuple[Path, str]],
    path_to_source: Dict[str, str],
    *,
    include_definitions: bool,
) -> List[Dict[str, object]]:
    """References to *target_id* (optionally including its definitions).

    The ``where_used`` projection, verbatim: a reference hit whose id matches,
    with its type; definition hits included only when *include_definitions*.
    """
    out: List[Dict[str, object]] = []
    for artifact_path, artifact_type, h in scan_records(artifacts_to_scan):
        if str(h.get("id") or "") != target_id:
            continue
        if h.get("type") == "definition" and not include_definitions:
            continue
        out.append(_record(artifact_path, artifact_type, h, path_to_source, include_type=True))
    return out
# @cpt-end:cpt-studio-algo-cpt-reference-scan:p1:inst-references


# @cpt-begin:cpt-studio-algo-cpt-reference-scan:p1:inst-definitions
def definitions(
    target_id: str,
    artifacts_to_scan: List[Tuple[Path, str]],
    path_to_source: Dict[str, str],
) -> List[Dict[str, object]]:
    """Definitions of *target_id* — the ``where_defined`` projection, verbatim
    (no ``type`` key; ``kind`` left ``None`` for the caller to annotate)."""
    out: List[Dict[str, object]] = []
    for artifact_path, artifact_type, h in scan_records(artifacts_to_scan):
        if h.get("type") != "definition":
            continue
        if str(h.get("id") or "") != target_id:
            continue
        out.append(_record(artifact_path, artifact_type, h, path_to_source, include_type=False))
    return out
# @cpt-end:cpt-studio-algo-cpt-reference-scan:p1:inst-definitions


# @cpt-begin:cpt-studio-algo-cpt-reference-scan:p1:inst-graph-for
def graph_for(
    target_id: str,
    artifacts_to_scan: List[Tuple[Path, str]],
    path_to_source: Optional[Dict[str, str]] = None,
) -> Dict[str, List[Dict[str, object]]]:
    """The def↔ref view a detector wants for one cpt-id: where it is defined and
    where it is referenced.

    ``defined_in`` is the definition loci (no ``type`` key); ``referenced_in`` is the
    non-definition reference loci (each with its ``type``). Built with the same
    ``references`` / ``definitions`` logic the query commands use, so it classifies
    definitions and references identically to them.

    Two-pass by construction: ``defined_in`` and ``referenced_in`` come from two
    independent ``scan_records`` passes, so they are computed separately — do not rely
    on cross-list atomicity between them. That is fine for one id while the view is
    unused, but a caller that needs many ids must NOT call ``graph_for`` per id in a
    loop — that is ``O(n_ids × n_artifacts)`` rescans of the whole tree. Build a single
    ``scan_records`` pass and partition it locally instead.

    ``path_to_source`` is optional here — a detector usually wants only the def/ref
    loci, not source text — whereas ``references`` / ``definitions`` require it, since
    every command call site has the map. Requiring it there is deliberate: a missing
    map at those call sites is a bug we want surfaced, not silently defaulted. Passing
    ``None`` is equivalent to an empty map (no ``source`` keys emitted).
    """
    src = path_to_source or {}
    return {
        "defined_in": definitions(target_id, artifacts_to_scan, src),
        "referenced_in": references(
            target_id, artifacts_to_scan, src, include_definitions=False
        ),
    }
# @cpt-end:cpt-studio-algo-cpt-reference-scan:p1:inst-graph-for
