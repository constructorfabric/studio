"""Resolve a gate's decision key against the decisions a plan declares.

A gate that resolves without asking has to resolve against something. This is that
something: a ``[[gate_decisions]]`` array in a plan's own ``plan.toml``, and the lookup that
reads it.

**Exact match, or ask.** No normalisation, no prefix match, no similarity fallback. A plan
declaring ``ubuntu-24.04`` does not answer a gate asking about ``Ubuntu 24.04``. That looks
pedantic until you notice what the alternative buys: a workflow that proceeds confidently
on a value nobody wrote, and reports that it followed the plan. The contract this
implements says normalisation happens at plan authoring, where the user can see the
correction, and never at resolution -- because normalising here would readmit similarity
matching through the back door, which is the failure the whole contract exists to prevent.

Three outcomes, and only one of them proceeds:

``resolved``
    exactly one declaration answers the key.
``absent``
    the plan is silent on it.
``ambiguous``
    the plan spoke and did not decide -- two declarations for one key, or a policy that
    covers this dimension but has no row for this case.

The last distinction is the one the contract turns on, and it is easy to collapse by
accident. A plan that declares a policy over ``register.classification`` and has no row for
``urgent`` is *not* silent: it claimed that dimension and then failed to determine this
case. Reporting that as ``absent`` would file a gap in the plan under the same heading as a
question the plan never undertook to answer.

No ``@cpt-flow`` marker. The flow this serves is a gate consulting the plan before it asks,
and nothing calls this yet -- the enforcement that will is the increment after this one.
Claiming participation in a flow that does not reach here would be a traced claim with no
code behind it, which is the thing the marker exists to make checkable.
"""
from __future__ import annotations

import logging
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .decision_log import capped_text

logger = logging.getLogger(__name__)

# @cpt-begin:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-vocab
#: The plan's own filename inside a task's plan directory.
PLAN_FILE = "plan.toml"

#: The array a plan declares its decisions in, beside the existing ``[[phases]]``.
#:
#: ``gate_decisions``, not ``decisions``. A plain ``decisions`` key already exists in this
#: same file and is read as a *table* by `ralphex_export._resolve_lifecycle_action`, which
#: reaches for ``decisions.get("lifecycle_action")``. An array of tables arrives there as a
#: list, so a plan carrying this section would have raised `AttributeError` inside a shipped
#: export command -- for any plan whose lifecycle is `manual`. Their name was there first
#: and is in shipped code; this one was not written anywhere yet, so it moved.
DECISIONS_TABLE = "gate_decisions"

#: The key naming which declared enum a policy is keyed on. Written by the plan author,
#: never inferred: a policy whose dimension is guessed from the shape of the file is the
#: same inference this module refuses everywhere else, and it is the field that separates
#: "the plan is silent" from "the plan covers this and missed your case".
POLICY_DIMENSION = "dimension"

#: The table of ``enum value -> value`` rows a policy resolves through.
POLICY_TABLE = "policy"
# @cpt-end:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-vocab


# @cpt-begin:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-outcome
@dataclass(frozen=True)
class PlanLookup:
    """One lookup's outcome, in the frozen contract's own field names.

    ``decision_key -> value -> provenance -> status``, matching
    :class:`studio.utils.decision_log.GateRuling` field for field rather than paraphrasing
    it. The contract requires the ledger to share the plan's shape "distinguished by
    provenance -- not a second format to look in", so a lookup result that renamed any of
    these would make the reader map between two vocabularies to answer one question.

    ``why`` is for the caller to log, not for the resolver to decide with: it says which
    of the three outcomes was reached and on what evidence, so an ``ambiguous`` in a trail
    can be told from an ``absent`` without re-reading the plan.
    """

    #: The key as asked for. Echoed rather than re-derived, so a caller can match an
    #: outcome to its question -- with one exception it must know about: a key past the
    #: text cap comes back truncated, because every field of an outcome is bounded and an
    #: unbounded one here would be a sink for author text like any other. Keys that size
    #: are hostile input rather than real ones, and the truncation is visible.
    decision_key: str
    value: str
    provenance: str
    status: str
    why: str

    @property
    def resolved(self) -> bool:
        """Whether the caller may proceed without asking. Only one status qualifies."""
        return self.status == "resolved"
# @cpt-end:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-outcome


