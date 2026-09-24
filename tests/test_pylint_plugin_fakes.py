"""Tests for the shared harness the pylint-plugin test families run through."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tests import pylint_plugin_fakes
from tests.pylint_plugin_fakes import run_pylint, subprocess_env


def _user_site(env: dict) -> str:
    """Ask a real child process where it would look for user-installed packages."""
    result = subprocess.run(
        [sys.executable, "-c", "import site; print(site.getusersitepackages())"],
        env=env, capture_output=True, text=True,
        # `check=False` and raised here, because `CalledProcessError` does not put the
        # captured streams in its message: a failing probe reported only its exit code and
        # threw away the traceback that says why. Raised in review.
        check=False,
        # Bounded because an unbounded call does not fail a test, it stops the suite --
        # which reads as CI being broken rather than as this check failing. Generous
        # against a cold interpreter start on a loaded runner, and still finite.
        timeout=60,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"the probe interpreter exited {result.returncode}\n"
            f"stdout: {result.stdout.strip()!r}\nstderr: {result.stderr.strip()!r}"
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
        captured = pylint_plugin_fakes._REAL_HOME
        if captured is None:
            # A supported case, not a failure: `$HOME` was unset when this module was
            # imported, so there is nothing to restore and the helper *removes* `HOME` from
            # the child rather than passing the fixture's temp one through. The first
            # version of this test asserted `_REAL_HOME` was truthy and so failed on the
            # very behaviour the helper documents. Raised in review.
            assert "HOME" not in subprocess_env(), sorted(subprocess_env())[:5]
            return
        assert not captured.startswith(str(_temp_home_root())), (
            f"_REAL_HOME is a pytest temp directory ({captured}), "
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
        # Skipped when nothing was captured — see the unset-`$HOME` branch above; asserting
        # a prefix of `None` raises a TypeError rather than saying what went wrong.
        if pylint_plugin_fakes._REAL_HOME is not None:
            assert where.startswith(pylint_plugin_fakes._REAL_HOME), (
                f"expected a path under {pylint_plugin_fakes._REAL_HOME}, got {where}"
            )

    def test_a_redirected_user_site_base_does_not_survive(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`$HOME` is not the only thing that decides where a child looks.

        `PYTHONUSERBASE` moves the user-site base to any path regardless of `$HOME`, and
        `PYTHONNOUSERSITE` switches user-site off altogether — either one reproduces the
        same unimportable-`pipx` failure with `$HOME` perfectly restored. Raised in review,
        along with the observation that made the earlier test weak: `getusersitepackages()`
        computes its answer whether or not user-site is enabled, so asserting the path alone
        passed under `PYTHONNOUSERSITE=1`.

        Behavioural: the redirect is exported, and the child is asked where it would look.
        """
        import os as _os  # noqa: PLC0415

        elsewhere = "/tmp/not-the-real-user-base"
        # Set in the *ambient* environment, which is the only way the helper can be asked
        # to drop them. A first version built a local dict and asserted the names were
        # absent from `subprocess_env()` — where they had never been — so removing the drop
        # left it green. That is the same vacuity as the `$HOME` test this file already
        # records, found the same way, by mutation.
        monkeypatch.setenv("PYTHONUSERBASE", elsewhere)
        monkeypatch.setenv("PYTHONNOUSERSITE", "1")

        # The control: the redirect really does move where a child looks.
        assert _user_site(dict(_os.environ)).startswith(elsewhere), (
            "PYTHONUSERBASE no longer redirects user-site, so this guard measures nothing"
        )

        # And through the helper it is gone, so the child resolves against the real home.
        cleaned = subprocess_env()
        assert "PYTHONUSERBASE" not in cleaned, sorted(cleaned)[:5]
        assert "PYTHONNOUSERSITE" not in cleaned, sorted(cleaned)[:5]
        if pylint_plugin_fakes._REAL_HOME is not None:
            assert _user_site(cleaned).startswith(pylint_plugin_fakes._REAL_HOME), \
                _user_site(cleaned)

    def test_home_cannot_be_passed_as_an_extra(self) -> None:
        """A silent override would undo the one thing this function does.

        No caller needs it, and the failure it would produce is the fingerprint-free one
        this helper exists to prevent — so it is refused where it is visible. Raised in
        review.
        """
        with pytest.raises(ValueError, match="restores HOME"):
            subprocess_env(HOME="/tmp/somewhere")

    def test_extra_values_are_applied_on_top(self) -> None:
        """`PYTHONPATH` is what every caller passes, so it must survive the restore."""
        assert subprocess_env(PYTHONPATH="/x/y")["PYTHONPATH"] == "/x/y"


class TestTheSharedLauncher:
    """`run_pylint` itself, which nothing here exercised.

    Every test above calls `subprocess_env`, so the module's claim to cover "the shared
    harness" held for half of it: the launcher that builds the temp file, the `pipx` argv,
    the working directory and the timeout was never imported. Raised in review — and the
    timeout is the part that matters most, because none of the four copies this replaced
    carried one and a hung `pipx` stops the suite rather than failing a test.

    The subprocess is intercepted rather than run. What is asserted is how the call is
    *composed*; that it works end to end is what the four pylint families already prove,
    forty-two times, on every run.
    """

    def test_the_call_is_composed_the_way_the_families_need_it(
            self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # Run from somewhere else first, or the `cwd` assertion cannot tell `REPO_ROOT`
        # from `Path.cwd()` -- they are the same value when pytest runs from the repository
        # root, so swapping one for the other left this green. Found by mutation.
        monkeypatch.chdir(tmp_path)
        seen: dict = {}

        def _capture(argv, **kwargs):
            seen["argv"] = argv
            seen.update(kwargs)
            return subprocess.CompletedProcess(argv, 0, "", "")

        monkeypatch.setattr(pylint_plugin_fakes.subprocess, "run", _capture)
        run_pylint("x = 1\n", enable="stdout-bypass", relative_path="pkg/sample.py")

        argv = seen["argv"]
        assert argv[:5] == ["pipx", "run", "--spec", "pylint", "pylint"], argv
        assert "--enable=stdout-bypass" in argv, argv
        assert argv[-1].endswith("pkg/sample.py"), argv[-1]
        # Bounded, and that is the reason this launcher exists rather than four copies.
        assert seen["timeout"] == 600, seen.get("timeout")
        assert seen["cwd"] == pylint_plugin_fakes.REPO_ROOT, seen.get("cwd")
        assert seen["check"] is False, "a non-zero exit is the caller's to interpret"
        # And it goes through the environment helper, not a raw `os.environ`.
        assert seen["env"]["PYTHONPATH"] == pylint_plugin_fakes.PLUGIN_PYTHONPATH
        assert "PYTHONUSERBASE" not in seen["env"]

    def test_the_source_is_dedented_before_it_is_written(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Callers pass indented triple-quoted blocks; pylint would see an IndentationError."""
        written: dict = {}

        def _capture(argv, **kwargs):
            written["text"] = pathlib.Path(argv[-1]).read_text(encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, "", "")

        monkeypatch.setattr(pylint_plugin_fakes.subprocess, "run", _capture)
        run_pylint("\n        import os\n        print(os)\n", enable="stdout-bypass")

        assert written["text"].lstrip("\n").startswith("import os"), repr(written["text"])
