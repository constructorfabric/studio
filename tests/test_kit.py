"""
Tests for commands/kit.py — kit install, update, dispatcher, helpers.

Scenario-based tests covering CLI subcommands and core kit logic.
"""

import io
import json
import os
import shutil
import sys
import tarfile
import tomllib
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))

from _test_helpers import bootstrap_test_project as _bootstrap_project


def _make_kit_source(td: Path, slug: str = "testkit") -> Path:
    """Create a minimal kit source directory (direct file package)."""
    kit_src = td / slug
    kit_src.mkdir(parents=True, exist_ok=True)
    # Content dirs
    (kit_src / "artifacts" / "FEATURE").mkdir(parents=True)
    (kit_src / "artifacts" / "FEATURE" / "template.md").write_text(
        "# Feature Spec\n", encoding="utf-8",
    )
    (kit_src / "workflows").mkdir(exist_ok=True)
    # Content files
    (kit_src / "SKILL.md").write_text(
        f"---\nname: skill\ndescription: Kit {slug}\n---\n# Kit {slug}\nKit skill instructions.\n",
        encoding="utf-8",
    )
    (kit_src / "constraints.toml").write_text(
        "[naming]\npattern = '{slug}-*'\n", encoding="utf-8",
    )
    # conf.toml
    from studio.utils import toml_utils
    toml_utils.dump({"version": 1, "slug": slug}, kit_src / "conf.toml")
    return kit_src


def _make_manifest_kit_source(td: Path, slug: str = "testkit") -> Path:
    kit_src = _make_kit_source(td, slug)
    (kit_src / "AGENTS.md").write_text(
        f"---\nname: agents\ndescription: Agents {slug}\n---\n# Agents {slug}\n",
        encoding="utf-8",
    )
    (kit_src / "manifest.toml").write_text(
        "\n".join([
            "[manifest]",
            'version = "1"',
            'root = "{cf-studio-path}/config/kits/{slug}"',
            "user_modifiable = false",
            "",
            "[[resources]]",
            'id = "skill"',
            'source = "SKILL.md"',
            'default_path = "SKILL.md"',
            'type = "file"',
            "user_modifiable = false",
            "",
            "[[resources]]",
            'id = "agents"',
            'source = "AGENTS.md"',
            'default_path = "AGENTS.md"',
            'type = "file"',
            "user_modifiable = false",
            "",
            "[[resources]]",
            'id = "constraints"',
            'source = "constraints.toml"',
            'default_path = "constraints.toml"',
            'type = "file"',
            "user_modifiable = false",
        ]) + "\n",
        encoding="utf-8",
    )
    return kit_src


def _make_canonical_kit_source(td: Path, slug: str = "canonicalkit") -> Path:
    kit_src = td / slug
    kit_src.mkdir(parents=True, exist_ok=True)
    (kit_src / "SKILL.md").write_text(
        "---\nname: skill\ndescription: Canonical kit\n---\n# Canonical kit\n",
        encoding="utf-8",
    )
    (kit_src / ".cf-studio-kit.toml").write_text(
        "\n".join([
            'manifest_version = "1.0"',
            "",
            "[[kits]]",
            f'slug = "{slug}"',
            f'name = "{slug}"',
            'version = "1.2.3"',
            "",
            "[[kits.resources]]",
            'id = "skill"',
            'kind = "skill"',
            'source = "SKILL.md"',
            'install_path = "SKILL.md"',
            'type = "file"',
            "public = true",
        ]) + "\n",
        encoding="utf-8",
    )
    return kit_src


def _make_strict_canonical_kit_source(
    td: Path,
    slug: str = "strictkit",
    *,
    version: str = "1.0.0",
    declared_text: str = "declared\n",
) -> Path:
    kit_src = td / slug
    kit_src.mkdir(parents=True, exist_ok=True)
    (kit_src / "declared.txt").write_text(declared_text, encoding="utf-8")
    (kit_src / "AGENTS.md").write_text("# UNDECLARED ROOT AGENTS\n", encoding="utf-8")
    (kit_src / "SKILL.md").write_text("# UNDECLARED ROOT SKILL\n", encoding="utf-8")
    (kit_src / ".cf-studio-kit.toml").write_text(
        "\n".join([
            'manifest_version = "1.0"',
            "",
            "[[kits]]",
            f'slug = "{slug}"',
            f'name = "{slug}"',
            f'version = "{version}"',
            "",
            "[[kits.resources]]",
            'id = "declared"',
            'kind = "other"',
            'source = "declared.txt"',
            'install_path = "declared.txt"',
            'type = "file"',
            "user_modifiable = false",
        ]) + "\n",
        encoding="utf-8",
    )
    return kit_src


def _make_strict_legacy_manifest_kit_source(td: Path, slug: str = "strictlegacy") -> Path:
    kit_src = td / slug
    kit_src.mkdir(parents=True, exist_ok=True)
    (kit_src / "declared.txt").write_text("declared\n", encoding="utf-8")
    (kit_src / "AGENTS.md").write_text("# UNDECLARED ROOT AGENTS\n", encoding="utf-8")
    (kit_src / "SKILL.md").write_text("# UNDECLARED ROOT SKILL\n", encoding="utf-8")
    (kit_src / "manifest.toml").write_text(
        "\n".join([
            "[manifest]",
            'version = "1"',
            'root = "{cf-studio-path}/config/kits/{slug}"',
            "user_modifiable = false",
            "",
            "[[resources]]",
            'id = "declared"',
            'source = "declared.txt"',
            'default_path = "declared.txt"',
            'type = "file"',
            "user_modifiable = false",
        ]) + "\n",
        encoding="utf-8",
    )
    return kit_src


def _make_multi_canonical_kit_source(td: Path) -> Path:
    kit_src = td / "multi-kit"
    kit_src.mkdir(parents=True, exist_ok=True)
    (kit_src / "alpha.md").write_text("# Alpha\n", encoding="utf-8")
    (kit_src / "beta.md").write_text("# Beta\n", encoding="utf-8")
    (kit_src / ".cf-studio-kit.toml").write_text(
        "\n".join([
            'manifest_version = "1.0"',
            "",
            "[[kits]]",
            'slug = "alpha"',
            'name = "Alpha"',
            'version = "1.0.0"',
            "",
            "[[kits.resources]]",
            'id = "skill"',
            'kind = "skill"',
            'source = "alpha.md"',
            'install_path = "SKILL.md"',
            'type = "file"',
            "public = true",
            "",
            "[[kits]]",
            'slug = "beta"',
            'name = "Beta"',
            'version = "2.0.0"',
            "",
            "[[kits.resources]]",
            'id = "skill"',
            'kind = "skill"',
            'source = "beta.md"',
            'install_path = "SKILL.md"',
            'type = "file"',
            "public = true",
        ]) + "\n",
        encoding="utf-8",
    )
    return kit_src


class TestCmdKitDispatcher(unittest.TestCase):
    """Kit CLI dispatcher: handles subcommands and errors."""

    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_no_subcommand(self):
        from studio.commands.kit import cmd_kit
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_kit([])
        self.assertEqual(rc, 1)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "ERROR")
        self.assertIn("subcommand", out["message"].lower())

    def test_unknown_subcommand(self):
        from studio.commands.kit import cmd_kit
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_kit(["frobnicate"])
        self.assertEqual(rc, 1)
        out = json.loads(buf.getvalue())
        self.assertIn("Unknown", out["message"])

    def test_help_subcommand(self):
        from studio.commands.kit import cmd_kit
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_kit(["--help"])
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "PASS")
        self.assertIn("usage", out)


class TestKitNormalize(unittest.TestCase):
    """Kit model normalization and cfs kit normalize command."""

    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_normalize_legacy_manifest_dry_run(self):
        from studio.commands.kit import cmd_kit_normalize

        with TemporaryDirectory() as td:
            kit_src = _make_manifest_kit_source(Path(td), "manifestkit")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_kit_normalize([str(kit_src), "--dry-run"])
            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["status"], "PASS")
            self.assertTrue(out["dry_run"])
            self.assertEqual(out["kit"], "manifestkit")
            self.assertEqual(out["report"]["manifest_source"], "legacy_manifest")
            self.assertNotIn("content_identity", out["report"])
            warnings = "\n".join(out["report"]["warnings"])
            self.assertIn("legacy manifest.toml is supported for migration", warnings)
            self.assertIn(".cf-studio-kit.toml", warnings)
            self.assertIn('manifest_version = "1.0"', out["manifest"])
            self.assertIn("[[kits]]", out["manifest"])
            self.assertIn("[[kits.resources]]", out["manifest"])
            manifest_data = tomllib.loads(out["manifest"])
            resources = {r["id"]: r for r in manifest_data["kits"][0]["resources"]}
            self.assertEqual(resources["constraints"]["kind"], "constraints")
            self.assertFalse((kit_src / ".cf-studio-kit.toml").exists())

    def test_normalize_legacy_manifest_v2_components(self):
        from studio.commands.kit import cmd_kit_normalize

        with TemporaryDirectory() as td:
            kit_src = Path(td) / "componentkit"
            kit_src.mkdir()
            (kit_src / "skills").mkdir()
            (kit_src / "agents").mkdir()
            (kit_src / "rules").mkdir()
            (kit_src / "workflows").mkdir()
            (kit_src / "skills" / "standctl.md").write_text("# Standctl\n", encoding="utf-8")
            (kit_src / "agents" / "bug-fixer.md").write_text("# Bug fixer\n", encoding="utf-8")
            (kit_src / "rules" / "repo.md").write_text("# Rule\n", encoding="utf-8")
            (kit_src / "workflows" / "ship.md").write_text("# Ship\n", encoding="utf-8")
            (kit_src / "manifest.toml").write_text(
                "\n".join([
                    "[manifest]",
                    'version = "2.0"',
                    "",
                    "[[skills]]",
                    'id = "standctl"',
                    'description = "Stand control skill"',
                    'source = "skills/standctl.md"',
                    'agents = ["claude"]',
                    "",
                    "[[agents]]",
                    'id = "bug-fixer"',
                    'description = "Fix bugs on stands"',
                    'source = "agents/bug-fixer.md"',
                    'tools = ["Bash", "Read"]',
                    'model = "sonnet"',
                    'color = "magenta"',
                    'memory_dir = ".claude/agent-memory/bug-fixer"',
                    'skills = ["standctl"]',
                    'agents = ["claude"]',
                    "",
                    "[[rules]]",
                    'id = "repo-rule"',
                    'description = "Repository rule"',
                    'source = "rules/repo.md"',
                    'agents = ["claude"]',
                    "",
                    "[[workflows]]",
                    'id = "ship-flow"',
                    'description = "Ship workflow"',
                    'source = "workflows/ship.md"',
                    'agents = ["claude"]',
                ]) + "\n",
                encoding="utf-8",
            )

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_kit_normalize([str(kit_src), "--dry-run"])

            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            data = tomllib.loads(out["manifest"])
            resources = {r["id"]: r for r in data["kits"][0]["resources"]}

            self.assertEqual(resources["standctl"]["kind"], "skill")
            self.assertEqual(resources["standctl"]["generated_targets"], ["claude"])
            self.assertEqual(resources["bug-fixer"]["kind"], "agent")
            self.assertEqual(resources["bug-fixer"]["tools"], ["Bash", "Read"])
            self.assertEqual(resources["bug-fixer"]["model"], "sonnet")
            self.assertEqual(resources["bug-fixer"]["color"], "magenta")
            self.assertEqual(resources["bug-fixer"]["memory_dir"], ".claude/agent-memory/bug-fixer")
            self.assertEqual(resources["bug-fixer"]["skills"], ["standctl"])
            self.assertEqual(resources["repo-rule"]["kind"], "rule")
            self.assertEqual(resources["ship-flow"]["kind"], "skill")
            self.assertEqual(resources["ship-flow"]["origin"], "legacy-workflow")


class TestManifestKitStrictResourceAuthority(unittest.TestCase):
    """Manifest-backed kits install and aggregate only declared resources."""

    def test_canonical_manifest_install_ignores_undeclared_root_metadata_files(self):
        from studio.commands.kit import install_kit, regenerate_gen_aggregates

        with TemporaryDirectory() as td:
            root = Path(td) / "project"
            adapter = _bootstrap_project(root)
            kit_src = _make_strict_canonical_kit_source(Path(td), "strictkit")

            result = install_kit(kit_src, adapter, "strictkit", interactive=False)
            self.assertEqual(result["status"], "PASS")

            installed = adapter / "config" / "kits" / "strictkit"
            self.assertEqual((installed / "declared.txt").read_text(encoding="utf-8"), "declared\n")
            self.assertFalse((installed / "AGENTS.md").exists())
            self.assertFalse((installed / "SKILL.md").exists())

            regenerate_gen_aggregates(adapter)
            self.assertNotIn(
                "UNDECLARED ROOT AGENTS",
                (adapter / ".gen" / "AGENTS.md").read_text(encoding="utf-8"),
            )
            self.assertFalse((adapter / ".gen" / "SKILL.md").exists())

    def test_legacy_manifest_install_ignores_undeclared_root_metadata_files(self):
        from studio.commands.kit import install_kit, regenerate_gen_aggregates

        with TemporaryDirectory() as td:
            root = Path(td) / "project"
            adapter = _bootstrap_project(root)
            kit_src = _make_strict_legacy_manifest_kit_source(Path(td), "strictlegacy")

            result = install_kit(kit_src, adapter, "strictlegacy", interactive=False)
            self.assertEqual(result["status"], "PASS")

            installed = adapter / "config" / "kits" / "strictlegacy"
            self.assertEqual((installed / "declared.txt").read_text(encoding="utf-8"), "declared\n")
            self.assertFalse((installed / "AGENTS.md").exists())
            self.assertFalse((installed / "SKILL.md").exists())

            regenerate_gen_aggregates(adapter)
            self.assertNotIn(
                "UNDECLARED ROOT AGENTS",
                (adapter / ".gen" / "AGENTS.md").read_text(encoding="utf-8"),
            )
            self.assertFalse((adapter / ".gen" / "SKILL.md").exists())

    def test_manifest_update_filters_undeclared_root_metadata_files(self):
        from studio.commands.kit import install_kit, update_kit

        with TemporaryDirectory() as td:
            root = Path(td) / "project"
            adapter = _bootstrap_project(root)
            source_v1 = _make_strict_canonical_kit_source(
                Path(td) / "v1",
                "strictkit",
                version="1.0.0",
                declared_text="v1\n",
            )
            source_v2 = _make_strict_canonical_kit_source(
                Path(td) / "v2",
                "strictkit",
                version="2.0.0",
                declared_text="v2\n",
            )

            install = install_kit(source_v1, adapter, "strictkit", interactive=False)
            self.assertEqual(install["status"], "PASS")
            result = update_kit(
                "strictkit",
                source_v2,
                adapter,
                interactive=False,
                auto_approve=True,
                force=True,
            )
            self.assertIn(result["version"]["status"], {"updated", "current"})

            installed = adapter / "config" / "kits" / "strictkit"
            self.assertEqual((installed / "declared.txt").read_text(encoding="utf-8"), "v2\n")
            self.assertFalse((installed / "AGENTS.md").exists())
            self.assertFalse((installed / "SKILL.md").exists())

    def test_public_rule_resource_injects_into_gen_agents_only(self):
        from studio.commands.kit import install_kit, regenerate_gen_aggregates

        with TemporaryDirectory() as td:
            root = Path(td) / "project"
            adapter = _bootstrap_project(root)
            kit_src = Path(td) / "rulekit"
            kit_src.mkdir()
            (kit_src / "rules").mkdir()
            (kit_src / "rules" / "public.md").write_text("# PUBLIC RULE SENTINEL\n", encoding="utf-8")
            (kit_src / ".cf-studio-kit.toml").write_text(
                "\n".join([
                    'manifest_version = "1.0"',
                    "",
                    "[[kits]]",
                    'slug = "rulekit"',
                    'name = "rulekit"',
                    'version = "1.0.0"',
                    "",
                    "[[kits.resources]]",
                    'id = "public-rule"',
                    'kind = "rule"',
                    'source = "rules/public.md"',
                    'install_path = "rules/public.md"',
                    'type = "file"',
                    "public = true",
                ]) + "\n",
                encoding="utf-8",
            )

            result = install_kit(kit_src, adapter, "rulekit", interactive=False)
            self.assertEqual(result["status"], "PASS")
            regenerate_gen_aggregates(adapter)

            self.assertIn(
                "PUBLIC RULE SENTINEL",
                (adapter / ".gen" / "AGENTS.md").read_text(encoding="utf-8"),
            )
            self.assertFalse((adapter / ".gen" / "SKILL.md").exists())