# @cpt-begin:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-open
#: The largest plan this module will read. A plan is written by a person and describes a
#: task; one past this size is not a plan this workflow produced, and reading it unbounded
#: would let a file in the task directory stall every gate that consults it.
_MAX_PLAN_BYTES = 1 * 1024 * 1024


def _read_failure(exc: OSError) -> str:
    """An OSError described so an operator can act on it.

    The class name alone says `OSError` and nothing else -- not which errno, not what the
    system said. Both are what someone diagnosing a failed gate reads first. The path is
    already named by the caller's message, and `strerror` is the system's text rather than
    the author's, so it is bounded on principle rather than because it is untrusted.
    """
    detail = _bounded(exc.strerror or "")
    return (f"the plan could not be read: {type(exc).__name__}"
            + (f" (errno {exc.errno})" if exc.errno is not None else "")
            + (f": {detail}" if detail else ""))


#: What a failed read means for the lookup: the plan being silent, or the plan being
#: broken. Returned as a value rather than inferred from the wording of the reason --
#: routing the contract's most important distinction through `reason.startswith(...)`
#: couples it to prose in another function, and a rephrase there silently reclassifies
#: every task without a plan. Raised in review; a test did catch that exact rephrase, but
#: a test catching one rewording is not the same as the routing being unable to drift.
SILENCE = "absent"
DEFECT = "ambiguous"


def _plan_bytes(plan_path: Path) -> Tuple[Optional[bytes], str, str]:
    """The plan file's bytes, or ``None`` and why they could not be had.

    Separated from parsing so each half stays inside this repo's return-count cap, and
    because the two failures are genuinely different: bytes that never arrived, and bytes
    that arrived and are not a plan.

    The bound is enforced by the read, not by the preceding ``stat()``. Those are two
    observations of one path, so a file replaced between them makes the first a lie -- the
    same shape review found on the decision log's segment bound. The ``stat()`` stays as a
    cheap filter that avoids opening a file already known to be too large; removing it
    changes no behaviour, which is exactly why it cannot be what the guarantee rests on.
    """
    fd, reason, verdict = _open_plan(plan_path)
    if fd < 0:
        return None, reason, verdict
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            # Judged on the descriptor being read, never on a prior look at the path --
            # the same reason the size bound below is enforced by the read.
            return None, (f"{plan_path.name} is not a regular file, so it is not a plan "
                          "this workflow wrote"), DEFECT
        if info.st_size > _MAX_PLAN_BYTES:
            return None, (f"{plan_path.name} is larger than any plan this workflow writes, "
                          "so it is not read"), DEFECT
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            data = handle.read(_MAX_PLAN_BYTES + 1)
    except OSError as exc:
        return None, _read_failure(exc), DEFECT
    finally:
        if fd >= 0:
            os.close(fd)
    if len(data) > _MAX_PLAN_BYTES:
        return None, (f"{plan_path.name} grew past the plan bound while being read, "
                      "so it is not used"), DEFECT
    return data, "", SILENCE


def _open_plan(plan_path: Path) -> Tuple[int, str, str]:
    """A descriptor on the plan, or ``-1`` and why there is none.

    Split from the read so each half stays inside this repo's return-count cap, and because
    the two are separate questions: whether a descriptor can be had at all, and whether
    what is behind it is a plan.
    """
    try:
        # `os.open` with `O_NONBLOCK`, not `Path.open`. A FIFO named plan.toml reports
        # `st_size == 0`, so it passes any size guard, and opening it blocking waits for a
        # writer that never comes -- no exception, no timeout, the gate simply never
        # returns. Raised in review as Critical and reproduced: six seconds in, nothing.
        # The flag makes the open itself return rather than wait, which is the only place
        # the guarantee can live: checking the path first and opening it second leaves the
        # window in which it becomes a FIFO between the two.
        return os.open(plan_path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)), "", SILENCE
    except FileNotFoundError:
        # A dangling symlink also raises this, and it is not the same fact: something is
        # sitting at that path. `lstat` sees the link itself, so the two are separable, and
        # only the genuinely-nothing case may be reported as the plan being silent.
        try:
            os.lstat(plan_path)
        except OSError:
            return -1, "the task has no plan.toml, so nothing is declared", SILENCE
        return -1, (f"{plan_path.name} is a symlink to something that is not there, so "
                    "the plan cannot be read"), DEFECT
    except OSError as exc:
        return -1, _read_failure(exc), DEFECT


# @cpt-end:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-open


