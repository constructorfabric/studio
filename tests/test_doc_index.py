"""Tests for the cached, read-once-per-file document index (doc_index.py).

See constructorfabric/studio#104.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest

from studio.commands.doc_index import cmd_doc_index
from studio.utils.doc_index import (
    annotate_section_summary,
    build_doc_index,
    diff_stale_sections,
    get_or_build_doc_index,
    infer_section_level,
    load_doc_index,
    save_doc_index,
)
from studio.utils.toc import parse_headings_with_lines

_SAMPLE = (
    "# Title\n\n"
    "## Section A\n\n"
    "Body of A.\n\n"
    "### A.1\n\n"
    "Body of A.1.\n\n"
    "## Section B\n\n"
    "Body of B.\n"
)


def _write(tmp_path: Path, content: str = _SAMPLE, name: str = "doc.md") -> Path:
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


@pytest.fixture
def studio_logger_propagates():
    """Force the "studio" logger to propagate for the duration of a test.

    Whichever CLI test runs first in the full suite triggers
    cli.py's own _configure_studio_logging(), which sets
    logging.getLogger("studio").propagate = False for the rest of the
    process -- a real, ambient global-state mutation, not something this
    test file controls. That silently blocks pytest's caplog (which
    listens on the root logger) from ever seeing a child logger's records
    for any test that runs after it. Tests asserting on log output for
    "studio.utils.doc_index" opt into this fixture to stay correct
    regardless of suite ordering, restoring the original value afterward.
    """
    studio_logger = logging.getLogger("studio")
    original = studio_logger.propagate
    studio_logger.propagate = True
    try:
        yield
    finally:
        studio_logger.propagate = original


class TestBuildDocIndex:
    def test_extracts_sections_with_line_ranges(self, tmp_path: Path):
        f = _write(tmp_path)
        index = build_doc_index(f)
        headings = [(s["level"], s["heading"], s["line_start"], s["line_end"]) for s in index["sections"]]
        assert headings == [
            (1, "Title", 1, 2),
            (2, "Section A", 3, 6),
            (3, "A.1", 7, 10),
            (2, "Section B", 11, 14),
        ]

    def test_sections_start_with_no_summary(self, tmp_path: Path):
        f = _write(tmp_path)
        index = build_doc_index(f)
        assert all(s["summary"] is None for s in index["sections"])

    def test_etag_present_and_stable_for_same_content(self, tmp_path: Path):
        f = _write(tmp_path)
        idx1 = build_doc_index(f)
        idx2 = build_doc_index(f)
        assert idx1["etag"] == idx2["etag"]

    def test_etag_changes_when_content_changes(self, tmp_path: Path):
        f = _write(tmp_path)
        idx1 = build_doc_index(f)
        f.write_text(_SAMPLE + "\n## Section C\n")
        idx2 = build_doc_index(f)
        assert idx1["etag"] != idx2["etag"]

    def test_skips_headings_in_fenced_code(self, tmp_path: Path):
        content = "# Title\n\n## Real\n\n```bash\n# not a heading\n```\n\n## Also Real\n"
        f = _write(tmp_path, content)
        index = build_doc_index(f)
        assert [s["heading"] for s in index["sections"]] == ["Title", "Real", "Also Real"]

    def test_retrieval_sections_grouped_at_inferred_level(self, tmp_path: Path):
        f = _write(tmp_path)
        index = build_doc_index(f)
        assert index["section_level"] == 2
        # "### A.1" (H3, off-level) stays inside "## Section A", not its own section.
        assert [s["heading"] for s in index["retrieval_sections"]] == ["Section A", "Section B"]

    def test_headingless_document_has_no_retrieval_sections(self, tmp_path: Path):
        f = _write(tmp_path, "Just a paragraph, no headings at all.\n")
        index = build_doc_index(f)
        assert index["section_level"] is None
        assert index["retrieval_sections"] == []

    def test_retrieval_section_hash_changes_only_for_the_edited_section(self, tmp_path: Path):
        f = _write(tmp_path)
        before = build_doc_index(f)
        f.write_text(_SAMPLE.replace("Body of A.", "Body of A, edited."), encoding="utf-8")
        after = build_doc_index(f)
        by_heading_before = {s["heading"]: s["hash"] for s in before["retrieval_sections"]}
        by_heading_after = {s["heading"]: s["hash"] for s in after["retrieval_sections"]}
        assert by_heading_before["Section A"] != by_heading_after["Section A"]
        assert by_heading_before["Section B"] == by_heading_after["Section B"]

    def test_trailing_whitespace_only_edit_does_not_change_the_hash(self, tmp_path: Path):
        """CodeRabbit PR #109: a "trim trailing whitespace on save" editor
        default changes no meaningful content and must not look like a
        real edit to diff_stale_sections -- the whole point of hashing at
        section granularity."""
        f = _write(tmp_path)
        before = build_doc_index(f)
        f.write_text(_SAMPLE.replace("Body of A.\n", "Body of A.   \n"), encoding="utf-8")
        after = build_doc_index(f)
        by_heading_before = {s["heading"]: s["hash"] for s in before["retrieval_sections"]}
        by_heading_after = {s["heading"]: s["hash"] for s in after["retrieval_sections"]}
        assert by_heading_before["Section A"] == by_heading_after["Section A"]


class TestInferSectionLevel:
    def test_uniform_level_is_chosen(self):
        headings = [(2, "A", 1), (2, "B", 5), (2, "C", 9)]
        assert infer_section_level(headings) == 2

    def test_real_bug_regression_dominant_level_wins_over_a_stray_shallower_one(self):
        """Reproduces the actual failure found developing this feature: a
        PDF-converted document put its 8 real chapters on H5 and a single
        subsection heading on H3. Picking the shallowest level present
        (H3) -- or any fixed level -- turned the rest of the document into
        one fake mega-section. The dominant (most-recurring) level must
        win over a level that appears only once, however shallow."""
        headings = (
            [(5, f"Chapter {i}", i * 100) for i in range(1, 9)]
            + [(3, "Stray Subsection", 250)]
        )
        assert infer_section_level(headings) == 5

    def test_no_headings_returns_none(self):
        assert infer_section_level([]) is None

    def test_all_singleton_levels_falls_back_to_shallowest(self):
        headings = [(4, "A", 1), (2, "B", 5), (6, "C", 9)]
        assert infer_section_level(headings) == 2

    def test_tie_between_recurring_levels_prefers_shallower(self):
        headings = [(3, "A", 1), (3, "B", 5), (5, "C", 9), (5, "D", 13)]
        assert infer_section_level(headings) == 3

    def test_matches_real_parser_output(self, tmp_path: Path):
        content = "##### Ch1\n\nbody\n\n##### Ch2\n\nbody\n\n### Odd\n\nbody\n\n##### Ch3\n\nbody\n"
        f = _write(tmp_path, content)
        lines = f.read_text(encoding="utf-8").split("\n")
        headings = parse_headings_with_lines(lines)
        assert infer_section_level(headings) == 5


class TestDiffStaleSections:
    def test_returns_none_when_no_cache_exists(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        assert diff_stale_sections(f) is None

    def test_returns_none_for_pre_retrieval_sections_cache_format(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        old_format = build_doc_index(f)
        del old_format["retrieval_sections"]  # simulate an index built before this field existed
        save_doc_index(f, old_format)
        assert diff_stale_sections(f) is None

    def test_no_edit_reports_everything_unchanged(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        save_doc_index(f, build_doc_index(f))
        diff = diff_stale_sections(f)
        assert diff["structural_change"] is False
        assert diff["changed"] == []
        assert {(e["heading"], e["line_start"]) for e in diff["unchanged"]} == {
            ("Section A", 3),
            ("Section B", 11),
        }

    def test_editing_one_section_reports_only_that_one_changed(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        save_doc_index(f, build_doc_index(f))
        f.write_text(_SAMPLE.replace("Body of B.", "Body of B, edited."), encoding="utf-8")
        diff = diff_stale_sections(f)
        assert diff["structural_change"] is False
        assert diff["changed"] == [{"heading": "Section B", "line_start": 11}]
        assert diff["unchanged"] == [{"heading": "Section A", "line_start": 3}]

    def test_duplicate_headings_are_disambiguated_by_line_start(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #109: heading text alone can't tell two identically
        named sections apart -- line_start must be returned so a caller
        knows exactly which one changed."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        content = "## Details\n\nFirst.\n\n## Details\n\nSecond.\n"
        f = _write(tmp_path, content)
        save_doc_index(f, build_doc_index(f))
        f.write_text(content.replace("Second.", "Second, edited."), encoding="utf-8")
        diff = diff_stale_sections(f)
        assert diff["structural_change"] is False
        assert diff["unchanged"] == [{"heading": "Details", "line_start": 1}]
        assert diff["changed"] == [{"heading": "Details", "line_start": 5}]

    def test_returns_none_when_file_deleted_after_caching(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        save_doc_index(f, build_doc_index(f))
        f.unlink()
        assert diff_stale_sections(f) is None

    def test_adding_a_retrieval_level_heading_is_a_structural_change(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        save_doc_index(f, build_doc_index(f))
        f.write_text(_SAMPLE + "\n## Section C\n\nBody of C.\n", encoding="utf-8")
        diff = diff_stale_sections(f)
        assert diff["structural_change"] is True
        assert diff["unchanged"] == []
        assert {e["heading"] for e in diff["changed"]} == {"Section A", "Section B", "Section C"}


class TestCachePersistence:
    def test_load_returns_none_when_no_cache_exists(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        assert load_doc_index(f) is None

    def test_legacy_cache_with_matching_etag_but_old_schema_is_rebuilt_not_returned(
        self, tmp_path: Path, monkeypatch
    ):
        """CodeRabbit PR #109 (second round): a cache written before
        section_level/retrieval_sections existed can have a matching etag
        if the file hasn't changed since -- load_doc_index() must not
        return it as-is, or a caller reading those fields hits a
        KeyError instead of a clean rebuild."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        legacy = build_doc_index(f)
        del legacy["section_level"]
        del legacy["retrieval_sections"]
        save_doc_index(f, legacy)

        assert load_doc_index(f) is None  # not the legacy dict, and not a crash

        # The real caller path rebuilds cleanly rather than raising.
        index = get_or_build_doc_index(f)
        assert index["cache_hit"] is False
        assert "section_level" in index
        assert "retrieval_sections" in index

    def test_cmd_doc_index_does_not_crash_on_a_legacy_cache(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        legacy = build_doc_index(f)
        del legacy["section_level"]
        del legacy["retrieval_sections"]
        save_doc_index(f, legacy)

        rc = cmd_doc_index([str(f)])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["cache_hit"] is False
        assert "retrieval_sections" in out

    def test_save_then_load_round_trips(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        built = build_doc_index(f)
        save_doc_index(f, built)
        loaded = load_doc_index(f)
        assert loaded is not None
        assert loaded["etag"] == built["etag"]
        assert loaded["sections"] == built["sections"]

    def test_load_returns_none_when_cache_is_stale(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        save_doc_index(f, build_doc_index(f))
        f.write_text(_SAMPLE + "\n## Section C\n")  # content changed after caching
        assert load_doc_index(f) is None

    def test_same_size_same_line_count_edit_is_still_detected_as_stale(
        self, tmp_path: Path, monkeypatch
    ):
        """Regression test (see PR #108 review): a same-size, same-line-count
        content swap must still invalidate the cache. A byte-size +
        line-count fingerprint alone cannot distinguish this from an
        unchanged file -- mtime can, since a real write always advances it.
        """
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        save_doc_index(f, build_doc_index(f))

        edited = _SAMPLE.replace("Section A", "Section Z")
        assert len(edited) == len(_SAMPLE)
        assert edited.count("\n") == _SAMPLE.count("\n")
        f.write_text(edited, encoding="utf-8")
        # Force a distinct mtime regardless of filesystem clock resolution --
        # the mechanism under test is "mtime changed", not "enough wall-clock
        # time elapsed during the test run".
        st = f.stat()
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1))

        assert load_doc_index(f) is None
        fresh = get_or_build_doc_index(f)
        assert any(s["heading"] == "Section Z" for s in fresh["sections"])

    def test_studio_directory_resolved_from_file_path_not_cwd(
        self, tmp_path: Path, monkeypatch
    ):
        """CodeRabbit PR #108: the Studio directory must be resolved from the
        indexed file's own location, not the process's cwd -- otherwise
        indexing a file outside the caller's cwd can miss or mis-target the
        cache."""
        seen_paths = []

        def _spy(start_path):
            seen_paths.append(start_path)
            return tmp_path

        monkeypatch.setattr("studio.utils.files.find_studio_directory", _spy)
        f = _write(tmp_path)
        save_doc_index(f, build_doc_index(f))

        assert seen_paths, "find_studio_directory was never called"
        assert seen_paths[0] == f.resolve().parent

    def test_load_returns_none_on_corrupt_cache_file(
        self, tmp_path: Path, monkeypatch, caplog, studio_logger_propagates
    ):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        save_doc_index(f, build_doc_index(f))
        # Corrupt the cache file directly
        cache_dir = tmp_path / ".cache" / "doc-index"
        for cache_file in cache_dir.glob("*.json"):
            cache_file.write_text("{not valid json", encoding="utf-8")
        with caplog.at_level("WARNING"):
            assert load_doc_index(f) is None
        # CodeRabbit PR #109: real corruption is a genuine anomaly, not a
        # routine cache miss -- must be visible at the CLI's default log
        # level (WARNING), not buried at debug.
        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_cmd_doc_index_rebuilds_cleanly_after_corrupt_cache(self, tmp_path: Path, capsys, monkeypatch):
        """CodeRabbit PR #108: prove the corrupt-cache fallback at the
        CLI/exit-code level, not just load_doc_index() in isolation."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        save_doc_index(f, build_doc_index(f))
        cache_dir = tmp_path / ".cache" / "doc-index"
        for cache_file in cache_dir.glob("*.json"):
            cache_file.write_text("{not valid json", encoding="utf-8")

        rc = cmd_doc_index([str(f)])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["cache_hit"] is False

    def test_cache_missing_a_required_field_is_rebuilt_not_returned(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #108: a matching-etag cache missing "sections"
        (hand-edited, or truncated mid-write) used to pass load_doc_index's
        etag-only check and reach cmd_doc_index()'s len(index["sections"])
        as an unhandled KeyError."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        incomplete = build_doc_index(f)
        del incomplete["sections"]
        save_doc_index(f, incomplete)

        assert load_doc_index(f) is None
        index = get_or_build_doc_index(f)
        assert index["cache_hit"] is False
        assert "sections" in index

    def test_cache_from_an_older_schema_version_is_rebuilt_not_returned(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        old_schema = build_doc_index(f)
        old_schema["schema_version"] = 0
        save_doc_index(f, old_schema)

        assert load_doc_index(f) is None
        index = get_or_build_doc_index(f)
        assert index["cache_hit"] is False

    def test_save_does_not_leave_a_temp_file_behind(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #108: save_doc_index() writes atomically (temp
        file + os.replace) -- the temp file must not survive a successful
        write."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        save_doc_index(f, build_doc_index(f))
        cache_dir = tmp_path / ".cache" / "doc-index"
        names = [p.name for p in cache_dir.iterdir()]
        assert all(name.endswith(".json") for name in names)
        assert load_doc_index(f) is not None

    def test_no_studio_directory_means_no_crash_and_always_none(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: None)
        f = _write(tmp_path)
        save_doc_index(f, build_doc_index(f))  # must no-op silently, not raise
        assert load_doc_index(f) is None

    def test_studio_directory_lookup_error_means_no_crash_and_no_cache(
        self, tmp_path: Path, monkeypatch, caplog, studio_logger_propagates
    ):
        """An OSError from find_studio_directory (e.g. an unreadable parent
        directory) must degrade to 'no cache', not raise -- and it must be
        logged, not silently swallowed (see PR #108 review / pylint W9001).
        CodeRabbit PR #109: this is a genuine anomaly, distinct from the
        ordinary (unlogged) "no Studio directory found" case, so it must
        log at WARNING, visible at the CLI's default level, not DEBUG."""
        def _raise(_start_path):
            raise OSError("permission denied")

        monkeypatch.setattr("studio.utils.files.find_studio_directory", _raise)
        f = _write(tmp_path)
        with caplog.at_level("WARNING"):
            save_doc_index(f, build_doc_index(f))  # must no-op, not raise
            assert load_doc_index(f) is None
        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_load_returns_none_when_file_deleted_after_caching(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        save_doc_index(f, build_doc_index(f))
        f.unlink()
        assert load_doc_index(f) is None


class TestGetOrBuildDocIndex:
    def test_first_call_is_cache_miss(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        assert index["cache_hit"] is False

    def test_second_call_is_cache_hit(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        get_or_build_doc_index(f)
        index = get_or_build_doc_index(f)
        assert index["cache_hit"] is True

    def test_cache_hit_preserves_previously_annotated_summary(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        get_or_build_doc_index(f)
        assert annotate_section_summary(f, line_start=3, summary="Covers A.") is True
        index = get_or_build_doc_index(f)
        assert index["cache_hit"] is True
        section_a = next(s for s in index["sections"] if s["heading"] == "Section A")
        assert section_a["summary"] == "Covers A."

    def test_content_change_invalidates_and_drops_stale_summaries(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        get_or_build_doc_index(f)
        annotate_section_summary(f, line_start=3, summary="Covers A.")
        f.write_text(_SAMPLE + "\n## Section C\n")
        index = get_or_build_doc_index(f)
        assert index["cache_hit"] is False
        assert all(s["summary"] is None for s in index["sections"])

    def test_force_rebuild_bypasses_valid_cache(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        get_or_build_doc_index(f)
        index = get_or_build_doc_index(f, force_rebuild=True)
        assert index["cache_hit"] is False


class TestAnnotateSectionSummary:
    def test_returns_false_when_no_cache_exists_yet(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        assert annotate_section_summary(f, line_start=3, summary="x") is False

    def test_returns_false_for_unmatched_line_start(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        get_or_build_doc_index(f)
        assert annotate_section_summary(f, line_start=999, summary="x") is False

    def test_returns_true_and_persists_on_match(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        get_or_build_doc_index(f)
        assert annotate_section_summary(f, line_start=1, summary="The title.") is True
        cached = load_doc_index(f)
        assert cached["sections"][0]["summary"] == "The title."

    def test_updates_matching_retrieval_section_too(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #109: annotate_section_summary() updated only
        `sections`, leaving the matching `retrieval_sections` entry at
        summary=None -- a caller reading retrieval_sections (the more
        relevant list for a future OKF-style summarizer) couldn't see it."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        get_or_build_doc_index(f)
        assert annotate_section_summary(f, line_start=3, summary="Covers A.") is True
        index = load_doc_index(f)
        retrieval_a = next(s for s in index["retrieval_sections"] if s["heading"] == "Section A")
        assert retrieval_a["summary"] == "Covers A."

    def test_off_level_heading_leaves_retrieval_sections_untouched(self, tmp_path: Path, monkeypatch):
        """line_start=7 is "### A.1" -- present in `sections` but not itself
        a retrieval section's start (retrieval sections are at H2 here).
        Only `sections` should be updated; there's no corresponding
        retrieval section to touch."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        get_or_build_doc_index(f)
        assert annotate_section_summary(f, line_start=7, summary="About A.1.") is True
        index = load_doc_index(f)
        a1 = next(s for s in index["sections"] if s["heading"] == "A.1")
        assert a1["summary"] == "About A.1."
        assert all(s["summary"] is None for s in index["retrieval_sections"])

    def test_concurrent_annotations_of_different_sections_do_not_lose_either_update(
        self, tmp_path: Path, monkeypatch
    ):
        """CodeRabbit PR #109: two concurrent read-modify-write cycles
        annotating different sections of the same document must not race --
        without the lock, thread B's load could happen before thread A's
        save, so thread B's own save would overwrite thread A's summary
        with a stale base index. Injects a delay inside the locked section
        (between load and save) to force a real overlap window if the lock
        weren't actually serializing the two calls."""
        import threading
        import time as time_module

        from studio.utils import doc_index as di

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        index = get_or_build_doc_index(f)
        line_a = index["sections"][1]["line_start"]  # "Section A"
        line_b = index["sections"][3]["line_start"]  # "Section B"

        original_save = di.save_doc_index

        def slow_save(path, saved_index):
            time_module.sleep(0.1)
            original_save(path, saved_index)

        monkeypatch.setattr(di, "save_doc_index", slow_save)

        results: dict = {}

        def run(line_start: int, summary: str) -> None:
            results[line_start] = di.annotate_section_summary(f, line_start, summary)

        t1 = threading.Thread(target=run, args=(line_a, "Summary A"))
        t2 = threading.Thread(target=run, args=(line_b, "Summary B"))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert results == {line_a: True, line_b: True}
        final = di.load_doc_index(f)
        by_line = {s["line_start"]: s["summary"] for s in final["sections"]}
        assert by_line[line_a] == "Summary A"
        assert by_line[line_b] == "Summary B"


class TestReadWithStableEtag:
    def test_retries_when_the_file_changes_mid_read(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #109: a write landing between reading content and
        computing the etag could save headings from the *old* content
        stamped with the *new* etag. Snapshotting before and after the
        read, and retrying on mismatch, closes that window."""
        import studio.utils.doc_index as di

        f = _write(tmp_path)
        etag_sequence = ["a", "b", "b"]  # initial snapshot, then a mismatch, then a stable match
        calls = {"n": 0}

        def fake_compute_etag(_path):
            value = etag_sequence[calls["n"]]
            calls["n"] += 1
            return value

        monkeypatch.setattr(di, "_compute_etag", fake_compute_etag)
        content, etag = di._read_with_stable_etag(f)
        assert content == _SAMPLE
        assert etag == "b"
        assert calls["n"] == 3  # one retry: initial snapshot + two read-and-check cycles

    def test_gives_up_after_max_attempts_under_sustained_contention(self, tmp_path: Path, monkeypatch):
        import studio.utils.doc_index as di

        f = _write(tmp_path)
        calls = {"n": 0}

        def always_different(_path):
            calls["n"] += 1
            return f"etag-{calls['n']}"

        monkeypatch.setattr(di, "_compute_etag", always_different)
        content, etag = di._read_with_stable_etag(f)
        assert content == _SAMPLE  # still returns a real read, not an error
        assert calls["n"] == di._MAX_READ_ATTEMPTS + 1
        assert etag == f"etag-{calls['n']}"


class TestCmdDocIndex:
    def test_missing_file(self, tmp_path: Path, capsys):
        rc = cmd_doc_index([str(tmp_path / "nope.md")])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_unreadable_file_reports_a_clean_error_not_a_raw_traceback(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """CodeRabbit PR #108 (round 2): an OSError from get_or_build_doc_index
        (e.g. a permissions failure or a race where the file vanishes after
        the is_file() check) must use the same clean error contract as a
        UnicodeDecodeError, not escape as a raw traceback."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)

        def _raise_os_error(*_a, **_k):
            raise OSError("permission denied")

        monkeypatch.setattr("studio.commands.doc_index.get_or_build_doc_index", _raise_os_error)
        rc = cmd_doc_index([str(f)])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_basic(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        rc = cmd_doc_index([str(f)])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["cache_hit"] is False
        assert out["section_count"] == 4

    def test_json_output_exposes_retrieval_sections(self, tmp_path: Path, capsys, monkeypatch):
        """CodeRabbit PR #109: cmd_doc_index() built its output from `index`
        but omitted retrieval_sections/section_level -- the new data this
        PR adds was invisible through the CLI."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        rc = cmd_doc_index([str(f)])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["section_level"] == 2
        assert out["retrieval_section_count"] == 2
        assert [s["heading"] for s in out["retrieval_sections"]] == ["Section A", "Section B"]
        assert "hash" in out["retrieval_sections"][0]

    def test_non_utf8_file_reports_a_clean_error_not_a_raw_traceback(self, tmp_path: Path, capsys, monkeypatch):
        """CodeRabbit PR #109: a binary/non-UTF-8 file used to crash with an
        unhandled UnicodeDecodeError; must now report a clean ERROR result,
        consistent with the existing "File not found" pattern."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = tmp_path / "binary.md"
        f.write_bytes(b"\xff\xfe\x00\x01garbage")
        rc = cmd_doc_index([str(f)])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"
        assert "utf-8" in out["message"].lower() or "UTF-8" in out["message"]

    def test_help_explains_how_section_level_is_inferred(self):
        """CodeRabbit PR #109: --help gave no indication that section_level
        is a heuristic, not simply "H1/H2"."""
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            with pytest.raises(SystemExit):
                cmd_doc_index(["--help"])
        assert "most frequently" in buf.getvalue()

    def test_human_output_lists_retrieval_sections(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_doc_index([str(f)])
        finally:
            set_json_mode(orig)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Retrieval sections (level 2, 2 section(s))" in out
        assert "Section A" in out
        assert "Section B" in out

    def test_second_invocation_is_cache_hit(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        cmd_doc_index([str(f)])
        capsys.readouterr()
        rc = cmd_doc_index([str(f)])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["cache_hit"] is True

    def test_rebuild_flag_forces_cache_miss(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        cmd_doc_index([str(f)])
        capsys.readouterr()
        rc = cmd_doc_index([str(f), "--rebuild"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["cache_hit"] is False

    def test_human_output_mode(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_doc_index([str(f)])
        finally:
            set_json_mode(orig)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Doc Index" in out
        assert "cache miss" in out
        assert "Section A" in out

    def test_human_output_mode_cache_hit(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        cmd_doc_index([str(f)])
        capsys.readouterr()
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_doc_index([str(f)])
        finally:
            set_json_mode(orig)
        assert rc == 0
        assert "cache hit" in capsys.readouterr().out

    def test_human_output_mode_with_section_summary(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        cmd_doc_index([str(f)])
        capsys.readouterr()
        assert annotate_section_summary(f, line_start=3, summary="Covers A.") is True
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_doc_index([str(f)])
        finally:
            set_json_mode(orig)
        assert rc == 0
        assert "Covers A." in capsys.readouterr().out
