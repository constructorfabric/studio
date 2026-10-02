"""Enumerate a plan's deliverable items from its phase files' acceptance criteria.

Verification-before-completion (the T4b close-of-run) checks a run against the items the
approved plan says it must satisfy. Those items are not a structured array in ``plan.toml``
today -- they live as Markdown task-list checkboxes under an ``## Acceptance Criteria``
heading in each phase file, the shape ``requirements/plan-template.md`` Section 8 mandates
(3-10 objectively-verifiable criteria per phase). This reads them into an enumerable list so
the completion check can walk it.

**The one bit of plan syntax it adds** is an optional trailing ``(needs: key)`` marker on a
criterion, declaring the open question the item waits on by that question's decision ``KEY``.
It reuses the existing ``needs`` vocabulary (a phase already declares the decisions it
``needs``) and the existing decision-key grammar, so only the inline placement is new. An item
whose question is still outstanding cannot be shown complete -- the open-question invariant.
A malformed marker -- a broken trailing shape (missing colon or unbalanced parentheses) or an
unusable key -- is reported, never silently read as "waits on nothing".

**The checkbox is a claim, never a verdict.** A ``[x]`` records that the *author* marked the
criterion done. This reader carries that as ``authored_done`` and nothing more -- whether the
item is actually satisfied is verification's job, not the box's, exactly as a sub-agent's
success report is not evidence its diff landed. Trusting the box here would delete the check
T4b exists to run.

**Every item is ``explicit`` in v1.** The plan does not yet declare *how* an item is checked
(a validator, a path, a schema), so none is inferred -- the conservative direction. The
``verify_kind`` field exists so a later increment can add ``deterministic`` without reshaping
any caller.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# Reuse the plan module's loader and text bound rather than a second copy of either: two
# plan readers drift, and two capping rules drift, and only one of each gets the next fix
# (the same argument `_bounded`'s own docstring makes). `_load_plan` is fail-loud -- it
# returns the reason a plan could not be read, which this surfaces rather than swallows.
from .plan_decisions import (  # noqa: F401  (re-exported constants kept near their use)
    PLAN_FILE,
    PHASES_TABLE,
    _MAX_PLAN_BYTES,
    _bounded,
    _load_plan,
)
# The decision-key grammar, imported rather than re-compiled: the key a `(needs: key)`
# marker names is a `decision_key`, and a second copy of its pattern would drift from the
# one the MENU `KEY:` declaration and `GateRuling.decision_key` already use.
from .pdsl import MENU_KEY_SYNTAX_RE
# The reserved sentinel the log uses for "no key": a `(needs: unspecified)` marker would be
# syntactically valid yet unrepresentable in the register (which treats it as absent), so it
# must be rejected here rather than applied silently. Imported, never re-spelled.
# `capped_text` is the log's own `decision_key` field transform: a marker key that does not
# survive it unchanged (e.g. longer than the field) would be recorded in a truncated form an
# answering event could never match, so it is rejected here using that same transform rather
# than a re-spelled length rule that would drift from the log's.
from .decision_log import UNSPECIFIED, capped_text

# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-model
#: The level-2 heading whose task-list items are the deliverable criteria
#: (``requirements/plan-template.md`` Section 8). Matched case-insensitively.
_ACCEPTANCE_HEADING = "acceptance criteria"

#: A Markdown task-list item: a ``-`` or ``*`` bullet, a ``[ ]``/``[x]``/``[X]`` box, then
#: the criterion text. Anchored so a bare ``[x]`` mid-sentence is not mistaken for an item.
#: The text is captured greedily to end-of-line (no trailing ``\s*$``, which backtracks) and
#: trimmed by ``_bounded`` at the call site.
_CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[(?P<box>[ xX])\]\s+(?P<text>\S.*)$")

#: A level-2 ATX heading line. A deeper (``###``) or shallower (``#``) heading does not open
#: or close the criteria section, so a sub-heading inside it does not end it. The title is
#: captured greedily and ``.strip()``-ed at the call site, so no trailing ``\s*$`` is needed.
_H2_RE = re.compile(r"^\s*##\s+(?P<title>\S.*)$")

#: A trailing ``(needs: key)`` marker on a criterion: declares the open question the item
#: waits on, by that question's decision ``KEY``. Anchored to end-of-line so only a *trailing*
#: marker is read (``needs:`` mid-prose is left alone), and the key is captured raw (``.strip``ed
#: at the call site) so a malformed one is reported rather than silently treated as no
#: dependency. The key is validated against ``MENU_KEY_SYNTAX_RE``, the shared decision-key
#: grammar. ``[^)]*`` owns the whole inner span with no adjacent ``\s*`` to backtrack against.
#: Trailing sentence punctuation and whitespace after the marker are allowed
#: (``…(needs: key).``), so an author who ends the criterion as ordinary prose still has the
#: marker honoured rather than silently ignored. One combined class ``[\s.;:,!?]*`` — not two
#: adjacent quantified groups — so there is no super-linear backtracking (Sonar S8786).
_NEEDS_RE = re.compile(r"\(needs:(?P<key>[^)]*)\)[\s.;:,!?]*$")

#: v1 verification kind -- an explicit statement to be made at completion. See module doc.
VERIFY_EXPLICIT = "explicit"

#: An author-controlled count, so it is bounded: a phase file declaring ten thousand
#: checkboxes yields the first `MAX_ITEMS_PER_PHASE` and a recorded note that the rest were
#: not read, never ten thousand items. The template's own ceiling is 10; this is generous.
MAX_ITEMS_PER_PHASE = 100
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-model


# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-model
@dataclass(frozen=True)
class PlanItem:
    """One deliverable criterion a run must satisfy."""

    phase: int           #: the phase number whose acceptance criteria this came from
    ordinal: int         #: 0-based position within that phase's criteria (authoring order)
    text: str            #: the criterion text, bounded and whitespace-collapsed
    authored_done: bool  #: the ``[x]`` box as AUTHORED -- a claim, not a verified fact
    verify_kind: str = VERIFY_EXPLICIT
    #: The decision ``KEY`` of the open question this item waits on, from a trailing
    #: ``(needs: key)`` marker, or ``None`` when the item declares no dependency. An item
    #: whose question is still outstanding cannot be shown complete (the open-question invariant).
    depends_on_question: Optional[str] = None
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-model


# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-model
@dataclass(frozen=True)
class PlanItems:
    """Every deliverable item a run must satisfy, plus what could not be read.

    One shape for every outcome: a caller reads ``items`` for the list and ``error`` for a
    manifest that would not load at all (no items are returned in that case).
    ``phases_without_criteria`` is not an error -- a phase may legitimately declare none --
    but a later increment decides what an empty plan means, so it is surfaced, not hidden.
    ``read_problems`` names each phase whose criteria could not be fully read (a missing or
    unreadable file, a path escaping the plan directory, a non-UTF-8 file, or a criteria
    list past the per-phase cap), each with its reason: fail-loud, never a silent gap.
    """

    items: List[PlanItem]
    error: Optional[str] = None
    phases_without_criteria: List[int] = field(default_factory=list)
    read_problems: List[str] = field(default_factory=list)
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-model


# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-read
def read_plan_items(plan_dir: Path) -> PlanItems:
    """The deliverable items the plan at ``plan_dir`` declares, in phase then authoring order.

    Re-reads the plan on every call (never cached): a plan edited mid-run has to take effect
    on the next read, the same reason the decision lookup re-reads. A manifest that will not
    load returns ``error`` and no items; a phase file that will not read is named in
    ``read_problems`` while the other phases still contribute theirs -- one bad phase file is
    a reported gap about that phase, not a crash that hides the rest.
    """
    plan, reason, _verdict = _load_plan(plan_dir / PLAN_FILE)
    if plan is None:
        return PlanItems(items=[], error=reason)

    phases = plan.get(PHASES_TABLE)
    if not isinstance(phases, list):
        if PHASES_TABLE in plan:
            # The author wrote a `phases` that is not an array -- a defect they must hear,
            # distinct from a plan that simply declares no phases (nothing to read).
            return PlanItems(
                items=[],
                error=(f"{PLAN_FILE}'s `{PHASES_TABLE}` is not an array, so no phase "
                       "files can be read for their acceptance criteria"),
            )
        return PlanItems(items=[])

    items: List[PlanItem] = []
    without: List[int] = []
    problems: List[str] = []
    for index, phase in enumerate(phases):
        found, empty_of, phase_problems = _items_for_phase(plan_dir, phase, index)
        items.extend(found)
        if empty_of is not None:
            without.append(empty_of)
        problems.extend(phase_problems)
    return PlanItems(items=items, phases_without_criteria=without, read_problems=problems)
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-read


# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-phase
def _items_for_phase(
    plan_dir: Path, phase: object, index: int
) -> Tuple[List[PlanItem], Optional[int], List[str]]:
    """One phase's contribution: its items, the number to file under
    ``phases_without_criteria`` when it has none, and its ``read_problems`` notes when reading
    it went wrong. A phase speaks to exactly the lists it has something to say for -- a read
    failure yields only a problem; truncation yields both items and a problem; a malformed
    ``(needs: …)`` marker yields the item *and* a problem, so one phase may have several.
    """
    if not isinstance(phase, dict):
        return [], None, [f"phase at position {index}: not a table, so it was skipped"]
    number = _phase_number(phase, index)
    file_name = phase.get("file")
    if not isinstance(file_name, str) or not file_name:
        return [], None, [f"phase {number}: declares no `file` to read criteria from"]
    text, read_error = _read_phase_text(plan_dir, file_name)
    if read_error is not None:
        return [], None, [f"phase {number} ({_bounded(file_name)}): {read_error}"]
    criteria, truncated, marker_problems = _acceptance_items(text, number)
    problems = [f"phase {number}: {note}" for note in marker_problems]
    if truncated:
        problems.append(f"phase {number}: more than {MAX_ITEMS_PER_PHASE} criteria; "
                        "the rest were not read")
        return criteria, None, problems
    if not criteria:
        return [], number, problems
    return criteria, None, problems
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-phase


# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-file
def _phase_number(phase: dict, index: int) -> int:
    """The phase's declared ``number``, or its position when that is absent or unusable.

    An unparseable ``number`` falls back to ``index + 1`` rather than raising: the reader's
    job is to surface items, and a phase mis-numbering is the structural validator's finding,
    not a reason to read no items at all.
    """
    raw = phase.get("number")
    if isinstance(raw, bool):  # bool is an int subclass; a `number = true` is not a number
        return index + 1
    if isinstance(raw, int):
        return raw
    return index + 1
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-file


# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-file
def _read_phase_text(plan_dir: Path, file_name: str) -> Tuple[Optional[str], Optional[str]]:
    """A phase file's text, or ``None`` and the reason it could not be had.

    The file name comes from the plan, which is author-controlled, so the resolved path is
    required to stay inside the plan directory -- a ``file = "../../etc/passwd"`` is refused,
    not read. The file is read strictly as UTF-8: a byte sequence that is not UTF-8 is
    reported, never decoded with replacement, because a mangled criterion silently changes
    what the run is checked against.
    """
    base = plan_dir.resolve()
    candidate = (plan_dir / file_name).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None, "its file path escapes the plan directory, so it is not read"
    if not candidate.is_file():
        return None, "is not a readable regular file"
    try:
        with candidate.open("rb") as handle:
            data = handle.read(_MAX_PLAN_BYTES + 1)
    except OSError as exc:
        return None, (exc.strerror or "could not be read").lower()
    if len(data) > _MAX_PLAN_BYTES:
        return None, "is larger than any phase file this workflow writes, so it is not read"
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError as exc:
        return None, (f"is not valid UTF-8 at byte {exc.start}, so its criteria would be "
                      "read as bytes the author did not write")
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-file


# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-criteria
def _acceptance_items(
    phase_text: str, phase_number: int
) -> Tuple[List[PlanItem], bool, List[str]]:
    """The task-list items under this phase's ``## Acceptance Criteria`` heading.

    Scans line by line: a level-2 heading opens the section when its title is
    ``Acceptance Criteria`` (case-folded) and closes it when it is anything else, so a
    checkbox under a different ``##`` heading is never collected. Returns the items, a flag
    for whether the per-phase cap truncated them, and a note for each item whose trailing
    ``(needs: …)`` marker was malformed (reported, never silently dropped).
    """
    in_section = False
    items: List[PlanItem] = []
    problems: List[str] = []
    ordinal = 0
    for line in phase_text.splitlines():
        heading = _H2_RE.match(line)
        if heading is not None:
            in_section = heading.group("title").strip().casefold() == _ACCEPTANCE_HEADING
            continue
        if not in_section:
            continue
        box = _CHECKBOX_RE.match(line)
        if box is None:
            continue
        if ordinal >= MAX_ITEMS_PER_PHASE:
            return items, True, problems
        depends_on, marker_problem = _extract_needs(box.group("text"))
        if marker_problem is not None:
            problems.append(f"criterion {ordinal + 1}: {marker_problem}")
        items.append(
            PlanItem(
                phase=phase_number,
                ordinal=ordinal,
                text=_bounded(box.group("text")),  # full text; the marker is kept, never stripped
                authored_done=box.group("box").casefold() == "x",
                depends_on_question=depends_on,
            )
        )
        ordinal += 1
    return items, False, problems
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-criteria


# @cpt-begin:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-needs
def _looks_like_broken_marker(raw_text: str) -> bool:
    """Whether the criterion ends in a *broken* attempt at a ``(needs: key)`` marker.

    Only a **trailing** attempt counts: a properly closed ``(needs: …)`` group followed by real
    words is ordinary prose (``"the API (needs: auth) exposes …"``) and is left alone. A trailing
    group that opens with ``(needs`` but is not the exact valid shape -- missing the colon, missing
    the closing parenthesis, or carrying an extra one -- is a typo the author meant as a marker, so
    the caller reports it rather than letting the intended dependency silently vanish. Called only
    after the strict ``_NEEDS_RE`` has already failed, so a valid marker never reaches here.
    """
    stripped = raw_text.rstrip(" \t.;:,!?")
    start = stripped.rfind("(needs")
    if start == -1:
        return False
    after_needs = stripped[start + 6:start + 7]
    if after_needs.isalnum() or after_needs == "_":
        return False  # "(needsfoo…" is a different word, not a marker attempt
    tail = stripped[start:]
    close = tail.find(")")
    if close == -1:
        return True  # unclosed, e.g. "(needs: key"
    # Closed: a marker attempt only if nothing but punctuation / extra parens follows the close
    # ("(needs key)", "(needs: key))"); real words after it make it mid-sentence prose.
    return not any(ch.isalnum() for ch in tail[close + 1:])


def _extract_needs(raw_text: str) -> Tuple[Optional[str], Optional[str]]:
    """Find a criterion's optional trailing ``(needs: key)`` dependency key.

    Returns ``(depends_on, problem)``. The criterion text is **left intact** -- the marker is
    not stripped -- because two criteria with identical wording but different dependency keys
    are different deliverables, and stripping the marker would collapse them to one verdict
    identity (same ``(phase, text)``). The marker stays part of the text, so the two keep
    distinct identities and an author can give each its own verdict by its full wording.

    A well-formed key sets ``depends_on``. The dependency is **reported and left unset** --
    fail-loud, never a silent partial application -- when the trailing marker is a broken shape
    (a typo'd ``(needs …)`` the author meant as a marker -- missing colon or unbalanced
    parentheses -- so the intended dependency does not silently vanish), or when the key is not a
    valid decision key, is the reserved ``UNSPECIFIED`` sentinel (which the register treats as "no
    key", so it could never block), does not survive the log's ``decision_key`` field transform
    unchanged (a longer key is stored truncated, so an answering event could never match it -- the
    item would stay blocked with no further diagnostic), or when a *second*, earlier marker is
    present (only the trailing one is read).
    """
    match = _NEEDS_RE.search(raw_text)
    if match is None:
        # A trailing typo'd marker is reported; anything else genuinely has no marker.
        problem = ("a trailing `(needs: …)` dependency marker is malformed — it must be exactly "
                   "`(needs: key)`, a colon after `needs` inside one balanced pair of parentheses "
                   "at the end of the criterion; the dependency was not applied"
                   ) if _looks_like_broken_marker(raw_text) else None
        return None, problem
    key = match.group("key").strip()
    if not MENU_KEY_SYNTAX_RE.match(key):
        return None, (f"a `(needs: …)` marker whose key {key!r} is not a valid decision key "
                      "(lowercase, starting with a letter, letters/digits/underscores only); "
                      "the dependency was not applied")
    if key == UNSPECIFIED:
        return None, (f"a `(needs: …)` marker whose key {key!r} is the reserved value the log "
                      'uses for "no key", so it could never block; the dependency was not applied')
    if capped_text(key) != key:
        return None, ("a `(needs: …)` marker whose key is longer than the decision log can "
                      "store (it would be recorded truncated, so an answer could never match "
                      "it and the item would stay blocked); the dependency was not applied")
    if "(needs:" in raw_text[:match.start()]:
        return None, ("more than one `(needs: …)` marker on this criterion; only the trailing "
                      "one is read, so the dependency was not applied — keep a single marker")
    return key, None
# @cpt-end:cpt-studio-algo-execution-plans-deliverable-items:p1:inst-items-needs
