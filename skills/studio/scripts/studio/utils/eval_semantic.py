"""Semantic coverage — *does a marked block implement the requirement it cites?*

Structural ``spec-coverage`` scores marker **density**: a file can read 100% covered while the
code inside its markers does the wrong thing. This engine adds the layer density cannot reach —
**code-vs-requirement correctness** — and it does so honestly:

* **Rank first, judge last.** A deterministic, stdlib-only token-overlap pre-filter scores every
  marked block against its requirement text and surfaces the **weak links** (low overlap). Only
  those go to a model, so a large repo triggers **zero model calls per block**. The pre-filter is a
  *budget heuristic*, not a correctness oracle: strong overlap → ``presumed_covered`` buys a block
  out of a model call, it never proves the block correct. Lexical overlap is gameable, so
  ``presumed_covered`` is not evidence of correctness — only a judged verdict is.
* **Seam, not transport.** Like the rules-judge, the model call is a pluggable ``SemanticJudgeFn``
  supplied out-of-tree; with none wired the weak links are ``UNJUDGEABLE`` (never a false verdict)
  and nothing gates. This module contains no model client.
* **Advisory, never gates.** A verdict here never touches an exit code (enforced at integration).
* **Honest coverage.** Blocks with no retrievable requirement, or too little text to compare, are
  reported ``UNJUDGEABLE`` — never a silent "covered". The report states what it could not judge.
* **Scoped by the frozen coverage contract.** Files a human declared ``excluded`` are skipped;
  files flagged ``whole_file_claims`` (scope-only) are prioritised — that is where a green
  structural number most plausibly hides wrong code.

@cpt-algo:cpt-studio-algo-eval-semantic:p1
"""
# @cpt-begin:cpt-studio-algo-eval-semantic:p1:inst-semantic-imports
from __future__ import annotations

import io
import logging
import re
import tokenize as _tokenize   # aliased: this module defines its own public ``tokenize`` word-splitter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Sequence, Set, Tuple, runtime_checkable

from .document import get_content_scoped
from .manifest import load_toml_file

logger = logging.getLogger(__name__)

#: The three model verdicts, plus the honest "could not compare" outcome the engine owns.
SEM_COVERED = "covered"
SEM_PARTIAL = "partial"
SEM_WRONG = "wrong"
SEM_UNJUDGEABLE = "unjudgeable"
_MODEL_VERDICTS = frozenset({SEM_COVERED, SEM_PARTIAL, SEM_WRONG})

#: Schema version stamped on ``SemanticReport`` / ``SemanticCalibration`` so a coverage-report
#: consumer can detect a shape change. Bump on any breaking field change.
SEMANTIC_SCHEMA_VERSION = 1

#: Provisional calibration constants — a comparison needs at least this many domain tokens on each
#: side, and a block scoring below the threshold is a weak link. Named here (not buried in logic)
#: so calibration on our own corpus can retune them. They are **not yet corpus-calibrated** — their
#: empirical basis is future work (see the design note); these are conservative defaults.
_MIN_TOKENS = 4
_WEAK_LINK_THRESHOLD = 0.30
#: Per-field cap on the requirement/code interpolated into the judge prompt, so a huge block or
#: requirement can never produce an unbounded prompt. The structured request fields stay full (for
#: the evidence guard and a host that builds its own prompt); only the prompt string is bounded.
_PROMPT_FIELD_CAP = 2000

#: Syntax words that are not evidence a requirement was implemented — dropped before overlap so a
#: score reflects domain vocabulary, not boilerplate shared by every block.
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "not", "is", "are", "be", "to", "of", "in", "on", "for",
    "with", "as", "if", "else", "elif", "return", "def", "class", "self", "import", "from",
    "none", "true", "false", "pass", "raise", "try", "except", "this", "that", "it",
})
#: Split on Unicode non-word runs *and* underscore, so accented / non-Latin terms (Gebühr, Cyrillic)
#: stay whole instead of fragmenting to empty — an ASCII-only class silently deflated the pre-filter
#: on multilingual corpora and could report a real block UNJUDGEABLE. Transliteration mismatches
#: (gebuehr vs Gebühr) remain inherent to lexical overlap.
_TOKEN_SPLIT = re.compile(r"[\W_]+")
_CAMEL_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
# @cpt-end:cpt-studio-algo-eval-semantic:p1:inst-semantic-imports


# @cpt-begin:cpt-studio-algo-eval-semantic:p1:inst-semantic-datamodel
@dataclass(frozen=True)
class Pairing:
    """One marked code block paired with the requirement text it cites. The engine's unit of work.

    ``requirement`` is ``None`` when no scoped requirement could be retrieved for the block's id —
    an honest "unjudgeable", never treated as an empty requirement the code trivially satisfies.
    """

    block_id: str
    inst: str
    path: str
    start_line: int
    code: str
    requirement: Optional[str]


@dataclass(frozen=True)
class Ranked:
    """A pairing scored by the deterministic pre-filter."""

    pairing: Pairing
    score: Optional[float]        # overlap in [0, 1]; None when unjudgeable (below the floor)
    weak_link: bool               # scored and below the weak-link threshold → send to the judge
    reason: str                   # why unjudgeable / why a weak link (human-readable)
    forced: bool = False          # judged because it is a whole_file_claim, regardless of overlap


