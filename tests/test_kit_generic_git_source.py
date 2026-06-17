"""Tests for generic Git-backed kit install/update."""

from __future__ import annotations

import io
import json
import os
import shutil
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


def _make_subdir_git_kit_repo(root: Path) -> tuple[Path, str]:
    repo = root / "repo"
    repo.mkdir()
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test User")
    kit_dir = repo / "kits" / "sdlc"
    kit_dir.mkdir(parents=True)
    _write_git_kit(kit_dir, "sdlc", "# SDLC Kit\n")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-q", "-m", "initial")
    return repo, _run_git(repo, "rev-parse", "HEAD")


def _make_multi_canonical_git_kit_repo(root: Path) -> tuple[Path, str]:
    repo = root / "repo"
    repo.mkdir()
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test User")
    (repo / "alpha.md").write_text("# Alpha v1\n", encoding="utf-8")
    (repo / "beta.md").write_text("# Beta v1\n", encoding="utf-8")
    (repo / ".cf-studio-kit.toml").write_text(
        "\n".join([
            'manifest_version = "1.0"',
            "",
            "[[kits]]",
            'slug = "alpha"',
            'name = "Alpha"',
            'version = "1.0.0"',
            "",
            "[[kits.resources]]",
            'id = "skill"',
            'kind = "skill"',
            'source = "alpha.md"',
            'install_path = "SKILL.md"',
            'type = "file"',
            "",
            "[[kits]]",
            'slug = "beta"',
            'name = "Beta"',
            'version = "1.0.0"',
            "",
            "[[kits.resources]]",
            'id = "skill"',
            'kind = "skill"',
            'source = "beta.md"',
            'install_path = "SKILL.md"',
            'type = "file"',
        ]) + "\n",
        encoding="utf-8",
    )
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-q", "-m", "initial")
    return repo, _run_git(repo, "rev-parse", "HEAD")


