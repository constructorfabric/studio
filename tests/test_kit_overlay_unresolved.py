import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

from _test_helpers import bootstrap_test_project as _bootstrap_project

_FIXTURES = Path(__file__).parent / "fixtures" / "kits" / "overlay"
_SLUG = "team-sdlc"


def _copy(td: Path, name: str, dest_name: str = "") -> Path:
    dest = td / (dest_name or name)
    shutil.copytree(_FIXTURES / name, dest)
    return dest


def _run_cli(func, argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = func(argv)
    return rc, json.loads(buf.getvalue())


def _assert_overlay_message(test: unittest.TestCase, text: str) -> None:
    test.assertIn("#180", text)
    test.assertIn("base resolution", text)


class _ProjectCase(unittest.TestCase):
    def setUp(self):
        from studio.utils.ui import set_json_mode

        set_json_mode(True)
        self.addCleanup(set_json_mode, False)
        self._cwd = os.getcwd()
        self.addCleanup(os.chdir, self._cwd)
        self._td = TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.td = Path(self._td.name)
        self.root = self.td / "proj"
        self.adapter = _bootstrap_project(self.root)
        self.core = self.adapter / "config" / "core.toml"
        os.chdir(self.root)


class TestOverlayInstallRejected(_ProjectCase):
    def test_register_mode_rejected_without_writes(self):
        from studio.commands.kit import cmd_kit_install

        kit = _copy(self.td, "extends-full")
        before = self.core.read_bytes()
        rc, out = _run_cli(cmd_kit_install, ["--path", str(kit), "--install-mode", "register"])
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["status"], "FAIL")
        _assert_overlay_message(self, json.dumps(out))
        self.assertEqual(self.core.read_bytes(), before)
        self.assertFalse((self.adapter / "config" / "kits" / _SLUG).exists())

    def test_copy_mode_rejected_without_writes(self):
        from studio.commands.kit import cmd_kit_install

        kit = _copy(self.td, "extends-full")
        before = self.core.read_bytes()
        rc, out = _run_cli(cmd_kit_install, ["--path", str(kit), "--install-mode", "copy"])
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["status"], "FAIL")
        _assert_overlay_message(self, json.dumps(out))
        self.assertEqual(self.core.read_bytes(), before)
        self.assertFalse((self.adapter / "config" / "kits" / _SLUG).exists())

    def test_install_kit_api_rejected_in_both_modes(self):
        from studio.commands.kit import install_kit

        kit = _copy(self.td, "extends-full")
        before = self.core.read_bytes()
        for mode in ("copy", "register"):
            result = install_kit(kit, self.adapter, _SLUG, install_mode=mode)
            self.assertEqual(result["status"], "FAIL")
            _assert_overlay_message(self, " ".join(result["errors"]))
        self.assertEqual(self.core.read_bytes(), before)
        self.assertFalse((self.adapter / "config" / "kits" / _SLUG).exists())

    def test_git_source_rejected_without_writes(self):
        from urllib.parse import quote

        from studio.commands.kit import cmd_kit_install

        repo = _copy(self.td, "extends-full", "repo")
        for args in (
            ("init", "-q"),
            ("config", "user.email", "test@example.com"),
            ("config", "user.name", "Test User"),
            ("add", "."),
            ("commit", "-q", "-m", "initial"),
            ("tag", "v1"),
        ):
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
        before = self.core.read_bytes()
        source = "git/" + quote(repo.as_uri(), safe="")
        rc, out = _run_cli(cmd_kit_install, [source, "--version", "v1"])
        self.assertNotEqual(rc, 0)
        self.assertEqual(out["status"], "FAIL")
        _assert_overlay_message(self, json.dumps(out))
        self.assertEqual(self.core.read_bytes(), before)
        self.assertFalse((self.adapter / "config" / "kits" / _SLUG).exists())

    def test_control_without_extends_still_installs(self):
        from studio.commands.kit import cmd_kit_install

        kit = _copy(self.td, "plain")
        rc, out = _run_cli(cmd_kit_install, ["--path", str(kit), "--install-mode", "copy"])
        self.assertEqual(rc, 0, out)
        self.assertEqual(out["status"], "PASS")
        self.assertTrue((self.adapter / "config" / "kits" / _SLUG / "SKILL.md").is_file())


class TestOverlayUpdateRejected(_ProjectCase):
    def test_update_to_overlay_source_rejected_without_writes(self):
        from studio.commands.kit import cmd_kit_install, cmd_kit_update

        plain = _copy(self.td, "plain")
        rc, _out = _run_cli(cmd_kit_install, ["--path", str(plain), "--install-mode", "copy"])
        self.assertEqual(rc, 0)
        installed = self.adapter / "config" / "kits" / _SLUG / "SKILL.md"
        before_core = self.core.read_bytes()
        before_skill = installed.read_bytes()
        overlay = _copy(self.td, "extends-full")
        rc, out = _run_cli(cmd_kit_update, ["--path", str(overlay), "--force"])
        self.assertNotEqual(rc, 0)
        _assert_overlay_message(self, json.dumps(out))
        self.assertEqual(self.core.read_bytes(), before_core)
        self.assertEqual(installed.read_bytes(), before_skill)

    def test_first_install_via_update_rejected_without_writes(self):
        from studio.commands.kit import cmd_kit_update

        overlay = _copy(self.td, "extends-full")
        before = self.core.read_bytes()
        rc, out = _run_cli(cmd_kit_update, ["--path", str(overlay)])
        self.assertNotEqual(rc, 0)
        _assert_overlay_message(self, json.dumps(out))
        self.assertEqual(self.core.read_bytes(), before)
        self.assertFalse((self.adapter / "config" / "kits" / _SLUG).exists())

    def test_control_update_without_extends_still_works(self):
        from studio.commands.kit import cmd_kit_install, cmd_kit_update

        plain = _copy(self.td, "plain")
        rc, _out = _run_cli(cmd_kit_install, ["--path", str(plain), "--install-mode", "copy"])
        self.assertEqual(rc, 0)
        rc, out = _run_cli(cmd_kit_update, ["--path", str(plain), "--force"])
        self.assertEqual(rc, 0, out)


class TestOverlayValidateKitsPath(unittest.TestCase):
    def test_overlay_not_reported_as_valid(self):
        from studio.commands.validate_kits import _validate_kit_by_path

        with TemporaryDirectory() as td:
            kit = _copy(Path(td), "extends-full")
            rc, report = _validate_kit_by_path(kit, verbose=True)
        self.assertNotEqual(rc, 0)
        _assert_overlay_message(self, json.dumps(report, default=str))

    def test_control_without_extends_not_flagged(self):
        from studio.commands.validate_kits import _validate_kit_by_path

        with TemporaryDirectory() as td:
            kit = _copy(Path(td), "plain")
            _rc, report = _validate_kit_by_path(kit, verbose=True)
        self.assertNotIn("#180", json.dumps(report, default=str))


class TestOverlayNormalizeStillWorks(unittest.TestCase):
    def test_normalize_overlay_preserves_declaration(self):
        from studio.utils.kit_model import load_kit_model, normalize_kit_source

        with TemporaryDirectory() as td:
            kit = _copy(Path(td), "extends-full")
            self.assertIsNotNone(load_kit_model(kit).extends)
            _model, text = normalize_kit_source(kit, "manifest")
        self.assertIn("[kits.extends]", text)


if __name__ == "__main__":
    unittest.main()
