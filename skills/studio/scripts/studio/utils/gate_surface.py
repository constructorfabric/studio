"""Count the gates a workflow can reach, so "Studio interrupts you less" can be measured.

A static walk of the declared surface. No agent, no cost, deterministic. A spike tried the
obvious alternative -- run the thing and count what it asks -- and refuted it: a transcript
cannot distinguish a gate the workflow declared from one the model invented, and the
run-to-run spread on an identical request was 1-8 stops. So this reads the declarations
instead, where the answer is the same every time.

**Reachability is an upper bound, not a path trace.** A `LOAD` guarded by `WHEN` is followed
anyway, because deciding a guard needs runtime state this does not have. Said plainly rather
than hidden: what the number is good for is *ranking* -- which gates dominate the surface --
and a ranking is robust to counting a guarded branch that a given run would skip.

**Three numbers, and only the first is the metric.**

``stop_sites``
    emit sites whose sequence ends the turn — **the declared stop**, and the headline. This
    is what "Studio stops to ask me" means and what the autonomy work is trying to reduce.
``non_stop_sites``
    emit sites whose sequence runs on. A ledger entry, not an interruption.
``halt_sites``
    a `STOP_TURN` reached with no menu emitted before it: the turn ends and nothing was
    asked. Refusing to dispatch an unapproved plan is one. Real, and deliberately not
    folded into the first -- a change that adds a refusal would otherwise read as one that
    adds an interruption.

**Where the wait is written, and why that is the whole design.** The first version of this
read the *menu definition* and asked whether `WAIT user.reply` / `STOP_TURN` appeared
anywhere inside it. That is the wrong side of the join, and the corpus says so plainly:

    EMIT_MENU PlanGateMenu
    WAIT user.reply
    STOP_TURN

The wait belongs to the **emitting sequence**, not to the menu. Reading the definition
instead found waits where they were not declarations at all -- an option the user might
pick (`3 stop -> STOP_TURN`) or an `INVALID ->` re-prompt -- and so labelled the plan
approval gate, the git-commit-mode gate and the simple-mode gate as menus that interrupt
nobody. Measured on the pinned kit, that rule scored 315 of 478 emit-site visits where
reading the emit site scores 377, and the three it missed most visibly are the three
gates a user meets first.
"""
from __future__ import annotations

import collections
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# @cpt-begin:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-vocab
#: The three PDSL actions this counts, named here and checked against the validator's own
#: keyword set at import. A rename there would otherwise leave this walking a corpus and
#: finding nothing -- a silent zero that reads as "no gates" rather than "wrong keyword",
#: and under-counting flatters every comparison made afterwards.
_LOAD = "LOAD"
_EMIT_MENU = "EMIT_MENU"
_STOP_TURN = "STOP_TURN"

#: The menu-name grammar, spelled out to match the validator's `[A-Za-z][A-Za-z0-9_-]*`
#: exactly. Not `str.isalpha`/`str.isalnum`, which are Unicode-aware and accept names the
#: validator rejects outright.
_NAME_HEAD = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
_NAME_BODY = frozenset(_NAME_HEAD | set("0123456789_-"))

#: What a menu waits on, spelled as the corpus spells it.
_WAIT = "WAIT user.reply"

#: Where a `LOAD` points, relative to the kit root.
#:
#: Deliberately **not** restricted to a directive position, which is the one place this
#: module's scans differ from each other on purpose: the halt count reads only `DO` and
#: `ON_ERROR`, and this reads anywhere inside a fence. Proposed in review as an
#: inconsistency, and measured before answering. Counted on this branch as it will merge
#: (`workflows/` + `skills/`, fenced text only), of the 520 `LOAD` lines there,
#: 474 are in `DO`, **43 are in `OPTIONS`** and **3 are in `RULES`**:
#:
#:     OPTIONS   2 edit - open the manifest ... -> LOAD {cf-studio-path}/.core/...
#:     RULES     ALWAYS auto-skip and SET ..., LOAD {cf-studio-path}/.core/...
#:
#: A menu option that loads a module is a real edge, and so is a rule that says to load
#: one; scoping this to `DO`/`ON_ERROR` would drop 46 dependencies the closure needs. The
#: asymmetry is the right one because the two scans answer different questions: a halt is
#: an *action taken* and belongs to an action section, while a `LOAD` is a *dependency
#: declared* and the corpus declares them in options and rules as well.
LOAD_TARGET = re.compile(r"LOAD[ \t]+\{cf-studio-path\}/\.core/([\w./-]+\.md)")