@dataclass(frozen=True)
class SemanticRequest:
    """The deterministic input handed to a ``SemanticJudgeFn`` — pure, no model call."""

    block_id: str
    requirement: str
    code: str
    prompt: str


@dataclass(frozen=True)
class SemanticReply:
    """A model's structured answer, parsed back by the engine."""

    verdict: str                  # covered | partial | wrong
    rationale: str = ""
    evidence_quote: str = ""      # a substring of the code the verdict rests on (grep-verified)


@runtime_checkable
class SemanticJudgeFn(Protocol):  # pylint: disable=too-few-public-methods
    """The seam the host/agent supplies: turn a ``SemanticRequest`` into a ``SemanticReply``.

    Never implemented here with a real model — that lives out-of-tree. Tests and calibration use
    a deterministic stub.

    **Latency is the implementer's contract.** The engine calls this *synchronously* and does not
    bound its runtime: a judge that blocks (e.g. an un-timed network call) blocks ``assess`` /
    ``calibrate`` for exactly as long as it runs. An implementation that can hang MUST enforce its
    own timeout and raise on expiry — a raise degrades that one finding to UNJUDGEABLE (never sinks
    the run), whereas a hang has no in-engine recourse.
    """

    def __call__(self, request: SemanticRequest) -> SemanticReply:
        """Return the model's verdict on ``request``."""  # pragma: no cover
# @cpt-end:cpt-studio-algo-eval-semantic:p1:inst-semantic-datamodel


# @cpt-begin:cpt-studio-algo-eval-semantic:p1:inst-semantic-blank
def _blank(code: str, spans: Sequence[Tuple[int, int]]) -> str:
    """Replace each ``[start, end)`` character span with spaces, preserving newlines and every other
    character's position — so a verbatim quote of the untouched text still matches as a substring."""
    if not spans:
        return code
    chars = list(code)
    for start, end in spans:
        for i in range(start, min(end, len(chars))):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)
# @cpt-end:cpt-studio-algo-eval-semantic:p1:inst-semantic-blank


# @cpt-begin:cpt-studio-algo-eval-semantic:p1:inst-semantic-strip
#: Fallback-only: strip ``#`` comment tails when a block will not tokenize (a mid-file fragment).
#: The grammar-aware ``tokenize`` pass below is the real lexer; Python's comments and string literals
#: are mutually recursive (``#`` lives in strings, ``'''`` lives in comments), so no sequence of
#: independent regexes can strip them correctly — only a single left-to-right scan can.
_LINE_COMMENT = re.compile(r"#[^\n]*")
#: Token types a string can follow to be a *statement-leading* (docstring-like) string rather than an
#: inline value — a suite start (INDENT), a statement break (NEWLINE), or a block close (DEDENT, which
#: ends an inner suite so the next token opens a fresh statement). Such prose is blanked from the
#: evidence view; an inline string (after ``=``, ``(``, …) never follows one of these.
_STATEMENT_START = frozenset({_tokenize.NEWLINE, _tokenize.INDENT, _tokenize.DEDENT})
#: PEP 701 (Python 3.12+) tokenizes an f-string as FSTRING_START/MIDDLE/END around its interior
#: expressions, not a single STRING token. FSTRING_MIDDLE carries the literal *text* (prose); the
#: interior expressions are ordinary tokens (kept). ``None`` on < 3.12, where f-strings are STRING.
_FSTRING_MIDDLE = getattr(_tokenize, "FSTRING_MIDDLE", None)


def _code_views(code: str) -> Tuple[str, str, bool]:
    """One ``tokenize`` pass → ``(overlap_view, evidence_view, lexed)``; comment/string spans blanked in place.

    * ``overlap_view`` blanks comments **and every string literal**, so prose (a comment, docstring, or
      string echoing the requirement) can never inflate the overlap score and mask wrong code.
    * ``evidence_view`` blanks comments **and docstrings** but keeps inline string literals, so a quote
      of a real string the code executes (an error message, SQL, a regex) is valid evidence while a
      quote lifted only from a comment or docstring is not. A docstring is a statement-leading string.
    * ``lexed`` is ``False`` when the block did not tokenize (an indentation-broken or unterminated
      fragment). The fallback can only comment-strip, so a string literal would survive into the
      overlap view — ``overlap_score`` therefore treats ``lexed=False`` as **unjudgeable** (returns
      ``None``) rather than risk a prose-inflated ``presumed_covered``. Never raises.

    Grammar-aware, so ``#`` inside a string and ``'''`` inside a comment are handled correctly, and an
    f-string's literal text is blanked from overlap on Python 3.12+ (PEP 701) where it is no longer a
    single STRING token.
    """
    # Split on ``\n`` only, matching ``io.StringIO(...).readline`` below — NOT ``str.splitlines()``,
    # which also breaks on form-feed / NEL / LS / PS and would insert phantom lines the tokenizer's
    # row numbering lacks, desyncing every later span. The trailing surplus entry is never indexed.
    line_start = [0]
    for segment in code.split("\n"):
        line_start.append(line_start[-1] + len(segment) + 1)
    all_strings_and_comments: List[Tuple[int, int]] = []   # overlap view blanks these
    comments_and_docstrings: List[Tuple[int, int]] = []    # evidence view blanks these
    prev = _tokenize.NEWLINE                                # file start behaves like a statement break
    try:
        for tok in _tokenize.generate_tokens(io.StringIO(code).readline):
            span = (line_start[tok.start[0] - 1] + tok.start[1],
                    line_start[tok.end[0] - 1] + tok.end[1])
            if tok.type == _tokenize.COMMENT:
                all_strings_and_comments.append(span)
                comments_and_docstrings.append(span)
            elif tok.type == _tokenize.STRING:
                all_strings_and_comments.append(span)
                if prev in _STATEMENT_START:               # a statement-leading string = docstring
                    comments_and_docstrings.append(span)
            elif tok.type == _FSTRING_MIDDLE:              # PEP 701 f-string literal text (Py 3.12+)
                all_strings_and_comments.append(span)      # blank the prose from overlap; the interior
                                                           # expressions are separate tokens, kept. An
                                                           # f-string is an inline value → kept for evidence.
            if tok.type not in (_tokenize.NL, _tokenize.COMMENT):
                prev = tok.type
    except (_tokenize.TokenError, SyntaxError, ValueError):   # IndentationError ⊂ SyntaxError
        stripped = _LINE_COMMENT.sub(" ", code)               # best-effort: comments only (strings survive)
        return stripped, stripped, False                      # lexed=False → caller treats as unjudgeable
    return _blank(code, all_strings_and_comments), _blank(code, comments_and_docstrings), True
