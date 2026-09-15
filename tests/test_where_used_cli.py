"""CLI coverage for `where-used --include-code` (OLE-42)."""

from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.commands.where_used import cmd_where_used
from studio.utils.ui import is_json_mode, set_json_mode

_CODE_HITS = [
    {"id": "cpt-example-thing-x", "line": 10, "artifact": "src/auth.py", "type": "code_reference", "kind": "flow"},
    {"id": "cpt-other", "line": 3, "artifact": "src/other.py", "type": "code_reference", "kind": "flow"},
]


def _run_where_used(argv: list[str]) -> dict:
    saved = is_json_mode()
    stdout = io.StringIO()
    try:
        set_json_mode(True)
        with redirect_stdout(stdout):
            exit_code = cmd_where_used(argv)
        assert exit_code == 0
        return json.loads(stdout.getvalue())
    finally:
        set_json_mode(saved)


def _run_where_used_with_mocked_scan(tmp: str, argv: list[str]):
    """Run `where-used` with context resolution and code scanning mocked out."""
    artifact = Path(tmp) / "doc.md"
    artifact.write_text("no references here\n", encoding="utf-8")

    with patch(
        "studio.commands.where_used.resolve_target_and_artifacts",
        return_value=("cpt-example-thing-x", object(), [(artifact, "FEATURE")], {}, None),
    ), patch(
        "studio.commands.where_used.scan_registered_codebase_references",
        return_value=(_CODE_HITS, 3, 0),
    ) as mock_scan:
        data = _run_where_used(argv)
        return data, mock_scan


def test_where_used_ignores_code_without_flag() -> None:
    with TemporaryDirectory() as tmp:
        data, mock_scan = _run_where_used_with_mocked_scan(tmp, ["cpt-example-thing-x"])
        mock_scan.assert_not_called()

    assert data["count"] == 0
    assert "code_files_scanned" not in data


def test_where_used_include_code_returns_matching_code_hits() -> None:
    with TemporaryDirectory() as tmp:
        data, mock_scan = _run_where_used_with_mocked_scan(tmp, ["cpt-example-thing-x", "--include-code"])
        mock_scan.assert_called_once()

    assert data["count"] == 1
    assert data["code_files_scanned"] == 3
    assert data["references"][0]["artifact_type"] == "CODE"
    assert data["references"][0]["artifact"] == "src/auth.py"


def _write_codebase_only_project(root: Path) -> None:
    """Build a project with a registered codebase entry but no artifacts."""
    from studio.utils import toml_utils

    (root / ".git").mkdir()
    (root / "AGENTS.md").write_text(
        '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "adapter"\n```\n',
        encoding="utf-8",
    )
    adapter = root / "adapter"
    (adapter / "config").mkdir(parents=True)
    (adapter / "config" / "AGENTS.md").write_text("# Test adapter\n", encoding="utf-8")

    src = root / "src"
    src.mkdir()
    (src / "impl.py").write_text(
        "# @cpt-begin:cpt-test-req-1:p1:inst-do-work\n"
        "print('working')\n"
        "# @cpt-end:cpt-test-req-1:p1:inst-do-work\n",
        encoding="utf-8",
    )

    toml_utils.dump(
        {
            "version": "1.0",
            "project_root": "..",
            "kits": {},
            "systems": [{
                "name": "Test", "slug": "test",
                "artifacts": [],
                "codebase": [{"path": "src", "extensions": [".py"]}],
            }],
        },
        adapter / "config" / "artifacts.toml",
    )


def test_where_used_include_code_works_with_no_registered_artifacts() -> None:
    """A codebase-only project (no registered artifacts) must still return code hits.

    Mirrors test_list_ids_include_code_works_with_no_registered_artifacts —
    where-used's `if not artifacts_to_scan and not args.include_code:` early
    return (where_used.py) has the same zero-artifacts branch as list-ids.
    """
    from studio.cli import main

    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_codebase_only_project(root)

        cwd = os.getcwd()
        try:
            os.chdir(root)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["where-used", "cpt-test-req-1", "--include-code"])
            assert rc == 0
            out = json.loads(buf.getvalue())
            assert out["code_files_scanned"] == 1
            assert len(out["references"]) == 1
            assert out["references"][0]["artifact_type"] == "CODE"
        finally:
            os.chdir(cwd)


def test_where_used_include_code_real_scan_through_cli() -> None:
    """Exercise the real (non-mocked) scan_registered_codebase_references path.

    Unlike the mocked-scan tests above, this drives a real codebase entry
    with an ignored file mixed in, through the actual CLI entry point, to
    catch regressions in the shared codebase.py scanning helper itself.
    """
    from studio.cli import main

    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_codebase_only_project(root)
        (root / "src" / "unrelated.py").write_text(
            "# @cpt-begin:cpt-other-thing:p1:inst-noop\npass\n# @cpt-end:cpt-other-thing:p1:inst-noop\n",
            encoding="utf-8",
        )

        cwd = os.getcwd()
        try:
            os.chdir(root)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["where-used", "cpt-test-req-1", "--include-code"])
            assert rc == 0
            out = json.loads(buf.getvalue())
            assert out["code_files_scanned"] == 2
            assert out["count"] == 1
            assert out["references"][0]["artifact"].endswith("impl.py")
        finally:
            os.chdir(cwd)
