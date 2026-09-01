"""Tests for the cached, read-once-per-file document index (doc_index.py).

See constructorfabric/studio#104.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from studio.commands.doc_index import cmd_doc_index
from studio.utils.doc_index import (
    annotate_section_summary,
    build_doc_index,
    get_or_build_doc_index,
    load_doc_index,
    save_doc_index,
)

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

    def test_etag_is_computed_before_reading_content(self, tmp_path: Path, monkeypatch):
        """CodeRabbit PR #108 (round 2): the etag must be captured before the
        content read, not after -- a write landing between the two calls
        would otherwise let the stored etag describe content newer than
        what got parsed, and no later stat comparison could ever detect
        that mismatch. Computing the etag first means a race can only make
        it look older than the parsed content, which a later check always
        catches."""
        from studio.utils import doc_index as doc_index_module

        f = _write(tmp_path)
        call_order = []

        real_compute_etag = doc_index_module._compute_etag
        real_read_text = Path.read_text

        def _tracked_compute_etag(path):
            call_order.append("etag")
            return real_compute_etag(path)

        def _tracked_read_text(self, *args, **kwargs):
            call_order.append("read")
            return real_read_text(self, *args, **kwargs)

        monkeypatch.setattr(doc_index_module, "_compute_etag", _tracked_compute_etag)
        monkeypatch.setattr(Path, "read_text", _tracked_read_text)

        doc_index_module.build_doc_index(f)
        assert call_order == ["etag", "read"]

    def test_skips_headings_in_fenced_code(self, tmp_path: Path):
        content = "# Title\n\n## Real\n\n```bash\n# not a heading\n```\n\n## Also Real\n"
        f = _write(tmp_path, content)
        index = build_doc_index(f)
        assert [s["heading"] for s in index["sections"]] == ["Title", "Real", "Also Real"]


class TestCachePersistence:
    def test_load_returns_none_when_no_cache_exists(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        assert load_doc_index(f) is None

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

    def test_load_returns_none_on_corrupt_cache_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        save_doc_index(f, build_doc_index(f))
        # Corrupt the cache file directly
        cache_dir = tmp_path / ".cache" / "doc-index"
        for cache_file in cache_dir.glob("*.json"):
            cache_file.write_text("{not valid json", encoding="utf-8")
        assert load_doc_index(f) is None

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
        self, tmp_path: Path, monkeypatch
    ):
        """An OSError from find_studio_directory (e.g. an unreadable parent
        directory) must degrade to 'no cache', not raise -- and it must be
        logged, not silently swallowed (see PR #108 review / pylint W9001)."""
        def _raise(_start_path):
            raise OSError("permission denied")

        monkeypatch.setattr("studio.utils.files.find_studio_directory", _raise)
        f = _write(tmp_path)
        save_doc_index(f, build_doc_index(f))  # must no-op, not raise
        assert load_doc_index(f) is None

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


class TestCmdDocIndex:
    def test_missing_file(self, tmp_path: Path, capsys):
        rc = cmd_doc_index([str(tmp_path / "nope.md")])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_non_utf8_file_reports_a_clean_error_not_a_raw_traceback(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """CodeRabbit PR #108 (round 2): a non-UTF-8 file raises
        UnicodeDecodeError inside build_doc_index's read_text -- this must
        surface as a clean exit-code-2 JSON error, the same contract a
        missing file already gets, not an unhandled traceback."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = tmp_path / "bad.md"
        f.write_bytes(b"# Title\n\xff\xfe not valid utf-8\n")
        rc = cmd_doc_index([str(f)])
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
