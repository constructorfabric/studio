"""
Skill Bundle Cache Management

Downloads skill bundle from GitHub releases into ~/.cf-studio/cache/.
Uses only Python stdlib (urllib.request) — no third-party dependencies.

@cpt-algo:cpt-studio-algo-core-infra-cache-skill:p1
@cpt-dod:cpt-studio-dod-core-infra-skill-cache:p1
"""

# @cpt-begin:cpt-studio-algo-core-infra-cache-skill:p1:inst-cache-helpers
import io
import json
import os
import shutil
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from studio_proxy.resolve import (
    get_cache_dir,
    get_cache_provenance,
    get_cache_provenance_file,
    get_version_file,
)

# GitHub repository for skill bundle releases
GITHUB_OWNER = "constructorfabric"
GITHUB_REPO = "studio"
GITHUB_API_BASE = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
USER_AGENT = "constructor-studio/1.0"


class _WhatsnewGenerationError(RuntimeError):
    """Internal sentinel for optional GitHub whatsnew generation failures."""


def _warn(message: str) -> None:
    sys.stderr.write(f"Warning: {message}\n")


def _patch_cached_version(cache_dir: Path, version: str) -> None:
    """Patch __version__ in cached skill's __init__.py with the resolved version."""
    # Primary path for the renamed skill dir (Bucket B layout)
    init_file = cache_dir / "skills" / "studio" / "scripts" / "studio" / "__init__.py"
    if not init_file.is_file():
        # Fallback: backwards-compat cache layout from pre-rebrand releases
        init_file = cache_dir / "skills" / "cypilot" / "scripts" / "cypilot" / "__init__.py"
    if not init_file.is_file():
        return
    try:
        content = init_file.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        patched = False
        for i, line in enumerate(lines):
            if line.startswith("__version__") and "=" in line:
                lines[i] = f'__version__ = "{version}"\n'
                patched = True
                break
        if patched:
            init_file.write_text("".join(lines), encoding="utf-8")
    except OSError as exc:
        _warn(f"unable to patch cached version in {init_file}: {exc}")


