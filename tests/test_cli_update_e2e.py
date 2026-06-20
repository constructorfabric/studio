"""Public CLI e2e coverage for exact `update` command."""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.cli import main
from studio.utils import toml_utils


def _run_main(argv: list[str], *, cwd: Path) -> tuple[int, str, str]:
    from studio.utils.ui import is_json_mode, set_json_mode

    stdout = io.StringIO()
    stderr = io.StringIO()
    old_cwd = Path.cwd()
    saved_json_mode = is_json_mode()
    try:
        set_json_mode(False)
        os.chdir(cwd)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(argv)
        return exit_code, stdout.getvalue(), stderr.getvalue()
    finally:
        set_json_mode(saved_json_mode)
        os.chdir(old_cwd)


def _snapshot_tree(root: Path) -> dict[str, tuple[str, bytes | None]]:
    snapshot: dict[str, tuple[str, bytes | None]] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            snapshot[rel] = ("dir", None)
        elif path.is_file():
            snapshot[rel] = ("file", path.read_bytes())
    return snapshot


def _bootstrap_update_project(root: Path, adapter_rel: str = "adapter") -> Path:
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / "AGENTS.md").write_text(
        f'<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "{adapter_rel}"\n```\n<!-- /@cf:root-agents -->\n',
        encoding="utf-8",
    )
    adapter = root / adapter_rel
    (adapter / ".core").mkdir(parents=True, exist_ok=True)
    (adapter / ".gen").mkdir(parents=True, exist_ok=True)
    (adapter / "config").mkdir(parents=True, exist_ok=True)
    (adapter / "config" / "AGENTS.md").write_text("# Test adapter\n", encoding="utf-8")
    toml_utils.dump({"version": "1.0", "project_root": "..", "kits": {}}, adapter / "config" / "core.toml")
    return adapter


class TestCLIUpdateE2E(unittest.TestCase):
    def test_update_without_project_root_errors_without_writing(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(["--json", "update"], cwd=root)
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("No project root found", payload["message"])

    def test_update_dry_run_option_matrix_is_non_mutating(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_update_project(root)
            core_toml_path = adapter / "config" / "core.toml"
            cache_dir = Path(td) / "cache"
            cache_dir.mkdir()
            before = _snapshot_tree(root)
            core_before = core_toml_path.read_text(encoding="utf-8")

            with patch("studio.commands.update.CACHE_DIR", cache_dir):
                exit_code, stdout, stderr = _run_main(
                    [
                        "--json",
                        "update",
                        "--project-root",
                        str(root),
                        "--dry-run",
                        "--with-kits",
                        "yes",
                        "--migrate-from-cypilot",
                        "no",
                        "--update-legacy-studio",
                        "no",
                        "--no-interactive",
                        "--yes",
                    ],
                    cwd=root,
                )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            self.assertEqual(core_toml_path.read_text(encoding="utf-8"), core_before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "PASS")
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["actions"]["core_toml_metadata"], "dry_run")
            self.assertEqual(payload["actions"]["gitignore"], "dry_run")
            self.assertEqual(payload["actions"]["kits"], {})
            self.assertFalse((root / ".gitignore").exists())

    def test_update_missing_cache_returns_error_without_writing(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_update_project(root)
            before = _snapshot_tree(root)
            missing_cache = Path(td) / "missing-cache"

            with patch("studio.commands.update.CACHE_DIR", missing_cache):
                exit_code, stdout, stderr = _run_main(
                    ["--json", "update", "--project-root", str(root), "--migrate-from-cypilot", "no", "--update-legacy-studio", "no"],
                    cwd=root,
                )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("Cache not found", payload["message"])


if __name__ == "__main__":
    unittest.main()
