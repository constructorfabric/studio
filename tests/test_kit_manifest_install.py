"""Tests for manifest-driven kit installation (WP3).

Covers install_kit_with_manifest(), manifest detection in install_kit(),
resource copying, template variable resolution, and core.toml resource bindings.
"""
from __future__ import annotations

import io
import json
import os
import sys
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))

from studio.utils.manifest import Manifest, ManifestResource, load_manifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_manifest(kit_dir: Path, content: str) -> Path:
    """Write manifest.toml into *kit_dir* and return the path."""
    manifest_path = kit_dir / "manifest.toml"
    manifest_path.write_text(textwrap.dedent(content), encoding="utf-8")
    return manifest_path


def _make_kit_with_manifest(td: Path, slug: str = "testkit") -> Path:
    """Create a kit source directory with a valid manifest and source files."""
    kit = td / slug
    kit.mkdir(parents=True, exist_ok=True)

    # Source resources
    (kit / "artifacts" / "ADR").mkdir(parents=True)
    (kit / "artifacts" / "ADR" / "template.md").write_text("# ADR Template\n", encoding="utf-8")
    (kit / "artifacts" / "ADR" / "rules.md").write_text("# ADR Rules\n", encoding="utf-8")
    (kit / "constraints.toml").write_text('[artifacts]\n', encoding="utf-8")
    (kit / "SKILL.md").write_text(f"# Kit {slug}\nKit skill.\n", encoding="utf-8")

    # conf.toml for version
    from studio.utils import toml_utils
    toml_utils.dump({"version": "2.0", "slug": slug}, kit / "conf.toml")

    _write_manifest(kit, """\
        [manifest]
        version = "1.0"
        root = "{cf-studio-path}/config/kits/{slug}"
        user_modifiable = false

        [[resources]]
        id = "adr_artifacts"
        description = "ADR artifact definitions"
        source = "artifacts/ADR"
        default_path = "artifacts/ADR"
        type = "directory"
        user_modifiable = false

        [[resources]]
        id = "constraints"
        description = "Kit structural constraints"
        source = "constraints.toml"
        default_path = "constraints.toml"
        type = "file"
        user_modifiable = false

        [[resources]]
        id = "skill"
        description = "Kit skill instructions"
        source = "SKILL.md"
        default_path = "SKILL.md"
        type = "file"
        user_modifiable = false
    """)
    return kit


def _make_legacy_kit_source(td: Path, slug: str = "legacykit") -> Path:
    """Create a kit source directory WITHOUT manifest.toml (legacy)."""
    kit = td / slug
    kit.mkdir(parents=True, exist_ok=True)
    (kit / "artifacts" / "FEATURE").mkdir(parents=True)
    (kit / "artifacts" / "FEATURE" / "template.md").write_text("# Feature\n", encoding="utf-8")
    (kit / "SKILL.md").write_text(f"# Kit {slug}\n", encoding="utf-8")
    (kit / "constraints.toml").write_text('[artifacts]\n', encoding="utf-8")
    from studio.utils import toml_utils
    toml_utils.dump({"version": "1.0", "slug": slug}, kit / "conf.toml")
    return kit