# @cpt-begin:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-read
def _load_plan(plan_path: Path) -> Tuple[Optional[Dict[str, Any]], str, str]:
    """The plan's parsed contents, or ``None`` and the reason it could not be read.

    Re-read on every call, never cached. The contract's second amendment says a cached
    ``resolved`` is a stale authority: a plan edited mid-run has to take effect on the next
    lookup, and a resolver holding yesterday's answer is exactly the confidently-wrong
    behaviour this design refuses. The cost is one small file read per gate.

    The reason is returned rather than logged-and-swallowed, because the three outcomes are
    not interchangeable to a caller reading the trail later: "no such plan" and "this plan
    will not parse" both stop the gate, and only one of them is a defect.
    """
    data, reason, verdict = _plan_bytes(plan_path)
    if data is None:
        return None, reason, verdict
    try:
        import tomllib  # pylint: disable=import-outside-toplevel
    except ImportError as exc:  # pragma: no cover - 3.11+ ships tomllib
        return None, f"no TOML reader is available in this interpreter: {exc}", DEFECT
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        # Strictly, not with `replace`. Substituting U+FFFD for an undecodable byte makes a
        # plan saved in another encoding parse cleanly, and a value containing that byte
        # resolve -- mangled -- with `status == "resolved"`. That is this module proceeding
        # on a value nobody wrote, which is the one thing it exists to refuse. Raised in
        # review, and the same edit removes an `except (ValueError, UnicodeDecodeError)`
        # that could never fire twice over: `replace` never raises, and the second class is
        # a subclass of the first.
        return None, (f"the plan is not valid UTF-8 at byte {exc.start}, so a declaration "
                      "would resolve to bytes the author did not write"), DEFECT
    try:
        return tomllib.loads(text), "", SILENCE
    except ValueError as exc:
        return None, (f"the plan is not valid TOML, so no declaration can be trusted: "
                      f"{exc}"), DEFECT
# @cpt-end:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-read


# @cpt-begin:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-entries
def _declared_entries(plan: Dict[str, Any], decision_key: str) -> List[Dict[str, Any]]:
    """Every declaration whose key is exactly ``decision_key``.

    Exact string equality, and the only comparison in this module. No casefold, no strip,
    no separator folding: each of those is a similarity match wearing a smaller name, and
    the contract permits normalisation at plan authoring only.

    A malformed member -- a string where a table belongs, a table with no ``key`` -- is
    skipped rather than raising, because one bad entry must not hide the good declarations
    beside it. It is counted, though: the caller reports how many were skipped, so a plan
    silently losing half its decisions to a typo is visible rather than merely quiet.
    """
    table = plan.get(DECISIONS_TABLE)
    if not isinstance(table, list):
        return []
    return [entry for entry in table
            if isinstance(entry, dict) and entry.get("key") == decision_key]


def _section_is_malformed(plan: Dict[str, Any]) -> bool:
    """Whether the plan carries the section as something other than an array of tables.

    `gate_decisions = "oops"` is not the plan being silent about decisions -- it mentions
    them and then is unusable, which is the plan having spoken without deciding. Reporting
    it as `absent` tells an author their plan says nothing about a key they can see written
    in it, and files a broken section under the same heading as one that was never written.
    """
    return DECISIONS_TABLE in plan and not isinstance(plan.get(DECISIONS_TABLE), list)


def _malformed_count(plan: Dict[str, Any]) -> int:
    """How many members of the decisions array are not usable declarations."""
    table = plan.get(DECISIONS_TABLE)
    if not isinstance(table, list):
        return 0
    return sum(1 for entry in table
               if not isinstance(entry, dict) or not isinstance(entry.get("key"), str))
# @cpt-end:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-entries


# @cpt-begin:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-evidence
def _bounded(value: Any) -> str:
    """Author-controlled text, redacted and capped, for storing in a field.

    ``why`` and ``decision_key`` are sinks for text that arrives from a plan file and from
    a gate's own arguments, and a 200,000-character dimension name produced a
    200,097-character explanation. Reuses the ledger's transform rather than a second one,
    since two capping rules drift and only one of them gets the next fix.

    Imported at module level. An earlier version imported it inside the function with a
    comment claiming the package root's ``from .utils import *`` made a module-level import
    circular -- reasoning copied from the sibling module without checking that it applied
    here. It does not: raised in review, and both import paths work. A lazy import guarding
    an impossible cycle reads as evidence the cycle exists.
    """
    return capped_text(str(value))