# @cpt-end:cpt-studio-algo-eval-semantic:p1:inst-semantic-strip


# @cpt-begin:cpt-studio-algo-eval-semantic:p1:inst-semantic-tokenize
def tokenize(text: str) -> Set[str]:
    """Domain tokens of ``text``: split on Unicode word boundaries *and* camelCase, casefold, drop
    stopwords and 1-char fragments. Deterministic — the basis of every overlap score."""
    out: Set[str] = set()
    for raw in _TOKEN_SPLIT.split(text):
        for piece in _CAMEL_SPLIT.split(raw):
            token = piece.casefold()
            if len(token) > 1 and token not in _STOPWORDS:
                out.add(token)
    return out


def overlap_score(code: str, requirement: str) -> Optional[float]:
    """Fraction of the requirement's domain tokens present in the code, in [0, 1].

    An **advisory budget heuristic**, never a correctness proof: a strong score buys a block out of
    a model call, it does not show the block is correct. Comments/docstrings/strings are stripped from
    the code first so *prose* echoing the requirement cannot inflate the score. A residual gap remains
    and is inherent to any lexical measure: executable identifiers named after the requirement can push
    the score **above** the threshold, so the block is ``presumed_covered`` and never judged — the
    judge (which only sees weak links) does not close this case; only a semantic model would.
    Scored against the (smaller) requirement set — "does the code cover what the requirement asks",
    not the reverse. Returns ``None`` when either side has fewer than ``_MIN_TOKENS`` domain tokens
    (too little to compare honestly) **or** the block did not tokenize (the fallback can't strip
    strings, so scoring it could mask wrong code) — unjudgeable, not zero.
    """
    overlap_view, _evidence, lexed = _code_views(code)
    if not lexed:                          # could not lex → cannot honestly score; never presumed_covered
        return None
    code_tokens = tokenize(overlap_view)
    req_tokens = tokenize(requirement)
    if len(code_tokens) < _MIN_TOKENS or len(req_tokens) < _MIN_TOKENS:
        return None
    return len(code_tokens & req_tokens) / len(req_tokens)
# @cpt-end:cpt-studio-algo-eval-semantic:p1:inst-semantic-tokenize


# @cpt-begin:cpt-studio-algo-eval-semantic:p1:inst-semantic-prefilter
def _rank_one(pairing: Pairing, priority: Set[str]) -> Ranked:
    """Score a single pairing → ``Ranked``. Unjudgeable when no requirement or below the floor.

    A pairing in a ``priority`` (``whole_file_claims``) file is **always** a weak link regardless of
    overlap: its structural coverage rests on a whole-file scope marker, so its lexical overlap is
    untrustworthy (comments/leftover text inflate it) and it is exactly where wrong code hides — a
    high score there must not buy a free pass. This is what "prioritise" means: always judge it.
    """
    if not pairing.requirement:
        return Ranked(pairing, None, False, "no retrievable requirement for this id")
    score = overlap_score(pairing.code, pairing.requirement)
    if score is None:
        return Ranked(pairing, None, False,
                      "too little text to compare (below token floor) or the block did not tokenize")
    if _norm_path(pairing.path) in priority:
        return Ranked(pairing, score, True,
                      f"whole-file claim — always judged (overlap {score:.2f})", forced=True)
    if score < _WEAK_LINK_THRESHOLD:
        return Ranked(pairing, score, True, f"low overlap {score:.2f} < {_WEAK_LINK_THRESHOLD}")
    return Ranked(pairing, score, False, f"overlap {score:.2f}")


def rank_pairings(pairings: Sequence[Pairing], priority_paths: Sequence[str] = ()) -> List[Ranked]:
    """Rank every pairing weakest-first so the judge budget is spent where it matters.

    A ``whole_file_claims`` file is always judged (see ``_rank_one``). Sort key: weak links before
    strong, then blocks in a ``priority_paths`` file ahead of the rest, then by ascending overlap.
    Unjudgeable blocks sort last — they carry no signal and are reported separately as coverage gaps.
    """
    priority = {_norm_path(p) for p in priority_paths}
    ranked = [_rank_one(p, priority) for p in pairings]

    def key(item: Ranked) -> Tuple[int, int, float]:
        if item.weak_link:
            group = 0                       # weak links first — where the judge budget goes
        elif item.score is None:
            group = 2                       # unjudgeable last — no signal
        else:
            group = 1                       # strong overlap in between
        return (group,
                0 if _norm_path(item.pairing.path) in priority else 1,
                item.score if item.score is not None else 1.0)

    return sorted(ranked, key=key)
