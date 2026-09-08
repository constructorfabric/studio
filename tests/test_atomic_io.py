"""Tests for the shared atomic-write and file-locking primitives (atomic_io.py).

See constructorfabric/studio#104.
"""

from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from studio.utils.atomic_io import atomic_write_text, with_file_lock


class TestAtomicWriteText:
    def test_writes_content(self, tmp_path: Path):
        target = tmp_path / "sub" / "file.txt"
        atomic_write_text(target, "hello")
        assert target.read_text(encoding="utf-8") == "hello"

    def test_creates_parent_directories(self, tmp_path: Path):
        target = tmp_path / "a" / "b" / "c.txt"
        atomic_write_text(target, "x")
        assert target.is_file()

    def test_overwrites_existing_content(self, tmp_path: Path):
        target = tmp_path / "file.txt"
        atomic_write_text(target, "first")
        atomic_write_text(target, "second")
        assert target.read_text(encoding="utf-8") == "second"

    def test_leaves_no_temp_file_behind(self, tmp_path: Path):
        target = tmp_path / "file.txt"
        atomic_write_text(target, "content")
        names = [p.name for p in tmp_path.iterdir()]
        assert names == ["file.txt"]

    def test_cleans_up_the_temp_file_when_replace_fails(self, tmp_path: Path, monkeypatch):
        """A failure between the temp write and the final os.replace (disk
        full, a permissions change mid-write) must not leave an orphaned
        temp file behind, and must propagate the original error rather
        than swallowing it."""
        import os as os_module

        target = tmp_path / "file.txt"

        def _raise_replace(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(os_module, "replace", _raise_replace)
        with pytest.raises(OSError, match="disk full"):
            atomic_write_text(target, "content")

        assert not target.exists()
        assert list(tmp_path.iterdir()) == []

    def test_concurrent_writes_to_the_same_target_do_not_collide(self, tmp_path: Path):
        """CodeRabbit PR #110: a PID-based temp filename is shared by every
        call within one process -- two threads writing the same target
        could each pick up the other's temp file mid-write, causing a
        FileNotFoundError on os.replace or one call silently publishing
        the other's content. A unique temp name per call (tempfile.mkstemp)
        closes that window: each thread's write completes cleanly, and the
        final content is one call's payload in full, never a torn mix."""
        import threading

        target = tmp_path / "file.txt"
        barrier = threading.Barrier(2)
        errors = []
        payloads = ["a" * 200_000, "b" * 200_000]

        def _write(content):
            barrier.wait()
            try:
                atomic_write_text(target, content)
            except OSError as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_write, args=(p,)) for p in payloads]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert target.read_text(encoding="utf-8") in payloads


class TestWithFileLock:
    def test_runs_and_returns_the_callback_result(self, tmp_path: Path):
        lock_path = tmp_path / "x.lock"
        assert with_file_lock(lock_path, lambda: 42) == 42

    def test_creates_parent_directory_for_the_lock_file(self, tmp_path: Path):
        lock_path = tmp_path / "nested" / "x.lock"
        with_file_lock(lock_path, lambda: None)
        assert lock_path.parent.is_dir()

    def test_runs_unlocked_when_fcntl_is_unavailable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Mirrors decision_log.py's own test for the identical fallback
        shape: a platform without fcntl (e.g. Windows) still runs the
        callback, just without cross-process serialization."""
        real_import = builtins.__import__

        def _no_fcntl(name, *args, **kwargs):
            if name == "fcntl":
                raise ImportError("fcntl unavailable on this platform")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_fcntl)
        lock_path = tmp_path / "x.lock"
        assert with_file_lock(lock_path, lambda: "ran") == "ran"
        assert not lock_path.exists()  # never created -- the fallback never opens it

    def test_timeout_none_still_blocks_forever_by_default(self, tmp_path: Path):
        """constructorfabric/studio#136 (round-4 review, Major): adding a
        ``timeout`` parameter must not change any existing caller's
        behavior. ``None`` (the default, and every caller's behavior before
        this parameter existed) takes the original always-blocking
        ``LOCK_EX`` path, not the poll loop -- confirmed here by patching
        ``fcntl.flock`` to observe it is called without ``LOCK_NB``."""
        import fcntl

        calls = []
        real_flock = fcntl.flock

        def _spy(fd, operation):
            calls.append(operation)
            return real_flock(fd, operation)

        import unittest.mock as mock

        lock_path = tmp_path / "x.lock"
        with mock.patch("fcntl.flock", side_effect=_spy):
            assert with_file_lock(lock_path, lambda: "ran") == "ran"
        assert calls == [fcntl.LOCK_EX]
        assert not any(op & fcntl.LOCK_NB for op in calls)

    def test_succeeds_within_a_generous_timeout_when_uncontended(self, tmp_path: Path):
        """The normal (uncontended) case must not be affected by passing a
        bounded timeout at all -- it should acquire immediately and return
        the callback's real result, not time out just because a timeout
        was given."""
        lock_path = tmp_path / "x.lock"
        assert with_file_lock(lock_path, lambda: 99, timeout=5.0) == 99

    def test_raises_timeout_error_when_the_lock_is_held_by_someone_else(self, tmp_path: Path):
        """Simulates "someone else has this locked and won't release it":
        a separate open file description on the same lock path holds an
        exclusive flock (flock locks are scoped to the open file
        description, not the process, so this genuinely contends with
        with_file_lock's own flock call even from the same process/thread
        -- no second thread or process is needed to prove the contention
        is real). Bounded to a small timeout so this test itself cannot
        hang even if the fix under test were broken."""
        import fcntl

        lock_path = tmp_path / "x.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        holder = open(lock_path, "a", encoding="utf-8")
        try:
            fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
            with pytest.raises(TimeoutError):
                with_file_lock(lock_path, lambda: "should not run", timeout=0.2)
        finally:
            fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
            holder.close()

    def test_callback_never_runs_on_a_timeout(self, tmp_path: Path):
        """A caller must never see its read-modify-write cycle start
        without actually holding the lock -- a TimeoutError means fn() was
        never invoked at all, not that it ran unsynchronized."""
        import fcntl

        lock_path = tmp_path / "x.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        holder = open(lock_path, "a", encoding="utf-8")
        ran = []
        try:
            fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
            with pytest.raises(TimeoutError):
                with_file_lock(lock_path, lambda: ran.append(1), timeout=0.2)
        finally:
            fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
            holder.close()
        assert ran == []
