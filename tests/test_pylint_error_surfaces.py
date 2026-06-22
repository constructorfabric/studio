"""Integration tests for the user-facing error surface Pylint checker."""

from __future__ import annotations

import os
import subprocess
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
                "--enable=user-facing-error-without-log",
                str(target),
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )


class TestErrorSurfacesChecker(unittest.TestCase):
    """Exercise user-facing error surfacing requirements."""

    def test_flags_ui_error_without_logger_in_except(self) -> None:
        result = _run_pylint(
            """
            class UI:
                def error(self, message):
                    return message

            ui = UI()

            def run():
                try:
                    work()
                except OSError:
                    ui.error("failed")
            """
        )
        self.assertIn("user-facing-error-without-log", result.stdout)

    def test_flags_ui_result_error_without_logger_in_except(self) -> None:
        result = _run_pylint(
            """
            class UI:
                def result(self, payload):
                    return payload

            ui = UI()

            def run():
                try:
                    work()
                except OSError:
                    ui.result({"status": "ERROR", "message": "failed"})
            """
        )
        self.assertIn("user-facing-error-without-log", result.stdout)

    def test_allows_ui_error_with_logger_exception(self) -> None:
        result = _run_pylint(
            """
            class UI:
                def error(self, message):
                    return message

            class Logger:
                def exception(self, message):
                    return message

            ui = UI()
            logger = Logger()

            def run():
                try:
                    work()
                except OSError:
                    logger.exception("failed to run")
                    ui.error("failed")
            """
        )
        self.assertNotIn("user-facing-error-without-log", result.stdout)

    def test_ignores_ui_info_outside_error_surface(self) -> None:
        result = _run_pylint(
            """
            class UI:
                def info(self, message):
                    return message

            ui = UI()

            def run():
                try:
                    work()
                except OSError:
                    ui.info("retrying")
            """
        )
        self.assertNotIn("user-facing-error-without-log", result.stdout)


if __name__ == "__main__":
    unittest.main()
