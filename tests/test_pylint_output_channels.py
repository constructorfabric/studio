"""Integration tests for the local output-channel Pylint checker."""

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


def _run_pylint(code: str, *, relative_path: str = "sample.py") -> subprocess.CompletedProcess[str]:
    with TemporaryDirectory() as td:
        target = Path(td) / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
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
                "--enable=stdout-bypass,stderr-bypass",
                str(target),
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )


class TestOutputChannelsChecker(unittest.TestCase):
    """Exercise the local Pylint checker on temporary files."""

    def test_flags_plain_print_to_stdout(self) -> None:
        result = _run_pylint(
            """
            def run():
                print("hello")
            """
        )
        self.assertIn("stdout-bypass", result.stdout)

    def test_flags_sys_stdout_write(self) -> None:
        result = _run_pylint(
            """
            import sys

            def run():
                sys.stdout.write("hello\\n")
            """
        )
        self.assertIn("stdout-bypass", result.stdout)

    def test_flags_print_to_stderr(self) -> None:
        result = _run_pylint(
            """
            import sys

            def run():
                print("bad", file=sys.stderr)
            """
        )
        self.assertIn("stderr-bypass", result.stdout)

    def test_flags_subprocess_passthrough_to_stderr(self) -> None:
        result = _run_pylint(
            """
            import subprocess
            import sys

            def run():
                subprocess.run(["echo", "hello"], stderr=sys.stderr, check=False)
            """
        )
        self.assertIn("stderr-bypass", result.stdout)

    def test_allows_logger_usage(self) -> None:
        result = _run_pylint(
            """
            import logging

            logger = logging.getLogger(__name__)

            def run():
                logger.warning("bad")
            """
        )
        self.assertNotIn("stdout-bypass", result.stdout)
        self.assertNotIn("stderr-bypass", result.stdout)

    def test_allows_stdout_inside_ui_module(self) -> None:
        result = _run_pylint(
            """
            import sys

            def render():
                sys.stdout.write("ok\\n")
            """,
            relative_path="skills/studio/scripts/studio/utils/ui.py",
        )
        self.assertNotIn("stdout-bypass", result.stdout)

    def test_allows_stdout_inside_proxy_module(self) -> None:
        result = _run_pylint(
            """
            import subprocess
            import sys

            def render():
                print("ok")
                sys.stdout.write("still ok\\n")
                subprocess.run(["echo", "hello"], stdout=sys.stdout, check=False)
            """,
            relative_path="src/studio_proxy/cli.py",
        )
        self.assertNotIn("stdout-bypass", result.stdout)

    def test_still_forbids_stderr_inside_ui_module(self) -> None:
        result = _run_pylint(
            """
            import sys

            def render():
                sys.stderr.write("bad\\n")
            """,
            relative_path="skills/studio/scripts/studio/utils/ui.py",
        )
        self.assertIn("stderr-bypass", result.stdout)

    def test_still_forbids_stderr_inside_proxy_module(self) -> None:
        result = _run_pylint(
            """
            import sys

            def render():
                sys.stderr.write("bad\\n")
            """,
            relative_path="src/studio_proxy/cli.py",
        )
        self.assertIn("stderr-bypass", result.stdout)


if __name__ == "__main__":
    unittest.main()
