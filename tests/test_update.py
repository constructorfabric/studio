"""
Tests for commands/update.py — full update pipeline, dry-run, version drift, error paths.
"""

import io
import json
import os
import shutil
import sys
import unittest
from contextlib import contextmanager
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))


def _write_toml(path: Path, data: dict) -> None:
    from studio.utils import toml_utils
    path.parent.mkdir(parents=True, exist_ok=True)
    toml_utils.dump(data, path)


def _make_cache(cache_dir: Path, kit_version: int = 1) -> None:
    """Create a realistic ~/.cypilot/cache for update tests."""
    for d in ("architecture", "requirements", "schemas", "workflows", "skills"):
        (cache_dir / d).mkdir(parents=True, exist_ok=True)
        (cache_dir / d / "README.md").write_text(f"# {d}\n", encoding="utf-8")
    # Kit as direct file package (no blueprints)
    kit_dir = cache_dir / "kits" / "sdlc"
    kit_dir.mkdir(parents=True, exist_ok=True)
    (kit_dir / "artifacts" / "PRD").mkdir(parents=True)
    (kit_dir / "artifacts" / "PRD" / "template.md").write_text(
        "# Product Requirements\n", encoding="utf-8",
    )
    (kit_dir / "workflows").mkdir(exist_ok=True)
    scripts_dir = kit_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "helper.py").write_text("# helper\n", encoding="utf-8")
    (kit_dir / "SKILL.md").write_text(
        "# Kit sdlc\nKit skill instructions.\n", encoding="utf-8",
    )
    (kit_dir / "constraints.toml").write_text(
        "[naming]\npattern = 'sdlc-*'\n", encoding="utf-8",
    )
    _write_toml(kit_dir / "conf.toml", {
        "version": kit_version,
    })
    (cache_dir / "version.toml").write_text(
        '[cfs]\nversion = "v1.0.0"\n',
        encoding="utf-8",
    )


def _init_project(root: Path, cache_dir: Path) -> Path:
    """Run init to create a fully initialized project.

    Mocks GitHub download to use cache kit source (via a temp copy so init's
    cleanup of the download dir doesn't destroy the cache).
    Strips GitHub source from core.toml so cmd_update uses cache fallback.
    """
    from studio.cli import main
    import tempfile
    (root / ".git").mkdir(exist_ok=True)
    # Copy kit source to a temp dir — init will delete kit_src.parent after install
    tmp_dl = Path(tempfile.mkdtemp())
    kit_copy = tmp_dl / "sdlc"
    shutil.copytree(cache_dir / "kits" / "sdlc", kit_copy)
    cwd = os.getcwd()
    try:
        os.chdir(str(root))
        with (
            patch("studio.commands.init.CACHE_DIR", cache_dir),
            patch(
                "studio.commands.kit._download_kit_from_github",
                return_value=(kit_copy, "1.0.0"),
            ),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["init", "--yes"])
            assert rc == 0, f"init failed: {buf.getvalue()}"
    finally:
        os.chdir(cwd)
    # Remove GitHub source from core.toml so cmd_update uses cache fallback
    adapter = root / ".cf-studio"
    core_toml = adapter / "config" / "core.toml"
    if core_toml.is_file():
        import tomllib
        from studio.utils import toml_utils
        with open(core_toml, "rb") as f:
            data = tomllib.load(f)
        for kit_data in data.get("kits", {}).values():
            kit_data.pop("source", None)
        toml_utils.dump(data, core_toml)
    return adapter


# =========================================================================
# Helpers
# =========================================================================

class TestUpdateHelpers(unittest.TestCase):
    """Unit tests for update.py helper functions."""

    def test_ensure_file_creates_when_missing(self):
        from studio.commands.update import _ensure_file
        with TemporaryDirectory() as td:
            p = Path(td) / "new.md"
            actions = {}
            _ensure_file(p, "content", actions, "test_key")
            self.assertEqual(actions["test_key"], "created")
            self.assertEqual(p.read_text(encoding="utf-8"), "content")

    def test_ensure_file_preserves_existing(self):
        from studio.commands.update import _ensure_file
        with TemporaryDirectory() as td:
            p = Path(td) / "existing.md"
            p.write_text("old", encoding="utf-8")
            actions = {}
            _ensure_file(p, "new content", actions, "test_key")
            self.assertEqual(actions["test_key"], "preserved")
            self.assertEqual(p.read_text(encoding="utf-8"), "old")

    def test_config_readme_content(self):
        from studio.commands.update import _config_readme_content
        content = _config_readme_content()
        self.assertIn("config", content.lower())
        self.assertIn("core.toml", content)

    def test_read_conf_version(self):
        from studio.commands.update import _read_conf_version
        with TemporaryDirectory() as td:
            p = Path(td) / "conf.toml"
            _write_toml(p, {"version": 3})
            self.assertEqual(_read_conf_version(p), 3)

    def test_read_conf_version_missing(self):
        from studio.commands.update import _read_conf_version
        self.assertEqual(_read_conf_version(Path("/nonexistent")), 0)

    def test_read_conf_version_no_key(self):
        from studio.commands.update import _read_conf_version
        with TemporaryDirectory() as td:
            p = Path(td) / "conf.toml"
            _write_toml(p, {"other": "data"})
            self.assertEqual(_read_conf_version(p), 0)

    def test_remove_system_locks_full_read_modify_write_cycle(self):
        """Concurrent core.toml changes made before lock acquisition are preserved."""
        from studio.commands.update import _remove_system_from_core_toml
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            config_dir = Path(td)
            core_toml = config_dir / "core.toml"
            _write_toml(core_toml, {
                "system": {"name": "legacy"},
                "kits": {"sdlc": {"path": "config/kits/sdlc"}},
            })

            @contextmanager
            def fake_lock(_path):
                _write_toml(core_toml, {
                    "system": {"name": "legacy"},
                    "kits": {
                        "sdlc": {"path": "config/kits/sdlc"},
                        "custom": {"path": "config/kits/custom"},
                    },
                })
                yield

            with patch.object(toml_utils, "_with_core_toml_lock", fake_lock):
                self.assertTrue(_remove_system_from_core_toml(config_dir))

            data = toml_utils.load(core_toml)
            self.assertNotIn("system", data)
            self.assertIn("custom", data["kits"])


# =========================================================================
# cmd_update error paths
# =========================================================================

class TestCmdUpdateErrors(unittest.TestCase):
    """Error handling in cmd_update."""

    def test_no_project_root(self):
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            cwd = os.getcwd()
            try:
                os.chdir(td)
                buf = io.StringIO()
                err = io.StringIO()
                with redirect_stdout(buf), redirect_stderr(err):
                    rc = cmd_update([])
                self.assertEqual(rc, 1)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "ERROR")
            finally:
                os.chdir(cwd)

    def test_no_cypilot_var(self):
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            (root / "AGENTS.md").write_text("# no toml\n", encoding="utf-8")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                err = io.StringIO()
                with redirect_stdout(buf), redirect_stderr(err):
                    rc = cmd_update([])
                self.assertEqual(rc, 1)
            finally:
                os.chdir(cwd)

    def test_cypilot_dir_missing(self):
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            (root / "AGENTS.md").write_text(
                '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "cpt"\n```\n<!-- /@cf:root-agents -->\n',
                encoding="utf-8",
            )
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                buf = io.StringIO()
                err = io.StringIO()
                with redirect_stdout(buf), redirect_stderr(err):
                    rc = cmd_update([])
                self.assertEqual(rc, 1)
            finally:
                os.chdir(cwd)

    def test_no_cache(self):
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            cpt = root / "cpt"
            cpt.mkdir()
            (root / "AGENTS.md").write_text(
                '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "cpt"\n```\n<!-- /@cf:root-agents -->\n',
                encoding="utf-8",
            )
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                fake_cache = Path(td) / "nonexistent"
                with patch("studio.commands.update.CACHE_DIR", fake_cache):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["--with-kits", "yes"])
                self.assertEqual(rc, 1)
            finally:
                os.chdir(cwd)

    def test_malformed_gitignore_returns_controlled_error(self):
        from studio.commands.update import cmd_update

        with TemporaryDirectory() as td:
            root = Path(td)
            cache = root / "cache"
            _make_cache(cache)
            (root / ".git").mkdir()
            (root / "AGENTS.md").write_text(
                '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = ".cf-studio"\n```\n<!-- /@cf:root-agents -->\n',
                encoding="utf-8",
            )
            (root / ".gitignore").write_text(
                "# existing\n# BEGIN Constructor Studio\n",
                encoding="utf-8",
            )
            studio_dir = root / ".cf-studio"
            config_dir = studio_dir / "config"
            config_dir.mkdir(parents=True)
            _write_toml(config_dir / "core.toml", {
                "version": "1.0",
                "project_root": "..",
                "install": {
                    "kit_tracking": "tracked",
                    "runtime_tracking": "ignored",
                    "agent_tracking": "ignored",
                },
                "kits": {},
            })

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with patch("studio.commands.update.CACHE_DIR", cache):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["-y"])
                self.assertEqual(rc, 1)
                result = json.loads(buf.getvalue())
                self.assertEqual(result["status"], "ERROR")
                self.assertEqual(result["errors"][0]["path"], ".gitignore")
                self.assertIn("malformed", result["errors"][0]["error"])
            finally:
                os.chdir(cwd)

    def test_update_preserves_runtime_and_agent_tracking(self):
        from studio.commands.update import cmd_update
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            root = Path(td)
            cache = root / "cache"
            _make_cache(cache)
            (root / ".git").mkdir()
            (root / "AGENTS.md").write_text(
                '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = ".cf-studio"\n```\n<!-- /@cf:root-agents -->\n',
                encoding="utf-8",
            )
            studio_dir = root / ".cf-studio"
            config_dir = studio_dir / "config"
            config_dir.mkdir(parents=True)
            core_toml = config_dir / "core.toml"
            _write_toml(core_toml, {
                "version": "1.0",
                "project_root": "..",
                "install": {
                    "kit_tracking": "tracked",
                    "runtime_tracking": "tracked",
                    "agent_tracking": "tracked",
                },
                "kits": {},
            })

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with patch("studio.commands.update.CACHE_DIR", cache):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["-y"])
                self.assertEqual(rc, 0, buf.getvalue())
                install = toml_utils.load(core_toml)["install"]
                self.assertEqual(install["runtime_tracking"], "tracked")
                self.assertEqual(install["agent_tracking"], "tracked")
            finally:
                os.chdir(cwd)

    def test_cmd_update_handles_unexpected_exception_type(self):
        """Regression: update_kit raising TypeError must not surface as UnboundLocalError.

        The except clause in cmd_update only catches (OSError, ValueError, KeyError,
        RuntimeError).  A TypeError propagates outward.  The kit_r variable is
        initialized before the try block so there should be no UnboundLocalError.

        Test setup note: _migrate_kit_sources is patched to return {} to prevent
        it from adding a github: source to the kit entry (which would trigger a
        download attempt that fails before update_kit is called).  The cache
        fallback path is used instead so update_kit is actually invoked.
        """
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache = Path(td) / "cache"
            _make_cache(cache)
            (cache / ".provenance.json").write_text(
                json.dumps({
                    "source_type": "github",
                    "installed_version": "v9.8.7",
                    "resolved_ref": "v9.8.7",
                    "effective_source": "github:o/r",
                    "verified": "verified",
                }),
                encoding="utf-8",
            )
            _init_project(root, cache)

            cwd = os.getcwd()
            raised_exc = None
            return_code = None
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache),
                    # Prevent source-migration step from adding github: source —
                    # otherwise the download fails before update_kit is reached.
                    patch(
                        "studio.commands.update._migrate_kit_sources",
                        return_value={},
                    ),
                    patch(
                        "studio.commands.kit.update_kit",
                        side_effect=TypeError("simulated unexpected error"),
                    ),
                ):
                    buf = io.StringIO()
                    err_buf = io.StringIO()
                    try:
                        with redirect_stdout(buf), redirect_stderr(err_buf):
                            return_code = cmd_update(["--yes", "--with-kits", "yes"])
                    except Exception as exc:
                        raised_exc = exc
            finally:
                os.chdir(cwd)

            # The function must NOT raise UnboundLocalError regardless of outcome.
            self.assertNotIsInstance(
                raised_exc,
                UnboundLocalError,
                "cmd_update must not raise UnboundLocalError when update_kit raises TypeError",
            )
            # Exactly one of: an exception was raised OR a non-zero return code was returned.
            # return_code is None when an exception propagated out of cmd_update, which counts
            # as the "exception raised" side of the contract, not the "non-zero rc" side.
            rc_nonzero = return_code is not None and return_code != 0
            exc_raised = raised_exc is not None
            self.assertTrue(
                exc_raised ^ rc_nonzero,
                "expected exactly one of: an exception raised OR non-zero rc",
            )
            if return_code is not None:
                # If cmd_update returned normally, it should report error status.
                self.assertNotEqual(
                    return_code, 0,
                    "cmd_update must return non-zero when update_kit raises TypeError",
                )
            else:
                # TypeError propagated — confirm it is TypeError, not UnboundLocalError.
                self.assertIsInstance(
                    raised_exc,
                    TypeError,
                    f"Expected TypeError to propagate, got {type(raised_exc).__name__}",
                )


