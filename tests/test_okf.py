"""Tests for the local, regenerable OKF bundle (okf.py).

See constructorfabric/studio#104.
"""

from __future__ import annotations

import json
from pathlib import Path

from studio.commands.okf import cmd_okf_status
from studio.utils.doc_index import get_or_build_doc_index
from studio.utils.okf import (
    _okf_bundle_dir,
    get_okf_status,
    load_okf_manifest,
    save_okf_manifest,
    write_concept_file,
)

_SAMPLE = (
    "## Introduction\n\n"
    "Body of the introduction.\n\n"
    "## Details\n\n"
    "Body of details.\n\n"
    "## Details\n\n"
    "Body of the second details section (duplicate heading).\n"
)


def _write(tmp_path: Path, content: str = _SAMPLE, name: str = "doc.md") -> Path:
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


class TestGetOkfStatus:
    def test_unavailable_outside_a_studio_project(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: None)
        f = _write(tmp_path)
        status = get_okf_status(f)
        assert status == {"available": False, "bundle_dir": None, "entries": []}

    def test_all_sections_missing_before_anything_is_written(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        status = get_okf_status(f)
        assert status["available"] is True
        assert len(status["entries"]) == 3
        assert all(e["status"] == "missing" for e in status["entries"])

    def test_duplicate_headings_get_distinct_concept_filenames(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        status = get_okf_status(f)
        filenames = [e["concept_file"] for e in status["entries"]]
        assert len(filenames) == len(set(filenames))
        assert filenames == ["01-introduction.md", "02-details.md", "03-details.md"]

    def test_written_section_reports_current(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        intro = index["retrieval_sections"][0]
        assert write_concept_file(
            f, intro["line_start"], description="Covers the intro.", body="Summary here.", generated_by="test"
        ) is True

        status = get_okf_status(f)
        by_heading = {e["heading"]: e for e in status["entries"]}
        assert by_heading["Introduction"]["status"] == "current"
        assert by_heading["Details"]["status"] == "missing"  # untouched, both of them

    def test_deleting_a_written_concept_file_reports_missing_not_current(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #110: a manifest entry's hash still matches after
        its concept file is deleted out from under it (a manual cleanup,
        say) -- the hash alone can't prove the file it points at survives,
        so status must fall back to missing rather than current."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        intro = index["retrieval_sections"][0]
        write_concept_file(f, intro["line_start"], description="d", body="b")
        assert get_okf_status(f)["entries"][0]["status"] == "current"

        bundle_dir = _okf_bundle_dir(f)
        (bundle_dir / "01-introduction.md").unlink()

        status = get_okf_status(f)
        by_heading = {e["heading"]: e for e in status["entries"]}
        assert by_heading["Introduction"]["status"] == "missing"

    def test_editing_the_source_after_writing_reports_stale(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        intro = index["retrieval_sections"][0]
        write_concept_file(f, intro["line_start"], description="d", body="b")

        f.write_text(_SAMPLE.replace("Body of the introduction.", "Edited intro body."), encoding="utf-8")
        status = get_okf_status(f)
        by_heading = {e["heading"]: e for e in status["entries"]}
        assert by_heading["Introduction"]["status"] == "stale"


class TestWriteConceptFile:
    def test_returns_false_outside_a_studio_project(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: None)
        f = _write(tmp_path)
        assert write_concept_file(f, 1, description="d", body="b") is False

    def test_returns_false_for_unmatched_line_start(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        assert write_concept_file(f, 9999, description="d", body="b") is False

    def test_writes_concept_file_with_frontmatter_and_body(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        intro = index["retrieval_sections"][0]
        assert write_concept_file(
            f, intro["line_start"], description="Covers the intro.", body="Real summary body.", generated_by="claude"
        ) is True

        status = get_okf_status(f)
        bundle_dir = Path(status["bundle_dir"])
        concept_path = bundle_dir / "01-introduction.md"
        assert concept_path.is_file()
        content = concept_path.read_text(encoding="utf-8")
        assert 'title: "Introduction"' in content
        assert 'description: "Covers the intro."' in content
        assert 'by: "claude"' in content
        assert "Real summary body." in content

    def test_writes_a_concept_file_for_the_preamble_section(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #110: the synthetic preamble section (heading=None,
        content before a document's first real heading) must slugify to a
        real, readable filename/title instead of crashing on a heading
        that was never a real string."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        content = "# Title\n\nAn intro paragraph.\n\n" + _SAMPLE
        f = _write(tmp_path, content)
        index = get_or_build_doc_index(f)
        preamble = index["retrieval_sections"][0]
        assert preamble["heading"] is None
        assert write_concept_file(
            f, preamble["line_start"], description="The preamble.", body="Body.", generated_by="claude"
        ) is True

        status = get_okf_status(f)
        bundle_dir = Path(status["bundle_dir"])
        concept_path = bundle_dir / "01-preamble.md"
        assert concept_path.is_file()
        assert 'title: "(preamble)"' in concept_path.read_text(encoding="utf-8")

    def test_writes_and_updates_index_md(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        intro = index["retrieval_sections"][0]
        write_concept_file(f, intro["line_start"], description="Covers the intro.", body="Summary.")

        status = get_okf_status(f)
        index_md = (Path(status["bundle_dir"]) / "index.md").read_text(encoding="utf-8")
        assert "[Introduction](01-introduction.md) - Covers the intro." in index_md

    def test_second_write_does_not_duplicate_manifest_entries(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        intro = index["retrieval_sections"][0]
        write_concept_file(f, intro["line_start"], description="First.", body="a")
        write_concept_file(f, intro["line_start"], description="Second.", body="b")

        manifest = load_okf_manifest(f)
        matching = [e for e in manifest["entries"] if e["line_start"] == intro["line_start"]]
        assert len(matching) == 1
        assert matching[0]["description"] == "Second."

    def test_rewriting_after_a_source_edit_clears_stale_status(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        intro = index["retrieval_sections"][0]
        write_concept_file(f, intro["line_start"], description="d", body="b")
        f.write_text(_SAMPLE.replace("Body of the introduction.", "Edited."), encoding="utf-8")
        assert get_okf_status(f)["entries"][0]["status"] == "stale"

        write_concept_file(f, intro["line_start"], description="d2", body="b2")
        assert get_okf_status(f)["entries"][0]["status"] == "current"


class TestBundleDirLookup:
    def test_lookup_error_means_no_crash_and_unavailable(self, tmp_path: Path, monkeypatch):
        """An OSError from find_studio_directory (e.g. an unreadable parent
        directory) must degrade to 'unavailable', not raise -- and it must
        be logged, not silently swallowed."""
        def _raise(_start_path):
            raise OSError("permission denied")

        monkeypatch.setattr("studio.utils.files.find_studio_directory", _raise)
        f = _write(tmp_path)
        assert get_okf_status(f) == {"available": False, "bundle_dir": None, "entries": []}

    def test_save_manifest_returns_false_outside_a_studio_project(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: None)
        f = _write(tmp_path)
        assert save_okf_manifest(f, {"entries": []}) is False


class TestLoadOkfManifest:
    def test_returns_none_when_no_manifest_exists(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        assert load_okf_manifest(f) is None

    def test_returns_none_outside_a_studio_project(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: None)
        f = _write(tmp_path)
        assert load_okf_manifest(f) is None

    def test_returns_none_on_corrupt_manifest(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        write_concept_file(f, index["retrieval_sections"][0]["line_start"], description="d", body="b")
        status = get_okf_status(f)
        manifest_path = Path(status["bundle_dir"]) / "manifest.json"
        manifest_path.write_text("{not valid json", encoding="utf-8")
        assert load_okf_manifest(f) is None


class TestCmdOkfStatus:
    def test_missing_file(self, tmp_path: Path, capsys):
        rc = cmd_okf_status([str(tmp_path / "nope.md")])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_directory_as_file_argument_is_rejected(self, tmp_path: Path, capsys):
        rc = cmd_okf_status([str(tmp_path)])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_missing_required_argument_emits_json_error_not_a_plain_text_banner(self, capsys):
        """CodeRabbit PR #110: an argparse parsing failure used to bypass
        this project's own --json output contract entirely."""
        rc = cmd_okf_status([])  # file omitted
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_headingless_document_reports_zero_entries(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, "Just a paragraph, no headings at all.\n")
        rc = cmd_okf_status([str(f)])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["available"] is True
        assert out["entries"] == []

    def test_basic_json_output(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        rc = cmd_okf_status([str(f)])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["available"] is True
        assert len(out["entries"]) == 3

    def test_human_output_available(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_okf_status([str(f)])
        finally:
            set_json_mode(orig)
        assert rc == 0
        out = capsys.readouterr().out
        assert "3 missing" in out
        assert "Introduction" in out

    def test_human_output_unavailable(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: None)
        f = _write(tmp_path)
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_okf_status([str(f)])
        finally:
            set_json_mode(orig)
        assert rc == 0
        assert "unavailable" in capsys.readouterr().out
