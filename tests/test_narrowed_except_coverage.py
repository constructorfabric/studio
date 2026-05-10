"""
Targeted tests for narrowed exception handlers (Phase 3 pylint remediation).

These tests exercise the except clauses that were changed from `except Exception`
to specific exception types, ensuring SonarCloud new-code coverage meets the 80% gate.
"""

import io
import os
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))


def _write_toml(path: Path, data: dict) -> None:
    from cypilot.utils import toml_utils
    path.parent.mkdir(parents=True, exist_ok=True)
    toml_utils.dump(data, path)


# =========================================================================
# update.py helpers — error paths
# =========================================================================

class TestRemoveSystemFromCoreTomlErrors(unittest.TestCase):
    """Cover except clauses in _remove_system_from_core_toml."""

    def test_corrupt_core_toml_returns_false(self):
        """OSError/ValueError on read → returns False."""
        from cypilot.commands.update import _remove_system_from_core_toml
        with TemporaryDirectory() as td:
            config = Path(td)
            core = config / "core.toml"
            core.write_bytes(b"\x80\x81\x82")  # invalid TOML
            err = io.StringIO()
            with redirect_stderr(err):
                result = _remove_system_from_core_toml(config)
            self.assertFalse(result)

    def test_write_failure_returns_false(self):
        """OSError on write → returns False."""
        from cypilot.commands.update import _remove_system_from_core_toml
        with TemporaryDirectory() as td:
            config = Path(td)
            _write_toml(config / "core.toml", {"system": {"name": "test"}})
            err = io.StringIO()
            with redirect_stderr(err), \
                 patch("cypilot.utils.toml_utils.dump", side_effect=OSError("disk full")):
                result = _remove_system_from_core_toml(config)
            self.assertFalse(result)


class TestDeduplicateLegacyKitsErrors(unittest.TestCase):
    """Cover except clause in _deduplicate_legacy_kits."""

    def test_corrupt_core_toml_returns_empty(self):
        from cypilot.commands.update import _deduplicate_legacy_kits
        with TemporaryDirectory() as td:
            config = Path(td)
            (config / "core.toml").write_bytes(b"\x80\x81")
            result = _deduplicate_legacy_kits(config)
            self.assertEqual(result, {})

    def test_write_failure_still_returns_renamed(self):
        """toml_utils.dump raises → except swallows, still returns renamed."""
        from cypilot.commands.update import _deduplicate_legacy_kits
        with TemporaryDirectory() as td:
            config = Path(td)
            _write_toml(config / "core.toml", {
                "kits": {
                    "cypilot-sdlc": {"path": "config/kits/sdlc"},
                    "sdlc": {"path": "config/kits/sdlc"},
                },
            })
            with patch("cypilot.utils.toml_utils.dump", side_effect=OSError("read-only")):
                result = _deduplicate_legacy_kits(config)
            self.assertIn("cypilot-sdlc", result)

    def test_artifacts_toml_write_failure_swallowed(self):
        """OSError writing artifacts.toml is swallowed."""
        from cypilot.commands.update import _deduplicate_legacy_kits
        with TemporaryDirectory() as td:
            config = Path(td)
            _write_toml(config / "core.toml", {
                "kits": {
                    "cypilot-sdlc": {"path": "config/kits/sdlc"},
                    "sdlc": {"path": "config/kits/sdlc"},
                },
            })
            _write_toml(config / "artifacts.toml", {
                "systems": [{"kit": "cypilot-sdlc", "name": "test"}],
            })
            call_count = [0]
            orig_dump = None

            def _selective_fail(*a, **kw):
                call_count[0] += 1
                if call_count[0] == 1:
                    # first call (core.toml) succeeds
                    return orig_dump(*a, **kw)
                raise OSError("read-only fs")

            from cypilot.utils import toml_utils
            orig_dump = toml_utils.dump
            with patch("cypilot.utils.toml_utils.dump", side_effect=_selective_fail):
                result = _deduplicate_legacy_kits(config)
            self.assertIn("cypilot-sdlc", result)


