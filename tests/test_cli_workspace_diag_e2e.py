"""Public CLI e2e coverage for workspace, delegate, and doctor surfaces."""

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


def _changed_paths(before: dict[str, tuple[str, bytes | None]], after: dict[str, tuple[str, bytes | None]]) -> set[str]:
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


def _make_repo(root: Path, *, with_git: bool = True) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if with_git:
        (root / ".git").mkdir(exist_ok=True)


def _make_adapter_repo(root: Path, *, adapter_rel: str = ".bootstrap", role_dir: str = "architecture") -> None:
    _make_repo(root)
    _write_root_agents(root, adapter_rel)
    adapter = root / adapter_rel / "config"
    adapter.mkdir(parents=True, exist_ok=True)
    (adapter / "AGENTS.md").write_text("# Test adapter\n", encoding="utf-8")
    (root / role_dir).mkdir(parents=True, exist_ok=True)


def _write_core_config(root: Path, text: str, *, adapter_rel: str = ".bootstrap") -> Path:
    _write_root_agents(root, adapter_rel)
    config_path = root / adapter_rel / "config" / "core.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(text, encoding="utf-8")
    return config_path


class TestCLIWorkspaceE2E(unittest.TestCase):
    def test_workspace_init_inline_writes_core_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            _make_adapter_repo(root / "docs-repo", role_dir="architecture")
            _write_core_config(root, '[project]\nname = "workspace-root"\n')

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(["--json", "workspace-init", "--inline"], cwd=root)
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(_changed_paths(before, after), {".bootstrap/config/core.toml"})

            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "CREATED")
            self.assertEqual(payload["config_path"], str((root / ".bootstrap" / "config" / "core.toml").resolve()))

            core_data = toml_utils.load(root / ".bootstrap" / "config" / "core.toml")
            self.assertEqual(core_data["project"]["name"], "workspace-root")
            self.assertEqual(core_data["workspace"]["version"], "1.0")
            self.assertEqual(core_data["workspace"]["sources"]["docs-repo"]["path"], "docs-repo")

    def test_workspace_init_output_writes_custom_location_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            _make_adapter_repo(root / "docs-repo", role_dir="architecture")
            custom_dir = root / "generated"
            custom_dir.mkdir(parents=True, exist_ok=True)
            output_path = custom_dir / "custom-workspace.toml"

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(
                ["--json", "workspace-init", "--output", str(output_path)],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(_changed_paths(before, after), {"generated/custom-workspace.toml"})

            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "CREATED")
            self.assertEqual(payload["config_path"], str(output_path.resolve()))
            self.assertIn("Custom output path used", payload["hint"])
            self.assertFalse((root / ".cf-workspace.toml").exists())

    def test_workspace_init_inline_and_output_are_mutually_exclusive(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(
                ["--json", "workspace-init", "--inline", "--output", "custom.toml"],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("mutually exclusive", payload["message"])

    def test_workspace_init_invalid_root_errors_without_writing(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            missing_root = root / "missing"

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(
                ["--json", "workspace-init", "--root", str(missing_root)],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("Scan root directory not found", payload["message"])

    def test_workspace_init_force_overwrites_existing_workspace(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            _make_adapter_repo(root / "docs-repo", role_dir="architecture")
            _make_adapter_repo(root / "shared-lib", role_dir="src")

            workspace_path = root / ".cf-workspace.toml"
            toml_utils.dump(
                {
                    "version": "1.0",
                    "sources": {
                        "stale-source": {
                            "path": "stale-source",
                            "role": "codebase",
                        },
                    },
                },
                workspace_path,
            )
            before = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(["--json", "workspace-init", "--force"], cwd=root)
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(_changed_paths(before, after), {".cf-workspace.toml"})

            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "CREATED")
            workspace_data = toml_utils.load(workspace_path)
            self.assertNotIn("stale-source", workspace_data["sources"])
            self.assertEqual(set(workspace_data["sources"]), {"docs-repo", "shared-lib"})

    def test_workspace_init_max_depth_excludes_deeper_repos(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            _make_adapter_repo(root / "level1-repo", role_dir="architecture")
            nested_parent = root / "group"
            nested_parent.mkdir(parents=True, exist_ok=True)
            _make_adapter_repo(nested_parent / "level2-repo", role_dir="src")

            exit_code, stdout, stderr = _run_main(
                ["--json", "workspace-init", "--dry-run", "--max-depth", "1"],
                cwd=root,
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "DRY_RUN")
            self.assertEqual(payload["sources"], ["level1-repo"])

    def test_workspace_init_dry_run_reports_sources_without_writing(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            _make_adapter_repo(root / "docs-repo", role_dir="architecture")
            _make_adapter_repo(root / "shared-lib", role_dir="src")

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(
                ["--json", "workspace-init", "--dry-run"],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)

            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "DRY_RUN")
            self.assertEqual(payload["message"], "Would generate workspace config")
            self.assertEqual(payload["sources_count"], 2)
            self.assertEqual(set(payload["sources"]), {"docs-repo", "shared-lib"})
            self.assertEqual(payload["workspace"]["sources"]["docs-repo"]["role"], "artifacts")
            self.assertEqual(payload["workspace"]["sources"]["shared-lib"]["role"], "codebase")

    def test_workspace_init_add_info_round_trip_with_bounded_writes(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            _make_adapter_repo(root / "docs-repo", role_dir="architecture")
            workspace_path = root / ".cf-workspace.toml"

            before_init = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(["--json", "workspace-init"], cwd=root)
            after_init = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            init_payload = json.loads(stdout)
            self.assertEqual(init_payload["status"], "CREATED")
            self.assertEqual(init_payload["sources_count"], 1)
            self.assertEqual(init_payload["sources"], ["docs-repo"])
            self.assertEqual(_changed_paths(before_init, after_init), {".cf-workspace.toml"})
            self.assertTrue(workspace_path.is_file())

            workspace_data = toml_utils.load(workspace_path)
            self.assertEqual(workspace_data["version"], "1.0")
            self.assertEqual(workspace_data["sources"]["docs-repo"]["path"], "docs-repo")
            self.assertEqual(workspace_data["sources"]["docs-repo"]["adapter"], ".bootstrap")
            self.assertEqual(workspace_data["sources"]["docs-repo"]["role"], "artifacts")

            _make_adapter_repo(root / "shared-lib", role_dir="src")
            before_add = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(
                [
                    "--json",
                    "workspace-add",
                    "--name",
                    "shared-lib",
                    "--path",
                    "shared-lib",
                    "--role",
                    "codebase",
                    "--adapter",
                    ".bootstrap",
                ],
                cwd=root,
            )
            after_add = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            add_payload = json.loads(stdout)
            self.assertEqual(add_payload["status"], "ADDED")
            self.assertEqual(add_payload["source"]["name"], "shared-lib")
            self.assertEqual(_changed_paths(before_add, after_add), {".cf-workspace.toml"})

            workspace_data = toml_utils.load(workspace_path)
            self.assertEqual(workspace_data["sources"]["shared-lib"]["path"], "shared-lib")
            self.assertEqual(workspace_data["sources"]["shared-lib"]["role"], "codebase")
            self.assertEqual(workspace_data["sources"]["shared-lib"]["adapter"], ".bootstrap")

            before_info = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(["--json", "workspace-info"], cwd=root)
            after_info = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after_info, before_info)

            info_payload = json.loads(stdout)
            self.assertEqual(info_payload["status"], "OK")
            self.assertFalse(info_payload["degraded"])
            self.assertEqual(info_payload["warning_count"], 0)
            self.assertNotIn("warnings", info_payload)
            self.assertEqual(info_payload["sources_count"], 2)
            self.assertFalse(info_payload["is_inline"])
            self.assertFalse(info_payload["context_loaded"])

            sources = {source["name"]: source for source in info_payload["sources"]}
            self.assertTrue(sources["docs-repo"]["reachable"])
            self.assertEqual(sources["docs-repo"]["adapter"], ".bootstrap")
            self.assertTrue(sources["shared-lib"]["reachable"])
            self.assertEqual(sources["shared-lib"]["adapter"], ".bootstrap")

    def test_workspace_add_accepts_unreachable_path_and_persists_source(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            _make_adapter_repo(root / "docs-repo", role_dir="architecture")

            exit_code, stdout, stderr = _run_main(["--json", "workspace-init"], cwd=root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")

            before_add = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(
                [
                    "--json",
                    "workspace-add",
                    "--name",
                    "shared-lib",
                    "--path",
                    "../shared-lib",
                    "--role",
                    "codebase",
                    "--adapter",
                    ".bootstrap",
                ],
                cwd=root,
            )
            after_add = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertNotEqual(after_add, before_add)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ADDED")
            self.assertEqual(payload["source"]["name"], "shared-lib")
            self.assertEqual(payload["source"]["path"], "../shared-lib")
            self.assertEqual(payload["source"]["role"], "codebase")
            self.assertEqual(payload["source"]["adapter"], ".bootstrap")

            ws_payload = toml_utils.load(root / ".cf-workspace.toml")
            self.assertEqual(
                ws_payload["sources"]["shared-lib"],
                {
                    "path": "../shared-lib",
                    "role": "codebase",
                    "adapter": ".bootstrap",
                },
            )

    def test_workspace_add_url_source_to_standalone_config(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            _make_adapter_repo(root / "docs-repo", role_dir="architecture")
            _run_main(["--json", "workspace-init"], cwd=root)

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(
                [
                    "--json",
                    "workspace-add",
                    "--name",
                    "remote-docs",
                    "--url",
                    "https://gitlab.com/acme/docs.git",
                    "--branch",
                    "main",
                    "--role",
                    "artifacts",
                    "--adapter",
                    ".bootstrap",
                ],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(_changed_paths(before, after), {".cf-workspace.toml"})

            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ADDED")
            self.assertEqual(payload["source"]["name"], "remote-docs")
            self.assertEqual(payload["source"]["url"], "https://gitlab.com/acme/docs.git")
            self.assertEqual(payload["source"]["branch"], "main")

            workspace_data = toml_utils.load(root / ".cf-workspace.toml")
            self.assertEqual(workspace_data["sources"]["remote-docs"]["url"], "https://gitlab.com/acme/docs.git")
            self.assertEqual(workspace_data["sources"]["remote-docs"]["branch"], "main")
            self.assertEqual(workspace_data["sources"]["remote-docs"]["adapter"], ".bootstrap")

    def test_workspace_add_duplicate_source_requires_force(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            _make_adapter_repo(root / "docs-repo", role_dir="architecture")
            _make_adapter_repo(root / "shared-lib", role_dir="src")
            _run_main(["--json", "workspace-init"], cwd=root)

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(
                [
                    "--json",
                    "workspace-add",
                    "--name",
                    "docs-repo",
                    "--path",
                    "shared-lib",
                    "--role",
                    "codebase",
                ],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("already exists", payload["message"])
            self.assertIn("--force", payload["message"])

    def test_workspace_add_force_replaces_existing_source(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            _make_adapter_repo(root / "docs-repo", role_dir="architecture")
            _make_adapter_repo(root / "shared-lib", role_dir="src")
            _run_main(["--json", "workspace-init"], cwd=root)

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(
                [
                    "--json",
                    "workspace-add",
                    "--name",
                    "docs-repo",
                    "--path",
                    "shared-lib",
                    "--role",
                    "codebase",
                    "--adapter",
                    ".bootstrap",
                    "--force",
                ],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(_changed_paths(before, after), {".cf-workspace.toml"})
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ADDED")
            self.assertTrue(payload["replaced"])

            workspace_data = toml_utils.load(root / ".cf-workspace.toml")
            self.assertEqual(workspace_data["sources"]["docs-repo"]["path"], "shared-lib")
            self.assertEqual(workspace_data["sources"]["docs-repo"]["role"], "codebase")

    def test_workspace_add_invalid_name_errors_without_writing(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(
                ["--json", "workspace-add", "--name", "bad/name", "--path", "repo"],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("Invalid source name", payload["message"])

    def test_workspace_add_inline_rejects_git_url_source(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            _write_core_config(root, '[project]\nname = "workspace-root"\n')

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(
                [
                    "--json",
                    "workspace-add",
                    "--name",
                    "remote-docs",
                    "--url",
                    "https://gitlab.com/acme/docs.git",
                    "--inline",
                ],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("not supported in inline", payload["message"])

    def test_workspace_info_git_source_not_cloned_reports_warning_without_network(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            workspace_path = root / ".cf-workspace.toml"
            toml_utils.dump(
                {
                    "version": "1.0",
                    "sources": {
                        "remote-docs": {
                            "url": "https://gitlab.com/acme/docs.git",
                            "branch": "main",
                            "role": "artifacts",
                        },
                    },
                },
                workspace_path,
            )

            before = _snapshot_tree(root)
            with patch(
                "studio.utils.git_utils.resolve_git_source",
                return_value=root / ".workspace-sources" / "acme" / "docs",
            ):
                exit_code, stdout, stderr = _run_main(["--json", "workspace-info"], cwd=root)
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "OK")
            self.assertTrue(payload["degraded"])
            self.assertEqual(payload["warning_count"], 1)
            self.assertEqual(
                payload["warnings"],
                ["remote-docs: Source not cloned — run 'workspace-sync' to fetch: https://gitlab.com/acme/docs.git"],
            )
            source = payload["sources"][0]
            self.assertFalse(source["reachable"])
            self.assertIn("Source not cloned", source["warning"])

    def test_workspace_info_invalid_adapter_reports_adapter_found_false(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            source_root = root / "docs-repo"
            _make_adapter_repo(source_root, role_dir="architecture")
            toml_utils.dump(
                {
                    "version": "1.0",
                    "sources": {
                        "docs-repo": {
                            "path": "docs-repo",
                            "role": "artifacts",
                            "adapter": "missing-adapter",
                        },
                    },
                },
                root / ".cf-workspace.toml",
            )

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(["--json", "workspace-info"], cwd=root)
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "OK")
            self.assertTrue(payload["degraded"])
            self.assertEqual(payload["warning_count"], 1)
            source = payload["sources"][0]
            self.assertTrue(source["reachable"])
            self.assertFalse(source["adapter_found"])
            self.assertEqual(source["warning"], "Configured adapter not found: missing-adapter")
            self.assertEqual(
                payload["warnings"],
                ["docs-repo: Configured adapter not found: missing-adapter"],
            )

    def test_workspace_info_config_warning_is_exposed(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            _write_core_config(root, '[project]\nname = "workspace-root"\n')
            _make_adapter_repo(root / "docs-repo", role_dir="architecture")

            before = _snapshot_tree(root)
            with patch("studio.utils.workspace.find_workspace_config") as mock_find:
                from studio.utils.workspace import WorkspaceConfig, SourceEntry

                ws_cfg = WorkspaceConfig(
                    sources={
                        "broken-source": SourceEntry(name="broken-source", path="docs-repo", role="artifacts"),
                    },
                    workspace_file=root / ".cf-workspace.toml",
                )
                mock_find.return_value = (ws_cfg, None)
                with patch.object(
                    WorkspaceConfig,
                    "validate",
                    return_value=["synthetic warning from test"],
                ):
                    exit_code, stdout, stderr = _run_main(["--json", "workspace-info"], cwd=root)
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "OK")
            self.assertTrue(payload["degraded"])
            self.assertEqual(payload["warning_count"], 1)
            self.assertEqual(payload["config_warnings"], ["synthetic warning from test"])
            self.assertEqual(payload["warnings"], ["config: synthetic warning from test"])

    def test_workspace_info_no_workspace_error_is_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(["--json", "workspace-info"], cwd=root)
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertEqual(payload["message"], "No workspace configuration found")
            self.assertIn("workspace-init", payload["hint"])

    def test_workspace_sync_dry_run_is_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            toml_utils.dump(
                {
                    "version": "1.0",
                    "sources": {
                        "remote-docs": {
                            "url": "https://gitlab.com/acme/docs.git",
                            "branch": "main",
                            "role": "artifacts",
                        },
                    },
                },
                root / ".cf-workspace.toml",
            )

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(
                ["--json", "workspace-sync", "--dry-run"],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)

            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "DRY_RUN")
            self.assertEqual(payload["message"], "Would sync the following Git URL sources")
            self.assertEqual(payload["sources"], [{"name": "remote-docs", "url": "https://gitlab.com/acme/docs.git", "branch": "main"}])

    def test_workspace_sync_non_dry_run_reports_mixed_results_without_local_writes(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            toml_utils.dump(
                {
                    "version": "1.0",
                    "sources": {
                        "remote-docs": {
                            "url": "https://gitlab.com/acme/docs.git",
                            "branch": "main",
                            "role": "artifacts",
                        },
                        "remote-code": {
                            "url": "https://gitlab.com/acme/code.git",
                            "branch": "develop",
                            "role": "codebase",
                        },
                    },
                },
                root / ".cf-workspace.toml",
            )

            before = _snapshot_tree(root)
            with patch(
                "studio.commands.workspace_sync._sync_sources",
                return_value=(
                    [
                        {"name": "remote-docs", "status": "synced"},
                        {"name": "remote-code", "status": "failed", "error": "dirty worktree"},
                    ],
                    1,
                    1,
                ),
            ) as mock_sync:
                exit_code, stdout, stderr = _run_main(["--json", "workspace-sync"], cwd=root)
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            self.assertEqual(set(mock_sync.call_args.args[0].keys()), {"remote-docs", "remote-code"})
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["synced"], 1)
            self.assertEqual(payload["failed"], 1)
            self.assertEqual(payload["results"][0]["status"], "synced")
            self.assertEqual(payload["results"][1]["status"], "failed")
            self.assertEqual(payload["results"][1]["error"], "dirty worktree")

    def test_workspace_sync_source_not_found_errors_cleanly(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            toml_utils.dump(
                {
                    "version": "1.0",
                    "sources": {
                        "remote-docs": {
                            "url": "https://gitlab.com/acme/docs.git",
                            "branch": "main",
                        },
                    },
                },
                root / ".cf-workspace.toml",
            )

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(
                ["--json", "workspace-sync", "--source", "missing-source"],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertEqual(payload["available"], ["remote-docs"])

    def test_workspace_sync_no_git_sources_returns_ok_and_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            _make_adapter_repo(root / "docs-repo", role_dir="architecture")
            toml_utils.dump(
                {
                    "version": "1.0",
                    "sources": {
                        "docs-repo": {
                            "path": "docs-repo",
                            "role": "artifacts",
                            "adapter": ".bootstrap",
                        },
                    },
                },
                root / ".cf-workspace.toml",
            )

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(["--json", "workspace-sync"], cwd=root)
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["message"], "No Git URL sources to sync")
            self.assertEqual(payload["results"], [])

    def test_workspace_sync_all_failed_returns_exit_2(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            toml_utils.dump(
                {
                    "version": "1.0",
                    "sources": {
                        "remote-docs": {
                            "url": "https://gitlab.com/acme/docs.git",
                            "branch": "main",
                        },
                    },
                },
                root / ".cf-workspace.toml",
            )

            before = _snapshot_tree(root)
            with patch(
                "studio.commands.workspace_sync._sync_sources",
                return_value=([{"name": "remote-docs", "status": "failed", "error": "network error"}], 0, 1),
            ):
                exit_code, stdout, stderr = _run_main(["--json", "workspace-sync"], cwd=root)
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["synced"], 0)
            self.assertEqual(payload["failed"], 1)

    def test_workspace_sync_force_propagates_to_sync_layer(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace-root"
            _make_repo(root)
            toml_utils.dump(
                {
                    "version": "1.0",
                    "sources": {
                        "remote-docs": {
                            "url": "https://gitlab.com/acme/docs.git",
                            "branch": "main",
                        },
                    },
                },
                root / ".cf-workspace.toml",
            )

            before = _snapshot_tree(root)
            with patch(
                "studio.commands.workspace_sync._sync_sources",
                return_value=([{"name": "remote-docs", "status": "synced"}], 1, 0),
            ) as mock_sync:
                exit_code, stdout, stderr = _run_main(["--json", "workspace-sync", "--force"], cwd=root)
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            self.assertTrue(mock_sync.call_args.kwargs["force"])
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "OK")


class TestCLIDelegateE2E(unittest.TestCase):
    def test_delegate_invalid_root_is_read_only(self):
        with TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            before = _snapshot_tree(cwd)

            exit_code, stdout, stderr = _run_main(
                ["--json", "delegate", "plan-dir", "--root", str(cwd / "missing-root")],
                cwd=cwd,
            )
            after = _snapshot_tree(cwd)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)

            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("Project root not found", payload["error"])

    def test_delegate_missing_plan_toml_is_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            _make_repo(root)
            plan_dir = root / "plans" / "slice"
            plan_dir.mkdir(parents=True, exist_ok=True)

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(
                ["--json", "delegate", str(plan_dir), "--root", str(root)],
                cwd=root,
            )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)

            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("plan.toml not found", payload["error"])

    def test_delegate_dry_run_via_public_cli_is_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            _make_repo(root)
            plan_dir = root / "plans" / "slice"
            plan_dir.mkdir(parents=True, exist_ok=True)
            (plan_dir / "plan.toml").write_text("[plan]\ntask = 'slice'\n", encoding="utf-8")

            before = _snapshot_tree(root)
            with patch(
                "studio.ralphex_export.run_delegation",
                return_value={
                    "status": "ready",
                    "command": ["/usr/bin/ralphex", "delegate-plan.md", "--serve"],
                    "plan_file": str(plan_dir / "delegate-plan.md"),
                    "dashboard_url": "http://127.0.0.1:8400",
                    "lifecycle_state": "exported",
                },
            ) as mock_run:
                exit_code, stdout, stderr = _run_main(
                    ["delegate", str(plan_dir), "--root", str(root), "--dry-run"],
                    cwd=root,
                )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(after, before)
            self.assertEqual(mock_run.call_args.kwargs["dry_run"], True)
            self.assertEqual(mock_run.call_args.kwargs["repo_root"], str(root.resolve()))
            self.assertEqual(stdout, "")
            self.assertIn("[DRY RUN] Command assembled (not invoked):", stderr)
            self.assertIn("Dashboard: http://127.0.0.1:8400", stderr)
            self.assertIn("Lifecycle: exported", stderr)

    def test_delegate_json_non_dry_run_success_is_read_only_locally(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            _make_repo(root)
            plan_dir = root / "plans" / "slice"
            plan_dir.mkdir(parents=True, exist_ok=True)
            (plan_dir / "plan.toml").write_text("[plan]\ntask = 'slice'\n", encoding="utf-8")

            before = _snapshot_tree(root)
            with patch(
                "studio.ralphex_export.run_delegation",
                return_value={
                    "status": "delegated",
                    "command": ["/usr/bin/ralphex", "delegate-plan.md", "--serve"],
                    "plan_file": str(plan_dir / "delegate-plan.md"),
                    "dashboard_url": "http://127.0.0.1:8400",
                    "lifecycle_state": "started",
                    "mode": "execute",
                },
            ) as mock_run:
                exit_code, stdout, stderr = _run_main(
                    ["--json", "delegate", str(plan_dir), "--root", str(root)],
                    cwd=root,
                )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            self.assertFalse(mock_run.call_args.kwargs["dry_run"])
            self.assertTrue(mock_run.call_args.kwargs["serve"])
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "delegated")
            self.assertEqual(payload["lifecycle_state"], "started")
            self.assertEqual(payload["dashboard_url"], "http://127.0.0.1:8400")
            self.assertEqual(payload["mode"], "execute")


class TestCLIDoctorE2E(unittest.TestCase):
    def test_doctor_json_exception_path_is_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            _make_repo(root)

            before = _snapshot_tree(root)
            with patch("studio.commands.doctor._check_ralphex", side_effect=RuntimeError("boom")):
                exit_code, stdout, stderr = _run_main(["--json", "doctor", "--root", str(root)], cwd=root)
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(after, before)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "unhealthy")
            self.assertEqual(payload["checks"][0]["status"], "fail")
            self.assertIn("Check raised an exception: boom", payload["checks"][0]["detail"])
            self.assertEqual(payload["summary"], "Doctor found issues that need attention.")

    def test_doctor_json_fail_path_is_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            _make_repo(root)

            before = _snapshot_tree(root)
            with patch(
                "studio.commands.doctor._check_ralphex",
                return_value={
                    "level": "FAIL",
                    "name": "inst-check-ralphex",
                    "message": "ralphex installation is corrupted",
                },
            ):
                exit_code, stdout, stderr = _run_main(
                    ["--json", "doctor", "--root", str(root)],
                    cwd=root,
                )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 2)
            self.assertEqual(after, before)
            self.assertEqual(stderr, "")

            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "unhealthy")
            self.assertEqual(payload["summary"], "Doctor found issues that need attention.")
            self.assertEqual(
                payload["checks"],
                [
                    {
                        "name": "inst-check-ralphex",
                        "status": "fail",
                        "detail": "ralphex installation is corrupted",
                    },
                ],
            )

    def test_doctor_healthy_output_is_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            _make_repo(root)

            before = _snapshot_tree(root)
            with patch(
                "studio.commands.doctor._check_ralphex",
                return_value={
                    "level": "PASS",
                    "name": "inst-check-ralphex",
                    "message": "ralphex 1.2.3 at /tmp/ralphex",
                },
            ):
                exit_code, stdout, stderr = _run_main(
                    ["doctor", "--root", str(root)],
                    cwd=root,
                )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(after, before)
            self.assertEqual(stdout, "")
            self.assertIn("Studio Doctor", stderr)
            self.assertIn("[PASS] inst-check-ralphex: ralphex 1.2.3 at /tmp/ralphex", stderr)
            self.assertIn("All checks passed.", stderr)

    def test_doctor_degraded_output_is_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            _make_repo(root)

            before = _snapshot_tree(root)
            with patch(
                "studio.commands.doctor._check_ralphex",
                return_value={
                    "level": "WARN",
                    "name": "inst-check-ralphex",
                    "message": "ralphex not found. install guidance",
                },
            ):
                exit_code, stdout, stderr = _run_main(
                    ["doctor", "--root", str(root)],
                    cwd=root,
                )
            after = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(after, before)
            self.assertEqual(stdout, "")
            self.assertIn("Studio Doctor", stderr)
            self.assertIn("[WARN] inst-check-ralphex: ralphex not found. install guidance", stderr)
            self.assertIn("All checks passed with warnings.", stderr)