# @cpt-end:cpt-studio-algo-eval-semantic:p1:inst-semantic-prefilter


# @cpt-begin:cpt-studio-algo-eval-semantic:p1:inst-semantic-scope
@dataclass(frozen=True)
class CoverageScope:
    """Scoping read from the frozen coverage-report contract (excluded / whole-file-claim files)."""

    excluded: Set[str] = field(default_factory=set)      # human-declared, skip entirely
    prioritised: List[str] = field(default_factory=list)  # whole_file_claims, in the producer's order


def _norm_path(path: str) -> str:
    """Normalise a path for scope comparison: back- to forward-slashes and a stripped leading
    ``./``, so a report path and a pairing path that differ only by separator style still match.
    Matching stays **case-sensitive** — case-folding would wrongly merge distinct files on a
    case-sensitive filesystem (the common one for this codebase)."""
    norm = path.replace("\\", "/")
    return norm[2:] if norm.startswith("./") else norm


def _paths_from(report: Dict[str, object], key: str) -> List[str]:
    """Extract normalised ``path`` strings from ``report[key]`` (a list of dicts), tolerating a bad shape."""
    rows = report.get(key)
    if not isinstance(rows, list):
        return []
    return [_norm_path(row["path"]) for row in rows
            if isinstance(row, dict) and isinstance(row.get("path"), str)]


def coverage_scope(report: Optional[Dict[str, object]]) -> CoverageScope:
    """Read ``excluded[]`` / ``whole_file_claims[]`` from a coverage report, degrading to empty.

    The producer (the coverage-report reporting change) may not have emitted these yet; a report
    without them simply yields an empty scope — skip nothing, prioritise nothing — never an error.
    """
    if not isinstance(report, dict):
        return CoverageScope()
    return CoverageScope(excluded=set(_paths_from(report, "excluded")),
                         prioritised=_paths_from(report, "whole_file_claims"))
# @cpt-end:cpt-studio-algo-eval-semantic:p1:inst-semantic-scope


# @cpt-begin:cpt-studio-algo-eval-semantic:p1:inst-semantic-prompt
def _capped(text: str) -> str:
    """Trim ``text`` to ``_PROMPT_FIELD_CAP``, marking a cut so the judge sees it was truncated."""
    return text if len(text) <= _PROMPT_FIELD_CAP else text[:_PROMPT_FIELD_CAP].rstrip() + "\n[…truncated]"


def build_semantic_request(ranked: Ranked) -> SemanticRequest:
    """Assemble the deterministic judge prompt for one weak link — pure, no model call. The
    requirement and code are capped in the prompt so it stays bounded; the returned request keeps
    the full fields for the evidence guard and any host that builds its own prompt."""
    pairing = ranked.pairing
    requirement = pairing.requirement or ""
    prompt = (
        "You are judging whether a block of code implements the requirement it cites. This is an "
        "advisory judgement; it never gates a build.\n\n"
        f"REQUIREMENT (id {pairing.block_id}):\n{_capped(requirement)}\n\n"
        f"CODE ({pairing.path}:{pairing.start_line}):\n{_capped(pairing.code)}\n\n"
        "Answer with a verdict of 'covered', 'partial', or 'wrong', a one-line rationale, and an "
        "evidence_quote copied verbatim from the CODE above that your verdict rests on.")
    return SemanticRequest(pairing.block_id, requirement, pairing.code, prompt)


def _reply_to_verdict(reply: object) -> str:
    """Map a reply to a verdict; anything unrecognised — ``None``, a bad object, a **non-string**
    ``verdict`` (e.g. an int), or an unknown string — is UNJUDGEABLE. A first line of defence: it
    never raises on a *missing* or non-string attribute; ``_judge_one`` additionally wraps this call
    so a reply whose attribute *access* raises degrades to UNJUDGEABLE instead of sinking the run."""
    verdict = getattr(reply, "verdict", "")
    if not isinstance(verdict, str):
        return SEM_UNJUDGEABLE
    verdict = verdict.strip().lower()
    return verdict if verdict in _MODEL_VERDICTS else SEM_UNJUDGEABLE


# @cpt-end:cpt-studio-algo-eval-semantic:p1:inst-semantic-prompt


# @cpt-begin:cpt-studio-algo-eval-semantic:p1:inst-semantic-evidence
def evidence_present(code: str, quote: str) -> bool:
    """Hallucination guard: the model's ``evidence_quote`` must actually occur in the *executable*
    code.

    The haystack is the ``_code_views`` evidence view — comments and docstrings removed, **inline
    string literals kept** — so a quote lifted only from a comment or docstring (e.g. a stale comment
    describing intended-but-unimplemented behaviour) is **not** accepted, while a quote of a real
    string the code executes (an error message, SQL, a regex — often the exact evidence) still is.
    Whitespace-normalised so trivial reformatting does not fail a genuine quote; an empty quote is
    not evidence. A deterministic check sitting *under* the non-deterministic judge.
    """
    needle = " ".join(quote.split())
    haystack = " ".join(_code_views(code)[1].split())
    return bool(needle) and needle in haystack
