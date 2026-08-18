"""Public CLI e2e coverage for exact `agents` command."""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.cli import main


def _run_main(argv: list[str], *, cwd: Path) -> tuple[int, str, str]:
    from studio.utils.ui import is_json_mode, set_json_mode

    stdout = io.StringIO()
    stderr = io.StringIO()
    old_cwd = Path.cwd()
    saved_json_mode = is_json_mode()
    try:
        set_json_mode(False)
        os.chdir(cwd)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(argv)
        return exit_code, stdout.getvalue(), stderr.getvalue()
    finally:
        set_json_mode(saved_json_mode)
        os.chdir(old_cwd)


def _snapshot_tree(root: Path) -> dict[str, tuple[str, bytes | None]]:
    snapshot: dict[str, tuple[str, bytes | None]] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            snapshot[rel] = ("dir", None)
        elif path.is_file():
            snapshot[rel] = ("file", path.read_bytes())
    return snapshot


def _bootstrap_generator_project(root: Path) -> None:
    (root / ".git").mkdir(parents=True, exist_ok=True)
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


def _bootstrap_opencode_registry(root: Path) -> None:
    """Add the current cf-namespaced registry needed by the OpenCode path."""
    source = root / "skills" / "studio"
    agents = source / "agents"
    agents.mkdir(parents=True)
    (source / "agents.toml").write_text(
        """[agents.cf-codegen]
description = "Constructor Studio code generator"
prompt_file = "agents/cf-codegen.md"
mode = "readwrite"

[agents.cf-pr-review]
description = "Constructor Studio PR reviewer"
prompt_file = "agents/cf-pr-review.md"
mode = "readonly"
""",
        encoding="utf-8",
    )
    (agents / "cf-codegen.md").write_text("Code generation instructions.\n", encoding="utf-8")
    (agents / "cf-pr-review.md").write_text("PR review instructions.\n", encoding="utf-8")