def _get_github_headers() -> dict:
    """Build GitHub API request headers, including auth token if available."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    # Support GITHUB_TOKEN or GH_TOKEN (gh CLI convention)
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_cache_provenance(metadata: Dict[str, Any]) -> None:
    """Persist structured cache provenance; legacy .version remains separate."""
    provenance_file = get_cache_provenance_file()
    provenance_file.parent.mkdir(parents=True, exist_ok=True)
    provenance_file.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_cache_version_toml(cache_dir: Path, version: str, metadata: Dict[str, Any]) -> None:
    """Persist project-installable cfs version metadata."""
    lines = [
        "# Constructor Studio pinned cfs version",
        "[cfs]",
        f"version = {_toml_string(version)}",
    ]
    requested_ref = metadata.get("requested_ref")
    if requested_ref:
        lines.append(f"requested_ref = {_toml_string(requested_ref)}")
    source_type = metadata.get("source_type")
    if source_type:
        lines.append(f"source_type = {_toml_string(source_type)}")
    canonical_source = metadata.get("canonical_source")
    if canonical_source:
        lines.append(f"canonical_source = {_toml_string(canonical_source)}")
    effective_source = metadata.get("effective_source")
    if effective_source:
        lines.append(f"effective_source = {_toml_string(effective_source)}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "version.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _github_json(url: str) -> Dict[str, Any]:
    req = Request(url, headers=_get_github_headers())
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data if isinstance(data, dict) else {}


def _github_json_list(url: str) -> List[Dict[str, Any]]:
    req = Request(url, headers=_get_github_headers())
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, json.JSONDecodeError, OSError, ValueError) as exc:
        raise _WhatsnewGenerationError(str(exc)) from exc
    except AssertionError as exc:
        raise _WhatsnewGenerationError(str(exc)) from exc
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _warn_whatsnew_generation_failed(scope: str, exc: BaseException) -> None:
    sys.stderr.write(
        f"Warning: unable to generate {scope} whatsnew.toml from GitHub release notes: {exc}\n"
    )


def _toml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _release_notes_section(release: Dict[str, Any]) -> str:
    tag = str(release.get("tag_name") or "").strip()
    if not tag:
        return ""
    summary = str(release.get("name") or "").strip() or tag
    details = str(release.get("body") or "").strip()
    return "\n".join((
        f'[whatsnew.{_toml_string(tag)}]',
        f"summary = {_toml_string(summary)}",
        f"details = {_toml_string(details)}",
    ))


def _release_notes_to_whatsnew_toml(releases: List[Dict[str, Any]]) -> str:
    sections = [section for section in (_release_notes_section(release) for release in releases) if section]
    return "\n\n".join(sections)


def _write_github_whatsnew(cache_dir: Path, api_base: str) -> None:
    """Generate cache whatsnew.toml only from GitHub release notes."""
    whatsnew_path = cache_dir / "whatsnew.toml"
    whatsnew_path.unlink(missing_ok=True)
    try:
        from studio_proxy.mirrors import apply_override

        releases = _github_json_list(apply_override(f"{api_base}/releases?per_page=100"))
        content = _release_notes_to_whatsnew_toml(releases)
    except _WhatsnewGenerationError as exc:
        _warn_whatsnew_generation_failed("Studio cache", exc)
        return
    if content.strip():
        whatsnew_path.write_text(content, encoding="utf-8")


def _remove_non_github_whatsnew(cache_dir: Path) -> None:
    """Remove whatsnew files copied from local/source trees."""
    paths = [cache_dir / "whatsnew.toml"]
    kits_dir = cache_dir / "kits"
    if kits_dir.is_dir():
        paths.extend(kits_dir.glob("*/whatsnew.toml"))
    for path in paths:
        path.unlink(missing_ok=True)


def _select_release_download_url(release_data: Dict[str, Any]) -> Optional[str]:
    from studio_proxy.mirrors import apply_override
    for asset in release_data.get("assets", []):
        name = asset.get("name", "")
        if (
            name.startswith("studio-skill") or name.startswith("cf-constructor-skill")
        ) and (
            name.endswith(".tar.gz") or name.endswith(".zip")
        ):
            asset_url = asset.get("browser_download_url")
            return apply_override(asset_url) if asset_url else None
    tarball_url = release_data.get("tarball_url")
    return apply_override(tarball_url) if tarball_url else None


def _canonical_api_base(url: Optional[str]) -> str:
    """Return the canonical GitHub API source before mirror overrides."""
    if url is None:
        return GITHUB_API_BASE
    raw = str(url).strip().rstrip("/")
    if raw.startswith("https://api.github.com/repos/"):
        return raw
    if raw.startswith("https://github.com/"):
        path = raw[len("https://github.com/"):]
        parts = path.strip("/").split("/")
        if len(parts) >= 2:
            return f"https://api.github.com/repos/{parts[0]}/{parts[1]}"
    if "/" in raw and not raw.startswith("http"):
        return f"https://api.github.com/repos/{raw}"
    return raw


def _resolve_tag_commit_sha(api_base: str, requested_ref: str) -> str:
    from studio_proxy.mirrors import apply_override
    tag_url = apply_override(f"{api_base}/git/ref/tags/{requested_ref}")
    tag_data = _github_json(tag_url)
    obj = tag_data.get("object", {})
    if not isinstance(obj, dict):
        return ""
    commit_sha = str(obj.get("sha") or "")
    if obj.get("type") == "tag":
        tag_object_url = obj.get("url") or apply_override(f"{api_base}/git/tags/{commit_sha}")
        tag_object = _github_json(str(tag_object_url))
        tag_target = tag_object.get("object", {})
        if isinstance(tag_target, dict):
            return str(tag_target.get("sha") or commit_sha)
    return commit_sha


def _resolve_explicit_github_version(api_base: str, requested_ref: str) -> Dict[str, Any]:
    """Resolve an explicit selector through GitHub Release, tag, then ref fallback."""
    from studio_proxy.mirrors import apply_override
    release_url = apply_override(f"{api_base}/releases/tags/{requested_ref}")
    try:
        release_data = _github_json(release_url)
        resolved_ref = str(release_data.get("tag_name") or requested_ref)
        try:
            commit_sha = _resolve_tag_commit_sha(api_base, resolved_ref)
        except HTTPError as exc:
            if exc.code != 404:
                raise
            commit_sha = str(release_data.get("target_commitish") or "")
        return {
            "source_type": "github",
            "installed_version": resolved_ref,
            "requested_ref": requested_ref,
            "resolved_ref": resolved_ref,
            "commit_sha": commit_sha,
            "resolver_mode": "explicit_release",
            "resolution_basis": "github_release",
            "download_url": _select_release_download_url(release_data),
            "verified": "verified",
            "freshness": "fresh",
        }
    except HTTPError as exc:
        if exc.code != 404:
            raise

    try:
        commit_sha = _resolve_tag_commit_sha(api_base, requested_ref)
        return {
            "source_type": "github",
            "installed_version": requested_ref,
            "requested_ref": requested_ref,
            "resolved_ref": requested_ref,
            "commit_sha": str(commit_sha or ""),
            "resolver_mode": "semver_tag_fallback",
            "resolution_basis": "github_tag",
            "download_url": apply_override(f"{api_base}/tarball/{requested_ref}"),
            "verified": "verified",
            "freshness": "fresh",
        }
    except HTTPError as exc:
        if exc.code != 404:
            raise

    return {
        "source_type": "github",
        "installed_version": requested_ref,
        "requested_ref": requested_ref,
        "resolved_ref": requested_ref,
        "resolver_mode": "github_ref",
        "resolution_basis": "github_ref",
        "download_url": apply_override(f"{api_base}/tarball/{requested_ref}"),
        "verified": "unverified",
        "freshness": "unknown",
    }


def _last_known_offline_metadata(
    api_base: str,
    canonical_source: str,
) -> Optional[Dict[str, Any]]:
    metadata = get_cache_provenance()
    if not metadata:
        return None
    if metadata.get("source_type") != "github":
        return None
    cached_effective = str(metadata.get("effective_source") or "")
    cached_canonical = str(metadata.get("canonical_source") or "")
    if cached_effective and cached_effective != api_base:
        return None
    if cached_canonical and cached_canonical != canonical_source:
        return None
    offline = dict(metadata)
    offline["resolver_mode"] = "offline_last_known"
    offline["resolution_basis"] = "last_known_cache_provenance"
    offline["verified"] = "unknown"
    offline["freshness"] = "offline"
    offline["effective_source"] = offline.get("effective_source") or api_base
    offline["offline_at"] = _utc_now_iso()
    return offline


def _cache_matches_authority(
    resolved_version: str,
    metadata: Dict[str, Any],
) -> bool:
    cached = get_cache_provenance()
    if not cached:
        return False
    return (
        cached.get("source_type") == metadata.get("source_type")
        and cached.get("resolved_ref") == resolved_version
        and cached.get("effective_source") == metadata.get("effective_source")
        and cached.get("canonical_source") == metadata.get("canonical_source")
    )


def _resolve_api_base(url: str) -> str:
    """
    Resolve GitHub API base URL from a custom repo URL or owner/repo shorthand.

    Resolution order: canonicalize → mirror-override → return.

    Accepts:
        - "owner/repo" → "https://api.github.com/repos/owner/repo"
        - "https://github.com/owner/repo" → "https://api.github.com/repos/owner/repo"
        - "https://api.github.com/repos/owner/repo" → as-is
    """
    from studio_proxy.mirrors import apply_override
    url = url.strip().rstrip("/")
    if url.startswith("https://api.github.com/repos/"):
        return apply_override(url)
    if url.startswith("https://github.com/"):
        # https://github.com/owner/repo → owner/repo
        path = url[len("https://github.com/"):]
        parts = path.strip("/").split("/")
        if len(parts) >= 2:
            canonical = f"https://api.github.com/repos/{parts[0]}/{parts[1]}"
            return apply_override(canonical)
    if "/" in url and not url.startswith("http"):
        # owner/repo shorthand
        canonical = f"https://api.github.com/repos/{url}"
        return apply_override(canonical)
    return apply_override(url)

def _resolve_default_branch_snapshot(api_base: str) -> Optional[Dict[str, str]]:
    """Resolve the repository default branch to a concrete commit snapshot."""
    from studio_proxy.mirrors import apply_override
    repo_data = _github_json(apply_override(api_base))
    default_branch = str(repo_data.get("default_branch") or "").strip()
    if not default_branch:
        return None
    ref_data = _github_json(apply_override(f"{api_base}/git/ref/heads/{default_branch}"))
    obj = ref_data.get("object", {})
    if not isinstance(obj, dict):
        return None
    commit_sha = str(obj.get("sha") or "").strip()
    if not commit_sha:
        return None
    return {
        "branch": default_branch,
        "commit_sha": commit_sha,
        "download_url": apply_override(f"{api_base}/tarball/{commit_sha}"),
    }


def _latest_release_request(api_base: str) -> Request:
    from studio_proxy.mirrors import apply_override

    url = apply_override(f"{api_base}/releases/latest")
    return Request(url, headers=_get_github_headers())


def _latest_release_snapshot_fallback(api_base: str) -> Tuple[Optional[str], Optional[str], Dict[str, str]]:
    try:
        snapshot = _resolve_default_branch_snapshot(api_base)
    except (HTTPError, URLError, json.JSONDecodeError, OSError) as exc:
        sys.stderr.write(f"No releases found and default branch resolution failed: {exc}\n")
        return None, None, {}
    if not snapshot:
        sys.stderr.write("No releases found and default branch could not be resolved.\n")
        return None, None, {}
    sys.stderr.write(
        "No releases found. Using default branch commit "
        f"{snapshot['branch']}@{snapshot['commit_sha']}.\n"
    )
    return snapshot["commit_sha"], snapshot["download_url"], {
        "resolver_mode": "default_branch_snapshot",
        "resolution_basis": "github_default_branch",
        "default_branch": snapshot["branch"],
        "commit_sha": snapshot["commit_sha"],
        "verified": "unverified",
    }


def _report_github_http_error(exc: HTTPError) -> Tuple[Optional[str], Optional[str], Dict[str, str]]:
    body = ""
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except OSError as read_exc:
        _warn(f"unable to read GitHub error body: {read_exc}")
    sys.stderr.write(f"GitHub API error: HTTP {exc.code} - {exc.reason}\n")
    if body:
        try:
            err_data = json.loads(body)
            if "message" in err_data:
                sys.stderr.write(f"  {err_data['message']}\n")
        except json.JSONDecodeError:
            sys.stderr.write(f"  {body[:200]}\n")
    return None, None, {}


def _report_github_error(exc: BaseException) -> Tuple[Optional[str], Optional[str], Dict[str, str]]:
    sys.stderr.write(f"GitHub API error: {exc}\n")
    return None, None, {}


def _resolve_latest_version_with_metadata(
    api_base: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Dict[str, str]]:
    """
    Query GitHub API for the latest release tag and asset download URL.

    Args:
        api_base: Custom GitHub API base URL (for forks). Defaults to GITHUB_API_BASE.

    Returns (version_tag, asset_url, metadata) or (None, None, {}) on failure.
    """
    base = api_base or GITHUB_API_BASE
    try:
        with urlopen(_latest_release_request(base), timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        if e.code == 404:
            return _latest_release_snapshot_fallback(base)
        return _report_github_http_error(e)
    except (URLError, json.JSONDecodeError, OSError) as e:
        return _report_github_error(e)

    tag = data.get("tag_name")
    if not tag:
        return None, None, {}
    return tag, _select_release_download_url(data), {}


def resolve_latest_version(
    api_base: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Query GitHub API for the latest release tag and asset download URL.

    Returns (version_tag, asset_url) or (None, None) on failure.
    """
    resolved_version, asset_url, _metadata = _resolve_latest_version_with_metadata(
        api_base=api_base,
    )
    return resolved_version, asset_url


