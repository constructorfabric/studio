"""Tests for the ``[kits.extends]`` declaration of overlay kits (ADR-0025, #427).

Declaration only: the loader parses and validates the block, ``cfs kit normalize``
round-trips it, and nothing here resolves or fetches a base kit.
"""

import shutil
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.utils import kit_model as km
from studio.utils.kit_model import KitExtends, load_kit_model, normalize_kit_source

_FIXTURES = Path(__file__).parent / "fixtures" / "kits" / "overlay"
_MANIFEST = ".cf-studio-kit.toml"
_BASE_BLOCK = (
    '[kits.extends]\n'
    'source = "github:org/studio-sdlc"\n'
    'ref = "v2.3.0"\n'
    'kit = "sdlc"\n'
    'suppress = ["prd-metrics", "adr-extras"]\n'
)


def _copy_fixture(td: Path, name: str, replace: tuple[str, str] = ("", "")) -> Path:
    """Copy fixture kit *name* into *td*, optionally replacing text in its manifest."""
    dest = td / name
    shutil.copytree(_FIXTURES / name, dest)
    if replace[0]:
        manifest = dest / _MANIFEST
        text = manifest.read_text(encoding="utf-8")
        assert replace[0] in text, replace[0]
        manifest.write_text(text.replace(*replace), encoding="utf-8")
    return dest


def _set_manifest_version(kit: Path, version: str) -> None:
    manifest = kit / _MANIFEST
    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(text.replace('manifest_version = "1.0"', f'manifest_version = "{version}"', 1), encoding="utf-8")


class TestExtendsParsing(unittest.TestCase):
    def test_extends_parsed_with_all_fields(self):
        with TemporaryDirectory() as td:
            model = load_kit_model(_copy_fixture(Path(td), "extends-full"))
        self.assertEqual(
            model.extends,
            KitExtends(
                source="github:org/studio-sdlc",
                ref="v2.3.0",
                kit="sdlc",
                suppress=["prd-metrics", "adr-extras"],
            ),
        )
        self.assertEqual(model.warnings, [])

    def test_optional_fields_default_empty(self):
        with TemporaryDirectory() as td:
            kit = _copy_fixture(Path(td), "extends-full")
            manifest = kit / _MANIFEST
            lines = manifest.read_text(encoding="utf-8").splitlines(keepends=True)
            manifest.write_text(
                "".join(ln for ln in lines if not ln.startswith(("kit =", "suppress ="))),
                encoding="utf-8",
            )
            model = load_kit_model(kit)
        self.assertEqual(model.extends, KitExtends(source="github:org/studio-sdlc", ref="v2.3.0"))

    def test_ref_is_required(self):
        with TemporaryDirectory() as td:
            kit = _copy_fixture(Path(td), "extends-full", ('ref = "v2.3.0"\n', ""))
            with self.assertRaisesRegex(ValueError, r"extends.*missing or invalid string field 'ref'"):
                load_kit_model(kit)

    def test_latest_ref_is_rejected_as_unpinned(self):
        for value in ("latest", "LATEST", "Latest"):
            with self.subTest(ref=value), TemporaryDirectory() as td:
                kit = _copy_fixture(Path(td), "extends-full", ('ref = "v2.3.0"', f'ref = "{value}"'))
                with self.assertRaisesRegex(ValueError, r"unpinned.*pin.*tag, branch or commit"):
                    load_kit_model(kit)

    def test_source_is_required(self):
        with TemporaryDirectory() as td:
            kit = _copy_fixture(Path(td), "extends-full", ('source = "github:org/studio-sdlc"\n', ""))
            with self.assertRaisesRegex(ValueError, r"extends.*missing or invalid string field 'source'"):
                load_kit_model(kit)

    def test_suppress_must_be_list_of_strings(self):
        for bad in ('"prd-metrics"', "[1, 2]"):
            with self.subTest(suppress=bad), TemporaryDirectory() as td:
                kit = _copy_fixture(
                    Path(td), "extends-full",
                    ('suppress = ["prd-metrics", "adr-extras"]', f"suppress = {bad}"),
                )
                with self.assertRaisesRegex(ValueError, "suppress.*list of strings"):
                    load_kit_model(kit)

    def test_unknown_extends_key_is_an_error_not_a_silent_drop(self):
        with TemporaryDirectory() as td:
            kit = _copy_fixture(Path(td), "extends-full", ('kit = "sdlc"\n', 'kit = "sdlc"\nsupress = ["a"]\n'))
            with self.assertRaisesRegex(ValueError, r"extends.*unknown field 'supress'.*suppress"):
                load_kit_model(kit)

    def test_extends_must_be_a_table(self):
        with TemporaryDirectory() as td:
            kit = _copy_fixture(Path(td), "plain", ('version = "1.2.3"\n', 'version = "1.2.3"\nextends = "x"\n'))
            _set_manifest_version(kit, "1.1")
            with self.assertRaisesRegex(ValueError, "extends must be a table"):
                load_kit_model(kit)


