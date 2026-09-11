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
        def _fake_run(cmd, **_kwargs):
            seen["cmd"] = list(cmd)
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
        out, _seen = run_provider(
            _stream(_skill_call(skill="cf-generate"), _skill_result(), _result()),
        )

        assert "output" not in out
        assert "none of them named 'cf'" in out["error"]
        assert out["metadata"]["skill_state"] == "failed"

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
        assert set(out["metadata"]) == {"duration_s", "sandbox"}
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