class TestGenericGitKitSourceParser(unittest.TestCase):
    def test_parse_canonicalizes_encoded_file_url(self):
        from studio.utils.git_kit_source import parse_git_kit_source

        encoded = quote("file:///tmp/example.git", safe="")
        parsed = parse_git_kit_source(f"git/{encoded}//kits/sdlc@sdlc")
        self.assertEqual(parsed.decoded_remote_url, "file:///tmp/example.git")
        self.assertEqual(parsed.selected_subdirectory, "kits/sdlc")
        self.assertEqual(parsed.kit_identity, "sdlc")
        self.assertEqual(parsed.canonical_source, f"git:{encoded}//kits/sdlc@sdlc")

    def test_parse_accepts_raw_copy_paste_clone_urls(self):
        from studio.utils.git_kit_source import parse_git_kit_source

        scp = parse_git_kit_source("git/git@github.com:constructorfabric/studio-kit-sdlc.git")
        self.assertEqual(scp.transport, "scp")
        self.assertEqual(scp.decoded_remote_url, "git@github.com:constructorfabric/studio-kit-sdlc.git")
        self.assertEqual(
            scp.canonical_source,
            "git:" + quote("git@github.com:constructorfabric/studio-kit-sdlc.git", safe=""),
        )

        https = parse_git_kit_source("git/https://github.com/constructorfabric/studio-kit-sdlc.git")
        self.assertEqual(https.transport, "https")
        self.assertEqual(
            https.canonical_source,
            "git:" + quote("https://github.com/constructorfabric/studio-kit-sdlc.git", safe=""),
        )

    def test_parse_accepts_raw_ssh_url_with_user_and_port(self):
        from studio.utils.git_kit_source import parse_git_kit_source

        raw_url = "ssh://git@git.acronis.com:7989/real/cyber-repo.git"
        parsed = parse_git_kit_source(f"git/{raw_url}")
        self.assertEqual(parsed.transport, "ssh")
        self.assertEqual(parsed.decoded_remote_url, raw_url)
        self.assertEqual(parsed.sanitized_url_display, raw_url)
        self.assertEqual(parsed.canonical_source, "git:" + quote(raw_url, safe=""))

    def test_parse_raw_clone_url_with_subdir_and_kit_identity(self):
        from studio.utils.git_kit_source import parse_git_kit_source

        parsed = parse_git_kit_source(
            "git/https://github.com/constructorfabric/studio-kit-sdlc.git//kits/sdlc@sdlc"
        )
        self.assertEqual(parsed.decoded_remote_url, "https://github.com/constructorfabric/studio-kit-sdlc.git")
        self.assertEqual(parsed.selected_subdirectory, "kits/sdlc")
        self.assertEqual(parsed.kit_identity, "sdlc")
        self.assertEqual(
            parsed.canonical_source,
            "git:" + quote("https://github.com/constructorfabric/studio-kit-sdlc.git", safe="") + "//kits/sdlc@sdlc",
        )

    def test_parse_accepts_raw_file_url(self):
        from studio.utils.git_kit_source import parse_git_kit_source

        parsed = parse_git_kit_source("git/file:///tmp/example.git")
        self.assertEqual(parsed.transport, "file")
        self.assertEqual(parsed.decoded_remote_url, "file:///tmp/example.git")
        self.assertEqual(parsed.canonical_source, "git:" + quote("file:///tmp/example.git", safe=""))

    def test_parse_accepts_ssh_shorthand_clone_url(self):
        from studio.utils.git_kit_source import parse_git_kit_source

        parsed = parse_git_kit_source("git/ssh:github.com:constructorfabric/studio-kit-sdlc.git")
        normalized = "git@github.com:constructorfabric/studio-kit-sdlc.git"
        self.assertEqual(parsed.transport, "scp")
        self.assertEqual(parsed.decoded_remote_url, normalized)
        self.assertEqual(parsed.sanitized_url_display, normalized)
        self.assertEqual(parsed.canonical_source, "git:" + quote(normalized, safe=""))

    def test_parse_accepts_ssh_shorthand_clone_url_with_port(self):
        from studio.utils.git_kit_source import parse_git_kit_source

        parsed = parse_git_kit_source("git/ssh:git.acronis.com:7989/real/cyber-repo.git")
        normalized = "ssh://git@git.acronis.com:7989/real/cyber-repo.git"
        self.assertEqual(parsed.transport, "ssh")
        self.assertEqual(parsed.decoded_remote_url, normalized)
        self.assertEqual(parsed.sanitized_url_display, normalized)
        self.assertEqual(parsed.canonical_source, "git:" + quote(normalized, safe=""))

    def test_parse_normalizes_standard_url_scheme_host_and_default_port(self):
        from studio.utils.git_kit_source import parse_git_kit_source

        parsed = parse_git_kit_source("git/" + quote("HTTPS://EXAMPLE.COM:443/Org/Repo.git", safe=""))
        self.assertEqual(
            parsed.canonical_source,
            "git:" + quote("https://example.com/Org/Repo.git", safe=""),
        )
        self.assertEqual(parsed.sanitized_url_display, "https://example.com/Org/Repo.git")

    def test_rejects_credentials_with_stable_error_code(self):
        from studio.utils.git_kit_source import GitSourceError, parse_git_kit_source

        encoded = quote("https://user:secret@example.com/org/repo.git", safe="")
        with self.assertRaises(GitSourceError) as ctx:
            parse_git_kit_source(f"git/{encoded}")
        self.assertEqual(ctx.exception.code, "GIT_SOURCE_CREDENTIALS_IN_URL")
        diagnostics = ctx.exception.to_result()
        self.assertNotIn("secret", json.dumps(diagnostics))
        self.assertEqual(diagnostics["component"], "userinfo")

    def test_rejects_ssh_url_password_with_stable_error_code(self):
        from studio.utils.git_kit_source import GitSourceError, parse_git_kit_source

        with self.assertRaises(GitSourceError) as ctx:
            parse_git_kit_source("git/ssh://git:secret@example.com/org/repo.git")
        self.assertEqual(ctx.exception.code, "GIT_SOURCE_CREDENTIALS_IN_URL")
        self.assertNotIn("secret", json.dumps(ctx.exception.to_result()))

    def test_rejects_query_and_fragment_with_stable_error_codes(self):
        from studio.utils.git_kit_source import GitSourceError, parse_git_kit_source

        cases = [
            ("https://example.com/org/repo.git?token=secret", "GIT_SOURCE_QUERY_UNSUPPORTED", "query"),
            ("https://example.com/org/repo.git#secret", "GIT_SOURCE_FRAGMENT_UNSUPPORTED", "fragment"),
        ]
        for raw_url, code, component in cases:
            with self.subTest(code=code):
                encoded = quote(raw_url, safe="")
                with self.assertRaises(GitSourceError) as ctx:
                    parse_git_kit_source(f"git/{encoded}")
                diagnostics = ctx.exception.to_result()
                self.assertEqual(ctx.exception.code, code)
                self.assertEqual(diagnostics["component"], component)
                self.assertNotIn("secret", json.dumps(diagnostics))

    def test_rejects_unsafe_subdir(self):
        from studio.utils.git_kit_source import GitSourceError, parse_git_kit_source

        encoded = quote("file:///tmp/example.git", safe="")
        with self.assertRaises(GitSourceError) as ctx:
            parse_git_kit_source(f"git/{encoded}//../escape")
        self.assertEqual(ctx.exception.code, "GIT_SOURCE_INVALID_SUBDIR")

    def test_parses_ssh_and_scp_like_transports(self):
        from studio.utils.git_kit_source import parse_git_kit_source

        ssh = parse_git_kit_source("git/" + quote("ssh://example.com/org/repo.git", safe=""))
        scp = parse_git_kit_source("git/" + quote("deploy@EXAMPLE.com:org/repo.git", safe=""))
        self.assertEqual(ssh.transport, "ssh")
        self.assertEqual(scp.transport, "scp")
        self.assertEqual(scp.sanitized_url_display, "deploy@example.com:org/repo.git")
        self.assertEqual(scp.canonical_source, "git:" + quote("deploy@example.com:org/repo.git", safe=""))

    def test_rejects_malformed_source_boundaries(self):
        from studio.utils.git_kit_source import GitSourceError, parse_git_kit_source

        cases = [
            ("git/", "GIT_SOURCE_INVALID_URL"),
            ("git/" + quote("https://example.com/%2Forg/repo.git", safe=""), "GIT_SOURCE_INVALID_URL"),
            ("git/https%3A%2F%2Fexample.com%2Forg%ZZrepo.git", "GIT_SOURCE_INVALID_URL"),
            ("git/" + quote("https://example.com/org/repo.git\x00", safe=""), "GIT_SOURCE_INVALID_URL"),
            ("git/" + quote("https://example.com/org/repo.git", safe="") + "@Bad", "GIT_SOURCE_INVALID_KIT"),
            ("git/" + quote("git@example.com:/abs.git", safe=""), "GIT_SOURCE_INVALID_URL"),
            ("git/ssh:github.com:/abs.git", "GIT_SOURCE_INVALID_URL"),
            ("git/" + quote("ftp://example.com/org/repo.git", safe=""), "GIT_SOURCE_INVALID_URL"),
            ("git/" + quote("https:///org/repo.git", safe=""), "GIT_SOURCE_INVALID_URL"),
            ("github:owner/repo", "GIT_SOURCE_INVALID_PREFIX"),
        ]
        for source, code in cases:
            with self.subTest(source=source):
                with self.assertRaises(GitSourceError) as ctx:
                    parse_git_kit_source(source)
                self.assertEqual(ctx.exception.code, code)

    def test_sanitized_display_preserves_non_default_port(self):
        from studio.utils.git_kit_source import parse_git_kit_source

        parsed = parse_git_kit_source("git/" + quote("https://example.com:8443/org/repo.git", safe=""))
        self.assertEqual(parsed.sanitized_url_display, "https://example.com:8443/org/repo.git")


