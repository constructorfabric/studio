"""Human-mode CLI e2e coverage for generate-agents and kit flows."""

from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.cli import main
from studio.utils import toml_utils


class _TTYStringIO(io.StringIO):
    def __init__(self, text: str = "", *, is_tty: bool) -> None:
        super().__init__(text)
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


def _run_main_human(
    argv: list[str],
    *,
    cwd: Path,
    stdin_text: str = "",
    stdin_tty: bool = False,
) -> tuple[int, str, str]:
    from studio.utils.ui import is_json_mode, set_json_mode

    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin = _TTYStringIO(stdin_text, is_tty=stdin_tty)
    old_cwd = Path.cwd()
    saved_json_mode = is_json_mode()
    try:
        set_json_mode(False)
        os.chdir(cwd)
        with patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(stderr):
            rc = main(argv)
        return rc, stdout.getvalue(), stderr.getvalue()
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


def _bootstrap_generate_agents_project(root: Path) -> None:
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / "skills" / "cypilot").mkdir(parents=True, exist_ok=True)
    (root / "skills" / "cypilot" / "SKILL.md").write_text(
        "---\nname: cypilot\ndescription: Cypilot skill for testing\n---\n# Cypilot\n",
        encoding="utf-8",
    )
    (root / "workflows").mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "generate.md").write_text(
        "---\ncypilot: true\ntype: workflow\nname: cypilot-generate\ndescription: Generate artifacts\n---\n# Generate\n",
        encoding="utf-8",
    )
    (root / "workflows" / "analyze.md").write_text(
        "---\ncypilot: true\ntype: workflow\nname: cypilot-analyze\ndescription: Analyze artifacts\n---\n# Analyze\n",
        encoding="utf-8",
    )


def _bootstrap_studio_project(root: Path, adapter_rel: str = "cypilot") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    (root / "AGENTS.md").write_text(
        (
            "<!-- @cf:root-agents -->\n"
            "```toml\n"
            f'cf-studio-path = "{adapter_rel}"\n'
            "```\n"
            "<!-- /@cf:root-agents -->\n"
        ),
        encoding="utf-8",
    )
    adapter = root / adapter_rel
    (adapter / ".core").mkdir(parents=True, exist_ok=True)
    (adapter / ".gen").mkdir(parents=True, exist_ok=True)
    (adapter / "config").mkdir(parents=True, exist_ok=True)
    (adapter / "config" / "AGENTS.md").write_text("# Test adapter\n", encoding="utf-8")
    toml_utils.dump(
        {"version": "1.0", "project_root": "..", "kits": {}},
        adapter / "config" / "core.toml",
    )
    toml_utils.dump(
        {"systems": [{"name": "TestProject", "slug": "test"}]},
        adapter / "config" / "artifacts.toml",
    )
    return adapter


def _make_legacy_layout_kit_source(root: Path, slug: str = "layoutkit") -> Path:
    kit_src = root / slug
    (kit_src / "artifacts" / "FEATURE").mkdir(parents=True, exist_ok=True)
    (kit_src / "artifacts" / "FEATURE" / "template.md").write_text(
        "# Feature template\n",
        encoding="utf-8",
    )
    (kit_src / "workflows").mkdir(parents=True, exist_ok=True)
    (kit_src / "workflows" / "review.md").write_text(
        "---\ntype: workflow\nname: review\ndescription: Review\n---\n# Review\n",
        encoding="utf-8",
    )
    (kit_src / "SKILL.md").write_text(
        f"---\nname: {slug}\ndescription: Legacy kit\n---\n# {slug}\n",
        encoding="utf-8",
    )
    (kit_src / "constraints.toml").write_text(
        "[FEATURE.identifiers.flow]\nrequired = true\n",
        encoding="utf-8",
    )
    toml_utils.dump({"version": 1, "slug": slug}, kit_src / "conf.toml")
    return kit_src


