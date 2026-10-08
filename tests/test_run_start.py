"""Tests for ``cfs run-start`` and the shared run-correlation id.

A run spans many separate ``cfs`` processes, each with its own per-process ``_RUN_ID``; ``start_run``
writes one id to a shared file beside the log so every command of the run reads the same id via
``current_run_id``. These round-trip through the real file. Fail-safe: an absent, empty, or malformed
file falls back to the per-process id and never raises.
"""
from __future__ import annotations

import sys
from pathlib import Path

import os
import stat

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/studio/scripts"))

from studio import cli  # noqa: E402
from studio.commands import run_start as rs  # noqa: E402
from studio.utils import decision_log as dl  # noqa: E402


@pytest.fixture
def log_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the log (and so the run-id file) at an isolated tmp dir, not the repo's own."""
    log = tmp_path / ".cache" / "decisions.jsonl"
    monkeypatch.setenv("CFS_DECISION_LOG", str(log))
    return log


def test_current_run_id_reads_the_shared_file(log_env: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dl, "_RUN_ID", "ffffffffffff")  # a distinct per-process fallback
    rid = dl.start_run()
    assert rid is not None
    assert rid != "ffffffffffff"
    assert dl.current_run_id() == rid  # the file's id, not the process fallback


def test_absent_file_falls_back_to_the_process_id(log_env: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dl, "_RUN_ID", "abc123abc123")
    assert dl.current_run_id() == "abc123abc123"  # no start_run called → no file


def test_a_malformed_file_falls_back_fail_safe(log_env: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dl, "_RUN_ID", "abc123abc123")
    path = dl.run_id_path()
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not a valid id — has spaces and punctuation\n", encoding="utf-8")
    assert dl.current_run_id() == "abc123abc123"  # malformed → fallback, never raises


def test_invalid_utf8_file_falls_back_fail_safe(log_env: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    # A corrupted run-id file of invalid UTF-8 bytes raises UnicodeDecodeError (a ValueError, not an
    # OSError); current_run_id must still degrade to the per-process id, not crash.
    monkeypatch.setattr(dl, "_RUN_ID", "abc123abc123")
    path = dl.run_id_path()
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xfe not valid utf-8")
    assert dl.current_run_id() == "abc123abc123"


def test_start_run_writes_a_fresh_id_each_time(log_env: Path) -> None:
    first = dl.start_run()
    second = dl.start_run()
    assert first is not None
    assert second is not None
    assert first != second  # each run-start begins a clean run


def test_no_log_location_returns_none_and_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dl, "default_log_path", lambda start=None: None)
    monkeypatch.setattr(dl, "_RUN_ID", "deadbeefdead")
    assert dl.run_id_path() is None
    assert dl.start_run() is None          # nowhere to write
    assert dl.current_run_id() == "deadbeefdead"  # falls back, no crash