# @cpt-end:cpt-studio-algo-eval-semantic:p1:inst-semantic-evidence


# @cpt-begin:cpt-studio-algo-eval-semantic:p1:inst-semantic-finding
@dataclass(frozen=True)
class SemanticFinding:
    """One judged weak link — the advisory unit the report carries."""

    block_id: str
    path: str
    start_line: int
    verdict: str                  # covered | partial | wrong | unjudgeable
    rationale: str
    evidence_ok: bool             # did evidence_present() confirm the quote?
    forced: bool = False          # judged because its file is a whole_file_claim, not by low overlap


def judge_weak_links(ranked: Sequence[Ranked],
                     judge_fn: Optional[SemanticJudgeFn]) -> List[SemanticFinding]:
    """Judge only the weak links. With no ``judge_fn`` every weak link is UNJUDGEABLE (advisory).

    A judge that raises or returns a malformed reply degrades that one finding to UNJUDGEABLE —
    it never sinks the assessment. Each verdict carries an evidence check (the hallucination
    guard); a quote absent from the code sets ``evidence_ok=False`` rather than being trusted.
    """
    findings: List[SemanticFinding] = []
    for item in ranked:
        if not item.weak_link:
            continue
        findings.append(_judge_one(item, judge_fn))
    return findings


def _judge_one(item: Ranked, judge_fn: Optional[SemanticJudgeFn]) -> SemanticFinding:
    """Judge a single weak link defensively → a ``SemanticFinding``."""
    pairing = item.pairing
    if judge_fn is None:
        return SemanticFinding(pairing.block_id, pairing.path, pairing.start_line,
                               SEM_UNJUDGEABLE, "no judge model wired (advisory)", False, item.forced)
    request = build_semantic_request(item)
    try:
        reply = judge_fn(request)
        # Marshal *inside* the try: the call is not the only thing that can raise. ``reply`` is
        # duck-typed ``object``, so a lazily-parsed proxy whose ``.verdict``/``.evidence_quote`` is
        # a property can raise any exception on access (getattr's default only swallows
        # AttributeError). Reading here degrades that one finding to UNJUDGEABLE rather than
        # aborting judge_weak_links/assess — and calibrate, which routes through here too.
        verdict = _reply_to_verdict(reply)
        quote = getattr(reply, "evidence_quote", "")
        rationale = getattr(reply, "rationale", "")
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("semantic: judge_fn raised on %s: %s", pairing.block_id, exc)
        return SemanticFinding(pairing.block_id, pairing.path, pairing.start_line,
                               SEM_UNJUDGEABLE, f"judge_fn raised: {exc}", False, item.forced)
    # A non-string evidence_quote/rationale (a host may return an int or a list) is coerced, not
    # trusted. An unrecognised verdict names its own cause rather than echoing the model's text.
    quote = quote if isinstance(quote, str) else ""
    rationale = rationale if isinstance(rationale, str) else ""
    if verdict == SEM_UNJUDGEABLE:
        rationale = "judge returned an unrecognized verdict"
    return SemanticFinding(pairing.block_id, pairing.path, pairing.start_line, verdict,
                           rationale, evidence_present(pairing.code, quote), item.forced)
# @cpt-end:cpt-studio-algo-eval-semantic:p1:inst-semantic-finding


# @cpt-begin:cpt-studio-algo-eval-semantic:p1:inst-semantic-stub
def reference_stub_judge(request: SemanticRequest) -> SemanticReply:
    """A deterministic overlap ``SemanticJudgeFn`` — **not a real model.**

    Ships so tests and calibration exercise the machinery with no model wired. It re-scores the
    request's own overlap and buckets it (high→covered, mid→partial, low→wrong), quoting the code
    line with the most requirement tokens so the evidence guard has something real to verify.
    A real judge_fn is supplied out-of-tree and replaces it.

    **Not an independent oracle.** It buckets the *same* ``overlap_score`` against the *same*
    ``_WEAK_LINK_THRESHOLD`` the pre-filter already used to flag the pairing, so it is structurally
    correlated with the pre-filter, not an independent check of it. Calibrating against this stub
    measures the wiring, not judge quality — meaningful accuracy/consistency need a real judge.
    """
    score = overlap_score(request.code, request.requirement) or 0.0
    if score >= _WEAK_LINK_THRESHOLD:
        verdict = SEM_COVERED
    elif score >= _WEAK_LINK_THRESHOLD / 2:
        verdict = SEM_PARTIAL
    else:
        verdict = SEM_WRONG
    return SemanticReply(verdict, f"reference stub: overlap {score:.2f}",
                         _best_evidence_line(request))


def _best_evidence_line(request: SemanticRequest) -> str:
    """The *executable* code line sharing the most tokens with the requirement — a real, verifiable
    quote. Selected over the ``_code_views`` evidence view (comments/docstrings blanked, strings kept)
    — the same view ``evidence_present`` matches against — so the quote it returns is one the guard
    will accept, even on a block whose comment echoes the requirement."""
    req_tokens = tokenize(request.requirement)
    # Split on ``\n`` only, consistent with how ``_code_views`` defines "one line" — ``str.splitlines()``
    # would fragment a line at a form-feed/NEL/etc. and could pick a truncated fragment as evidence.
    lines = [line for line in _code_views(request.code)[1].split("\n") if line.strip()]
    if not lines:
        return ""
    return max(lines, key=lambda line: len(tokenize(line) & req_tokens)).strip()
