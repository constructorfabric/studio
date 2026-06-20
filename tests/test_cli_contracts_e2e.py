"""Public JSON contract e2e coverage for selected CLI commands."""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tomllib
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.cli import main


FIXTURE_KITS_DIR = Path(__file__).resolve().parent / "fixtures" / "kits"


@contextmanager
def _chdir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _run_main_json(argv: list[str], *, cwd: Path) -> tuple[int, dict, str]:
    from studio.utils.ui import is_json_mode, set_json_mode

    stdout = io.StringIO()
    stderr = io.StringIO()
    saved_json_mode = is_json_mode()
    try:
        set_json_mode(False)
        with _chdir(cwd), redirect_stdout(stdout), redirect_stderr(stderr):
            rc = main(["--json", *argv])
    finally:
        set_json_mode(saved_json_mode)
    return rc, json.loads(stdout.getvalue()), stderr.getvalue()


def _make_cache(root: Path) -> Path:
    cache = root / "cache"
    for name in ("requirements", "schemas", "workflows", "skills"):
        (cache / name).mkdir(parents=True, exist_ok=True)
        (cache / name / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    (cache / "skills" / "studio").mkdir(parents=True, exist_ok=True)
    (cache / "skills" / "studio" / "SKILL.md").write_text(
        "---\nname: studio\ndescription: Test Studio skill\n---\n# Studio\n",
        encoding="utf-8",
    )
    for workflow_name in ("generate", "analyze", "plan", "explore", "workspace"):
        (cache / "workflows" / f"{workflow_name}.md").write_text(
            (
                "---\n"
                "type: workflow\n"
                f"name: {workflow_name}\n"
                f"description: Test {workflow_name} workflow\n"
                "---\n"
                f"# {workflow_name.title()}\n"
            ),
            encoding="utf-8",
        )
    for rel in (
        "architecture/specs/traceability.md",
        "architecture/specs/CDSL.md",
        "architecture/specs/PDSL.md",
        "architecture/specs/cli.md",
        "architecture/specs/CLISPEC.md",
        "architecture/specs/artifacts-registry.md",
        "architecture/specs/kit/constraints.md",
        "architecture/specs/kit/kit.md",
    ):
        target = cache / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {rel}\n", encoding="utf-8")
    (cache / "whatsnew.toml").write_text(
        '[whatsnew."v1.0.0"]\nsummary = "Initial"\ndetails = ""\n',
        encoding="utf-8",
    )
    (cache / "version.toml").write_text(
        '[cfs]\nversion = "v1.0.0"\n',
        encoding="utf-8",
    )
    return cache


def _init_project(root: Path, cache: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    with patch("studio.commands.init.CACHE_DIR", cache), patch(
        "studio.commands.init._install_default_kit",
        return_value={},
    ):
        rc, out, stderr = _run_main_json(
            [
                "init",
                "--project-root",
                str(root),
                "--install-dir",
                ".bootstrap",
                "--runtime-tracking",
                "ignored",
                "--agent-tracking",
                "ignored",
                "--kit-tracking",
                "ignored",
                "--yes",
            ],
            cwd=root,
        )
    assert rc == 0, stderr
    assert out["status"] == "PASS", out


def _copy_fixture(src_name: str, dst: Path) -> Path:
    shutil.copytree(FIXTURE_KITS_DIR / src_name, dst)
    return dst


def _make_manifest_kit_source(root: Path, slug: str = "manifestkit") -> Path:
    kit_src = root / slug
    (kit_src / "artifacts" / "FEATURE").mkdir(parents=True, exist_ok=True)
    (kit_src / "artifacts" / "FEATURE" / "template.md").write_text(
        "# Feature Spec\n",
        encoding="utf-8",
    )
    (kit_src / "SKILL.md").write_text(
        f"---\nname: skill\ndescription: Kit {slug}\n---\n# Kit {slug}\n",
        encoding="utf-8",
    )
    (kit_src / "AGENTS.md").write_text(
        f"---\nname: agents\ndescription: Agents {slug}\n---\n# Agents {slug}\n",
        encoding="utf-8",
    )
    (kit_src / "constraints.toml").write_text(
        f"[naming]\npattern = '{slug}-*'\n",
        encoding="utf-8",
    )
    (kit_src / "conf.toml").write_text(
        f'version = "1.0.0"\nslug = "{slug}"\n',
        encoding="utf-8",
    )
    (kit_src / "manifest.toml").write_text(
        "\n".join(
            [
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
            ],
        )
        + "\n",
        encoding="utf-8",
    )
    return kit_src


def _empty_workflows_section() -> dict:
    return {
        "created": [],
        "updated": [],
        "unchanged": [],
        "renamed": [],
        "deleted": [],
        "errors": [],
        "counts": {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "renamed": 0,
            "deleted": 0,
        },
    }


def _empty_output_section() -> dict:
    return {
        "created": [],
        "updated": [],
        "deleted": [],
        "skipped": [],
        "outputs": [],
        "counts": {
            "created": 0,
            "updated": 0,
            "deleted": 0,
            "skipped": 0,
        },
    }


class TestCliContractsE2E(unittest.TestCase):
    def test_generate_agents_partial_json_contract_includes_partial_reasons_shape(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-v2", temp_root / "local-kits" / "example-v2")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            partial_result = {
                "status": "PARTIAL",
                "agent": "openai",
                "workflows": _empty_workflows_section(),
                "skills": {
                    **_empty_output_section(),
                    "outputs": [
                        {
                            "path": ".agents/skills/cf-example-v2-review/SKILL.md",
                            "action": "preserved",
                            "reason": "user_modified",
                        },
                    ],
                },
                "subagents": {
                    "created": [],
                    "updated": [],
                    "deleted": [],
                    "skipped": ["reviewer-helper"],
                    "skip_reason": "provider_not_supported",
                    "outputs": [],
                    "counts": {"created": 0, "updated": 0, "deleted": 0},
                },
                "rules": {
                    "created": [],
                    "updated": [],
                    "deleted": [],
                    "skipped": True,
                    "skip_reason": "target_not_supported",
                    "outputs": [],
                    "counts": {"created": 0, "updated": 0, "deleted": 0},
                },
                "errors": ["failed to inspect .codex/agents/cf-example-v2-reviewer.toml"],
            }

            with patch("studio.commands.agents._process_single_agent", return_value=partial_result), patch(
                "studio.commands.agents._refresh_managed_gitignore",
                return_value="updated",
            ):
                rc, out, stderr = _run_main_json(
                    ["generate-agents", "--agent", "openai", "--root", str(project_root), "--yes"],
                    cwd=project_root,
                )

            self.assertEqual(rc, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(out["status"], "PARTIAL")
            self.assertEqual(out["agents"], ["openai"])
            self.assertEqual(out["gitignore"], "updated")
            self.assertFalse(out["dry_run"])
            self.assertIn("results", out)
            self.assertEqual(sorted(out["results"].keys()), ["openai"])
            self.assertEqual(out["results"]["openai"]["status"], "PARTIAL")

            partial_reasons = out["partial_reasons"]
            self.assertIsInstance(partial_reasons, list)
            self.assertEqual(len(partial_reasons), 1)
            partial_reason = partial_reasons[0]
            self.assertEqual(partial_reason["agent"], "openai")
            self.assertEqual(
                partial_reason["categories"],
                ["errors", "preserved_outputs", "skipped_components"],
            )
            self.assertEqual(
                partial_reason["errors"],
                ["failed to inspect .codex/agents/cf-example-v2-reviewer.toml"],
            )
            self.assertEqual(
                partial_reason["preserved_outputs"],
                [
                    {
                        "path": ".agents/skills/cf-example-v2-review/SKILL.md",
                        "reason": "user_modified",
                    },
                ],
            )
            self.assertEqual(
                partial_reason["skipped"],
                [
                    "subagents: provider_not_supported",
                    "rules: target_not_supported",
                ],
            )

    def test_kit_update_partial_json_contract_reports_top_level_partial_reasons(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-v2", temp_root / "local-kits" / "example-v2")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            installed_template = (
                project_root
                / ".bootstrap"
                / "config"
                / "kits"
                / "example-v2"
                / "artifacts"
                / "PRD"
                / "template.md"
            )
            installed_template.write_text("USER MODIFIED TEMPLATE\n", encoding="utf-8")
            (local_kit / "artifacts" / "PRD" / "template.md").write_text(
                "@cpt-template:cpt-example-v2-prd-template:p1\n# Upstream changed template\n",
                encoding="utf-8",
            )

            rc, out, stderr = _run_main_json(
                ["kit", "update", "--path", str(local_kit), "--force", "--no-interactive", "-y"],
                cwd=project_root,
            )

            self.assertEqual(rc, 2)
            self.assertEqual(out["status"], "WARN")
            self.assertEqual(out["kits_updated"], 0)
            self.assertEqual(out["kits_partially_updated"], 1)
            self.assertEqual(out["results"][0]["kit"], "example-v2")
            self.assertEqual(out["results"][0]["action"], "partial")
            self.assertEqual(out["results"][0]["declined"], ["artifacts/PRD/template.md"])

            partial_reasons = out["partial_reasons"]
            self.assertEqual(
                partial_reasons,
                [
                    {
                        "kit": "example-v2",
                        "declined": ["artifacts/PRD/template.md"],
                        "categories": ["declined_files", "partial_update"],
                    },
                ],
            )

    def test_kit_check_updates_fail_contract_uses_nonzero_exit_for_mixed_degraded_results(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)

            kits_map = {"alpha": {}, "beta": {}, "gamma": {}}
            mixed_results = [
                {
                    "kit": "alpha",
                    "action": "current",
                    "installed_ref": "v1.0.0",
                    "latest_ref": "v1.0.0",
                },
                {
                    "kit": "beta",
                    "action": "update_available",
                    "installed_ref": "v1.0.0",
                    "latest_ref": "v1.1.0",
                    "command": "cfs kit update beta",
                },
                {
                    "kit": "gamma",
                    "action": "failed",
                    "message": "remote unavailable",
                },
            ]

            with patch("studio.commands.kit._read_kits_from_core_toml", return_value=kits_map), patch(
                "studio.commands.kit._check_registered_kit_updates",
                return_value=(mixed_results, []),
            ):
                rc, out, stderr = _run_main_json(
                    ["kit", "check-updates", "--project-root", str(project_root)],
                    cwd=project_root,
                )

            self.assertEqual(rc, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(out["status"], "FAIL")
            self.assertEqual(out["updates_available"], 1)
            self.assertEqual(out["message"], "Kit updates available")
            self.assertEqual(out["commands"], ["cfs kit update beta"])
            self.assertEqual(out["errors"], ["gamma: remote unavailable"])

            results = {result["kit"]: result for result in out["results"]}
            self.assertEqual(results["alpha"]["action"], "current")
            self.assertEqual(results["beta"]["action"], "update_available")
            self.assertEqual(results["beta"]["command"], "cfs kit update beta")
            self.assertEqual(results["gamma"]["action"], "failed")
            self.assertEqual(results["gamma"]["message"], "remote unavailable")

    def test_kit_normalize_dry_run_json_contract_includes_manifest_without_writing(self):
        with TemporaryDirectory() as td:
            kit_src = _make_manifest_kit_source(Path(td), "manifestkit")

            rc, out, stderr = _run_main_json(
                ["kit", "normalize", str(kit_src), "--dry-run"],
                cwd=Path(td),
            )

            self.assertEqual(rc, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["action"], "normalized")
            self.assertTrue(out["dry_run"])
            self.assertEqual(out["kit"], "manifestkit")
            self.assertEqual(out["kits"], ["manifestkit"])
            self.assertEqual(out["kits_normalized"], 1)
            self.assertEqual(out["output"], str((kit_src / ".cf-studio-kit.toml").resolve()))
            self.assertEqual(out["report"]["manifest_source"], "legacy_manifest")
            self.assertIn("manifest", out)
            manifest_data = tomllib.loads(out["manifest"])
            self.assertEqual(manifest_data["manifest_version"], "1.0")
            self.assertEqual(manifest_data["kits"][0]["slug"], "manifestkit")
            self.assertFalse((kit_src / ".cf-studio-kit.toml").exists())

    def test_kit_normalize_write_json_contract_omits_manifest_and_writes_same_output(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            kit_src = _make_manifest_kit_source(root, "manifestkit")

            dry_rc, dry_out, dry_stderr = _run_main_json(
                ["kit", "normalize", str(kit_src), "--dry-run"],
                cwd=root,
            )
            self.assertEqual(dry_rc, 0)
            self.assertEqual(dry_stderr, "")

            rc, out, stderr = _run_main_json(
                ["kit", "normalize", str(kit_src)],
                cwd=root,
            )

            self.assertEqual(rc, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["action"], "normalized")
            self.assertFalse(out["dry_run"])
            self.assertEqual(out["kit"], "manifestkit")
            self.assertEqual(out["kits"], ["manifestkit"])
            self.assertEqual(out["kits_normalized"], 1)
            self.assertEqual(out["output"], str((kit_src / ".cf-studio-kit.toml").resolve()))
            self.assertEqual(out["report"], dry_out["report"])
            self.assertNotIn("manifest", out)

            written_manifest = (kit_src / ".cf-studio-kit.toml").read_text(encoding="utf-8")
            self.assertEqual(written_manifest, dry_out["manifest"])
            written_data = tomllib.loads(written_manifest)
            self.assertEqual(written_data["manifest_version"], "1.0")
            self.assertEqual(written_data["kits"][0]["slug"], "manifestkit")


if __name__ == "__main__":
    unittest.main()
