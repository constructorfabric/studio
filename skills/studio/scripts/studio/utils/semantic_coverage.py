"""Advisory semantic-coverage pass — wire the semantic engine into ``spec-coverage``.

Structural ``spec-coverage`` scores marker *density*; the semantic engine
(:mod:`studio.utils.eval_semantic`) asks the layer density cannot reach — *does a marked block
implement the requirement it cites?* This module is the thin glue between them: it builds the
engine's ``Pairing`` list from the real marked blocks and their resolved requirements, runs the
advisory ``assess``, and serialises the result for the coverage report plus a one-line human summary.

**Advisory, never gates.** Nothing here touches the coverage status or exit code — the caller
attaches the returned section to the report *after* the structural gate is computed.

Requirement granularity is **per-algo**, not per-instruction: a block marker's ``id`` is its algo id,
and the feature-doc requirement text is scoped to that id (the instruction slug is not independently
scoped in the doc format). Every block of an algo therefore pairs with the algo's declaration text;
blocks whose code diverges from that vocabulary surface as weak links.

@cpt-algo:cpt-studio-algo-semantic-coverage-pass:p1
"""
# @cpt-begin:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-imports
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .codebase import CodeFile
from .context import collect_artifacts_to_scan
from .document import scan_cpt_ids
from . import eval_semantic

logger = logging.getLogger(__name__)
# @cpt-end:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-imports


# @cpt-begin:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-defmap
def _definition_map(ctx: object) -> Dict[str, Path]:
    """Map every cpt **definition** id to its declaring artifact path.

    This is the id→doc lookup the requirement side needs: a block cites an algo id, and the
    requirement text lives in whichever artifact *defines* that id. Built from the registered
    artifacts (``collect_artifacts_to_scan``); the first definition wins on the rare duplicate.
    """
    out: Dict[str, Path] = {}
    artifacts, _sources = collect_artifacts_to_scan(ctx)
    for artifact_path, _kind in artifacts:
        for hit in scan_cpt_ids(artifact_path):
            if hit.get("type") == "definition" and isinstance(hit.get("id"), str):
                existing = out.get(hit["id"])
                if existing is not None and existing != artifact_path:
                    logger.warning("semantic: cpt id %s defined in both %s and %s; keeping the first",
                                   hit["id"], existing, artifact_path)
                out.setdefault(hit["id"], artifact_path)
    return out
# @cpt-end:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-defmap


# @cpt-begin:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-pairings
def _relative_posix(path: Path, project_root: Optional[Path]) -> str:
    """A **project-relative POSIX** path, never absolute — so no local path leaks into the report or
    the out-of-tree judge prompt. Degrades to a ``..``-relative path for a file outside the root,
    then to the bare filename if even that is impossible (Windows cross-drive)."""
    if project_root is None:
        return path.as_posix()
    root, resolved = Path(project_root).resolve(), path.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        logger.debug("semantic: %s is outside project_root; using a relative path", path)
    try:
        return Path(os.path.relpath(resolved, root)).as_posix()
    except ValueError:
        return Path(path.name).as_posix()


def _pairings_for_files(files: Sequence[Path], definitions: Dict[str, Path],
                        project_root: Optional[Path] = None) -> List[eval_semantic.Pairing]:
    """One ``Pairing`` per marked block: code = the block's own lines, requirement = the algo
    declaration resolved from the block's id, or ``None`` (unjudgeable) when the id declares no
    retrievable text. ``block_id`` is ``<algo>:<inst>`` so each block is individually identifiable
    even though the requirement (and ``bm.id``) is shared across an algo's blocks.

    ``path`` is emitted **project-relative POSIX** (see ``_relative_posix``) so it matches the
    coverage report's own scope arrays — the code files arrive absolute, so without this the scope
    reader would compare an absolute pairing path against a relative report path and never match."""
    pairings: List[eval_semantic.Pairing] = []
    for code_path in dict.fromkeys(files):        # dedup duplicate registrations, keep order
        code_file, errs = CodeFile.from_path(code_path)
        if code_file is None:
            logger.warning("semantic: skipping unparseable file %s: %s", code_path, errs)
            continue
        path_posix = _relative_posix(code_file.path, project_root)
        for block in code_file.block_markers:
            doc = definitions.get(block.id)
            requirement = eval_semantic.resolve_requirement(doc, block.id) if doc is not None else None
            pairings.append(eval_semantic.Pairing(
                block_id=f"{block.id}:{block.inst}",
                inst=block.inst,
                path=path_posix,
                start_line=block.start_line,
                code="\n".join(block.content),
                requirement=requirement))
    return pairings
# @cpt-end:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-pairings


# @cpt-begin:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-run
def run_semantic_pass(ctx: object, files: Sequence[Path], coverage_report: Dict[str, object],
                      judge_fn: Optional[eval_semantic.SemanticJudgeFn] = None) -> Dict[str, object]:
    """Build pairings from the marked blocks, run the advisory engine, return the ``semantic`` section.

    ``coverage_report`` is passed straight to ``assess`` for scoping (``excluded`` / ``whole_file_claims``,
    tolerated absent → empty scope). With no ``judge_fn`` wired, weak links are ``unjudgeable`` and no
    model is called. The returned dict is advisory on its face (``"advisory": True``) and is never read
    by the coverage gate — the caller attaches it after the status/exit are set.
    """
    definitions = _definition_map(ctx)
    pairings = _pairings_for_files(files, definitions, getattr(ctx, "project_root", None))
    result = eval_semantic.assess(pairings, judge_fn=judge_fn, report=coverage_report)
    return {
        "assessed": result.assessed,
        "presumed_covered": result.presumed_covered,
        "unjudgeable": [{"block_id": gap.block_id, "path": gap.path,
                         "start_line": gap.start_line, "reason": gap.reason}
                        for gap in result.unjudgeable],
        "findings": [{"block_id": finding.block_id, "path": finding.path,
                      "start_line": finding.start_line, "verdict": finding.verdict,
                      "rationale": finding.rationale, "evidence_ok": finding.evidence_ok,
                      "forced": finding.forced}
                     for finding in result.findings],
        "skipped_excluded": result.skipped_excluded,
        "schema_version": result.schema_version,
        "advisory": True,
    }
# @cpt-end:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-run


# @cpt-begin:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-summary
def summary_line(semantic: Dict[str, object]) -> str:
    """A one-line advisory human summary: counts + the weak/wrong finding tally, labelled advisory."""
    if semantic.get("error"):
        return f"semantic (advisory, never gates): pass errored, skipped — {semantic['error']}"
    findings = semantic.get("findings") or []
    weak = sum(1 for finding in findings
               if finding.get("verdict") in (eval_semantic.SEM_WRONG, eval_semantic.SEM_PARTIAL))
    return (f"semantic (advisory, never gates): {semantic.get('assessed', 0)} judged, "
            f"{semantic.get('presumed_covered', 0)} presumed-covered, "
            f"{len(semantic.get('unjudgeable') or [])} unjudgeable, {weak} weak/wrong")
# @cpt-end:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-summary