class TestKitUpdateCheckCoverage(unittest.TestCase):
    """Focused coverage for kit update-check and public name conflict helpers."""

    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def _component(self, component_id, generated_name, kind="skill", subagents=None):
        return SimpleNamespace(
            id=component_id,
            generated_name=generated_name,
            kind=kind,
            subagents=subagents or [],
        )

    def _model(self, slug, components):
        return SimpleNamespace(slug=slug, public_components=components)

    def test_public_component_name_conflicts_include_nested_subagents(self):
        from studio.commands.kit import _kit_model_public_component_names, _public_component_name_conflicts

        model = self._model(
            "pubkit",
            [
                self._component(
                    "agent",
                    "cf-pubkit-agent",
                    kind="agent",
                    subagents=[
                        {"id": "helper"},
                        {"id": ""},
                        "not-a-table",
                        {"id": "exact", "prefix_generated_name": False},
                    ],
                ),
                self._component("duplicate", "cf-pubkit-helper"),
            ],
        )

        names = _kit_model_public_component_names(model)
        self.assertEqual(names["cf-pubkit-helper"], "duplicate")
        self.assertEqual(names["exact"], "agent.subagents.exact")

        errors = _public_component_name_conflicts(Path("/no-studio"), "pubkit", model)
        self.assertTrue(any("cf-pubkit-helper" in error for error in errors))

    def test_public_component_name_conflicts_against_existing_registered_kit(self):
        from studio.commands.kit import _public_component_name_conflicts

        with TemporaryDirectory() as td:
            studio_dir = Path(td) / ".bootstrap"
            existing_root = studio_dir / "config" / "kits" / "existing"
            existing_root.mkdir(parents=True)
            installing = self._model(
                "newkit",
                [self._component("skill", "cf-newkit-skill")],
            )
            existing = self._model(
                "existing",
                [self._component("skill", "cf-newkit-skill")],
            )

            with patch(
                "studio.commands.kit._read_kits_from_core_toml",
                return_value={"existing": {"path": "config/kits/existing"}},
            ), patch("studio.utils.kit_model.load_kit_model", return_value=existing):
                errors = _public_component_name_conflicts(studio_dir, "newkit", installing)

            self.assertTrue(any("already generated by kit 'existing'" in error for error in errors))

    def test_kit_update_check_result_branches(self):
        from studio.commands.kit import _kit_update_check_result

        github = _kit_update_check_result(
            "kit",
            {"source": "github:owner/repo", "source_provenance": {"resolved_ref": "v1.0.0"}},
            {"source_type": "github", "resolved_ref": "v1.1.0"},
        )
        self.assertEqual(github["action"], "update_available")
        self.assertEqual(github["latest_ref"], "v1.1.0")

        git = _kit_update_check_result(
            "kit",
            {"source_provenance": {"commit_sha": "abc"}},
            {"source_type": "git", "commit_sha": "def"},
        )
        self.assertEqual(git["action"], "update_available")
        self.assertEqual(git["installed_commit"], "abc")

        failed = _kit_update_check_result("kit", {}, None)
        self.assertEqual(failed["action"], "failed")

    def test_seed_kit_config_files_copies_missing_toml_only(self):
        from studio.commands.kit import _seed_kit_config_files

        with TemporaryDirectory() as td:
            root = Path(td)
            gen_scripts_dir = root / "scripts"
            config_dir = root / "config"
            gen_scripts_dir.mkdir()
            (gen_scripts_dir / "settings.toml").write_text("value = 1\n", encoding="utf-8")
            (gen_scripts_dir / "ignored.txt").write_text("value = 2\n", encoding="utf-8")

            actions = {}
            _seed_kit_config_files(gen_scripts_dir, config_dir, actions)

            self.assertEqual((config_dir / "settings.toml").read_text(encoding="utf-8"), "value = 1\n")
            self.assertFalse((config_dir / "ignored.txt").exists())
            self.assertEqual(actions, {"config_settings": "seeded"})

            (gen_scripts_dir / "settings.toml").write_text("value = 3\n", encoding="utf-8")
            _seed_kit_config_files(gen_scripts_dir, config_dir, actions)
            self.assertEqual((config_dir / "settings.toml").read_text(encoding="utf-8"), "value = 1\n")

    def test_write_whatsnew_from_github_releases_branches(self):
        import json as json_module
        from studio.commands.kit import _write_kit_whatsnew_from_github_releases

        class _Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json_module.dumps(self.payload).encode("utf-8")

        with TemporaryDirectory() as td:
            kit_dir = Path(td)
            with patch("studio.commands.kit.urllib.request.urlopen", return_value=_Response({"message": "not a list"})):
                _write_kit_whatsnew_from_github_releases(kit_dir, "owner", "repo")
            self.assertFalse((kit_dir / "whatsnew.toml").exists())

            releases = [
                {"tag_name": "", "name": "blank"},
                "not-a-release",
                {"tag_name": "v1.0.0", "name": "First release", "body": "Details"},
            ]
            with patch("studio.commands.kit.urllib.request.urlopen", return_value=_Response(releases)):
                _write_kit_whatsnew_from_github_releases(kit_dir, "owner", "repo")

            rendered = (kit_dir / "whatsnew.toml").read_text(encoding="utf-8")
            self.assertIn('[whatsnew."v1.0.0"]', rendered)
            self.assertIn('summary = "First release"', rendered)

    def test_check_registered_kit_updates_summarizes_failures_and_cleans_tmpdir(self):
        from studio.commands.kit import _check_registered_kit_updates

        with TemporaryDirectory() as td:
            tmp_dir = Path(td) / "tmp-kit"
            tmp_dir.mkdir()
            with patch(
                "studio.commands.kit._resolve_registered_update_targets",
                return_value=(
                    [("gitkit", Path(td), "git:https://example.invalid/repo.git", tmp_dir, {"source_type": "git", "commit_sha": "new"})],
                    [{"kit": "bad", "action": "ERROR", "message": "broken", "source": "git:bad"}],
                ),
            ):
                results, failures = _check_registered_kit_updates({
                    "gitkit": {
                        "source": "git:https://example.invalid/repo.git",
                        "source_provenance": {"commit_sha": "old"},
                    }
                })

            self.assertFalse(tmp_dir.exists())
            self.assertEqual(failures[0]["kit"], "bad")
            actions = {result["kit"]: result["action"] for result in results}
            self.assertEqual(actions["bad"], "failed")
            self.assertEqual(actions["gitkit"], "update_available")

    def test_cmd_kit_check_updates_filters_slug_and_outputs_commands(self):
        from studio.commands.kit import cmd_kit_check_updates

        with TemporaryDirectory() as td:
            root = Path(td)
            studio_dir = root / ".bootstrap"
            studio_dir.mkdir()
            with patch("studio.commands.kit._resolve_studio_dir", return_value=(root, studio_dir)), \
                    patch(
                        "studio.commands.kit._read_kits_from_core_toml",
                        return_value={"sdlc": {"source": "github:owner/repo"}},
                    ), \
                    patch(
                        "studio.commands.kit._check_registered_kit_updates",
                        return_value=([
                            {
                                "kit": "sdlc",
                                "action": "update_available",
                                "command": "cfs kit update sdlc",
                                "installed_ref": "v1.0.0",
                                "latest_ref": "v1.1.0",
                            }
                        ], []),
                    ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_check_updates(["sdlc", "--project-root", str(root)])

        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["updates_available"], 1)
        self.assertEqual(out["commands"], ["cfs kit update sdlc"])

    def test_cmd_kit_check_updates_reports_missing_slug(self):
        from studio.commands.kit import cmd_kit_check_updates

        with TemporaryDirectory() as td:
            root = Path(td)
            studio_dir = root / ".bootstrap"
            studio_dir.mkdir()
            with patch("studio.commands.kit._resolve_studio_dir", return_value=(root, studio_dir)), \
                    patch(
                        "studio.commands.kit._read_kits_from_core_toml",
                        return_value={"sdlc": {"source": "github:owner/repo"}},
                    ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_check_updates(["missing"])

        self.assertEqual(rc, 2)
        self.assertIn("Kit 'missing' not found", json.loads(buf.getvalue())["message"])

    def test_cmd_kit_check_updates_no_project_and_no_kits_branches(self):
        from studio.commands.kit import cmd_kit_check_updates

        with patch("studio.commands.kit._resolve_studio_dir", return_value=None):
            self.assertEqual(cmd_kit_check_updates([]), 1)

        with TemporaryDirectory() as td:
            root = Path(td)
            studio_dir = root / ".bootstrap"
            studio_dir.mkdir()
            with patch("studio.commands.kit._resolve_studio_dir", return_value=(root, studio_dir)), \
                    patch("studio.commands.kit._read_kits_from_core_toml", return_value={}):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_check_updates([])

        self.assertEqual(rc, 2)
        self.assertIn("No kits registered", json.loads(buf.getvalue())["message"])

    def test_cmd_kit_update_aborts_when_whatsnew_declined_and_cleans_tmpdir(self):
        from studio.commands.kit import cmd_kit_update

        with TemporaryDirectory() as td:
            root = Path(td)
            studio_dir = root / ".bootstrap"
            config_dir = studio_dir / "config"
            kit_source = Path(td) / "kit-source"
            tmp_dir = Path(td) / "tmp-kit"
            config_dir.mkdir(parents=True)
            kit_source.mkdir()
            tmp_dir.mkdir()

            with patch("studio.commands.kit._resolve_studio_dir", return_value=(root, studio_dir)), \
                    patch(
                        "studio.commands.kit._read_kits_from_core_toml",
                        return_value={"sdlc": {"source": "github:owner/repo", "version": "v1.0.0"}},
                    ), \
                    patch(
                        "studio.commands.kit._resolve_registered_update_targets",
                        return_value=(
                            [("sdlc", kit_source, "github:owner/repo", tmp_dir, {"source_type": "github"})],
                            [],
                        ),
                    ), \
                    patch("studio.commands.kit._read_kit_version_from_core", return_value="v1.0.0"), \
                    patch("studio.commands.kit.show_kit_whatsnew", return_value=False), \
                    patch("studio.commands.kit.regenerate_gen_aggregates") as regen_mock:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["sdlc", "--project-root", str(root)])

        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "PASS")
        self.assertEqual(out["results"][0]["action"], "aborted")
        self.assertFalse(tmp_dir.exists())
        regen_mock.assert_called_once_with(studio_dir)

    def test_human_kit_check_updates_renders_all_result_kinds(self):
        from studio.commands.kit import _human_kit_check_updates
        from studio.utils.ui import set_json_mode

        set_json_mode(False)
        try:
            buf = io.StringIO()
            with redirect_stderr(buf):
                _human_kit_check_updates({
                    "status": "WARN",
                    "updates_available": 1,
                    "results": [
                        {
                            "kit": "sdlc",
                            "action": "update_available",
                            "installed_ref": "v1.0.0",
                            "latest_ref": "v1.1.0",
                            "command": "cfs kit update sdlc",
                        },
                        {"kit": "bad", "action": "failed", "message": "broken"},
                        {"kit": "ok", "action": "current"},
                    ],
                })
            rendered = buf.getvalue()
        finally:
            set_json_mode(True)

        self.assertIn("Kit Update Check", rendered)
        self.assertIn("update available", rendered)
        self.assertIn("broken", rendered)

    def test_semver_tag_resolution_error_and_no_candidates(self):
        import json as json_module
        from studio.commands.kit import _resolve_latest_semver_tag

        class _Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json_module.dumps(self.payload).encode("utf-8")

        with patch("studio.commands.kit.urllib.request.urlopen", return_value=_Response(["bad-entry", {"name": "latest"}])):
            self.assertEqual(_resolve_latest_semver_tag("owner", "repo"), "")

        with patch("studio.commands.kit.urllib.request.urlopen", side_effect=OSError("offline")):
            with self.assertRaisesRegex(RuntimeError, "Failed to query GitHub tags"):
                _resolve_latest_semver_tag("owner", "repo")

    def test_resolve_registered_update_targets_error_branches(self):
        from studio.commands.kit import _resolve_registered_update_targets
        from studio.utils.git_kit_source import GitSourceError

        with patch(
            "studio.commands.kit.parse_git_kit_source",
            side_effect=GitSourceError("invalid", "bad source"),
        ):
            targets, failures = _resolve_registered_update_targets({"bad": {"source": "git:bad"}})
        self.assertEqual(targets, [])
        self.assertEqual(failures[0]["kit"], "bad")
        self.assertEqual(failures[0]["error_code"], "invalid")

        parsed = SimpleNamespace(canonical_source="git:https://example.invalid/repo.git")
        with patch("studio.commands.kit.parse_git_kit_source", return_value=parsed), \
                patch("studio.commands.kit.materialize_git_kit_source", side_effect=RuntimeError("offline")):
            targets, failures = _resolve_registered_update_targets({
                "bad": {
                    "source": "git:https://example.invalid/repo.git",
                    "source_provenance": {"requested_ref": "HEAD"},
                }
            })
        self.assertEqual(targets, [])
        self.assertIn("offline", failures[0]["message"])

    def test_resolve_github_update_targets_error_and_last_known_branches(self):
        from studio.commands.kit import _resolve_github_update_targets

        kits = {
            "missing": {},
            "pathkit": {"source": "path:/tmp/kit"},
            "bad": {"source": "github:not-enough"},
            "current": {"source": "github:owner/repo@v1.2.3", "version": "v1.2.3"},
            "failed": {"source": "github:owner/repo@v2.0.0", "version": "v1.0.0"},
        }

        def fake_resolve(owner, repo, version="", previous_entry=None):
            if previous_entry and previous_entry.get("version") == "v1.2.3":
                return {
                    "source_type": "github",
                    "freshness": "last_known",
                    "resolved_ref": "v1.2.3",
                }
            raise RuntimeError("no authority")

        with patch(
            "studio.commands.kit._download_kit_from_github_with_authority",
            side_effect=RuntimeError("offline"),
        ), patch("studio.commands.kit._resolve_github_ref", side_effect=fake_resolve):
            targets, failures = _resolve_github_update_targets(kits)

        self.assertEqual(targets, [])
        actions = {failure["kit"]: failure["action"] for failure in failures}
        self.assertEqual(actions["missing"], "ERROR")
        self.assertEqual(actions["pathkit"], "ERROR")
        self.assertEqual(actions["bad"], "ERROR")
        self.assertEqual(actions["current"], "current")
        self.assertEqual(actions["failed"], "failed")

    def test_resolve_github_update_targets_success_returns_cleanup_dir_and_authority(self):
        from studio.commands.kit import _resolve_github_update_targets

        with TemporaryDirectory() as td:
            source_dir = Path(td) / "repo" / "kit"
            source_dir.mkdir(parents=True)
            authority = {"source_type": "github", "resolved_ref": "v1.0.0"}
            with patch(
                "studio.commands.kit._download_kit_from_github_with_authority",
                return_value=(source_dir, "v1.0.0", authority),
            ):
                targets, failures = _resolve_github_update_targets({
                    "ok": {"source": "github:owner/repo@v1.0.0"}
                })

        self.assertEqual(failures, [])
        self.assertEqual(targets[0][0], "ok")
        self.assertEqual(targets[0][3], source_dir.parent)
        self.assertEqual(targets[0][4], authority)

    def test_human_kit_update_renders_authority_and_warning_status(self):
        from studio.commands.kit import _human_kit_update
        from studio.utils.ui import set_json_mode

        set_json_mode(False)
        try:
            buf = io.StringIO()
            with redirect_stderr(buf):
                _human_kit_update({
                    "status": "WARN",
                    "kits_updated": 1,
                    "results": [
                        {
                            "kit": "sdlc",
                            "action": "updated",
                            "accepted": ["SKILL.md"],
                            "declined": ["AGENTS.md"],
                            "unchanged": 2,
                            "authority": {
                                "resolution_basis": "semver",
                                "resolved_ref": "v1.1.0",
                                "commit_sha": "abc123",
                                "freshness": "live",
                            },
                        },
                    ],
                    "errors": ["minor warning"],
                })
            rendered = buf.getvalue()
        finally:
            set_json_mode(True)

        self.assertIn("Kit Update", rendered)
        self.assertIn("authority", rendered)
        self.assertIn("minor warning", rendered)

    def test_human_kit_install_renders_dry_run_fail_and_unknown(self):
        from studio.commands.kit import _human_kit_install
        from studio.utils.ui import set_json_mode

        set_json_mode(False)
        try:
            buf = io.StringIO()
            with redirect_stderr(buf):
                _human_kit_install({
                    "status": "DRY_RUN",
                    "kit": "sdlc",
                    "version": "1.0",
                    "source": "path:/kit",
                    "target": ".bootstrap/config/kits/sdlc",
                })
                _human_kit_install({
                    "status": "FAIL",
                    "kit": "sdlc",
                    "version": "1.0",
                    "files_written": 0,
                    "artifact_kinds": ["skill"],
                    "errors": ["conflict"],
                    "message": "Install failed",
                    "hint": "pick another name",
                })
                _human_kit_install({
                    "status": "PARTIAL",
                    "kit": "sdlc",
                    "version": "1.0",
                    "files_written": 1,
                })
            rendered = buf.getvalue()
        finally:
            set_json_mode(True)

        self.assertIn("Dry run", rendered)
        self.assertIn("conflict", rendered)
        self.assertIn("Status: PARTIAL", rendered)

    def test_manifest_resource_copy_and_change_detection_directory_branches(self):
        from studio.commands.kit import _copy_manifest_resource, _manifest_resource_changed

        with TemporaryDirectory() as td:
            root = Path(td)
            kit_source = root / "source"
            kit_source.mkdir()
            source_dir = kit_source / "bundle"
            source_dir.mkdir()
            (source_dir / "a.txt").write_text("one", encoding="utf-8")
            (source_dir / "nested").mkdir()
            (source_dir / "nested" / "b.txt").write_text("two", encoding="utf-8")

            dir_res = SimpleNamespace(source="bundle", type="directory")
            target_dir = root / "target"
            self.assertFalse(_manifest_resource_changed(kit_source, dir_res, target_dir))

            target_dir.mkdir()
            (target_dir / "stale.txt").write_text("stale", encoding="utf-8")
            self.assertTrue(_manifest_resource_changed(kit_source, dir_res, target_dir))

            _copy_manifest_resource(kit_source, dir_res, target_dir)
            self.assertFalse((target_dir / "stale.txt").exists())
            self.assertFalse(_manifest_resource_changed(kit_source, dir_res, target_dir))

            (target_dir / "nested" / "b.txt").write_text("changed", encoding="utf-8")
            self.assertTrue(_manifest_resource_changed(kit_source, dir_res, target_dir))

            file_res = SimpleNamespace(source="bundle/a.txt", type="file")
            file_target = root / "copied" / "a.txt"
            _copy_manifest_resource(kit_source, file_res, file_target)
            self.assertEqual(file_target.read_text(encoding="utf-8"), "one")
            self.assertFalse(_manifest_resource_changed(kit_source, file_res, file_target))
            with patch.object(Path, "read_bytes", side_effect=OSError("unreadable")):
                self.assertTrue(_manifest_resource_changed(kit_source, file_res, file_target))

            file_target.unlink()
            file_target.mkdir()
            self.assertTrue(_manifest_resource_changed(kit_source, file_res, file_target))

    def test_resolve_install_source_git_error_and_success_branches(self):
        from studio.commands.kit import _resolve_install_source_git
        from studio.utils.git_kit_source import GitSourceError

        with patch(
            "studio.commands.kit.parse_git_kit_source",
            side_effect=GitSourceError("invalid", "bad git source"),
        ):
            self.assertIsNone(_resolve_install_source_git("git:bad"))

        parsed = SimpleNamespace(canonical_source="git:https://example.invalid/repo.git", kit_identity="")
        with patch("studio.commands.kit.parse_git_kit_source", return_value=parsed), \
                patch("studio.commands.kit.materialize_git_kit_source", side_effect=RuntimeError("offline")):
            result = _resolve_install_source_git("git:https://example.invalid/repo.git")
        self.assertEqual(result[5], 1)

        with TemporaryDirectory() as td:
            tmp_dir = Path(td) / "tmp"
            kit_source = tmp_dir / "kit"
            kit_source.mkdir(parents=True)
            resolution = SimpleNamespace(
                kit_source_dir=kit_source,
                tmp_dir=tmp_dir,
                authority_metadata={"installed_version": "abc123"},
            )

            with patch("studio.commands.kit.parse_git_kit_source", return_value=parsed), \
                    patch("studio.commands.kit.materialize_git_kit_source", return_value=resolution), \
                    patch("studio.commands.kit._read_kit_slug", return_value=""):
                missing_slug = _resolve_install_source_git("git:https://example.invalid/repo.git")
            self.assertEqual(missing_slug[5], 1)
            self.assertFalse(tmp_dir.exists())

        with TemporaryDirectory() as td:
            tmp_dir = Path(td) / "tmp"
            kit_source = tmp_dir / "kit"
            kit_source.mkdir(parents=True)
            parsed_with_identity = SimpleNamespace(
                canonical_source="git:https://example.invalid/repo.git@wanted",
                kit_identity="wanted",
            )
            resolution = SimpleNamespace(
                kit_source_dir=kit_source,
                tmp_dir=tmp_dir,
                authority_metadata={"installed_version": "def456"},
            )
            with patch("studio.commands.kit.parse_git_kit_source", return_value=parsed_with_identity), \
                    patch("studio.commands.kit.materialize_git_kit_source", return_value=resolution), \
                    patch("studio.commands.kit._read_kit_slug", return_value="actual"):
                mismatch = _resolve_install_source_git("git:https://example.invalid/repo.git@wanted")
            self.assertEqual(mismatch[5], 1)
            self.assertFalse(tmp_dir.exists())

        with TemporaryDirectory() as td:
            tmp_dir = Path(td) / "tmp"
            kit_source = tmp_dir / "kit"
            kit_source.mkdir(parents=True)
            resolution = SimpleNamespace(
                kit_source_dir=kit_source,
                tmp_dir=tmp_dir,
                authority_metadata={"installed_version": "cafebabe"},
            )
            with patch("studio.commands.kit.parse_git_kit_source", return_value=parsed), \
                    patch("studio.commands.kit.materialize_git_kit_source", return_value=resolution), \
                    patch("studio.commands.kit._read_kit_slug", return_value="sdlc"):
                success = _resolve_install_source_git("git:https://example.invalid/repo.git")
            self.assertEqual(success[1], "sdlc")
            self.assertEqual(success[2], "cafebabe")
            self.assertEqual(success[4], tmp_dir)

    def test_project_root_from_core_toml_branches(self):
        from studio.commands.kit import _project_root_from_core_toml

        with TemporaryDirectory() as td:
            studio_dir = Path(td) / ".bootstrap"
            config_dir = studio_dir / "config"
            config_dir.mkdir(parents=True)
            self.assertIsNone(_project_root_from_core_toml(config_dir, studio_dir))

            (config_dir / "core.toml").write_text("project_root = 123\n", encoding="utf-8")
            self.assertIsNone(_project_root_from_core_toml(config_dir, studio_dir))

            (config_dir / "core.toml").write_text('project_root = ".."\n', encoding="utf-8")
            self.assertEqual(_project_root_from_core_toml(config_dir, studio_dir), studio_dir.parent.resolve())

            absolute_root = Path(td).resolve()
            (config_dir / "core.toml").write_text(
                f'project_root = "{absolute_root.as_posix()}"\n',
                encoding="utf-8",
            )
            self.assertEqual(_project_root_from_core_toml(config_dir, studio_dir), absolute_root)

    def test_normalize_layout_writes_default_manifest(self):
        from studio.commands.kit import cmd_kit_normalize

        with TemporaryDirectory() as td:
            kit_src = _make_kit_source(Path(td), "layoutkit")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_kit_normalize([str(kit_src), "--from", "layout"])
            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["status"], "PASS")
            manifest_path = kit_src / ".cf-studio-kit.toml"
            self.assertEqual(Path(out["output"]).resolve(), manifest_path.resolve())
            warnings = "\n".join(out["report"]["warnings"])
            self.assertIn("layout-only kit discovery is supported for migration", warnings)
            self.assertIn("legacy workflow resources are normalized to public skill resources", warnings)
            with open(manifest_path, "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(data["manifest_version"], "1.0")
            self.assertEqual(data["kits"][0]["slug"], "layoutkit")
            resource_ids = {r["id"] for r in data["kits"][0]["resources"]}
            self.assertIn("artifacts", resource_ids)
            self.assertIn("skill", resource_ids)
            resources = {r["id"]: r for r in data["kits"][0]["resources"]}
            self.assertEqual(resources["constraints"]["kind"], "constraints")

    def test_normalize_dry_run_human_prints_versioned_manifest(self):
        from studio.commands.kit import cmd_kit_normalize
        from studio.utils.ui import set_json_mode

        with TemporaryDirectory() as td:
            kit_src = _make_manifest_kit_source(Path(td), "humankit")
            buf = io.StringIO()
            set_json_mode(False)
            try:
                with redirect_stderr(buf):
                    rc = cmd_kit_normalize([str(kit_src), "--dry-run"])
            finally:
                set_json_mode(True)

            self.assertEqual(rc, 0)
            out = buf.getvalue()
            self.assertIn('manifest_version = "1.0"', out)
            self.assertIn("[[kits]]", out)
            self.assertIn("[[kits.resources]]", out)

    def test_normalize_stdout_prints_raw_versioned_manifest_only(self):
        from studio.commands.kit import cmd_kit_normalize

        with TemporaryDirectory() as td:
            kit_src = _make_manifest_kit_source(Path(td), "stdoutkit")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_kit_normalize([str(kit_src), "--from", "manifest", "--stdout"])

            self.assertEqual(rc, 0)
            out = buf.getvalue()
            self.assertIn('manifest_version = "1.0"', out)
            self.assertIn("[[kits]]", out)
            self.assertIn("[[kits.resources]]", out)
            data = tomllib.loads(out)
            self.assertEqual(data["manifest_version"], "1.0")
            self.assertEqual(data["kits"][0]["slug"], "stdoutkit")
            self.assertFalse((kit_src / ".cf-studio-kit.toml").exists())

    def test_normalize_refuses_unversioned_rendered_manifest(self):
        from studio.utils import kit_model

        with TemporaryDirectory() as td:
            kit_src = _make_manifest_kit_source(Path(td), "guardkit")

            with patch.object(
                kit_model,
                "render_canonical_manifest",
                return_value='[[kits]]\nslug = "guardkit"\n',
            ):
                with self.assertRaisesRegex(ValueError, "missing required manifest_version"):
                    kit_model.normalize_kit_source(kit_src)

    def test_normalize_report_includes_public_component_preview(self):
        from studio.commands.kit import cmd_kit_normalize

        with TemporaryDirectory() as td:
            kit_src = _make_manifest_kit_source(Path(td), "previewkit")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_kit_normalize([str(kit_src), "--dry-run"])
            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            components = out["report"]["public_components"]
            self.assertTrue(any(c["generated_name"] == "cf-previewkit-skill" for c in components))
            self.assertNotIn("content_identity", out["report"])

    def test_normalize_core_bindings_dry_run(self):
        from studio.commands.kit import cmd_kit_normalize

        with TemporaryDirectory() as td:
            adapter_dir = Path(td) / ".cypilot-adapter"
            config_dir = adapter_dir / "config"
            kit_src = config_dir / "kits" / "sdlc"
            (kit_src / "workflows").mkdir(parents=True)
            (kit_src / "SKILL.md").write_text("# SDLC\n", encoding="utf-8")
            (kit_src / "constraints.toml").write_text("[PRD.identifiers.fr]\nrequired = true\n", encoding="utf-8")
            (kit_src / "workflows" / "implement.md").write_text(
                "---\ntype: workflow\nname: implement\n---\n# Implement\n",
                encoding="utf-8",
            )
            (config_dir / "core.toml").write_text(
                "\n".join([
                    'version = "1.0"',
                    "",
                    "[kits.sdlc]",
                    'path = "config/kits/sdlc"',
                    'version = "1.1.1"',
                    "",
                    "[kits.sdlc.resources.skill]",
                    'path = "config/kits/sdlc/SKILL.md"',
                    "",
                    "[kits.sdlc.resources.constraints]",
                    'path = "config/kits/sdlc/constraints.toml"',
                    "",
                    "[kits.sdlc.resources.implement]",
                    'path = "config/kits/sdlc/workflows/implement.md"',
                ]) + "\n",
                encoding="utf-8",
            )

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_kit_normalize([str(kit_src), "--from", "core", "--dry-run"])

            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["report"]["manifest_source"], "core")
            manifest = out["manifest"]
            self.assertIn('source = "SKILL.md"', manifest)
            self.assertIn('source = "workflows/implement.md"', manifest)
            self.assertIn('origin = "legacy-workflow"', manifest)
            manifest_data = tomllib.loads(manifest)
            resources = {r["id"]: r for r in manifest_data["kits"][0]["resources"]}
            self.assertEqual(resources["constraints"]["kind"], "constraints")
            self.assertTrue(any(
                component["generated_name"] == "cf-sdlc-implement"
                for component in out["report"]["public_components"]
            ))

    def test_normalize_core_rejects_outside_binding(self):
        from studio.commands.kit import cmd_kit_normalize

        with TemporaryDirectory() as td:
            adapter_dir = Path(td) / ".cypilot-adapter"
            config_dir = adapter_dir / "config"
            kit_src = config_dir / "kits" / "sdlc"
            kit_src.mkdir(parents=True)
            (adapter_dir / "shared.md").write_text("# Shared\n", encoding="utf-8")
            (config_dir / "core.toml").write_text(
                "\n".join([
                    'version = "1.0"',
                    "",
                    "[kits.sdlc]",
                    'path = "config/kits/sdlc"',
                    "",
                    "[kits.sdlc.resources.shared]",
                    'path = "shared.md"',
                ]) + "\n",
                encoding="utf-8",
            )

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_kit_normalize([str(kit_src), "--from", "core", "--dry-run"])

            self.assertEqual(rc, 2)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["status"], "FAIL")
            self.assertIn("outside selected kit root", out["message"])

    def test_generated_manifest_can_reload_generated_name_without_warning(self):
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            kit_src = _make_manifest_kit_source(Path(td), "reloadkit")
            model = load_kit_model(kit_src)
            from studio.utils.kit_model import render_canonical_manifest

            (kit_src / ".cf-studio-kit.toml").write_text(
                render_canonical_manifest(model),
                encoding="utf-8",
            )
            reloaded = load_kit_model(kit_src)
            warnings = "\n".join(reloaded.warnings)
            self.assertNotIn("generated_name", warnings)

    def test_rendered_canonical_manifest_does_not_emit_generated_name(self):
        from studio.utils.kit_model import load_kit_model, render_canonical_manifest

        with TemporaryDirectory() as td:
            kit_src = _make_canonical_kit_source(Path(td), "nogenerated")
            rendered = render_canonical_manifest(load_kit_model(kit_src))
            self.assertNotIn("generated_name", rendered)

    def test_kit_model_rejects_non_boolean_user_modifiable(self):
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            kit_src = Path(td) / "badkit"
            kit_src.mkdir()
            (kit_src / "skill.md").write_text("# Skill\n", encoding="utf-8")
            (kit_src / ".cf-studio-kit.toml").write_text(
                "\n".join([
                    'manifest_version = "1.0"',
                    "",
                    "[[kits]]",
                    'slug = "badkit"',
                    'version = "1.0.0"',
                    "",
                    "[[kits.resources]]",
                    'id = "skill"',
                    'kind = "skill"',
                    'source = "skill.md"',
                    'user_modifiable = "false"',
                ]) + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as ctx:
                load_kit_model(kit_src)
            self.assertIn("user_modifiable", str(ctx.exception))

    def test_dispatcher_routes_normalize(self):
        from studio.commands.kit import cmd_kit

        with TemporaryDirectory() as td:
            kit_src = _make_kit_source(Path(td), "routekit")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_kit(["normalize", str(kit_src), "--dry-run"])
            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["kit"], "routekit")

    def test_kit_model_computes_resource_and_manifest_hashes(self):
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            kit_src = _make_canonical_kit_source(Path(td), "hashkit")
            model = load_kit_model(kit_src)
            self.assertRegex(model.manifest_bytes_hash, r"^[0-9a-f]{64}$")
            self.assertRegex(model.tool_risk_fingerprint, r"^[0-9a-f]{64}$")
            self.assertEqual(model.resources[0].content_hash, model.resource_hashes["skill"])

            first_hash = model.resource_hashes["skill"]
            (kit_src / "SKILL.md").write_text("# Changed\n", encoding="utf-8")
            changed = load_kit_model(kit_src)
            self.assertNotEqual(changed.resource_hashes["skill"], first_hash)

    def test_kit_model_directory_hash_ignores_cache_dirs(self):
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            kit_src = _make_kit_source(Path(td), "dirhash")
            model = load_kit_model(kit_src, "layout")
            artifacts_hash = model.resource_hashes["artifacts"]

            cache_dir = kit_src / "artifacts" / "__pycache__"
            cache_dir.mkdir()
            (cache_dir / "ignored.pyc").write_bytes(b"ignored")
            self.assertEqual(load_kit_model(kit_src, "layout").resource_hashes["artifacts"], artifacts_hash)

            (kit_src / "artifacts" / "FEATURE" / "second.md").write_text("new\n", encoding="utf-8")
            self.assertNotEqual(load_kit_model(kit_src, "layout").resource_hashes["artifacts"], artifacts_hash)

    def test_kit_model_public_components_use_generated_names_and_targets(self):
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            kit_src = _make_canonical_kit_source(Path(td), "pubkit")
            model = load_kit_model(kit_src)

            self.assertEqual([component.id for component in model.public_components], ["skill"])
            component = model.public_components[0]
            self.assertEqual(component.generated_name, "cf-pubkit-skill")
            self.assertEqual(component.generated_targets, ["installed"])
            self.assertEqual(model.resources[0].id, "skill")

    def test_kit_model_can_disable_public_name_prefix_per_resource(self):
        from studio.utils.kit_model import load_kit_model, kit_model_to_toml_data

        with TemporaryDirectory() as td:
            kit_src = _make_canonical_kit_source(Path(td), "pubkit")
            manifest = kit_src / ".cf-studio-kit.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8") + "prefix_generated_name = false\n",
                encoding="utf-8",
            )

            model = load_kit_model(kit_src)

            self.assertEqual(model.public_components[0].generated_name, "skill")
            self.assertFalse(model.resources[0].prefix_generated_name)
            self.assertFalse(kit_model_to_toml_data(model)["kits"][0]["resources"][0]["prefix_generated_name"])

    def test_kit_model_rejects_public_supporting_resource(self):
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            kit_src = _make_canonical_kit_source(Path(td), "pubkit")
            manifest = kit_src / ".cf-studio-kit.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace('kind = "skill"', 'kind = "template"'),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "public=true is only allowed"):
                load_kit_model(kit_src)

    def test_kit_model_rejects_non_public_generated_name_fields(self):
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            kit_src = _make_canonical_kit_source(Path(td), "pubkit")
            manifest = kit_src / ".cf-studio-kit.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "public = true",
                    "public = false\nprefix_generated_name = false",
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "prefix_generated_name=false is only allowed"):
                load_kit_model(kit_src)

            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "prefix_generated_name = false",
                    'generated_targets = ["cursor"]',
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "generated_targets is only allowed"):
                load_kit_model(kit_src)

    def test_kit_model_tool_risk_summary_warns_and_fingerprints(self):
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            kit_src = _make_canonical_kit_source(Path(td), "riskkit")
            manifest = kit_src / ".cf-studio-kit.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8")
                + "\n[kits.resources.agent]\n"
                + 'tools = ["Bash", "FutureTool"]\n',
                encoding="utf-8",
            )

            model = load_kit_model(kit_src)

            self.assertRegex(model.tool_risk_fingerprint, r"^[0-9a-f]{64}$")
            self.assertTrue(model.tool_risk_summary["requires_confirmation"])
            self.assertEqual(model.tool_risk_summary["dangerous_tools"]["skill"], ["Bash"])
            self.assertEqual(model.tool_risk_summary["unknown_tools"]["skill"], ["FutureTool"])
            self.assertTrue(any("FutureTool" in warning for warning in model.warnings))

    def test_kit_model_render_preserves_tool_declarations(self):
        from studio.utils.kit_model import load_kit_model, kit_model_to_toml_data

        with TemporaryDirectory() as td:
            kit_src = _make_canonical_kit_source(Path(td), "riskkit")
            manifest = kit_src / ".cf-studio-kit.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8")
                + "\n[kits.resources.agent]\n"
                + 'tools = ["Bash"]\n',
                encoding="utf-8",
            )

            data = kit_model_to_toml_data(load_kit_model(kit_src))

            self.assertEqual(data["kits"][0]["resources"][0]["tools"], ["Bash"])

    def test_kit_model_preserves_public_agent_configuration_fields(self):
        from studio.utils.kit_model import load_kit_model, kit_model_to_toml_data

        with TemporaryDirectory() as td:
            kit_src = _make_canonical_kit_source(Path(td), "agentkit")
            manifest = kit_src / ".cf-studio-kit.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8")
                .replace('kind = "skill"', 'kind = "agent"')
                + "\n[kits.resources.agent]\n"
                + 'mode = "readonly"\n'
                + "isolation = true\n"
                + 'model = "cf:tier:balanced"\n'
                + 'skills = ["cf-agentkit-helper"]\n'
                + 'color = "blue"\n'
                + 'memory_dir = ".memory/agentkit"\n'
                + 'role = "analyze"\n'
                + 'target = "codebase"\n'
                + 'provider = "anthropic"\n'
                + 'reasoning_effort = "high"\n'
                + 'context_window = "max"\n'
                + '\n[kits.resources.permissions]\n'
                + 'tools = ["Read"]\n'
                + '[[kits.resources.agent.subagents]]\n'
                + 'id = "helper"\n'
                + 'source = "SKILL.md"\n'
                + '\n[kits.resources.targets.cursor]\n'
                + 'mode = "readonly"\n'
                + 'reasoning_effort = "high"\n',
                encoding="utf-8",
            )

            model = load_kit_model(kit_src)
            component = model.public_components[0]

            self.assertEqual(component.mode, "readonly")
            self.assertTrue(component.isolation)
            self.assertEqual(component.model, "cf:tier:balanced")
            self.assertEqual(component.skills, ["cf-agentkit-helper"])
            self.assertEqual(component.color, "blue")
            self.assertEqual(component.memory_dir, ".memory/agentkit")
            self.assertEqual(component.role, "analyze")
            self.assertEqual(component.target, "codebase")
            self.assertEqual(component.reasoning_effort, "high")
            self.assertEqual(component.context_window, "max")
            self.assertEqual(component.tools, ["Read"])
            self.assertEqual(component.subagents[0]["id"], "helper")
            self.assertEqual(component.target_configs["cursor"]["mode"], "readonly")

            data = kit_model_to_toml_data(model)
            resource = data["kits"][0]["resources"][0]
            self.assertEqual(resource["mode"], "readonly")
            self.assertTrue(resource["isolation"])
            self.assertEqual(resource["tools"], ["Read"])
            self.assertEqual(resource["skills"], ["cf-agentkit-helper"])
            self.assertEqual(resource["subagents"][0]["id"], "helper")
            self.assertEqual(resource["targets"]["cursor"]["reasoning_effort"], "high")

    def test_kit_model_preserves_prefixed_public_name_from_frontmatter(self):
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            kit_src = _make_canonical_kit_source(Path(td), "pubkit")
            (kit_src / "SKILL.md").write_text(
                "---\nname: cf-pubkit-skill\ndescription: Canonical kit\n---\n# Canonical kit\n",
                encoding="utf-8",
            )
            component = load_kit_model(kit_src).public_components[0]
            self.assertEqual(component.id, "skill")
            self.assertEqual(component.generated_name, "cf-pubkit-skill")

    def test_kit_model_canonical_workflow_kind_warns_and_normalizes_to_skill(self):
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            kit_src = _make_canonical_kit_source(Path(td), "workflowkit")
            manifest = kit_src / ".cf-studio-kit.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace('kind = "skill"', 'kind = "workflow"'),
                encoding="utf-8",
            )
            model = load_kit_model(kit_src)
            self.assertEqual(model.resources[0].kind, "skill")
            self.assertEqual(model.resources[0].origin, "")
            self.assertIn("normalized to 'skill'", "\n".join(model.warnings))

    def test_kit_model_legacy_v2_workflow_becomes_public_skill(self):
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            kit_src = Path(td) / "legacyv2"
            kit_src.mkdir()
            (kit_src / "release.md").write_text(
                "---\nname: release\ndescription: Ship release\n---\n# Release workflow\n",
                encoding="utf-8",
            )
            (kit_src / "manifest.toml").write_text(
                "\n".join([
                    "[manifest]",
                    'version = "2.0"',
                    "",
                    "[[workflows]]",
                    'id = "release"',
                    'prompt_file = "release.md"',
                ]) + "\n",
                encoding="utf-8",
            )

            model = load_kit_model(kit_src)
            self.assertEqual(model.resources[0].id, "release")
            self.assertEqual(model.resources[0].kind, "skill")
            self.assertEqual(model.resources[0].origin, "legacy-workflow")
            self.assertEqual(model.public_components[0].generated_name, "cf-legacyv2-release")
            warnings = "\n".join(model.warnings)
            self.assertIn("Legacy workflow 'release'", warnings)
            self.assertIn("legacy workflow resources are normalized to public skill resources", warnings)
            self.assertIn('use kind = "skill"', warnings)

    def test_kit_model_warns_on_unknown_canonical_fields_and_rejects_binding_path(self):
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            kit_src = _make_canonical_kit_source(Path(td), "warnkit")
            manifest = kit_src / ".cf-studio-kit.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8")
                .replace('version = "1.2.3"', 'version = "1.2.3"\nextra_meta = "ignored"')
                .replace("public = true", 'public = true\nextra_resource = "ignored"'),
                encoding="utf-8",
            )
            model = load_kit_model(kit_src)
            warnings = "\n".join(model.warnings)
            self.assertIn("[[kits]][0]: unknown optional field 'extra_meta' ignored", warnings)
            self.assertIn("[[kits]][0].resources[0]: unknown optional field 'extra_resource' ignored", warnings)

            manifest.write_text(
                manifest.read_text(encoding="utf-8") + 'binding_path = "config/kits/warnkit/SKILL.md"\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "binding_path"):
                load_kit_model(kit_src)

    def test_kit_model_requires_canonical_manifest_version(self):
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            kit_src = _make_canonical_kit_source(Path(td), "versionless")
            manifest = kit_src / ".cf-studio-kit.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace('manifest_version = "1.0"\n\n', ""),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "missing required manifest_version"):
                load_kit_model(kit_src)

    def test_kit_model_rejects_unknown_canonical_manifest_version_with_update_hint(self):
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            kit_src = _make_canonical_kit_source(Path(td), "futurekit")
            manifest = kit_src / ".cf-studio-kit.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    'manifest_version = "1.0"',
                    'manifest_version = "99.0"',
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "unsupported manifest_version '99.0'.*pipx upgrade constructor-studio"):
                load_kit_model(kit_src)


