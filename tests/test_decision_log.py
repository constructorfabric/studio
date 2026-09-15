"""Tests for the local decision/outcome log (``studio.utils.decision_log``).

Covers the rigor the design note calls for: local-only (no socket), opt-out silences
everything, fail-safe (never raises), no-project no-op, rotation, redaction, and the
decision_id correlation that chains one decision's events.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import logging
import os
import re
import time
from pathlib import Path

import pytest

from studio.utils import decision_log as dl


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / ".cache" / "decisions.jsonl"


# ---------------------------------------------------------------------------
# writing + reading

def test_record_writes_one_wellformed_line(log_path: Path) -> None:
    assert dl.record("validation", {"check": "toc", "status": "PASS"},
                     command="validate", path=log_path) is True
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["schema"] == dl.SCHEMA_VERSION
    assert obj["event"] == "validation"
    assert obj["command"] == "validate"
    assert obj["run_id"]                      # non-empty
    assert obj["payload"]["status"] == "PASS"
    assert "ts" in obj


def test_append_never_truncates(log_path: Path) -> None:
    for i in range(3):
        dl.record("routing", {"i": i}, path=log_path)
    assert len(log_path.read_text().splitlines()) == 3


def test_read_events_and_summarize_roundtrip(log_path: Path) -> None:
    dl.record("routing", {"a": 1}, path=log_path)
    dl.record("validation", {"status": "FAIL"}, path=log_path)
    events = list(dl.read_events(log_path))
    assert [e["event"] for e in events] == ["routing", "validation"]
    summary = dl.summarize(log_path)
    assert summary["total_events"] == 2
    assert summary["event_counts"] == {"routing": 1, "validation": 1}


def test_read_events_skips_corrupt_lines(log_path: Path) -> None:
    dl.record("routing", {"a": 1}, path=log_path)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write("this is not json\n\n")
    dl.record("routing", {"a": 2}, path=log_path)
    assert len(list(dl.read_events(log_path))) == 2   # the junk line is dropped, not raised


# ---------------------------------------------------------------------------
# decision_id correlation

def test_decision_id_chains_and_filters(log_path: Path) -> None:
    did = dl.new_decision_id()
    dl.record_routing("gen", ["a", "b"], "a", decision_id=did, path=log_path)
    dl.record_dispatch("author", tier="cheap", decision_id=did, path=log_path)
    dl.record("routing", {"other": True}, decision_id="zzz", path=log_path)
    chained = list(dl.read_events(log_path, decision_id=did))
    assert len(chained) == 2
    assert {e["event"] for e in chained} == {"routing", "dispatch"}


# ---------------------------------------------------------------------------
# opt-out

def test_env_off_writes_nothing(log_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CFS_DECISION_LOG", "off")
    assert dl.is_enabled() is False
    assert dl.record("routing", {}, path=log_path) is False
    assert not log_path.exists()


def test_sentinel_file_disables(tmp_path: Path, log_path: Path,
                                monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CFS_DECISION_LOG", raising=False)
    brand = tmp_path / ".cf-studio"
    brand.mkdir()
    (brand / "decisions.off").write_text("")
    monkeypatch.setattr(dl, "_brand_dir", lambda: brand)
    assert dl.is_enabled() is False
    assert dl.record("routing", {}, path=log_path) is False


# ---------------------------------------------------------------------------
# no-project no-op

def test_no_project_is_a_noop_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CFS_DECISION_LOG", raising=False)
    monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: None)
    assert dl.default_log_path() is None
    assert dl.record("routing", {}) is False          # returns, does not raise


# ---------------------------------------------------------------------------
# fail-safe + local-only

def test_record_never_raises_on_bad_target(tmp_path: Path) -> None:
    # Point the path at a directory: opening it for append fails — must degrade to False.
    bad = tmp_path / "adir"
    bad.mkdir()
    assert dl.record("routing", {}, path=bad) is False


def test_write_failure_warns_once_then_stays_quiet(
        log_path: Path, monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture) -> None:
    # A real write failure is surfaced (fail-open, not fail-silent) exactly once, then
    # telemetry latches off so a broken log can't spam every event or keep retrying.
    monkeypatch.setattr(dl, "_FAILURE_WARNED", False)
    home = str(Path.home())
    calls = {"n": 0}

    def boom(*_a, **_k):
        calls["n"] += 1
        # An OSError carries the absolute log path (home included).
        raise OSError(f"[Errno 30] Read-only file system: '{home}/proj/.cache/d.jsonl'")

    monkeypatch.setattr(dl, "_append_locked", boom)
    with caplog.at_level(logging.WARNING, logger=dl.logger.name):
        assert dl.record("routing", {"a": 1}, path=log_path) is False
        assert dl.record("routing", {"a": 2}, path=log_path) is False
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1                                   # surfaced once, not per event
    assert calls["n"] == 1                                      # latched off — no retry
    assert "could not write its decision log" in caplog.text
    assert home not in caplog.text                              # $HOME redacted from the warning
    assert "~/proj/.cache" in caplog.text


def test_disabled_and_no_project_never_warn(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture) -> None:
    # Expected no-op cases (opt-out, outside a project) must stay silent — no warning.
    monkeypatch.setattr(dl, "_FAILURE_WARNED", False)
    with caplog.at_level(logging.WARNING, logger=dl.logger.name):
        monkeypatch.setenv("CFS_DECISION_LOG", "off")
        assert dl.record("routing", {}, path=tmp_path / "d.jsonl") is False   # opt-out
        monkeypatch.delenv("CFS_DECISION_LOG")
        monkeypatch.setattr("studio.utils.files.find_studio_directory",
                            lambda *_a, **_k: None)
        assert dl.record("routing", {}) is False                             # no project
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_record_opens_no_socket(log_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def _boom(*_a, **_k):  # any socket construction is a failure for this module
        raise AssertionError("decision_log must not open a network socket")

    monkeypatch.setattr(socket, "socket", _boom)
    assert dl.record_validation("toc", "PASS", path=log_path) is True   # still writes, no socket


# ---------------------------------------------------------------------------
# redaction

def test_home_path_is_redacted(log_path: Path) -> None:
    home = str(Path.home())
    # $HOME must be redacted in payload values, payload keys, AND the command field.
    dl.record("dispatch", {f"{home}/k": f"{home}/project/x.md"},
              command=f"run {home}/x", path=log_path)
    obj = json.loads(log_path.read_text().splitlines()[0])
    assert obj["payload"]["~/k"].startswith("~/")
    assert obj["command"] == "run ~/x"
    assert home not in json.dumps(obj)


# ---------------------------------------------------------------------------
# rotation

def test_rotation_keeps_single_backup(log_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dl, "_MAX_BYTES", 200)
    for i in range(50):
        dl.record("routing", {"pad": "x" * 20, "i": i}, path=log_path)
    assert log_path.exists()
    assert log_path.with_name("decisions.jsonl.1").exists()   # rotated backup present


# ---------------------------------------------------------------------------
# wrappers

def test_wrappers_emit_expected_shapes(log_path: Path) -> None:
    dl.record_routing("gen", ["a", "b"], "b", "why", path=log_path)
    dl.record_dispatch("author", tier="std", model="m", path=log_path)
    dl.record_validation("toc", "FAIL", findings=3, rules={"E1": 3}, path=log_path)
    dl.record_review("PRD", "accept", path=log_path)
    dl.record_escalation("cheap", "std", "hard", path=log_path)
    events = {e["event"]: e["payload"] for e in dl.read_events(log_path)}
    assert set(events) == {"routing", "dispatch", "validation", "review", "escalation"}
    assert events["routing"]["selected"] == "b"
    assert events["validation"]["findings"] == 3
    assert events["review"]["decision"] == "accept"
    assert events["escalation"]["to_tier"] == "std"


def test_record_invocation_shape(log_path: Path) -> None:
    dl.record_invocation("validate", exit_code=2, duration_ms=42,
                         args_shape={"paths": 1}, path=log_path)
    ev = next(iter(dl.read_events(log_path, event="invocation")))
    assert ev["command"] == "validate"
    assert ev["payload"]["exit_code"] == 2
    assert ev["payload"]["duration_ms"] == 42
    assert ev["payload"]["args"] == {"paths": 1}      # arg-shape summary, never raw argv


def test_record_read_shape(log_path: Path) -> None:
    dl.record_read("tfidf", "doc.md", 8925, 49676, source="cli", path=log_path)
    ev = next(iter(dl.read_events(log_path, event="read")))
    assert ev["payload"]["method"] == "tfidf"
    assert ev["payload"]["lines"] == 8925
    assert ev["payload"]["tokens"] == 49676
    assert ev["payload"]["source"] == "cli"


def test_read_is_a_declared_event_name() -> None:
    assert "read" in dl.EVENTS


def test_summarize_reads_aggregates_tokens_and_lines_per_method(log_path: Path) -> None:
    dl.record_read("tfidf", "doc.md", 8925, 49676, path=log_path)
    dl.record_read("tfidf", "doc.md", 8925, 12000, path=log_path)
    dl.record_read("baseline", "doc.md", 8925, 333573, path=log_path)
    dl.record("routing", {"a": 1}, path=log_path)  # non-read event, must be ignored

    result = dl.summarize_reads(log_path)
    assert result["methods"]["tfidf"] == {"count": 2, "total_tokens": 61676, "total_lines": 17850}
    assert result["methods"]["baseline"] == {"count": 1, "total_tokens": 333573, "total_lines": 8925}
    assert result["total_tokens"] == 61676 + 333573


def test_summarize_reads_on_empty_log_returns_no_methods(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
    assert dl.summarize_reads() == {"methods": {}, "total_tokens": 0}


def _append_raw_read_line(log_path: Path, payload) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    obj = {"schema": dl.SCHEMA_VERSION, "ts": "2026-01-01T00:00:00+00:00",
           "run_id": "x", "decision_id": "", "event": "read", "command": "", "payload": payload}
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(obj) + "\n")


def test_summarize_reads_skips_a_non_dict_payload(log_path: Path) -> None:
    """CodeRabbit PR #111: a parseable "read" record whose payload isn't a
    dict (hand-edited or corrupted log) must not crash .get() -- skipped,
    same tolerance read_events() already gives an unparseable line."""
    _append_raw_read_line(log_path, "not-a-dict")
    dl.record_read("tfidf", "doc.md", 100, 200, path=log_path)

    result = dl.summarize_reads(log_path)
    assert result == {"methods": {"tfidf": {"count": 1, "total_tokens": 200, "total_lines": 100}},
                      "total_tokens": 200}


def test_summarize_reads_skips_non_numeric_tokens_or_lines(log_path: Path) -> None:
    _append_raw_read_line(log_path, {"method": "tfidf", "tokens": "not-a-number", "lines": 100})
    dl.record_read("baseline", "doc.md", 100, 200, path=log_path)

    result = dl.summarize_reads(log_path)
    assert result == {"methods": {"baseline": {"count": 1, "total_tokens": 200, "total_lines": 100}},
                      "total_tokens": 200}


# ---------------------------------------------------------------------------
# path resolution

def test_env_override_sets_log_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "custom.jsonl"
    monkeypatch.setenv("CFS_DECISION_LOG", str(target))
    assert dl.default_log_path() == target


def test_default_path_in_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CFS_DECISION_LOG", raising=False)
    monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
    assert dl.default_log_path() == tmp_path / ".cache" / "decisions.jsonl"


def test_default_path_survives_locator_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CFS_DECISION_LOG", raising=False)

    def _boom(*_a, **_k):
        raise RuntimeError("no working directory")

    monkeypatch.setattr("studio.utils.files.find_studio_directory", _boom)
    assert dl.default_log_path() is None          # locator error → no project, no raise


# ---------------------------------------------------------------------------
# fail-safe opt-out / redaction branches

def test_is_enabled_survives_unreadable_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CFS_DECISION_LOG", raising=False)

    class _Unreadable:
        def exists(self):
            raise OSError("home directory unreadable")

    monkeypatch.setattr(dl, "opt_out_sentinel_path", lambda: _Unreadable())
    assert dl.is_enabled() is False               # can't check opt-out → stay disabled, don't crash


def test_redact_survives_missing_home(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom():
        raise RuntimeError("no home directory")

    monkeypatch.setattr(Path, "home", _boom)
    assert dl._redact("/some/absolute/path") == "/some/absolute/path"   # returned unchanged, no raise


def test_redact_respects_home_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    # $HOME is only collapsed at a path boundary — a sibling dir must not be mangled.
    monkeypatch.setattr(Path, "home", lambda: Path("/Users/max"))
    assert dl._redact("/Users/maxine/x") == "/Users/maxine/x"   # sibling untouched (not "~ine/x")
    assert dl._redact("/Users/max/x") == "~/x"                  # real home redacted
    assert dl._redact("/Users/max") == "~"                      # bare home
    assert dl._redact("run /Users/max/x") == "run ~/x"          # mid-string, at boundary
    monkeypatch.setattr(Path, "home", lambda: Path("/"))
    assert dl._redact("/Users/max/x") == "/Users/max/x"         # root home -> no-op (never redact "/")


def test_rotation_failure_is_swallowed(log_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dl, "_MAX_BYTES", 50)
    dl.record("routing", {"pad": "x" * 80}, path=log_path)     # push the log over the limit

    def _boom(*_a, **_k):
        raise OSError("cannot rename")

    monkeypatch.setattr(dl.os, "replace", _boom)
    assert dl.record("routing", {"i": 1}, path=log_path) is True   # rotation fails, write still proceeds


def test_append_without_fcntl_still_writes(log_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def _no_fcntl(name, *a, **k):
        if name == "fcntl":
            raise ImportError("fcntl unavailable on this platform")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _no_fcntl)
    assert dl.record("routing", {"x": 1}, path=log_path) is True    # unlocked fallback path
    assert len(list(dl.read_events(log_path))) == 1


# ---------------------------------------------------------------------------
# read_events branches

def test_read_events_no_project_yields_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CFS_DECISION_LOG", raising=False)
    monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: None)
    assert list(dl.read_events()) == []


def test_read_events_missing_file_yields_nothing(tmp_path: Path) -> None:
    assert list(dl.read_events(tmp_path / "absent.jsonl")) == []


def test_read_events_unreadable_file_yields_nothing(log_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    dl.record("routing", {"a": 1}, path=log_path)
    real_open = Path.open

    def _boom(self, *a, **k):
        if self == log_path:
            raise OSError("permission denied")
        return real_open(self, *a, **k)

    monkeypatch.setattr(Path, "open", _boom)
    assert list(dl.read_events(log_path)) == []      # unreadable log → empty, not a raise


def test_read_events_skips_non_dict_json(log_path: Path) -> None:
    dl.record("routing", {"a": 1}, path=log_path)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write("123\n[1, 2]\n")                     # valid JSON, but not event objects
    events = list(dl.read_events(log_path))
    assert len(events) == 1
    assert events[0]["event"] == "routing"


def test_read_events_filters_and_limit(log_path: Path) -> None:
    dl.record("routing", {"a": 1}, path=log_path)
    dl.record("validation", {"status": "PASS"}, path=log_path)
    dl.record("routing", {"a": 2}, path=log_path)
    assert [e["payload"]["a"] for e in dl.read_events(log_path, event="routing")] == [1, 2]
    assert list(dl.read_events(log_path, run_id="does-not-exist")) == []
    assert len(list(dl.read_events(log_path, limit=1))) == 1


# ---------------------------------------------------------------------------
# gate events -- the write path a chat gate uses

def _gate_payload(log_path: Path) -> dict:
    """The single gate event's payload, read back through the module's reader."""
    events = [e for e in dl.read_events(path=log_path) if e["event"] == "gate"]
    assert len(events) == 1, f"expected one gate event, got {len(events)}"
    return events[0]["payload"]


@pytest.mark.parametrize("kind", dl.GATE_KINDS)
def test_every_gate_kind_emits_and_reads_back(kind: str, log_path: Path) -> None:
    """All five subtypes write, and land under one event name.

    The kind lives in the payload rather than the event name so a reader
    filtering `event == "gate"` sees every subtype; a test per kind is what makes
    that true of all five rather than of the one that happened to be tried.
    """
    assert dl.record_gate(kind, "PlanProduceChoice", "decision", path=log_path) is True
    payload = _gate_payload(log_path)
    assert payload["kind"] == kind
    assert payload["gate"] == "PlanProduceChoice"


def test_a_gate_event_carries_the_literal_type_and_the_engine_version(log_path: Path) -> None:
    """Both fields a post-hoc audit needs, or it cannot pin what to compare against.

    The audit compares an `auto-proceeded` event against the gate's source *at the
    version that read it*, which is the only way to catch a gate whose declared
    type changed after the run. Without the version the comparison has no anchor.
    """
    dl.record_gate("auto-proceeded", "SubAgentApprovalRequest", "blocking",
                   dl.GateRuling(why="the plan names native", cost_if_wrong="a re-run",
                                 provenance="plan", status="resolved"), path=log_path)
    payload = _gate_payload(log_path)
    assert payload["declared_type"] == "blocking"      # the literal token, not a paraphrase
    assert payload["core_version"], "no engine version recorded, so the audit has no anchor"
    assert payload["provenance"] == "plan"
    assert payload["cost_if_wrong"] == "a re-run"
    assert payload["status"] == "resolved"


def test_the_recorded_version_is_always_the_engine_that_ran(
        log_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No caller can substitute one, which is the point of removing the argument.

    `record_gate` used to accept `core_version=`, and only tests ever passed it. A
    handed-in value landed in the record indistinguishable from one the engine
    reported, so an auditor reading `core_version` could not tell which they had.
    The value is read here or not at all.
    """
    monkeypatch.setattr(dl, "_core_version", lambda: "v0.9.9")
    dl.record_gate("plan-resolved", "G", "decision", path=log_path)
    assert _gate_payload(log_path)["core_version"] == "v0.9.9"

    import inspect
    assert "core_version" not in inspect.signature(dl.record_gate).parameters, \
        "the caller-supplied version seam is back"


