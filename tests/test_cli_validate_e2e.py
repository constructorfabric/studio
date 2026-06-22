"""Public CLI e2e coverage for exact `validate` command."""

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


def _changed_paths(
    before: dict[str, tuple[str, bytes | None]],
    after: dict[str, tuple[str, bytes | None]],
) -> set[str]:
    return {path for path in set(before) | set(after) if before.get(path) != after.get(path)}


def _bootstrap_empty_validate_project(root: Path) -> None:
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / "AGENTS.md").write_text(
        '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "adapter"\n```\n<!-- /@cf:root-agents -->\n',
        encoding="utf-8",
    )
    config_dir = root / "adapter" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "AGENTS.md").write_text("# Test adapter\n", encoding="utf-8")
    toml_utils.dump(
        {
            "version": "1.0",
            "project_root": "..",
            "kits": {},
            "systems": [],
        },
        config_dir / "artifacts.toml",
    )


def _bootstrap_workspace_validate_source(root: Path, *, source_id: str) -> None:
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / "AGENTS.md").write_text(
        '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = ".bootstrap"\n```\n<!-- /@cf:root-agents -->\n',
        encoding="utf-8",
    )
    cfg = root / ".bootstrap" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "AGENTS.md").write_text("# Adapter\n", encoding="utf-8")
    for kind in ("PRD", "DESIGN"):
        template_dir = root / "kits" / "test" / "artifacts" / kind
        template_dir.mkdir(parents=True, exist_ok=True)
        (template_dir / "template.md").write_text(
            "---\n"
            "cypilot-template:\n"
            "  version:\n"
            "    major: 1\n"
            "    minor: 0\n"
            f"  kind: {kind}\n"
            "---\n"
            "text\n",
            encoding="utf-8",
        )
    toml_utils.dump(
        {
            "version": "1.0",
            "project_root": "..",
            "kits": {"test": {"format": "CFS", "path": "kits/test"}},
            "systems": [
                {
                    "name": "Test",
                    "slug": "test",
                    "kit": "test",
                    "artifacts": [
                        {"path": "architecture/PRD.md", "kind": "PRD"},
                        {"path": "architecture/DESIGN.md", "kind": "DESIGN"},
                    ],
                },
            ],
        },
        cfg / "artifacts.toml",
    )
    architecture = root / "architecture"
    architecture.mkdir(parents=True, exist_ok=True)
    (architecture / "PRD.md").write_text(f"**ID**: `{source_id}`\ncontent\n", encoding="utf-8")
    (architecture / "DESIGN.md").write_text(f"ref `{source_id}`\n", encoding="utf-8")


def _bootstrap_validate_traceability_project(
    root: Path,
    *,
    prd_body: str,
    design_body: str,
) -> tuple[Path, Path]:
    _bootstrap_empty_validate_project(root)
    for kind in ("PRD", "DESIGN"):
        template_dir = root / "kits" / "test" / "artifacts" / kind
        template_dir.mkdir(parents=True, exist_ok=True)
        (template_dir / "template.md").write_text(
            "---\n"
            "cypilot-template:\n"
            "  version:\n"
            "    major: 1\n"
            "    minor: 0\n"
            f"  kind: {kind}\n"
            "---\n"
            "text\n",
            encoding="utf-8",
        )
    toml_utils.dump(
        {
            "version": "1.0",
            "project_root": "..",
            "kits": {"test": {"format": "CFS", "path": "kits/test"}},
            "systems": [
                {
                    "name": "Test",
                    "slug": "test",
                    "kit": "test",
                    "artifacts": [
                        {"path": "architecture/PRD.md", "kind": "PRD"},
                        {"path": "architecture/DESIGN.md", "kind": "DESIGN"},
                    ],
                },
            ],
        },
        root / "adapter" / "config" / "artifacts.toml",
    )
    architecture = root / "architecture"
    architecture.mkdir(parents=True, exist_ok=True)
    prd = architecture / "PRD.md"
    design = architecture / "DESIGN.md"
    prd.write_text(prd_body, encoding="utf-8")
    design.write_text(design_body, encoding="utf-8")
    return prd, design


