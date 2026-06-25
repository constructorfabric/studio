"""Integration tests for the studio/proxy import-boundary Pylint checker."""

from __future__ import annotations

import os
import subprocess
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.pylint_plugin_fakes import Import, ImportFrom, Name, load_plugin_module, set_root

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

    def test_helper_functions_cover_paths_and_import_name_extraction(self) -> None:
        module = load_plugin_module("import_boundaries")
        proxy_import = set_root(Import([("studio.utils.files", None)]), r"src\studio_proxy\resolve.py")
        studio_import = set_root(ImportFrom("studio_proxy.resolve"), "skills/studio/scripts/studio/commands/sample.py")
        absolute_proxy_import = set_root(
            Import([("studio_proxy.stderr", None)]),
            "/tmp/some-worktree/src/studio_proxy/resolve.py",
        )

        self.assertEqual(module._module_path(proxy_import), "src/studio_proxy/resolve.py")
        self.assertTrue(module._is_proxy_module(proxy_import))
        self.assertFalse(module._is_studio_module(proxy_import))
        self.assertTrue(module._is_studio_module(studio_import))
        self.assertTrue(module._is_proxy_module(absolute_proxy_import))
        self.assertFalse(module._is_studio_module(absolute_proxy_import))
        self.assertEqual(module._import_name(proxy_import), "studio.utils.files")
        self.assertEqual(module._import_name(studio_import), "studio_proxy.resolve")
        self.assertIsNone(module._import_name(Import([])))
        self.assertIsNone(module._import_name(Name("not_import")))
        self.assertTrue(module._imports_proxy("studio_proxy.cli"))
        self.assertFalse(module._imports_proxy("studio.cli"))
        self.assertTrue(module._imports_studio("studio.utils.ui"))
        self.assertFalse(module._imports_studio("studio_proxy.resolve"))

    def test_checker_and_register_paths(self) -> None:
        module = load_plugin_module("import_boundaries")
        checker = module.ImportBoundariesChecker(linter=None)
        messages: list[str] = []
        checker.add_message = lambda msgid, node=None: messages.append(msgid)

        checker.visit_import(set_root(Import([("studio.utils.files", None)]), "src/studio_proxy/resolve.py"))
        checker.visit_importfrom(
            set_root(ImportFrom("studio_proxy.resolve"), "skills/studio/scripts/studio/commands/sample.py")
        )
        checker.visit_import(set_root(Import([("studio_proxy.cli", None)]), "src/studio_proxy/resolve.py"))

        self.assertEqual(messages, ["proxy-imports-studio", "studio-imports-proxy"])

        existing = type("Existing", (), {"name": module.ImportBoundariesChecker.name})()
        linter = type(
            "Linter",
            (),
            {"_checkers": {"astroid": [existing]}, "register_checker": lambda self, checker: (_ for _ in ()).throw(AssertionError)},
        )()
        module.register(linter)

        recorded: list[object] = []
        fresh_linter = type(
            "Linter",
            (),
            {"_checkers": {}, "register_checker": lambda self, checker: recorded.append(checker)},
        )()
        module.register(fresh_linter)
        self.assertEqual(len(recorded), 1)
        self.assertIsInstance(recorded[0], module.ImportBoundariesChecker)

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
