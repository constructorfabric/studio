"""Public CLI router smoke tests."""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.cli import main


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
            rc = main(argv)
        return rc, stdout.getvalue(), stderr.getvalue()
    finally:
        set_json_mode(saved_json_mode)
        os.chdir(old_cwd)


class TestCLIRouterE2E(unittest.TestCase):
    def test_help_json_contract(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            rc, stdout, stderr = _run_main(["--json", "--help"], cwd=root)

            self.assertEqual(rc, 0)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["usage"], "cfs <command> [options]")
            self.assertIn("validate", payload["commands"])
            self.assertIn("Workspace", payload["sections"])

    def test_unknown_command_errors_cleanly(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            rc, stdout, stderr = _run_main(["--json", "definitely-missing"], cwd=root)

            self.assertEqual(rc, 1)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("Unknown command", payload["message"])
            self.assertIn("validate", payload["available"])

    def test_self_check_alias_routes_to_validate_kits(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            alias_rc, alias_stdout, alias_stderr = _run_main(["--json", "self-check"], cwd=root)
            canonical_rc, canonical_stdout, canonical_stderr = _run_main(
                ["--json", "validate-kits"],
                cwd=root,
            )

            self.assertEqual(alias_rc, canonical_rc)
            self.assertEqual(alias_stderr, "")
            self.assertEqual(canonical_stderr, "")
            self.assertEqual(json.loads(alias_stdout), json.loads(canonical_stdout))


if __name__ == "__main__":
    unittest.main()