class TestCLIValidateE2E(unittest.TestCase):
    def test_validate_uninitialized_project_errors_without_writing(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(["--json", "validate"], cwd=root)
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("Constructor Studio not initialized", payload["message"])

    def test_validate_no_artifacts_reports_pass_and_only_bootstraps_runtime_files(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_empty_validate_project(root)
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(["--json", "validate"], cwd=root)
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["artifacts_validated"], 0)
            self.assertEqual(payload["error_count"], 0)
            self.assertEqual(payload["warning_count"], 0)
            self.assertEqual(payload["message"], "No artifacts found in registry")
            self.assertFalse((root / ".gitignore").exists())

    def test_validate_artifact_not_in_registry_returns_error_without_extra_writes(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_empty_validate_project(root)
            artifact = root / "architecture" / "PRD.md"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("# PRD\n", encoding="utf-8")
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "validate", "--artifact", "architecture/PRD.md"],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("Artifact not in registry", payload["message"])
            self.assertFalse((root / ".gitignore").exists())

    def test_validate_cross_artifact_reference_failure_is_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            prd, _design = _bootstrap_validate_traceability_project(
                root,
                prd_body="**ID**: `cpt-test-aa`\ncontent\n",
                design_body="# Design\n(no refs)\n",
            )
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "validate", "--artifact", str(prd), "--skip-code", "--verbose"],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["artifacts_validated"], 1)
            self.assertEqual(payload["error_count"], 1)
            self.assertEqual(payload["warnings"], [])
            self.assertEqual(payload["errors"][0]["code"], "id-not-referenced")
            self.assertEqual(payload["errors"][0]["id"], "cpt-test-aa")
            self.assertEqual(payload["errors"][0]["other_kinds"], ["DESIGN"])

    def test_validate_cross_artifact_reference_pass_is_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            prd, _design = _bootstrap_validate_traceability_project(
                root,
                prd_body="**ID**: `cpt-test-aa`\ncontent\n",
                design_body="ref `cpt-test-aa`\n",
            )
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "validate", "--artifact", str(prd), "--skip-code", "--verbose"],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["artifacts_validated"], 1)
            self.assertEqual(payload["error_count"], 0)
            self.assertEqual(payload["warning_count"], 0)
            self.assertEqual(payload["errors"], [])
            self.assertEqual(payload["warnings"], [])

    def test_validate_output_writes_report_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            prd, _design = _bootstrap_validate_traceability_project(
                root,
                prd_body="**ID**: `cpt-test-aa`\ncontent\n",
                design_body="ref `cpt-test-aa`\n",
            )
            report_path = root / "validate-report.json"
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                [
                    "--json",
                    "validate",
                    "--artifact",
                    str(prd),
                    "--skip-code",
                    "--output",
                    str(report_path),
                ],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout, "")
            self.assertEqual(stderr, "")
            self.assertEqual(_changed_paths(before, after), {"validate-report.json"})
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["artifacts_validated"], 1)
            self.assertEqual(payload["error_count"], 0)
            self.assertEqual(payload["warning_count"], 0)
            self.assertIn("next_step", payload)

    def test_validate_source_missing_errors_without_writes(self):
        with TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir) / "workspace-root"
            workspace_root.mkdir(parents=True, exist_ok=True)
            (workspace_root / ".git").mkdir()
            _bootstrap_workspace_validate_source(workspace_root / "docs-repo", source_id="cpt-docs-item-home")

            exit_code, stdout, stderr = _run_main(["--json", "workspace-init"], cwd=workspace_root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")

            before = _snapshot_tree(workspace_root)
            exit_code, stdout, stderr = _run_main(
                ["--json", "validate", "--source", "missing-source", "--skip-code"],
                cwd=workspace_root,
            )
            after = _snapshot_tree(workspace_root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("Source 'missing-source' not found in workspace", payload["message"])

    def test_validate_workspace_artifact_source_mismatch_errors_without_writes(self):
        with TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir) / "workspace-root"
            workspace_root.mkdir(parents=True, exist_ok=True)
            (workspace_root / ".git").mkdir()

            docs_repo = workspace_root / "docs-repo"
            backend_repo = workspace_root / "backend-repo"
            _bootstrap_workspace_validate_source(docs_repo, source_id="cpt-docs-item-home")
            _bootstrap_workspace_validate_source(backend_repo, source_id="cpt-backend-item-api")

            exit_code, stdout, stderr = _run_main(["--json", "workspace-init"], cwd=workspace_root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")

            before = _snapshot_tree(workspace_root)
            exit_code, stdout, stderr = _run_main(
                [
                    "--json",
                    "validate",
                    "--source",
                    "docs-repo",
                    "--artifact",
                    str(backend_repo / "architecture" / "PRD.md"),
                    "--skip-code",
                ],
                cwd=workspace_root,
            )
            after = _snapshot_tree(workspace_root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("belongs to source 'backend-repo'", payload["message"])
            self.assertIn("not 'docs-repo'", payload["message"])

    def test_validate_missing_artifact_path_errors_without_writes(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_empty_validate_project(root)
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "validate", "--artifact", "architecture/missing.md"],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("Artifact not found:", payload["message"])
            self.assertIn("architecture/missing.md", payload["message"])

    def test_validate_local_only_skips_workspace_expansion_branches(self):
        with TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir) / "workspace-root"
            workspace_root.mkdir(parents=True, exist_ok=True)
            (workspace_root / ".git").mkdir()

            docs_repo = workspace_root / "docs-repo"
            backend_repo = workspace_root / "backend-repo"
            _bootstrap_workspace_validate_source(docs_repo, source_id="cpt-docs-item-home")
            _bootstrap_workspace_validate_source(backend_repo, source_id="cpt-backend-item-api")

            exit_code, stdout, stderr = _run_main(["--json", "workspace-init"], cwd=workspace_root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")

            before = _snapshot_tree(workspace_root)
            with patch(
                "studio.utils.context.WorkspaceContext.get_all_artifact_ids",
                side_effect=AssertionError("workspace ID expansion must be skipped under --local-only"),
            ), patch(
                "studio.commands.validate._collect_cross_repo_artifacts",
                side_effect=AssertionError("cross-repo artifact expansion must be skipped under --local-only"),
            ):
                exit_code, stdout, stderr = _run_main(
                    [
                        "--json",
                        "validate",
                        "--source",
                        "backend-repo",
                        "--artifact",
                        str(backend_repo / "architecture" / "PRD.md"),
                        "--skip-code",
                        "--local-only",
                        "--verbose",
                    ],
                    cwd=workspace_root,
                )
            after = _snapshot_tree(workspace_root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["artifacts_validated"], 1)
            self.assertEqual(payload["error_count"], 0)

    def test_validate_self_check_failure_is_surfaced_without_writes(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            prd, _design = _bootstrap_validate_traceability_project(
                root,
                prd_body="**ID**: `cpt-test-aa`\ncontent\n",
                design_body="ref `cpt-test-aa`\n",
            )
            before = _snapshot_tree(root)

            with patch(
                "studio.commands.validate_kits.run_validate_kits",
                return_value=(2, {"status": "FAIL", "error_count": 1, "errors": [{"code": "kit-bad"}]}),
            ):
                exit_code, stdout, stderr = _run_main(
                    ["--json", "validate", "--artifact", str(prd), "--skip-code"],
                    cwd=root,
                )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 2)
            self.assertEqual(after, before)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["message"], "validate-kits failed (kit structure or templates are inconsistent)")
            self.assertEqual(payload["validate_kits"]["status"], "FAIL")
            self.assertEqual(payload["validate_kits"]["error_count"], 1)

    def test_validate_workspace_config_errors_are_surfaced_in_report(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            prd, _design = _bootstrap_validate_traceability_project(
                root,
                prd_body="**ID**: `cpt-test-aa`\ncontent\n",
                design_body="ref `cpt-test-aa`\n",
            )
            (root / ".cf-workspace.toml").write_text(
                'version = "1.0"\n'
                "\n"
                "[sources.local]\n"
                'path = "."\n'
                'role = "full"\n'
                "\n"
                "[validation]\n"
                'allowed_content_languages = ["xx_fake"]\n',
                encoding="utf-8",
            )
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "validate", "--artifact", str(prd), "--skip-code", "--verbose"],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 2)
            self.assertEqual(after, before)
            self.assertIn("Workspace config error:", stderr)
            self.assertIn("xx_fake", stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["artifact_count"], 1)
            self.assertEqual(payload["error_count"], 1)
            self.assertEqual(payload["warning_count"], 0)
            self.assertEqual(payload["errors"][0]["code"], "file-load-error")
            self.assertIn("Workspace config error", payload["errors"][0]["message"])
            self.assertIn("xx_fake", payload["errors"][0]["message"])

    def test_validate_source_works_from_workspace_root_without_local_adapter(self):
        with TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir) / "workspace-root"
            workspace_root.mkdir(parents=True, exist_ok=True)
            (workspace_root / ".git").mkdir()

            docs_repo = workspace_root / "docs-repo"
            backend_repo = workspace_root / "backend-repo"
            _bootstrap_workspace_validate_source(docs_repo, source_id="cpt-docs-item-home")
            _bootstrap_workspace_validate_source(backend_repo, source_id="cpt-backend-item-api")

            exit_code, stdout, stderr = _run_main(["--json", "workspace-init"], cwd=workspace_root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")

            before = _snapshot_tree(workspace_root)
            exit_code, stdout, stderr = _run_main(
                ["--json", "validate", "--source", "backend-repo", "--artifact", str(backend_repo / "architecture" / "PRD.md"), "--skip-code", "--verbose"],
                cwd=workspace_root,
            )
            after = _snapshot_tree(workspace_root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["artifacts_validated"], 1)
            self.assertEqual(payload["error_count"], 0)
            self.assertEqual(payload["warning_count"], 0)


if __name__ == "__main__":
    unittest.main()
