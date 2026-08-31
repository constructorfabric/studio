"""Tests for heading-nav retrieval over a document's retrieval sections
(heading_nav.py).

See constructorfabric/studio#104.
"""

from __future__ import annotations

import json
from pathlib import Path

from studio.commands.heading_nav import cmd_heading_nav
from studio.utils.heading_nav import find_sections

_SAMPLE = (
    "## Introduction\n\n"
    "This section introduces the KAPING framework for knowledge graphs.\n\n"
    "## Related Work\n\n"
    "This section covers unrelated background material with no overlap.\n\n"
    "## Conclusion\n\n"
    "A short closing section.\n"
)


def _write(tmp_path: Path, content: str = _SAMPLE, name: str = "doc.md") -> Path:
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


class TestFindSections:
    def test_headingless_document_returns_no_matches(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, "Just a paragraph, no headings.\n")
        result = find_sections(f, "anything")
        assert result == {"matches": [], "first_match": None}

    def test_exact_term_present_in_one_section(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        result = find_sections(f, "KAPING")
        assert [m["heading"] for m in result["matches"]] == ["Introduction"]
        assert result["matches"][0]["hit_count"] == 1
        assert result["first_match"] == result["matches"][0]

    def test_wording_mismatch_is_a_hard_failure_zero_hits(self, tmp_path: Path, monkeypatch):
        """Mirrors findings.md's real "making up" case: this method has no
        semantic fallback, so a query phrased differently than the source's
        own vocabulary returns nothing, even though a related word exists."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, "## Section\n\nThe model sometimes hallucinates facts.\n")
        result = find_sections(f, "making up")
        assert result == {"matches": [], "first_match": None}

    def test_is_case_insensitive(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        result = find_sections(f, "kaping")
        assert result["first_match"]["heading"] == "Introduction"

    def test_multiple_occurrences_in_one_section_are_counted(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, "## A\n\nwidget widget widget\n")
        result = find_sections(f, "widget")
        assert result["matches"][0]["hit_count"] == 3

    def test_term_present_in_multiple_sections_lists_all_in_document_order(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, "## A\n\nshared here\n\n## B\n\nshared there too\n")
        result = find_sections(f, "shared")
        assert [m["heading"] for m in result["matches"]] == ["A", "B"]
        assert result["first_match"]["heading"] == "A"

    def test_empty_query_returns_no_matches(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        assert find_sections(f, "   ") == {"matches": [], "first_match": None}


class TestCmdHeadingNav:
    def test_missing_file(self, tmp_path: Path, capsys):
        rc = cmd_heading_nav([str(tmp_path / "nope.md"), "query"])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_basic_json_output(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        rc = cmd_heading_nav([str(f), "KAPING"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["first_match"]["heading"] == "Introduction"

    def test_human_output_with_matches(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_heading_nav([str(f), "KAPING"])
        finally:
            set_json_mode(orig)
        assert rc == 0
        assert "Introduction" in capsys.readouterr().out

    def test_human_output_no_matches(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_heading_nav([str(f), "zzzznomatch"])
        finally:
            set_json_mode(orig)
        assert rc == 0
        assert "no semantic fallback" in capsys.readouterr().out
