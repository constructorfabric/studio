"""
Regression tests for _format_value in toml_utils — float and datetime support.

Covers:
  - float round-trip through dump → tomllib.loads
  - datetime.datetime round-trip through dump → tomllib.loads
  - datetime.date round-trip through dump → tomllib.loads
  - None still raises TypeError (TOML has no null)
  - POSIX flock lock sentinel file is left in place and reusable
  - bool round-trip (true/false) via _format_value
  - dumps() with a multi-line header_comment
  - array-of-tables round-trip
  - quoted keys (keys with spaces) round-trip
  - scalar keys appear before table sections in raw dumps() output
"""

from __future__ import annotations

import datetime
import io
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))

from studio.utils.toml_utils import (
    _format_value,
    _with_core_toml_lock,
    dump,
    dumps,
    load,
    loads,
    parse_toml_from_markdown,
    _deep_merge,
    _validate_lists,
)


def _roundtrip(data: dict) -> dict:
    """Serialize *data* with dumps() then parse back with tomllib."""
    toml_text = dumps(data)
    return tomllib.loads(toml_text)


class TestFormatValueFloat(unittest.TestCase):
    """_format_value correctly serializes float values."""

    def test_float_basic_roundtrip(self):
        """A plain float round-trips through dump → tomllib.loads."""
        result = _roundtrip({"score": 3.14})
        self.assertAlmostEqual(result["score"], 3.14)

    def test_float_negative(self):
        result = _roundtrip({"val": -0.5})
        self.assertAlmostEqual(result["val"], -0.5)

    def test_float_zero(self):
        result = _roundtrip({"val": 0.0})
        self.assertAlmostEqual(result["val"], 0.0)

    def test_float_large(self):
        result = _roundtrip({"val": 1.23456789e100})
        self.assertAlmostEqual(result["val"], 1.23456789e100, delta=1e90)

    def test_format_value_float_produces_repr(self):
        """_format_value(float) uses repr() — preserves precision."""
        val = 1.1
        formatted = _format_value(val)
        self.assertEqual(formatted, repr(val))

    def test_float_in_nested_dict(self):
        result = _roundtrip({"metadata": {"confidence": 0.99}})
        self.assertAlmostEqual(result["metadata"]["confidence"], 0.99)


class TestFormatValueDatetime(unittest.TestCase):
    """_format_value correctly serializes datetime.datetime and datetime.date values."""

    def test_datetime_naive_roundtrip(self):
        """A naive datetime round-trips through dump → tomllib.loads."""
        dt = datetime.datetime(2024, 6, 15, 12, 30, 45)
        result = _roundtrip({"created_at": dt})
        # tomllib parses TOML local-datetime as datetime without timezone
        parsed = result["created_at"]
        self.assertIsInstance(parsed, datetime.datetime)
        self.assertEqual(parsed.year, 2024)
        self.assertEqual(parsed.month, 6)
        self.assertEqual(parsed.day, 15)
        self.assertEqual(parsed.hour, 12)
        self.assertEqual(parsed.minute, 30)
        self.assertEqual(parsed.second, 45)

    def test_datetime_with_microseconds(self):
        dt = datetime.datetime(2025, 1, 1, 0, 0, 0, 500000)
        result = _roundtrip({"ts": dt})
        parsed = result["ts"]
        self.assertEqual(parsed.microsecond, 500000)

    def test_date_roundtrip(self):
        """A datetime.date round-trips through dump → tomllib.loads."""
        d = datetime.date(2026, 5, 22)
        result = _roundtrip({"release_date": d})
        parsed = result["release_date"]
        self.assertIsInstance(parsed, datetime.date)
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.month, 5)
        self.assertEqual(parsed.day, 22)

    def test_format_value_datetime_uses_isoformat(self):
        dt = datetime.datetime(2024, 3, 10, 8, 0, 0)
        formatted = _format_value(dt)
        self.assertEqual(formatted, dt.isoformat())

    def test_format_value_date_uses_isoformat(self):
        d = datetime.date(2024, 3, 10)
        formatted = _format_value(d)
        self.assertEqual(formatted, d.isoformat())


