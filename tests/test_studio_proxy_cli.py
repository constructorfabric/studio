from pathlib import Path
import sys
import tarfile
from io import BytesIO
import json
from urllib.error import HTTPError, URLError


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _skill_tarball() -> bytes:
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        root = "studio-release/"
        init_body = b'__version__ = "0.0.0-local"\n'
        init_info = tarfile.TarInfo(root + "skills/studio/scripts/studio/__init__.py")
        init_info.size = len(init_body)
        tf.addfile(init_info, BytesIO(init_body))
        cli_body = b"print('ok')\n"
        cli_info = tarfile.TarInfo(root + "skills/studio/scripts/studio.py")
        cli_info.size = len(cli_body)
        tf.addfile(cli_info, BytesIO(cli_body))
    return buf.getvalue()


def test_update_forwards_migration_flags_and_project_root(monkeypatch):
    from studio_proxy import cli
    import studio_proxy.cache as cache
    import studio_proxy.telemetry as telemetry

    captured = {}

    def fake_download_and_cache(*, version=None, force=False, url=None):
        captured["cache"] = {"version": version, "force": force, "url": url}
        return True, "cached"

    def fake_forward(skill_path, args):
        captured["forward"] = {"skill_path": skill_path, "args": list(args)}
        return 0

    monkeypatch.setattr(cache, "download_and_cache", fake_download_and_cache)
    monkeypatch.setattr(telemetry, "track_invocation", lambda _args: None)
    monkeypatch.setattr(cli, "find_cached_skill", lambda: Path("/tmp/studio.py"))
    monkeypatch.setattr(cli, "_forward_to_skill", fake_forward)

    rc = cli.main([
        "update",
        "--project-root",
        "/repo",
        "--migrate-from-cypilot=yes",
        "--from-dir",
        "cypilot",
        "--update-legacy-studio=yes",
        "--yes",
    ])

    assert rc == 0
    assert captured["cache"]["version"] is None
    assert captured["forward"]["args"] == [
        "update",
        "--project-root",
        "/repo",
        "--migrate-from-cypilot=yes",
        "--from-dir",
        "cypilot",
        "--update-legacy-studio=yes",
        "--yes",
    ]


def test_update_strips_only_positional_cache_version(monkeypatch):
    from studio_proxy import cli
    import studio_proxy.cache as cache
    import studio_proxy.telemetry as telemetry

    captured = {}

    def fake_download_and_cache(*, version=None, force=False, url=None):
        captured["cache"] = {"version": version, "force": force, "url": url}
        return True, "cached"

    def fake_forward(_skill_path, args):
        captured["forward_args"] = list(args)
        return 0

    monkeypatch.setattr(cache, "download_and_cache", fake_download_and_cache)
    monkeypatch.setattr(telemetry, "track_invocation", lambda _args: None)
    monkeypatch.setattr(cli, "find_cached_skill", lambda: Path("/tmp/studio.py"))
    monkeypatch.setattr(cli, "_forward_to_skill", fake_forward)

    rc = cli.main(["update", "v1.2.3", "--project-root", "/repo", "--yes"])

    assert rc == 0
    assert captured["cache"]["version"] == "v1.2.3"
    assert captured["forward_args"] == ["update", "--project-root", "/repo", "--yes"]


def test_download_and_cache_writes_github_provenance(monkeypatch, tmp_path):
    import studio_proxy.cache as cache

    monkeypatch.setenv("CFS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(
        cache,
        "_resolve_latest_version_with_metadata",
        lambda api_base=None: ("v9.8.7", "https://downloads.example/studio.tar.gz", {}),
    )

    class FakeResp:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def read(self):
            return _skill_tarball()

    monkeypatch.setattr(cache, "urlopen", lambda *_args, **_kwargs: FakeResp())

    success, message = cache.download_and_cache()

    assert success is True
    assert "v9.8.7" in message
    provenance = (tmp_path / "cache" / ".provenance.json").read_text(encoding="utf-8")
    assert '"source_type": "github"' in provenance
    assert '"installed_version": "v9.8.7"' in provenance
    assert '"requested_ref": "latest"' in provenance
    assert '"resolved_ref": "v9.8.7"' in provenance
    assert '"verified": "verified"' in provenance


