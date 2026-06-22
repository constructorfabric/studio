"""Public CLI e2e coverage for chunk-input and kit utility commands."""

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
from studio.utils.ui import is_json_mode, set_json_mode


VALID_PDSL = """UNIT Demo

PURPOSE:
  Validate a small block.

DO:
  - RUN Do something deterministic

RULES:
  - ALWAYS keep output stable
"""


@contextmanager
def _chdir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _run_main(argv: list[str], *, cwd: Path, stdin_text: str | None = None) -> tuple[int, str, str]:
    from studio.utils.ui import is_json_mode, set_json_mode

    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin = io.StringIO(stdin_text) if stdin_text is not None else None
    saved_json_mode = is_json_mode()
    try:
        with _chdir(cwd), redirect_stdout(stdout), redirect_stderr(stderr):
            set_json_mode(False)
            if stdin is None:
                rc = main(argv)
            else:
                with patch("sys.stdin", stdin):
                    rc = main(argv)
        return rc, stdout.getvalue(), stderr.getvalue()
    finally:
        set_json_mode(saved_json_mode)


def _run_main_json(argv: list[str], *, cwd: Path, stdin_text: str | None = None) -> tuple[int, dict, str]:
    rc, stdout, stderr = _run_main(["--json", *argv], cwd=cwd, stdin_text=stdin_text)
    return rc, json.loads(stdout), stderr


def _snapshot_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


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


class TestRunMainIsolation(unittest.TestCase):
    def test_run_main_restores_json_mode(self):
        with TemporaryDirectory() as td:
            set_json_mode(True)

            def _fake_main(_argv):
                set_json_mode(False)
                return 0

            with patch(f"{__name__}.main", side_effect=_fake_main):
                rc, stdout, _stderr = _run_main(["doctor"], cwd=Path(td))

            self.assertEqual(rc, 0)
            self.assertEqual(stdout, "")
            self.assertTrue(is_json_mode())
            set_json_mode(False)


def _make_local_kit_source(root: Path, slug: str = "demo") -> Path:
    kit_src = root / slug
    (kit_src / "artifacts" / "FEATURE").mkdir(parents=True, exist_ok=True)
    (kit_src / "artifacts" / "FEATURE" / "template.md").write_text(
        f"# {slug} feature\n",
        encoding="utf-8",
    )
    (kit_src / "SKILL.md").write_text(
        f"---\nname: {slug}\ndescription: Test kit\n---\n# {slug}\nkit body\n",
        encoding="utf-8",
    )
    (kit_src / "constraints.toml").write_text(
        f"[naming]\npattern = '{slug}-*'\n",
        encoding="utf-8",
    )
    (kit_src / "conf.toml").write_text(
        f'version = "1.2.3"\nslug = "{slug}"\n',
        encoding="utf-8",
    )
    return kit_src


def _make_public_manifest_kit_source(root: Path, slug: str = "pubkit") -> Path:
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
    (kit_src / "auditor.md").write_text(
        "---\nname: auditor\ndescription: Nested auditor\n---\n# Auditor\n",
        encoding="utf-8",
    )
    (kit_src / ".cf-studio-kit.toml").write_text(
        "\n".join([
            'manifest_version = "1.0"',
            "",
            "[[kits]]",
            f'slug = "{slug}"',
            'name = "Public Kit"',
            'version = "2.0.0"',
            "",
            "[[kits.resources]]",
            'id = "helper"',
            'kind = "skill"',
            'source = "skill.md"',
            'type = "file"',
            "public = true",
            'generated_targets = ["cursor"]',
            'description = "Helper skill"',
            "",
            "[[kits.resources]]",
            'id = "reviewer"',
            'kind = "agent"',
            'source = "agent.md"',
            'type = "file"',
            "public = true",
            'generated_targets = ["cursor"]',
            'description = "Reviewer agent"',
            "",
            "[kits.resources.targets.cursor]",
            'mode = "readonly"',
            'provider = "anthropic"',
            'reasoning_effort = "medium"',
            "",
            "[[kits.resources.agent.subagents]]",
            'id = "auditor"',
            'source = "auditor.md"',
            'description = "Nested auditor"',
            'generated_targets = ["cursor"]',
            "prefix_generated_name = false",
            'mode = "readonly"',
            'provider = "anthropic"',
            'tools = ["Read"]',
        ]) + "\n",
        encoding="utf-8",
    )
    return kit_src


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
    return out