# =========================================================================
# cmd_update full pipeline
# =========================================================================

class TestCmdUpdatePipeline(unittest.TestCase):
    """Full update pipeline: init then update."""

    def test_update_after_init(self):
        """Update on a freshly initialized project succeeds."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache = Path(td) / "cache"
            _make_cache(cache)
            (cache / ".provenance.json").write_text(
                json.dumps({
                    "source_type": "github",
                    "installed_version": "v9.8.7",
                    "resolved_ref": "v9.8.7",
                    "effective_source": "github:o/r",
                    "verified": "verified",
                }),
                encoding="utf-8",
            )
            _init_project(root, cache)

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache),
                    # _migrate_kit_sources performs a network fetch on init.py-stripped
                    # GitHub sources; isolate by patching to a no-op.
                    patch("studio.commands.update._migrate_kit_sources", return_value={}),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["--with-kits", "yes"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertIn(out["status"], ["PASS", "WARN"])
                self.assertIn("actions", out)
                self.assertIn("core_update", out["actions"])
                self.assertIn("kits", out["actions"])
                self.assertEqual(out["actions"]["install_provenance"], "updated")
                installed_provenance = root / ".cf-studio" / ".core" / ".provenance.json"
                self.assertTrue(installed_provenance.is_file())
            finally:
                os.chdir(cwd)

    def test_update_dry_run(self):
        """--dry-run reports what would change without writing."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache = Path(td) / "cache"
            _make_cache(cache)
            _init_project(root, cache)

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with patch("studio.commands.update.CACHE_DIR", cache):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["--dry-run"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertTrue(out["dry_run"])
                self.assertEqual(out["actions"]["core_update"]["whatsnew.toml"], "missing_in_cache")
                self.assertEqual(out["actions"]["core_update"]["version.toml"], "dry_run")
            finally:
                os.chdir(cwd)

    def test_update_with_explicit_project_root(self):
        """--project-root flag works correctly."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache = Path(td) / "cache"
            _make_cache(cache)
            _init_project(root, cache)

            with (
                patch("studio.commands.update.CACHE_DIR", cache),
                # _migrate_kit_sources performs a network fetch on init.py-stripped
                # GitHub sources; isolate by patching to a no-op.
                patch("studio.commands.update._migrate_kit_sources", return_value={}),
            ):
                buf = io.StringIO()
                err = io.StringIO()
                with redirect_stdout(buf), redirect_stderr(err):
                    rc = cmd_update(["--project-root", str(root)])
            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            self.assertIn("actions", out)
            self.assertIn(str(root), json.dumps(out))

    def test_update_version_drift(self):
        """When cache has newer kit version, update applies file-level diff."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache_v1 = Path(td) / "cache_v1"
            _make_cache(cache_v1, kit_version=1)
            _init_project(root, cache_v1)

            # Now update cache to v2
            cache_v2 = Path(td) / "cache_v2"
            _make_cache(cache_v2, kit_version=2)
            kit_src_v2 = cache_v2 / "kits" / "sdlc"

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache_v2),
                    patch(
                        "studio.commands.kit._download_kit_from_github",
                        return_value=(kit_src_v2, "2"),
                    ),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["--with-kits", "yes"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                kits = out["actions"].get("kits", {})
                sdlc_r = kits.get("sdlc", {})
                ver = sdlc_r.get("version", {})
                # Version drift runs the diff; if file content is identical, status is "current"
                self.assertIn(ver.get("status"), ["created", "updated", "current"])
            finally:
                os.chdir(cwd)

    def test_update_github_kit_records_authority_metadata(self):
        """Main cmd_update path persists GitHub release authority for kits."""
        from studio.commands.update import cmd_update
        from studio.utils import toml_utils
        import tomllib

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache_v1 = Path(td) / "cache_v1"
            _make_cache(cache_v1, kit_version=1)
            adapter = _init_project(root, cache_v1)

            cache_v2 = Path(td) / "cache_v2"
            _make_cache(cache_v2, kit_version=2)
            kit_src_v2 = cache_v2 / "kits" / "sdlc"

            core_toml = adapter / "config" / "core.toml"
            with open(core_toml, "rb") as f:
                core_data = tomllib.load(f)
            core_data["kits"]["sdlc"]["source"] = "github:o/r"
            toml_utils.dump(core_data, core_toml)

            authority = {
                "source_type": "github",
                "requested_ref": "latest",
                "resolved_ref": "v2.0.0",
                "installed_version": "v2.0.0",
                "canonical_source": "github:o/r",
                "effective_source": "github:o/r",
                "resolver_mode": "latest_release",
                "resolution_basis": "github_release",
                "verified": "verified",
                "freshness": "fresh",
                "commit_sha": "abc123",
                "identity": "o/r@v2.0.0#abc123",
            }

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache_v2),
                    patch(
                        "studio.commands.kit._download_kit_from_github_with_authority",
                        return_value=(kit_src_v2, "v2.0.0", authority),
                    ),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["-y", "--with-kits", "yes"])
                self.assertEqual(rc, 0)
            finally:
                os.chdir(cwd)

            with open(core_toml, "rb") as f:
                updated_core = tomllib.load(f)
            kit_data = updated_core["kits"]["sdlc"]
            self.assertEqual(kit_data["version"], "v2.0.0")
            self.assertEqual(
                kit_data["source_provenance"]["resolution_basis"],
                "github_release",
            )
            self.assertEqual(
                kit_data["content_identity"]["commit_sha"],
                "abc123",
            )

    def test_update_github_kit_cache_fallback_preserves_authority_metadata(self):
        """Offline cache fallback must not use local kit conf.toml as authority."""
        from studio.commands.update import cmd_update
        from studio.utils import toml_utils
        import tomllib

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache_v1 = Path(td) / "cache_v1"
            _make_cache(cache_v1, kit_version=1)
            adapter = _init_project(root, cache_v1)

            cache_v2 = Path(td) / "cache_v2"
            _make_cache(cache_v2, kit_version=2)

            core_toml = adapter / "config" / "core.toml"
            with open(core_toml, "rb") as f:
                core_data = tomllib.load(f)
            core_data["kits"]["sdlc"]["source"] = "github:o/r"
            core_data["kits"]["sdlc"]["version"] = "v1.0.0"
            core_data["kits"]["sdlc"]["source_provenance"] = {
                "source_type": "github",
                "requested_ref": "latest",
                "resolved_ref": "v1.0.0",
                "canonical_source": "github:o/r",
                "effective_source": "github:o/r",
                "resolver_mode": "latest_release",
                "resolution_basis": "github_release",
                "verified": "verified",
                "freshness": "fresh",
            }
            core_data["kits"]["sdlc"]["content_identity"] = {
                "resolved_ref": "v1.0.0",
                "commit_sha": "abc123",
                "identity": "o/r@v1.0.0#abc123",
            }
            toml_utils.dump(core_data, core_toml)

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache_v2),
                    patch(
                        "studio.commands.kit._download_kit_from_github_with_authority",
                        side_effect=RuntimeError("offline"),
                    ),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["-y", "--with-kits", "yes"])
                self.assertEqual(rc, 0)
            finally:
                os.chdir(cwd)

            with open(core_toml, "rb") as f:
                updated_core = tomllib.load(f)
            kit_data = updated_core["kits"]["sdlc"]
            self.assertEqual(kit_data["version"], "v1.0.0")
            self.assertEqual(
                kit_data["source_provenance"]["resolver_mode"],
                "latest_release",
            )
            self.assertEqual(
                kit_data["content_identity"]["commit_sha"],
                "abc123",
            )

    def test_update_invalid_github_source_with_cache_does_not_crash(self):
        """Invalid GitHub source plus cache fallback returns structured output."""
        from studio.commands.update import cmd_update
        from studio.utils import toml_utils
        import tomllib

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache_v1 = Path(td) / "cache_v1"
            _make_cache(cache_v1, kit_version=1)
            adapter = _init_project(root, cache_v1)

            core_toml = adapter / "config" / "core.toml"
            with open(core_toml, "rb") as f:
                core_data = tomllib.load(f)
            core_data["kits"]["sdlc"]["source"] = "github:bad-source"
            core_data["kits"]["sdlc"]["version"] = "v1.0.0"
            core_data["kits"]["sdlc"]["source_provenance"] = {
                "source_type": "github",
                "requested_ref": "latest",
                "resolved_ref": "v1.0.0",
                "canonical_source": "github:bad-source",
                "effective_source": "github:bad-source",
                "resolver_mode": "latest_release",
                "resolution_basis": "github_release",
                "verified": "verified",
                "freshness": "fresh",
            }
            toml_utils.dump(core_data, core_toml)

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with patch("studio.commands.update.CACHE_DIR", cache_v1):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["-y", "--with-kits", "yes"])
                self.assertEqual(rc, 0)
                output = json.loads(buf.getvalue())
                self.assertEqual(output["status"], "WARN")
                self.assertIn("kits", output["actions"])
                self.assertIn("sdlc", output["actions"]["kits"])
                self.assertEqual(
                    output["actions"]["kits"]["sdlc"]["version"]["status"],
                    "current",
                )
                self.assertEqual(
                    output["actions"]["kits"]["sdlc"]["authority"]["resolver_mode"],
                    "offline_last_known",
                )
            finally:
                os.chdir(cwd)

    def test_update_creates_missing_config_scaffold(self):
        """Update creates config/ scaffold files if missing."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache = Path(td) / "cache"
            _make_cache(cache)
            adapter = _init_project(root, cache)

            # Remove config scaffold files to test recreation
            for f in ["AGENTS.md", "SKILL.md", "README.md"]:
                p = adapter / "config" / f
                if p.exists():
                    p.unlink()

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache),
                    # _migrate_kit_sources performs a network fetch on init.py-stripped
                    # GitHub sources; isolate by patching to a no-op.
                    patch("studio.commands.update._migrate_kit_sources", return_value={}),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["--with-kits", "yes"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                # Scaffold files should be recreated
                self.assertTrue((adapter / "config" / "AGENTS.md").is_file())
                self.assertTrue((adapter / "config" / "SKILL.md").is_file())
                self.assertTrue((adapter / "config" / "README.md").is_file())
            finally:
                os.chdir(cwd)

    def test_update_first_install_kit_content(self):
        """Update copies kit content on first install (no user kit yet)."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache = Path(td) / "cache"
            _make_cache(cache)
            adapter = _init_project(root, cache)

            # Remove kit content to simulate first install scenario
            config_kit = adapter / "config" / "kits" / "sdlc"
            if config_kit.exists():
                shutil.rmtree(config_kit)

            kit_src = cache / "kits" / "sdlc"
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache),
                    patch(
                        "studio.commands.kit._download_kit_from_github",
                        return_value=(kit_src, "1"),
                    ),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["--with-kits", "yes"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                kits = out["actions"].get("kits", {})
                sdlc_r = kits.get("sdlc", {})
                self.assertEqual(sdlc_r.get("version", {}).get("status"), "created")
                # Kit content should now exist in config/kits/sdlc/
                self.assertTrue(config_kit.is_dir())
            finally:
                os.chdir(cwd)




class TestUpdateHelperExceptions(unittest.TestCase):
    """Cover exception paths in _read_conf_version."""

    def test_read_conf_version_corrupt_toml(self):
        from studio.commands.update import _read_conf_version
        with TemporaryDirectory() as td:
            p = Path(td) / "conf.toml"
            p.write_text("{{corrupt", encoding="utf-8")
            self.assertEqual(_read_conf_version(p), 0)


    def test_update_non_dir_in_kits_cache_skipped(self):
        """Files (non-dirs) in kits cache dir are skipped."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache = Path(td) / "cache"
            _make_cache(cache)
            # Add a stray file in kits/ dir
            (cache / "kits" / "README.md").write_text("stray\n", encoding="utf-8")
            _init_project(root, cache)

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache),
                    # _migrate_kit_sources performs a network fetch on init.py-stripped
                    # GitHub sources; isolate by patching to a no-op.
                    patch("studio.commands.update._migrate_kit_sources", return_value={}),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["--with-kits", "yes"])
                self.assertEqual(rc, 0)
            finally:
                os.chdir(cwd)


# =========================================================================
# read_whatsnew / show_core_whatsnew (moved to cypilot.utils.whatsnew)
# =========================================================================

class TestReadCoreWhatsnew(unittest.TestCase):
    """Tests for reading standalone whatsnew.toml."""

    def test_read_valid(self):
        from studio.utils.whatsnew import read_whatsnew as _read_core_whatsnew
        with TemporaryDirectory() as td:
            p = Path(td) / "whatsnew.toml"
            p.write_text(
                '["v3.0.4-beta"]\nsummary = "A"\ndetails = "D1"\n\n'
                '["v3.0.5-beta"]\nsummary = "B"\ndetails = "D2"\n',
                encoding="utf-8",
            )
            result = _read_core_whatsnew(p)
            self.assertEqual(len(result), 2)
            self.assertIn("v3.0.4-beta", result)
            self.assertEqual(result["v3.0.4-beta"]["summary"], "A")
            self.assertEqual(result["v3.0.5-beta"]["details"], "D2")

    def test_read_missing_file(self):
        from studio.utils.whatsnew import read_whatsnew as _read_core_whatsnew
        self.assertEqual(_read_core_whatsnew(Path("/nonexistent/whatsnew.toml")), {})

    def test_read_corrupt_file(self):
        from studio.utils.whatsnew import read_whatsnew as _read_core_whatsnew
        with TemporaryDirectory() as td:
            p = Path(td) / "whatsnew.toml"
            p.write_text("{{invalid", encoding="utf-8")
            self.assertEqual(_read_core_whatsnew(p), {})

    def test_read_skips_non_dict_entries(self):
        from studio.utils.whatsnew import read_whatsnew as _read_core_whatsnew
        with TemporaryDirectory() as td:
            p = Path(td) / "whatsnew.toml"
            p.write_text(
                'scalar_key = "not a dict"\n\n'
                '["v1.0"]\nsummary = "OK"\ndetails = ""\n',
                encoding="utf-8",
            )
            result = _read_core_whatsnew(p)
            self.assertEqual(len(result), 1)
            self.assertIn("v1.0", result)

    def test_read_whatsnew_section_format(self):
        """Test reading whatsnew.toml with [whatsnew."X.Y.Z"] format."""
        from studio.utils.whatsnew import read_whatsnew
        with TemporaryDirectory() as td:
            p = Path(td) / "whatsnew.toml"
            p.write_text(
                '[whatsnew."1.2.0"]\nsummary = "New feature"\ndetails = "- Added X"\n\n'
                '[whatsnew."1.3.0"]\nsummary = "Bug fix"\ndetails = "- Fixed Y"\n',
                encoding="utf-8",
            )
            result = read_whatsnew(p)
            self.assertEqual(len(result), 2)
            self.assertIn("1.2.0", result)
            self.assertIn("1.3.0", result)
            self.assertEqual(result["1.2.0"]["summary"], "New feature")
            self.assertEqual(result["1.3.0"]["details"], "- Fixed Y")


class TestWhatsnewVersionParsing(unittest.TestCase):
    """Tests for semver parsing and comparison in whatsnew module."""

    def test_parse_semver_basic(self):
        from studio.utils.whatsnew import parse_semver
        self.assertEqual(parse_semver("1.2.3"), (1, 2, 3, 1))
        self.assertEqual(parse_semver("0.0.1"), (0, 0, 1, 1))
        self.assertEqual(parse_semver("10.20.30"), (10, 20, 30, 1))

    def test_parse_semver_with_v_prefix(self):
        from studio.utils.whatsnew import parse_semver
        self.assertEqual(parse_semver("v1.2.3"), (1, 2, 3, 1))
        self.assertEqual(parse_semver("v0.1.0"), (0, 1, 0, 1))

    def test_parse_semver_with_whatsnew_prefix(self):
        from studio.utils.whatsnew import parse_semver
        self.assertEqual(parse_semver("whatsnew.1.2.3"), (1, 2, 3, 1))

    def test_parse_semver_partial(self):
        from studio.utils.whatsnew import parse_semver
        self.assertEqual(parse_semver("1.2"), (1, 2, 0, 1))
        self.assertEqual(parse_semver("1"), (1, 0, 0, 1))

    def test_parse_semver_prerelease_does_not_collapse_to_zero(self):
        from studio.utils.whatsnew import parse_semver
        self.assertNotEqual(parse_semver("v3.0.4-beta"), (0, 0, 0))

    def test_parse_semver_invalid(self):
        from studio.utils.whatsnew import parse_semver
        self.assertEqual(parse_semver("invalid"), (0, 0, 0))
        self.assertEqual(parse_semver("a.b.c"), (0, 0, 0))
        self.assertEqual(parse_semver(""), (0, 0, 0))

    def test_compare_versions_less_than(self):
        from studio.utils.whatsnew import compare_versions
        self.assertEqual(compare_versions("1.0.0", "2.0.0"), -1)
        self.assertEqual(compare_versions("1.0.0", "1.1.0"), -1)
        self.assertEqual(compare_versions("1.0.0", "1.0.1"), -1)

    def test_compare_versions_greater_than(self):
        from studio.utils.whatsnew import compare_versions
        self.assertEqual(compare_versions("2.0.0", "1.0.0"), 1)
        self.assertEqual(compare_versions("1.1.0", "1.0.0"), 1)
        self.assertEqual(compare_versions("1.0.1", "1.0.0"), 1)

    def test_compare_versions_equal(self):
        from studio.utils.whatsnew import compare_versions
        self.assertEqual(compare_versions("1.0.0", "1.0.0"), 0)
        self.assertEqual(compare_versions("v1.0.0", "1.0.0"), 0)

    def test_compare_versions_prerelease_sorts_before_release(self):
        from studio.utils.whatsnew import compare_versions
        self.assertEqual(compare_versions("v3.0.4-beta", "v3.0.4"), -1)


class TestShowKitWhatsnew(unittest.TestCase):
    """Tests for kit-specific whatsnew display."""

    def test_no_whatsnew_file_returns_true(self):
        from studio.utils.whatsnew import show_kit_whatsnew
        with TemporaryDirectory() as td:
            kit_dir = Path(td)
            result = show_kit_whatsnew(kit_dir, "1.0.0", "test-kit", interactive=False)
            self.assertTrue(result)

    def test_no_new_entries_returns_true(self):
        from studio.utils.whatsnew import show_kit_whatsnew
        with TemporaryDirectory() as td:
            kit_dir = Path(td)
            (kit_dir / "whatsnew.toml").write_text(
                '[whatsnew."1.0.0"]\nsummary = "Old"\ndetails = ""\n',
                encoding="utf-8",
            )
            # installed version is same or newer
            result = show_kit_whatsnew(kit_dir, "1.0.0", "test-kit", interactive=False)
            self.assertTrue(result)

    def test_shows_new_entries(self):
        from studio.utils.whatsnew import show_kit_whatsnew
        with TemporaryDirectory() as td:
            kit_dir = Path(td)
            (kit_dir / "whatsnew.toml").write_text(
                '[whatsnew."1.1.0"]\nsummary = "New feature"\ndetails = "- Added X"\n'
                '[whatsnew."1.2.0"]\nsummary = "Bug fix"\ndetails = ""\n',
                encoding="utf-8",
            )
            err = io.StringIO()
            with redirect_stderr(err):
                result = show_kit_whatsnew(kit_dir, "1.0.0", "test-kit", interactive=False)
            self.assertTrue(result)
            output = err.getvalue()
            self.assertIn("What's new in test-kit kit", output)
            self.assertIn("New feature", output)
            self.assertIn("Bug fix", output)

    def test_tty_ansi_formatting_plain_summary(self):
        """Test ANSI formatting when summary has no markdown."""
        from studio.utils.whatsnew import show_kit_whatsnew
        with TemporaryDirectory() as td:
            kit_dir = Path(td)
            (kit_dir / "whatsnew.toml").write_text(
                '[whatsnew."1.1.0"]\nsummary = "Plain summary"\ndetails = ""\n',
                encoding="utf-8",
            )
            err = io.StringIO()
            with patch("studio.utils.whatsnew.stderr_supports_ansi", return_value=True):
                with redirect_stderr(err):
                    show_kit_whatsnew(kit_dir, "1.0.0", "test-kit", interactive=False)
            output = err.getvalue()
            # Should have ANSI bold around version and summary
            self.assertIn("\033[1m1.1.0: Plain summary\033[0m", output)

    def test_filters_old_versions(self):
        from studio.utils.whatsnew import show_kit_whatsnew
        with TemporaryDirectory() as td:
            kit_dir = Path(td)
            (kit_dir / "whatsnew.toml").write_text(
                '[whatsnew."1.0.0"]\nsummary = "Old"\ndetails = ""\n'
                '[whatsnew."1.2.0"]\nsummary = "New"\ndetails = ""\n',
                encoding="utf-8",
            )
            err = io.StringIO()
            with redirect_stderr(err):
                show_kit_whatsnew(kit_dir, "1.1.0", "test-kit", interactive=False)
            output = err.getvalue()
            self.assertNotIn("Old", output)
            self.assertIn("New", output)

    def test_missing_version_treated_as_zero(self):
        from studio.utils.whatsnew import show_kit_whatsnew
        with TemporaryDirectory() as td:
            kit_dir = Path(td)
            (kit_dir / "whatsnew.toml").write_text(
                '[whatsnew."0.0.1"]\nsummary = "Initial"\ndetails = ""\n',
                encoding="utf-8",
            )
            err = io.StringIO()
            with redirect_stderr(err):
                result = show_kit_whatsnew(kit_dir, "", "test-kit", interactive=False)
            self.assertTrue(result)
            output = err.getvalue()
            self.assertIn("Initial", output)

    def test_interactive_q_aborts(self):
        from studio.utils.whatsnew import show_kit_whatsnew
        with TemporaryDirectory() as td:
            kit_dir = Path(td)
            (kit_dir / "whatsnew.toml").write_text(
                '[whatsnew."1.1.0"]\nsummary = "New"\ndetails = ""\n',
                encoding="utf-8",
            )
            err = io.StringIO()
            with patch("builtins.input", return_value="q"), redirect_stderr(err):
                result = show_kit_whatsnew(kit_dir, "1.0.0", "test-kit", interactive=True)
            self.assertFalse(result)

    def test_interactive_enter_continues(self):
        from studio.utils.whatsnew import show_kit_whatsnew
        with TemporaryDirectory() as td:
            kit_dir = Path(td)
            (kit_dir / "whatsnew.toml").write_text(
                '[whatsnew."1.1.0"]\nsummary = "New"\ndetails = ""\n',
                encoding="utf-8",
            )
            err = io.StringIO()
            with patch("builtins.input", return_value=""), redirect_stderr(err):
                result = show_kit_whatsnew(kit_dir, "1.0.0", "test-kit", interactive=True)
            self.assertTrue(result)


class TestShowCoreWhatsnew(unittest.TestCase):
    """Tests for core whatsnew display and prompting."""

    def test_non_interactive_shows_missing(self):
        from studio.utils.whatsnew import show_core_whatsnew as _show_core_whatsnew
        ref = {
            "v3.0.4": {"summary": "A", "details": "- d1"},
            "v3.0.5": {"summary": "B", "details": "- d2"},
        }
        err = io.StringIO()
        with redirect_stderr(err):
            result = _show_core_whatsnew(ref, {}, interactive=False)
        self.assertTrue(result)
        output = err.getvalue()
        self.assertIn("What's new", output)
        self.assertIn("A", output)
        self.assertIn("B", output)

    def test_non_interactive_renders_bold_markdown_in_summary(self):
        from studio.utils.whatsnew import show_core_whatsnew as _show_core_whatsnew
        ref = {
            "v3.2.0-beta": {
                "summary": "Prompt **compactification** release",
                "details": "",
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            result = _show_core_whatsnew(ref, {}, interactive=False)
        self.assertTrue(result)
        output = err.getvalue()
        self.assertIn("Prompt compactification release", output)
        self.assertNotIn("**compactification**", output)
        self.assertNotIn("\033[1mcompactification\033[0m", output)

    def test_non_interactive_renders_bold_markdown_in_details(self):
        from studio.utils.whatsnew import show_core_whatsnew as _show_core_whatsnew
        ref = {
            "v3.2.0-beta": {
                "summary": "Prompt compactification",
                "details": "- **Aggressive** prompt compactification release",
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            result = _show_core_whatsnew(ref, {}, interactive=False)
        self.assertTrue(result)
        output = err.getvalue()
        self.assertIn("- Aggressive prompt compactification release", output)
        self.assertNotIn("**Aggressive**", output)
        self.assertNotIn("\033[1mAggressive\033[0m", output)

    def test_non_interactive_renders_inline_code_in_summary(self):
        from studio.utils.whatsnew import show_core_whatsnew as _show_core_whatsnew
        ref = {
            "v3.2.0-beta": {
                "summary": "Use `workflows/analyze.md` for compact analysis",
                "details": "",
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            result = _show_core_whatsnew(ref, {}, interactive=False)
        self.assertTrue(result)
        output = err.getvalue()
        self.assertIn("Use workflows/analyze.md for compact analysis", output)
        self.assertNotIn("`workflows/analyze.md`", output)
        self.assertNotIn("\033[36mworkflows/analyze.md\033[0m", output)

    def test_non_interactive_renders_inline_code_in_details(self):
        from studio.utils.whatsnew import show_core_whatsnew as _show_core_whatsnew
        ref = {
            "v3.2.0-beta": {
                "summary": "Prompt compactification",
                "details": "- Updated `skills/cypilot/SKILL.md` and `requirements/workspace.md`",
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            result = _show_core_whatsnew(ref, {}, interactive=False)
        self.assertTrue(result)
        output = err.getvalue()
        self.assertIn("- Updated skills/cypilot/SKILL.md and requirements/workspace.md", output)
        self.assertNotIn("`skills/cypilot/SKILL.md`", output)
        self.assertNotIn("\033[36mskills/cypilot/SKILL.md\033[0m", output)

    def test_non_interactive_tty_renders_ansi_markup(self):
        from studio.utils.whatsnew import show_core_whatsnew as _show_core_whatsnew
        ref = {
            "v3.2.0-beta": {
                "summary": "Prompt **compactification** release in `workflows/analyze.md`",
                "details": "",
            },
        }
        err = io.StringIO()
        with patch("studio.utils.whatsnew.stderr_supports_ansi", return_value=True):
            with redirect_stderr(err):
                result = _show_core_whatsnew(ref, {}, interactive=False)
        self.assertTrue(result)
        output = err.getvalue()
        self.assertIn("\033[1mcompactification\033[0m", output)
        self.assertIn("\033[36mworkflows/analyze.md\033[0m", output)

    def test_non_interactive_strips_control_chars_from_summary_and_details(self):
        from studio.utils.whatsnew import show_core_whatsnew as _show_core_whatsnew
        ref = {
            "v3.2.0\x1b[2J": {
                "summary": "Safe\x1b[31m summary",
                "details": "- detail\x1b[2K\n- second\x07 line",
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            result = _show_core_whatsnew(ref, {}, interactive=False)
        self.assertTrue(result)
        output = err.getvalue()
        self.assertIn("v3.2.0: Safe summary", output)
        self.assertIn("- detail", output)
        self.assertIn("- second line", output)
        self.assertNotIn("\x1b", output)
        self.assertNotIn("\x07", output)

    def test_filters_by_core_keys(self):
        """Only entries missing from .core/ whatsnew are shown."""
        from studio.utils.whatsnew import show_core_whatsnew as _show_core_whatsnew
        ref = {
            "v3.0.4": {"summary": "Old", "details": ""},
            "v3.0.5": {"summary": "New", "details": ""},
        }
        core = {"v3.0.4": {"summary": "Old", "details": ""}}
        err = io.StringIO()
        with redirect_stderr(err):
            _show_core_whatsnew(ref, core, interactive=False)
        output = err.getvalue()
        self.assertNotIn("Old", output)
        self.assertIn("New", output)

    def test_missing_entries_are_sorted_semantically(self):
        from studio.utils.whatsnew import show_core_whatsnew as _show_core_whatsnew

        ref = {
            "1.10.0": {"summary": "Tenth minor", "details": ""},
            "1.9.0": {"summary": "Ninth minor", "details": ""},
        }
        err = io.StringIO()
        with redirect_stderr(err):
            _show_core_whatsnew(ref, {}, interactive=False)
        output = err.getvalue()
        self.assertLess(output.index("1.9.0"), output.index("1.10.0"))

    def test_all_seen_returns_true(self):
        from studio.utils.whatsnew import show_core_whatsnew as _show_core_whatsnew
        same = {"v1": {"summary": "X", "details": ""}}
        self.assertTrue(_show_core_whatsnew(same, same, interactive=True))

    def test_empty_ref_returns_true(self):
        from studio.utils.whatsnew import show_core_whatsnew as _show_core_whatsnew
        self.assertTrue(_show_core_whatsnew({}, {}, interactive=True))

    def test_enter_continues(self):
        from studio.utils.whatsnew import show_core_whatsnew as _show_core_whatsnew
        ref = {"v1": {"summary": "X", "details": ""}}
        err = io.StringIO()
        with patch("builtins.input", return_value=""), redirect_stderr(err):
            self.assertTrue(_show_core_whatsnew(ref, {}, interactive=True))

    def test_q_aborts(self):
        from studio.utils.whatsnew import show_core_whatsnew as _show_core_whatsnew
        ref = {"v1": {"summary": "X", "details": ""}}
        err = io.StringIO()
        with patch("builtins.input", return_value="q"), redirect_stderr(err):
            self.assertFalse(_show_core_whatsnew(ref, {}, interactive=True))

    def test_eof_aborts(self):
        from studio.utils.whatsnew import show_core_whatsnew as _show_core_whatsnew
        ref = {"v1": {"summary": "X", "details": ""}}
        err = io.StringIO()
        with patch("builtins.input", side_effect=EOFError), redirect_stderr(err):
            self.assertFalse(_show_core_whatsnew(ref, {}, interactive=True))

    def test_non_interactive_auto_continues(self):
        """Non-interactive mode (CI/non-TTY) must auto-continue without blocking."""
        from studio.utils.whatsnew import show_core_whatsnew as _show_core_whatsnew
        ref = {"v1": {"summary": "X", "details": ""}}
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertTrue(_show_core_whatsnew(ref, {}, interactive=False))


class TestCmdUpdateWhatsnew(unittest.TestCase):
    """Integration tests for core whatsnew in cmd_update pipeline."""

    def test_update_shows_whatsnew_and_copies_to_install_root(self):
        """Update with new whatsnew entries shows them and copies to install root."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache = Path(td) / "cache"
            _make_cache(cache)
            # Add whatsnew.toml to cache
            (cache / "whatsnew.toml").write_text(
                '["v3.0.4"]\nsummary = "Test change"\ndetails = "- detail"\n',
                encoding="utf-8",
            )
            _init_project(root, cache)
            (root / ".cf-studio" / "whatsnew.toml").unlink(missing_ok=True)

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache),
                    # _migrate_kit_sources performs a network fetch on init.py-stripped
                    # GitHub sources; isolate by patching to a no-op.
                    patch("studio.commands.update._migrate_kit_sources", return_value={}),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["-y", "--with-kits", "yes"])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                stderr_text = err.getvalue()
                self.assertIn("Test change", stderr_text)
                install_wn = root / ".cf-studio" / "whatsnew.toml"
                self.assertTrue(install_wn.is_file())
                install_version = root / ".cf-studio" / "version.toml"
                self.assertTrue(install_version.is_file())
                self.assertIn('version = "v1.0.0"', install_version.read_text(encoding="utf-8"))
                self.assertEqual(out["actions"]["core_update"]["version.toml"], "updated")
                self.assertFalse((root / ".cf-studio" / ".core" / "whatsnew.toml").exists())
            finally:
                os.chdir(cwd)

    def test_update_uses_legacy_core_whatsnew_as_seen_state_once(self):
        """First update after layout change does not re-show already seen core entries."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache = Path(td) / "cache"
            _make_cache(cache)
            (cache / "whatsnew.toml").write_text(
                '[whatsnew."v3.0.4"]\nsummary = "Test change"\ndetails = ""\n',
                encoding="utf-8",
            )
            _init_project(root, cache)
            install_wn = root / ".cf-studio" / "whatsnew.toml"
            legacy_wn = root / ".cf-studio" / ".core" / "whatsnew.toml"
            install_wn.unlink(missing_ok=True)
            legacy_wn.write_text(
                '[whatsnew."v3.0.4"]\nsummary = "Test change"\ndetails = ""\n',
                encoding="utf-8",
            )

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache),
                    patch("studio.commands.update._migrate_kit_sources", return_value={}),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["-y"])
                self.assertEqual(rc, 0)
                self.assertNotIn("Test change", err.getvalue())
                self.assertTrue(install_wn.is_file())
                self.assertFalse(legacy_wn.exists())
            finally:
                os.chdir(cwd)

    def test_update_second_run_no_whatsnew(self):
        """Second update with same cache → no whatsnew shown (already in install root)."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache = Path(td) / "cache"
            _make_cache(cache)
            (cache / "whatsnew.toml").write_text(
                '["v3.0.4"]\nsummary = "Test"\ndetails = ""\n',
                encoding="utf-8",
            )
            _init_project(root, cache)
            (root / ".cf-studio" / "whatsnew.toml").unlink(missing_ok=True)

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                # First update — shows whatsnew (non-interactive to avoid input())
                # _migrate_kit_sources performs a network fetch on init.py-stripped
                # GitHub sources; isolate by patching to a no-op.
                with (
                    patch("studio.commands.update.CACHE_DIR", cache),
                    patch("studio.commands.update._migrate_kit_sources", return_value={}),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        cmd_update(["-y"])
                self.assertIn("Test", err.getvalue())

                # Second update — whatsnew already in install root, nothing to show
                with (
                    patch("studio.commands.update.CACHE_DIR", cache),
                    patch("studio.commands.update._migrate_kit_sources", return_value={}),
                ):
                    buf2 = io.StringIO()
                    err2 = io.StringIO()
                    with redirect_stdout(buf2), redirect_stderr(err2):
                        rc = cmd_update(["--with-kits", "yes"])
                self.assertEqual(rc, 0)
                self.assertNotIn("What's new", err2.getvalue())
            finally:
                os.chdir(cwd)

    def test_update_whatsnew_abort(self):
        """User types 'q' at whatsnew prompt → update aborted."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache = Path(td) / "cache"
            _make_cache(cache)
            (cache / "whatsnew.toml").write_text(
                '["v3.0.4"]\nsummary = "X"\ndetails = ""\n',
                encoding="utf-8",
            )
            _init_project(root, cache)
            (root / ".cf-studio" / "whatsnew.toml").unlink(missing_ok=True)

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with patch("studio.commands.update.CACHE_DIR", cache), \
                     patch("builtins.input", return_value="q"), \
                     patch("sys.stdin") as mock_stdin:
                    mock_stdin.isatty.return_value = True
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update([])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "ABORTED")
                # .core/ should NOT have been updated
                install_wn = root / ".cf-studio" / "whatsnew.toml"
                core_wn = root / ".cf-studio" / ".core" / "whatsnew.toml"
                self.assertFalse(install_wn.is_file())
                self.assertFalse(core_wn.is_file())
            finally:
                os.chdir(cwd)

    def test_update_dry_run_skips_whatsnew(self):
        """--dry-run skips whatsnew display entirely."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache = Path(td) / "cache"
            _make_cache(cache)
            (cache / "whatsnew.toml").write_text(
                '["v3.0.4"]\nsummary = "X"\ndetails = ""\n',
                encoding="utf-8",
            )
            _init_project(root, cache)

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with patch("studio.commands.update.CACHE_DIR", cache):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["--dry-run"])
                self.assertEqual(rc, 0)
                self.assertNotIn("What's new", err.getvalue())
            finally:
                os.chdir(cwd)

    def test_update_shows_kit_whatsnew(self):
        """Main cmd_update flow shows kit whatsnew before updating the kit."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache_v1 = Path(td) / "cache_v1"
            _make_cache(cache_v1, kit_version=1)
            _init_project(root, cache_v1)

            cache_v2 = Path(td) / "cache_v2"
            _make_cache(cache_v2, kit_version=2)
            (cache_v2 / "kits" / "sdlc" / "whatsnew.toml").write_text(
                '[whatsnew."2.0.0"]\nsummary = "Kit update"\ndetails = "- Added feature"\n',
                encoding="utf-8",
            )

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with patch("studio.commands.update.CACHE_DIR", cache_v2), \
                     patch(
                         "studio.commands.kit._read_kits_from_core_toml",
                         return_value={"sdlc": {"path": "config/kits/sdlc"}},
                     ), \
                     patch("studio.commands.kit._read_kit_version_from_core", return_value="1"), \
                     patch(
                         "studio.commands.kit.update_kit",
                         return_value={"version": {"status": "current"}, "gen": {"files_written": 0}},
                     ) as mock_update, \
                     patch("studio.commands.update.show_kit_whatsnew", return_value=True) as mock_show:
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["-y", "--with-kits", "yes"])
                self.assertEqual(rc, 0)
                mock_show.assert_called()
                mock_update.assert_called()
            finally:
                os.chdir(cwd)

    def test_update_kit_whatsnew_abort_skips_kit_update(self):
        """Aborting kit whatsnew in cmd_update skips that kit update."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache_v1 = Path(td) / "cache_v1"
            _make_cache(cache_v1, kit_version=1)
            adapter = _init_project(root, cache_v1)
            original_skill = (adapter / "config" / "kits" / "sdlc" / "SKILL.md").read_text(encoding="utf-8")

            cache_v2 = Path(td) / "cache_v2"
            _make_cache(cache_v2, kit_version=2)
            (cache_v2 / "kits" / "sdlc" / "SKILL.md").write_text(
                "# Kit sdlc\nUpdated skill instructions.\n",
                encoding="utf-8",
            )
            (cache_v2 / "kits" / "sdlc" / "whatsnew.toml").write_text(
                '[whatsnew."2.0.0"]\nsummary = "Kit update"\ndetails = ""\n',
                encoding="utf-8",
            )

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with patch("studio.commands.update.CACHE_DIR", cache_v2), \
                     patch(
                         "studio.commands.kit._read_kits_from_core_toml",
                         return_value={"sdlc": {"path": "config/kits/sdlc"}},
                     ), \
                     patch("studio.commands.kit._read_kit_version_from_core", return_value="1"), \
                     patch("studio.commands.kit.update_kit") as mock_update, \
                     patch("studio.commands.update.show_kit_whatsnew", return_value=False), \
                     patch("sys.stdin") as mock_stdin:
                    mock_stdin.isatty.return_value = True
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update([])
                self.assertEqual(rc, 0)
                mock_update.assert_not_called()
                updated_skill = (adapter / "config" / "kits" / "sdlc" / "SKILL.md").read_text(encoding="utf-8")
                self.assertEqual(updated_skill, original_skill)
            finally:
                os.chdir(cwd)