# @cpt-end:cpt-studio-algo-eval-semantic:p1:inst-semantic-stub


# @cpt-begin:cpt-studio-algo-eval-semantic:p1:inst-semantic-gap
@dataclass(frozen=True)
class SemanticGap:
    """One block the engine could not judge — a coverage gap, located like a ``SemanticFinding``.

    Carries ``start_line`` (unlike a bare dict) so a coverage-report consumer can point at every gap
    precisely, with a shape consistent with ``findings``.
    """

    block_id: str
    path: str
    start_line: int
    reason: str                   # no requirement / below the token floor / judge could not verdict
# @cpt-end:cpt-studio-algo-eval-semantic:p1:inst-semantic-gap


# @cpt-begin:cpt-studio-algo-eval-semantic:p1:inst-semantic-report
@dataclass
class SemanticReport:
    """The advisory result of assessing a set of pairings. Never carries a gate signal.

    Every pairing is accounted for: ``skipped_excluded`` (files a human excluded, dropped before
    ranking) + ``assessed`` (weak links that got a real covered/partial/wrong verdict) +
    ``presumed_covered`` (strong overlap, not judged) + ``len(unjudgeable)`` (coverage gaps — no
    requirement, below the token floor, or the judge could not produce a verdict). So a small
    ``assessed`` can never be mistaken for "only this many blocks existed".

    "Nothing to assess" and "could not assess" are distinguishable: an **empty** pairing set yields
    an all-zero report with an **empty** ``unjudgeable``, whereas a resolution failure (no
    requirement / below floor) yields ``unjudgeable`` **entries** — never a silent all-zero.
    """

    assessed: int                          # weak links that got a real covered/partial/wrong verdict
    presumed_covered: int                  # strong overlap → not judged; a budget heuristic, NOT a
                                           # correctness claim (lexical overlap is gameable)
    unjudgeable: List[SemanticGap]         # coverage gaps: no requirement / below floor / judge unjudgeable
    findings: List[SemanticFinding] = field(default_factory=list)   # only the real-verdict findings
    skipped_excluded: int = 0              # blocks in human-excluded files, dropped before ranking
    schema_version: int = SEMANTIC_SCHEMA_VERSION   # report-shape version for the coverage consumer


def assess(pairings: Sequence[Pairing], judge_fn: Optional[SemanticJudgeFn] = None,
           report: Optional[Dict[str, object]] = None) -> SemanticReport:
    """Assess ``pairings`` end-to-end: scope → rank → judge weak links → honest report.

    Advisory throughout. Files in the coverage report's ``excluded`` set are dropped before
    ranking (human-declared, skip safely); every block with no requirement or too little text is
    listed in ``unjudgeable`` rather than silently counted covered. ``excluded`` takes precedence
    over ``whole_file_claims``: a path in both is dropped here, before ranking ever sees it — the
    human exclusion is the override.
    """
    scope = coverage_scope(report)
    in_scope = [p for p in pairings if _norm_path(p.path) not in scope.excluded]
    ranked = rank_pairings(in_scope, scope.prioritised)
    presumed = sum(1 for r in ranked if not r.weak_link and r.score is not None)
    all_findings = judge_weak_links(ranked, judge_fn)
    # A weak link the judge could not verdict (no judge wired / crash / malformed) is a coverage
    # gap, not a "judged" result — it joins the unjudgeable list, not the findings.
    findings = [f for f in all_findings if f.verdict in _MODEL_VERDICTS]
    unjudgeable = [SemanticGap(r.pairing.block_id, r.pairing.path, r.pairing.start_line, r.reason)
                   for r in ranked if r.score is None]
    unjudgeable += [SemanticGap(f.block_id, f.path, f.start_line, f.rationale or "judge unjudgeable")
                    for f in all_findings if f.verdict == SEM_UNJUDGEABLE]
    return SemanticReport(assessed=len(findings), presumed_covered=presumed,
                          unjudgeable=unjudgeable, findings=findings,
                          skipped_excluded=len(pairings) - len(in_scope))
# @cpt-end:cpt-studio-algo-eval-semantic:p1:inst-semantic-report


# @cpt-begin:cpt-studio-algo-eval-semantic:p1:inst-semantic-resolve
def resolve_requirement(doc_path: Path, block_id: str) -> Optional[str]:
    """Fetch the requirement text scoped to ``block_id`` from a feature doc, or ``None``.

    A thin adapter over ``get_content_scoped``; a ``None`` (id absent / doc unreadable) is the
    honest "unjudgeable" signal the pre-filter propagates, never a crash. The id→doc mapping that
    drives this at scale is the reporting-integration follow-up; the engine only needs the lookup.

    **Security — caller contract.** ``doc_path`` is opened as given; ``block_id`` never selects a
    file, so there is no traversal via the id. The caller owns the path's trust boundary: pass a
    path already resolved and confirmed to be within the intended project root. The engine has no
    project root of its own to check against, so it cannot enforce containment here.
    """
    scoped = get_content_scoped(doc_path, id_value=block_id)
    return scoped[0] if scoped else None
# @cpt-end:cpt-studio-algo-eval-semantic:p1:inst-semantic-resolve


