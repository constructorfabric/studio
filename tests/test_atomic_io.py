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

    def test_a_non_contention_oserror_propagates_immediately_not_as_a_generic_timeout(
        self, tmp_path: Path, monkeypatch,
    ):
        """Real gap caught in review (constructorfabric/studio#136, round-4,
        Major): the bounded-timeout poll loop caught any OSError from
        flock(LOCK_NB), not just the errno flock actually uses for "someone
        else holds this lock right now" (EAGAIN/EWOULDBLOCK). A real
        filesystem/descriptor failure (EINVAL, EBADF, ENOLCK, ...) would
        otherwise be silently retried for the full timeout and then
        reported as a generic "timed out waiting for the lock", discarding
        the actual errno that would have explained it. Mocks fcntl.flock to
        always raise EINVAL and asserts it propagates on the very first
        call -- immediately, not after polling for the (generous) timeout
        below."""
        import errno
        import fcntl

        def _raise_einval(*_a, **_k):
            raise OSError(errno.EINVAL, "invalid argument")

        monkeypatch.setattr(fcntl, "flock", _raise_einval)
        lock_path = tmp_path / "x.lock"
        with pytest.raises(OSError) as exc_info:
            with_file_lock(lock_path, lambda: "should not run", timeout=30.0)
        assert exc_info.value.errno == errno.EINVAL
        assert not isinstance(exc_info.value, TimeoutError)

    def test_eagain_from_flock_still_retries_as_ordinary_contention(
        self, tmp_path: Path, monkeypatch,
    ):
        """The other half of the fix above: EAGAIN/EWOULDBLOCK (real lock
        contention) must still be retried, not misclassified as a fatal
        error alongside EINVAL/EBADF/ENOLCK. Mocks fcntl.flock to raise
        EAGAIN exactly twice, then succeed -- proving the poll loop
        actually retries this specific errno rather than raising on first
        sight of any OSError."""
        import errno
        import fcntl

        real_flock = fcntl.flock
        calls = []

        def _flaky(fd, op):
            calls.append(op)
            if len(calls) <= 2 and op & fcntl.LOCK_NB:
                raise OSError(errno.EAGAIN, "resource temporarily unavailable")
            return real_flock(fd, op)

        monkeypatch.setattr(fcntl, "flock", _flaky)
        lock_path = tmp_path / "x.lock"
        assert with_file_lock(lock_path, lambda: "ok", timeout=5.0) == "ok"
        assert len(calls) == 3  # two simulated-contention retries, then a real success


