"""promptfoo native python provider — Claude Code CLI in a cf-studio sandbox."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, NamedTuple

from _sandbox import SandboxError, sandbox

logger = logging.getLogger(__name__)

CLAUDE_BIN = "claude"
CALL_TIMEOUT_S = 850  # under promptfoo worker timeout (900s)

# Cheap-by-default model + low reasoning. Override via env if a scenario
# legitimately needs a stronger model.
#
# Note on 1M context: the 1M-token window is a beta enabled via
# `--betas context-1m-2025-08-07` and only on Opus/Sonnet. Haiku 4.5 has the
# standard 200K window — by selecting Haiku we implicitly opt out of 1M, and
# we never pass --betas here.
DEFAULT_MODEL = os.environ.get("CF_UX_CLAUDE_MODEL", "claude-haiku-4-5")
DEFAULT_EFFORT = os.environ.get("CF_UX_CLAUDE_EFFORT", "low")

# Skill *execution* asks for permission, and `-p` has nobody to ask, so the
# request is denied, the `cf` skill never runs, and the agent answers directly
# instead — returning something plausible that the shared rubric then scores as
# though Studio had behaved well. The codex provider has always passed the
# equivalent pair (`--sandbox workspace-write`, `approval_policy="never"`); this
# is the same decision for this CLI, and the asymmetry was the bug.
#
# Scoped to a throwaway tree: `_sandbox.sandbox()` builds a fresh directory
# under the system temp dir and wipes it in `finally`, on `atexit`, and on
# SIGTERM/SIGINT/SIGHUP. The one exception is `CF_UX_SHARED_SANDBOX`, which
# points a run at a directory the caller chose — noted in the README, because
# there the agent writes where it is told to.
PERMISSION_MODE = "bypassPermissions"

#: Cost ceiling for one scenario. Named because the error text for a transcript
#: that stops early has to be able to point at it as a cause.
MAX_BUDGET_USD = "0.30"

#: The tool Claude Code reports when it executes a skill.
_SKILL_TOOL = "Skill"
#: The skill this suite exists to measure, compared whole against each string in
#: the tool input. Substring containment will not do: the prompt is `/cf …`, so
#: the input's *argument* text carries "cf" on every scenario in this suite, and
#: a competing skill (`superpowers:brainstorming`) quoting the user message back
#: would have counted as this one running.
_SKILL_NAME = "cf"
#: Skill identifiers may be namespaced (`plugin:skill`); the trailing segment is
#: the name. Splitting on these and not on `-` is what keeps a hypothetical
#: `cf-generate` distinct from `cf`.
_NAME_SEPARATORS = (":", "/")
#: What a skill identifier can look like. Used to tell the name in a tool input
#: from the request text sitting beside it, so `skills_invoked` reports names
#: and not prose.
_NAME_SHAPE = re.compile(r"[A-Za-z0-9_.:/-]{1,64}")
#: What a *failed* execution looks like in the transcript: `<error>Execute
#: skill: cf</error>`. Bound to the name, with a boundary, for the same reason
#: the positive check is: an unrelated skill failing (`Execute skill:
#: superpowers`) must not fail this one, and neither must answer prose that
#: quotes the phrase. The previous guard searched for "skills failed to load",
#: which the CLI never emits, so it could not fire at all.
_SKILL_ERROR_TEXT = "Execute skill:"
_SKILL_ERROR_MARK = re.compile(rf"{_SKILL_ERROR_TEXT}\s*{_SKILL_NAME}(?![\w.:/-])")
#: The terminal event's subtype when the turn ran to completion. Anything else
#: (`error_max_turns`, `error_during_execution`) leaves `result` holding a
#: fragment rather than an answer.
_RESULT_OK = "success"

#: Counting a dropped line into the metadata is not the same as saying so where
#: a person will see it, and the house rule is that a swallowed exception warns
#: on stderr rather than only in a return value (`architecture/DESIGN.md`).
_LOG_UNPARSED_LINE = "cf-ux claude provider: stream line %d would not parse; skipped"
#: A `ran` verdict reached from an input that names more than one identifier is
#: the shape a false pass takes, so it is reported per run rather than left to
#: whoever thinks to inspect `skill_call_inputs` afterwards.
#:
#: Deliberately an over-approximation, and named for what it observes rather
#: than what it suspects. Since the name's key is unknown, this cannot tell a
#: wrong-field match from a correct call that merely carries a second
#: identifier: every false positive of this class is reported, and so are some
#: perfectly good runs. Narrowing it would need the very knowledge whose absence
#: created the trade.
_LOG_AMBIGUOUS_MATCH = (
    "cf-ux claude provider: matched %r in a Skill input that also names %s; "
    "the verdict may rest on a field that is not the skill name"
)


def _stream_events(raw: str) -> tuple[list[dict[str, Any]], int]:
    """Parse `--output-format stream-json`: one JSON object per line.

    Returns the events and *how many lines would not parse*. A malformed line is
    skipped rather than fatal — the stream is a transcript, and one bad entry
    says nothing about the rest — but it is counted and reported, because a
    dropped line can be a dropped `tool_result`, and this module decides what a
    run means from exactly those. Silently discarding one would let the count of
    evidence shrink without the verdict admitting it.
    """
    events: list[dict[str, Any]] = []
    unparsed = 0
    for number, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            unparsed += 1
            logger.warning(_LOG_UNPARSED_LINE, number)
            continue
        if isinstance(event, dict):
            events.append(event)
    return events, unparsed


def _result_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The terminal `result` event, which carries the answer and the totals.

    Last one wins: the stream is ordered and the terminal event is the final
    one, so a transcript carrying two (a resumed or restarted turn) is read as
    ending in its last.
    """
    for event in reversed(events):
        if event.get("type") == "result":
            return event
    return None


