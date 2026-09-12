"""Studio gate-log command — record how one gate resolved, for a workflow that
resolved it without asking.

This is the write path a chat gate uses: PDSL reaches Python by
``RUN `{cfs_cmd} <subcommand>` ``, so a gate that auto-resolves runs this and the
event lands in the same local decision log every other command writes to.

Thin CLI wrapper around ``studio.utils.decision_log.record_gate``.

@cpt-flow:cpt-studio-flow-core-infra-cli-invocation:p1
"""

import logging
from typing import List, Optional

from ..utils.decision_log import (GATE_KINDS, GATE_PROVENANCE, GATE_STATUSES,
                                  UNSPECIFIED, GateRuling, capped_text,
                                  default_log_path, is_blank, logging_state,
                                  record_gate)
from ..utils.pdsl import GATE_TYPES
from ..utils.ui import ui

logger = logging.getLogger(__name__)


# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-gate-cmd
def cmd_gate_log(argv: List[str]) -> int:
    """Record one gate resolution in the local decision log.

    Exits 0 whether or not a line was written, and says which in ``recorded``.
    Logging is user-disableable and never authoritative: a gate's authority comes
    from its declared type, so a workflow must not treat "not recorded" as "not
    permitted" and stop working because a log is off or a disk is full.
    """
    p = ui.JsonSafeArgumentParser(
        prog="cfs gate-log",
        description="Record how one gate resolved in the local decision log.",
    )
    p.add_argument("--kind", required=True, choices=list(GATE_KINDS),
                   help="Which kind of resolution this was")
    p.add_argument("--gate", required=True, help="The gate's name, as written in its MENU block")
    p.add_argument("--declared-type", required=True, choices=list(GATE_TYPES),
                   help="The literal TYPE token from that gate's own MENU block, never a "
                        "paraphrase; the closed set the PDSL lint already validates against")
    p.add_argument("--decision-key", default=UNSPECIFIED,
                   help="The declared, stable identity this gate resolves by — never inferred "
                        "from wording")
    p.add_argument("--value", default=UNSPECIFIED, help="The answer, if one was found")
    p.add_argument("--provenance", default=UNSPECIFIED, choices=[*GATE_PROVENANCE, UNSPECIFIED],
                   help="Where the answer came from; the discriminator between a plan entry "
                        "and a ledger entry, so it is a closed set")
    p.add_argument("--status", default=UNSPECIFIED, choices=[*GATE_STATUSES, UNSPECIFIED],
                   help="Outcome of the lookup: resolved, absent or ambiguous")
    p.add_argument("--why", default=UNSPECIFIED, help="Why, in one line")
    p.add_argument("--cost-if-wrong", default=UNSPECIFIED,
                   help="What it costs if the decision is wrong; required for an autonomous ruling")
    # `parse_args_or_json_error`, not `parse_args`: JsonSafeArgumentParser raises
    # rather than exiting, so a bad `--kind` escaped as a traceback until this used
    # the helper that turns it into a reported ERROR and a clean code.
    args = ui.parse_args_or_json_error(p, argv)
    if args is None:
        return 2

    if is_blank(args.gate):
        return _refuse(args, "empty-gate")
    if args.status in _ASKED_STATUSES and args.kind in _RESOLVED_KINDS:
        return _refuse(args, "status-contradicts-kind")
    if args.kind in _RESOLVED_WITHOUT_A_HUMAN:
        if _is_unstated(args.cost_if_wrong):
            return _refuse(args, "missing-cost-if-wrong")
        if _is_unstated(args.decision_key):
            return _refuse(args, "missing-decision-key")

    recorded = record_gate(
        args.kind, args.gate, args.declared_type,
        GateRuling(decision_key=args.decision_key, value=args.value,
                   provenance=args.provenance, status=args.status,
                   why=args.why, cost_if_wrong=args.cost_if_wrong),
        command="gate-log",
    )
    ui.result(_payload(args, recorded=recorded,
                       reason=None if recorded else _not_recorded_reason()),
              human_fn=_human_gate_log)
    return 0
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-gate-cmd