#: The directories a `LOAD` may point into and still be this walk's business. A target
#: outside them (`requirements/`, `architecture/specs/`) is a documented out-of-scope
#: reference -- 17 of them in the pinned kit -- and skipping those silently is correct.
#: A target *inside* them that no file provides is a typo or a deleted module, and
#: skipping that silently under-counts every menu behind it.
SCANNED = ("workflows/", "skills/")

#: How much of one reported path or menu name the result keeps.
_MAX_REPORTED = 200

#: A fenced code block, and the language it declares.
_FENCE = re.compile(r"^```(\w*)")

#: The sections whose lines are actions. `DO` is a unit's body and `ON_ERROR` its recovery
#: path; the rest describe behaviour rather than performing it, and an `ALWAYS` or `NEVER`
#: naming `STOP_TURN` is a rule about halting, not a halt.
_ACTION_SECTIONS = frozenset({"DO", "ON_ERROR"})

#: A markdown list marker in front of a PDSL action. The corpus writes actions both bare
#: and as list items, and the first version of this scan read only the bare form: it found
#: 80 of the 88 emit sites, and one of the eight it missed is reachable from 39 workflows.
_LIST_MARKER = re.compile(r"^(?:[-*][ \t]+|\d+\.[ \t]+)")

#: The headers that end an action sequence. Reaching one means the emit was not followed
#: by a wait *in its own sequence*, and scanning past it would attribute another block's
#: wait to this emit -- an emit at the end of one unit borrowing the wait of the next.
#:
#: The whole PDSL block vocabulary, though only three of these are ever reached on the
#: pinned kit: `RULES` five times, `INVARIANTS` once and `MENU` once, with the other 81
#: emit sites reaching a wait before any boundary. The nine that never fire are kept
#: because the set is the language's, not this corpus's: `UNIT` is the boundary that
#: matters most and fires zero times here only because every unit in this kit happens to
#: end with `RULES` first. Measured rather than assumed, and each entry is pinned by a
#: test -- dropping any one of them used to change neither a test nor a number, because
#: another entry always caught the same case.
_SECTIONS = frozenset({"PURPOSE", "DO", "RULES", "WHEN", "STATE", "INVARIANTS",
                       "OPTIONS", "INVALID", "NOTES", "TITLE", "UNIT", "MENU"})
# @cpt-end:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-vocab


# @cpt-begin:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-scan
def _declared(text: str) -> str:
    """``text`` with everything outside a ```pdsl fence blanked out.

    PDSL lives in fenced blocks and prose lives around them, so the fence is the structural
    answer to "is this a declaration, or someone writing about one". The scan used to read
    every line and lean on a backtick to tell those apart, which fails for the case review
    raised: an unindented sentence beginning with the word `MENU`, or mentioning
    `EMIT_MENU` without quoting it, was read as a real declaration and put a gate in the
    surface that no workflow can reach.

    Measured before changing anything, since a filter that removes real declarations is the
    worse failure: on the pinned kit **every** declaration is already fenced -- 88 of 88
    emit sites, 107 of 107 menu headers and 526 of 526 `LOAD` lines -- so this excludes
    nothing the walk was counting and closes the prose case by construction.

    Lines are blanked rather than dropped so the text keeps its shape: a blank line is a
    boundary to no rule, where a dropped one would silently join the text either side.
    """
    kept: List[str] = []
    language: Optional[str] = None
    for line in text.splitlines():
        marker = _FENCE.match(line.strip())
        if marker is not None:
            # Opening records the language, closing forgets it. A fence with no language,
            # or another language, is not PDSL and its body is blanked like any prose.
            language = marker.group(1) if language is None else None
            kept.append("")
            continue
        kept.append(line if language == "pdsl" else "")
    return "\n".join(kept)


def _action(line: str) -> str:
    """One line as the action it declares: indentation and any list marker removed."""
    return _LIST_MARKER.sub("", line.strip())