def _content_blocks(event: dict[str, Any]) -> list[dict[str, Any]]:
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def _invoked_names(payload: Any) -> list[str]:
    """The skill identifiers a `Skill` tool input names.

    Which key holds the name is not part of any stable contract, so every string
    value shaped like an identifier is a candidate — *at any depth*, because a
    tool input that nests its identifier one level down (`{"options": {"skill":
    "cf"}}`) is a shape this cannot rule out either. Stopping at the top level
    would mean a nested name is never found, and then every run errors: the
    certain false failure this trade exists to avoid, rather than the rare false
    pass it accepts.

    Each candidate is compared *whole* — but only after any `plugin:` or `path/`
    namespace is dropped, so `plugin:cf` counts and `cf-generate` does not. What
    the shape filter excludes is the argument text, which in this suite always
    quotes a `/cf …` prompt.

    A top-level input that is not a dict is scanned rather than refused, for the
    same reason: a bare string or a list is a shape this cannot rule out either,
    and refusing it would mean the name is never found and every run errors.

    Returned sorted and deduplicated. The traversal is a stack, so its own order
    is an implementation detail, and nothing downstream should vary with it —
    this list reaches a warning message a person reads.
    """
    names = set()
    pending = [payload]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            pending.extend(current.values())
            continue
        if isinstance(current, list):
            pending.extend(current)
            continue
        if not isinstance(current, str) or not _NAME_SHAPE.fullmatch(current.strip()):
            continue
        name = current.strip()
        for separator in _NAME_SEPARATORS:
            name = name.rsplit(separator, 1)[-1]
        if name:
            names.add(name)
    return sorted(names)


class _SkillTrace(NamedTuple):
    """What the transcript says about the skill this suite measures."""

    state: str          # "ran" | "failed" | "absent"
    names: list[str]    # skill identifiers the transcript names
    inputs: list[str]   # the tool inputs verbatim, serialized, for diagnosis
    detail: str
    #: The other identifiers in the matched call, when there were any. Reported
    #: rather than judged: see `_LOG_AMBIGUOUS_MATCH`.
    other_candidates: tuple[str, ...] = ()


