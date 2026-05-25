"""Tests for the content_language utility module.

Covers:
- build_allowed_ranges() — merging Unicode ranges for language codes
- is_allowed() — binary-search character check
- scan_file() — single-file scan with fences and skip patterns
- scan_paths() — recursive directory scan
- LangViolation helpers (bad_chars_preview, line_preview)
- LangScanError on unreadable files
"""

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory, NamedTemporaryFile

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))

from studio.utils.content_language import (
    SCRIPT_RANGES,
    SUPPORTED_LANGUAGES,
    LangScanError,
    LangViolation,
    build_allowed_ranges,
    is_allowed,
    scan_file,
    scan_paths,
)


class TestBuildAllowedRanges(unittest.TestCase):
    """build_allowed_ranges() merges language ranges correctly."""

    def test_english_ranges_include_ascii(self):
        ranges = build_allowed_ranges(["en"])
        self.assertTrue(is_allowed(ord("A"), ranges))
        self.assertTrue(is_allowed(ord("z"), ranges))
        self.assertTrue(is_allowed(ord("0"), ranges))

    def test_english_blocks_cyrillic(self):
        ranges = build_allowed_ranges(["en"])
        self.assertFalse(is_allowed(0x0410, ranges))  # Cyrillic А

    def test_russian_allows_cyrillic(self):
        ranges = build_allowed_ranges(["en", "ru"])
        self.assertTrue(is_allowed(0x0410, ranges))  # Cyrillic А

    def test_unknown_code_silently_skipped(self):
        ranges = build_allowed_ranges(["en", "xx_INVALID"])
        self.assertIsInstance(ranges, list)
        self.assertTrue(is_allowed(ord("a"), ranges))

    def test_empty_list_allows_only_common(self):
        ranges = build_allowed_ranges([])
        # Common ranges (emoji, ZW, BOM) should still be present
        self.assertIsInstance(ranges, list)

    def test_result_is_sorted(self):
        ranges = build_allowed_ranges(["en", "ru", "ar"])
        starts = [r[0] for r in ranges]
        self.assertEqual(starts, sorted(starts))

    def test_ranges_are_non_overlapping_after_merge(self):
        """No two intervals in the result should overlap."""
        ranges = build_allowed_ranges(["en", "ru", "ar", "zh"])
        for i in range(len(ranges) - 1):
            self.assertLess(
                ranges[i][1], ranges[i + 1][0],
                f"Overlap between {ranges[i]} and {ranges[i+1]}",
            )

    def test_overlapping_inner_range_does_not_cause_false_negative(self):
        """A code point inside the outer range but above the inner range must be allowed.

        0x200B-0x200F is nested inside 0x2000-0x206F in _COMMON_RANGES.
        Before merging, binary search could land on (0x200B, 0x200F) and
        wrongly reject 0x2010 (HYPHEN, inside the outer range).
        After merging both collapse to (0x2000, 0x206F) so 0x2010 is allowed.
        """
        ranges = build_allowed_ranges(["en"])
        self.assertTrue(
            is_allowed(0x2010, ranges),  # HYPHEN — inside 0x2000-0x206F
            "0x2010 should be allowed by the merged General Punctuation range",
        )

    def test_case_insensitive_lang_code(self):
        ranges_lower = build_allowed_ranges(["ru"])
        ranges_upper = build_allowed_ranges(["RU"])
        self.assertEqual(ranges_lower, ranges_upper)


class TestIsAllowed(unittest.TestCase):
    """is_allowed() binary search works for boundary and interior values."""

    def _en_ranges(self):
        return build_allowed_ranges(["en"])

    def test_ascii_letter_allowed(self):
        self.assertTrue(is_allowed(ord("A"), self._en_ranges()))

    def test_newline_is_ascii(self):
        self.assertTrue(is_allowed(ord("\n"), self._en_ranges()))

    def test_emoji_always_allowed(self):
        ranges = build_allowed_ranges(["en"])
        self.assertTrue(is_allowed(0x1F300, ranges))  # 🌀 start of emoji range
        self.assertTrue(is_allowed(0x1F600, ranges))  # 😀

    def test_range_start_inclusive(self):
        ranges = build_allowed_ranges(["ru"])
        self.assertTrue(is_allowed(0x0400, ranges))  # start of Cyrillic

    def test_range_end_inclusive(self):
        ranges = build_allowed_ranges(["ru"])
        self.assertTrue(is_allowed(0x04FF, ranges))  # end of Cyrillic

    def test_empty_ranges_nothing_allowed(self):
        # Only common ranges would match emoji etc., but CJK would not
        ranges = build_allowed_ranges([])
        self.assertFalse(is_allowed(0x4E00, ranges))  # CJK ideograph

    def test_boundary_just_below_range(self):
        # 0x0400 is Cyrillic start; 0x03FF is not in ru ranges but is in en (Greek)
        en_ranges = build_allowed_ranges(["en"])
        # 0x0400 is NOT in en ranges
        self.assertFalse(is_allowed(0x0400, en_ranges))

    def test_between_ranges_not_allowed(self):
        # Gap between ASCII (0x007F) and Latin-1 Sup (0x0080) — none; they are contiguous.
        # Check something clearly outside all ranges for "en"
        ranges = build_allowed_ranges(["en"])
        self.assertFalse(is_allowed(0x0900, ranges))  # Devanagari, not in en


