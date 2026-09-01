"""Filesystem primitives shared by every local cache/bundle writer in this
package: atomic replace-on-write, and cross-process exclusive locking
around a read-modify-write cycle.

Extracted once a second consumer (``okf.py``, alongside ``doc_index.py``)
needed the exact same two behaviors, rather than reimplementing them a
second time. Mirrors the fallback shape ``decision_log.py``'s own
``_append_locked`` already established for this codebase (exclusive
``fcntl`` lock where available, unlocked elsewhere) -- kept separate from
that module since it also bakes in log-rotation behavior these two callers
don't need.

@cpt-algo:cpt-studio-algo-traceability-validation-atomic-io:p1
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")


# @cpt-begin:cpt-studio-algo-traceability-validation-atomic-io:p1:inst-atomic-write
def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write ``content`` to ``path`` atomically: temp file + ``os.replace``,
    so a reader racing a concurrent writer sees either the old complete
    file or the new complete one, never a torn/partial write.

    The temp file gets a unique name per call (``tempfile.mkstemp``), not
    just per-process (a PID-based name): two threads in the same process
    writing the same target would otherwise share one temp path and race
    each other's write/replace/cleanup.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as tmp_fh:
            tmp_fh.write(content)
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
# @cpt-end:cpt-studio-algo-traceability-validation-atomic-io:p1:inst-atomic-write


# @cpt-begin:cpt-studio-algo-traceability-validation-atomic-io:p1:inst-atomic-lock
def with_file_lock(lock_path: Path, fn: Callable[[], T]) -> T:
    """Run ``fn()`` -- a read-modify-write cycle -- under an exclusive lock
    on ``lock_path``, serializing concurrent callers so two overlapping
    cycles against the same underlying resource can't each read the same
    base state, mutate their own part, and have whichever writes last
    silently discard the other's update.

    An exclusive ``fcntl`` lock where available (POSIX), otherwise runs
    ``fn()`` unlocked (e.g. Windows) -- the atomicity of any individual
    write is :func:`atomic_write_text`'s separate guarantee; only the
    cross-call serialization is best-effort here.
    """
    try:
        import fcntl  # pylint: disable=import-outside-toplevel
    except ImportError:
        return fn()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a", encoding="utf-8") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        return fn()
# @cpt-end:cpt-studio-algo-traceability-validation-atomic-io:p1:inst-atomic-lock