def _skill_trace(events: list[dict[str, Any]], raw: str) -> _SkillTrace:
    """Did the `cf` skill actually run?

    A *positive* check against tool-use events, not a substring search over the
    prose: the fallback answer is well-formed and says nothing about whether the
    skill was reached, which is exactly why the old heuristic scored it.

    The evidence is bound per call. `ran` needs one `Skill` call that names `cf`
    *and* a non-error result for that same call — not merely some call naming it
    and some other call succeeding. A call with no observed result is not a
    confirmed run either: a truncated or interrupted trace is the case this
    whole module exists to refuse to score.
    """
    calls: dict[Any, Any] = {}
    results: dict[Any, bool] = {}
    for event in events:
        for block in _content_blocks(event):
            kind = block.get("type")
            if kind == "tool_use" and block.get("name") == _SKILL_TOOL:
                # Last wins on a repeated id. Either order is safe: the verdict
                # below needs a success bound to the surviving cf call, and a
                # collision can only take evidence away, never invent it.
                calls[block.get("id")] = block.get("input") or {}
            elif kind == "tool_result":
                results[block.get("tool_use_id")] = bool(block.get("is_error"))

    named = {call_id: _invoked_names(payload) for call_id, payload in calls.items()}
    names = sorted({name for found in named.values() for name in found})
    inputs = sorted({json.dumps(payload, default=str, sort_keys=True) for payload in calls.values()})

    if _SKILL_ERROR_MARK.search(raw):
        return _SkillTrace(
            "failed", names, inputs,
            f"the transcript reports {_SKILL_ERROR_TEXT} {_SKILL_NAME}",
        )
    if not calls:
        return _SkillTrace("absent", names, inputs, f"no {_SKILL_TOOL} tool call in the transcript")

    targeted = [call_id for call_id, found in named.items() if _SKILL_NAME in found]
    if not targeted:
        return _SkillTrace(
            "failed", names, inputs,
            f"a {_SKILL_TOOL} ran but none of them named {_SKILL_NAME!r}",
        )
    for call_id in targeted:
        if results.get(call_id) is not False:
            continue
        # Because the name's key is unknown, `cf` may have been matched against a
        # field that is not the name at all — a rival skill invoked with some
        # unrelated value of `cf` reads as this one running. That trade is
        # accepted (a rare false pass beats a certain false failure), but a
        # verdict resting on one of several candidates is said out loud rather
        # than left for whoever thinks to diff the metadata afterwards.
        others = tuple(name for name in named[call_id] if name != _SKILL_NAME)
        if others:
            logger.warning(_LOG_AMBIGUOUS_MATCH, _SKILL_NAME, list(others))
        return _SkillTrace("ran", names, inputs, "", others)
    if any(call_id not in results for call_id in targeted):
        return _SkillTrace(
            "failed", names, inputs,
            f"the {_SKILL_NAME!r} call has no result in the transcript",
        )
    return _SkillTrace(
        "failed", names, inputs, f"every {_SKILL_NAME!r} call came back as an error",
    )


def _baseline(cwd: Path, started: float) -> dict[str, Any]:
    """What every return carries, answer or error: how long it took, and where."""
    return {"duration_s": round(time.monotonic() - started, 2), "sandbox": str(cwd)}


def call_api(prompt: str, options: dict | None = None, context: dict | None = None) -> dict:
    started = time.monotonic()
    try:
        with sandbox() as cwd:
            return _invoke(prompt, cwd, started)
    except SandboxError as exc:
        return {"error": f"sandbox setup failed: {exc}"}
    except subprocess.TimeoutExpired as exc:
        # Not the `claude` call — `_invoke` handles its own timeout, where the
        # sandbox path is still in scope. Reaching here means a setup command
        # (`git`, the in-tree `cfs init`) hit its own deadline, and saying
        # "claude timed out" would have sent triage to the wrong process.
        return {
            "error": f"sandbox setup timed out after {exc.timeout}s: {exc.cmd[0] if exc.cmd else '?'}",
            "metadata": {"duration_s": round(time.monotonic() - started, 2)},
        }
    except Exception as exc:  # noqa: BLE001 — surface unexpected errors to promptfoo
        return {"error": f"unexpected: {type(exc).__name__}: {exc}"}


