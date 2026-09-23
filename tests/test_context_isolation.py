"""The context singleton must not travel between tests.

`studio.utils.context` keeps `_global_context` at module level. Without the autouse fixture in
`conftest.py`, a test that sets it hands it to every later test in the same worker.

The instance that did the damage came from
`tests/test_narrowed_except_coverage.py::TestCliAgentsInjectionError`, which builds
`StudioContext.__new__(StudioContext)` — a real instance with no fields set — patches
`StudioContext.load` to return it, and runs the CLI. The patch is undone when its `with` block
exits; the context the CLI installed in the singleton is not. Any later test in that worker
then reads a `StudioContext` that has no `project_root`, which is exactly what
`tests/test_toc.py::TestCmdValidateToc` did once #242 added a `ctx.project_root` read to the
TOC severity path. The leak had been harmless since May because nothing on that path read the
field.

These two tests are deliberately ordered and deliberately coupled: the first leaves a context
behind on purpose, and the second asserts it did not arrive. They live in a file of their own,
rather than beside tests that merely happen to use a context, so nothing reorders them.

What the pair depends on, written down because it is easy to be misled by it: the second test
only catches a missing fixture when it runs after the first *on the same xdist worker*. In a
full `make test` run that holds — with the fixture disabled it was the suite's only failure,
five runs out of five, and deselecting the first test made the second pass. Running this file on
its own under `-n 6` is the case where it does not hold: two tests and six idle workers are
handed to different workers, and the second then passes whatever `conftest.py` says. A green
run of this file by itself is not evidence that the isolation fixture survives; run the suite.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from studio.utils.context import StudioContext, get_context, set_context


def test_a_sets_a_context_and_leaves_it_behind() -> None:
    """Deliberate contamination, so the next test has something to catch."""
    set_context(MagicMock(spec=StudioContext))
    assert get_context() is not None


def test_b_does_not_inherit_it() -> None:
    """The assertion that fails when the isolation fixture is removed.

    `get_context()` is a process-wide singleton; the test above set it and never cleared it.
    Seeing `None` here means each test starts from the module's own initial state rather than
    from whatever ran before it.
    """
    assert get_context() is None, (
        "a context set by an earlier test is still installed — the autouse isolation fixture "
        "in conftest.py is missing or no longer restores studio.utils.context._global_context"
    )
