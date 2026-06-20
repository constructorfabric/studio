"""
End-to-end CLI coverage for setup/config public surfaces.

These tests stay at the public ``studio.cli.main([...])`` layer and focus on
thin setup/config branches without re-testing deeper command internals already
covered elsewhere.
"""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.cli import main
from studio.utils import toml_utils


@contextmanager
def _chdir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _run_main(argv: list[str], *, cwd: Path) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with _chdir(cwd), redirect_stdout(stdout), redirect_stderr(stderr):
        rc = main(argv)
    return rc, stdout.getvalue(), stderr.getvalue()


def _run_main_json(argv: list[str], *, cwd: Path) -> tuple[int, dict, str]:
    rc, stdout, stderr = _run_main(["--json", *argv], cwd=cwd)
    return rc, json.loads(stdout), stderr


def _write_toml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    toml_utils.dump(data, path)


def _snapshot_tree(root: Path) -> dict[str, tuple[str, bytes | None]]:
    snapshot: dict[str, tuple[str, bytes | None]] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            snapshot[rel] = ("dir", None)
        elif path.is_file():
            snapshot[rel] = ("file", path.read_bytes())
    return snapshot


def _bootstrap_adapter_project(root: Path, adapter_rel: str = "adapter") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    (root / "AGENTS.md").write_text(
        f'<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "{adapter_rel}"\n```\n<!-- /@cf:root-agents -->\n',
        encoding="utf-8",
    )
    adapter = root / adapter_rel
    (adapter / ".core").mkdir(parents=True, exist_ok=True)
    (adapter / ".gen").mkdir(parents=True, exist_ok=True)
    (adapter / "config").mkdir(parents=True, exist_ok=True)
    (adapter / "config" / "AGENTS.md").write_text("# Test adapter\n", encoding="utf-8")
    return adapter


def _bootstrap_generator_project(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "skills" / "cypilot").mkdir(parents=True, exist_ok=True)
    (root / "skills" / "cypilot" / "SKILL.md").write_text(
        "---\nname: cypilot\ndescription: Test skill\n---\n# Cypilot\n",
        encoding="utf-8",
    )
    (root / "workflows").mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "generate.md").write_text(
        "---\ntype: workflow\nname: cypilot-generate\ndescription: Generate\n---\n# Generate\n",
        encoding="utf-8",
    )
    (root / "workflows" / "analyze.md").write_text(
        "---\ntype: workflow\nname: cypilot-analyze\ndescription: Analyze\n---\n# Analyze\n",
        encoding="utf-8",
    )


