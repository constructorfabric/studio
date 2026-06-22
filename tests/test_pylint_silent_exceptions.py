"""Integration tests for the local silent-exception Pylint checker."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHONPATH = os.pathsep.join([
    str(REPO_ROOT / "src"),
    str(REPO_ROOT / "skills" / "studio" / "scripts"),
])


def _run_pylint(code: str) -> subprocess.CompletedProcess[str]:
    with TemporaryDirectory() as td:
        target = Path(td) / "sample.py"
        target.write_text(textwrap.dedent(code), encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = PYTHONPATH
        return subprocess.run(
            [
                "pipx",
                "run",
                "--spec",
                "pylint",
                "pylint",
                "--score=n",
                "--disable=all",
                "--enable=silent-exception-swallowed",
                str(target),
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )


class TestSilentExceptionSwallowedChecker(unittest.TestCase):
    """Exercise the local Pylint checker on temporary files."""

    def test_flags_except_pass(self) -> None:
        result = _run_pylint(
            """
            def run():
                try:
                    work()
                except OSError:
                    pass
            """
        )
        self.assertIn("silent-exception-swallowed", result.stdout)

    def test_flags_sentinel_return(self) -> None:
        result = _run_pylint(
            """
            def run():
                try:
                    work()
                except OSError:
                    return None
            """
        )
        self.assertIn("silent-exception-swallowed", result.stdout)

    def test_flags_assignment_then_empty_dict_return(self) -> None:
        result = _run_pylint(
            """
            def run():
                try:
                    work()
                except OSError:
                    data = {}
                    return data
            """
        )
        self.assertIn("silent-exception-swallowed", result.stdout)

    def test_allows_visible_error_reporting(self) -> None:
        result = _run_pylint(
            """
            class Logger:
                def warning(self, message, exc):
                    return message, exc

            logger = Logger()

            def run():
                try:
                    work()
                except OSError as exc:
                    logger.warning("fallback", exc)
                    return None
            """
        )
        self.assertNotIn("silent-exception-swallowed", result.stdout)

    def test_allows_printed_warning_then_fallback(self) -> None:
        result = _run_pylint(
            """
            def run():
                try:
                    work()
                except OSError:
                    print("warning: fallback")
                    return {}
            """
        )
        self.assertNotIn("silent-exception-swallowed", result.stdout)

    def test_allows_keyboard_interrupt_short_circuit(self) -> None:
        result = _run_pylint(
            """
            def run():
                try:
                    work()
                except KeyboardInterrupt:
                    return False
            """
        )
        self.assertNotIn("silent-exception-swallowed", result.stdout)


if __name__ == "__main__":
    unittest.main()