def copy_from_local(
    source_dir: str,
    force: bool = False,
) -> Tuple[bool, str]:
    """
    Copy skill bundle from a local directory to cache.

    Args:
        source_dir: Path to local directory containing the skill bundle.
        force: If True, overwrite even if cache exists.

    Returns:
        (success, message) tuple.
    """
    source = Path(source_dir).resolve()
    if not source.is_dir():
        return False, f"Source directory not found: {source}"

    cache_dir = get_cache_dir()
    version_file = get_version_file()

    # Determine version from source (read __init__.py or fallback to "local")
    local_version = "local"
    for init_candidate in [
        # New (Bucket B) layout
        source / "skills" / "studio" / "scripts" / "studio" / "__init__.py",
        source / "studio" / "skills" / "studio" / "scripts" / "studio" / "__init__.py",
        # Legacy cypilot layout fallback for backwards-compat cache layouts
        source / "skills" / "cypilot" / "scripts" / "cypilot" / "__init__.py",
        source / "cypilot" / "skills" / "cypilot" / "scripts" / "cypilot" / "__init__.py",
    ]:
        if init_candidate.is_file():
            try:
                text = init_candidate.read_text(encoding="utf-8")
                for line in text.splitlines():
                    if "__version__" in line and "=" in line:
                        local_version = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            except OSError as exc:
                _warn(f"unable to read local version from {init_candidate}: {exc}")
            break

    if not force and version_file.is_file():
        cached_version = version_file.read_text(encoding="utf-8").strip()
        if cached_version == f"local:{local_version}":
            _write_cache_version_toml(cache_dir, cached_version, {
                "source_type": "local_path",
                "requested_ref": "local",
            })
            return True, f"Cache already up to date (local:{local_version})"

    # Remove old cache and copy
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Copy source contents to cache
    for item in source.iterdir():
        dst = cache_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dst)
        elif item.is_file():
            shutil.copy2(item, dst)
    _remove_non_github_whatsnew(cache_dir)

    display_version = f"local:{local_version}"
    version_file.write_text(display_version, encoding="utf-8")
    metadata = {
        "source_type": "local_path",
        "installed_version": display_version,
        "requested_ref": "local",
        "resolved_ref": local_version,
        "resolver_mode": "local_path",
        "resolution_basis": "local_path",
        "canonical_source": source.as_posix(),
        "effective_source": source.as_posix(),
        "verified": "unknown",
        "freshness": "local",
        "resolved_at": _utc_now_iso(),
    }
    _write_cache_version_toml(cache_dir, display_version, metadata)
    _write_cache_provenance(metadata)

    return True, (
        f"Cached: {display_version}\n"
        f"  from: {source}\n"
        f"  to:   {cache_dir}"
    )