class TestKitSourceModeValidation(unittest.TestCase):
    """Local path kit commands reject remote source selectors."""

    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_install_path_rejects_version_selector(self):
        from studio.commands.kit import cmd_kit_install

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_kit_install(["--path", "/tmp/local-kit", "--version", "v1.2.3"])
        self.assertEqual(rc, 2)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "FAIL")
        self.assertIn("--version", out["message"])
        self.assertIn("--path", out["message"])

    def test_install_mode_is_local_path_only(self):
        from studio.commands.kit import cmd_kit_install

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_kit_install(["owner/repo", "--install-mode", "register"])
        self.assertEqual(rc, 2)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "FAIL")
        self.assertIn("--install-mode", out["message"])
        self.assertIn("--path", out["message"])

    def test_multi_kit_manifest_parser_lists_models(self):
        from studio.utils.kit_model import load_canonical_kit_models

        with TemporaryDirectory() as td:
            kit_src = _make_multi_canonical_kit_source(Path(td))

            models = load_canonical_kit_models(kit_src)

            self.assertEqual([model.slug for model in models], ["alpha", "beta"])
            self.assertEqual(models[0].resources[0].source, "alpha.md")
            self.assertEqual(models[1].resources[0].source, "beta.md")

    def test_multi_kit_manifest_requires_selection_noninteractive(self):
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_project(root)
            kit_src = _make_multi_canonical_kit_source(root / "local-kits")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "copy"])
                self.assertEqual(rc, 2)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "FAIL")
                self.assertIn("multiple kits", out["message"])
                self.assertEqual(out["available_kits"], ["alpha", "beta"])
            finally:
                os.chdir(cwd)

    def test_multi_kit_manifest_installs_selected_kit(self):
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_multi_canonical_kit_source(root / "local-kits")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install([
                        "--path", str(kit_src),
                        "--install-mode", "copy",
                        "--kit", "beta",
                    ])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["kit"], "beta")
                self.assertEqual(out["version"], "2.0.0")
                self.assertEqual(
                    (adapter / "config" / "kits" / "beta" / "SKILL.md").read_text(encoding="utf-8"),
                    "# Beta\n",
                )
                self.assertFalse((adapter / "config" / "kits" / "alpha").exists())
            finally:
                os.chdir(cwd)

    def test_multi_kit_manifest_installs_all_selected_kits(self):
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_multi_canonical_kit_source(root / "local-kits")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install([
                        "--path", str(kit_src),
                        "--install-mode", "copy",
                        "--kit", "all",
                    ])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["kits_installed"], 2)
                self.assertTrue((adapter / "config" / "kits" / "alpha" / "SKILL.md").is_file())
                self.assertTrue((adapter / "config" / "kits" / "beta" / "SKILL.md").is_file())
            finally:
                os.chdir(cwd)

    def test_install_mode_registers_in_project_manifest_resources(self):
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_canonical_kit_source(root / "local-kits", "regkit")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "register"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["install_mode"], "register")
                self.assertEqual(out["files_written"], 0)
                self.assertEqual(out["files_registered"], 1)

                with open(adapter / "config" / "core.toml", "rb") as f:
                    core = tomllib.load(f)
                entry = core["kits"]["regkit"]
                self.assertEqual(entry["install_mode"], "register")
                self.assertTrue(entry["path"].endswith("local-kits/regkit"))
                self.assertNotIn("resources", entry)
                self.assertEqual(entry["source_provenance"]["source_type"], "local_path")
                self.assertEqual(entry["source_provenance"]["resolver_mode"], "register")
                self.assertTrue(entry["source_provenance"]["effective_source"].endswith("local-kits/regkit"))
                self.assertFalse(Path(entry["source_provenance"]["effective_source"]).is_absolute())
                self.assertNotIn("content_identity", entry)
                self.assertFalse((adapter / "config" / "kits" / "regkit" / "SKILL.md").exists())
            finally:
                os.chdir(cwd)

    def test_interactive_install_mode_defaults_register_when_contained(self):
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_canonical_kit_source(root / "local-kits", "prompt-regkit")
            fake_stdin = type("_FakeStdin", (), {"isatty": lambda self: True})()
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with (
                    patch("sys.stdin", fake_stdin),
                    patch("builtins.input", side_effect=[""]),
                    redirect_stdout(buf),
                ):
                    rc = cmd_kit_install(["--path", str(kit_src)])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["install_mode"], "register")
                self.assertEqual(out["files_registered"], 1)
                self.assertFalse((adapter / "config" / "kits" / "prompt-regkit" / "SKILL.md").exists())
            finally:
                os.chdir(cwd)

    def test_interactive_install_mode_defaults_copy_when_register_unavailable(self):
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_canonical_kit_source(Path(td), "prompt-copykit")
            fake_stdin = type("_FakeStdin", (), {"isatty": lambda self: True})()
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with (
                    patch("sys.stdin", fake_stdin),
                    patch("builtins.input", side_effect=["", ""]),
                    redirect_stdout(buf),
                ):
                    rc = cmd_kit_install(["--path", str(kit_src)])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["install_mode"], "copy")
                self.assertEqual(out["files_written"], 1)
                self.assertEqual(
                    (adapter / "config" / "kits" / "prompt-copykit" / "SKILL.md").read_text(encoding="utf-8"),
                    "---\nname: skill\ndescription: Canonical kit\n---\n# Canonical kit\n",
                )
            finally:
                os.chdir(cwd)

    def test_update_register_mode_refreshes_hashes_without_copying(self):
        from studio.commands.kit import cmd_kit_install, update_kit

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_canonical_kit_source(root / "local-kits", "regupdate")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with redirect_stdout(io.StringIO()):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "register"])
                self.assertEqual(rc, 0)
                with open(adapter / "config" / "core.toml", "rb") as f:
                    before = tomllib.load(f)["kits"]["regupdate"]["version"]

                (kit_src / "SKILL.md").write_text("# Registered update\n", encoding="utf-8")
                result = update_kit(
                    "regupdate",
                    kit_src,
                    adapter,
                    project_root=root,
                )

                self.assertEqual(result["version"]["status"], "current")
                self.assertEqual(result["gen"]["files_written"], 0)
                self.assertFalse((adapter / "config" / "kits" / "regupdate" / "SKILL.md").exists())
                with open(adapter / "config" / "core.toml", "rb") as f:
                    entry = tomllib.load(f)["kits"]["regupdate"]
                after = entry["version"]
                self.assertEqual(after, before)
                self.assertEqual(entry["install_mode"], "register")
                self.assertNotIn("resources", entry)
                self.assertEqual(
                    result["resource_bindings"]["skill"],
                    "../local-kits/regupdate/SKILL.md",
                )
            finally:
                os.chdir(cwd)

    def test_update_register_mode_returns_core_registration_errors(self):
        from studio.commands.kit import cmd_kit_install, update_kit
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_canonical_kit_source(root / "local-kits", "regfail")
            toml_utils.dump({"version": "9.9.9", "slug": "regfail"}, kit_src / "conf.toml")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with redirect_stdout(io.StringIO()):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "register"])
                self.assertEqual(rc, 0)
                (kit_src / "SKILL.md").write_text("# Registered update failure\n", encoding="utf-8")

                with patch("studio.commands.kit._register_kit_in_core_toml", return_value=["cannot write core"]):
                    result = update_kit("regfail", kit_src, adapter, project_root=root)

                self.assertEqual(result["version"]["status"], "failed")
                self.assertEqual(result["gen"]["files_written"], 0)
                self.assertEqual(result["errors"], ["cannot write core"])
            finally:
                os.chdir(cwd)

    def test_update_register_mode_revalidates_containment(self):
        from studio.commands.kit import cmd_kit_install, update_kit

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_canonical_kit_source(root / "local-kits", "regcontain")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with redirect_stdout(io.StringIO()):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "register"])
                self.assertEqual(rc, 0)

                result = update_kit(
                    "regcontain",
                    kit_src,
                    adapter,
                    project_root=Path(td) / "other-project",
                )

                self.assertEqual(result["version"]["status"], "failed")
                self.assertIn("project root", " ".join(result["errors"]))
            finally:
                os.chdir(cwd)

    def test_install_mode_register_rejects_symlink_escape(self):
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = root / "local-kits" / "escapekit"
            kit_src.mkdir(parents=True)
            outside = Path(td) / "outside.md"
            outside.write_text("# Outside\n", encoding="utf-8")
            try:
                os.symlink(outside, kit_src / "SKILL.md")
            except (AttributeError, NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink unavailable: {exc}")
            (kit_src / "manifest.toml").write_text(
                "\n".join([
                    "[manifest]",
                    'version = "1"',
                    'root = "{cf-studio-path}/config/kits/{slug}"',
                    "user_modifiable = false",
                    "",
                    "[[resources]]",
                    'id = "skill"',
                    'source = "SKILL.md"',
                    'default_path = "SKILL.md"',
                    'type = "file"',
                    "user_modifiable = false",
                ]) + "\n",
                encoding="utf-8",
            )
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "register"])
                self.assertEqual(rc, 2)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "FAIL")
                self.assertIn("escapes", " ".join(out["errors"]))
                with open(adapter / "config" / "core.toml", "rb") as f:
                    core = tomllib.load(f)
                self.assertNotIn("escapekit", core.get("kits", {}))
            finally:
                os.chdir(cwd)


class TestCanonicalKitMetadata(unittest.TestCase):
    """Canonical manifests provide kit metadata without conf.toml."""

    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_read_kit_slug_prefers_canonical_manifest(self):
        from studio.commands.kit import _read_kit_slug

        with TemporaryDirectory() as td:
            kit_src = _make_canonical_kit_source(Path(td), "canon-slug")
            self.assertFalse((kit_src / "conf.toml").exists())
            self.assertEqual(_read_kit_slug(kit_src), "canon-slug")

    def test_install_dry_run_uses_canonical_slug_without_conf(self):
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_project(root)
            kit_src = _make_canonical_kit_source(Path(td), "canon-install")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src), "--dry-run"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "DRY_RUN")
                self.assertEqual(out["kit"], "canon-install")
            finally:
                os.chdir(cwd)

    def test_install_uses_canonical_manifest_resources_and_version(self):
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_canonical_kit_source(Path(td), "canon-install")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "copy"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["kit"], "canon-install")
                self.assertEqual(out["version"], "1.2.3")
                self.assertEqual(out["install_mode"], "copy")

                installed_skill = adapter / "config" / "kits" / "canon-install" / "SKILL.md"
                self.assertEqual(
                    installed_skill.read_text(encoding="utf-8"),
                    "---\nname: skill\ndescription: Canonical kit\n---\n# Canonical kit\n",
                )

                with open(adapter / "config" / "core.toml", "rb") as f:
                    core = tomllib.load(f)
                kit_entry = core["kits"]["canon-install"]
                self.assertEqual(kit_entry["version"], "1.2.3")
                self.assertEqual(kit_entry["install_mode"], "copy")
                self.assertEqual(kit_entry["resources"]["skill"]["path"], "config/kits/canon-install/SKILL.md")
            finally:
                os.chdir(cwd)

    def test_install_refuses_changed_user_modifiable_resource_without_approval(self):
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_canonical_kit_source(Path(td), "canon-install")
            installed_skill = adapter / "config" / "kits" / "canon-install" / "SKILL.md"
            installed_skill.parent.mkdir(parents=True, exist_ok=True)
            installed_skill.write_text("# User edit\n", encoding="utf-8")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install([
                        "--path", str(kit_src),
                        "--install-mode", "copy",
                        "--force",
                    ])
                self.assertEqual(rc, 2)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "FAIL")
                self.assertEqual(out["install_mode"], "copy")
                self.assertIn("--approve-overwrite skill", out["errors"][0])
                self.assertEqual(installed_skill.read_text(encoding="utf-8"), "# User edit\n")
            finally:
                os.chdir(cwd)

    def test_install_approved_changed_user_modifiable_resource_overwrites(self):
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_canonical_kit_source(Path(td), "canon-install")
            installed_skill = adapter / "config" / "kits" / "canon-install" / "SKILL.md"
            installed_skill.parent.mkdir(parents=True, exist_ok=True)
            installed_skill.write_text("# User edit\n", encoding="utf-8")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install([
                        "--path", str(kit_src),
                        "--install-mode", "copy",
                        "--force",
                        "--approve-overwrite", "skill",
                    ])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(
                    installed_skill.read_text(encoding="utf-8"),
                    "---\nname: skill\ndescription: Canonical kit\n---\n# Canonical kit\n",
                )
            finally:
                os.chdir(cwd)

    def test_update_auto_approve_declines_user_modifiable_resource_without_approval(self):
        from studio.commands.kit import cmd_kit_install, update_kit

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_canonical_kit_source(Path(td), "canon-install")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with redirect_stdout(io.StringIO()):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "copy"])
                self.assertEqual(rc, 0)
                installed_skill = adapter / "config" / "kits" / "canon-install" / "SKILL.md"
                installed_skill.write_text("# User edit\n", encoding="utf-8")
                (kit_src / "SKILL.md").write_text("# Upstream edit\n", encoding="utf-8")

                result = update_kit(
                    "canon-install",
                    kit_src,
                    adapter,
                    interactive=False,
                    auto_approve=True,
                    force=True,
                )

                self.assertEqual(result["version"]["status"], "partial")
                self.assertEqual(result["gen"]["files_written"], 0)
                self.assertEqual(result["gen_rejected"], ["SKILL.md"])
                self.assertEqual(installed_skill.read_text(encoding="utf-8"), "# User edit\n")
            finally:
                os.chdir(cwd)

    def test_update_approved_user_modifiable_resource_overwrites(self):
        from studio.commands.kit import cmd_kit_install, update_kit

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_canonical_kit_source(Path(td), "canon-install")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with redirect_stdout(io.StringIO()):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "copy"])
                self.assertEqual(rc, 0)
                installed_skill = adapter / "config" / "kits" / "canon-install" / "SKILL.md"
                installed_skill.write_text("# User edit\n", encoding="utf-8")
                (kit_src / "SKILL.md").write_text("# Upstream edit\n", encoding="utf-8")

                result = update_kit(
                    "canon-install",
                    kit_src,
                    adapter,
                    interactive=False,
                    auto_approve=True,
                    force=True,
                    approved_overwrites=["skill"],
                )

                self.assertEqual(result["version"]["status"], "updated")
                self.assertEqual(result["gen"]["files_written"], 1)
                self.assertEqual(installed_skill.read_text(encoding="utf-8"), "# Upstream edit\n")
            finally:
                os.chdir(cwd)

    def test_install_dangerous_tool_risk_requires_approval(self):
        from studio.commands.kit import cmd_kit_install
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_project(root)
            kit_src = _make_canonical_kit_source(Path(td), "risk-install")
            manifest = kit_src / ".cf-studio-kit.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8")
                + "\n[kits.resources.agent]\n"
                + 'tools = ["Bash"]\n',
                encoding="utf-8",
            )
            fingerprint = load_kit_model(kit_src).tool_risk_fingerprint
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install([
                        "--path", str(kit_src),
                        "--install-mode", "copy",
                    ])
                self.assertEqual(rc, 2)
                out = json.loads(buf.getvalue())
                self.assertIn(f"--approve-tool-risk {fingerprint}", out["errors"][0])

                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install([
                        "--path", str(kit_src),
                        "--install-mode", "copy",
                        "--approve-tool-risk", fingerprint,
                    ])
                self.assertEqual(rc, 0)
                self.assertEqual(json.loads(buf.getvalue())["status"], "PASS")
            finally:
                os.chdir(cwd)

    def test_update_dangerous_tool_risk_requires_approval_and_refreshes_core(self):
        from studio.commands.kit import cmd_kit_install, update_kit
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_canonical_kit_source(Path(td), "risk-update")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with redirect_stdout(io.StringIO()):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "copy"])
                self.assertEqual(rc, 0)

                manifest = kit_src / ".cf-studio-kit.toml"
                manifest.write_text(
                    manifest.read_text(encoding="utf-8")
                    + "\n[kits.resources.agent]\n"
                    + 'tools = ["Bash"]\n',
                    encoding="utf-8",
                )
                fingerprint = load_kit_model(kit_src).tool_risk_fingerprint

                result = update_kit(
                    "risk-update",
                    kit_src,
                    adapter,
                    interactive=False,
                )
                self.assertEqual(result["version"]["status"], "failed")
                self.assertIn(f"--approve-tool-risk {fingerprint}", result["errors"][0])

                result = update_kit(
                    "risk-update",
                    kit_src,
                    adapter,
                    interactive=False,
                    approved_tool_risks=[fingerprint],
                )
                self.assertIn(result["version"]["status"], {"current", "updated"})
                with open(adapter / "config" / "core.toml", "rb") as f:
                    entry = tomllib.load(f)["kits"]["risk-update"]
                self.assertEqual(entry["tool_risk_fingerprint"], fingerprint)
            finally:
                os.chdir(cwd)

    def test_install_canonical_manifest_noninteractive_requires_install_mode(self):
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_project(root)
            kit_src = _make_canonical_kit_source(Path(td), "canon-install")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src)])
                self.assertEqual(rc, 2)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "FAIL")
                self.assertIn("--install-mode", out["message"])
            finally:
                os.chdir(cwd)

    def test_update_path_rejects_version_selector(self):
        from studio.commands.kit import cmd_kit_update

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_kit_update(["--path", "/tmp/local-kit", "--version", "v1.2.3"])
        self.assertEqual(rc, 2)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "FAIL")
        self.assertIn("--version", out["message"])
        self.assertIn("--path", out["message"])


