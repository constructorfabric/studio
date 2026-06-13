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
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

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

class TestManifestInstallAdapter(unittest.TestCase):
    """Manifest install adapter is selected through the KitModel boundary."""

    def test_canonical_manifest_loads_adapter(self):
        from studio.commands.kit import _load_manifest_install_adapter

        with TemporaryDirectory() as td:
            kit_src = Path(td) / "kit"
            kit_src.mkdir()
            (kit_src / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
            (kit_src / ".cf-studio-kit.toml").write_text(
                textwrap.dedent(
                    """\
                    manifest_version = "1.0"

                    [[kits]]
                    slug = "mykit"
                    name = "My Kit"
                    version = "1.0"

                    [[kits.resources]]
                    id = "skill"
                    kind = "skill"
                    source = "SKILL.md"
                    install_path = "SKILL.md"
                    """
                ),
                encoding="utf-8",
            )

            manifest = _load_manifest_install_adapter(kit_src, kit_slug="mykit")

            self.assertIsNotNone(manifest)
            assert manifest is not None
            self.assertEqual(manifest.resources[0].id, "skill")

    def test_canonical_manifest_adapter_preserves_artifact_bindings(self):
        from studio.commands.kit import _load_manifest_install_adapter

        with TemporaryDirectory() as td:
            kit_src = Path(td) / "kit"
            kit_src.mkdir()
            (kit_src / "constraints.toml").write_text("[FEATURE.identifiers.flow]\nrequired = true\n", encoding="utf-8")
            (kit_src / "feature-template.md").write_text("# Feature\n", encoding="utf-8")
            (kit_src / ".cf-studio-kit.toml").write_text(
                textwrap.dedent(
                    """\
                    manifest_version = "1.0"

                    [[kits]]
                    slug = "mykit"
                    name = "My Kit"
                    version = "1.0"

                    [[kits.resources]]
                    id = "ruleset"
                    kind = "constraints"
                    source = "constraints.toml"
                    type = "file"

                    [kits.resources.artifacts.FEATURE]
                    template = "feature-template"

                    [[kits.resources]]
                    id = "feature-template"
                    kind = "template"
                    source = "feature-template.md"
                    type = "file"
                    """
                ),
                encoding="utf-8",
            )

            manifest = _load_manifest_install_adapter(kit_src, kit_slug="mykit")

            self.assertIsNotNone(manifest)
            assert manifest is not None
            ruleset = [res for res in manifest.resources if res.id == "ruleset"][0]
            self.assertEqual(ruleset.kind, "constraints")
            self.assertEqual(ruleset.artifact_bindings, {"FEATURE": {"template": "feature-template"}})

    def test_source_without_manifest_returns_none(self):
        from studio.commands.kit import _load_manifest_install_adapter

        with TemporaryDirectory() as td:
            kit_src = Path(td) / "kit"
            kit_src.mkdir()
            (kit_src / "conf.toml").write_text('name = "legacy"\n', encoding="utf-8")

            self.assertIsNone(_load_manifest_install_adapter(kit_src, kit_slug="legacy"))

    def test_sync_manifest_resource_bindings_preserves_artifact_bindings(self):
        from studio.commands.kit import _sync_manifest_resource_bindings
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            config = Path(td) / "config"
            config.mkdir()
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "mykit": {
                        "format": "CFS",
                        "path": "config/kits/mykit",
                        "resources": {
                            "ruleset": {
                                "path": "config/kits/mykit/constraints.toml",
                                "kind": "constraints",
                                "artifacts": {"OLD": {"template": "old-template"}},
                            },
                            "feature-template": {
                                "path": "config/kits/mykit/feature-template.md",
                                "kind": "template",
                                "artifacts": {"OLD": {"template": "old-template"}},
                            },
                        },
                    },
                },
            }, config / "core.toml")
            manifest = SimpleNamespace(
                root="{cf-studio-path}/config/kits/{slug}",
                resources=[
                    SimpleNamespace(
                        id="ruleset",
                        kind="constraints",
                        install_path="constraints.toml",
                        default_path="constraints.toml",
                        public=False,
                        artifact_bindings={"FEATURE": {"template": "feature-template"}},
                    ),
                    SimpleNamespace(
                        id="feature-template",
                        kind="template",
                        install_path="feature-template.md",
                        default_path="feature-template.md",
                        public=False,
                        artifact_bindings={},
                    ),
                ],
            )

            merged = _sync_manifest_resource_bindings(manifest, config, "mykit")

        assert merged is not None
        self.assertEqual(
            merged["ruleset"]["artifacts"],
            {"FEATURE": {"template": "feature-template"}},
        )
        self.assertNotIn("artifacts", merged["feature-template"])

    def test_manifest_resource_bindings_writer_persists_artifact_bindings(self):
        from studio.commands.kit import _manifest_resource_bindings

        with TemporaryDirectory() as td:
            root = Path(td)
            kit_root = root / "adapter" / "config" / "kits" / "mykit"
            kit_root.mkdir(parents=True)
            res = SimpleNamespace(
                id="ruleset",
                kind="constraints",
                install_path="constraints.toml",
                default_path="constraints.toml",
                public=False,
                artifact_bindings={"FEATURE": {"template": "feature-template"}},
            )

            bindings = _manifest_resource_bindings(root / "adapter", kit_root, [res], {})

        self.assertEqual(
            bindings["ruleset"]["artifacts"],
            {"FEATURE": {"template": "feature-template"}},
        )


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
            self.assertEqual(resources["constraints"]["kind"], "constraints")

    def test_manifest_install_fails_when_core_toml_cannot_be_registered(self):
        from studio.commands.kit import install_kit_with_manifest

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = _make_kit_with_manifest(td_path, "mykit")

            adapter = td_path / "adapter"
            (adapter / "config").mkdir(parents=True)

            manifest = load_manifest(kit_src)
            assert manifest is not None

            result = install_kit_with_manifest(
                kit_src, adapter, "mykit", "2.0", manifest,
                interactive=False,
            )

            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(result["files_copied"] > 0)
            self.assertIn("missing", "\n".join(result["errors"]))

    def test_canonical_constraints_resource_kind_is_preserved_in_core_toml(self):
        from studio.commands.kit import install_kit_with_manifest
        import tomllib

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = td_path / "source"
            kit_src.mkdir()
            (kit_src / "custom-rules.toml").write_text(
                "[PRD.identifiers.fr]\nrequired = true\n",
                encoding="utf-8",
            )
            (kit_src / ".cf-studio-kit.toml").write_text(
                textwrap.dedent(
                    """\
                    manifest_version = "1.0"

                    [[kits]]
                    slug = "mykit"
                    version = "1.0"

                    [[kits.resources]]
                    id = "policy"
                    kind = "constraints"
                    source = "custom-rules.toml"
                    install_path = "rules/custom.toml"
                    type = "file"
                    """
                ),
                encoding="utf-8",
            )

            adapter = td_path / "adapter"
            config = adapter / "config"
            config.mkdir(parents=True)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0", "project_root": "..", "kits": {},
            }, config / "core.toml")

            from studio.commands.kit import _load_manifest_install_adapter
            manifest = _load_manifest_install_adapter(kit_src, kit_slug="mykit")
            assert manifest is not None

            result = install_kit_with_manifest(
                kit_src, adapter, "mykit", "1.0", manifest,
                interactive=False,
            )

            self.assertEqual(result["status"], "PASS")
            with open(config / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(
                data["kits"]["mykit"]["resources"]["policy"]["kind"],
                "constraints",
            )
            self.assertEqual(
                data["kits"]["mykit"]["resources"]["policy"]["path"],
                "config/kits/mykit/rules/custom.toml",
            )

    def test_public_component_name_conflict_blocks_install(self):
        from studio.commands.kit import _load_manifest_install_adapter, install_kit_with_manifest

        with TemporaryDirectory() as td:
            td_path = Path(td)
            adapter = td_path / "adapter"
            config = adapter / "config"
            existing = config / "kits" / "existing"
            existing.mkdir(parents=True)
            (existing / "SKILL.md").write_text("# Existing\n", encoding="utf-8")
            (existing / ".cf-studio-kit.toml").write_text(
                textwrap.dedent(
                    """\
                    manifest_version = "1.0"

                    [[kits]]
                    slug = "existing"
                    version = "1.0"

                    [[kits.resources]]
                    id = "shared"
                    kind = "skill"
                    source = "SKILL.md"
                    type = "file"
                    public = true
                    prefix_generated_name = false
                    """
                ),
                encoding="utf-8",
            )
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "existing": {
                        "format": "CFS",
                        "path": "config/kits/existing",
                    },
                },
            }, config / "core.toml")

            kit_src = td_path / "incoming"
            kit_src.mkdir()
            (kit_src / "SKILL.md").write_text("# Incoming\n", encoding="utf-8")
            (kit_src / ".cf-studio-kit.toml").write_text(
                textwrap.dedent(
                    """\
                    manifest_version = "1.0"

                    [[kits]]
                    slug = "incoming"
                    version = "1.0"

                    [[kits.resources]]
                    id = "shared"
                    kind = "skill"
                    source = "SKILL.md"
                    type = "file"
                    public = true
                    prefix_generated_name = false
                    """
                ),
                encoding="utf-8",
            )

            manifest = _load_manifest_install_adapter(kit_src, kit_slug="incoming")
            assert manifest is not None

            result = install_kit_with_manifest(
                kit_src, adapter, "incoming", "1.0", manifest,
                interactive=False,
            )

            self.assertEqual(result["status"], "FAIL")
            self.assertIn("Public component name conflict", "\n".join(result["errors"]))
            self.assertFalse((adapter / "config" / "kits" / "incoming" / "SKILL.md").exists())

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

    def test_user_modifiable_false_non_tty_no_prompt(self):
        """Non-TTY installs use defaults without prompting."""
        import builtins

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

            monkeypatch_input_called = False

            def fail_input(*_args, **_kwargs):
                nonlocal monkeypatch_input_called
                monkeypatch_input_called = True
                raise AssertionError("input() must not be called for non-TTY manifest install")

            self.assertTrue(hasattr(sys.stdin, "isatty"))
            from unittest.mock import patch

            with patch.object(sys.stdin, "isatty", lambda: False), patch.object(builtins, "input", fail_input):
                manifest = load_manifest(kit_src)
                # interactive=True but stdin is not a TTY, so no prompts
                result = install_kit_with_manifest(
                    kit_src, adapter, "mykit", "2.0", manifest,
                    interactive=True,
                )

            self.assertFalse(monkeypatch_input_called)

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["files_copied"], 3)

    def test_interactive_prompt_shows_locked_paths_but_edits_only_modifiable_paths(self):
        """Install plan shows all resources, edit menu contains only editable paths."""
        from studio.commands.kit import install_kit_with_manifest
        from unittest.mock import patch

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = td_path / "mixedkit"
            kit_src.mkdir()
            (kit_src / "locked.toml").write_text("locked = true\n", encoding="utf-8")
            (kit_src / "editable.md").write_text("# Editable\n", encoding="utf-8")
            _write_manifest(kit_src, """\
                [manifest]
                version = "1.0"
                user_modifiable = false

                [[resources]]
                id = "locked"
                source = "locked.toml"
                default_path = "locked.toml"
                type = "file"
                user_modifiable = false

                [[resources]]
                id = "editable"
                source = "editable.md"
                default_path = "editable.md"
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

            custom_editable = "docs/editable.md"
            inputs = iter(["y", "1", custom_editable, "n"])
            stderr = io.StringIO()
            with patch("sys.stdin") as mock_stdin, \
                 patch("builtins.input", side_effect=lambda prompt: next(inputs)), \
                 redirect_stderr(stderr):
                mock_stdin.isatty.return_value = True
                result = install_kit_with_manifest(
                    kit_src, adapter, "mixedkit", "2.0", manifest,
                    interactive=True,
                )

            self.assertEqual(result["status"], "PASS")
            self.assertTrue((adapter / "config" / "kits" / "mixedkit" / "locked.toml").is_file())
            self.assertTrue((adapter / "config" / "kits" / "mixedkit" / custom_editable).is_file())
            self.assertEqual(result["resource_bindings"]["editable"], f"config/kits/mixedkit/{custom_editable}")
            prompt_text = stderr.getvalue()
            self.assertIn("locked (file, locked)", prompt_text)
            self.assertIn("editable (file, editable)", prompt_text)
            edit_menu = prompt_text.split("Select path to change", 1)[1].split("Choice:", 1)[0]
            self.assertNotIn("locked ->", edit_menu)
            self.assertIn("editable ->", edit_menu)

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
            # Mock isatty → True. New UX shows a full plan, then lets the
            # user select the resource path by number before accepting it.
            inputs = iter(["y", "2", str(custom_dest), "n"])
            stderr = io.StringIO()
            with patch("sys.stdin") as mock_stdin, \
                 patch("builtins.input", side_effect=lambda prompt: next(inputs)), \
                 redirect_stderr(stderr):
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
            self.assertIn("Kit install plan: ikit", stderr.getvalue())
            self.assertIn("Select path to change", stderr.getvalue())
            self.assertIn("(file, editable)", stderr.getvalue())

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
# Template variable preservation
# ---------------------------------------------------------------------------

class TestTemplateVariablePreservation(unittest.TestCase):
    """Tests that install preserves {identifier} variables in copied files."""

    def test_template_variables_preserved_in_copied_resources(self):
        """Template variables stay in copied kit source files."""
        from studio.commands.kit import install_kit_with_manifest

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = td_path / "tplkit"
            kit_src.mkdir()

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

            kit_root = adapter / "config" / "kits" / "tplkit"
            rules_text = (kit_root / "rules.md").read_text(encoding="utf-8")
            self.assertEqual(
                rules_text,
                "See constraints at {constraints}\nSee ADR at {adr_artifacts}\n",
            )
            self.assertEqual(
                result["resource_bindings"]["constraints"],
                "config/kits/tplkit/constraints.toml",
            )
            self.assertEqual(
                result["resource_bindings"]["adr_artifacts"],
                "config/kits/tplkit/artifacts/ADR",
            )


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
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "copy"])
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
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "copy"])
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
# _preserve_template_variables
# ---------------------------------------------------------------------------

class TestPreserveTemplateVariables(unittest.TestCase):
    """Tests for _preserve_template_variables helper."""

    def test_preserves_variables_in_md_files(self):
        from studio.commands.kit import _preserve_template_variables

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "kit_root"
            root.mkdir()
            (root / "doc.md").write_text(
                "Path: {constraints}\nRef: {adr}\n", encoding="utf-8",
            )

            _preserve_template_variables(root, {
                "constraints": {"path": "config/kits/x/constraints.toml"},
                "adr": {"path": "config/kits/x/artifacts/ADR"},
            })

            text = (root / "doc.md").read_text()
            self.assertEqual(text, "Path: {constraints}\nRef: {adr}\n")

    def test_preserves_binary_files(self):
        from studio.commands.kit import _preserve_template_variables

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "kit_root"
            root.mkdir()
            (root / "image.png").write_bytes(b"\x89PNG{constraints}")

            _preserve_template_variables(root, {
                "constraints": {"path": "x"},
            })

            self.assertEqual((root / "image.png").read_bytes(), b"\x89PNG{constraints}")

    def test_empty_bindings_noop(self):
        from studio.commands.kit import _preserve_template_variables

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "kit_root"
            root.mkdir()
            (root / "doc.md").write_text("{foo}\n", encoding="utf-8")

            _preserve_template_variables(root, {})

            self.assertEqual((root / "doc.md").read_text(), "{foo}\n")


if __name__ == "__main__":
    unittest.main()
