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

    def test_corrupted_concept_file_reports_missing_not_current(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #111: a manifest entry's hash still matches even
        after its concept file is truncated/corrupted in place -- physical
        presence alone can't prove the content is real, so status must
        fall back to missing rather than trusting a file never read."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        intro = index["retrieval_sections"][0]
        write_concept_file(f, intro["line_start"], description="d", body="b")
        assert get_okf_status(f)["entries"][0]["status"] == "current"

        bundle_dir = _okf_bundle_dir(f)
        (bundle_dir / "01-introduction.md").write_text("garbage, not frontmatter", encoding="utf-8")

        status = get_okf_status(f)
        by_heading = {e["heading"]: e for e in status["entries"]}
        assert by_heading["Introduction"]["status"] == "missing"

    def test_truncated_right_after_the_opening_delimiter_reports_missing(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #111: a concept file cut off right after the
        opening ``---`` still starts with it, so checking only that would
        report a genuinely unusable file as current. The closing delimiter
        must be present too."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        intro = index["retrieval_sections"][0]
        write_concept_file(f, intro["line_start"], description="d", body="b")
        assert get_okf_status(f)["entries"][0]["status"] == "current"

        bundle_dir = _okf_bundle_dir(f)
        (bundle_dir / "01-introduction.md").write_text("---\n", encoding="utf-8")

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

    def test_stale_entry_keeps_its_own_written_concept_file_not_a_new_name(
        self, tmp_path: Path, monkeypatch
    ):
        """CodeRabbit PR #110 (round 3): a heading rename changes the
        section's hash (stale), but the *old* concept file, written under
        the *old* heading's filename, still exists on disk. Reporting a
        freshly-derived filename from the new heading would point
        okf-status/index.md at a file that was never written."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        intro = index["retrieval_sections"][0]
        write_concept_file(f, intro["line_start"], description="d", body="b")
        original_concept_file = get_okf_status(f)["entries"][0]["concept_file"]
        assert original_concept_file == "01-introduction.md"

        renamed = _SAMPLE.replace("## Introduction", "## Intro")
        f.write_text(renamed, encoding="utf-8")

        status = get_okf_status(f)
        renamed_entry = status["entries"][0]
        assert renamed_entry["heading"] == "Intro"
        assert renamed_entry["status"] == "stale"
        assert renamed_entry["concept_file"] == original_concept_file
        bundle_dir = _okf_bundle_dir(f)
        assert (bundle_dir / renamed_entry["concept_file"]).is_file()

    def test_stale_entry_with_a_deleted_concept_file_reports_missing(
        self, tmp_path: Path, monkeypatch
    ):
        """The other side of the fix above: if the stale entry's own
        concept file is gone (or corrupted), it must report missing, not
        stale -- a caller can't be pointed at a file that isn't there."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        intro = index["retrieval_sections"][0]
        write_concept_file(f, intro["line_start"], description="d", body="b")
        bundle_dir = _okf_bundle_dir(f)
        (bundle_dir / "01-introduction.md").unlink()

        renamed = _SAMPLE.replace("## Introduction", "## Intro")
        f.write_text(renamed, encoding="utf-8")

        status = get_okf_status(f)
        assert status["entries"][0]["status"] == "missing"

    def test_new_section_landing_on_a_moved_sections_old_line_start_is_not_stale(
        self, tmp_path: Path, monkeypatch
    ):
        """CodeRabbit PR #110 (round 4): a moved section's manifest entry is
        only removed from the hash pool, not from by_line_start -- a
        completely different, brand-new section that lands exactly on that
        vacated line_start could inherit the moved section's concept_file
        and report "stale" instead of "missing", pointing index.md at a
        summary that was never written for it."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        content = (
            "## Alpha\n\nAlpha body line one.\nAlpha body line two.\n\n"
            "## Beta\n\nBeta body.\n"
        )
        f = _write(tmp_path, content)
        index = get_or_build_doc_index(f)
        beta = index["retrieval_sections"][1]
        assert beta["heading"] == "Beta"
        write_concept_file(f, beta["line_start"], description="d", body="b")
        beta_concept_file = get_okf_status(f)["entries"][1]["concept_file"]

        # Insert a new section ("Gamma") the same size as what it displaces,
        # so it lands precisely on Beta's *old* line_start while Beta itself
        # (unchanged content) shifts further down.
        moved = content.replace(
            "## Beta", "## Gamma\n\nGamma body.\n\n## Beta"
        )
        f.write_text(moved, encoding="utf-8")
        new_index = get_or_build_doc_index(f)
        gamma = next(s for s in new_index["retrieval_sections"] if s["heading"] == "Gamma")
        assert gamma["line_start"] == beta["line_start"]  # landed exactly on Beta's old spot

        status = get_okf_status(f)
        by_heading = {e["heading"]: e for e in status["entries"]}
        assert by_heading["Gamma"]["status"] == "missing"
        assert by_heading["Gamma"]["concept_file"] != beta_concept_file
        assert by_heading["Beta"]["status"] == "current"
        assert by_heading["Beta"]["concept_file"] == beta_concept_file

    def test_a_section_that_moved_without_changing_reports_current_not_missing(
        self, tmp_path: Path, monkeypatch
    ):
        """CodeRabbit PR #110 (round 2): inserting a new section between two
        already-written ones shifts everything after it to a new
        line_start -- content-identical sections must reconcile to their
        existing manifest entry by hash and keep their original
        concept_file, not report "missing" and force a needless
        re-summarization. Section lengths differ deliberately so no old
        line_start numerically collides with an unrelated new one."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        content = (
            "## Alpha\n\nAlpha body line one.\nAlpha body line two.\n\n"
            "## Beta\n\nBeta body.\n"
        )
        f = _write(tmp_path, content)
        index = get_or_build_doc_index(f)
        beta = index["retrieval_sections"][1]
        assert beta["heading"] == "Beta"
        write_concept_file(f, beta["line_start"], description="d", body="b")
        beta_concept_file = get_okf_status(f)["entries"][1]["concept_file"]

        # Insert a differently-sized section between Alpha and Beta -- Beta's
        # own text is untouched, but its line_start shifts.
        moved = content.replace(
            "## Beta", "## Gamma\n\nGamma body.\n\n## Beta"
        )
        f.write_text(moved, encoding="utf-8")
        new_index = get_or_build_doc_index(f)
        new_beta = next(s for s in new_index["retrieval_sections"] if s["heading"] == "Beta")
        assert new_beta["line_start"] != beta["line_start"]

        status = get_okf_status(f)
        by_heading = {e["heading"]: e for e in status["entries"]}
        assert by_heading["Beta"]["status"] == "current"
        assert by_heading["Beta"]["concept_file"] == beta_concept_file
        assert by_heading["Alpha"]["status"] == "missing"
        assert by_heading["Gamma"]["status"] in ("missing", "stale")

    def test_duplicate_content_sections_each_reconcile_to_a_distinct_entry(
        self, tmp_path: Path, monkeypatch
    ):
        """CodeRabbit PR #110 (round 2): two sections with byte-identical
        text share one content hash -- reconciling both to the *same*
        manifest entry after a reorder would silently drop one's own
        summary. Each must claim its own entry from the hash pool."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        dup_content = (
            "## Details\n\nSame body text.\n\n"
            "## Details\n\nSame body text.\n"
        )
        f = _write(tmp_path, dup_content)
        index = get_or_build_doc_index(f)
        details_sections = index["retrieval_sections"]
        assert len(details_sections) == 2
        assert details_sections[0]["hash"] == details_sections[1]["hash"]

        write_concept_file(f, details_sections[0]["line_start"], description="first", body="b1")
        write_concept_file(f, details_sections[1]["line_start"], description="second", body="b2")
        before = get_okf_status(f)["entries"]
        before_files = {e["line_start"]: e["concept_file"] for e in before}

        # Reorder by prepending a new section -- both Details sections shift
        # by the same offset, hashes unchanged.
        f.write_text("## Preamble\n\nPreamble body line only.\n\n" + dup_content, encoding="utf-8")
        after = get_okf_status(f)["entries"]
        after_details = [e for e in after if e["heading"] == "Details"]
        assert len(after_details) == 2
        assert all(e["status"] == "current" for e in after_details)
        after_files = sorted(e["concept_file"] for e in after_details)
        assert after_files == sorted(before_files.values())


class TestWriteConceptFile:
    def test_returns_false_outside_a_studio_project(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: None)
        f = _write(tmp_path)
        assert write_concept_file(f, 1, description="d", body="b") is False

    def test_returns_false_for_unmatched_line_start(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        assert write_concept_file(f, 9999, description="d", body="b") is False

    def test_propagates_a_persistence_failure_instead_of_reporting_true(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #111: write_concept_file used to return True
        unconditionally after calling save_okf_manifest, discarding
        whatever save_okf_manifest actually reported."""
        import studio.utils.okf as okf_module

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        line_start = index["retrieval_sections"][0]["line_start"]

        monkeypatch.setattr(okf_module, "save_okf_manifest", lambda *_a, **_k: False)
        assert write_concept_file(f, line_start, description="d", body="b") is False

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

    def test_index_md_keeps_a_moved_sections_description_after_reorder(
        self, tmp_path: Path, monkeypatch
    ):
        """CodeRabbit PR #110 (round 3): index.md's description lookup used
        to be keyed by the *current* line_start, but a section resolved as
        "current" after a reorder keeps its *original* manifest entry
        (see get_okf_status) -- whose line_start is the *old* one. Looking
        it up by the new line_start silently misses it and index.md shows
        "(no summary yet)" for a section that really has a description."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        details = index["retrieval_sections"][1]
        assert details["heading"] == "Details"
        write_concept_file(f, details["line_start"], description="Covers details.", body="b")

        # Grow the Introduction section (position 1) -- Details' line_start
        # shifts, its content (and hash) don't, so it resolves as current
        # via the reorder-tolerant hash match, keeping its own entry.
        grown = _SAMPLE.replace(
            "Body of the introduction.\n\n", "Body of the introduction.\n\nMore intro text.\n\n"
        )
        f.write_text(grown, encoding="utf-8")

        # Trigger an index.md regeneration via an unrelated write.
        new_index = get_or_build_doc_index(f)
        intro = new_index["retrieval_sections"][0]
        write_concept_file(f, intro["line_start"], description="Covers the intro.", body="a")

        status = get_okf_status(f)
        index_md = (Path(status["bundle_dir"]) / "index.md").read_text(encoding="utf-8")
        assert "Covers details." in index_md
        assert "(no summary yet)" not in index_md

    def test_new_section_does_not_steal_a_moved_sections_concept_filename(
        self, tmp_path: Path, monkeypatch
    ):
        """CodeRabbit PR #110 (round 4): concept_filename was derived purely
        from the section's *current* position/heading, computed outside the
        lock. If a reorder leaves a brand-new section at the same
        position+heading a different, already-written (moved) section now
        occupies, the naive filename collides and atomic_write_text
        silently replaces the moved section's real summary."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        content = (
            "## Alpha\n\nAlpha body one.\nAlpha body two.\n\n"
            "## Details\n\nDetails body A.\n"
        )
        f = _write(tmp_path, content)
        index = get_or_build_doc_index(f)
        details = index["retrieval_sections"][1]
        assert details["heading"] == "Details"
        write_concept_file(f, details["line_start"], description="Original.", body="a")
        original_concept_file = get_okf_status(f)["entries"][1]["concept_file"]
        assert original_concept_file == "02-details.md"

        # Insert a brand-new "Details" section ahead of the original --
        # the new one now sits at position 2 (the exact position/heading
        # combination that used to name the original's file), while the
        # original (unchanged content) shifts to position 3 and resolves
        # via hash match, keeping its own file.
        reordered = content.replace(
            "## Details", "## Details\n\nDetails body NEW.\n\n## Details", 1
        )
        f.write_text(reordered, encoding="utf-8")
        new_index = get_or_build_doc_index(f)
        new_details = new_index["retrieval_sections"][1]
        moved_original = new_index["retrieval_sections"][2]
        assert new_details["line_start"] == details["line_start"]  # took over the old slot
        assert moved_original["line_start"] != details["line_start"]  # original shifted

        write_concept_file(f, new_details["line_start"], description="New one.", body="b")

        status = get_okf_status(f)
        by_line_start = {e["line_start"]: e for e in status["entries"]}
        original_after = next(e for e in status["entries"] if e["status"] == "current"
                               and e["concept_file"] == original_concept_file)
        assert original_after["status"] == "current"
        new_entry = by_line_start[new_details["line_start"]]
        assert new_entry["concept_file"] != original_concept_file

        bundle_dir = _okf_bundle_dir(f)
        original_content = (bundle_dir / original_concept_file).read_text(encoding="utf-8")
        assert "Original." in original_content  # not clobbered by the new write

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

    def test_returns_none_when_top_level_is_not_a_dict(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #110/#111 (both independently flagged this): a
        manifest that decodes to valid JSON but isn't the expected object
        shape (e.g. a bare list) must be treated the same as a
        corrupt/absent one, not passed through for a reader to fail on."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        write_concept_file(f, index["retrieval_sections"][0]["line_start"], description="d", body="b")
        status = get_okf_status(f)
        manifest_path = Path(status["bundle_dir"]) / "manifest.json"
        manifest_path.write_text("[]", encoding="utf-8")
        assert load_okf_manifest(f) is None

    def test_returns_none_when_entries_is_not_a_list(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        write_concept_file(f, index["retrieval_sections"][0]["line_start"], description="d", body="b")
        status = get_okf_status(f)
        manifest_path = Path(status["bundle_dir"]) / "manifest.json"
        manifest_path.write_text(json.dumps({"entries": "not-a-list"}), encoding="utf-8")
        assert load_okf_manifest(f) is None

    def test_returns_none_when_an_entry_is_missing_a_required_field(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #110/#111 (both independently flagged this): an
        entry missing a required field (hand-edited, or a future/older
        schema) used to reach get_okf_status()'s dict comprehensions as an
        unhandled KeyError."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        write_concept_file(f, index["retrieval_sections"][0]["line_start"], description="d", body="b")
        status = get_okf_status(f)
        manifest_path = Path(status["bundle_dir"]) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        del manifest["entries"][0]["line_start"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        assert load_okf_manifest(f) is None
        # get_okf_status must not crash either -- it falls back to "no manifest".
        assert all(e["status"] == "missing" for e in get_okf_status(f)["entries"])

    def test_empty_entries_list_is_a_valid_manifest(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        assert save_okf_manifest(f, {"entries": []}) is True
        assert load_okf_manifest(f) == {"entries": []}

    def test_returns_none_when_a_field_has_the_wrong_type(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #111: {"line_start": [], ...} passes a presence-only
        shape check but then raises TypeError when get_okf_status() uses
        the unhashable list as a dict key -- field values must be
        type-checked, not just present."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        write_concept_file(f, index["retrieval_sections"][0]["line_start"], description="d", body="b")
        status = get_okf_status(f)
        manifest_path = Path(status["bundle_dir"]) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["entries"][0]["line_start"] = []
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        assert load_okf_manifest(f) is None
        # get_okf_status must not crash either -- it falls back to "no manifest".
        assert all(e["status"] == "missing" for e in get_okf_status(f)["entries"])


class TestGetOkfStatusReorderTolerance:
    def test_content_inserted_above_an_unchanged_section_keeps_it_current(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #111: a section's own line_start shifts whenever
        earlier content changes size, even without any structural change.
        Since matching is primarily by content hash (see
        get_okf_status's docstring), a section genuinely unchanged in
        content must not report "missing" just because something above it
        grew and shifted its line_start."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        details = index["retrieval_sections"][1]  # "Details", position 2
        assert details["heading"] == "Details"
        write_concept_file(f, details["line_start"], description="d", body="b")
        assert get_okf_status(f)["entries"][1]["status"] == "current"

        # Grow the Introduction section (position 1) without touching Details --
        # Details' line_start shifts, but its content (and hash) don't.
        grown = _SAMPLE.replace(
            "Body of the introduction.\n\n", "Body of the introduction.\n\nMore intro text.\n\n"
        )
        f.write_text(grown, encoding="utf-8")

        status = get_okf_status(f)
        assert status["entries"][1]["heading"] == "Details"
        assert status["entries"][1]["status"] == "current"


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
