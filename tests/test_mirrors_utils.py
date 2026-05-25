"""Tests for skills/studio/scripts/studio/utils/mirrors.py.

The skill-engine view of mirror overrides — read-only TOML loader and
substring-substitution helper used by kit network operations. Coverage of
this module is environment-dependent (the production code-path runs only
when the user has ~/.constructor-studio/mirrors.toml or the XDG-equivalent),
so CI Docker (clean home) reported 62% locally while developer hosts with a
populated mirrors.toml reported 92%+. These tests pin the contract
deterministically by mocking the path resolvers.
"""

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.utils import mirrors


class TestXdgPath(unittest.TestCase):
    def test_xdg_path_uses_xdg_config_home_when_set(self):
        with patch.dict("os.environ", {"XDG_CONFIG_HOME": "/custom/xdg"}, clear=False):
            self.assertEqual(
                mirrors._xdg_path(),
                Path("/custom/xdg/constructor-studio/mirrors.toml"),
            )

    def test_xdg_path_falls_back_to_home_config_when_unset(self):
        env = {k: v for k, v in __import__("os").environ.items() if k != "XDG_CONFIG_HOME"}
        with patch.dict("os.environ", env, clear=True):
            path = mirrors._xdg_path()
        self.assertEqual(
            path,
            Path.home() / ".config" / "constructor-studio" / "mirrors.toml",
        )

    def test_brand_home_path_under_dot_constructor_studio(self):
        self.assertEqual(
            mirrors._brand_home_path(),
            Path.home() / ".constructor-studio" / "mirrors.toml",
        )


class TestLoadFile(unittest.TestCase):
    def test_returns_empty_when_file_missing(self):
        with TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "nope.toml"
            self.assertEqual(mirrors._load_file(missing), [])

    def test_returns_empty_on_invalid_toml(self):
        with TemporaryDirectory() as tmpdir:
            broken = Path(tmpdir) / "broken.toml"
            broken.write_text("[unterminated section\n", encoding="utf-8")
            self.assertEqual(mirrors._load_file(broken), [])

    def test_returns_empty_on_oserror(self):
        with TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "x.toml"
            target.write_text("[[mirror]]\nfrom='a'\nto='b'\n", encoding="utf-8")
            with patch.object(Path, "read_text", side_effect=OSError("denied")):
                self.assertEqual(mirrors._load_file(target), [])

    def test_loads_well_formed_mirrors(self):
        with TemporaryDirectory() as tmpdir:
            cfg = Path(tmpdir) / "m.toml"
            cfg.write_text(
                "[[mirror]]\nfrom='github.com/upstream/repo'\nto='git.internal/mirror/repo'\n"
                "[[mirror]]\nfrom='https://foo'\nto='https://bar'\n",
                encoding="utf-8",
            )
            self.assertEqual(
                mirrors._load_file(cfg),
                [
                    ("github.com/upstream/repo", "git.internal/mirror/repo"),
                    ("https://foo", "https://bar"),
                ],
            )

    def test_skips_entries_missing_from_or_to(self):
        with TemporaryDirectory() as tmpdir:
            cfg = Path(tmpdir) / "m.toml"
            cfg.write_text(
                "[[mirror]]\nfrom='ok-from'\nto='ok-to'\n"
                "[[mirror]]\nfrom=''\nto='no-from'\n"
                "[[mirror]]\nfrom='no-to'\nto=''\n"
                "[[mirror]]\nfrom='also-ok'\nto='also-mapped'\n",
                encoding="utf-8",
            )
            self.assertEqual(
                mirrors._load_file(cfg),
                [("ok-from", "ok-to"), ("also-ok", "also-mapped")],
            )


class TestLoadOverrides(unittest.TestCase):
    def _write(self, path: Path, body: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def test_merges_xdg_and_brand_home(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            xdg = root / "xdg.toml"
            brand = root / "brand.toml"
            self._write(xdg, "[[mirror]]\nfrom='a'\nto='xdg-target'\n")
            self._write(brand, "[[mirror]]\nfrom='b'\nto='brand-target'\n")
            with patch.object(mirrors, "_xdg_path", return_value=xdg), \
                    patch.object(mirrors, "_brand_home_path", return_value=brand):
                result = mirrors._load_overrides()
            self.assertEqual(sorted(result), [("a", "xdg-target"), ("b", "brand-target")])

    def test_brand_home_wins_on_duplicate_from(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            xdg = root / "xdg.toml"
            brand = root / "brand.toml"
            self._write(xdg, "[[mirror]]\nfrom='dup'\nto='xdg-value'\n")
            self._write(brand, "[[mirror]]\nfrom='dup'\nto='brand-value'\n")
            with patch.object(mirrors, "_xdg_path", return_value=xdg), \
                    patch.object(mirrors, "_brand_home_path", return_value=brand):
                result = mirrors._load_overrides()
            self.assertEqual(result, [("dup", "brand-value")])


class TestApplyOverride(unittest.TestCase):
    def test_empty_url_returns_unchanged(self):
        self.assertEqual(mirrors.apply_override(""), "")

    def test_no_overrides_returns_unchanged(self):
        with patch.object(mirrors, "_load_overrides", return_value=[]):
            self.assertEqual(mirrors.apply_override("https://github.com/x/y"), "https://github.com/x/y")

    def test_single_substring_replacement(self):
        with patch.object(mirrors, "_load_overrides", return_value=[("github.com", "mirror.example.com")]):
            self.assertEqual(
                mirrors.apply_override("https://github.com/owner/repo"),
                "https://mirror.example.com/owner/repo",
            )

    def test_no_match_returns_unchanged(self):
        with patch.object(mirrors, "_load_overrides", return_value=[("nomatch.example", "elsewhere")]):
            self.assertEqual(
                mirrors.apply_override("https://github.com/owner/repo"),
                "https://github.com/owner/repo",
            )

    def test_multiple_overrides_applied_in_load_order(self):
        # First override transforms 'github.com' -> 'g.intermediate', then second
        # override transforms 'g.intermediate' -> 'final.mirror'. Verifies the
        # function applies every matching override, not just the first.
        with patch.object(
            mirrors,
            "_load_overrides",
            return_value=[
                ("github.com", "g.intermediate"),
                ("g.intermediate", "final.mirror"),
            ],
        ):
            self.assertEqual(
                mirrors.apply_override("https://github.com/o/r"),
                "https://final.mirror/o/r",
            )


if __name__ == "__main__":
    unittest.main()