def _menu_name(rest: str) -> Optional[str]:
    """The menu name at the start of ``rest``, or ``None`` when there is not one.

    Hyphens are part of a name. The validator permits them (`[A-Za-z][A-Za-z0-9_-]*`) and
    this stopped at the first one, so `Plan-Approval-Gate` was read as `Plan` -- a name
    that silently merges with any real menu called `Plan` and takes its reachability with
    it. The pinned kit has none today; a scanner that mis-reads a legal name is a wrong
    number waiting for the first author who writes one.

    The character sets are **ASCII, spelled out**, because the validator's grammar is
    `[A-Za-z][A-Za-z0-9_-]*` and agreement with it is the only property that matters here:
    a name this walk reads differently is a name no gate can emit. Python's `isalpha` and
    `isalnum` are Unicode-aware and did not agree -- the validator *rejects* `CaféMenu`
    outright, while this returned it whole, so the walk would have counted a menu the
    product refuses to declare. It agreed only on the decomposed spelling, which is the
    half I checked and the half I wrote the docstring from. Raised in review.

    Zero non-ASCII names in either tree, so no figure moves; the point is that the stated
    agreement is now true rather than true of one spelling.
    """
    token = rest.split(None, 1)[0] if rest.split() else ""
    if token[:1] not in _NAME_HEAD:
        return None
    cut = 1
    while cut < len(token) and token[cut] in _NAME_BODY:
        cut += 1
    if cut < len(token) and (token[cut].isalnum() or token[cut] == "_"):
        # The validator ends its name with `\b`, and there is no word boundary between
        # `f` and `é` -- so `CaféMenu` does not match at all and the declaration is
        # rejected. Truncating to `Caf` here would count a menu the product refuses to
        # declare; returning nothing agrees with it.
        return None
    return token[:cut]

def _block_header(line: str) -> Optional[str]:
    """The name this line opens a block for, or ``None`` when it opens none.

    A header sits at the left margin: `MENU` written inside a body — quoted in prose, or
    inside an option — must not end the definition it appears in. `UNIT` opens a block too
    and has no menu name, so it returns the empty string: "a header, but not a menu".
    """
    if line[:1] in (" ", "\t"):
        return None
    head = line.split(None, 1)
    keyword = head[0] if head else ""
    if keyword == "UNIT":
        return ""
    if keyword != "MENU" or len(head) < 2:
        return None
    return _menu_name(head[1])

def menu_blocks(text: str) -> List[Tuple[str, str]]:
    """Every `MENU` definition in ``text`` as ``(name, body)``, body up to the next block.

    A line scan for the same reason as the emit scan: the pattern this replaces paired a
    reluctant quantifier with a lookahead, which the analyser reads as matching nothing. It
    did match — bodies of 38 and 12 characters on a two-menu sample — but a construct that
    has to be defended with a measurement is worth replacing with one that needs none.

    The header test is its own function because deciding *whether a line opens a block* and
    *accumulating a body* are separate jobs, and folding them together put this one over
    the cognitive-complexity limit.

    This is the one reading of "a menu is defined here". A second pattern answering the
    same question is how two answers drift apart, which is what a separate `MENU_DEF`
    regex did: it excluded hyphens where this did not.
    """
    blocks: List[Tuple[str, str]] = []
    name: Optional[str] = None
    body: List[str] = []
    for line in text.splitlines():
        opened = _block_header(line)
        if opened is None:
            if name is not None:
                body.append(line)
            continue
        if name is not None:
            blocks.append((name, "\n".join(body)))
        name, body = (opened or None), []
    if name is not None:
        blocks.append((name, "\n".join(body)))
    return blocks
# @cpt-end:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-scan


# @cpt-begin:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-stop-definition
def _ends_the_turn(action: str) -> bool:
    """Whether this action stops the turn: the wait, or the halt that follows it."""
    return action.startswith((_WAIT, _STOP_TURN))

def _ends_the_sequence(action: str) -> bool:
    """Whether this action closes the block an emit sits in."""
    if action.startswith("```"):
        return True
    head = action.split(None, 1)[0] if action.split() else ""
    return head.rstrip(":") in _SECTIONS

# @cpt-end:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-stop-definition


# @cpt-begin:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-emit
def _emit_on(action: str) -> Optional[Tuple[str, str]]:
    """The menu and the rest of the line when ``action`` is an `EMIT_MENU`, else ``None``.

    Split out of the scan below, which the analyser read at a cognitive complexity of 19
    against a limit of 15: deciding *whether a line is an emit* and *what the sequence
    does with the emits it has* are two jobs, and they nest badly when written as one.
    """
    if not action.startswith(_EMIT_MENU):
        return None
    rest = action[len(_EMIT_MENU):]
    if not rest[:1].isspace():
        return None                           # `EMIT_MENUX` is a different token
    name = _menu_name(rest)
    if name is None:
        return None
    parts = rest.split(None, 1)
    return name, (parts[1] if len(parts) > 1 else "")


# @cpt-end:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-emit


