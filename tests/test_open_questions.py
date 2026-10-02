"""Tests for the open-questions register (``studio.utils.open_questions``).

The register is a projection over the decision log's ``gate`` events: an
``open-question`` event opens a keyed question, a later ``plan-resolved`` or
``blocking-confirmed`` for the same key closes it, and ``auto-proceeded`` does not.
Events are written through the real producer (``record_gate``) so these are round-trips,
not assertions against a hand-built log line.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from studio.utils import decision_log as dl
from studio.utils import open_questions as oq
from studio.utils.decision_log import GateRuling


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / ".cache" / "decisions.jsonl"


def _defer(key: str, log_path: Path, *, gate: str = "PlanGate", why: str = "no plan answer") -> None:
    """Record a parked (open) question for ``key`` the way the producer does."""
    dl.record_gate("open-question", gate, "decision",
                   GateRuling(decision_key=key, why=why, status="absent"),
                   command="gate-log", path=log_path)


def _resolve(key: str, log_path: Path, *, kind: str = "plan-resolved") -> None:
    """Record an answering event for ``key``."""
    dl.record_gate(kind, "PlanGate", "decision",
                   GateRuling(decision_key=key, value="chosen", provenance="plan",
                              status="resolved", cost_if_wrong="re-run"),
                   command="gate-log", path=log_path)


def test_absent_log_has_no_open_questions(log_path: Path) -> None:
    result = oq.read_open_questions(log_path)
    assert result.outstanding == {}
    assert result.is_open("anything") is False


def test_open_question_is_outstanding(log_path: Path) -> None:
    _defer("pricing_model", log_path, gate="PricingGate", why="the plan is silent")
    result = oq.read_open_questions(log_path)
    assert result.is_open("pricing_model") is True
    question = result.outstanding["pricing_model"]
    assert question.key == "pricing_model"
    assert question.gate == "PricingGate"
    assert question.reason == "the plan is silent"


def test_answered_question_drops_out(log_path: Path) -> None:
    _defer("pricing_model", log_path)
    _resolve("pricing_model", log_path)
    result = oq.read_open_questions(log_path)
    assert result.is_open("pricing_model") is False
    assert result.is_answered("pricing_model") is True  # settled, so a dependency may complete


def test_a_never_raised_key_is_not_answered(log_path: Path) -> None:
    # The fail-safe crux for the completion invariant: a key nobody raised is not "answered",
    # so a dependency on it is not assumed satisfied.
    result = oq.read_open_questions(log_path)
    assert result.is_answered("never_raised") is False
    assert result.is_open("never_raised") is False


def test_a_reopened_key_is_not_answered(log_path: Path) -> None:
    _defer("scope", log_path)
    _resolve("scope", log_path)
    _defer("scope", log_path)  # re-raised after the answer
    result = oq.read_open_questions(log_path)
    assert result.is_open("scope") is True
    assert result.is_answered("scope") is False  # the re-deferral un-settles it


def test_blocking_confirmed_also_closes(log_path: Path) -> None:
    _defer("deploy_target", log_path)
    _resolve("deploy_target", log_path, kind="blocking-confirmed")
    assert oq.read_open_questions(log_path).is_open("deploy_target") is False


def test_auto_proceeded_does_not_close(log_path: Path) -> None:
    # Proceeding on a default is not an answer to the raised question: it stays open,
    # the fail-safe direction (hold the dependent item, never silently pass).
    _defer("retry_policy", log_path)
    _resolve("retry_policy", log_path, kind="auto-proceeded")
    assert oq.read_open_questions(log_path).is_open("retry_policy") is True


def test_redeferral_reopens_after_an_answer(log_path: Path) -> None:
    _defer("scope", log_path)
    _resolve("scope", log_path)
    _defer("scope", log_path, why="re-raised after the answer was withdrawn")
    result = oq.read_open_questions(log_path)
    assert result.is_open("scope") is True
    assert result.outstanding["scope"].reason == "re-raised after the answer was withdrawn"


def test_unkeyed_deferral_is_skipped_not_an_error(log_path: Path) -> None:
    # A deferral with no decision_key cannot be named by an item, so it is not tracked;
    # it is not an error either.
    dl.record_gate("open-question", "SomeGate", "blocking",
                   GateRuling(why="parked with no key"),
                   command="gate-log", path=log_path)
    result = oq.read_open_questions(log_path)
    assert result.outstanding == {}


def test_distinct_keys_are_independent(log_path: Path) -> None:
    _defer("alpha", log_path)
    _defer("beta", log_path)
    _resolve("alpha", log_path)
    result = oq.read_open_questions(log_path)
    assert result.is_open("alpha") is False
    assert result.is_open("beta") is True


def test_reader_is_fresh_each_call(log_path: Path) -> None:
    # Never caches: a question answered between two reads has to drop out on the second.
    _defer("budget", log_path)
    assert oq.read_open_questions(log_path).is_open("budget") is True
    _resolve("budget", log_path)
    assert oq.read_open_questions(log_path).is_open("budget") is False


def test_corrupt_line_is_tolerated(log_path: Path) -> None:
    # Inherits the log reader's contract: a bad line is dropped, not raised.
    _defer("alpha", log_path)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("}{ not json\n")
    _defer("beta", log_path)
    result = oq.read_open_questions(log_path)
    assert result.is_open("alpha") is True
    assert result.is_open("beta") is True


def test_scoped_to_run_so_another_runs_answer_cannot_clear_this_block(
        log_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The log is shared across runs. Run A parks a question; a DIFFERENT run B answers the same
    # key. A's question must stay open — B's answer must not clear A's blocker.
    monkeypatch.setattr(dl, "_RUN_ID", "run-a")
    _defer("pricing_model", log_path)
    monkeypatch.setattr(dl, "_RUN_ID", "run-b")
    _resolve("pricing_model", log_path)
    assert oq.read_open_questions(log_path, run_id="run-a").is_open("pricing_model") is True
    # run B never opened it, so it has nothing outstanding from B's own events
    assert oq.read_open_questions(log_path, run_id="run-b").is_open("pricing_model") is False


def test_empty_run_id_does_not_disable_scoping(log_path: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: an empty run_id must fall back to the current run, not read every run. The log
    # reader treats an empty-string filter as "no filter", so `--run-id ""` would otherwise
    # silently disable the cross-run scoping guarantee.
    monkeypatch.setattr(dl, "_RUN_ID", "run-a")
    _defer("alpha", log_path)                      # opened in run-a
    monkeypatch.setattr(dl, "_RUN_ID", "run-b")    # the current run is now run-b
    # empty run_id scopes to the current run (run-b), which never opened alpha
    assert oq.read_open_questions(log_path, run_id="").is_open("alpha") is False
    # the data is there — run-a's own view shows it open, so this proves scoping is active
    assert oq.read_open_questions(log_path, run_id="run-a").is_open("alpha") is True


def test_default_scope_is_the_current_run(log_path: Path,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dl, "_RUN_ID", "run-x")
    _defer("budget", log_path)
    assert oq.read_open_questions(log_path).is_open("budget") is True  # default = current run
    monkeypatch.setattr(dl, "_RUN_ID", "run-y")
    assert oq.read_open_questions(log_path).is_open("budget") is False  # a different current run


def test_gate_event_with_non_dict_payload_is_skipped(log_path: Path) -> None:
    # A well-formed JSON line whose `gate` payload is not an object is ignored, not a
    # crash: defensive against a hand-edited or future-schema log.
    _defer("alpha", log_path)
    with log_path.open("a", encoding="utf-8") as handle:
        # Same run_id as the register's default scope, so it reaches the payload-shape guard
        # rather than being filtered out by the run scope first.
        handle.write(f'{{"event": "gate", "run_id": "{dl._RUN_ID}", "payload": ["x"]}}\n')
    result = oq.read_open_questions(log_path)
    assert result.is_open("alpha") is True
    assert result.outstanding.keys() == {"alpha"}
