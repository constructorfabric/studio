"""Unit coverage for `list-ids` hit collection and dedupe (OLE-41)."""

from __future__ import annotations

import argparse
import sys
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