# @cpt-begin:cpt-studio-algo-eval-semantic:p1:inst-semantic-gold
@dataclass
class SemanticGold:
    """A human label for one pairing — the ground truth calibration compares against."""

    verdict: str                  # covered | partial | wrong
    rationale: str = ""


def load_gold(gold_path: Optional[Path]) -> Optional[SemanticGold]:
    """Read a ``[gold]`` verdict label, or ``None`` when absent/malformed. Never raises.

    A missing or unreadable gold file means the pairing is not gold-backed, so its verdict is
    unvalidated advisory rather than a crash.

    **Security — caller contract.** ``gold_path`` is opened as given. The caller owns the path's
    trust boundary: pass a path already resolved and confirmed within the intended project root. The
    engine has no project root of its own to check containment against, so it cannot enforce it here.
    """
    if gold_path is None:
        return None
    data = load_toml_file(gold_path)   # shared tolerant reader: logs + returns None on OSError/parse
    if data is None:
        # Case B — the reader returned None for *any* reason. Surface both sub-cases (the reader is
        # silent on a missing file, and logs only the low-level detail on a read/parse failure): a
        # present-but-unreadable gold file is an unexpected misconfiguration, not "no gold provided".
        if gold_path.is_file():
            logger.warning("semantic: gold file present but unreadable/unparseable: %s", gold_path)
        else:
            logger.warning("semantic: gold file not found: %s", gold_path)
        return None
    section = data.get("gold")
    verdict = section.get("verdict") if isinstance(section, dict) else None
    # isinstance-guard before the frozenset test: a TOML array/table verdict is unhashable and would
    # raise ``TypeError: unhashable type`` from ``in`` — breaking the "never raises" contract.
    if not isinstance(verdict, str) or verdict not in _MODEL_VERDICTS:
        logger.warning("semantic: gold needs [gold].verdict in covered|partial|wrong: %s", gold_path)
        return None
    return SemanticGold(verdict=verdict, rationale=str(section.get("rationale", "")))
# @cpt-end:cpt-studio-algo-eval-semantic:p1:inst-semantic-gold


# @cpt-begin:cpt-studio-algo-eval-semantic:p1:inst-semantic-calibrate
@dataclass
class SemanticCalibration:
    """The judge's measured quality over gold-backed pairings."""

    accuracy: Optional[float]     # fraction whose majority matches the label, over cases with a majority
    consistency: Optional[float]  # majority verdict's mean share of surviving runs, over cases with ≥2
    covered: List[str]            # block ids that carry a gold label
    runs_per_scenario: int
    per_case: List[Dict[str, object]] = field(default_factory=list)
    excluded: List[str] = field(default_factory=list)   # unscoreable pairing / judge crash — not a mismatch
    judge: str = ""               # best-effort identity of the judge_fn these numbers describe
    schema_version: int = SEMANTIC_SCHEMA_VERSION   # calibration-shape version for the consumer


def _majority(verdicts: Sequence[str]) -> Tuple[str, int]:
    """The most common verdict and its count. Ties resolve by sorted verdict name (canonical), so
    the *display* value is independent of run order — not the first-seen order the runs produced.
    The canonical pick (alphabetically-first: covered < partial < wrong) must never decide accuracy —
    that would skew scoring by the gold label's rank — so ``_calibrate_case`` detects a strict tie
    (no single verdict holds the top count) and excludes it from accuracy rather than trusting this."""
    counts: Dict[str, int] = {}
    for verdict in verdicts:
        counts[verdict] = counts.get(verdict, 0) + 1
    if not counts:
        return SEM_UNJUDGEABLE, 0
    best = max(sorted(counts), key=lambda v: counts[v])
    return best, counts[best]


def _pairing_unscoreable(pairing: Pairing) -> bool:
    """A pairing the pre-filter would mark unjudgeable — no requirement, or too little text to
    compare. The judge would never see it in normal operation, so it is excluded from calibration
    rather than judged on empty input and scored as a mismatch."""
    if not pairing.requirement:
        return True
    return overlap_score(pairing.code, pairing.requirement) is None