class TestGenericGitKitInstallUpdate(unittest.TestCase):
    def setUp(self):
        from studio.utils.ui import set_json_mode

        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode

        set_json_mode(False)

    def test_materialize_default_branch_and_full_commit_selectors(self):
        from studio.utils.git_kit_source import materialize_git_kit_source, parse_git_kit_source

        with TemporaryDirectory() as td:
            root = Path(td)
            repo, first_sha = _make_git_kit_repo(root)
            parsed = parse_git_kit_source("git/" + quote(repo.as_uri(), safe=""))

            default_resolution = materialize_git_kit_source(parsed)
            try:
                default_authority = default_resolution.authority_metadata
                self.assertEqual(default_authority["resolution_basis"], "default_branch")
                self.assertEqual(default_authority["resolver_mode"], "default_branch")
                self.assertEqual(default_authority["requested_ref"], "HEAD")
                self.assertEqual(default_authority["commit_sha"], first_sha)
            finally:
                shutil.rmtree(default_resolution.tmp_dir, ignore_errors=True)

            pinned_resolution = materialize_git_kit_source(parsed, requested_ref=first_sha)
            try:
                pinned_authority = pinned_resolution.authority_metadata
                self.assertEqual(pinned_authority["resolution_basis"], "git_ref")
                self.assertEqual(pinned_authority["resolver_mode"], "pinned_commit")
                self.assertEqual(pinned_authority["requested_ref"], first_sha)
                self.assertEqual(pinned_authority["commit_sha"], first_sha)
            finally:
                shutil.rmtree(pinned_resolution.tmp_dir, ignore_errors=True)

    def test_materialize_subdirectory_with_kit_identity(self):
        from studio.utils.git_kit_source import materialize_git_kit_source, parse_git_kit_source

        with TemporaryDirectory() as td:
            root = Path(td)
            repo, first_sha = _make_subdir_git_kit_repo(root)
            parsed = parse_git_kit_source("git/" + quote(repo.as_uri(), safe="") + "//kits/sdlc@sdlc")
            resolution = materialize_git_kit_source(parsed, requested_ref=first_sha)
            try:
                authority = resolution.authority_metadata
                self.assertEqual(resolution.kit_source_dir.name, "sdlc")
                self.assertEqual(authority["selected_subdirectory"], "kits/sdlc")
                self.assertEqual(authority["kit_identity"], "sdlc")
                self.assertEqual(authority["commit_sha"], first_sha)
            finally:
                shutil.rmtree(resolution.tmp_dir, ignore_errors=True)

    def test_materialize_rejects_unsafe_requested_ref(self):
        from studio.utils.git_kit_source import GitSourceError, materialize_git_kit_source, parse_git_kit_source

        with TemporaryDirectory() as td:
            root = Path(td)
            repo, _first_sha = _make_git_kit_repo(root)
            parsed = parse_git_kit_source("git/" + quote(repo.as_uri(), safe=""))
            with self.assertRaises(GitSourceError) as ctx:
                materialize_git_kit_source(parsed, requested_ref="main^{commit}")
            self.assertEqual(ctx.exception.code, "GIT_SOURCE_INVALID_REF")

    def test_materialize_accepts_runtime_git_auth_options_without_persisting_them(self):
        from studio.utils.git_kit_source import materialize_git_kit_source, parse_git_kit_source

        with TemporaryDirectory() as td:
            root = Path(td)
            repo, first_sha = _make_git_kit_repo(root)
            parsed = parse_git_kit_source("git/" + quote(repo.as_uri(), safe=""))
            resolution = materialize_git_kit_source(
                parsed,
                requested_ref=first_sha,
                git_auth={
                    "env": {"GIT_TERMINAL_PROMPT": "0"},
                    "ssh_command": "ssh -o BatchMode=yes",
                    "askpass_command": "echo",
                },
            )
            try:
                authority_json = json.dumps(resolution.authority_metadata)
                self.assertEqual(resolution.authority_metadata["commit_sha"], first_sha)
                self.assertNotIn("BatchMode", authority_json)
                self.assertNotIn("GIT_TERMINAL_PROMPT", authority_json)
            finally:
                shutil.rmtree(resolution.tmp_dir, ignore_errors=True)

    def test_materialize_missing_subdirectory_fails_without_offline_match(self):
        from studio.utils.git_kit_source import materialize_git_kit_source, parse_git_kit_source

        with TemporaryDirectory() as td:
            root = Path(td)
            repo, first_sha = _make_git_kit_repo(root)
            parsed = parse_git_kit_source("git/" + quote(repo.as_uri(), safe="") + "//missing")
            with self.assertRaises(RuntimeError):
                materialize_git_kit_source(
                    parsed,
                    requested_ref=first_sha,
                    previous_metadata={
                        "source_provenance": {
                            "decoded_remote_url_hash": "different",
                            "selected_subdirectory": "missing",
                            "kit_identity": "",
                            "requested_ref": first_sha,
                        },
                        "source_provenance": {"commit_sha": first_sha},
                    },
                )

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
                self.assertEqual(kit["source_provenance"]["source_type"], "git")
                self.assertEqual(kit["source_provenance"]["commit_sha"], first_sha)
            finally:
                os.chdir(cwd)

    def test_install_from_file_git_source_uses_default_branch_without_version(self):
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
                    rc = cmd_kit_install([source])
                self.assertEqual(rc, 0, buf.getvalue())
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
                with open(adapter / "config" / "core.toml", "rb") as f:
                    core = tomllib.load(f)
                kit = core["kits"]["gitkit"]
                self.assertEqual(kit["source_provenance"]["requested_ref"], "HEAD")
                self.assertEqual(kit["source_provenance"]["resolution_basis"], "default_branch")
                self.assertEqual(kit["source_provenance"]["commit_sha"], first_sha)
            finally:
                os.chdir(cwd)

    def test_install_from_file_git_source_rejects_unsafe_version_selector(self):
        from studio.commands.kit import cmd_kit_install

        with TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            _bootstrap_project(project)
            repo, _first_sha = _make_git_kit_repo(root)
            source = "git/" + quote(repo.as_uri(), safe="")
            cwd = os.getcwd()
            try:
                os.chdir(project)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_install([source, "--version", "main^{commit}"])
                self.assertEqual(rc, 2, buf.getvalue())
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "FAIL")
                self.assertEqual(out["error_code"], "GIT_SOURCE_INVALID_REF")
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
                    self.assertEqual(cmd_kit_install([source, "--version", "HEAD"]), 0)
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
                self.assertEqual(kit["source_provenance"]["commit_sha"], second_sha)
                self.assertEqual(kit["source_provenance"]["source_type"], "git")
                self.assertEqual(kit["source_provenance"]["requested_ref"], "HEAD")
            finally:
                os.chdir(cwd)

    def test_update_force_multi_kit_git_source_keeps_selected_manifest_resources(self):
        from studio.commands.kit import cmd_kit_install, cmd_kit_update

        with TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            adapter = _bootstrap_project(project)
            repo, _first_sha = _make_multi_canonical_git_kit_repo(root)
            source = "git/" + quote(repo.as_uri(), safe="")
            cache_dir = root / "git-cache"
            cwd = os.getcwd()
            previous_cache_env = os.environ.get("CFS_GIT_KIT_CACHE_DIR")
            os.environ["CFS_GIT_KIT_CACHE_DIR"] = str(cache_dir)
            try:
                os.chdir(project)
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cmd_kit_install([source + "@beta"]), 0)

                installed_skill = adapter / "config" / "kits" / "beta" / "SKILL.md"
                self.assertEqual(installed_skill.read_text(encoding="utf-8"), "# Beta v1\n")

                (repo / "beta.md").write_text("# Beta v2\n", encoding="utf-8")
                _run_git(repo, "add", ".")
                _run_git(repo, "commit", "-q", "-m", "beta update")

                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update([
                        "beta",
                        "--force",
                        "--no-interactive",
                        "-y",
                        "--approve-overwrite",
                        "skill",
                    ])
                self.assertEqual(rc, 0, buf.getvalue())
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["results"][0]["action"], "updated")
                self.assertTrue(installed_skill.is_file())
                self.assertEqual(installed_skill.read_text(encoding="utf-8"), "# Beta v2\n")

                with open(adapter / "config" / "core.toml", "rb") as f:
                    core = tomllib.load(f)
                self.assertEqual(core["kits"]["beta"]["source"], "git:" + quote(repo.as_uri(), safe="") + "@beta")
            finally:
                os.chdir(cwd)
                if previous_cache_env is None:
                    os.environ.pop("CFS_GIT_KIT_CACHE_DIR", None)
                else:
                    os.environ["CFS_GIT_KIT_CACHE_DIR"] = previous_cache_env

    def test_update_uses_offline_last_known_cache_when_remote_unavailable(self):
        from studio.commands.kit import cmd_kit_install, cmd_kit_update

        with TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            adapter = _bootstrap_project(project)
            repo, first_sha = _make_git_kit_repo(root)
            source = "git/" + quote(repo.as_uri(), safe="")
            cache_dir = root / "git-cache"
            cwd = os.getcwd()
            previous_cache_env = os.environ.get("CFS_GIT_KIT_CACHE_DIR")
            os.environ["CFS_GIT_KIT_CACHE_DIR"] = str(cache_dir)
            try:
                os.chdir(project)
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cmd_kit_install([source, "--version", "HEAD"]), 0)
                self.assertTrue(any(cache_dir.rglob("artifact-manifest.json")))
                cache_paths = [str(path.relative_to(cache_dir)) for path in cache_dir.rglob("*")]
                self.assertTrue(cache_paths)
                for path in cache_paths:
                    self.assertNotIn("master", path)
                    self.assertNotIn("repo", path)
                    self.assertNotIn("token", path)
                    self.assertNotIn("secret", path)
                shutil.move(str(repo), str(root / "repo-offline"))

                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["gitkit", "--no-interactive", "-y"])
                self.assertEqual(rc, 0, buf.getvalue())
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["results"][0]["action"], "current")
                self.assertEqual(out["results"][0]["authority"]["freshness"], "last_known")
                self.assertEqual(out["results"][0]["authority"]["resolution_basis"], "offline_last_known")
                self.assertNotEqual(out["results"][0]["authority"]["resolver_mode"], "pinned_commit")
                with open(adapter / "config" / "core.toml", "rb") as f:
                    core = tomllib.load(f)
                self.assertTrue(core["kits"]["gitkit"]["source"].startswith("git:"))
                self.assertEqual(core["kits"]["gitkit"]["source_provenance"]["commit_sha"], first_sha)
                self.assertEqual(core["kits"]["gitkit"]["source_provenance"]["freshness"], "last_known")

                shutil.move(str(root / "repo-offline"), str(repo))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cmd_kit_update(["gitkit", "--no-interactive", "-y"])
                self.assertEqual(rc, 0, buf.getvalue())
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "PASS")
                self.assertEqual(out["results"][0]["action"], "current")
                self.assertEqual(out["results"][0]["authority"]["freshness"], "fresh")
                with open(adapter / "config" / "core.toml", "rb") as f:
                    core = tomllib.load(f)
                self.assertEqual(core["kits"]["gitkit"]["source_provenance"]["freshness"], "fresh")
                self.assertEqual(core["kits"]["gitkit"]["source_provenance"]["commit_sha"], first_sha)
            finally:
                os.chdir(cwd)
                if previous_cache_env is None:
                    os.environ.pop("CFS_GIT_KIT_CACHE_DIR", None)
                else:
                    os.environ["CFS_GIT_KIT_CACHE_DIR"] = previous_cache_env