# =========================================================================
# _maybe_regenerate_agents
# =========================================================================

class TestMaybeRegenerateAgents(unittest.TestCase):
    """Tests for auto-regeneration of agent files during update."""

    def _make_project_with_agents(self, root: Path, cache: Path) -> Path:
        """Create a project with init + generate-agents for one agent."""
        _make_cache(cache)
        cypilot_dir = _init_project(root, cache)

        # Create a fake .core/skills/studio/SKILL.md (needed by agents)
        skill_src = cypilot_dir / ".core" / "skills" / "studio" / "SKILL.md"
        skill_src.parent.mkdir(parents=True, exist_ok=True)
        skill_src.write_text(
            "---\nname: studio\ndescription: Test skill\n---\nContent\n",
            encoding="utf-8",
        )
        return cypilot_dir

    def test_no_changes_returns_empty(self):
        """When copy_results are all 'skipped', no agents are regenerated."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            result = _maybe_regenerate_agents(
                {"architecture": "skipped", "skills": "skipped"},
                {"sdlc": {"version": {"status": "current"}}},
                root, root / ".cf-studio",
            )
            self.assertEqual(result, [])

    def test_core_updated_regenerates_existing_agents(self):
        """When core is updated, agents with existing Cypilot-specific files are regenerated."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            # Create Constructor Studio-specific windsurf marker file
            wf = root / ".windsurf" / "workflows" / "cf.md"
            wf.parent.mkdir(parents=True)
            wf.write_text("old", encoding="utf-8")

            result = _maybe_regenerate_agents(
                {"skills": "updated", "architecture": "updated"},
                {"sdlc": {"version": {"status": "current"}}},
                root, cypilot_dir,
            )
            self.assertIn("windsurf", result)
            # Shared .agents/skills/ file should have been created
            agents_skill = root / ".agents" / "skills" / "cf" / "SKILL.md"
            self.assertTrue(agents_skill.exists())

    def test_kit_migrated_triggers_regen(self):
        """When a kit is migrated, agents are regenerated."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            # Create Constructor Studio-specific windsurf marker file
            wf = root / ".windsurf" / "workflows" / "cf.md"
            wf.parent.mkdir(parents=True)
            wf.write_text("old", encoding="utf-8")

            result = _maybe_regenerate_agents(
                {"skills": "skipped"},
                {"sdlc": {"version": {"status": "migrated"}}},
                root, cypilot_dir,
            )
            self.assertIn("windsurf", result)

    def test_no_existing_agent_files_skips(self):
        """When no agent output files exist on disk, none are regenerated."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            # Don't create any agent files — all should be skipped
            result = _maybe_regenerate_agents(
                {"skills": "updated"},
                {},
                root, cypilot_dir,
            )
            self.assertEqual(result, [])

    def test_cmd_update_pipeline_regenerates_agents(self):
        """Full cmd_update pipeline: agents are regenerated when core updates."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            # Place SKILL.md in the cache's skills dir so cmd_update copies it
            # to .core/skills/cypilot/SKILL.md (needed by _process_single_agent).
            cache_skill = cache / "skills" / "cypilot" / "SKILL.md"
            cache_skill.parent.mkdir(parents=True, exist_ok=True)
            cache_skill.write_text(
                "---\nname: cypilot\ndescription: Test skill\n---\nContent\n",
                encoding="utf-8",
            )

            # Create Constructor Studio-specific windsurf marker file
            wf = root / ".windsurf" / "workflows" / "cf.md"
            wf.parent.mkdir(parents=True)
            wf.write_text("old", encoding="utf-8")

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache),
                    # _migrate_kit_sources performs a network fetch on init.py-stripped
                    # GitHub sources; isolate by patching to a no-op.
                    patch("studio.commands.update._migrate_kit_sources", return_value={}),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update([])
                self.assertEqual(rc, 0)
                out = json.loads(buf.getvalue())
                self.assertIn("agents_regenerated", out["actions"])
                self.assertIn("windsurf", out["actions"]["agents_regenerated"])
            finally:
                os.chdir(cwd)

    def test_only_installed_agents_regenerated(self):
        """Only agents with Cypilot-specific files are regenerated, others skipped."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            # Create Constructor Studio-specific cursor file + Claude skill file
            cursor_cmd = root / ".cursor" / "commands" / "cf.md"
            cursor_cmd.parent.mkdir(parents=True)
            cursor_cmd.write_text("old", encoding="utf-8")
            (root / ".claude" / "skills" / "cf").mkdir(parents=True)
            (root / ".claude" / "skills" / "cf" / "SKILL.md").write_text("old", encoding="utf-8")

            result = _maybe_regenerate_agents(
                {"skills": "updated"},
                {},
                root, cypilot_dir,
            )
            # cursor has .cursor/commands/cf-constructor.md → regenerated
            self.assertIn("cursor", result)
            # claude has .claude/skills/cf-constructor/SKILL.md → regenerated
            self.assertIn("claude", result)
            # windsurf has no Constructor Studio-specific file → not regenerated
            self.assertNotIn("windsurf", result)

    def test_shared_agents_skills_does_not_trigger_all(self):
        """Shared .agents/skills/cf/SKILL.md triggers only OpenAI (legacy compat), not others."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            # Only create shared .agents/skills/cf/SKILL.md — no tool-specific files
            agents_skill = root / ".agents" / "skills" / "cf" / "SKILL.md"
            agents_skill.parent.mkdir(parents=True, exist_ok=True)
            agents_skill.write_text("old", encoding="utf-8")

            result = _maybe_regenerate_agents(
                {"skills": "updated"},
                {},
                root, cypilot_dir,
            )
            # .agents/skills/cf/SKILL.md matches openai (legacy compat)
            self.assertIn("openai", result)
            # windsurf, cursor, copilot have no Cypilot-specific markers
            self.assertNotIn("windsurf", result)
            self.assertNotIn("cursor", result)
            self.assertNotIn("copilot", result)

    def test_unrelated_cursor_commands_does_not_trigger(self):
        """Unrelated .cursor/commands/other.md must NOT trigger Cursor regeneration."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            # Create unrelated cursor file — not a Cypilot-generated file
            unrelated = root / ".cursor" / "commands" / "other.md"
            unrelated.parent.mkdir(parents=True)
            unrelated.write_text("# unrelated tool command", encoding="utf-8")

            result = _maybe_regenerate_agents(
                {"skills": "updated"}, {}, root, cypilot_dir,
            )
            self.assertNotIn("cursor", result)

    def test_unrelated_github_prompts_does_not_trigger(self):
        """Unrelated .github/prompts/unrelated.md must NOT trigger Copilot regeneration."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            unrelated = root / ".github" / "prompts" / "unrelated.prompt.md"
            unrelated.parent.mkdir(parents=True)
            unrelated.write_text("# unrelated prompt", encoding="utf-8")

            result = _maybe_regenerate_agents(
                {"skills": "updated"}, {}, root, cypilot_dir,
            )
            self.assertNotIn("copilot", result)

    def test_unrelated_windsurf_workflows_does_not_trigger(self):
        """Unrelated .windsurf/workflows/other.md must NOT trigger Windsurf regeneration."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            unrelated = root / ".windsurf" / "workflows" / "other.md"
            unrelated.parent.mkdir(parents=True)
            unrelated.write_text("# unrelated workflow", encoding="utf-8")

            result = _maybe_regenerate_agents(
                {"skills": "updated"}, {}, root, cypilot_dir,
            )
            self.assertNotIn("windsurf", result)

    def test_legacy_openai_with_shared_skill_only(self):
        """Legacy OpenAI install with only .agents/skills/cypilot/SKILL.md is detected."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            # Simulate legacy OpenAI: only shared skill, no .codex/ marker
            agents_skill = root / ".agents" / "skills" / "cf" / "SKILL.md"
            agents_skill.parent.mkdir(parents=True, exist_ok=True)
            agents_skill.write_text("old", encoding="utf-8")

            result = _maybe_regenerate_agents(
                {"skills": "updated"}, {}, root, cypilot_dir,
            )
            self.assertIn("openai", result)

    def test_shared_skill_with_cursor_does_not_trigger_openai(self):
        """When cursor marker exists alongside shared skill, OpenAI must NOT be detected."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            # Shared skill + cursor-specific marker
            agents_skill = root / ".agents" / "skills" / "cf" / "SKILL.md"
            agents_skill.parent.mkdir(parents=True, exist_ok=True)
            agents_skill.write_text("old", encoding="utf-8")
            cursor_cmd = root / ".cursor" / "commands" / "cf.md"
            cursor_cmd.parent.mkdir(parents=True)
            cursor_cmd.write_text("old", encoding="utf-8")

            result = _maybe_regenerate_agents(
                {"skills": "updated"}, {}, root, cypilot_dir,
            )
            self.assertIn("cursor", result)
            self.assertNotIn("openai", result)

    def test_copilot_detected_via_cypilot_installed_marker(self):
        """Copilot is detected via .github/.cf-installed marker."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            marker = root / ".github" / ".cf-installed"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("# Constructor Studio Copilot integration marker\n", encoding="utf-8")

            result = _maybe_regenerate_agents(
                {"skills": "updated"}, {}, root, cypilot_dir,
            )
            self.assertIn("copilot", result)

    def test_legacy_copilot_detected_via_managed_instructions(self):
        """Legacy Copilot install detected via Constructor Studio-managed copilot-instructions.md."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            # Constructor Studio-managed legacy file (starts with "# Constructor Studio")
            instructions = root / ".github" / "copilot-instructions.md"
            instructions.parent.mkdir(parents=True, exist_ok=True)
            instructions.write_text("# Constructor Studio\n\nManaged content.\n", encoding="utf-8")

            result = _maybe_regenerate_agents(
                {"skills": "updated"}, {}, root, cypilot_dir,
            )
            self.assertIn("copilot", result)

    def test_user_copilot_instructions_does_not_trigger_detection(self):
        """User-authored .github/copilot-instructions.md must NOT trigger Copilot detection."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            # User's own copilot-instructions.md without Cypilot marker
            instructions = root / ".github" / "copilot-instructions.md"
            instructions.parent.mkdir(parents=True, exist_ok=True)
            instructions.write_text("# My project\nUse TypeScript.\n", encoding="utf-8")

            result = _maybe_regenerate_agents(
                {"skills": "updated"}, {}, root, cypilot_dir,
            )
            self.assertNotIn("copilot", result)

    def test_mixed_openai_with_cypilot_codex_agents_detected(self):
        """Legacy OpenAI with Cypilot-generated .codex/agents/ content is detected."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            # Mixed install: cursor marker + .codex/agents/ with Constructor Studio-generated toml
            cursor_cmd = root / ".cursor" / "commands" / "cf.md"
            cursor_cmd.parent.mkdir(parents=True)
            cursor_cmd.write_text("old", encoding="utf-8")
            codex_agent = root / ".codex" / "agents" / "cf-constructor-ralphex.toml"
            codex_agent.parent.mkdir(parents=True, exist_ok=True)
            codex_agent.write_text(
                'name = "cf-constructor-ralphex"\n'
                'developer_instructions = """\n'
                'ALWAYS open and follow `{cf-constructor-path}/.core/prompts/ralphex.md`\n'
                '"""\n',
                encoding="utf-8",
            )

            _maybe_regenerate_agents(
                {"skills": "updated"}, {}, root, cypilot_dir,
            )
            # OpenAI detected and auto-migrated: primary marker created
            marker = root / ".codex" / ".cf-installed"
            self.assertTrue(marker.exists(),
                ".codex/.cf-installed must be auto-created for legacy OpenAI")

    def test_non_cypilot_codex_agents_does_not_trigger_openai(self):
        """Arbitrary .codex/agents/ content (not Cypilot-generated) must NOT trigger OpenAI."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            # .codex/agents/ with user-created toml (no Cypilot marker)
            codex_agent = root / ".codex" / "agents" / "custom.toml"
            codex_agent.parent.mkdir(parents=True, exist_ok=True)
            codex_agent.write_text('name = "custom"\ndescription = "My agent"\n', encoding="utf-8")

            result = _maybe_regenerate_agents(
                {"skills": "updated"}, {}, root, cypilot_dir,
            )
            self.assertNotIn("openai", result)

    def test_bare_codex_dir_does_not_trigger_openai(self):
        """An empty .codex/ directory must NOT trigger OpenAI detection."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            # Bare .codex/agents/ directory with no content
            codex_dir = root / ".codex" / "agents"
            codex_dir.mkdir(parents=True, exist_ok=True)

            result = _maybe_regenerate_agents(
                {"skills": "updated"}, {}, root, cypilot_dir,
            )
            self.assertNotIn("openai", result)

    def test_legacy_windsurf_skill_triggers_regeneration(self):
        """Legacy .windsurf/skills/cypilot/SKILL.md with Cypilot content triggers regeneration."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            legacy = root / ".windsurf" / "skills" / "cypilot" / "SKILL.md"
            legacy.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text("ALWAYS open and follow `{cf-studio-path}/.core/skills/cypilot/SKILL.md`\n")

            result = _maybe_regenerate_agents(
                {"skills": "updated"}, {}, root, cypilot_dir,
            )
            self.assertIn("windsurf", result)

    def test_legacy_cursor_rules_triggers_regeneration(self):
        """Legacy .cursor/rules/cypilot.mdc with Cypilot content triggers regeneration."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            legacy = root / ".cursor" / "rules" / "studio.mdc"
            legacy.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text("ALWAYS open and follow `{cf-studio-path}/.core/skills/cypilot/SKILL.md`\n")

            result = _maybe_regenerate_agents(
                {"skills": "updated"}, {}, root, cypilot_dir,
            )
            self.assertIn("cursor", result)

    def test_copilot_detected_via_prompt_file_in_update(self):
        """Copilot with user-authored instructions but existing prompt file is detectable."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            # User-authored copilot-instructions.md (not Cypilot-managed)
            instructions = root / ".github" / "copilot-instructions.md"
            instructions.parent.mkdir(parents=True, exist_ok=True)
            instructions.write_text("# My project\nUse TypeScript.\n", encoding="utf-8")
            # But Cypilot prompt file exists
            prompt = root / ".github" / "prompts" / "studio.prompt.md"
            prompt.parent.mkdir(parents=True, exist_ok=True)
            prompt.write_text("---\nname: cypilot\n---\nALWAYS open and follow ...\n")

            result = _maybe_regenerate_agents(
                {"skills": "updated"}, {}, root, cypilot_dir,
            )
            self.assertIn("copilot", result)

    def test_shared_skill_with_legacy_copilot_prompt_does_not_trigger_openai(self):
        """Legacy Copilot prompt fallback must suppress OpenAI shared-skill detection."""
        from studio.commands.update import _maybe_regenerate_agents
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()
            cache = Path(td) / "cache"
            cypilot_dir = self._make_project_with_agents(root, cache)

            agents_skill = root / ".agents" / "skills" / "cypilot" / "SKILL.md"
            agents_skill.parent.mkdir(parents=True, exist_ok=True)
            agents_skill.write_text("old", encoding="utf-8")
            prompt = root / ".github" / "prompts" / "studio.prompt.md"
            prompt.parent.mkdir(parents=True, exist_ok=True)
            prompt.write_text("---\nname: cypilot\n---\nALWAYS open and follow ...\n", encoding="utf-8")

            result = _maybe_regenerate_agents(
                {"skills": "updated"}, {}, root, cypilot_dir,
            )
            self.assertIn("copilot", result)
            self.assertNotIn("openai", result)


class TestHumanUpdateOk(unittest.TestCase):
    """Cover _human_update_ok display branches."""

    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_basic_pass(self):
        from studio.commands.update import _human_update_ok
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_update_ok({
                "status": "PASS",
                "project_root": "/tmp/proj",
                "cypilot_dir": "/tmp/proj/cypilot",
                "dry_run": False,
                "actions": {},
            })
        out = buf.getvalue()
        self.assertIn("Update complete", out)

    def test_dry_run(self):
        from studio.commands.update import _human_update_ok
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_update_ok({
                "status": "PASS",
                "project_root": "/tmp/proj",
                "cypilot_dir": "/tmp/proj/cypilot",
                "dry_run": True,
                "actions": {},
            })
        out = buf.getvalue()
        self.assertIn("dry-run", out.lower())

    def test_with_errors_and_warnings(self):
        from studio.commands.update import _human_update_ok
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_update_ok({
                "status": "WARN",
                "project_root": "/tmp/proj",
                "cypilot_dir": "/tmp/proj/cypilot",
                "dry_run": False,
                "actions": {},
                "errors": [{"path": "kit.py", "error": "bad"}, "plain error"],
                "warnings": ["warn1"],
            })
        out = buf.getvalue()
        self.assertIn("bad", out)
        self.assertIn("warn1", out)
        self.assertIn("warnings", out.lower())

    def test_with_kits_data(self):
        from studio.commands.update import _human_update_ok
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_update_ok({
                "status": "PASS",
                "project_root": "/tmp/proj",
                "cypilot_dir": "/tmp/proj/cypilot",
                "dry_run": False,
                "actions": {
                    "kits": {
                        "sdlc": {
                            "version": {"status": "created"},
                            "gen": {"files_written": 10, "artifact_kinds": ["DESIGN"]},
                            "reference": "installed",
                        },
                        "bad": "string_value",
                    },
                },
            })
        out = buf.getvalue()
        self.assertIn("sdlc", out)
        self.assertIn("Kits", out)

    def test_with_kits_skipped_tracking_summary(self):
        from studio.commands.update import _human_update_ok
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_update_ok({
                "status": "PASS",
                "project_root": "/tmp/proj",
                "studio_dir": "/tmp/proj/.bootstrap",
                "dry_run": False,
                "actions": {
                    "kits": {
                        "status": "skipped",
                        "reason": "--with-kits not enabled",
                        "kit_tracking": {
                            "default": "tracked",
                            "kits": {"sdlc": "ignored"},
                        },
                    },
                },
            })
        out = buf.getvalue()
        self.assertIn("Kits: skipped", out)
        self.assertIn("--with-kits not enabled", out)
        self.assertIn("kit_tracking=", out)

    def test_with_core_update(self):
        from studio.commands.update import _human_update_ok
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_update_ok({
                "status": "PASS",
                "project_root": "/tmp/proj",
                "cypilot_dir": "/tmp/proj/cypilot",
                "dry_run": False,
                "actions": {
                    "core_update": {"architecture/": "updated", "skills/": "created"},
                    "file.md": "created",
                    "other.md": "updated",
                    "keep.md": "unchanged",
                },
            })
        out = buf.getvalue()
        self.assertIn("Core", out)
        self.assertIn("Created", out)
        self.assertIn("Updated", out)

    def test_with_agents_regenerated(self):
        from studio.commands.update import _human_update_ok
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_update_ok({
                "status": "PASS",
                "project_root": "/tmp/proj",
                "cypilot_dir": "/tmp/proj/cypilot",
                "dry_run": False,
                "actions": {
                    "agents_regenerated": ["cursor", "windsurf"],
                },
            })
        out = buf.getvalue()
        self.assertIn("cursor", out)

    def test_with_dict_and_list_actions(self):
        from studio.commands.update import _human_update_ok
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_update_ok({
                "status": "PASS",
                "project_root": "/tmp/proj",
                "cypilot_dir": "/tmp/proj/cypilot",
                "dry_run": False,
                "actions": {
                    "layout_migration": {"sdlc": "migrated"},
                    "extra_list": ["item1", "item2"],
                },
            })
        out = buf.getvalue()
        self.assertIn("layout_migration", out)
        self.assertIn("sdlc", out)
        self.assertIn("extra_list", out)
        self.assertIn("item1", out)


# ---------------------------------------------------------------------------
# _deduplicate_legacy_kits
# ---------------------------------------------------------------------------

class TestDeduplicateLegacyKits(unittest.TestCase):
    def test_no_core_toml(self):
        from studio.commands.update import _deduplicate_legacy_kits
        self.assertEqual(_deduplicate_legacy_kits(Path("/nonexistent")), {})

    def test_no_legacy_slugs(self):
        from studio.commands.update import _deduplicate_legacy_kits
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            config = Path(td)
            toml_utils.dump({"kits": {"sdlc": {"path": "config/kits/sdlc"}}}, config / "core.toml")
            self.assertEqual(_deduplicate_legacy_kits(config), {})

    def test_dedup_same_path(self):
        """When studio-sdlc and sdlc both exist with same path, legacy is removed."""
        from studio.commands.update import _deduplicate_legacy_kits
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            config = Path(td)
            toml_utils.dump({
                "kits": {
                    "studio-sdlc": {"path": "config/kits/sdlc", "format": "CFS"},
                    "sdlc": {"path": "config/kits/sdlc", "format": "CFS"},
                },
            }, config / "core.toml")
            result = _deduplicate_legacy_kits(config)
            self.assertEqual(result, {"studio-sdlc": "sdlc"})
            with open(config / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertNotIn("studio-sdlc", data["kits"])
            self.assertIn("sdlc", data["kits"])

    def test_dedup_different_paths_skipped(self):
        from studio.commands.update import _deduplicate_legacy_kits
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            config = Path(td)
            toml_utils.dump({
                "kits": {
                    "studio-sdlc": {"path": "kits/studio-sdlc"},
                    "sdlc": {"path": "config/kits/sdlc"},
                },
            }, config / "core.toml")
            result = _deduplicate_legacy_kits(config)
            self.assertEqual(result, {})

    def test_dedup_updates_artifacts_toml(self):
        from studio.commands.update import _deduplicate_legacy_kits
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            config = Path(td)
            toml_utils.dump({
                "kits": {
                    "studio-sdlc": {"path": "config/kits/sdlc"},
                    "sdlc": {"path": "config/kits/sdlc"},
                },
            }, config / "core.toml")
            toml_utils.dump({
                "systems": [{"name": "default", "kit": "studio-sdlc"}],
            }, config / "artifacts.toml")
            _deduplicate_legacy_kits(config)
            with open(config / "artifacts.toml", "rb") as f:
                art = tomllib.load(f)
            self.assertEqual(art["systems"][0]["kit"], "sdlc")

    def test_artifacts_toml_fixed_even_without_core_dedup(self):
        """artifacts.toml legacy slug is fixed even when core.toml has only canonical slug."""
        from studio.commands.update import _deduplicate_legacy_kits
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            config = Path(td)
            # core.toml only has canonical slug — no dedup needed
            toml_utils.dump({
                "kits": {
                    "sdlc": {"path": "config/kits/sdlc"},
                },
            }, config / "core.toml")
            # artifacts.toml still references the legacy slug
            toml_utils.dump({
                "systems": [{"name": "Myapp", "slug": "myapp", "kit": "studio-sdlc"}],
            }, config / "artifacts.toml")
            result = _deduplicate_legacy_kits(config)
            self.assertEqual(result, {"studio-sdlc": "sdlc"})
            with open(config / "artifacts.toml", "rb") as f:
                art = tomllib.load(f)
            self.assertEqual(art["systems"][0]["kit"], "sdlc")


# ---------------------------------------------------------------------------
# _migrate_kit_sources
# ---------------------------------------------------------------------------

class TestMigrateKitSources(unittest.TestCase):
    def test_no_core_toml(self):
        from studio.commands.update import _migrate_kit_sources
        self.assertEqual(_migrate_kit_sources(Path("/nonexistent")), {})

    def test_already_has_source(self):
        from studio.commands.update import _migrate_kit_sources
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            config = Path(td)
            toml_utils.dump({
                "kits": {"sdlc": {"source": "github:cyberfabric/cyber-pilot-kit-sdlc"}},
            }, config / "core.toml")
            self.assertEqual(_migrate_kit_sources(config), {})

    def test_adds_known_source(self):
        from studio.commands.update import _migrate_kit_sources
        from studio.utils import toml_utils
        import tomllib
        with TemporaryDirectory() as td:
            config = Path(td)
            toml_utils.dump({
                "kits": {"sdlc": {"path": "config/kits/sdlc"}},
            }, config / "core.toml")
            result = _migrate_kit_sources(config)
            self.assertEqual(result, {"sdlc": "github:constructorfabric/studio-kit-sdlc"})
            with open(config / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(data["kits"]["sdlc"]["source"], "github:constructorfabric/studio-kit-sdlc")

    def test_unknown_kit_skipped(self):
        from studio.commands.update import _migrate_kit_sources
        from studio.utils import toml_utils
        with TemporaryDirectory() as td:
            config = Path(td)
            toml_utils.dump({
                "kits": {"custom": {"path": "config/kits/custom"}},
            }, config / "core.toml")
            self.assertEqual(_migrate_kit_sources(config), {})

    def test_corrupt_core_toml(self):
        from studio.commands.update import _migrate_kit_sources
        with TemporaryDirectory() as td:
            (Path(td) / "core.toml").write_text("{{bad", encoding="utf-8")
            self.assertEqual(_migrate_kit_sources(Path(td)), {})


# ---------------------------------------------------------------------------
# Human formatter edge cases
# ---------------------------------------------------------------------------

class TestHumanUpdateOkEdgeCases(unittest.TestCase):
    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_kit_updated_status(self):
        from studio.commands.update import _human_update_ok
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_update_ok({
                "status": "PASS",
                "project_root": "/tmp/proj",
                "cypilot_dir": "/tmp/proj/cypilot",
                "dry_run": False,
                "actions": {
                    "kits": {
                        "sdlc": {
                            "version": {"status": "updated"},
                            "gen": {"files_written": 2, "accepted_files": ["a.md", "b.md"]},
                            "gen_rejected": ["c.md"],
                        },
                    },
                },
            })
        out = buf.getvalue()
        self.assertIn("updated", out)
        self.assertIn("a.md", out)
        self.assertIn("c.md", out)

    def test_kit_partial_status(self):
        from studio.commands.update import _human_update_ok
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_update_ok({
                "status": "WARN",
                "project_root": "/tmp/proj",
                "cypilot_dir": "/tmp/proj/cypilot",
                "dry_run": False,
                "actions": {
                    "kits": {
                        "sdlc": {
                            "version": {"status": "partial"},
                            "gen": {"files_written": 1, "accepted_files": ["a.md"]},
                            "gen_rejected": ["b.md", "c.md"],
                        },
                    },
                },
                "warnings": ["some warning"],
            })
        out = buf.getvalue()
        self.assertIn("partial", out)
        self.assertIn("declined", out)

    def test_dry_run_output(self):
        from studio.commands.update import _human_update_ok
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_update_ok({
                "status": "PASS",
                "project_root": "/tmp/proj",
                "cypilot_dir": "/tmp/proj/cypilot",
                "dry_run": True,
                "actions": {},
            })
        out = buf.getvalue()
        self.assertIn("Dry run", out)

    def test_nested_dict_action(self):
        from studio.commands.update import _human_update_ok
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_update_ok({
                "status": "PASS",
                "project_root": "/tmp/proj",
                "cypilot_dir": "/tmp/proj/cypilot",
                "dry_run": False,
                "actions": {
                    "layout_migration": {"sdlc": "migrated"},
                    "some_list": ["item1"],
                    "nested_complex": {"sub": {"deep": True}},
                },
            })
        out = buf.getvalue()
        self.assertIn("layout_migration", out)
        self.assertIn("some_list", out)

    def test_errors_in_output(self):
        from studio.commands.update import _human_update_ok
        buf = io.StringIO()
        with redirect_stderr(buf):
            _human_update_ok({
                "status": "WARN",
                "project_root": "/tmp/proj",
                "cypilot_dir": "/tmp/proj/cypilot",
                "dry_run": False,
                "actions": {},
                "errors": [
                    {"path": "sdlc", "error": "download failed"},
                    "plain error string",
                ],
                "warnings": ["w1"],
            })
        out = buf.getvalue()
        self.assertIn("download failed", out)
        self.assertIn("plain error string", out)


# ---------------------------------------------------------------------------
# cmd_update with layout migration + kit source migration paths
# ---------------------------------------------------------------------------

class TestCmdUpdateLayoutMigration(unittest.TestCase):
    def test_update_triggers_layout_migration(self):
        """cmd_update migrates old kits/ layout to config/kits/."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache = Path(td) / "cache"
            _make_cache(cache)
            adapter = _init_project(root, cache)

            # Create old layout: cypilot/kits/sdlc/ directory
            old_kits = adapter / "kits" / "sdlc"
            old_kits.mkdir(parents=True)
            (old_kits / "conf.toml").write_text("version = 1\n", encoding="utf-8")
            (old_kits / "artifacts").mkdir()
            (old_kits / "artifacts" / "old.md").write_text("# old\n", encoding="utf-8")

            kit_src = cache / "kits" / "sdlc"
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache),
                    patch(
                        "studio.commands.kit._download_kit_from_github",
                        return_value=(kit_src, "1"),
                    ),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update([])
                self.assertEqual(rc, 0)
                # Old kits/ dir should be removed
                self.assertFalse(old_kits.exists())
            finally:
                os.chdir(cwd)

    def test_update_download_failure(self):
        """When GitHub download fails, update continues with errors."""
        from studio.commands.update import cmd_update
        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache = Path(td) / "cache"
            _make_cache(cache)
            _init_project(root, cache)

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache),
                    patch(
                        "studio.commands.kit._download_kit_from_github",
                        side_effect=RuntimeError("rate limit"),
                    ),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update([])
                # May warn but shouldn't crash
                self.assertIn(rc, [0, 1])
            finally:
                os.chdir(cwd)


