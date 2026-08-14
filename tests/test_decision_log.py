"""Tests for the local decision/outcome log (``studio.utils.decision_log``).

Covers the rigor the design note calls for: local-only (no socket), opt-out silences
everything, fail-safe (never raises), no-project no-op, rotation, redaction, and the
decision_id correlation that chains one decision's events.
"""

from __future__ import annotations

import json
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
