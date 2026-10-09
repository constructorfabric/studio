"""Verify a run against its plan before it may report success.

The close of a run: read the deliverable items the approved plan declares, read the verdicts
the run recorded for them, reconcile the two, and refuse to call the run complete if any item
is unsatisfied or unstated. It is **not** a second judgement engine -- it does not decide
whether an item is met. The run states each verdict (in v1 every item is an explicit
statement); this tallies those statements and enforces that every item has a satisfying one.

Each item's verdict is recorded to the decision log through ``record_verification``, so the
close is auditable and the session summary (a later increment) can be projected from the
ledger rather than re-constructed.

An item may also declare that it **waits on an open question** (a ``(needs: key)`` marker). The
open-question check is scoped to **one run** -- the decision log is shared across runs, so it
must be, or a different run's answer would clear this run's blocker. That scoping has a
consequence worth stating plainly: run **stand-alone** against a plan, with no ``--run-id``, the
check scopes to *this* command's run, which answered no questions -- so **every** ``(needs: …)``
item blocks and the run reports incomplete. That is the fail-safe direction (it refuses to pass
rather than passing on a dependency it cannot confirm), but it means a plan using the marker
cannot be shown complete stand-alone: meaningful enforcement needs the close to run **in the
executing run** (the end-of-run wiring, a later increment) or that run's id passed with
``--run-id``. The verdict checks above do not need this and work stand-alone as before.

Exit codes follow the project contract (``architecture/specs/cli.md``): **0** the run is
complete, **2** a check FAILED (an item is not satisfied, not stated, or its criteria could
not be read), **1** a fault (the plan or the verdicts file could not be read). A fault is kept
apart from a failed check so CI keying on 2 for an incomplete run is not confused by a close
that could not run.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..utils import decision_log, open_questions, plan_items, ui
from ..utils.plan_decisions import PLAN_FILE, _bounded, _load_plan

#: The run writes its verdicts here, beside the plan's own ``plan.toml`` by default.
# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-model
VERDICTS_FILE = "verdicts.toml"

#: Where a plan records that its decomposition was authorised, and the one value that counts.
#: The same field and value the phase dispatcher requires before it will run any phase -- a run
#: must not be able to report success against a plan no dispatcher would have run in the first
#: place. A plan carrying no `approval_status` at all predates approvals being recorded; that is
#: still not an approval, and saying so names the remedy rather than leaving a bare refusal.
_APPROVAL_TABLE = "plan"
_APPROVAL_FIELD = "approval_status"
_APPROVED = "approved"

#: The array a verdicts file declares its per-item verdicts in.
_VERDICTS_TABLE = "verdicts"

_COMMAND = "verify-completion"


@dataclass(frozen=True)
class _Verdict:
    """One recorded verdict and the evidence it rests on."""

    verdict: str
    evidence: str


@dataclass(frozen=True)
class Verdicts:
    """The verdicts a run recorded, keyed by ``(phase, bounded-text)`` -- phase ``None`` for an
    entry that names no phase.

    Keying by phase as well as text is what lets the **same criterion in two phases** receive
    two separate answers; a phase-less entry answers a criterion only when that text is unique
    across the plan (resolved in ``_verdict_for``). ``duplicates`` names keys a file answered
    more than once: a conflicting double-answer is no trustworthy answer, not the last one.
    ``error`` is set when the file itself could not be read, which is a fault, not a verdict.
    ``declared_run_id`` is the run the file says produced it -- the scope hint, trusted only
    after the cross-check in ``_scope_from_verdicts``.
    """

    declared_run_id: Optional[str] = None
    by_key: Dict[Tuple[Optional[int], str], _Verdict] = field(default_factory=dict)
    duplicates: Set[Tuple[Optional[int], str]] = field(default_factory=set)
    error: Optional[str] = None


@dataclass(frozen=True)
class Completion:
    """One result shape for every outcome of a completion check.

    ``status`` is ``COMPLETE``, ``INCOMPLETE`` or ``ERROR``; ``exit_code`` is the contract
    code it maps to. ``unsatisfied``, ``unstated`` and ``blocked_on_question`` name the items
    that block completion -- the last being items that still wait on an unanswered open
    question, which cannot be shown done however their verdict reads; ``read_problems`` carries
    the plan phases whose criteria could not be read (so an item may be missing entirely);
    ``applicable`` is ``False`` only when the plan declares no items at all, a vacuous pass that
    is stated rather than hidden.
    """

    status: str
    exit_code: int
    checked: int = 0
    unsatisfied: List[str] = field(default_factory=list)
    unstated: List[str] = field(default_factory=list)
    blocked_on_question: List[str] = field(default_factory=list)
    read_problems: List[str] = field(default_factory=list)
    phases_without_criteria: List[int] = field(default_factory=list)
    unmatched_verdicts: List[str] = field(default_factory=list)
    applicable: bool = True
    message: str = ""


# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-model

# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-run-scope
#: The key a verdicts file names the run that produced it under.
_RUN_ID_FIELD = "run_id"


def _declared_run_id(data: Dict[str, Any]) -> Optional[str]:
    """The run a verdicts file says produced it, or ``None``. A hint, never yet trusted."""
    raw = data.get(_RUN_ID_FIELD)
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


def _scope_from_verdicts(verdicts: Verdicts, log_path: Optional[Path]) -> Optional[str]:
    """The verdicts file's own run id, used only while it still matches the shared file.

    The scope must match the **evidence being checked**, and the verdicts file is that
    evidence: the run writes it immediately before this check and nothing else produces it.

    Taking that id on its word would be **worse than taking none**. A stale verdicts file left
    in a plan directory names an older run, and scoping to it makes that run's answers visible
    to this one: measured, an item this run never answered reports COMPLETE where it is
    otherwise held. So the id is used only while it still equals ``current_run_id``.

    **What this check does and does not establish.** An earlier version of this docstring
    called the comparison "two independent artifacts agreeing". That was wrong, and review
    caught it. The gate events are stamped by ``record()`` from the **same** project-wide
    run-id file this compares against, so the two sources are one source read twice -- not
    independent witnesses. The comparison therefore detects a verdicts file left behind by an
    **earlier** run (its id no longer matches what the file says now) and nothing more. It
    does **not** establish that the events it will go on to read belong to the run named,
    because a ``run-start`` landing mid-run restamps later events without changing either side
    of this comparison. That remaining hole is tracked separately and blocks the close being
    relied on as a gate.

    No grammar check is needed: equality with ``current_run_id`` is the validation, because
    that value is either the validated shared-file id or this process's own.
    """
    declared = verdicts.declared_run_id
    if declared is None:
        return None
    return declared if declared == decision_log.current_run_id(log_path) else None
# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-run-scope


# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-read-verdicts
def _read_verdicts(path: Path) -> Verdicts:
    """The verdicts a run recorded, or a ``Verdicts`` carrying the reason the file failed.

    Reuses the plan loader's fail-loud TOML read rather than a second one. A file that
    declares no ``verdicts`` array is not an error -- it means the run stated nothing, so
    every item will read as unstated; a ``verdicts`` that is present but not an array is the
    author's defect and is reported.
    """
    data, reason, _verdict = _load_plan(path)
    if data is None:
        return Verdicts(error=reason)
    entries = data.get(_VERDICTS_TABLE)
    if not isinstance(entries, list):
        if _VERDICTS_TABLE in data:
            return Verdicts(error=(f"`{_VERDICTS_TABLE}` in {path.name} is not an array, "
                                   "so no verdicts can be read"))
        return Verdicts(declared_run_id=_declared_run_id(data))
    by_key: Dict[Tuple[Optional[int], str], _Verdict] = {}
    duplicates: Set[Tuple[Optional[int], str]] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        item = _bounded(entry.get("item", ""))
        if not item:
            continue
        raw_phase = entry.get("phase")
        # A `bool` is an `int` subclass; `phase = true` is not a phase number.
        phase = raw_phase if isinstance(raw_phase, int) and not isinstance(raw_phase, bool) else None
        key = (phase, item)
        if key in by_key:
            duplicates.add(key)
        by_key[key] = _Verdict(
            verdict=_bounded(entry.get("verdict", "")),
            evidence=_bounded(entry.get("evidence", "")),
        )
    return Verdicts(declared_run_id=_declared_run_id(data), by_key=by_key, duplicates=duplicates)


# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-read-verdicts

# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-item
def _verdict_for(item: plan_items.PlanItem, verdicts: Verdicts,
                 text_counts: Dict[str, int]) -> Tuple[str, str, str]:
    """The verdict, evidence, and a **reason tag** for one item, fail-safe toward not-satisfied.

    Looks the answer up by ``(phase, text)`` first; falls back to a phase-less entry only when
    this criterion's text is **unique** across the plan, since a phase-less answer to a text
    that appears in several phases cannot say which phase it means. The reason -- ``missing``,
    ``conflict``, ``unrecognised``, ``ambiguous`` or ``ok`` -- is returned explicitly so the
    caller classifies on it, never on the evidence text (which is author-controlled).
    """
    phased = (item.phase, item.text)
    if phased in verdicts.duplicates:
        return "not-satisfied", "conflicting verdicts were recorded for this item", "conflict"
    found = verdicts.by_key.get(phased)
    if found is None:
        phaseless = (None, item.text)
        if phaseless in verdicts.duplicates:
            return "not-satisfied", "conflicting verdicts were recorded for this item", "conflict"
        if phaseless in verdicts.by_key:
            if text_counts.get(item.text, 0) > 1:
                return ("not-satisfied", "a verdict with no phase is ambiguous because this "
                        "criterion appears in more than one phase", "ambiguous")
            found = verdicts.by_key[phaseless]
    if found is None:
        return "not-satisfied", "no verdict was recorded for this item", "missing"
    if found.verdict not in decision_log.VERIFICATION_VERDICTS:
        # A verdict outside the enumerated set is a typo or an invented value, not a pass:
        # accepting it would let `verdict = "done"` slip an unchecked item through.
        return "not-satisfied", f"unrecognised verdict {found.verdict!r}", "unrecognised"
    return found.verdict, found.evidence, "ok"


# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-item

# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-assess
def _reconcile(items: plan_items.PlanItems, verdicts: Verdicts,
               register: open_questions.OpenQuestions,
               log_path: Optional[Path]) -> Tuple[List[str], List[str], List[str]]:
    """Record one verification event per item and split the blockers into
    (unsatisfied, unstated, blocked_on_question).

    An item that still waits on an **outstanding open question** cannot be shown done however
    its verdict reads, so that check comes first and overrides the verdict: it is recorded
    ``not-satisfied`` with reason ``blocked-on-question``. Otherwise an item with no usable
    answer (``missing``/``ambiguous``) is *unstated*; one answered wrongly
    (``conflict``/``unrecognised``/an explicit not-satisfied) is *unsatisfied*. The split is on
    the reason tag, never on the evidence text.
    """
    unsatisfied: List[str] = []
    unstated: List[str] = []
    blocked: List[str] = []
    text_counts = Counter(item.text for item in items.items)
    for item in items.items:
        key = item.depends_on_question
        if key is not None and not register.is_answered(key):
            # Block unless the dependency's question was answered: a key still outstanding OR one
            # never raised both leave the declared dependency unaddressed, so the item is not done.
            why = ("is still outstanding" if register.is_open(key)
                   else "was never raised, so this declared dependency is unaddressed")
            # Record the run's OWN verdict alongside the block so an audit can tell "blocked, but the
            # work passed" from "blocked, never attempted". The block still overrides -- the primary
            # verdict stays not-satisfied and the item stays in `blocked` -- completion is unchanged.
            own_verdict = _verdict_for(item, verdicts, text_counts)[0]  # the run's own belief
            decision_log.record_verification(
                item.text, "not-satisfied",
                f"waits on the open question {key!r}, which {why}", item.phase,
                own_verdict=own_verdict, command=_COMMAND, path=log_path)
            blocked.append(item.text)
            continue
        verdict, evidence, reason = _verdict_for(item, verdicts, text_counts)
        decision_log.record_verification(item.text, verdict, evidence, item.phase,
                                         command=_COMMAND, path=log_path)
        if verdict == "not-satisfied":
            (unstated if reason in ("missing", "ambiguous") else unsatisfied).append(item.text)
    return unsatisfied, unstated, blocked
# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-assess


# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-assess
def _unmatched(items: plan_items.PlanItems, verdicts: Verdicts) -> List[str]:
    """Verdict keys that answer no plan item -- by exact ``(phase, text)``, or by text for a
    phase-less entry. Reported, never counted against completion."""
    item_keys = {(item.phase, item.text) for item in items.items}
    item_texts = {item.text for item in items.items}
    unmatched: List[str] = []
    for key in verdicts.by_key:  # the keys are (phase, text); the values are not needed here
        phase, text = key
        matched = text in item_texts if phase is None else key in item_keys
        if not matched:
            unmatched.append(text if phase is None else f"{text} (phase {phase})")
    return sorted(unmatched)
# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-assess


# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-assess
# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-approval
def _approval_refusal(plan_dir: Path) -> Optional[Completion]:
    """Why this plan may not report success, or ``None`` when it was approved.

    The close is what stands between a run and declaring itself done, so it must not pass a
    plan nobody authorised. The phase dispatcher already refuses to run a phase for one; a
    close that accepts the same plan would let the work be reported complete without ever
    having been allowed to start.

    Not knowing whether a plan was approved is different from knowing it was not, so the two
    outcomes carry different exit codes: a plan that will not load here is a **fault**, while
    one that loads and lacks the field is a failed check.
    """
    data, _reason, _verdict = _load_plan(plan_dir / PLAN_FILE)
    if data is None:
        # Review finding: this used to return `None`, on the reasoning that an unreadable plan
        # is "a fault the caller reports". The caller cannot report it -- `read_plan_items`
        # already read the file successfully, which is the only way control reaches here, so
        # the second read failing is a race the caller has no second chance to see. `None`
        # means approved, so a plan that became unreadable between the two reads was silently
        # treated as authorised and could report COMPLETE. The intent was right and the
        # mechanism was not; the fault is now returned instead of described.
        return Completion(status="ERROR", exit_code=1,
                          message=("the plan could not be read to check its approval; it was "
                                   "readable a moment earlier, so it changed mid-check"))
    table = data.get(_APPROVAL_TABLE)
    status = table.get(_APPROVAL_FIELD) if isinstance(table, dict) else None
    if status == _APPROVED:
        # Compared **exactly**, because the dispatcher compares exactly: both
        # `plan-native-dispatch.md` and `plan-compiler-dispatch.md` refuse a phase unless
        # `plan.approval_status != "approved"` is false, and `plan-compile.md` only ever
        # writes the literal `"approved"`. Accepting `" Approved "` here would let a
        # hand-edited plan report success that the dispatcher would never have let start --
        # a close more permissive than the gate it is meant to be closing behind.
        return None
    # A failed check, not a fault: the plan is readable, it simply was never authorised.
    # Exit 2 keeps it with the other "this run may not report success" causes, so a caller
    # already keying on 2 needs no change.
    if status is None:
        return Completion(status="INCOMPLETE", exit_code=2, message=(
            f"this plan records no {_APPROVAL_TABLE}.{_APPROVAL_FIELD}, so it was written "
            "before approvals were recorded; re-run the decomposition gate to approve it"))
    return Completion(status="INCOMPLETE", exit_code=2, message=(
        f"this plan's {_APPROVAL_TABLE}.{_APPROVAL_FIELD} is {str(status)!r}, not "
        f"{_APPROVED!r}, so it may not report success"))
# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-approval


def _plan_refusal(plan_dir: Path, items: plan_items.PlanItems) -> Optional[Completion]:
    """Why this plan cannot be assessed at all, or ``None`` to carry on.

    Two refusals, kept together because both are answered before any verdict is read and both
    are about the plan rather than the run: it could not be read, or it was never approved.
    They map to different exit codes on purpose -- an unreadable plan is a fault the check
    could not perform, while an unapproved one is a check that failed.
    """
    if items.error is not None:
        return Completion(status="ERROR", exit_code=1,
                          message=f"the plan could not be read: {items.error}")
    return _approval_refusal(plan_dir)


def assess(plan_dir: Path, verdicts_path: Path, *, log_path: Optional[Path] = None,
           run_id: Optional[str] = None) -> Completion:
    """Reconcile the plan's items against the run's verdicts and decide if the run is complete.

    Reads the items the plan declares and the verdicts the run recorded, records one
    verification event per item, and reports ``INCOMPLETE`` if any item is not satisfied, not
    stated, or had criteria that could not be read. A plan or verdicts file that will not load
    is an ``ERROR`` (a fault), not an incomplete run.
    """
    items = plan_items.read_plan_items(plan_dir)
    refusal = _plan_refusal(plan_dir, items)
    if refusal is not None:
        return refusal
    verdicts = _read_verdicts(verdicts_path)
    if verdicts.error is not None:
        return Completion(status="ERROR", exit_code=1,
                          message=f"the verdicts file could not be read: {verdicts.error}")

    # Read the open-question register only when an item actually declares a dependency: a plan
    # that uses no `(needs: …)` marker must not pay a log read, and behaves exactly as before.
    # The read is scoped to one run (`run_id`, defaulting to the current run), so another run's
    # answer can never clear this run's blocker.
    # Scope precedence, widest trust first: what this was **told** (`--run-id`), then the run the
    # verdicts file says produced it -- but only while `_scope_from_verdicts` finds that id still
    # current -- and otherwise this process's own id. That middle tier detects a verdicts file left
    # by an EARLIER run; it does not establish that the events read belong to the run named, since
    # both sides of its comparison come from the same shared file. See its docstring. The shared run-id file is still
    # never trusted ALONE: it is project-wide and mutable, so a second `run-start` in the same
    # checkout replaces it, and a later command of the *first* run would read the second run's id and
    # with it the second run's answers. Since an item blocks only while its key is unanswered, that
    # shows a run complete on an answer it never gave. The per-process fallback matches nothing this
    # run did not record, so an unscoped check fails toward INCOMPLETE. A report may approximate; a
    # gate may not.
    scope = (run_id
             or _scope_from_verdicts(verdicts, log_path)
             or decision_log.process_run_id())
    register = (open_questions.read_open_questions(log_path, run_id=scope)
                if any(item.depends_on_question for item in items.items)
                else open_questions.OpenQuestions())
    unsatisfied, unstated, blocked_on_question = _reconcile(items, verdicts, register, log_path)
    unmatched = _unmatched(items, verdicts)

    if not items.items and not items.read_problems:
        return Completion(status="COMPLETE", exit_code=0, checked=0, applicable=False,
                          read_problems=list(items.read_problems),
                          phases_without_criteria=list(items.phases_without_criteria),
                          unmatched_verdicts=unmatched,
                          message="the plan declares no deliverable items to verify")
    # A phase whose criteria could not be read means an item may be missing entirely, so the
    # run cannot be shown complete -- fail-safe toward more friction, never toward a pass.
    status, code = ("INCOMPLETE", 2) if (unsatisfied or unstated or blocked_on_question
                                         or items.read_problems) else ("COMPLETE", 0)
    return Completion(
        status=status, exit_code=code, checked=len(items.items),
        unsatisfied=unsatisfied, unstated=unstated, blocked_on_question=blocked_on_question,
        read_problems=list(items.read_problems),
        phases_without_criteria=list(items.phases_without_criteria),
        unmatched_verdicts=unmatched,
        message=_message(status, len(items.items), unsatisfied, unstated,
                         blocked_on_question, items.read_problems),
    )


# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-assess

# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-report
def _message(status: str, checked: int, unsatisfied: List[str],
             unstated: List[str], blocked_on_question: List[str],
             read_problems: List[str]) -> str:
    """One human line summarising the outcome, naming the first blocking cause."""
    if status == "COMPLETE":
        return f"all {checked} item(s) satisfied"
    parts = []
    if unsatisfied:
        parts.append(f"{len(unsatisfied)} not satisfied")
    if unstated:
        parts.append(f"{len(unstated)} with no recorded verdict")
    if blocked_on_question:
        parts.append(f"{len(blocked_on_question)} waiting on an open question")
    if read_problems:
        parts.append(f"{len(read_problems)} phase(s) whose criteria could not be read")
    return "incomplete: " + "; ".join(parts)


def _payload(result: Completion) -> Dict[str, object]:
    """The structured result, one shape for every outcome."""
    return {
        "status": result.status,
        "checked": result.checked,
        "applicable": result.applicable,
        "unsatisfied": result.unsatisfied,
        "unstated": result.unstated,
        "blocked_on_question": result.blocked_on_question,
        "read_problems": result.read_problems,
        "phases_without_criteria": result.phases_without_criteria,
        "unmatched_verdicts": result.unmatched_verdicts,
        "message": result.message,
    }


# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-report

# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-report
def _say(payload: Dict[str, object]) -> None:
    """The human rendering: the headline, then each blocking item named."""
    if payload["status"] == "COMPLETE":
        ui.success(f"verify-completion: {payload['message']}")
        return
    ui.error(f"verify-completion: {payload['message']}")
    if payload["status"] == "ERROR":
        return
    for text in payload["unsatisfied"]:  # type: ignore[union-attr]
        ui.detail("not satisfied", str(text))
    for text in payload["unstated"]:  # type: ignore[union-attr]
        ui.detail("no verdict", str(text))
    for text in payload["blocked_on_question"]:  # type: ignore[union-attr]
        ui.detail("waits on an open question", str(text))


# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-report

# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-cli
def _parser() -> ui.JsonSafeArgumentParser:
    """The command's arguments.

    A ``JsonSafeArgumentParser`` so a bad argument under ``--json`` still emits a structured
    ERROR object on stdout rather than argparse's plain-text banner and a bare exit.
    """
    parser = ui.JsonSafeArgumentParser(
        prog="cfs verify-completion",
        description="Verify a run against its plan before it may report success. Reads the "
                    "plan's acceptance-criteria items and the verdicts the run recorded, and "
                    "exits 2 if any item is unsatisfied or unstated.")
    parser.add_argument("plan_dir", nargs="?", default=".",
                        help="the plan directory holding plan.toml (default: current dir)")
    parser.add_argument("--verdicts", default=None,
                        help=f"the verdicts file (default: {VERDICTS_FILE} under the plan dir)")
    parser.add_argument("--run-id", default=None,
                        help="the run whose open questions scope the check. The log is shared "
                             "across runs, so the check is confined to one. Scope is taken, widest "
                             "trust first, from this option; else from a run_id the verdicts file "
                             "declares, used only when it still matches the current run id; else "
                             "this command's own run. Stand-alone against a verdicts file naming "
                             "no run, this run has answered nothing, so every (needs: …) item "
                             "blocks and the run reports incomplete (fail-safe)")
    return parser


# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-cli

# @cpt-begin:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-cli
def cmd_verify_completion(argv: List[str]) -> int:
    """Run the completion check and return its contract exit code (0/1/2)."""
    args = _parser().parse_args(argv)
    plan_dir = Path(args.plan_dir)
    verdicts_path = Path(args.verdicts) if args.verdicts else plan_dir / VERDICTS_FILE
    if not (plan_dir / PLAN_FILE).exists():
        ui.result({"status": "ERROR", "message": f"no {PLAN_FILE} under {plan_dir}"},
                  human_fn=lambda d: ui.error(f"verify-completion: {d['message']}"))
        return 1
    result = assess(plan_dir, verdicts_path, run_id=args.run_id)
    payload = _payload(result)
    ui.result(payload, human_fn=_say)
    return result.exit_code

# @cpt-end:cpt-studio-algo-execution-plans-verify-completion:p1:inst-verify-cli