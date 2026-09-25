"""Tests for the cf-ux Claude provider — that a run which never loaded the skill
is not scored as one that did.

The suite these back cannot run here: `claude` is a CLI this repository does not
vendor, and a real invocation costs money and needs credentials. So the provider
is driven with a faked `subprocess.run` and a faked sandbox, which is enough to
pin the three things that went wrong — the missing permission flag, a guard that
searched for a string the CLI never emits, and a skill failure recorded as
metadata where the grader would never see it.

What these tests deliberately do *not* claim: that `--permission-mode
bypassPermissions` makes the skill execute. That is a fact about the CLI, and it
belongs to whoever can run one.
"""

from __future__ import annotations

import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

_PROVIDERS = Path(__file__).resolve().parents[1] / "tests" / "prompts" / "cf-ux" / "providers"
if str(_PROVIDERS) not in sys.path:
    sys.path.insert(0, str(_PROVIDERS))

claude_provider = pytest.importorskip("claude_provider")


# --------------------------------------------------------------------------- helpers

def _skill_call(call_id: str = "t1", name: str = "Skill", skill: str = "cf") -> dict:
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": call_id, "name": name, "input": {"command": skill}},
    ]}}


def _skill_result_without_flag(call_id: str = "t1") -> dict:
    """The shape a *successful* skill result actually has: claude-code omits
    `is_error` entirely when a `Skill` call succeeds."""
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": call_id, "content": "..."},
    ]}}


def _skill_result(call_id: str = "t1", *, is_error: bool = False) -> dict:
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": call_id, "is_error": is_error, "content": "..."},
    ]}}


def _result(text: str = "the answer", cost: float = 0.01, **overrides) -> dict:
    return {"type": "result", "subtype": "success", "result": text,
            "session_id": "s1", "num_turns": 3, "total_cost_usd": cost, **overrides}


def _stream(*events: dict) -> str:
    return "".join(json.dumps(event) + "\n" for event in events)


@pytest.fixture
def run_provider(tmp_path, monkeypatch):
    """Drive `call_api` against a canned transcript; hand back the call's argv."""
    seen: dict = {}

    @contextmanager
    def _fake_sandbox():
        yield tmp_path

    def _make(stdout: str, returncode: int = 0, stderr: str = "", raises: Exception | None = None):
        def _fake_run(cmd, **kwargs):
            seen["cmd"] = list(cmd)
            seen["kwargs"] = kwargs
            if raises is not None:
                raise raises
            return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)

        monkeypatch.setattr(claude_provider, "sandbox", _fake_sandbox)
        monkeypatch.setattr(claude_provider.subprocess, "run", _fake_run)
        return claude_provider.call_api("write a PRD"), seen

    return _make


# ------------------------------------------------------- the permission flag

class TestTheSkillIsAllowedToExecute:

    def test_the_invocation_carries_a_permission_mode(self, run_provider):
        """The defect itself: with no permission flag, skill execution is denied in
        print mode because there is nobody to ask, so the agent answers directly
        and the run scores the fallback path."""
        _out, seen = run_provider(_stream(_skill_call(), _skill_result(), _result()))

        cmd = seen["cmd"]
        assert "--permission-mode" in cmd, "print mode has nobody to grant permission"
        assert cmd[cmd.index("--permission-mode") + 1] == "bypassPermissions"

    def test_the_transcript_is_requested_not_only_the_answer(self, run_provider):
        """Tool-use events are the only place the run says whether the skill was
        reached, and `-p` emits them only in the streaming format."""
        _out, seen = run_provider(_stream(_skill_call(), _skill_result(), _result()))

        cmd = seen["cmd"]
        assert cmd[cmd.index("--output-format") + 1] == "stream-json"
        assert "--verbose" in cmd, "without it `-p` returns the result alone"


# ------------------------------------------------- a run that loaded the skill

class TestARunThatLoadedTheSkillIsScored:

    def test_the_answer_and_the_totals_come_back(self, run_provider):
        out, _seen = run_provider(
            _stream(_skill_call(), _skill_result(), _result("gate rendered", cost=0.02)),
        )

        assert "error" not in out
        assert out["output"] == "gate rendered"
        assert out["cost"] == 0.02
        assert out["metadata"]["skill_state"] == "ran"
        assert out["metadata"]["num_turns"] == 3
        assert out["metadata"]["unparsed_lines"] == 0, "a clean transcript dropped nothing"

    def test_a_namespaced_cf_skill_is_still_the_cf_skill(self, run_provider):
        """`plugin:skill` is how a skill from a marketplace is named, so the
        trailing segment is the identifier to compare."""
        out, _seen = run_provider(
            _stream(_skill_call(skill="studio:cf"), _skill_result(), _result()),
        )

        assert out["output"] == "the answer"
        assert out["metadata"]["skill_state"] == "ran"

    def test_the_metadata_names_the_skill_and_keeps_the_input_beside_it(self, run_provider):
        """`skills_invoked` used to hold `'{"command": "cf"}'` — a serialized
        payload under a key promising a name. The raw input is still worth having
        for diagnosis, so it keeps its own key instead of borrowing this one."""
        out, _seen = run_provider(
            _stream(_skill_call(skill="studio:cf"), _skill_result(), _result()),
        )

        assert out["metadata"]["skills_invoked"] == ["cf"]
        assert out["metadata"]["skill_call_inputs"] == ['{"command": "studio:cf"}']

    def test_the_request_text_is_not_listed_as_a_skill_name(self, run_provider):
        """Which key holds the name is not contractual, so every string value is
        a candidate — but only the ones shaped like an identifier. Otherwise a
        field promising names reports the user's sentence as one of them."""
        call = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": {
                "command": "cf", "args": "write a PRD for the billing service",
            }},
        ]}}

        out, _seen = run_provider(_stream(call, _skill_result(), _result()))

        assert out["metadata"]["skill_state"] == "ran"
        assert out["metadata"]["skills_invoked"] == ["cf"]

    def test_a_bare_cf_in_an_unrelated_field_still_counts(self, run_provider):
        """A known false positive, pinned rather than closed.

        Which key holds the skill name is not contractual, so every
        identifier-shaped value is a candidate — and a rival skill invoked with
        some field whose *whole* value is `cf` therefore reads as this skill
        running. Prose does not do this (the test above), but a single token in
        an unrelated field does.

        Narrowing to a fixed set of name keys would close this and open a worse
        hole: guess the key wrong and *every* run errors, because the name would
        never be found where it actually lives. This way round the failure is a
        rare false pass; that way round it is a certain false failure. Erring
        toward recall is what makes the harness work without knowing the key,
        and `skill_call_inputs` keeps the raw input so the verdict stays
        inspectable. If the key is ever pinned down, this test is where the
        trade gets renegotiated.
        """
        rival = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": {
                "command": "superpowers:brainstorming", "mode": "cf",
            }},
        ]}}

        out, _seen = run_provider(_stream(rival, _skill_result(), _result()))

        assert out["output"] == "the answer", "the point of the false positive: it gets scored"
        assert "error" not in out
        assert out["metadata"]["skill_state"] == "ran"
        assert out["metadata"]["skills_invoked"] == ["brainstorming", "cf"]
        assert out["metadata"]["skill_call_inputs"] == [
            '{"command": "superpowers:brainstorming", "mode": "cf"}'
        ], "the raw input shows where the name was found, so a false pass is visible"

    def test_a_namespaced_value_in_an_unrelated_field_counts_the_same_way(self, run_provider):
        """The same false-positive class through a second mechanism: the value is
        not literally `cf`, it reduces to it once the namespace is dropped. The
        comparison is whole-value *after* stripping, which is what lets
        `plugin:cf` count while `cf-generate` does not."""
        rival = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": {
                "command": "superpowers:brainstorming", "mode": "plugin:cf",
            }},
        ]}}

        out, _seen = run_provider(_stream(rival, _skill_result(), _result()))

        assert out["metadata"]["skill_state"] == "ran"
        assert out["metadata"]["skills_invoked"] == ["brainstorming", "cf"]

    @pytest.mark.parametrize("shape", [
        pytest.param({"options": {"skill": "cf"}}, id="one-level"),
        pytest.param({"o": {"p": {"skill": "cf"}}}, id="two-levels"),
        pytest.param({"args": [{"skill": "cf"}]}, id="list-of-dicts"),
        pytest.param({"a": [{"b": {"skill": "cf"}}]}, id="dict-in-list-in-dict"),
        pytest.param({"a": [["cf"]]}, id="nested-lists"),
    ])
    def test_a_nested_identifier_is_found_at_any_depth(self, run_provider, shape):
        """Stopping at the top level would contradict the trade above rather than
        implement it: a tool input that nests its identifier is a shape this
        cannot rule out, and missing it means *every* run errors — the certain
        false failure, not the rare false pass.

        Parametrized past depth one because "any depth" is the claim; a single
        level would leave a regression below it uncaught.
        """
        nested = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": shape},
        ]}}

        out, _seen = run_provider(_stream(nested, _skill_result(), _result()))

        assert out["metadata"]["skill_state"] == "ran"
        assert out["metadata"]["skills_invoked"] == ["cf"]

    @pytest.mark.parametrize("payload", ["cf", ["cf"], ["other", {"skill": "cf"}]])
    def test_an_input_that_is_not_a_dict_is_scanned_rather_than_refused(
        self, run_provider, payload,
    ):
        """A boundary the earlier version refused outright (`if not
        isinstance(payload, dict): return []`). Scanning it follows from the same
        reasoning as the depth walk: a bare string or list input is a shape that
        cannot be ruled out, and refusing it means the name is never found and
        every run errors. Called out because it is a behaviour change, not a
        side effect."""
        odd = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": payload},
        ]}}

        out, _seen = run_provider(_stream(odd, _skill_result(), _result()))

        assert out["metadata"]["skill_state"] == "ran"

    def test_a_sole_candidate_leaves_the_other_candidates_empty(self, run_provider):
        """The field has to distinguish, or it says nothing."""
        out, _seen = run_provider(
            _stream(_skill_call(skill="studio:cf"), _skill_result(), _result()),
        )

        assert out["metadata"]["skill_match_other_candidates"] == []

    def test_a_result_event_with_no_subtype_is_still_an_answer(self, run_provider):
        """Only a subtype that is present and says otherwise means a short turn.
        An unfamiliar event shape must not be able to manufacture failures."""
        bare = {"type": "result", "result": "the answer", "session_id": "s1"}

        out, _seen = run_provider(_stream(_skill_call(), _skill_result(), bare))

        assert out["output"] == "the answer"

    def test_two_result_events_are_read_as_ending_in_the_last(self, run_provider):
        out, _seen = run_provider(
            _stream(_skill_call(), _skill_result(), _result("first"), _result("second")),
        )

        assert out["output"] == "second"

    def test_a_skill_that_ran_alongside_a_failed_unrelated_tool_still_counts(self, run_provider):
        """Only the `Skill` call's own result decides this. An unrelated tool
        erroring mid-workflow is ordinary, and must not read as the skill failing."""
        other = {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "other", "is_error": True, "content": "nope"},
        ]}}
        out, _seen = run_provider(
            _stream(_skill_call(), _skill_result(), other, _result()),
        )

        assert "error" not in out
        assert out["metadata"]["skill_state"] == "ran"