def test_download_and_cache_generates_whatsnew_from_github_releases(monkeypatch, tmp_path):
    import studio_proxy.cache as cache

    monkeypatch.setenv("CFS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(
        cache,
        "_resolve_latest_version_with_metadata",
        lambda api_base=None: ("v9.8.7", "https://downloads.example/studio.tar.gz", {}),
    )

    class FakeResp:
        def __init__(self, data):
            self._data = data
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def read(self):
            return self._data

    def fake_urlopen(req, **_kwargs):
        url = req.full_url
        if url == "https://downloads.example/studio.tar.gz":
            return FakeResp(_skill_tarball())
        if url.endswith("/releases?per_page=100"):
            return FakeResp(json.dumps([
                {"tag_name": "v9.8.7", "name": "Release title", "body": "- GitHub-only note"},
            ]).encode())
        raise AssertionError(url)

    monkeypatch.setattr(cache, "urlopen", fake_urlopen)

    success, _message = cache.download_and_cache()

    assert success is True
    whatsnew = (tmp_path / "cache" / "whatsnew.toml").read_text(encoding="utf-8")
    assert '[whatsnew."v9.8.7"]' in whatsnew
    assert 'summary = "Release title"' in whatsnew
    assert "GitHub-only note" in whatsnew


def test_download_and_cache_warns_when_github_whatsnew_generation_fails(
    monkeypatch,
    tmp_path,
    capsys,
):
    import studio_proxy.cache as cache

    monkeypatch.setenv("CFS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(
        cache,
        "_resolve_latest_version_with_metadata",
        lambda api_base=None: ("v9.8.7", "https://downloads.example/studio.tar.gz", {}),
    )

    class FakeResp:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def read(self):
            return _skill_tarball()

    def fake_urlopen(req, **_kwargs):
        url = req.full_url
        if url == "https://downloads.example/studio.tar.gz":
            return FakeResp()
        raise AssertionError(url)

    monkeypatch.setattr(cache, "urlopen", fake_urlopen)

    success, _message = cache.download_and_cache()

    assert success is True
    assert not (tmp_path / "cache" / "whatsnew.toml").exists()
    assert "unable to generate Studio cache whatsnew.toml" in capsys.readouterr().err


def test_download_and_cache_no_releases_uses_default_branch_snapshot(monkeypatch, tmp_path):
    import studio_proxy.cache as cache

    monkeypatch.setenv("CFS_CACHE_DIR", str(tmp_path / "cache"))
    calls = []
    commits = iter(["abc123", "def456"])

    class FakeResp:
        def __init__(self, data):
            self._data = data
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def read(self):
            return self._data

    def fake_urlopen(req, **_kwargs):
        url = req.full_url
        calls.append(url)
        if url.endswith("/releases/latest"):
            raise HTTPError(url, 404, "Not Found", hdrs=None, fp=None)
        if url == "https://api.github.com/repos/o/r":
            return FakeResp(json.dumps({"default_branch": "trunk"}).encode())
        if url.endswith("/git/ref/heads/trunk"):
            commit = next(commits)
            return FakeResp(json.dumps({
                "object": {"type": "commit", "sha": commit},
            }).encode())
        if url.endswith("/tarball/abc123"):
            return FakeResp(_skill_tarball())
        if url.endswith("/tarball/def456"):
            return FakeResp(_skill_tarball())
        raise AssertionError(url)

    monkeypatch.setattr(cache, "urlopen", fake_urlopen)

    success, message = cache.download_and_cache(url="o/r")

    assert success is True
    assert "abc123" in message
    assert any(call.endswith("/tarball/abc123") for call in calls)
    assert not any(call.endswith("/tarball/main") for call in calls)
    metadata = json.loads((tmp_path / "cache" / ".provenance.json").read_text(encoding="utf-8"))
    assert metadata["installed_version"] == "abc123"
    assert metadata["resolved_ref"] == "abc123"
    assert metadata["resolver_mode"] == "default_branch_snapshot"
    assert metadata["resolution_basis"] == "github_default_branch"
    assert metadata["default_branch"] == "trunk"
    assert metadata["commit_sha"] == "abc123"
    assert metadata["verified"] == "unverified"

    success, message = cache.download_and_cache(url="o/r")

    assert success is True
    assert "already up to date" not in message
    assert "def456" in message
    assert any(call.endswith("/tarball/def456") for call in calls)
    metadata = json.loads((tmp_path / "cache" / ".provenance.json").read_text(encoding="utf-8"))
    assert metadata["installed_version"] == "def456"
    assert metadata["resolved_ref"] == "def456"
    assert metadata["default_branch"] == "trunk"
    assert metadata["commit_sha"] == "def456"


