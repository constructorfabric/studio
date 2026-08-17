"""CLI coverage for `where-used --include-code` (OLE-42)."""

from __future__ import annotations

import io
import json
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
        return_value=(_CODE_HITS, 3),
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