# --------------------------------------------- a run that did not, is not scored

class TestARunThatNeverLoadedTheSkillIsNotScored:
    """The heart of the report: the fallback answer is plausible and well-formed,
    so left to the grader it scores as a pass and the suite reports confidently on
    an agent that never loaded Studio."""

    def test_no_skill_call_at_all_is_an_error_not_an_output(self, run_provider):
        out, _seen = run_provider(_stream(_result("here is a PRD I wrote myself")))

        assert "output" not in out, "a fallback answer must never reach the grader"
        assert "did not run (absent)" in out["error"]
        assert out["metadata"]["skill_state"] == "absent"
        assert out["metadata"]["unscored_output"].startswith("here is a PRD")

    def test_a_skill_call_that_errored_is_an_error(self, run_provider):
        out, _seen = run_provider(
            _stream(_skill_call(), _skill_result(is_error=True), _result("drafted directly")),
        )

        assert "output" not in out
        assert "did not run (failed)" in out["error"]
        assert out["metadata"]["skill_state"] == "failed"

    def test_the_real_failure_signature_is_recognised(self, run_provider):
        """The observed failure is `<error>Execute skill: cf</error>`. The previous
        guard looked for "skills failed to load", which the CLI never emits, so the
        one check meant to catch this could not fire."""
        transcript = _stream(_result("<error>Execute skill: cf</error> so I answered"))

        out, _seen = run_provider(transcript)

        assert "output" not in out
        assert "Execute skill:" in out["error"]
        assert out["metadata"]["skill_state"] == "failed"

    @pytest.mark.parametrize("rival", ["superpowers", "cf-generate"])
    def test_another_skill_failing_does_not_fail_the_cf_run(self, run_provider, rival):
        """`Execute skill:` with no name attached meant one skill's failure
        condemned another's success — the mirror of the substring problem on the
        positive side, and it fired before any positive evidence was weighed."""
        out, _seen = run_provider(_stream(
            _skill_call(), _skill_result(),
            _result(f"<error>Execute skill: {rival}</error> but cf answered"),
        ))

        assert "error" not in out
        assert out["metadata"]["skill_state"] == "ran"

    def test_a_different_skill_running_is_not_the_cf_skill_running(self, run_provider):
        out, _seen = run_provider(
            _stream(_skill_call(skill="superpowers"), _skill_result(), _result()),
        )

        assert "output" not in out
        assert "none of them named 'cf'" in out["error"]
        assert out["metadata"]["skill_state"] == "failed"
        assert out["metadata"]["skills_invoked"] == ["superpowers"], "and it says which did run"

    def test_a_skill_whose_name_merely_begins_with_cf_is_not_the_cf_skill(self, run_provider):
        """Still not the router: the name matcher is untouched, and `cf-generate`
        does not equal `cf`. What it is now is `bypassed` rather than `failed` --
        see `TestAWorkflowRunWithoutTheRouter` for why that distinction was
        introduced, and what it costs."""
        out, _seen = run_provider(
            _stream(_skill_call(skill="cf-generate"), _skill_result(), _result()),
        )

        assert out["metadata"]["skill_state"] != "ran"
        assert out["metadata"]["skill_state"] == "bypassed"
        assert out["metadata"]["skills_invoked"] == ["cf-generate"]

    def test_a_single_token_that_is_not_cf_does_not_count_either(self, run_provider):
        """The trade pinned above is not "any short token wins". The comparison
        stays whole-value in every field, so a sibling name sitting in the same
        unrelated position does not match."""
        rival = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": {
                "command": "superpowers:brainstorming", "mode": "cf-generate",
            }},
        ]}}

        out, _seen = run_provider(_stream(rival, _skill_result(), _result()))

        assert "output" not in out
        assert "none of them named 'cf'" in out["error"]
        assert out["metadata"]["skill_state"] == "failed"
        assert out["metadata"]["skills_invoked"] == ["brainstorming", "cf-generate"], (
            "both candidates were parsed and neither matched — not one silently dropped"
        )

    def test_a_rival_carrying_a_cf_workflow_name_is_not_a_bypass(self, run_provider):
        """The bypass state must not become the loose match the whole matcher was
        written to avoid, one prefix wider. A rival skill mentioning a `cf-` name
        in some unrelated field names something else too, so the call is not
        unambiguously a Studio workflow and is not graded as one."""
        rival = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": {
                "command": "superpowers:brainstorming", "mode": "cf-documenting-review",
            }},
        ]}}

        out, _seen = run_provider(_stream(rival, _skill_result(), _result()))

        assert "output" not in out
        assert out["metadata"]["skill_state"] == "failed"

    def test_a_false_positive_match_whose_call_errored_is_still_a_failure(self, run_provider):
        """The accepted false positive buys a *name* match, not a verdict. The
        matched call still has to have come back clean, so the interaction of
        the loose match with the error branch is the one worth pinning."""
        rival = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": {
                "command": "superpowers:brainstorming", "mode": "cf",
            }},
        ]}}

        out, _seen = run_provider(
            _stream(rival, _skill_result(is_error=True), _result("answered directly")),
        )

        assert "output" not in out
        assert "came back as an error" in out["error"]
        assert out["metadata"]["skill_state"] == "failed"

    def test_argument_text_naming_cf_is_not_the_skill_naming_cf(self, run_provider):
        """The prompt this suite sends is `/cf <request>`, so every scenario's
        argument text carries "cf". Under substring containment a competing skill
        that quoted the user message back was scored as the cf skill running —
        the false positive the whole PR exists to remove, reintroduced by the
        matcher itself."""
        rival = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": {
                "command": "superpowers:brainstorming",
                "args": "the user asked: /cf write a PRD for cf-studio",
            }},
        ]}}

        out, _seen = run_provider(_stream(rival, _skill_result(), _result()))

        assert "output" not in out
        assert "none of them named 'cf'" in out["error"]

    def test_a_failed_cf_call_beside_a_successful_other_skill_is_not_a_run(self, run_provider):
        """Evidence has to be bound per call. "Some Skill call succeeded" and
        "some payload names cf" were both true here while the cf call itself
        errored."""
        out, _seen = run_provider(_stream(
            _skill_call("A", skill="cf"),
            _skill_call("B", skill="superpowers:brainstorming"),
            _skill_result("A", is_error=True),
            _skill_result("B"),
            _result("drafted directly"),
        ))

        assert "output" not in out
        assert "came back as an error" in out["error"]
        assert out["metadata"]["skill_state"] == "failed"

    def test_a_cf_call_with_no_result_at_all_is_not_a_confirmed_run(self, run_provider):
        """Absence of a result is not a non-error result. A trace cut off after
        the call — a killed CLI, a truncated stream — is the case this module
        exists to refuse, so it cannot be the case it waves through."""
        out, _seen = run_provider(_stream(_skill_call(), _result("answered anyway")))

        assert "output" not in out
        assert "no result in the transcript" in out["error"]
        assert out["metadata"]["skill_state"] == "failed"

    def test_a_repeated_call_id_collapses_to_the_last_one(self, run_provider):
        """The id is the only binding between a call and its result, so a
        collision has to resolve one way. Last wins, and it can only take
        evidence away: here the cf call is overwritten by a later rival sharing
        its id, and the verdict is refusal rather than an unexamined pass."""
        out, _seen = run_provider(_stream(
            _skill_call("dup", skill="cf"),
            _skill_call("dup", skill="superpowers"),
            _skill_result("dup"),
            _result(),
        ))

        assert "output" not in out
        assert "none of them named 'cf'" in out["error"]