# ---------------------------------------------------------------------------
# _cleanup_legacy_blueprint_dirs (ADR-0001)
# ---------------------------------------------------------------------------

class TestCleanupLegacyBlueprintDirs(unittest.TestCase):
    """Tests for removing leftover blueprints/ from config/kits/*/."""

    def test_removes_blueprints_dir(self):
        from studio.commands.update import _cleanup_legacy_blueprint_dirs
        with TemporaryDirectory() as td:
            config = Path(td)
            bp = config / "kits" / "sdlc" / "blueprints"
            bp.mkdir(parents=True)
            (bp / "PRD.md").write_text("# old blueprint\n", encoding="utf-8")
            _cleanup_legacy_blueprint_dirs(config)
            self.assertFalse(bp.exists())
            # Kit dir itself should remain
            self.assertTrue((config / "kits" / "sdlc").is_dir())

    def test_noop_when_no_blueprints(self):
        from studio.commands.update import _cleanup_legacy_blueprint_dirs
        with TemporaryDirectory() as td:
            config = Path(td)
            kit = config / "kits" / "sdlc"
            kit.mkdir(parents=True)
            (kit / "SKILL.md").write_text("# skill\n", encoding="utf-8")
            _cleanup_legacy_blueprint_dirs(config)
            self.assertTrue((kit / "SKILL.md").is_file())

    def test_noop_when_no_kits_dir(self):
        from studio.commands.update import _cleanup_legacy_blueprint_dirs
        with TemporaryDirectory() as td:
            config = Path(td)
            _cleanup_legacy_blueprint_dirs(config)  # should not raise