def _bootstrap_project(root: Path, adapter_rel: str = "cypilot") -> Path:
    """Set up a minimal initialized project for kit commands."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    (root / "AGENTS.md").write_text(
        f'<!-- @cf:root-agents -->\n```toml\n"cf-studio-path" = "{adapter_rel}"\n```\n<!-- /@cf:root-agents -->\n',
        encoding="utf-8",
    )
    adapter = root / adapter_rel
    config = adapter / "config"
    gen = adapter / ".gen"
    for d in [adapter, config, gen, adapter / ".core"]:
        d.mkdir(parents=True, exist_ok=True)
    (config / "AGENTS.md").write_text("# Test\n", encoding="utf-8")
    from studio.utils import toml_utils
    toml_utils.dump({
        "version": "1.0",
        "project_root": "..",
        "kits": {},
    }, config / "core.toml")
    # Minimal artifacts.toml for _read_project_name_from_registry
    toml_utils.dump({
        "systems": [{"name": "TestProject", "slug": "test"}],
    }, config / "artifacts.toml")
    return adapter


# ---------------------------------------------------------------------------
# install_kit_with_manifest (unit tests)
# ---------------------------------------------------------------------------

class TestInstallKitWithManifest(unittest.TestCase):
    """Unit tests for install_kit_with_manifest()."""

    def test_resources_copied_to_correct_paths(self):
        """Manifest install copies each resource to kit_root/default_path."""
        from studio.commands.kit import install_kit_with_manifest

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = _make_kit_with_manifest(td_path, "mykit")

            adapter = td_path / "adapter"
            config = adapter / "config"
            config.mkdir(parents=True)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0", "project_root": "..", "kits": {},
            }, config / "core.toml")

            manifest = load_manifest(kit_src)
            assert manifest is not None

            result = install_kit_with_manifest(
                kit_src, adapter, "mykit", "2.0", manifest,
                interactive=False, source="",
            )

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["kit"], "mykit")
            self.assertEqual(result["version"], "2.0")
            self.assertEqual(result["files_copied"], 3)  # adr_artifacts + constraints + skill

            # Check resources are on disk
            kit_root = adapter / "config" / "kits" / "mykit"
            self.assertTrue((kit_root / "artifacts" / "ADR" / "template.md").is_file())
            self.assertTrue((kit_root / "artifacts" / "ADR" / "rules.md").is_file())
            self.assertTrue((kit_root / "constraints.toml").is_file())
            self.assertTrue((kit_root / "SKILL.md").is_file())

    def test_resource_bindings_in_core_toml(self):
        """Resource bindings are written to core.toml [kits.mykit.resources]."""
        from studio.commands.kit import install_kit_with_manifest
        import tomllib

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = _make_kit_with_manifest(td_path, "mykit")

            adapter = td_path / "adapter"
            config = adapter / "config"
            config.mkdir(parents=True)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0", "project_root": "..", "kits": {},
            }, config / "core.toml")

            manifest = load_manifest(kit_src)
            assert manifest is not None

            result = install_kit_with_manifest(
                kit_src, adapter, "mykit", "2.0", manifest,
                interactive=False,
            )

            self.assertEqual(result["status"], "PASS")

            # Read core.toml and check resources
            with open(config / "core.toml", "rb") as f:
                data = tomllib.load(f)

            kit_entry = data["kits"]["mykit"]
            self.assertIn("resources", kit_entry)
            resources = kit_entry["resources"]
            self.assertIn("adr_artifacts", resources)
            self.assertIn("constraints", resources)
            self.assertIn("skill", resources)
            # Each binding has a "path" key
            self.assertIn("path", resources["adr_artifacts"])
            self.assertIn("path", resources["constraints"])

    def test_resource_bindings_in_result(self):
        """Result dict contains flattened resource_bindings."""
        from studio.commands.kit import install_kit_with_manifest

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = _make_kit_with_manifest(td_path, "mykit")

            adapter = td_path / "adapter"
            config = adapter / "config"
            config.mkdir(parents=True)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0", "project_root": "..", "kits": {},
            }, config / "core.toml")

            manifest = load_manifest(kit_src)
            result = install_kit_with_manifest(
                kit_src, adapter, "mykit", "2.0", manifest,
                interactive=False,
            )

            self.assertIn("resource_bindings", result)
            bindings = result["resource_bindings"]
            self.assertIn("adr_artifacts", bindings)
            self.assertIn("constraints", bindings)
            # Values are path strings (flattened from {path: ...})
            self.assertIsInstance(bindings["adr_artifacts"], str)

    def test_user_modifiable_false_no_prompt(self):
        """When user_modifiable=false, paths are taken from defaults — no prompt."""
        from studio.commands.kit import install_kit_with_manifest

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = _make_kit_with_manifest(td_path, "mykit")

            adapter = td_path / "adapter"
            config = adapter / "config"
            config.mkdir(parents=True)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0", "project_root": "..", "kits": {},
            }, config / "core.toml")

            manifest = load_manifest(kit_src)
            # interactive=True but manifest.user_modifiable=false, so no prompts
            result = install_kit_with_manifest(
                kit_src, adapter, "mykit", "2.0", manifest,
                interactive=True,
            )

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["files_copied"], 3)

    def test_interactive_prompt_custom_path(self):
        """When user_modifiable=true and user provides a path, resource goes there."""
        from studio.commands.kit import install_kit_with_manifest
        from unittest.mock import patch

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = td_path / "ikit"
            kit_src.mkdir()
            (kit_src / "rules.md").write_text("# Rules\n", encoding="utf-8")

            _write_manifest(kit_src, """\
                [manifest]
                version = "1.0"
                user_modifiable = true

                [[resources]]
                id = "rules"
                source = "rules.md"
                default_path = "rules.md"
                type = "file"
                user_modifiable = true
            """)

            adapter = td_path / "adapter"
            config = adapter / "config"
            config.mkdir(parents=True)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0", "project_root": "..", "kits": {},
            }, config / "core.toml")

            manifest = load_manifest(kit_src)
            assert manifest is not None

            custom_dest = td_path / "custom" / "my_rules.md"
            # Mock isatty → True, input → returns custom absolute path
            # First call: root prompt (accept default by returning "")
            # Second call: resource prompt (return custom path)
            inputs = iter(["", str(custom_dest)])
            with patch("sys.stdin") as mock_stdin, \
                 patch("builtins.input", side_effect=lambda prompt: next(inputs)):
                mock_stdin.isatty.return_value = True
                result = install_kit_with_manifest(
                    kit_src, adapter, "ikit", "1.0", manifest,
                    interactive=True,
                )

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["files_copied"], 1)
            # File was copied to the custom path
            self.assertTrue(custom_dest.is_file())
            self.assertEqual(custom_dest.read_text(), "# Rules\n")
            # Binding reflects the custom path (absolute, outside cypilot_dir)
            self.assertIn("rules", result["resource_bindings"])

    def test_version_read_from_conf_toml(self):
        """If kit_version is empty, version is read from source conf.toml."""
        from studio.commands.kit import install_kit_with_manifest

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = _make_kit_with_manifest(td_path, "mykit")

            adapter = td_path / "adapter"
            config = adapter / "config"
            config.mkdir(parents=True)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0", "project_root": "..", "kits": {},
            }, config / "core.toml")

            manifest = load_manifest(kit_src)
            result = install_kit_with_manifest(
                kit_src, adapter, "mykit", "", manifest,
                interactive=False,
            )

            self.assertEqual(result["version"], "2.0")

    def test_validation_errors_return_fail(self):
        """If manifest validation fails, return FAIL with errors."""
        from studio.commands.kit import install_kit_with_manifest

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = td_path / "badkit"
            kit_src.mkdir()
            # manifest references a non-existent source
            manifest = Manifest(
                version="1.0",
                root="{cf-studio-path}/config/kits/{slug}",
                user_modifiable=False,
                resources=[
                    ManifestResource(
                        id="missing",
                        source="does_not_exist.md",
                        default_path="out.md",
                        type="file",
                    ),
                ],
            )

            adapter = td_path / "adapter"
            (adapter / "config").mkdir(parents=True)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0", "project_root": "..", "kits": {},
            }, adapter / "config" / "core.toml")

            result = install_kit_with_manifest(
                kit_src, adapter, "badkit", "1.0", manifest,
                interactive=False,
            )

            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(len(result["errors"]) > 0)

    def test_metadata_collected_for_gen(self):
        """SKILL.md metadata is collected for .gen/ aggregation."""
        from studio.commands.kit import install_kit_with_manifest

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = _make_kit_with_manifest(td_path, "mykit")

            adapter = td_path / "adapter"
            config = adapter / "config"
            config.mkdir(parents=True)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0", "project_root": "..", "kits": {},
            }, config / "core.toml")

            manifest = load_manifest(kit_src)
            result = install_kit_with_manifest(
                kit_src, adapter, "mykit", "2.0", manifest,
                interactive=False,
            )

            self.assertIn("skill_nav", result)
            self.assertIn("mykit", result["skill_nav"])


# ---------------------------------------------------------------------------
# Template variable resolution
# ---------------------------------------------------------------------------

class TestTemplateVariableResolution(unittest.TestCase):
    """Tests for {identifier} template variable resolution in copied files."""

    def test_template_variables_resolved(self):
        """Template variables {resource_id} are replaced in copied .md files."""
        from studio.commands.kit import install_kit_with_manifest

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = td_path / "tplkit"
            kit_src.mkdir()

            # Create a resource with template variables
            (kit_src / "rules.md").write_text(
                "See constraints at {constraints}\nSee ADR at {adr_artifacts}\n",
                encoding="utf-8",
            )
            (kit_src / "data.toml").write_text('[artifacts]\n', encoding="utf-8")

            _write_manifest(kit_src, """\
                [manifest]
                version = "1.0"
                user_modifiable = false

                [[resources]]
                id = "rules"
                source = "rules.md"
                default_path = "rules.md"
                type = "file"
                user_modifiable = false

                [[resources]]
                id = "constraints"
                source = "data.toml"
                default_path = "constraints.toml"
                type = "file"
                user_modifiable = false

                [[resources]]
                id = "adr_artifacts"
                source = "data.toml"
                default_path = "artifacts/ADR"
                type = "file"
                user_modifiable = false
            """)

            adapter = td_path / "adapter"
            config = adapter / "config"
            config.mkdir(parents=True)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0", "project_root": "..", "kits": {},
            }, config / "core.toml")

            manifest = load_manifest(kit_src)
            result = install_kit_with_manifest(
                kit_src, adapter, "tplkit", "1.0", manifest,
                interactive=False,
            )

            self.assertEqual(result["status"], "PASS")

            # Read the copied rules.md and check that variables were resolved
            kit_root = adapter / "config" / "kits" / "tplkit"
            rules_text = (kit_root / "rules.md").read_text(encoding="utf-8")
            # {constraints} should have been replaced with its binding path
            self.assertNotIn("{constraints}", rules_text)
            self.assertNotIn("{adr_artifacts}", rules_text)
            # Check that the resolved path is present
            self.assertIn("constraints.toml", rules_text)


# ---------------------------------------------------------------------------
# install_kit manifest detection (integration)
# ---------------------------------------------------------------------------

class TestInstallKitManifestDetection(unittest.TestCase):
    """Test that install_kit() auto-detects manifest.toml and delegates."""

    def test_manifest_kit_delegates_to_manifest_install(self):
        """install_kit() with manifest.toml → manifest-driven path."""
        from studio.commands.kit import install_kit

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = _make_kit_with_manifest(td_path, "mkit")

            adapter = td_path / "adapter"
            config = adapter / "config"
            config.mkdir(parents=True)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0", "project_root": "..", "kits": {},
            }, config / "core.toml")

            result = install_kit(kit_src, adapter, "mkit", "2.0")

            self.assertEqual(result["status"], "PASS")
            self.assertIn("resource_bindings", result)
            self.assertEqual(result["files_copied"], 3)

            # Resources are on disk
            kit_root = adapter / "config" / "kits" / "mkit"
            self.assertTrue((kit_root / "artifacts" / "ADR" / "template.md").is_file())
            self.assertTrue((kit_root / "constraints.toml").is_file())

    def test_legacy_kit_uses_copy_path(self):
        """install_kit() without manifest.toml → legacy copy path."""
        from studio.commands.kit import install_kit

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = _make_legacy_kit_source(td_path, "legkit")

            adapter = td_path / "adapter"
            config = adapter / "config"
            config.mkdir(parents=True)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0", "project_root": "..", "kits": {},
            }, config / "core.toml")

            result = install_kit(kit_src, adapter, "legkit", "1.0")

            self.assertEqual(result["status"], "PASS")
            # Legacy path returns "actions" dict, not "resource_bindings"
            self.assertIn("actions", result)
            self.assertNotIn("resource_bindings", result)

            # Files are on disk via legacy copy
            kit_root = adapter / "config" / "kits" / "legkit"
            self.assertTrue((kit_root / "artifacts" / "FEATURE" / "template.md").is_file())
            self.assertTrue((kit_root / "SKILL.md").is_file())


# ---------------------------------------------------------------------------
# cmd_kit_install integration with manifest
# ---------------------------------------------------------------------------

class TestCmdKitInstallManifest(unittest.TestCase):
    """Integration tests for cmd_kit_install with manifest-driven kits."""

    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_install_manifest_kit_via_cli(self):
        """cpt kit install --path with manifest kit → resources installed."""
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_with_manifest(td_path / "src", "mkit")

            cwd = os.getcwd()
            try:
                os.chdir(root)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src)])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["kit"], "mkit")
            finally:
                os.chdir(cwd)

            # Verify files on disk
            kit_root = adapter / "config" / "kits" / "mkit"
            self.assertTrue((kit_root / "artifacts" / "ADR" / "template.md").is_file())
            self.assertTrue((kit_root / "constraints.toml").is_file())

    def test_install_legacy_kit_via_cli(self):
        """cpt kit install --path without manifest → legacy install."""
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_legacy_kit_source(td_path / "src", "legkit")

            cwd = os.getcwd()
            try:
                os.chdir(root)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src)])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
            finally:
                os.chdir(cwd)

            # Legacy files installed
            kit_root = adapter / "config" / "kits" / "legkit"
            self.assertTrue((kit_root / "artifacts" / "FEATURE" / "template.md").is_file())


# ---------------------------------------------------------------------------
# _copy_manifest_resource
# ---------------------------------------------------------------------------

class TestCopyManifestResource(unittest.TestCase):
    """Tests for _copy_manifest_resource helper."""

    def test_copy_directory_resource(self):
        from studio.commands.kit import _copy_manifest_resource

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = td_path / "kit"
            kit_src.mkdir()
            (kit_src / "mydir" / "sub").mkdir(parents=True)
            (kit_src / "mydir" / "sub" / "file.md").write_text("hi\n", encoding="utf-8")

            res = ManifestResource(
                id="mydir", source="mydir", default_path="mydir", type="directory",
            )
            target = td_path / "out" / "mydir"
            _copy_manifest_resource(kit_src, res, target)

            self.assertTrue((target / "sub" / "file.md").is_file())
            self.assertEqual((target / "sub" / "file.md").read_text(), "hi\n")

    def test_copy_file_resource(self):
        from studio.commands.kit import _copy_manifest_resource

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = td_path / "kit"
            kit_src.mkdir()
            (kit_src / "readme.md").write_text("# Hello\n", encoding="utf-8")

            res = ManifestResource(
                id="readme", source="readme.md", default_path="readme.md", type="file",
            )
            target = td_path / "out" / "readme.md"
            _copy_manifest_resource(kit_src, res, target)

            self.assertTrue(target.is_file())
            self.assertEqual(target.read_text(), "# Hello\n")

    def test_copy_directory_overwrites_existing(self):
        from studio.commands.kit import _copy_manifest_resource

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = td_path / "kit"
            kit_src.mkdir()
            (kit_src / "d").mkdir()
            (kit_src / "d" / "new.md").write_text("new\n", encoding="utf-8")

            target = td_path / "out" / "d"
            target.mkdir(parents=True)
            (target / "old.md").write_text("old\n", encoding="utf-8")

            res = ManifestResource(
                id="d", source="d", default_path="d", type="directory",
            )
            _copy_manifest_resource(kit_src, res, target)

            self.assertTrue((target / "new.md").is_file())
            self.assertFalse((target / "old.md").exists())


# ---------------------------------------------------------------------------
# _resolve_template_variables
# ---------------------------------------------------------------------------

class TestResolveTemplateVariables(unittest.TestCase):
    """Tests for _resolve_template_variables helper."""

    def test_replaces_variables_in_md_files(self):
        from studio.commands.kit import _resolve_template_variables

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "kit_root"
            root.mkdir()
            (root / "doc.md").write_text(
                "Path: {constraints}\nRef: {adr}\n", encoding="utf-8",
            )

            _resolve_template_variables(root, {
                "constraints": {"path": "config/kits/x/constraints.toml"},
                "adr": {"path": "config/kits/x/artifacts/ADR"},
            })

            text = (root / "doc.md").read_text()
            self.assertIn("config/kits/x/constraints.toml", text)
            self.assertIn("config/kits/x/artifacts/ADR", text)
            self.assertNotIn("{constraints}", text)
            self.assertNotIn("{adr}", text)

    def test_ignores_non_text_files(self):
        from studio.commands.kit import _resolve_template_variables

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "kit_root"
            root.mkdir()
            (root / "image.png").write_bytes(b"\x89PNG{constraints}")

            _resolve_template_variables(root, {
                "constraints": {"path": "x"},
            })

            # .png not in _TEMPLATE_EXTENSIONS — content unchanged
            self.assertEqual((root / "image.png").read_bytes(), b"\x89PNG{constraints}")

    def test_empty_bindings_noop(self):
        from studio.commands.kit import _resolve_template_variables

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "kit_root"
            root.mkdir()
            (root / "doc.md").write_text("{foo}\n", encoding="utf-8")

            _resolve_template_variables(root, {})

            self.assertEqual((root / "doc.md").read_text(), "{foo}\n")


if __name__ == "__main__":
    unittest.main()