# ------------------------------------------------------------------ fail-closed

class TestAnUnreadableRunIsNeverScored:

    def test_a_missing_result_event_is_an_error(self, run_provider):
        """Without the terminal event there is no answer to grade and no transcript
        to trust. Returning the raw text would hand the rubric something to score
        with no idea what produced it."""
        transcript = _stream(_skill_call(), _skill_result())

        out, _seen = run_provider(transcript)

        assert "output" not in out
        assert "no result event" in out["error"]
        assert out["metadata"]["stdout_tail"].endswith(json.dumps(_skill_result()))

    def test_the_missing_result_error_names_both_causes(self, run_provider):
        """A budget ceiling reached mid-turn ends the stream exactly as an
        unhonoured `--output-format` does, and the two lead to opposite fixes:
        raise the budget, or chase a CLI contract change. Naming only the second
        sent triage after a bug that was not there."""
        out, seen = run_provider(_stream(_skill_call(), _skill_result()))

        budget = seen["cmd"][seen["cmd"].index("--max-budget-usd") + 1]
        assert f"--max-budget-usd {budget}" in out["error"], "the ceiling it may have hit"
        assert "stream-json" in out["error"], "or the regression it may be instead"

    @pytest.mark.parametrize("ending", [
        {"subtype": "error_max_turns"},
        {"subtype": "error_during_execution"},
        {"is_error": True},
    ])
    def test_a_turn_that_stopped_short_is_not_graded(self, run_provider, ending):
        """The skill can load and the turn still fail — hit max turns, hit the
        budget, error out. `result` then holds whatever had been written when the
        limit landed, and grading that fragment reports on Studio for a run that
        never finished."""
        out, _seen = run_provider(
            _stream(_skill_call(), _skill_result(), _result("half a gate", **ending)),
        )

        assert "output" not in out
        assert "did not finish the turn" in out["error"]
        assert out["metadata"]["skill_state"] == "ran", "the skill loaded; the turn is what failed"
        assert out["metadata"]["unscored_output"] == "half a gate"
        assert out["cost"] == 0.01, "a run that hit a limit is the expensive kind; report it"

    def test_a_non_text_result_is_not_handed_to_the_grader(self, run_provider):
        """Nothing downstream would notice: promptfoo would pass the rubric a
        dict and the rubric would score whatever it made of it."""
        out, _seen = run_provider(
            _stream(_skill_call(), _skill_result(), _result({"answer": "structured"})),
        )

        assert "output" not in out
        assert "non-text result (dict)" in out["error"]
        assert "structured" in out["metadata"]["unscored_output"], "kept for diagnosis"

    def test_a_non_text_result_on_a_short_turn_reports_the_turn(self, run_provider):
        """Both faults at once. The turn is the outer fact, so it is what the
        error names — and nothing slices the dict on the way out."""
        out, _seen = run_provider(_stream(
            _skill_call(), _skill_result(),
            _result({"answer": "structured"}, subtype="error_max_turns"),
        ))

        assert "did not finish the turn" in out["error"]
        assert "structured" in out["metadata"]["unscored_output"]

    def test_the_missing_result_metadata_tells_the_two_causes_apart(self, run_provider):
        """Naming both causes in prose still leaves triage reading the tail by
        hand. A stream that was never JSON lines parses to nothing; a turn cut
        off at the ceiling leaves events that stop mid-turn."""
        broken, _seen = run_provider("not json at all\nnor this\n")
        truncated, _seen2 = run_provider(_stream(_skill_call(), _skill_result()))

        assert broken["metadata"]["events_seen"] == 0
        assert broken["metadata"]["last_event_type"] is None
        assert broken["metadata"]["unparsed_lines"] == 2
        assert truncated["metadata"]["events_seen"] == 2
        assert truncated["metadata"]["last_event_type"] == "user"
        assert truncated["metadata"]["unparsed_lines"] == 0

    def test_a_dropped_line_is_counted_where_the_verdict_is_read(self, run_provider):
        """A line that will not parse can be a dropped `tool_result`, and the
        verdict is read off exactly those. Skipping one silently let the evidence
        shrink without the answer admitting it."""
        transcript = (
            json.dumps(_skill_call()) + "\n"
            + "{ truncated mid-line\n"
            + json.dumps(_skill_result()) + "\n"
            + json.dumps(_result()) + "\n"
        )

        out, _seen = run_provider(transcript)

        assert out["metadata"]["unparsed_lines"] == 1

    def test_the_other_candidates_are_surfaced_not_merely_inspectable(self, run_provider, caplog):
        """"Inspectable" only mitigates the false positive if someone inspects.
        A verdict reached from an input naming more than one identifier is the
        shape a false pass takes, so it is reported per run — on stderr and in
        the metadata — rather than left for whoever thinks to diff
        `skill_call_inputs` afterwards."""
        rival = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": {
                "command": "superpowers:brainstorming", "mode": "cf",
            }},
        ]}}

        with caplog.at_level("WARNING", logger=claude_provider.logger.name):
            out, _seen = run_provider(_stream(rival, _skill_result(), _result()))

        assert out["metadata"]["skill_match_other_candidates"] == ["brainstorming"]
        assert "may rest on a field that is not the skill name" in caplog.text
        assert "brainstorming" in caplog.text, "and names the other candidate"

    def test_the_other_candidates_are_deduplicated_and_ordered(self, run_provider, caplog):
        """This list reaches a message a person reads, and the traversal is a
        stack — so left raw it repeats a value that appears twice and orders the
        rest by an implementation detail. Two runs of the same transcript would
        then produce different prose for the same finding."""
        rival = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": {
                "a": "zebra", "b": "alpha", "c": "cf",
                "d": {"e": "zebra"}, "f": ["alpha", "middle"],
            }},
        ]}}

        with caplog.at_level("WARNING", logger=claude_provider.logger.name):
            out, _seen = run_provider(_stream(rival, _skill_result(), _result()))

        assert out["metadata"]["skill_match_other_candidates"] == [
            "alpha", "middle", "zebra",
        ], "each named once, in an order that does not depend on the walk"
        assert "['alpha', 'middle', 'zebra']" in caplog.text

    def test_a_second_identifier_beside_a_genuine_call_is_reported_too(self, run_provider):
        """The field is an over-approximation and says so: it cannot tell a
        wrong-field match from a correct call that merely carries a second
        identifier, because telling them apart needs the very knowledge whose
        absence created the trade. Reported, not judged — `ran` still stands."""
        genuine = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill",
             "input": {"command": "cf", "mode": "auto"}},
        ]}}

        out, _seen = run_provider(_stream(genuine, _skill_result(), _result()))

        assert out["output"] == "the answer", "a flag, not a verdict"
        assert out["metadata"]["skill_match_other_candidates"] == ["auto"]

    def test_a_dropped_line_also_warns_where_a_person_will_see_it(self, run_provider, caplog):
        """A count riding along in a metadata dict is not the same as saying so.
        The house rule is that a swallowed exception warns rather than only
        returning a number."""
        transcript = (
            json.dumps(_skill_call()) + "\n"
            + "{ truncated mid-line\n"
            + json.dumps(_skill_result()) + "\n"
            + json.dumps(_result()) + "\n"
        )

        with caplog.at_level("WARNING", logger=claude_provider.logger.name):
            run_provider(transcript)

        assert [r for r in caplog.records if "would not parse" in r.getMessage()]
        assert "line 2" in caplog.text, "and says which line it was"

    def test_a_timeout_reports_how_long_it_ran_and_where(self, run_provider, tmp_path):
        """850s under the 900s worker deadline is a documented failure mode. It
        used to come back as a bare error string, so a wave of them could not be
        told apart from runs that failed instantly."""
        out, _seen = run_provider(
            "", raises=subprocess.TimeoutExpired(cmd=["claude"], timeout=850),
        )

        assert f"timed out after {claude_provider.CALL_TIMEOUT_S}s" in out["error"]
        assert set(out["metadata"]) == {"duration_s", "sandbox", "home"}
        assert out["metadata"]["sandbox"] == str(tmp_path)

    def test_a_setup_timeout_is_not_blamed_on_the_cli(self, monkeypatch):
        """`git` and the in-tree `cfs init` carry their own deadlines. Reported as
        "claude timed out after 850s", they pointed triage at a process that had
        not started yet."""
        def _fake_sandbox():
            raise subprocess.TimeoutExpired(cmd=["git", "init"], timeout=180)

        monkeypatch.setattr(claude_provider, "sandbox", _fake_sandbox)

        out = claude_provider.call_api("write a PRD")

        assert "sandbox setup timed out after 180s" in out["error"]
        assert "git" in out["error"]
        assert "claude" not in out["error"], "the CLI was never reached"

    def test_a_non_json_stream_is_an_error(self, run_provider):
        out, _seen = run_provider("not json at all\nnor this\n")

        assert "output" not in out
        assert "no result event" in out["error"]

    def test_one_malformed_line_does_not_discard_the_rest(self, run_provider):
        """A transcript is a stream; one bad entry says nothing about the others.
        The run is judged by what it contains, not by whether every line parsed."""
        transcript = (
            json.dumps(_skill_call()) + "\n"
            + "{ this line is broken\n"
            + json.dumps(_skill_result()) + "\n"
            + json.dumps(_result("survived")) + "\n"
        )

        out, _seen = run_provider(transcript)

        assert out["output"] == "survived"
        assert out["metadata"]["skill_state"] == "ran"

    def test_a_non_zero_exit_still_reports_the_exit(self, run_provider, tmp_path):
        out, _seen = run_provider("", returncode=2, stderr="unknown flag")

        assert "claude exited 2" in out["error"]
        assert out["metadata"]["sandbox"] == str(tmp_path), "which tree, as elsewhere"