class TestCmdKitUpdate(unittest.TestCase):
    """CLI kit update command scenarios."""

    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_update_source_not_found(self):
        from studio.commands.kit import cmd_kit_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_project(root)
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["--path", str(Path(td) / "nonexistent")])
                self.assertEqual(rc, 2)
                out = json.loads(buf.getvalue())
                self.assertIn("not found", out["message"])
            finally:
                os.chdir(cwd)

    def test_update_no_project_root(self):
        from studio.commands.kit import cmd_kit_update
        with TemporaryDirectory() as td:
            kit_src = _make_kit_source(Path(td), "mykit")
            cwd = os.getcwd()
            try:
                os.chdir(td)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["--path", str(kit_src)])
                self.assertEqual(rc, 1)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "ERROR")
                self.assertIn("No project root found", out["message"])
            finally:
                os.chdir(cwd)

    def test_update_kit_not_installed_does_first_install(self):
        """update_kit handles first-install if kit is not yet installed."""
        from studio.commands.kit import cmd_kit_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "newkit")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["--path", str(kit_src)])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["results"][0]["action"], "created")
            finally:
                os.chdir(cwd)

    def test_update_dry_run(self):
        from studio.commands.kit import cmd_kit_update, install_kit
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "upkit")
            install_kit(kit_src, adapter, "upkit")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["--path", str(kit_src), "--dry-run"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
            finally:
                os.chdir(cwd)

    def test_update_auto_approve(self):
        from studio.commands.kit import cmd_kit_update, install_kit
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "autokit")
            install_kit(kit_src, adapter, "autokit")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["--path", str(kit_src), "--no-interactive", "-y"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
            finally:
                os.chdir(cwd)

    def test_update_same_version_skips(self):
        """Same version in source and installed → skip update."""
        from studio.commands.kit import cmd_kit_update, install_kit
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "vkit")
            install_kit(kit_src, adapter, "vkit")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["--path", str(kit_src)])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["results"][0]["action"], "current")
            finally:
                os.chdir(cwd)

    def test_update_path_uses_canonical_manifest_for_registered_kit(self):
        """cmd_kit_update --path honors .cf-studio-kit.toml for register-mode kits."""
        from studio.commands.kit import cmd_kit_install, cmd_kit_update

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_canonical_kit_source(root / "local-kits", "pathmanifest")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with redirect_stdout(io.StringIO()):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "register"])
                self.assertEqual(rc, 0)

                (kit_src / "SKILL.md").write_text("# Updated canonical kit\n", encoding="utf-8")
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["--path", str(kit_src)])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["results"][0]["action"], "current")
                self.assertNotIn("resource_bindings", out["results"][0])

                with open(adapter / "config" / "core.toml", "rb") as f:
                    entry = tomllib.load(f)["kits"]["pathmanifest"]
                self.assertEqual(entry["install_mode"], "register")
                self.assertNotIn("resources", entry)
            finally:
                os.chdir(cwd)

    def test_build_source_to_resource_mapping_uses_requested_canonical_slug(self):
        """Manifest source mapping must select the requested canonical kit entry."""
        from studio.utils.manifest import build_source_to_resource_mapping

        with TemporaryDirectory() as td:
            root = Path(td)
            kit_src = root / "multi-kit"
            kit_src.mkdir()
            (kit_src / "a-skill.md").write_text("# A\n", encoding="utf-8")
            (kit_src / "b-skill.md").write_text("# B\n", encoding="utf-8")
            (kit_src / ".cf-studio-kit.toml").write_text(
                "\n".join([
                    'manifest_version = "1.0"',
                    "",
                    "[[kits]]",
                    'slug = "kit-a"',
                    'version = "1.0"',
                    "",
                    "[[kits.resources]]",
                    'id = "skill_a"',
                    'kind = "skill"',
                    'source = "a-skill.md"',
                    'install_path = "SKILL.md"',
                    'type = "file"',
                    "",
                    "[[kits]]",
                    'slug = "kit-b"',
                    'version = "1.0"',
                    "",
                    "[[kits.resources]]",
                    'id = "skill_b"',
                    'kind = "skill"',
                    'source = "b-skill.md"',
                    'install_path = "SKILL.md"',
                    'type = "file"',
                ]) + "\n",
                encoding="utf-8",
            )

            mapping_a, info_a = build_source_to_resource_mapping(kit_src, kit_slug="kit-a")
            mapping_b, info_b = build_source_to_resource_mapping(kit_src, kit_slug="kit-b")

            self.assertEqual(mapping_a, {"a-skill.md": "skill_a"})
            self.assertEqual(mapping_b, {"b-skill.md": "skill_b"})
            self.assertIn("skill_a", info_a)
            self.assertNotIn("skill_b", info_a)
            self.assertIn("skill_b", info_b)
            self.assertNotIn("skill_a", info_b)

    def test_update_force_bypasses_version_check(self):
        """--force skips version check even if versions match."""
        from studio.commands.kit import cmd_kit_update, install_kit
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "fkit")
            install_kit(kit_src, adapter, "fkit")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["--path", str(kit_src), "--force"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                # With identical files, force still reports "current" (no actual diff)
                self.assertIn(out["results"][0]["action"], ("current", "updated"))
            finally:
                os.chdir(cwd)

    def test_update_offline_last_known_current_exits_success(self):
        from studio.commands.kit import cmd_kit_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "config/kits/sdlc",
                        "source": "github:o/r",
                        "version": "v1.0.0",
                    },
                },
            }, adapter / "config" / "core.toml")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with patch(
                    "studio.commands.kit._resolve_github_update_targets",
                    return_value=(
                        [],
                        [{
                            "kit": "sdlc",
                            "action": "current",
                            "message": "offline current",
                            "source": "github:o/r",
                            "authority": {
                                "resolver_mode": "offline_last_known",
                                "resolved_ref": "v1.0.0",
                                "freshness": "last_known",
                            },
                        }],
                    ),
                ):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = cmd_kit_update([])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["results"][0]["action"], "current")
                self.assertEqual(
                    out["results"][0]["authority"]["resolver_mode"],
                    "offline_last_known",
                )
            finally:
                os.chdir(cwd)

    def test_update_manifest_invalid_binding_fails(self):
        from studio.commands.kit import cmd_kit_update
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_manifest_kit_source(Path(td), "manifestfail")
            installed_dir = adapter / "config" / "kits" / "manifestfail"
            installed_dir.mkdir(parents=True)
            installed_skill = installed_dir / "SKILL.md"
            installed_skill.write_text("# Existing Skill\n", encoding="utf-8")
            invalid_binding = "/opt/cypilot/constraints.toml" if os.name == "nt" else "C:/external-kits/sdlc/constraints.toml"
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "manifestfail": {
                        "format": "CFS",
                        "path": "config/kits/manifestfail",
                        "version": "0",
                        "resources": {
                            "skill": {"path": "config/kits/manifestfail/SKILL.md"},
                            "agents": {"path": "config/kits/manifestfail/AGENTS.md"},
                            "constraints": {"path": invalid_binding},
                        },
                    },
                },
            }, adapter / "config" / "core.toml")

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["--path", str(kit_src), "--no-interactive", "-y"])
                self.assertEqual(rc, 2)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "FAIL")
                self.assertEqual(out["results"][0]["action"], "failed")
                self.assertTrue(any("not accessible on this OS" in err for err in out.get("errors", [])))
                self.assertEqual(installed_skill.read_text(encoding="utf-8"), "# Existing Skill\n")
            finally:
                os.chdir(cwd)

    def test_update_mixed_failed_run_returns_fail_and_skips_regen(self):
        import studio.commands.kit as kit_module
        from studio.commands.kit import cmd_kit_update
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src_a = _make_kit_source(Path(td), "akit")
            kit_src_b = _make_kit_source(Path(td), "bkit")
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "akit": {"format": "CFS", "path": "config/kits/akit", "version": "1", "source": "github:owner/akit"},
                    "bkit": {"format": "CFS", "path": "config/kits/bkit", "version": "1", "source": "github:owner/bkit"},
                },
            }, adapter / "config" / "core.toml")

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with patch.object(
                    kit_module,
                    "_resolve_github_update_targets",
                    return_value=([
                        ("akit", kit_src_a, "github:owner/akit", None),
                        ("bkit", kit_src_b, "github:owner/bkit", None),
                    ], []),
                ):
                    with patch.object(kit_module, "show_kit_whatsnew", return_value=True):
                        with patch.object(
                            kit_module,
                            "update_kit",
                            side_effect=[
                                {
                                    "kit": "akit",
                                    "version": {"status": "failed"},
                                    "gen": {"files_written": 0},
                                    "errors": ["binding resolution failed"],
                                },
                                {
                                    "kit": "bkit",
                                    "version": {"status": "updated"},
                                    "gen": {"files_written": 1, "accepted_files": ["SKILL.md"], "unchanged": 0},
                                },
                            ],
                        ):
                            with patch.object(kit_module, "regenerate_gen_aggregates") as regen_mock:
                                with redirect_stdout(buf):
                                    rc = cmd_kit_update([])
                self.assertEqual(rc, 2)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "FAIL")
                self.assertEqual([r["action"] for r in out["results"]], ["failed", "updated"])
                self.assertTrue(any("binding resolution failed" in err for err in out.get("errors", [])))
                regen_mock.assert_not_called()
            finally:
                os.chdir(cwd)

    def test_update_mixed_exception_run_returns_fail_and_skips_regen(self):
        import studio.commands.kit as kit_module
        from studio.commands.kit import cmd_kit_update
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src_a = _make_kit_source(Path(td), "akit")
            kit_src_b = _make_kit_source(Path(td), "bkit")
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "akit": {"format": "CFS", "path": "config/kits/akit", "version": "1", "source": "github:owner/akit"},
                    "bkit": {"format": "CFS", "path": "config/kits/bkit", "version": "1", "source": "github:owner/bkit"},
                },
            }, adapter / "config" / "core.toml")

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with patch.object(
                    kit_module,
                    "_resolve_github_update_targets",
                    return_value=([
                        ("akit", kit_src_a, "github:owner/akit", None),
                        ("bkit", kit_src_b, "github:owner/bkit", None),
                    ], []),
                ):
                    with patch.object(kit_module, "show_kit_whatsnew", return_value=True):
                        with patch.object(
                            kit_module,
                            "update_kit",
                            side_effect=[
                                RuntimeError("unexpected update error"),
                                {
                                    "kit": "bkit",
                                    "version": {"status": "updated"},
                                    "gen": {"files_written": 1, "accepted_files": ["SKILL.md"], "unchanged": 0},
                                },
                            ],
                        ):
                            with patch.object(kit_module, "regenerate_gen_aggregates") as regen_mock:
                                with redirect_stdout(buf):
                                    rc = cmd_kit_update([])
                self.assertEqual(rc, 2)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "FAIL")
                self.assertEqual([r["action"] for r in out["results"]], ["failed", "updated"])
                self.assertTrue(any("unexpected update error" in err for err in out.get("errors", [])))
                regen_mock.assert_not_called()
            finally:
                os.chdir(cwd)

    def test_check_updates_reports_github_update_command(self):
        import studio.commands.kit as kit_module
        from studio.commands.kit import cmd_kit_check_updates
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "sdlc")
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "config/kits/sdlc",
                        "version": "v1.0.0",
                        "source": "github:o/r",
                        "source_provenance": {
                            "source_type": "github",
                            "resolved_ref": "v1.0.0",
                        },
                    },
                },
            }, adapter / "config" / "core.toml")

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with patch.object(
                    kit_module,
                    "_resolve_registered_update_targets",
                    return_value=([
                        ("sdlc", kit_src, "github:o/r", None, {
                            "source_type": "github",
                            "resolved_ref": "v1.1.0",
                            "resolver_mode": "latest_release",
                            "resolution_basis": "github_release",
                            "freshness": "fresh",
                        }),
                    ], []),
                ):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = cmd_kit_check_updates([])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["updates_available"], 1)
                self.assertEqual(out["commands"], ["cfs kit update sdlc"])
                self.assertEqual(out["results"][0]["action"], "update_available")
                self.assertEqual(out["results"][0]["installed_ref"], "v1.0.0")
                self.assertEqual(out["results"][0]["latest_ref"], "v1.1.0")
            finally:
                os.chdir(cwd)

    def test_check_updates_reports_generic_git_commit_update(self):
        from studio.commands.kit import _kit_update_check_result

        result = _kit_update_check_result(
            "custom",
            {
                "source": "git:https://example.com/org/repo.git",
                "source_provenance": {"commit_sha": "old123"},
            },
            {
                "source_type": "git",
                "resolved_ref": "new456",
                "commit_sha": "new456",
                "canonical_source": "git:https://example.com/org/repo.git",
                "freshness": "fresh",
            },
        )

        self.assertEqual(result["action"], "update_available")
        self.assertEqual(result["command"], "cfs kit update custom")
        self.assertEqual(result["installed_commit"], "old123")
        self.assertEqual(result["latest_commit"], "new456")

    def test_check_updates_remote_failure_is_nonblocking_warn(self):
        import studio.commands.kit as kit_module
        from studio.commands.kit import cmd_kit_check_updates
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "config/kits/sdlc",
                        "version": "v1.0.0",
                        "source": "github:o/r",
                    },
                },
            }, adapter / "config" / "core.toml")

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with patch.object(
                    kit_module,
                    "_resolve_registered_update_targets",
                    return_value=([], [{
                        "kit": "sdlc",
                        "action": "failed",
                        "source": "github:o/r",
                        "message": "GitHub unavailable",
                    }]),
                ):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = cmd_kit_check_updates([])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "WARN")
                self.assertEqual(out["updates_available"], 0)
                self.assertEqual(out["results"][0]["action"], "failed")
                self.assertIn("GitHub unavailable", out["errors"][0])
            finally:
                os.chdir(cwd)