# @cpt-begin:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-stop-definition
@dataclass(frozen=True)
class EmitSite:
    """One `EMIT_MENU`, and what the sequence around it does next."""

    menu: str
    #: A `WHEN` on the emit line: the difference between "may ask" and "asks".
    conditional: bool
    #: The sequence reaches `WAIT user.reply` / `STOP_TURN` -- **this is the stop**.
    waits: bool


def emit_sites(text: str) -> List[EmitSite]:
    r"""Every `EMIT_MENU` in ``text``, with whether its sequence ends the turn.

    A line scan, not a pattern. The regex this replaces used `^\s*` under `re.M`, and `\s`
    matches a newline — so the leading run spanned lines and the match went quadratic on
    whitespace followed by a near-miss: 0.8ms, 3.2ms, 12.5ms, 52.4ms for 500, 1000, 2000,
    4000 lines. Narrowing it to horizontal whitespace fixed the measurement, and the
    analyser still objected to the shape.

    **One pass over the text, not one per emit.** The first line-scan version asked each
    emit separately how its sequence ended, and each of those answers scanned forward to
    the next boundary -- so a block of *n* emits did O(n squared) work: 57ms, 236ms, 946ms
    and 3597ms for 500 to 4000 emits. Raised in review, and the linearity test could not
    have caught it: that test's hostile input is `EMIT_MENUX`, which is rejected before
    any forward scan runs, so it measured the one path this cost nothing on.

    Emits are collected instead, and settled when the scan reaches the thing that decides
    them: a wait makes every emit still open a stop, and a block boundary or the end of
    the text makes them all non-stops. One wait therefore covers the emits before it,
    which is what the corpus writes -- two guarded emits served by a single
    `WAIT user.reply`, and a `SET` in between.
    """
    found: List[EmitSite] = []
    open_emits: List[Tuple[str, str]] = []

    def settle(waits: bool) -> None:
        """Every emit still open is decided by whatever the scan has just reached."""
        for menu, tail in open_emits:
            found.append(EmitSite(menu=menu, conditional="WHEN" in tail, waits=waits))
        open_emits.clear()

    for line in text.splitlines():
        action = _action(line)
        if not action:
            continue
        emit = _emit_on(action)
        if emit is not None:
            open_emits.append(emit)
        elif _ends_the_turn(action):
            settle(True)
        elif _ends_the_sequence(action):
            settle(False)
    # The text can end mid-block; an emit with nothing after it never waited.
    settle(False)
    return found


# @cpt-end:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-stop-definition


# @cpt-begin:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-guard
def _check_keywords_still_exist() -> None:
    """Fail loudly at import if PDSL renamed an action this counts.

    The alternative is a walk that finds nothing and reports it as a clean surface.

    An unreadable keyword set raises rather than warning. A warning is not failing loudly
    in a pipeline that collects them and reads none, and this guard exists precisely for
    the case whose failure is invisible in the output -- a guard that switches itself off
    quietly is the same defect one level up, which is what this used to do.
    """
    try:
        from .pdsl import DO_KEYWORDS  # pylint: disable=import-outside-toplevel
    except ImportError as exc:  # pragma: no cover - the validator is a sibling here
        raise RuntimeError(
            "gate surface: the PDSL keyword set could not be read, so a rename of LOAD, "
            "EMIT_MENU or STOP_TURN would go unnoticed and this walk would count zero "
            "and report it as no gates") from exc
    missing = {_LOAD, _EMIT_MENU, _STOP_TURN} - set(DO_KEYWORDS)
    if missing:
        raise RuntimeError(
            f"gate surface: {sorted(missing)} are no longer PDSL actions, so this walk "
            "would count zero and report it as no gates")


_check_keywords_still_exist()
# @cpt-end:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-guard


# @cpt-begin:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-outcome
@dataclass(frozen=True)
class WorkflowSurface:
    """One workflow's reachable gate surface."""

    workflow: str
    files_reached: int
    #: `STOP_TURN` sites reached with no menu emitted before them — the turn ends and
    #: nothing was asked.
    halt_sites: int
    #: Emit sites whose sequence ends the turn — **the declared-stop count**.
    stop_sites: int
    #: Emit sites whose sequence runs on. Reported so the two are never conflated: a menu
    #: that auto-proceeds is a ledger entry, not an interruption.
    non_stop_sites: int
    distinct_menus: int


