"""
DISABLED for Constructor Studio 4.0.0 — breaking changes in default paths,
template variable, skill names, and agent names mean v3.x → 4.0.0 upgrade
paths cannot be exercised. The 4.0.0 release is intentionally a fresh start
with no migration; this test will be re-enabled (or rewritten for 4.x → 4.y
upgrades) in a future release.

End-to-end tests for cypilot core upgrade from every historical version to HEAD.

For each v3.x git tag:
  1. Extract the cache snapshot (architecture/, requirements/, schemas/,
     workflows/, skills/, kits/, whatsnew.toml) as it existed at that tag.
  2. ``cpt init --yes`` a fresh project using that old cache.
  3. ``cpt update -y`` with the CURRENT (HEAD) cache.
  4. Assert:
     - exit code 0
     - status PASS or WARN (no hard errors)
     - .core/ files replaced
     - kit updated / migrated / installed
     - no top-level errors

All operations are non-interactive (``--yes`` auto-approves everything).
"""

import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))

# ---------------------------------------------------------------------------
# Repo constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories that constitute a valid cache (copied into .core/ by _copy_from_cache).
_CACHE_DIRS = ["architecture", "requirements", "schemas", "workflows", "skills"]
# Extra top-level files that may exist in cache.
_CACHE_FILES = ["whatsnew.toml"]

