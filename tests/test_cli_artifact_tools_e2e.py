"""Public CLI end-to-end coverage for artifact utility commands."""

from __future__ import annotations

import io
import json
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


VALID_PDSL = """UNIT Demo

PURPOSE:
  Validate a small block.

DO:
  - RUN Do something deterministic

RULES:
  - ALWAYS keep output stable
"""


def _run_main(argv: list[str], *, cwd: Path, stdin: str = "") -> tuple[int, str, str]:
    from studio.utils.ui import is_json_mode, set_json_mode

    stdout = io.StringIO()
    stderr = io.StringIO()
    old_cwd = Path.cwd()
    saved_json_mode = is_json_mode()
    try:
        set_json_mode(False)
        os.chdir(cwd)
        with patch.object(sys, "stdin", io.StringIO(stdin)):
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


def _changed_paths(
    before: dict[str, tuple[str, bytes | None]],
    after: dict[str, tuple[str, bytes | None]],
) -> set[str]:
    return {path for path in set(before) | set(after) if before.get(path) != after.get(path)}


def _write_root_agents(root: Path, adapter_rel: str) -> None:
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


def _bootstrap_content_project(root: Path, *, project_root_rel: str = "..") -> None:
    (root / ".git").mkdir(parents=True, exist_ok=True)
    _write_root_agents(root, "adapter")

    adapter = root / "adapter"
    config_dir = adapter / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "AGENTS.md").write_text("# Test adapter\n", encoding="utf-8")

    toml_utils.dump(
        {
            "version": "1.0",
            "project_root": project_root_rel,
            "kits": {"test": {"format": "CFS", "path": "kits/test"}},
        },
        config_dir / "core.toml",
    )
    toml_utils.dump(
        {
            "version": "1.0",
            "project_root": project_root_rel,
            "kits": {"test": {"format": "CFS", "path": "kits/test"}},
            "systems": [
                {
                    "name": "Web",
                    "slug": "web",
                    "kit": "test",
                    "artifacts": [
                        {"path": "architecture/FEATURE.md", "kind": "FEATURE", "traceability": "FULL"},
                    ],
                    "codebase": [{"path": "src/web", "extensions": [".py"]}],
                },
            ],
        },
        config_dir / "artifacts.toml",
    )
    toml_utils.dump(
        {
            "artifacts": {
                "FEATURE": {"identifiers": {"item": {"template": "cpt-{system}-item-{slug}"}}},
            },
        },
        root / "kits" / "test" / "constraints.toml",
    )

    architecture = root / "architecture"
    architecture.mkdir(parents=True, exist_ok=True)
    (architecture / "FEATURE.md").write_text(
        "# Feature\n\n"
        "### cpt-web-item-scope\n"
        "alpha\n"
        "beta\n",
        encoding="utf-8",
    )

    code_file = root / "src" / "web" / "handlers.py"
    code_file.parent.mkdir(parents=True, exist_ok=True)
    code_file.write_text(
        "# @cpt-begin:cpt-web-flow-login:p1:inst-validate\n"
        "def validate():\n"
        "    return True\n"
        "# @cpt-end:cpt-web-flow-login:p1:inst-validate\n"
        "# @cpt-flow:cpt-web-flow-scope:p2\n",
        encoding="utf-8",
    )