def test_download_and_cache_refreshes_default_branch_snapshot_metadata(monkeypatch, tmp_path):
    import studio_proxy.cache as cache

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setenv("CFS_CACHE_DIR", str(cache_dir))
    (cache_dir / ".version").write_text("abc123", encoding="utf-8")
    (cache_dir / ".provenance.json").write_text(json.dumps({
        "source_type": "github",
        "installed_version": "abc123",
        "requested_ref": "latest",
        "resolved_ref": "abc123",
        "resolver_mode": "default_branch_snapshot",
        "resolution_basis": "github_default_branch",
        "canonical_source": "https://api.github.com/repos/o/r",
        "effective_source": "https://api.github.com/repos/o/r",
        "default_branch": "main",
        "commit_sha": "abc123",
        "verified": "unverified",
        "freshness": "fresh",
    }), encoding="utf-8")
    monkeypatch.setattr(
        cache,
        "_resolve_latest_version_with_metadata",
        lambda api_base=None: (
            "abc123",
            "https://api.github.com/repos/o/r/tarball/abc123",
            {
                "resolver_mode": "default_branch_snapshot",
                "resolution_basis": "github_default_branch",
                "default_branch": "trunk",
                "commit_sha": "abc123",
                "verified": "unverified",
            },
        ),
    )
    monkeypatch.setattr(cache, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("downloaded")))

    success, message = cache.download_and_cache(url="o/r")

    assert success is True
    assert "already up to date" in message
    metadata = json.loads((cache_dir / ".provenance.json").read_text(encoding="utf-8"))
    assert metadata["default_branch"] == "trunk"
    assert metadata["commit_sha"] == "abc123"


def test_download_and_cache_explicit_release_uses_release_metadata(monkeypatch, tmp_path):
    import studio_proxy.cache as cache

    monkeypatch.setenv("CFS_CACHE_DIR", str(tmp_path / "cache"))
    calls = []

    class FakeResp:
        def __init__(self, data):
            self._data = data
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def read(self):
            return self._data

    def fake_urlopen(req, **_kwargs):
        url = req.full_url
        calls.append(url)
        if url.endswith("/releases/tags/v1.2.3"):
            return FakeResp(json.dumps({
                "tag_name": "v1.2.3",
                "target_commitish": "main",
                "tarball_url": "https://api.github.com/repos/o/r/tarball/v1.2.3",
                "assets": [],
            }).encode())
        if url.endswith("/git/ref/tags/v1.2.3"):
            return FakeResp(json.dumps({
                "object": {"type": "commit", "sha": "abc123"},
            }).encode())
        if url.endswith("/tarball/v1.2.3"):
            return FakeResp(_skill_tarball())
        raise AssertionError(url)

    monkeypatch.setattr(cache, "urlopen", fake_urlopen)

    success, _message = cache.download_and_cache(version="v1.2.3", url="o/r")

    assert success is True
    metadata = json.loads((tmp_path / "cache" / ".provenance.json").read_text(encoding="utf-8"))
    assert metadata["resolver_mode"] == "explicit_release"
    assert metadata["resolution_basis"] == "github_release"
    assert metadata["commit_sha"] == "abc123"
    assert metadata["resolved_ref"] == "v1.2.3"
    assert any(call.endswith("/releases/tags/v1.2.3") for call in calls)