def _write_legacy_follow_stub(path: Path, follow_target: str, *, name: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = ""
    if name is not None:
        frontmatter = f"---\nname: {name}\n---\n"
    path.write_text(
        frontmatter + f"ALWAYS open and follow `{follow_target}`\n",
        encoding="utf-8",
    )


def _bootstrap_legacy_cypilot_outputs(root: Path) -> None:
    _write_legacy_follow_stub(
        root / ".claude" / "skills" / "cypilot" / "SKILL.md",
        "{cypilot_path}/skills/cypilot/SKILL.md",
        name="cypilot",
    )
    _write_legacy_follow_stub(
        root / ".claude" / "skills" / "cypilot-analyze" / "SKILL.md",
        "{cypilot_path}/workflows/analyze.md",
        name="cypilot-analyze",
    )
    _write_legacy_follow_stub(
        root / ".claude" / "skills" / "cypilot-generate" / "SKILL.md",
        "{cypilot_path}/workflows/generate.md",
        name="cypilot-generate",
    )
    _write_legacy_follow_stub(
        root / ".claude" / "agents" / "cypilot-reviewer.md",
        "{cypilot_path}/agents/reviewer.md",
    )


def _make_test_cache(cache_dir: Path) -> Path:
    from _test_helpers import make_test_cache

    make_test_cache(cache_dir)
    (cache_dir / "whatsnew.toml").write_text(
        '[whatsnew."v1.0.0"]\nsummary = "Initial"\ndetails = ""\n',
        encoding="utf-8",
    )
    (cache_dir / "version.toml").write_text(
        '[cfs]\nversion = "v1.0.0"\n',
        encoding="utf-8",
    )
    return cache_dir


def _bootstrap_legacy_project(root: Path, legacy_dir: str = "cypilot", version: str = "3.9.0") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    (root / "AGENTS.md").write_text(
        '<!-- @cpt:root-agents -->\n'
        '```toml\n'
        f'cypilot_path = "{legacy_dir}"\n'
        '```\n'
        '<!-- /@cpt:root-agents -->\n'
        '\n'
        '# Project rules\n',
        encoding="utf-8",
    )
    (root / "CLAUDE.md").write_text(
        '<!-- @cpt:root-agents -->\n'
        '```toml\n'
        f'cypilot_path = "{legacy_dir}"\n'
        '```\n'
        '<!-- /@cpt:root-agents -->\n',
        encoding="utf-8",
    )
    legacy_root = root / legacy_dir
    config = legacy_root / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "core.toml").write_text(
        "# Cypilot project configuration\n"
        'version = "1.0"\n'
        'project_root = ".."\n'
        "\n"
        "[kits]\n"
        "[kits.sdlc]\n"
        'format = "CFS"\n'
        'path = "config/kits/sdlc"\n'
        'version = "1.0.0"\n'
        'source = "github:cyberfabric/cyber-pilot-kit-sdlc"\n',
        encoding="utf-8",
    )
    (config / "artifacts.toml").write_text(
        "# Cypilot artifacts registry\n"
        "\n"
        "[[systems]]\n"
        'name = "App"\n'
        'slug = "app"\n'
        'kit = "sdlc"\n',
        encoding="utf-8",
    )
    (config / "AGENTS.md").write_text(
        "These rules are loaded alongside `{cypilot_path}/.gen/AGENTS.md`.\n",
        encoding="utf-8",
    )
    version_file = legacy_root / ".core" / "skills" / "cypilot" / "scripts" / "cypilot" / "__init__.py"
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    return legacy_root