class TestKitHelpers(unittest.TestCase):
    def test_human_kit_install_covers_status_variants(self):
        from studio.commands.kit import _human_kit_install
        from studio.utils.ui import set_json_mode

        set_json_mode(False)
        try:
            cases = [
                {
                    "status": "DRY_RUN",
                    "kit": "drykit",
                    "version": "v1",
                    "action": "planned",
                    "source": "/src",
                    "target": "/dst",
                },
                {
                    "status": "PASS",
                    "kit": "okkit",
                    "version": "v2",
                    "action": "installed",
                    "files_written": 3,
                    "artifact_kinds": ["FEATURE", "ADR"],
                    "errors": ["non-fatal warning"],
                },
                {
                    "status": "FAIL",
                    "kit": "badkit",
                    "version": "v3",
                    "action": "failed",
                    "files_written": 0,
                    "message": "Install failed hard",
                    "hint": "Use a valid kit source",
                },
                {
                    "status": "ODD",
                    "kit": "oddkit",
                    "version": "v4",
                    "action": "weird",
                    "files_written": 1,
                },
            ]
            err = io.StringIO()
            with redirect_stderr(err):
                for case in cases:
                    _human_kit_install(case)
            rendered = err.getvalue()
            self.assertIn("Dry run", rendered)
            self.assertIn("FEATURE, ADR", rendered)
            self.assertIn("Use a valid kit source", rendered)
            self.assertIn("Status: ODD", rendered)
        finally:
            set_json_mode(True)

    def test_human_kit_update_covers_status_and_authority_variants(self):
        from studio.commands.kit import _human_kit_update
        from studio.utils.ui import set_json_mode

        set_json_mode(False)
        try:
            err = io.StringIO()
            with redirect_stderr(err):
                _human_kit_update({
                    "status": "PASS",
                    "kits_updated": 1,
                    "results": [{
                        "kit": "sdlc",
                        "action": "updated",
                        "accepted": ["SKILL.md"],
                        "declined": ["AGENTS.md"],
                        "unchanged": 2,
                        "authority": {
                            "resolution_basis": "latest_release",
                            "resolved_ref": "v2.0.0",
                            "commit_sha": "abc123",
                            "freshness": "fresh",
                        },
                    }],
                })
                _human_kit_update({
                    "status": "WARN",
                    "kits_updated": 0,
                    "results": [{"kit": "warnkit", "action": "current"}],
                    "errors": ["source warning"],
                })
                _human_kit_update({
                    "status": "FAIL",
                    "kits_updated": 0,
                    "results": [{
                        "kit": "offline",
                        "action": "current",
                        "authority": {"resolver_mode": "offline_last_known"},
                    }],
                })
            rendered = err.getvalue()
            self.assertIn("sdlc: updated", rendered)
            self.assertIn("basis=latest_release", rendered)
            self.assertIn("~ SKILL.md", rendered)
            self.assertIn("AGENTS.md (declined)", rendered)
            self.assertIn("source warning", rendered)
            self.assertIn("Status: FAIL", rendered)
        finally:
            set_json_mode(True)

    def test_build_kit_update_result_normalizes_errors_and_authority(self):
        from studio.commands.kit import (
            _build_kit_update_result,
            _normalize_kit_update_action,
        )

        self.assertEqual(_normalize_kit_update_action("ERROR"), "failed")
        self.assertEqual(_normalize_kit_update_action(" fail "), "failed")
        self.assertEqual(_normalize_kit_update_action(None), "")
        result = _build_kit_update_result("sdlc", {
            "version": "FAILED",
            "gen": "dry_run",
            "gen_rejected": ["AGENTS.md"],
            "errors": ["boom"],
            "authority": {"resolved_ref": "v1"},
            "prune_required": [
                {
                    "path": "old.md",
                    "action": "declined",
                    "prune_fingerprint": "abc123",
                },
            ],
        })
        self.assertEqual(result["action"], "failed")
        self.assertEqual(result["accepted"], [])
        self.assertEqual(result["declined"], ["AGENTS.md"])
        self.assertEqual(result["files_written"], 0)
        self.assertEqual(result["unchanged"], 0)
        self.assertEqual(result["errors"], ["boom"])
        self.assertEqual(result["authority"]["resolved_ref"], "v1")
        self.assertEqual(result["prune_required"][0]["prune_fingerprint"], "abc123")

    def test_resolve_github_update_targets_covers_source_branches(self):
        import studio.commands.kit as kit_module
        from studio.commands.kit import _resolve_github_update_targets
        from studio.utils.ui import set_json_mode

        set_json_mode(False)
        with TemporaryDirectory() as td:
            source_dir = Path(td) / "okkit"
            source_dir.mkdir()
            last_known = {
                "freshness": "last_known",
                "resolved_ref": "v1.0.0",
                "resolver_mode": "offline_last_known",
            }
            kits_map = {
                "missing": {},
                "local": {"source": "file:/tmp/kit"},
                "invalid": {"source": "github:not-enough-parts"},
                "ok": {"source": "github:owner/ok", "version": "v0.9.0"},
                "offline": {"source": "github:owner/offline", "version": "v1.0.0"},
                "broken": {"source": "github:owner/broken", "version": "v0.1.0"},
            }
            try:
                with patch.object(
                    kit_module,
                    "_download_kit_from_github_with_authority",
                    side_effect=[
                        (source_dir, "v2.0.0", {"resolved_ref": "v2.0.0"}),
                        RuntimeError("network unavailable"),
                        RuntimeError("tarball unavailable"),
                    ],
                ):
                    with patch.object(
                        kit_module,
                        "_resolve_github_ref",
                        side_effect=[last_known, RuntimeError("still unavailable")],
                    ):
                        err = io.StringIO()
                        with redirect_stderr(err):
                            targets, failures = _resolve_github_update_targets(kits_map)
                self.assertEqual(len(targets), 1)
                self.assertEqual(targets[0][0], "ok")
                by_kit = {failure["kit"]: failure for failure in failures}
                self.assertEqual(by_kit["missing"]["action"], "ERROR")
                self.assertEqual(by_kit["local"]["action"], "ERROR")
                self.assertEqual(by_kit["invalid"]["action"], "ERROR")
                self.assertEqual(by_kit["offline"]["action"], "current")
                self.assertEqual(by_kit["broken"]["action"], "failed")
            finally:
                set_json_mode(True)

    def test_read_kit_version_valid(self):
        from studio.commands.kit import _read_kit_version
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            p = Path(td) / "conf.toml"
            toml_utils.dump({"version": 2}, p)
            self.assertEqual(_read_kit_version(p), "2")

    def test_read_kit_version_missing(self):
        from studio.commands.kit import _read_kit_version
        self.assertEqual(_read_kit_version(Path("/nonexistent/conf.toml")), "")

    def test_read_kit_version_no_key(self):
        from studio.commands.kit import _read_kit_version
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            p = Path(td) / "conf.toml"
            toml_utils.dump({"other": "data"}, p)
            self.assertEqual(_read_kit_version(p), "")

    def test_register_kit_in_core_toml(self):
        from studio.commands.kit import _register_kit_in_core_toml
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            config_dir = Path(td) / "config"
            config_dir.mkdir()
            toml_utils.dump({"version": "1.0", "kits": {}}, config_dir / "core.toml")
            _register_kit_in_core_toml(config_dir, "mykit", "1", Path(td))
            import tomllib
            with open(config_dir / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertIn("mykit", data["kits"])
            self.assertEqual(data["kits"]["mykit"]["path"], "config/kits/mykit")

    def test_register_kit_no_core_toml(self):
        """No core.toml → does nothing, no error."""
        from studio.commands.kit import _register_kit_in_core_toml
        with TemporaryDirectory() as td:
            _register_kit_in_core_toml(Path(td), "nokit", "1", Path(td))

    def test_register_kit_corrupt_core_toml(self):
        """Corrupt core.toml → does nothing, no error."""
        from studio.commands.kit import _register_kit_in_core_toml
        with TemporaryDirectory() as td:
            config_dir = Path(td)
            (config_dir / "core.toml").write_text("{{invalid", encoding="utf-8")
            _register_kit_in_core_toml(config_dir, "nokit", "1", Path(td))

    def test_read_conf_version_handles_valid_missing_and_invalid(self):
        from studio.commands.kit import _read_conf_version
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            root = Path(td)
            valid = root / "valid.toml"
            missing_version = root / "missing_version.toml"
            invalid = root / "invalid.toml"
            toml_utils.dump({"version": "7"}, valid)
            toml_utils.dump({"other": "value"}, missing_version)
            invalid.write_text("version = 'not-an-int'\n", encoding="utf-8")

            self.assertEqual(_read_conf_version(valid), 7)
            self.assertEqual(_read_conf_version(missing_version), 0)
            self.assertEqual(_read_conf_version(invalid), 0)
            self.assertEqual(_read_conf_version(root / "absent.toml"), 0)

    def test_layout_copy_backup_restore_helpers(self):
        from studio.commands.kit import (
            _backup_existing_config_kit,
            _copy_legacy_kit_item,
            _restore_existing_config_kit,
        )

        with TemporaryDirectory() as td:
            root = Path(td)
            source_dir = root / "source_dir"
            source_dir.mkdir()
            (source_dir / "new.txt").write_text("new", encoding="utf-8")
            dst_dir = root / "dst_dir"
            dst_dir.mkdir()
            (dst_dir / "old.txt").write_text("old", encoding="utf-8")

            _copy_legacy_kit_item(source_dir, dst_dir)
            self.assertFalse((dst_dir / "old.txt").exists())
            self.assertEqual((dst_dir / "new.txt").read_text(encoding="utf-8"), "new")

            source_file = root / "source.txt"
            source_file.write_text("source", encoding="utf-8")
            existing_file = root / "existing.txt"
            existing_file.write_text("keep", encoding="utf-8")
            _copy_legacy_kit_item(source_file, existing_file)
            self.assertEqual(existing_file.read_text(encoding="utf-8"), "keep")
            copied_file = root / "copied.txt"
            _copy_legacy_kit_item(source_file, copied_file)
            self.assertEqual(copied_file.read_text(encoding="utf-8"), "source")

            config_kit = root / "config" / "kits" / "sdlc"
            config_kit.mkdir(parents=True)
            (config_kit / "SKILL.md").write_text("original", encoding="utf-8")
            backup = _backup_existing_config_kit(config_kit, root / "backup" / "sdlc")
            shutil.rmtree(config_kit)
            _restore_existing_config_kit(backup, config_kit)
            self.assertEqual((config_kit / "SKILL.md").read_text(encoding="utf-8"), "original")

            shutil.rmtree(config_kit)
            _restore_existing_config_kit(root / "missing_backup", config_kit)
            self.assertFalse(config_kit.exists())

    def test_migrate_single_kits_dir_entry_success_and_rollback(self):
        import studio.commands.kit as kit_module
        from studio.commands.kit import _migrate_single_kits_dir_entry

        with TemporaryDirectory() as td:
            root = Path(td)
            kit_dir = root / "kits" / "sdlc"
            (kit_dir / "docs").mkdir(parents=True)
            (kit_dir / "docs" / "guide.md").write_text("guide", encoding="utf-8")
            (kit_dir / "conf.toml").write_text("version = 1\n", encoding="utf-8")
            (kit_dir / "blueprints").mkdir()
            (kit_dir / "blueprints" / "skip.md").write_text("skip", encoding="utf-8")
            config_kits = root / "config" / "kits"
            config_kits.mkdir(parents=True)
            backup_dir = root / ".layout_backup"

            result = _migrate_single_kits_dir_entry(kit_dir, config_kits, backup_dir)
            self.assertEqual(result, "migrated")
            self.assertEqual((config_kits / "sdlc" / "docs" / "guide.md").read_text(encoding="utf-8"), "guide")
            self.assertFalse((config_kits / "sdlc" / "blueprints").exists())

            (config_kits / "sdlc" / "SKILL.md").write_text("existing", encoding="utf-8")
            with patch.object(kit_module.os, "replace", side_effect=OSError("replace failed")):
                result = _migrate_single_kits_dir_entry(kit_dir, config_kits, backup_dir)
            self.assertTrue(result.startswith("FAILED: replace failed"))
            self.assertEqual((config_kits / "sdlc" / "SKILL.md").read_text(encoding="utf-8"), "existing")

    def test_migrate_single_gen_kit_entry_success_and_rollback(self):
        import studio.commands.kit as kit_module
        from studio.commands.kit import _migrate_single_gen_kit_entry

        with TemporaryDirectory() as td:
            root = Path(td)
            gen_kit = root / ".gen" / "kits" / "sdlc"
            (gen_kit / "agents").mkdir(parents=True)
            (gen_kit / "agents" / "A.md").write_text("agent", encoding="utf-8")
            (gen_kit / "SKILL.md").write_text("generated", encoding="utf-8")
            config_kits = root / "config" / "kits"
            config_kit = config_kits / "sdlc"
            config_kit.mkdir(parents=True)
            (config_kit / "SKILL.md").write_text("existing", encoding="utf-8")
            backup_dir = root / ".layout_backup"

            result = _migrate_single_gen_kit_entry(gen_kit, config_kits, backup_dir)
            self.assertEqual(result, "migrated")
            self.assertEqual((config_kit / "SKILL.md").read_text(encoding="utf-8"), "existing")
            self.assertEqual((config_kit / "agents" / "A.md").read_text(encoding="utf-8"), "agent")

            with patch.object(kit_module.os, "replace", side_effect=OSError("replace failed")):
                result = _migrate_single_gen_kit_entry(gen_kit, config_kits, backup_dir)
            self.assertTrue(result.startswith("FAILED: replace failed"))
            self.assertEqual((config_kit / "SKILL.md").read_text(encoding="utf-8"), "existing")

    def test_update_core_toml_kit_paths_rewrites_only_legacy_paths(self):
        from studio.commands.kit import _update_core_toml_kit_paths
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            config_dir = Path(td) / "config"
            config_dir.mkdir()
            _update_core_toml_kit_paths(config_dir)

            core = config_dir / "core.toml"
            toml_utils.dump({
                "version": "1.0",
                "kits": {
                    "from_gen": {"path": ".gen/kits/from_gen"},
                    "from_kits": {"path": "kits/from_kits"},
                    "current": {"path": "config/kits/current"},
                    "string": "ignored",
                },
            }, core)

            _update_core_toml_kit_paths(config_dir)
            with open(core, "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(data["kits"]["from_gen"]["path"], "config/kits/from_gen")
            self.assertEqual(data["kits"]["from_kits"]["path"], "config/kits/from_kits")
            self.assertEqual(data["kits"]["current"]["path"], "config/kits/current")
            self.assertEqual(data["kits"]["string"], "ignored")


class TestResolveRegisteredKitDir(unittest.TestCase):
    def test_relative_custom_path_resolves_under_adapter(self):
        from studio.commands.kit import _resolve_registered_kit_dir
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            adapter.mkdir()
            resolved = _resolve_registered_kit_dir(adapter, "custom-kits/sdlc")
            self.assertEqual(resolved, (adapter / "custom-kits" / "sdlc").resolve())

    def test_posix_absolute_path_is_rejected(self):
        from studio.commands.kit import _resolve_registered_kit_dir
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            adapter.mkdir()
            external = Path(td) / "external-kits" / "sdlc"
            resolved = _resolve_registered_kit_dir(adapter, external.as_posix())
            self.assertIsNone(resolved)

    def test_windows_drive_absolute_path_not_project_relative_on_non_windows(self):
        from studio.commands.kit import _resolve_registered_kit_dir
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            adapter.mkdir()
            resolved = _resolve_registered_kit_dir(adapter, "C:/external-kits/sdlc")
            if os.name == "nt":
                self.assertIsNotNone(resolved)
                self.assertTrue(resolved.is_absolute())
            else:
                self.assertIsNone(resolved)

    def test_windows_backslash_absolute_path_not_project_relative_on_non_windows(self):
        from studio.commands.kit import _resolve_registered_kit_dir
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            adapter.mkdir()
            resolved = _resolve_registered_kit_dir(adapter, r"C:\external-kits\sdlc")
            if os.name == "nt":
                self.assertIsNotNone(resolved)
                self.assertTrue(resolved.is_absolute())
            else:
                self.assertIsNone(resolved)


class TestSerializeManifestBindingPath(unittest.TestCase):
    def test_preserves_windows_drive_absolute_path_when_relpath_raises(self):
        import studio.commands.kit as kit_module
        from studio.commands.kit import _serialize_manifest_binding_path

        with patch.object(
            kit_module.os.path,
            "relpath",
            side_effect=ValueError("path is on mount 'D:', start on mount 'C:'"),
        ):
            binding = _serialize_manifest_binding_path(
                PureWindowsPath("D:/external-kits/sdlc/SKILL.md"),
                Path("project/.bootstrap"),
            )

        self.assertEqual(binding, "D:/external-kits/sdlc/SKILL.md")


class TestCmdKitInstall(unittest.TestCase):
    """Cover cmd_kit_install CLI command."""

    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_install_invalid_source(self):
        from studio.commands.kit import cmd_kit_install
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_kit_install(["--path", "/nonexistent/path/to/kit"])
        self.assertEqual(rc, 2)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "FAIL")

    def test_install_no_project_root(self):
        from studio.commands.kit import cmd_kit_install
        with TemporaryDirectory() as td:
            kit_src = _make_kit_source(Path(td), "testkit")
            cwd = os.getcwd()
            try:
                os.chdir(td)
                # Remove .git so no project root is found
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "copy"])
                self.assertEqual(rc, 1)
            finally:
                os.chdir(cwd)

    def test_install_no_cypilot_dir(self):
        from studio.commands.kit import cmd_kit_install
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            (root / "AGENTS.md").write_text("# nothing\n", encoding="utf-8")
            kit_src = _make_kit_source(Path(td), "testkit")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "copy"])
                self.assertEqual(rc, 1)
            finally:
                os.chdir(cwd)

    def test_install_already_exists(self):
        from studio.commands.kit import cmd_kit_install
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "testkit")
            (adapter / "config" / "kits" / "testkit").mkdir(parents=True)
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "copy"])
                self.assertEqual(rc, 2)
                out = json.loads(buf.getvalue())
                self.assertIn("already installed", out["message"])
            finally:
                os.chdir(cwd)

    def test_install_already_exists_at_registered_custom_root(self):
        from studio.commands.kit import cmd_kit_install
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "testkit")
            custom_kit_dir = adapter / "custom-kits" / "testkit"
            custom_kit_dir.mkdir(parents=True)
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "testkit": {
                        "format": "CFS",
                        "path": "custom-kits/testkit",
                        "version": "1",
                    }
                },
            }, adapter / "config" / "core.toml")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "copy"])
                self.assertEqual(rc, 2)
                out = json.loads(buf.getvalue())
                self.assertIn("already installed", out["message"])
                self.assertIn(str(custom_kit_dir), out["message"])
                self.assertTrue(custom_kit_dir.is_dir())
                self.assertFalse((adapter / "config" / "kits" / "testkit").exists())
            finally:
                os.chdir(cwd)

    def test_install_dry_run(self):
        from studio.commands.kit import cmd_kit_install
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "testkit")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src), "--dry-run"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "DRY_RUN")
            finally:
                os.chdir(cwd)

    def test_install_success(self):
        from studio.commands.kit import cmd_kit_install
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "testkit")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "copy"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["kit"], "testkit")
            finally:
                os.chdir(cwd)

    def test_install_with_force(self):
        from studio.commands.kit import cmd_kit_install
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "testkit")
            (adapter / "config" / "kits" / "testkit").mkdir(parents=True)
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src), "--force", "--install-mode", "copy"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
            finally:
                os.chdir(cwd)

    def test_install_with_force_uses_registered_custom_root(self):
        from studio.commands.kit import cmd_kit_install
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "testkit")
            custom_kit_dir = adapter / "custom-kits" / "testkit"
            custom_kit_dir.mkdir(parents=True)
            (custom_kit_dir / "SKILL.md").write_text("# Old Skill\n", encoding="utf-8")
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "testkit": {
                        "format": "CFS",
                        "path": "custom-kits/testkit",
                        "version": "1",
                    }
                },
            }, adapter / "config" / "core.toml")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src), "--force", "--install-mode", "copy"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
            finally:
                os.chdir(cwd)

            self.assertTrue((custom_kit_dir / "SKILL.md").is_file())
            self.assertFalse((adapter / "config" / "kits" / "testkit").exists())
            with open(adapter / "config" / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(data["kits"]["testkit"]["path"], "custom-kits/testkit")

    def test_install_with_force_uses_registered_custom_root_for_manifest_kit(self):
        from studio.commands.kit import cmd_kit_install
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_manifest_kit_source(Path(td), "testkit")
            custom_kit_dir = adapter / "custom-kits" / "testkit"
            custom_kit_dir.mkdir(parents=True)
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "testkit": {
                        "format": "CFS",
                        "path": "custom-kits/testkit",
                        "version": "1",
                    }
                },
            }, adapter / "config" / "core.toml")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src), "--force", "--install-mode", "copy"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
            finally:
                os.chdir(cwd)

            self.assertTrue((custom_kit_dir / "SKILL.md").is_file())
            self.assertTrue((custom_kit_dir / "AGENTS.md").is_file())
            self.assertFalse((adapter / "config" / "kits" / "testkit").exists())
            with open(adapter / "config" / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(data["kits"]["testkit"]["path"], "custom-kits/testkit")

    def test_install_manifest_custom_root_preserves_absolute_path_when_relpath_raises(self):
        import studio.commands.kit as kit_module
        from studio.commands.kit import install_kit
        import tomllib
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_manifest_kit_source(Path(td), "customroot")
            manifest_path = kit_src / "manifest.toml"
            manifest_path.write_text(
                manifest_path.read_text(encoding="utf-8").replace(
                    "user_modifiable = false",
                    "user_modifiable = true",
                    1,
                ),
                encoding="utf-8",
            )
            external_kit_dir = (Path(td) / "external-kits" / "customroot").resolve()

            original_relpath = kit_module.os.path.relpath

            def _patched_relpath(path, start):
                if os.fspath(path).startswith(external_kit_dir.as_posix()):
                    raise ValueError("path is on mount 'D:', start on mount 'C:'")
                return original_relpath(path, start)

            fake_stdin = type("_FakeStdin", (), {"isatty": lambda self: True})()
            inputs = iter(["y", "1", external_kit_dir.as_posix(), "n"])

            with patch.object(kit_module.sys, "stdin", fake_stdin):
                with patch("builtins.input", side_effect=lambda prompt: next(inputs)):
                    with patch.object(kit_module.os.path, "relpath", side_effect=_patched_relpath):
                        result = install_kit(kit_src, adapter, "customroot", interactive=True)

            self.assertEqual(result["status"], "PASS")
            self.assertTrue((external_kit_dir / "SKILL.md").is_file())
            with open(adapter / "config" / "core.toml", "rb") as f:
                data = tomllib.load(f)
            resources = data["kits"]["customroot"]["resources"]
            self.assertEqual(data["kits"]["customroot"]["path"], external_kit_dir.as_posix())
            self.assertEqual(resources["skill"]["path"], f"{external_kit_dir.as_posix()}/SKILL.md")
            self.assertEqual(resources["agents"]["path"], f"{external_kit_dir.as_posix()}/AGENTS.md")
            self.assertEqual(resources["constraints"]["path"], f"{external_kit_dir.as_posix()}/constraints.toml")

    def test_install_with_force_manifest_preserves_absolute_bindings_when_relpath_raises(self):
        import studio.commands.kit as kit_module
        from studio.commands.kit import cmd_kit_install
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_manifest_kit_source(Path(td), "testkit")
            external_kit_dir = (Path(td) / "external-kits" / "testkit").resolve()
            registered_path = "D:/external-kits/testkit"
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "testkit": {
                        "format": "CFS",
                        "path": registered_path,
                        "version": "1",
                    }
                },
            }, adapter / "config" / "core.toml")

            original_resolve_registered_kit_dir = kit_module._resolve_registered_kit_dir
            original_relpath = kit_module.os.path.relpath

            def _patched_resolve_registered_kit_dir(cypilot_dir, registered_kit_path):
                if registered_kit_path == registered_path:
                    return external_kit_dir
                return original_resolve_registered_kit_dir(cypilot_dir, registered_kit_path)

            def _patched_relpath(path, start):
                if os.fspath(path).startswith(external_kit_dir.as_posix()):
                    raise ValueError("path is on mount 'D:', start on mount 'C:'")
                return original_relpath(path, start)

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with patch.object(
                    kit_module,
                    "_resolve_registered_kit_dir",
                    side_effect=_patched_resolve_registered_kit_dir,
                ):
                    with patch.object(kit_module.os.path, "relpath", side_effect=_patched_relpath):
                        with redirect_stdout(buf):
                            rc = cmd_kit_install(["--path", str(kit_src), "--force", "--install-mode", "copy"])
                self.assertEqual(rc, 2)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "FAIL")
                self.assertIn("relative paths", " ".join(out.get("errors", [])))
            finally:
                os.chdir(cwd)

    def test_install_slug_from_conf_toml(self):
        """Kit slug is read from conf.toml slug field."""
        from studio.commands.kit import cmd_kit_install
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "rawdir")
            toml_utils.dump({"slug": "custom-slug", "version": 1}, kit_src / "conf.toml")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install(["--path", str(kit_src), "--install-mode", "copy"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["kit"], "custom-slug")
            finally:
                os.chdir(cwd)


class TestDetectAndMigrateLayoutLegacy(unittest.TestCase):
    """Cover _detect_and_migrate_layout — legacy layout migration."""

    def test_no_migration_needed(self):
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            (adapter / "config" / "kits" / "sdlc").mkdir(parents=True)
            result = _detect_and_migrate_layout(adapter)
            self.assertEqual(result, {})

    def test_dry_run_kits_dir(self):
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            kits_dir = adapter / "kits" / "sdlc"
            kits_dir.mkdir(parents=True)
            (kits_dir / "conf.toml").write_text("version = 1\n", encoding="utf-8")
            result = _detect_and_migrate_layout(adapter, dry_run=True)
            self.assertIn("sdlc", result)
            self.assertEqual(result["sdlc"], "would_migrate")
            # Verify kits/ dir still exists (dry run)
            self.assertTrue(kits_dir.is_dir())

    def test_migrate_kits_dir(self):
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            kits_dir = adapter / "kits" / "sdlc"
            kits_dir.mkdir(parents=True)
            (kits_dir / "conf.toml").write_text("version = 1\n", encoding="utf-8")
            (kits_dir / "artifacts").mkdir()
            (kits_dir / "artifacts" / "PRD.md").write_text("# PRD\n", encoding="utf-8")
            # Legacy artifacts to skip
            bp_dir = kits_dir / "blueprints"
            bp_dir.mkdir()
            (bp_dir / "DESIGN.md").write_text("blueprint\n", encoding="utf-8")
            result = _detect_and_migrate_layout(adapter)
            self.assertEqual(result["sdlc"], "migrated")
            config_kit = adapter / "config" / "kits" / "sdlc"
            self.assertTrue((config_kit / "conf.toml").is_file())
            self.assertTrue((config_kit / "artifacts" / "PRD.md").is_file())
            # Blueprints should NOT be copied
            self.assertFalse((config_kit / "blueprints").exists())
            # Old kits/ dir should be removed
            self.assertFalse((adapter / "kits").is_dir())

    def test_migrate_gen_kits_dir(self):
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            gen_kit = adapter / ".gen" / "kits" / "sdlc"
            gen_kit.mkdir(parents=True)
            (gen_kit / "SKILL.md").write_text("# Skill\n", encoding="utf-8")

            result = _detect_and_migrate_layout(adapter)

            self.assertIn("sdlc", result)
            config_kit = adapter / "config" / "kits" / "sdlc"
            self.assertTrue((config_kit / "SKILL.md").is_file())
            # .gen/kits/ should be removed
            self.assertFalse((adapter / ".gen" / "kits").is_dir())

    def test_migrate_updates_core_toml_paths(self):
        from studio.commands.kit import _detect_and_migrate_layout
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            kits_dir = adapter / "kits" / "sdlc"
            kits_dir.mkdir(parents=True)
            (kits_dir / "conf.toml").write_text("v=1\n", encoding="utf-8")
            config_dir = adapter / "config"
            config_dir.mkdir(parents=True)
            toml_utils.dump({
                "kits": {"sdlc": {"path": "kits/sdlc", "format": "CFS"}},
            }, config_dir / "core.toml")
            _detect_and_migrate_layout(adapter)
            import tomllib
            with open(config_dir / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(data["kits"]["sdlc"]["path"], "config/kits/sdlc")

    def test_migrate_with_subdir(self):
        """Migration copies subdirectories from kits/{slug}/."""
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            kits_dir = adapter / "kits" / "sdlc"
            (kits_dir / "artifacts" / "DESIGN").mkdir(parents=True)
            (kits_dir / "artifacts" / "DESIGN" / "template.md").write_text("# T\n", encoding="utf-8")
            (kits_dir / "conf.toml").write_text("version = 1\n", encoding="utf-8")
            _detect_and_migrate_layout(adapter)
            config_kit = adapter / "config" / "kits" / "sdlc"
            self.assertTrue((config_kit / "artifacts" / "DESIGN" / "template.md").is_file())

    def test_dry_run_gen_kits(self):
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            gen_kit = adapter / ".gen" / "kits" / "sdlc"
            gen_kit.mkdir(parents=True)
            (gen_kit / "SKILL.md").write_text("# S\n", encoding="utf-8")
            result = _detect_and_migrate_layout(adapter, dry_run=True)
            self.assertEqual(result["sdlc"], "would_migrate")
            # .gen/kits/ should still exist (dry run)
            self.assertTrue(gen_kit.is_dir())


class TestDetectAndMigrateLayout(unittest.TestCase):
    """Cover _detect_and_migrate_layout — legacy layout migration."""

    def test_no_migration_needed(self):
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            (adapter / "config" / "kits" / "sdlc").mkdir(parents=True)
            result = _detect_and_migrate_layout(adapter)
            self.assertEqual(result, {})

    def test_dry_run_kits_dir(self):
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            kits_dir = adapter / "kits" / "sdlc"
            kits_dir.mkdir(parents=True)
            (kits_dir / "conf.toml").write_text("version = 1\n", encoding="utf-8")
            result = _detect_and_migrate_layout(adapter, dry_run=True)
            self.assertIn("sdlc", result)
            self.assertEqual(result["sdlc"], "would_migrate")
            # Verify kits/ dir still exists (dry run)
            self.assertTrue(kits_dir.is_dir())

    def test_migrate_kits_dir(self):
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            kits_dir = adapter / "kits" / "sdlc"
            kits_dir.mkdir(parents=True)
            (kits_dir / "conf.toml").write_text("version = 1\n", encoding="utf-8")
            (kits_dir / "artifacts").mkdir()
            (kits_dir / "artifacts" / "PRD.md").write_text("# PRD\n", encoding="utf-8")
            # Legacy artifacts to skip
            bp_dir = kits_dir / "blueprints"
            bp_dir.mkdir()
            (bp_dir / "DESIGN.md").write_text("blueprint\n", encoding="utf-8")
            result = _detect_and_migrate_layout(adapter)
            self.assertEqual(result["sdlc"], "migrated")
            config_kit = adapter / "config" / "kits" / "sdlc"
            self.assertTrue((config_kit / "conf.toml").is_file())
            self.assertTrue((config_kit / "artifacts" / "PRD.md").is_file())
            # Blueprints should NOT be copied
            self.assertFalse((config_kit / "blueprints").exists())
            # Old kits/ dir should be removed
            self.assertFalse((adapter / "kits").is_dir())

    def test_migrate_gen_kits_dir(self):
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            gen_kit = adapter / ".gen" / "kits" / "sdlc"
            gen_kit.mkdir(parents=True)
            (gen_kit / "SKILL.md").write_text("# Skill\n", encoding="utf-8")

            result = _detect_and_migrate_layout(adapter)

            self.assertIn("sdlc", result)
            config_kit = adapter / "config" / "kits" / "sdlc"
            self.assertTrue((config_kit / "SKILL.md").is_file())
            # .gen/kits/ should be removed
            self.assertFalse((adapter / ".gen" / "kits").is_dir())

    def test_migrate_updates_core_toml_paths(self):
        from studio.commands.kit import _detect_and_migrate_layout
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            kits_dir = adapter / "kits" / "sdlc"
            kits_dir.mkdir(parents=True)
            (kits_dir / "conf.toml").write_text("v=1\n", encoding="utf-8")
            config_dir = adapter / "config"
            config_dir.mkdir(parents=True)
            toml_utils.dump({
                "kits": {"sdlc": {"path": "kits/sdlc", "format": "CFS"}},
            }, config_dir / "core.toml")
            _detect_and_migrate_layout(adapter)
            import tomllib
            with open(config_dir / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(data["kits"]["sdlc"]["path"], "config/kits/sdlc")

    def test_migrate_with_subdir(self):
        """Migration copies subdirectories from kits/{slug}/."""
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            kits_dir = adapter / "kits" / "sdlc"
            (kits_dir / "artifacts" / "DESIGN").mkdir(parents=True)
            (kits_dir / "artifacts" / "DESIGN" / "template.md").write_text("# T\n", encoding="utf-8")
            (kits_dir / "conf.toml").write_text("version = 1\n", encoding="utf-8")
            _detect_and_migrate_layout(adapter)
            config_kit = adapter / "config" / "kits" / "sdlc"
            self.assertTrue((config_kit / "artifacts" / "DESIGN" / "template.md").is_file())

    def test_dry_run_gen_kits(self):
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            gen_kit = adapter / ".gen" / "kits" / "sdlc"
            gen_kit.mkdir(parents=True)
            (gen_kit / "SKILL.md").write_text("# S\n", encoding="utf-8")
            result = _detect_and_migrate_layout(adapter, dry_run=True)
            self.assertEqual(result["sdlc"], "would_migrate")
            # .gen/kits/ should still exist (dry run)
            self.assertTrue(gen_kit.is_dir())


class TestCmdKitMigrateDeprecated(unittest.TestCase):
    """cmd_kit_migrate redirects to cmd_kit_update."""

    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_migrate_warns_and_returns_error(self):
        from studio.commands.kit import cmd_kit_migrate
        err = io.StringIO()
        with redirect_stderr(err):
            rc = cmd_kit_migrate([])
        self.assertEqual(rc, 1)
        self.assertIn("deprecated", err.getvalue().lower())
        self.assertIn("kit update", err.getvalue())


class TestCmdKitDispatcherRoutes(unittest.TestCase):
    """Cover cmd_kit routing to install, update, migrate subcommands."""

    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_route_install(self):
        from studio.commands.kit import cmd_kit
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_kit(["install", "--path", "/nonexistent"])
        self.assertEqual(rc, 2)

    def test_route_update(self):
        from studio.commands.kit import cmd_kit
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_project(root)
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit(["update", "--path", "/nonexistent"])
                self.assertEqual(rc, 2)
            finally:
                os.chdir(cwd)

    def test_route_migrate(self):
        from studio.commands.kit import cmd_kit
        with TemporaryDirectory() as td:
            cwd = os.getcwd()
            try:
                os.chdir(td)
                err = io.StringIO()
                buf = io.StringIO()
                with redirect_stderr(err), redirect_stdout(buf):
                    rc = cmd_kit(["migrate"])
                self.assertIn("deprecated", err.getvalue().lower())
            finally:
                os.chdir(cwd)


class TestUpdateKitExistingBranch(unittest.TestCase):
    """Cover update_kit when kit already exists (file-level diff path)."""

    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_update_existing_kit_auto_approve(self):
        from studio.commands.kit import update_kit, install_kit
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "ukit")
            install_kit(kit_src, adapter, "ukit")
            # Modify source to create a diff
            (kit_src / "SKILL.md").write_text("# Updated Skill\n", encoding="utf-8")
            result = update_kit("ukit", kit_src, adapter, auto_approve=True)
            self.assertEqual(result["kit"], "ukit")
            self.assertIn(result["version"]["status"], ("updated", "current"))

    def test_update_existing_kit_non_interactive(self):
        from studio.commands.kit import update_kit, install_kit
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "ukit2")
            install_kit(kit_src, adapter, "ukit2")
            (kit_src / "SKILL.md").write_text("# Changed\n", encoding="utf-8")
            result = update_kit("ukit2", kit_src, adapter, interactive=False)
            # Non-interactive declines changes
            self.assertIn(result["version"]["status"], ("partial", "current"))

    def test_update_kit_dry_run(self):
        from studio.commands.kit import update_kit
        with TemporaryDirectory() as td:
            adapter = Path(td) / "cypilot"
            adapter.mkdir()
            result = update_kit("test", Path(td), adapter, dry_run=True)
            self.assertEqual(result["version"]["status"], "dry_run")

    def test_update_existing_with_declined(self):
        from studio.commands.kit import update_kit, install_kit
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "dkit")
            install_kit(kit_src, adapter, "dkit")
            # Modify source
            (kit_src / "constraints.toml").write_text("[changed]\nx = 1\n", encoding="utf-8")
            result = update_kit("dkit", kit_src, adapter, interactive=False)
            if result.get("gen_rejected"):
                self.assertIsInstance(result["gen_rejected"], list)

    def test_update_same_version_current_at_registered_custom_root(self):
        from studio.commands.kit import install_kit, update_kit
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "customcurrent")
            install_kit(kit_src, adapter, "customcurrent")
            default_kit_dir = adapter / "config" / "kits" / "customcurrent"
            custom_kit_dir = adapter / "custom-kits" / "customcurrent"
            custom_kit_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(default_kit_dir), str(custom_kit_dir))
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "customcurrent": {
                        "format": "CFS",
                        "path": "custom-kits/customcurrent",
                        "version": "1",
                    }
                },
            }, adapter / "config" / "core.toml")

            result = update_kit("customcurrent", kit_src, adapter)

            self.assertEqual(result["version"]["status"], "current")
            self.assertTrue(custom_kit_dir.is_dir())
            self.assertFalse(default_kit_dir.exists())

    def test_update_same_version_returns_authority_registration_errors(self):
        from studio.commands.kit import install_kit, update_kit

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "currentfail")
            authority = {
                "source_type": "github",
                "requested_ref": "main",
                "resolved_ref": "main",
                "installed_version": "main",
                "canonical_source": "github:o/r",
                "effective_source": "github:o/r",
                "resolver_mode": "explicit",
                "resolution_basis": "github_ref",
                "verified": "verified",
                "freshness": "fresh",
                "commit_sha": "same123",
                "identity": "o/r@main#same123",
            }
            install_kit(kit_src, adapter, "currentfail", "main", source="github:o/r", authority_metadata=authority)

            with patch("studio.commands.kit._register_kit_in_core_toml", return_value=["cannot write core"]):
                result = update_kit(
                    "currentfail",
                    kit_src,
                    adapter,
                    source="github:o/r",
                    authority_metadata=authority,
                )

            self.assertEqual(result["version"]["status"], "failed")
            self.assertEqual(result["gen"]["files_written"], 0)
            self.assertEqual(result["errors"], ["cannot write core"])

    def test_update_uses_registered_custom_root_as_update_target(self):
        from studio.commands.kit import install_kit, update_kit
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "customupdate")
            install_kit(kit_src, adapter, "customupdate")
            default_kit_dir = adapter / "config" / "kits" / "customupdate"
            custom_kit_dir = adapter / "custom-kits" / "customupdate"
            custom_kit_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(default_kit_dir), str(custom_kit_dir))
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "customupdate": {
                        "format": "CFS",
                        "path": "custom-kits/customupdate",
                        "version": "1",
                    }
                },
            }, adapter / "config" / "core.toml")
            (kit_src / "SKILL.md").write_text("# Updated Skill\n", encoding="utf-8")
            toml_utils.dump({"version": 2}, kit_src / "conf.toml")

            result = update_kit("customupdate", kit_src, adapter, auto_approve=True)

            self.assertEqual(result["version"]["status"], "updated")
            self.assertEqual((custom_kit_dir / "SKILL.md").read_text(encoding="utf-8"), "# Updated Skill\n")
            self.assertFalse(default_kit_dir.exists())
            import tomllib
            with open(adapter / "config" / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(data["kits"]["customupdate"]["path"], "custom-kits/customupdate")

    def test_update_existing_returns_core_registration_errors(self):
        from studio.commands.kit import install_kit, update_kit
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "updatefail")
            install_kit(kit_src, adapter, "updatefail")
            (kit_src / "SKILL.md").write_text("# Updated Skill\n", encoding="utf-8")
            toml_utils.dump({"version": 2}, kit_src / "conf.toml")

            with patch("studio.commands.kit._register_kit_in_core_toml", return_value=["cannot write core"]):
                result = update_kit("updatefail", kit_src, adapter, auto_approve=True)

            self.assertEqual(result["version"]["status"], "failed")
            self.assertEqual(result["gen"]["files_written"], 0)
            self.assertEqual(result["errors"], ["cannot write core"])

    def test_update_manifest_migration_preserves_absolute_bindings_when_relpath_raises(self):
        import studio.commands.kit as kit_module
        from studio.commands.kit import update_kit
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_manifest_kit_source(Path(td), "manifestupdate")
            manifest_path = kit_src / "manifest.toml"
            manifest_path.write_text(
                manifest_path.read_text(encoding="utf-8")
                + "\n".join([
                    "",
                    "[[resources]]",
                    'id = "notes"',
                    'source = "notes.txt"',
                    'default_path = "notes.txt"',
                    'type = "file"',
                    "user_modifiable = false",
                ])
                + "\n",
                encoding="utf-8",
            )
            (kit_src / "notes.txt").write_text("notes\n", encoding="utf-8")

            external_kit_dir = (Path(td) / "external-kits" / "manifestupdate").resolve()
            external_kit_dir.mkdir(parents=True)
            shutil.copy2(kit_src / "SKILL.md", external_kit_dir / "SKILL.md")
            shutil.copy2(kit_src / "AGENTS.md", external_kit_dir / "AGENTS.md")
            shutil.copy2(kit_src / "constraints.toml", external_kit_dir / "constraints.toml")

            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "manifestupdate": {
                        "format": "CFS",
                        "path": external_kit_dir.as_posix(),
                        "version": "0",
                    }
                },
            }, adapter / "config" / "core.toml")

            original_relpath = kit_module.os.path.relpath

            def _patched_relpath(path, start):
                if os.fspath(path).startswith(external_kit_dir.as_posix()):
                    raise ValueError("path is on mount 'D:', start on mount 'C:'")
                return original_relpath(path, start)

            with patch.object(kit_module.os.path, "relpath", side_effect=_patched_relpath):
                result = update_kit("manifestupdate", kit_src, adapter, auto_approve=True)

            self.assertNotEqual(result["version"]["status"], "failed")
            with open(adapter / "config" / "core.toml", "rb") as f:
                data = tomllib.load(f)
            resources = data["kits"]["manifestupdate"]["resources"]
            self.assertEqual(data["kits"]["manifestupdate"]["path"], external_kit_dir.as_posix())
            self.assertEqual(resources["skill"]["path"], f"{external_kit_dir.as_posix()}/SKILL.md")
            self.assertEqual(resources["constraints"]["path"], f"{external_kit_dir.as_posix()}/constraints.toml")
            self.assertEqual(resources["notes"]["path"], f"{external_kit_dir.as_posix()}/notes.txt")

    def test_update_kit_not_installed_coverage(self):
        """cmd_kit_update with valid source but kit not installed."""
        from studio.commands.kit import cmd_kit_update
        from studio.utils.ui import set_json_mode
        set_json_mode(True)
        try:
            with TemporaryDirectory() as td:
                root = Path(td) / "proj"
                _bootstrap_project(root)
                kit_src = _make_kit_source(Path(td), "notinstalled")
                cwd = os.getcwd()
                try:
                    os.chdir(str(root))
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = cmd_kit_update(["--path", str(kit_src)])
                    self.assertEqual(rc, 0)
                    out = json.loads(buf.getvalue())
                    self.assertEqual(out["results"][0]["action"], "created")
                finally:
                    os.chdir(cwd)
        finally:
            set_json_mode(False)


class TestHumanKitInstall(unittest.TestCase):
    """Cover _human_kit_install display function (runs with JSON mode OFF)."""

    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_pass(self):
        from studio.commands.kit import _human_kit_install
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_kit_install({"status": "PASS", "kit": "sdlc", "version": "1", "action": "installed", "files_written": 5})
        self.assertIn("sdlc", buf.getvalue())

    def test_dry_run(self):
        from studio.commands.kit import _human_kit_install
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_kit_install({"status": "DRY_RUN", "kit": "sdlc", "version": "1", "source": "/a", "target": "/b"})
        self.assertIn("Dry run", buf.getvalue())

    def test_fail(self):
        from studio.commands.kit import _human_kit_install
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_kit_install({"status": "FAIL", "kit": "sdlc", "message": "not found", "hint": "check path"})
        self.assertIn("not found", buf.getvalue())

    def test_with_errors(self):
        from studio.commands.kit import _human_kit_install
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_kit_install({"status": "WARN", "kit": "sdlc", "version": "1", "errors": ["err1"]})
        self.assertIn("err1", buf.getvalue())


class TestHumanKitUpdate(unittest.TestCase):
    """Cover _human_kit_update display function."""

    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_pass_with_results(self):
        from studio.commands.kit import _human_kit_update
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_kit_update({
                "status": "PASS",
                "kits_updated": 1,
                "results": [
                    {"kit": "sdlc", "action": "updated", "accepted": ["a.md", "b.md"], "declined": ["c.md"], "unchanged": 5},
                ],
            })
        out = buf.getvalue()
        self.assertIn("sdlc", out)
        self.assertIn("2 accepted", out)
        self.assertIn("1 declined", out)
        self.assertIn("5 unchanged", out)
        self.assertIn("complete", out)

    def test_authority_summary(self):
        from studio.commands.kit import _human_kit_update
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_kit_update({
                "status": "PASS",
                "kits_updated": 1,
                "results": [
                    {
                        "kit": "sdlc",
                        "action": "updated",
                        "authority": {
                            "resolution_basis": "github_release",
                            "resolved_ref": "v2.0.0",
                            "commit_sha": "abc123",
                            "freshness": "fresh",
                        },
                    },
                ],
            })
        out = buf.getvalue()
        self.assertIn("authority", out)
        self.assertIn("basis=github_release", out)
        self.assertIn("ref=v2.0.0", out)
        self.assertIn("commit=abc123", out)
        self.assertIn("freshness=fresh", out)

    def test_warn_with_errors(self):
        from studio.commands.kit import _human_kit_update
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_kit_update({
                "status": "WARN",
                "kits_updated": 1,
                "results": [{"kit": "sdlc", "action": "current"}],
                "errors": ["oops", "fail"],
            })
        out = buf.getvalue()
        self.assertIn("oops", out)
        self.assertIn("fail", out)
        self.assertIn("warnings", out.lower())

    def test_unknown_status(self):
        from studio.commands.kit import _human_kit_update
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_kit_update({"status": "CUSTOM", "results": []})
        self.assertIn("CUSTOM", buf.getvalue())

    def test_no_results(self):
        from studio.commands.kit import _human_kit_update
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_kit_update({"status": "PASS", "kits_updated": 0, "results": []})
        self.assertIn("0", buf.getvalue())


class TestSeedKitConfigFiles(unittest.TestCase):
    """Cover _seed_kit_config_files."""

    def test_seeds_missing_files(self):
        from studio.commands.kit import _seed_kit_config_files
        with TemporaryDirectory() as td:
            scripts_dir = Path(td) / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            config_dir = Path(td) / "config"
            config_dir.mkdir()
            actions = {}
            _seed_kit_config_files(scripts_dir, config_dir, actions)
            # Function should copy scripts content to config if missing