class TestTheFailurePathDoesNotBecomeTheFailure:
    """Cleanup runs when the write already went wrong. It must not take over from it."""

    def test_a_cleanup_error_does_not_replace_the_original_exception(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`unlink` inside an `except` block can raise too -- a read-only directory, a
        vanished mount -- and when it did, its exception propagated instead of the one
        that explained what actually happened. The caller got the janitor's error."""
        from studio.utils import atomic_io

        def _replace_boom(_src, _dst):            # the real failure
            raise RuntimeError("disk full")

        def _unlink_boom(_self, **_kwargs):       # the janitor tripping over it
            raise PermissionError("read-only directory")

        monkeypatch.setattr(atomic_io.os, "replace", _replace_boom)
        monkeypatch.setattr(Path, "unlink", _unlink_boom)

        with pytest.raises(RuntimeError, match="disk full"):
            atomic_io.atomic_write_text(tmp_path / "out.txt", "content")

    def test_a_descriptor_is_not_leaked_when_fdopen_fails(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`os.fdopen` takes ownership of the descriptor only once it succeeds.

        When it raises -- an unknown encoding, memory pressure -- nobody had wrapped the
        descriptor and nobody closed it, so it leaked for the life of the process.
        """
        import os as _os

        from studio.utils import atomic_io

        closed: list[int] = []
        real_close = _os.close

        def _fdopen_boom(_fd, *_a, **_k):
            raise OSError("cannot wrap the descriptor")

        def _tracking_close(fd):
            closed.append(fd)
            return real_close(fd)

        monkeypatch.setattr(atomic_io.os, "fdopen", _fdopen_boom)
        monkeypatch.setattr(atomic_io.os, "close", _tracking_close)

        with pytest.raises(OSError, match="cannot wrap"):
            atomic_io.atomic_write_text(tmp_path / "out.txt", "content")

        assert closed, "the descriptor fdopen never took ownership of must still be closed"
        # The branch does two things, and the test only watched one of them: the temp
        # file `mkstemp` created must not survive the failure either (#236 review).
        assert not list(tmp_path.glob("**/*.tmp")), "the temp file was left behind"

    def test_a_successful_write_is_untouched(self, tmp_path: Path) -> None:
        """The restructured path must still do the ordinary thing."""
        target = tmp_path / "nested" / "out.txt"
        atomic_write_text(target, "hello")

        assert target.read_text(encoding="utf-8") == "hello"
        assert not list(tmp_path.glob("**/*.tmp"))          # no temp file left behind


class TestAnInterruptDuringTheWriteStillCleansUp:
    """`except Exception` skips `KeyboardInterrupt`, which is not an `Exception`.

    The cleanup blocks exist so that a failed write leaves neither a leaked
    descriptor nor a stray `.tmp` beside the target. Ctrl-C is the most ordinary
    way for a write to fail, and it was the one way that skipped both
    (#236 review).
    """

    def test_an_interrupt_in_fdopen_closes_the_descriptor_and_removes_the_temp(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from studio.utils import atomic_io

        real_close = atomic_io.os.close
        closed: list[int] = []

        def _interrupted(_fd, *_a, **_k):
            raise KeyboardInterrupt

        def _tracking_close(fd):
            closed.append(fd)
            return real_close(fd)

        monkeypatch.setattr(atomic_io.os, "fdopen", _interrupted)
        monkeypatch.setattr(atomic_io.os, "close", _tracking_close)

        with pytest.raises(KeyboardInterrupt):
            atomic_io.atomic_write_text(tmp_path / "out.txt", "content")

        assert closed, "an interrupt must not leak the descriptor fdopen never took"
        assert not list(tmp_path.glob("**/*.tmp")), "an interrupt must not strand the temp file"

    def test_an_interrupt_during_the_write_removes_the_temp(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from studio.utils import atomic_io

        def _interrupted(*_a, **_k):
            raise KeyboardInterrupt

        monkeypatch.setattr(atomic_io.os, "replace", _interrupted)

        with pytest.raises(KeyboardInterrupt):
            atomic_io.atomic_write_text(tmp_path / "out.txt", "content")

        assert not list(tmp_path.glob("**/*.tmp")), "an interrupt must not strand the temp file"

    def test_the_interrupt_itself_reaches_the_caller_unchanged(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cleanup is added; how the process dies is not changed."""
        from studio.utils import atomic_io

        sentinel = KeyboardInterrupt("user pressed ctrl-c")

        def _interrupted(*_a, **_k):
            raise sentinel

        monkeypatch.setattr(atomic_io.os, "replace", _interrupted)

        with pytest.raises(KeyboardInterrupt) as caught:
            atomic_io.atomic_write_text(tmp_path / "out.txt", "content")

        assert caught.value is sentinel


class TestTheTolerantJsonRead:
    """One definition of what a tolerant read absorbs, for both cache readers.

    `doc_index._read_cache_file` and `okf.load_okf_manifest` kept the same
    try/except by hand, and it drifted: `UnicodeDecodeError` was named in one
    and missed in the other (#236 review).
    """

    def test_valid_json_is_returned(self, tmp_path: Path) -> None:
        from studio.utils.atomic_io import read_json_tolerantly

        path = tmp_path / "cache.json"
        path.write_text('{"a": 1}', encoding="utf-8")

        def _unreachable(_exc):
            raise AssertionError("a readable file must not report a failure")

        assert read_json_tolerantly(path, on_unreadable=_unreachable) == {"a": 1}

    @pytest.mark.parametrize(
        "write, expected",
        [
            (lambda p: p.write_bytes(b"\xff\xfe not utf-8"), UnicodeDecodeError),
            (lambda p: p.write_text("{not json", encoding="utf-8"), ValueError),
            (lambda p: None, OSError),          # the file is never created
        ],
        ids=["invalid-utf8", "invalid-json", "unreadable-path"],
    )
    def test_an_unreadable_file_is_reported_and_read_as_none(
            self, tmp_path: Path, write, expected) -> None:
        from studio.utils.atomic_io import read_json_tolerantly

        path = tmp_path / "cache.json"
        write(path)
        seen: list[Exception] = []

        assert read_json_tolerantly(path, on_unreadable=seen.append) is None
        assert len(seen) == 1
        assert isinstance(seen[0], expected)

    def test_invalid_utf8_is_the_case_the_two_readers_disagreed_on(
            self, tmp_path: Path) -> None:
        """`UnicodeDecodeError` is a ValueError subclass, so neither sibling catches it.

        Named directly because this is the exception whose omission was the
        original bug: `OSError` does not cover it and neither does
        `json.JSONDecodeError`.
        """
        import json

        from studio.utils.atomic_io import read_json_tolerantly

        path = tmp_path / "cache.json"
        path.write_bytes(b"\xff\xfe")
        seen: list[Exception] = []

        assert read_json_tolerantly(path, on_unreadable=seen.append) is None
        assert not isinstance(seen[0], (OSError, json.JSONDecodeError))