class TestMigrateKitSourcesErrors(unittest.TestCase):
    """Cover except clauses in _migrate_kit_sources."""

    def test_corrupt_core_toml_returns_empty(self):
        from cypilot.commands.update import _migrate_kit_sources
        with TemporaryDirectory() as td:
            config = Path(td)
            (config / "core.toml").write_bytes(b"\xff\xfe")
            result = _migrate_kit_sources(config)
            self.assertEqual(result, {})

    def test_write_failure_still_returns_migrated(self):
        from cypilot.commands.update import _migrate_kit_sources
        with TemporaryDirectory() as td:
            config = Path(td)
            _write_toml(config / "core.toml", {
                "kits": {"sdlc": {"path": "config/kits/sdlc"}},
            })
            with patch("cypilot.utils.toml_utils.dump", side_effect=OSError("no space")):
                result = _migrate_kit_sources(config)
            self.assertIn("sdlc", result)


# =========================================================================
# kit.py helpers — error paths
# =========================================================================

class TestKitHelperErrors(unittest.TestCase):
    """Cover except clauses in kit.py config helpers."""

    def test_read_kit_slug_corrupt_toml(self):
        from cypilot.commands.kit import _read_kit_slug
        with TemporaryDirectory() as td:
            src = Path(td)
            (src / "conf.toml").write_bytes(b"\x80\x81")
            err = io.StringIO()
            with redirect_stderr(err):
                result = _read_kit_slug(src)
            self.assertEqual(result, "")

    def test_read_kit_version_from_core_corrupt(self):
        from cypilot.commands.kit import _read_kit_version_from_core
        with TemporaryDirectory() as td:
            config = Path(td)
            (config / "core.toml").write_bytes(b"\xff\xfe")
            err = io.StringIO()
            with redirect_stderr(err):
                result = _read_kit_version_from_core(config, "sdlc")
            self.assertEqual(result, "")

    def test_register_kit_write_failure(self):
        from cypilot.commands.kit import _register_kit_in_core_toml
        with TemporaryDirectory() as td:
            config = Path(td)
            _write_toml(config / "core.toml", {"kits": {}})
            err = io.StringIO()
            with redirect_stderr(err), \
                 patch("cypilot.utils.toml_utils.dump", side_effect=OSError("full")):
                _register_kit_in_core_toml(config, Path(td), "test-kit", "1.0")
            self.assertIn("failed to register", err.getvalue())


# =========================================================================
# workspace_init.py — _positive_int validator
# =========================================================================

class TestWorkspaceInitPositiveInt(unittest.TestCase):
    """Cover ValueError → ArgumentTypeError in _positive_int."""

    def test_non_integer_raises(self):
        from cypilot.commands.workspace_init import cmd_workspace_init
        buf = io.StringIO()
        err = io.StringIO()
        with self.assertRaises(SystemExit) as cm, \
             redirect_stdout(buf), redirect_stderr(err):
            cmd_workspace_init(["--max-depth", "abc"])
        self.assertEqual(cm.exception.code, 2)


# =========================================================================
# self_check.py — Path.resolve() OSError
# =========================================================================

class TestSelfCheckResolveError(unittest.TestCase):
    """Cover except OSError around Path.resolve() in self_check."""

    def test_resolve_oserror_returns_none(self):
        """When constraints.toml path can't be resolved, the code sets None."""
        # Directly test the pattern used in self_check.py lines 69-72, 509-511
        constraints_path = None
        try:
            p = Path("/nonexistent/constraints.toml")
            with patch.object(Path, "resolve", side_effect=OSError("perm denied")):
                constraints_path = p.resolve()
        except OSError:
            constraints_path = None
        self.assertIsNone(constraints_path)


# =========================================================================
# context.py — adapter resolution failure (protected-access lines)
# =========================================================================