#: A lookup that came back `absent` or `ambiguous` did not resolve: the frozen
#: contract is that both ask, and the ask is logged as an exception. So neither can
#: sit on a kind that claims the gate resolved -- `--kind auto-proceeded --status
#: absent` is a contradiction, and each vocabulary validating alone accepted it.
_ASKED_STATUSES = ("absent", "ambiguous")
_RESOLVED_KINDS = ("auto-proceeded", "plan-resolved")

#: The two documented reasons for refusing a ruling outright, kept next to the kinds
#: they apply to: a resolution nobody was asked about is only auditable if it says
#: what it answered and what being wrong costs. Both are refusals rather than
#: warnings because the CLI is the boundary a workflow crosses, and a record missing
#: either is auditable in name only.
#: Kinds that proceed without a human, so a stated cost-if-wrong is what makes them
#: auditable rather than merely recorded. The acceptance line names `auto-proceeded`
#: by example; `plan-resolved` is the same class -- an answer taken from the plan
#: without asking -- so it is held to the same rule, and the two that involve a
#: person plus the one that decides nothing are not.
# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-gate-cmd-result
_RESOLVED_WITHOUT_A_HUMAN = ("auto-proceeded", "plan-resolved")


def _payload(args, *, recorded: bool, reason: Optional[str]) -> dict:
    """One shape on every path, so a caller never branches on key presence.

    An earlier version emitted three different key sets -- `reason` only on a
    refusal, `logging_enabled` only on the others -- so a workflow keying on either
    got a `KeyError` for outcomes it had not hit yet.
    """
    # `capped_text`, not the raw argument. The echoed `gate` used to be the only
    # author-controlled field that left this command untransformed: the persisted
    # record was redacted and capped, and this copy of the same string was not --
    # so a gate name carrying an absolute home path kept the username on the way
    # out while losing it on the way in. A reported field is a sink like any other.
    return {"recorded": recorded, "logging_enabled": _logging_enabled(),
            "reason": reason, "gate": capped_text(args.gate), "kind": args.kind}


def _refuse(args, reason: str) -> int:
    """Report a refusal in the common shape and return the refusal code."""
    ui.result(_payload(args, recorded=False, reason=reason), human_fn=_human_refused)
    return 2
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-gate-cmd-result


# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-gate-cmd-reason
def _logging_enabled() -> Optional[bool]:
    """Whether logging is on, off by choice, or undeterminable.

    Two failure shapes, both of which used to be reported as "off by choice".
    `is_enabled()` fails closed and returns `False` for an unreadable sentinel,
    which sends someone looking for a setting they never changed -- so this reads
    `logging_state()`, which keeps the third state. And `Path.home()` raises
    `RuntimeError`, not `OSError`, when `$HOME` is unset and the uid has no passwd
    entry, as under `docker run --user 1234`; the writer degrades correctly, and
    this call is the only one in a command outside a guard, so reporting the
    outcome used to kill the command after the write had been handled properly.
    """
    try:
        return logging_state()
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("could not determine whether decision logging is enabled: %s", exc)
        return None


def _not_recorded_reason() -> str:
    """Name which of the four causes applies, since there are four, not two.

    An unreadable opt-out sentinel is its own cause: reporting it as `logging-off`
    asserts a choice the user may never have made.
    """
    enabled = _logging_enabled()
    if enabled is False:
        return "logging-off"
    if enabled is None:
        return "logging-state-unknown"
    if default_log_path() is None:
        return "no-log-location"
    return "write-failed"
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-gate-cmd-reason


# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-gate-cmd-format
def _for_display(value: str) -> str:
    """Strip what could forge a line in a transcript a person reads.

    `--gate` comes from a MENU block, which is author-controlled text. A value
    carrying a newline plus an escape sequence rendered as a second, invented
    outcome line -- `recorded blocking-confirmed for RealGate` for a gate that was
    never confirmed -- and a `\r` variant overwrote the real line instead.
    """
    flattened = " ".join("".join(
        ch if ch.isprintable() else " " for ch in value).split())
    if not flattened:
        return "(unnamed)"
    # Also bounded for display: the value is capped in the record, but a long one
    # rendered in full still lets a reader lose the sentence it sits inside.
    return flattened if len(flattened) <= 60 else flattened[:60] + "…"


def _human_gate_log(data: dict) -> None:
    """Print one line, distinguishing "logging is off" from "the write failed".

    ``ui.result`` calls this for its side effect and discards a return value, so a
    formatter that returns its text prints nothing -- which is how the first draft
    of this command exited 2 in silence.
    """
    # Quoted, so a reader can see where the author-controlled value ends. Stripping
    # the escapes stops a crafted name forging a *line*; the quotes stop it reading
    # as the sentence's own words.
    gate = f'"{_for_display(data["gate"])}"'
    ui.header("Gate Log")
    if data["recorded"]:
        ui.substep(f"recorded {data['kind']} for {gate}")
    else:
        ui.substep(f"not recorded ({data['kind']} for {gate}): {_REASON_TEXT[data['reason']]}")
        # The logging state, said out loud on the refusal paths. For the four
        # logging-state reasons the reason text already carries it, but a
        # validation refusal happens before the writer is reached, so `empty-gate`
        # rendered one identical line whether logging was on, off or
        # undeterminable -- information the JSON had and the human read did not.
        #
        # Stated rather than dropped from the payload, which was the other option
        # offered: `_payload` deliberately emits one shape on every path, because
        # an earlier version varied its keys and callers got a `KeyError` for
        # outcomes they had not hit yet. Removing a key to fix a rendering gap
        # would reintroduce that.
        if data["reason"] in _VALIDATION_REFUSALS:
            ui.substep(f"logging: {_LOGGING_STATE_TEXT[data['logging_enabled']]}")
    ui.blank()


def _is_unstated(value: str) -> bool:
    """Whether a field says nothing, however it was spelled.

    `.strip() == UNSPECIFIED` compared case-sensitively against the lowercase
    literal, so `Unspecified` — a plausible thing to type, and the constant's own
    display form capitalised — was visible text that satisfied `is_blank` and
    missed the sentinel check, and the guard that makes an autonomous ruling
    auditable was defeated by a shift key.
    """
    return is_blank(value) or value.strip().casefold() == UNSPECIFIED


#: Refusals decided before the writer is reached, so their reason says nothing
#: about whether logging was on. These are the ones that have to state it.
_VALIDATION_REFUSALS = ("empty-gate", "missing-cost-if-wrong", "missing-decision-key",
                        "status-contradicts-kind")

#: The tri-state in words. `None` is "unknown", never "off": calling an unreadable
#: opt-out state a choice sends someone looking for a setting they never changed.
_LOGGING_STATE_TEXT = {True: "on", False: "off by choice", None: "unknown"}

#: One line per reason, so the rendered text and the machine-readable `reason` can
#: never disagree about which of them applies.
_REASON_TEXT = {
    "logging-off": "decision logging is off",
    "logging-state-unknown": "whether logging is enabled could not be determined",
    "no-log-location": "there is no log location — this is not a Studio project",
    "write-failed": "the log could not be written",
    "missing-cost-if-wrong": "an autonomous ruling must state what it costs if wrong "
                             "— pass --cost-if-wrong",
    "empty-gate": "the gate must be named — pass --gate",
    "missing-decision-key": "an autonomous ruling must name the decision it answered "
                            "— pass --decision-key",
    "status-contradicts-kind": "a lookup that was absent or ambiguous did not resolve, "
                               "so it cannot be recorded as a kind that did",
}


def _human_refused(data: dict) -> None:
    """Print why a call was refused, rather than exiting 2 in silence."""
    _human_gate_log(data)
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-gate-cmd-format