@dataclass
class GateSurface:
    """The whole tree's surface, plus everything that would make its counts a floor.

    ``unreadable``, ``missing_loads`` and ``duplicate_menu_definitions`` are fields rather
    than log lines because a walk that quietly skips something under-counts, and
    under-counting flatters every comparison made against it. A caller comparing two trees
    has to be able to see that one of them was read completely and the other was not.
    """

    tree: str
    workflows: List[WorkflowSurface] = field(default_factory=list)
    #: ``menu name -> how many workflows can reach it at least once``. Counted per
    #: **workflow**: a menu emitted three times inside one workflow counts once here.
    menu_reachability: Dict[str, int] = field(default_factory=dict)
    #: ``menu name -> how many emit sites carry no WHEN``. Counted per **emit site** and
    #: summed over every workflow that reaches it -- a different denominator from the
    #: field above, said here because the two are both `Dict[str, int]` and read alike.
    unconditional: Dict[str, int] = field(default_factory=dict)
    distinct_menu_definitions: int = 0
    #: Menu names defined in more than one file. Reported rather than merged quietly: two
    #: files claiming one name is a collision the tree's author should get to see.
    duplicate_menu_definitions: List[str] = field(default_factory=list)
    #: `LOAD` targets inside the scanned directories that no file provides.
    missing_loads: List[str] = field(default_factory=list)
    unreadable: List[str] = field(default_factory=list)

    @property
    def concentration(self) -> Tuple[int, int]:
        """``(reachability carried by the ten most-reachable menus, total)``.

        The figure the sizing rests on: if a small set of menus carries most of the
        surface, typing that set covers most of the behaviour and the tail can be
        grandfathered rather than migrated at once.
        """
        counts = sorted(self.menu_reachability.values(), reverse=True)
        return sum(counts[:10]), sum(counts)
# @cpt-end:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-outcome


# @cpt-begin:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-read
def _said(value: object) -> str:
    """A path on its way into the result, with the home directory collapsed.

    The tree path lands in a saved baseline artifact, which is the one output of this walk
    intended to be kept and compared later -- so an absolute path under `$HOME` puts a
    username into a file made to be shared. The same leak was fixed in the reversal check
    earlier today; finding it again in the next module is the reason the rule says fix the
    class rather than the instance.

    The relative paths in `unreadable` are already safe: they are relative to the tree.
    """
    text = str(value)
    # `$HOME` is read first because it is the precondition for *both* layers, and because
    # it is the only way to check the shared redactor actually did anything. `capped_text`
    # collapses `$HOME` by reading `Path.home()` itself and, when that raises, returns the
    # value **unchanged without raising** (`decision_log._redact`) -- so a clean return is
    # not proof of redaction. Raised in review three times: the first two fixes guarded the
    # branch where `capped_text` throws, and the leak is on the branch where it succeeds.
    try:
        home = str(Path.home()).rstrip("/\\")
    except (OSError, RuntimeError) as exc:
        # Neither layer can redact and there is no prefix to remove, so the guard stops
        # reporting a path at all rather than reporting an absolute one -- which would put
        # the username in the field this function exists to keep it out of.
        logger.warning("gate surface: the home directory could not be read, so only the "
                       "final path component is reported: %s", type(exc).__name__)
        return ".../" + PurePosixPath(text.replace("\\", "/")).name
    try:
        from .decision_log import capped_text  # pylint: disable=import-outside-toplevel
        reported = capped_text(text)
    except Exception as exc:  # pylint: disable=broad-except
        # Broad, and warned rather than swallowed. `capped_text` is another module's
        # function, so any exception from it would escape a leak guard through the guard's
        # own reporting path; and a leak guard that stops running without saying so is
        # worth a line.
        logger.warning("gate surface: the shared redactor is unavailable, so a path is "
                       "reported through a local fallback: %s", type(exc).__name__)
        reported = text
    if home and reported.startswith(home):
        # Reached when the shared redactor was unavailable, and also when it ran and
        # silently no-opped. Checked on the value it returned rather than inferred from a
        # clean return, because those two are exactly what this function got wrong.
        reported = "~" + reported[len(home):]
    return reported[:_MAX_REPORTED]