def _get_all_v3_tags() -> List[str]:
    """Return sorted list of all v3.* git tags in the repo."""
    try:
        out = subprocess.check_output(
            ["git", "tag", "--list", "v3.*", "--sort=version:refname"],
            cwd=str(REPO_ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return [t.strip() for t in out.strip().splitlines() if t.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


# Auto-populated from git tags — no manual maintenance needed.
_VERSION_TAGS: Dict[str, str] = {tag: tag for tag in _get_all_v3_tags()}

_HAS_TAGS = bool(_VERSION_TAGS)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git_show(ref: str, path: str) -> Optional[bytes]:
    """Return raw content of *path* at *ref*, or None if missing."""
    try:
        return subprocess.check_output(
            ["git", "show", f"{ref}:{path}"],
            cwd=str(REPO_ROOT),
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None


def _git_ls_tree(ref: str, directory: str) -> List[str]:
    """List file paths under *directory* at *ref*."""
    try:
        out = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", ref, directory],
            cwd=str(REPO_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return [line for line in out.strip().splitlines() if line]
    except subprocess.CalledProcessError:
        return []


def _extract_cache_at_tag(tag: str, dest: Path) -> None:
    """Extract a cache-like directory tree from *tag* into *dest*.

    Copies: architecture/, requirements/, schemas/, workflows/, skills/,
    kits/, and whatsnew.toml (if present).
    """
    # Core dirs + kits
    for directory in _CACHE_DIRS + ["kits"]:
        paths = _git_ls_tree(tag, f"{directory}/")
        for rel in paths:
            content = _git_show(tag, rel)
            if content is None:
                continue
            out_path = dest / rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(content)
    # Top-level files
    for fname in _CACHE_FILES:
        content = _git_show(tag, fname)
        if content is not None:
            (dest / fname).write_bytes(content)


def _build_head_cache(dest: Path) -> None:
    """Build a cache from the current working tree (HEAD)."""
    for directory in _CACHE_DIRS + ["kits"]:
        src = REPO_ROOT / directory
        if src.is_dir():
            shutil.copytree(src, dest / directory, dirs_exist_ok=True)
    for fname in _CACHE_FILES:
        src = REPO_ROOT / fname
        if src.is_file():
            shutil.copy2(src, dest / fname)
    # If kits/sdlc/ doesn't exist locally (kit moved to separate repo),
    # create a minimal synthetic kit so update tests have a cache source.
    kit_dir = dest / "kits" / "sdlc"
    if not kit_dir.is_dir():
        kit_dir.mkdir(parents=True, exist_ok=True)
        (kit_dir / "artifacts" / "PRD").mkdir(parents=True)
        (kit_dir / "artifacts" / "PRD" / "template.md").write_text(
            "# Product Requirements\n", encoding="utf-8",
        )
        import tomllib
        from studio.utils import toml_utils
        toml_utils.dump({"version": 99}, kit_dir / "conf.toml")


# ---------------------------------------------------------------------------
# Project helpers
# ---------------------------------------------------------------------------

def _init_project(root: Path, cache_dir: Path) -> Path:
    """Run ``cpt init --yes`` inside *root* using *cache_dir*.

    Mocks GitHub download to use cache kit source.
    Strips GitHub source from core.toml so cmd_update uses cache fallback.
    Returns the adapter directory (root / "cypilot").
    """
    import tempfile
    from studio.commands.init import cmd_init
    (root / ".git").mkdir(exist_ok=True)
    # Copy kit source to a temp dir — init deletes kit_src.parent after install
    kit_cache = cache_dir / "kits" / "sdlc"
    tmp_dl = Path(tempfile.mkdtemp())
    if kit_cache.is_dir():
        kit_copy = tmp_dl / "sdlc"
        shutil.copytree(kit_cache, kit_copy)
    else:
        kit_copy = tmp_dl / "sdlc"
        kit_copy.mkdir(parents=True)
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
            err = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(err):
                rc = cmd_init(["--yes"])
            assert rc == 0, (
                f"init failed (rc={rc})\nstdout: {buf.getvalue()}\nstderr: {err.getvalue()}"
            )
    finally:
        os.chdir(cwd)
    # Remove GitHub source from core.toml so cmd_update uses cache fallback
    adapter = root / "cypilot"
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


# ---------------------------------------------------------------------------
# E2E upgrade tests
# ---------------------------------------------------------------------------

@unittest.skip(
    "Disabled for Constructor Studio 4.0.0: breaking changes in default paths, "
    "template variable name, skill names, and agent names mean v3.x -> 4.0.0 "
    "upgrade paths cannot be exercised. 4.0.0 is intentionally a fresh start "
    "with no migration. Re-enable (or rewrite for 4.x -> 4.y upgrades) in a "
    "future release."
)
@unittest.skipUnless(_HAS_TAGS, "Full git history with tags required (use fetch-depth: 0)")
class TestCoreUpgradeE2E(unittest.TestCase):
    """Upgrade from every historical cypilot release to HEAD."""

    @classmethod
    def setUpClass(cls):
        """Pre-build the HEAD cache (shared across tests)."""
        cls._head_td = TemporaryDirectory()
        cls.head_cache = Path(cls._head_td.name) / "head_cache"
        _build_head_cache(cls.head_cache)

    @classmethod
    def tearDownClass(cls):
        cls._head_td.cleanup()

    # -- parametrised helper ------------------------------------------------

    def _run_upgrade(self, tag: str) -> Dict[str, Any]:
        """Init project at *tag*, update to HEAD.  Returns parsed JSON output."""
        from studio.commands.update import cmd_update

        with TemporaryDirectory() as td:
            td_p = Path(td)

            # 1. Extract old cache from tag
            old_cache = td_p / "old_cache"
            _extract_cache_at_tag(tag, old_cache)

            # 2. Init project with old cache
            root = td_p / "proj"
            root.mkdir()
            adapter = _init_project(root, old_cache)
            self.assertTrue(adapter.is_dir(), f"adapter dir not created for {tag}")

            # 3. Run cmd_update -y with HEAD cache
            # Mock GitHub download to use head_cache kit (avoids API rate limits)
            head_kit = self.head_cache / "kits" / "sdlc"
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                with (
                    patch("studio.commands.update.CACHE_DIR", self.head_cache),
                    patch(
                        "studio.commands.kit._download_kit_from_github",
                        return_value=(head_kit, "99"),
                    ),
                ):
                    buf = io.StringIO()
                    err = io.StringIO()
                    with redirect_stdout(buf), redirect_stderr(err):
                        rc = cmd_update(["-y"])
            finally:
                os.chdir(cwd)

            raw = buf.getvalue()
            self.assertEqual(
                rc, 0,
                f"{tag}→HEAD: rc={rc}\nstdout: {raw}\nstderr: {err.getvalue()}",
            )
            return json.loads(raw)

    def _assert_upgrade_ok(self, tag: str) -> None:
        """Run upgrade and validate all assertions."""
        out = self._run_upgrade(tag)

        # -- top-level status --
        self.assertIn(
            out["status"], ("PASS", "WARN"),
            f"{tag}: unexpected status {out['status']}: {json.dumps(out, indent=2)}",
        )

        # -- no top-level errors --
        errors = out.get("errors", [])
        self.assertEqual(errors, [], f"{tag}: top-level errors: {errors}")

        # -- core update happened --
        actions = out.get("actions", {})
        core_update = actions.get("core_update", {})
        self.assertIsInstance(core_update, dict, f"{tag}: core_update missing")
        for name, action in core_update.items():
            self.assertIn(
                action, ("created", "updated"),
                f"{tag}: core dir '{name}' action = '{action}', expected created/updated",
            )

        # -- kit results --
        kits = actions.get("kits", {})
        self.assertIn("sdlc", kits, f"{tag}: sdlc not in kit results")
        sdlc = kits["sdlc"]
        gen_errors = sdlc.get("gen_errors", [])
        self.assertEqual(gen_errors, [], f"{tag}: kit gen_errors: {gen_errors}")


# -- Dynamically generate one test per tag for clear reporting ----------------
def _make_upgrade_test(tag: str):
    """Factory to create a test method for a specific tag."""
    def test_method(self):
        self._assert_upgrade_ok(tag)
    return test_method


for _tag in _VERSION_TAGS:
    _test_name = f"test_upgrade_from_{_tag.replace('.', '_').replace('-', '_')}"
    setattr(TestCoreUpgradeE2E, _test_name, _make_upgrade_test(_tag))


if __name__ == "__main__":
    unittest.main()