class TestReadConfVersion(unittest.TestCase):
    """Cover _read_conf_version edge cases."""

    def test_valid(self):
        from studio.commands.kit import _read_conf_version
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            p = Path(td) / "conf.toml"
            toml_utils.dump({"version": 3}, p)
            self.assertEqual(_read_conf_version(p), 3)

    def test_missing_file(self):
        from studio.commands.kit import _read_conf_version
        self.assertEqual(_read_conf_version(Path("/nonexistent/conf.toml")), 0)

    def test_no_version_key(self):
        from studio.commands.kit import _read_conf_version
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            p = Path(td) / "conf.toml"
            toml_utils.dump({"slug": "sdlc"}, p)
            self.assertEqual(_read_conf_version(p), 0)

    def test_corrupt(self):
        from studio.commands.kit import _read_conf_version
        with TemporaryDirectory() as td:
            p = Path(td) / "conf.toml"
            p.write_text("{{invalid", encoding="utf-8")
            self.assertEqual(_read_conf_version(p), 0)


# ---------------------------------------------------------------------------
# GitHub source parsing
# ---------------------------------------------------------------------------

class TestParseGithubSource(unittest.TestCase):
    def test_basic(self):
        from studio.commands.kit import _parse_github_source
        o, r, v = _parse_github_source("owner/repo")
        self.assertEqual((o, r, v), ("owner", "repo", ""))

    def test_with_version(self):
        from studio.commands.kit import _parse_github_source
        o, r, v = _parse_github_source("owner/repo@v1.2.3")
        self.assertEqual((o, r, v), ("owner", "repo", "v1.2.3"))

    def test_invalid(self):
        from studio.commands.kit import _parse_github_source
        with self.assertRaises(ValueError):
            _parse_github_source("invalid-no-slash")


# ---------------------------------------------------------------------------
# GitHub download (mocked)
# ---------------------------------------------------------------------------

class TestDownloadKitFromGithub(unittest.TestCase):
    def _make_tarball_bytes(self, entries):
        tar_bytes = io.BytesIO()
        with tarfile.open(fileobj=tar_bytes, mode="w:gz") as tar:
            for entry in entries:
                info = tarfile.TarInfo(name=entry["name"])
                info.type = entry.get("type", tarfile.REGTYPE)
                data = entry.get("data", b"")
                info.size = 0 if info.isdir() else len(data)
                tar.addfile(info, None if info.isdir() else io.BytesIO(data))
        tar_bytes.seek(0)
        return tar_bytes

    def _fake_response(self, tar_bytes):
        class FakeResp:
            def read(self, n=-1):
                return tar_bytes.read(n)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        return FakeResp()

    def test_success(self):
        """Mocked download: creates tarball, extracts to temp dir."""
        from studio.commands.kit import _download_kit_from_github

        tar_bytes = self._make_tarball_bytes([
            {"name": "owner-repo-abc123/", "type": tarfile.DIRTYPE},
            {"name": "owner-repo-abc123/conf.toml", "data": b"version = 1\n"},
        ])

        with patch(
            "studio.commands.kit.urllib.request.urlopen",
            return_value=self._fake_response(tar_bytes),
        ):
            result_dir, ver = _download_kit_from_github("owner", "repo", "v1.0")
            self.assertTrue(result_dir.is_dir())
            self.assertEqual(ver, "v1.0")
            self.assertEqual(
                (result_dir / "conf.toml").read_text(encoding="utf-8"),
                "version = 1\n",
            )
            # Cleanup
            shutil.rmtree(result_dir.parent, ignore_errors=True)

    def test_success_without_version_resolves_latest_release(self):
        from studio.commands.kit import _download_kit_from_github

        tar_bytes = self._make_tarball_bytes([
            {"name": "owner-repo-abc123/", "type": tarfile.DIRTYPE},
            {"name": "owner-repo-abc123/conf.toml", "data": b"version = 1\n"},
        ])

        with patch("studio.commands.kit._resolve_latest_github_release", return_value="v2.0"), \
                patch(
                    "studio.commands.kit.urllib.request.urlopen",
                    return_value=self._fake_response(tar_bytes),
                ):
            result_dir, ver = _download_kit_from_github("owner", "repo")
            self.assertTrue(result_dir.is_dir())
            self.assertEqual(ver, "v2.0")
            shutil.rmtree(result_dir.parent, ignore_errors=True)

    def test_download_generates_whatsnew_from_github_releases(self):
        from studio.commands.kit import _download_kit_from_github

        tar_bytes = self._make_tarball_bytes([
            {"name": "owner-repo-abc123/", "type": tarfile.DIRTYPE},
            {"name": "owner-repo-abc123/conf.toml", "data": b"version = 1\n"},
            {
                "name": "owner-repo-abc123/whatsnew.toml",
                "data": b'[whatsnew."0.0.0"]\nsummary = "local"\ndetails = ""\n',
            },
        ])

        def fake_urlopen(req, **_kwargs):
            url = req.full_url
            if url.endswith("/tarball/v1.0"):
                return self._fake_response(tar_bytes)
            if url.endswith("/releases?per_page=100"):
                return self._fake_response(io.BytesIO(json.dumps([
                    {"tag_name": "v1.0", "name": "Kit release", "body": "- GitHub note"},
                ]).encode()))
            raise AssertionError(url)

        with patch("studio.commands.kit.urllib.request.urlopen", side_effect=fake_urlopen):
            result_dir, ver = _download_kit_from_github("owner", "repo", "v1.0")
            self.assertEqual(ver, "v1.0")
            whatsnew = (result_dir / "whatsnew.toml").read_text(encoding="utf-8")
            self.assertIn('[whatsnew."v1.0"]', whatsnew)
            self.assertIn('summary = "Kit release"', whatsnew)
            self.assertIn("GitHub note", whatsnew)
            self.assertNotIn('summary = "local"', whatsnew)
            shutil.rmtree(result_dir.parent, ignore_errors=True)

    def test_download_warns_when_github_whatsnew_generation_fails(self):
        from studio.commands.kit import _download_kit_from_github

        tar_bytes = self._make_tarball_bytes([
            {"name": "owner-repo-abc123/", "type": tarfile.DIRTYPE},
            {"name": "owner-repo-abc123/conf.toml", "data": b"version = 1\n"},
            {
                "name": "owner-repo-abc123/whatsnew.toml",
                "data": b'[whatsnew."0.0.0"]\nsummary = "local"\ndetails = ""\n',
            },
        ])

        def fake_urlopen(req, **_kwargs):
            url = req.full_url
            if url.endswith("/tarball/v1.0"):
                return self._fake_response(tar_bytes)
            raise AssertionError(url)

        with patch("studio.commands.kit.urllib.request.urlopen", side_effect=fake_urlopen):
            with patch("studio.commands.kit.ui.warn") as warn:
                result_dir, _ver = _download_kit_from_github("owner", "repo", "v1.0")
        self.assertFalse((result_dir / "whatsnew.toml").exists())
        warn.assert_called_once()
        self.assertIn("unable to generate whatsnew.toml", warn.call_args.args[0])
        shutil.rmtree(result_dir.parent, ignore_errors=True)

    def test_with_authority_derives_commit_identity_from_tar_root(self):
        from studio.commands.kit import _download_kit_from_github_with_authority

        tar_bytes = self._make_tarball_bytes([
            {"name": "owner-repo-abc123/", "type": tarfile.DIRTYPE},
            {"name": "owner-repo-abc123/conf.toml", "data": b"version = 1\n"},
        ])

        with patch(
            "studio.commands.kit.urllib.request.urlopen",
            return_value=self._fake_response(tar_bytes),
        ):
            result_dir, ver, authority = _download_kit_from_github_with_authority(
                "owner", "repo", "v1.0",
            )
            self.assertTrue(result_dir.is_dir())
            self.assertEqual(ver, "v1.0")
            self.assertEqual(authority["commit_sha"], "abc123")
            self.assertIn("#abc123", authority["identity"])
            shutil.rmtree(result_dir.parent, ignore_errors=True)

    def test_unsafe_path_rejected(self):
        from studio.commands.kit import _download_kit_from_github

        tar_bytes = self._make_tarball_bytes([
            {"name": "owner-repo-abc123/", "type": tarfile.DIRTYPE},
            {"name": "../escape.txt", "data": b"boom"},
        ])

        with patch(
            "studio.commands.kit.urllib.request.urlopen",
            return_value=self._fake_response(tar_bytes),
        ):
            with self.assertRaisesRegex(RuntimeError, "Unsafe path in archive"):
                _download_kit_from_github("owner", "repo", "v1.0")

    def test_too_many_members_rejected(self):
        import studio.commands.kit as kit_module
        from studio.commands.kit import _download_kit_from_github

        tar_bytes = self._make_tarball_bytes([
            {"name": "owner-repo-abc123/", "type": tarfile.DIRTYPE},
            {"name": "owner-repo-abc123/a.txt", "data": b"a"},
            {"name": "owner-repo-abc123/b.txt", "data": b"b"},
        ])

        with patch.object(kit_module, "_GITHUB_TARBALL_MAX_MEMBERS", 2):
            with patch(
                "studio.commands.kit.urllib.request.urlopen",
                return_value=self._fake_response(tar_bytes),
            ):
                with self.assertRaisesRegex(RuntimeError, "too many archive entries"):
                    _download_kit_from_github("owner", "repo", "v1.0")

    def test_total_uncompressed_size_rejected(self):
        import studio.commands.kit as kit_module
        from studio.commands.kit import _download_kit_from_github

        tar_bytes = self._make_tarball_bytes([
            {"name": "owner-repo-abc123/", "type": tarfile.DIRTYPE},
            {"name": "owner-repo-abc123/big.txt", "data": b"abcdef"},
        ])

        with patch.object(kit_module, "_GITHUB_TARBALL_MAX_TOTAL_SIZE", 5):
            with patch(
                "studio.commands.kit.urllib.request.urlopen",
                return_value=self._fake_response(tar_bytes),
            ):
                with self.assertRaisesRegex(RuntimeError, "total extracted size exceeds"):
                    _download_kit_from_github("owner", "repo", "v1.0")

    def test_suspicious_compression_ratio_rejected(self):
        import studio.commands.kit as kit_module
        from studio.commands.kit import _download_kit_from_github

        tar_bytes = self._make_tarball_bytes([
            {"name": "owner-repo-abc123/", "type": tarfile.DIRTYPE},
            {"name": "owner-repo-abc123/repeated.txt", "data": b"A" * 4096},
        ])

        with patch.object(kit_module, "_GITHUB_TARBALL_MAX_EXPANSION_RATIO", 1):
            with patch(
                "studio.commands.kit.urllib.request.urlopen",
                return_value=self._fake_response(tar_bytes),
            ):
                with self.assertRaisesRegex(RuntimeError, "suspicious compression expansion ratio"):
                    _download_kit_from_github("owner", "repo", "v1.0")

    def test_network_error(self):
        from studio.commands.kit import _download_kit_from_github
        with patch("studio.commands.kit.urllib.request.urlopen", side_effect=Exception("timeout")):
            with self.assertRaises(RuntimeError):
                _download_kit_from_github("owner", "repo", "v1")

    def test_bad_archive(self):
        """Download succeeds but tarball is corrupt."""
        from studio.commands.kit import _download_kit_from_github

        class FakeResp:
            def __init__(self):
                self._data = io.BytesIO(b"not a tarball")
            def read(self, n=-1):
                return self._data.read(n)
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        with patch("studio.commands.kit.urllib.request.urlopen", return_value=FakeResp()):
            with self.assertRaises(RuntimeError):
                _download_kit_from_github("owner", "repo", "v1")


class TestGithubHeaders(unittest.TestCase):
    def test_no_token(self):
        from studio.commands.kit import _github_headers
        with patch.dict("os.environ", {}, clear=True):
            h = _github_headers()
            self.assertEqual(h["User-Agent"], "studio-kit-installer")
            self.assertNotIn("Authorization", h)

    def test_with_token(self):
        from studio.commands.kit import _github_headers
        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test123"}):
            h = _github_headers()
            self.assertEqual(h["Authorization"], "Bearer ghp_test123")


class TestResolveLatestRelease(unittest.TestCase):
    def test_success(self):
        from studio.commands.kit import _resolve_latest_github_release

        class FakeResp:
            def read(self):
                return json.dumps({"tag_name": "v2.0"}).encode()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        with patch("studio.commands.kit.urllib.request.urlopen", return_value=FakeResp()):
            tag = _resolve_latest_github_release("o", "r")
            self.assertEqual(tag, "v2.0")

    def test_no_releases_404(self):
        import urllib.error
        from studio.commands.kit import _resolve_latest_github_release

        class FakeResp:
            def read(self):
                return json.dumps([
                    {"name": "v1.9.0"},
                    {"name": "v2.0.0"},
                    {"name": "not-semver"},
                ]).encode()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        def fake_urlopen(req, **_kwargs):
            url = req.full_url
            if url.endswith("/releases/latest"):
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            if url.endswith("/tags?per_page=100"):
                return FakeResp()
            raise AssertionError(url)

        with patch("studio.commands.kit.urllib.request.urlopen", fake_urlopen):
            tag = _resolve_latest_github_release("o", "r")
            self.assertEqual(tag, "v2.0.0")

    def test_api_error_raises(self):
        import urllib.error
        from studio.commands.kit import _resolve_latest_github_release

        exc = urllib.error.HTTPError("url", 403, "rate limit", {}, None)
        with patch("studio.commands.kit.urllib.request.urlopen", side_effect=exc):
            with self.assertRaises(RuntimeError):
                _resolve_latest_github_release("o", "r")

    def test_network_error_raises(self):
        from studio.commands.kit import _resolve_latest_github_release
        with patch("studio.commands.kit.urllib.request.urlopen", side_effect=OSError("dns")):
            with self.assertRaises(RuntimeError):
                _resolve_latest_github_release("o", "r")


class TestResolveGithubRef(unittest.TestCase):
    def test_explicit_ref_does_not_call_latest_release(self):
        from studio.commands.kit import _resolve_github_ref

        calls = []

        def fake_latest(_owner, _repo):
            calls.append("latest")
            return "v9"

        with patch("studio.commands.kit._resolve_latest_github_release", fake_latest):
            meta = _resolve_github_ref("o", "r", "v1.0")

        self.assertEqual(calls, [])
        self.assertEqual(meta["requested_ref"], "v1.0")
        self.assertEqual(meta["resolved_ref"], "v1.0")
        self.assertEqual(meta["resolver_mode"], "explicit")

    def test_latest_release_metadata(self):
        from studio.commands.kit import _resolve_github_ref

        with patch("studio.commands.kit._resolve_latest_github_release", return_value="v2.0"):
            meta = _resolve_github_ref("o", "r", "")

        self.assertEqual(meta["requested_ref"], "latest")
        self.assertEqual(meta["resolved_ref"], "v2.0")
        self.assertEqual(meta["resolver_mode"], "latest_release")
        self.assertEqual(meta["resolution_basis"], "github_release")

    def test_latest_release_network_error_uses_previous_provenance(self):
        from studio.commands.kit import _resolve_github_ref

        previous = {
            "source_provenance": {
                "requested_ref": "latest",
                "resolved_ref": "v2.0",
                "resolver_mode": "latest_release",
                "resolution_basis": "github_release",
                "commit_sha": "abc123",
            },
            "version": "v2.0",
        }

        with patch("studio.commands.kit._resolve_latest_github_release", side_effect=RuntimeError("offline")):
            meta = _resolve_github_ref("o", "r", "", previous_entry=previous)

        self.assertEqual(meta["resolved_ref"], "v2.0")
        self.assertEqual(meta["freshness"], "last_known")
        self.assertEqual(meta["verified"], "stale")
        self.assertEqual(meta["commit_sha"], "abc123")

    def test_authority_summary_includes_source_and_identity(self):
        from studio.commands.kit import _authority_result_summary

        summary = _authority_result_summary({
            "source_type": "github",
            "resolver_mode": "latest_release",
            "resolution_basis": "github_release",
            "requested_ref": "latest",
            "resolved_ref": "v2.0.0",
            "commit_sha": "abc123",
            "canonical_source": "github:o/r",
            "effective_source": "github:mirror/r",
            "identity": "o/r@v2.0.0#abc123",
            "freshness": "fresh",
            "verified": "verified",
        })

        self.assertEqual(summary["source_type"], "github")
        self.assertEqual(summary["canonical_source"], "github:o/r")
        self.assertEqual(summary["effective_source"], "github:mirror/r")
        self.assertEqual(summary["identity"], "o/r@v2.0.0#abc123")
        self.assertEqual(summary["commit_sha"], "abc123")