class TestInfoAndResolveVarsE2E(unittest.TestCase):
    def test_info_no_project_root_returns_not_found_without_writes(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "plain"
            root.mkdir(parents=True, exist_ok=True)
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(["info", "--root", str(root)], cwd=root)

            self.assertEqual(rc, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(out["status"], "NOT_FOUND")
            self.assertIn("No project root found", out["message"])
            self.assertEqual(_snapshot_tree(root), before)

    def test_info_not_initialized_project_returns_not_found_without_writes(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir(parents=True, exist_ok=True)
            (root / ".git").mkdir()
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(["info", "--root", str(root)], cwd=root)

            self.assertEqual(rc, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(out["status"], "NOT_FOUND")
            self.assertIn("not initialized", out["message"])
            self.assertEqual(_snapshot_tree(root), before)

    def test_info_honors_global_json_flag(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_adapter_project(root)
            _write_toml(
                adapter / "config" / "core.toml",
                {"version": "1.0", "project_root": "..", "kits": {}},
            )
            before = _snapshot_tree(root)
            gitignore_path = root / ".gitignore"
            self.assertFalse(gitignore_path.exists())

            rc, stdout, _stderr = _run_main(
                ["--json", "info", "--root", str(root)],
                cwd=root,
            )

            self.assertEqual(rc, 0)
            out = json.loads(stdout)
            self.assertEqual(out["status"], "FOUND")
            self.assertEqual(out["project_root"], root.resolve().as_posix())
            self.assertEqual(out["relative_path"], "adapter")
            self.assertTrue(out["has_config"])
            self.assertFalse(gitignore_path.exists())
            self.assertEqual(_snapshot_tree(root), before)

    def test_info_legacy_registry_json_fallback_is_reported(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_adapter_project(root)
            (adapter / "artifacts.json").write_text(
                json.dumps(
                    {
                        "version": "1.0",
                        "project_root": "..",
                        "systems": [{"name": "Legacy", "slug": "legacy", "artifacts": []}],
                    }
                ),
                encoding="utf-8",
            )
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(["info", "--root", str(root)], cwd=root)

            self.assertEqual(rc, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(out["status"], "FOUND")
            self.assertTrue(out["artifacts_registry_path"].endswith("artifacts.json"))
            self.assertIsNone(out["artifacts_registry_error"])
            self.assertEqual(out["artifacts_registry"]["systems"][0]["slug"], "legacy")
            self.assertEqual(_snapshot_tree(root), before)

    def test_info_cf_studio_root_override_returns_same_project_without_writes(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir(parents=True, exist_ok=True)
            (root / ".git").mkdir()
            cfs_root = root / "Cypilot"
            cfs_root.mkdir()
            (cfs_root / "AGENTS.md").write_text("# Cypilot Core\n", encoding="utf-8")
            (cfs_root / "requirements").mkdir()
            (cfs_root / "workflows").mkdir()
            adapter = root / ".cypilot-adapter"
            (adapter / "config" / "rules").mkdir(parents=True, exist_ok=True)
            (adapter / "AGENTS.md").write_text(
                "# Constructor Studio Adapter: RealProject\n\n"
                "**Extends**: `../Cypilot/AGENTS.md`\n",
                encoding="utf-8",
            )
            _write_toml(adapter / "config" / "core.toml", {"version": "1.0", "project_root": "..", "kits": {}})
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(
                ["info", "--root", str(root), "--cf-studio-root", str(cfs_root)],
                cwd=root,
            )

            self.assertEqual(rc, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(out["status"], "FOUND")
            self.assertEqual(out["project_root"], root.resolve().as_posix())
            self.assertEqual(out["project_name"], "RealProject")
            self.assertEqual(out["relative_path"], ".cypilot-adapter")
            self.assertTrue(out["has_config"])
            self.assertEqual(out["studio_dir"], adapter.resolve().as_posix())
            self.assertEqual(_snapshot_tree(root), before)

    def test_resolve_vars_flat_success_via_main(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_adapter_project(root)
            _write_toml(
                adapter / "config" / "core.toml",
                {
                    "version": "1.0",
                    "project_root": "..",
                    "kits": {
                        "sdlc": {
                            "resources": {
                                "adr_template": {
                                    "path": "config/kits/sdlc/artifacts/ADR/template.md",
                                },
                            },
                        },
                    },
                },
            )
            before = _snapshot_tree(root)
            gitignore_path = root / ".gitignore"
            self.assertFalse(gitignore_path.exists())

            rc, stdout, _stderr = _run_main(
                ["--json", "resolve-vars", "--root", str(root), "--flat"],
                cwd=root,
            )

            self.assertEqual(rc, 0)
            out = json.loads(stdout)
            self.assertIn("variables", out)
            self.assertIn("cf-studio-path", out["variables"])
            self.assertIn("adr_template", out["variables"])
            self.assertTrue(
                out["variables"]["adr_template"].endswith(
                    "config/kits/sdlc/artifacts/ADR/template.md"
                )
            )
            self.assertFalse(gitignore_path.exists())
            self.assertEqual(_snapshot_tree(root), before)

    def test_resolve_vars_missing_kit_errors_via_main(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_adapter_project(root)
            _write_toml(
                adapter / "config" / "core.toml",
                {"version": "1.0", "project_root": "..", "kits": {}},
            )
            before = _snapshot_tree(root)
            gitignore_path = root / ".gitignore"
            self.assertFalse(gitignore_path.exists())

            rc, stdout, _stderr = _run_main(
                ["--json", "resolve-vars", "--root", str(root), "--kit", "missing"],
                cwd=root,
            )

            self.assertEqual(rc, 1)
            out = json.loads(stdout)
            self.assertEqual(out["status"], "ERROR")
            self.assertIn("Kit 'missing' not found", out["message"])
            self.assertEqual(out["available_kits"], [])
            self.assertFalse(gitignore_path.exists())
            self.assertEqual(_snapshot_tree(root), before)

    def test_resolve_vars_no_project_root_errors_without_writes(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "plain"
            root.mkdir(parents=True, exist_ok=True)
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(["resolve-vars", "--root", str(root)], cwd=root)

            self.assertEqual(rc, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(out["status"], "ERROR")
            self.assertIn("No project root found", out["message"])
            self.assertEqual(_snapshot_tree(root), before)

    def test_resolve_vars_kit_filter_returns_only_selected_kit_and_system_vars(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_adapter_project(root)
            _write_toml(
                adapter / "config" / "core.toml",
                {
                    "version": "1.0",
                    "project_root": "..",
                    "kits": {
                        "alpha": {
                            "resources": {
                                "alpha_template": {"path": "config/kits/alpha/template.md"},
                            },
                        },
                        "beta": {
                            "resources": {
                                "beta_template": {"path": "config/kits/beta/template.md"},
                            },
                        },
                    },
                },
            )
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(
                ["resolve-vars", "--root", str(root), "--kit", "alpha", "--flat"],
                cwd=root,
            )

            self.assertEqual(rc, 0)
            self.assertEqual(stderr, "")
            self.assertIn("variables", out)
            self.assertIn("alpha_template", out["variables"])
            self.assertNotIn("beta_template", out["variables"])
            self.assertIn("cf-studio-path", out["variables"])
            self.assertEqual(_snapshot_tree(root), before)

    def test_resolve_vars_core_parse_warning_is_degraded_but_returns_json(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_adapter_project(root)
            (adapter / "config" / "core.toml").write_text(
                'version = "1.0"\nproject_root = ".."\ninvalid = [\n',
                encoding="utf-8",
            )
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(
                ["resolve-vars", "--root", str(root), "--flat"],
                cwd=root,
            )

            self.assertEqual(rc, 0)
            self.assertIn("Failed to parse", stderr)
            self.assertIn("core_load_error", out)
            self.assertIn("variables", out)
            self.assertIn("cf-studio-path", out["variables"])
            self.assertEqual(_snapshot_tree(root), before)


class TestUpdateE2E(unittest.TestCase):
    def test_update_bare_with_kits_requires_value(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            with _chdir(root), self.assertRaises(SystemExit):
                main(["update", "--with-kits"])

    def test_update_dry_run_accepts_explicit_option_matrix(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_adapter_project(root)
            core_toml_path = adapter / "config" / "core.toml"
            _write_toml(
                core_toml_path,
                {"version": "1.0", "project_root": "..", "kits": {}},
            )
            cache_dir = Path(td) / "cache"
            cache_dir.mkdir()
            before = _snapshot_tree(root)
            core_toml_before = core_toml_path.read_text(encoding="utf-8")
            gitignore_path = root / ".gitignore"
            self.assertFalse(gitignore_path.exists())

            with patch("studio.commands.update.CACHE_DIR", cache_dir):
                rc, stdout, _stderr = _run_main(
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

            self.assertEqual(rc, 0)
            out = json.loads(stdout)
            self.assertEqual(out["status"], "PASS")
            self.assertTrue(out["dry_run"])
            self.assertEqual(out["actions"]["core_toml_metadata"], "dry_run")
            self.assertEqual(out["actions"]["gitignore"], "dry_run")
            self.assertEqual(out["actions"]["kits"], {})
            self.assertFalse(gitignore_path.exists())
            self.assertEqual(core_toml_path.read_text(encoding="utf-8"), core_toml_before)
            self.assertEqual(_snapshot_tree(root), before)

    def test_update_success_has_bounded_filesystem_diff(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_adapter_project(root)
            _write_toml(
                adapter / "config" / "core.toml",
                {
                    "version": "1.0",
                    "project_root": "..",
                    "install": {
                        "version_source": "project_config",
                        "runtime_tracking": "ignored",
                        "agent_tracking": "ignored",
                        "kit_tracking": "tracked",
                    },
                    "kits": {},
                },
            )
            _write_toml(
                adapter / "config" / "artifacts.toml",
                {"version": "1.0", "project_root": "..", "kits": {}, "systems": []},
            )
            (adapter / ".core" / "obsolete.txt").write_text("old\n", encoding="utf-8")
            (adapter / "whatsnew.toml").write_text('[whatsnew."v0.9.0"]\nsummary = "Old"\n', encoding="utf-8")
            (adapter / "version.toml").write_text('[cfs]\nversion = "v0.9.0"\n', encoding="utf-8")
            before = _snapshot_tree(root)
            cache_dir = _make_test_cache(Path(td) / "cache")

            with patch("studio.commands.update.CACHE_DIR", cache_dir):
                rc, out, stderr = _run_main_json(
                    ["update", "--project-root", str(root), "--yes", "--migrate-from-cypilot", "no", "--update-legacy-studio", "no"],
                    cwd=root,
                )

            self.assertEqual(rc, 0, stderr)
            self.assertIn("What's new in Studio", stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["actions"]["gitignore"], "created")
            self.assertEqual(out["actions"]["root_agents"], "updated")
            self.assertEqual(out["actions"]["root_claude"], "created")
            self.assertEqual(out["actions"]["config_readme"], "created")
            self.assertEqual(out["actions"]["config_skill"], "created")
            self.assertEqual(out["actions"]["kits"]["status"], "skipped")
            self.assertEqual(out["validate_kits"]["status"], "PASS")

            after = _snapshot_tree(root)
            added_paths = sorted(set(after) - set(before))
            removed_paths = sorted(set(before) - set(after))
            changed_paths = sorted(path for path in set(before) & set(after) if before[path] != after[path])

            self.assertEqual(
                added_paths,
                sorted(
                    [
                        ".gitignore",
                        "CLAUDE.md",
                        "adapter/.core/README.md",
                        "adapter/.core/requirements",
                        "adapter/.core/requirements/README.md",
                        "adapter/.core/schemas",
                        "adapter/.core/schemas/README.md",
                        "adapter/.core/skills",
                        "adapter/.core/skills/README.md",
                        "adapter/.core/workflows",
                        "adapter/.core/workflows/README.md",
                        "adapter/.gen/AGENTS.md",
                        "adapter/.gen/README.md",
                        "adapter/config/README.md",
                        "adapter/config/SKILL.md",
                        "adapter/config/core.toml.lock",
                    ]
                ),
            )
            self.assertEqual(removed_paths, ["adapter/.core/obsolete.txt"])
            self.assertEqual(
                changed_paths,
                sorted(
                    [
                        "AGENTS.md",
                        "adapter/config/core.toml",
                        "adapter/version.toml",
                        "adapter/whatsnew.toml",
                    ]
                ),
            )
            self.assertFalse((adapter / ".core" / "obsolete.txt").exists())


class TestAgentsAndGenerateAgentsE2E(unittest.TestCase):
    def test_generate_agents_show_layers_legacy_via_main(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_generator_project(root)
            before = _snapshot_tree(root)
            gitignore_path = root / ".gitignore"
            self.assertFalse(gitignore_path.exists())

            rc, stdout, _stderr = _run_main(
                [
                    "--json",
                    "generate-agents",
                    "--agent",
                    "claude",
                    "--root",
                    str(root),
                    "--cf-constructor-root",
                    str(root),
                    "--show-layers",
                ],
                cwd=root,
            )

            self.assertEqual(rc, 0)
            out = json.loads(stdout)
            self.assertEqual(out["status"], "OK")
            self.assertEqual(out["provenance"]["components"], [])
            self.assertFalse(gitignore_path.exists())
            self.assertEqual(_snapshot_tree(root), before)

    def test_generate_agents_discover_writes_manifest_via_main(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_generator_project(root)
            (root / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
            (root / ".claude" / "agents" / "local-reviewer.md").write_text(
                "---\ndescription: Local reviewer\n---\n# Reviewer\n",
                encoding="utf-8",
            )
            before = _snapshot_tree(root)
            gitignore_path = root / ".gitignore"
            self.assertFalse(gitignore_path.exists())

            rc, stdout, _stderr = _run_main(
                [
                    "--json",
                    "generate-agents",
                    "--agent",
                    "claude",
                    "--root",
                    str(root),
                    "--cf-constructor-root",
                    str(root),
                    "--discover",
                    "--yes",
                ],
                cwd=root,
            )

            self.assertEqual(rc, 0)
            out = json.loads(stdout)
            self.assertEqual(out["status"], "PASS")
            manifest_path = root / "config" / "manifest.toml"
            self.assertTrue(manifest_path.exists())
            manifest_text = manifest_path.read_text(encoding="utf-8")
            self.assertIn('id = "local-reviewer"', manifest_text)
            self.assertIn(
                f'source = "{(root / ".claude" / "agents" / "local-reviewer.md").resolve().as_posix()}"',
                manifest_text,
            )
            self.assertTrue(gitignore_path.exists())
            gitignore_text = gitignore_path.read_text(encoding="utf-8")
            self.assertIn("config/manifest.toml", gitignore_text)
            self.assertIn(".claude/skills/cf/SKILL.md", gitignore_text)
            self.assertIn(".claude/skills/cypilot-generate/SKILL.md", gitignore_text)
            after = _snapshot_tree(root)
            added_paths = sorted(set(after) - set(before))
            removed_paths = sorted(set(before) - set(after))
            changed_paths = sorted(
                path for path in set(before) & set(after) if before[path] != after[path]
            )
            expected_added_paths = sorted(
                [
                    ".claude/skills",
                    ".claude/skills/cf",
                    ".claude/skills/cf/SKILL.md",
                    ".claude/skills/cf-analyze",
                    ".claude/skills/cf-analyze/SKILL.md",
                    ".claude/skills/cf-explore",
                    ".claude/skills/cf-explore/SKILL.md",
                    ".claude/skills/cf-generate",
                    ".claude/skills/cf-generate/SKILL.md",
                    ".claude/skills/cf-plan",
                    ".claude/skills/cf-plan/SKILL.md",
                    ".claude/skills/cf-workspace",
                    ".claude/skills/cf-workspace/SKILL.md",
                    ".claude/skills/cypilot-analyze",
                    ".claude/skills/cypilot-analyze/SKILL.md",
                    ".claude/skills/cypilot-generate",
                    ".claude/skills/cypilot-generate/SKILL.md",
                    ".gitignore",
                    "config/manifest.toml",
                ]
            )
            self.assertEqual(removed_paths, [])
            self.assertEqual(added_paths, expected_added_paths)
            self.assertEqual(changed_paths, [])
            self.assertFalse((root / ".agents").exists())
            self.assertFalse((root / ".codex").exists())

    def test_generate_agents_openai_dry_run_via_main(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_generator_project(root)

            rc, stdout, _stderr = _run_main(
                [
                    "--json",
                    "generate-agents",
                    "--openai",
                    "--root",
                    str(root),
                    "--cf-constructor-root",
                    str(root),
                    "--dry-run",
                ],
                cwd=root,
            )

            self.assertEqual(rc, 0)
            out = json.loads(stdout)
            self.assertEqual(out["status"], "PASS")
            self.assertTrue(out["dry_run"])
            self.assertEqual(out["agents"], ["openai"])
            self.assertIn("openai", out["results"])
            self.assertFalse((root / ".codex").exists())
            self.assertFalse((root / ".agents").exists())

    def test_generate_agents_yes_remove_cypilot_cleans_legacy_outputs(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_generator_project(root)
            _bootstrap_legacy_cypilot_outputs(root)
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(
                [
                    "generate-agents",
                    "--agent",
                    "claude",
                    "--root",
                    str(root),
                    "--cf-constructor-root",
                    str(root),
                    "--remove-cypilot",
                    "yes",
                    "--yes",
                ],
                cwd=root,
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            claude = out["results"]["claude"]
            deleted = set(claude.get("skills", {}).get("deleted", [])) | set(
                claude.get("subagents", {}).get("deleted", [])
            )
            self.assertIn(".claude/skills/cypilot/SKILL.md", deleted)
            self.assertIn(".claude/agents/cypilot-reviewer.md", deleted)

            self.assertFalse((root / ".claude" / "skills" / "cypilot" / "SKILL.md").exists())
            self.assertFalse((root / ".claude" / "agents" / "cypilot-reviewer.md").exists())

            after = _snapshot_tree(root)
            self.assertNotEqual(after, before)
            self.assertTrue((root / ".claude" / "skills" / "cf-analyze" / "SKILL.md").exists())
            self.assertTrue((root / ".claude" / "skills" / "cf-plan" / "SKILL.md").exists())

    def test_agents_openai_flag_stays_read_only(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_generator_project(root)

            rc, stdout, _stderr = _run_main(
                [
                    "--json",
                    "agents",
                    "--openai",
                    "--root",
                    str(root),
                    "--cf-constructor-root",
                    str(root),
                ],
                cwd=root,
            )

            self.assertEqual(rc, 0)
            out = json.loads(stdout)
            self.assertEqual(out["status"], "OK")
            self.assertEqual(out["agents"], ["openai"])
            self.assertIn("openai", out["results"])
            self.assertFalse((root / ".codex").exists())
            self.assertFalse((root / ".agents").exists())


class TestValidateKitsAndInitE2E(unittest.TestCase):
    def test_validate_kits_kit_filter_validates_only_selected_registered_kit(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_adapter_project(root)
            _write_toml(
                adapter / "config" / "core.toml",
                {
                    "version": "1.0",
                    "project_root": "..",
                    "kits": {
                        "alpha": {"format": "CFS", "path": "config/kits/alpha"},
                        "beta": {"format": "CFS", "path": "config/kits/beta"},
                    },
                },
            )
            _write_toml(
                adapter / "config" / "artifacts.toml",
                {
                    "version": "1.0",
                    "project_root": "..",
                    "kits": {
                        "alpha": {"format": "CFS", "path": "config/kits/alpha"},
                        "beta": {"format": "CFS", "path": "config/kits/beta"},
                    },
                    "systems": [],
                },
            )
            for slug in ("alpha", "beta"):
                kit_root = adapter / "config" / "kits" / slug
                kit_root.mkdir(parents=True, exist_ok=True)
                toml_utils.dump({"artifacts": {"REQ": {"identifiers": {"req": {"required": True}}}}}, kit_root / "constraints.toml")
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(["validate-kits", "--kit", "beta"], cwd=root)

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["kits_validated"], 1)
            self.assertEqual(out["error_count"], 0)
            self.assertEqual(_snapshot_tree(root), before)

    def test_init_project_name_writes_custom_registry_name(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "my-proj"
            root.mkdir(parents=True, exist_ok=True)
            (root / ".git").mkdir()
            cache_dir = _make_test_cache(Path(td) / "cache")

            with (
                patch("studio.commands.init.CACHE_DIR", cache_dir),
                patch("studio.commands.init._install_default_kit", return_value={}),
            ):
                rc, out, stderr = _run_main_json(
                    ["init", "--yes", "--project-root", str(root), "--project-name", "Custom Name"],
                    cwd=root,
                )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["root_system"], {"name": "MyProj", "slug": "my-proj"})
            registry = toml_utils.load(root / ".cf-studio" / "config" / "artifacts.toml")
            self.assertEqual(registry["systems"][0]["name"], "Custom Name")
            self.assertEqual(registry["systems"][0]["slug"], "custom-name")

    def test_init_from_dir_migrates_explicit_legacy_directory(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_legacy_project(root, legacy_dir=".bootstrap")

            with patch("studio.commands.migrate_from_cypilot._run_followup_update", return_value=(0, {"status": "PASS"})):
                rc, out, stderr = _run_main_json(
                    [
                        "init",
                        "--yes",
                        "--project-root",
                        str(root),
                        "--from-dir",
                        ".bootstrap",
                        "--migrate-from-cypilot",
                        "yes",
                    ],
                    cwd=root,
                )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["from_dir"], ".bootstrap")
            self.assertEqual(out["actions"]["update"], "PASS")
            self.assertTrue((root / ".cf-studio" / "config" / "core.toml").is_file())
            self.assertIn('cf-studio-path = ".cf-studio"', (root / "AGENTS.md").read_text(encoding="utf-8"))

    def test_init_force_replaces_runtime_and_creates_backup(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir(parents=True, exist_ok=True)
            (root / ".git").mkdir()
            cache_dir = _make_test_cache(Path(td) / "cache")

            with (
                patch("studio.commands.init.CACHE_DIR", cache_dir),
                patch("studio.commands.init._install_default_kit", return_value={}),
            ):
                first_rc, _first_out, first_stderr = _run_main_json(
                    ["init", "--yes", "--project-root", str(root), "--install-dir", ".bootstrap"],
                    cwd=root,
                )
                self.assertEqual(first_rc, 0, first_stderr)

                stale = root / ".bootstrap" / ".core" / "stale.txt"
                stale.write_text("remove me\n", encoding="utf-8")

                rc, out, stderr = _run_main_json(
                    ["init", "--yes", "--force", "--project-root", str(root), "--install-dir", ".bootstrap"],
                    cwd=root,
                )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(stderr, "")
            self.assertEqual(out["status"], "PASS")
            self.assertIn("backups", out)
            self.assertTrue(out["backups"])
            self.assertFalse(stale.exists())
            backup_dir = Path(out["backups"][0])
            self.assertTrue((backup_dir / ".core" / "stale.txt").is_file())

    def test_init_migrate_yes_migrates_legacy_project_without_prompt(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_legacy_project(root, legacy_dir="cypilot", version="3.9.0")

            with patch("studio.commands.migrate_from_cypilot._run_followup_update", return_value=(0, {"status": "PASS"})):
                rc, out, stderr = _run_main_json(
                    [
                        "init",
                        "--yes",
                        "--project-root",
                        str(root),
                        "--migrate-from-cypilot",
                        "yes",
                    ],
                    cwd=root,
                )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["from_dir"], "cypilot")
            self.assertEqual(out["actions"]["update"], "PASS")
            self.assertTrue((root / ".cf-studio" / "config" / "core.toml").is_file())
            self.assertIn('cf-studio-path = ".cf-studio"', (root / "AGENTS.md").read_text(encoding="utf-8"))

    def test_init_update_legacy_studio_yes_updates_baseline_then_migrates(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_legacy_project(root, legacy_dir="cypilot", version="3.8.4")

            def _upgrade_legacy(project_root: Path):
                version_file = (
                    project_root
                    / "cypilot"
                    / ".core"
                    / "skills"
                    / "cypilot"
                    / "scripts"
                    / "cypilot"
                    / "__init__.py"
                )
                version_file.write_text('__version__ = "3.10.0"\n', encoding="utf-8")
                return {"status": "PASS", "returncode": 0}

            with (
                patch("studio.commands.migrate_from_cypilot._run_legacy_update_to_baseline", side_effect=_upgrade_legacy),
                patch("studio.commands.migrate_from_cypilot._run_followup_update", return_value=(0, {"status": "PASS"})),
            ):
                rc, out, stderr = _run_main_json(
                    [
                        "init",
                        "--yes",
                        "--project-root",
                        str(root),
                        "--migrate-from-cypilot",
                        "yes",
                        "--update-legacy-studio",
                        "yes",
                    ],
                    cwd=root,
                )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["normalized_legacy_version"], "3.10.0")
            self.assertEqual(out["actions"]["update"], "PASS")
            self.assertTrue((root / ".cf-studio" / "config" / "core.toml").is_file())


if __name__ == "__main__":
    unittest.main()
