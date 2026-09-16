"""Tests for `document.scan_cpt_id_lines` — the ID scan split from its file read.

`scan_cpt_ids(path)` reads then scans; `scan_cpt_id_lines(lines)` is the scan alone, for
a caller that already holds the text — the change-summary linkage feeds it text obtained
through `codebase.read_code_text` rather than `document.read_text_safe`. These tests pin
the standalone contract and prove the two readers yield identical hits for the same
content, including the line endings and the binary rule on which they could diverge.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from studio.utils import document
from studio.utils import error_codes as EC
from studio.utils.codebase import read_code_text

FIXTURE = (
    "# Feature\n"
    "\n"
    "- [x] `p1` - **ID**: `cpt-x-algo-one`\n"
    "\n"
    "This serves `cpt-x-algo-two` and, in passing, `cpt-x-algo-three`.\n"
    "\n"
    "```\n"
    "`cpt-x-algo-fenced` is inside a code fence and must not count.\n"
    "```\n"
)


class TestScanCptIdLines:

    def test_definitions_references_and_fenced_exclusion(self):
        hits = document.scan_cpt_id_lines(FIXTURE.splitlines())

        kinds = {(h["type"], h["id"]) for h in hits}
        assert ("definition", "cpt-x-algo-one") in kinds
        assert ("reference", "cpt-x-algo-two") in kinds
        assert ("reference", "cpt-x-algo-three") in kinds
        assert not any(h["id"] == "cpt-x-algo-fenced" for h in hits), "fenced text is not scanned"

    def test_line_numbers_are_one_based_positions_in_the_given_lines(self):
        hits = document.scan_cpt_id_lines(FIXTURE.splitlines())

        assert {h["id"]: h["line"] for h in hits}["cpt-x-algo-one"] == 3

    def test_no_lines_no_hits(self):
        assert document.scan_cpt_id_lines([]) == []

    def test_the_standalone_scan_is_what_the_path_scan_uses(self, tmp_path, monkeypatch):
        """Reverting the split — inlining the scan back into `scan_cpt_ids` — would make
        the two drift silently. This fails if the path scan stops delegating."""
        path = tmp_path / "f.md"
        path.write_text(FIXTURE, encoding="utf-8")
        seen = {}
        real = document.scan_cpt_id_lines

        def _spy(lines):
            seen["lines"] = list(lines)
            return real(lines)
        monkeypatch.setattr(document, "scan_cpt_id_lines", _spy)

        document.scan_cpt_ids(path)

        assert seen["lines"] == FIXTURE.splitlines()


class TestBothReadersYieldTheSameHits:
    """`read_text_safe` (used by `scan_cpt_ids`) and `codebase.read_code_text` (used by
    the change-summary linkage) must present identical lines to the scan."""

    @pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"], ids=["lf", "crlf", "cr"])
    def test_identical_hits_for_identical_content(self, tmp_path: Path, newline: str):
        """Every terminator `str.splitlines` recognises, the bare CR of classic Mac files
        included — the one on which a reader translating newlines and one reading bytes
        could most plausibly part ways."""
        path = tmp_path / "f.md"
        path.write_bytes(FIXTURE.replace("\n", newline).encode("utf-8"))

        via_path = document.scan_cpt_ids(path)
        text, errors = read_code_text(path)
        assert text is not None and not errors
        via_text = document.scan_cpt_id_lines(text.splitlines())

        assert via_text == via_path
        assert len(via_text) == 3

    def test_both_readers_refuse_nul_bytes_as_binary(self, tmp_path: Path):
        """`read_text_safe` treats a NUL byte as binary and yields no lines; the code
        reader now applies the same rule, so a NUL-bearing file is unreadable to both
        rather than scanned by one and skipped by the other."""
        path = tmp_path / "b.md"
        path.write_bytes(b"- [x] `p1` - **ID**: `cpt-x-algo-one`\n\x00")

        assert document.scan_cpt_ids(path) == []
        text, errors = read_code_text(path)
        assert text is None
        assert [e["code"] for e in errors] == [EC.FILE_READ_ERROR]
