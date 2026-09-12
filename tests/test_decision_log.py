"""Tests for the local decision/outcome log (``studio.utils.decision_log``).

Covers the rigor the design note calls for: local-only (no socket), opt-out silences
everything, fail-safe (never raises), no-project no-op, rotation, redaction, and the
decision_id correlation that chains one decision's events.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
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
