"""Tests for verify-completion: a run is complete only if every plan item is satisfied.

The contract these pin: an unsatisfied, unstated, conflicting, or unrecognised verdict all
make the run incomplete and exit 2; a plan or verdicts file that will not load is a fault and
exits 1; an empty checklist is a stated vacuous pass; and every item records one verification
event, so the close is auditable.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/studio/scripts"))

from studio import cli  # noqa: E402
from studio.commands import verify_completion as vc  # noqa: E402
from studio.utils import decision_log as dl  # noqa: E402

_MANIFEST = '[plan]\ntask = "t"\n[[phases]]\nnumber = 1\nfile = "p.md"\n'
_TWO_CRITERIA = "## Acceptance Criteria\n- [ ] A exists\n- [ ] B passes\n"


def _plan(tmp_path: Path, *, manifest: str = _MANIFEST,
          phase: str = _TWO_CRITERIA, verdicts: str = "") -> tuple[Path, Path]:
    """Write a plan dir (plan.toml + p.md) and a verdicts file; return (plan_dir, verdicts_path)."""
    (tmp_path / "plan.toml").write_text(manifest, encoding="utf-8")
    (tmp_path / "p.md").write_text(phase, encoding="utf-8")
    verdicts_path = tmp_path / "verdicts.toml"
    verdicts_path.write_text(verdicts, encoding="utf-8")
    return tmp_path, verdicts_path


def _verdict(item: str, verdict: str, evidence: str = "ok") -> str:
    return f'[[verdicts]]\nitem = "{item}"\nverdict = "{verdict}"\nevidence = "{evidence}"\n'


def test_all_satisfied_is_complete_and_exits_zero(tmp_path: Path) -> None:
    plan_dir, vpath = _plan(tmp_path,
                            verdicts=_verdict("A exists", "satisfied") + _verdict("B passes", "satisfied"))
    result = vc.assess(plan_dir, vpath)
    assert result.status == "COMPLETE"
    assert result.exit_code == 0
    assert result.checked == 2


def test_a_not_satisfied_item_is_incomplete_and_exits_two(tmp_path: Path) -> None:
    plan_dir, vpath = _plan(tmp_path,
                            verdicts=_verdict("A exists", "satisfied") + _verdict("B passes", "not-satisfied"))
    result = vc.assess(plan_dir, vpath)
    assert result.status == "INCOMPLETE"
    assert result.exit_code == 2
    assert result.unsatisfied == ["B passes"]


def test_an_item_with_no_verdict_is_unstated_and_incomplete(tmp_path: Path) -> None:
    plan_dir, vpath = _plan(tmp_path, verdicts=_verdict("A exists", "satisfied"))
    result = vc.assess(plan_dir, vpath)
    assert result.status == "INCOMPLETE"
    assert result.exit_code == 2
    assert result.unstated == ["B passes"]


def test_not_applicable_items_do_not_block_completion(tmp_path: Path) -> None:
    plan_dir, vpath = _plan(tmp_path,
                            verdicts=_verdict("A exists", "satisfied") + _verdict("B passes", "not-applicable"))
    result = vc.assess(plan_dir, vpath)
    assert result.status == "COMPLETE"
    assert result.exit_code == 0


def test_conflicting_verdicts_make_an_item_not_satisfied(tmp_path: Path) -> None:
    doubled = _verdict("A exists", "satisfied") + _verdict("A exists", "not-satisfied")
    plan_dir, vpath = _plan(tmp_path, phase="## Acceptance Criteria\n- [ ] A exists\n",
                            verdicts=doubled)
    result = vc.assess(plan_dir, vpath)
    assert result.status == "INCOMPLETE"
    assert result.unsatisfied == ["A exists"]


def test_an_unrecognised_verdict_is_not_satisfied(tmp_path: Path) -> None:
    # `verdict = "done"` is outside the enumerated set and must not pass as satisfied.
    plan_dir, vpath = _plan(tmp_path, phase="## Acceptance Criteria\n- [ ] A exists\n",
                            verdicts=_verdict("A exists", "done"))
    result = vc.assess(plan_dir, vpath)
    assert result.status == "INCOMPLETE"
    assert result.exit_code == 2
    assert result.unsatisfied == ["A exists"]


def test_a_plan_that_will_not_load_is_a_fault_exit_one(tmp_path: Path) -> None:
    vpath = tmp_path / "verdicts.toml"
    vpath.write_text("", encoding="utf-8")
    (tmp_path / "plan.toml").write_text('phases = "oops"\n[plan]\ntask = "t"\n', encoding="utf-8")
    result = vc.assess(tmp_path, vpath)
    assert result.status == "ERROR"
    assert result.exit_code == 1


def test_a_verdicts_file_that_will_not_parse_is_a_fault(tmp_path: Path) -> None:
    plan_dir, vpath = _plan(tmp_path, verdicts="")
    vpath.write_text("verdicts = = broken toml", encoding="utf-8")
    result = vc.assess(plan_dir, vpath)
    assert result.status == "ERROR"
    assert result.exit_code == 1


def test_a_plan_with_no_criteria_is_a_stated_vacuous_pass(tmp_path: Path) -> None:
    plan_dir, vpath = _plan(tmp_path, phase="## What\nnothing to check\n", verdicts="")
    result = vc.assess(plan_dir, vpath)
    assert result.status == "COMPLETE"
    assert result.exit_code == 0
    assert result.applicable is False


def test_an_unreadable_phase_blocks_completion(tmp_path: Path) -> None:
    # The manifest points at a phase file that does not exist: its criteria are unknown, so the
    # run cannot be shown complete even though the one readable item is satisfied.
    manifest = (_MANIFEST + '[[phases]]\nnumber = 2\nfile = "missing.md"\n')
    plan_dir, vpath = _plan(tmp_path, manifest=manifest,
                            verdicts=_verdict("A exists", "satisfied") + _verdict("B passes", "satisfied"))
    result = vc.assess(plan_dir, vpath)
    assert result.status == "INCOMPLETE"
    assert result.exit_code == 2
    assert any("phase 2" in p for p in result.read_problems)


def test_a_verdict_for_an_unknown_item_is_reported_not_blocking(tmp_path: Path) -> None:
    verdicts = (_verdict("A exists", "satisfied") + _verdict("B passes", "satisfied")
                + _verdict("Z nonexistent", "satisfied"))
    plan_dir, vpath = _plan(tmp_path, verdicts=verdicts)
    result = vc.assess(plan_dir, vpath)
    assert result.status == "COMPLETE"
    assert result.unmatched_verdicts == ["Z nonexistent"]


def test_each_item_records_one_verification_event(tmp_path: Path) -> None:
    plan_dir, vpath = _plan(tmp_path,
                            verdicts=_verdict("A exists", "satisfied") + _verdict("B passes", "not-satisfied"))
    log_path = tmp_path / ".cache" / "decisions.jsonl"
    vc.assess(plan_dir, vpath, log_path=log_path)
    events = [e for e in dl.read_events(path=log_path) if e["event"] == "verification"]
    assert len(events) == 2
    verdicts = {e["payload"]["item"]: e["payload"]["verdict"] for e in events}
    assert verdicts == {"A exists": "satisfied", "B passes": "not-satisfied"}
    # Each event carries its plan phase, so same-text items in different phases stay distinct.
    assert all(e["payload"]["phase"] == 1 for e in events)


@pytest.mark.parametrize("verdict_value, expected_exit", [("satisfied", 0), ("not-satisfied", 2)])
def test_cli_entry_point_returns_the_contract_exit_code(
    tmp_path: Path, verdict_value: str, expected_exit: int
) -> None:
    plan_dir, _ = _plan(tmp_path, phase="## Acceptance Criteria\n- [ ] A exists\n",
                        verdicts=_verdict("A exists", verdict_value))
    assert vc.cmd_verify_completion([str(plan_dir)]) == expected_exit


def test_cli_missing_plan_is_a_fault_exit_one(tmp_path: Path) -> None:
    assert vc.cmd_verify_completion([str(tmp_path / "nowhere")]) == 1


def test_a_non_array_verdicts_table_is_a_fault(tmp_path: Path) -> None:
    # A `verdicts` key that is present but not an array is the author's defect, not a verdict.
    plan_dir, vpath = _plan(tmp_path, verdicts="")
    vpath.write_text('verdicts = "oops"\n', encoding="utf-8")
    result = vc.assess(plan_dir, vpath)
    assert result.status == "ERROR"
    assert result.exit_code == 1


def test_malformed_verdict_entries_are_skipped(tmp_path: Path) -> None:
    # A non-table entry and an empty-item entry are skipped; the real one still counts.
    plan_dir, vpath = _plan(tmp_path, phase="## Acceptance Criteria\n- [ ] A exists\n", verdicts="")
    vpath.write_text(
        'verdicts = [ 1, { item = "", verdict = "satisfied" }, '
        '{ item = "A exists", verdict = "satisfied", evidence = "ok" } ]\n',
        encoding="utf-8")
    result = vc.assess(plan_dir, vpath)
    assert result.status == "COMPLETE"
    assert result.exit_code == 0


@pytest.mark.parametrize("status, headline", [
    ("COMPLETE", "success"), ("ERROR", "error"), ("INCOMPLETE", "error")])
def test_say_routes_each_status_to_the_right_ui_call(
    status: str, headline: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(vc.ui, "success", lambda m: calls.append(("success", m)))
    monkeypatch.setattr(vc.ui, "error", lambda m: calls.append(("error", m)))
    monkeypatch.setattr(vc.ui, "detail", lambda k, v: calls.append(("detail", k, v)))
    payload = {"status": status, "message": "the message",
               "unsatisfied": ["item X"], "unstated": ["item Y"],
               "blocked_on_question": ["item Z"]}
    vc._say(payload)
    assert calls[0] == (headline, "verify-completion: the message")
    # Only INCOMPLETE lists the blocking items; COMPLETE/ERROR stop at the headline.
    details = [c for c in calls if c[0] == "detail"]
    if status == "INCOMPLETE":
        assert ("detail", "not satisfied", "item X") in details
        assert ("detail", "no verdict", "item Y") in details
        assert ("detail", "waits on an open question", "item Z") in details
    else:
        assert details == []


_TWO_PHASE_SHARED = ('[plan]\ntask = "t"\n[[phases]]\nnumber = 1\nfile = "p1.md"\n'
                     '[[phases]]\nnumber = 2\nfile = "p2.md"\n')


def _shared_criterion_plan(tmp_path: Path, verdicts: str) -> tuple[Path, Path]:
    """A plan whose two phases declare the SAME criterion text."""
    (tmp_path / "plan.toml").write_text(_TWO_PHASE_SHARED, encoding="utf-8")
    body = "## Acceptance Criteria\n- [ ] No unresolved variables\n"
    (tmp_path / "p1.md").write_text(body, encoding="utf-8")
    (tmp_path / "p2.md").write_text(body, encoding="utf-8")
    vpath = tmp_path / "verdicts.toml"
    vpath.write_text(verdicts, encoding="utf-8")
    return tmp_path, vpath


def test_same_criterion_in_two_phases_completes_with_phased_verdicts(tmp_path: Path) -> None:
    # The MAJOR fix: a criterion repeated across phases is answerable per phase via `phase`.
    plan_dir, vpath = _shared_criterion_plan(
        tmp_path,
        '[[verdicts]]\nphase = 1\nitem = "No unresolved variables"\nverdict = "satisfied"\nevidence = "ok"\n'
        '[[verdicts]]\nphase = 2\nitem = "No unresolved variables"\nverdict = "satisfied"\nevidence = "ok"\n')
    result = vc.assess(plan_dir, vpath)
    assert result.status == "COMPLETE"
    assert result.exit_code == 0
    assert result.checked == 2


def test_same_criterion_in_two_phases_is_ambiguous_without_a_phase(tmp_path: Path) -> None:
    # A single phase-less verdict cannot answer a criterion that appears in two phases, so it
    # does not silently pass both -- the run is incomplete until the author disambiguates.
    plan_dir, vpath = _shared_criterion_plan(
        tmp_path,
        '[[verdicts]]\nitem = "No unresolved variables"\nverdict = "satisfied"\nevidence = "ok"\n')
    result = vc.assess(plan_dir, vpath)
    assert result.status == "INCOMPLETE"
    assert result.exit_code == 2
    assert result.unstated == ["No unresolved variables", "No unresolved variables"]


def test_phased_conflicting_verdicts_are_not_satisfied(tmp_path: Path) -> None:
    # Two verdicts for the SAME (phase, criterion) conflict -> not-satisfied for that item
    # (the symmetric case to the phase-less conflict test above).
    plan_dir, vpath = _plan(tmp_path, phase="## Acceptance Criteria\n- [ ] A exists\n", verdicts="")
    vpath.write_text(
        '[[verdicts]]\nphase = 1\nitem = "A exists"\nverdict = "satisfied"\nevidence = "a"\n'
        '[[verdicts]]\nphase = 1\nitem = "A exists"\nverdict = "not-satisfied"\nevidence = "b"\n',
        encoding="utf-8")
    result = vc.assess(plan_dir, vpath)
    assert result.status == "INCOMPLETE"
    assert result.unsatisfied == ["A exists"]


def test_classification_does_not_depend_on_evidence_text(tmp_path: Path) -> None:
    # The MINOR fix: a real not-satisfied whose evidence contains the "no verdict" phrase is
    # still classified as unsatisfied, not unstated -- the reason tag decides, not the evidence.
    plan_dir, vpath = _plan(tmp_path, phase="## Acceptance Criteria\n- [ ] A exists\n", verdicts="")
    vpath.write_text(
        '[[verdicts]]\nitem = "A exists"\nverdict = "not-satisfied"\n'
        'evidence = "no verdict was recorded in the upstream log"\n', encoding="utf-8")
    result = vc.assess(plan_dir, vpath)
    assert result.status == "INCOMPLETE"
    assert result.unsatisfied == ["A exists"]
    assert result.unstated == []


def _defer(key: str, log: Path) -> None:
    """Record an open (parked) question for ``key`` in the log the register reads."""
    dl.record_gate("open-question", "SomeGate", "decision",
                   dl.GateRuling(decision_key=key, why="the plan is silent", status="absent"),
                   command="gate-log", path=log)


def _answer(key: str, log: Path) -> None:
    """Record an answer that closes the open question ``key``."""
    dl.record_gate("plan-resolved", "SomeGate", "decision",
                   dl.GateRuling(decision_key=key, value="chosen", provenance="plan",
                                 status="resolved", cost_if_wrong="re-run"),
                   command="gate-log", path=log)


_NEEDS_PHASE = "## Acceptance Criteria\n- [ ] PRD approved (needs: pricing_model)\n"
# The marker is NOT stripped from the item text (so two criteria differing only by their
# marker stay distinct), so a verdict is keyed by the full criterion text.
_NEEDS_ITEM = "PRD approved (needs: pricing_model)"


def test_item_waiting_on_an_open_question_is_incomplete_even_if_satisfied(tmp_path: Path) -> None:
    # The dependency overrides the verdict: a satisfied item that still waits on an
    # unanswered question cannot be shown done.
    log = tmp_path / "log.jsonl"
    _defer("pricing_model", log)
    plan_dir, vpath = _plan(tmp_path, phase=_NEEDS_PHASE,
                            verdicts=_verdict(_NEEDS_ITEM, "satisfied"))
    result = vc.assess(plan_dir, vpath, log_path=log)
    assert result.status == "INCOMPLETE"
    assert result.exit_code == 2
    assert result.blocked_on_question == [_NEEDS_ITEM]
    assert result.unsatisfied == []  # blocked, not "unsatisfied" -- a distinct cause


def test_answering_the_question_lets_the_item_complete(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    _defer("pricing_model", log)
    _answer("pricing_model", log)  # the register no longer holds the key
    plan_dir, vpath = _plan(tmp_path, phase=_NEEDS_PHASE,
                            verdicts=_verdict(_NEEDS_ITEM, "satisfied"))
    result = vc.assess(plan_dir, vpath, log_path=log)
    assert result.status == "COMPLETE"
    assert result.exit_code == 0
    assert result.blocked_on_question == []


def test_dependency_on_a_never_raised_question_blocks(tmp_path: Path) -> None:
    # A declared dependency on a question nobody ever raised is NOT assumed irrelevant: it
    # blocks (the fail-safe direction) until that question is actually raised and answered,
    # even with a satisfying verdict.
    log = tmp_path / "log.jsonl"
    plan_dir, vpath = _plan(tmp_path, phase=_NEEDS_PHASE,
                            verdicts=_verdict(_NEEDS_ITEM, "satisfied"))
    result = vc.assess(plan_dir, vpath, log_path=log)
    assert result.status == "INCOMPLETE"
    assert result.blocked_on_question == [_NEEDS_ITEM]


def test_open_question_block_is_scoped_to_the_run_being_verified(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A DIFFERENT run answering the same key must not clear this run's blocker (the shared-log
    # cross-run contamination CodeRabbit flagged). Verify the executing run; another run's
    # answer is ignored.
    log = tmp_path / "log.jsonl"
    monkeypatch.setattr(dl, "_RUN_ID", "exec-run")
    _defer("pricing_model", log)
    monkeypatch.setattr(dl, "_RUN_ID", "other-run")
    _answer("pricing_model", log)
    plan_dir, vpath = _plan(tmp_path, phase=_NEEDS_PHASE,
                            verdicts=_verdict(_NEEDS_ITEM, "satisfied"))
    result = vc.assess(plan_dir, vpath, log_path=log, run_id="exec-run")
    assert result.status == "INCOMPLETE"
    assert result.blocked_on_question == [_NEEDS_ITEM]


def test_blocked_item_records_a_not_satisfied_verification(tmp_path: Path) -> None:
    # The close stays auditable: the blocked item leaves one not-satisfied verification event.
    log = tmp_path / "log.jsonl"
    _defer("pricing_model", log)
    plan_dir, vpath = _plan(tmp_path, phase=_NEEDS_PHASE,
                            verdicts=_verdict(_NEEDS_ITEM, "satisfied"))
    vc.assess(plan_dir, vpath, log_path=log)
    verifications = [e for e in dl.read_events(log, event="verification")
                     if e["payload"].get("item") == _NEEDS_ITEM]
    assert len(verifications) == 1
    assert verifications[0]["payload"]["verdict"] == "not-satisfied"


class TestRegistration:
    """verify-completion is reachable through every dispatch table (B7)."""

    def test_handler_is_mapped(self) -> None:
        assert cli._COMMAND_HANDLERS["verify-completion"] == "_cmd_verify_completion"

    def test_handler_reference_is_kept_for_dead_code_scanners(self) -> None:
        assert cli._cmd_verify_completion in cli._COMMAND_HANDLER_REFERENCES

    def test_command_has_a_description(self) -> None:
        assert "verify-completion" in cli._COMMAND_DESCRIPTIONS
