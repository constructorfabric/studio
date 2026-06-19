"""Public CLI e2e coverage for filesystem invariants and stale-output cleanup."""

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
from studio.commands.init import GITIGNORE_MARKER_END, GITIGNORE_MARKER_START
from studio.utils import toml_utils


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
    runtime_tracking: str = "tracked",
    agent_tracking: str = "tracked",
    kit_tracking: str = "tracked",
) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    with patch("studio.commands.init.CACHE_DIR", cache), patch(
        "studio.commands.init._install_default_kit",
        return_value={},
    ):
        rc, out, stderr = _run_main(
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
    return out


def _snapshot_tree(root: Path) -> dict[str, tuple[str, bytes | None]]:
    snapshot: dict[str, tuple[str, bytes | None]] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            snapshot[rel] = ("dir", None)
        elif path.is_file():
            snapshot[rel] = ("file", path.read_bytes())
    return snapshot


def _extract_managed_gitignore_block(root: Path) -> list[str]:
    lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    self_start = [index for index, line in enumerate(lines) if line == GITIGNORE_MARKER_START]
    self_end = [index for index, line in enumerate(lines) if line == GITIGNORE_MARKER_END]
    if len(self_start) != 1 or len(self_end) != 1:
        raise AssertionError("Expected exactly one managed Constructor Studio .gitignore block")
    start_idx = self_start[0]
    end_idx = self_end[0]
    if end_idx < start_idx:
        raise AssertionError("Malformed Constructor Studio managed .gitignore block")
    return lines[start_idx : end_idx + 1]


def _extract_managed_gitignore_entries(root: Path) -> list[str]:
    return [
        line
        for line in _extract_managed_gitignore_block(root)
        if line
        and not line.startswith("#")
    ]


def _kit_resources_by_id(project_root: Path, slug: str) -> dict[str, dict]:
    core = toml_utils.load(project_root / ".bootstrap" / "config" / "core.toml")
    kits = core.get("kits", {})
    assert isinstance(kits, dict), core
    entry = kits.get(slug, {})
    assert isinstance(entry, dict), entry
    resources = entry.get("resources", {})
    assert isinstance(resources, dict), resources
    return resources


def _resource_path_map(project_root: Path, slug: str) -> dict[str, str]:
    resources = _kit_resources_by_id(project_root, slug)
    return {
        resource_id: str(binding.get("path", ""))
        for resource_id, binding in sorted(resources.items())
        if isinstance(binding, dict)
    }


def _assert_resource_paths_match_installed_tree(
    testcase: unittest.TestCase,
    project_root: Path,
    slug: str,
) -> None:
    installed_root = project_root / ".bootstrap" / "config" / "kits" / slug
    tree = _snapshot_tree(installed_root)
    file_paths = {
        f"config/kits/{slug}/{rel}"
        for rel, (kind, _content) in tree.items()
        if kind == "file"
    }
    resource_paths = set(_resource_path_map(project_root, slug).values())
    testcase.assertEqual(resource_paths, file_paths)


def _write_manifest_copy_kit_source(
    root: Path,
    *,
    slug: str,
    version: str,
    include_guide: bool,
) -> Path:
    kit_src = root / slug
    (kit_src / "artifacts" / "FEATURE").mkdir(parents=True, exist_ok=True)
    (kit_src / "docs").mkdir(parents=True, exist_ok=True)
    (kit_src / "SKILL.md").write_text(
        f"---\nname: {slug}\ndescription: Snapshot kit\n---\n# {slug}\n",
        encoding="utf-8",
    )
    (kit_src / "constraints.toml").write_text(
        "[naming]\npattern = 'snap-*'\n",
        encoding="utf-8",
    )
    (kit_src / "artifacts" / "FEATURE" / "template.md").write_text(
        f"# Feature template {version}\n",
        encoding="utf-8",
    )
    guide_path = kit_src / "docs" / "guide.md"
    if include_guide:
        guide_path.write_text(
            f"# Guide {version}\n",
            encoding="utf-8",
        )
    elif guide_path.exists():
        guide_path.unlink()
    (kit_src / "conf.toml").write_text(
        f'version = "{version}"\nslug = "{slug}"\n',
        encoding="utf-8",
    )
    manifest_lines = [
        "[manifest]",
        'version = "1.0"',
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
        'id = "constraints"',
        'source = "constraints.toml"',
        'default_path = "constraints.toml"',
        'type = "file"',
        "user_modifiable = false",
        "",
        "[[resources]]",
        'id = "feature_template"',
        'source = "artifacts/FEATURE/template.md"',
        'default_path = "artifacts/FEATURE/template.md"',
        'type = "file"',
        "user_modifiable = false",
    ]
    if include_guide:
        manifest_lines.extend(
            [
                "",
                "[[resources]]",
                'id = "guide"',
                'source = "docs/guide.md"',
                'default_path = "docs/guide.md"',
                'type = "file"',
                "user_modifiable = false",
            ]
        )
    (kit_src / "manifest.toml").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    return kit_src


def _write_public_manifest_kit_source(
    root: Path,
    *,
    slug: str,
    version: str,
    skill_targets: tuple[str, ...],
    agent_targets: tuple[str, ...],
) -> Path:
    kit_src = root / slug
    kit_src.mkdir(parents=True, exist_ok=True)
    (kit_src / "skill.md").write_text(
        "---\nname: helper\ndescription: Public helper skill\n---\n# Helper\n",
        encoding="utf-8",
    )
    (kit_src / "agent.md").write_text(
        "---\nname: reviewer\ndescription: Public reviewer agent\n---\n# Reviewer\n",
        encoding="utf-8",
    )
    (kit_src / "conf.toml").write_text(
        f'version = "{version}"\nslug = "{slug}"\n',
        encoding="utf-8",
    )
    target_skill_list = ", ".join(f'"{target}"' for target in skill_targets)
    target_agent_list = ", ".join(f'"{target}"' for target in agent_targets)
    (kit_src / ".cf-studio-kit.toml").write_text(
        "\n".join(
            [
                'manifest_version = "1.0"',
                "",
                "[[kits]]",
                f'slug = "{slug}"',
                'name = "Public Kit"',
                f'version = "{version}"',
                "",
                "[[kits.resources]]",
                'id = "helper"',
                'kind = "skill"',
                'source = "skill.md"',
                'install_path = "skill.md"',
                'type = "file"',
                "public = true",
                f"generated_targets = [{target_skill_list}]",
                'description = "Helper skill"',
                "",
                "[[kits.resources]]",
                'id = "reviewer"',
                'kind = "agent"',
                'source = "agent.md"',
                'install_path = "agent.md"',
                'type = "file"',
                "public = true",
                f"generated_targets = [{target_agent_list}]",
                'description = "Reviewer agent"',
                "",
                "[kits.resources.reviewer]",
                'mode = "readonly"',
                'provider = "anthropic"',
                'reasoning_effort = "medium"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return kit_src


class TestCliFsInvariantsE2E(unittest.TestCase):
    def test_copy_install_and_prune_update_keep_exact_tree_and_core_resources(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            kit_src = _write_manifest_copy_kit_source(
                temp_root,
                slug="snapkit",
                version="1.0.0",
                include_guide=True,
            )
            _init_project(
                project_root,
                cache,
                runtime_tracking="tracked",
                agent_tracking="tracked",
                kit_tracking="tracked",
            )

            install_rc, install_out, install_stderr = _run_main(
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
            self.assertEqual(install_rc, 0, install_stderr)
            self.assertEqual(install_out["status"], "PASS")

            installed_root = project_root / ".bootstrap" / "config" / "kits" / "snapkit"
            self.assertEqual(
                _snapshot_tree(installed_root),
                {
                    "SKILL.md": ("file", b"---\nname: snapkit\ndescription: Snapshot kit\n---\n# snapkit\n"),
                    "artifacts": ("dir", None),
                    "artifacts/FEATURE": ("dir", None),
                    "artifacts/FEATURE/template.md": ("file", b"# Feature template 1.0.0\n"),
                    "constraints.toml": ("file", b"[naming]\npattern = 'snap-*'\n"),
                    "docs": ("dir", None),
                    "docs/guide.md": ("file", b"# Guide 1.0.0\n"),
                },
            )
            self.assertEqual(
                _resource_path_map(project_root, "snapkit"),
                {
                    "constraints": "config/kits/snapkit/constraints.toml",
                    "feature_template": "config/kits/snapkit/artifacts/FEATURE/template.md",
                    "guide": "config/kits/snapkit/docs/guide.md",
                    "skill": "config/kits/snapkit/SKILL.md",
                },
            )
            _assert_resource_paths_match_installed_tree(self, project_root, "snapkit")

            _write_manifest_copy_kit_source(
                temp_root,
                slug="snapkit",
                version="1.1.0",
                include_guide=False,
            )

            update_rc, update_out, update_stderr = _run_main(
                [
                    "kit",
                    "update",
                    "--path",
                    str(kit_src),
                    "--prune",
                    "--no-interactive",
                    "--yes",
                ],
                cwd=project_root,
            )
            self.assertEqual(update_rc, 0, update_stderr)
            self.assertEqual(update_out["status"], "PASS")
            self.assertEqual(
                _snapshot_tree(installed_root),
                {
                    "SKILL.md": ("file", b"---\nname: snapkit\ndescription: Snapshot kit\n---\n# snapkit\n"),
                    "artifacts": ("dir", None),
                    "artifacts/FEATURE": ("dir", None),
                    "artifacts/FEATURE/template.md": ("file", b"# Feature template 1.1.0\n"),
                    "constraints.toml": ("file", b"[naming]\npattern = 'snap-*'\n"),
                    "docs": ("dir", None),
                },
            )
            self.assertEqual(
                _resource_path_map(project_root, "snapkit"),
                {
                    "constraints": "config/kits/snapkit/constraints.toml",
                    "feature_template": "config/kits/snapkit/artifacts/FEATURE/template.md",
                    "skill": "config/kits/snapkit/SKILL.md",
                },
            )
            _assert_resource_paths_match_installed_tree(self, project_root, "snapkit")

    def test_generate_agents_rewrites_exact_managed_gitignore_block_after_public_target_shift(self):
        with TemporaryDirectory() as td:
            temp_root = Path(td)
            cache = _make_cache(temp_root)
            project_root = temp_root / "proj"
            kit_src = _write_public_manifest_kit_source(
                temp_root,
                slug="pubkit",
                version="1.0.0",
                skill_targets=("cursor",),
                agent_targets=("cursor",),
            )
            _init_project(
                project_root,
                cache,
                runtime_tracking="tracked",
                agent_tracking="ignored",
                kit_tracking="tracked",
            )
            base_block = _extract_managed_gitignore_block(project_root)
            base_entries = _extract_managed_gitignore_entries(project_root)

            install_rc, install_out, install_stderr = _run_main(
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
            self.assertEqual(install_rc, 0, install_stderr)
            self.assertEqual(install_out["status"], "PASS")
            install_entries = set(_extract_managed_gitignore_entries(project_root))
            self.assertEqual(install_entries, set(base_entries))

            first_generate_rc, first_generate_out, first_generate_stderr = _run_main(
                [
                    "generate-agents",
                    "--agent",
                    "cursor",
                    "--yes",
                ],
                cwd=project_root,
            )
            self.assertEqual(first_generate_rc, 0, first_generate_stderr)
            first_cursor = first_generate_out.get("results", {}).get("cursor", first_generate_out)
            self.assertEqual(first_cursor.get("status"), "PASS")
            self.assertTrue((project_root / ".cursor" / "agents" / "cf-pubkit-reviewer.mdc").is_file())
            self.assertEqual(
                set(_extract_managed_gitignore_entries(project_root)),
                set(base_entries)
                | {
                    ".agents/skills/cf-pubkit-helper/SKILL.md",
                    ".agents/skills/helper/SKILL.md",
                    ".claude/skills/helper/SKILL.md",
                    ".cursor/agents/cf-pubkit-reviewer.mdc",
                },
            )

            _write_public_manifest_kit_source(
                temp_root,
                slug="pubkit",
                version="1.1.0",
                skill_targets=("openai",),
                agent_targets=("openai",),
            )

            update_rc, update_out, update_stderr = _run_main(
                [
                    "kit",
                    "update",
                    "--path",
                    str(kit_src),
                    "--no-interactive",
                    "--yes",
                ],
                cwd=project_root,
            )
            self.assertEqual(update_rc, 0, update_stderr)
            self.assertEqual(update_out["status"], "PASS")

            second_generate_rc, second_generate_out, second_generate_stderr = _run_main(
                [
                    "generate-agents",
                    "--agent",
                    "openai",
                    "--yes",
                ],
                cwd=project_root,
            )
            self.assertEqual(second_generate_rc, 0, second_generate_stderr)
            second_openai = second_generate_out.get("results", {}).get("openai", second_generate_out)
            self.assertEqual(second_openai.get("status"), "PASS")
            self.assertFalse((project_root / ".cursor" / "agents" / "cf-pubkit-reviewer.mdc").exists())
            self.assertEqual(
                set(_extract_managed_gitignore_entries(project_root)),
                set(base_entries)
                | {
                    ".agents/skills/cf-pubkit-helper/SKILL.md",
                    ".agents/skills/helper/SKILL.md",
                    ".claude/skills/helper/SKILL.md",
                    ".codex/agents/cf-pubkit-reviewer.toml",
                },
            )
            self.assertEqual(_extract_managed_gitignore_block(project_root)[0], base_block[0])
            self.assertEqual(_extract_managed_gitignore_block(project_root)[-1], base_block[-1])


if __name__ == "__main__":
    unittest.main()