# --------------------------------------------------- what bypassPermissions rests on

class TestTheSandboxIsWipedEvenWhenTheRunDies:
    """`bypassPermissions` is defensible because the tree it writes into is
    temporary and always removed. That is a claim about `_sandbox.sandbox()`, so
    these drive the real one — the rest of the suite fakes it away."""

    def test_the_directory_is_gone_after_the_invocation_raises(self, tmp_path, monkeypatch):
        sandbox_module = pytest.importorskip("_sandbox")
        monkeypatch.delenv("CF_UX_SHARED_SANDBOX", raising=False)
        monkeypatch.delenv("CF_UX_KEEP_SANDBOX", raising=False)
        monkeypatch.setattr(sandbox_module, "_SANDBOX_PARENT", tmp_path / "cf-ux-sandboxes")
        # `cfs init` in a fresh tree is minutes of work and is not what is under
        # test here; the process-wide signal handlers would outlive the test.
        monkeypatch.setattr(sandbox_module, "_init_sandbox", lambda root: None)
        monkeypatch.setattr(sandbox_module, "_install_handlers_once", lambda: None)
        seen: dict = {}

        def _dies(cmd, **kwargs):
            seen["cwd"] = Path(kwargs["cwd"])
            assert seen["cwd"].is_dir(), "the CLI is handed a real directory to write in"
            raise RuntimeError("the CLI died mid-run")

        monkeypatch.setattr(claude_provider.subprocess, "run", _dies)

        out = claude_provider.call_api("write a PRD")

        assert "unexpected: RuntimeError" in out["error"]
        assert not seen["cwd"].exists(), "and the directory does not outlive the run"
        assert seen["cwd"] not in sandbox_module._LIVE_SANDBOXES


# --------------------------------------- a workflow reached without the router