# @cpt-end:cpt-studio-algo-core-infra-cache-skill:p1:inst-cache-helpers


def _resolve_cache_sources(url: Optional[str]) -> Tuple[str, str]:
    from studio_proxy.mirrors import apply_override

    canonical_source = _canonical_api_base(url)
    api_base = apply_override(GITHUB_API_BASE)
    if url is not None:
        api_base = _resolve_api_base(url)
    return canonical_source, api_base


def _offline_cache_hit(
    api_base: str,
    canonical_source: str,
    cache_dir: Path,
    version_file: Path,
) -> Tuple[bool, str]:
    offline = _last_known_offline_metadata(api_base, canonical_source)
    if offline and cache_dir.is_dir() and version_file.is_file():
        _write_cache_provenance(offline)
        offline_version = str(
            offline.get("installed_version")
            or offline.get("resolved_ref")
            or version_file.read_text(encoding="utf-8").strip()
        )
        _write_cache_version_toml(cache_dir, offline_version, offline)
        return True, (
            "Using last-known cache state "
            f"(version {offline.get('resolved_ref') or offline.get('installed_version')})\n"
            "  freshness: offline\n"
            "  reverify:  cfs update --force"
        )
    return False, "Failed to resolve latest version from GitHub API. Check network connectivity."


def _latest_download_metadata(
    api_base: str,
    canonical_source: str,
    cache_dir: Path,
    version_file: Path,
) -> Tuple[Optional[str], Optional[str], Dict[str, Any], Optional[Tuple[bool, str]]]:
    resolved_version, asset_url, latest_metadata = _resolve_latest_version_with_metadata(api_base=api_base)
    if resolved_version is None:
        return None, None, {}, _offline_cache_hit(api_base, canonical_source, cache_dir, version_file)
    metadata: Dict[str, Any] = {
        "source_type": "github",
        "installed_version": resolved_version,
        "requested_ref": "latest",
        "resolved_ref": resolved_version,
        "resolver_mode": latest_metadata.get("resolver_mode", "latest_release"),
        "resolution_basis": latest_metadata.get("resolution_basis", "github_release"),
        "download_url": asset_url,
        "verified": latest_metadata.get("verified", "verified"),
        "freshness": "fresh",
    }
    if latest_metadata.get("default_branch"):
        metadata["default_branch"] = latest_metadata["default_branch"]
    if latest_metadata.get("commit_sha"):
        metadata["commit_sha"] = latest_metadata["commit_sha"]
    return resolved_version, asset_url, metadata, None


