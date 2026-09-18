"""Tests for the shared harness the pylint-plugin test families run through."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tests import pylint_plugin_fakes
from tests.pylint_plugin_fakes import subprocess_env


def _user_site(env: dict) -> str:
    """Ask a real child process where it would look for user-installed packages."""
    result = subprocess.run(
        [sys.executable, "-c", "import site; print(site.getusersitepackages())"],
        env=env, capture_output=True, text=True, check=True,
        # Bounded because an unbounded call does not fail a test, it stops the suite --
        # which reads as CI being broken rather than as this check failing. Generous
        # against a cold interpreter start on a loaded runner, and still finite.
        timeout=60,
    )
    return result.stdout.strip()


def _temp_home_root() -> Path:
    """The directory every per-test `$HOME` is created under.

    `conftest.py` builds each one with `tmp_path_factory.mktemp("cfs_home")`, so they are
    siblings and this is their shared parent. Derived from the moved `$HOME` rather than
    requested as `tmp_path_factory`, which is session-scoped and does not belong in a
    function-scoped test, and rather than `tmp_path`, which names only *this* test's
    directory -- the distinction these tests exist to make.
    """
    return Path(os.environ["HOME"]).parent


class TestASubprocessCanStillFindUserInstalledTools:
    """The autouse `$HOME` move left every pylint subprocess unable to import `pipx`.

    These run a real child and ask it where its user site-packages directory is, rather
    than comparing two dictionaries — the dictionaries were never in doubt, and what broke
    was where a child resolved its imports from.

    Comparisons are against the **root** all the per-test homes sit under, not against this
    test's own. That distinction is the whole test: the autouse fixture calls `mktemp` per
    test, so every test gets a *different* temp home, and an assertion that merely says
    "not this test's home" passes just as happily when the captured home came from another
    test's. The first version of this file asserted exactly that and was vacuous.

    What the mutation actually pins: reading `$HOME` at call time instead of import time —
    the late-capture bug, and the one shape this can realistically regress into — fails
    `test_the_shared_env_restores_the_real_home`, and independently breaks 10 of the real
    pylint-family tests. A `_REAL_HOME` set to some arbitrary unrelated path is not caught
    and is not guarded against; nothing in the module can produce one.
    """

    def test_the_captured_home_is_the_real_one_not_a_temp_directory(self) -> None:
        """`_REAL_HOME` is read at import time, which is collection — before any fixture.

        If the module were ever first imported from inside a test body instead, it would
        capture the moved `$HOME` and the restore below would be a no-op that still looked
        correct. Anchored to the shared root so *any* test's temp home fails this, not just
        the one this test happens to have been given.
        """
        assert pylint_plugin_fakes._REAL_HOME, "no $HOME was captured at import"
        assert not pylint_plugin_fakes._REAL_HOME.startswith(str(_temp_home_root())), (
            f"_REAL_HOME is a pytest temp directory ({pylint_plugin_fakes._REAL_HOME}), "
            "so it was captured after the autouse fixture had already moved $HOME"
        )

    def test_the_moved_home_is_what_breaks_it(self) -> None:
        """The control. Without this the fix below could be proving nothing.

        `conftest.py` has already moved `$HOME` by the time any test body runs, so a plain
        `dict(os.environ)` sends the child looking for packages inside a temp directory
        where nothing is installed. On a machine whose tooling is a `pip install --user`
        install — `pipx` among it — that is unimportable, and the tests that shell out
        through `pipx` fail with empty output and no hint of why.
        """
        moved = os.environ["HOME"]
        assert moved.startswith(tempfile.gettempdir()), (
            f"the autouse fixture no longer moves $HOME somewhere temporary ({moved}), "
            "so this guard is measuring nothing"
        )
        assert _user_site(dict(os.environ)).startswith(moved)

    def test_the_shared_env_restores_the_real_home(self) -> None:
        """And the fix: a child started through the helper resolves against the real one."""
        where = _user_site(subprocess_env())

        assert not where.startswith(str(_temp_home_root())), (
            f"the subprocess still resolves its packages under a temp $HOME: {where}"
        )
        # Positive half: it is the real home specifically, not merely somewhere else.
        assert where.startswith(pylint_plugin_fakes._REAL_HOME), (
            f"expected a path under {pylint_plugin_fakes._REAL_HOME}, got {where}"
        )

    def test_extra_values_are_applied_on_top(self) -> None:
        """`PYTHONPATH` is what every caller passes, so it must survive the restore."""
        assert subprocess_env(PYTHONPATH="/x/y")["PYTHONPATH"] == "/x/y"
