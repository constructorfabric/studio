"""
Focused public-CLI e2e coverage for managed ``.gitignore`` content.

These tests stay at the public ``studio.cli.main([...])`` layer and assert the
exact managed ignore entries written for runtime files, ignored kit installs,
and generated host integration outputs.
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


def _run_main(argv: list[str], *, cwd: Path) -> tuple[int, dict, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with _chdir(cwd), redirect_stdout(stdout), redirect_stderr(stderr):
        rc = main(argv)
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
    arch = cache / "architecture" / "specs" / "kit"
    arch.mkdir(parents=True, exist_ok=True)
    for rel in (
        "specs/traceability.md",
        "specs/CDSL.md",
        "specs/PDSL.md",
        "specs/cli.md",
        "specs/CLISPEC.md",
        "specs/artifacts-registry.md",
        "specs/kit/constraints.md",
        "specs/kit/kit.md",
    ):
        target = cache / "architecture" / rel
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


def _make_local_kit_source(root: Path, slug: str = "demo") -> Path:
    kit_src = root / slug
    kit_src.mkdir(parents=True, exist_ok=True)
    (kit_src / "artifacts" / "FEATURE").mkdir(parents=True, exist_ok=True)
    (kit_src / "artifacts" / "FEATURE" / "template.md").write_text(
        "# Feature\n",
        encoding="utf-8",
    )
    (kit_src / "SKILL.md").write_text(
        f"---\nname: {slug}\ndescription: Test kit\n---\n# {slug}\n",
        encoding="utf-8",
    )
    (kit_src / "constraints.toml").write_text(
        "[naming]\npattern = 'demo-*'\n",
        encoding="utf-8",
    )
    (kit_src / "conf.toml").write_text(
        f'version = "1.2.3"\nslug = "{slug}"\n',
        encoding="utf-8",
    )
    return kit_src


def _make_public_components_kit_source(root: Path, slug: str = "kitpub") -> Path:
    kit_src = root / slug
    kit_src.mkdir(parents=True, exist_ok=True)

    (kit_src / "SKILL.md").write_text(
        "---\nname: skill\ndescription: Public kit skill\n---\n# Public kit skill\n",
        encoding="utf-8",
    )
    (kit_src / "agent.md").write_text(
        "# Public agent prompt\nPublic agent body.\n",
        encoding="utf-8",
    )
    (kit_src / "helper.md").write_text(
        "# Public helper prompt\nPublic helper body.\n",
        encoding="utf-8",
    )
    (kit_src / ".cf-studio-kit.toml").write_text(
        "\n".join(
            [
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
                'generated_targets = ["openai"]',
                "",
                "[[kits.resources]]",
                'id = "agent"',
                'kind = "agent"',
                'source = "agent.md"',
                'install_path = "agent.md"',
                'type = "file"',
                "public = true",
                'generated_targets = ["openai"]',
                'description = "Public kit agent"',
                "",
                "[kits.resources.agent]",
                'mode = "readonly"',
                "",
                "[[kits.resources.agent.subagents]]",
                'id = "helper"',
                'source = "helper.md"',
                'generated_targets = ["openai"]',
                'description = "Public helper agent"',
                'mode = "readonly"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return kit_src


def _make_agent_proxy_kit_source(root: Path, slug: str = "proxykit") -> Path:
    kit_src = root / slug
    (kit_src / "agents").mkdir(parents=True, exist_ok=True)
    (kit_src / "conf.toml").write_text(
        f'version = "1.2.3"\nslug = "{slug}"\n',
        encoding="utf-8",
    )
    (kit_src / "agents.toml").write_text(
        '[agents.kitproxy]\n'
        'description = "Kit proxy agent"\n'
        'prompt_file = "agents/kitproxy.md"\n'
        'mode = "readonly"\n',
        encoding="utf-8",
    )
    (kit_src / "agents" / "kitproxy.md").write_text(
        "# Kit proxy prompt\nLegacy kit proxy body.\n",
        encoding="utf-8",
    )
    (kit_src / "manifest.toml").write_text(
        "\n".join(
            [
                "[manifest]",
                'version = "1.0"',
                f'root = "{{cf-studio-path}}/config/kits/{slug}"',
                "user_modifiable = false",
                "",
                "[[resources]]",
                'id = "agents_toml"',
                'source = "agents.toml"',
                'default_path = "agents.toml"',
                'type = "file"',
                "user_modifiable = false",
                "",
                "[[resources]]",
                'id = "agent_prompt"',
                'source = "agents/kitproxy.md"',
                'default_path = "agents/kitproxy.md"',
                'type = "file"',
                "user_modifiable = false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return kit_src


def _init_project(
    root: Path,
    cache: Path,
    *,
    runtime_tracking: str = "ignored",
    agent_tracking: str = "ignored",
    kit_tracking: str = "tracked",
) -> tuple[int, dict, str]:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    with patch("studio.commands.init.CACHE_DIR", cache), patch(
        "studio.commands.init._install_default_kit",
        return_value={},
    ):
        return _run_main(
            [
                "--json",
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


class TestCliGitignoreE2E(unittest.TestCase):
    def test_init_writes_only_managed_runtime_entries(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"

            rc, out, _stderr = _init_project(
                project_root,
                cache,
                runtime_tracking="ignored",
                agent_tracking="tracked",
                kit_tracking="tracked",
            )

            self.assertEqual(rc, 0)
            self.assertEqual(out["status"], "PASS")

            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("# BEGIN Constructor Studio", gitignore_text)
            self.assertIn(".bootstrap/.core/", gitignore_text)
            self.assertIn(".bootstrap/.gen/", gitignore_text)
            self.assertNotIn(".bootstrap/\n", gitignore_text)
            self.assertNotIn(".bootstrap/whatsnew.toml", gitignore_text)
            self.assertNotIn(".bootstrap/version.toml", gitignore_text)
            self.assertNotIn(".github/prompts/cf.prompt.md", gitignore_text)
            self.assertNotIn(".claude/skills/cf/SKILL.md", gitignore_text)

            self.assertTrue((project_root / ".bootstrap" / ".core").is_dir())
            self.assertTrue((project_root / ".bootstrap" / ".gen").is_dir())
            self.assertTrue((project_root / ".bootstrap" / "whatsnew.toml").is_file())
            self.assertTrue((project_root / ".bootstrap" / "version.toml").is_file())
            self.assertFalse((project_root / ".github").exists())
            self.assertFalse((project_root / ".claude").exists())

    def test_kit_install_with_ignored_tracking_adds_only_specific_kit_path(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            kit_src = _make_local_kit_source(temp_root, "demo")
            project_root = temp_root / "proj"

            init_rc, init_out, _stderr = _init_project(
                project_root,
                cache,
                runtime_tracking="tracked",
                agent_tracking="tracked",
                kit_tracking="tracked",
            )
            self.assertEqual(init_rc, 0)
            self.assertEqual(init_out["status"], "PASS")

            with patch("studio.commands.kit._prompt_git_tracking_for_installed_kit", return_value="ignored"), patch(
                "sys.stdin.isatty",
                return_value=True,
            ):
                rc, out, _stderr = _run_main(
                    [
                        "--json",
                        "kit",
                        "install",
                        "--path",
                        str(kit_src),
                    ],
                    cwd=project_root,
                )

            self.assertEqual(rc, 0)
            self.assertEqual(out["status"], "PASS")

            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".bootstrap/config/kits/demo/", gitignore_text)
            self.assertNotIn(".bootstrap/config/kits/\n", gitignore_text)
            self.assertNotIn(".bootstrap/.core/", gitignore_text)
            self.assertNotIn(".bootstrap/.gen/", gitignore_text)
            self.assertNotIn(".github/prompts/cf.prompt.md", gitignore_text)

            installed_skill = project_root / ".bootstrap" / "config" / "kits" / "demo" / "SKILL.md"
            installed_template = (
                project_root / ".bootstrap" / "config" / "kits" / "demo" / "artifacts" / "FEATURE" / "template.md"
            )
            self.assertTrue(installed_skill.is_file())
            self.assertTrue(installed_template.is_file())
            self.assertFalse((project_root / ".bootstrap" / "config" / "kits" / "missing").exists())
            self.assertFalse((project_root / ".github").exists())
            self.assertFalse((project_root / ".claude").exists())

    def test_generate_agents_outputs_match_managed_host_gitignore_entries(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"

            init_rc, init_out, _stderr = _init_project(
                project_root,
                cache,
                runtime_tracking="tracked",
                agent_tracking="ignored",
                kit_tracking="tracked",
            )
            self.assertEqual(init_rc, 0)
            self.assertEqual(init_out["status"], "PASS")

            gitignore_before = (project_root / ".gitignore").read_text(encoding="utf-8")
            for expected in (
                ".claude/skills/cf/SKILL.md",
                ".cursor/commands/cf.md",
                ".github/prompts/cf.prompt.md",
                ".windsurf/workflows/cf.md",
                ".codex/.cf-installed",
            ):
                self.assertIn(expected, gitignore_before)
            for forbidden in (
                ".claude/\n",
                ".cursor/\n",
                ".github/\n",
                ".windsurf/\n",
                ".codex/\n",
            ):
                self.assertNotIn(forbidden, gitignore_before)

            rc, out, _stderr = _run_main(
                [
                    "--json",
                    "generate-agents",
                    "--root",
                    str(project_root),
                    "--yes",
                ],
                cwd=project_root,
            )

            self.assertEqual(rc, 0)
            self.assertEqual(out["status"], "PASS")

            gitignore_after = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertEqual(gitignore_after, gitignore_before)

            self.assertTrue((project_root / ".claude" / "skills" / "cf" / "SKILL.md").is_file())
            self.assertTrue((project_root / ".cursor" / "commands" / "cf.md").is_file())
            self.assertTrue((project_root / ".github" / "prompts" / "cf.prompt.md").is_file())
            self.assertTrue((project_root / ".windsurf" / "workflows" / "cf.md").is_file())
            self.assertTrue((project_root / ".codex" / ".cf-installed").is_file())
            self.assertTrue((project_root / ".agents" / "skills" / "cf" / "SKILL.md").is_file())

    def test_generate_agents_adds_gitignore_entry_for_kit_public_skill(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            kit_src = _make_public_components_kit_source(temp_root, "kitpub")
            project_root = temp_root / "proj"

            init_rc, init_out, _stderr = _init_project(
                project_root,
                cache,
                runtime_tracking="tracked",
                agent_tracking="ignored",
                kit_tracking="tracked",
            )
            self.assertEqual(init_rc, 0)
            self.assertEqual(init_out["status"], "PASS")

            install_rc, install_out, _stderr = _run_main(
                [
                    "--json",
                    "kit",
                    "install",
                    "--path",
                    str(kit_src),
                    "--install-mode",
                    "copy",
                ],
                cwd=project_root,
            )
            self.assertEqual(install_rc, 0)
            self.assertEqual(install_out["status"], "PASS")

            rc, out, _stderr = _run_main(
                [
                    "--json",
                    "generate-agents",
                    "--root",
                    str(project_root),
                    "--yes",
                ],
                cwd=project_root,
            )
            self.assertEqual(rc, 0)
            self.assertEqual(out["status"], "PASS")

            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".agents/skills/cf-kitpub-skill/SKILL.md", gitignore_text)
            self.assertNotIn(".agents/skills/cf-kitpub-skill/\n", gitignore_text)

            installed_skill = project_root / ".bootstrap" / "config" / "kits" / "kitpub" / "SKILL.md"
            generated_skill = project_root / ".agents" / "skills" / "cf-kitpub-skill" / "SKILL.md"

            self.assertTrue(installed_skill.is_file())
            self.assertTrue(generated_skill.is_file())
            self.assertIn(
                "{cf-studio-path}/config/kits/kitpub/SKILL.md",
                generated_skill.read_text(encoding="utf-8"),
            )

    def test_generate_agents_adds_gitignore_entry_for_kit_agent_proxy(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            kit_src = _make_agent_proxy_kit_source(temp_root, "proxykit")
            project_root = temp_root / "proj"

            init_rc, init_out, _stderr = _init_project(
                project_root,
                cache,
                runtime_tracking="tracked",
                agent_tracking="ignored",
                kit_tracking="tracked",
            )
            self.assertEqual(init_rc, 0)
            self.assertEqual(init_out["status"], "PASS")

            install_rc, install_out, _stderr = _run_main(
                [
                    "--json",
                    "kit",
                    "install",
                    "--path",
                    str(kit_src),
                    "--install-mode",
                    "copy",
                ],
                cwd=project_root,
            )
            self.assertEqual(install_rc, 0)
            self.assertEqual(install_out["status"], "PASS")

            rc, out, _stderr = _run_main(
                [
                    "--json",
                    "generate-agents",
                    "--root",
                    str(project_root),
                    "--yes",
                ],
                cwd=project_root,
            )
            self.assertEqual(rc, 0)
            self.assertEqual(out["status"], "PASS")

            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".codex/agents/kitproxy.toml", gitignore_text)
            self.assertNotIn(".codex/agents/\n", gitignore_text)

            installed_agents_toml = project_root / ".bootstrap" / "config" / "kits" / "proxykit" / "agents.toml"
            installed_prompt = project_root / ".bootstrap" / "config" / "kits" / "proxykit" / "agents" / "kitproxy.md"
            generated_proxy = project_root / ".codex" / "agents" / "kitproxy.toml"

            self.assertTrue(installed_agents_toml.is_file())
            self.assertTrue(installed_prompt.is_file())
            self.assertTrue(generated_proxy.is_file())
            self.assertIn("{cf-studio-path}/config/kits/proxykit/agents/kitproxy.md", generated_proxy.read_text(encoding="utf-8"))