def _explicit_download_metadata(
    version: str,
    api_base: str,
) -> Tuple[Optional[str], Optional[str], Dict[str, Any], Optional[Tuple[bool, str]]]:
    try:
        metadata = _resolve_explicit_github_version(api_base, version)
    except (HTTPError, URLError, json.JSONDecodeError, OSError) as exc:
        return None, None, {}, (False, f"Failed to resolve version {version} from GitHub API: {exc}")
    resolved_version = str(metadata.get("resolved_ref") or version)
    asset_url = metadata.get("download_url")
    return resolved_version, asset_url, metadata, None


def _resolve_download_metadata(
    version: Optional[str],
    api_base: str,
    canonical_source: str,
    cache_dir: Path,
    version_file: Path,
) -> Tuple[Optional[str], Optional[str], Dict[str, Any], Optional[Tuple[bool, str]]]:
    if version is None or version == "latest":
        return _latest_download_metadata(api_base, canonical_source, cache_dir, version_file)
    return _explicit_download_metadata(version, api_base)


def _cache_hit_metadata_changed(metadata: Dict[str, Any], asset_url: Optional[str]) -> bool:
    cached_provenance = get_cache_provenance() or {}
    provenance_keys = (
        "freshness",
        "verified",
        "resolver_mode",
        "resolution_basis",
        "default_branch",
        "commit_sha",
    )
    if not any(cached_provenance.get(key) != metadata.get(key) for key in provenance_keys):
        return False
    metadata.update({
        "download_url": asset_url,
        "resolved_at": _utc_now_iso(),
    })
    _write_cache_provenance(metadata)
    return True


