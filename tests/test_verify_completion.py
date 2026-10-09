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

#: An **approved** plan: the close refuses to report success for one that was never
#: authorised, the same field and value the phase dispatcher requires before it will run
#: a phase. Tests of the unapproved cases pass their own manifest.
_MANIFEST = '[plan]\ntask = "t"\napproval_status = "approved"\n[[phases]]\nnumber = 1\nfile = "p.md"\n'
_UNAPPROVED = '[plan]\ntask = "t"\n[[phases]]\nnumber = 1\nfile = "p.md"\n'
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


_TWO_PHASE_SHARED = ('[plan]\ntask = "t"\napproval_status = "approved"\n'
                     '[[phases]]\nnumber = 1\nfile = "p1.md"\n'
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


def test_a_second_run_in_the_same_project_cannot_complete_the_first(tmp_path: Path,
                                                                   monkeypatch: pytest.MonkeyPatch
                                                                   ) -> None:
    # Reported by review: the run-id file is project-wide and `run-start` replaces it, so run B
    # starting in the same checkout re-scoped run A's close -- and because an item blocks only while
    # its key is UNANSWERED, A was shown complete on an answer B gave. The gate must take its scope
    # from what it was told (`--run-id`) or from this process, never from that mutable file.
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("CFS_DECISION_LOG", str(log))

    run_a = dl.start_run()                 # run A begins
    assert run_a is not None
    _defer("pricing_model", log)           # A parks its question, under A's id
    run_b = dl.start_run()                 # run B begins in the SAME project, replacing the file
    assert run_b is not None
    assert run_b != run_a   # B really did replace A's id
    _answer("pricing_model", log)          # B answers the same key, under B's id

    plan_dir, vpath = _plan(tmp_path, phase=_NEEDS_PHASE,
                            verdicts=_verdict(_NEEDS_ITEM, "satisfied"))
    result = vc.assess(plan_dir, vpath, log_path=log)

    # B's answer must not complete A's item. Fail-safe: unscoped, nothing is answered, so it blocks.
    assert result.status == "INCOMPLETE"
    assert result.exit_code == 2
    assert result.blocked_on_question == [_NEEDS_ITEM]


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


def _verification_event(log: Path, item: str) -> dict:
    return next(e["payload"] for e in dl.read_events(path=log)
                if e["event"] == "verification" and e["payload"].get("item") == item)


def test_a_blocked_item_records_its_own_verdict(tmp_path: Path) -> None:
    # A satisfied item blocked on an open question: the block overrides (not-satisfied, still blocked),
    # but the event also carries own_verdict="satisfied" so an audit sees the work passed.
    log = tmp_path / "log.jsonl"
    _defer("pricing_model", log)
    plan_dir, vpath = _plan(tmp_path, phase=_NEEDS_PHASE,
                            verdicts=_verdict(_NEEDS_ITEM, "satisfied"))
    result = vc.assess(plan_dir, vpath, log_path=log)
    assert result.blocked_on_question == [_NEEDS_ITEM]  # completion unchanged -- still blocks
    payload = _verification_event(log, _NEEDS_ITEM)
    assert payload["verdict"] == "not-satisfied"        # the block overrides
    assert payload["own_verdict"] == "satisfied"        # the run's own belief is recorded


def test_a_blocked_item_never_stated_records_own_verdict_not_satisfied(tmp_path: Path) -> None:
    # Blocked AND never attempted: own_verdict is the fail-safe not-satisfied, distinguishing it from
    # "blocked but passed".
    log = tmp_path / "log.jsonl"
    _defer("pricing_model", log)
    plan_dir, vpath = _plan(tmp_path, phase=_NEEDS_PHASE, verdicts="")  # nothing stated
    result = vc.assess(plan_dir, vpath, log_path=log)
    assert result.blocked_on_question == [_NEEDS_ITEM]
    assert _verification_event(log, _NEEDS_ITEM)["own_verdict"] == "not-satisfied"


def test_a_non_blocked_item_has_an_unchanged_payload(tmp_path: Path) -> None:
    # An item with no dependency is byte-identical to before: assert the WHOLE payload, not just that
    # own_verdict is absent, so a stray added field would also be caught.
    log = tmp_path / "log.jsonl"
    plan_dir, vpath = _plan(tmp_path, phase="## Acceptance Criteria\n- [ ] PRD approved\n",
                            verdicts=_verdict("PRD approved", "satisfied"))
    vc.assess(plan_dir, vpath, log_path=log)
    assert _verification_event(log, "PRD approved") == {
        "item": "PRD approved", "verdict": "satisfied", "evidence": "ok", "phase": 1,
    }


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


def _verdicts_naming(run: str, item: str, verdict: str = "satisfied") -> str:
    """A verdicts file that names the run which produced it, as #400's close writes it."""
    return f'run_id = "{run}"\n' + _verdict(item, verdict)


def test_the_run_id_a_verdicts_file_declares_scopes_the_check(tmp_path: Path,
                                                              monkeypatch: pytest.MonkeyPatch
                                                              ) -> None:
    # The scope must match the EVIDENCE being checked, and the verdicts file is that evidence.
    # Carrying the run id there lets the close see the answers its own run recorded, without
    # trusting the project-wide run-id file on its own.
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("CFS_DECISION_LOG", str(log))
    run = dl.start_run()
    assert run is not None
    _defer("pricing_model", log)
    _answer("pricing_model", log)

    plan_dir, vpath = _plan(tmp_path, phase=_NEEDS_PHASE,
                            verdicts=_verdicts_naming(run, _NEEDS_ITEM))
    result = vc.assess(plan_dir, vpath, log_path=log)
    assert result.status == "COMPLETE"
    assert result.exit_code == 0


def test_a_stale_verdicts_run_id_is_refused_and_the_item_is_held(tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch
                                                                 ) -> None:
    # Measured before this guard existed: taking the declared id on its word reported COMPLETE
    # here, where the per-process fallback holds the item. A verdicts file left behind by an
    # earlier run names that run, and scoping to it makes ITS answers visible to this one. The
    # cross-check against `current_run_id` refuses an id nothing else still agrees with.
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("CFS_DECISION_LOG", str(log))
    run_a = dl.start_run()
    assert run_a is not None
    _defer("pricing_model", log)
    _answer("pricing_model", log)      # only A ever answered it
    run_b = dl.start_run()             # B begins; the shared file no longer says A
    assert run_b != run_a

    plan_dir, vpath = _plan(tmp_path, phase=_NEEDS_PHASE,
                            verdicts=_verdicts_naming(run_a, _NEEDS_ITEM))
    result = vc.assess(plan_dir, vpath, log_path=log)
    assert result.status == "INCOMPLETE"
    assert result.exit_code == 2
    assert result.blocked_on_question == [_NEEDS_ITEM]


def test_an_explicit_run_id_still_overrides_the_verdicts_file(tmp_path: Path,
                                                              monkeypatch: pytest.MonkeyPatch
                                                              ) -> None:
    # `--run-id` is what the caller was told; it outranks a hint read out of a file. The
    # declared id here is one that PASSES the cross-check, so only the precedence can decide
    # the outcome -- naming an id that fails the cross-check would leave both orders agreeing
    # and prove nothing.
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("CFS_DECISION_LOG", str(log))
    run = dl.start_run()
    assert run is not None
    _defer("pricing_model", log)
    _answer("pricing_model", log)       # answered under `run`, which the verdicts file names

    plan_dir, vpath = _plan(tmp_path, phase=_NEEDS_PHASE,
                            verdicts=_verdicts_naming(run, _NEEDS_ITEM))
    # Told to check a different run, which recorded nothing: the told id must win and hold.
    result = vc.assess(plan_dir, vpath, log_path=log, run_id="a-run-with-no-events")
    assert result.status == "INCOMPLETE"
    assert result.exit_code == 2
    assert result.blocked_on_question == [_NEEDS_ITEM]


def test_a_verdicts_file_naming_no_run_behaves_exactly_as_before(tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch
                                                                 ) -> None:
    # Backward compatibility: every verdicts file written before #400 names no run, and must
    # keep falling back to the per-process id rather than becoming an error.
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("CFS_DECISION_LOG", str(log))
    assert dl.start_run() is not None
    _defer("pricing_model", log)
    _answer("pricing_model", log)

    plan_dir, vpath = _plan(tmp_path, phase=_NEEDS_PHASE,
                            verdicts=_verdict(_NEEDS_ITEM, "satisfied"))
    assert vc.assess(plan_dir, vpath, log_path=log).exit_code == 2


class TestAPlanNobodyApprovedCannotReportSuccess:
    """The close is what stands between a run and declaring itself done.

    Review finding: it never looked at `plan.approval_status`, so a run could report success
    against a plan the phase dispatcher would have refused to run in the first place. Not a
    fault — the plan reads fine — so it joins the other "may not report success" causes at
    exit 2, and a caller already keying on 2 needs no change.
    """

    def test_a_plan_with_no_approval_field_is_held(self, tmp_path: Path) -> None:
        plan_dir, vpath = _plan(tmp_path, manifest=_UNAPPROVED,
                                verdicts=_verdict("A exists", "satisfied")
                                + _verdict("B passes", "satisfied"))
        result = vc.assess(plan_dir, vpath)
        assert result.status == "INCOMPLETE"
        assert result.exit_code == 2
        # The remedy is named, not just the refusal: a plan with no field at all predates
        # approvals being recorded, which is a different situation from one marked revised.
        assert "before approvals were recorded" in result.message

    @pytest.mark.parametrize("value", ["revised", "draft", "pending", "rejected", ""])
    def test_a_plan_approved_as_anything_else_is_held(self, tmp_path: Path, value: str) -> None:
        manifest = f'[plan]\ntask = "t"\napproval_status = "{value}"\n[[phases]]\nnumber = 1\nfile = "p.md"\n'
        plan_dir, vpath = _plan(tmp_path, manifest=manifest,
                                verdicts=_verdict("A exists", "satisfied")
                                + _verdict("B passes", "satisfied"))
        result = vc.assess(plan_dir, vpath)
        assert result.status == "INCOMPLETE"
        assert result.exit_code == 2
        assert "not 'approved'" in result.message

    @pytest.mark.parametrize("written", ['"  Approved "', '"APPROVED"', '"approved "'])
    def test_an_approval_the_dispatcher_would_reject_is_rejected_here(
            self, tmp_path: Path, written: str) -> None:
        # Review finding, confirmed in the modules: `plan-native-dispatch.md` and
        # `plan-compiler-dispatch.md` both refuse a phase unless `plan.approval_status` is the
        # exact literal `"approved"`, and `plan-compile.md` writes nothing else. An earlier
        # version of this check accepted `" Approved "`, so a hand-edited plan the dispatcher
        # would never have started could still be reported complete. The close must not be
        # more permissive than the gate.
        manifest = f'[plan]\ntask = "t"\napproval_status = {written}\n[[phases]]\nnumber = 1\nfile = "p.md"\n'
        plan_dir, vpath = _plan(tmp_path, manifest=manifest,
                                verdicts=_verdict("A exists", "satisfied")
                                + _verdict("B passes", "satisfied"))
        result = vc.assess(plan_dir, vpath)
        assert result.exit_code == 2, "a near-miss approval was accepted as an approval"
        assert "not 'approved'" in result.message

    def test_the_exact_literal_the_dispatcher_writes_is_accepted(self, tmp_path: Path) -> None:
        # The other edge: holding the comparison exact must not reject the ordinary case that
        # `plan-compile.md` actually writes.
        manifest = '[plan]\ntask = "t"\napproval_status = "approved"\n[[phases]]\nnumber = 1\nfile = "p.md"\n'
        plan_dir, vpath = _plan(tmp_path, manifest=manifest,
                                verdicts=_verdict("A exists", "satisfied")
                                + _verdict("B passes", "satisfied"))
        assert vc.assess(plan_dir, vpath).exit_code == 0

    def test_a_non_string_approval_is_held_not_crashed(self, tmp_path: Path) -> None:
        # `approval_status = true` is an author's defect, not an approval, and not a traceback.
        manifest = '[plan]\ntask = "t"\napproval_status = true\n[[phases]]\nnumber = 1\nfile = "p.md"\n'
        plan_dir, vpath = _plan(tmp_path, manifest=manifest,
                                verdicts=_verdict("A exists", "satisfied")
                                + _verdict("B passes", "satisfied"))
        assert vc.assess(plan_dir, vpath).exit_code == 2

    def test_the_approval_read_reports_a_plan_it_cannot_parse_as_a_fault(self,
                                                                        tmp_path: Path) -> None:
        # Called directly, because `assess` reads the plan first and reports an unreadable one
        # before this helper runs. The branch exists for the narrow race where the file becomes
        # unreadable between those two reads. Not knowing whether a plan was approved must stay
        # a FAULT — never "not approved", which would turn a transient read error into an
        # accusation that the plan lacks sign-off, and never `None`, which means approved.
        (tmp_path / "plan.toml").write_text("this is not toml = = =", encoding="utf-8")
        refusal = vc._approval_refusal(tmp_path)
        assert refusal is not None, "an unreadable plan was treated as an approved one"
        assert refusal.exit_code == 1, "a fault was reported as a failed check"
        assert refusal.status == "ERROR"

    def test_a_plan_that_becomes_unreadable_mid_check_cannot_report_complete(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Review finding, reproduced: `assess` reads the plan twice — once for its items, once
        # for its approval. The first read decided whether an unreadable plan was reported, so
        # a plan that broke between them returned `None` from the approval read, which means
        # "approved". With every verdict satisfied, the run reported COMPLETE having never had
        # its approval confirmed. Only the SECOND read is made to fail here; the first must
        # succeed, or the test proves nothing about the race.
        plan_dir, vpath = _plan(tmp_path,
                                verdicts=_verdict("A exists", "satisfied")
                                + _verdict("B passes", "satisfied"))
        assert vc.assess(plan_dir, vpath).exit_code == 0, (
            "control: this plan completes cleanly when both reads succeed")

        # Keyed on the PATH, not on call order. `read_plan_items` binds `_load_plan` from
        # `plan_decisions`, so patching the name here cannot affect the first read — but the
        # verdicts file is loaded through this same binding, and an earlier version of this
        # test failed the second CALL, which was the verdicts read. It then reported exit 1
        # for the wrong reason and passed whether or not the approval fix was present.
        real_load = vc._load_plan
        plan_reads: list[Path] = []

        def _only_the_plan_breaks(path: Path):
            if path.name == vc.PLAN_FILE:
                plan_reads.append(path)
                return None, "unreadable", "ERROR"
            return real_load(path)

        monkeypatch.setattr(vc, "_load_plan", _only_the_plan_breaks)
        result = vc.assess(plan_dir, vpath)
        assert result.exit_code != 0, (
            "a plan that became unreadable before its approval check reported success")
        assert result.exit_code == 1, "the unread approval is a fault, not a failed check"
        assert plan_reads, "the approval read never happened, so this proves nothing"
        assert "approval" in result.message

    def test_an_unreadable_plan_stays_a_fault_not_an_approval_verdict(self, tmp_path: Path) -> None:
        # Not knowing whether a plan was approved is different from knowing it was not: the
        # caller's own read reports it as a fault (exit 1), and this check stays out of it.
        (tmp_path / "plan.toml").write_text("this is not toml = = =", encoding="utf-8")
        (tmp_path / "p.md").write_text(_TWO_CRITERIA, encoding="utf-8")
        vpath = tmp_path / "verdicts.toml"
        vpath.write_text("", encoding="utf-8")
        assert vc.assess(tmp_path, vpath).exit_code == 1


class TestTheAuthorFacingTemplateMatchesTheMatchingRule:
    """The template is where an author learns the verdicts schema, so it must not teach a
    shape the check rejects. Review finding: the example showed `item`/`verdict`/`evidence`
    only, while `_verdict_for` falls back to a phase-less entry *only* for text unique across
    the plan -- and Section 8 of the same template requires every phase to carry a "no
    unresolved variables" criterion, so repeated text is guaranteed in any multi-phase plan.
    An author following the example exactly got INCOMPLETE for work genuinely done.
    """

    TEMPLATE = Path(__file__).resolve().parents[1] / "requirements/plan-template.md"

    def _example(self) -> str:
        text = self.TEMPLATE.read_text(encoding="utf-8")
        marker = 'run_id = "a1b2c3d4e5f6"'
        assert marker in text, "the verdicts example moved; this guard is reading the wrong block"
        start = text.index(marker)
        return text[start:text.index("```", start)]

    def test_every_verdict_entry_in_the_example_names_its_phase(self) -> None:
        example = self._example()
        entries = example.count("[[verdicts]]")
        assert entries >= 2, "a single-entry example cannot show why `phase` is needed"
        assert example.count("phase = ") == entries, (
            "an example entry omits `phase`; an author copying it writes verdicts the check "
            "cannot attribute once any criterion text repeats across phases")

    def test_the_example_shows_text_repeated_across_phases(self) -> None:
        # The trap only appears with repeated text, so an example without it demonstrates
        # nothing: it would pass whether or not `phase` mattered.
        example = self._example()
        assert example.count('item = "no unresolved variables"') >= 2, (
            "the example must show the mandated per-phase criterion in more than one phase, "
            "which is the case that makes `phase` load-bearing")
        assert "phase = 1" in example, "the example never names a first phase"
        assert "phase = 2" in example, "the example never names a second phase"

    def test_the_prose_states_when_a_phase_less_entry_is_accepted(self) -> None:
        text = self.TEMPLATE.read_text(encoding="utf-8")
        assert "appears in exactly **one** phase" in text, (
            "the rule `_verdict_for` applies is not stated anywhere an author will read it")


class TestApprovalPrecedesTheVacuousPass:
    """Review finding: both docs described the zero-criteria plan as an unconditional benign
    exit 0, but the approval refusal is checked first, so an *unapproved* zero-criteria plan
    exits 2. The existing vacuous-pass test only passed because the shared manifest helper is
    already approved -- the suite was treating approval as a silent precondition.
    """

    def test_an_unapproved_plan_with_no_criteria_is_refused_not_passed(
            self, tmp_path: Path) -> None:
        plan_dir, vpath = _plan(tmp_path, manifest=_UNAPPROVED,
                                phase="## Acceptance Criteria\n")
        result = vc.assess(plan_dir, vpath)
        assert result.exit_code == 2, "an unapproved plan reported the benign vacuous pass"
        assert result.applicable is not False, (
            "the refusal must not be dressed up as a not-applicable result")
        assert "approval_status" in result.message

    def test_an_approved_plan_with_no_criteria_is_still_the_benign_case(
            self, tmp_path: Path) -> None:
        # The other edge: the refusal must not swallow the vacuous pass it runs ahead of.
        plan_dir, vpath = _plan(tmp_path, phase="## Acceptance Criteria\n")
        result = vc.assess(plan_dir, vpath)
        assert result.exit_code == 0, "the approval refusal swallowed the vacuous pass"
        assert result.applicable is False, "the vacuous pass was not stated as not-applicable"