class TestCliHumanModeE2E(unittest.TestCase):
    def test_generate_agents_human_preview_abort_preserves_tree(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_generate_agents_project(root)
            before = _snapshot_tree(root)

            rc, stdout, stderr = _run_main_human(
                [
                    "generate-agents",
                    "--agent",
                    "windsurf",
                    "--root",
                    str(root),
                    "--cf-constructor-root",
                    str(root),
                ],
                cwd=root,
                stdin_text="n\n",
                stdin_tty=True,
            )

            after = _snapshot_tree(root)
            combined = stdout + stderr

            self.assertEqual(rc, 1)
            self.assertEqual(after, before)
            self.assertIn("Generate Agent Integration", combined)
            self.assertIn("Reply with `y` to write these generated files or `n` to abort.", combined)
            self.assertIn("Proceed? [Y/n]", combined)
            self.assertIn("Aborted.", combined)
            self.assertFalse((root / ".agents").exists())

    def test_generate_agents_human_success_prints_real_cli_summary(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_generate_agents_project(root)

            rc, stdout, stderr = _run_main_human(
                [
                    "generate-agents",
                    "--agent",
                    "windsurf",
                    "--root",
                    str(root),
                    "--cf-constructor-root",
                    str(root),
                    "-y",
                ],
                cwd=root,
            )

            combined = stdout + stderr

            self.assertEqual(rc, 0)
            self.assertIn("Constructor Studio Agent Setup", combined)
            self.assertIn("windsurf", combined)
            self.assertIn(".agents/skills/cf/SKILL.md", combined)
            self.assertIn("Agent integration complete!", combined)
            self.assertIn("Your IDE will now:", combined)
            self.assertTrue((root / ".agents" / "skills" / "cf" / "SKILL.md").is_file())

    def test_kit_update_human_partial_summary_after_mixed_decisions(self):
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            _bootstrap_studio_project(root)
            kit_src = Path(td) / "demokit"
            kit_src.mkdir(parents=True, exist_ok=True)
            toml_utils.dump({"version": 1, "slug": "demokit"}, kit_src / "conf.toml")

            with patch("studio.commands.kit.show_kit_whatsnew", return_value=True), patch(
                "studio.commands.kit.update_kit",
                return_value={
                    "version": {"status": "partial"},
                    "gen": {
                        "files_written": 1,
                        "accepted_files": ["SKILL.md"],
                        "unchanged": 2,
                    },
                    "gen_rejected": ["constraints.toml"],
                },
            ), patch("studio.commands.kit.regenerate_gen_aggregates"):
                rc, stdout, stderr = _run_main_human(
                    [
                        "kit",
                        "update",
                        f"path/{kit_src}",
                        "--project-root",
                        str(root),
                    ],
                    cwd=root,
                    stdin_tty=True,
                )

            combined = stdout + stderr

            self.assertEqual(rc, 0)
            self.assertIn("Kit Update", combined)
            self.assertIn("Kits updated", combined)
            self.assertIn("demokit: partial", combined)
            self.assertIn("1 accepted", combined)
            self.assertIn("1 declined", combined)
            self.assertIn("2 unchanged", combined)
            self.assertIn("SKILL.md", combined)
            self.assertIn("constraints.toml (declined)", combined)
            self.assertIn("partial reason for demokit: declined_files, partial_update", combined)
            self.assertIn("Kit update complete.", combined)

    def test_kit_normalize_human_happy_path_writes_manifest(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            kit_src = _make_legacy_layout_kit_source(root)

            rc, stdout, stderr = _run_main_human(
                ["kit", "normalize", str(kit_src), "--from", "layout"],
                cwd=root,
            )

            combined = stdout + stderr
            manifest_path = kit_src / ".cf-studio-kit.toml"

            self.assertEqual(rc, 0)
            self.assertTrue(manifest_path.is_file())
            self.assertIn("Kit Normalize", combined)
            self.assertIn("Canonical manifest written.", combined)
            self.assertIn('manifest_version = "1.0"', manifest_path.read_text(encoding="utf-8"))
            self.assertIn('slug = "layoutkit"', manifest_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