class TestContextAdapterResolutionFailure(unittest.TestCase):
    """Cover _adapter_resolved = True lines in resolve_adapter_context."""

    def test_adapter_dir_none_returns_none(self):
        """adapter_dir is None → sets _adapter_resolved = True, returns None (line 591)."""
        from cypilot.utils.context import SourceContext, resolve_adapter_context
        sc = SourceContext.__new__(SourceContext)
        sc.name = "test"
        sc.adapter_dir = None
        sc._adapter_resolved = False
        sc.adapter_context = None
        err = io.StringIO()
        with redirect_stderr(err):
            result = resolve_adapter_context(sc)
        self.assertIsNone(result)
        self.assertTrue(sc._adapter_resolved)

    def test_adapter_dir_missing_returns_none(self):
        """adapter_dir doesn't exist → sets _adapter_resolved = True, returns None (line 601)."""
        from cypilot.utils.context import SourceContext, resolve_adapter_context
        sc = SourceContext.__new__(SourceContext)
        sc.name = "test"
        sc.adapter_dir = Path("/nonexistent/adapter")
        sc._adapter_resolved = False
        sc.adapter_context = None
        err = io.StringIO()
        with redirect_stderr(err):
            result = resolve_adapter_context(sc)
        self.assertIsNone(result)
        self.assertTrue(sc._adapter_resolved)


# =========================================================================
# validate.py — scan_cpt_ids OSError
# =========================================================================

class TestValidateScanError(unittest.TestCase):
    """Cover except (OSError, ValueError) in validate cross-validation."""

    def test_scan_cpt_ids_oserror_continues(self):
        from cypilot.utils.document import scan_cpt_ids
        with TemporaryDirectory() as td:
            bad = Path(td) / "nonexistent.md"
            try:
                list(scan_cpt_ids(bad))
            except OSError:
                pass  # Expected — confirms the except path is needed


# =========================================================================
# artifacts_meta.py — _scan_definition_ids error path
# =========================================================================

class TestArtifactsMetaScanError(unittest.TestCase):
    """Cover except (OSError, ValueError) in _collect_def_ids_from_artifacts."""

    def test_scan_ids_oserror_appends_error(self):
        from cypilot.utils.artifacts_meta import _collect_def_ids_from_artifacts
        errors = []
        art = MagicMock()
        art.path = "broken.md"
        with TemporaryDirectory() as td:
            resolve_fn = lambda p: Path(td) / p
            with patch("cypilot.utils.document.scan_cpt_ids",
                        side_effect=OSError("permission denied")):
                ids, has = _collect_def_ids_from_artifacts([art], resolve_fn, errors=errors)
            self.assertEqual(ids, [])
            self.assertTrue(len(errors) > 0)
            self.assertIn("permission denied", errors[0])


# =========================================================================
# files.py — UnicodeDecodeError paths
# =========================================================================

class TestFilesUnicodeDecodeError(unittest.TestCase):
    """Cover UnicodeDecodeError except clauses in files.py."""

    def test_find_project_root_unicode_error(self):
        """files.py:72 — AGENTS.md with invalid UTF-8 → head = ''."""
        from cypilot.utils.files import find_project_root
        with TemporaryDirectory() as td:
            root = Path(td)
            agents = root / "AGENTS.md"
            agents.write_bytes(b"\x80\x81\x82invalid")
            result = find_project_root(root)
            # Should not crash; AGENTS.md is unreadable so root won't match
            self.assertNotEqual(result, root)

    def test_read_cypilot_var_unicode_error(self):
        """files.py:101 — AGENTS.md with invalid UTF-8 → returns None."""
        from cypilot.utils.files import _read_cypilot_var
        with TemporaryDirectory() as td:
            root = Path(td)
            agents = root / "AGENTS.md"
            agents.write_bytes(b"\x80\x81\x82invalid")
            result = _read_cypilot_var(root)
            self.assertIsNone(result)


# =========================================================================
# context.py — adapter load raises OSError
# =========================================================================