def test_download_and_cache_explicit_tag_fallback_records_commit(monkeypatch, tmp_path):
    import studio_proxy.cache as cache

    monkeypatch.setenv("CFS_CACHE_DIR", str(tmp_path / "cache"))

    class FakeResp:
        def __init__(self, data):
            self._data = data
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def read(self):
            return self._data

    def fake_urlopen(req, **_kwargs):
        url = req.full_url
        if url.endswith("/releases/tags/v1.2.3"):
            raise HTTPError(url, 404, "Not Found", {}, None)
        if url.endswith("/git/ref/tags/v1.2.3"):
            return FakeResp(json.dumps({
                "object": {"type": "commit", "sha": "def456"},
            }).encode())
        if url.endswith("/tarball/v1.2.3"):
            return FakeResp(_skill_tarball())
        raise AssertionError(url)

    monkeypatch.setattr(cache, "urlopen", fake_urlopen)

    success, _message = cache.download_and_cache(version="v1.2.3", url="o/r")

    assert success is True
    metadata = json.loads((tmp_path / "cache" / ".provenance.json").read_text(encoding="utf-8"))
    assert metadata["resolver_mode"] == "semver_tag_fallback"
    assert metadata["resolution_basis"] == "github_tag"
    assert metadata["commit_sha"] == "def456"


def test_download_and_cache_annotated_tag_records_target_commit(monkeypatch, tmp_path):
    import studio_proxy.cache as cache

    monkeypatch.setenv("CFS_CACHE_DIR", str(tmp_path / "cache"))

    class FakeResp:
        def __init__(self, data):
            self._data = data
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def read(self):
            return self._data

    def fake_urlopen(req, **_kwargs):
        url = req.full_url
        if url.endswith("/releases/tags/v1.2.3"):
            raise HTTPError(url, 404, "Not Found", {}, None)
        if url.endswith("/git/ref/tags/v1.2.3"):
            return FakeResp(json.dumps({
                "object": {
                    "type": "tag",
                    "sha": "tag-object-sha",
                    "url": "https://api.github.com/repos/o/r/git/tags/tag-object-sha",
                },
            }).encode())
        if url.endswith("/git/tags/tag-object-sha"):
            return FakeResp(json.dumps({
                "object": {"type": "commit", "sha": "commit789"},
            }).encode())
        if url.endswith("/tarball/v1.2.3"):
            return FakeResp(_skill_tarball())
        raise AssertionError(url)

    monkeypatch.setattr(cache, "urlopen", fake_urlopen)

    success, _message = cache.download_and_cache(version="v1.2.3", url="o/r")

    assert success is True
    metadata = json.loads((tmp_path / "cache" / ".provenance.json").read_text(encoding="utf-8"))
    assert metadata["resolver_mode"] == "semver_tag_fallback"
    assert metadata["commit_sha"] == "commit789"