class TestAWorkflowRunWithoutTheRouter:
    """Measured in a real pilot run: asked to validate an artifact, the model
    invoked `cf-documenting-review` directly and never called `cf`. Studio did the
    work, so the answer is Studio's and worth grading -- but no gate, menu or
    routing decision happened, which is the thing this suite exists to measure.

    Neither pole states that. `failed` files it with the runs where nothing of
    Studio was reached; a pass hides the routing finding in every report
    downstream. Hence a third state, reported in the metadata rather than folded
    into the tally.
    """

    def test_a_cf_workflow_without_the_router_is_bypassed_not_failed(self, run_provider):
        out, _seen = run_provider(_stream(
            _skill_call(skill="cf-documenting-review"),
            _skill_result(),
            _result("findings for 0001-postgres.md"),
        ))

        assert out["output"] == "findings for 0001-postgres.md"
        assert out["metadata"]["skill_state"] == "bypassed"
        assert out["metadata"]["skills_invoked"] == ["cf-documenting-review"]

    def test_the_router_itself_is_still_a_plain_run(self, run_provider):
        """The prefix must not read `cf` as a bypass of itself."""
        out, _seen = run_provider(_stream(_skill_call(), _skill_result(), _result()))

        assert out["metadata"]["skill_state"] == "ran"

    def test_a_workflow_that_errored_is_not_graded(self, run_provider):
        """Same evidence bar as a plain run: a call that came back an error leaves
        only the model's own prose, and grading that reports on Studio for a run
        Studio did not produce."""
        out, _seen = run_provider(_stream(
            _skill_call(skill="cf-documenting-review"),
            _skill_result(is_error=True),
            _result("answered anyway"),
        ))

        assert "output" not in out
        assert out["metadata"]["skill_state"] == "failed"

    def test_a_workflow_with_no_result_is_not_graded(self, run_provider):
        out, _seen = run_provider(_stream(
            _skill_call(skill="cf-documenting-review"), _result("answered anyway")))

        assert "output" not in out
        assert out["metadata"]["skill_state"] == "failed"

    def test_an_unrelated_skill_is_still_a_failure_not_a_bypass(self, run_provider):
        """Only the `cf-` family is a bypass. Anything else running instead is the
        router losing skill selection outright."""
        out, _seen = run_provider(_stream(
            _skill_call(skill="superpowers:brainstorming"),
            _skill_result(),
            _result("answered directly"),
        ))

        assert "output" not in out
        assert out["metadata"]["skill_state"] == "failed"
        assert "none of them named" in out["error"]

    def test_the_bypass_is_logged_by_name(self, run_provider, caplog):
        """A bypass is graded like a pass, so the log is where a person finds out
        it happened without diffing metadata."""
        with caplog.at_level("WARNING", logger=claude_provider.logger.name):
            run_provider(_stream(
                _skill_call(skill="cf-documenting-review"),
                _skill_result(),
                _result(),
            ))

        assert "cf-documenting-review" in caplog.text

    def test_a_bypass_survives_an_unrelated_erroring_false_cf_match(self, run_provider):
        """`targeted` accepts the documented false positive — any field, any depth
        — so one unrelated call carrying `cf` somewhere, and erroring, used to
        skip the bypass check entirely and lose both the finding and a gradeable
        answer."""
        rival = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "A", "name": "Skill", "input": {
                "command": "superpowers:brainstorming", "mode": "cf",
            }},
        ]}}

        out, _seen = run_provider(_stream(
            rival, _skill_result("A", is_error=True),
            _skill_call("B", skill="cf-documenting-review"), _skill_result("B"),
            _result("findings"),
        ))

        assert out["output"] == "findings"
        assert out["metadata"]["skill_state"] == "bypassed"

    def test_a_bare_prefix_is_not_a_workflow_name(self, run_provider):
        """`cf-` is shaped like an identifier and says nothing. "'cf-' ran
        directly" helps nobody triaging a run."""
        out, _seen = run_provider(
            _stream(_skill_call(skill="cf-"), _skill_result(), _result()))

        assert "output" not in out
        assert out["metadata"]["skill_state"] == "failed"

    def test_several_workflow_names_in_one_call_are_reported_as_ambiguous(self, run_provider):
        """The same transparency the `ran` path has: a verdict resting on one of
        several candidates is said out loud."""
        call = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": {
                "a": "cf-generate", "b": "cf-review",
            }},
        ]}}

        out, _seen = run_provider(_stream(call, _skill_result(), _result()))

        assert out["metadata"]["skill_state"] == "bypassed"
        assert out["metadata"]["skill_match_other_candidates"] == ["cf-review"]

    def test_one_workflow_failing_does_not_hide_another_succeeding(self, run_provider):
        """Mixed outcomes across distinct `cf-*` calls: the clean one is the
        evidence, and the failed one does not erase it."""
        out, _seen = run_provider(_stream(
            _skill_call("A", skill="cf-generate"), _skill_result("A", is_error=True),
            _skill_call("B", skill="cf-documenting-review"), _skill_result("B"),
            _result("findings"),
        ))

        assert out["metadata"]["skill_state"] == "bypassed"
        assert out["metadata"]["skills_invoked"] == ["cf-documenting-review", "cf-generate"]

    def test_a_rename_of_the_router_moves_the_workflow_family_with_it(self, run_provider,
                                                                      monkeypatch):
        """Behaviour, not a restatement of the assignment: with the router named
        `zz`, `zz-*` becomes the bypass family and `cf-*` stops being one."""
        monkeypatch.setattr(claude_provider, "_SKILL_NAME", "zz")
        monkeypatch.setattr(claude_provider, "_SKILL_WORKFLOW_PREFIX", "zz-")

        renamed, _seen = run_provider(
            _stream(_skill_call(skill="zz-documenting-review"), _skill_result(), _result()))
        stale, _seen = run_provider(
            _stream(_skill_call(skill="cf-documenting-review"), _skill_result(), _result()))

        assert renamed["metadata"]["skill_state"] == "bypassed"
        assert stale["metadata"]["skill_state"] == "failed"

    def test_a_router_error_outranks_a_successful_direct_workflow(self, run_provider):
        """Precedence, pinned rather than left to the order of the branches.

        `<error>Execute skill: cf</error>` is direct evidence the router itself
        failed. A workflow succeeding afterwards does not soften that: the thing
        this suite measures is the router, and grading the run `bypassed` would
        file a cf failure as a routing observation. The workflow is still named
        in `skills_invoked`, so nothing is lost — only ranked.
        """
        errored = {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "A", "is_error": True,
             "content": "<error>Execute skill: cf</error>"},
        ]}}

        out, _seen = run_provider(_stream(
            _skill_call("A"), errored,
            _skill_call("B", skill="cf-documenting-review"), _skill_result("B"),
            _result("findings"),
        ))

        assert out["metadata"]["skill_state"] == "failed"
        assert "cf-documenting-review" in out["metadata"]["skills_invoked"]

    def test_the_ambiguous_bypass_warning_names_the_reported_one(self, run_provider, caplog):
        """Its own message, not the `ran` one — that says "matched 'cf'", which is
        the one thing that did not happen here."""
        call = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": {
                "a": "cf-generate", "b": "cf-review",
            }},
        ]}}

        with caplog.at_level("WARNING", logger=claude_provider.logger.name):
            run_provider(_stream(call, _skill_result(), _result()))

        assert "rests on more than one candidate" in caplog.text
        assert "matched 'cf'" not in caplog.text