def _reuse_cached_download(
    force: bool,
    version_file: Path,
    cache_dir: Path,
    resolved_version: str,
    metadata: Dict[str, Any],
    asset_url: Optional[str],
) -> Optional[Tuple[bool, str]]:
    if force or not version_file.is_file():
        return None
    cached_version = version_file.read_text(encoding="utf-8").strip()
    if cached_version != resolved_version:
        return None
    if not _cache_matches_authority(resolved_version, metadata):
        return None
    _cache_hit_metadata_changed(metadata, asset_url)
    _write_cache_version_toml(cache_dir, resolved_version, metadata)
    return True, f"Cache already up to date (version {resolved_version})"


def _download_archive(asset_url: str) -> Tuple[bool, bytes | str]:
    req = Request(asset_url, headers=_get_github_headers())
    try:
        with urlopen(req, timeout=120) as resp:
            return True, resp.read()
    except HTTPError as exc:
        return False, f"Download failed: HTTP {exc.code} - {exc.reason}. URL: {asset_url}"
    except URLError as exc:
        return False, f"Download failed: {exc.reason}. Check network connectivity."
    except OSError as exc:
        return False, f"Download failed: {exc}. Check network connectivity."


def _reset_cache_dir(cache_dir: Path) -> None:
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)


def _extract_tar_archive(archive_data: bytes, cache_dir: Path) -> bool:
    try:
        buf = io.BytesIO(archive_data)
        if not tarfile.is_tarfile(buf):
            return False
        buf.seek(0)
        with tarfile.open(fileobj=buf, mode="r:*") as tf:
            members = tf.getmembers()
            prefix = _find_common_prefix(members)
            _extract_stripped(tf, members, prefix, cache_dir)
        return True
    except (tarfile.TarError, OSError) as exc:
        _warn(f"unable to extract tar archive into {cache_dir}: {exc}")
        return False


def _extract_zip_archive(archive_data: bytes, cache_dir: Path) -> bool:
    try:
        buf = io.BytesIO(archive_data)
        with zipfile.ZipFile(buf) as zf:
            members = zf.namelist()
            prefix = _find_zip_prefix(members)
            _extract_zip_stripped(zf, members, prefix, cache_dir)
        return True
    except (zipfile.BadZipFile, OSError) as exc:
        _warn(f"unable to extract zip archive into {cache_dir}: {exc}")
        return False


def _extract_archive(archive_data: bytes, cache_dir: Path) -> bool:
    return _extract_tar_archive(archive_data, cache_dir) or _extract_zip_archive(archive_data, cache_dir)


def _finalize_cached_download(
    cache_dir: Path,
    version_file: Path,
    resolved_version: str,
    asset_url: str,
    api_base: str,
    metadata: Dict[str, Any],
) -> Tuple[bool, str]:
    _patch_cached_version(cache_dir, resolved_version)
    _remove_non_github_whatsnew(cache_dir)
    _write_github_whatsnew(cache_dir, api_base)
    version_file.write_text(resolved_version, encoding="utf-8")
    metadata.update({
        "download_url": asset_url,
        "resolved_at": _utc_now_iso(),
    })
    _write_cache_version_toml(cache_dir, resolved_version, metadata)
    _write_cache_provenance(metadata)
    return True, (
        f"Cached: {resolved_version}\n"
        f"  from: {asset_url}\n"
        f"  to:   {cache_dir}"
    )