def test_author_controlled_gate_text_is_capped_and_the_cut_is_marked(log_path: Path) -> None:
    """`why` and `cost_if_wrong` are the one unbounded input on this path.

    Whatever resolved the gate writes them, so an uncapped value goes to disk at
    whatever length it likes. Truncation is marked, because a silently shortened
    reason reads as a complete one.
    """
    dl.record_gate("auto-proceeded", "g" * 5000, "decision",
                   dl.GateRuling(decision_key="k" * 5000, value="v" * 5000,
                                 why="w" * 5000, cost_if_wrong="c" * 5000),
                   path=log_path)
    payload = _gate_payload(log_path)
    # Every author-controlled field, not just the two free-text ones: uncapped,
    # the identity fields let a caller pad ~500 KB per event and drive real audit
    # history past the log's rotation bound.
    for field in ("gate", "decision_key", "value", "why", "cost_if_wrong"):
        assert len(payload[field]) <= dl._GATE_TEXT_CAP, \
            f"{field} is {len(payload[field])} chars, over the stated cap"
        assert dl._TRUNCATION_MARKER in payload[field], \
            f"{field} was cut without saying so"
    # Asserted against the constant, not a loose bound: `< 5000` passed with the
    # cap raised eightfold, so it pinned nothing about the stated 500.
    assert dl._GATE_TEXT_CAP == 500


def test_a_home_path_cut_by_the_cap_is_still_redacted(log_path: Path) -> None:
    """The cut must not land where redaction needs a path boundary.

    `_redact` collapses `$HOME` only where the path ends at a separator or at
    end-of-string. Capping first put the truncation marker in exactly that
    position, the lookahead failed, and a home path cut at the bound reached the
    log verbatim -- username included. Every offset around the boundary is probed,
    because the leak only appears where the cut lands on the prefix.
    """
    home = str(Path.home())
    for pad in range(dl._GATE_TEXT_CAP - len(home) - 4, dl._GATE_TEXT_CAP + 4):
        log_path.unlink(missing_ok=True)
        dl.record_gate("auto-proceeded", "G", "decision",
                       dl.GateRuling(why="a" * pad + home + "/notes.md"), path=log_path)
        assert home not in log_path.read_text(encoding="utf-8"), \
            f"$HOME reached the log when the cut fell at offset {pad}"


