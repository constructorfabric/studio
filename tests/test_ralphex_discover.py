"""
Tests for ralphex discovery and validation module.

Covers:
- discover(): PATH lookup, persisted path fallback, missing binary
- validate(): available, unavailable, incompatible outcomes
- persist_path(): config persistence to core.toml
"""

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))

from studio.ralphex_discover import discover, validate, persist_path, INSTALL_GUIDANCE


class TestDiscover:
    """Tests for discover() — PATH lookup and persisted fallback."""

    def test_found_on_path(self):
        """discover() returns absolute path when ralphex is on PATH."""
        config = {"integrations": {"ralphex": {"executable_path": ""}}}
        with patch("studio.ralphex_discover.shutil.which", return_value="/usr/local/bin/ralphex"):
            result = discover(config)
        assert result == "/usr/local/bin/ralphex"

    def test_fallback_to_persisted_path(self):
        """discover() falls back to core.toml persisted path when PATH misses."""
        with TemporaryDirectory() as tmp:
            fake_bin = Path(tmp) / "ralphex"
            fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_bin.chmod(0o755)

            config = {"integrations": {"ralphex": {"executable_path": str(fake_bin)}}}
            with patch("studio.ralphex_discover.shutil.which", return_value=None):
                result = discover(config)
            assert result == str(fake_bin)

    def test_persisted_path_stale(self):
        """discover() returns None when persisted path points to missing file."""
        config = {"integrations": {"ralphex": {"executable_path": "/no/such/ralphex"}}}
        with patch("studio.ralphex_discover.shutil.which", return_value=None):
            result = discover(config)
        assert result is None

    def test_not_found_anywhere(self):
        """discover() returns None when ralphex is not on PATH and no persisted path."""
        config = {"integrations": {"ralphex": {"executable_path": ""}}}
        with patch("studio.ralphex_discover.shutil.which", return_value=None):
            result = discover(config)
        assert result is None

    def test_empty_config_no_integrations(self):
        """discover() handles config with no integrations section."""
        config = {}
        with patch("studio.ralphex_discover.shutil.which", return_value=None):
            result = discover(config)
        assert result is None

    def test_path_preferred_over_persisted(self):
        """discover() prefers PATH result over persisted config."""
        config = {"integrations": {"ralphex": {"executable_path": "/old/ralphex"}}}
        with patch("studio.ralphex_discover.shutil.which", return_value="/new/ralphex"):
            result = discover(config)
        assert result == "/new/ralphex"


class TestValidate:
    """Tests for validate() — version check outcomes."""

    def test_unavailable_when_path_is_none(self):
        """validate() returns unavailable with install guidance when path is None."""
        result = validate(None)
        assert result["status"] == "unavailable"
        assert result["version"] is None
        assert "install" in result["message"].lower() or "brew" in result["message"].lower()

    def test_available_when_version_succeeds(self):
        """validate() returns available with version when ralphex --version works."""
        proc = MagicMock(returncode=0, stdout="ralphex version 0.3.1\n", stderr="")
        with patch("studio.ralphex_discover.subprocess.run", return_value=proc):
            result = validate("/usr/local/bin/ralphex")
        assert result["status"] == "available"
        assert result["version"] == "0.3.1"

    def test_incompatible_when_version_fails(self):
        """validate() returns incompatible when ralphex --version exits non-zero."""
        proc = MagicMock(returncode=1, stdout="", stderr="unknown flag")
        with patch("studio.ralphex_discover.subprocess.run", return_value=proc):
            result = validate("/usr/local/bin/ralphex")
        assert result["status"] == "incompatible"
        assert "upgrade" in result["message"].lower() or "update" in result["message"].lower()

    def test_incompatible_when_subprocess_raises(self):
        """validate() returns incompatible when subprocess times out or errors."""
        with patch("studio.ralphex_discover.subprocess.run", side_effect=OSError("not found")):
            result = validate("/bad/ralphex")
        assert result["status"] == "incompatible"

    def test_version_parsing_various_formats(self):
        """validate() parses version from different output formats."""
        proc = MagicMock(returncode=0, stdout="v1.2.0", stderr="")
        with patch("studio.ralphex_discover.subprocess.run", return_value=proc):
            result = validate("/usr/local/bin/ralphex")
        assert result["version"] == "1.2.0"

    def test_available_with_build_metadata_version(self):
        """validate() parses version with build metadata suffix (e.g. ralphex v0.26.2-7a637fa-20260331T171815)."""
        proc = MagicMock(returncode=0, stdout="ralphex v0.26.2-7a637fa-20260331T171815\n", stderr="")
        with patch("studio.ralphex_discover.subprocess.run", return_value=proc):
            result = validate("/usr/local/bin/ralphex")
        assert result["status"] == "available"
        assert result["version"] == "0.26.2-7a637fa-20260331T171815"

    def test_install_guidance_content(self):
        """Installation guidance includes platform-appropriate options."""
        assert "brew" in INSTALL_GUIDANCE.lower()
        assert "go install" in INSTALL_GUIDANCE.lower()


class TestPersistPath:
    """Tests for persist_path() — config file updates."""

    def test_writes_executable_path(self):
        """persist_path() writes ralphex path to core.toml integrations section."""
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "core.toml"
            config_path.write_text(
                '# Cypilot project configuration\n\nversion = "1.0"\n\n'
                '[integrations.ralphex]\nexecutable_path = ""\n',
                encoding="utf-8",
            )
            persist_path(config_path, "/usr/local/bin/ralphex")

            import tomllib
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            assert data["integrations"]["ralphex"]["executable_path"] == "/usr/local/bin/ralphex"

    def test_preserves_other_config(self):
        """persist_path() preserves other config keys when updating."""
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "core.toml"
            config_path.write_text(
                'version = "1.0"\nproject_root = ".."\n\n'
                '[integrations.ralphex]\nexecutable_path = ""\n',
                encoding="utf-8",
            )
            persist_path(config_path, "/usr/local/bin/ralphex")

            import tomllib
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            assert data["version"] == "1.0"
            assert data["project_root"] == ".."
            assert data["integrations"]["ralphex"]["executable_path"] == "/usr/local/bin/ralphex"