class TestCLIAgentsE2E(unittest.TestCase):
    def test_generate_agents_opencode_collision_is_nonfatal_and_generates_remaining_owned_outputs(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_generator_project(root)
            _bootstrap_opencode_registry(root)
            (root / "config" / "core.toml").write_text(
                '[install]\nagent_tracking = "ignored"\n',
                encoding="utf-8",
            )
            collision = root / ".opencode" / "agents" / "cf-codegen.md"
            collision.parent.mkdir(parents=True)
            collision_content = "# User-owned OpenCode agent\n"
            collision.write_text(collision_content, encoding="utf-8")

            exit_code, stdout, _stderr = _run_main(
                [
                    "--json",
                    "generate-agents",
                    "--opencode",
                    "--yes",
                    "--root",
                    str(root),
                    "--cf-constructor-root",
                    str(root),
                ],
                cwd=root,
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "PARTIAL")
            self.assertEqual(payload["results"]["opencode"]["status"], "PARTIAL")
            self.assertEqual(collision.read_text(encoding="utf-8"), collision_content)
            self.assertTrue((root / ".opencode" / ".cf-studio-installed").is_file())
            self.assertTrue((root / ".opencode" / "agents" / "cf-pr-review.md").is_file())
            record_path = root / ".opencode" / ".cf-studio-unowned-outputs.json"
            self.assertEqual(
                json.loads(record_path.read_text(encoding="utf-8")),
                {
                    "schema": "cf-studio-opencode-unowned-outputs-v1",
                    "paths": [".opencode/agents/cf-codegen.md"],
                },
            )
            self.assertIn(
                ".opencode/.cf-studio-unowned-outputs.json",
                (root / ".gitignore").read_text(encoding="utf-8"),
            )

    def test_agents_specific_windsurf_flag_is_read_only(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_generator_project(root)
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "agents", "--agent", "windsurf", "--root", str(root), "--cf-constructor-root", str(root)],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["agents"], ["windsurf"])
            self.assertIn("windsurf", payload["results"])
            self.assertFalse((root / ".codex").exists())
            self.assertFalse((root / ".agents").exists())

    def test_agents_default_targets_established_five_agents_without_writing(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_generator_project(root)
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "agents", "--root", str(root), "--cf-constructor-root", str(root)],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["agents"], ["windsurf", "cursor", "claude", "copilot", "openai"])
            self.assertNotIn("opencode", payload["agents"])
            self.assertEqual(sorted(payload["results"].keys()), ["claude", "copilot", "cursor", "openai", "windsurf"])

    def test_agents_explicit_opencode_selection_is_read_only(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_generator_project(root)
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "agents", "--agent", "opencode", "--root", str(root), "--cf-constructor-root", str(root)],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["agents"], ["opencode"])
            state = payload["results"]["opencode"]
            self.assertTrue(state["selected"])
            self.assertFalse(state["sentinel"])
            self.assertEqual(state["generated"], [])
            self.assertFalse(state["partial"])
            self.assertEqual(state["collision"], [])

    def test_agents_opencode_shortcut_is_read_only(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_generator_project(root)
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "agents", "--opencode", "--root", str(root), "--cf-constructor-root", str(root)],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["agents"], ["opencode"])
            self.assertTrue(payload["results"]["opencode"]["selected"])

    def test_agents_opencode_scans_current_generated_and_collision_state_read_only(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_generator_project(root)
            marker = root / ".opencode" / ".cf-studio-installed"
            marker.parent.mkdir(parents=True)
            marker.write_text("Constructor Studio marker\n", encoding="utf-8")
            agents_dir = root / ".opencode" / "agents"
            agents_dir.mkdir()
            generated = agents_dir / "cf-codegen.md"
            generated.write_text(
                "<!-- Generated by cf agents -- do not edit -->\n",
                encoding="utf-8",
            )
            collision = agents_dir / "cf-user.md"
            collision.write_text("# User-owned OpenCode agent\n", encoding="utf-8")
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "agents", "--opencode", "--root", str(root), "--cf-constructor-root", str(root)],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            state = json.loads(stdout)["results"]["opencode"]
            self.assertTrue(state["selected"])
            self.assertTrue(state["sentinel"])
            self.assertEqual(state["generated"], [".opencode/agents/cf-codegen.md"])
            self.assertTrue(state["partial"])
            self.assertEqual(
                state["collision"],
                [{"path": ".opencode/agents/cf-user.md", "reason": "unowned_or_missing_marker"}],
            )

    def test_agents_openai_flag_is_read_only(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_generator_project(root)
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "agents", "--openai", "--root", str(root), "--cf-constructor-root", str(root)],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["agents"], ["openai"])
            self.assertIn("openai", payload["results"])
            self.assertFalse((root / ".codex").exists())
            self.assertFalse((root / ".agents").exists())

    def test_agents_invalid_config_errors_without_writing(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_generator_project(root)
            (root / "broken.json").write_text("{broken", encoding="utf-8")
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                [
                    "--json",
                    "agents",
                    "--openai",
                    "--root",
                    str(root),
                    "--cf-constructor-root",
                    str(root),
                    "--config",
                    str(root / "broken.json"),
                ],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertIn("failed to load JSON file", stderr)
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "CONFIG_ERROR")
            self.assertIn("Cannot read or parse config file", payload["message"])

    def test_agents_cf_studio_root_override_is_reflected_in_output(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            external = Path(td) / "external-studio"
            _bootstrap_generator_project(root)
            (external / ".core").mkdir(parents=True, exist_ok=True)
            (external / ".gen").mkdir(parents=True, exist_ok=True)
            (external / "config").mkdir(parents=True, exist_ok=True)
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                [
                    "--json",
                    "agents",
                    "--agent",
                    "openai",
                    "--root",
                    str(root),
                    "--cf-studio-root",
                    str(external),
                ],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["studio_root"], external.resolve().as_posix())

    def test_agents_missing_root_errors_without_writing(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir(parents=True, exist_ok=True)
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "agents", "--openai", "--root", str(root / "missing"), "--cf-constructor-root", str(root)],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "NOT_FOUND")
            self.assertIn("No project root found", payload["message"])


if __name__ == "__main__":
    unittest.main()