class TestKitUpdateAuthorityIdentity(unittest.TestCase):
    def test_same_ref_with_new_commit_does_not_short_circuit_as_current(self):
        from studio.commands.kit import install_kit, update_kit

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            old_src = _make_kit_source(Path(td), "driftkit")
            new_src = _make_kit_source(Path(td), "driftkit-new")
            (new_src / "SKILL.md").write_text("# Kit driftkit\nUpdated.\n", encoding="utf-8")

            install_kit(
                old_src,
                adapter,
                "driftkit",
                "main",
                source="github:o/r",
                authority_metadata={
                    "source_type": "github",
                    "requested_ref": "main",
                    "resolved_ref": "main",
                    "installed_version": "main",
                    "canonical_source": "github:o/r",
                    "effective_source": "github:o/r",
                    "resolver_mode": "explicit",
                    "resolution_basis": "github_ref",
                    "verified": "verified",
                    "freshness": "fresh",
                    "commit_sha": "old123",
                    "identity": "o/r@main#old123",
                },
            )

            result = update_kit(
                "driftkit",
                new_src,
                adapter,
                interactive=False,
                auto_approve=True,
                source="github:o/r",
                authority_metadata={
                    "source_type": "github",
                    "requested_ref": "main",
                    "resolved_ref": "main",
                    "installed_version": "main",
                    "canonical_source": "github:o/r",
                    "effective_source": "github:o/r",
                    "resolver_mode": "explicit",
                    "resolution_basis": "github_ref",
                    "verified": "verified",
                    "freshness": "fresh",
                    "commit_sha": "new456",
                    "identity": "o/r@main#new456",
                },
            )

            self.assertEqual(result["version"]["status"], "updated")
            self.assertEqual(result["authority"]["resolution_basis"], "github_ref")
            self.assertEqual(result["authority"]["commit_sha"], "new456")
            with open(adapter / "config" / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(
                data["kits"]["driftkit"]["source_provenance"]["commit_sha"],
                "new456",
            )


# ---------------------------------------------------------------------------
# Layout migration
# ---------------------------------------------------------------------------

class TestDetectAndMigrateLayout(unittest.TestCase):
    def test_no_legacy_dirs(self):
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            cypilot = Path(td) / "cypilot"
            cypilot.mkdir()
            result = _detect_and_migrate_layout(cypilot)
            self.assertEqual(result, {})

    def test_migrate_kits_dir(self):
        """kits/{slug}/ content migrates to config/kits/{slug}/."""
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            cypilot = Path(td) / "cypilot"
            # Create old layout: kits/sdlc/ with content
            kits_dir = cypilot / "kits" / "sdlc"
            kits_dir.mkdir(parents=True)
            (kits_dir / "conf.toml").write_text("version = 1\n", encoding="utf-8")
            (kits_dir / "artifacts").mkdir()
            (kits_dir / "artifacts" / "PRD.md").write_text("# PRD\n", encoding="utf-8")
            # blueprints should be skipped
            (kits_dir / "blueprints").mkdir()
            (kits_dir / "blueprints" / "old.md").write_text("old", encoding="utf-8")

            result = _detect_and_migrate_layout(cypilot)

            self.assertEqual(result.get("sdlc"), "migrated")
            config_kit = cypilot / "config" / "kits" / "sdlc"
            self.assertTrue((config_kit / "conf.toml").is_file())
            self.assertTrue((config_kit / "artifacts" / "PRD.md").is_file())
            # blueprints should NOT be copied
            self.assertFalse((config_kit / "blueprints").exists())
            # Old kits/ dir should be removed
            self.assertFalse((cypilot / "kits").is_dir())

    def test_migrate_gen_kits(self):
        """.gen/kits/{slug}/ content migrates to config/kits/{slug}/."""
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            cypilot = Path(td) / "cypilot"
            gen_kit = cypilot / ".gen" / "kits" / "sdlc"
            gen_kit.mkdir(parents=True)
            (gen_kit / "SKILL.md").write_text("# Skill\n", encoding="utf-8")

            result = _detect_and_migrate_layout(cypilot)

            self.assertIn("sdlc", result)
            config_kit = cypilot / "config" / "kits" / "sdlc"
            self.assertTrue((config_kit / "SKILL.md").is_file())
            # .gen/kits/ should be removed
            self.assertFalse((cypilot / ".gen" / "kits").is_dir())

    def test_dry_run(self):
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            cypilot = Path(td) / "cypilot"
            kits_dir = cypilot / "kits" / "sdlc"
            kits_dir.mkdir(parents=True)
            (kits_dir / "conf.toml").write_text("v=1\n", encoding="utf-8")

            result = _detect_and_migrate_layout(cypilot, dry_run=True)
            self.assertEqual(result.get("sdlc"), "would_migrate")
            # Files should NOT be moved
            self.assertTrue(kits_dir.exists())

    def test_updates_core_toml_paths(self):
        from studio.commands.kit import _detect_and_migrate_layout
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            cypilot = Path(td) / "cypilot"
            kits_dir = cypilot / "kits" / "sdlc"
            kits_dir.mkdir(parents=True)
            (kits_dir / "conf.toml").write_text("v=1\n", encoding="utf-8")
            config_dir = cypilot / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            toml_utils.dump({
                "kits": {"sdlc": {"path": "kits/sdlc", "format": "CFS"}},
            }, config_dir / "core.toml")

            _detect_and_migrate_layout(cypilot)

            import tomllib
            with open(config_dir / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(data["kits"]["sdlc"]["path"], "config/kits/sdlc")

    def test_overwrite_existing_dir(self):
        """When config/kits/{slug}/artifacts/ already exists, it gets overwritten."""
        from studio.commands.kit import _detect_and_migrate_layout
        with TemporaryDirectory() as td:
            cypilot = Path(td) / "cypilot"
            # Old layout
            kits_dir = cypilot / "kits" / "sdlc"
            (kits_dir / "artifacts").mkdir(parents=True)
            (kits_dir / "artifacts" / "new.md").write_text("new", encoding="utf-8")
            # Existing config
            config_art = cypilot / "config" / "kits" / "sdlc" / "artifacts"
            config_art.mkdir(parents=True)
            (config_art / "old.md").write_text("old", encoding="utf-8")

            _detect_and_migrate_layout(cypilot)
            # artifacts dir should have the NEW content
            self.assertTrue((config_art / "new.md").is_file())


# ---------------------------------------------------------------------------
# install_kit validation
# ---------------------------------------------------------------------------

class TestInstallKitValidation(unittest.TestCase):
    def test_nonexistent_source(self):
        from studio.commands.kit import install_kit
        result = install_kit(Path("/no/such/dir"), Path("/tmp"), "x")
        self.assertEqual(result["status"], "FAIL")


# ---------------------------------------------------------------------------
# _copy_kit_content overwrite path
# ---------------------------------------------------------------------------

class TestCopyKitContentOverwrite(unittest.TestCase):
    def test_existing_dir_overwritten(self):
        from studio.commands.kit import _copy_kit_content
        with TemporaryDirectory() as td:
            src = Path(td) / "src"
            dst = Path(td) / "dst"
            (src / "artifacts" / "PRD").mkdir(parents=True)
            (src / "artifacts" / "PRD" / "new.md").write_text("new", encoding="utf-8")
            # Existing target with different content
            (dst / "artifacts" / "PRD").mkdir(parents=True)
            (dst / "artifacts" / "PRD" / "old.md").write_text("old", encoding="utf-8")

            actions = _copy_kit_content(src, dst)
            self.assertEqual(actions.get("artifacts"), "copied")
            # new.md should exist, old.md should NOT (dir was replaced)
            self.assertTrue((dst / "artifacts" / "PRD" / "new.md").is_file())
            self.assertFalse((dst / "artifacts" / "PRD" / "old.md").exists())


# ---------------------------------------------------------------------------
# _collect_kit_metadata OSError
# ---------------------------------------------------------------------------

class TestCollectKitMetadataOsError(unittest.TestCase):
    def test_agents_read_oserror(self):
        from studio.commands.kit import _collect_kit_metadata
        with TemporaryDirectory() as td:
            kit_dir = Path(td) / "sdlc"
            kit_dir.mkdir()
            agents = kit_dir / "AGENTS.md"
            agents.mkdir()  # directory, not file — read will fail
            meta = _collect_kit_metadata(kit_dir, "sdlc")
            self.assertEqual(meta["agents_content"], "")

    def test_skill_nav_ignores_registered_custom_path(self):
        from studio.commands.kit import _collect_kit_metadata
        with TemporaryDirectory() as td:
            kit_dir = Path(td) / "custom-kits" / "sdlc"
            kit_dir.mkdir(parents=True)
            (kit_dir / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
            meta = _collect_kit_metadata(kit_dir, "sdlc", "custom-kits/sdlc")
            self.assertEqual(meta["skill_nav"], "")

    def test_skill_nav_ignores_absolute_registered_custom_path(self):
        from studio.commands.kit import _collect_kit_metadata
        with TemporaryDirectory() as td:
            kit_dir = Path(td) / "custom-kits" / "sdlc"
            kit_dir.mkdir(parents=True)
            (kit_dir / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
            meta = _collect_kit_metadata(kit_dir, "sdlc", kit_dir.as_posix())
            self.assertEqual(meta["skill_nav"], "")

    def test_skill_nav_ignores_windows_drive_registered_custom_path(self):
        from studio.commands.kit import _collect_kit_metadata
        with TemporaryDirectory() as td:
            kit_dir = Path(td) / "custom-kits" / "sdlc"
            kit_dir.mkdir(parents=True)
            (kit_dir / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
            meta = _collect_kit_metadata(kit_dir, "sdlc", "C:/external-kits/sdlc")
            self.assertEqual(meta["skill_nav"], "")

    def test_skill_nav_ignores_windows_backslash_registered_custom_path(self):
        from studio.commands.kit import _collect_kit_metadata
        with TemporaryDirectory() as td:
            kit_dir = Path(td) / "custom-kits" / "sdlc"
            kit_dir.mkdir(parents=True)
            (kit_dir / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
            meta = _collect_kit_metadata(kit_dir, "sdlc", r"C:\external-kits\sdlc")
            self.assertEqual(meta["skill_nav"], "")

    def test_registered_resource_metadata_uses_public_bindings_only(self):
        from studio.commands.kit import _collect_registered_kit_metadata

        with TemporaryDirectory() as td:
            studio_dir = Path(td) / ".bootstrap"
            public_skill = studio_dir / "custom" / "SKILL.md"
            public_rule = studio_dir / "custom" / "AGENTS.md"
            private_rule = studio_dir / "custom" / "PRIVATE.md"
            public_skill.parent.mkdir(parents=True)
            public_skill.write_text("# Skill\n", encoding="utf-8")
            public_rule.write_text("PUBLIC RULE\n", encoding="utf-8")
            private_rule.write_text("PRIVATE RULE\n", encoding="utf-8")

            meta = _collect_registered_kit_metadata(
                studio_dir,
                "sdlc",
                {
                    "resources": {
                        "skill": {"path": "custom/SKILL.md", "kind": "skill", "public": "yes"},
                        "rule": {"path": "custom/AGENTS.md", "kind": "rule", "public": True},
                        "private-rule": {"path": "custom/PRIVATE.md", "kind": "rule", "public": False},
                        "constraints": {"path": "custom/constraints.toml", "kind": "constraints", "public": True},
                        "missing": {"path": ""},
                    },
                },
            )

        self.assertEqual(meta["skill_nav"], "")
        self.assertEqual(meta["agents_content"], "PUBLIC RULE\n")
        self.assertNotIn("PRIVATE RULE", meta["agents_content"])

    def test_registered_resource_metadata_infers_legacy_skill_and_rule_kinds(self):
        from studio.commands.kit import _collect_registered_kit_metadata

        with TemporaryDirectory() as td:
            studio_dir = Path(td) / ".bootstrap"
            kit_dir = studio_dir / "external"
            kit_dir.mkdir(parents=True)
            (kit_dir / "SKILL.md").write_text("# Legacy skill\n", encoding="utf-8")
            (kit_dir / "AGENTS.md").write_text("LEGACY RULE\n", encoding="utf-8")

            meta = _collect_registered_kit_metadata(
                studio_dir,
                "legacy",
                {
                    "resources": {
                        "skill": "external/SKILL.md",
                        "agents": "external/AGENTS.md",
                    },
                },
            )

        self.assertEqual(meta["skill_nav"], "")
        self.assertEqual(meta["agents_content"], "LEGACY RULE\n")

    def test_prompt_manifest_install_plan_allows_root_and_resource_overrides(self):
        from studio.commands.kit import _prompt_manifest_install_plan

        with TemporaryDirectory() as td:
            studio_dir = Path(td) / ".bootstrap"
            kit_root = studio_dir / "config" / "kits" / "sdlc"
            studio_dir.mkdir(parents=True)
            resource = SimpleNamespace(
                id="constraints",
                type="file",
                source="constraints.toml",
                default_path="constraints.toml",
                install_path="constraints.toml",
                user_modifiable=True,
                public=False,
                kind="constraints",
                artifact_bindings={"FEATURE": {"template": "feature-template"}},
            )
            manifest = SimpleNamespace(user_modifiable=True, resources=[resource])

            with patch("studio.commands.kit.sys.stdin.isatty", return_value=True), patch(
                "studio.commands.kit._input_stderr",
                side_effect=["yes", "1", "custom-root", "yes", "2", "overrides/constraints.toml", "done"],
            ):
                new_root, new_root_rel, bindings = _prompt_manifest_install_plan(
                    "sdlc",
                    studio_dir,
                    kit_root,
                    manifest,
                    interactive=True,
                )

        self.assertEqual(new_root, (studio_dir / "custom-root").resolve())
        self.assertEqual(new_root_rel, "custom-root")
        self.assertEqual(bindings["constraints"]["path"], "custom-root/overrides/constraints.toml")
        self.assertEqual(bindings["constraints"]["artifacts"], {"FEATURE": {"template": "feature-template"}})

    def test_manifest_root_resolution_helpers_cover_fallbacks(self):
        from studio.commands.kit import (
            _resolve_declared_manifest_root,
            _resolve_manifest_kit_root_rel,
            _resolve_manifest_root_from_binding,
        )

        self.assertIsNone(_resolve_manifest_root_from_binding(None, "constraints.toml"))
        self.assertIsNone(_resolve_manifest_root_from_binding("short.toml", "nested/constraints.toml"))
        self.assertIsNone(_resolve_manifest_root_from_binding("kit/other.toml", "constraints.toml"))
        self.assertEqual(_resolve_manifest_root_from_binding("kit/constraints.toml", "constraints.toml"), "kit")
        self.assertEqual(_resolve_manifest_root_from_binding("constraints.toml", "constraints.toml"), "")

        self.assertEqual(
            _resolve_declared_manifest_root(SimpleNamespace(root="{cf-studio-path}/kits/{slug}"), "sdlc"),
            "kits/sdlc",
        )
        self.assertEqual(_resolve_declared_manifest_root(SimpleNamespace(root="."), "sdlc"), "config/kits/sdlc")

        manifest = SimpleNamespace(
            root="fallback/{slug}",
            resources=[SimpleNamespace(id="constraints", install_path="constraints.toml")],
        )
        self.assertEqual(
            _resolve_manifest_kit_root_rel(
                manifest,
                {"constraints": {"path": "registered/constraints.toml"}},
                "sdlc",
            ),
            "registered",
        )
        self.assertEqual(_resolve_manifest_kit_root_rel(manifest, {}, "sdlc"), "fallback/sdlc")

    def test_validate_register_manifest_containment_reports_escape_branches(self):
        from studio.commands.kit import _validate_register_manifest_containment

        with TemporaryDirectory() as td:
            project_root = Path(td) / "project"
            studio_dir = project_root / ".bootstrap"
            kit_source = project_root / "kits" / "sdlc"
            external_dir = Path(td) / "external"
            external_dir.mkdir()
            external_constraints = external_dir / "constraints.toml"
            external_constraints.write_text("", encoding="utf-8")
            kit_source.mkdir(parents=True)
            (kit_source / ".cf-studio-kit.toml").write_text("manifest\n", encoding="utf-8")
            manifest = SimpleNamespace(
                root="/outside",
                resources=[
                    SimpleNamespace(id="absolute", source=external_constraints.as_posix()),
                    SimpleNamespace(id="escape", source="../../../outside.toml"),
                ],
            )

            missing_root_errors = _validate_register_manifest_containment(
                None,
                studio_dir,
                kit_source,
                "sdlc",
                manifest,
            )
            errors = _validate_register_manifest_containment(
                project_root,
                studio_dir,
                kit_source,
                "sdlc",
                manifest,
            )

        self.assertEqual(missing_root_errors, ["Register install mode requires a resolved project root"])
        self.assertTrue(any("Manifest root" in error for error in errors))
        self.assertTrue(any("must be relative" in error for error in errors))
        self.assertTrue(any("escapes the project root" in error for error in errors))

    def test_project_root_from_core_toml_handles_relative_absolute_and_invalid(self):
        from studio.commands.kit import _project_root_from_core_toml

        with TemporaryDirectory() as td:
            studio_dir = Path(td) / ".bootstrap"
            config_dir = studio_dir / "config"
            config_dir.mkdir(parents=True)

            self.assertIsNone(_project_root_from_core_toml(config_dir, studio_dir))

            core = config_dir / "core.toml"
            core.write_text("project_root = \"..\"\n", encoding="utf-8")
            self.assertEqual(_project_root_from_core_toml(config_dir, studio_dir), studio_dir.parent.resolve())

            absolute_root = Path(td).resolve()
            core.write_text(f"project_root = \"{absolute_root.as_posix()}\"\n", encoding="utf-8")
            self.assertEqual(_project_root_from_core_toml(config_dir, studio_dir), absolute_root)

            core.write_text("project_root = 123\n", encoding="utf-8")
            self.assertIsNone(_project_root_from_core_toml(config_dir, studio_dir))

            core.write_text("{{bad", encoding="utf-8")
            self.assertIsNone(_project_root_from_core_toml(config_dir, studio_dir))


# ---------------------------------------------------------------------------
# _read_project_name_from_registry
# ---------------------------------------------------------------------------

class TestResolveRegisteredKitMetadataTarget(unittest.TestCase):
    def test_uses_resource_binding_when_registered_kit_dir_has_no_metadata(self):
        from studio.commands.kit import _resolve_registered_kit_metadata_target

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            resource_dir = adapter / "registered"
            resource_dir.mkdir()
            (resource_dir / "AGENTS.md").write_text("RULE\n", encoding="utf-8")

            kit_dir, kit_rel_path = _resolve_registered_kit_metadata_target(
                adapter,
                "sdlc",
                {
                    "path": "config/kits/sdlc",
                    "resources": {
                        "rule": {"path": "registered/AGENTS.md", "kind": "rule", "public": True},
                    },
                },
            )

        self.assertEqual(kit_dir, resource_dir.resolve())
        self.assertEqual(kit_rel_path, "registered")

    def test_uses_existing_raw_windows_backslash_registered_path(self):
        from studio.commands.kit import _resolve_registered_kit_metadata_target
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_dir, kit_rel_path = _resolve_registered_kit_metadata_target(
                adapter,
                "sdlc",
                {"path": r"C:\external-kits\sdlc"},
            )

            if os.name == "nt":
                self.assertIsNotNone(kit_dir)
                self.assertTrue(kit_dir.is_absolute())
            else:
                self.assertIsNone(kit_dir)
            self.assertEqual(kit_rel_path, "C:/external-kits/sdlc")

class TestReadProjectNameFromRegistry(unittest.TestCase):
    def test_missing_file(self):
        from studio.commands.kit import _read_project_name_from_registry
        self.assertIsNone(_read_project_name_from_registry(Path("/nonexistent")))

    def test_corrupt_toml(self):
        from studio.commands.kit import _read_project_name_from_registry
        with TemporaryDirectory() as td:
            p = Path(td) / "artifacts.toml"
            p.write_text("{{bad", encoding="utf-8")
            self.assertIsNone(_read_project_name_from_registry(Path(td)))

    def test_empty_name(self):
        from studio.commands.kit import _read_project_name_from_registry
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            toml_utils.dump({"systems": [{"name": "  "}]}, Path(td) / "artifacts.toml")
            self.assertIsNone(_read_project_name_from_registry(Path(td)))

    def test_reads_first_system_name(self):
        from studio.commands.kit import _read_project_name_from_registry
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            toml_utils.dump(
                {"systems": [{"name": "MyProject", "slug": "myproject", "kit": "sdlc"}]},
                Path(td) / "artifacts.toml",
            )
            self.assertEqual(_read_project_name_from_registry(Path(td)), "MyProject")


# ---------------------------------------------------------------------------
# _read_kits_from_core_toml edge cases
# ---------------------------------------------------------------------------

class TestReadKitsFromCoreToml(unittest.TestCase):
    def test_missing_file(self):
        from studio.commands.kit import _read_kits_from_core_toml
        self.assertEqual(_read_kits_from_core_toml(Path("/nonexistent")), {})

    def test_corrupt(self):
        from studio.commands.kit import _read_kits_from_core_toml
        with TemporaryDirectory() as td:
            (Path(td) / "core.toml").write_text("{{bad", encoding="utf-8")
            self.assertEqual(_read_kits_from_core_toml(Path(td)), {})

    def test_non_dict_kits(self):
        from studio.commands.kit import _read_kits_from_core_toml
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            toml_utils.dump({"kits": "not_a_dict"}, Path(td) / "core.toml")
            self.assertEqual(_read_kits_from_core_toml(Path(td)), {})

    def test_filters_non_dict_entries(self):
        from studio.commands.kit import _read_kits_from_core_toml
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            toml_utils.dump({
                "kits": {"good": {"path": "x"}, "bad": "string_val"},
            }, Path(td) / "core.toml")
            result = _read_kits_from_core_toml(Path(td))
            self.assertIn("good", result)
            self.assertNotIn("bad", result)


# ---------------------------------------------------------------------------
# _register_kit_in_core_toml
# ---------------------------------------------------------------------------

class TestRegisterKitInCoreToml(unittest.TestCase):
    def test_new_kit(self):
        from studio.commands.kit import _register_kit_in_core_toml
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            config = Path(td)
            toml_utils.dump({"kits": {}}, config / "core.toml")
            _register_kit_in_core_toml(config, "mykit", "1.0", Path(td) / "cyp")
            with open(config / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(data["kits"]["mykit"]["version"], "1.0")
            self.assertEqual(data["kits"]["mykit"]["format"], "CFS")
            self.assertEqual(data["kits"]["mykit"]["path"], "config/kits/mykit")

    def test_with_source(self):
        from studio.commands.kit import _register_kit_in_core_toml
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            config = Path(td)
            toml_utils.dump({"kits": {}}, config / "core.toml")
            _register_kit_in_core_toml(config, "mykit", "2.0", Path(td), source="github:o/r")
            with open(config / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(data["kits"]["mykit"]["source"], "github:o/r")

    def test_with_github_authority_metadata(self):
        from studio.commands.kit import _register_kit_in_core_toml
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            config = Path(td)
            toml_utils.dump({"kits": {}}, config / "core.toml")
            _register_kit_in_core_toml(
                config,
                "mykit",
                "v2.0.0",
                Path(td),
                source="github:o/r",
                authority_metadata={
                    "requested_ref": "latest",
                    "resolved_ref": "v2.0.0",
                    "commit_sha": "abc123",
                    "canonical_source": "github:o/r",
                    "effective_source": "github:mirror/r",
                    "resolver_mode": "latest_release",
                    "resolution_basis": "github_release",
                    "verified": "verified",
                    "freshness": "fresh",
                },
            )
            with open(config / "core.toml", "rb") as f:
                data = tomllib.load(f)
            kit = data["kits"]["mykit"]
            self.assertEqual(kit["version"], "v2.0.0")
            self.assertEqual(kit["source_provenance"]["source_type"], "github")
            self.assertEqual(kit["source_provenance"]["requested_ref"], "latest")
            self.assertEqual(kit["source_provenance"]["resolved_ref"], "v2.0.0")
            self.assertEqual(kit["source_provenance"]["effective_source"], "github:mirror/r")
            self.assertEqual(kit["source_provenance"]["commit_sha"], "abc123")

    def test_install_kit_uses_github_version_not_conf_version_for_authority(self):
        from studio.commands.kit import install_kit
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            root = Path(td)
            kit_src = _make_kit_source(root, "mykit")
            toml_utils.dump({"version": "999.0.0", "slug": "mykit"}, kit_src / "conf.toml")
            studio_dir = root / ".cf-studio"
            (studio_dir / "config").mkdir(parents=True)
            toml_utils.dump({"kits": {}}, studio_dir / "config" / "core.toml")

            result = install_kit(
                kit_src,
                studio_dir,
                "mykit",
                "v2.0.0",
                source="github:o/r",
                authority_metadata={
                    "requested_ref": "latest",
                    "resolved_ref": "v2.0.0",
                    "commit_sha": "abc123",
                    "canonical_source": "github:o/r",
                    "effective_source": "github:o/r",
                    "resolver_mode": "latest_release",
                    "resolution_basis": "github_release",
                    "verified": "verified",
                    "freshness": "fresh",
                },
            )

            self.assertEqual(result["version"], "v2.0.0")
            self.assertEqual(result["local_metadata"]["conf_version"], "999.0.0")
            with open(studio_dir / "config" / "core.toml", "rb") as f:
                data = tomllib.load(f)
            kit = data["kits"]["mykit"]
            self.assertEqual(kit["version"], "v2.0.0")
            self.assertEqual(kit["source_provenance"]["resolved_ref"], "v2.0.0")
            self.assertEqual(kit["local_metadata"]["conf_version"], "999.0.0")

    def test_update_kit_currentness_uses_github_authority_not_conf_version(self):
        from studio.commands.kit import update_kit
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            root = Path(td)
            source = _make_kit_source(root, "mykit")
            toml_utils.dump({"version": "999.0.0", "slug": "mykit"}, source / "conf.toml")
            studio_dir = root / ".cf-studio"
            installed = studio_dir / "config" / "kits" / "mykit"
            installed.mkdir(parents=True)
            (installed / "SKILL.md").write_text("# installed\n", encoding="utf-8")
            toml_utils.dump({
                "kits": {
                    "mykit": {
                        "format": "CFS",
                        "path": "config/kits/mykit",
                        "source": "github:o/r",
                        "version": "v2.0.0",
                    },
                },
            }, studio_dir / "config" / "core.toml")

            result = update_kit(
                "mykit",
                source,
                studio_dir,
                source="github:o/r",
                authority_metadata={
                    "requested_ref": "latest",
                    "resolved_ref": "v2.0.0",
                    "commit_sha": "abc123",
                    "canonical_source": "github:o/r",
                    "effective_source": "github:o/r",
                    "resolver_mode": "latest_release",
                    "resolution_basis": "github_release",
                    "verified": "verified",
                    "freshness": "fresh",
                },
            )

            self.assertEqual(result["version"]["status"], "current")

    def test_local_install_does_not_create_github_authority(self):
        from studio.commands.kit import install_kit
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            root = Path(td)
            kit_src = _make_kit_source(root, "mykit")
            studio_dir = root / ".cf-studio"
            (studio_dir / "config").mkdir(parents=True)
            toml_utils.dump({"kits": {}}, studio_dir / "config" / "core.toml")

            install_kit(kit_src, studio_dir, "mykit")

            with open(studio_dir / "config" / "core.toml", "rb") as f:
                data = tomllib.load(f)
            kit = data["kits"]["mykit"]
            self.assertNotIn("source_provenance", kit)
            self.assertEqual(kit["local_metadata"]["conf_version"], "1")

    def test_with_explicit_path(self):
        from studio.commands.kit import _register_kit_in_core_toml
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            config = Path(td)
            toml_utils.dump({"kits": {}}, config / "core.toml")
            _register_kit_in_core_toml(
                config, "mykit", "2.0", Path(td), kit_path="custom-kits/mykit",
            )
            with open(config / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(data["kits"]["mykit"]["path"], "custom-kits/mykit")

    def test_preserves_existing_custom_path_when_no_explicit_path_given(self):
        from studio.commands.kit import _register_kit_in_core_toml
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            config = Path(td)
            toml_utils.dump({
                "kits": {
                    "mykit": {
                        "format": "CFS",
                        "path": "custom-kits/mykit",
                        "version": "1.0",
                    }
                }
            }, config / "core.toml")
            _register_kit_in_core_toml(config, "mykit", "2.0", Path(td), source="github:o/r")
            with open(config / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(data["kits"]["mykit"]["path"], "custom-kits/mykit")
            self.assertEqual(data["kits"]["mykit"]["version"], "2.0")

    def test_preserves_existing_windows_backslash_path_spelling(self):
        from studio.commands.kit import _register_kit_in_core_toml
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            config = Path(td)
            toml_utils.dump({
                "kits": {
                    "mykit": {
                        "format": "CFS",
                        "path": r"C:\external-kits\mykit",
                        "version": "1.0",
                    }
                }
            }, config / "core.toml")
            _register_kit_in_core_toml(
                config, "mykit", "2.0", Path(td), kit_path="C:/external-kits/mykit",
            )
            with open(config / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(data["kits"]["mykit"]["path"], r"C:\external-kits\mykit")

    def test_register_returns_write_errors(self):
        from studio.commands.kit import _register_kit_in_core_toml
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            config = Path(td)
            toml_utils.dump({"kits": {}}, config / "core.toml")
            err = io.StringIO()
            with redirect_stderr(err), patch("studio.utils.toml_utils.dump", side_effect=OSError("full")):
                errors = _register_kit_in_core_toml(config, "mykit", "1.0", Path(td))

            self.assertEqual(len(errors), 1)
            self.assertIn("failed to register mykit", errors[0])
            self.assertIn("failed to register mykit", err.getvalue())

    def test_install_kit_fails_when_core_registration_fails(self):
        from studio.commands.kit import install_kit
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            root = Path(td)
            kit_src = _make_kit_source(root, "failkit")
            studio_dir = root / ".cf-studio"
            (studio_dir / "config").mkdir(parents=True)
            toml_utils.dump({"kits": {}}, studio_dir / "config" / "core.toml")

            with patch("studio.commands.kit._register_kit_in_core_toml", return_value=["cannot write core"]):
                result = install_kit(kit_src, studio_dir, "failkit")

            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["kit"], "failkit")
            self.assertEqual(result["errors"], ["cannot write core"])

    def test_install_canonical_manifest_fails_when_core_registration_fails(self):
        from studio.commands.kit import install_kit
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            root = Path(td)
            kit_src = _make_canonical_kit_source(root, "failmanifest")
            studio_dir = root / ".cf-studio"
            (studio_dir / "config").mkdir(parents=True)
            toml_utils.dump({"kits": {}}, studio_dir / "config" / "core.toml")

            with patch("studio.commands.kit._register_kit_in_core_toml", return_value=["cannot write core"]):
                result = install_kit(kit_src, studio_dir, "failmanifest", install_mode="copy")

            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["kit"], "failmanifest")
            self.assertEqual(result["errors"], ["cannot write core"])

    def test_missing_core_toml(self):
        from studio.commands.kit import _register_kit_in_core_toml
        # Should not raise
        _register_kit_in_core_toml(Path("/nonexistent"), "k", "1", Path("/x"))


class TestRegenerateGenAggregates(unittest.TestCase):
    def test_ignores_unregistered_config_kit_dirs(self):
        from studio.commands.kit import regenerate_gen_aggregates
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"
            loose_kit = config / "kits" / "loose"
            loose_kit.mkdir(parents=True)
            (loose_kit / "SKILL.md").write_text("# Loose Skill\n", encoding="utf-8")
            (loose_kit / "AGENTS.md").write_text("# Loose Agents\n", encoding="utf-8")
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {},
            }, config / "core.toml")
            toml_utils.dump({
                "systems": [{"name": "MyProject", "slug": "myproject", "kit": "sdlc"}],
            }, config / "artifacts.toml")

            regenerate_gen_aggregates(adapter)

            gen_agents = (adapter / ".gen" / "AGENTS.md").read_text(encoding="utf-8")
            self.assertFalse((adapter / ".gen" / "SKILL.md").exists())
            self.assertNotIn("# Loose Agents", gen_agents)

    def test_uses_default_installed_kit_path_when_path_not_explicitly_registered(self):
        from studio.commands.kit import regenerate_gen_aggregates
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"
            default_kit = config / "kits" / "sdlc"
            default_kit.mkdir(parents=True)
            (default_kit / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
            (default_kit / "AGENTS.md").write_text("# Default Agents\n", encoding="utf-8")
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                    },
                },
            }, config / "core.toml")
            toml_utils.dump({
                "systems": [{"name": "MyProject", "slug": "myproject", "kit": "sdlc"}],
            }, config / "artifacts.toml")

            regenerate_gen_aggregates(adapter)

            gen_agents = (adapter / ".gen" / "AGENTS.md").read_text(encoding="utf-8")
            self.assertFalse((adapter / ".gen" / "SKILL.md").exists())
            self.assertIn("# Default Agents", gen_agents)

    def test_deletes_legacy_generated_skill_aggregate(self):
        from studio.commands.kit import regenerate_gen_aggregates
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"
            gen_dir = adapter / ".gen"
            gen_dir.mkdir(parents=True, exist_ok=True)
            legacy_skill = gen_dir / "SKILL.md"
            legacy_skill.write_text("# Studio Generated Skills\n", encoding="utf-8")
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {},
            }, config / "core.toml")

            result = regenerate_gen_aggregates(adapter)

            self.assertEqual(result["gen_skill"], "deleted")
            self.assertFalse(legacy_skill.exists())

    def test_uses_registered_custom_kit_path(self):
        from studio.commands.kit import regenerate_gen_aggregates
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"
            custom_kit = adapter / "custom-kits" / "sdlc"
            custom_kit.mkdir(parents=True)
            (custom_kit / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
            (custom_kit / "AGENTS.md").write_text("# Custom Agents\n", encoding="utf-8")
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "custom-kits/sdlc",
                    },
                },
            }, config / "core.toml")
            toml_utils.dump({
                "systems": [{"name": "MyProject", "slug": "myproject", "kit": "sdlc"}],
            }, config / "artifacts.toml")

            regenerate_gen_aggregates(adapter)

            gen_agents = (adapter / ".gen" / "AGENTS.md").read_text(encoding="utf-8")
            self.assertFalse((adapter / ".gen" / "SKILL.md").exists())
            self.assertIn("# Custom Agents", gen_agents)

    def test_uses_registered_absolute_custom_kit_path(self):
        from studio.commands.kit import regenerate_gen_aggregates
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"
            custom_kit = Path(td) / "external-kits" / "sdlc"
            custom_kit.mkdir(parents=True)
            (custom_kit / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
            (custom_kit / "AGENTS.md").write_text("# Custom Agents\n", encoding="utf-8")
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": custom_kit.as_posix(),
                    },
                },
            }, config / "core.toml")
            toml_utils.dump({
                "systems": [{"name": "MyProject", "slug": "myproject", "kit": "sdlc"}],
            }, config / "artifacts.toml")

            regenerate_gen_aggregates(adapter)

            gen_agents = (adapter / ".gen" / "AGENTS.md").read_text(encoding="utf-8")
            self.assertFalse((adapter / ".gen" / "SKILL.md").exists())
            self.assertIn("# Custom Agents", gen_agents)

    def test_uses_registered_windows_drive_custom_kit_path(self):
        from studio.commands.kit import regenerate_gen_aggregates
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            if os.name == "nt":
                self.skipTest("Cross-OS absolute-path regression is specific to non-Windows hosts")
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"
            fake_project_relative_kit = adapter / "C:" / "external-kits" / "sdlc"
            fake_project_relative_kit.mkdir(parents=True)
            (fake_project_relative_kit / "SKILL.md").write_text("# Wrong Skill\n", encoding="utf-8")
            (fake_project_relative_kit / "AGENTS.md").write_text("# Fake Project Relative Agents\n", encoding="utf-8")
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "C:/external-kits/sdlc",
                    },
                },
            }, config / "core.toml")
            toml_utils.dump({
                "systems": [{"name": "MyProject", "slug": "myproject", "kit": "sdlc"}],
            }, config / "artifacts.toml")

            regenerate_gen_aggregates(adapter)

            gen_agents = (adapter / ".gen" / "AGENTS.md").read_text(encoding="utf-8")
            self.assertFalse((adapter / ".gen" / "SKILL.md").exists())
            self.assertNotIn("# Fake Project Relative Agents", gen_agents)

    def test_uses_registered_windows_backslash_custom_kit_path(self):
        from studio.commands.kit import regenerate_gen_aggregates
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            if os.name == "nt":
                self.skipTest("Cross-OS absolute-path regression is specific to non-Windows hosts")
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"
            fake_project_relative_kit = adapter / r"C:\external-kits\sdlc"
            fake_project_relative_kit.mkdir(parents=True)
            (fake_project_relative_kit / "SKILL.md").write_text("# Wrong Skill\n", encoding="utf-8")
            (fake_project_relative_kit / "AGENTS.md").write_text("# Fake Project Relative Agents\n", encoding="utf-8")
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": r"C:\external-kits\sdlc",
                    },
                },
            }, config / "core.toml")
            toml_utils.dump({
                "systems": [{"name": "MyProject", "slug": "myproject", "kit": "sdlc"}],
            }, config / "artifacts.toml")

            regenerate_gen_aggregates(adapter)

            gen_agents = (adapter / ".gen" / "AGENTS.md").read_text(encoding="utf-8")
            self.assertFalse((adapter / ".gen" / "SKILL.md").exists())
            self.assertNotIn("# Fake Project Relative Agents", gen_agents)


# ---------------------------------------------------------------------------
# _read_kit_version_from_core
# ---------------------------------------------------------------------------

class TestReadKitVersionFromCore(unittest.TestCase):
    def test_missing(self):
        from studio.commands.kit import _read_kit_version_from_core
        self.assertEqual(_read_kit_version_from_core(Path("/nonexistent"), "x"), "")

    def test_found(self):
        from studio.commands.kit import _read_kit_version_from_core
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            toml_utils.dump({"kits": {"sdlc": {"version": "3"}}}, Path(td) / "core.toml")
            self.assertEqual(_read_kit_version_from_core(Path(td), "sdlc"), "3")


# ---------------------------------------------------------------------------
# cmd_kit_install CLI GitHub path (mocked)
# ---------------------------------------------------------------------------