class TestFormatValueNoneStillRaises(unittest.TestCase):
    """None must still raise TypeError — TOML has no null type."""

    def test_none_raises_type_error(self):
        with self.assertRaises(TypeError) as ctx:
            _format_value(None)
        self.assertIn("Unsupported TOML value type", str(ctx.exception))


class TestTomlLocking(unittest.TestCase):
    """Regression tests for _with_core_toml_lock POSIX flock sentinel behavior.

    Verifies that:
    - The .lock sentinel file is left in place after context exit (no TOCTOU race).
    - Sequential acquisitions succeed without exceptions.
    """

    def test_posix_lock_sentinel_left_in_place(self):
        """After releasing the lock, the .lock sentinel file still exists."""
        try:
            import fcntl  # noqa: F401
            _has_fcntl = True
        except ImportError:
            _has_fcntl = False

        if not _has_fcntl:
            self.skipTest("fcntl not available; skipping POSIX lock test")

        with tempfile.TemporaryDirectory() as tmpdir:
            core_toml_path = Path(tmpdir) / "core.toml"
            lock_path = Path(tmpdir) / "core.toml.lock"

            # First acquisition and release
            with _with_core_toml_lock(core_toml_path):
                pass

            # Assert lock sentinel exists
            self.assertTrue(
                lock_path.exists(),
                f"Lock sentinel {lock_path} should exist after context exit",
            )

    def test_sequential_lock_acquisitions_succeed(self):
        """Sequential lock acquisitions (no exception on second acquire)."""
        try:
            import fcntl  # noqa: F401
            _has_fcntl = True
        except ImportError:
            _has_fcntl = False

        if not _has_fcntl:
            self.skipTest("fcntl not available; skipping POSIX lock test")

        with tempfile.TemporaryDirectory() as tmpdir:
            core_toml_path = Path(tmpdir) / "core.toml"

            # First acquisition
            with _with_core_toml_lock(core_toml_path):
                pass

            # Second acquisition should not raise
            try:
                with _with_core_toml_lock(core_toml_path):
                    pass
            except Exception as e:
                self.fail(f"Sequential lock acquisition raised {type(e).__name__}: {e}")


class TestFormatValueControlCharRoundtrip(unittest.TestCase):
    """_format_value must escape control characters so dumps() produces valid TOML.

    This class covers the CR-T9-003 fix: strings containing \\n, \\r, \\t, and
    other U+0000-U+001F characters must round-trip through dumps() → tomllib.loads
    without raising a TOMLDecodeError and must yield the original string value.
    """

    def _roundtrip_str(self, raw: str) -> str:
        """Serialize a single-key dict with a string value, then parse it back."""
        result = _roundtrip({"v": raw})
        return result["v"]

    def test_newline_in_string_roundtrips(self):
        """A string with a literal newline must round-trip correctly."""
        raw = "line1\nline2"
        self.assertEqual(self._roundtrip_str(raw), raw)

    def test_carriage_return_in_string_roundtrips(self):
        """A string with a literal carriage return must round-trip correctly."""
        raw = "a\rb"
        self.assertEqual(self._roundtrip_str(raw), raw)

    def test_tab_in_string_roundtrips(self):
        """A string with a literal tab must round-trip correctly."""
        raw = "col1\tcol2"
        self.assertEqual(self._roundtrip_str(raw), raw)

    def test_combined_control_chars_roundtrip(self):
        """A string with \\n, \\r and \\t together must round-trip correctly."""
        raw = "first\nsecond\r\nthird\t!"
        self.assertEqual(self._roundtrip_str(raw), raw)

    def test_null_byte_roundtrips(self):
        """A string with a null byte (U+0000) must round-trip correctly."""
        raw = "before\x00after"
        self.assertEqual(self._roundtrip_str(raw), raw)

    def test_backspace_formfeed_roundtrip(self):
        """\\b and \\f control characters must round-trip correctly."""
        raw = "a\bb\fc"
        self.assertEqual(self._roundtrip_str(raw), raw)

    def test_existing_backslash_plus_control_char_roundtrips(self):
        """Backslash immediately before a control char must not corrupt the output."""
        raw = "path\\\nvalue"
        self.assertEqual(self._roundtrip_str(raw), raw)


# ---------------------------------------------------------------------------
# CR-T6-019 / CR-T9-004..008 / CR-T9-012..013 additions
# ---------------------------------------------------------------------------

