"""Public CLI end-to-end coverage for navigation/read commands."""

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


def _bootstrap_navigation_project(root: Path, *, adapter_rel: str = "adapter") -> None:
    (root / ".git").mkdir(parents=True, exist_ok=True)
    _write_root_agents(root, adapter_rel)

    adapter = root / adapter_rel
    config_dir = adapter / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "AGENTS.md").write_text("# Test adapter\n", encoding="utf-8")

    toml_utils.dump(
        {
            "version": "1.0",
            "project_root": "..",
            "kits": {"test": {"format": "CFS", "path": "kits/test"}},
        },
        config_dir / "core.toml",
    )
    toml_utils.dump(
        {
            "version": "1.0",
            "project_root": "..",
            "kits": {"test": {"format": "CFS", "path": "kits/test"}},
            "systems": [
                {
                    "name": "Web",
                    "slug": "web",
                    "kit": "test",
                    "artifacts": [
                        {"path": "architecture/PRD.md", "kind": "PRD", "traceability": "FULL"},
                        {"path": "architecture/DESIGN.md", "kind": "DESIGN", "traceability": "FULL"},
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
                "PRD": {"identifiers": {"item": {"template": "cpt-{system}-item-{slug}"}}},
                "DESIGN": {"identifiers": {"item": {"template": "cpt-{system}-item-{slug}"}}},
                "FEATURE": {"identifiers": {"item": {"template": "cpt-{system}-item-{slug}"}}},
            },
        },
        root / "kits" / "test" / "constraints.toml",
    )

    architecture = root / "architecture"
    architecture.mkdir(parents=True, exist_ok=True)
    (architecture / "PRD.md").write_text(
        "- [x] `p1` - **ID**: `cpt-web-item-login`\n"
        "- [x] `p2` - `cpt-web-item-login`: referenced from requirement\n",
        encoding="utf-8",
    )
    (architecture / "DESIGN.md").write_text(
        "- [x] `p1` - **ID**: `cpt-web-item-login`\n"
        "Design details.\n",
        encoding="utf-8",
    )
    (architecture / "FEATURE.md").write_text(
        "# Feature\n\n"
        "### cpt-web-item-scope\n"
        "alpha\n"
        "beta\n\n"
        "### cpt-web-item-other\n"
        "gamma\n",
        encoding="utf-8",
    )

    code_file = root / "src" / "web" / "handlers.py"
    code_file.parent.mkdir(parents=True, exist_ok=True)
    code_file.write_text(
        "# @cpt-begin:cpt-web-flow-login:p1:inst-validate\n"
        "def validate():\n"
        "    return True\n"
        "# @cpt-end:cpt-web-flow-login:p1:inst-validate\n",
        encoding="utf-8",
    )


def _bootstrap_workspace_source(root: Path, *, source_id: str, source_name: str) -> None:
    _bootstrap_navigation_project(root, adapter_rel=".bootstrap")
    prd = root / "architecture" / "PRD.md"
    prd.write_text(
        f"- [x] `p1` - **ID**: `{source_id}`\n"
        f"- [x] `p2` - `{source_id}`: referenced from {source_name}\n",
        encoding="utf-8",
    )
    (root / "architecture" / "DESIGN.md").unlink()
    (root / "architecture" / "FEATURE.md").unlink()
    shutil_target = root / "src" / "web" / "handlers.py"
    shutil_target.write_text(
        f"# @cpt-flow:{source_id}:p1\n"
        "def validate():\n"
        "    return True\n",
        encoding="utf-8",
    )


class TestCLINavigationE2E(unittest.TestCase):
    def test_list_ids_filters_and_negative_paths_are_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_navigation_project(root)
            baseline = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "list-ids", "--pattern", "login", "--all"],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(payload["count"], 3)
            self.assertEqual({item["id"] for item in payload["ids"]}, {"cpt-web-item-login"})

            exit_code, stdout, stderr = _run_main(
                ["--json", "list-ids", "--pattern", r"cpt-web-item-log.*", "--regex", "--all"],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(payload["count"], 3)
            self.assertEqual({item["id"] for item in payload["ids"]}, {"cpt-web-item-login"})

            exit_code, stdout, stderr = _run_main(
                ["--json", "list-ids", "--kind", "item", "--all"],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(payload["count"], 3)
            self.assertTrue(all(item["kind"] == "item" for item in payload["ids"]))

            exit_code, stdout, stderr = _run_main(
                ["--json", "list-ids", "--source", "docs-repo"],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertEqual(payload["message"], "--source requires a workspace context")

            unregistered = root / "architecture" / "UNREGISTERED.md"
            unregistered.write_text("- [x] `p1` - **ID**: `cpt-web-item-untracked`\n", encoding="utf-8")
            with_unregistered = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "list-ids", "--artifact", str(unregistered)],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 1)
            self.assertEqual(stderr, "")
            self.assertEqual(after, with_unregistered)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertEqual(payload["message"], "Artifact not registered in Constructor Studio registry.")

    def test_single_project_matrix_is_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_navigation_project(root)

            before = _snapshot_tree(root)
            exit_code, stdout, stderr = _run_main(
                ["--json", "list-ids", "--include-code", "--all"],
                cwd=root,
            )
            after_list_ids = _snapshot_tree(root)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after_list_ids, before)

            list_payload = json.loads(stdout)
            self.assertEqual(list_payload["count"], 4)
            self.assertEqual(list_payload["artifacts_scanned"], 3)
            self.assertEqual(list_payload["code_files_scanned"], 1)
            ids = [(item["id"], item["type"], Path(item["artifact"]).name) for item in list_payload["ids"]]
            self.assertEqual(
                ids,
                [
                    ("cpt-web-flow-login", "code_reference", "handlers.py"),
                    ("cpt-web-item-login", "definition", "PRD.md"),
                    ("cpt-web-item-login", "definition", "DESIGN.md"),
                    ("cpt-web-item-login", "reference", "PRD.md"),
                ],
            )

            baseline = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(["--json", "list-id-kinds"], cwd=root)
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            kinds_payload = json.loads(stdout)
            self.assertEqual(kinds_payload["artifacts_scanned"], 3)
            self.assertEqual(kinds_payload["kinds"], ["item"])
            self.assertEqual(kinds_payload["kind_counts"]["item"], 2)
            self.assertEqual(kinds_payload["kind_to_templates"]["item"], ["DESIGN", "PRD"])
            self.assertEqual(kinds_payload["template_to_kinds"]["DESIGN"], ["item"])
            self.assertEqual(kinds_payload["template_to_kinds"]["PRD"], ["item"])

            exit_code, stdout, stderr = _run_main(
                [
                    "--json",
                    "get-content",
                    "--artifact",
                    str(root / "architecture" / "FEATURE.md"),
                    "--id",
                    "cpt-web-item-scope",
                ],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            content_payload = json.loads(stdout)
            self.assertEqual(content_payload["status"], "FOUND")
            self.assertEqual(content_payload["id"], "cpt-web-item-scope")
            self.assertEqual(content_payload["kind"], "FEATURE")
            self.assertEqual(content_payload["system"], "Web")
            self.assertEqual(content_payload["start_line"], 4)
            self.assertEqual(content_payload["end_line"], 5)
            self.assertEqual(content_payload["text"], "alpha\nbeta")

            exit_code, stdout, stderr = _run_main(
                [
                    "--json",
                    "get-content",
                    "--code",
                    str(root / "src" / "web" / "handlers.py"),
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
            code_payload = json.loads(stdout)
            self.assertEqual(code_payload["status"], "FOUND")
            self.assertEqual(code_payload["id"], "cpt-web-flow-login")
            self.assertEqual(code_payload["inst"], "validate")
            self.assertIn("def validate():", code_payload["text"])

            exit_code, stdout, stderr = _run_main(
                ["--json", "where-defined", "--id", "cpt-web-item-login"],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            where_defined_payload = json.loads(stdout)
            self.assertEqual(where_defined_payload["status"], "AMBIGUOUS")
            self.assertEqual(where_defined_payload["count"], 2)
            self.assertEqual(
                [(Path(item["artifact"]).name, item["artifact_type"]) for item in where_defined_payload["definitions"]],
                [("PRD.md", "PRD"), ("DESIGN.md", "DESIGN")],
            )

            exit_code, stdout, stderr = _run_main(
                ["--json", "where-used", "--id", "cpt-web-item-login"],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            where_used_payload = json.loads(stdout)
            self.assertEqual(where_used_payload["count"], 1)
            self.assertEqual(where_used_payload["references"][0]["type"], "reference")
            self.assertEqual(Path(where_used_payload["references"][0]["artifact"]).name, "PRD.md")

            exit_code, stdout, stderr = _run_main(
                ["--json", "where-used", "--id", "cpt-web-item-login", "--include-definitions"],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            where_used_defs_payload = json.loads(stdout)
            self.assertEqual(where_used_defs_payload["count"], 3)
            self.assertEqual(
                [(Path(item["artifact"]).name, item["type"]) for item in where_used_defs_payload["references"]],
                [("DESIGN.md", "definition"), ("PRD.md", "definition"), ("PRD.md", "reference")],
            )

    def test_where_defined_negative_and_positional_id_paths_are_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_navigation_project(root)
            baseline = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "where-defined", "--id", "cpt-web-item-missing"],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "NOT_FOUND")
            self.assertEqual(payload["count"], 0)
            self.assertEqual(payload["id"], "cpt-web-item-missing")

            exit_code, stdout, stderr = _run_main(
                ["--json", "where-defined", "cpt-web-item-login"],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 2)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "AMBIGUOUS")
            self.assertEqual(payload["count"], 2)
            self.assertEqual(payload["id"], "cpt-web-item-login")

    def test_where_used_scope_positional_and_no_match_paths_are_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_navigation_project(root)
            baseline = _snapshot_tree(root)

            exit_code, stdout, stderr = _run_main(
                [
                    "--json",
                    "where-used",
                    "--artifact",
                    str(root / "architecture" / "PRD.md"),
                    "--id",
                    "cpt-web-item-login",
                    "--include-definitions",
                ],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(payload["count"], 2)
            self.assertEqual(
                [(Path(item["artifact"]).name, item["type"]) for item in payload["references"]],
                [("PRD.md", "definition"), ("PRD.md", "reference")],
            )

            exit_code, stdout, stderr = _run_main(
                ["--json", "where-used", "cpt-web-item-login"],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["id"], "cpt-web-item-login")
            self.assertEqual(payload["references"][0]["type"], "reference")

            exit_code, stdout, stderr = _run_main(
                ["--json", "where-used", "--id", "cpt-web-item-missing"],
                cwd=root,
            )
            after = _snapshot_tree(root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            payload = json.loads(stdout)
            self.assertEqual(payload["count"], 0)
            self.assertEqual(payload["references"], [])
            self.assertEqual(payload["id"], "cpt-web-item-missing")

    def test_workspace_root_source_queries_work_without_local_adapter(self):
        with TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir) / "workspace-root"
            workspace_root.mkdir(parents=True, exist_ok=True)
            (workspace_root / ".git").mkdir()

            docs_repo = workspace_root / "docs-repo"
            backend_repo = workspace_root / "backend-repo"
            _bootstrap_workspace_source(docs_repo, source_id="cpt-docs-item-home", source_name="docs")
            _bootstrap_workspace_source(backend_repo, source_id="cpt-backend-item-api", source_name="backend")

            exit_code, stdout, stderr = _run_main(["--json", "workspace-init"], cwd=workspace_root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            init_payload = json.loads(stdout)
            self.assertEqual(init_payload["status"], "CREATED")

            baseline = _snapshot_tree(workspace_root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "list-ids", "--source", "backend-repo"],
                cwd=workspace_root,
            )
            after = _snapshot_tree(workspace_root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            list_payload = json.loads(stdout)
            self.assertEqual(list_payload["count"], 1)
            self.assertEqual(list_payload["artifacts_scanned"], 1)
            self.assertEqual(list_payload["ids"][0]["id"], "cpt-backend-item-api")
            self.assertTrue(list_payload["ids"][0]["artifact"].endswith("backend-repo/architecture/PRD.md"))

            exit_code, stdout, stderr = _run_main(
                ["--json", "where-defined", "--id", "cpt-backend-item-api"],
                cwd=workspace_root,
            )
            after = _snapshot_tree(workspace_root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            where_defined_payload = json.loads(stdout)
            self.assertEqual(where_defined_payload["status"], "FOUND")
            self.assertEqual(where_defined_payload["count"], 1)
            self.assertEqual(where_defined_payload["definitions"][0]["source"], "backend-repo")

            exit_code, stdout, stderr = _run_main(
                ["--json", "where-used", "--id", "cpt-backend-item-api", "--include-definitions"],
                cwd=workspace_root,
            )
            after = _snapshot_tree(workspace_root)
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(after, baseline)
            where_used_payload = json.loads(stdout)
            self.assertEqual(where_used_payload["count"], 2)
            self.assertEqual(
                [(Path(item["artifact"]).name, item["type"], item.get("source")) for item in where_used_payload["references"]],
                [("PRD.md", "definition", "backend-repo"), ("PRD.md", "reference", "backend-repo")],
            )

if __name__ == "__main__":
    unittest.main()