def _invoke(prompt: str, cwd: Path, started: float) -> dict:
    # Explicit skill invocation: Claude Code uses `/cf <prompt>`.
    invoked = f"/cf {prompt}"
    cmd = [
        CLAUDE_BIN, "-p",
        "--model", DEFAULT_MODEL,
        "--effort", DEFAULT_EFFORT,
        # Without this the skill is denied and the run scores the fallback path.
        "--permission-mode", PERMISSION_MODE,
        # The transcript, not just the answer: tool-use events are the only place
        # the run says whether the skill was reached. `--verbose` is what makes
        # `-p` emit the intermediate events rather than the result alone.
        "--output-format", "stream-json",
        "--verbose",
        "--max-budget-usd", MAX_BUDGET_USD,
        invoked,
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=CALL_TIMEOUT_S, check=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        # Handled here rather than in `call_api` so it carries the same baseline
        # as every other error: an operator triaging a wave of them can tell a
        # run that burned 850s from one that failed at once, and can say where.
        return {
            "error": f"claude timed out after {CALL_TIMEOUT_S}s",
            "metadata": _baseline(cwd, started),
        }
    base = _baseline(cwd, started)

    if proc.returncode != 0:
        return {
            "error": f"claude exited {proc.returncode}: {proc.stderr.strip()[:500]}",
            "metadata": base,
        }

    events, unparsed = _stream_events(proc.stdout)
    payload = _result_event(events)
    base["unparsed_lines"] = unparsed
    if payload is None:
        # Fail closed. Without the terminal event there is no answer to grade and
        # no transcript to trust, so returning the raw text would hand the rubric
        # something to score with no idea what produced it.
        #
        # Both causes are named because they look identical here and lead to
        # opposite fixes: a budget ceiling reached mid-turn ends the stream just
        # as an unhonoured `--output-format` does, and only one of them is a bug.
        #
        # `events_seen` and `last_event_type` are what tell the two apart without
        # reading the tail by hand: a stream that was never JSON lines parses to
        # nothing, while a turn cut off at the ceiling leaves a run of events
        # ending somewhere mid-turn. `unparsed_lines` distinguishes truncation
        # mid-line from a stream that simply stopped between lines.
        return {
            "error": (
                "claude emitted no result event: the turn may have stopped at the "
                f"--max-budget-usd {MAX_BUDGET_USD} ceiling, or stream-json was not honoured"
            ),
            "metadata": {
                **base,
                "events_seen": len(events),
                "last_event_type": events[-1].get("type") if events else None,
                "stdout_tail": proc.stdout.strip()[-500:],
            },
        }

    answer = payload.get("result")
    is_text = isinstance(answer, str)
    output_text = answer if is_text else ""
    # What to show when the answer is withheld from the grader: the text itself,
    # or a repr of whatever non-text thing arrived instead of one. Kept as a
    # string so no branch below can slice a dict.
    withheld = (output_text if is_text else "" if answer is None else repr(answer))[:500]
    trace = _skill_trace(events, proc.stdout)
    state, detail = trace.state, trace.detail
    metadata = {
        **base,
        "session_id": payload.get("session_id"),
        "num_turns": payload.get("num_turns"),
        "total_cost_usd": payload.get("total_cost_usd"),
        "skill_state": state,
        "skills_invoked": trace.names,
        "skill_call_inputs": trace.inputs,
        "skill_match_other_candidates": list(trace.other_candidates),
    }
    cost = payload.get("total_cost_usd")

    # A turn that stopped short is not an answer, even when the skill did load:
    # `result` then holds whatever had been written when the limit hit, and
    # grading a fragment reports on Studio for a run that never finished. Only a
    # subtype that is *present and not success* counts as that — an unfamiliar
    # shape should not be able to manufacture failures.
    subtype = payload.get("subtype")
    if payload.get("is_error") or (subtype is not None and subtype != _RESULT_OK):
        result: dict[str, Any] = {
            "error": f"claude did not finish the turn (result subtype {subtype!r})",
            "metadata": {**metadata, "unscored_output": withheld},
        }
    elif answer is not None and not is_text:
        # Nothing downstream would notice: promptfoo would hand the rubric a
        # dict and the rubric would score whatever it made of it. Text is what
        # this suite grades, so a non-text answer is a shape change to report,
        # not to render.
        result = {
            "error": f"claude returned a non-text result ({type(answer).__name__})",
            "metadata": {**metadata, "unscored_output": withheld},
        }
    elif state != "ran":
        # A hard error, not a metadata flag. The fallback answer is plausible and
        # well-formed, so left to the grader it scores as a pass and the suite
        # reports on an agent that never loaded Studio. A run that did not engage
        # the skill is not a measurement of the skill, and must not be graded as
        # one — this is the part of the fix that keeps the defect from returning
        # the next time an invocation detail changes.
        result = {
            "error": f"cf skill did not run ({state}): {detail}",
            "metadata": {**metadata, "unscored_output": withheld},
        }
    else:
        result = {"output": output_text, "metadata": metadata}
    if isinstance(cost, (int, float)):
        result["cost"] = float(cost)
    return result