def _said(value: Any) -> str:
    """The same text, quoted for reading inside a sentence.

    Two helpers rather than one with a flag: a stored field wants the text and a message
    wants it delimited, and an earlier version returned the quoted form for both and then
    stripped the quotes back off at the storing site -- which mangles any value that
    genuinely begins or ends with one.
    """
    return repr(_bounded(value))
# @cpt-end:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-evidence


# @cpt-begin:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-policy
def _policy_table_fault(table: Any, dimension: str) -> str:
    """Why a policy's rows cannot be consulted, or the empty string when they can.

    Split out to keep the resolver inside this repo's return-count cap, and because these
    are one question -- is there a usable table -- asked in three ways. A dimension with no
    table at all is reported separately from one with an empty table: the first claims to
    answer by rule and states no rule, the second states a rule that decides nothing, and
    an author fixes them differently.
    """
    if table is None:
        return (f"the declaration names {_said(dimension)} as its dimension and carries no "
                "policy table at all, so it claims to answer by rule and states no rule")
    if not isinstance(table, dict) or not table:
        return (f"a policy over {_said(dimension)} is declared with no usable rows, so it "
                "covers the dimension without deciding any case")
    return ""


def _resolve_policy(entry: Dict[str, Any], decision_key: str,
                    case: Optional[str]) -> PlanLookup:
    """One declaration that answers by rule rather than by value.

    The permitted indirection: a table keyed by an enum the plan *declares*, so a plan can
    say "follow-up depth depends on classification" once instead of listing every
    classification an author can imagine.

    The dimension is read from the entry, never inferred from the presence of a policy
    table. A resolver that guessed which enum a rule was keyed on would be doing the
    inference this module refuses everywhere else -- and would lose the distinction below,
    since it could not tell a policy that misses this case from one that was never about
    this dimension at all.

    Every way this can fail to determine a value is ``ambiguous``, not ``absent``: the plan
    claimed a dimension. A missing row, a malformed table, a dimension the caller supplied
    no value for -- in each the plan spoke about this decision and did not settle it, which
    is a gap in the plan rather than silence about the subject.
    """
    dimension = entry.get(POLICY_DIMENSION)
    table = entry.get(POLICY_TABLE)
    if not isinstance(dimension, str) or not dimension:
        return _ambiguous(decision_key,
                          "a policy is declared without naming the dimension it is keyed "
                          "on, so which value to look up cannot be known")
    unusable = _policy_table_fault(table, dimension)
    if unusable:
        return _ambiguous(decision_key, unusable)
    if case is None:
        return _ambiguous(decision_key,
                          f"the plan answers this through {_said(dimension)}, and no value for "
                          "that dimension was supplied with the lookup")
    if case not in table:
        return _ambiguous(decision_key,
                          f"the plan's policy over {_said(dimension)} has no row for {_said(case)}, "
                          "so it covers this dimension but not this case")
    value = table[case]
    if not isinstance(value, str):
        return _ambiguous(decision_key,
                          f"the policy row for {_said(case)} is a "
                          f"{type(value).__name__}, not a value this can resolve to")
    return _lookup(decision_key, value, "policy", "resolved",
                   f"the plan's policy over {_said(dimension)} declares {_said(case)}")
# @cpt-end:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-policy


# @cpt-begin:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-verdicts
#: The value a lookup carries when it did not resolve. Increment 1's record defaults every
#: field to this same literal, so an unanswered decision reads as a visible `unspecified`
#: in the trail rather than as an empty field indistinguishable from one never written.
UNSPECIFIED = "unspecified"


def _lookup(decision_key: str, value: str, provenance: str, status: str,
            why: str) -> PlanLookup:
    """Every outcome is built here, so ``why`` is bounded in one place rather than four.

    The first version capped each value on its way into an explanation, which held until
    the next interpolation was written -- and the guard watching it matched one spelling of
    one syntax, so an exception's own text walked straight past. Bounding the finished
    string instead makes the property hold for interpolations nobody has written yet, which
    is what "every sink" means when the sinks are not all present.
    """
    return PlanLookup(decision_key=_bounded(decision_key), value=value,
                      provenance=provenance, status=status, why=_bounded(why))


def _absent(decision_key: str, why: str) -> PlanLookup:
    """The plan is silent on this key. The gate asks, and nothing is wrong with the plan."""
    return _lookup(decision_key, UNSPECIFIED, "plan", "absent", why)