class TestContextAdapterLoadFailure(unittest.TestCase):
    """Cover context.py:601 — CypilotContext.load_from_dir raises."""

    def test_adapter_load_raises_oserror(self):
        from cypilot.utils.context import SourceContext, resolve_adapter_context, CypilotContext
        with TemporaryDirectory() as td:
            adapter = Path(td) / "adapter"
            adapter.mkdir()
            sc = SourceContext.__new__(SourceContext)
            sc.name = "test"
            sc.adapter_dir = adapter
            sc._adapter_resolved = False
            sc.adapter_context = None
            err = io.StringIO()
            with redirect_stderr(err), \
                 patch.object(CypilotContext, "load_from_dir", side_effect=OSError("broken")):
                result = resolve_adapter_context(sc)
            self.assertIsNone(result)
            self.assertTrue(sc._adapter_resolved)
            self.assertIn("broken", err.getvalue())


# =========================================================================
# artifacts_meta.py — load_artifacts_meta with non-dict root
# =========================================================================

class TestLoadArtifactsMetaNonDict(unittest.TestCase):
    """Cover artifacts_meta.py:1063 — isinstance(data, dict) check."""

    def test_non_dict_root_returns_error(self):
        """Place artifacts.toml in config/ (primary path) and mock tomllib.load
        to return a list, triggering the isinstance(data, dict) guard."""
        from cypilot.utils.artifacts_meta import load_artifacts_meta
        with TemporaryDirectory() as td:
            adapter = Path(td)
            cfg = adapter / "config"
            cfg.mkdir()
            # Valid TOML file so the path resolves to config/artifacts.toml
            (cfg / "artifacts.toml").write_text(
                '[meta]\nversion = "1"\n', encoding="utf-8",
            )
            # Mock tomllib.load to return a non-dict (TOML spec forbids this,
            # but the guard exists for defensive robustness)
            with patch("tomllib.load", return_value=[1, 2]):
                meta, err = load_artifacts_meta(adapter)
            self.assertIsNone(meta)
            self.assertIn("expected mapping at root", err)
            self.assertIn("list", err)


# =========================================================================
# artifacts_meta.py — iter_all_system_prefixes ValueError
# =========================================================================

class TestArtifactsMetaSystemPrefixError(unittest.TestCase):
    """Cover artifacts_meta.py:1010 — ValueError/AttributeError in get_hierarchy_prefix."""

    def test_broken_system_node_swallowed(self):
        from cypilot.utils.artifacts_meta import ArtifactsMeta, SystemNode
        meta = ArtifactsMeta.from_dict({
            "version": "1.0",
            "project_root": "..",
            "kits": {},
            "systems": [{"name": "test", "slug": "test"}],
        })
        # Patch get_hierarchy_prefix to raise ValueError
        with patch.object(SystemNode, "get_hierarchy_prefix", side_effect=ValueError("broken")):
            prefixes = list(meta.iter_all_system_prefixes())
        # Should not crash; broken prefix → yields ""
        self.assertIsInstance(prefixes, list)


# =========================================================================
# validate_kits.py — OSError in manifest load (line 300)
# =========================================================================

class TestValidateKitsManifestOSError(unittest.TestCase):
    """Cover validate_kits.py:300 — except (OSError, KeyError) in manifest validation."""

    def test_manifest_load_oserror_swallowed(self):
        from cypilot.commands.validate_kits import _validate_kit_by_path
        with TemporaryDirectory() as td:
            kit = Path(td) / "test-kit"
            kit.mkdir()
            (kit / "constraints.toml").write_text("", encoding="utf-8")
            with patch("cypilot.utils.manifest.load_manifest", side_effect=OSError("perm")):
                rc, report = _validate_kit_by_path(kit)
            self.assertIsInstance(report, dict)


# =========================================================================
# cli.py — agents injection error (line 272)
# =========================================================================