def _calibrate_case(pairing: Pairing, gold: SemanticGold, judge_fn: SemanticJudgeFn,
                    runs: int) -> "Tuple[bool, Optional[bool], Optional[float], Dict[str, object]]":
    """Judge one gold-backed pairing ``runs`` times → ``(unscoreable, matched, consistency, row)``.
    ``consistency`` is ``None`` when fewer than two runs survived (run-to-run agreement is unmeasurable
    with one verdict, never a false 1.0). ``matched`` is ``None`` on a strict tie (no majority) and on a
    *crash-degraded* case (``runs>=2`` reduced to one survivor — which run crashed must not flip
    accuracy); an *intentional* ``runs=1`` single verdict still scores accuracy (a trivial majority).

    ``unscoreable`` is true when **no** run produced a real verdict (every run was UNJUDGEABLE — a
    crash, a malformed reply, or none wired): a harness/operational outcome, not a disagreement, so
    the caller excludes it. UNJUDGEABLE runs are dropped **before** majority/consistency. ``accuracy``
    is fully guarded — below two survivors ``matched`` is ``None`` (a crash that drops survivors to one
    must not turn an excluded tie into a hit or miss). ``consistency`` is a share **over the survivors**,
    so when a crash coincides with a *dissenting* run it is an estimate: e.g. real ``[covered, covered,
    wrong]`` is 0.667, but a crash on the ``wrong`` run reads 1.0 and a crash on a ``covered`` run reads
    0.5. It is honest for what it measures (agreement among the runs that returned) and ``runs_effective``
    records the survivor count; it does not pretend a crashed run agreed. Keying off the verdicts (not a
    rationale substring) means a real verdict is never falsely excluded for mentioning an error.
    """
    forced = Ranked(pairing, 0.0, True, "calibration")
    verdicts = [_judge_one(forced, judge_fn).verdict for _ in range(runs)]
    real = [verdict for verdict in verdicts if verdict != SEM_UNJUDGEABLE]
    if not real:
        return True, False, None, {"block_id": pairing.block_id, "expected": gold.verdict,
                                   "majority": SEM_UNJUDGEABLE, "matched": False,
                                   "runs_effective": 0, "consistency": None}
    majority, count = _majority(real)
    # Normalise the gold side the same way ``_reply_to_verdict`` normalises the judge side, so a
    # directly-built ``SemanticGold("Covered")`` / ``" covered"`` (``load_gold`` enforces lowercase,
    # direct construction does not) is a formatting difference, never a false accuracy=0 mismatch.
    gold_verdict = gold.verdict.strip().lower()
    matched: Optional[bool]
    consistency: Optional[float]
    if len(real) >= 2:
        # A strict tie (more than one verdict shares the top count) has no majority: scoring it against
        # gold would credit the canonical (alphabetically-first) pick, deflating accuracy whenever gold
        # is a later label (e.g. the safety-critical ``wrong``). ``matched=None`` leaves accuracy alone.
        tied = sum(1 for verdict in set(real) if real.count(verdict) == count) > 1
        matched = None if tied else majority == gold_verdict
        # Consistency = the majority verdict's share of the surviving runs (``count / len(real)``): 1.0
        # when every real run agreed, 0.5 when a 3-run case split 2:1. ``runs_effective`` records how
        # many runs produced a verdict, so a case decided on fewer than ``runs`` stays visible.
        consistency = round(count / len(real), 4)
    elif runs == 1:
        # Intentional single run: a lone clean verdict has a trivial majority, so it *does* score
        # accuracy (matching the doc); consistency needs ≥2 runs to mean anything, so it stays None.
        matched = majority == gold_verdict
        consistency = None
    else:
        # Crash-degraded: ``runs`` asked for repetition but crashes left one survivor. Scoring that
        # lone verdict would let *which* run crashed flip a would-be tie into a hit or miss, so a
        # degraded case feeds neither denominator — gold-independent.
        matched = None
        consistency = None
    return False, matched, consistency, {"block_id": pairing.block_id, "expected": gold.verdict,
                                         "majority": majority, "matched": matched,
                                         "runs_effective": len(real), "consistency": consistency}


def calibrate(cases: Sequence[Tuple[Pairing, SemanticGold]], judge_fn: SemanticJudgeFn,
              runs: int = 3) -> SemanticCalibration:
    """Run the judge ``runs`` times over each gold-backed pairing; report accuracy + consistency.

    Both are ``None`` when there is nothing to measure — never a false 0. A pairing the pre-filter
    would mark unjudgeable (no requirement / below the token floor), or one whose judged majority is
    UNJUDGEABLE (a crash, a malformed reply, or no judge wired), is **excluded** — a harness/
    operational outcome, not a judge mismatch — so it never deflates accuracy. ``covered`` still
    lists every gold-backed pairing.

    Calibrating against ``reference_stub_judge`` is warned at runtime: the stub re-uses the
    pre-filter's own overlap, so its numbers measure the machinery, not judge quality.
    """
    runs = max(1, runs)
    if judge_fn is reference_stub_judge:
        logger.warning("semantic: calibrating against reference_stub_judge — it re-uses the pre-filter's "
                       "own overlap score, so accuracy/consistency measure the machinery, not judge "
                       "quality; wire a real judge for meaningful calibration.")
    scoreable = [(pairing, gold) for pairing, gold in cases if not _pairing_unscoreable(pairing)]
    excluded = [pairing.block_id for pairing, _ in cases if _pairing_unscoreable(pairing)]
    outcomes = [(pairing, _calibrate_case(pairing, gold, judge_fn, runs))
                for pairing, gold in scoreable]
    excluded = excluded + [pairing.block_id for pairing, out in outcomes if out[0]]  # out[0]: unscoreable?
    scored = [out for _, out in outcomes if not out[0]]
    # Accuracy is over cases with a real majority (matched is not None — a strict tie is unmeasurable,
    # not a miss); consistency only over cases with a real run-to-run measurement (≥2 survivors), so a
    # one-survivor case cannot contribute a spurious 1.0. Independent denominators, each honest.
    matched = [m for _, m, _, _ in scored if m is not None]
    measured = [c for _, _, c, _ in scored if c is not None]
    judge = getattr(judge_fn, "__qualname__", "") or type(judge_fn).__name__
    return SemanticCalibration(
        accuracy=round(sum(1 for m in matched if m) / len(matched), 4) if matched else None,
        consistency=round(sum(measured) / len(measured), 4) if measured else None,
        covered=[pairing.block_id for pairing, _ in cases],
        runs_per_scenario=runs, per_case=[row for _, _, _, row in scored], excluded=excluded,
        judge=judge)
# @cpt-end:cpt-studio-algo-eval-semantic:p1:inst-semantic-calibrate
