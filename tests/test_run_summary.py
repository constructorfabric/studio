"""Tests for run-summary: project a run's close into four headings from the decision log.

The contract: the summary is a pure projection over the ledger (it records nothing new); a ruling
and an open question never share a heading; an empty heading is stated, not dropped; and the read
is scoped to one run. Events are written through the real recorders, so these are round-trips.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/studio/scripts"))

from studio import cli  # noqa: E402
from studio.commands import run_summary as rs  # noqa: E402
from studio.utils import decision_log as dl  # noqa: E402
from studio.utils.decision_log import GateRuling  # noqa: E402


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / ".cache" / "decisions.jsonl"


def _resolved(key: str, log: Path, *, value: str = "chosen", why: str = "the plan says so",
              cost: str = "a re-run") -> None:
    dl.record_gate("plan-resolved", f"{key}Gate", "decision",
                   GateRuling(decision_key=key, value=value, provenance="plan",
                              status="resolved", why=why, cost_if_wrong=cost),
                   command="gate-log", path=log)


def _auto(key: str, log: Path, *, why: str = "a safe default") -> None:
    dl.record_gate("auto-proceeded", f"{key}Gate", "confirmation",
                   GateRuling(decision_key=key, why=why, cost_if_wrong="low"),
                   command="gate-log", path=log)


def _open(key: str, log: Path, *, why: str = "the plan is silent") -> None:
    dl.record_gate("open-question", f"{key}Gate", "decision",
                   GateRuling(decision_key=key, why=why, status="absent"),
                   command="gate-log", path=log)


def _labels(entries: list) -> set:
    return {e["label"] for e in entries}


def test_each_event_kind_lands_under_the_right_heading(log_path: Path) -> None:
    _auto("retry_policy", log_path)
    _resolved("pricing_model", log_path)
    _open("deploy_target", log_path)
    dl.record_verification("PRD approved", "satisfied", "ok", 1,
                           command="verify-completion", path=log_path)
    dl.record_validation("lint", "PASS", 0, command="validate", path=log_path)

    payload = rs._payload(rs.summarise(log_path))
    assert _labels(payload["defaults_applied"]) == {"retry_policyGate"}
    assert _labels(payload["rulings"]) == {"pricing_modelGate"}
    assert _labels(payload["open_questions"]) == {"deploy_target"}
    assert _labels(payload["completed_actions"]) == {"PRD approved", "lint"}


def test_empty_run_id_does_not_disable_scoping(log_path: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: an empty run_id must fall back to the current run, not read every run. The ledger
    # reader treats an empty-string filter as "no filter", so `--run-id ""` would otherwise pull
    # another run's events into this summary (the same fix the open-question register carries).
    monkeypatch.setattr(dl, "_RUN_ID", "run-a")
    _resolved("alpha", log_path)                    # ruled in run-a
    monkeypatch.setattr(dl, "_RUN_ID", "run-b")     # the current run is now run-b
    # empty run_id scopes to the current run (run-b), which has no rulings
    assert _labels(rs._payload(rs.summarise(log_path, run_id=""))["rulings"]) == set()
    # run-a's own view still shows it — proves the data is there and scoping is active
    assert _labels(rs._payload(rs.summarise(log_path, run_id="run-a"))["rulings"]) == {"alphaGate"}


def test_a_ruling_and_an_open_question_never_share_a_heading(log_path: Path) -> None:
    # A key deferred then resolved: it is a ruling (resolved) and NOT an open question (the register
    # drops the answered key). A different key stays open. Neither heading holds both.
    _open("pricing_model", log_path)
    _resolved("pricing_model", log_path)   # answers it
    _open("scope", log_path)               # still outstanding
    payload = rs._payload(rs.summarise(log_path))
    rulings = _labels(payload["rulings"])
    open_q = _labels(payload["open_questions"])
    assert "pricing_modelGate" in rulings
    assert "pricing_model" not in open_q           # answered → not open
    assert open_q == {"scope"}
    assert rulings.isdisjoint(open_q)              # the two headings never overlap


def test_a_reopened_key_is_an_open_question_not_also_a_ruling(log_path: Path) -> None:
    # Resolved, then REOPENED: the register reports it outstanding again, so it must appear only
    # under open questions. Without reconciling, the earlier resolve event would leave it in rulings
    # too (the bug @ainetx flagged) -- a key in both headings.
    _resolved("deploy_target", log_path)   # a ruling from the resolve event
    _open("deploy_target", log_path)        # then reopened -> outstanding again
    payload = rs._payload(rs.summarise(log_path))
    rulings = _labels(payload["rulings"])
    open_q = _labels(payload["open_questions"])
    assert open_q == {"deploy_target"}
    assert "deploy_targetGate" not in rulings      # reconciled out of rulings
    assert rulings.isdisjoint({"deploy_target"})


def test_cmd_run_summary_rejects_a_bad_argument(log_path: Path, capsys: pytest.CaptureFixture,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    # A malformed argument must emit the standard **structured ERROR** and exit 2 -- not just the
    # exit code, but the ERROR payload it claims to produce (routed through parse_args_or_json_error).
    import json
    from studio.utils import ui  # noqa: E402
    monkeypatch.setattr(ui, "_JSON_MODE", True)
    assert rs.cmd_run_summary(["--no-such-flag"]) == 2
    emitted = json.loads(capsys.readouterr().out.strip())  # the one structured ERROR payload
    assert emitted["status"] == "ERROR"


def test_unspecified_sentinel_does_not_leak_into_rulings(log_path: Path) -> None:
    # A ruling whose value/why/cost were not supplied carries the internal UNSPECIFIED sentinel; it
    # must not appear verbatim in the human text or the JSON -- it reads as an omitted field.
    dl.record_gate("blocking-confirmed", "PlainGate", "blocking",
                   GateRuling(decision_key="k", status="resolved"),  # value/why/cost default UNSPECIFIED
                   command="gate-log", path=log_path)
    payload = rs._payload(rs.summarise(log_path))
    row = next(r for r in payload["rulings"] if r["label"] == "PlainGate")
    assert "unspecified" not in row["detail"].lower()
    assert "unspecified" not in row["label"].lower()
    assert row["detail"] == "resolved"  # no supplied fields -> the neutral default


def test_an_exception_asked_that_resolved_appears_as_a_ruling(log_path: Path) -> None:
    # exception-asked is a live gate kind (one of the five GATE_KINDS); it must not silently vanish
    # from the summary. An ask that RESOLVED is a decision, so it belongs under rulings.
    dl.record_gate("exception-asked", "RiskGate", "blocking",
                   GateRuling(decision_key="risk", value="accepted", why="surfaced for review",
                              status="resolved", cost_if_wrong="re-review"),
                   command="gate-log", path=log_path)
    payload = rs._payload(rs.summarise(log_path))
    assert "RiskGate" in _labels(payload["rulings"])


def test_an_exception_asked_that_did_not_resolve_is_an_open_question(log_path: Path) -> None:
    # It still does not vanish -- it moves to the heading that tells the truth. An ask that
    # produced no answer is not a decision, and reporting it under rulings would say the gate
    # was settled when it was not. The register now treats such an ask as reopening its key,
    # and the summary's reconciliation drops a still-outstanding key from rulings, so the two
    # agree: "I decided this for you" and "nobody has decided this yet" stay distinguishable.
    dl.record_gate("exception-asked", "RiskGate", "blocking",
                   GateRuling(decision_key="risk", why="surfaced for review"),
                   command="gate-log", path=log_path)
    payload = rs._payload(rs.summarise(log_path))
    assert "RiskGate" not in _labels(payload["rulings"])
    assert "risk" in _labels(payload["open_questions"])


def test_corrupt_values_are_sanitized_for_both_json_and_render() -> None:
    # A corrupt ledger value (control chars, an escaped lone surrogate) must neither crash the JSON
    # serialisation nor the human render -- both read from the same sanitised rows.
    import json
    nasty = rs.Summary(rulings=[rs._Entry("g\x07\ud800x", "d\x00y")])
    payload = rs._payload(nasty)
    json.dumps(payload)  # would raise UnicodeEncodeError on a lone surrogate if not neutralised
    label = payload["rulings"][0]["label"]
    assert "\ud800" not in label
    assert "\x07" not in label
    rs._say(payload)  # human render must not raise either


def test_empty_headings_are_stated_not_dropped(log_path: Path) -> None:
    _resolved("only_a_ruling", log_path)
    payload = rs._payload(rs.summarise(log_path))
    # every heading is present even when empty
    assert set(payload.keys()) == {
        "defaults_applied", "rulings", "open_questions", "completed_actions"}
    assert payload["defaults_applied"] == []
    assert payload["open_questions"] == []


def test_scoped_to_the_run(log_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A different run's events must not appear in this run's summary.
    monkeypatch.setattr(dl, "_RUN_ID", "run-a")
    _resolved("alpha", log_path)
    monkeypatch.setattr(dl, "_RUN_ID", "run-b")
    _resolved("beta", log_path)
    assert _labels(rs._payload(rs.summarise(log_path, run_id="run-a"))["rulings"]) == {"alphaGate"}
    assert _labels(rs._payload(rs.summarise(log_path, run_id="run-b"))["rulings"]) == {"betaGate"}


def test_absent_log_gives_four_empty_headings(log_path: Path) -> None:
    payload = rs._payload(rs.summarise(log_path))
    assert all(payload[h] == [] for h in
               ("defaults_applied", "rulings", "open_questions", "completed_actions"))


def test_gate_event_with_non_dict_payload_is_skipped(log_path: Path) -> None:
    _resolved("alpha", log_path)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f'{{"event": "gate", "run_id": "{dl._RUN_ID}", "payload": ["x"]}}\n')
    assert _labels(rs._payload(rs.summarise(log_path))["rulings"]) == {"alphaGate"}


def test_command_exits_zero_and_is_a_report(log_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dl, "default_log_path", lambda *a, **k: log_path)
    _resolved("alpha", log_path)
    assert rs.cmd_run_summary([]) == 0  # a report, never a gate


def test_invocation_event_is_a_completed_action(log_path: Path) -> None:
    # Pin the exact label (command) and detail (the real exit code, not a hardcoded 0) so a
    # regression that drops the code or mislabels the action is caught.
    dl.record_invocation("verify-completion", 2, path=log_path)
    payload = rs._payload(rs.summarise(log_path))
    completed = {(e["label"], e["detail"]) for e in payload["completed_actions"]}
    assert ("verify-completion", "exit 2") in completed


def test_say_renders_each_heading_and_states_empty_as_none(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    monkeypatch.setattr(rs.ui, "info", lambda m: calls.append(("info", m)))
    monkeypatch.setattr(rs.ui, "detail", lambda k, v: calls.append(("detail", k, v)))
    payload = {
        "defaults_applied": [{"label": "G", "detail": "d"}],
        "rulings": [],
        "open_questions": [],
        "completed_actions": [{"label": "X", "detail": ""}],
    }
    rs._say(payload)
    assert ("detail", "defaults applied", "G: d") in calls   # label: detail
    assert ("detail", "rulings", "none") in calls            # empty stated as none
    assert ("detail", "completed actions", "X") in calls     # no detail -> label alone


class TestRegistration:
    """run-summary is reachable through every dispatch table (B7)."""

    def test_handler_is_mapped(self) -> None:
        assert cli._COMMAND_HANDLERS["run-summary"] == "_cmd_run_summary"

    def test_handler_reference_is_kept_for_dead_code_scanners(self) -> None:
        assert cli._cmd_run_summary in cli._COMMAND_HANDLER_REFERENCES

    def test_command_has_a_description(self) -> None:
        assert "run-summary" in cli._COMMAND_DESCRIPTIONS