class TestFormatValueBool(unittest.TestCase):
    """_format_value correctly serializes bool values (CR-T9-004)."""

    def test_true_roundtrip(self):
        result = _roundtrip({"flag": True})
        self.assertIs(result["flag"], True)

    def test_false_roundtrip(self):
        result = _roundtrip({"flag": False})
        self.assertIs(result["flag"], False)

    def test_format_value_true_literal(self):
        self.assertEqual(_format_value(True), "true")

    def test_format_value_false_literal(self):
        self.assertEqual(_format_value(False), "false")


class TestDumpsHeaderComment(unittest.TestCase):
    """dumps() emits comment lines before any key-value (CR-T9-005)."""

    def test_single_line_comment_precedes_key(self):
        toml_text = dumps({"k": 1}, header_comment="my comment")
        lines = toml_text.splitlines()
        comment_idx = next(i for i, l in enumerate(lines) if l.startswith("#"))
        kv_idx = next(i for i, l in enumerate(lines) if l.startswith("k"))
        self.assertLess(comment_idx, kv_idx)

    def test_multi_line_comment_all_lines_present(self):
        toml_text = dumps({"k": 1}, header_comment="line1\nline2")
        self.assertIn("# line1", toml_text)
        self.assertIn("# line2", toml_text)
        # Both comment lines precede the key-value pair
        idx_line1 = toml_text.index("# line1")
        idx_line2 = toml_text.index("# line2")
        idx_kv = toml_text.index("k = ")
        self.assertLess(idx_line1, idx_kv)
        self.assertLess(idx_line2, idx_kv)


class TestArrayOfTables(unittest.TestCase):
    """Array-of-tables round-trip (CR-T9-006)."""

    def test_array_of_tables_roundtrip(self):
        data = {"items": [{"name": "a"}, {"name": "b"}]}
        result = _roundtrip(data)
        self.assertEqual(result["items"][0]["name"], "a")
        self.assertEqual(result["items"][1]["name"], "b")

    def test_array_of_tables_length(self):
        data = {"items": [{"name": "a"}, {"name": "b"}]}
        result = _roundtrip(data)
        self.assertEqual(len(result["items"]), 2)


class TestQuotedKeys(unittest.TestCase):
    """Keys with spaces are quoted and round-trip correctly (CR-T9-007)."""

    def test_key_with_space_roundtrips(self):
        data = {"key with space": 42}
        result = _roundtrip(data)
        self.assertEqual(result["key with space"], 42)

    def test_quoted_key_present_in_raw_output(self):
        toml_text = dumps({"key with space": 42})
        self.assertIn('"key with space"', toml_text)


class TestKeyOrdering(unittest.TestCase):
    """Scalar keys appear before table sections in raw dumps() output (CR-T9-008)."""

    def test_scalar_before_table(self):
        data = {"b_key": 1, "a_table": {"x": 2}}
        toml_text = dumps(data)
        idx_scalar = toml_text.index("b_key")
        idx_table = toml_text.index("[a_table]")
        self.assertLess(idx_scalar, idx_table)

    def test_scalar_value_correct_after_roundtrip(self):
        data = {"b_key": 1, "a_table": {"x": 2}}
        result = _roundtrip(data)
        self.assertEqual(result["b_key"], 1)
        self.assertEqual(result["a_table"]["x"], 2)