def test_recorded_events_carry_the_shared_run_id(log_env: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    # The crux: the WRITE path must stamp events with the shared run id (what a run-start wrote), not
    # the per-process `_RUN_ID` — otherwise readers scoped to the shared id never match the events the
    # run recorded, and the whole mechanism is inert. (An in-process stand-in for the cross-process
    # reality: run-start in one process, record in another, read in a third.)
    from studio.utils.decision_log import GateRuling  # noqa: E402  (local, mirrors other tests)
    monkeypatch.setattr(dl, "_RUN_ID", "ffffffffffff")  # a distinct per-process id it must NOT use
    rid = dl.start_run()
    dl.record_gate("plan-resolved", "GateX", "decision",
                   GateRuling(decision_key="k", value="v", provenance="plan",
                              status="resolved", why="w", cost_if_wrong="c"),
                   command="gate-log")
    gates = [e for e in dl.read_events() if e.get("event") == "gate"]
    assert gates
    assert all(e.get("run_id") == rid for e in gates)            # stamped with the shared id
    assert all(e.get("run_id") != "ffffffffffff" for e in gates)  # not the per-process fallback


def test_logging_opt_out_disables_the_run_id_file(log_env: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    # When logging is opted out, run-start must not write a run-id file and current_run_id must fall
    # back to the per-process id -- the same per-process behaviour the rest of the module keeps.
    monkeypatch.setattr(dl, "is_enabled", lambda: False)
    monkeypatch.setattr(dl, "_RUN_ID", "abc123abc123")
    assert dl.run_id_path() is None
    assert dl.start_run() is None
    assert dl.current_run_id() == "abc123abc123"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="os.mkfifo is POSIX-only")
def test_a_fifo_run_id_file_falls_back_without_blocking(log_env: Path,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    # A FIFO with no writer would make a blocking open wait forever, and because every event write
    # calls current_run_id() that would hang every command. The read bound and the OSError handler
    # both sit after the open, so only a non-blocking open plus an S_ISREG check on the descriptor
    # can catch it. Fail-safe: fall back to the per-process id, never hang, never raise.
    monkeypatch.setattr(dl, "_RUN_ID", "abc123abc123")
    path = dl.run_id_path()
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    os.mkfifo(path)  # no writer is ever opened for it
    assert dl.current_run_id() == "abc123abc123"


def test_a_directory_at_the_run_id_path_falls_back(log_env: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    # NOT a guard test for S_ISREG -- verified by mutation: this passes against the pre-fix blocking
    # open too, because `open("rb")` on a directory already raises IsADirectoryError and the existing
    # `except OSError` catches it. It is kept as a regression test for the fail-safe contract itself
    # (never raise, never hang, always fall back), which is worth pinning on its own. The FIFO case
    # above is the one that actually exercises the descriptor check.
    monkeypatch.setattr(dl, "_RUN_ID", "abc123abc123")
    path = dl.run_id_path()
    assert path is not None
    path.mkdir(parents=True, exist_ok=True)
    assert dl.current_run_id() == "abc123abc123"


def test_an_oversized_run_id_file_falls_back(log_env: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    # A huge malformed file must be rejected without being loaded whole into memory, and the read
    # must fall back to the per-process id.
    monkeypatch.setattr(dl, "_RUN_ID", "abc123abc123")
    path = dl.run_id_path()
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("a" * 5000, encoding="utf-8")  # far over the read bound
    assert dl.current_run_id() == "abc123abc123"


def test_the_read_is_never_asked_for_more_than_the_bound(log_env: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    # Review (NIT): `os.read(fd, _RUN_ID_READ_LIMIT + 1)` -> `os.read(fd, 1 << 30)` passed every
    # test, because a long file is rejected by the id regex anyway -- so nothing pinned the bound
    # itself, only its side effect. Spy on the read and assert the SIZE asked for, which is the
    # claim ("rejected without being loaded whole into memory").
    path = dl.run_id_path()
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"a" * 100_000)

    asked: list[int] = []
    real_read = os.read
    monkeypatch.setattr(os, "read", lambda fd, n: asked.append(n) or real_read(fd, n))
    dl.current_run_id()

    assert asked, "the run-id file was never read"
    assert max(asked) <= dl._RUN_ID_READ_LIMIT + 1, (
        f"read asked for {max(asked)} bytes; the bound is {dl._RUN_ID_READ_LIMIT} + 1")


def test_an_id_padded_past_the_bound_is_rejected(log_env: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    # Review (NIT): `if len(raw) <= _RUN_ID_READ_LIMIT` -> `if True` passed every test. It needs a
    # file whose value is valid *after stripping* but whose length exceeds the bound -- a real id
    # followed by whitespace padding. Bounded: the oversize check rejects it. Unbounded: `.strip()`
    # removes the padding and it is accepted, which is the hole.
    monkeypatch.setattr(dl, "_RUN_ID", "abc123abc123")
    path = dl.run_id_path()
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"a" * 64 + b"\n" + b" " * 200)

    assert dl.current_run_id() == "abc123abc123"  # the padded value must NOT be adopted


def test_an_unresolvable_home_falls_back_instead_of_raising(log_env: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    # Review (MAJOR): run_id_path() -> is_enabled() -> opt_out_sentinel_path() -> Path.home(), which
    # raises RuntimeError -- not an OSError -- when no home can be resolved (a container run as a uid
    # with no passwd entry). Both functions document that they never raise, so both must absorb it.
    monkeypatch.setattr(dl, "_RUN_ID", "abc123abc123")
    monkeypatch.delenv("HOME", raising=False)
    pwd = pytest.importorskip("pwd")  # POSIX-only; imported here so Windows can still COLLECT this file
    monkeypatch.setattr(pwd, "getpwuid",
                        lambda uid: (_ for _ in ()).throw(KeyError("uid not found")))
    assert dl.current_run_id() == "abc123abc123"   # the per-process fallback, not a traceback
    assert dl.start_run() is None                  # "nowhere to write", its documented no-op


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="O_NOFOLLOW is POSIX-only")
def test_a_symlinked_run_id_path_is_refused(log_env: Path,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    # Review (MAJOR): S_ISREG on the descriptor is not enough. For a symlink it describes the file
    # the link POINTS AT, so a link to an ordinary file passes it and the id is read from wherever
    # the link aims. Owner-only permissions do not close this: they are applied only when start_run
    # creates the directory, so an install whose .cache predates that keeps its old mode.
    monkeypatch.setattr(dl, "_RUN_ID", "abc123abc123")
    path = dl.run_id_path()
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    planted = path.parent / "planted"
    planted.write_text("deadbeefcafe\n", encoding="utf-8")
    path.symlink_to(planted)

    assert dl.current_run_id() == "abc123abc123"   # the link is refused, not followed


def test_a_write_failure_cannot_leave_a_readable_stale_id(log_env: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    # Review (MAJOR): start_run() returning None tells the caller this run uses per-process ids. If
    # the write fails AND the cleanup unlink also fails, a previous run's id stays readable on disk
    # and the next current_run_id() hands it back -- so the None is a lie and this run's events scope
    # to someone else's run. The file must be left in a state the reader refuses.
    first = dl.start_run()
    assert first is not None
    path = dl.run_id_path()
    assert path is not None

    # A scoped context, NOT monkeypatch.undo(): `log_env` takes the same monkeypatch object, so
    # undo() also reverts its CFS_DECISION_LOG and the run-id file resolves somewhere else entirely
    # -- which made an earlier version of this test pass against the unfixed code.
    with monkeypatch.context() as failing:
        failing.setattr("studio.utils.atomic_io.atomic_write_text",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
        failing.setattr(Path, "unlink",
                        lambda self, **k: (_ for _ in ()).throw(OSError("read-only")))
        assert dl.start_run() is None

    assert dl.current_run_id() != first                   # not the previous run's id
    assert dl.current_run_id() == dl.process_run_id()     # the fallback the None promised


@pytest.mark.skipif(os.name != "posix", reason="file modes are POSIX-only")
def test_the_run_id_file_and_its_directory_are_owner_only(log_env: Path) -> None:
    # Review (MAJOR): atomic_write_text's mkdir uses ambient umask with no hardening, so the run
    # marker was readable (and replaceable) by other accounts -- and replacing it alters which run
    # an event is attributed to. record() already hardens its own directory; start_run() must match.
    assert dl.start_run() is not None
    path = dl.run_id_path()
    assert path is not None
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_the_id_is_read_beside_the_log_the_caller_names(tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    # Review (MAJOR): record()/_write_rotation_link() accept an explicit path but called
    # current_run_id() with NO argument, so the sidecar was resolved from the current working
    # directory -- an event written to the log the caller named was stamped from somewhere else.
    #
    # CFS_DECISION_LOG is removed deliberately: `default_log_path` documents that the override wins
    # over `start`, so leaving it set makes both projects resolve to ONE run-id file and the
    # assertion can never fail. A first version of this test did exactly that and survived the
    # mutation; two distinct project roots is the only shape that discriminates.
    monkeypatch.setattr(dl, "_RUN_ID", "ffffffffffff")
    monkeypatch.delenv("CFS_DECISION_LOG", raising=False)
    here, there = tmp_path / "here", tmp_path / "there"
    for d in (here, there):
        d.mkdir()
    def _which(start=None, *_a, **_k):
        # `default_log_path` passes whatever it was given -- a project root on the start_run call,
        # a log FILE path on the record() call -- so match on containment, not equality.
        s = Path(start) if start else Path.cwd()
        return there if s == there or there in s.parents else here
    monkeypatch.setattr("studio.utils.files.find_studio_directory", _which)

    cwd_run = dl.start_run()        # the project we stand in
    other_run = dl.start_run(there)  # the project we name
    assert cwd_run is not None
    assert other_run is not None
    assert cwd_run != other_run   # two projects, two ids

    target = dl.default_log_path(there)
    assert target is not None
    assert there in target.parents   # resolved under the named project, not the cwd
    dl.record("routing", {"i": 1}, path=target)
    events = [e for e in dl.read_events(path=target) if e.get("event") == "routing"]
    assert events, "nothing was written to the named log"
    assert all(e.get("run_id") == other_run for e in events), (
        "the event was stamped from the cwd's run-id file, not the named log's")


def test_a_failed_write_removes_the_stale_run_id(log_env: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    # If the new id cannot be written, a previous run's id must NOT remain readable -- else this run's
    # commands would scope to the stale run. The stale file is removed so the fallback is per-process.
    from studio.utils import atomic_io  # noqa: E402
    previous = dl.start_run()
    assert previous is not None
    monkeypatch.setattr(dl, "_RUN_ID", "abc123abc123")

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("cannot replace")

    monkeypatch.setattr(atomic_io, "atomic_write_text", _boom)
    assert dl.start_run() is None                         # the write failed
    assert dl.current_run_id() == "abc123abc123"          # stale id gone -> per-process fallback


def test_cmd_run_start_exits_zero(log_env: Path) -> None:
    assert rs.cmd_run_start([]) == 0  # setup, never a gate


def test_cmd_run_start_exits_zero_with_no_log(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dl, "default_log_path", lambda start=None: None)
    assert rs.cmd_run_start([]) == 0  # no log location is reported, still exit 0


def test_cmd_run_start_rejects_a_bad_argument(log_env: Path) -> None:
    # A malformed argument must emit the standard structured error and exit 2, not crash past the
    # CLI handler (routed through ui.parse_args_or_json_error, not a raw parse_args).
    assert rs.cmd_run_start(["--no-such-flag"]) == 2


class TestRegistration:
    def test_handler_is_mapped(self) -> None:
        assert cli._COMMAND_HANDLERS["run-start"] == "_cmd_run_start"

    def test_handler_reference_is_kept_for_dead_code_scanners(self) -> None:
        assert cli._cmd_run_start in cli._COMMAND_HANDLER_REFERENCES

    def test_command_has_a_description(self) -> None:
        assert "run-start" in cli._COMMAND_DESCRIPTIONS