class TestCmdKitInstallGithubPath(unittest.TestCase):
    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_install_from_github_mocked(self):
        from studio.commands.kit import cmd_kit_install
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_manifest_kit_source(Path(td) / "dl", "sdlc")

            cwd = os.getcwd()
            try:
                os.chdir(root)
                with (
                    patch(
                        "studio.commands.kit._resolve_latest_github_release",
                        return_value="1.0",
                    ),
                    patch(
                        "studio.commands.kit._download_kit_from_github",
                        return_value=(kit_src, "1.0"),
                    ),
                ):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = cmd_kit_install(["constructorfabric/studio-kit-sdlc"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertIn(out["status"], ["PASS", "OK"])
            finally:
                os.chdir(cwd)

    def test_invalid_source_format(self):
        from studio.commands.kit import cmd_kit_install
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(io.StringIO()):
            rc = cmd_kit_install(["bad-no-slash"])
        self.assertEqual(rc, 2)

    def test_download_failure(self):
        from studio.commands.kit import cmd_kit_install
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_project(root)
            cwd = os.getcwd()
            try:
                os.chdir(root)
                with patch(
                    "studio.commands.kit._download_kit_from_github",
                    side_effect=RuntimeError("rate limit"),
                ):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = cmd_kit_install(["owner/repo"])
                self.assertEqual(rc, 1)
            finally:
                os.chdir(cwd)


# ---------------------------------------------------------------------------
# cmd_kit_update CLI paths
# ---------------------------------------------------------------------------

def test_cmd_kit_update_accepts_project_root(tmp_path, monkeypatch):
    from studio.commands import kit as kit_mod

    captured = {}

    def fake_resolve_studio_dir(project_root_arg=None):
        captured["project_root_arg"] = project_root_arg
        return None

    monkeypatch.setattr(kit_mod, "_resolve_studio_dir", fake_resolve_studio_dir)

    rc = kit_mod.cmd_kit_update(["--project-root", str(tmp_path)])

    assert rc == 1
    assert captured["project_root_arg"] == tmp_path


class TestCmdKitUpdateCli(unittest.TestCase):
    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_update_local_path(self):
        from studio.commands.kit import cmd_kit_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td) / "src", "testkit")
            # Register kit in core.toml so it's installed
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {"testkit": {"format": "CFS", "path": "config/kits/testkit"}},
            }, adapter / "config" / "core.toml")
            # Create installed kit dir
            config_kit = adapter / "config" / "kits" / "testkit"
            config_kit.mkdir(parents=True)
            (config_kit / "SKILL.md").write_text("old\n", encoding="utf-8")

            cwd = os.getcwd()
            try:
                os.chdir(root)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["--path", str(kit_src), "--force", "-y"])
                self.assertEqual(rc, 0)
            finally:
                os.chdir(cwd)

    def test_install_accepts_path_prefix_alias(self):
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td) / "src", "pathalias")

            cwd = os.getcwd()
            try:
                os.chdir(root)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install([f"path/{kit_src}", "--install-mode", "copy", "--force"])
                self.assertEqual(rc, 0, buf.getvalue())
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
                with open(adapter / "config" / "core.toml", "rb") as f:
                    core = tomllib.load(f)
                self.assertIn("pathalias", core["kits"])
            finally:
                os.chdir(cwd)

    def test_update_accepts_path_prefix_alias(self):
        from studio.commands.kit import cmd_kit_update

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td) / "src", "pathalias")
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {"pathalias": {"format": "CFS", "path": "config/kits/pathalias"}},
            }, adapter / "config" / "core.toml")
            config_kit = adapter / "config" / "kits" / "pathalias"
            config_kit.mkdir(parents=True)
            (config_kit / "SKILL.md").write_text("old\n", encoding="utf-8")

            cwd = os.getcwd()
            try:
                os.chdir(root)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update([f"path/{kit_src}", "--force", "-y"])
                self.assertEqual(rc, 0, buf.getvalue())
                out = json.loads(buf.getvalue())
                self.assertEqual(out["results"][0]["kit"], "pathalias")
            finally:
                os.chdir(cwd)

    def test_update_local_path_uses_registered_slug_for_matching_path(self):
        from studio.commands.kit import cmd_kit_update
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = root / "studio-kit-gears"
            kit_src.mkdir(parents=True)
            (kit_src / "AGENTS.md").write_text("# Kit agents\n", encoding="utf-8")
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "gears": {
                        "format": "CFS",
                        "path": "../studio-kit-gears",
                        "version": "1",
                    }
                },
            }, adapter / "config" / "core.toml")

            wrong_fallback = adapter / "config" / "kits" / "studio-kit-gears"
            wrong_fallback.mkdir(parents=True)
            (wrong_fallback / "obsolete.md").write_text("stale\n", encoding="utf-8")

            cwd = os.getcwd()
            try:
                os.chdir(kit_src)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update([
                        "--path", ".",
                        "--project-root", str(root),
                        "--force",
                        "-y",
                    ])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["results"][0]["kit"], "gears")
                self.assertTrue((wrong_fallback / "obsolete.md").is_file())
            finally:
                os.chdir(cwd)

    def test_update_local_path_not_found(self):
        from studio.commands.kit import cmd_kit_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_project(root)
            cwd = os.getcwd()
            try:
                os.chdir(root)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["--path", "/no/such/dir"])
                self.assertEqual(rc, 2)
            finally:
                os.chdir(cwd)

    def test_update_no_kits_registered(self):
        from studio.commands.kit import cmd_kit_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            # core.toml with empty kits
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {},
            }, adapter / "config" / "core.toml")
            cwd = os.getcwd()
            try:
                os.chdir(root)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update([])
                self.assertEqual(rc, 2)
            finally:
                os.chdir(cwd)

    def test_update_slug_not_found(self):
        from studio.commands.kit import cmd_kit_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {"sdlc": {"format": "CFS", "path": "config/kits/sdlc", "source": "github:o/r"}},
            }, adapter / "config" / "core.toml")
            cwd = os.getcwd()
            try:
                os.chdir(root)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["nosuchkit"])
                self.assertEqual(rc, 2)
            finally:
                os.chdir(cwd)

    def test_update_register_mode_kit_without_source_is_current(self):
        from studio.commands.kit import cmd_kit_update
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = root / "kits" / "gears"
            kit_src.mkdir(parents=True)
            (kit_src / "SKILL.md").write_text("# Gears\n", encoding="utf-8")
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "gears": {
                        "format": "CFS",
                        "path": "../kits/gears",
                        "version": "1.0.0",
                        "install_mode": "register",
                    }
                },
            }, adapter / "config" / "core.toml")

            cwd = os.getcwd()
            try:
                os.chdir(root)
                for argv in (["gears"], ["gears", "--force"]):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = cmd_kit_update(argv)
                    self.assertEqual(rc, 0, (argv, buf.getvalue()))
                    out = json.loads(buf.getvalue())
                    self.assertEqual(out["status"], "PASS")
                    self.assertEqual(out["results"][0]["kit"], "gears")
                    self.assertEqual(out["results"][0]["action"], "current")
            finally:
                os.chdir(cwd)

    def test_update_from_github_source(self):
        from studio.commands.kit import cmd_kit_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td) / "dl", "sdlc")
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {"sdlc": {"format": "CFS", "path": "config/kits/sdlc", "source": "github:cyberfabric/cyber-pilot-kit-sdlc"}},
            }, adapter / "config" / "core.toml")

            cwd = os.getcwd()
            try:
                os.chdir(root)
                with (
                    patch(
                        "studio.commands.kit._resolve_latest_github_release",
                        return_value="1.0",
                    ),
                    patch(
                        "studio.commands.kit._download_kit_from_github",
                        return_value=(kit_src, "1.0"),
                    ),
                ):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = cmd_kit_update(["sdlc", "--force", "-y"])
                self.assertEqual(rc, 0)
            finally:
                os.chdir(cwd)

    def test_update_github_download_failure(self):
        from studio.commands.kit import cmd_kit_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {"sdlc": {"format": "CFS", "path": "config/kits/sdlc", "source": "github:o/r"}},
            }, adapter / "config" / "core.toml")
            cwd = os.getcwd()
            try:
                os.chdir(root)
                with patch(
                    "studio.commands.kit._download_kit_from_github",
                    side_effect=RuntimeError("rate limit"),
                ):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = cmd_kit_update([])
                self.assertEqual(rc, 2)
            finally:
                os.chdir(cwd)

    def test_update_unsupported_source(self):
        from studio.commands.kit import cmd_kit_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {"mykit": {"format": "CFS", "path": "config/kits/mykit", "source": "ftp://bad"}},
            }, adapter / "config" / "core.toml")
            cwd = os.getcwd()
            try:
                os.chdir(root)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update([])
                self.assertEqual(rc, 2)
            finally:
                os.chdir(cwd)

    def test_update_no_source_skipped(self):
        from studio.commands.kit import cmd_kit_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {"mykit": {"format": "CFS", "path": "config/kits/mykit"}},
            }, adapter / "config" / "core.toml")
            cwd = os.getcwd()
            try:
                os.chdir(root)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update([])
                self.assertEqual(rc, 2)
            finally:
                os.chdir(cwd)

    def test_update_all_fail_returns_nonzero(self):
        """cmd_kit_update returns 2 when all kit updates raise errors."""
        from studio.commands.kit import cmd_kit_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td) / "src", "mykit")
            cwd = os.getcwd()
            try:
                os.chdir(root)
                with patch(
                    "studio.commands.kit.update_kit",
                    side_effect=RuntimeError("forced failure"),
                ):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = cmd_kit_update(["--path", str(kit_src)])
                self.assertEqual(rc, 2)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "FAIL")
                self.assertTrue(
                    all(r.get("action") == "failed" for r in out["results"]),
                    f"Expected all actions to be failed, got {out['results']}",
                )
            finally:
                os.chdir(cwd)


# ---------------------------------------------------------------------------
# update_kit version-check + partial/declined paths
# ---------------------------------------------------------------------------

class TestUpdateKitVersionPaths(unittest.TestCase):
    def test_dry_run(self):
        from studio.commands.kit import update_kit
        with TemporaryDirectory() as td:
            src = _make_kit_source(Path(td) / "src", "tk")
            cyp = Path(td) / "cyp"
            (cyp / "config" / "kits" / "tk").mkdir(parents=True)
            r = update_kit("tk", src, cyp, dry_run=True)
            self.assertEqual(r["version"]["status"], "dry_run")

    def test_version_current_skips(self):
        from studio.commands.kit import update_kit
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            src = _make_kit_source(Path(td) / "src", "tk")
            cyp = Path(td) / "cyp"
            config_kit = cyp / "config" / "kits" / "tk"
            config_kit.mkdir(parents=True)
            (config_kit / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
            toml_utils.dump({
                "kits": {"tk": {"version": "1", "path": "config/kits/tk"}},
            }, cyp / "config" / "core.toml")
            # Source has version=1 via conf.toml
            r = update_kit("tk", src, cyp, force=False)
            self.assertEqual(r["version"]["status"], "current")
            self.assertNotIn("skill_nav", r)

    def test_manifest_invalid_binding_returns_failed_without_writing(self):
        from studio.commands.kit import update_kit
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            src = _make_manifest_kit_source(Path(td) / "src", "tk")
            cyp = Path(td) / "cyp"
            config_kit = cyp / "config" / "kits" / "tk"
            config_kit.mkdir(parents=True)
            skill_path = config_kit / "SKILL.md"
            skill_path.write_text("# Existing Skill\n", encoding="utf-8")
            invalid_binding = "/opt/cypilot/constraints.toml" if os.name == "nt" else "C:/external-kits/sdlc/constraints.toml"
            toml_utils.dump({
                "version": "1.0",
                "kits": {
                    "tk": {
                        "version": "0",
                        "path": "config/kits/tk",
                        "resources": {
                            "skill": {"path": "config/kits/tk/SKILL.md"},
                            "agents": {"path": "config/kits/tk/AGENTS.md"},
                            "constraints": {"path": invalid_binding},
                        },
                    },
                },
            }, cyp / "config" / "core.toml")

            r = update_kit("tk", src, cyp, auto_approve=True)

            self.assertEqual(r["version"]["status"], "failed")
            self.assertTrue(any("not accessible on this OS" in err for err in r.get("errors", [])))
            self.assertEqual(skill_path.read_text(encoding="utf-8"), "# Existing Skill\n")


# ---------------------------------------------------------------------------
# Regression tests for phase-04 Sonar refactor bugs
# ---------------------------------------------------------------------------

class TestFirstInstallSourcePersistence(unittest.TestCase):
    """Regression A: update_kit first-install must persist source in core.toml."""

    def test_first_install_persists_source(self):
        from studio.commands.kit import update_kit
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root, "cypilot")
            kit_src = _make_kit_source(Path(td) / "src", "demo")

            r = update_kit("demo", kit_src, adapter, source="github:owner/repo", interactive=False)

            self.assertEqual(r["version"]["status"], "created")
            core_toml = adapter / "config" / "core.toml"
            self.assertTrue(core_toml.is_file())
            with open(core_toml, "rb") as f:
                data = tomllib.load(f)
            kit_entry = data.get("kits", {}).get("demo", {})
            self.assertEqual(kit_entry.get("path"), "config/kits/demo")
            self.assertIn("version", kit_entry)
            self.assertEqual(kit_entry.get("source"), "github:owner/repo")


class TestDetectMigrateLayoutFailureSafe(unittest.TestCase):
    """Regression B+C: _detect_and_migrate_layout must be failure-safe."""

    def _setup_adapter(self, td: Path) -> Path:
        """Create a minimal adapter dir with config/core.toml."""
        adapter = Path(td) / "adapter"
        (adapter / "config" / "kits").mkdir(parents=True)
        from studio.utils import toml_utils
        toml_utils.dump({
            "version": "1.0",
            "kits": {"badkit": {"format": "CFS", "path": "kits/badkit"}},
        }, adapter / "config" / "core.toml")
        return adapter

    def test_failed_migration_keeps_legacy_dirs_and_core_toml(self):
        """B: when kits/badkit migration fails, kits/ and .gen/kits/ must survive."""
        from studio.commands.kit import _detect_and_migrate_layout
        import tomllib
        with TemporaryDirectory() as td:
            adapter = self._setup_adapter(Path(td))

            # Create legacy kits/ and .gen/kits/ for badkit
            kit_legacy = adapter / "kits" / "badkit"
            kit_legacy.mkdir(parents=True)
            (kit_legacy / "SKILL.md").write_text("# Kit\n", encoding="utf-8")
            gen_kit_legacy = adapter / ".gen" / "kits" / "badkit"
            gen_kit_legacy.mkdir(parents=True)
            (gen_kit_legacy / "SKILL.md").write_text("# Gen Kit\n", encoding="utf-8")

            # Force kits/badkit iteration to raise so migration fails
            original_iterdir = Path.iterdir
            def _failing_iterdir(self_path):
                if self_path == kit_legacy:
                    raise OSError("boom")
                return original_iterdir(self_path)

            with patch.object(Path, "iterdir", _failing_iterdir):
                result = _detect_and_migrate_layout(adapter)

            self.assertTrue(result.get("badkit", "").startswith("FAILED"),
                            f"Expected FAILED status, got: {result}")
            self.assertTrue((adapter / "kits").is_dir(), "kits/ was deleted on failure")
            self.assertTrue((adapter / ".gen" / "kits").is_dir(), ".gen/kits/ was deleted on failure")

            # core.toml path must still point to legacy location
            with open(adapter / "config" / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(data["kits"]["badkit"]["path"], "kits/badkit",
                             "core.toml was rewritten despite migration failure")

    def test_gen_failure_overrides_earlier_success_for_same_slug(self):
        """C: .gen/kits/{slug} failure must override earlier kits/{slug} success."""
        from studio.commands.kit import _detect_and_migrate_layout
        import tomllib
        with TemporaryDirectory() as td:
            adapter = self._setup_adapter(Path(td))
            # Reset core.toml to reference samekit via kits/
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "kits": {"samekit": {"format": "CFS", "path": "kits/samekit"}},
            }, adapter / "config" / "core.toml")

            # Create legacy kits/samekit (will succeed) and .gen/kits/samekit (will fail)
            kit_legacy = adapter / "kits" / "samekit"
            kit_legacy.mkdir(parents=True)
            (kit_legacy / "SKILL.md").write_text("# Kit\n", encoding="utf-8")
            gen_kit_legacy = adapter / ".gen" / "kits" / "samekit"
            gen_kit_legacy.mkdir(parents=True)
            (gen_kit_legacy / "SKILL.md").write_text("# Gen Kit\n", encoding="utf-8")

            # Force .gen/kits/samekit iteration to raise
            original_iterdir = Path.iterdir
            def _failing_gen_iterdir(self_path):
                if self_path == gen_kit_legacy:
                    raise OSError("gen-boom")
                return original_iterdir(self_path)

            with patch.object(Path, "iterdir", _failing_gen_iterdir):
                result = _detect_and_migrate_layout(adapter)

            self.assertTrue(result.get("samekit", "").startswith("FAILED"),
                            f"Expected FAILED (not masked), got: {result}")
            # Legacy dirs must survive
            self.assertTrue((adapter / "kits").is_dir(), "kits/ was deleted on failure")
            self.assertTrue((adapter / ".gen" / "kits").is_dir(), ".gen/kits/ was deleted on failure")
            # core.toml must not have been rewritten
            with open(adapter / "config" / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(data["kits"]["samekit"]["path"], "kits/samekit",
                             "core.toml was rewritten despite .gen migration failure")


# ---------------------------------------------------------------------------
# Regression: partial GitHub source failures surfaced in structured output
# ---------------------------------------------------------------------------

class TestPartialGithubSourceFailures(unittest.TestCase):
    """Bug 1: cmd_kit_update must surface per-kit failures when some GitHub
    downloads fail while others succeed."""

    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_one_good_one_bad_github_kit(self):
        """One kit downloads OK, one fails → partial failure in results."""
        from studio.commands.kit import cmd_kit_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            good_src = _make_kit_source(Path(td) / "dl", "goodkit")
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "goodkit": {"format": "CFS", "path": "config/kits/goodkit", "source": "github:owner/goodkit"},
                    "badkit": {"format": "CFS", "path": "config/kits/badkit", "source": "github:owner/badkit"},
                },
            }, adapter / "config" / "core.toml")

            def _mock_download(owner, repo, version):
                if repo == "goodkit":
                    return (good_src, "1.0")
                raise RuntimeError("rate limit")

            cwd = os.getcwd()
            try:
                os.chdir(root)
                with patch("studio.commands.kit._download_kit_from_github", side_effect=_mock_download):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = cmd_kit_update(["--force", "-y"])
                self.assertEqual(rc, 2)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "FAIL")
                self.assertIn("errors", out)
                # Failed kit must appear in results
                slugs = {r["kit"] for r in out["results"]}
                self.assertIn("badkit", slugs)
                self.assertIn("goodkit", slugs)
                bad_r = next(r for r in out["results"] if r["kit"] == "badkit")
                self.assertEqual(bad_r["action"], "failed")
                self.assertIn("message", bad_r)
            finally:
                os.chdir(cwd)

    def test_all_kits_fail_returns_structured_errors(self):
        """When ALL kits fail download, rc=2 but results contain per-kit errors."""
        from studio.commands.kit import cmd_kit_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "k1": {"format": "CFS", "path": "config/kits/k1", "source": "github:o/r1"},
                    "k2": {"format": "CFS", "path": "config/kits/k2", "source": "github:o/r2"},
                },
            }, adapter / "config" / "core.toml")

            cwd = os.getcwd()
            try:
                os.chdir(root)
                with patch(
                    "studio.commands.kit._download_kit_from_github",
                    side_effect=RuntimeError("network error"),
                ):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = cmd_kit_update([])
                self.assertEqual(rc, 2)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "FAIL")
                self.assertIn("results", out)
                self.assertEqual(len(out["results"]), 2)
                for r in out["results"]:
                    self.assertEqual(r["action"], "failed")
            finally:
                os.chdir(cwd)

    def test_resolve_github_update_targets_returns_failures(self):
        """_resolve_github_update_targets returns (targets, failures) tuple."""
        from studio.commands.kit import _resolve_github_update_targets
        kits_map = {
            "nokit": {"format": "CFS"},
            "badproto": {"format": "CFS", "source": "local:/nonexistent"},
        }
        targets, failures = _resolve_github_update_targets(kits_map)
        self.assertEqual(targets, [])
        self.assertEqual(len(failures), 2)
        slugs = {f["kit"] for f in failures}
        self.assertEqual(slugs, {"nokit", "badproto"})
        for f in failures:
            self.assertEqual(f["action"], "ERROR")
            self.assertIn("message", f)


# ---------------------------------------------------------------------------
# Regression: unchanged count preserved through cmd_kit_update
# ---------------------------------------------------------------------------

class TestUnchangedPreservedInUpdateResult(unittest.TestCase):
    """Bug 2: unchanged count from file_level_kit_update must survive
    through _build_kit_update_result into the emitted JSON."""

    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_build_kit_update_result_preserves_unchanged(self):
        """_build_kit_update_result extracts unchanged from gen dict."""
        from studio.commands.kit import _build_kit_update_result
        kit_r = {
            "version": {"status": "current"},
            "gen": {"files_written": 0, "accepted_files": [], "unchanged": 7},
        }
        result = _build_kit_update_result("mykit", kit_r)
        self.assertEqual(result["unchanged"], 7)
        self.assertEqual(result["action"], "current")

    def test_build_kit_update_result_unchanged_defaults_zero(self):
        """When gen has no unchanged key, defaults to 0."""
        from studio.commands.kit import _build_kit_update_result
        kit_r = {
            "version": {"status": "updated"},
            "gen": {"files_written": 2, "accepted_files": ["a.md", "b.md"]},
        }
        result = _build_kit_update_result("mykit", kit_r)
        self.assertEqual(result["unchanged"], 0)

    def test_cmd_kit_update_emits_unchanged(self):
        """Full cmd_kit_update path with identical files → unchanged in JSON results."""
        from studio.commands.kit import cmd_kit_update, install_kit
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td), "unchkit")
            install_kit(kit_src, adapter, "unchkit")
            # Update with identical source → all files unchanged
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["--path", str(kit_src), "--force"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                r = out["results"][0]
                self.assertIn("unchanged", r)
                self.assertGreaterEqual(r["unchanged"], 0)
            finally:
                os.chdir(cwd)


# ---------------------------------------------------------------------------
# Regression: init artifact_kinds metadata preserved
# ---------------------------------------------------------------------------

class TestInitArtifactKindsMetadata(unittest.TestCase):
    """Bug 3: _install_default_kit must propagate artifact_kinds into
    kit_results so _human_init_ok can display them."""

    def test_install_default_kit_includes_artifact_kinds(self):
        from studio.commands.init import _install_default_kit
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td) / "dl", "sdlc")

            with patch(
                "studio.commands.kit._parse_github_source",
                return_value=("owner", "repo", "v1"),
            ), patch(
                "studio.commands.kit._download_kit_from_github",
                return_value=(kit_src, "1.0"),
            ):
                actions: dict = {}
                errors: list = []
                kit_results = _install_default_kit(adapter, False, actions, errors)

            self.assertIn("sdlc", kit_results)
            kr = kit_results["sdlc"]
            self.assertIn("artifact_kinds", kr)
            # Our _make_kit_source creates artifacts/FEATURE/
            self.assertIn("FEATURE", kr["artifact_kinds"])
            self.assertGreater(kr["files_written"], 0)


# ---------------------------------------------------------------------------
# Regression: init.py status contract alignment with kit.py
# ---------------------------------------------------------------------------

class TestInitKitStatusContract(unittest.TestCase):
    """_install_default_kit must treat kit status 'PASS' as success (no warning)
    and 'WARN' as a warning — not misreport due to checking wrong status values."""

    def test_pass_status_emits_substep_not_warn(self):
        """PASS from install_kit → substep (success), never warn."""
        from studio.commands.init import _install_default_kit
        from studio.utils.ui import ui as _ui_inst
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td) / "dl", "sdlc")

            warns = []
            orig_warn = _ui_inst.warn
            _ui_inst.warn = lambda msg, **kw: warns.append(msg)
            try:
                with patch(
                    "studio.commands.kit._parse_github_source",
                    return_value=("owner", "repo", "v1"),
                ), patch(
                    "studio.commands.kit._download_kit_from_github",
                    return_value=(kit_src, "1.0"),
                ):
                    actions: dict = {}
                    errors: list = []
                    _install_default_kit(adapter, False, actions, errors)
            finally:
                _ui_inst.warn = orig_warn

            self.assertEqual(errors, [])
            kit_warns = [w for w in warns if "sdlc" in w and "installed" in w.lower()]
            self.assertEqual(kit_warns, [], "PASS status should not emit a kit warning")

    def test_warn_status_emits_warning(self):
        """WARN from install_kit → ui.warn is called."""
        from studio.commands.init import _install_default_kit
        from studio.utils.ui import ui as _ui_inst
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td) / "dl", "sdlc")

            warns = []
            orig_warn = _ui_inst.warn
            _ui_inst.warn = lambda msg, **kw: warns.append(msg)
            mock_result = {"status": "WARN", "errors": ["minor issue"], "files_copied": 1, "actions": {}}
            try:
                with patch(
                    "studio.commands.kit._parse_github_source",
                    return_value=("owner", "repo", "v1"),
                ), patch(
                    "studio.commands.kit._download_kit_from_github",
                    return_value=(kit_src, "1.0"),
                ), patch(
                    "studio.commands.kit.install_kit",
                    return_value=mock_result,
                ):
                    actions: dict = {}
                    errors: list = []
                    _install_default_kit(adapter, False, actions, errors)
            finally:
                _ui_inst.warn = orig_warn

            kit_warns = [w for w in warns if "sdlc" in w]
            self.assertGreater(len(kit_warns), 0, "WARN status should emit a kit warning")

    def test_warn_status_does_not_promote_errors_to_fatal(self):
        """WARN from install_kit → errors list stays empty (not fatal)."""
        from studio.commands.init import _install_default_kit
        from studio.utils.ui import ui as _ui_inst
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td) / "dl", "sdlc")

            orig_warn = _ui_inst.warn
            _ui_inst.warn = lambda msg, **kw: None
            mock_result = {"status": "WARN", "errors": ["minor issue"], "files_copied": 1, "actions": {}}
            try:
                with patch(
                    "studio.commands.kit._parse_github_source",
                    return_value=("owner", "repo", "v1"),
                ), patch(
                    "studio.commands.kit._download_kit_from_github",
                    return_value=(kit_src, "1.0"),
                ), patch(
                    "studio.commands.kit.install_kit",
                    return_value=mock_result,
                ):
                    actions: dict = {}
                    errors: list = []
                    _install_default_kit(adapter, False, actions, errors)
            finally:
                _ui_inst.warn = orig_warn

            self.assertEqual(errors, [],
                "WARN kit errors must not be promoted to the fatal errors list")

    def test_error_status_does_promote_errors_to_fatal(self):
        """Non-WARN/non-PASS status → errors ARE promoted to fatal list."""
        from studio.commands.init import _install_default_kit
        from studio.utils.ui import ui as _ui_inst
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root)
            kit_src = _make_kit_source(Path(td) / "dl", "sdlc")

            orig_warn = _ui_inst.warn
            _ui_inst.warn = lambda msg, **kw: None
            mock_result = {"status": "ERROR", "errors": ["fatal issue"], "files_copied": 0, "actions": {}}
            try:
                with patch(
                    "studio.commands.kit._parse_github_source",
                    return_value=("owner", "repo", "v1"),
                ), patch(
                    "studio.commands.kit._download_kit_from_github",
                    return_value=(kit_src, "1.0"),
                ), patch(
                    "studio.commands.kit.install_kit",
                    return_value=mock_result,
                ):
                    actions: dict = {}
                    errors: list = []
                    _install_default_kit(adapter, False, actions, errors)
            finally:
                _ui_inst.warn = orig_warn

            self.assertGreater(len(errors), 0,
                "ERROR kit errors must be promoted to the fatal errors list")


if __name__ == "__main__":
    unittest.main()