class TestLoadAndDumpFunctions(unittest.TestCase):
    """load() and dump() cover file I/O paths (lines 47-48, 115-116)."""

    def test_load_reads_toml_file(self):
        """load() reads a TOML file from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "test.toml"
            p.write_bytes(b'key = "hello"\n')
            result = load(p)
            self.assertEqual(result, {"key": "hello"})

    def test_dump_writes_toml_file(self):
        """dump() serializes and writes a TOML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "out.toml"
            dump({"answer": 42}, p)
            content = p.read_text(encoding="utf-8")
            self.assertIn("answer = 42", content)

    def test_dump_creates_parent_dirs(self):
        """dump() creates missing parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "sub" / "dir" / "out.toml"
            dump({"x": 1}, p)
            self.assertTrue(p.exists())


class TestLoadsFunction(unittest.TestCase):
    """loads() wraps tomllib.loads — covers line 42."""

    def test_loads_returns_dict(self):
        result = loads('key = "value"\n')
        self.assertEqual(result, {"key": "value"})

    def test_loads_integer(self):
        result = loads("count = 42\n")
        self.assertEqual(result["count"], 42)


class TestParseTomlFromMarkdownInvalidFence(unittest.TestCase):
    """parse_toml_from_markdown skips invalid TOML blocks — covers lines 71-72."""

    def test_invalid_toml_block_skipped(self):
        """An invalid TOML fence is silently skipped; valid ones are merged."""
        md = "```toml\nBAD TOML @@@ = =\n```\n```toml\nkey = 1\n```\n"
        result = parse_toml_from_markdown(md)
        self.assertEqual(result.get("key"), 1)

    def test_only_invalid_fence_returns_empty(self):
        md = "```toml\n[[invalid[\n```\n"
        result = parse_toml_from_markdown(md)
        self.assertEqual(result, {})


class TestDeepMergeNestedDict(unittest.TestCase):
    """_deep_merge merges nested dicts recursively — covers line 82."""

    def test_nested_dicts_merged(self):
        base = {"a": {"x": 1, "y": 2}}
        override = {"a": {"y": 99, "z": 3}}
        _deep_merge(base, override)
        self.assertEqual(base["a"]["x"], 1)
        self.assertEqual(base["a"]["y"], 99)
        self.assertEqual(base["a"]["z"], 3)

    def test_nested_dict_override_scalar_replaces(self):
        base = {"a": 1}
        override = {"a": {"nested": True}}
        _deep_merge(base, override)
        self.assertEqual(base["a"], {"nested": True})


class TestValidateListsMixed(unittest.TestCase):
    """_validate_lists raises TypeError for mixed lists — covers line 128."""

    def test_mixed_list_raises_type_error(self):
        with self.assertRaises(TypeError) as ctx:
            _validate_lists([{"key": "val"}, "scalar"])
        self.assertIn("cannot mix", str(ctx.exception))

    def test_nested_mixed_list_raises(self):
        with self.assertRaises(TypeError):
            _validate_lists({"items": [{"k": 1}, 42]})

    def test_pure_dict_list_ok(self):
        _validate_lists([{"a": 1}, {"b": 2}])  # must not raise

    def test_pure_scalar_list_ok(self):
        _validate_lists([1, 2, 3])  # must not raise


class TestFormatValueNonFiniteFloat(unittest.TestCase):
    """_format_value raises TypeError for non-finite floats — covers line 191."""

    def test_nan_raises(self):
        import math
        with self.assertRaises(TypeError) as ctx:
            _format_value(float("nan"))
        self.assertIn("non-finite", str(ctx.exception))

    def test_inf_raises(self):
        with self.assertRaises(TypeError) as ctx:
            _format_value(float("inf"))
        self.assertIn("non-finite", str(ctx.exception))

    def test_neg_inf_raises(self):
        with self.assertRaises(TypeError) as ctx:
            _format_value(float("-inf"))
        self.assertIn("non-finite", str(ctx.exception))


class TestFormatValueStringEscapeQuote(unittest.TestCase):
    """_format_value escapes double-quote characters — covers line 202."""

    def test_double_quote_in_string_roundtrips(self):
        """A string with a literal double-quote must round-trip correctly."""
        raw = 'say "hello"'
        result = _roundtrip({"msg": raw})
        self.assertEqual(result["msg"], raw)

    def test_double_quote_escaped_in_output(self):
        formatted = _format_value('he said "hi"')
        self.assertIn('\\"', formatted)


class TestFormatValueList(unittest.TestCase):
    """_format_value handles plain (non-table) lists — covers lines 219-220."""

    def test_scalar_list_roundtrip(self):
        result = _roundtrip({"tags": ["a", "b", "c"]})
        self.assertEqual(result["tags"], ["a", "b", "c"])

    def test_integer_list_roundtrip(self):
        result = _roundtrip({"nums": [1, 2, 3]})
        self.assertEqual(result["nums"], [1, 2, 3])

    def test_empty_list_roundtrip(self):
        result = _roundtrip({"empty": []})
        self.assertEqual(result["empty"], [])


if __name__ == "__main__":
    unittest.main()