class TestLangViolation(unittest.TestCase):
    """LangViolation helper methods."""

    def _make(self, chars, line="содержит"):
        return LangViolation(
            path=Path("test.md"),
            lineno=1,
            line=line,
            chars=[(ord(ch), ch) for ch in chars],
        )

    def test_bad_chars_preview_short(self):
        v = self._make("АБВ")
        self.assertEqual(v.bad_chars_preview(), "АБВ")

    def test_bad_chars_preview_truncates(self):
        v = self._make("АБВГДЕЖЗИ")  # 9 chars
        preview = v.bad_chars_preview(limit=4)
        self.assertEqual(preview, "АБВГ")

    def test_line_preview_short(self):
        v = self._make("А", line="Hello world")
        self.assertEqual(v.line_preview(), "Hello world")

    def test_line_preview_truncates_long_line(self):
        long_line = "X" * 120
        v = self._make("А", line=long_line)
        preview = v.line_preview(limit=90)
        self.assertTrue(preview.endswith("…"))
        self.assertLessEqual(len(preview), 92)

    def test_line_preview_strips_leading_whitespace(self):
        v = self._make("А", line="  leading spaces")
        self.assertEqual(v.line_preview(), "leading spaces")


class TestScanFile(unittest.TestCase):
    """scan_file() — various document patterns."""

    def _write_and_scan(self, content: str, langs=None):
        if langs is None:
            langs = ["en"]
        ranges = build_allowed_ranges(langs)
        with NamedTemporaryFile(suffix=".md", mode="w", encoding="utf-8", delete=False) as f:
            f.write(content)
            path = Path(f.name)
        try:
            return scan_file(path, ranges)
        finally:
            path.unlink(missing_ok=True)

    def test_clean_english_file(self):
        violations = self._write_and_scan("# Hello\n\nThis is plain English text.\n")
        self.assertEqual(violations, [])

    def test_cyrillic_detected_in_english_doc(self):
        violations = self._write_and_scan("# Title\n\nПривет мир\n")
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].lineno, 3)

    def test_cyrillic_allowed_when_ru_configured(self):
        violations = self._write_and_scan("# Title\n\nПривет мир\n", langs=["en", "ru"])
        self.assertEqual(violations, [])

    def test_fenced_code_block_skipped(self):
        content = "# Title\n\n```\nПривет\n```\nAfter fence\n"
        violations = self._write_and_scan(content)
        self.assertEqual(violations, [])

    def test_tilde_fence_skipped(self):
        content = "~~~\nБлок\n~~~\n"
        violations = self._write_and_scan(content)
        self.assertEqual(violations, [])

    def test_nested_fence_opens_and_closes(self):
        # Opening fence closes the scan; a second fence re-opens outside mode
        content = "```\nПривет\n```\nАнглийский\n"
        violations = self._write_and_scan(content)
        # "Английский" is OUTSIDE the fence (after second fence marker)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].lineno, 4)

    def test_html_comment_line_skipped(self):
        content = "<!-- Комментарий -->\n"
        violations = self._write_and_scan(content)
        self.assertEqual(violations, [])

    def test_cpt_marker_line_skipped(self):
        content = "@cpt-begin:cpt-cypilot-flow-test:p1:inst-step\nEnglish text.\n"
        violations = self._write_and_scan(content)
        self.assertEqual(violations, [])

    def test_traceability_table_row_skipped(self):
        content = "| Feature | `cpt-cypilot-test:p1` | Done |\n"
        violations = self._write_and_scan(content)
        self.assertEqual(violations, [])

    def test_multiple_violations_on_different_lines(self):
        content = "# Title\n\nПривет\nДругая строка\nEnglish\n"
        violations = self._write_and_scan(content)
        self.assertEqual(len(violations), 2)
        linenos = {v.lineno for v in violations}
        self.assertIn(3, linenos)
        self.assertIn(4, linenos)

    def test_violation_contains_correct_chars(self):
        violations = self._write_and_scan("Привет\n")
        self.assertGreater(len(violations[0].chars), 0)
        char_values = [cp for cp, _ in violations[0].chars]
        self.assertIn(ord("П"), char_values)

    def test_lang_scan_error_on_unreadable_file(self):
        ranges = build_allowed_ranges(["en"])
        missing = Path("/nonexistent/path/file.md")
        with self.assertRaises(LangScanError) as ctx:
            scan_file(missing, ranges)
        self.assertIs(ctx.exception.path, missing)
        self.assertIsNotNone(ctx.exception.cause)

    def test_empty_file_no_violations(self):
        violations = self._write_and_scan("")
        self.assertEqual(violations, [])

    def test_four_backtick_fence(self):
        content = "````\nПривет\n````\n"
        violations = self._write_and_scan(content)
        self.assertEqual(violations, [])