def test_an_unrecognised_gate_kind_warns_but_is_still_recorded(
        log_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Dropping it would hide a caller's bug; raising would break the never-raises contract.

    `record()` exists so instrumentation cannot change what a command does, so an
    unknown kind cannot be an exception. It also must not vanish: the audit seeing
    a malformed event is strictly better than seeing nothing.
    """
    with caplog.at_level(logging.WARNING, logger=dl.logger.name):
        assert dl.record_gate("invented", "G", "decision", path=log_path) is True
    assert _gate_payload(log_path)["kind"] == "invented"
    # getMessage(), not .message: the latter is set by a Formatter, so it may not
    # exist on a captured record and the assertion would fail on its own accessor.
    assert any("not a recognised gate kind" in r.getMessage() for r in caplog.records), \
        "an unknown kind was accepted in silence"


def test_record_gate_opens_no_socket(log_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No socket is constructed on the gate path.

    Weaker than it reads: it patches `socket.socket`, which nothing on this path
    references, so it catches a *future* network call rather than proving the
    present one is local. Kept as a tripwire, described as one.
    """
    import socket

    def _boom(*_a, **_k):
        raise AssertionError("record_gate must not open a network socket")

    monkeypatch.setattr(socket, "socket", _boom)
    assert dl.record_gate("plan-resolved", "G", "decision", path=log_path) is True


def test_a_gate_record_carries_no_home_path(log_path: Path) -> None:
    """The ruling fields are free text, so they are where $HOME leaks in."""
    home = str(Path.home())
    dl.record_gate("auto-proceeded", "G", "decision",
                   dl.GateRuling(why=f"read {home}/notes.md",
                                 cost_if_wrong=f"rewrite {home}/out.md"), path=log_path)
    written = log_path.read_text(encoding="utf-8")
    assert home not in written, "an absolute $HOME path reached the log"
    assert "~/notes.md" in written
    assert "~/out.md" in written


def test_an_explicit_path_does_not_defeat_the_opt_out(
        log_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`record_gate` inherits the opt-out rather than implementing one.

    Named for what it proves: the previous name said "without a special path" while
    the test passes one, which is the inverse of the property it establishes -- that
    naming a path explicitly does not bypass the user's opt-out.

    Opting out loses the record, never the authority: a gate's authority comes
    from its declared type. So this returns False and writes nothing, and a
    caller must not read that as "not permitted".
    """
    monkeypatch.setenv("CFS_DECISION_LOG", "off")
    assert dl.record_gate("auto-proceeded", "G", "decision", path=log_path) is False
    assert not log_path.exists()


def test_the_gate_payload_carries_the_frozen_resolution_shape(log_path: Path) -> None:
    """`decision_key → value → provenance → status`, so the plan reader maps nothing.

    The contract's fourth amendment requires the ledger to share the plan's shape
    "distinguished by `provenance` -- not a second format to look in". An earlier
    draft called `value` `resolution` and carried neither `decision_key` nor
    `status`, which is the second vocabulary that amendment forbids.
    """
    dl.record_gate("plan-resolved", "G", "decision",
                   dl.GateRuling(decision_key="plan.produce-mode", value="inline",
                                 provenance="plan", status="resolved"), path=log_path)
    payload = _gate_payload(log_path)
    for field in ("decision_key", "value", "provenance", "status"):
        assert field in payload, f"the frozen shape is missing {field}"
    assert "resolution" not in payload, "the pre-rename name is still being written"
    assert payload["decision_key"] == "plan.produce-mode"
    assert payload["value"] == "inline"


def test_an_omitted_ruling_field_is_visible_rather_than_blank(log_path: Path) -> None:
    """An omitted field renders as the literal `unspecified`, never a silent default.

    The contract's first amendment, from a field incident: a missing key and a key
    meaning "not specified" must not be distinguishable only by absence. Defaults
    of `""` made an omitted ruling byte-identical to an explicit empty one.
    """
    dl.record_gate("open-question", "G", "blocking", path=log_path)
    payload = _gate_payload(log_path)
    for field in ("decision_key", "value", "provenance", "status", "why", "cost_if_wrong"):
        assert payload[field] == dl.UNSPECIFIED, f"{field} is blank rather than visible"
    assert dl.UNSPECIFIED == "unspecified"


def test_the_gate_event_and_its_kinds_are_pinned_literally() -> None:
    """The constants, asserted against literals rather than against themselves.

    Two mutations survived otherwise. Removing `"gate"` from `EVENTS` changed
    nothing observable, although the module documents `EVENTS` as the event names
    it writes -- so the documentation would have quietly become false. And the
    per-kind test draws its cases from `GATE_KINDS`, so shrinking that tuple to one
    entry silently stopped exercising the other four while still passing.
    """
    assert "gate" in dl.EVENTS, "the module no longer documents the event it writes"
    assert dl.GATE_KINDS == ("auto-proceeded", "plan-resolved", "exception-asked",
                             "blocking-confirmed", "open-question")
    assert dl.GATE_PROVENANCE == ("plan", "ledger", "workflow-recommendation", "policy")
    assert dl.GATE_STATUSES == ("resolved", "absent", "ambiguous")


def test_the_recorded_version_is_the_engine_version(log_path: Path) -> None:
    """Not merely truthy: a stub string satisfied the previous assertion.

    The field is the engine that read the gate, so it has to *be* that, and a test
    that only checked for non-empty passed while the function returned a literal
    that was not a version at all.
    """
    from studio import __version__

    dl.record_gate("plan-resolved", "G", "decision", path=log_path)
    assert _gate_payload(log_path)["core_version"] == __version__


def _link_to_rotated(live: Path) -> None:
    """Write the rotation event a real rotation puts first in the new live segment.

    Tests build a `.1` by hand rather than writing 5 MiB, so they have to write the
    link by hand too -- an unclaimed backup is deliberately excluded now, and a
    fixture without this is testing the exclusion, not the join.
    """
    live.parent.mkdir(parents=True, exist_ok=True)
    with live.open("a", encoding="utf-8") as handle:
        handle.write('{"schema": 1, "event": "rotate", "run_id": "r", '
                     '"payload": {"segment": "%s.1"}}\n' % live.name)


def test_read_events_includes_the_rotated_segment(log_path: Path) -> None:
    """After a rotation the older half must still be reachable through the reader.

    `_rotate_if_large` keeps one `.1` backup, and the reader opened only the live
    file -- so a log that had rotated once presented half its history as absent,
    while the rest sat on disk. Harmless for telemetry; not harmless now that an
    autonomous resolution is audited from this log.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.with_name(log_path.name + ".1").write_text(
        '{"schema": 1, "event": "gate", "run_id": "old", "payload": {"gate": "Older"}}\n',
        encoding="utf-8")
    _link_to_rotated(log_path)          # the backup is this log's own predecessor
    dl.record_gate("plan-resolved", "Newer", "decision", path=log_path)

    gates = [e for e in dl.read_events(path=log_path) if e["event"] == "gate"]
    names = [e["payload"]["gate"] for e in gates]
    assert names == ["Older", "Newer"], f"rotated history missing or misordered: {names}"


def test_record_gate_never_raises_on_an_unstringable_value(
        log_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Assembling the payload must not be able to escape as an exception.

    `_capped` calls `str(value)` and runs before `record()`'s own guard, so a value
    whose `__str__` raises used to propagate out of `record_gate` -- breaking the
    contract that logging never changes what a command does. Reachable only from a
    library caller, since the CLI passes strings, but the contract is stated here.
    """
    class Hostile:
        def __str__(self):
            raise ValueError("boom from __str__")

    with caplog.at_level(logging.WARNING, logger=dl.logger.name):
        assert dl.record_gate("plan-resolved", "G", "decision",
                              dl.GateRuling(why=Hostile()), path=log_path) is False
    assert any("could not be assembled" in r.getMessage() for r in caplog.records), \
        "the failure was swallowed without a reason"
    assert not log_path.exists() or not [
        e for e in dl.read_events(path=log_path) if e["event"] == "gate"]


@pytest.mark.parametrize(("label", "codepoint"), [
    ("BOM", 0xFEFF), ("zero-width space", 0x200B), ("NBSP", 0xA0),
    ("NEL", 0x85), ("ideographic space", 0x3000),
])
def test_a_value_of_invisible_characters_counts_as_blank(label: str, codepoint: int) -> None:
    """`.strip()` alone let a BOM or a zero-width space stand in for an answer.

    It removes NBSP and NEL but not U+FEFF or U+200B, so a `cost_if_wrong` of
    those satisfied the guard that exists to require a stated cost -- an
    autonomous ruling recorded with nothing in it.
    """
    assert dl.is_blank(chr(codepoint)), f"{label} is treated as a real value"
    assert dl.is_blank(chr(codepoint) * 5 + " ")
    assert not dl.is_blank(chr(codepoint) + "a real cost")


def test_the_writer_reports_an_off_list_declared_type(
        log_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Parity with the command, which rejects one outright.

    `declared_type` is the field an auditor compares against. The CLI constrained
    it and the writer did not, so the looser of the two paths decided what a record
    could contain. The writer warns rather than refuses, because instrumentation
    must not change what a caller does -- but it no longer accepts one in silence.
    """
    with caplog.at_level(logging.WARNING, logger=dl.logger.name):
        assert dl.record_gate("plan-resolved", "G", "a paraphrase of blocking",
                              path=log_path) is True
    assert any("not a recognised declared gate type" in r.getMessage()
               for r in caplog.records)


def test_the_writer_uses_the_checkers_own_gate_types() -> None:
    """One set, not a copy that can drift from the lint's."""
    from studio.utils.pdsl import GATE_TYPES

    assert dl._gate_types() == GATE_TYPES
    assert GATE_TYPES == ("confirmation", "decision", "blocking")


def test_one_gate_event_is_bounded_by_its_caps_not_by_its_caller(log_path: Path) -> None:
    """An event's size must be the caps' business, not the caller's.

    A3b: uncapped author-controlled fields plus a size-bounded log is a
    history-destruction primitive -- ~500 KB per event drove the 5 MiB rotation, so
    ten calls made a real record unreachable and twenty destroyed it. Capping every
    field is what makes eviction slow enough to be uninteresting, so the bound on a
    single line is the property worth pinning.
    """
    huge = "x" * 200_000
    assert dl.record_gate(huge, huge, huge,
                          dl.GateRuling(decision_key=huge, value=huge, provenance=huge,
                                        status=huge, why=huge, cost_if_wrong=huge),
                          path=log_path) is True

    line = log_path.read_text(encoding="utf-8").splitlines()[0]
    # Nine capped fields plus the envelope; generous, but orders below the input.
    assert len(line) < dl._GATE_TEXT_CAP * 20, f"one event reached {len(line)} chars"
    assert len(line) < len(huge), "the caller's length still decides the event's size"


def test_a_capped_event_does_not_evict_an_earlier_one(
        log_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The canary must survive the writes that used to bury it."""
    monkeypatch.setattr(dl, "_MAX_BYTES", 20_000)
    dl.record_gate("auto-proceeded", "Canary", "blocking",
                   dl.GateRuling(why="the one an auditor comes back for"), path=log_path)
    huge = "y" * 200_000
    for _ in range(3):
        dl.record_gate("plan-resolved", huge, "decision",
                       dl.GateRuling(value=huge, why=huge), path=log_path)

    names = [e["payload"]["gate"] for e in dl.read_events(path=log_path)
             if e["event"] == "gate"]
    assert "Canary" in names, f"the earlier record was evicted; log holds {len(names)} events"


def test_logging_state_keeps_the_undeterminable_case_apart(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`is_enabled()` fails closed; a *reporter* needs the third state.

    An unreadable opt-out sentinel is not a user's opt-out, and reporting it as one
    sends someone hunting for a setting they never changed. `is_enabled()` keeps its
    boolean contract for writers, which is right -- it should fail closed.
    """
    class _Unreadable:
        def exists(self):
            raise OSError("permission denied")

    # Isolated before the ordinary case is asserted, not after. It used to read the
    # real `~/.cf-studio/decisions.off`, so a maintainer who had opted out on their
    # own machine failed this test for a reason unrelated to the code -- and an
    # inherited `$CFS_DECISION_LOG` could decide it either way. The two later cases
    # were already isolated; this one was borrowing the developer's environment.
    monkeypatch.delenv("CFS_DECISION_LOG", raising=False)
    monkeypatch.setattr(dl, "opt_out_sentinel_path",
                        lambda: tmp_path / "absent" / "decisions.off")
    assert dl.logging_state() is True                      # ordinary case
    monkeypatch.setenv("CFS_DECISION_LOG", "off")
    assert dl.logging_state() is False                     # off by choice
    monkeypatch.delenv("CFS_DECISION_LOG")
    monkeypatch.setattr(dl, "opt_out_sentinel_path", lambda: _Unreadable())
    assert dl.logging_state() is None                      # cannot be told
    assert dl.is_enabled() is False                        # the writer still fails closed



class TestTheRulingShapeIsFrozen:
    """`frozen=True` is a claim the tests never checked.

    The ruling is the shape the plan's vocabulary is shared through, and it is
    passed by reference into the writer. If a field could be reassigned after
    construction, a caller could mutate a ruling that another had already handed
    over -- and `frozen=True` was carrying that guarantee with nothing pinning it,
    so dropping the flag would have broken no test.
    """

    def test_a_field_cannot_be_reassigned_after_construction(self) -> None:
        """`FrozenInstanceError` by name: `Exception` would also pass on a typo.

        The first version caught `Exception` and accepted any message containing
        "frozen", which would have been satisfied by an `AttributeError` from
        misspelling the field -- the opposite of the property under test.
        """
        ruling = dl.GateRuling(decision_key="plan.produce-mode", value="inline")
        with pytest.raises(dataclasses.FrozenInstanceError):
            ruling.value = "package"        # type: ignore[misc]

    def test_every_field_defaults_to_the_visible_sentinel(self) -> None:
        """An omitted value has to be readable as omitted, not as blank."""
        ruling = dl.GateRuling()
        for field in ("decision_key", "value", "provenance", "status", "why",
                      "cost_if_wrong"):
            assert getattr(ruling, field) == dl.UNSPECIFIED, field


class TestEveryRecordedFieldIsCappedAndRedacted:
    """Field by field, not one field standing in for the rest.

    The cap and the redaction were asserted through `why` and `cost_if_wrong`, the
    two obviously author-controlled fields. The identity fields carry
    author-controlled text too -- a `kind` or a `provenance` from a MENU block is
    as unbounded as a reason -- and uncapped they let a caller flush real audit
    history past the log's rotation bound. One test per field, so a field losing
    its transform fails on its own name.
    """

    @pytest.mark.parametrize("field", ["kind", "gate", "declared_type", "provenance",
                                       "status", "why", "cost_if_wrong",
                                       "core_version"])
    def test_the_field_is_cut_at_the_cap_with_the_cut_marked(
            self, field: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        log = tmp_path / "decisions.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        long = "x" * (dl._GATE_TEXT_CAP * 3)
        call = {"kind": "auto-proceeded", "gate": "G", "declared_type": "decision"}
        ruling_fields = {"provenance": "plan", "status": "resolved",
                         "why": "w", "cost_if_wrong": "c"}
        core_version = "1.0.0"
        if field in call:
            call[field] = long
        elif field in ruling_fields:
            ruling_fields[field] = long
        else:
            core_version = long

        monkeypatch.setattr(dl, "_core_version", lambda: core_version)
        assert dl.record_gate(call["kind"], call["gate"], call["declared_type"],
                              dl.GateRuling(**ruling_fields), path=log) is True
        payload = [e for e in dl.read_events(path=log)][-1]["payload"]
        written = payload.get(field) or payload.get("ruling", {}).get(field)
        assert isinstance(written, str), (field, payload)
        assert len(written) <= dl._GATE_TEXT_CAP, (field, len(written))
        assert written.endswith(dl._TRUNCATION_MARKER), field

    @pytest.mark.parametrize("field", ["kind", "gate", "declared_type", "provenance",
                                       "status", "why", "cost_if_wrong"])
    def test_a_home_path_in_the_field_is_collapsed(
            self, field: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        log = tmp_path / "decisions.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        monkeypatch.setenv("HOME", "/home/someone")
        home = "/home/someone/work"
        call = {"kind": "auto-proceeded", "gate": "G", "declared_type": "decision"}
        ruling_fields = {"provenance": "plan", "status": "resolved",
                         "why": "w", "cost_if_wrong": "c"}
        if field in call:
            call[field] = home
        else:
            ruling_fields[field] = home

        assert dl.record_gate(call["kind"], call["gate"], call["declared_type"],
                             dl.GateRuling(**ruling_fields), path=log) is True
        line = log.read_text(encoding="utf-8").strip().splitlines()[-1]
        assert "/home/someone" not in line, field
        assert "~/work" in line, field


class TestTheRecoveryPathCannotItselfRaise:
    """The guard around the payload build used to reproduce the defect it fixed.

    A value whose `__str__` raises escaped `record_gate`, so the build was wrapped.
    The handler then called `str()` on the exception it had caught -- the same act
    of trust one level up -- and an exception with a hostile `__str__` raised
    straight out of the handler. Only a library caller can reach either, since the
    CLI always passes strings, but the never-raises contract is stated on this
    function too.
    """

    class _Hostile(Exception):
        def __str__(self) -> str:
            raise RuntimeError("this exception will not describe itself")

    class _Unprintable:
        def __str__(self) -> str:
            raise TestTheRecoveryPathCannotItselfRaise._Hostile()

    def test_a_hostile_exception_is_described_by_class_and_not_raised(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
            caplog) -> None:
        monkeypatch.setenv("CFS_DECISION_LOG", str(tmp_path / "d.jsonl"))
        with caplog.at_level(logging.WARNING, logger=dl.logger.name):
            recorded = dl.record_gate("auto-proceeded", self._Unprintable(),  # type: ignore[arg-type]
                                      "decision", path=tmp_path / "d.jsonl")
        assert recorded is False
        assert any("_Hostile" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]

    def test_an_ordinary_exception_is_still_described_by_its_message(self) -> None:
        """The fallback must not cost the detail every other failure carries."""
        assert dl._describe(ValueError("a plain message")) == "a plain message"


class TestTheReaderLockActuallySerialises:
    """The lock was asserted by reading the code, which is not evidence.

    `_read_segments_locked` was added because a rotation between the two reads
    moves live events into a segment already read. Nothing proved it *waits* --
    the tests only showed it returned the right lines, which it did before the
    lock existed too. These drive the lock itself.
    """

    def test_a_read_waits_while_the_writers_lock_is_held(self, tmp_path: Path) -> None:
        """Held from a second descriptor, which is what the writer really is.

        `flock` is held per open file description, so two opens in one process
        contend exactly as two processes would.
        """
        fcntl = pytest.importorskip("fcntl")
        import threading

        log = tmp_path / "decisions.jsonl"
        log.write_text('{"event":"gate","run_id":"r"}\n', encoding="utf-8")
        lock = log.with_name(log.name + ".lock")

        finished = threading.Event()
        lines: list[str] = []

        def _read() -> None:
            lines.extend(dl._read_segments_locked(log))
            finished.set()

        reader = threading.Thread(target=_read, daemon=True)
        with open(lock, "a", encoding="utf-8") as held:
            fcntl.flock(held.fileno(), fcntl.LOCK_EX)
            reader.start()
            assert not finished.wait(0.5), \
                "the read completed while the writer's lock was held"
        reader.join(timeout=10)
        assert finished.is_set(), "the read never completed after the lock was freed"
        assert len(lines) == 1

    def test_both_segments_come_back_as_one_snapshot(self, tmp_path: Path) -> None:
        """Oldest-first across the rotation boundary, which is the contract."""
        log = tmp_path / "decisions.jsonl"
        log.with_name(log.name + ".1").write_text('{"event":"a"}\n', encoding="utf-8")
        _link_to_rotated(log)
        with log.open("a", encoding="utf-8") as handle:
            handle.write('{"event":"b"}\n')
        assert [e["event"] for e in dl.read_events(path=log)
                if e["event"] != "rotate"] == ["a", "b"]


class TestTheUnlockedFallbacksAreReached:
    """Both degradations, neither of which any test entered.

    They exist so a platform without `fcntl` and a log whose lock cannot be opened
    still yield a trail rather than an empty one -- and an untested fallback is a
    claim, not a behaviour.
    """

    def test_a_platform_without_fcntl_still_reads_both_segments(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`None` in `sys.modules` makes the lazy `import fcntl` raise ImportError."""
        import sys
        monkeypatch.setitem(sys.modules, "fcntl", None)
        log = tmp_path / "decisions.jsonl"
        log.with_name(log.name + ".1").write_text('{"event":"a"}\n', encoding="utf-8")
        _link_to_rotated(log)
        with log.open("a", encoding="utf-8") as handle:
            handle.write('{"event":"b"}\n')
        assert [e["event"] for e in dl.read_events(path=log)
                if e["event"] != "rotate"] == ["a", "b"]

    def test_an_unopenable_lock_is_read_unlocked_rather_than_reported_empty(
            self, tmp_path: Path, caplog) -> None:
        """A log that cannot be locked is still evidence."""
        log = tmp_path / "decisions.jsonl"
        log.write_text('{"event":"a"}\n', encoding="utf-8")
        # A directory where the lock file belongs: `open(..., "a")` raises
        # IsADirectoryError, an OSError, which is the branch under test.
        log.with_name(log.name + ".lock").mkdir()
        with caplog.at_level(logging.DEBUG, logger=dl.logger.name):
            assert [e["event"] for e in dl.read_events(path=log)] == ["a"]
        # The branch, not just the outcome: returning ["a"] is also what a *lockable*
        # log returns, so without this the test passed whether or not the fallback ran.
        assert any("lock unavailable" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]

    def test_an_unreadable_segment_warns_rather_than_hiding_at_debug(
            self, tmp_path: Path, caplog) -> None:
        """Absence is normal and quiet; a segment that exists and will not read is not."""
        if not hasattr(os, "geteuid"):
            pytest.skip("POSIX-only: mode bits do not gate reads the same way elsewhere")
        if os.geteuid() == 0:
            pytest.skip("root reads a mode-000 file, so the branch cannot be entered")
        log = tmp_path / "decisions.jsonl"
        # The link first, then the live event. Appended after it, the claim is not
        # the file's first line, so the backup was excluded and this never reached
        # the unreadable-segment branch at all -- and because the rotation event
        # was itself in `events`, the guard clause that was meant to allow for root
        # never matched either, so the assertion did not run. The test passed
        # without testing anything.
        _link_to_rotated(log)
        with log.open("a", encoding="utf-8") as handle:
            handle.write('{"event":"a"}\n')
        rotated = log.with_name(log.name + ".1")
        rotated.write_text('{"event":"older"}\n', encoding="utf-8")
        rotated.chmod(0o000)
        try:
            with caplog.at_level(logging.WARNING, logger=dl.logger.name):
                events = [e["event"] for e in dl.read_events(path=log)]
        finally:
            rotated.chmod(0o644)
        assert "older" not in events, events
        assert any("could not be read" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]


class TestAStaleBackupIsNotPresentedAsHistory:
    """The reported case: clear the live log, leave the backup, read continuous history.

    Reading the `.1` segment was itself a fix -- a rotated log used to present half
    its history as absent. Reading it *unconditionally* is the opposite failure:
    nothing on disk says whether that segment is this log's own predecessor or a
    leftover from a lifecycle an operator deliberately ended. So the rotation writes
    the link, and a segment nothing claims is excluded.
    """

    def test_a_cleared_log_does_not_prepend_its_leftover_backup(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        log = tmp_path / "decisions.jsonl"
        log.with_name(log.name + ".1").write_text(
            '{"event":"gate","payload":{"gate":"FromAPreviousLifecycle"}}\n',
            encoding="utf-8")
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        # A fresh live log: its first event is an ordinary one, not a rotation.
        assert dl.record_gate("plan-resolved", "AfterTheReset", "decision",
                              path=log) is True
        gates = [e["payload"]["gate"] for e in dl.read_events(path=log)
                 if e["event"] == "gate"]
        assert gates == ["AfterTheReset"], gates

    def test_the_exclusion_is_warned_about_rather_than_silent(
            self, tmp_path: Path, caplog) -> None:
        """Half a trail vanishing quietly is the failure this level exists to avoid."""
        log = tmp_path / "decisions.jsonl"
        log.write_text('{"event":"gate","payload":{"gate":"Live"}}\n', encoding="utf-8")
        log.with_name(log.name + ".1").write_text('{"event":"gate"}\n', encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger=dl.logger.name):
            list(dl.read_events(path=log))
        assert any("not claimed" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]

    def test_a_link_naming_a_different_segment_does_not_claim_this_one(
            self, tmp_path: Path) -> None:
        """The link names its segment, so it cannot be satisfied by any rotation."""
        log = tmp_path / "decisions.jsonl"
        log.write_text('{"event":"rotate","payload":{"segment":"somewhere-else.1"}}\n'
                       '{"event":"gate","payload":{"gate":"Live"}}\n', encoding="utf-8")
        log.with_name(log.name + ".1").write_text('{"event":"gate"}\n', encoding="utf-8")
        assert [e["event"] for e in dl.read_events(path=log)] == ["rotate", "gate"]

    def test_only_the_first_event_can_claim_the_backup(self, tmp_path: Path) -> None:
        """A rotation event later in the file describes a rotation this file is not."""
        log = tmp_path / "decisions.jsonl"
        log.write_text('{"event":"gate","payload":{"gate":"Live"}}\n'
                       '{"event":"rotate","payload":{"segment":"decisions.jsonl.1"}}\n',
                       encoding="utf-8")
        log.with_name(log.name + ".1").write_text('{"event":"gate"}\n', encoding="utf-8")
        assert [e["event"] for e in dl.read_events(path=log)] == ["gate", "rotate"]

    def test_a_real_rotation_writes_the_link_and_the_join_survives_it(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """End to end through the writer's own rotation, not a hand-built fixture."""
        log = tmp_path / "decisions.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        monkeypatch.setattr(dl, "_MAX_BYTES", 200)
        for i in range(6):
            assert dl.record_gate("plan-resolved", f"Gate{i}", "decision",
                                  path=log) is True
        assert log.with_name(log.name + ".1").is_file(), "did not rotate"
        events = list(dl.read_events(path=log))
        assert any(e["event"] == "rotate" for e in events), "no link written"
        gates = [e["payload"]["gate"] for e in events if e["event"] == "gate"]
        # Not every gate: one backup is kept, so a cap this small rotates several
        # times and the earliest generations are gone by design. What this pins is
        # that the surviving backup is *joined* -- the newest gate plus at least one
        # older one, which is only possible across the two segments.
        assert "Gate5" in gates, gates                 # the live segment
        assert len(gates) > 1, gates                   # and at least one from the backup


class TestTheReadLockIsBounded:
    """An unbounded `flock` is a hang, and this repo fixed that once already.

    `#136` round-4 review found `record_tier2_escalation` entering the
    always-blocking path, so one process holding a lock could hang an entire
    command. `atomic_io.with_file_lock` grew a bounded poll loop for it. The first
    version of this reader wrote a fresh `flock(LOCK_EX)` instead, reintroducing
    exactly that defect one module over.
    """

    def test_a_held_lock_does_not_hang_the_read(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
        """Bounded, and it still returns the trail rather than nothing."""
        pytest.importorskip("fcntl")
        import fcntl as fcntl_mod

        log = tmp_path / "decisions.jsonl"
        log.write_text('{"event":"gate","payload":{"gate":"Held"}}\n', encoding="utf-8")
        monkeypatch.setattr(dl, "_READ_LOCK_TIMEOUT_SECONDS", 0.3)

        # On a thread with a join bound, because an unbounded reader does not *fail*
        # this test -- it hangs it, and a hung test is a worse signal than a red one.
        # With the bound removed, the join expires and this reports cleanly.
        import threading
        events: list[str] = []
        done = threading.Event()

        def _read() -> None:
            events.extend(e["payload"]["gate"] for e in dl.read_events(path=log))
            done.set()

        with open(log.with_name(log.name + ".lock"), "a", encoding="utf-8") as held:
            fcntl_mod.flock(held.fileno(), fcntl_mod.LOCK_EX)
            with caplog.at_level(logging.WARNING, logger=dl.logger.name):
                reader = threading.Thread(target=_read, daemon=True)
                reader.start()
                assert done.wait(10), (
                    "the read never returned while the lock was held: the bound is gone"
                )

        assert events == ["Held"], "the trail was lost rather than read unlocked"
        assert any("timed out" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]

    def test_the_bound_is_a_named_constant_not_a_literal(self) -> None:
        """So it can be found, tuned and compared with the sibling bound."""
        assert isinstance(dl._READ_LOCK_TIMEOUT_SECONDS, float)
        assert 0 < dl._READ_LOCK_TIMEOUT_SECONDS <= 30

    def test_the_reader_uses_the_shared_helper_rather_than_its_own_flock(self) -> None:
        """The point of the fix: one bounded lock implementation, not two."""
        # From the module, not the working directory: a relative path made this pass
        # only when pytest happened to run from the repository root.
        src = Path(dl.__file__).read_text(encoding="utf-8")
        assert "with_file_lock(" in src, "the reader no longer uses the shared helper"
        assert "flock(" not in src.split("def _read_segments_locked")[1].split("def ")[0], \
            "the reader took its own flock again"


class TestTheRotationLinkSurvivesAHostileName:
    """A filesystem name is bytes, and bytes reach Python as lone surrogates.

    `_write_rotation_link` serialised `backup.name` straight into JSON. A name
    carrying a raw byte arrives through surrogateescape, `json.dumps` cannot encode
    it, and the `UnicodeEncodeError` — a `ValueError` — went straight past the
    `OSError` guard. The damage is worse than a failed write: `os.replace` has
    already rotated the file by then, so the backup is left permanently unclaimed
    and unreadable by the very check the link exists to satisfy.
    """

    def test_a_surrogate_in_the_segment_name_does_not_raise(self, tmp_path: Path) -> None:
        log = tmp_path / "decisions\udcff.jsonl"
        dl._write_rotation_link(log, log.with_name(log.name + ".1"))
        # Not `is_file()`: the encode error happens *during* the write, after append
        # mode has already created the file, so existence proves nothing. The link
        # line itself has to be there and parseable — that is what the claim check
        # reads, and what an unencodable name destroyed.
        written = [json.loads(line) for line in
                   log.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert written, "the link line was never written"
        assert written[0]["event"] == "rotate", written[0]
        assert written[0]["payload"]["segment"], "the segment name is empty"

    def test_the_link_is_still_readable_after_the_name_is_capped(
            self, tmp_path: Path) -> None:
        """Capping must not break the claim: a capped name still has to match."""
        log = tmp_path / "decisions.jsonl"
        backup = log.with_name(log.name + ".1")
        backup.write_text('{"event":"older"}\n', encoding="utf-8")
        dl._write_rotation_link(log, backup)
        with log.open("a", encoding="utf-8") as handle:
            handle.write('{"event":"live"}\n')
        assert [e["event"] for e in dl.read_events(path=log)] == \
            ["older", "rotate", "live"]


class TestEveryGateFieldIsRedactedNotJustTheObviousOnes:
    """`decision_key`, `value` and `core_version` were asserted for the cap only.

    The per-field cap test covered all eight; the redaction test covered seven and
    skipped `core_version`, and neither named `decision_key` or `value` explicitly
    for `$HOME`. An identity field carrying a home path leaks exactly as a reason
    field does.
    """

    @pytest.mark.parametrize("field", ["decision_key", "value", "core_version"])
    def test_a_home_path_in_this_field_is_collapsed(
            self, field: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        log = tmp_path / "decisions.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        monkeypatch.setenv("HOME", "/home/someone")
        home = "/home/someone/work"
        ruling = {"decision_key": "k", "value": "v"}
        core_version = "1.0.0"
        if field in ruling:
            ruling[field] = home
        else:
            core_version = home
        monkeypatch.setattr(dl, "_core_version", lambda: core_version)
        assert dl.record_gate("auto-proceeded", "G", "decision",
                              dl.GateRuling(**ruling), path=log) is True
        line = log.read_text(encoding="utf-8").strip().splitlines()[-1]
        assert "/home/someone" not in line, field
        assert "~/work" in line, field


def test_the_cap_boundary_is_exact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """At the cap, one under, one over — the off-by-one the cap tests never probed.

    Every cap test used a value three times the bound, which cannot tell a correct
    cap from one that is off by one in either direction.
    """
    monkeypatch.setenv("CFS_DECISION_LOG", str(tmp_path / "d.jsonl"))
    cap = dl._GATE_TEXT_CAP
    for length, truncated in ((cap - 1, False), (cap, False), (cap + 1, True)):
        out = dl._capped("x" * length)
        assert len(out) <= cap, (length, len(out))
        assert out.endswith(dl._TRUNCATION_MARKER) is truncated, (length, out[-20:])


class TestASwappedBackupIsNotAcceptedAsThePredecessor:
    """The name proves a rotation happened; it does not prove *this* file was it.

    `_rotated_segment_belongs` compared `backup.name` alone, so any file later placed
    at that path was accepted as the claimed predecessor and joined into the trail —
    the same silent-fabrication failure the claim check was built to prevent, one
    level down.
    """

    def _rotated_pair(self, tmp_path: Path) -> tuple[Path, Path]:
        log = tmp_path / "decisions.jsonl"
        backup = log.with_name(log.name + ".1")
        backup.write_text('{"event":"older","payload":{}}\n', encoding="utf-8")
        dl._write_rotation_link(log, backup)
        with log.open("a", encoding="utf-8") as handle:
            handle.write('{"event":"live","payload":{}}\n')
        return log, backup

    def test_the_genuine_segment_is_still_joined(self, tmp_path: Path) -> None:
        log, _ = self._rotated_pair(tmp_path)
        assert [e["event"] for e in dl.read_events(path=log)] == \
            ["older", "rotate", "live"]

    def test_a_different_file_with_the_same_name_is_excluded(
            self, tmp_path: Path, caplog) -> None:
        log, backup = self._rotated_pair(tmp_path)
        backup.write_text('{"event":"substituted","payload":{}}\n', encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger=dl.logger.name):
            events = [e["event"] for e in dl.read_events(path=log)]
        assert "substituted" not in events, events
        assert any("does not match" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]

    def test_a_same_length_substitution_is_still_caught(self, tmp_path: Path) -> None:
        """Size alone is weak, which is why the segment's content is digested too.

        Stale wording, caught in review: this said "the first line is digested",
        which was the superseded design. A reader could conclude that records after
        the first go unverified — the opposite of what the sibling test below proves.
        """
        log, backup = self._rotated_pair(tmp_path)
        original = backup.read_text(encoding="utf-8")
        swapped = original.replace("older", "newer")
        assert len(swapped) == len(original), "the fixture no longer tests equal length"
        backup.write_text(swapped, encoding="utf-8")
        assert "newer" not in [e["event"] for e in dl.read_events(path=log)]

    def test_a_link_written_before_fingerprints_existed_is_still_honoured(
            self, tmp_path: Path) -> None:
        """Rejecting those would drop history that is very probably genuine."""
        log = tmp_path / "decisions.jsonl"
        log.with_name(log.name + ".1").write_text('{"event":"older"}\n', encoding="utf-8")
        log.write_text(
            '{"event":"rotate","payload":{"segment":"decisions.jsonl.1"}}\n'
            '{"event":"live"}\n', encoding="utf-8")
        assert [e["event"] for e in dl.read_events(path=log)] == \
            ["older", "rotate", "live"]


class TestTheFingerprintCoversTheWholeSegment:
    """Four holes the first version of this fix left, each found in its own review."""

    def _linked(self, tmp_path: Path, name: str = "decisions.jsonl") -> tuple[Path, Path]:
        log = tmp_path / name
        backup = log.with_name(log.name + ".1")
        backup.write_text('{"event":"older","payload":{}}\n{"event":"second","payload":{}}\n',
                          encoding="utf-8")
        dl._write_rotation_link(log, backup)
        with log.open("a", encoding="utf-8") as handle:
            handle.write('{"event":"live","payload":{}}\n')
        return log, backup

    def test_a_change_to_a_later_record_is_caught(self, tmp_path: Path) -> None:
        """First line and length both preserved — the case a head digest cannot see."""
        log, backup = self._linked(tmp_path)
        original = backup.read_text(encoding="utf-8")
        tampered = original.replace('"second"', '"SECOND"')
        assert len(tampered) == len(original), "the fixture no longer preserves length"
        assert tampered.split("\n")[0] == original.split("\n")[0], "first line changed"
        backup.write_text(tampered, encoding="utf-8")
        assert "older" not in [e["event"] for e in dl.read_events(path=log)]

    def test_an_unreadable_fingerprint_excludes_rather_than_admits(
            self, tmp_path: Path, caplog) -> None:
        """A claimed fingerprint that cannot be checked is not a match.

        The first version returned True here, conflating "none was recorded" with "one
        was recorded and cannot be read" — so an unverifiable segment joined anyway.
        """
        if not hasattr(os, "geteuid") or os.geteuid() == 0:
            pytest.skip("needs a non-root POSIX uid for mode bits to gate the read")
        log, backup = self._linked(tmp_path)
        backup.chmod(0o000)
        try:
            with caplog.at_level(logging.WARNING, logger=dl.logger.name):
                events = [e["event"] for e in dl.read_events(path=log)]
        finally:
            backup.chmod(0o644)
        assert "older" not in events, events
        # `stat()` succeeds on a mode-000 file while the read does not, so the identity
        # comes back *partial* — the size without the digest — and the comparison
        # rejects it rather than the empty-identity branch firing. Either way the segment
        # is excluded and a warning says why; asserting one specific message pinned the
        # wrong path.
        # The read itself now fails first, so the message is about the read rather than
        # about a partial fingerprint: the backup is read once and checked against those
        # bytes, which is what closed the window between the two. Asserted on what the
        # line has to tell an operator — that the bytes did not arrive, and that the
        # segment is therefore out of this read — not on its exact phrasing.
        messages = [r.getMessage() for r in caplog.records]
        assert any("could not be read" in m for m in messages), messages
        assert any("excluded from this read" in m for m in messages), messages

    def test_a_hostile_name_can_still_claim_its_own_backup(self, tmp_path: Path) -> None:
        """The link stores the capped name, so the comparison must cap too.

        Capping the name to stop an encode crash made the stored value differ from the
        raw one compared against it, so a rotation with a surrogate in its name could
        never claim its genuine backup and the reader dropped valid history.
        """
        log, _ = self._linked(tmp_path, name="decisions\udcff.jsonl")
        assert [e["event"] for e in dl.read_events(path=log)] == \
            ["older", "second", "rotate", "live"]

    def test_no_filesystem_warning_anywhere_renders_a_raw_exception(self) -> None:
        """CWE-532: an OSError's own text carries the absolute path, and any bytes in it.

        Swept across the module rather than over the one function that had the defect.
        Pinning it to `_segment_identity` meant that moving the read into a shared helper
        moved the sink out from under the test, which is exactly how the next one gets
        added unnoticed.

        Bound by the AST, not by the spelling: the first version grepped for the name
        `exc`, so a handler that called its exception anything else walked straight past
        it. Here every `except ... as <name>` contributes its own name, whatever it is,
        and any log call that passes that name without `_describe` is the finding.
        """
        tree = ast.parse(Path(dl.__file__).read_text(encoding="utf-8"))
        offenders = []
        for handler in ast.walk(tree):
            if not isinstance(handler, ast.ExceptHandler) or not handler.name:
                continue
            caught = handler.name
            for call in ast.walk(handler):
                if not isinstance(call, ast.Call):
                    continue
                func = call.func
                if not (isinstance(func, ast.Attribute)
                        and isinstance(func.value, ast.Name) and func.value.id == "logger"):
                    continue
                for arg in call.args:
                    if isinstance(arg, ast.Name) and arg.id == caught:
                        offenders.append(f"line {call.lineno}: logger.{func.attr}(..., {caught})")
        assert not offenders, \
            f"an exception reaches a log record unredacted: {offenders}"


def test_an_entirely_unreadable_identity_excludes_the_segment(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    """The branch the filesystem cases do not reach, exercised directly.

    The backup is now read once and fingerprinted from those bytes, so a filesystem
    failure is caught by the read itself. The empty-identity branch remains for the case
    where the fingerprint of bytes in hand comes back empty, and it is the one that used
    to return `True` and admit an unverified segment. Patching the fingerprinter is the
    only way to reach it.
    """
    log = tmp_path / "decisions.jsonl"
    backup = log.with_name(log.name + ".1")
    backup.write_text('{"event":"older","payload":{}}\n', encoding="utf-8")
    dl._write_rotation_link(log, backup)
    with log.open("a", encoding="utf-8") as handle:
        handle.write('{"event":"live","payload":{}}\n')

    monkeypatch.setattr(dl, "_identity_of", lambda data: {})
    with caplog.at_level(logging.WARNING, logger=dl.logger.name):
        events = [e["event"] for e in dl.read_events(path=log)]

    assert "older" not in events, "an unverifiable segment was joined"
    assert any("could not be read" in r.getMessage() for r in caplog.records), \
        [r.getMessage() for r in caplog.records]


class TestAPartialFingerprintIsNeverTrusted:
    """`stat()` and the read fail independently, so a partial identity is the norm.

    Mode bits gate the read and not the stat, so the ordinary shape of an unreadable
    segment is "size known, contents not". Recording that as a fingerprint is worse
    than recording none: it reads as verification and an equal-size replacement
    satisfies it.
    """

    def test_a_failed_hash_records_no_identity_at_all(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        log = tmp_path / "decisions.jsonl"
        backup = log.with_name(log.name + ".1")
        backup.write_text('{"event":"older"}\n', encoding="utf-8")

        real_open = Path.open

        def _open(self, *args, **kwargs):
            if self == backup and "b" in (args[0] if args else kwargs.get("mode", "")):
                raise PermissionError("hash cannot read this")
            return real_open(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", _open)
        identity = dl._segment_identity(backup)
        assert identity == {}, f"a partial identity was recorded: {identity}"

    def test_a_one_field_claim_is_excluded_not_half_matched(
            self, tmp_path: Path, caplog) -> None:
        """Written by a rotation whose hash failed — not a legacy claim, and unverifiable."""
        log = tmp_path / "decisions.jsonl"
        backup = log.with_name(log.name + ".1")
        backup.write_text('{"event":"older"}\n', encoding="utf-8")
        size = backup.stat().st_size
        log.write_text(
            '{"event":"rotate","payload":{"segment":"decisions.jsonl.1",'
            f'"segment_bytes":{size}}}}}\n'
            '{"event":"live"}\n', encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger=dl.logger.name):
            events = [e["event"] for e in dl.read_events(path=log)]
        assert "older" not in events, events
        assert any("incomplete fingerprint" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]

    def test_the_recovery_path_survives_an_exception_that_cannot_describe_itself(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`str(exc)` runs before any transform, so a hostile `__str__` escaped `record`."""
        class Hostile(OSError):
            def __str__(self) -> str:
                raise RuntimeError("this exception will not describe itself")

        monkeypatch.setenv("CFS_DECISION_LOG", str(tmp_path / "d.jsonl"))
        monkeypatch.setattr(dl, "_append_locked",
                            lambda *a, **k: (_ for _ in ()).throw(Hostile("boom")))
        monkeypatch.setattr(dl, "_FAILURE_WARNED", False, raising=False)
        assert dl.record("gate", {"k": "v"}) is False, "the failure escaped record()"


def test_the_backup_is_verified_against_the_bytes_that_are_used(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No window between checking the segment and consuming it.

    Validation used to open the backup, fingerprint it, close it, and the read then
    reopened it by path. A replacement landing in that window was consumed silently,
    and the advisory lock does not close it: `flock` serialises this module's own
    callers, not an external `mv`. The bytes are read once and the fingerprint is
    computed from those same bytes.

    Simulated by swapping the file the instant its fingerprint is taken — under the old
    shape the swapped content was read; now the verified bytes are the returned ones.
    """
    log = tmp_path / "decisions.jsonl"
    backup = log.with_name(log.name + ".1")
    backup.write_text('{"event":"genuine"}\n', encoding="utf-8")
    dl._write_rotation_link(log, backup)
    with log.open("a", encoding="utf-8") as handle:
        handle.write('{"event":"live"}\n')

    real = dl._identity_of

    def _swap_then_fingerprint(data: bytes):
        backup.write_text('{"event":"substituted"}\n', encoding="utf-8")
        return real(data)

    monkeypatch.setattr(dl, "_identity_of", _swap_then_fingerprint)
    events = [e["event"] for e in dl.read_events(path=log)]
    assert "substituted" not in events, events
    assert events == ["genuine", "rotate", "live"], events


def test_a_segment_larger_than_any_rotation_is_not_hashed(
        tmp_path: Path, caplog) -> None:
    """The work is bounded before any read, and both paths hold a lock while doing it.

    The writer fingerprints under its own `LOCK_EX` at rotation and the reader under
    its own on the way in, so an unbounded hash is a lock held for as long as the file
    is large. A segment past the rotation threshold cannot be one this log produced.
    """
    log = tmp_path / "decisions.jsonl"
    backup = log.with_name(log.name + ".1")
    backup.write_bytes(b"x" * (dl._MAX_SEGMENT_BYTES + 1))
    log.write_text(
        '{"event":"rotate","payload":{"segment":"decisions.jsonl.1"}}\n'
        '{"event":"live"}\n', encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger=dl.logger.name):
        events = [e["event"] for e in dl.read_events(path=log)]
    assert events == ["rotate", "live"], events
    assert any("larger than any segment" in r.getMessage() for r in caplog.records), \
        [r.getMessage() for r in caplog.records]


class TestTheWriteSideDegradesVisibly:
    """The rotation's own fingerprint failure, and the silence of the legacy path."""

    def test_a_write_time_fingerprint_failure_warns_and_writes_a_bare_link(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
        """The rotation still happened, so the link is still written — without a claim.

        `_segment_identity` returning nothing is the shape of a segment that cannot be
        read at rotation time. The link must still name the segment, since the rotation
        is a fact, and it must carry no fingerprint rather than a partial one.
        """
        log = tmp_path / "decisions.jsonl"
        backup = log.with_name(log.name + ".1")
        backup.write_text('{"event":"older"}\n', encoding="utf-8")
        monkeypatch.setattr(dl, "_segment_identity", lambda segment: {})
        with caplog.at_level(logging.WARNING, logger=dl.logger.name):
            dl._write_rotation_link(log, backup)
        written = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
        assert written["event"] == "rotate"
        assert written["payload"]["segment"] == backup.name
        assert "segment_bytes" not in written["payload"], written["payload"]
        assert "segment_sha256" not in written["payload"], written["payload"]

    def test_honouring_a_link_without_a_fingerprint_is_silent(
            self, tmp_path: Path, caplog) -> None:
        """A legacy claim is the ordinary case, not an anomaly; warning on it is noise."""
        log = tmp_path / "decisions.jsonl"
        log.with_name(log.name + ".1").write_text('{"event":"older"}\n', encoding="utf-8")
        log.write_text(
            '{"event":"rotate","payload":{"segment":"decisions.jsonl.1"}}\n'
            '{"event":"live"}\n', encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger=dl.logger.name):
            events = [e["event"] for e in dl.read_events(path=log)]
        assert events == ["older", "rotate", "live"]
        assert not caplog.records, [r.getMessage() for r in caplog.records]

    def test_a_real_rotation_records_both_fingerprint_fields(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """End to end through the writer's own rotation, asserting the link's content.

        Every other test builds the link by hand. This one drives
        `record → _append_locked → _rotate_if_large → os.replace → _write_rotation_link`
        and then reads the result back, so the natural chain is exercised once.
        """
        log = tmp_path / "decisions.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        monkeypatch.setattr(dl, "_MAX_BYTES", 200)
        for i in range(6):
            assert dl.record_gate("plan-resolved", f"Gate{i}", "decision", path=log) is True

        backup = log.with_name(log.name + ".1")
        assert backup.is_file(), "the writer never rotated"
        link = next(json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
                    if '"rotate"' in line)
        assert link["payload"]["segment"] == backup.name
        assert link["payload"]["segment_bytes"] == backup.stat().st_size
        assert len(link["payload"]["segment_sha256"]) == 64, link["payload"]
        # and the trail reads across the boundary the link created
        gates = [e["payload"]["gate"] for e in dl.read_events(path=log)
                 if e["event"] == "gate"]
        assert "Gate5" in gates, gates                 # the live segment
        assert len(gates) > 1, gates                   # and at least one from the backup


class TestTheSegmentBoundIsExactAndEnforcedByTheRead:
    """Where the bound sits, and that `stat()` is not what enforces it."""

    def _linked(self, tmp_path: Path, payload: bytes) -> tuple[Path, Path]:
        log = tmp_path / "decisions.jsonl"
        backup = log.with_name(log.name + ".1")
        backup.write_bytes(payload)
        dl._write_rotation_link(log, backup)
        with log.open("a", encoding="utf-8") as handle:
            handle.write('{"event":"live"}\n')
        return log, backup

    def test_a_segment_exactly_at_the_bound_is_still_fingerprinted(
            self, tmp_path: Path) -> None:
        """`> _MAX_SEGMENT_BYTES` makes the bound inclusive; only cap+1 was covered.

        A rotated segment can legitimately reach the bound exactly — it is the rotation
        threshold plus one event — so rejecting at the bound would exclude a genuine
        segment, and only the far side of the boundary was being tested.
        """
        payload = b'{"event":"older"}\n'.ljust(dl._MAX_SEGMENT_BYTES, b" ")
        assert len(payload) == dl._MAX_SEGMENT_BYTES
        identity = dl._segment_identity(self._linked(tmp_path, payload)[1])
        assert identity, "a segment exactly at the bound was refused"
        assert identity["segment_bytes"] == dl._MAX_SEGMENT_BYTES

    def test_a_segment_one_byte_over_is_refused(self, tmp_path: Path) -> None:
        payload = b'{"event":"older"}\n'.ljust(dl._MAX_SEGMENT_BYTES + 1, b" ")
        assert dl._segment_identity(self._linked(tmp_path, payload)[1]) == {}

    def test_the_read_stops_even_when_stat_understates_the_size(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
        """`stat()` and `open()` are two observations of one path.

        A replacement landing between them makes the first a lie, so a size check alone
        would let an arbitrarily large file be hashed while a lock is held. The read
        itself is what stops, one byte past the bound.
        """
        log, backup = self._linked(tmp_path, b'{"event":"older"}\n')
        oversized = b"x" * (dl._MAX_SEGMENT_BYTES + 4096)
        backup.write_bytes(oversized)

        real_stat = Path.stat

        def _understate(self, *args, **kwargs):
            result = real_stat(self, *args, **kwargs)
            if self == backup:
                class _Small:
                    st_size = 10
                return _Small()
            return result

        monkeypatch.setattr(Path, "stat", _understate)
        with caplog.at_level(logging.WARNING, logger=dl.logger.name):
            identity = dl._segment_identity(backup)
        assert identity == {}, "an oversized segment was hashed on a stale size"
        assert any("grew past the segment bound" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]


class TestAnEventTooLargeCannotHideASegment:
    """The "plus one event" in `_MAX_SEGMENT_BYTES` has to be something the writer enforces.

    The bound is documented as the rotation threshold plus one event, and the reader
    refuses anything larger on the grounds that this log did not produce it. Nothing made
    the second half true: `record()` truncates nothing, and six of the seven typed
    wrappers forward their arguments uncapped. One oversized event therefore pushed a
    genuine segment past the bound, and the substitution check then excluded this log's
    own history — the failure that check exists to prevent, reached from the other side.
    """

    def _fill_to_one_byte_under_the_threshold(self, log: Path) -> int:
        """Land the log on exactly `_MAX_BYTES - 1`, the worst case the bound allows.

        Padded to the byte rather than left a filler line short. The segment a rotation
        produces is `(_MAX_BYTES - 1) + one event + its newline`, so this is the size at
        which the event cap has no slack — anywhere below it, an over-long event can be
        absorbed and the test would pass without the cap doing anything.
        """
        filler = '{"event":"older","schema":1,"payload":{"x":"%s"}}\n' % ("y" * 900)
        written = 0
        with log.open("w", encoding="utf-8") as handle:
            while written + len(filler) < dl._MAX_BYTES - 1:
                handle.write(filler)
                written += len(filler)
            remaining = dl._MAX_BYTES - 1 - written
            pad = '{"event":"older","schema":1,"payload":{"x":"%s"}}\n'
            handle.write(pad % ("y" * (remaining - (len(pad % "") ))))
            written = dl._MAX_BYTES - 1
        assert log.stat().st_size == dl._MAX_BYTES - 1, log.stat().st_size
        return written

    def test_a_rotated_segment_survives_an_oversized_event(self, tmp_path: Path) -> None:
        """The reproduction from the report, asserted on the events rather than the size."""
        log = tmp_path / "decisions.jsonl"
        self._fill_to_one_byte_under_the_threshold(log)
        dl.record("read", path=log, payload={"method": "m", "source": "x" * 70000})
        dl.record("live", path=log, payload={})

        backup = log.with_name(log.name + ".1")
        assert backup.is_file(), "the oversized event did not trigger the rotation"
        events = [event["event"] for event in dl.read_events(path=log)]
        assert "older" in events, (
            "a segment this log wrote itself was excluded from its own history; "
            f"backup={backup.stat().st_size} bound={dl._MAX_SEGMENT_BYTES}"
        )

    def test_the_segment_a_rotation_produces_stays_within_the_bound(self, tmp_path: Path) -> None:
        """The arithmetic, not just its consequence.

        `_MAX_SEGMENT_BYTES` is `_MAX_BYTES + 64 KiB`, and a rotation happens *before* the
        append that crossed the threshold — so the largest segment this log can produce is
        one byte under the threshold plus one whole event. Asserting the size directly
        says which of the two numbers is wrong when this fails.
        """
        log = tmp_path / "decisions.jsonl"
        self._fill_to_one_byte_under_the_threshold(log)
        dl.record("read", path=log, payload={"method": "m", "source": "x" * 70000})
        dl.record("live", path=log, payload={})

        backup = log.with_name(log.name + ".1")
        assert backup.stat().st_size <= dl._MAX_SEGMENT_BYTES, (
            f"a rotation produced a segment the reader will refuse: "
            f"{backup.stat().st_size} > {dl._MAX_SEGMENT_BYTES}"
        )

    def test_the_bounds_are_the_sizes_they_are_documented_to_be(self) -> None:
        """Pinned against literals, because every other test here derives from them.

        The cases below are built from `_MAX_EVENT_BYTES` and checked against
        `_MAX_SEGMENT_BYTES`, so shrinking both together keeps them all green while the
        documented sizes quietly stop being true. A constant a test draws its cases from
        has to be pinned to a literal somewhere, or it is testing itself.
        """
        assert dl._MAX_BYTES == 5 * 1024 * 1024, dl._MAX_BYTES
        assert dl._MAX_EVENT_BYTES == 64 * 1024, dl._MAX_EVENT_BYTES
        assert dl._MAX_SEGMENT_BYTES == 5 * 1024 * 1024 + 64 * 1024, dl._MAX_SEGMENT_BYTES

    def test_the_two_bounds_agree_on_what_one_event_may_be(self) -> None:
        """The arithmetic the segment bound rests on, asserted as a number.

        A rotation happens at the threshold, so the largest segment this log can produce
        is one byte under it plus one whole event and its newline. That stays inside
        `_MAX_SEGMENT_BYTES` exactly while `_MAX_BYTES + _MAX_EVENT_BYTES` does.

        Stated here rather than inferred from a fixture. The scenario tests below cannot
        reach it: an over-long event is replaced by a short marker, so raising the event
        cap leaves every one of them green while making a legitimate segment unreadable.
        """
        largest_segment = (dl._MAX_BYTES - 1) + dl._MAX_EVENT_BYTES + len("\n")
        assert largest_segment <= dl._MAX_SEGMENT_BYTES, (
            f"an event of {dl._MAX_EVENT_BYTES} bytes on a log of {dl._MAX_BYTES - 1} "
            f"produces a {largest_segment}-byte segment, past the reader's "
            f"{dl._MAX_SEGMENT_BYTES}-byte bound"
        )

    def test_no_event_is_ever_written_longer_than_the_cap(self, tmp_path: Path) -> None:
        """The other half: the cap has to hold for what `record()` actually writes.

        Asserted on the bytes in the file, not on a hand-built record. An earlier version
        of this test measured `_bounded_event` on a dict it built itself and then called
        `record()`, which builds its own with a real timestamp — so the assertion and the
        action were about two different events, and a one-byte-too-large cap passed.
        """
        log = tmp_path / "decisions.jsonl"
        for payload in ({"method": "m", "source": "x" * 70000},
                        {f"{'k' * 200}{n}": "v" * 400 for n in range(500)},
                        {f"key{n}": "v" * 900 for n in range(200)},
                        {"nested": {"deep": ["y" * 90000]}}):
            dl.record("read", path=log, payload=payload)
        lines = log.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 4, lines
        for line in lines:
            assert len(line.encode("utf-8")) <= dl._MAX_EVENT_BYTES, len(line.encode("utf-8"))

    def test_an_event_too_large_leaves_a_marker_rather_than_a_hole(
            self, tmp_path: Path) -> None:
        """Silence here would be the same defect one level down.

        The trail exists to be audited, so a record that could not be written has to say
        so in the place it would have occupied — dropping it leaves a gap indistinguishable
        from a decision never taken.
        """
        log = tmp_path / "decisions.jsonl"
        dl.record("read", path=log, payload={"method": "m", "source": "x" * 70000})
        events = list(dl.read_events(path=log))
        assert [event["event"] for event in events] == ["read"], events
        payload = events[0]["payload"]
        assert payload["truncated"] is True, payload
        assert payload["original_bytes"] > dl._MAX_EVENT_BYTES, payload
        assert "source" in payload["dropped_keys"], payload

    def _record_of(self, source: str) -> dict:
        """A fixed record shape, so only the payload varies between the two sides."""
        return {"schema": dl.SCHEMA_VERSION, "ts": "2026-09-15T00:00:00.000000+00:00",
                "run_id": "r" * 8, "decision_id": "", "event": "read",
                "command": "", "payload": {"source": source}}

    def test_an_event_of_exactly_the_cap_is_written_through_unchanged(self) -> None:
        """`<=` makes the cap inclusive, and only the far side of it was covered.

        An event may legitimately reach the cap exactly — that is the largest one the
        segment arithmetic is built around — so truncating at the bound would replace a
        recordable event with a marker and lose a payload for nothing. Asserted on
        `_bounded_event` directly, which is the unit that decides this.
        """
        overhead = len(dl._bounded_event(self._record_of("")).encode("utf-8"))
        line = dl._bounded_event(self._record_of("x" * (dl._MAX_EVENT_BYTES - overhead)))
        assert len(line.encode("utf-8")) == dl._MAX_EVENT_BYTES, len(line.encode("utf-8"))
        assert "truncated" not in json.loads(line)["payload"], "an event at the cap was cut"

    def test_an_event_one_byte_over_the_cap_is_marked(self) -> None:
        overhead = len(dl._bounded_event(self._record_of("")).encode("utf-8"))
        line = dl._bounded_event(self._record_of("x" * (dl._MAX_EVENT_BYTES - overhead + 1)))
        assert json.loads(line)["payload"]["truncated"] is True, line[:200]

    def test_a_record_whose_own_explanation_does_not_fit_still_fits(self) -> None:
        """The marker needs a floor of its own: key names alone can exceed the bound.

        `dropped_keys` lists what was cut, and a payload of many long keys makes that list
        larger than the cap it exists to respect — so the marker would be truncated by
        nothing and written over-long.
        """
        record_obj = self._record_of("")
        record_obj["payload"] = {f"{'k' * 900}{n}": "v" for n in range(200)}
        line = dl._bounded_event(record_obj)
        assert len(line.encode("utf-8")) <= dl._MAX_EVENT_BYTES, len(line.encode("utf-8"))
        assert json.loads(line)["payload"]["truncated"] is True, line[:200]

    def test_str_is_only_reached_for_keys_that_cannot_fail_it(self) -> None:
        """Why the marker does not guard `str(key)`, written down so it stays true.

        Listing the dropped keys calls `str()` on author-controlled keys, which looks like
        a way for one bad payload to raise out of a function whose caller promises never
        to. It is not reachable: serialisation happens first and rejects any key type
        outside this set, and `str()` cannot fail on any member of it.

        A guard was written here and then removed rather than shipped — defending a case
        that cannot occur reads as evidence that it can.
        """
        for key in (1, 1.5, True, None, "plain"):
            assert str(key), key
        line = dl._bounded_event({"schema": 1, "ts": "t", "run_id": "r", "decision_id": "",
                                  "event": "read", "command": "",
                                  "payload": {1: "a", 2.5: "b", None: "c"}})
        # `True` is deliberately not in that payload: `True == 1` in Python, so a literal
        # containing both collapses to one key and the case would silently not be tested.
        assert json.loads(line)["payload"] == {"1": "a", "2.5": "b", "null": "c"}, line

    def test_the_keys_a_marker_lists_are_named_the_way_the_record_names_them(self) -> None:
        """Raised in review: the marker said `None` and `True` where the log says `null`/`true`.

        This one *reaches the truncation branch* — an earlier version of the test above
        serialised to about a hundred bytes, so it exercised the ordinary path while
        claiming to verify the marker. An auditor greps the marker for a key name; a name
        the record would never have written fails at exactly the job the marker has.
        """
        line = dl._bounded_event({"schema": 1, "ts": "t", "run_id": "r", "decision_id": "",
                                  "event": "read", "command": "",
                                  "payload": {None: "a", True: "b", 2.5: "c",
                                              "big": "x" * 70000}})
        payload = json.loads(line)["payload"]
        assert payload["truncated"] is True, "this did not reach the truncation branch"
        assert set(payload["dropped_keys"]) == {"null", "true", "2.5", "big"}, payload

    def test_the_marker_keeps_the_fields_that_identify_the_event(self) -> None:
        """`schema`, `ts` and `run_id` are how a reader places a cut record in the trail.

        Untested: the marker copied them through a comprehension nothing asserted, so
        dropping one would have left a record that says a write was cut without saying
        which run, when, or under which schema.
        """
        line = dl._bounded_event({"schema": 99, "ts": "2026-09-15T00:00:00+00:00",
                                  "run_id": "run-abc", "decision_id": "dec-1",
                                  "event": "read", "command": "cmd",
                                  "payload": {"big": "x" * 70000}})
        kept = json.loads(line)
        assert kept["schema"] == 99, kept
        assert kept["ts"] == "2026-09-15T00:00:00+00:00", kept
        assert kept["run_id"] == "run-abc", kept
        assert kept["decision_id"] == "dec-1", kept
        assert kept["event"] == "read", kept

    @pytest.mark.parametrize("filler,label", [
        ("\u00e9", "2-byte"), ("\u4e2d", "3-byte"), ("\U0001f600", "4-byte"),
    ])
    def test_the_cap_counts_bytes_not_characters(self, filler: str, label: str) -> None:
        """Every other boundary fixture here is ASCII, where the two counts are equal.

        So swapping `_utf8_len` for `len` would pass all of them while letting an event of
        65,536 characters — up to four times that in bytes — through the cap and past the
        segment bound. Raised in review, and it is the encoding half of the same boundary
        the rest of this class pins.
        """
        record_obj = {"schema": 1, "ts": "t", "run_id": "r", "decision_id": "",
                      "event": "read", "command": "",
                      "payload": {"source": filler * 30_000}}
        line = dl._bounded_event(record_obj)
        assert len(line.encode("utf-8")) <= dl._MAX_EVENT_BYTES, (label, len(line.encode("utf-8")))

    def test_one_unserialisable_payload_costs_the_whole_run_its_trail(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Known, pre-existing, and not fixed here — pinned so the fix has a starting point.

        `record`'s catch-all latches telemetry off for the rest of the run, which is right
        for a target it has learned is unwritable and wrong for one bad payload, which says
        nothing about the target. One event with an unusable key therefore silences every
        later event too.

        Asserted as it behaves today rather than as it should, so that changing it fails
        here and the change is deliberate.
        """
        log = tmp_path / "decisions.jsonl"
        # `monkeypatch`, not an assignment with a `finally`: the module-level latch is
        # global state, and a hand-rolled restore leaves it set for every later test in
        # the session if the assertion raises before the `finally` is reached in a way
        # the fixture handles for free.
        monkeypatch.setattr(dl, "_FAILURE_WARNED", False)
        assert dl.record("before", path=log, payload={"k": "v"}) is True
        assert dl.record("bad", path=log, payload={("tuple",): "v"}) is False
        assert dl.record("after", path=log, payload={"k": "v"}) is False, (
            "the latch no longer swallows later events — if that is deliberate, "
            "this test records the old behaviour and should be updated with the fix"
        )
        assert [e["event"] for e in dl.read_events(path=log)] == ["before"]

    def test_every_typed_wrapper_is_covered_by_the_choke_point(self) -> None:
        """The count in the docstring, checked against the module rather than trusted.

        It said seven wrappers with six uncapped, taken from the report that raised the
        defect — which listed six and omitted `record_dispatch`. There are eight, seven
        of them uncapped, and the number was repeated three times before anyone counted.

        What actually matters is the second assertion: every typed wrapper reaches
        `record`, so the bound in `record` covers all of them however many there are.
        """
        tree = ast.parse(Path(dl.__file__).read_text(encoding="utf-8"))
        wrappers = {node.name: ast.unparse(node) for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name.startswith("record_")}
        assert len(wrappers) == 8, sorted(wrappers)
        for name, body in wrappers.items():
            assert "record(" in body.replace(f"{name}(", ""), (
                f"{name} does not go through `record`, so the event bound does not cover it"
            )
        capping = {name for name, body in wrappers.items() if "_gate_payload(" in body}
        assert capping == {"record_gate"}, (
            f"the set of wrappers that cap their own fields has changed: {capping}"
        )

    def test_the_marker_bounds_every_field_it_keeps_not_just_the_payload(self) -> None:
        """Raised in review, and the claim it falsified was mine.

        The marker keeps the fields that identify the event — `decision_id`, `event`,
        `command` — and all three are caller-supplied. Capping only `dropped_keys` left a
        200 KB `command` producing a 200 KB marker: the bound broken by the very record
        that exists to report the bound being broken.

        The floor written for this covered the reported field rather than the class of
        field, which is the generalisation the playbook's B10 asks for and I did not make.
        """
        record_obj = {"schema": dl.SCHEMA_VERSION, "ts": "2026-09-15T00:00:00+00:00",
                      "run_id": "r" * 8, "decision_id": "d" * 100_000,
                      "event": "e" * 100_000, "command": "c" * 200_000,
                      "payload": {"source": "x" * 70_000}}
        line = dl._bounded_event(record_obj)
        assert len(line.encode("utf-8")) <= dl._MAX_EVENT_BYTES, len(line.encode("utf-8"))
        payload = json.loads(line)["payload"]
        assert payload["truncated"] is True, payload
        # and each kept field is individually bounded, not merely small by luck
        kept = json.loads(line)
        for field in ("decision_id", "event", "command"):
            assert len(kept[field]) <= dl._GATE_TEXT_CAP, (field, len(kept[field]))

    def test_one_event_is_one_byte_of_newline_on_every_platform(self) -> None:
        """Raised in review: text mode makes the segment arithmetic platform-dependent.

        `_MAX_SEGMENT_BYTES` is the threshold plus one event plus its newline. In text
        mode Windows writes `\\r\\n` for `\\n`, so a full-size event lands one byte past the
        bound there and a segment this log wrote becomes unreadable — the original defect,
        on a platform nobody tests on.

        Every append site is opened with an explicit `newline="\\n"`, which also keeps one
        log byte-identical across platforms. That matters here beyond the arithmetic: the
        segments are fingerprinted by SHA-256.
        """
        src = Path(dl.__file__).read_text(encoding="utf-8")
        appends = re.findall(r'\.open\("a"[^)]*\)', src)
        assert appends, "no append sites found — this guard has lost its subject"
        for call in appends:
            assert 'newline="\\n"' in call, (
                f"an append site leaves newline translation on, so one event is two bytes "
                f"of newline on Windows and the segment bound is off by one per event: {call}"
            )

    def test_every_line_this_module_writes_goes_through_the_bound(self) -> None:
        """B10: the bound is a property of the log, not of one writer.

        `record` is not the only thing that appends a line — `_write_rotation_link` writes
        the `rotate` event that opens each new live segment. It was bounded incidentally,
        every field capped by hand, which is a property a reader has to re-derive and a
        future field can quietly break. The segment arithmetic assumes it of *every* line.
        """
        tree = ast.parse(Path(dl.__file__).read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name == "_bounded_event":
                continue
            body = ast.unparse(node)
            if ".write(" in body and "json.dumps(" in body:
                offenders.append(node.name)
        assert not offenders, (
            f"these write a line built with a bare json.dumps, bypassing the event "
            f"bound: {offenders}"
        )


# ---------------------------------------------------------------------------
# the append lock is bounded

def test_a_lock_held_by_someone_else_does_not_block_the_append(
        log_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """record() must return even while another process holds the append lock.

    The append lock used to be a blocking ``flock(LOCK_EX)`` -- the read lock next to
    it was already bounded. A hung sibling, or one killed without releasing, would
    freeze the caller inside instrumentation, and record()'s ``except Exception``
    cannot intercept a call that blocks rather than raises. The wait is now bounded and
    a timeout degrades to an unlocked append.
    """
    fcntl = pytest.importorskip("fcntl")
    monkeypatch.setattr(dl, "_APPEND_LOCK_TIMEOUT_SECONDS", 0.2)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = log_path.with_name(log_path.name + ".lock")

    with open(lock_path, "a", encoding="utf-8") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
        started = time.monotonic()
        wrote = dl.record("validation", {"check": "toc"}, path=log_path)
        waited = time.monotonic() - started

    assert wrote is True                       # degraded to unlocked, did not give up
    assert waited < 5.0                        # bounded by the timeout, not by the holder
    assert json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])["event"] == "validation"


def test_the_append_lock_bound_is_sane_and_below_the_read_bound() -> None:
    assert isinstance(dl._APPEND_LOCK_TIMEOUT_SECONDS, float)
    assert 0 < dl._APPEND_LOCK_TIMEOUT_SECONDS <= dl._READ_LOCK_TIMEOUT_SECONDS
