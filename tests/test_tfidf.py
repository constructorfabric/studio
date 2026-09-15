"""Tests for TF-IDF scoring over a document's retrieval sections (tfidf.py).

See constructorfabric/studio#104.
"""

from __future__ import annotations

import json
from pathlib import Path

from studio.commands.tfidf import cmd_tfidf_score
from studio.utils.tfidf import score_sections, tokenize

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


class TestTokenize:
    def test_lowercases_and_splits_on_non_alphanumeric(self):
        assert tokenize("KAPING Framework-2023!") == ["kaping", "framework", "2023"]

    def test_drops_tokens_shorter_than_three_chars(self):
        assert tokenize("making up things") == ["making", "things"]

    def test_empty_text_returns_empty_list(self):
        assert tokenize("") == []


class TestScoreSections:
    def test_headingless_document_returns_empty_result(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, "Just a paragraph, no headings.\n")
        result = score_sections(f, "anything")
        assert result == {"ranked": [], "margin": None, "unambiguous": False}

    def test_exact_score_tie_has_margin_one_and_is_not_unambiguous(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #110: two sections with identical positive scores
        fall through to margin == top/second == 1.0, unambiguous == False
        -- correct by inspection, but previously unpinned by any test."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        content = "## A\n\nshared\n\n## B\n\nshared\n"
        f = _write(tmp_path, content)
        result = score_sections(f, "shared")
        assert result["margin"] == 1.0
        assert result["unambiguous"] is False

    def test_empty_query_scores_everything_zero(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        result = score_sections(f, "")
        assert result["margin"] is None
        assert result["unambiguous"] is False
        assert all(r["score"] == 0 for r in result["ranked"])

    def test_distinctive_rare_term_is_unambiguous(self, tmp_path: Path, monkeypatch):
        """Mirrors the real KAPING case from findings.md: a rare term that
        appears in exactly one section scores that section positively and
        every other section exactly zero."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        result = score_sections(f, "KAPING")
        assert result["unambiguous"] is True
        assert result["margin"] is None
        assert result["ranked"][0]["heading"] == "Introduction"
        assert result["ranked"][0]["score"] > 0
        assert all(r["score"] == 0 for r in result["ranked"][1:])

    def test_query_term_present_in_multiple_sections_has_finite_margin(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        content = (
            "## A\n\nshared shared shared unique_a\n\n"
            "## B\n\nshared unique_b\n"
        )
        f = _write(tmp_path, content)
        result = score_sections(f, "shared")
        assert result["unambiguous"] is False
        assert result["margin"] is not None
        assert result["margin"] > 1.0  # section A repeats "shared" more densely

    def test_no_query_term_matches_anything_has_no_margin(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        result = score_sections(f, "zzzznomatch")
        assert result["margin"] is None
        assert result["unambiguous"] is False
        assert all(r["score"] == 0 for r in result["ranked"])

    def test_ranked_is_sorted_descending_by_score(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        result = score_sections(f, "KAPING framework")
        scores = [r["score"] for r in result["ranked"]]
        assert scores == sorted(scores, reverse=True)

    def test_single_section_with_positive_score_is_unambiguous(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #111: a lone section can't be confused with
        anything else -- the same "nothing to compete with" case as a
        section that beat every rival's zero score, just with zero rivals
        instead of losing ones. Matters for real: route_tier1() only
        resolves a Tier-1 agreement when unambiguous, so this previously
        forced every single-section document to escalate needlessly."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, "## Only\n\nSome KAPING content.\n")
        result = score_sections(f, "KAPING")
        assert len(result["ranked"]) == 1
        assert result["margin"] is None
        assert result["unambiguous"] is True

    def test_single_section_with_zero_score_is_not_unambiguous(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, "## Only\n\nSome unrelated content.\n")
        result = score_sections(f, "zzzznomatch")
        assert len(result["ranked"]) == 1
        assert result["margin"] is None
        assert result["unambiguous"] is False


class TestCmdTfidfScore:
    def test_missing_file(self, tmp_path: Path, capsys):
        rc = cmd_tfidf_score([str(tmp_path / "nope.md"), "query"])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_directory_as_file_argument_is_rejected(self, tmp_path: Path, capsys):
        """CodeRabbit PR #110: require_existing_file's .is_file() check
        (not .exists()) correctly rejects a directory, but this exact case
        was never exercised by a test."""
        rc = cmd_tfidf_score([str(tmp_path), "query"])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_non_utf8_file_reports_a_clean_error_not_a_raw_traceback(self, tmp_path: Path, capsys):
        f = tmp_path / "bad.md"
        f.write_bytes(b"# Title\n\xff\xfe not valid utf-8\n")
        rc = cmd_tfidf_score([str(f), "query"])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_missing_required_argument_emits_json_error_not_a_plain_text_banner(
        self, tmp_path: Path, capsys
    ):
        """CodeRabbit PR #110: an argparse parsing failure (a required
        positional omitted) used to bypass this project's own --json
        output contract entirely, printing a plain-text usage banner to
        stderr instead of a JSON ERROR result to stdout."""
        f = _write(tmp_path)
        rc = cmd_tfidf_score([str(f)])  # query omitted
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_empty_string_query(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        rc = cmd_tfidf_score([str(f), ""])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["margin"] is None
        assert out["unambiguous"] is False
        assert all(r["score"] == 0 for r in out["ranked"])

    def test_basic_json_output(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        rc = cmd_tfidf_score([str(f), "KAPING"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["unambiguous"] is True
        assert out["ranked"][0]["heading"] == "Introduction"

    def test_human_output_unambiguous(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_tfidf_score([str(f), "KAPING"])
        finally:
            set_json_mode(orig)
        assert rc == 0
        out = capsys.readouterr().out
        assert "unambiguous" in out
        assert "Introduction" in out

    def test_human_output_with_margin(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        content = "## A\n\nshared shared shared unique_a\n\n## B\n\nshared unique_b\n"
        f = _write(tmp_path, content)
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_tfidf_score([str(f), "shared"])
        finally:
            set_json_mode(orig)
        assert rc == 0
        assert "margin" in capsys.readouterr().out

    def test_human_output_no_match(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_tfidf_score([str(f), "zzzznomatch"])
        finally:
            set_json_mode(orig)
        assert rc == 0
        assert "confidence: none" in capsys.readouterr().out

    def test_human_output_headingless_document(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, "Just a paragraph, no headings.\n")
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_tfidf_score([str(f), "anything"])
        finally:
            set_json_mode(orig)
        assert rc == 0
        assert "no retrieval sections" in capsys.readouterr().out