# ---------------------------------------------------------------------------
# _remove_system_from_core_toml (ADR-0014)
# ---------------------------------------------------------------------------

class TestRemoveSystemFromCoreToml(unittest.TestCase):
    """Tests for the [system] removal migration step."""

    def test_removes_system_section(self):
        from studio.commands.update import _remove_system_from_core_toml
        with TemporaryDirectory() as td:
            config_dir = Path(td)
            _write_toml(config_dir / "core.toml", {
                "version": "1.0",
                "project_root": "..",
                "system": {"name": "Test", "slug": "test", "kit": "sdlc"},
                "kits": {"sdlc": {"format": "CFS", "path": "config/kits/sdlc"}},
            })
            result = _remove_system_from_core_toml(config_dir)
            self.assertTrue(result)

            from studio.utils import toml_utils
            core = toml_utils.load(config_dir / "core.toml")
            self.assertNotIn("system", core)
            self.assertEqual(core["version"], "1.0")
            self.assertIn("sdlc", core["kits"])

    def test_no_system_section_is_noop(self):
        from studio.commands.update import _remove_system_from_core_toml
        with TemporaryDirectory() as td:
            config_dir = Path(td)
            _write_toml(config_dir / "core.toml", {
                "version": "1.0",
                "project_root": "..",
                "kits": {},
            })
            result = _remove_system_from_core_toml(config_dir)
            self.assertFalse(result)

    def test_missing_core_toml(self):
        from studio.commands.update import _remove_system_from_core_toml
        result = _remove_system_from_core_toml(Path("/nonexistent"))
        self.assertFalse(result)

    def test_corrupt_core_toml(self):
        from studio.commands.update import _remove_system_from_core_toml
        with TemporaryDirectory() as td:
            config_dir = Path(td)
            (config_dir / "core.toml").write_text("{{invalid", encoding="utf-8")
            result = _remove_system_from_core_toml(config_dir)
            self.assertFalse(result)