def _ambiguous(decision_key: str, why: str) -> PlanLookup:
    """The plan spoke and did not decide. The gate asks, and something is wrong with the plan.

    Kept apart from ``absent`` deliberately, though both ask. Collapsing them files a gap
    in the plan under the same heading as a question the plan never undertook to answer,
    and only one of those is worth an author's attention.
    """
    return _lookup(decision_key, UNSPECIFIED, "plan", "ambiguous", why)
# @cpt-end:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-verdicts


# @cpt-begin:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-resolve
def _resolve_entry(entry: Dict[str, Any], decision_key: str,
                   case: Optional[str]) -> PlanLookup:
    """The single declaration that carries this key, read according to its shape.

    A declaration answers directly or by policy, never both: one carrying a value *and* a
    policy states two answers, and picking either would be this module guessing which the
    author meant -- so it asks, which is what a plan that contradicts itself deserves.
    """
    has_value = "value" in entry
    has_policy = POLICY_TABLE in entry or POLICY_DIMENSION in entry
    if has_value and has_policy:
        return _ambiguous(decision_key,
                          "the declaration carries both a direct value and a policy, so "
                          "which of the two answers is meant cannot be known")
    if has_policy:
        return _resolve_policy(entry, decision_key, case)
    value = entry.get("value")
    if not isinstance(value, str):
        return _ambiguous(decision_key,
                          "the declaration carries no value this can resolve to")
    return _lookup(decision_key, value, "plan", "resolved",
                   "the plan declares this key directly")


def resolve(decision_key: str, plan_dir: Path, *, case: Optional[str] = None) -> PlanLookup:
    """Answer one decision key from a plan's declarations, or say why it cannot.

    ``case`` is the value the gate holds for a declared dimension, supplied only where the
    plan answers by policy. A direct declaration ignores it.

    The plan is re-read here on every call. That is the point: an edited plan takes effect
    on the next lookup, and no ``resolved`` outlives the text it came from.
    """
    plan, reason, verdict = _load_plan(plan_dir / PLAN_FILE)
    if plan is None:
        # Unreadable, not silent. `absent` asserts something about the plan's contents,
        # and an unparseable file supports no such claim -- so this is `ambiguous`, which
        # asks for the same reason but records a defect rather than a normal omission.
        # Warned as well as returned: a plan that will not parse stops every gate that
        # consults it, and a caller logging only the status would show a run of ordinary
        # `absent`s with nothing saying the plan itself is broken.
        if verdict == SILENCE:
            return _absent(decision_key, reason)
        logger.warning("plan decisions: %s", reason)
        return _ambiguous(decision_key, reason)

    if _section_is_malformed(plan):
        return _ambiguous(decision_key,
                          f"the plan carries a {DECISIONS_TABLE} section that is not an "
                          "array of declarations, so it speaks about decisions and "
                          "declares none")
    entries = _declared_entries(plan, decision_key)
    skipped = _malformed_count(plan)
    if skipped:
        # Warned, not only carried in the `why`. A parse failure warns and a section that
        # is not an array warns, so entries the plan lost to a typo being visible in one
        # lookup's explanation and nowhere else is the odd one out -- and it is the case an
        # author most wants told, because the plan looks like it declares something.
        logger.warning("plan decisions: the plan carries %d malformed %s %s that cannot be "
                       "read as declarations", skipped, DECISIONS_TABLE,
                       "entry" if skipped == 1 else "entries")
    if not entries:
        why = f"no declaration in the plan carries the key {_said(decision_key)}"
        if skipped:
            # Said out loud rather than folded into a plain `absent`: an author who wrote
            # the decision and mistyped its shape gets "your plan has N unusable entries",
            # not "the plan does not mention it", which reads as though they never wrote it.
            why += (f"; the plan also carries {skipped} malformed "
                    f"entr{'y' if skipped == 1 else 'ies'} anywhere in its "
                    f"{DECISIONS_TABLE} array — not necessarily for this key — so a "
                    "declaration may have been lost to a typo")
        return _absent(decision_key, why)
    if len(entries) > 1:
        return _ambiguous(decision_key,
                          f"{len(entries)} declarations carry the key {_said(decision_key)}, so "
                          "the plan states more than one answer and settles on none")

    return _resolve_entry(entries[0], decision_key, case)
# @cpt-end:cpt-studio-algo-execution-plans-decision-lookup:p1:inst-plan-resolve
