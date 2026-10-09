"""Structural artifact-quality detectors (HYP-2720 T2).

Deterministic, stdlib-only, advisory-never-gates detectors over Project Markdown
artifacts. Each detector returns a list of :class:`ArtifactFinding` with
``kind="structural"`` and ``verdict=None`` — a review aid, never an auto-editor and
never a gate.

v1 ships exact / near-exact **duplication**: two artifact sections whose domain-word
sets overlap at or above a threshold. Paraphrase/meaning-level duplication is
embedding work routed elsewhere, out of scope here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Sequence, Set, Tuple

from .artifact_quality import ArtifactFinding, Locus
from .document import headings_by_line, read_text_safe
from .eval_semantic import tokenize

logger = logging.getLogger(__name__)

# @cpt-algo:cpt-studio-algo-artifact-quality-detectors:p1

# A section must carry at least this many domain tokens to be comparable — below it a
# fragment (a lone heading, a one-line note) is noise, not duplicable content.
_MIN_SECTION_TOKENS = 12
# Word-set overlap at or above this is reported as near-exact duplication. Strict by
# design: catch lifted paragraphs, not shared boilerplate headings. Tunable at the API.
_DUP_THRESHOLD = 0.9
# Evidence is one real source line, capped — still a substring of the source, so it
# stays grep-verifiable.
_EVIDENCE_CAP = 200
_MAX_ANCHOR = 120
# A real ATX heading: 1-6 '#' then whitespace or end of line. A line like '#tag' (no space)
# is content, not a heading, so it stays eligible as evidence.
_ATX_HEADING = re.compile(r"#{1,6}(\s|$)")
# A fenced code block: a line opening/closing ``` (mirrors document.py _CODE_FENCE_RE). Inside a
# fence, a ``# comment`` line is content, not a heading, so heading-skipping is suspended there.
_CODE_FENCE = re.compile(r"^\s*```")


@dataclass(frozen=True)
class _Section:
    """One heading-scoped slice of an artifact: where it is, its word set, a quote."""

    locus: Locus
    tokens: Set[str]
    evidence: str


# @cpt-begin:cpt-studio-algo-artifact-quality-detectors:p1:inst-aqd-locus
def _safe_resolve(path: Path) -> Path:
    """``path.resolve()``, or the path itself when resolution fails -- an advisory scan must not
    crash on one odd path. ``resolve()`` can raise ``OSError`` (an inaccessible component) or, on
    some CPython versions, ``RuntimeError`` (a symlink loop in non-strict mode); catch both. The
    path still degrades to its bare name in ``_rel_posix``, so nothing leaks."""
    try:
        return Path(path).resolve()
    except (OSError, RuntimeError):
        return Path(path)


def _rel_posix(path: Path, project_root: Optional[Path]) -> str:
    """A project-relative POSIX path (never absolute, so no local path leaks); the bare
    filename when the file is outside the root or cannot be resolved."""
    if project_root is None:
        return Path(path.name).as_posix()
    try:
        return _safe_resolve(path).relative_to(_safe_resolve(project_root)).as_posix()
    except ValueError:
        return Path(path.name).as_posix()


def _clean_anchor(stack: Sequence[str]) -> Optional[str]:
    """The deepest heading title as a Locus anchor, or None when it is empty, too long,
    or control-char-bearing — so the Locus constructor never rejects it."""
    title = stack[-1].strip() if stack else ""
    if not title or len(title) > _MAX_ANCHOR or any(ord(ch) < 0x20 for ch in title):
        return None
    return title


def _evidence_of(text: str) -> str:
    """The first non-empty, non-heading source line, capped — a grep-verifiable quote. Mirrors
    ``document.py``'s heading grammar: only an ATX heading (``#``..``######`` + space/EOL) that is
    **not inside a fenced code block** is a heading, so a ``#tag`` line and a ``# comment`` inside a
    ``` fence both stay eligible as content. Fence delimiters themselves are skipped."""
    in_fence = False
    for line in text.splitlines():
        if _CODE_FENCE.match(line):
            in_fence = not in_fence
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if not in_fence and _ATX_HEADING.match(stripped):
            continue
        return stripped[:_EVIDENCE_CAP]
    return ""
# @cpt-end:cpt-studio-algo-artifact-quality-detectors:p1:inst-aqd-locus


# @cpt-begin:cpt-studio-algo-artifact-quality-detectors:p1:inst-aqd-sections
def _iter_runs(lines: List[str], heads: List[List[str]]) -> Iterator[Tuple[Optional[str], int, str]]:
    """Yield ``(anchor, start_line_1based, text)`` for each maximal run of lines sharing
    one heading stack — the natural section granularity of the document."""
    n = len(lines)
    if not n:
        return
    start, current = 1, tuple(heads[1]) if len(heads) > 1 else ()
    for line_no in range(2, n + 1):
        stack = tuple(heads[line_no]) if line_no < len(heads) else ()
        if stack != current:
            yield _clean_anchor(current), start, "\n".join(lines[start - 1:line_no - 1])
            start, current = line_no, stack
    yield _clean_anchor(current), start, "\n".join(lines[start - 1:n])


def _sections(path: Path, project_root: Optional[Path], min_tokens: int) -> List[_Section]:
    """Split one artifact into comparable sections, dropping fragments below *min_tokens*."""
    lines = read_text_safe(path)
    if lines is None:
        return []
    rel = _rel_posix(path, project_root)
    heads = headings_by_line(path)
    out: List[_Section] = []
    for anchor, start, text in _iter_runs(lines, heads):
        token_set = tokenize(text)
        evidence = _evidence_of(text)
        if len(token_set) < min_tokens or not evidence:
            continue
        try:
            locus = Locus(rel, anchor=anchor, line=start)
        except ValueError as exc:
            # A path the model rejects (too long/deep, control chars). Surface it, then
            # skip — never let one pathological artifact crash an advisory scan.
            logger.debug("skipped a section whose locus the model rejected (%s)", type(exc).__name__)
            continue
        out.append(_Section(locus, token_set, evidence))
    return out
# @cpt-end:cpt-studio-algo-artifact-quality-detectors:p1:inst-aqd-sections


# @cpt-begin:cpt-studio-algo-artifact-quality-detectors:p1:inst-aqd-jaccard
def _jaccard(left: Set[str], right: Set[str]) -> float:
    """Word-set overlap in [0, 1]: shared tokens over the union. 0 when either is empty."""
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
# @cpt-end:cpt-studio-algo-artifact-quality-detectors:p1:inst-aqd-jaccard


# @cpt-begin:cpt-studio-algo-artifact-quality-detectors:p1:inst-aqd-emit
def _dup_finding(primary: _Section, related: _Section, score: float) -> ArtifactFinding:
    """A structural ``duplication`` finding naming both sites. ``evidence`` is a quote from
    the **primary** section (the two overlap by word set, not necessarily line for line), so
    it is grep-verifiable there; the finding names ``related`` for the reviewer to compare."""
    return ArtifactFinding(
        detector="duplication",
        severity="warn",
        kind="structural",
        message=f"Near-exact duplicate content ({score:.0%} word overlap) with another section.",
        primary=primary.locus,
        related=related.locus,
        evidence=primary.evidence,
        suggested_action="Keep one source of truth and reference it, or remove the duplicate.",
    )
# @cpt-end:cpt-studio-algo-artifact-quality-detectors:p1:inst-aqd-emit


# @cpt-begin:cpt-studio-algo-artifact-quality-detectors:p1:inst-aqd-compare
def _pair_finding(primary: _Section, related: _Section, threshold: float) -> Optional[ArtifactFinding]:
    """One finding for a section pair, or None when the pair shares a locus, is pruned by
    the size ratio, or scores below *threshold*."""
    if related.locus == primary.locus:  # distinct files can still share a bare-name locus
        return None
    smaller, larger = sorted((len(primary.tokens), len(related.tokens)))
    if smaller < threshold * larger:  # Jaccard <= smaller/larger: prune cheaply
        return None
    score = _jaccard(primary.tokens, related.tokens)
    return _dup_finding(primary, related, score) if score >= threshold else None


def detect_exact_duplication(
    artifacts_to_scan: Sequence[Tuple[Path, str]],
    project_root: Optional[Path],
    *,
    threshold: float = _DUP_THRESHOLD,
    min_tokens: int = _MIN_SECTION_TOKENS,
) -> List[ArtifactFinding]:
    """Exact / near-exact duplication across artifact sections.

    Compares every pair of distinct sections by word-set :func:`_jaccard`; a pair at or
    above *threshold* is reported once, naming both loci and a grep-verifiable quote.
    Deterministic: sections are ordered, findings follow that order. An artifact listed
    twice is scanned once, and a pair sharing one locus is never reported — a finding
    cannot relate a section to itself. Advisory only — ``severity`` never reaches ``error``
    and no artifact is rewritten.
    """
    sections: List[_Section] = []
    seen: Set[Path] = set()
    for path, _kind in artifacts_to_scan:
        resolved = _safe_resolve(path)
        if resolved in seen:  # the same artifact listed twice would duplicate against itself
            continue
        seen.add(resolved)
        sections.extend(_sections(path, project_root, min_tokens))
    sections.sort(key=lambda s: (s.locus.artifact_path, s.locus.line or 0, s.locus.anchor or ""))

    findings: List[ArtifactFinding] = []
    for index, primary in enumerate(sections):
        for related in sections[index + 1:]:
            finding = _pair_finding(primary, related, threshold)
            if finding is not None:
                findings.append(finding)
    return findings
# @cpt-end:cpt-studio-algo-artifact-quality-detectors:p1:inst-aqd-compare
