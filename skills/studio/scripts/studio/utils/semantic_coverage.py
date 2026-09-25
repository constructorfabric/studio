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
from typing import Dict, List, Optional, Sequence, Tuple

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
    # Only for the warning below: the map itself keeps absolute paths, which is what
    # callers resolve against. Log records are the thing that travels.
    root = getattr(ctx, "project_root", None)
    for artifact_path, _kind in artifacts:
        for hit in scan_cpt_ids(artifact_path):
            if hit.get("type") == "definition" and isinstance(hit.get("id"), str):
                existing = out.get(hit["id"])
                if existing is not None and existing != artifact_path:
                    # Project-relative, like every other path this module emits: an
                    # absolute one here discloses the username and directory layout for
                    # no benefit, and is harder to read besides.
                    logger.warning("semantic: cpt id %s defined in both %s and %s; keeping the first",
                                   hit["id"], _relative_posix(existing, root),
                                   _relative_posix(artifact_path, root))
                out.setdefault(hit["id"], artifact_path)
    return out
# @cpt-end:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-defmap


# @cpt-begin:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-pairings
def _relative_posix(path: Path, project_root: Optional[Path]) -> str:
    """A **project-relative POSIX** path, never absolute — so no local path leaks into the report or
    the out-of-tree judge prompt. Degrades to a ``..``-relative path for a file outside the root,
    then to the bare filename if even that is impossible (Windows cross-drive, or no root at all).

    ``project_root`` is resolved by the caller with ``getattr(ctx, "project_root", None)``, so a
    context that carries no root at all arrives here as ``None``. Returning ``path.as_posix()``
    for that case handed back the full absolute path -- username and directory layout included --
    straight into the judge prompt and the serialised report, which is the one thing the first
    sentence of this docstring promises never happens. With no root to be relative to, the bare
    filename is the most that can be said without leaking where the file lives.
    """
    if project_root is None:
        return Path(path.name).as_posix()
    root, resolved = Path(project_root).resolve(), path.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        # The *name*, not the path. The function's first sentence promises no local path
        # leaks, and #200 made the return value keep that promise -- this line still
        # interpolated the raw absolute path, so the username and directory layout went
        # into the log instead of the report. A debug record is a narrower audience than
        # a judge prompt, not a different rule.
        logger.debug("semantic: %s is outside project_root; using a relative path", path.name)
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
            # The error *codes*, not the raw finding dicts: each one carries its own
            # absolute `path` and `location`, so interpolating them put back the path
            # this line had just been made to drop. The file is already named.
            codes = sorted({str(err.get("code")) for err in errs if isinstance(err, dict)})
            logger.warning("semantic: skipping unparseable file %s: %s",
                           _relative_posix(code_path, project_root), ", ".join(codes) or errs)
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


# @cpt-begin:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-selector-forms
def _selector_forms(selector: str) -> List[str]:
    """The selector as typed, and with a leading ``inst-`` stripped from its instruction part.

    A marker in the source reads ``@cpt-begin:<algo>:p1:inst-scov-run``, but the parser drops the
    ``inst-`` prefix, so the ``block_id`` is ``<algo>:scov-run``. Copying the id straight out of
    the code — the obvious thing to do — therefore matched nothing, and an unmatched selector
    reads as "this requirement is clean". Every example first written for this flag used the
    ``inst-`` form and none of them worked; caught by a test built from real pairings rather than
    hand-made ones.

    Both forms are accepted rather than demanding the reader know an internal prefix rule. The
    bare ``<algo>`` form has no instruction part and is returned unchanged.

    A list, not a tuple: the length varies with the selector — one form or two — and a tuple
    reads as a fixed record shape, which is what ``python:S8495`` objects to.
    """
    algo, sep, inst = selector.partition(":")
    if sep and inst.startswith("inst-"):
        return [selector, f"{algo}:{inst[len('inst-'):]}"]
    return [selector]
# @cpt-end:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-selector-forms


# @cpt-begin:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-select
def _select_blocks(pairings: List[eval_semantic.Pairing],
                   selectors: Optional[Sequence[str]]
                   ) -> Tuple[List[eval_semantic.Pairing], List[str]]:
    """Narrow ``pairings`` to the named selectors, and name any selector that matched nothing.

    A ``block_id`` is ``<algo>:<inst>``, and one requirement is shared across an algo's blocks, so
    a selector is accepted at either granularity: the bare ``<algo>`` selects every block
    implementing that requirement, ``<algo>:<inst>`` narrows to that instruction. It is **not** a
    promise of one block: block ids are not unique in this repository — of the 2632 ``@cpt-begin``
    markers in ``.py`` files, 283 ids are carried by more than one block, the worst by ten — so
    the narrow form selects every block carrying that id. (Counted over the markers in the tree,
    not over one run's pairings: the pairing set is scoped to the files in the coverage report,
    so a count taken from it would not be a fact about the repository.) The prefix rule is
    anchored on the colon rather than a bare ``startswith`` — otherwise ``cpt-studio-algo-eval``
    would silently also select ``cpt-studio-algo-eval-harness``, handing a reviewer a wider set
    than they asked for while looking like it worked.

    Unmatched selectors are **returned, not dropped**. An empty result and a typo are the same
    picture on screen — no findings — and they mean opposite things. The caller surfaces them; it
    cannot raise, because this whole pass is walled off from the status and exit code by design.
    """
    if not selectors:
        return pairings, []
    wanted = list(dict.fromkeys(selectors))          # de-duplicated, order preserved for the report
    kept: List[eval_semantic.Pairing] = []
    matched: set[str] = set()
    for pairing in pairings:
        block_id = pairing.block_id
        for selector in wanted:
            if any(block_id == form or block_id.startswith(f"{form}:")
                   for form in _selector_forms(selector)):
                matched.add(selector)
                kept.append(pairing)
                break
    return kept, [selector for selector in wanted if selector not in matched]
