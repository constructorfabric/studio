"""Tests for the dispatch-wrapper telemetry in ``studio.cli`` + validation correlation.

Covers: one ``invocation`` event per command, ``decision_id`` correlation of events
recorded *inside* a command, and the fail-open contract — telemetry must never change
a command's exit code or behaviour.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from studio import cli
from studio.utils import decision_log


def _events(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _fixed_handler(exit_code: int):
    """A stand-in command handler that ignores its args and returns *exit_code*."""
    return lambda cmd: (lambda rest: exit_code)


# ---------------------------------------------------------------------------
# emission + correlation

def test_command_emits_one_invocation_event(tmp_path: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "decisions.jsonl"
    monkeypatch.setenv("CFS_DECISION_LOG", str(log))   # set in body → overrides autouse
    monkeypatch.setattr(cli, "_resolve_command_handler", _fixed_handler(0))
    assert cli.main(["demo", "-a", "b"]) == 0
    invocations = [e for e in _events(log) if e["event"] == "invocation"]
    assert len(invocations) == 1
    ev = invocations[0]
    assert ev["command"] == "demo"
    assert ev["payload"]["exit_code"] == 0
    assert ev["payload"]["args"] == {"argc": 2, "flags": 1}   # "-a" is a flag, "b" is not
    assert isinstance(ev["payload"]["duration_ms"], int)
    assert ev["decision_id"]                                   # non-empty


def test_events_inside_a_command_share_the_run_decision_id(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "decisions.jsonl"
    monkeypatch.setenv("CFS_DECISION_LOG", str(log))

    def handler(_rest):
        # A record deep inside the command, with NO explicit decision_id, must
        # inherit the run's id set by the dispatcher.
        decision_log.record_validation("inner", "PASS", findings=0)
        return 0

    monkeypatch.setattr(cli, "_resolve_command_handler", lambda cmd: handler)
    cli.main(["demo"])
    events = _events(log)
    ids = {e["decision_id"] for e in events}
    assert len(events) == 2                    # invocation + the inner validation
    assert len(ids) == 1                        # both chained to one decision
    assert all(ids)                             # ...and the id is non-empty


# ---------------------------------------------------------------------------
# fail-open: telemetry never changes command behaviour

def test_command_survives_an_unwritable_log(tmp_path: Path,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "decisions.jsonl"
    monkeypatch.setenv("CFS_DECISION_LOG", str(log))
    monkeypatch.setattr(cli, "_resolve_command_handler", _fixed_handler(5))

    def boom(*_a, **_k):
        raise OSError("unwritable log")

    monkeypatch.setattr(decision_log, "_append_locked", boom)
    assert cli.main(["demo"]) == 5      # a real write failure never changes the exit code
    assert not log.exists()              # ...and no event is written
    # (the single visible warning is asserted at the decision_log level)


def test_handler_exception_records_invocation_and_propagates(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "decisions.jsonl"
    monkeypatch.setenv("CFS_DECISION_LOG", str(log))

    def crash(_rest):
        raise RuntimeError("handler crash")

    monkeypatch.setattr(cli, "_resolve_command_handler", lambda cmd: crash)
    with pytest.raises(RuntimeError, match="handler crash"):
        cli.main(["demo"])
    invocations = [e for e in _events(log) if e["event"] == "invocation"]
    assert len(invocations) == 1                       # a crashing run is still recorded
    assert invocations[0]["payload"]["exit_code"] == 1


@pytest.mark.parametrize("raised, expected", [(0, 0), (2, 2), (None, 0), ("boom", 1)])
def test_systemexit_records_its_real_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                          raised, expected) -> None:
    log = tmp_path / "decisions.jsonl"
    monkeypatch.setenv("CFS_DECISION_LOG", str(log))

    def exiter(_rest):
        raise SystemExit(raised)   # argparse-style exit (--help / bad args)

    monkeypatch.setattr(cli, "_resolve_command_handler", lambda cmd: exiter)
    with pytest.raises(SystemExit):
        cli.main(["demo"])
    invocations = [e for e in _events(log) if e["event"] == "invocation"]
    assert invocations[-1]["payload"]["exit_code"] == expected


def test_decision_id_is_scoped_to_the_run(tmp_path: Path,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "decisions.jsonl"
    monkeypatch.setenv("CFS_DECISION_LOG", str(log))
    monkeypatch.setattr(cli, "_resolve_command_handler", _fixed_handler(0))
    cli.main(["demo"])
    # After the run the correlation context is cleared, so a stray record does not
    # inherit the finished run's decision id.
    decision_log.record_validation("stray", "PASS", path=log)
    stray = [e for e in _events(log) if e["payload"].get("check") == "stray"]
    assert stray
    assert stray[0]["decision_id"] == ""