# ---------------------------------------------------------------------------
# _default_core_toml (ADR-0014)
# ---------------------------------------------------------------------------

class TestDefaultCoreToml(unittest.TestCase):
    """Verify _default_core_toml no longer includes [system]."""

    def test_no_system_section(self):
        from studio.commands.init import _default_core_toml
        core = _default_core_toml()
        self.assertNotIn("system", core)
        self.assertEqual(core["version"], "1.0")
        self.assertEqual(core["project_root"], "..")
        # Kits are empty by default — registered dynamically via install_kit()
        self.assertEqual(core["kits"], {})


# ---------------------------------------------------------------------------
# WP7: _maybe_migrate_legacy_to_manifest (update pipeline integration)
# ---------------------------------------------------------------------------

def _make_kit_source_with_manifest(td: Path, slug: str = "testkit") -> Path:
    """Create a kit source with manifest.toml and source files for WP7 tests."""
    kit = td / slug
    kit.mkdir(parents=True, exist_ok=True)

    (kit / "artifacts" / "ADR").mkdir(parents=True)
    (kit / "artifacts" / "ADR" / "template.md").write_text("# ADR\n", encoding="utf-8")
    (kit / "artifacts" / "ADR" / "rules.md").write_text("# Rules\n", encoding="utf-8")
    (kit / "constraints.toml").write_text('[artifacts]\n', encoding="utf-8")
    (kit / "SKILL.md").write_text(f"# Kit {slug}\n", encoding="utf-8")

    _write_toml(kit / "conf.toml", {"version": "2.0", "slug": slug})

    import textwrap
    (kit / "manifest.toml").write_text(textwrap.dedent("""\
        [manifest]
        version = "1.0"
        root = "{cf-studio-path}/config/kits/{slug}"
        user_modifiable = false

        [[resources]]
        id = "adr_artifacts"
        description = "ADR artifact definitions"
        source = "artifacts/ADR"
        default_path = "artifacts/ADR"
        type = "directory"
        user_modifiable = false

        [[resources]]
        id = "constraints"
        description = "Kit structural constraints"
        source = "constraints.toml"
        default_path = "constraints.toml"
        type = "file"
        user_modifiable = false

        [[resources]]
        id = "skill"
        description = "Kit skill instructions"
        source = "SKILL.md"
        default_path = "SKILL.md"
        type = "file"
        user_modifiable = false
    """), encoding="utf-8")
    return kit


