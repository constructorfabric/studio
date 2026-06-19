"""E2E coverage for technical kit fixtures under ``tests/fixtures/kits``."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tomllib
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import quote

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
    stdout = io.StringIO()
    stderr = io.StringIO()
    with _chdir(cwd), redirect_stdout(stdout), redirect_stderr(stderr):
        rc = main(["--json", *argv])
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


def _init_project(
    root: Path,
    cache: Path,
    *,
    runtime_tracking: str = "ignored",
    agent_tracking: str = "ignored",
    kit_tracking: str = "ignored",
) -> None:
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
                runtime_tracking,
                "--agent-tracking",
                agent_tracking,
                "--kit-tracking",
                kit_tracking,
                "--yes",
            ],
            cwd=root,
        )
    assert rc == 0, stderr
    assert out["status"] == "PASS", out


def _copy_fixture(src_name: str, dst: Path) -> Path:
    src = FIXTURE_KITS_DIR / src_name
    shutil.copytree(src, dst)
    return dst


def _read_core(project_root: Path) -> dict:
    with (project_root / ".bootstrap" / "config" / "core.toml").open("rb") as fh:
        return tomllib.load(fh)


def _run_git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout)
    return proc.stdout.strip()


def _make_git_repo_from_fixture(root: Path, fixture_name: str) -> tuple[Path, str]:
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "repo"
    _copy_fixture(fixture_name, repo)
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test User")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-q", "-m", "initial")
    return repo, _run_git(repo, "rev-parse", "HEAD")


def _make_subdir_git_repo_from_fixture(root: Path, fixture_name: str, *, subdir: str) -> tuple[Path, str]:
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "repo"
    kit_dir = repo / subdir
    kit_dir.parent.mkdir(parents=True, exist_ok=True)
    _copy_fixture(fixture_name, kit_dir)
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test User")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-q", "-m", "initial")
    return repo, _run_git(repo, "rev-parse", "HEAD")


def _make_multi_canonical_git_repo(root: Path) -> tuple[Path, str]:
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "alpha.md").write_text("# Alpha v1\n", encoding="utf-8")
    (repo / "beta.md").write_text("# Beta v1\n", encoding="utf-8")
    (repo / ".cf-studio-kit.toml").write_text(
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
            "",
            "[[kits]]",
            'slug = "beta"',
            'name = "Beta"',
            'version = "1.0.0"',
            "",
            "[[kits.resources]]",
            'id = "skill"',
            'kind = "skill"',
            'source = "beta.md"',
            'install_path = "SKILL.md"',
            'type = "file"',
        ]) + "\n",
        encoding="utf-8",
    )
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test User")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-q", "-m", "initial")
    return repo, _run_git(repo, "rev-parse", "HEAD")


def _make_simple_canonical_kit(root: Path, slug: str = "canon-interactive") -> Path:
    kit_src = root / slug
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


def _make_multi_canonical_local_kit(root: Path, slug: str = "multi-local") -> Path:
    kit_src = root / slug
    kit_src.mkdir(parents=True, exist_ok=True)
    (kit_src / "alpha.md").write_text("# Alpha v1\n", encoding="utf-8")
    (kit_src / "beta.md").write_text("# Beta v1\n", encoding="utf-8")
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
            "",
            "[[kits]]",
            'slug = "beta"',
            'name = "Beta"',
            'version = "1.0.0"',
            "",
            "[[kits.resources]]",
            'id = "skill"',
            'kind = "skill"',
            'source = "beta.md"',
            'install_path = "SKILL.md"',
            'type = "file"',
        ]) + "\n",
        encoding="utf-8",
    )
    return kit_src


def _make_two_file_canonical_kit(root: Path, slug: str = "multi-update") -> Path:
    kit_src = root / slug
    kit_src.mkdir(parents=True, exist_ok=True)
    (kit_src / "SKILL.md").write_text("# Skill v1\n", encoding="utf-8")
    (kit_src / "guide.md").write_text("# Guide v1\n", encoding="utf-8")
    (kit_src / ".cf-studio-kit.toml").write_text(
        "\n".join([
            'manifest_version = "1.0"',
            "",
            "[[kits]]",
            f'slug = "{slug}"',
            f'name = "{slug}"',
            'version = "1.0.0"',
            "",
            "[[kits.resources]]",
            'id = "skill"',
            'kind = "skill"',
            'source = "SKILL.md"',
            'install_path = "SKILL.md"',
            'type = "file"',
            "public = true",
            "",
            "[[kits.resources]]",
            'id = "guide"',
            'kind = "other"',
            'source = "guide.md"',
            'install_path = "guide.md"',
            'type = "file"',
        ]) + "\n",
        encoding="utf-8",
    )
    return kit_src


def _make_prune_canonical_kit(root: Path, slug: str = "prune-local") -> Path:
    kit_src = root / slug
    kit_src.mkdir(parents=True, exist_ok=True)
    (kit_src / "keep.md").write_text("# Keep\n", encoding="utf-8")
    (kit_src / "remove.md").write_text("# Remove\n", encoding="utf-8")
    (kit_src / ".cf-studio-kit.toml").write_text(
        "\n".join([
            'manifest_version = "1.0"',
            "",
            "[[kits]]",
            f'slug = "{slug}"',
            f'name = "{slug}"',
            'version = "1.0.0"',
            "",
            "[[kits.resources]]",
            'id = "keep"',
            'kind = "other"',
            'source = "keep.md"',
            'install_path = "keep.md"',
            'type = "file"',
            "",
            "[[kits.resources]]",
            'id = "remove"',
            'kind = "other"',
            'source = "remove.md"',
            'install_path = "remove.md"',
            'type = "file"',
        ]) + "\n",
        encoding="utf-8",
    )
    return kit_src


def _make_public_skill_kit(
    root: Path,
    *,
    slug: str,
    generated_name: str,
    prefix_generated_name: bool = False,
) -> Path:
    kit_src = root / slug
    kit_src.mkdir(parents=True, exist_ok=True)
    (kit_src / "SKILL.md").write_text(
        f"---\nname: {slug}\ndescription: {slug} skill\n---\n# {slug}\n",
        encoding="utf-8",
    )
    lines = [
        'manifest_version = "1.0"',
        "",
        "[[kits]]",
        f'slug = "{slug}"',
        f'name = "{slug}"',
        'version = "1.0.0"',
        "",
        "[[kits.resources]]",
        'id = "skill"',
        'kind = "skill"',
        'source = "SKILL.md"',
        'install_path = "SKILL.md"',
        'type = "file"',
        "public = true",
        f'generated_name = "{generated_name}"',
    ]
    if not prefix_generated_name:
        lines.append("prefix_generated_name = false")
    (kit_src / ".cf-studio-kit.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return kit_src


def _make_duplicate_public_component_kit(root: Path, slug: str = "conflict-kit") -> Path:
    kit_src = root / slug
    kit_src.mkdir(parents=True, exist_ok=True)
    (kit_src / "first.md").write_text("---\nname: first\ndescription: First\n---\n# First\n", encoding="utf-8")
    (kit_src / "second.md").write_text("---\nname: second\ndescription: Second\n---\n# Second\n", encoding="utf-8")
    (kit_src / ".cf-studio-kit.toml").write_text(
        "\n".join([
            'manifest_version = "1.0"',
            "",
            "[[kits]]",
            f'slug = "{slug}"',
            f'name = "{slug}"',
            'version = "1.0.0"',
            "",
            "[[kits.resources]]",
            'id = "first"',
            'kind = "skill"',
            'source = "first.md"',
            'install_path = "first.md"',
            'type = "file"',
            "public = true",
            'generated_name = "shared-public-skill"',
            "prefix_generated_name = false",
            "",
            "[[kits.resources]]",
            'id = "second"',
            'kind = "skill"',
            'source = "second.md"',
            'install_path = "second.md"',
            'type = "file"',
            "public = true",
            'generated_name = "shared-public-skill"',
            "prefix_generated_name = false",
        ]) + "\n",
        encoding="utf-8",
    )
    return kit_src


def _run_main_json_with_stdin(argv: list[str], *, cwd: Path, stdin_text: str) -> tuple[int, dict, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin = io.StringIO(stdin_text)
    with _chdir(cwd), redirect_stdout(stdout), redirect_stderr(stderr), patch("sys.stdin", stdin), patch(
        "sys.stdin.isatty",
        return_value=True,
    ):
        rc = main(["--json", *argv])
    return rc, json.loads(stdout.getvalue()), stderr.getvalue()


class TestCliExampleKitsE2E(unittest.TestCase):
    def _assert_shared_provider_outputs(self, project_root: Path, gitignore_text: str) -> None:
        claude_skill = project_root / ".claude" / "skills" / "cf" / "SKILL.md"
        cursor_command = project_root / ".cursor" / "commands" / "cf.md"
        copilot_prompt = project_root / ".github" / "prompts" / "cf.prompt.md"
        windsurf_workflow = project_root / ".windsurf" / "workflows" / "cf.md"

        self.assertIn(".claude/skills/cf/SKILL.md", gitignore_text)
        self.assertIn(".cursor/commands/cf.md", gitignore_text)
        self.assertIn(".github/prompts/cf.prompt.md", gitignore_text)
        self.assertIn(".windsurf/workflows/cf.md", gitignore_text)

        self.assertTrue(claude_skill.is_file())
        self.assertTrue(cursor_command.is_file())
        self.assertTrue(copilot_prompt.is_file())
        self.assertTrue(windsurf_workflow.is_file())

        self.assertIn('name: cf', claude_skill.read_text(encoding="utf-8"))
        self.assertIn("# /cf", cursor_command.read_text(encoding="utf-8"))
        self.assertIn('name: studio', copilot_prompt.read_text(encoding="utf-8"))
        self.assertIn("# /cf", windsurf_workflow.read_text(encoding="utf-8"))

    def _assert_legacy_provider_agent_outputs(
        self,
        project_root: Path,
        gitignore_text: str,
        *,
        prompt_source: str,
    ) -> None:
        claude_agent = project_root / ".claude" / "agents" / "example-legacy-reviewer.md"
        cursor_agent = project_root / ".cursor" / "agents" / "example-legacy-reviewer.md"
        copilot_agent = project_root / ".github" / "agents" / "example-legacy-reviewer.agent.md"
        openai_agent = project_root / ".codex" / "agents" / "example-legacy-reviewer.toml"

        self.assertIn(".claude/agents/example-legacy-reviewer.md", gitignore_text)
        self.assertIn(".cursor/agents/example-legacy-reviewer.md", gitignore_text)
        self.assertIn(".github/agents/example-legacy-reviewer.agent.md", gitignore_text)
        self.assertIn(".codex/agents/example-legacy-reviewer.toml", gitignore_text)

        self.assertTrue(claude_agent.is_file())
        self.assertTrue(cursor_agent.is_file())
        self.assertTrue(copilot_agent.is_file())
        self.assertTrue(openai_agent.is_file())

        self.assertIn("Example legacy reviewer", claude_agent.read_text(encoding="utf-8"))
        self.assertIn(prompt_source, claude_agent.read_text(encoding="utf-8"))
        self.assertIn("Example legacy reviewer", cursor_agent.read_text(encoding="utf-8"))
        self.assertIn("readonly: true", cursor_agent.read_text(encoding="utf-8"))
        self.assertIn("Example legacy reviewer", copilot_agent.read_text(encoding="utf-8"))
        self.assertIn(prompt_source, copilot_agent.read_text(encoding="utf-8"))
        self.assertIn('name = "example-legacy-reviewer"', openai_agent.read_text(encoding="utf-8"))
        self.assertIn(prompt_source, openai_agent.read_text(encoding="utf-8"))

    def _assert_no_non_openai_public_agent_outputs(self, project_root: Path, slug: str, gitignore_text: str) -> None:
        for rel in (
            f".claude/agents/cf-{slug}-reviewer.md",
            f".claude/agents/cf-{slug}-reviewer-helper.md",
            f".cursor/agents/cf-{slug}-reviewer.mdc",
            f".cursor/agents/cf-{slug}-reviewer-helper.mdc",
            f".github/agents/cf-{slug}-reviewer.agent.md",
            f".github/agents/cf-{slug}-reviewer-helper.agent.md",
        ):
            self.assertNotIn(rel, gitignore_text)
            self.assertFalse((project_root / rel).exists())

    def test_example_legacy_kit_normalize_dry_run_reports_canonical_manifest_without_writing(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            legacy = _copy_fixture("example-legacy", root / "example-legacy")

            rc, out, stderr = _run_main_json(
                ["kit", "normalize", str(legacy), "--dry-run"],
                cwd=root,
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["action"], "normalized")
            self.assertTrue(out["dry_run"])
            self.assertEqual(out["kit"], "example-legacy")
            self.assertEqual(out["kits_normalized"], 1)
            self.assertEqual(out["report"]["manifest_source"], "legacy_manifest")
            self.assertEqual(out["report"]["resources"], 3)
            self.assertIn("feature_template", out["manifest"])
            self.assertIn('manifest_version = "1.0"', out["manifest"])
            self.assertFalse((legacy / ".cf-studio-kit.toml").exists())

    def test_example_mixed_kit_normalize_stdout_emits_manifest_only_and_writes_nothing(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            mixed = _copy_fixture("example-mixed", root / "example-mixed")
            before_snapshot = {
                path.relative_to(mixed).as_posix(): path.read_bytes()
                for path in sorted(mixed.rglob("*"))
                if path.is_file()
            }

            stdout = io.StringIO()
            stderr = io.StringIO()
            with _chdir(root), redirect_stdout(stdout), redirect_stderr(stderr):
                rc = main(["kit", "normalize", str(mixed), "--stdout"])

            self.assertEqual(rc, 0, stderr.getvalue())
            manifest_text = stdout.getvalue()
            self.assertEqual(stderr.getvalue(), "")
            self.assertIn('manifest_version = "1.0"', manifest_text)
            self.assertIn('slug = "example-mixed"', manifest_text)
            self.assertIn('id = "reviewer"', manifest_text)
            self.assertIn('generated_targets = ["openai"]', manifest_text)
            self.assertEqual(
                {
                    path.relative_to(mixed).as_posix(): path.read_bytes()
                    for path in sorted(mixed.rglob("*"))
                    if path.is_file()
                },
                before_snapshot,
            )

    def test_example_mixed_validate_kits_fails_for_invalid_constraints_toml(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-mixed", project_root / "local-kits" / "example-mixed")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            constraints_path = project_root / ".bootstrap" / "config" / "kits" / "example-mixed" / "constraints.toml"
            constraints_path.write_text("not toml = [", encoding="utf-8")

            rc, out, stderr = _run_main_json(["validate-kits"], cwd=project_root)

            self.assertEqual(rc, 2, stderr)
            self.assertEqual(out["status"], "FAIL")
            self.assertEqual(out["kits_validated"], 1)
            self.assertEqual(out["error_count"], 1)
            self.assertEqual(out["failed_kits"][0]["kit"], "example-mixed")
            self.assertEqual(out["errors"][0]["type"], "constraints")
            self.assertIn("Invalid constraints", out["errors"][0]["message"])
            self.assertIn("Failed to parse constraints.toml", out["errors"][0]["errors"][0])
            self.assertEqual(constraints_path.read_text(encoding="utf-8"), "not toml = [")

    def test_example_mixed_validate_kits_fails_for_missing_bound_resource_path(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-mixed", project_root / "local-kits" / "example-mixed")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            discovery_skill = (
                project_root / ".bootstrap" / "config" / "kits" / "example-mixed" / "skills" / "discovery" / "SKILL.md"
            )
            discovery_skill.unlink()

            rc, out, stderr = _run_main_json(["validate-kits"], cwd=project_root)

            self.assertEqual(rc, 2, stderr)
            self.assertEqual(out["status"], "FAIL")
            self.assertEqual(out["kits_validated"], 1)
            self.assertEqual(out["failed_kits"][0]["kit"], "example-mixed")
            self.assertEqual(out["errors"][0]["type"], "resources")
            self.assertIn("Resource 'discovery' path not found", out["errors"][0]["message"])
            self.assertFalse(discovery_skill.exists())

    def test_kit_normalize_multi_kit_dry_run_can_select_specific_kit_in_e2e(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            multi = _make_multi_canonical_local_kit(root)

            rc, out, stderr = _run_main_json(
                ["kit", "normalize", str(multi), "--dry-run", "--kit", "beta"],
                cwd=root,
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["kit"], "beta")
            self.assertEqual(out["kits"], ["beta"])
            self.assertEqual(out["kits_normalized"], 1)
            self.assertIn('slug = "beta"', out["manifest"])
            self.assertNotIn('slug = "alpha"', out["manifest"])
            self.assertFalse((multi / ".cf-studio-kit.toml").read_text(encoding="utf-8") == out["manifest"])

    def test_kit_normalize_multi_kit_subset_write_refusal_is_e2e_visible(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            multi = _make_multi_canonical_local_kit(root)
            before = (multi / ".cf-studio-kit.toml").read_text(encoding="utf-8")

            rc, out, stderr = _run_main_json(
                ["kit", "normalize", str(multi), "--kit", "alpha"],
                cwd=root,
            )

            self.assertEqual(rc, 2, stderr)
            self.assertEqual(out["status"], "FAIL")
            self.assertIn("Refusing to overwrite the source multi-kit manifest", out["message"])
            self.assertEqual((multi / ".cf-studio-kit.toml").read_text(encoding="utf-8"), before)

    def test_kit_normalize_multi_kit_writes_full_manifest_when_all_selected(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            multi = _make_multi_canonical_local_kit(root)
            manifest_path = multi / ".cf-studio-kit.toml"
            manifest_path.write_text(
                "# temporary comment to be normalized away\n" + manifest_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            rc, out, stderr = _run_main_json(
                ["kit", "normalize", str(multi), "--kit", "all"],
                cwd=root,
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["kits_normalized"], 2)
            manifest_text = manifest_path.read_text(encoding="utf-8")
            self.assertNotIn("temporary comment", manifest_text)
            self.assertIn('slug = "alpha"', manifest_text)
            self.assertIn('slug = "beta"', manifest_text)
            self.assertIn('source = "alpha.md"', manifest_text)
            self.assertIn('source = "beta.md"', manifest_text)

    def test_kit_normalize_multi_kit_unknown_selector_fails_cleanly(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            multi = _make_multi_canonical_local_kit(root)
            before = (multi / ".cf-studio-kit.toml").read_text(encoding="utf-8")

            rc, out, stderr = _run_main_json(
                ["kit", "normalize", str(multi), "--kit", "gamma"],
                cwd=root,
            )

            self.assertEqual(rc, 2, stderr)
            self.assertEqual(out["status"], "FAIL")
            self.assertIn("Unknown kit selection: gamma", out["message"])
            self.assertIn("alpha", out["message"])
            self.assertIn("beta", out["message"])
            self.assertEqual((multi / ".cf-studio-kit.toml").read_text(encoding="utf-8"), before)

    def test_kit_normalize_multi_kit_stdout_emits_selected_subset_without_writing(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            multi = _make_multi_canonical_local_kit(root)
            before = (multi / ".cf-studio-kit.toml").read_text(encoding="utf-8")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with _chdir(root), redirect_stdout(stdout), redirect_stderr(stderr):
                rc = main(["kit", "normalize", str(multi), "--stdout", "--kit", "beta"])

            self.assertEqual(rc, 0, stderr.getvalue())
            self.assertEqual(stderr.getvalue(), "")
            manifest_text = stdout.getvalue()
            self.assertIn('slug = "beta"', manifest_text)
            self.assertNotIn('slug = "alpha"', manifest_text)
            self.assertIn('generated_targets = ["installed"]', manifest_text)
            self.assertEqual((multi / ".cf-studio-kit.toml").read_text(encoding="utf-8"), before)

    def test_kit_update_interactive_prune_accepts_removed_resource(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _make_prune_canonical_kit(project_root / "local-kits", "prune-local")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            manifest_path = local_kit / ".cf-studio-kit.toml"
            manifest_path.write_text(
                manifest_path.read_text(encoding="utf-8").replace(
                    '\n[[kits.resources]]\nid = "remove"\nkind = "other"\nsource = "remove.md"\ninstall_path = "remove.md"\ntype = "file"\n',
                    "\n",
                ),
                encoding="utf-8",
            )
            (local_kit / "remove.md").unlink()

            installed_removed = project_root / ".bootstrap" / "config" / "kits" / "prune-local" / "remove.md"
            self.assertTrue(installed_removed.is_file())

            rc, out, stderr = _run_main_json_with_stdin(
                ["kit", "update", "--path", str(local_kit), "--force", "--prune"],
                cwd=project_root,
                stdin_text="a\n",
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            result = out["results"][0]
            self.assertEqual(result["action"], "updated")
            self.assertIn("remove.md", result["accepted"])
            self.assertIn("1 removed", stderr)
            self.assertIn("remove.md", stderr)
            self.assertIn("deleted upstream", stderr)
            self.assertIn("Reply with `a`, `d`, `A`, `D`, or `m`.", stderr)
            self.assertFalse(installed_removed.exists())

    def test_kit_update_interactive_multi_file_accept_all_updates_all_files(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _make_two_file_canonical_kit(project_root / "local-kits", "multi-update")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            (local_kit / "SKILL.md").write_text("# Skill v2\n", encoding="utf-8")
            (local_kit / "guide.md").write_text("# Guide v2\n", encoding="utf-8")

            rc, out, stderr = _run_main_json_with_stdin(
                ["kit", "update", "--path", str(local_kit), "--force"],
                cwd=project_root,
                stdin_text="A\n",
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            result = out["results"][0]
            self.assertEqual(result["action"], "updated")
            self.assertIn("SKILL.md", result["accepted"])
            self.assertIn("guide.md", result["accepted"])
            self.assertEqual(result["declined"], [])
            self.assertIn("Reply with `a`, `d`, `A`, `D`, or `m`.", stderr)
            self.assertEqual(
                (project_root / ".bootstrap" / "config" / "kits" / "multi-update" / "SKILL.md").read_text(encoding="utf-8"),
                "# Skill v2\n",
            )
            self.assertEqual(
                (project_root / ".bootstrap" / "config" / "kits" / "multi-update" / "guide.md").read_text(encoding="utf-8"),
                "# Guide v2\n",
            )

    def test_kit_update_interactive_decline_first_file_keeps_fs_and_accepts_second(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _make_two_file_canonical_kit(project_root / "local-kits", "mixed-decisions")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            (local_kit / "SKILL.md").write_text("# Skill v2\n", encoding="utf-8")
            (local_kit / "guide.md").write_text("# Guide v2\n", encoding="utf-8")

            rc, out, stderr = _run_main_json_with_stdin(
                ["kit", "update", "--path", str(local_kit), "--force"],
                cwd=project_root,
                stdin_text="d\na\n",
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            result = out["results"][0]
            self.assertEqual(result["action"], "partial")
            self.assertEqual(result["accepted"], ["guide.md"])
            self.assertEqual(result["declined"], ["SKILL.md"])
            self.assertEqual(
                (project_root / ".bootstrap" / "config" / "kits" / "mixed-decisions" / "SKILL.md").read_text(encoding="utf-8"),
                "# Skill v1\n",
            )
            self.assertEqual(
                (project_root / ".bootstrap" / "config" / "kits" / "mixed-decisions" / "guide.md").read_text(encoding="utf-8"),
                "# Guide v2\n",
            )

    def test_kit_update_interactive_modify_writes_editor_result_to_fs(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _make_simple_canonical_kit(project_root / "local-kits", "modify-local")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            (local_kit / "SKILL.md").write_text("# Skill upstream v2\n", encoding="utf-8")

            with patch("studio.utils.diff_engine._open_editor_for_file", return_value=b"# Skill merged\n"):
                rc, out, stderr = _run_main_json_with_stdin(
                    ["kit", "update", "--path", str(local_kit), "--force"],
                    cwd=project_root,
                    stdin_text="m\n",
                )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            result = out["results"][0]
            self.assertEqual(result["action"], "updated")
            self.assertEqual(result["accepted"], ["SKILL.md"])
            self.assertEqual(result["declined"], [])
            self.assertIn("Reply with `a`, `d`, `A`, `D`, or `m`.", stderr)
            self.assertEqual(
                (project_root / ".bootstrap" / "config" / "kits" / "modify-local" / "SKILL.md").read_text(encoding="utf-8"),
                "# Skill merged\n",
            )

    def test_kit_update_interactive_decline_all_keeps_all_files_unchanged(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _make_two_file_canonical_kit(project_root / "local-kits", "decline-all")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            (local_kit / "SKILL.md").write_text("# Skill v2\n", encoding="utf-8")
            (local_kit / "guide.md").write_text("# Guide v2\n", encoding="utf-8")

            rc, out, stderr = _run_main_json_with_stdin(
                ["kit", "update", "--path", str(local_kit), "--force"],
                cwd=project_root,
                stdin_text="D\n",
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            result = out["results"][0]
            self.assertEqual(result["action"], "partial")
            self.assertEqual(result["accepted"], [])
            self.assertEqual(result["declined"], ["SKILL.md", "guide.md"])
            self.assertEqual(
                (project_root / ".bootstrap" / "config" / "kits" / "decline-all" / "SKILL.md").read_text(encoding="utf-8"),
                "# Skill v1\n",
            )
            self.assertEqual(
                (project_root / ".bootstrap" / "config" / "kits" / "decline-all" / "guide.md").read_text(encoding="utf-8"),
                "# Guide v1\n",
            )

    def test_kit_update_interactive_accept_then_decline_all_preserves_remaining_files(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _make_two_file_canonical_kit(project_root / "local-kits", "accept-then-decline")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            (local_kit / "SKILL.md").write_text("# Skill v2\n", encoding="utf-8")
            (local_kit / "guide.md").write_text("# Guide v2\n", encoding="utf-8")

            rc, out, stderr = _run_main_json_with_stdin(
                ["kit", "update", "--path", str(local_kit), "--force"],
                cwd=project_root,
                stdin_text="a\nD\n",
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            result = out["results"][0]
            self.assertEqual(result["action"], "partial")
            self.assertEqual(result["accepted"], ["SKILL.md"])
            self.assertEqual(result["declined"], ["guide.md"])
            self.assertEqual(
                (project_root / ".bootstrap" / "config" / "kits" / "accept-then-decline" / "SKILL.md").read_text(encoding="utf-8"),
                "# Skill v2\n",
            )
            self.assertEqual(
                (project_root / ".bootstrap" / "config" / "kits" / "accept-then-decline" / "guide.md").read_text(encoding="utf-8"),
                "# Guide v1\n",
            )

    def test_kit_update_interactive_prune_decline_keeps_existing_file(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _make_prune_canonical_kit(project_root / "local-kits", "prune-decline")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            manifest_path = local_kit / ".cf-studio-kit.toml"
            manifest_path.write_text(
                manifest_path.read_text(encoding="utf-8").replace(
                    '\n[[kits.resources]]\nid = "remove"\nkind = "other"\nsource = "remove.md"\ninstall_path = "remove.md"\ntype = "file"\n',
                    "\n",
                ),
                encoding="utf-8",
            )
            (local_kit / "remove.md").unlink()

            installed_removed = project_root / ".bootstrap" / "config" / "kits" / "prune-decline" / "remove.md"
            self.assertTrue(installed_removed.is_file())

            rc, out, stderr = _run_main_json_with_stdin(
                ["kit", "update", "--path", str(local_kit), "--force", "--prune"],
                cwd=project_root,
                stdin_text="d\n",
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            result = out["results"][0]
            self.assertEqual(result["action"], "partial")
            self.assertEqual(result["accepted"], [])
            self.assertEqual(result["declined"], ["remove.md"])
            self.assertIn("deleted upstream", stderr)
            self.assertTrue(installed_removed.is_file())
            self.assertEqual(installed_removed.read_text(encoding="utf-8"), "# Remove\n")

    def test_kit_validate_public_command_runs_end_to_end_for_installed_example_kit(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-mixed", project_root / "local-kits" / "example-mixed")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            rc, out, stderr = _run_main_json(["kit", "validate"], cwd=project_root)

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["kits_validated"], 1)
            self.assertEqual(out["templates_checked"], 1)
            self.assertEqual(out["error_count"], 0)

    def test_kit_normalize_writes_canonical_manifest_for_legacy_fixture(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            legacy = _copy_fixture("example-legacy", root / "example-legacy")
            manifest_path = legacy / ".cf-studio-kit.toml"

            self.assertFalse(manifest_path.exists())
            before_manifest = (legacy / "manifest.toml").read_text(encoding="utf-8")
            before_conf = (legacy / "conf.toml").read_text(encoding="utf-8")

            rc, out, stderr = _run_main_json(
                ["kit", "normalize", str(legacy)],
                cwd=root,
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["action"], "normalized")
            self.assertEqual(out["kit"], "example-legacy")
            self.assertTrue(manifest_path.is_file())
            manifest_text = manifest_path.read_text(encoding="utf-8")
            self.assertIn('manifest_version = "1.0"', manifest_text)
            self.assertIn('slug = "example-legacy"', manifest_text)
            self.assertIn('id = "feature_template"', manifest_text)
            self.assertIn('id = "feature_example"', manifest_text)
            self.assertIn('id = "constraints"', manifest_text)
            self.assertNotIn('id = "reviewer"', manifest_text)
            self.assertEqual((legacy / "manifest.toml").read_text(encoding="utf-8"), before_manifest)
            self.assertEqual((legacy / "conf.toml").read_text(encoding="utf-8"), before_conf)

    def test_manifest_backed_update_refuses_when_source_manifest_loses_all_resources(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-mixed", project_root / "local-kits" / "example-mixed")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            installed_template = (
                project_root / ".bootstrap" / "config" / "kits" / "example-mixed" / "artifacts" / "ADR" / "template.md"
            )
            before_installed = installed_template.read_text(encoding="utf-8")
            (local_kit / ".cf-studio-kit.toml").write_text(
                "\n".join([
                    'manifest_version = "1.0"',
                    "",
                    "[[kits]]",
                    'slug = "example-mixed"',
                    'name = "Example Mixed"',
                    'version = "2.1.0"',
                ]) + "\n",
                encoding="utf-8",
            )

            rc, out, stderr = _run_main_json(
                ["kit", "update", "--path", str(local_kit), "--force", "--no-interactive", "-y"],
                cwd=project_root,
            )

            self.assertEqual(rc, 2, stderr)
            self.assertEqual(out["status"], "FAIL")
            result = out["results"][0]
            self.assertEqual(result["action"], "failed")
            self.assertIn("could not resolve resource bindings", result["errors"][0])
            self.assertIn("refusing to treat all files as deleted upstream", result["errors"][0])
            self.assertEqual(installed_template.read_text(encoding="utf-8"), before_installed)

    def test_example_v2_copy_install_and_generate_agents_asserts_fs_and_gitignore(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            kit_src = FIXTURE_KITS_DIR / "example-v2"
            _init_project(project_root, cache)

            rc, out, stderr = _run_main_json(
                [
                    "kit",
                    "install",
                    "--path",
                    str(kit_src),
                    "--install-mode",
                    "copy",
                ],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["install_mode"], "copy")

            installed_root = project_root / ".bootstrap" / "config" / "kits" / "example-v2"
            self.assertTrue((installed_root / "artifacts" / "PRD" / "template.md").is_file())
            self.assertTrue((installed_root / "artifacts" / "PRD" / "example.md").is_file())
            self.assertTrue((installed_root / "artifacts" / "FEATURE" / "template.md").is_file())
            self.assertTrue((installed_root / "artifacts" / "FEATURE" / "example.md").is_file())
            self.assertTrue((installed_root / "constraints.toml").is_file())
            self.assertTrue((installed_root / "skills" / "discovery" / "SKILL.md").is_file())
            self.assertTrue((installed_root / "skills" / "review" / "SKILL.md").is_file())
            self.assertTrue((installed_root / "agents" / "reviewer.md").is_file())
            self.assertTrue((installed_root / "agents" / "planner.md").is_file())
            self.assertFalse((installed_root / ".cf-studio-kit.toml").exists())
            self.assertEqual(
                (installed_root / "constraints.toml").read_text(encoding="utf-8"),
                "[PRD.identifiers.cpt]\nrequired = true\n\n[PRD.identifiers.fr]\nrequired = true\n\n[FEATURE.identifiers.cpt]\nrequired = true\n\n[FEATURE.identifiers.flow]\nrequired = true\n",
            )
            self.assertIn(
                "Example V2 PRD Template",
                (installed_root / "artifacts" / "PRD" / "template.md").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "@cpt-template:cpt-example-v2-prd-template:p1",
                (installed_root / "artifacts" / "PRD" / "template.md").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "cpt-example-v2-feature-flow",
                (installed_root / "artifacts" / "FEATURE" / "example.md").read_text(encoding="utf-8"),
            )

            core = _read_core(project_root)
            entry = core["kits"]["example-v2"]
            self.assertEqual(entry["install_mode"], "copy")
            self.assertEqual(entry["path"], "config/kits/example-v2")
            self.assertEqual(entry["resources"]["discovery"]["path"], "config/kits/example-v2/skills/discovery/SKILL.md")
            self.assertEqual(entry["resources"]["review"]["path"], "config/kits/example-v2/skills/review/SKILL.md")
            self.assertEqual(entry["resources"]["reviewer"]["mode"], "readonly")
            self.assertEqual(entry["resources"]["reviewer"]["subagents"][0]["id"], "reviewer-helper")
            self.assertEqual(entry["resources"]["planner"]["subagents"][0]["id"], "planner-helper")

            rc, out, stderr = _run_main_json(
                [
                    "generate-agents",
                    "--root",
                    str(project_root),
                    "--yes",
                ],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".bootstrap/.core/", gitignore_text)
            self.assertIn(".bootstrap/.gen/", gitignore_text)
            self.assertIn(".bootstrap/config/kits/example-v2/", gitignore_text)
            self.assertIn(".agents/skills/cf-example-v2-discovery/SKILL.md", gitignore_text)
            self.assertIn(".agents/skills/cf-example-v2-review/SKILL.md", gitignore_text)
            self.assertIn(".codex/agents/cf-example-v2-reviewer.toml", gitignore_text)
            self.assertIn(".codex/agents/cf-example-v2-reviewer-helper.toml", gitignore_text)
            self.assertIn(".codex/agents/cf-example-v2-planner.toml", gitignore_text)
            self.assertIn(".codex/agents/cf-example-v2-planner-helper.toml", gitignore_text)
            self.assertNotIn(".bootstrap/config/kits/\n", gitignore_text)
            self._assert_shared_provider_outputs(project_root, gitignore_text)
            self._assert_no_non_openai_public_agent_outputs(project_root, "example-v2", gitignore_text)

            generated_discovery = project_root / ".agents" / "skills" / "cf-example-v2-discovery" / "SKILL.md"
            generated_review = project_root / ".agents" / "skills" / "cf-example-v2-review" / "SKILL.md"
            self.assertTrue(generated_discovery.is_file())
            self.assertTrue(generated_review.is_file())
            self.assertIn(
                "{cf-studio-path}/config/kits/example-v2/skills/discovery/SKILL.md",
                generated_discovery.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "{cf-studio-path}/config/kits/example-v2/skills/review/SKILL.md",
                generated_review.read_text(encoding="utf-8"),
            )

            reviewer_agent = project_root / ".codex" / "agents" / "cf-example-v2-reviewer.toml"
            reviewer_helper = project_root / ".codex" / "agents" / "cf-example-v2-reviewer-helper.toml"
            planner_agent = project_root / ".codex" / "agents" / "cf-example-v2-planner.toml"
            planner_helper = project_root / ".codex" / "agents" / "cf-example-v2-planner-helper.toml"
            self.assertTrue(reviewer_agent.is_file())
            self.assertTrue(reviewer_helper.is_file())
            self.assertTrue(planner_agent.is_file())
            self.assertTrue(planner_helper.is_file())
            self.assertIn('name = "cf-example-v2-reviewer"', reviewer_agent.read_text(encoding="utf-8"))
            self.assertIn('sandbox_mode = "read-only"', reviewer_agent.read_text(encoding="utf-8"))
            self.assertIn("# Example V2 Reviewer", reviewer_agent.read_text(encoding="utf-8"))
            self.assertIn("edge cases for the reviewer", reviewer_helper.read_text(encoding="utf-8"))
            self.assertIn("# Example V2 Planner", planner_agent.read_text(encoding="utf-8"))
            self.assertIn("missing context for the planner", planner_helper.read_text(encoding="utf-8"))

    def test_example_v2_register_install_keeps_source_in_place_and_generates_from_registered_paths(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-v2", project_root / "local-kits" / "example-v2")

            rc, out, stderr = _run_main_json(
                [
                    "kit",
                    "install",
                    "--path",
                    str(local_kit),
                    "--install-mode",
                    "register",
                ],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["install_mode"], "register")
            self.assertEqual(out["files_written"], 0)
            self.assertEqual(out["files_registered"], 9)

            core = _read_core(project_root)
            entry = core["kits"]["example-v2"]
            self.assertEqual(entry["install_mode"], "register")
            self.assertEqual(entry["path"], "../local-kits/example-v2")
            self.assertNotIn("resources", entry)
            self.assertEqual(entry["source_provenance"]["source_type"], "local_path")
            self.assertEqual(entry["source_provenance"]["resolver_mode"], "register")
            self.assertEqual(
                entry["source_provenance"]["effective_source"],
                "../local-kits/example-v2",
            )
            self.assertFalse((project_root / ".bootstrap" / "config" / "kits" / "example-v2").exists())

            rc, out, stderr = _run_main_json(
                [
                    "generate-agents",
                    "--root",
                    str(project_root),
                    "--yes",
                ],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("local-kits/example-v2/", gitignore_text)
            self.assertIn(".agents/skills/cf-example-v2-discovery/SKILL.md", gitignore_text)
            self.assertIn(".agents/skills/cf-example-v2-review/SKILL.md", gitignore_text)
            self.assertIn(".codex/agents/cf-example-v2-reviewer.toml", gitignore_text)
            self.assertIn(".codex/agents/cf-example-v2-reviewer-helper.toml", gitignore_text)
            self.assertIn(".codex/agents/cf-example-v2-planner.toml", gitignore_text)
            self.assertIn(".codex/agents/cf-example-v2-planner-helper.toml", gitignore_text)
            self.assertNotIn(".bootstrap/../local-kits/example-v2/", gitignore_text)
            self.assertNotIn(".bootstrap/config/kits/example-v2/", gitignore_text)
            self._assert_shared_provider_outputs(project_root, gitignore_text)
            self._assert_no_non_openai_public_agent_outputs(project_root, "example-v2", gitignore_text)

            generated_discovery = project_root / ".agents" / "skills" / "cf-example-v2-discovery" / "SKILL.md"
            generated_review = project_root / ".agents" / "skills" / "cf-example-v2-review" / "SKILL.md"
            self.assertTrue(generated_discovery.is_file())
            self.assertTrue(generated_review.is_file())
            self.assertIn(
                "@/local-kits/example-v2/skills/discovery/SKILL.md",
                generated_discovery.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "@/local-kits/example-v2/skills/review/SKILL.md",
                generated_review.read_text(encoding="utf-8"),
            )
            reviewer_agent = project_root / ".codex" / "agents" / "cf-example-v2-reviewer.toml"
            reviewer_helper = project_root / ".codex" / "agents" / "cf-example-v2-reviewer-helper.toml"
            planner_agent = project_root / ".codex" / "agents" / "cf-example-v2-planner.toml"
            planner_helper = project_root / ".codex" / "agents" / "cf-example-v2-planner-helper.toml"
            self.assertTrue(reviewer_agent.is_file())
            self.assertTrue(reviewer_helper.is_file())
            self.assertTrue(planner_agent.is_file())
            self.assertTrue(planner_helper.is_file())
            self.assertIn('name = "cf-example-v2-reviewer"', reviewer_agent.read_text(encoding="utf-8"))
            self.assertIn("# Example V2 Reviewer", reviewer_agent.read_text(encoding="utf-8"))
            self.assertIn("Reviewer helper", reviewer_helper.read_text(encoding="utf-8"))
            self.assertIn("# Example V2 Planner", planner_agent.read_text(encoding="utf-8"))
            self.assertIn("missing context for the planner", planner_helper.read_text(encoding="utf-8"))
            self.assertTrue((local_kit / "skills" / "discovery" / "SKILL.md").is_file())
            self.assertTrue((local_kit / "agents" / "planner-helper.md").is_file())

    def test_example_mixed_github_install_uses_canonical_manifest_and_ignores_legacy_metadata_files(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)

            github_tmp = temp_root / "github-source"
            kit_src = _copy_fixture("example-mixed", github_tmp / "example-mixed")
            authority = {
                "source_type": "github",
                "canonical_source": "github:acme/example-mixed",
                "effective_source": "github:acme/example-mixed",
                "resolved_ref": "v2.1.0",
                "freshness": "fresh",
            }

            with patch(
                "studio.commands.kit._download_kit_from_github_with_authority",
                return_value=(kit_src, "v2.1.0", authority),
            ):
                rc, out, stderr = _run_main_json(
                    [
                        "kit",
                        "install",
                        "acme/example-mixed",
                    ],
                    cwd=project_root,
                )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["install_mode"], "copy")
            self.assertEqual(out["source"], "github:acme/example-mixed")

            installed_root = project_root / ".bootstrap" / "config" / "kits" / "example-mixed"
            self.assertTrue((installed_root / "artifacts" / "ADR" / "template.md").is_file())
            self.assertTrue((installed_root / "artifacts" / "ADR" / "example.md").is_file())
            self.assertTrue((installed_root / "skills" / "discovery" / "SKILL.md").is_file())
            self.assertTrue((installed_root / "skills" / "review" / "SKILL.md").is_file())
            self.assertTrue((installed_root / "agents" / "reviewer.md").is_file())
            self.assertTrue((installed_root / "agents" / "planner.md").is_file())
            self.assertFalse((installed_root / ".cf-studio-kit.toml").exists())
            self.assertFalse((installed_root / "manifest.toml").exists())
            self.assertFalse((installed_root / "core.toml").exists())
            self.assertEqual(
                (installed_root / "constraints.toml").read_text(encoding="utf-8"),
                "[ADR.identifiers.cpt]\nrequired = true\n\n[ADR.identifiers.adr]\nrequired = true\n",
            )
            self.assertIn(
                "@cpt-template:cpt-example-mixed-adr-template:p1",
                (installed_root / "artifacts" / "ADR" / "template.md").read_text(encoding="utf-8"),
            )

            core = _read_core(project_root)
            entry = core["kits"]["example-mixed"]
            self.assertEqual(entry["install_mode"], "copy")
            self.assertEqual(entry["source"], "github:acme/example-mixed")
            self.assertEqual(entry["resources"]["discovery"]["path"], "config/kits/example-mixed/skills/discovery/SKILL.md")
            self.assertEqual(entry["resources"]["review"]["path"], "config/kits/example-mixed/skills/review/SKILL.md")
            self.assertEqual(entry["resources"]["reviewer"]["path"], "config/kits/example-mixed/agents/reviewer.md")
            self.assertEqual(entry["resources"]["planner"]["path"], "config/kits/example-mixed/agents/planner.md")
            self.assertEqual(entry["resources"]["reviewer"]["subagents"][0]["id"], "reviewer-helper")
            self.assertEqual(entry["resources"]["planner"]["subagents"][0]["id"], "planner-helper")

            rc, out, stderr = _run_main_json(
                [
                    "generate-agents",
                    "--root",
                    str(project_root),
                    "--yes",
                ],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".bootstrap/config/kits/example-mixed/", gitignore_text)
            self.assertIn(".agents/skills/cf-example-mixed-discovery/SKILL.md", gitignore_text)
            self.assertIn(".agents/skills/cf-example-mixed-review/SKILL.md", gitignore_text)
            self.assertIn(".codex/agents/cf-example-mixed-reviewer.toml", gitignore_text)
            self.assertIn(".codex/agents/cf-example-mixed-reviewer-helper.toml", gitignore_text)
            self.assertIn(".codex/agents/cf-example-mixed-planner.toml", gitignore_text)
            self.assertIn(".codex/agents/cf-example-mixed-planner-helper.toml", gitignore_text)
            self._assert_shared_provider_outputs(project_root, gitignore_text)
            self._assert_no_non_openai_public_agent_outputs(project_root, "example-mixed", gitignore_text)

            generated_discovery = project_root / ".agents" / "skills" / "cf-example-mixed-discovery" / "SKILL.md"
            generated_review = project_root / ".agents" / "skills" / "cf-example-mixed-review" / "SKILL.md"
            self.assertTrue(generated_discovery.is_file())
            self.assertTrue(generated_review.is_file())
            self.assertIn(
                "{cf-studio-path}/config/kits/example-mixed/skills/discovery/SKILL.md",
                generated_discovery.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "{cf-studio-path}/config/kits/example-mixed/skills/review/SKILL.md",
                generated_review.read_text(encoding="utf-8"),
            )
            reviewer_agent = project_root / ".codex" / "agents" / "cf-example-mixed-reviewer.toml"
            reviewer_helper = project_root / ".codex" / "agents" / "cf-example-mixed-reviewer-helper.toml"
            planner_agent = project_root / ".codex" / "agents" / "cf-example-mixed-planner.toml"
            planner_helper = project_root / ".codex" / "agents" / "cf-example-mixed-planner-helper.toml"
            self.assertTrue(reviewer_agent.is_file())
            self.assertTrue(reviewer_helper.is_file())
            self.assertTrue(planner_agent.is_file())
            self.assertTrue(planner_helper.is_file())
            self.assertIn("# Example Mixed Reviewer", reviewer_agent.read_text(encoding="utf-8"))
            self.assertIn("legacy-vs-canonical deltas", reviewer_helper.read_text(encoding="utf-8"))
            self.assertIn("# Example Mixed Planner", planner_agent.read_text(encoding="utf-8"))
            self.assertIn("prerequisites for the mixed planner", planner_helper.read_text(encoding="utf-8"))

    def test_example_legacy_git_install_generates_proxy_agents_and_records_git_provenance(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            repo, commit_sha = _make_git_repo_from_fixture(temp_root / "fixture-root", "example-legacy")
            source = "git/" + quote(repo.as_uri(), safe="")

            with patch.dict(os.environ, {"CFS_GIT_KIT_CACHE_DIR": str(temp_root / "git-cache")}):
                rc, out, stderr = _run_main_json(
                    [
                        "kit",
                        "install",
                        source,
                        "--version",
                        "HEAD",
                    ],
                    cwd=project_root,
                )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["kit"], "example-legacy")
            self.assertEqual(out["install_mode"], "copy")

            installed_root = project_root / ".bootstrap" / "config" / "kits" / "example-legacy"
            self.assertTrue((installed_root / "artifacts" / "FEATURE" / "template.md").is_file())
            self.assertTrue((installed_root / "artifacts" / "FEATURE" / "example.md").is_file())
            self.assertTrue((installed_root / "constraints.toml").is_file())
            self.assertFalse((installed_root / "agents.toml").exists())
            self.assertFalse((installed_root / "core.toml").exists())
            self.assertIn(
                "@cpt-template:cpt-example-legacy-feature-template:p1",
                (installed_root / "artifacts" / "FEATURE" / "template.md").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "cpt-example-legacy-feature-flow",
                (installed_root / "artifacts" / "FEATURE" / "example.md").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                (installed_root / "constraints.toml").read_text(encoding="utf-8"),
                "[FEATURE.identifiers.cpt]\nrequired = true\n\n[FEATURE.identifiers.flow]\nrequired = true\n",
            )

            core = _read_core(project_root)
            entry = core["kits"]["example-legacy"]
            self.assertEqual(entry["install_mode"], "copy")
            self.assertTrue(str(entry["source"]).startswith("git:"))
            self.assertEqual(entry["source_provenance"]["source_type"], "git")
            self.assertEqual(entry["source_provenance"]["requested_ref"], "HEAD")
            self.assertEqual(entry["source_provenance"]["commit_sha"], commit_sha)

            rc, out, stderr = _run_main_json(
                [
                    "generate-agents",
                    "--root",
                    str(project_root),
                    "--yes",
                ],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".bootstrap/config/kits/example-legacy/", gitignore_text)
            self.assertNotIn(".codex/agents/example-legacy-reviewer.toml", gitignore_text)
            self.assertNotIn(".codex/agents/example-legacy-planner.toml", gitignore_text)
            self.assertFalse((project_root / ".codex" / "agents" / "example-legacy-reviewer.toml").exists())
            self.assertFalse((project_root / ".codex" / "agents" / "example-legacy-planner.toml").exists())
            self._assert_shared_provider_outputs(project_root, gitignore_text)

    def test_example_mixed_local_copy_install_supports_info_update_validate_and_all_provider_outputs(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-mixed", project_root / "local-kits" / "example-mixed")

            rc, out, stderr = _run_main_json(
                [
                    "kit",
                    "install",
                    "--path",
                    str(local_kit),
                    "--install-mode",
                    "copy",
                ],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["files_written"], 9)

            rc, out, stderr = _run_main_json(["info", "--root", str(project_root)], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "FOUND")
            self.assertEqual(out["kit_models"]["example-mixed"]["install_mode"], "copy")
            self.assertEqual(out["kit_details"]["example-mixed"]["resources"]["reviewer"]["mode"], "readonly")

            rc, out, stderr = _run_main_json(["validate-kits"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["kits_validated"], 1)
            self.assertEqual(out["templates_checked"], 1)

            rc, out, stderr = _run_main_json(
                ["kit", "update", "--path", str(local_kit), "--no-interactive", "-y"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["results"][0]["action"], "current")

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".bootstrap/config/kits/example-mixed/", gitignore_text)
            self.assertIn(".codex/agents/cf-example-mixed-reviewer-helper.toml", gitignore_text)
            self.assertIn(".codex/agents/cf-example-mixed-planner-helper.toml", gitignore_text)
            self._assert_shared_provider_outputs(project_root, gitignore_text)

    def test_example_mixed_register_local_install_generates_registered_outputs_and_keeps_source(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-mixed", project_root / "local-kits" / "example-mixed")

            rc, out, stderr = _run_main_json(
                [
                    "kit",
                    "install",
                    "--path",
                    str(local_kit),
                    "--install-mode",
                    "register",
                ],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["files_written"], 0)
            self.assertEqual(out["files_registered"], 7)

            core = _read_core(project_root)
            entry = core["kits"]["example-mixed"]
            self.assertEqual(entry["install_mode"], "register")
            self.assertEqual(entry["path"], "../local-kits/example-mixed")
            self.assertNotIn("resources", entry)

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("local-kits/example-mixed/", gitignore_text)
            self.assertIn(".codex/agents/cf-example-mixed-reviewer.toml", gitignore_text)
            self.assertIn(".codex/agents/cf-example-mixed-reviewer-helper.toml", gitignore_text)
            self.assertIn(".codex/agents/cf-example-mixed-planner.toml", gitignore_text)
            self.assertIn(".codex/agents/cf-example-mixed-planner-helper.toml", gitignore_text)
            self.assertNotIn(".bootstrap/../local-kits/example-mixed/", gitignore_text)
            self._assert_shared_provider_outputs(project_root, gitignore_text)
            self._assert_no_non_openai_public_agent_outputs(project_root, "example-mixed", gitignore_text)
            self.assertTrue((local_kit / "agents" / "reviewer-helper.md").is_file())

            rc, out, stderr = _run_main_json(["info", "--root", str(project_root)], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "FOUND")
            self.assertEqual(out["kit_models"]["example-mixed"]["install_mode"], "register")
            self.assertEqual(out["kit_models"]["example-mixed"]["drift"]["status"], "drifted")
            self.assertEqual(out["kit_details"]["example-mixed"]["resources"]["reviewer"]["path"], "../local-kits/example-mixed/agents/reviewer.md")

            rc, out, stderr = _run_main_json(["validate-kits"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["kits_validated"], 1)

            rc, out, stderr = _run_main_json(
                ["kit", "update", "--path", str(local_kit), "--no-interactive", "-y"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["results"][0]["action"], "current")

    def test_example_legacy_local_copy_install_runs_info_update_validate_without_provider_agents(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-legacy", project_root / "local-kits" / "example-legacy")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["files_written"], 3)

            rc, out, stderr = _run_main_json(["info", "--root", str(project_root)], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "FOUND")
            self.assertEqual(out["kit_models"]["example-legacy"]["install_mode"], "copy")

            rc, out, stderr = _run_main_json(["validate-kits"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["templates_checked"], 1)

            rc, out, stderr = _run_main_json(
                ["kit", "update", "--path", str(local_kit), "--no-interactive", "-y"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["results"][0]["action"], "current")

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self._assert_shared_provider_outputs(project_root, gitignore_text)
            self.assertNotIn(".claude/agents/example-legacy-reviewer.md", gitignore_text)
            self.assertNotIn(".cursor/agents/example-legacy-reviewer.md", gitignore_text)
            self.assertNotIn(".github/agents/example-legacy-reviewer.agent.md", gitignore_text)
            self.assertNotIn(".codex/agents/example-legacy-reviewer.toml", gitignore_text)

    def test_example_legacy_register_local_install_generates_provider_agents_for_all_targets(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-legacy", project_root / "local-kits" / "example-legacy")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "register"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["files_written"], 0)
            self.assertEqual(out["files_registered"], 3)

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self._assert_shared_provider_outputs(project_root, gitignore_text)
            self._assert_legacy_provider_agent_outputs(
                project_root,
                gitignore_text,
                prompt_source="@/local-kits/example-legacy/agents/reviewer.md",
            )

            rc, out, stderr = _run_main_json(["info", "--root", str(project_root)], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "FOUND")
            self.assertEqual(out["kit_models"]["example-legacy"]["install_mode"], "register")
            self.assertEqual(out["kit_models"]["example-legacy"]["manifest_source"], "legacy_manifest")

            rc, out, stderr = _run_main_json(["validate-kits"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["kits_validated"], 1)

            rc, out, stderr = _run_main_json(
                ["kit", "update", "--path", str(local_kit), "--no-interactive", "-y"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["results"][0]["action"], "current")

    def test_example_v2_register_supports_info_validate_and_update_current(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-v2", project_root / "local-kits" / "example-v2")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "register"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            rc, out, stderr = _run_main_json(["info", "--root", str(project_root)], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "FOUND")
            self.assertEqual(out["kit_models"]["example-v2"]["install_mode"], "register")
            self.assertEqual(out["kit_models"]["example-v2"]["drift"]["status"], "drifted")
            self.assertEqual(out["kit_details"]["example-v2"]["resources"]["reviewer"]["path"], "../local-kits/example-v2/agents/reviewer.md")

            rc, out, stderr = _run_main_json(["validate-kits"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["kits_validated"], 1)
            self.assertEqual(out["templates_checked"], 2)

            rc, out, stderr = _run_main_json(
                ["kit", "update", "--path", str(local_kit), "--no-interactive", "-y"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["results"][0]["action"], "current")

    def test_example_mixed_interactive_manifest_install_allows_resource_path_override(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-mixed", project_root / "local-kits" / "example-mixed")

            rc, out, stderr = _run_main_json_with_stdin(
                [
                    "kit",
                    "install",
                    "--path",
                    str(local_kit),
                    "--install-mode",
                    "copy",
                ],
                cwd=project_root,
                stdin_text="i\ny\n2\nartifacts/ADR/template-override.md\ny\n9\n",
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            overridden = project_root / ".bootstrap" / "config" / "kits" / "example-mixed" / "artifacts" / "ADR" / "template-override.md"
            default_template = project_root / ".bootstrap" / "config" / "kits" / "example-mixed" / "artifacts" / "ADR" / "template.md"
            self.assertTrue(overridden.is_file())
            self.assertFalse(default_template.exists())
            self.assertIn("Change kit install paths?", stderr)

            core = _read_core(project_root)
            self.assertEqual(
                core["kits"]["example-mixed"]["resources"]["adr-template"]["path"],
                "config/kits/example-mixed/artifacts/ADR/template-override.md",
            )

    def test_example_v2_reinstall_requires_explicit_overwrite_approval_and_restores_modified_files(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-v2", project_root / "local-kits" / "example-v2")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            installed_template = project_root / ".bootstrap" / "config" / "kits" / "example-v2" / "artifacts" / "PRD" / "template.md"
            installed_template.write_text("mutated\n", encoding="utf-8")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 2, stderr)
            self.assertEqual(out["status"], "FAIL")
            self.assertIn("already installed", out["message"])
            self.assertIn("kit update", out["hint"])

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy", "--force"],
                cwd=project_root,
            )
            self.assertEqual(rc, 2, stderr)
            self.assertEqual(out["status"], "FAIL")
            self.assertIn("approve-overwrite prd-template", out["errors"][0])

            rc, out, stderr = _run_main_json(
                [
                    "kit",
                    "install",
                    "--path",
                    str(local_kit),
                    "--install-mode",
                    "copy",
                    "--force",
                    "--approve-overwrite",
                    "prd-template",
                ],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertIn("Example V2 PRD Template", installed_template.read_text(encoding="utf-8"))

    def test_example_mixed_github_install_rejects_register_mode(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            kit_src = _copy_fixture("example-mixed", temp_root / "github-source" / "example-mixed")
            authority = {
                "source_type": "github",
                "canonical_source": "github:acme/example-mixed",
                "effective_source": "github:acme/example-mixed",
                "resolved_ref": "v2.1.0",
                "freshness": "fresh",
            }

            with patch(
                "studio.commands.kit._download_kit_from_github_with_authority",
                return_value=(kit_src, "v2.1.0", authority),
            ):
                rc, out, stderr = _run_main_json(
                    [
                        "kit",
                        "install",
                        "acme/example-mixed",
                        "--install-mode",
                        "register",
                    ],
                    cwd=project_root,
                )

            self.assertEqual(rc, 2, stderr)
            self.assertEqual(out["status"], "FAIL")
            self.assertEqual(out["message"], "--install-mode is only valid with local --path installs")
            self.assertIn("Remote GitHub and generic Git installs always copy managed artifacts", out["hint"])
            self.assertFalse((project_root / ".bootstrap" / "config" / "kits" / "example-mixed").exists())

    def test_example_legacy_generic_git_install_rejects_register_mode(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            repo, _commit_sha = _make_git_repo_from_fixture(temp_root / "fixture-root", "example-legacy")
            source = "git/" + quote(repo.as_uri(), safe="")

            with patch.dict(os.environ, {"CFS_GIT_KIT_CACHE_DIR": str(temp_root / "git-cache")}):
                rc, out, stderr = _run_main_json(
                    [
                        "kit",
                        "install",
                        source,
                        "--version",
                        "HEAD",
                        "--install-mode",
                        "register",
                    ],
                    cwd=project_root,
                )

            self.assertEqual(rc, 2, stderr)
            self.assertEqual(out["status"], "FAIL")
            self.assertEqual(out["message"], "--install-mode is only valid with local --path installs")
            self.assertIn("Remote GitHub and generic Git installs always copy managed artifacts", out["hint"])
            self.assertFalse((project_root / ".bootstrap" / "config" / "kits" / "example-legacy").exists())

    def test_example_legacy_generic_git_copy_update_applies_upstream_drift(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            repo, initial_commit = _make_git_repo_from_fixture(temp_root / "fixture-root", "example-legacy")
            source = "git/" + quote(repo.as_uri(), safe="")

            with patch.dict(os.environ, {"CFS_GIT_KIT_CACHE_DIR": str(temp_root / "git-cache")}):
                rc, out, stderr = _run_main_json(
                    [
                        "kit",
                        "install",
                        source,
                        "--version",
                        "HEAD",
                    ],
                    cwd=project_root,
                )
                self.assertEqual(rc, 0, stderr)
                self.assertEqual(out["status"], "PASS")

                installed_example = (
                    project_root / ".bootstrap" / "config" / "kits" / "example-legacy" / "artifacts" / "FEATURE" / "example.md"
                )
                self.assertIn("cpt-example-legacy-feature-flow", installed_example.read_text(encoding="utf-8"))

                upstream_example = repo / "artifacts" / "FEATURE" / "example.md"
                upstream_example.write_text("UPDATED FROM GIT SOURCE\n", encoding="utf-8")
                _run_git(repo, "add", "artifacts/FEATURE/example.md")
                _run_git(repo, "commit", "-q", "-m", "update feature example")
                updated_commit = _run_git(repo, "rev-parse", "HEAD")
                self.assertNotEqual(initial_commit, updated_commit)

                rc, out, stderr = _run_main_json(
                    ["kit", "update", "example-legacy", "--no-interactive", "-y"],
                    cwd=project_root,
                )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["kits_updated"], 1)
            result = out["results"][0]
            self.assertEqual(result["action"], "updated")
            self.assertEqual(result["accepted"], ["artifacts/FEATURE/example.md"])
            self.assertEqual(result["declined"], [])
            self.assertEqual(result["files_written"], 1)
            self.assertEqual(result["unchanged"], 2)
            self.assertEqual(result["authority"]["commit_sha"], updated_commit)
            self.assertEqual(installed_example.read_text(encoding="utf-8"), "UPDATED FROM GIT SOURCE\n")

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".bootstrap/config/kits/example-legacy/", gitignore_text)
            self._assert_shared_provider_outputs(project_root, gitignore_text)

    def test_example_mixed_register_reads_live_source_after_upstream_edit(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-mixed", project_root / "local-kits" / "example-mixed")

            rc, out, stderr = _run_main_json(
                [
                    "kit",
                    "install",
                    "--path",
                    str(local_kit),
                    "--install-mode",
                    "register",
                ],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            reviewer_agent = project_root / ".codex" / "agents" / "cf-example-mixed-reviewer.toml"
            initial_text = reviewer_agent.read_text(encoding="utf-8")
            self.assertIn("# Example Mixed Reviewer", initial_text)

            upstream_reviewer = local_kit / "agents" / "reviewer.md"
            upstream_reviewer.write_text(
                upstream_reviewer.read_text(encoding="utf-8") + "\nUpdated upstream body.\n",
                encoding="utf-8",
            )

            rc, out, stderr = _run_main_json(
                ["kit", "update", "--path", str(local_kit), "--no-interactive", "-y"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["results"][0]["action"], "current")

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            updated_text = reviewer_agent.read_text(encoding="utf-8")
            self.assertIn("Updated upstream body.", updated_text)
            self.assertNotEqual(initial_text, updated_text)

            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("local-kits/example-mixed/", gitignore_text)
            self.assertNotIn(".bootstrap/../local-kits/example-mixed/", gitignore_text)
            self.assertIn(".codex/agents/cf-example-mixed-reviewer.toml", gitignore_text)

    def test_example_mixed_register_regenerate_refreshes_openai_planner_and_skill_outputs(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-mixed", project_root / "local-kits" / "example-mixed")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "register"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)

            generated_discovery = project_root / ".agents" / "skills" / "cf-example-mixed-discovery" / "SKILL.md"
            planner_agent = project_root / ".codex" / "agents" / "cf-example-mixed-planner.toml"
            planner_helper = project_root / ".codex" / "agents" / "cf-example-mixed-planner-helper.toml"
            before_discovery = generated_discovery.read_text(encoding="utf-8")
            before_planner = planner_agent.read_text(encoding="utf-8")
            before_helper = planner_helper.read_text(encoding="utf-8")

            (local_kit / "skills" / "discovery" / "SKILL.md").write_text(
                (
                    "---\nname: discovery\ndescription: Example mixed discovery skill\n---\n"
                    "# Example Mixed Discovery\nDiscovery wrapper refresh body.\n"
                ),
                encoding="utf-8",
            )
            (local_kit / "agents" / "planner.md").write_text(
                (
                    "---\nname: planner\ndescription: Example mixed planner agent\n---\n"
                    "# Example Mixed Planner\nPlanner register refresh body.\n"
                ),
                encoding="utf-8",
            )
            (local_kit / "agents" / "planner-helper.md").write_text(
                (
                    "---\nname: planner-helper\ndescription: Mixed planner helper subagent\n---\n"
                    "# Planner helper\nPlanner helper register refresh body.\n"
                ),
                encoding="utf-8",
            )

            rc, out, stderr = _run_main_json(
                ["kit", "update", "--path", str(local_kit), "--no-interactive", "-y"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["results"][0]["action"], "current")

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)

            after_discovery = generated_discovery.read_text(encoding="utf-8")
            after_planner = planner_agent.read_text(encoding="utf-8")
            after_helper = planner_helper.read_text(encoding="utf-8")
            self.assertIn("@/local-kits/example-mixed/skills/discovery/SKILL.md", after_discovery)
            self.assertNotEqual(before_discovery, after_discovery)
            self.assertIn("Planner register refresh body.", after_planner)
            self.assertIn("Planner helper register refresh body.", after_helper)
            self.assertNotEqual(before_planner, after_planner)
            self.assertNotEqual(before_helper, after_helper)
            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("local-kits/example-mixed/", gitignore_text)
            self.assertNotIn(".bootstrap/../local-kits/example-mixed/", gitignore_text)
            self.assertIn(".agents/skills/cf-example-mixed-discovery/SKILL.md", gitignore_text)
            self.assertIn(".codex/agents/cf-example-mixed-planner.toml", gitignore_text)
            self.assertIn(".codex/agents/cf-example-mixed-planner-helper.toml", gitignore_text)

    def test_example_v2_register_regenerate_refreshes_openai_planner_outputs(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-v2", project_root / "local-kits" / "example-v2")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "register"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)

            planner_agent = project_root / ".codex" / "agents" / "cf-example-v2-planner.toml"
            planner_helper = project_root / ".codex" / "agents" / "cf-example-v2-planner-helper.toml"
            before_planner = planner_agent.read_text(encoding="utf-8")
            before_helper = planner_helper.read_text(encoding="utf-8")

            upstream_planner = local_kit / "agents" / "planner.md"
            upstream_planner.write_text(
                upstream_planner.read_text(encoding="utf-8") + "\nPlanner refresh body.\n",
                encoding="utf-8",
            )
            upstream_helper = local_kit / "agents" / "planner-helper.md"
            upstream_helper.write_text(
                upstream_helper.read_text(encoding="utf-8") + "\nPlanner helper refresh body.\n",
                encoding="utf-8",
            )

            rc, out, stderr = _run_main_json(
                ["kit", "update", "--path", str(local_kit), "--no-interactive", "-y"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["results"][0]["action"], "current")

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)

            after_planner = planner_agent.read_text(encoding="utf-8")
            after_helper = planner_helper.read_text(encoding="utf-8")
            self.assertIn("Planner refresh body.", after_planner)
            self.assertIn("Planner helper refresh body.", after_helper)
            self.assertNotEqual(before_planner, after_planner)
            self.assertNotEqual(before_helper, after_helper)
            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".codex/agents/cf-example-v2-planner.toml", gitignore_text)
            self.assertIn(".codex/agents/cf-example-v2-planner-helper.toml", gitignore_text)

    def test_example_legacy_register_regenerate_keeps_all_provider_proxy_agents_stable(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-legacy", project_root / "local-kits" / "example-legacy")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "register"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)

            claude_agent = project_root / ".claude" / "agents" / "example-legacy-reviewer.md"
            cursor_agent = project_root / ".cursor" / "agents" / "example-legacy-reviewer.md"
            copilot_agent = project_root / ".github" / "agents" / "example-legacy-reviewer.agent.md"
            openai_agent = project_root / ".codex" / "agents" / "example-legacy-reviewer.toml"
            before = {
                "claude": claude_agent.read_text(encoding="utf-8"),
                "cursor": cursor_agent.read_text(encoding="utf-8"),
                "copilot": copilot_agent.read_text(encoding="utf-8"),
                "openai": openai_agent.read_text(encoding="utf-8"),
            }

            upstream_reviewer = local_kit / "agents" / "reviewer.md"
            upstream_reviewer.write_text(
                upstream_reviewer.read_text(encoding="utf-8") + "\nLegacy provider refresh body.\n",
                encoding="utf-8",
            )

            rc, out, stderr = _run_main_json(
                ["kit", "update", "--path", str(local_kit), "--no-interactive", "-y"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["results"][0]["action"], "current")

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)

            after = {
                "claude": claude_agent.read_text(encoding="utf-8"),
                "cursor": cursor_agent.read_text(encoding="utf-8"),
                "copilot": copilot_agent.read_text(encoding="utf-8"),
                "openai": openai_agent.read_text(encoding="utf-8"),
            }
            for provider, content in after.items():
                self.assertIn("@/local-kits/example-legacy/agents/reviewer.md", content, provider)
                self.assertEqual(before[provider], content, provider)

    def test_example_mixed_copy_update_refreshes_openai_agents_and_preserves_skill_wrapper_after_regenerate(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-mixed", project_root / "local-kits" / "example-mixed")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)

            generated_review = project_root / ".agents" / "skills" / "cf-example-mixed-review" / "SKILL.md"
            reviewer_agent = project_root / ".codex" / "agents" / "cf-example-mixed-reviewer.toml"
            reviewer_helper = project_root / ".codex" / "agents" / "cf-example-mixed-reviewer-helper.toml"
            before_review = generated_review.read_text(encoding="utf-8")
            before_reviewer = reviewer_agent.read_text(encoding="utf-8")
            before_helper = reviewer_helper.read_text(encoding="utf-8")

            (local_kit / "skills" / "review" / "SKILL.md").write_text(
                (
                    "---\nname: review\ndescription: Example mixed review skill\n---\n"
                    "# Example Mixed Review\nRefreshed review skill body.\n"
                ),
                encoding="utf-8",
            )
            (local_kit / "agents" / "reviewer.md").write_text(
                (
                    "---\nname: reviewer\ndescription: Example mixed reviewer agent\n---\n"
                    "# Example Mixed Reviewer\nRefreshed reviewer body.\n"
                ),
                encoding="utf-8",
            )
            (local_kit / "agents" / "reviewer-helper.md").write_text(
                (
                    "---\nname: reviewer-helper\ndescription: Mixed reviewer helper subagent\n---\n"
                    "# Reviewer helper\nRefreshed helper body.\n"
                ),
                encoding="utf-8",
            )

            rc, out, stderr = _run_main_json(
                [
                    "kit",
                    "update",
                    "--path",
                    str(local_kit),
                    "--force",
                    "--no-interactive",
                    "-y",
                    "--approve-overwrite",
                    "review",
                    "--approve-overwrite",
                    "reviewer",
                    "--approve-overwrite",
                    "config/kits/example-mixed/agents/reviewer-helper.md",
                ],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertIn("skills/review/SKILL.md", out["results"][0]["accepted"])
            self.assertIn("agents/reviewer.md", out["results"][0]["accepted"])
            self.assertIn("agents/reviewer-helper.md", out["results"][0]["accepted"])

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)

            after_review = generated_review.read_text(encoding="utf-8")
            after_reviewer = reviewer_agent.read_text(encoding="utf-8")
            after_helper = reviewer_helper.read_text(encoding="utf-8")
            self.assertIn("{cf-studio-path}/config/kits/example-mixed/skills/review/SKILL.md", after_review)
            self.assertIn("Refreshed reviewer body.", after_reviewer)
            self.assertIn('name = "cf-example-mixed-reviewer-helper"', after_helper)
            self.assertNotEqual(before_review, after_review)
            self.assertNotEqual(before_reviewer, after_reviewer)
            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".agents/skills/cf-example-mixed-review/SKILL.md", gitignore_text)
            self.assertIn(".codex/agents/cf-example-mixed-reviewer.toml", gitignore_text)
            self.assertIn(".codex/agents/cf-example-mixed-reviewer-helper.toml", gitignore_text)

    def test_example_legacy_generic_git_check_updates_reports_available_then_current(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            repo, initial_commit = _make_git_repo_from_fixture(temp_root / "fixture-root", "example-legacy")
            source = "git/" + quote(repo.as_uri(), safe="")

            with patch.dict(os.environ, {"CFS_GIT_KIT_CACHE_DIR": str(temp_root / "git-cache")}):
                rc, out, stderr = _run_main_json(
                    ["kit", "install", source, "--version", "HEAD"],
                    cwd=project_root,
                )
                self.assertEqual(rc, 0, stderr)
                self.assertEqual(out["status"], "PASS")

                feature_example = repo / "artifacts" / "FEATURE" / "example.md"
                feature_example.write_text("update check source drift\n", encoding="utf-8")
                _run_git(repo, "add", "artifacts/FEATURE/example.md")
                _run_git(repo, "commit", "-q", "-m", "drift for check updates")
                updated_commit = _run_git(repo, "rev-parse", "HEAD")
                self.assertNotEqual(initial_commit, updated_commit)

                rc, out, stderr = _run_main_json(["kit", "check-updates"], cwd=project_root)
                self.assertEqual(rc, 0, stderr)
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["updates_available"], 1)
                self.assertEqual(out["message"], "Kit updates available")
                self.assertEqual(out["commands"], ["cfs kit update example-legacy"])
                result = out["results"][0]
                self.assertEqual(result["kit"], "example-legacy")
                self.assertEqual(result["action"], "update_available")
                self.assertEqual(result["installed_commit"], initial_commit)
                self.assertEqual(result["latest_commit"], updated_commit)
                self.assertEqual(result["command"], "cfs kit update example-legacy")

                rc, out, stderr = _run_main_json(
                    ["kit", "update", "example-legacy", "--no-interactive", "-y"],
                    cwd=project_root,
                )
                self.assertEqual(rc, 0, stderr)
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["results"][0]["action"], "updated")

                rc, out, stderr = _run_main_json(["kit", "check-updates"], cwd=project_root)

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["updates_available"], 0)
            self.assertEqual(out["message"], "All checked kits are up to date")
            self.assertEqual(out["results"][0]["kit"], "example-legacy")
            self.assertEqual(out["results"][0]["action"], "current")
            self.assertEqual(out["results"][0]["installed_commit"], updated_commit)
            self.assertEqual(out["results"][0]["latest_commit"], updated_commit)

    def test_kit_check_updates_batch_reports_mixed_current_and_update_available_results(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            legacy_repo, legacy_initial = _make_git_repo_from_fixture(temp_root / "legacy-root", "example-legacy")
            v2_repo, v2_initial = _make_subdir_git_repo_from_fixture(
                temp_root / "v2-root",
                "example-v2",
                subdir="kits/example-v2",
            )
            legacy_source = "git/" + quote(legacy_repo.as_uri(), safe="")
            v2_source = "git/" + quote(v2_repo.as_uri(), safe="") + "//kits/example-v2"

            with patch.dict(os.environ, {"CFS_GIT_KIT_CACHE_DIR": str(temp_root / "git-cache")}):
                rc, out, stderr = _run_main_json(
                    ["kit", "install", legacy_source, "--version", "HEAD"],
                    cwd=project_root,
                )
                self.assertEqual(rc, 0, stderr)
                rc, out, stderr = _run_main_json(
                    ["kit", "install", v2_source, "--version", "HEAD"],
                    cwd=project_root,
                )
                self.assertEqual(rc, 0, stderr)

                (legacy_repo / "artifacts" / "FEATURE" / "example.md").write_text(
                    "batch check update available\n",
                    encoding="utf-8",
                )
                _run_git(legacy_repo, "add", "artifacts/FEATURE/example.md")
                _run_git(legacy_repo, "commit", "-q", "-m", "legacy batch drift")
                legacy_updated = _run_git(legacy_repo, "rev-parse", "HEAD")
                self.assertNotEqual(legacy_initial, legacy_updated)

                rc, out, stderr = _run_main_json(["kit", "check-updates"], cwd=project_root)

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["updates_available"], 1)
            self.assertEqual(out["message"], "Kit updates available")
            self.assertEqual(out["commands"], ["cfs kit update example-legacy"])
            results = {result["kit"]: result for result in out["results"]}
            self.assertEqual(results["example-legacy"]["action"], "update_available")
            self.assertEqual(results["example-legacy"]["installed_commit"], legacy_initial)
            self.assertEqual(results["example-legacy"]["latest_commit"], legacy_updated)
            self.assertEqual(results["example-legacy"]["command"], "cfs kit update example-legacy")
            self.assertEqual(results["example-v2"]["action"], "current")
            self.assertEqual(results["example-v2"]["installed_commit"], v2_initial)
            self.assertEqual(results["example-v2"]["latest_commit"], v2_initial)

    def test_example_v2_copy_update_applies_upstream_changes_and_refreshes_generated_outputs(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-v2", project_root / "local-kits" / "example-v2")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")

            installed_agent = project_root / ".bootstrap" / "config" / "kits" / "example-v2" / "agents" / "reviewer.md"
            self.assertIn("Review the change set", installed_agent.read_text(encoding="utf-8"))

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            reviewer_proxy = project_root / ".codex" / "agents" / "cf-example-v2-reviewer.toml"
            initial_proxy = reviewer_proxy.read_text(encoding="utf-8")

            (local_kit / "agents" / "reviewer.md").write_text(
                "---\nname: reviewer\ndescription: Example V2 reviewer agent\n---\n# Example V2 Reviewer\nUpdated reviewer body approved.\n",
                encoding="utf-8",
            )

            rc, out, stderr = _run_main_json(
                [
                    "kit",
                    "update",
                    "--path",
                    str(local_kit),
                    "--force",
                    "--no-interactive",
                    "-y",
                    "--approve-overwrite",
                    "reviewer",
                ],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            result = out["results"][0]
            self.assertEqual(result["action"], "updated")
            self.assertIn("agents/reviewer.md", result["accepted"])
            self.assertEqual(result["declined"], [])
            self.assertGreaterEqual(result["files_written"], 1)
            self.assertIn("Updated reviewer body approved.", installed_agent.read_text(encoding="utf-8"))

            rc, out, stderr = _run_main_json(["generate-agents", "--root", str(project_root), "--yes"], cwd=project_root)
            self.assertEqual(rc, 0, stderr)
            updated_proxy = reviewer_proxy.read_text(encoding="utf-8")
            self.assertIn("Updated reviewer body approved.", updated_proxy)
            self.assertNotEqual(initial_proxy, updated_proxy)

    def test_example_v2_copy_update_requires_approve_overwrite_for_modified_template(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-v2", project_root / "local-kits" / "example-v2")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            installed_template = project_root / ".bootstrap" / "config" / "kits" / "example-v2" / "artifacts" / "PRD" / "template.md"
            installed_template.write_text("USER MODIFIED TEMPLATE\n", encoding="utf-8")
            (local_kit / "artifacts" / "PRD" / "template.md").write_text(
                "@cpt-template:cpt-example-v2-prd-template:p1\n# Upstream changed template\n",
                encoding="utf-8",
            )

            rc, out, stderr = _run_main_json(
                ["kit", "update", "--path", str(local_kit), "--force", "--no-interactive", "-y"],
                cwd=project_root,
            )
            self.assertEqual(rc, 2, stderr)
            self.assertEqual(out["status"], "WARN")
            result = out["results"][0]
            self.assertEqual(result["action"], "partial")
            self.assertEqual(result["declined"], ["artifacts/PRD/template.md"])
            self.assertIn("USER MODIFIED TEMPLATE\n", installed_template.read_text(encoding="utf-8"))

            rc, out, stderr = _run_main_json(
                [
                    "kit",
                    "update",
                    "--path",
                    str(local_kit),
                    "--force",
                    "--no-interactive",
                    "-y",
                    "--approve-overwrite",
                    "prd-template",
                ],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            result = out["results"][0]
            self.assertEqual(result["action"], "updated")
            self.assertIn("artifacts/PRD/template.md", result["accepted"])
            self.assertEqual(installed_template.read_text(encoding="utf-8"), "@cpt-template:cpt-example-v2-prd-template:p1\n# Upstream changed template\n")

    def test_example_mixed_copy_update_requires_prune_then_removes_deleted_resource(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _copy_fixture("example-mixed", project_root / "local-kits" / "example-mixed")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            installed_example = project_root / ".bootstrap" / "config" / "kits" / "example-mixed" / "artifacts" / "ADR" / "example.md"
            self.assertTrue(installed_example.is_file())

            manifest_path = local_kit / ".cf-studio-kit.toml"
            manifest_text = manifest_path.read_text(encoding="utf-8")
            manifest_path.write_text(
                manifest_text.replace(
                    '[[kits.resources]]\nid = "adr-example"\nkind = "other"\nsource = "artifacts/ADR/example.md"\ninstall_path = "artifacts/ADR/example.md"\ntype = "file"\n\n',
                    "",
                ),
                encoding="utf-8",
            )
            (local_kit / "artifacts" / "ADR" / "example.md").unlink()

            rc, out, stderr = _run_main_json(
                ["kit", "update", "--path", str(local_kit), "--force", "--no-interactive", "-y"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            result = out["results"][0]
            self.assertEqual(result["action"], "updated")
            self.assertIn("artifacts/ADR/example.md", result["accepted"])
            self.assertFalse(installed_example.exists())

            core = _read_core(project_root)
            self.assertNotIn("adr-example", core["kits"]["example-mixed"]["resources"])

    def test_kit_update_without_selector_updates_multiple_registered_git_kits(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            legacy_repo, legacy_initial = _make_git_repo_from_fixture(temp_root / "legacy-root", "example-legacy")
            subdir_repo, subdir_initial = _make_subdir_git_repo_from_fixture(
                temp_root / "subdir-root",
                "example-v2",
                subdir="kits/example-v2",
            )
            legacy_source = "git/" + quote(legacy_repo.as_uri(), safe="")
            subdir_source = "git/" + quote(subdir_repo.as_uri(), safe="") + "//kits/example-v2"

            with patch.dict(os.environ, {"CFS_GIT_KIT_CACHE_DIR": str(temp_root / "git-cache")}):
                rc, out, stderr = _run_main_json(
                    ["kit", "install", legacy_source, "--version", "HEAD"],
                    cwd=project_root,
                )
                self.assertEqual(rc, 0, stderr)
                rc, out, stderr = _run_main_json(
                    ["kit", "install", subdir_source, "--version", "HEAD"],
                    cwd=project_root,
                )
                self.assertEqual(rc, 0, stderr)

                (legacy_repo / "artifacts" / "FEATURE" / "example.md").write_text(
                    "UPDATED LEGACY FROM AGGREGATE\n",
                    encoding="utf-8",
                )
                _run_git(legacy_repo, "add", "artifacts/FEATURE/example.md")
                _run_git(legacy_repo, "commit", "-q", "-m", "legacy update")
                legacy_updated = _run_git(legacy_repo, "rev-parse", "HEAD")
                self.assertNotEqual(legacy_initial, legacy_updated)

                rc, out, stderr = _run_main_json(
                    ["kit", "update", "--no-interactive", "-y"],
                    cwd=project_root,
                )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["kits_updated"], 1)
            results = {result["kit"]: result for result in out["results"]}
            self.assertEqual(results["example-legacy"]["action"], "updated")
            self.assertEqual(results["example-v2"]["action"], "current")
            self.assertEqual(results["example-legacy"]["authority"]["commit_sha"], legacy_updated)
            self.assertEqual(results["example-v2"]["authority"]["commit_sha"], subdir_initial)
            self.assertEqual(
                (
                    project_root / ".bootstrap" / "config" / "kits" / "example-legacy" / "artifacts" / "FEATURE" / "example.md"
                ).read_text(encoding="utf-8"),
                "UPDATED LEGACY FROM AGGREGATE\n",
            )
            self.assertIn(
                "cpt-example-v2-prd-fr",
                (
                    project_root / ".bootstrap" / "config" / "kits" / "example-v2" / "artifacts" / "PRD" / "example.md"
                ).read_text(encoding="utf-8"),
            )

    def test_example_v2_generic_git_subdir_install_and_update_preserves_subdirectory_provenance(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            repo, initial_commit = _make_subdir_git_repo_from_fixture(
                temp_root / "subdir-root",
                "example-v2",
                subdir="kits/example-v2",
            )
            source = "git/" + quote(repo.as_uri(), safe="") + "//kits/example-v2"

            with patch.dict(os.environ, {"CFS_GIT_KIT_CACHE_DIR": str(temp_root / "git-cache")}):
                rc, out, stderr = _run_main_json(
                    ["kit", "install", source, "--version", "HEAD"],
                    cwd=project_root,
                )
                self.assertEqual(rc, 0, stderr)
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["kit"], "example-v2")

                core = _read_core(project_root)
                entry = core["kits"]["example-v2"]
                self.assertTrue(str(entry["source"]).endswith("//kits/example-v2"))
                self.assertEqual(entry["source_provenance"]["source_type"], "git")
                self.assertEqual(entry["source_provenance"]["selected_subdirectory"], "kits/example-v2")
                self.assertEqual(entry["source_provenance"]["commit_sha"], initial_commit)

                installed_template = (
                    project_root / ".bootstrap" / "config" / "kits" / "example-v2" / "artifacts" / "PRD" / "template.md"
                )
                self.assertIn("Example V2 PRD Template", installed_template.read_text(encoding="utf-8"))

                (repo / "kits" / "example-v2" / "artifacts" / "FEATURE" / "example.md").write_text(
                    "UPDATED FROM SUBDIR GIT\n",
                    encoding="utf-8",
                )
                _run_git(repo, "add", "kits/example-v2/artifacts/FEATURE/example.md")
                _run_git(repo, "commit", "-q", "-m", "subdir update")
                updated_commit = _run_git(repo, "rev-parse", "HEAD")

                rc, out, stderr = _run_main_json(
                    ["kit", "update", "example-v2", "--force", "--no-interactive", "-y"],
                    cwd=project_root,
                )

            self.assertEqual(rc, 2, stderr)
            self.assertEqual(out["status"], "WARN")
            result = out["results"][0]
            self.assertEqual(result["action"], "partial")
            self.assertEqual(result["accepted"], ["agents/planner-helper.md", "agents/reviewer-helper.md"])
            self.assertEqual(result["declined"], ["artifacts/FEATURE/example.md"])
            self.assertEqual(result["authority"]["commit_sha"], updated_commit)
            self.assertIn(
                "cpt-example-v2-feature-flow",
                (
                    project_root / ".bootstrap" / "config" / "kits" / "example-v2" / "artifacts" / "FEATURE" / "example.md"
                ).read_text(encoding="utf-8"),
            )
            core = _read_core(project_root)
            self.assertEqual(core["kits"]["example-v2"]["source_provenance"]["selected_subdirectory"], "kits/example-v2")

    def test_generic_git_multi_kit_selector_installs_and_updates_only_selected_kit(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            repo, _initial_commit = _make_multi_canonical_git_repo(temp_root / "multi-root")
            source = "git/" + quote(repo.as_uri(), safe="")

            with patch.dict(os.environ, {"CFS_GIT_KIT_CACHE_DIR": str(temp_root / "git-cache")}):
                rc, out, stderr = _run_main_json(
                    ["kit", "install", source + "@beta", "--version", "HEAD"],
                    cwd=project_root,
                )
                self.assertEqual(rc, 0, stderr)
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["kit"], "beta")

                beta_skill = project_root / ".bootstrap" / "config" / "kits" / "beta" / "SKILL.md"
                self.assertEqual(beta_skill.read_text(encoding="utf-8"), "# Beta v1\n")
                self.assertFalse((project_root / ".bootstrap" / "config" / "kits" / "alpha").exists())

                core = _read_core(project_root)
                self.assertTrue(str(core["kits"]["beta"]["source"]).endswith("@beta"))

                (repo / "beta.md").write_text("# Beta v2\n", encoding="utf-8")
                (repo / "alpha.md").write_text("# Alpha v2\n", encoding="utf-8")
                _run_git(repo, "add", "alpha.md", "beta.md")
                _run_git(repo, "commit", "-q", "-m", "update both kits")

                rc, out, stderr = _run_main_json(
                    [
                        "kit",
                        "update",
                        "beta",
                        "--force",
                        "--no-interactive",
                        "-y",
                        "--approve-overwrite",
                        "skill",
                    ],
                    cwd=project_root,
                )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            result = out["results"][0]
            self.assertEqual(result["action"], "updated")
            self.assertEqual(beta_skill.read_text(encoding="utf-8"), "# Beta v2\n")
            self.assertFalse((project_root / ".bootstrap" / "config" / "kits" / "alpha").exists())

    def test_example_mixed_github_ref_install_check_updates_and_update_flow(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)

            github_v1 = _copy_fixture("example-mixed", temp_root / "github-v1" / "example-mixed")
            github_v2 = _copy_fixture("example-mixed", temp_root / "github-v2" / "example-mixed")
            (github_v2 / "artifacts" / "ADR" / "template.md").write_text(
                "@cpt-template:cpt-example-mixed-adr-template:p1\n# Example Mixed ADR Template Updated\n",
                encoding="utf-8",
            )

            install_authority = {
                "source_type": "github",
                "canonical_source": "github:acme/example-mixed",
                "effective_source": "github:acme/example-mixed",
                "requested_ref": "v2.0.0",
                "resolved_ref": "v2.0.0",
                "installed_version": "v2.0.0",
                "resolver_mode": "explicit",
                "resolution_basis": "github_ref",
                "verified": "verified",
                "freshness": "fresh",
                "commit_sha": "1111111111111111111111111111111111111111",
            }
            update_authority = {
                "source_type": "github",
                "canonical_source": "github:acme/example-mixed",
                "effective_source": "github:acme/example-mixed",
                "requested_ref": "v2.1.0",
                "resolved_ref": "v2.1.0",
                "installed_version": "v2.1.0",
                "resolver_mode": "explicit",
                "resolution_basis": "github_ref",
                "verified": "verified",
                "freshness": "fresh",
                "commit_sha": "2222222222222222222222222222222222222222",
            }

            with patch(
                "studio.commands.kit._download_kit_from_github_with_authority",
                return_value=(github_v1, "v2.0.0", install_authority),
            ):
                rc, out, stderr = _run_main_json(
                    ["kit", "install", "acme/example-mixed@v2.0.0"],
                    cwd=project_root,
                )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["source"], "github:acme/example-mixed")

            installed_template = (
                project_root / ".bootstrap" / "config" / "kits" / "example-mixed" / "artifacts" / "ADR" / "template.md"
            )
            self.assertIn("cpt-example-mixed-adr-template", installed_template.read_text(encoding="utf-8"))

            core = _read_core(project_root)
            self.assertEqual(core["kits"]["example-mixed"]["source_provenance"]["resolved_ref"], "v2.0.0")
            self.assertEqual(core["kits"]["example-mixed"]["source_provenance"]["resolution_basis"], "github_ref")

            with patch(
                "studio.commands.kit._download_kit_from_github_with_authority",
                return_value=(github_v2, "v2.1.0", update_authority),
            ):
                rc, out, stderr = _run_main_json(["kit", "check-updates", "example-mixed"], cwd=project_root)
                self.assertEqual(rc, 0, stderr)
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["updates_available"], 1)
                result = out["results"][0]
                self.assertEqual(result["action"], "update_available")
                self.assertEqual(result["installed_ref"], "v2.0.0")
                self.assertEqual(result["latest_ref"], "v2.1.0")
                self.assertEqual(out["commands"], ["cfs kit update example-mixed"])

                rc, out, stderr = _run_main_json(
                    [
                        "kit",
                        "update",
                        "example-mixed",
                        "--force",
                        "--no-interactive",
                        "-y",
                        "--approve-overwrite",
                        "adr-template",
                    ],
                    cwd=project_root,
                )
                self.assertEqual(rc, 0, stderr)
                self.assertEqual(out["status"], "PASS")
                update_result = out["results"][0]
                self.assertEqual(update_result["action"], "updated")
                self.assertEqual(update_result["authority"]["resolved_ref"], "v2.1.0")
                self.assertEqual(update_result["authority"]["resolution_basis"], "github_ref")
                self.assertIn("artifacts/ADR/template.md", update_result["accepted"])

            core = _read_core(project_root)
            self.assertEqual(core["kits"]["example-mixed"]["source_provenance"]["resolved_ref"], "v2.1.0")
            self.assertEqual(core["kits"]["example-mixed"]["source_provenance"]["commit_sha"], update_authority["commit_sha"])

            with patch(
                "studio.commands.kit._download_kit_from_github_with_authority",
                return_value=(github_v2, "v2.1.0", update_authority),
            ):
                rc, out, stderr = _run_main_json(["kit", "check-updates", "example-mixed"], cwd=project_root)

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["updates_available"], 0)
            self.assertEqual(out["results"][0]["action"], "current")
            self.assertEqual(out["results"][0]["installed_ref"], "v2.1.0")
            self.assertEqual(out["results"][0]["latest_ref"], "v2.1.0")

    def test_example_v2_interactive_update_accepts_overwrite_prompt(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            _init_project(project_root, cache)
            local_kit = _make_simple_canonical_kit(project_root / "local-kits", "canon-interactive")

            rc, out, stderr = _run_main_json(
                ["kit", "install", "--path", str(local_kit), "--install-mode", "copy"],
                cwd=project_root,
            )
            self.assertEqual(rc, 0, stderr)

            installed_template = (
                project_root / ".bootstrap" / "config" / "kits" / "canon-interactive" / "SKILL.md"
            )
            installed_template.write_text("INTERACTIVE USER EDIT\n", encoding="utf-8")
            (local_kit / "SKILL.md").write_text(
                "---\nname: skill\ndescription: Canonical kit\n---\n# Interactive overwrite accepted\n",
                encoding="utf-8",
            )

            rc, out, stderr = _run_main_json_with_stdin(
                [
                    "kit",
                    "update",
                    "--path",
                    str(local_kit),
                    "--force",
                ],
                cwd=project_root,
                stdin_text="a\na\ny\n",
            )
            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            result = out["results"][0]
            self.assertEqual(result["action"], "updated")
            self.assertIn("SKILL.md", result["accepted"])
            self.assertIn("Reply with `a`, `d`, `A`, `D`, or `m`.", stderr)
            self.assertEqual(
                installed_template.read_text(encoding="utf-8"),
                "---\nname: skill\ndescription: Canonical kit\n---\n# Interactive overwrite accepted\n",
            )
