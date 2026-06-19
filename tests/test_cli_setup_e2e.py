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
    from studio.utils import toml_utils

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
            self.assertFalse(gitignore_path.exists())
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


if __name__ == "__main__":
    unittest.main()