def _setup_legacy_adapter(td: Path, slug: str = "testkit") -> Path:
    """Set up an adapter with a legacy kit install (no resources in core.toml)."""
    adapter = td / "adapter"
    config = adapter / "config"
    config_kit = config / "kits" / slug
    config_kit.mkdir(parents=True)

    (config_kit / "artifacts" / "ADR").mkdir(parents=True)
    (config_kit / "artifacts" / "ADR" / "template.md").write_text("# ADR\n", encoding="utf-8")
    (config_kit / "artifacts" / "ADR" / "rules.md").write_text("# Rules\n", encoding="utf-8")
    (config_kit / "constraints.toml").write_text('[artifacts]\n', encoding="utf-8")
    (config_kit / "SKILL.md").write_text(f"# Kit {slug}\n", encoding="utf-8")

    _write_toml(config / "core.toml", {
        "version": "1.0",
        "project_root": "..",
        "kits": {
            slug: {
                "format": "CFS",
                "path": f"config/kits/{slug}",
                "version": "2.0",
            }
        },
    })
    return adapter


class TestMaybeMigrateLegacyToManifest(unittest.TestCase):
    """Unit tests for _maybe_migrate_legacy_to_manifest() helper (WP7)."""

    def test_no_manifest_returns_none(self):
        """Kit source without manifest.toml → returns None (no migration)."""
        from studio.commands.update import _maybe_migrate_legacy_to_manifest
        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = td_path / "nokit"
            kit_src.mkdir()
            adapter = _setup_legacy_adapter(td_path, "nokit")
            config_dir = adapter / "config"

            result = _maybe_migrate_legacy_to_manifest(
                "nokit", kit_src, adapter, config_dir, interactive=False,
            )
            self.assertIsNone(result)

    def test_already_has_resources_returns_none(self):
        """Kit with existing resources in core.toml → returns None (skip)."""
        from studio.commands.update import _maybe_migrate_legacy_to_manifest
        import tomllib
        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = _make_kit_source_with_manifest(td_path, "mykit")
            adapter = _setup_legacy_adapter(td_path, "mykit")
            config_dir = adapter / "config"

            # Pre-populate resources in core.toml
            with open(config_dir / "core.toml", "rb") as f:
                data = tomllib.load(f)
            data["kits"]["mykit"]["resources"] = {
                "adr_artifacts": {"path": "config/kits/mykit/artifacts/ADR"},
            }
            _write_toml(config_dir / "core.toml", data)

            result = _maybe_migrate_legacy_to_manifest(
                "mykit", kit_src, adapter, config_dir, interactive=False,
            )
            self.assertIsNone(result)

    def test_triggers_migration_when_needed(self):
        """Source has manifest + no resources → triggers migration, returns result."""
        from studio.commands.update import _maybe_migrate_legacy_to_manifest
        import tomllib
        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = _make_kit_source_with_manifest(td_path, "mykit")
            adapter = _setup_legacy_adapter(td_path, "mykit")
            config_dir = adapter / "config"

            result = _maybe_migrate_legacy_to_manifest(
                "mykit", kit_src, adapter, config_dir, interactive=False,
            )

            self.assertIsNotNone(result)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["migrated_count"], 3)
            self.assertEqual(result["new_count"], 0)

            # Verify resources written to core.toml
            with open(config_dir / "core.toml", "rb") as f:
                data = tomllib.load(f)
            self.assertIn("resources", data["kits"]["mykit"])

    def test_invalid_manifest_returns_none(self):
        """Invalid manifest.toml in kit source → returns None (error handled)."""
        from studio.commands.update import _maybe_migrate_legacy_to_manifest
        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = td_path / "badkit"
            kit_src.mkdir()
            # Write an invalid manifest (missing required fields)
            (kit_src / "manifest.toml").write_text("[manifest]\n", encoding="utf-8")
            adapter = _setup_legacy_adapter(td_path, "badkit")
            config_dir = adapter / "config"

            result = _maybe_migrate_legacy_to_manifest(
                "badkit", kit_src, adapter, config_dir, interactive=False,
            )
            # ValueError from load_manifest is caught → returns None
            self.assertIsNone(result)

    def test_corrupt_manifest_returns_none(self):
        """Corrupt manifest.toml → returns None (exception caught)."""
        from studio.commands.update import _maybe_migrate_legacy_to_manifest
        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_src = td_path / "corrupt"
            kit_src.mkdir()
            (kit_src / "manifest.toml").write_text("{{invalid", encoding="utf-8")
            adapter = _setup_legacy_adapter(td_path, "corrupt")
            config_dir = adapter / "config"

            result = _maybe_migrate_legacy_to_manifest(
                "corrupt", kit_src, adapter, config_dir, interactive=False,
            )
            self.assertIsNone(result)


