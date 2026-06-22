"""Integration tests for the studio/proxy import-boundary Pylint checker."""

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


def _run_pylint(code: str, *, relative_path: str) -> subprocess.CompletedProcess[str]:
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
                "--enable=proxy-imports-studio,studio-imports-proxy",
                str(target),
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )


class TestImportBoundariesChecker(unittest.TestCase):
    """Exercise import-boundary enforcement between proxy and studio packages."""

    def test_flags_proxy_importing_studio_with_import(self) -> None:
        result = _run_pylint(
            """
            import studio.utils.files
            """,
            relative_path="src/studio_proxy/resolve.py",
        )
        self.assertIn("proxy-imports-studio", result.stdout)

    def test_flags_proxy_importing_studio_with_from_import(self) -> None:
        result = _run_pylint(
            """
            from studio.utils.files import load_text
            """,
            relative_path="src/studio_proxy/resolve.py",
        )
        self.assertIn("proxy-imports-studio", result.stdout)

    def test_flags_studio_importing_proxy(self) -> None:
        result = _run_pylint(
            """
            from studio_proxy.resolve import resolve_skill
            """,
            relative_path="skills/studio/scripts/studio/commands/sample.py",
        )
        self.assertIn("studio-imports-proxy", result.stdout)

    def test_allows_proxy_internal_imports(self) -> None:
        result = _run_pylint(
            """
            from studio_proxy.cli import main
            """,
            relative_path="src/studio_proxy/resolve.py",
        )
        self.assertNotIn("proxy-imports-studio", result.stdout)
        self.assertNotIn("studio-imports-proxy", result.stdout)

    def test_allows_studio_internal_imports(self) -> None:
        result = _run_pylint(
            """
            from studio.utils.files import load_text
            """,
            relative_path="skills/studio/scripts/studio/commands/sample.py",
        )
        self.assertNotIn("proxy-imports-studio", result.stdout)
        self.assertNotIn("studio-imports-proxy", result.stdout)


if __name__ == "__main__":
    unittest.main()