class TestScanPaths(unittest.TestCase):
    """scan_paths() — files, directories, extension filtering."""

    def setUp(self):
        self._tmpdir = TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.ranges = build_allowed_ranges(["en"])

    def tearDown(self):
        self._tmpdir.cleanup()

    def _write(self, rel: str, content: str):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def test_scan_single_md_file(self):
        p = self._write("doc.md", "Привет\n")
        violations = scan_paths([p], self.ranges)
        self.assertEqual(len(violations), 1)

    def test_skip_non_md_file(self):
        p = self._write("script.py", "Привет\n")
        violations = scan_paths([p], self.ranges)
        self.assertEqual(violations, [])

    def test_scan_directory_recursive(self):
        self._write("a/b/c.md", "Привет\n")
        self._write("a/b/d.md", "English only\n")
        violations = scan_paths([self.root], self.ranges)
        self.assertEqual(len(violations), 1)

    def test_custom_extensions(self):
        self._write("notes.txt", "Привет\n")
        violations = scan_paths([self.root], self.ranges, extensions=[".txt"])
        self.assertEqual(len(violations), 1)

    def test_empty_directory(self):
        empty = self.root / "empty"
        empty.mkdir()
        violations = scan_paths([empty], self.ranges)
        self.assertEqual(violations, [])

    def test_nonexistent_path_skipped(self):
        missing = self.root / "does_not_exist.md"
        violations = scan_paths([missing], self.ranges)
        self.assertEqual(violations, [])

    def test_multiple_roots(self):
        p1 = self._write("one.md", "Привет\n")
        p2 = self._write("two.md", "English\n")
        violations = scan_paths([p1, p2], self.ranges)
        self.assertEqual(len(violations), 1)

    def test_ignore_pattern_skips_file(self):
        """Files matching ignore_patterns are not scanned."""
        p = self._write("translations/ru.md", "Привет\n")
        violations = scan_paths([self.root], self.ranges, ignore_patterns=["*/translations/*"])
        self.assertEqual(violations, [])

    def test_ignore_pattern_does_not_skip_other_files(self):
        """Only matching files are skipped; others are still scanned."""
        self._write("translations/ru.md", "Привет\n")
        self._write("docs/guide.md", "Привет\n")
        violations = scan_paths([self.root], self.ranges, ignore_patterns=["*/translations/*"])
        self.assertEqual(len(violations), 1)
        self.assertIn("guide.md", str(violations[0].path))

    def test_ignore_pattern_empty_list_scans_all(self):
        p = self._write("doc.md", "Привет\n")
        violations = scan_paths([p], self.ranges, ignore_patterns=[])
        self.assertEqual(len(violations), 1)


class TestSupportedLanguages(unittest.TestCase):
    """SUPPORTED_LANGUAGES constant is complete and sorted."""

    def test_contains_common_languages(self):
        self.assertIn("en", SUPPORTED_LANGUAGES)
        self.assertIn("ru", SUPPORTED_LANGUAGES)
        self.assertIn("ar", SUPPORTED_LANGUAGES)

    def test_matches_script_ranges_keys(self):
        self.assertEqual(sorted(SUPPORTED_LANGUAGES), sorted(SCRIPT_RANGES.keys()))

    def test_is_sorted(self):
        self.assertEqual(SUPPORTED_LANGUAGES, sorted(SUPPORTED_LANGUAGES))


if __name__ == "__main__":
    unittest.main()