class TestCmdUpdateManifestMigration(unittest.TestCase):
    """Pipeline integration tests for WP7 manifest migration in cmd_update."""

    def test_update_triggers_manifest_migration_version_match(self):
        """When kit versions match but no resources, migration still triggers.

        Manually sets up a project where:
        - Cache kit has manifest.toml + matching version
        - Installed kit has same version in core.toml but NO resources
        - update_kit returns early ("current") but WP7 catch-all triggers migration
        """
        from studio.commands.update import cmd_update
        import tomllib, textwrap

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()

            # Set up adapter directory manually
            adapter = root / "cypilot"
            config = adapter / "config"
            config_kit = config / "kits" / "sdlc"
            config_kit.mkdir(parents=True)
            (adapter / ".core").mkdir(parents=True)
            (adapter / ".gen").mkdir(parents=True)

            # Create installed kit files
            (config_kit / "constraints.toml").write_text('[artifacts]\n', encoding="utf-8")
            (config_kit / "SKILL.md").write_text("# Kit sdlc\n", encoding="utf-8")
            _write_toml(config_kit / "conf.toml", {"version": "2.0"})

            # core.toml: version matches cache, NO resources
            _write_toml(config / "core.toml", {
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "config/kits/sdlc",
                        "version": "2.0",
                    },
                },
            })

            # AGENTS.md with cypilot_path
            (root / "AGENTS.md").write_text(
                '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "cypilot"\n```\n<!-- /@cf:root-agents -->\n',
                encoding="utf-8",
            )

            # Create cache with matching version + manifest.toml
            cache = Path(td) / "cache"
            _make_cache(cache, kit_version="2.0")
            kit_src = cache / "kits" / "sdlc"
            (kit_src / "constraints.toml").write_text('[artifacts]\n', encoding="utf-8")
            (kit_src / "SKILL.md").write_text("# Kit sdlc\n", encoding="utf-8")
            (kit_src / "manifest.toml").write_text(textwrap.dedent("""\
                [manifest]
                version = "1.0"
                root = "{cf-studio-path}/config/kits/{slug}"
                user_modifiable = false

                [[resources]]
                id = "constraints"
                description = "Kit constraints"
                source = "constraints.toml"
                default_path = "constraints.toml"
                type = "file"
                user_modifiable = false

                [[resources]]
                id = "skill"
                description = "Kit skill"
                source = "SKILL.md"
                default_path = "SKILL.md"
                type = "file"
                user_modifiable = false
            """), encoding="utf-8")

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache),
                    patch(
                        "studio.commands.kit._download_kit_from_github",
                        return_value=(kit_src, "2.0"),
                    ),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["--with-kits", "yes"])
                self.assertEqual(rc, 0)

                # Verify resources were populated in core.toml
                core_toml = config / "core.toml"
                with open(core_toml, "rb") as f:
                    data = tomllib.load(f)
                sdlc_entry = data["kits"]["sdlc"]
                self.assertIn("resources", sdlc_entry)
                self.assertIn("constraints", sdlc_entry["resources"])
                self.assertIn("skill", sdlc_entry["resources"])

                # Check manifest_migration in output
                out = json.loads(buf.getvalue())
                kits = out.get("actions", {}).get("kits", {})
                sdlc_r = kits.get("sdlc", {})
                mig = sdlc_r.get("manifest_migration")
                self.assertIsNotNone(mig)
                self.assertEqual(mig["status"], "PASS")
            finally:
                os.chdir(cwd)

    def test_update_manifest_migration_exception_is_reported_as_error(self):
        """Unexpected manifest-migration exceptions must fail update."""
        from studio.commands.update import cmd_update

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            cache = Path(td) / "cache"
            _make_cache(cache, kit_version=1)
            _init_project(root, cache)

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache),
                    patch(
                        "studio.commands.kit._download_kit_from_github",
                        return_value=(cache / "kits" / "sdlc", "1.0"),
                    ),
                    patch(
                        "studio.commands.update._maybe_migrate_legacy_to_manifest",
                        side_effect=RuntimeError("simulated migration crash"),
                    ),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["-y", "--with-kits", "yes"])

                self.assertEqual(rc, 1)
                out = json.loads(buf.getvalue())
                self.assertNotEqual(out.get("status"), "PASS")
                errors = out.get("errors", [])
                self.assertTrue(
                    any(
                        "manifest migration raised unexpected exception" in e.get("error", "")
                        for e in errors
                    ),
                    errors,
                )
            finally:
                os.chdir(cwd)

    def test_update_skips_migration_when_resources_exist(self):
        """When kit already has resources in core.toml, migration is skipped."""
        from studio.commands.update import cmd_update
        import textwrap

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()

            adapter = root / "cypilot"
            config = adapter / "config"
            config_kit = config / "kits" / "sdlc"
            config_kit.mkdir(parents=True)
            (adapter / ".core").mkdir(parents=True)
            (adapter / ".gen").mkdir(parents=True)

            (config_kit / "constraints.toml").write_text('[artifacts]\n', encoding="utf-8")
            (config_kit / "SKILL.md").write_text("# Kit sdlc\n", encoding="utf-8")
            _write_toml(config_kit / "conf.toml", {"version": "2.0"})

            # core.toml WITH resources already populated
            _write_toml(config / "core.toml", {
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "config/kits/sdlc",
                        "version": "2.0",
                        "resources": {
                            "constraints": {"path": "config/kits/sdlc/constraints.toml"},
                        },
                    },
                },
            })

            (root / "AGENTS.md").write_text(
                '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "cypilot"\n```\n<!-- /@cf:root-agents -->\n',
                encoding="utf-8",
            )

            cache = Path(td) / "cache"
            _make_cache(cache, kit_version="2.0")
            kit_src = cache / "kits" / "sdlc"
            (kit_src / "manifest.toml").write_text(textwrap.dedent("""\
                [manifest]
                version = "1.0"
                root = "{cf-studio-path}/config/kits/{slug}"
                user_modifiable = false

                [[resources]]
                id = "constraints"
                source = "constraints.toml"
                default_path = "constraints.toml"
                type = "file"
                user_modifiable = false
            """), encoding="utf-8")

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache),
                    patch(
                        "studio.commands.kit._download_kit_from_github",
                        return_value=(kit_src, "2.0"),
                    ),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update([])
                self.assertEqual(rc, 0)

                out = json.loads(buf.getvalue())
                kits = out.get("actions", {}).get("kits", {})
                sdlc_r = kits.get("sdlc", {})
                # No manifest_migration key — migration was skipped
                self.assertNotIn("manifest_migration", sdlc_r)
            finally:
                os.chdir(cwd)

    def test_dry_run_skips_migration(self):
        """--dry-run does not trigger manifest migration."""
        from studio.commands.update import cmd_update
        import tomllib, textwrap

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            (root / ".git").mkdir()

            adapter = root / "cypilot"
            config = adapter / "config"
            config_kit = config / "kits" / "sdlc"
            config_kit.mkdir(parents=True)
            (adapter / ".core").mkdir(parents=True)
            (adapter / ".gen").mkdir(parents=True)

            (config_kit / "constraints.toml").write_text('[artifacts]\n', encoding="utf-8")
            (config_kit / "SKILL.md").write_text("# Kit sdlc\n", encoding="utf-8")
            _write_toml(config_kit / "conf.toml", {"version": "2.0"})

            # core.toml: NO resources
            _write_toml(config / "core.toml", {
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "config/kits/sdlc",
                        "version": "2.0",
                    },
                },
            })

            (root / "AGENTS.md").write_text(
                '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "cypilot"\n```\n<!-- /@cf:root-agents -->\n',
                encoding="utf-8",
            )

            cache = Path(td) / "cache"
            _make_cache(cache, kit_version="2.0")
            kit_src = cache / "kits" / "sdlc"
            (kit_src / "manifest.toml").write_text(textwrap.dedent("""\
                [manifest]
                version = "1.0"
                root = "{cf-studio-path}/config/kits/{slug}"
                user_modifiable = false

                [[resources]]
                id = "constraints"
                source = "constraints.toml"
                default_path = "constraints.toml"
                type = "file"
                user_modifiable = false
            """), encoding="utf-8")

            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", cache),
                    patch(
                        "studio.commands.kit._download_kit_from_github",
                        return_value=(kit_src, "2.0"),
                    ),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["--dry-run"])
                self.assertEqual(rc, 0)

                # No resources should be populated (dry-run)
                core_toml = config / "core.toml"
                with open(core_toml, "rb") as f:
                    data = tomllib.load(f)
                sdlc_entry = data["kits"]["sdlc"]
                self.assertNotIn("resources", sdlc_entry)
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
