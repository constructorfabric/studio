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

import pytest

from tests import conftest

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


def _globals():
    """The three module globals the fixture saves, as one comparable tuple."""
    from studio.utils import context as context_module
    return (
        context_module._global_context,
        context_module._workspace_upgrade_attempted,
        context_module._workspace_upgrade_error,
    )


class TestTheFixtureRestoresWhatATestInstalled:
    """The same claim as the pair above, without depending on who runs first.

    The pair's own docstring is honest that it only catches a missing fixture when
    both tests land on the same xdist worker, which a full run gives it and this
    file on its own does not. Stepping the fixture's generator directly removes the
    scheduler from the question: setup, the mutation a test would make, teardown and
    the assertion all happen inside one test, so it holds however the suite is
    sliced (review, #256).

    Both are kept. The pair is the end-to-end statement and reads as the
    documentation of the bug; these are the ones that cannot be scheduled away.
    """

    @staticmethod
    def _fixture_body():
        """The undecorated generator behind the `_isolate_studio_context` fixture.

        `pytest.fixture` returns a wrapper that raises if called directly, and
        records the function it wrapped on `__wrapped__` -- the same attribute
        `functools.wraps` sets, which is how `inspect.signature` and every
        fixture-introspecting tool reaches it. Stable, but private enough that it
        deserves to fail by saying so: if a pytest release stops setting it, the
        assertion names the cause instead of leaving an `AttributeError` on a test
        that looks like it is about contexts (review, #256).
        """
        fixture = conftest._isolate_studio_context
        body = getattr(fixture, "__wrapped__", None)
        assert body is not None, (
            "pytest.fixture no longer records the wrapped function on __wrapped__; "
            "this test needs another way to reach the fixture's body"
        )
        return body

    @classmethod
    def _drive(cls, mutate):
        """Run the fixture around `mutate`, returning the globals afterwards."""
        generator = cls._fixture_body()()
        next(generator)          # setup: snapshot
        mutate()                 # what a test does
        with pytest.raises(StopIteration):
            next(generator)      # teardown: restore
        return _globals()

    def test_a_context_a_test_installed_is_gone_afterwards(self) -> None:
        before = _globals()

        after = self._drive(lambda: set_context(MagicMock(spec=StudioContext)))

        assert after == before

    def test_the_upgrade_flags_travel_with_the_value_they_belong_to(self) -> None:
        """Restoring the context without them would leave it marked as upgraded."""
        from studio.utils import context as context_module

        def _mutate():
            set_context(MagicMock(spec=StudioContext))
            context_module._workspace_upgrade_attempted = True
            context_module._workspace_upgrade_error = "something went wrong"

        before = _globals()
        after = self._drive(_mutate)

        assert after == before

    def test_a_test_that_changed_nothing_is_left_alone(self) -> None:
        before = _globals()

        after = self._drive(lambda: None)

        assert after == before


class TestThisFileDrivesTheRegisteredFixture:
    """`tests/` is a package, so pytest registers the conftest as `tests.conftest`.

    A bare `import conftest` compiles the same file into a *separate* module object,
    and the fixture reached through it is a different function from the one pytest
    runs. The tests above would then keep passing while the real fixture was
    renamed, unregistered or stripped of `autouse=True` (review, #256).
    """

    def test_the_conftest_imported_here_is_the_registered_plugin(self, request) -> None:
        own_file = Path(conftest.__file__).resolve()
        registered = [
            plugin for plugin in request.config.pluginmanager.get_plugins()
            if getattr(plugin, "__file__", None)
            and Path(plugin.__file__).resolve() == own_file
        ]

        assert registered, "pytest has no plugin registered for tests/conftest.py"
        assert registered[0] is conftest, (
            "this file imported a second copy of conftest.py; the fixture driven by "
            "the tests above is then not the one pytest runs"
        )

    def test_the_fixture_driven_here_is_the_registered_one(self, request) -> None:
        own_file = Path(conftest.__file__).resolve()
        registered = next(
            plugin for plugin in request.config.pluginmanager.get_plugins()
            if getattr(plugin, "__file__", None)
            and Path(plugin.__file__).resolve() == own_file
        )

        assert (registered._isolate_studio_context
                is conftest._isolate_studio_context)

    def test_the_fixture_is_still_autouse(self, request) -> None:
        """Driving its body proves the body works, not that anything runs it.

        Read off the fixture manager's **autouse-name index** for this node, not a marker on
        the function: since pytest 9.1 `pytest.fixture` returns a `FixtureFunctionDefinition`
        and no longer sets `_pytestfixturefunction`, and a `FixtureDef` has carried no
        `autouse` attribute since that information moved into the index. `_getautousenames`
        returns the autouse fixtures applicable to a node, so this asserts the slightly
        stronger property that the fixture is autouse **for this test**, not merely autouse
        somewhere.
        """
        assert "_isolate_studio_context" in request._fixturemanager._arg2fixturedefs, (
            "_isolate_studio_context is not a registered fixture"
        )
        autouse_here = set(request._fixturemanager._getautousenames(request.node))
        assert "_isolate_studio_context" in autouse_here, (
            "_isolate_studio_context is registered but not autouse for this test, so no "
            "test is actually protected by it"
        )