def _reported(value: str) -> str:
    """One entry on its way into a list the result carries: stripped, delimited, bounded.

    Every field here is read by something that prints or serialises it, and a tree can
    hold a 200,000-character filename as easily as a short one. Bounding the entries at
    the one place they are built, rather than at each of the three fields, is the
    correction review made twice already: cap the class of value, not the field that
    happened to be noticed.

    Delimited and stripped for a reason found by walking the checklist rather than by
    review. A filename may contain a newline, so a file named
    `bad\nSTOPS: 0 — no gates found.md` rendered as **two lines** in `unreadable` — the
    second a fabricated verdict, inside the one field whose whole job is to say the count
    is incomplete. That is the third appearance of this forgery in three modules: a
    directory name forged a refusal, a quote closed a hand-rolled delimiter early, and now
    a filename forges a result. The lesson each time was to fix the class, so this is the
    one gate every reported entry passes through.

    Stripped here and delimited where it is *rendered*, which is the split the reversal
    check did not need: there the value was one path inside a sentence, so the quotes had
    to travel with it. Here the value is an element of a list, and a list already shows a
    consumer where each entry ends -- quoting it in the field would put literal quotes
    into every path a caller reads back. So the strip lives at this choke point and the
    delimiter lives in `_warn_about_gaps`, where entries are joined into prose and the
    boundary stops being structural.
    """
    printable = "".join(ch if ch.isprintable() else " " for ch in value)
    collapsed = " ".join(printable.split())
    return collapsed if len(collapsed) <= _MAX_REPORTED else collapsed[:_MAX_REPORTED] + "..."


def _read_tree(root: Path) -> Tuple[Dict[str, str], List[str]]:
    """Every workflow and skill file under ``root``, and the ones that could not be read.

    Returned rather than logged. A file skipped in silence lowers every count that follows
    it, and a lower count is indistinguishable from progress.

    Both directories are walked to any depth, and both are named as the subdirectory they
    are. They used to disagree: `glob("workflows/*.md")` saw only the top level, so a
    workflow at `workflows/review/plan.md` vanished, while `rglob("skills/**/*.md")` --
    which pathlib expands to `**/skills/**/*.md` -- swept in any directory named `skills`
    at any depth, including one belonging to something else.
    """
    files: Dict[str, str] = {}
    unreadable: List[str] = []
    found = [path for name in SCANNED for path in (root / name.rstrip("/")).rglob("*.md")]
    for path in sorted(found):
        # `as_posix`, not `str`. On Windows this yields `workflows\\w.md`, and everything
        # downstream speaks forward slashes: the workflow set is selected by a
        # `workflows/` prefix and `LOAD` targets are written with `/` in the corpus. The
        # result would be zero workflows walked and every in-tree load reported missing —
        # a silent empty surface on one platform. Raised in review.
        rel = path.relative_to(root).as_posix()
        try:
            # `utf-8-sig`, not `utf-8`. An editor that writes a byte-order mark puts it
            # before the first character of the file, so the first line arrives as
            # `\ufeffEMIT_MENU First` and matches nothing -- the file's opening
            # declaration disappears, and a first-line `MENU` header takes its whole body
            # with it. Silent, and an under-count is the one failure this module is built
            # to make impossible. Identical to `utf-8` when there is no mark.
            files[rel] = _declared(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError) as exc:
            unreadable.append(_reported(f"{rel}: {type(exc).__name__}"))
    return files, unreadable


# @cpt-end:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-read


# @cpt-begin:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-missing-loads
def _missing_loads(files: Dict[str, str]) -> List[str]:
    """`LOAD` targets inside the scanned directories that no file provides.

    A target outside them is skipped without comment, and that is correct: the kit really
    does load `requirements/` and `architecture/specs/` files this walk has no reason to
    read -- 17 of them in the pinned kit. A target *inside* them is a module that should
    be here (a typo, or one deleted without its loaders) and every menu behind it is
    missing from the count. Reported for the reason `unreadable` is: from the outside, an
    under-count and an improvement look identical.
    """
    missing: Set[str] = set()
    for text in files.values():
        for target in LOAD_TARGET.findall(text):
            if target not in files and target.startswith(SCANNED):
                missing.add(_reported(target))
    return sorted(missing)


# @cpt-end:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-missing-loads


# @cpt-begin:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-read
def _closure(start: str, files: Dict[str, str]) -> Set[str]:
    """Every file reachable from ``start`` by following ``LOAD``, including itself.

    Cycle-safe by construction: a file already seen is never pushed again, so a module that
    loads a module that loads it back terminates rather than recursing. Targets not in the
    tree are skipped here and reported by `_missing_loads`, which keeps two questions
    apart: this one is "where can I get to", that one is "what is not where it says".
    """
    seen, stack = {start}, [start]
    # A closure can visit at most every file once, so exceeding that means the `seen`
    # guard below is not doing its job. The cap turns that into a loud failure instead of
    # a process that spins and allocates: a test bounding only its *wait* still leaks a
    # thread that keeps running, which is how removing the guard stalled a whole suite
    # rather than failing one test.
    budget = len(files) + 1
    while stack:
        budget -= 1
        if budget < 0:
            raise RuntimeError(
                f"gate surface: walking from {start!r} visited more files than exist, so "
                "the cycle guard is not holding")
        for rel in LOAD_TARGET.findall(files.get(stack.pop(), "")):
            if rel in files and rel not in seen:
                seen.add(rel)
                stack.append(rel)
    return seen
