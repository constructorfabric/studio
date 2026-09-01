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