class TestExtendsVersionGate(unittest.TestCase):
    def test_1_0_manifest_with_extends_fails_at_version_gate(self):
        with TemporaryDirectory() as td:
            with self.assertRaisesRegex(
                ValueError,
                r"extends requires manifest_version '1\.1'.*pipx upgrade constructor-studio",
            ):
                load_kit_model(_copy_fixture(Path(td), "extends-on-10"))

    def test_1_1_manifest_with_extends_loads(self):
        with TemporaryDirectory() as td:
            model = load_kit_model(_copy_fixture(Path(td), "extends-full"))
        self.assertEqual(model.slug, "team-sdlc")

    def test_1_1_manifest_without_extends_loads(self):
        with TemporaryDirectory() as td:
            kit = _copy_fixture(Path(td), "plain")
            _set_manifest_version(kit, "1.1")
            self.assertIsNone(load_kit_model(kit).extends)


class TestExtendsNormalize(unittest.TestCase):
    def test_normalize_preserves_extends_and_is_idempotent(self):
        with TemporaryDirectory() as td:
            kit = _copy_fixture(Path(td), "extends-full")
            model, first = normalize_kit_source(kit)
            self.assertIn('manifest_version = "1.1"', first)
            self.assertIn("[kits.extends]", first)
            (kit / _MANIFEST).write_text(first, encoding="utf-8")
            again_model, second = normalize_kit_source(kit)
        self.assertEqual(first, second)
        self.assertEqual(again_model.extends, model.extends)
        self.assertEqual(model.extends, KitExtends(
            source="github:org/studio-sdlc", ref="v2.3.0", kit="sdlc",
            suppress=["prd-metrics", "adr-extras"],
        ))

    def test_normalize_omits_empty_optional_extends_fields(self):
        with TemporaryDirectory() as td:
            kit = _copy_fixture(Path(td), "plain", (
                'version = "1.2.3"\n',
                'version = "1.2.3"\n\n[kits.extends]\nsource = "../base"\nref = "main"\n',
            ))
            _set_manifest_version(kit, "1.1")
            _, text = normalize_kit_source(kit)
        self.assertNotIn("suppress", text)
        self.assertNotIn("kit =", text)


class TestNoExtendsUnchanged(unittest.TestCase):
    def test_no_extends_model_and_output_have_no_new_keys(self):
        with TemporaryDirectory() as td:
            kit = _copy_fixture(Path(td), "plain")
            model, text = normalize_kit_source(kit)
        self.assertIsNone(model.extends)
        self.assertEqual(model.warnings, [])
        self.assertNotIn("extends", text)
        self.assertIn('manifest_version = "1.0"', text)
        self.assertEqual(text, (
            "# Generated by cfs kit normalize. Review before publishing.\n"
            "\n"
            'manifest_version = "1.0"\n'
            "\n"
            "[[kits]]\n"
            'slug = "team-sdlc"\n'
            'name = "Team SDLC"\n'
            'version = "1.2.3"\n'
            "\n"
            "[[kits.resources]]\n"
            'id = "skill"\n'
            'kind = "skill"\n'
            'source = "SKILL.md"\n'
            'install_path = "SKILL.md"\n'
            'type = "file"\n'
            "user_modifiable = true\n"
            "public = true\n"
            'generated_targets = ["installed"]\n'
        ))


class TestLoadNeverResolvesBase(unittest.TestCase):
    def test_load_kit_model_performs_no_network_or_base_lookup(self):
        def _forbidden(*_a, **_k):
            raise AssertionError("load_kit_model must not fetch or resolve a base kit")

        with TemporaryDirectory() as td:
            kit = _copy_fixture(Path(td), "extends-full")
            with patch("socket.socket", _forbidden), \
                    patch("socket.create_connection", _forbidden), \
                    patch("subprocess.run", _forbidden), \
                    patch("subprocess.Popen", _forbidden), \
                    patch("urllib.request.urlopen", _forbidden):
                model = load_kit_model(kit)
        self.assertEqual(model.extends.source, "github:org/studio-sdlc")
        self.assertEqual([r.id for r in model.resources], ["skill"])
        self.assertFalse(hasattr(km, "resolve_kit_chain"))


if __name__ == "__main__":
    unittest.main()
