"""Tests for generic Git-backed kit install/update."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tomllib
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))

from _test_helpers import bootstrap_test_project as _bootstrap_project


def _run_git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout)
    return proc.stdout.strip()


def _write_git_kit(repo: Path, slug: str, skill_text: str) -> None:
    from studio.utils import toml_utils

    (repo / "artifacts" / "FEATURE").mkdir(parents=True, exist_ok=True)
    (repo / "artifacts" / "FEATURE" / "template.md").write_text("# Feature\n", encoding="utf-8")
    (repo / "SKILL.md").write_text(skill_text, encoding="utf-8")
    (repo / "constraints.toml").write_text("[ids]\n", encoding="utf-8")
    toml_utils.dump({"version": "local-conf", "slug": slug}, repo / "conf.toml")


def _make_git_kit_repo(root: Path, slug: str = "gitkit") -> tuple[Path, str]:
    repo = root / "repo"
    repo.mkdir()
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test User")
    _write_git_kit(repo, slug, "# Git Kit\n")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-q", "-m", "initial")
    first_sha = _run_git(repo, "rev-parse", "HEAD")
    _run_git(repo, "tag", "v1")
    return repo, first_sha


class TestGenericGitKitSourceParser(unittest.TestCase):
    def test_parse_canonicalizes_encoded_file_url(self):
        from studio.utils.git_kit_source import parse_git_kit_source

        encoded = quote("file:///tmp/example.git", safe="")
        parsed = parse_git_kit_source(f"git/{encoded}//kits/sdlc@sdlc")
        self.assertEqual(parsed.decoded_remote_url, "file:///tmp/example.git")
        self.assertEqual(parsed.selected_subdirectory, "kits/sdlc")
        self.assertEqual(parsed.kit_identity, "sdlc")
        self.assertEqual(parsed.canonical_source, f"git:{encoded}//kits/sdlc@sdlc")

    def test_rejects_credentials_with_stable_error_code(self):
        from studio.utils.git_kit_source import GitSourceError, parse_git_kit_source

        encoded = quote("https://user:secret@example.com/org/repo.git", safe="")
        with self.assertRaises(GitSourceError) as ctx:
            parse_git_kit_source(f"git/{encoded}")
        self.assertEqual(ctx.exception.code, "GIT_SOURCE_CREDENTIALS_IN_URL")
        diagnostics = ctx.exception.to_result()
        self.assertNotIn("secret", json.dumps(diagnostics))
        self.assertEqual(diagnostics["component"], "userinfo")

    def test_rejects_unsafe_subdir(self):
        from studio.utils.git_kit_source import GitSourceError, parse_git_kit_source

        encoded = quote("file:///tmp/example.git", safe="")
        with self.assertRaises(GitSourceError) as ctx:
            parse_git_kit_source(f"git/{encoded}//../escape")
        self.assertEqual(ctx.exception.code, "GIT_SOURCE_INVALID_SUBDIR")


class TestGenericGitKitInstallUpdate(unittest.TestCase):
    def setUp(self):
        from studio.utils.ui import set_json_mode

        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode

        set_json_mode(False)

    def test_install_from_file_git_source_records_git_provenance(self):
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            adapter = _bootstrap_project(project)
            repo, first_sha = _make_git_kit_repo(root)
            source = "git/" + quote(repo.as_uri(), safe="")
            cwd = os.getcwd()
            try:
                os.chdir(project)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install([source, "--version", "v1"])
                self.assertEqual(rc, 0, buf.getvalue())
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["kit"], "gitkit")
                with open(adapter / "config" / "core.toml", "rb") as f:
                    core = tomllib.load(f)
                kit = core["kits"]["gitkit"]
                self.assertTrue(kit["source"].startswith("git:"))
                self.assertEqual(kit["source_provenance"]["source_type"], "git")
                self.assertEqual(kit["source_provenance"]["requested_ref"], "v1")
                self.assertEqual(kit["content_identity"]["vcs"], "git")
                self.assertEqual(kit["content_identity"]["commit_sha"], first_sha)
            finally:
                os.chdir(cwd)

    def test_update_from_registered_git_source_uses_new_commit_sha(self):
        from studio.commands.kit import cmd_kit_install, cmd_kit_update

        with TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            adapter = _bootstrap_project(project)
            repo, first_sha = _make_git_kit_repo(root)
            source = "git/" + quote(repo.as_uri(), safe="")
            cwd = os.getcwd()
            try:
                os.chdir(project)
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cmd_kit_install([source, "--version", "master"]), 0)
                _write_git_kit(repo, "gitkit", "# Git Kit\n\nUpdated\n")
                _run_git(repo, "add", ".")
                _run_git(repo, "commit", "-q", "-m", "update")
                second_sha = _run_git(repo, "rev-parse", "HEAD")

                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["gitkit", "--no-interactive", "-y"])
                self.assertEqual(rc, 0, buf.getvalue())
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["results"][0]["action"], "updated")
                with open(adapter / "config" / "core.toml", "rb") as f:
                    core = tomllib.load(f)
                kit = core["kits"]["gitkit"]
                self.assertNotEqual(first_sha, second_sha)
                self.assertEqual(kit["content_identity"]["commit_sha"], second_sha)
                self.assertEqual(kit["source_provenance"]["source_type"], "git")
                self.assertEqual(kit["source_provenance"]["requested_ref"], "master")
            finally:
                os.chdir(cwd)
