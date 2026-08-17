"""Unit coverage for `list-ids` hit collection and dedupe (OLE-41)."""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.commands.list_ids import _apply_hit_filters, _collect_artifact_hits, _dedupe_hits


def _default_args(**overrides: object) -> argparse.Namespace:
    base = {"kind": None, "pattern": None, "regex": False, "all": False}
    base.update(overrides)
    return argparse.Namespace(**base)


def test_list_ids_default_prefers_definition_over_earlier_reference() -> None:
    """A reference mentioned before its formal definition must not shadow it."""
    with TemporaryDirectory() as tmp:
        artifact = Path(tmp) / "doc.md"
        artifact.write_text(
            "See `cpt-example-thing-x` for details.\n"
            "\n"
            "**ID**: `cpt-example-thing-x`\n",
            encoding="utf-8",
        )

        hits = _collect_artifact_hits([(artifact, "FEATURE")], set(), set())
        assert [h["type"] for h in hits] == ["reference", "definition"]

        default_hits = _apply_hit_filters(hits, _default_args())
        assert len(default_hits) == 1
        assert default_hits[0]["type"] == "definition"
        assert default_hits[0]["line"] == 3

        all_hits = _apply_hit_filters(hits, _default_args(all=True))
        assert [h["type"] for h in all_hits] == ["reference", "definition"]


def test_list_ids_default_keeps_reference_when_no_definition_exists() -> None:
    """IDs with no definition anywhere keep their first-seen hit (unchanged behavior)."""
    with TemporaryDirectory() as tmp:
        artifact = Path(tmp) / "doc.md"
        artifact.write_text(
            "See `cpt-example-thing-y` for details.\n"
            "`cpt-example-thing-y`\n",
            encoding="utf-8",
        )

        hits = _collect_artifact_hits([(artifact, "FEATURE")], set(), set())
        default_hits = _apply_hit_filters(hits, _default_args())

        assert len(default_hits) == 1
        assert default_hits[0]["type"] == "reference"
        assert default_hits[0]["line"] == 1


def test_dedupe_hits_prefers_first_definition_when_multiple_exist() -> None:
    hits = [
        {"id": "cpt-x", "type": "reference", "line": 1},
        {"id": "cpt-x", "type": "definition", "line": 5},
        {"id": "cpt-x", "type": "definition", "line": 9},
    ]
    deduped = _dedupe_hits(hits)
    assert len(deduped) == 1
    assert deduped[0]["type"] == "definition"
    assert deduped[0]["line"] == 5


def test_list_ids_include_code_works_with_no_registered_artifacts() -> None:
    """A codebase-only project (no registered artifacts) must still return code hits."""
    from studio.cli import main
    from studio.utils import toml_utils

    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
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

        cwd = os.getcwd()
        try:
            os.chdir(root)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["list-ids", "--include-code"])
            assert rc == 0
            out = json.loads(buf.getvalue())
            code_hits = [h for h in out.get("ids", []) if h.get("type") == "code_reference"]
            assert len(code_hits) == 1
            assert code_hits[0]["id"] == "cpt-test-req-1"
        finally:
            os.chdir(cwd)