class TestBypassingNamesDirectly:
    """The helper on its own, away from the provider's plumbing."""

    @staticmethod
    def _names(named, results):
        return claude_provider._bypassing_names(named, results)

    def test_a_clean_workflow_call_qualifies(self):
        assert self._names({"a": ["cf-generate"]}, {"a": False}) == ["cf-generate"]

    def test_two_clean_calls_are_unioned(self):
        got = self._names({"a": ["cf-generate"], "b": ["cf-review"]}, {"a": False, "b": False})

        assert got == ["cf-generate", "cf-review"]

    def test_an_errored_call_contributes_nothing(self):
        assert self._names({"a": ["cf-generate"]}, {"a": True}) == []

    def test_a_call_with_no_result_contributes_nothing(self):
        assert self._names({"a": ["cf-generate"]}, {}) == []

    def test_a_call_naming_anything_else_contributes_nothing(self):
        assert self._names({"a": ["cf-generate", "brainstorming"]}, {"a": False}) == []

    def test_the_router_itself_is_not_a_workflow(self):
        assert self._names({"a": ["cf"]}, {"a": False}) == []

    def test_a_bare_prefix_is_not_a_name(self):
        assert self._names({"a": ["cf-"]}, {"a": False}) == []

    def test_a_call_naming_nothing_contributes_nothing(self):
        assert self._names({"a": []}, {"a": False}) == []

    def test_a_router_call_that_errored_outranks_a_bypass(self, run_provider):
        """Without the CLI's literal marker text, an errored `cf` call plus a
        successful workflow read as `bypassed` — and the detail said "'cf' was
        never invoked", which is the opposite of what happened. A router that
        failed is a finding about the router."""
        out, _seen = run_provider(_stream(
            _skill_call("A"), _skill_result("A", is_error=True),
            _skill_call("B", skill="cf-documenting-review"), _skill_result("B"),
            _result("findings"),
        ))

        assert out["metadata"]["skill_state"] == "failed"
        assert "came back as an error" in out["error"]

    def test_a_router_call_with_no_result_outranks_a_bypass(self, run_provider):
        out, _seen = run_provider(_stream(
            _skill_call("A"),
            _skill_call("B", skill="cf-documenting-review"), _skill_result("B"),
            _result("findings"),
        ))

        assert out["metadata"]["skill_state"] == "failed"

    def test_only_an_unambiguous_router_call_outranks_a_bypass(self, run_provider):
        """The documented false positive must not suppress a real bypass — that
        was the earlier defect. A call naming `cf` *among others* is that case."""
        rival = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "A", "name": "Skill", "input": {
                "command": "superpowers:brainstorming", "mode": "cf",
            }},
        ]}}

        out, _seen = run_provider(_stream(
            rival, _skill_result("A", is_error=True),
            _skill_call("B", skill="cf-documenting-review"), _skill_result("B"),
            _result("findings"),
        ))

        assert out["metadata"]["skill_state"] == "bypassed"
        assert out["output"] == "findings"

    def test_the_detail_claims_only_what_the_evidence_carries(self):
        """With `cf` named only by the loose match, "never invoked" would claim
        more than is known — the call may well have been the router."""
        events = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "A", "name": "Skill", "input": {
                    "command": "superpowers:brainstorming", "mode": "cf"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "A", "is_error": True, "content": "x"}]}},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "B", "name": "Skill",
                 "input": {"skill": "cf-documenting-review"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "B", "content": "ok"}]}},
        ]

        trace = claude_provider._skill_trace(events, json.dumps(events))

        assert trace.state == "bypassed"
        assert "never invoked" not in trace.detail
        assert "no unambiguous" in trace.detail

    def test_the_detail_does_say_never_invoked_when_that_is_true(self):
        events = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "B", "name": "Skill",
                 "input": {"skill": "cf-documenting-review"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "B", "content": "ok"}]}},
        ]

        trace = claude_provider._skill_trace(events, json.dumps(events))

        assert trace.state == "bypassed"
        assert "never invoked" in trace.detail


# ------------------------------------------------- what the subprocess inherits

