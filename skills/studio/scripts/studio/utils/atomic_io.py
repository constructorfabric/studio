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

import errno
import os
import tempfile
import time
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")

#: Poll interval (seconds) for the bounded-``timeout`` path in
#: :func:`with_file_lock`. ``fcntl.flock`` has no native timeout, so a
#: bounded wait is implemented as a non-blocking-lock poll loop instead;
#: this interval trades a little latency (worst case, one interval's worth
#: of extra wait past the real unlock moment) for not busy-spinning.
_LOCK_POLL_INTERVAL_SECONDS = 0.05


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
def with_file_lock(lock_path: Path, fn: Callable[[], T], *, timeout: float | None = None) -> T:
    """Run ``fn()`` -- a read-modify-write cycle -- under an exclusive lock
    on ``lock_path``, serializing concurrent callers so two overlapping
    cycles against the same underlying resource can't each read the same
    base state, mutate their own part, and have whichever writes last
    silently discard the other's update.

    An exclusive ``fcntl`` lock where available (POSIX), otherwise runs
    ``fn()`` unlocked (e.g. Windows) -- the atomicity of any individual
    write is :func:`atomic_write_text`'s separate guarantee; only the
    cross-call serialization is best-effort here.

    ``timeout``, in seconds, bounds how long this call will wait to
    acquire the lock. ``None`` (the default) blocks forever, exactly as
    before this parameter existed -- every existing caller
    (:func:`studio.utils.doc_index.annotate_section_summary`,
    :func:`studio.utils.doc_index.record_tier2_escalation`'s prior
    behavior, :func:`studio.utils.okf`'s manifest writer) keeps its
    original block-forever semantics unless it explicitly opts into a
    bound. A real timeout is implemented as a non-blocking (``LOCK_NB``)
    poll loop rather than a native ``flock`` timeout, since POSIX
    ``flock`` has none: on the last poll before the deadline that still
    fails to acquire the lock, this raises :class:`TimeoutError` instead
    of running ``fn()`` at all -- the caller never starts its
    read-modify-write cycle without actually holding the lock. Only an
    ``OSError`` whose ``errno`` is ``EAGAIN``/``EWOULDBLOCK`` (what
    ``flock`` actually raises for "someone else holds this lock right
    now") is treated as ordinary contention and retried; any other
    ``OSError`` (e.g. ``EINVAL``, ``EBADF``, ``ENOLCK`` -- a real
    filesystem or descriptor problem, not contention) propagates
    immediately instead of being silently polled away into a generic,
    less informative ``TimeoutError`` (constructorfabric/studio#136,
    round-4 review, Major).

    constructorfabric/studio#136 (round-4 review, Major):
    :func:`studio.utils.doc_index.record_tier2_escalation` used to enter
    this function's original always-blocking path unconditionally, so a
    live process holding the lock indefinitely (hung, deadlocked, or just
    very slow) would block the entire ``route_query``/``cfs retrieve``
    call forever before Tier 2 could return anything. It now passes a
    bounded ``timeout`` and treats :class:`TimeoutError` as a third,
    distinctly-logged "could not persist" case (see its own docstring).
    """
    try:
        import fcntl  # pylint: disable=import-outside-toplevel
    except ImportError:
        return fn()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a", encoding="utf-8") as lock_fh:
        if timeout is None:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        else:
            _acquire_lock_bounded(lock_fh, lock_path, timeout)
        return fn()
# @cpt-end:cpt-studio-algo-traceability-validation-atomic-io:p1:inst-atomic-lock


# @cpt-begin:cpt-studio-algo-traceability-validation-atomic-io:p1:inst-atomic-lock-poll
def _acquire_lock_bounded(lock_fh, lock_path: Path, timeout: float) -> None:
    """Poll for the exclusive lock on ``lock_fh`` until acquired or ``timeout``
    seconds pass, raising :class:`TimeoutError` on the latter.

    This errno check is scoped to POSIX ``flock(2)`` semantics only (same
    platform boundary as the ``ImportError``-based Windows fallback in
    :func:`with_file_lock`) -- not a claim these are the exhaustive
    contention errnos on every platform.

    Only the errno ``flock`` actually uses to signal "someone else holds
    this lock right now" (``EAGAIN``/``EWOULDBLOCK``) is worth retrying
    (constructorfabric/studio#136, round-4 review, Major). Any other
    ``OSError`` (``EINVAL``: not a lockable descriptor, ``EBADF``: bad fd,
    ``ENOLCK``: no lock resources on this filesystem, ...) is a real,
    distinct failure -- polling it for the full timeout and then raising a
    generic "timed out waiting for the lock" would misdiagnose a
    filesystem/descriptor problem as ordinary contention and discard the
    actual errno that would have explained it. ``EWOULDBLOCK`` and
    ``EAGAIN`` are the same integer on Linux but distinct names for
    portability -- checking both covers a platform where they differ.
    """
    import fcntl  # pylint: disable=import-outside-toplevel

    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                raise
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"timed out after {timeout:.1f}s waiting for the lock at {lock_path}"
                ) from exc
            time.sleep(_LOCK_POLL_INTERVAL_SECONDS)
# @cpt-end:cpt-studio-algo-traceability-validation-atomic-io:p1:inst-atomic-lock-poll