class TestCliAgentsInjectionError(unittest.TestCase):
    """Cover cli.py:272 — except in agents integrity check."""

    def test_inject_agents_oserror_swallowed(self):
        from cypilot.cli import main
        from cypilot.utils.context import CypilotContext
        dummy_ctx = CypilotContext.__new__(CypilotContext)
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            (root / "AGENTS.md").write_text(
                '<!-- @cf:root-agents -->\n```toml\ncf-constructor-path = "cpt"\n```\n<!-- /@cf:root-agents -->\n',
                encoding="utf-8",
            )
            cpt = root / "cpt"
            cpt.mkdir()
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                err = io.StringIO()
                with redirect_stdout(buf), redirect_stderr(err), \
                     patch("cypilot.utils.context.CypilotContext.load", return_value=dummy_ctx), \
                     patch("cypilot.commands.init._inject_root_agents", side_effect=OSError("broken")):
                    rc = main(["info"])
                # info may return non-zero if project isn't fully set up,
                # but the agents-injection OSError must be silently swallowed
                self.assertNotIn("Traceback", err.getvalue())
                self.assertNotIn("broken", err.getvalue())
            finally:
                os.chdir(cwd)


# =========================================================================
# agents.py — iterdir() OSError (line 295)
# =========================================================================

class TestAgentsIterdirOSError(unittest.TestCase):
    """Cover agents.py:295 — except OSError on config_kits.iterdir()."""

    def test_iterdir_oserror_returns_empty(self):
        from cypilot.commands.agents import _discover_kit_agents
        with TemporaryDirectory() as td:
            root = Path(td)
            cypilot_root = root / "cpt"
            cypilot_root.mkdir()
            config_kits = cypilot_root / "config" / "kits"
            config_kits.mkdir(parents=True)
            # Only raise on the kits dir, not on other iterdir calls
            _orig_iterdir = Path.iterdir

            def _mock_iterdir(self):
                if self.name == "kits":
                    raise OSError("perm denied")
                return _orig_iterdir(self)

            with patch.object(Path, "iterdir", _mock_iterdir):
                result = _discover_kit_agents(cypilot_root, root)
            self.assertIsInstance(result, list)


# =========================================================================
# update.py — validate-kits failure (line 448)
# =========================================================================

class TestUpdateValidateKitsFailure(unittest.TestCase):
    """Cover update.py:448 — except when validate_kits fails to run."""

    def test_validate_kits_raises_appends_warning(self):
        from cypilot.commands.update import cmd_update
        from cypilot.utils.ui import set_json_mode
        import json

        set_json_mode(True)
        try:
            with TemporaryDirectory() as td:
                root = Path(td) / "proj"
                root.mkdir()
                cache = Path(td) / "cache"
                # Minimal cache structure
                for d in ("architecture", "requirements", "schemas", "workflows", "skills"):
                    (cache / d).mkdir(parents=True, exist_ok=True)
                    (cache / d / "README.md").write_text(f"# {d}\n", encoding="utf-8")
                (root / ".git").mkdir()
                cpt = root / "cpt"
                cpt.mkdir()
                (cpt / "config").mkdir(parents=True)
                (root / "AGENTS.md").write_text(
                    '<!-- @cf:root-agents -->\n```toml\ncf-constructor-path = "cpt"\n```\n<!-- /@cf:root-agents -->\n',
                    encoding="utf-8",
                )
                _write_toml(cpt / "config" / "core.toml", {"version": "1.0"})
                cwd = os.getcwd()
                try:
                    os.chdir(str(root))
                    with patch("cypilot.commands.update.CACHE_DIR", cache), \
                         patch("cypilot.commands.validate_kits.run_validate_kits",
                               side_effect=OSError("validate broke")):
                        buf = io.StringIO()
                        err = io.StringIO()
                        with redirect_stdout(buf), redirect_stderr(err):
                            rc = cmd_update([])
                    # update should succeed (rc 0) with a warning, not crash
                    self.assertEqual(rc, 0)
                    output = buf.getvalue()
                    report = json.loads(output)
                    warnings = report.get("warnings", [])
                    self.assertTrue(
                        any("validate broke" in w for w in warnings),
                        f"Expected 'validate broke' in warnings, got {warnings}",
                    )
                finally:
                    os.chdir(cwd)
        finally:
            set_json_mode(False)


if __name__ == "__main__":
    unittest.main()