def test_download_and_cache_same_version_different_source_refreshes(monkeypatch, tmp_path):
    import studio_proxy.cache as cache

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setenv("CFS_CACHE_DIR", str(cache_dir))
    (cache_dir / ".version").write_text("v1.2.3", encoding="utf-8")
    (cache_dir / ".provenance.json").write_text(json.dumps({
        "source_type": "github",
        "installed_version": "v1.2.3",
        "requested_ref": "v1.2.3",
        "resolved_ref": "v1.2.3",
        "canonical_source": "old/repo",
        "effective_source": "https://api.github.com/repos/old/repo",
    }), encoding="utf-8")

    calls = []

    class FakeResp:
        def __init__(self, data):
            self._data = data
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def read(self):
            return self._data

    def fake_urlopen(req, **_kwargs):
        url = req.full_url
        calls.append(url)
        if url.endswith("/releases/tags/v1.2.3"):
            return FakeResp(json.dumps({
                "tag_name": "v1.2.3",
                "target_commitish": "new123",
                "tarball_url": "https://api.github.com/repos/new/repo/tarball/v1.2.3",
                "assets": [],
            }).encode())
        if url.endswith("/git/ref/tags/v1.2.3"):
            return FakeResp(json.dumps({
                "object": {"type": "commit", "sha": "new123"},
            }).encode())
        if url.endswith("/tarball/v1.2.3"):
            return FakeResp(_skill_tarball())
        raise AssertionError(url)

    monkeypatch.setattr(cache, "urlopen", fake_urlopen)

    success, message = cache.download_and_cache(version="v1.2.3", url="new/repo")

    assert success is True
    assert "already up to date" not in message
    assert any(call.endswith("/tarball/v1.2.3") for call in calls)
    metadata = json.loads((cache_dir / ".provenance.json").read_text(encoding="utf-8"))
    assert metadata["canonical_source"].endswith("/new/repo")
    assert metadata["effective_source"].endswith("/new/repo")