# @cpt-end:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-read


# @cpt-begin:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-count
def _halts_outside_menus(text: str) -> int:
    """`STOP_TURN` sites in ``text`` that end a turn no menu was emitted into.

    A `STOP_TURN` after an `EMIT_MENU` is what *makes that emit a stop*; counting it again
    as a halt would take one declaration and add it to both numbers at once. So the scan
    carries whether a menu is open in the current sequence, and only an unaccompanied
    `STOP_TURN` -- refusing to dispatch an unapproved plan, say -- is a halt.

    Counted only where actions live, `DO` and `ON_ERROR`. A `RULES` line reading *"ALWAYS
    treat WAIT plus STOP_TURN as a hard assistant-turn boundary"* states something about
    halting and halts nothing. This replaced a backtick test that was wrong in both
    directions: it dropped a real halt whose line happens to quote a command name, and
    kept rule prose that quoted none. The sections are where the difference actually lies
    -- on the pinned kit, 184 such lines sit in `DO` and 7 in `ON_ERROR`, against 24 in
    `RULES`, 3 in `INVARIANTS` and 2 in `NOTES`.

    Matched anywhere in the action, not only at its start: the corpus writes 94 at the
    start of a line and 61 after an `EMIT "..." and`, and anchoring to the start missed a
    third of them.

    Menu bodies need no test of their own: a `MENU` header clears the section, and a menu
    declares `TITLE`, `OPTIONS` and `INVALID` rather than `DO` or `ON_ERROR`, so nothing
    inside one is ever in an action section. The first version instead built a set of menu
    body line *text* and skipped any line equal to one -- so a real `STOP_TURN` in a `DO:`
    block vanished whenever some menu in the same file held an identically-worded line,
    which for a line whose whole content is `STOP_TURN` is most files. Raised in review
    and reproduced: one unit, one menu, both holding that line, halt count zero.

    A positional `in_menu` flag replaced it and then changed nothing measurable -- same
    tests, same 1109 -- because the section rule already excludes those lines. It is gone
    rather than kept: a guard that cannot be shown to do anything reads as evidence it can.
    """
    halts = 0
    emitted = False
    section: Optional[str] = None
    for line in text.splitlines():
        action = _action(line)
        if not action:
            continue
        if _block_header(line) is not None:
            section, emitted = None, False     # a new UNIT or MENU closes the last section
            continue
        # A header is the whole line, `DO:` alone — not a line that merely begins with a
        # word and a colon, which `EMIT: "..."` would satisfy while being an action.
        if action.endswith(":") and " " not in action:
            section, emitted = action[:-1], False
            continue
        if section not in _ACTION_SECTIONS:
            continue
        # `_emit_on` rather than a prefix test, so this scan and the emit scan agree on
        # what an emit is. A prefix test accepts `EMIT_MENUX` and `EMIT_MENU 9Invalid`,
        # neither of which the validator recognises -- and accepting one here *suppresses*
        # the halt that follows it, so a malformed line silently lowered the count in the
        # direction that flatters the measurement. Zero instances in the tree today; fixed
        # because the two scans disagreeing is the defect, not the frequency.
        # Raised in review.
        if _emit_on(action) is not None:
            emitted = True
        elif _STOP_TURN in action:
            halts += not emitted
            emitted = False
    return halts


def _count_reached(reached: Set[str], files: Dict[str, str],
                   unconditional: "collections.Counter"
                   ) -> Tuple[Dict[str, int], "collections.Counter"]:
    """The three numbers for one workflow's reachable files, plus the menus behind them.

    Split from the walk so each stays inside this repo's local-variable cap, and because
    counting one workflow and aggregating across all of them are separate jobs.
    """
    menus: collections.Counter = collections.Counter()
    stops = non_stops = halts = 0
    for rel in sorted(reached):
        halts += _halts_outside_menus(files[rel])
        for site in emit_sites(files[rel]):
            menus[site.menu] += 1
            stops += site.waits
            non_stops += not site.waits
            if not site.conditional:
                unconditional[site.menu] += 1
    # The menus are returned beside the counts rather than smuggled through the same dict:
    # a first version put them under a `_menus` key and unpacked the whole thing into the
    # dataclass, which took the private key with it.
    return ({"stop_sites": stops, "non_stop_sites": non_stops, "halt_sites": halts,
             "distinct_menus": len(menus)}, menus)