class TestTheSubprocessDoesNotInheritTheRunnersSecrets:
    """The CLI is started with `--permission-mode bypassPermissions`. Whatever the
    parent is carrying, it should not be carrying it *there*.

    `cwd=` sandboxes the filesystem; it does nothing for environment variables, and
    `subprocess.run` without `env=` passes the lot. On CI the lot includes
    GITHUB_TOKEN and cloud credentials.
    """

    @pytest.mark.parametrize("name", [
        "GITHUB_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
        # A runner carries GitHub's own ephemeral credentials too, and they are exactly
        # the kind a denylist written today would not have heard of.
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
        "ACTIONS_RUNTIME_TOKEN",
        # The invariant, not a list: an allowlist excludes what nobody thought of. A
        # denylist that happened to name the four above would pass the cases above and
        # fail this one (#229 review).
        "CF_SOME_VARIABLE_NOBODY_ANTICIPATED",
    ])
    def test_an_unrelated_variable_is_not_passed_through(self, run_provider, monkeypatch, name):
        monkeypatch.setenv(name, "should_not_travel")

        _out, seen = run_provider(_stream(_skill_call(), _skill_result(), _result()))

        env = seen["kwargs"]["env"]
        assert name not in env
        assert "should_not_travel" not in env.values()

    def test_every_allowlisted_name_survives_when_set(self, run_provider, monkeypatch):
        """The positive half of the invariant, over the whole list rather than a sample."""
        from _sandbox import ENV_NAMES

        for index, name in enumerate(ENV_NAMES):
            monkeypatch.setenv(name, f"value-{index}")

        _out, seen = run_provider(_stream(_skill_call(), _skill_result(), _result()))

        env = seen["kwargs"]["env"]
        missing = [name for name in ENV_NAMES if env.get(name) is None]
        assert not missing, f"allowlisted names dropped by the filter: {missing}"

    def test_the_harness_namespace_is_not_forwarded(self, run_provider, monkeypatch):
        """`CF_UX_*` is read by this Python parent, never by the `claude` binary."""
        monkeypatch.setenv("CF_UX_CLAUDE_MODEL", "some-model")

        _out, seen = run_provider(_stream(_skill_call(), _skill_result(), _result()))

        assert "CF_UX_CLAUDE_MODEL" not in seen["kwargs"]["env"]

    def test_what_the_cli_needs_does_come_through(self, run_provider, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/tmp/cfg")

        _out, seen = run_provider(_stream(_skill_call(), _skill_result(), _result()))

        env = seen["kwargs"]["env"]
        assert env["ANTHROPIC_API_KEY"] == "sk-test"      # its own credential, not a stray one
        assert env["CLAUDE_CONFIG_DIR"] == "/tmp/cfg"
        assert "PATH" in env                              # or `claude` is not findable
        assert "HOME" in env                              # its config and credential store

    def test_an_env_is_passed_at_all(self, run_provider):
        """The defect was the absence of the argument, so pin the argument."""
        _out, seen = run_provider(_stream(_skill_call(), _skill_result(), _result()))

        assert seen["kwargs"].get("env") is not None


# ------------------------------------ an omitted `is_error` is this CLI's success

class TestAToolResultWithoutIsErrorIsTheSuccessShape:
    """Measured against claude-code 2.1.276: a successful `Skill` result carries
    exactly `{"type", "tool_use_id", "content"}`, content "Launching skill: cf", and
    no `is_error` at all -- while `Bash` and `Read` results in the same transcript
    carry it explicitly. Reading the omission as missing evidence (#229's first
    attempt) graded every real successful run as a failure.

    What genuinely proves nothing is a call with no `tool_result` whatsoever, and
    that is still refused.
    """

    def test_a_missing_is_error_is_graded_as_a_run(self, run_provider):
        out, _seen = run_provider(
            _stream(_skill_call(), _skill_result_without_flag(), _result("the answer")))

        assert out["output"] == "the answer"
        assert out["metadata"]["skill_state"] == "ran"

    def test_no_tool_result_at_all_is_not_a_run(self, run_provider):
        """A stream cut short after the call -- nothing ever reported what it did."""
        out, _seen = run_provider(_stream(_skill_call(), _result("answered anyway")))

        assert "output" not in out
        assert out["metadata"]["skill_state"] == "failed"
        assert "no result in the transcript" in out["error"]

    def test_an_explicit_false_is_still_a_run(self, run_provider):
        out, _seen = run_provider(
            _stream(_skill_call(), _skill_result(is_error=False), _result("the answer")))

        assert out["output"] == "the answer"
        assert out["metadata"]["skill_state"] == "ran"

    def test_an_explicit_true_is_still_a_failure(self, run_provider):
        out, _seen = run_provider(
            _stream(_skill_call(), _skill_result(is_error=True), _result("answered anyway")))

        assert "output" not in out
        assert out["metadata"]["skill_state"] == "failed"


class TestTheChildsOwnCredentialDoesNotComeBackOut:
    """The provider hands its CLI a real API key and then returns that CLI's stderr,
    stdout tail and result text as promptfoo metadata — stored, and read by people. A
    CLI that echoes its key in an error ("invalid x-api-key: sk-ant-…") would put it in
    the report. Raised on #229's review.
    """

    _KEY = "sk-ant-secret-value-not-for-reports"

    def test_a_key_echoed_on_stderr_is_redacted(self, run_provider, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", self._KEY)

        out, _seen = run_provider("", returncode=2, stderr=f"invalid x-api-key: {self._KEY}")

        assert self._KEY not in out["error"]
        assert "[redacted]" in out["error"]

    def test_a_key_echoed_in_the_stdout_tail_is_redacted(self, run_provider, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", self._KEY)

        out, _seen = run_provider(f"no result event here, but a key: {self._KEY}\n")

        assert self._KEY not in json.dumps(out)

    def test_a_key_in_withheld_output_is_redacted(self, run_provider, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", self._KEY)

        # A skill call with no result: the answer is withheld, and carried in metadata.
        out, _seen = run_provider(
            _stream(_skill_call(), _result(f"leaked {self._KEY} in the answer")))

        assert self._KEY not in json.dumps(out)

    def test_ordinary_diagnostics_are_left_readable(self, run_provider, monkeypatch):
        """Only credential-ish names are redacted. PATH and HOME appear in real
        diagnostics constantly, and blanking them destroys what a reader needs."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", self._KEY)

        out, _seen = run_provider("", returncode=2, stderr="command not found: claude")

        assert "command not found: claude" in out["error"]


class TestDiagnosticsStayBounded:
    """`stderr`, `stdout_tail` and `unscored_output` are each sliced before they
    are returned. `skill_call_inputs` was not — and it is the one field whose
    length a model, and so a crafted prompt, decides."""

    def test_a_huge_skill_input_is_capped_like_its_siblings(self, run_provider):
        huge = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill",
             "input": {"command": "cf", "args": "A" * 50_000}},
        ]}}

        out, _seen = run_provider(_stream(huge, _skill_result(), _result()))

        for item in out["metadata"]["skill_call_inputs"]:
            assert len(item) <= claude_provider._MAX_DIAGNOSTIC_CHARS


class TestTheCliVersionIsRecorded:
    """The verdict rests on an output shape that was measured, not promised:
    an absent `is_error` means success. Nothing pins the installed CLI, so the
    run records which version it was graded against."""

    def test_the_version_from_the_init_event_reaches_metadata(self, run_provider):
        init = {"type": "system", "subtype": "init", "claude_code_version": "2.1.276"}

        out, _seen = run_provider(_stream(init, _skill_call(), _skill_result(), _result()))

        assert out["metadata"]["claude_code_version"] == "2.1.276"

    def test_a_stream_without_one_is_not_an_error(self, run_provider):
        """An older or newer CLI is the case this records; not finding it is an
        answer, not a failure."""
        out, _seen = run_provider(_stream(_skill_call(), _skill_result(), _result()))

        assert out["metadata"]["claude_code_version"] is None

    def test_an_over_long_version_is_capped(self, run_provider):
        """It comes from the CLI rather than from a model, so the risk is small —
        but a field bounded only by where it happens to come from is one source
        change away from not being bounded."""
        init = {"type": "system", "subtype": "init", "claude_code_version": "9" * 10_000}

        out, _seen = run_provider(_stream(init, _skill_call(), _skill_result(), _result()))

        assert len(out["metadata"]["claude_code_version"]) == (
            claude_provider._MAX_DIAGNOSTIC_CHARS)

    def test_a_version_string_carrying_a_secret_is_redacted(self, run_provider, monkeypatch):
        secret = "sk-ant-api03-SUPERSECRETVALUE0123456789"
        monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
        init = {"type": "system", "subtype": "init",
                "claude_code_version": f"2.1.276 ({secret})"}

        out, _seen = run_provider(_stream(init, _skill_call(), _skill_result(), _result()))

        version = out["metadata"]["claude_code_version"]
        assert secret not in version
        assert "[redacted]" in version and version.startswith("2.1.276")

    def test_an_empty_version_string_is_none_not_an_empty_string(self, run_provider):
        """`_safe_head("")` is `""`, and an empty string in metadata reads as a
        version that was reported as blank rather than one never reported."""
        init = {"type": "system", "subtype": "init", "claude_code_version": ""}

        out, _seen = run_provider(_stream(init, _skill_call(), _skill_result(), _result()))

        assert out["metadata"]["claude_code_version"] is None

    def test_a_non_string_version_is_not_passed_through(self, run_provider):
        init = {"type": "system", "subtype": "init", "claude_code_version": {"major": 2}}

        out, _seen = run_provider(_stream(init, _skill_call(), _skill_result(), _result()))

        assert out["metadata"]["claude_code_version"] is None


class TestACutNeverLandsInsideASecret:
    """`redact_secrets` matches whole values. Cutting first can land inside a
    credential, and the surviving prefix is one the redactor no longer
    recognises — so a size cap, added for safety, leaked the start of a key."""

    _SECRET = "sk-ant-api03-SUPERSECRETVALUE0123456789"

    def test_a_secret_straddling_the_head_cut_does_not_survive(self):
        limit = claude_provider._MAX_DIAGNOSTIC_CHARS
        text = "A" * (limit - 10) + self._SECRET

        got = claude_provider._safe_head(text, {"ANTHROPIC_API_KEY": self._SECRET})

        assert self._SECRET[:10] not in got
        assert "[redacted]" in got
        assert len(got) <= limit

    def test_a_secret_straddling_the_tail_cut_does_not_survive(self):
        limit = claude_provider._MAX_DIAGNOSTIC_CHARS
        text = self._SECRET + "B" * (limit - 10)

        got = claude_provider._safe_tail(text, {"ANTHROPIC_API_KEY": self._SECRET})

        assert self._SECRET[-10:] not in got
        assert len(got) <= limit

    def test_the_head_cap_still_caps(self):
        got = claude_provider._safe_head("A" * 10_000, {})

        assert len(got) == claude_provider._MAX_DIAGNOSTIC_CHARS

    def test_the_tail_cap_still_caps(self):
        """The same ceiling from the other end — asserted, not assumed from its
        sibling: they are separate functions and only one was pinned."""
        got = claude_provider._safe_tail("A" * 10_000, {})

        assert len(got) == claude_provider._MAX_DIAGNOSTIC_CHARS

    def test_the_tail_keeps_the_end_and_the_head_keeps_the_start(self):
        text = "START" + "A" * 10_000 + "END"

        assert claude_provider._safe_head(text, {}).startswith("START")
        assert claude_provider._safe_tail(text, {}).endswith("END")

    def test_a_straddling_secret_does_not_reach_skill_call_inputs(self, run_provider, monkeypatch):
        """End to end, through the field the cap was added to."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", self._SECRET)
        padding = "A" * (claude_provider._MAX_DIAGNOSTIC_CHARS - 10)
        call = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill",
             "input": {"command": "cf", "args": padding + self._SECRET}},
        ]}}

        out, _seen = run_provider(_stream(call, _skill_result(), _result()))

        for item in out["metadata"]["skill_call_inputs"]:
            assert self._SECRET[:12] not in item