def test_download_and_cache_offline_latest_uses_last_known(monkeypatch, tmp_path):
    import studio_proxy.cache as cache

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setenv("CFS_CACHE_DIR", str(cache_dir))
    (cache_dir / ".version").write_text("v1.2.3", encoding="utf-8")
    (cache_dir / ".provenance.json").write_text(json.dumps({
        "source_type": "github",
        "installed_version": "v1.2.3",
        "requested_ref": "latest",
        "resolved_ref": "v1.2.3",
        "resolver_mode": "latest_release",
        "resolution_basis": "github_release",
        "canonical_source": "https://api.github.com/repos/o/r",
        "effective_source": "https://api.github.com/repos/o/r",
        "verified": "verified",
        "freshness": "fresh",
    }), encoding="utf-8")

    monkeypatch.setattr(cache, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")))

    success, message = cache.download_and_cache(url="o/r")

    assert success is True
    assert "last-known" in message
    metadata = json.loads((cache_dir / ".provenance.json").read_text(encoding="utf-8"))
    assert metadata["resolver_mode"] == "offline_last_known"
    assert metadata["freshness"] == "offline"
    assert metadata["verified"] == "unknown"
    assert metadata["resolved_ref"] == "v1.2.3"


def test_download_and_cache_offline_latest_rejects_wrong_cached_source(monkeypatch, tmp_path):
    import studio_proxy.cache as cache

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setenv("CFS_CACHE_DIR", str(cache_dir))
    (cache_dir / ".version").write_text("v1.2.3", encoding="utf-8")
    (cache_dir / ".provenance.json").write_text(json.dumps({
        "source_type": "github",
        "installed_version": "v1.2.3",
        "requested_ref": "latest",
        "resolved_ref": "v1.2.3",
        "canonical_source": "https://api.github.com/repos/old/repo",
        "effective_source": "https://api.github.com/repos/old/repo",
    }), encoding="utf-8")

    monkeypatch.setattr(cache, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")))

    success, message = cache.download_and_cache(url="new/repo")

    assert success is False
    assert "Failed to resolve latest version" in message
    metadata = json.loads((cache_dir / ".provenance.json").read_text(encoding="utf-8"))
    assert metadata["canonical_source"].endswith("/old/repo")


def test_download_and_cache_refreshes_offline_provenance_on_cache_hit(monkeypatch, tmp_path):
    import studio_proxy.cache as cache

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setenv("CFS_CACHE_DIR", str(cache_dir))
    (cache_dir / ".version").write_text("v1.2.3", encoding="utf-8")
    (cache_dir / ".provenance.json").write_text(json.dumps({
        "source_type": "github",
        "installed_version": "v1.2.3",
        "requested_ref": "latest",
        "resolved_ref": "v1.2.3",
        "resolver_mode": "offline_last_known",
        "resolution_basis": "last_known_cache_provenance",
        "canonical_source": "https://api.github.com/repos/o/r",
        "effective_source": "https://api.github.com/repos/o/r",
        "verified": "unknown",
        "freshness": "offline",
    }), encoding="utf-8")
    monkeypatch.setattr(
        cache,
        "_resolve_latest_version_with_metadata",
        lambda api_base=None: ("v1.2.3", "https://api.github.com/repos/o/r/tarball/v1.2.3", {}),
    )

    success, message = cache.download_and_cache(url="https://github.com/o/r")

    assert success is True
    assert "already up to date" in message
    metadata = json.loads((cache_dir / ".provenance.json").read_text(encoding="utf-8"))
    assert metadata["resolver_mode"] == "latest_release"
    assert metadata["freshness"] == "fresh"
    assert metadata["verified"] == "verified"


def test_download_and_cache_equivalent_repo_spelling_hits_cache(monkeypatch, tmp_path):
    import studio_proxy.cache as cache

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setenv("CFS_CACHE_DIR", str(cache_dir))
    (cache_dir / ".version").write_text("v1.2.3", encoding="utf-8")
    (cache_dir / ".provenance.json").write_text(json.dumps({
        "source_type": "github",
        "installed_version": "v1.2.3",
        "requested_ref": "latest",
        "resolved_ref": "v1.2.3",
        "resolver_mode": "latest_release",
        "resolution_basis": "github_release",
        "canonical_source": "https://api.github.com/repos/o/r",
        "effective_source": "https://api.github.com/repos/o/r",
        "verified": "verified",
        "freshness": "fresh",
    }), encoding="utf-8")
    monkeypatch.setattr(
        cache,
        "_resolve_latest_version_with_metadata",
        lambda api_base=None: ("v1.2.3", "https://api.github.com/repos/o/r/tarball/v1.2.3", {}),
    )
    monkeypatch.setattr(cache, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("downloaded")))

    success, message = cache.download_and_cache(url="https://github.com/o/r")

    assert success is True
    assert "already up to date" in message


def test_copy_from_local_writes_non_github_provenance(monkeypatch, tmp_path):
    import studio_proxy.cache as cache

    monkeypatch.setenv("CFS_CACHE_DIR", str(tmp_path / "cache"))
    source = tmp_path / "source"
    pkg = source / "skills" / "studio" / "scripts" / "studio"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('__version__ = "dev-local"\n', encoding="utf-8")
    (source / "skills" / "studio" / "scripts" / "studio.py").write_text("print('ok')\n", encoding="utf-8")
    (source / "whatsnew.toml").write_text(
        '[whatsnew."0.0.0"]\nsummary = "local file must not be cached"\ndetails = ""\n',
        encoding="utf-8",
    )
    (source / "kits" / "demo").mkdir(parents=True)
    (source / "kits" / "demo" / "whatsnew.toml").write_text(
        '[whatsnew."0.0.0"]\nsummary = "local kit file must not be cached"\ndetails = ""\n',
        encoding="utf-8",
    )

    success, message = cache.copy_from_local(str(source))

    assert success is True
    assert "local:dev-local" in message
    assert (tmp_path / "cache" / ".version").read_text(encoding="utf-8") == "local:dev-local"
    provenance = (tmp_path / "cache" / ".provenance.json").read_text(encoding="utf-8")
    assert '"source_type": "local_path"' in provenance
    assert '"resolver_mode": "local_path"' in provenance
    assert '"verified": "unknown"' in provenance
    assert not (tmp_path / "cache" / "whatsnew.toml").exists()
    assert not (tmp_path / "cache" / "kits" / "demo" / "whatsnew.toml").exists()


def test_version_output_uses_cache_provenance(monkeypatch, capsys):
    from studio_proxy import cli
    import studio_proxy.telemetry as telemetry

    monkeypatch.setattr(telemetry, "track_invocation", lambda _args: None)
    monkeypatch.setattr(cli, "get_cached_version", lambda: "v1.0.0")
    monkeypatch.setattr(cli, "get_cache_provenance", lambda: {
        "installed_version": "v1.0.0",
        "source_type": "github",
        "effective_source": "https://api.github.com/repos/o/r",
        "resolved_ref": "v1.0.0",
        "verified": "verified",
    })
    monkeypatch.setattr(cli, "find_project_skill", lambda: None)

    rc = cli.main(["--version"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "package:" in out
    assert "skill cache: v1.0.0" in out
    assert "source: github" in out
    assert "verified: verified" in out


def test_local_cache_version_does_not_warn_as_project_update(monkeypatch, capsys, tmp_path):
    from studio_proxy import cli

    project_skill = tmp_path / "studio.py"
    project_skill.write_text("", encoding="utf-8")
    monkeypatch.setattr(cli, "get_cached_version", lambda: "local:v1.0.0")
    monkeypatch.setattr(cli, "get_project_version", lambda _path: "v1.0.0")

    cli._background_version_check(project_skill)

    assert "update available" not in capsys.readouterr().err


def test_version_output_uses_project_provenance(monkeypatch, capsys, tmp_path):
    from studio_proxy import cli
    import studio_proxy.telemetry as telemetry

    project_skill = tmp_path / ".cf-studio" / ".core" / "skills" / "studio" / "scripts" / "studio.py"
    project_skill.parent.mkdir(parents=True)
    (project_skill.parent / "studio").mkdir()
    (project_skill.parent / "studio" / "__init__.py").write_text('__version__ = "v2.0.0"\n', encoding="utf-8")
    (tmp_path / ".cf-studio" / ".core" / ".provenance.json").write_text(
        '{"source_type": "github", "resolved_ref": "v2.0.0", "verified": "verified"}',
        encoding="utf-8",
    )

    monkeypatch.setattr(telemetry, "track_invocation", lambda _args: None)
    monkeypatch.setattr(cli, "get_cached_version", lambda: None)
    monkeypatch.setattr(cli, "find_project_skill", lambda: project_skill)

    rc = cli.main(["--version"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "skill project: v2.0.0" in out
    assert "source: github" in out
    assert "resolved ref: v2.0.0" in out
    assert "verified: verified" in out


def test_version_output_uses_flat_project_provenance(monkeypatch, capsys, tmp_path):
    from studio_proxy import cli
    import studio_proxy.telemetry as telemetry

    project_skill = tmp_path / ".cf-studio" / "skills" / "studio" / "scripts" / "studio.py"
    project_skill.parent.mkdir(parents=True)
    (project_skill.parent / "studio").mkdir()
    (project_skill.parent / "studio" / "__init__.py").write_text('__version__ = "v2.0.0"\n', encoding="utf-8")
    (tmp_path / ".cf-studio" / ".provenance.json").write_text(
        '{"source_type": "github", "resolved_ref": "v2.0.0", "verified": "verified"}',
        encoding="utf-8",
    )

    monkeypatch.setattr(telemetry, "track_invocation", lambda _args: None)
    monkeypatch.setattr(cli, "get_cached_version", lambda: None)
    monkeypatch.setattr(cli, "find_project_skill", lambda: project_skill)

    rc = cli.main(["--version"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "skill project: v2.0.0" in out
    assert "verified: verified" in out