# @cpt-end:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-select


# @cpt-begin:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-run
def run_semantic_pass(ctx: object, files: Sequence[Path], coverage_report: Dict[str, object],
                      judge_fn: Optional[eval_semantic.SemanticJudgeFn] = None,
                      blocks: Optional[Sequence[str]] = None) -> Dict[str, object]:
    """Build pairings from the marked blocks, run the advisory engine, return the ``semantic`` section.

    ``coverage_report`` is passed straight to ``assess`` for scoping (``excluded`` / ``whole_file_claims``,
    tolerated absent → empty scope). With no ``judge_fn`` wired, weak links are ``unjudgeable`` and no
    model is called. The returned dict is advisory on its face (``"advisory": True``) and is never read
    by the coverage gate — the caller attaches it after the status/exit are set.

    ``blocks`` narrows the pass to named selectors (see ``_select_blocks``). A selector that
    matches nothing is reported back under ``unmatched_selectors`` rather than silently
    yielding an empty pass: "no findings" and "you spelled it wrong" must not look alike.
    """
    definitions = _definition_map(ctx)
    pairings = _pairings_for_files(files, definitions, getattr(ctx, "project_root", None))
    pairings, unmatched = _select_blocks(pairings, blocks)
    result = eval_semantic.assess(pairings, judge_fn=judge_fn, report=coverage_report)
    return {
        **({"unmatched_selectors": unmatched} if unmatched else {}),
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


#: Cap on named requirement rows in the human report; the rest are summarised as "+N more".
_SEMANTIC_CAP = 20


# @cpt-begin:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-flagged
def flagged_lines(semantic: Dict[str, object]) -> List[str]:
    """The weak/wrong requirements, named one per line for the human report, so a reader can act on
    the result without opening ``--json``: a finding whose ``verdict`` is ``wrong`` or ``partial``
    (the set ``summary_line`` counts as "weak/wrong") named by ``block_id`` + ``path:line``. The
    more severe ``wrong`` findings are listed before ``partial`` ones, so when the list is capped
    the rows that survive are the worst, not merely the first the engine happened to emit.
    Presumed-covered blocks are the passing majority and are not listed; *unjudgeable* blocks are
    not listed either — that category is dominated by no-judge-wired noise (with no judge wired
    every block is unjudgeable) but also holds permanent pre-filter gaps; neither is an actionable
    requirement here, and their combined count stays on the summary line above. Capped, with a
    "+N more — see --json" continuation. Advisory: rendering only, never gates. A malformed/absent
    shape yields no lines, never raises — including a single wrong/partial record missing or
    mistyping any of ``block_id``/``path``/``start_line`` (a boolean ``start_line`` is rejected too,
    since ``bool`` subclasses ``int``), which is skipped rather than rendered as ``None:None``."""
    if not isinstance(semantic, dict) or semantic.get("error"):
        return []
    findings = semantic.get("findings")
    findings = findings if isinstance(findings, list) else []
    valid = [f for f in findings if isinstance(f, dict)
             and f.get("verdict") in (eval_semantic.SEM_WRONG, eval_semantic.SEM_PARTIAL)
             and isinstance(f.get("block_id"), str) and f["block_id"]
             and isinstance(f.get("path"), str) and f["path"]
             and isinstance(f.get("start_line"), int) and not isinstance(f.get("start_line"), bool)]
    # wrong before partial, stable within each — so a cap keeps the most severe rows, not the first.
    valid.sort(key=lambda f: 0 if f.get("verdict") == eval_semantic.SEM_WRONG else 1)
    out = [f"  {f['block_id']}  {f['verdict']}  {f['path']}:{f['start_line']}" for f in valid]
    if len(out) > _SEMANTIC_CAP:
        return out[:_SEMANTIC_CAP] + [f"  (+{len(out) - _SEMANTIC_CAP} more — see --json)"]
    return out
# @cpt-end:cpt-studio-algo-semantic-coverage-pass:p1:inst-scov-flagged