def _prepare_download_payload(
    resolved_version: Optional[str],
    asset_url: Optional[str],
) -> Tuple[Optional[bytes], Optional[Tuple[bool, str]]]:
    """Validate resolved metadata and fetch the archive payload."""
    if resolved_version is None:
        return None, (False, "Failed to resolve version metadata.")
    if asset_url is None:
        return None, (False, f"No download URL found for version {resolved_version}")

    downloaded, archive_payload = _download_archive(asset_url)
    if not downloaded:
        return None, (False, str(archive_payload))
    if not isinstance(archive_payload, bytes):
        return None, (False, "Download produced invalid archive data.")
    return archive_payload, None

def download_and_cache(
    version: Optional[str] = None,
    force: bool = False,
    url: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Download skill bundle from GitHub and extract to cache directory.

    Args:
        version: Target version tag. If None, resolves to "latest".
        force: If True, re-download even if cache version matches.
        url: Custom GitHub repo URL (for forks). Format: "owner/repo" or full URL.

    Returns:
        (success, message) tuple.
    """
    cache_dir = get_cache_dir()
    version_file = get_version_file()
    canonical_source, api_base = _resolve_cache_sources(url)
    resolved_version, asset_url, metadata, early_result = _resolve_download_metadata(
        version,
        api_base,
        canonical_source,
        cache_dir,
        version_file,
    )
    if early_result is not None:
        return early_result

    metadata.update({
        "canonical_source": canonical_source,
        "effective_source": api_base,
    })
    cached_result = _reuse_cached_download(
        force,
        version_file,
        cache_dir,
        resolved_version,
        metadata,
        asset_url,
    )
    if cached_result is not None:
        return cached_result
    archive_data, archive_error = _prepare_download_payload(resolved_version, asset_url)
    if archive_error is not None:
        return archive_error

    _reset_cache_dir(cache_dir)
    if archive_data is None or not _extract_archive(archive_data, cache_dir):
        return False, "Failed to extract archive: unrecognized format"
    return _finalize_cached_download(
        cache_dir,
        version_file,
        resolved_version,
        asset_url,
        api_base,
        metadata,
    )

# @cpt-begin:cpt-studio-algo-core-infra-cache-skill:p1:inst-cache-helpers
def _find_common_prefix(members: list) -> str:
    """Find common top-level directory prefix in tar members."""
    names = [m.name for m in members if m.name and "/" in m.name]
    if not names:
        return ""
    first_parts = {n.split("/", 1)[0] for n in names}
    if len(first_parts) == 1:
        return first_parts.pop() + "/"
    return ""

def _extract_stripped(
    tf: tarfile.TarFile,
    members: list,
    prefix: str,
    dest: Path,
) -> None:
    """Extract tar members, stripping the common prefix."""
    for member in members:
        if not member.name.startswith(prefix):
            continue
        rel = member.name[len(prefix):]
        if not rel:
            continue
        # Security: skip absolute paths and parent references
        if rel.startswith("/") or ".." in rel.split("/"):
            continue
        member_copy = tarfile.TarInfo(name=rel)
        member_copy.size = member.size
        member_copy.mode = member.mode
        target = dest / rel
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
        elif member.isfile():
            target.parent.mkdir(parents=True, exist_ok=True)
            f = tf.extractfile(member)
            if f is not None:
                target.write_bytes(f.read())

def _find_zip_prefix(members: list) -> str:
    """Find common top-level directory prefix in zip members."""
    dirs = [m for m in members if "/" in m]
    if not dirs:
        return ""
    first_parts = {m.split("/", 1)[0] for m in dirs}
    if len(first_parts) == 1:
        return first_parts.pop() + "/"
    return ""

def _extract_zip_stripped(
    zf: zipfile.ZipFile,
    members: list,
    prefix: str,
    dest: Path,
) -> None:
    """Extract zip members, stripping the common prefix."""
    for name in members:
        if not name.startswith(prefix):
            continue
        rel = name[len(prefix):]
        if not rel:
            continue
        if rel.startswith("/") or ".." in rel.split("/"):
            continue
        target = dest / rel
        if name.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(name))
# @cpt-end:cpt-studio-algo-core-infra-cache-skill:p1:inst-cache-helpers