class TestCLIArtifactToolsE2E(unittest.TestCase):
    def test_get_content_code_mode_paths_are_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_content_project(root)
            baseline = _snapshot_tree(root)
            code_path = root / "src" / "web" / "handlers.py"

            exit_code, stdout, stderr = _run_main(
                ["--json", "get-content", "--code", str(code_path), "--id", "cpt-web-flow-login"],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FOUND")
            self.assertEqual(payload["id"], "cpt-web-flow-login")
            self.assertIsNone(payload["inst"])
            self.assertIn("def validate():", payload["text"])

            exit_code, stdout, stderr = _run_main(
                [
                    "--json",
                    "get-content",
                    "--code",
                    str(code_path),
                    "--id",
                    "cpt-web-flow-login",
                    "--inst",
                    "validate",
                ],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FOUND")
            self.assertEqual(payload["inst"], "validate")
            self.assertIn("def validate():", payload["text"])

    def test_get_content_code_mode_missing_inst_falls_back_to_id_without_writes(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_content_project(root)
            baseline = _snapshot_tree(root)
            code_path = root / "src" / "web" / "handlers.py"

            exit_code, stdout, stderr = _run_main(
                [
                    "--json",
                    "get-content",
                    "--code",
                    str(code_path),
                    "--id",
                    "cpt-web-flow-login",
                    "--inst",
                    "missing-inst",
                ],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FOUND")
            self.assertEqual(payload["id"], "cpt-web-flow-login")
            self.assertEqual(payload["inst"], "missing-inst")
            self.assertIn("def validate():", payload["text"])

    def test_get_content_code_mode_missing_inst_and_id_returns_not_found_without_writes(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_content_project(root)
            baseline = _snapshot_tree(root)
            code_path = root / "src" / "web" / "handlers.py"

            exit_code, stdout, stderr = _run_main(
                [
                    "--json",
                    "get-content",
                    "--code",
                    str(code_path),
                    "--id",
                    "cpt-web-flow-missing",
                    "--inst",
                    "missing-inst",
                ],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(
                payload,
                {
                    "status": "NOT_FOUND",
                    "id": "cpt-web-flow-missing",
                    "inst": "missing-inst",
                },
            )

    def test_get_content_code_mode_missing_file_is_non_mutating_error(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_content_project(root)
            baseline = _snapshot_tree(root)
            code_path = root / "src" / "web" / "missing.py"

            exit_code, stdout, stderr = _run_main(
                ["--json", "get-content", "--code", str(code_path), "--id", "cpt-web-flow-login"],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(
                payload,
                {
                    "status": "ERROR",
                    "message": f"Code file not found: {code_path.resolve()}",
                },
            )

    def test_get_content_code_mode_parse_failure_is_non_mutating_error(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_content_project(root)
            code_path = root / "src" / "web" / "broken.py"
            code_path.write_bytes(b"\xff\xfe\x00broken")
            baseline = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "get-content", "--code", str(code_path), "--id", "cpt-web-flow-login"],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("Failed to parse code file:", payload["message"])
            self.assertIn("Failed to read", payload["message"])
            self.assertIn(str(code_path.resolve()), payload["message"])

    def test_get_content_code_mode_missing_id_returns_not_found_without_writes(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_content_project(root)
            baseline = _snapshot_tree(root)
            code_path = root / "src" / "web" / "handlers.py"

            exit_code, stdout, stderr = _run_main(
                ["--json", "get-content", "--code", str(code_path), "--id", "cpt-web-flow-missing"],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(
                payload,
                {
                    "status": "NOT_FOUND",
                    "id": "cpt-web-flow-missing",
                    "inst": None,
                },
            )

    def test_get_content_missing_selector_is_non_mutating_error(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "get-content", "--id", "cpt-web-flow-login"],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertEqual(payload["message"], "Either --artifact or --code must be specified")

    def test_get_content_artifact_not_registered_is_non_mutating_error(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_content_project(root)
            unregistered = root / "architecture" / "UNREGISTERED.md"
            unregistered.write_text("### cpt-web-item-untracked\nbody\n", encoding="utf-8")
            baseline = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "get-content", "--artifact", str(unregistered), "--id", "cpt-web-item-untracked"],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertEqual(payload["message"], "Artifact not registered: architecture/UNREGISTERED.md")

    def test_get_content_artifact_outside_project_root_is_non_mutating_error(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_root = root / "project"
            project_root.mkdir()
            _bootstrap_content_project(project_root, project_root_rel="app")
            outside_artifact = project_root / "architecture" / "FEATURE.md"
            baseline = _snapshot_tree(project_root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "get-content", "--artifact", str(outside_artifact), "--id", "cpt-web-item-scope"],
                cwd=project_root,
            )
            after = _snapshot_tree(project_root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertEqual(payload["message"], f"Artifact not under project root: {outside_artifact.resolve()}")

    def test_toc_write_mutates_only_target_file_and_validates_output(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doc = root / "doc.md"
            doc.write_text("# Title\n\n## Alpha\n\n### Beta\n", encoding="utf-8")
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(["--json", "toc", str(doc)], cwd=root)
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(_changed_paths(before, after), {"doc.md"})

            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["files_processed"], 1)
            self.assertEqual(payload["results"][0]["status"], "UPDATED")
            self.assertEqual(payload["results"][0]["validation"]["status"], "PASS")
            updated = doc.read_text(encoding="utf-8")
            self.assertIn("<!-- toc -->", updated)
            self.assertIn("- [Alpha](#alpha)", updated)
            self.assertIn("<!-- /toc -->", updated)
            self.assertFalse((root / "CLAUDE.md").exists())
            self.assertFalse((root / ".gitignore").exists())

    def test_toc_dry_run_is_read_only_and_reports_would_update(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doc = root / "doc.md"
            doc.write_text("# Title\n\n## Alpha\n\n### Beta\n", encoding="utf-8")
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "toc", "--dry-run", str(doc)],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)

            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["results"][0]["status"], "WOULD_UPDATE")
            self.assertFalse((root / "CLAUDE.md").exists())
            self.assertFalse((root / ".gitignore").exists())

    def test_pdsl_validate_text_json_pass_is_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "pdsl", "validate", "--text", VALID_PDSL],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)

            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "pdsl validate")
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["summary"]["pass_count"], 1)
            self.assertEqual(payload["summary"]["fail_count"], 0)
            self.assertEqual(payload["summary"]["error_count"], 0)
            self.assertEqual(payload["results"][0]["source"], "<text>")
            self.assertEqual(payload["results"][0]["status"], "PASS")

    def test_pdsl_validate_mixed_selectors_is_error_and_non_mutating(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "pdsl", "validate", "--text", VALID_PDSL, "-"],
                cwd=root,
                stdin=VALID_PDSL,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)

            payload = json.loads(stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["summary"]["error_count"], 1)
            self.assertEqual(payload["results"][0]["status"], "ERROR")
            self.assertEqual(payload["results"][0]["errors"][0]["kind"], "INVOCATION_ERROR")

    def test_generate_resources_is_deprecated_and_non_mutating(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(["generate-resources"], cwd=root)
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout, "")
            self.assertEqual(after, before)
            self.assertIn("WARNING: 'generate-resources' is deprecated.", stderr)
            self.assertIn("use 'cfs kit update <path>' instead", stderr.lower())


if __name__ == "__main__":
    unittest.main()