# @cpt-end:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-count


# @cpt-begin:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-walk
def _definitions(files: Dict[str, str]) -> Dict[str, List[str]]:
    """``menu name -> the files that define it``, across the whole tree."""
    where: Dict[str, List[str]] = {}
    for rel in sorted(files):
        for name, _ in menu_blocks(files[rel]):
            where.setdefault(name, []).append(rel)
    return where


# @cpt-end:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-walk


# @cpt-begin:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-warn
def _listed(entries: List[str]) -> str:
    """The first few entries, each delimited, for a sentence a person reads.

    `json.dumps` per entry rather than a bare `", ".join`: an entry containing `, ` would
    otherwise read as two, and a hand-rolled pair of quotes is what a `"` in the value
    closes early -- which is how this forgery walked back in through its own fix once
    already. The entries are stripped before they get here; this is about the boundary
    between them, which a list gives a consumer structurally and prose does not.
    """
    return ", ".join(json.dumps(entry) for entry in entries[:5])


def _warn_about_gaps(surface: GateSurface) -> None:
    """Say out loud whatever would make the numbers a floor rather than a total.

    Warned as well as carried on the result: a caller reading only the counts would take
    an under-count for an improvement.
    """
    if surface.unreadable:
        # Named, not just counted. "3 files could not be read" sends a reader to find out
        # which; and this is the one of the three lists whose entries are filenames, so it
        # is the one where a `, ` inside an entry could read as two entries -- which is
        # what `_listed` is for. A target matches a pattern with no comma in it and a menu
        # name is a single token, so for those the delimiter is belt and braces.
        logger.warning("gate surface: %d file(s) under %s could not be read, so every "
                       "count below is a floor rather than a total: %s",
                       len(surface.unreadable), surface.tree, _listed(surface.unreadable))
    if surface.missing_loads:
        logger.warning("gate surface: %d LOAD target(s) under %s are not in the tree, so "
                       "every menu behind them is missing from the count: %s",
                       len(surface.missing_loads), surface.tree,
                       _listed(surface.missing_loads))
    if surface.duplicate_menu_definitions:
        logger.warning("gate surface: %d menu name(s) under %s are defined in more than "
                       "one file: %s", len(surface.duplicate_menu_definitions),
                       surface.tree, _listed(surface.duplicate_menu_definitions))


# @cpt-end:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-warn


# @cpt-begin:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-walk
def walk(root: Path) -> GateSurface:
    """The reachable gate surface of every workflow under ``root``.

    Deterministic: the same tree walked twice gives the same numbers, which is the whole
    reason this replaced running the product and counting what it said. Files are read in
    sorted order and every count is a sum over a set, so nothing depends on filesystem
    ordering.

    Raises ``FileNotFoundError`` when ``root`` has no `workflows/` directory. A root
    pointed one level too high used to return a clean empty surface with no warning, which
    is this module's own stated failure -- an under-count that reads as a finished walk.
    Nothing in the result distinguishes it from a tree that genuinely declares no gates,
    so the caller cannot be left to tell the two apart.
    """
    if not (root / "workflows").is_dir():
        raise FileNotFoundError(
            f"gate surface: {_said(root)} has no workflows/ directory, so there is no "
            "surface to walk; an empty result here would be indistinguishable from a "
            "tree that declares no gates")
    files, unreadable = _read_tree(root)
    surface = GateSurface(tree=_said(root), unreadable=unreadable,
                          missing_loads=_missing_loads(files))
    defined = _definitions(files)
    surface.distinct_menu_definitions = len(defined)
    surface.duplicate_menu_definitions = sorted(
        _reported(name) for name, where in defined.items() if len(where) > 1)

    reach: collections.Counter = collections.Counter()
    unconditional: collections.Counter = collections.Counter()
    for workflow in sorted(f for f in files if f.startswith("workflows/")):
        reached = _closure(workflow, files)
        counted, menus = _count_reached(reached, files, unconditional)
        surface.workflows.append(WorkflowSurface(
            workflow=workflow, files_reached=len(reached), **counted))
        for name in menus:
            reach[name] += 1

    surface.menu_reachability = dict(reach.most_common())
    surface.unconditional = dict(unconditional.most_common())
    _warn_about_gaps(surface)
    return surface
# @cpt-end:cpt-studio-algo-developer-experience-gate-surface:p1:inst-surface-walk