# ------------------------------------ the runner's home is closed to the tools

class TestTheRunnersHomeIsClosedToTheChildsTools:
    """`bypassPermissions` switches off the prompts, not the deny rules, and `cwd=`
    is where the child works rather than a wall: an ungated Read or Write resolves
    `~` and absolute paths against the runner's real home (#229 review). The
    invocation therefore carries deny rules for that home, and every refusal comes
    back as metadata -- a run in which the model reached for the runner's home is
    a finding, not noise.

    What these tests do not claim: that the CLI honours the rules. That was
    measured on 2.1.281 for Read, Write and Bash, and belongs to whoever can run
    one; what is pinned here is that the rules are passed, and what they name.
    """

    @staticmethod
    def _settings(seen: dict) -> dict:
        cmd = seen["cmd"]
        return json.loads(cmd[cmd.index("--settings") + 1])

    def test_the_invocation_carries_deny_rules_for_the_runners_home(self, run_provider):
        _out, seen = run_provider(_stream(_skill_call(), _skill_result(), _result()))

        deny = self._settings(seen)["permissions"]["deny"]
        runner_home = str(Path.home()).lstrip("/")
        assert f"Read(//{runner_home}/**)" in deny
        assert f"Edit(//{runner_home}/**)" in deny, "Edit rules govern Write too"

    def test_the_rules_name_the_home_both_ways(self):
        """Under `CF_UX_ISOLATED_HOME` `~` is the sandbox's home and the runner's
        is reachable only by absolute path, so both spellings are needed."""
        rules = claude_provider.permission_deny_rules(Path("/home/someone"))

        assert set(rules) == {
            "Read(//home/someone/**)", "Edit(//home/someone/**)",
            "Read(~/**)", "Edit(~/**)",
        }

    def test_the_settings_are_inline_not_a_file(self, run_provider, tmp_path):
        """Nothing is written for the child to find, or for the sandbox wipe to miss."""
        _out, seen = run_provider(_stream(_skill_call(), _skill_result(), _result()))

        cmd = seen["cmd"]
        argument = cmd[cmd.index("--settings") + 1]
        assert argument.startswith("{"), "a JSON document, not a path"
        assert not list(tmp_path.glob("*.json"))

    def test_a_refusal_reaches_the_metadata_and_the_log(self, run_provider, caplog):
        denials = [
            {"tool_name": "Read", "tool_use_id": "t9",
             "tool_input": {"file_path": "/home/someone/.ssh/id_rsa"}},
            {"tool_name": "Bash", "tool_use_id": "t10",
             "tool_input": {"command": "cat ~/.aws/credentials"}},
        ]

        with caplog.at_level("WARNING", logger=claude_provider.logger.name):
            out, _seen = run_provider(_stream(
                _skill_call(), _skill_result(), _result(permission_denials=denials)))

        reported = out["metadata"]["permission_denials"]
        assert [d["tool"] for d in reported] == ["Read", "Bash"]
        assert ".ssh/id_rsa" in reported[0]["input"]
        assert "refused 2 tool call(s)" in caplog.text
        assert "Bash, Read" in caplog.text

    def test_no_refusal_is_an_empty_list_and_silence(self, run_provider, caplog):
        with caplog.at_level("WARNING", logger=claude_provider.logger.name):
            out, _seen = run_provider(_stream(_skill_call(), _skill_result(), _result()))

        assert out["metadata"]["permission_denials"] == []
        assert "refused" not in caplog.text

    @pytest.mark.parametrize("shape", ["not-a-list", {"tool_name": "Read"}, None, 3])
    def test_an_unfamiliar_shape_reads_as_no_refusals(self, run_provider, shape):
        out, _seen = run_provider(_stream(
            _skill_call(), _skill_result(), _result(permission_denials=shape)))

        assert out["metadata"]["permission_denials"] == []

    def test_a_refused_input_is_redacted_and_bounded(self, run_provider, monkeypatch):
        """Model-authored, so it gets the same treatment as every other such field."""
        secret = "sk-ant-" + "Z" * 40
        monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
        denials = [{"tool_name": "Bash", "tool_use_id": "t1",
                    "tool_input": {"command": "echo " + secret + "A" * 10_000}}]

        out, _seen = run_provider(_stream(
            _skill_call(), _skill_result(), _result(permission_denials=denials)))

        item = out["metadata"]["permission_denials"][0]["input"]
        assert secret not in item
        assert len(item) <= claude_provider._MAX_DIAGNOSTIC_CHARS


# ------------------------------------------------ whose home the child was given

class TestTheReportSaysWhoseHomeTheChildHad:
    """An isolated run has no competing plugins, so it is a different measurement,
    and the report has to say which one it was (#229 review)."""

    def test_by_default_it_is_the_runners(self, run_provider, monkeypatch):
        monkeypatch.delenv("CF_UX_ISOLATED_HOME", raising=False)

        out, seen = run_provider(_stream(_skill_call(), _skill_result(), _result()))

        assert out["metadata"]["home"] == "runner"
        assert seen["kwargs"]["env"].get("HOME") == str(Path.home())

    def test_on_request_it_is_a_home_inside_the_sandbox(
            self, run_provider, monkeypatch, tmp_path):
        credential = tmp_path / "store" / ".credentials.json"
        credential.parent.mkdir()
        credential.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(claude_provider, "_claude_credential", lambda: credential)
        monkeypatch.setenv("CF_UX_ISOLATED_HOME", "1")
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/the/runners/config")

        out, seen = run_provider(_stream(_skill_call(), _skill_result(), _result()))

        env = seen["kwargs"]["env"]
        assert out["metadata"]["home"] == "isolated"
        assert Path(env["HOME"]).is_relative_to(tmp_path)
        assert "CLAUDE_CONFIG_DIR" not in env, "it points back at the runner's configuration"

    def test_the_credential_is_looked_for_under_claude_config_dir_when_set(
            self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))

        assert claude_provider._claude_credential() == tmp_path / "cfg" / ".credentials.json"

    def test_and_under_the_home_otherwise(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)

        assert claude_provider._claude_credential() == Path.home() / ".claude" / ".credentials.json"

    def test_a_timeout_says_so_too(self, run_provider, monkeypatch, tmp_path):
        credential = tmp_path / ".credentials.json"
        credential.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(claude_provider, "_claude_credential", lambda: credential)
        monkeypatch.setenv("CF_UX_ISOLATED_HOME", "1")

        out, _seen = run_provider(
            "", raises=subprocess.TimeoutExpired(cmd=["claude"], timeout=850))

        assert out["metadata"]["home"] == "isolated"


class TestTheGradedAnswerIsRedactedToo:
    """Every other returned field went through `redact_secrets`; the answer itself,
    the one field the model writes freely, did not (#229 review). Redacted but not
    capped: the grader has to see all of it."""

    _SECRET = "sk-ant-api03-ANSWERSECRETVALUE0123456789"

    def test_a_key_in_the_answer_does_not_reach_the_report(self, run_provider, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", self._SECRET)
        answer = "Here is your key: " + self._SECRET + ". Done."

        out, _seen = run_provider(_stream(_skill_call(), _skill_result(), _result(text=answer)))

        assert self._SECRET not in out["output"]
        assert out["output"] == "Here is your key: [redacted]. Done."

    def test_a_long_answer_is_not_cut(self, run_provider, monkeypatch):
        """A guard, passing before the change too: redaction must not become a cap."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", self._SECRET)
        answer = "A" * (claude_provider._MAX_DIAGNOSTIC_CHARS * 20)

        out, _seen = run_provider(_stream(_skill_call(), _skill_result(), _result(text=answer)))

        assert out["output"] == answer
