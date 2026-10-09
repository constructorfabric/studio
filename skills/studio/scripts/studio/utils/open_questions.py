"""Project a run's outstanding open questions from the decision log.

When the autonomous default cannot resolve a gate from the plan and is not safe to
proceed, the gate is parked as an **open question** -- a ``gate`` event of kind
``open-question`` carrying the gate's ``decision_key`` and the reason it could not be
ruled. This reads those events back into a register: which keyed questions are still
outstanding, so a plan item that declares it waits on one (``(needs: key)``) can be held
incomplete until the question is answered.

**A reader over recorded evidence, never a second writer.** The producer is whoever
records the deferral -- today the ``cfs gate-log`` command, later the autonomous audit
write-path -- not this module. A question is **closed** when a later event resolves the
same key: ``plan-resolved`` or ``blocking-confirmed`` always, and ``exception-asked`` only
when its ``status`` is exactly ``resolved``. That last one is conditional because the kind
records *why* the gate asked rather than an answer -- an ask logged ``absent`` or
``ambiguous`` never produced one, so the question stays open, which is the fail-safe
direction. Answered questions drop out, so the register holds only what is still open at the
moment it is read.

**Scoped to one run.** The decision log is **shared across runs**, so a read must be confined
to the run being verified: otherwise one run answering a question with the same ``decision_key``
would clear a *different* run's blocker, and that run's unfinished item would complete. The
register therefore reads only events stamped with a single ``run_id`` — the run it is called
from by default — never the whole log.

**Only keyed questions are tracked.** A deferral that recorded no ``decision_key`` cannot
be named by an item, so it cannot block one; that is not an error, only not addressable,
and it is left out of the register. Re-read on every call, like the plan readers: a
question answered mid-run has to drop out on the next read.

**Known limitation — log rotation.** The register is derived by replaying the log, which the
reader serves from the live segment plus one rotated segment. If a question's opening *and* its
answer both age out — it survives *two* rotations before being answered, so both events leave
the retained segments — the key is no longer replayed. Because the completion check asks whether
a key was **answered**, a key the replay no longer reports reads as *not answered*, so its item
is **held, not completed** — the over-cautious, fail-safe direction, never a silent pass (the
same property an absent or unreadable log has). In one run that needs a very large volume of gate
events; a durable open-question store that does not re-derive from the rotating log is the
follow-up, tracked separately rather than built here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Set

from . import decision_log

# @cpt-begin:cpt-studio-algo-execution-plans-open-questions:p1:inst-oq-kinds
#: The ``gate`` event kind a parked (deferred) question is recorded under.
OPEN_QUESTION_KIND = "open-question"

#: The kinds that ANSWER a question outright: a later event of one of these for the same
#: key closes it. ``auto-proceeded`` is deliberately excluded -- proceeding on a default is
#: not an answer to the question that was raised, and leaving the question open is the
#: fail-safe direction (toward holding the dependent item, never toward a silent pass).
_ANSWERED_KINDS = ("plan-resolved", "blocking-confirmed")
# @cpt-end:cpt-studio-algo-execution-plans-open-questions:p1:inst-oq-kinds


# @cpt-begin:cpt-studio-algo-execution-plans-open-questions:p1:inst-oq-kinds-asked
#: The kind that answers only when the ask actually produced an answer. ``exception-asked``
#: records that the plan could not resolve the gate, so the gate asked the user -- which is
#: the *reason* for asking, not by itself an answer. It becomes an answer when that ask
#: resolved. Without this, a question the user answered in person leaves no trace the
#: register can see, and its dependent item blocks on a decision that was in fact made.
#: The status guard keeps the fail-safe direction: an ask recorded ``absent`` or
#: ``ambiguous`` never resolved, so the question stays open.
_ANSWERED_WHEN_RESOLVED = ("exception-asked",)

#: The one ``GATE_STATUSES`` value that means the look-up produced an answer.
_RESOLVED_STATUS = "resolved"
# @cpt-end:cpt-studio-algo-execution-plans-open-questions:p1:inst-oq-kinds-asked


# @cpt-begin:cpt-studio-algo-execution-plans-open-questions:p1:inst-oq-model
@dataclass(frozen=True)
class OpenQuestion:
    """One outstanding open question: the key it is addressable by, the gate it was
    raised on, and the reason it could not be resolved."""

    key: str
    gate: str
    reason: str


@dataclass(frozen=True)
class OpenQuestions:
    """The run's open-question state when the log was read, by ``decision_key``.

    One shape for the whole register: ``outstanding`` maps each still-open key to its question,
    and ``answered`` holds the keys a later event settled. ``is_answered`` is what a completion
    check asks -- an item that waits on a key may complete **only** if that key was answered;
    a key that is still outstanding *or* was never raised is not answered, so it blocks. That
    makes an absent or unreadable log fail safe: no key reads as answered, so every declared
    dependency holds, never a silent pass.
    """

    outstanding: Dict[str, OpenQuestion] = field(default_factory=dict)
    answered: Set[str] = field(default_factory=set)

    def is_open(self, key: str) -> bool:
        """Whether ``key`` names a question that is still outstanding."""
        return key in self.outstanding

    def is_answered(self, key: str) -> bool:
        """Whether ``key`` names a question that was raised and settled (resolved, not re-opened).

        A never-raised key is **not** answered, so a dependency on it blocks -- the fail-safe
        direction: a declared dependency must be shown addressed, not assumed irrelevant.
        """
        return key in self.answered
# @cpt-end:cpt-studio-algo-execution-plans-open-questions:p1:inst-oq-model


# @cpt-begin:cpt-studio-algo-execution-plans-open-questions:p1:inst-oq-read
def read_open_questions(path: Optional[Path] = None, *,
                        run_id: Optional[str] = None) -> OpenQuestions:
    """The keyed open questions still outstanding for one run in the decision log at ``path``.

    Reads the ``gate`` events oldest-first (the log reader's contract) and replays them:
    an ``open-question`` event opens its key, a later answering event for the same key
    closes it, and a re-deferral opens it again -- so the final map is what is open now.
    An answering event is one of ``_ANSWERED_KINDS``, or an ``exception-asked`` whose
    ``status`` is ``resolved`` -- a gate the plan could not answer and the user then did.
    Re-reads every call; never caches. A deferral with no ``decision_key`` is skipped
    (not addressable by an item, so not a blocker), never treated as an error.

    The read is confined to a **single run** (``run_id``, defaulting to the run this is called
    from). The log is shared across runs, so an unscoped read would let one run's answer clear a
    different run's blocker -- the register must never do that.
    """
    # Truthiness, not `is not None`: an **empty** run_id must also fall back to the current run,
    # because the log reader treats an empty-string filter as "no filter" and would read every
    # run — silently disabling the scoping. So `""` scopes to the current run, never to all runs.
    scope = run_id or decision_log.current_run_id()
    outstanding: Dict[str, OpenQuestion] = {}
    answered: Set[str] = set()
    for obj in decision_log.read_events(path, event="gate", run_id=scope):
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            continue
        key = payload.get("decision_key")
        if not isinstance(key, str) or not key or key == decision_log.UNSPECIFIED:
            continue
        kind = payload.get("kind")
        # Two events mean the same thing -- this question is live again -- so they take one
        # branch. A **re-deferral** parks it afresh. An **ask that produced nothing** is not
        # merely "no new answer": the question was put again and went unresolved, so any
        # earlier answer is withdrawn. Without the second, a key answered by an earlier
        # resolved ask stays answered through a later failed one, and keys like
        # `interaction_mode` are asked repeatedly -- a dependent item would complete on a
        # resolution that had since fallen through.
        reopened = kind == OPEN_QUESTION_KIND or (
            kind in _ANSWERED_WHEN_RESOLVED and payload.get("status") != _RESOLVED_STATUS)
        if reopened:
            outstanding[key] = OpenQuestion(
                key=key,
                gate=str(payload.get("gate", "")),
                reason=str(payload.get("why", "")),
            )
            answered.discard(key)
        elif kind in _ANSWERED_KINDS or kind in _ANSWERED_WHEN_RESOLVED:
            outstanding.pop(key, None)
            answered.add(key)
    return OpenQuestions(outstanding=outstanding, answered=answered)
# @cpt-end:cpt-studio-algo-execution-plans-open-questions:p1:inst-oq-read