class TestCliKitUtilityE2E(unittest.TestCase):
    def test_chunk_input_dry_run_from_files_is_read_only(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            src = root / "input.md"
            src.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
            out_dir = root / "chunks"
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(
                [
                    "chunk-input",
                    str(src),
                    "--output-dir",
                    str(out_dir),
                    "--max-lines",
                    "2",
                    "--threshold-lines",
                    "3",
                    "--dry-run",
                ],
                cwd=root,
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "OK")
            self.assertTrue(out["dry_run"])
            self.assertEqual(out["total_sources"], 1)
            self.assertEqual(out["total_lines"], 4)
            self.assertTrue(out["plan_required"])
            self.assertFalse(out_dir.exists())
            self.assertEqual(_snapshot_tree(root), before)

    def test_chunk_input_public_cli_writes_manifest_and_chunk_contents(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            src = root / "request notes.md"
            out_dir = root / "chunks"
            src.write_text("alpha\nbeta\ngamma\ndelta\nepsilon\n", encoding="utf-8")

            rc, out, stderr = _run_main_json(
                [
                    "chunk-input",
                    str(src),
                    "--output-dir",
                    str(out_dir),
                    "--include-stdin",
                    "--stdin-label",
                    "Prompt Request",
                    "--max-lines",
                    "2",
                    "--threshold-lines",
                    "4",
                ],
                cwd=root,
                stdin_text="intro\ncontext\nbridge\n",
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "OK")
            self.assertEqual(out["total_sources"], 2)
            self.assertEqual(out["total_lines"], 8)
            self.assertEqual(out["chunk_count"], 5)
            self.assertTrue(out["plan_required"])

            direct_prompt = out_dir / "direct-prompt.md"
            manifest_path = out_dir / "manifest.json"
            self.assertEqual(out["direct_prompt_file"], direct_prompt.resolve().as_posix())
            self.assertEqual(out["package_manifest"], manifest_path.resolve().as_posix())
            self.assertEqual(direct_prompt.read_text(encoding="utf-8"), "intro\ncontext\nbridge\n")

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["input_signature"], out["input_signature"])
            self.assertEqual(manifest["direct_prompt_file"], "direct-prompt.md")
            self.assertEqual(manifest["total_sources"], 2)
            self.assertEqual(manifest["total_lines"], 8)
            self.assertEqual(manifest["max_lines"], 2)
            self.assertEqual(
                [chunk["file"] for chunk in manifest["chunks"]],
                [
                    "001-01-prompt-request-part-01.md",
                    "002-01-prompt-request-part-02.md",
                    "003-02-request-notes-part-01.md",
                    "004-02-request-notes-part-02.md",
                    "005-02-request-notes-part-03.md",
                ],
            )
            self.assertEqual(
                sorted(path.name for path in out_dir.iterdir() if path.is_file()),
                [
                    "001-01-prompt-request-part-01.md",
                    "002-01-prompt-request-part-02.md",
                    "003-02-request-notes-part-01.md",
                    "004-02-request-notes-part-02.md",
                    "005-02-request-notes-part-03.md",
                    "direct-prompt.md",
                    "manifest.json",
                ],
            )

            expected_chunks = {
                "001-01-prompt-request-part-01.md": "intro\ncontext\n",
                "002-01-prompt-request-part-02.md": "bridge\n",
                "003-02-request-notes-part-01.md": "alpha\nbeta\n",
                "004-02-request-notes-part-02.md": "gamma\ndelta\n",
                "005-02-request-notes-part-03.md": "epsilon\n",
            }
            for chunk in out["chunks"]:
                chunk_path = Path(chunk["path"])
                self.assertEqual(chunk_path.read_text(encoding="utf-8"), expected_chunks[chunk["file"]])

    def test_chunk_input_stdin_only_writes_expected_files(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            out_dir = root / "chunks"

            rc, out, stderr = _run_main_json(
                [
                    "chunk-input",
                    "--output-dir",
                    str(out_dir),
                    "--stdin-label",
                    "Direct Prompt",
                    "--max-lines",
                    "2",
                ],
                cwd=root,
                stdin_text="alpha\nbeta\ngamma\n",
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "OK")
            self.assertEqual(out["total_sources"], 1)
            self.assertEqual(out["chunk_count"], 2)
            self.assertEqual((out_dir / "direct-prompt.md").read_text(encoding="utf-8"), "alpha\nbeta\ngamma\n")
            self.assertTrue((out_dir / "001-01-direct-prompt-part-01.md").is_file())
            self.assertTrue((out_dir / "002-01-direct-prompt-part-02.md").is_file())

    def test_chunk_input_invalid_output_dir_errors_without_writes(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            src = root / "input.md"
            src.write_text("alpha\n", encoding="utf-8")
            output_file = root / "not-a-dir"
            output_file.write_text("occupied\n", encoding="utf-8")
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(
                [
                    "chunk-input",
                    str(src),
                    "--output-dir",
                    str(output_file),
                ],
                cwd=root,
            )

            self.assertEqual(rc, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(out["status"], "ERROR")
            self.assertIn("not a directory", out["message"])
            self.assertEqual(_snapshot_tree(root), before)

    def test_chunk_input_invalid_thresholds_error_without_writes(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            src = root / "input.md"
            src.write_text("alpha\n", encoding="utf-8")
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(
                [
                    "chunk-input",
                    str(src),
                    "--output-dir",
                    str(root / "chunks"),
                    "--threshold-lines",
                    "0",
                ],
                cwd=root,
            )

            self.assertEqual(rc, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(out["status"], "ERROR")
            self.assertIn("--threshold-lines must be > 0", out["message"])
            self.assertEqual(_snapshot_tree(root), before)

    def test_chunk_input_missing_source_file_errors_without_writes(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(
                [
                    "chunk-input",
                    str(root / "missing.md"),
                    "--output-dir",
                    str(root / "chunks"),
                ],
                cwd=root,
            )

            self.assertEqual(rc, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(out["status"], "ERROR")
            self.assertIn("Input file not found", out["message"])
            self.assertEqual(_snapshot_tree(root), before)

    def test_toc_skip_validate_and_indent_max_level_only_mutate_targets(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            doc = root / "doc.md"
            doc.write_text("# Title\n\n## Alpha\n\n### Beta\n\n#### Gamma\n", encoding="utf-8")
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(
                [
                    "toc",
                    str(doc),
                    "--skip-validate",
                    "--indent",
                    "4",
                    "--max-level",
                    "2",
                ],
                cwd=root,
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "OK")
            self.assertEqual(out["results"][0]["status"], "UPDATED")
            self.assertNotIn("validation", out["results"][0])
            text = doc.read_text(encoding="utf-8")
            self.assertIn("- [Alpha](#alpha)", text)
            self.assertNotIn("Beta](#beta)", text)
            self.assertEqual(_snapshot_tree(root).keys(), before.keys())

    def test_toc_multi_file_mixed_results(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            first = root / "first.md"
            second = root / "second.md"
            first.write_text("# One\n\n## Alpha\n", encoding="utf-8")
            second.write_text("# Two\n\n<!-- toc -->\n- [Two](#two)\n<!-- /toc -->\n", encoding="utf-8")

            rc, out, stderr = _run_main_json(["toc", str(first), str(second)], cwd=root)

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "OK")
            statuses = {item["file"]: item["status"] for item in out["results"]}
            self.assertEqual(statuses[first.resolve().as_posix()], "UPDATED")
            self.assertIn(statuses[second.resolve().as_posix()], {"UNCHANGED", "UPDATED", "SKIP"})

    def test_pdsl_stdin_mode_pass_is_read_only(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(
                ["pdsl", "validate", "-"],
                cwd=root,
                stdin_text=VALID_PDSL,
            )

            self.assertEqual(rc, 0, stderr)
            self.assertTrue(out["ok"])
            self.assertEqual(out["summary"]["error_count"], 0)
            self.assertEqual(_snapshot_tree(root), before)

    def test_pdsl_file_mode_pass_is_read_only(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            source = root / "prompt.md"
            source.write_text("```pdsl\n" + VALID_PDSL + "\n```\n", encoding="utf-8")
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(
                ["pdsl", "validate", str(source)],
                cwd=root,
            )

            self.assertEqual(rc, 0, stderr)
            self.assertTrue(out["ok"])
            self.assertEqual(out["results"][0]["status"], "PASS")
            self.assertEqual(_snapshot_tree(root), before)

    def test_pdsl_verbose_fail_contract_reports_findings(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            invalid = "UNIT Demo\n\nDO:\n  - MUST not use old keyword\n"
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(
                ["pdsl", "validate", "--text", invalid, "--verbose"],
                cwd=root,
            )

            self.assertEqual(rc, 2, stderr)
            self.assertFalse(out["ok"])
            self.assertGreater(out["summary"]["finding_count"], 0)
            self.assertTrue(any("context" in finding for finding in out["results"][0]["findings"]))
            self.assertEqual(_snapshot_tree(root), before)

    def test_pdsl_read_error_contract(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            missing = root / "missing.md"
            before = _snapshot_tree(root)

            rc, out, stderr = _run_main_json(
                ["pdsl", "validate", str(missing)],
                cwd=root,
            )

            self.assertEqual(rc, 1, stderr)
            self.assertFalse(out["ok"])
            self.assertEqual(out["results"][0]["status"], "ERROR")
            self.assertEqual(out["results"][0]["errors"][0]["kind"], "READ_ERROR")
            self.assertEqual(_snapshot_tree(root), before)

    def test_kit_install_dry_run_public_cli_writes_no_files(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            cache = _make_cache(root)
            project_root = root / "proj"
            kit_src = _make_local_kit_source(root, "drykit")
            _init_project(project_root, cache)
            before = _snapshot_tree(project_root)

            rc, out, stderr = _run_main_json(
                [
                    "kit",
                    "install",
                    "--path",
                    str(kit_src),
                    "--dry-run",
                ],
                cwd=project_root,
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "DRY_RUN")
            self.assertEqual(out["kit"], "drykit")
            self.assertEqual(out["version"], "1.2.3")
            self.assertEqual(
                Path(out["target"]).resolve(),
                (project_root / ".bootstrap" / "config" / "kits" / "drykit").resolve(),
            )
            self.assertFalse((project_root / ".bootstrap" / "config" / "kits" / "drykit").exists())
            self.assertEqual(_snapshot_tree(project_root), before)

    def test_kit_install_public_cli_copies_expected_files_and_core_entry(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            cache = _make_cache(root)
            project_root = root / "proj"
            kit_src = _make_local_kit_source(root, "demo")
            _init_project(project_root, cache)

            with patch("sys.stdin.isatty", return_value=False):
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
            self.assertEqual(out["kit"], "demo")
            self.assertEqual(out["install_mode"], "copy")

            installed_root = project_root / ".bootstrap" / "config" / "kits" / "demo"
            skill_path = installed_root / "SKILL.md"
            constraints_path = installed_root / "constraints.toml"
            template_path = installed_root / "artifacts" / "FEATURE" / "template.md"
            core_toml_path = project_root / ".bootstrap" / "config" / "core.toml"

            self.assertEqual(
                skill_path.read_text(encoding="utf-8"),
                "---\nname: demo\ndescription: Test kit\n---\n# demo\nkit body\n",
            )
            self.assertEqual(
                constraints_path.read_text(encoding="utf-8"),
                "[naming]\npattern = 'demo-*'\n",
            )
            self.assertEqual(
                template_path.read_text(encoding="utf-8"),
                "# demo feature\n",
            )
            core_toml = core_toml_path.read_text(encoding="utf-8")
            self.assertIn('[kits.demo]', core_toml)
            self.assertIn('path = "config/kits/demo"', core_toml)

    def test_kit_install_public_cli_ignored_tracking_updates_gitignore_narrowly(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            cache = _make_cache(root)
            project_root = root / "proj"
            kit_src = _make_local_kit_source(root, "ignoredkit")
            _init_project(project_root, cache)

            with patch("studio.commands.kit._prompt_git_tracking_for_installed_kit", return_value="ignored"), patch(
                "sys.stdin.isatty",
                return_value=True,
            ):
                rc, out, stderr = _run_main_json(
                    [
                        "kit",
                        "install",
                        "--path",
                        str(kit_src),
                    ],
                    cwd=project_root,
                )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".bootstrap/config/kits/ignoredkit/", gitignore_text)
            self.assertNotIn(".bootstrap/config/kits/\n", gitignore_text)
            self.assertEqual(
                (project_root / ".bootstrap" / "config" / "kits" / "ignoredkit" / "SKILL.md").read_text(
                    encoding="utf-8",
                ),
                "---\nname: ignoredkit\ndescription: Test kit\n---\n# ignoredkit\nkit body\n",
            )

    def test_kit_update_public_cli_dry_run_from_local_path_is_read_only(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            cache = _make_cache(root)
            project_root = root / "proj"
            kit_src = _make_local_kit_source(root, "updatekit")
            _init_project(project_root, cache)

            with patch("sys.stdin.isatty", return_value=False):
                install_rc, install_out, install_stderr = _run_main_json(
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

            installed_skill = project_root / ".bootstrap" / "config" / "kits" / "updatekit" / "SKILL.md"
            before = _snapshot_tree(project_root)

            (kit_src / "SKILL.md").write_text(
                "---\nname: updatekit\ndescription: Test kit\n---\n# updatekit\nchanged upstream\n",
                encoding="utf-8",
            )
            (kit_src / "artifacts" / "FEATURE" / "template.md").write_text(
                "# updated feature\n",
                encoding="utf-8",
            )

            rc, out, stderr = _run_main_json(
                [
                    "kit",
                    "update",
                    "--path",
                    str(kit_src),
                    "--dry-run",
                    "--no-interactive",
                ],
                cwd=project_root,
            )

            self.assertEqual(rc, 0, stderr)
            self.assertEqual(out["status"], "PASS")
            self.assertEqual(out["kits_updated"], 0)
            self.assertEqual(out["results"][0]["kit"], "updatekit")
            self.assertEqual(out["results"][0]["action"], "dry_run")
            self.assertEqual(
                installed_skill.read_text(encoding="utf-8"),
                "---\nname: updatekit\ndescription: Test kit\n---\n# updatekit\nkit body\n",
            )
            self.assertEqual(_snapshot_tree(project_root), before)

    def test_generate_agents_public_cli_ignores_manifest_kit_public_skill_and_agent_proxy(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            cache = _make_cache(root)
            project_root = root / "proj"
            kit_src = _make_public_manifest_kit_source(root, "pubkit")
            _init_project(project_root, cache, agent_tracking="ignored")

            with patch("sys.stdin.isatty", return_value=False):
                install_rc, install_out, install_stderr = _run_main_json(
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

            rc, out, stderr = _run_main_json(
                [
                    "generate-agents",
                    "--agent",
                    "cursor",
                ],
                cwd=project_root,
            )

            self.assertEqual(rc, 0, stderr)
            cursor_result = out.get("results", {}).get("cursor", out)
            self.assertEqual(cursor_result.get("status"), "PASS")

            skill_file = project_root / ".agents" / "skills" / "cf-pubkit-helper" / "SKILL.md"
            agent_file = project_root / ".cursor" / "agents" / "cf-pubkit-reviewer.mdc"
            gitignore_lines = (project_root / ".gitignore").read_text(encoding="utf-8").splitlines()

            self.assertTrue(skill_file.is_file())
            self.assertTrue(agent_file.is_file())

            self.assertIn(".agents/skills/cf-pubkit-helper/SKILL.md", gitignore_lines)
            self.assertIn(".cursor/agents/cf-pubkit-reviewer.mdc", gitignore_lines)
            self.assertNotIn(".agents/skills/cf-pubkit-helper/", gitignore_lines)
            self.assertNotIn(".cursor/agents/", gitignore_lines)

            self.assertIn("name: cf-pubkit-helper", skill_file.read_text(encoding="utf-8"))
            agent_text = agent_file.read_text(encoding="utf-8")
            self.assertIn("cf-pubkit-reviewer", agent_text)
            self.assertIn("Generated by cf agents -- do not edit", agent_text)
            self.assertIn("# Reviewer", agent_text)

    def test_kit_migrate_public_cli_is_deprecated_and_non_mutating(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            before = _snapshot_tree(root)

            rc, stdout, stderr = _run_main(["kit", "migrate"], cwd=root)

            self.assertEqual(rc, 1)
            self.assertIn("WARNING: 'cfs kit migrate' is deprecated.", stdout)
            self.assertIn("Use 'cfs kit update <path>' instead.", stdout)
            self.assertEqual(stderr, "")
            self.assertEqual(_snapshot_tree(root), before)
