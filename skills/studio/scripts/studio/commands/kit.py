"""
Kit Management Commands

Provides CLI handlers for kit install and kit update.
Kits are direct file packages — no blueprint processing or generation.
"""

from __future__ import annotations

# @cpt-algo:cpt-studio-algo-kit-github-helpers:p1
# @cpt-begin:cpt-studio-algo-kit-github-helpers:p1:inst-kit-imports
import argparse
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from ..utils._tomllib_compat import tomllib
from ..utils.git_kit_source import (
    GitSourceError,
    materialize_git_kit_source,
    parse_git_kit_source,
    source_is_generic_git,
)
from ..utils.ui import ui
from ..utils.whatsnew import show_kit_whatsnew
# @cpt-end:cpt-studio-algo-kit-github-helpers:p1:inst-kit-imports

if TYPE_CHECKING:
    from ..utils.manifest import Manifest, ManifestResource


# ---------------------------------------------------------------------------
# GitHub source helpers
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-kit-github-helpers:p1:inst-github-headers
def _github_headers() -> Dict[str, str]:
    """Build common headers for GitHub API requests.

    Includes Authorization if GITHUB_TOKEN is set in the environment.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "studio-kit-installer",
    }
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers
# @cpt-end:cpt-studio-algo-kit-github-helpers:p1:inst-github-headers


# @cpt-begin:cpt-studio-algo-kit-github-helpers:p1:inst-parse-source
def _parse_github_source(source: str) -> Tuple[str, str, str]:
    """Parse 'owner/repo[@version]' into (owner, repo, version).

    Returns (owner, repo, version) where version may be empty.
    Raises ValueError if format is invalid.
    """
    version = ""
    if "@" in source:
        source, version = source.rsplit("@", 1)

    parts = source.strip("/").split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"Invalid GitHub source: '{source}'. Expected format: owner/repo"
        )
    return parts[0], parts[1], version
# @cpt-end:cpt-studio-algo-kit-github-helpers:p1:inst-parse-source


def _parse_local_path_source(source: str) -> Optional[str]:
    """Parse a positional ``path/...`` or ``path:...`` local source alias."""
    if source.startswith("path/"):
        return source[len("path/"):]
    if source.startswith("path:"):
        return source[len("path:"):]
    return None


def _normalize_local_path_source_arg(
    *,
    source_value: Optional[str],
    local_path: Optional[str],
    arg_name: str,
) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, str]]]:
    """Translate positional ``path/...`` aliases into ``local_path``."""
    if not source_value:
        return source_value, local_path, None
    parsed_local_path = _parse_local_path_source(source_value)
    if parsed_local_path is None:
        return source_value, local_path, None
    if local_path:
        return source_value, local_path, {
            "status": "FAIL",
            "message": f"Cannot use both positional {arg_name} and --path",
            "hint": "Use either path/... or --path <dir>, but not both",
        }
    if not parsed_local_path:
        return source_value, local_path, {
            "status": "FAIL",
            "message": "Local path source cannot be empty",
            "hint": "Use path/<dir> or --path <dir>",
        }
    return None, parsed_local_path, None


_GITHUB_TARBALL_MAX_MEMBERS = 4096
_GITHUB_TARBALL_MAX_TOTAL_SIZE = 512 * 1024 * 1024
_GITHUB_TARBALL_MAX_EXPANSION_RATIO = 200


class _WhatsnewGenerationError(RuntimeError):
    """Internal sentinel for optional GitHub whatsnew generation failures."""


_SEMVER_TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


def _semver_key(tag: str) -> Optional[Tuple[int, int, int, int]]:
    match = _SEMVER_TAG_RE.match(tag)
    if not match:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    stable = 0 if "-" in tag else 1
    return major, minor, patch, stable


def _resolve_latest_semver_tag(owner: str, repo: str) -> str:
    """Resolve the highest semver-like GitHub tag, if any."""
    from ..utils.mirrors import apply_override
    url = apply_override(f"https://api.github.com/repos/{owner}/{repo}/tags?per_page=100")
    req = urllib.request.Request(url, headers=_github_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        raise RuntimeError(
            f"Failed to query GitHub tags for {owner}/{repo}: {exc}"
        ) from exc
    candidates: List[Tuple[Tuple[int, int, int, int], str]] = []
    for tag_data in data if isinstance(data, list) else []:
        if not isinstance(tag_data, dict):
            continue
        name = str(tag_data.get("name") or "")
        key = _semver_key(name)
        if key is not None:
            candidates.append((key, name))
    if not candidates:
        return ""
    return max(candidates)[1]


def _resolve_github_ref(
    owner: str,
    repo: str,
    requested_ref: str = "",
    previous_entry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve GitHub kit selector into structured authority metadata."""
    # @cpt-begin:cpt-studio-state-kit-authority:p1:inst-github-authority-state
    # @cpt-begin:cpt-studio-algo-kit-github-version-authority:p1:inst-core-version-github-authority
    # @cpt-begin:cpt-studio-algo-kit-github-version-authority:p1:inst-conf-version-local-only
    canonical_source = f"github:{owner}/{repo}"
    if requested_ref:
        # @cpt-begin:cpt-studio-algo-kit-github-version-authority:p1:inst-store-ref-identity
        return {
            "source_type": "github",
            "requested_ref": requested_ref,
            "resolved_ref": requested_ref,
            "installed_version": requested_ref,
            "canonical_source": canonical_source,
            "effective_source": canonical_source,
            "resolver_mode": "explicit",
            "resolution_basis": "github_ref",
            "verified": "verified",
            "freshness": "fresh",
        }
        # @cpt-end:cpt-studio-algo-kit-github-version-authority:p1:inst-store-ref-identity

    try:
        resolved_ref = _resolve_latest_github_release(owner, repo)
    except RuntimeError:
        # @cpt-begin:cpt-studio-algo-kit-github-helpers:p1:inst-offline-last-known
        # @cpt-begin:cpt-studio-algo-kit-github-version-authority:p1:inst-offline-authority
        if previous_entry:
            previous_provenance = previous_entry.get("source_provenance", {})
            resolved_ref = str(
                previous_provenance.get("resolved_ref")
                or previous_entry.get("version")
                or ""
            )
            if resolved_ref:
                return {
                    "source_type": "github",
                    "requested_ref": previous_provenance.get("requested_ref", "latest"),
                    "resolved_ref": resolved_ref,
                    "installed_version": resolved_ref,
                    "commit_sha": previous_provenance.get("commit_sha", ""),
                    "canonical_source": previous_provenance.get("canonical_source", canonical_source),
                    "effective_source": previous_provenance.get("effective_source", canonical_source),
                    "resolver_mode": "offline_last_known",
                    "resolution_basis": "last_known_core_toml",
                    "verified": "stale",
                    "freshness": "last_known",
                }
        # @cpt-end:cpt-studio-algo-kit-github-version-authority:p1:inst-offline-authority
        # @cpt-end:cpt-studio-algo-kit-github-helpers:p1:inst-offline-last-known
        raise

    # @cpt-begin:cpt-studio-algo-kit-github-version-authority:p1:inst-store-selector-and-identity
    return {
        "source_type": "github",
        "requested_ref": "latest",
        "resolved_ref": resolved_ref,
        "installed_version": resolved_ref,
        "canonical_source": canonical_source,
        "effective_source": canonical_source,
        "resolver_mode": "latest_release" if resolved_ref else "default_branch",
        "resolution_basis": "github_release" if resolved_ref else "github_default_branch",
        "verified": "verified",
        "freshness": "fresh",
    }
    # @cpt-end:cpt-studio-algo-kit-github-version-authority:p1:inst-store-selector-and-identity
    # @cpt-end:cpt-studio-algo-kit-github-version-authority:p1:inst-conf-version-local-only
    # @cpt-end:cpt-studio-algo-kit-github-version-authority:p1:inst-core-version-github-authority
    # @cpt-end:cpt-studio-state-kit-authority:p1:inst-github-authority-state


def _derive_commit_sha_from_tar_root(extracted_dir: Path, owner: str, repo: str) -> str:
    prefix = f"{owner}-{repo}-"
    name = extracted_dir.name
    if name.startswith(prefix):
        return name[len(prefix):]
    parts = name.rsplit("-", 1)
    return parts[-1] if len(parts) == 2 else ""


def _enrich_authority_with_commit_metadata(
    authority_metadata: Dict[str, Any],
    extracted_dir: Path,
    owner: str,
    repo: str,
) -> Dict[str, Any]:
    enriched = dict(authority_metadata)
    commit_sha = enriched.get("commit_sha") or _derive_commit_sha_from_tar_root(
        extracted_dir, owner, repo,
    )
    resolved_ref = str(enriched.get("resolved_ref") or enriched.get("installed_version") or "")
    if commit_sha:
        enriched["commit_sha"] = commit_sha
    identity = f"{owner}/{repo}@{resolved_ref}"
    if commit_sha:
        identity = f"{identity}#{commit_sha}"
    enriched["identity"] = identity
    return enriched


def _authority_result_summary(
    authority_metadata: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not authority_metadata:
        return None
    identity = str(authority_metadata.get("identity") or "")
    summary = {
        "source_type": str(authority_metadata.get("source_type") or ""),
        "resolver_mode": str(authority_metadata.get("resolver_mode") or ""),
        "resolution_basis": str(authority_metadata.get("resolution_basis") or ""),
        "requested_ref": str(authority_metadata.get("requested_ref") or ""),
        "resolved_ref": str(authority_metadata.get("resolved_ref") or ""),
        "commit_sha": str(authority_metadata.get("commit_sha") or ""),
        "canonical_source": str(authority_metadata.get("canonical_source") or ""),
        "effective_source": str(authority_metadata.get("effective_source") or ""),
        "identity": identity,
        "freshness": str(authority_metadata.get("freshness") or ""),
        "verified": str(authority_metadata.get("verified") or ""),
    }
    return {key: value for key, value in summary.items() if value not in ("", None, {})}


def _authority_commit_changed(
    authority_metadata: Optional[Dict[str, Any]],
    installed_kit_entry: Dict[str, Any],
) -> bool:
    if not authority_metadata:
        return False
    new_commit = str(
        authority_metadata.get("commit_sha")
        or ""
    )
    old_commit = str(
        (
            installed_kit_entry.get("source_provenance", {}).get("commit_sha")
            if isinstance(installed_kit_entry.get("source_provenance"), dict)
            else ""
        )
        or installed_kit_entry.get("commit_sha")
        or ""
    )
    return bool(new_commit and old_commit and new_commit != old_commit)


def _validate_tar_archive_before_extract(
    tar: tarfile.TarFile,
    tar_path: Path,
    tmp_dir: Path,
) -> None:
    tmp_dir_resolved = tmp_dir.resolve()
    total_size = 0
    member_count = 0

    while True:
        member = tar.next()
        if member is None:
            break
        member_count += 1
        if member_count > _GITHUB_TARBALL_MAX_MEMBERS:
            raise RuntimeError(
                "Archive extraction blocked: too many archive entries "
                f"(>{_GITHUB_TARBALL_MAX_MEMBERS})"
            )
        member_path = (tmp_dir / member.name).resolve()
        if not member_path.is_relative_to(tmp_dir_resolved):
            raise RuntimeError(
                f"Unsafe path in archive: {member.name!r}"
            )
        if member.isfile():
            total_size += member.size
            if total_size > _GITHUB_TARBALL_MAX_TOTAL_SIZE:
                raise RuntimeError(
                    "Archive extraction blocked: total extracted size exceeds "
                    f"limit ({total_size} > {_GITHUB_TARBALL_MAX_TOTAL_SIZE} bytes)"
                )

    archive_size = tar_path.stat().st_size
    if archive_size <= 0 < total_size:
        raise RuntimeError(
            "Archive extraction blocked: invalid compressed archive size "
            f"({archive_size} bytes)"
        )
    if archive_size > 0 and total_size > archive_size * _GITHUB_TARBALL_MAX_EXPANSION_RATIO:
        raise RuntimeError(
            "Archive extraction blocked: suspicious compression expansion ratio "
            f"({total_size}/{archive_size} > {_GITHUB_TARBALL_MAX_EXPANSION_RATIO}x)"
        )


# @cpt-begin:cpt-studio-algo-kit-github-helpers:p1:inst-download
def _download_kit_from_github(
    owner: str,
    repo: str,
    version: str = "",
) -> Tuple[Path, str]:
    """Download a kit from GitHub and extract to a temp directory.

    Uses GitHub API tarball endpoint (stdlib only, no dependencies).

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.
        version: Git ref (tag/branch/SHA). If empty, resolves latest release.

    Returns:
        (extracted_dir, resolved_version) — caller must clean up parent temp dir.

    Raises:
        RuntimeError: on network or extraction errors.
    """
    # Resolve version: if empty, query latest release
    if not version:
        version = _resolve_latest_github_release(owner, repo)

    # Download tarball (apply user-configured mirror overrides before fetch)
    from ..utils.mirrors import apply_override
    url = apply_override(f"https://api.github.com/repos/{owner}/{repo}/tarball/{version}")
    req = urllib.request.Request(url, headers=_github_headers())

    tmp_dir = Path(tempfile.mkdtemp(prefix="studio-kit-"))
    tar_path = tmp_dir / "kit.tar.gz"

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            with open(tar_path, "wb") as f:
                shutil.copyfileobj(resp, f)
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError(
            f"Failed to download kit from GitHub ({owner}/{repo}@{version}): {exc}"
        ) from exc

    # Extract — validate member paths to prevent zip-slip (S5042), then use
    # the built-in ``filter="data"`` safeguard for defence-in-depth.
    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            _validate_tar_archive_before_extract(tar, tar_path, tmp_dir)
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(path=tmp_dir, filter="data")  # noqa: S202
    except RuntimeError:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError(
            f"Failed to extract kit archive: {exc}"
        ) from exc

    tar_path.unlink(missing_ok=True)

    # Find the extracted directory (GitHub tarballs contain one top-level dir)
    subdirs = [d for d in tmp_dir.iterdir() if d.is_dir()]
    if len(subdirs) != 1:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError(
            f"Unexpected archive structure: expected 1 directory, found {len(subdirs)}"
        )

    _try_write_kit_whatsnew_from_github_releases(subdirs[0], owner, repo)
    return subdirs[0], version
# @cpt-end:cpt-studio-algo-kit-github-helpers:p1:inst-download


def _download_kit_from_github_with_authority(
    owner: str,
    repo: str,
    requested_ref: str = "",
    previous_entry: Optional[Dict[str, Any]] = None,
) -> Tuple[Path, str, Dict[str, Any]]:
    authority_metadata = _resolve_github_ref(
        owner,
        repo,
        requested_ref,
        previous_entry=previous_entry,
    )
    resolved_ref = str(authority_metadata.get("resolved_ref") or "")
    kit_source, resolved_version = _download_kit_from_github(owner, repo, resolved_ref)
    if resolved_version and not authority_metadata.get("resolved_ref"):
        authority_metadata["resolved_ref"] = resolved_version
        authority_metadata["installed_version"] = resolved_version
    authority_metadata = _enrich_authority_with_commit_metadata(
        authority_metadata,
        kit_source,
        owner,
        repo,
    )
    return kit_source, resolved_version, authority_metadata


# @cpt-begin:cpt-studio-algo-kit-github-helpers:p1:inst-resolve-release
def _resolve_latest_github_release(owner: str, repo: str) -> str:
    """Query GitHub API for the latest release tag.

    Falls back to default branch if no releases exist.
    """
    from ..utils.mirrors import apply_override
    url = apply_override(f"https://api.github.com/repos/{owner}/{repo}/releases/latest")
    req = urllib.request.Request(url, headers=_github_headers())

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            tag = data.get("tag_name", "")
            if tag:
                return tag
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            pass  # No releases — fall through to default branch
        else:
            raise RuntimeError(
                f"GitHub API error ({exc.code}): {exc.reason}"
            ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"Failed to query GitHub releases for {owner}/{repo}: {exc}"
        ) from exc

    # No releases found — use the highest semver-like tag if available.
    return _resolve_latest_semver_tag(owner, repo)
# @cpt-end:cpt-studio-algo-kit-github-helpers:p1:inst-resolve-release


def _toml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _github_release_notes_to_whatsnew_toml(releases: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for release in releases:
        tag = str(release.get("tag_name") or "").strip()
        if not tag:
            continue
        name = str(release.get("name") or "").strip()
        body = str(release.get("body") or "").strip()
        lines.extend([
            f'[whatsnew.{_toml_string(tag)}]',
            f"summary = {_toml_string(name or tag)}",
            f"details = {_toml_string(body)}",
            "",
        ])
    return "\n".join(lines)


def _warn_kit_whatsnew_generation_failed(owner: str, repo: str, exc: BaseException) -> None:
    ui.warn(
        f"{owner}/{repo}: unable to generate whatsnew.toml from GitHub release notes: {exc}"
    )


def _write_kit_whatsnew_from_github_releases(
    kit_source_dir: Path,
    owner: str,
    repo: str,
) -> None:
    """Generate kit whatsnew.toml only from GitHub release notes."""
    whatsnew_path = kit_source_dir / "whatsnew.toml"
    whatsnew_path.unlink(missing_ok=True)
    from ..utils.mirrors import apply_override

    url = apply_override(f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=100")
    req = urllib.request.Request(url, headers=_github_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        json.JSONDecodeError,
        OSError,
        ValueError,
    ) as exc:
        _warn_kit_whatsnew_generation_failed(owner, repo, exc)
        return
    except AssertionError as exc:
        raise _WhatsnewGenerationError(str(exc)) from exc
    if not isinstance(data, list):
        return
    releases = [item for item in data if isinstance(item, dict)]
    content = _github_release_notes_to_whatsnew_toml(releases)
    if content.strip():
        whatsnew_path.write_text(content, encoding="utf-8")


def _try_write_kit_whatsnew_from_github_releases(
    kit_source_dir: Path,
    owner: str,
    repo: str,
) -> None:
    try:
        _write_kit_whatsnew_from_github_releases(kit_source_dir, owner, repo)
    except _WhatsnewGenerationError as exc:
        _warn_kit_whatsnew_generation_failed(owner, repo, exc)

# ---------------------------------------------------------------------------
# Config seeding — copy default .toml configs from kit scripts to config/
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-kit-content-mgmt:p1:inst-content-constants
# Directories and files that constitute kit content (copied to config/kits/{slug}/)
_KIT_CONTENT_DIRS = ("artifacts", "codebase", "scripts", "workflows")
_KIT_SKILL_FILE = "SKILL.md"
_KIT_AGENTS_FILE = "AGENTS.md"
_KIT_CONTENT_FILES = ("constraints.toml", _KIT_SKILL_FILE, _KIT_AGENTS_FILE)
# Infrastructure file — copied but not subject to interactive diff
_KIT_CONF_FILE = "conf.toml"
_KIT_CORE_TOML = "core.toml"

_CONFIG_EXTENSIONS = {".toml"}
# @cpt-end:cpt-studio-algo-kit-content-mgmt:p1:inst-content-constants

# @cpt-begin:cpt-studio-algo-kit-content-mgmt:p1:inst-seed-configs
def _seed_kit_config_files(
    gen_scripts_dir: Path,
    config_dir: Path,
    actions: Dict[str, str],
) -> None:
    """Copy top-level .toml files from generated scripts into config/ if missing.

    Only seeds files that don't already exist in config/ — never overwrites
    user-editable config.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    for src in gen_scripts_dir.iterdir():
        if src.is_file() and src.suffix in _CONFIG_EXTENSIONS:
            dst = config_dir / src.name
            if not dst.exists():
                shutil.copy2(src, dst)
                actions[f"config_{src.stem}"] = "seeded"
# @cpt-end:cpt-studio-algo-kit-content-mgmt:p1:inst-seed-configs

# ---------------------------------------------------------------------------
# Shared CLI helper — resolve project root + studio directory
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-kit-config-helpers:p1:inst-resolve-studio-dir
def _resolve_studio_dir(project_root_arg: Optional[Path] = None) -> Optional[tuple]:
    """Resolve project root and studio directory from CWD.

    Returns (project_root, studio_dir) or None (after printing JSON error).
    """
    from ..utils.files import find_project_root, _read_studio_var

    project_root = project_root_arg.resolve() if project_root_arg is not None else find_project_root(Path.cwd())
    if project_root is None:
        ui.result({"status": "ERROR", "message": "No project root found"})
        return None

    studio_rel = _read_studio_var(project_root)
    if not studio_rel:
        ui.result({"status": "ERROR", "message": "No studio directory"})
        return None

    studio_dir = (project_root / studio_rel).resolve()
    return project_root, studio_dir
# @cpt-end:cpt-studio-algo-kit-config-helpers:p1:inst-resolve-studio-dir

# ---------------------------------------------------------------------------
# Kit content helpers — copy specific dirs/files, collect metadata for .gen/
# ---------------------------------------------------------------------------

# @cpt-algo:cpt-studio-algo-kit-content-mgmt:p1
# @cpt-begin:cpt-studio-algo-kit-content-mgmt:p1:inst-copy-content
def _copy_kit_content(
    kit_source: Path,
    config_kit_dir: Path,
) -> Dict[str, str]:
    """Copy kit content items from *kit_source* → *config_kit_dir*.

    Copies only the directories listed in ``_KIT_CONTENT_DIRS``, the files
    listed in ``_KIT_CONTENT_FILES``, and the infra ``_KIT_CONF_FILE``.
    Returns a dict of ``{item: action}`` entries.
    """
    actions: Dict[str, str] = {}
    config_kit_dir.mkdir(parents=True, exist_ok=True)

    for d in _KIT_CONTENT_DIRS:
        src = kit_source / d
        dst = config_kit_dir / d
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            actions[d] = "copied"

    for f in _KIT_CONTENT_FILES:
        src = kit_source / f
        dst = config_kit_dir / f
        if src.is_file():
            shutil.copy2(src, dst)
            actions[f] = "copied"

    return actions
    # @cpt-end:cpt-studio-algo-kit-content-mgmt:p1:inst-copy-content


# @cpt-begin:cpt-studio-algo-kit-content-mgmt:p1:inst-collect-metadata-fn
def _normalize_path_string(path_value: str) -> str:
    normalized = PurePosixPath(path_value.strip().replace("\\", "/")).as_posix()
    return "" if normalized == "." else normalized


def _is_windows_absolute_path(registered_kit_path: str) -> bool:
    if not registered_kit_path:
        return False
    normalized = _normalize_path_string(registered_kit_path)
    return PureWindowsPath(normalized).is_absolute()


def _is_posix_absolute_path(registered_kit_path: str) -> bool:
    if not registered_kit_path:
        return False
    normalized = _normalize_path_string(registered_kit_path)
    return PurePosixPath(normalized).is_absolute()


def _is_registered_kit_path_absolute(registered_kit_path: str) -> bool:
    if not registered_kit_path:
        return False
    return (
        _is_posix_absolute_path(registered_kit_path)
        or _is_windows_absolute_path(registered_kit_path)
    )


# @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-persist-relative-only
def _resolve_registered_kit_dir(
    studio_dir: Path,
    registered_kit_path: str,
) -> Optional[Path]:
    normalized = _normalize_path_string(registered_kit_path)
    if not normalized:
        return studio_dir.resolve()
    if _is_registered_kit_path_absolute(normalized):
        return None
    return (studio_dir / Path(normalized)).resolve()


def _resolve_same_os_absolute_path(registered_kit_path: str) -> Optional[Path]:
    normalized = _normalize_path_string(registered_kit_path)
    if not normalized:
        return None
    if _is_windows_absolute_path(normalized):
        return Path(normalized).resolve() if os.name == "nt" else None
    if _is_posix_absolute_path(normalized):
        return Path(normalized).resolve() if os.name != "nt" else None
    return None


def _resolve_registered_kit_root_dir(
    studio_dir: Path,
    registered_kit_path: str,
) -> Optional[Path]:
    resolved_absolute = _resolve_same_os_absolute_path(registered_kit_path)
    if resolved_absolute is not None:
        return resolved_absolute
    return _resolve_registered_kit_dir(studio_dir, registered_kit_path)


def _normalize_registered_kit_path(
    registered_kit_path: Any,
    kit_slug: str,
) -> str:
    if isinstance(registered_kit_path, str) and registered_kit_path.strip():
        return _normalize_path_string(registered_kit_path)
    return f"config/kits/{kit_slug}"


def _serialize_manifest_binding_path(target_path: Any, studio_dir: Path) -> str:
    raw_target = os.fspath(target_path)
    if os.name != "nt" and _is_windows_absolute_path(raw_target):
        return _normalize_path_string(raw_target)
    target_str = os.fspath(Path(raw_target).resolve())
    studio_str = os.fspath(studio_dir.resolve())
    try:
        return _normalize_path_string(
            os.path.relpath(target_str, studio_str)
        )
    except ValueError:
        return _normalize_path_string(target_str)
# @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-persist-relative-only


def _project_root_for_core_paths(_config_dir: Path, studio_dir: Path, data: Dict[str, Any]) -> Path:
    studio_dir = Path(studio_dir)
    raw_root = data.get("project_root")
    if isinstance(raw_root, str) and raw_root.strip():
        root_path = Path(raw_root.strip())
        if root_path.is_absolute():
            return root_path.resolve()
        return (studio_dir / root_path).resolve()
    return studio_dir.parent.resolve()


def _validate_persisted_core_path(
    label: str,
    persisted_path: str,
    studio_dir: Path,
    project_root: Path,
    *,
    allow_same_os_absolute: bool = False,
    allowed_absolute_root: str = "",
) -> Optional[str]:
    # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-persist-relative-only
    normalized = _normalize_path_string(persisted_path)
    if not normalized:
        return f"{label} cannot be empty"
    is_absolute = _is_registered_kit_path_absolute(normalized)
    if is_absolute:
        resolved_absolute = _resolve_same_os_absolute_path(normalized)
        if resolved_absolute is None:
            return (
                f"{label} '{normalized}' is not accessible on this OS; "
                "use project-relative paths for persisted core.toml state"
            )
        if allow_same_os_absolute:
            return None
        normalized_allowed_root = _normalize_path_string(allowed_absolute_root)
        resolved_allowed_root = (
            _resolve_same_os_absolute_path(normalized_allowed_root)
            if normalized_allowed_root else None
        )
        if resolved_allowed_root is not None and _path_is_within(resolved_absolute, resolved_allowed_root):
            return None
        return (
            f"{label} '{normalized}' is invalid state: "
            "absolute paths must not be persisted in core.toml; use project-relative paths"
        )
    resolved_path = _resolve_registered_kit_dir(studio_dir, normalized)
    if resolved_path is None:
        return (
            f"{label} '{normalized}' is not accessible on this OS; "
            "use project-relative paths for persisted core.toml state"
        )
    if not _path_is_within(resolved_path, project_root):
        return (
            f"{label} '{normalized}' escapes the current project root '{project_root}'; "
            "core.toml may persist only in-project relative paths"
        )
    return None
    # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-persist-relative-only


def _extract_registered_binding_path(binding: Any) -> Optional[str]:
    binding_path = binding.get("path") if isinstance(binding, dict) else binding
    if not isinstance(binding_path, str) or not binding_path.strip():
        return None
    return _normalize_path_string(binding_path)


def _resolve_registered_metadata_target_for_name(
    studio_dir: Path,
    binding_paths: List[str],
    target_name: str,
) -> Optional[Tuple[Path, str]]:
    for binding_rel in binding_paths:
        if PurePosixPath(binding_rel).name != target_name:
            continue
        binding_abs = _resolve_registered_kit_dir(studio_dir, binding_rel)
        if binding_abs is None or not binding_abs.is_file():
            continue
        binding_root = PurePosixPath(binding_rel).parent.as_posix()
        return binding_abs.parent, "" if binding_root == "." else binding_root
    return None


def _resolve_registered_metadata_target_from_resources(
    studio_dir: Path,
    resources: Any,
) -> Optional[Tuple[Path, str]]:
    if not isinstance(resources, dict):
        return None
    binding_paths = [
        binding_path
        for binding_path in (
            _extract_registered_binding_path(binding)
            for binding in resources.values()
        )
        if binding_path is not None
    ]
    for target_name in (_KIT_SKILL_FILE, _KIT_AGENTS_FILE):
        metadata_target = _resolve_registered_metadata_target_for_name(
            studio_dir,
            binding_paths,
            target_name,
        )
        if metadata_target is not None:
            return metadata_target
    return None


def _resolve_registered_kit_metadata_target(
    studio_dir: Path,
    kit_slug: str,
    kit_entry: Any,
) -> Tuple[Optional[Path], str]:
    kit_data = kit_entry if isinstance(kit_entry, dict) else {}
    registered_path = kit_data.get("path") if isinstance(kit_data.get("path"), str) else None
    kit_rel_path = _normalize_registered_kit_path(registered_path, kit_slug)
    kit_dir = _resolve_registered_kit_root_dir(
        studio_dir,
        registered_path if isinstance(registered_path, str) and registered_path.strip() else kit_rel_path,
    )
    if kit_dir is not None and (
        (kit_dir / _KIT_SKILL_FILE).is_file() or (kit_dir / _KIT_AGENTS_FILE).is_file()
    ):
        return kit_dir, kit_rel_path

    metadata_target = _resolve_registered_metadata_target_from_resources(
        studio_dir,
        kit_data.get("resources", {}),
    )
    if metadata_target is not None:
        return metadata_target

    return kit_dir, kit_rel_path


def _resolve_installed_kit_root(
    studio_dir: Path,
    config_dir: Path,
    kit_slug: str,
) -> Tuple[Optional[Path], str, Dict[str, Any], bool]:
    kit_entry = _read_kits_from_core_toml(config_dir).get(kit_slug, {})
    registered_path = kit_entry.get("path") if isinstance(kit_entry, dict) else None
    kit_rel_path = _normalize_registered_kit_path(registered_path, kit_slug)
    kit_dir = _resolve_registered_kit_root_dir(
        studio_dir,
        registered_path if isinstance(registered_path, str) and registered_path.strip() else kit_rel_path,
    )
    return kit_dir, kit_rel_path, kit_entry, isinstance(registered_path, str) and bool(registered_path.strip())


def _registered_slug_for_local_kit_path(
    config_dir: Path,
    studio_dir: Path,
    kit_source: Path,
) -> str:
    kit_source_resolved = kit_source.resolve()
    matches: List[str] = []
    for kit_slug, kit_entry in _read_kits_from_core_toml(config_dir).items():
        if not isinstance(kit_entry, dict):
            continue
        registered_path = kit_entry.get("path")
        if not isinstance(registered_path, str) or not registered_path.strip():
            continue
        registered_dir = _resolve_registered_kit_root_dir(studio_dir, registered_path)
        if registered_dir is not None and registered_dir.resolve() == kit_source_resolved:
            matches.append(kit_slug)
    return matches[0] if len(matches) == 1 else ""


def _collect_kit_metadata(
    config_kit_dir: Optional[Path],
    kit_slug: str,
    registered_kit_path: Optional[str] = None,
) -> Dict[str, str]:
    """Read installed kit files and return metadata for .gen/ aggregation.

    Returns dict with:
        agents_content — raw content of kit's AGENTS.md for ``.gen/AGENTS.md``
    """
    # @cpt-begin:cpt-studio-algo-kit-content-mgmt:p1:inst-collect-metadata
    del kit_slug, registered_kit_path
    result: Dict[str, str] = {"skill_nav": "", "agents_content": ""}

    agents_path = config_kit_dir / _KIT_AGENTS_FILE if config_kit_dir is not None else None
    if agents_path is not None and agents_path.is_file():
        try:
            result["agents_content"] = agents_path.read_text(encoding="utf-8")
        except OSError:
            pass

    return result
    # @cpt-end:cpt-studio-algo-kit-content-mgmt:p1:inst-collect-metadata
# @cpt-end:cpt-studio-algo-kit-content-mgmt:p1:inst-collect-metadata-fn


def _binding_is_public_metadata_resource(binding: Dict[str, Any], kind: str) -> bool:
    public_value = binding.get("public")
    if isinstance(public_value, bool):
        return public_value
    if isinstance(public_value, str):
        return public_value.strip().lower() in {"1", "true", "yes", "on"}
    return kind in {"skill", "rule"}


def _collect_registered_kit_metadata(
    studio_dir: Path,
    kit_slug: str,
    kit_entry: Any,
) -> Dict[str, str]:
    kit_data = kit_entry if isinstance(kit_entry, dict) else {}
    resources = kit_data.get("resources")
    install_mode = str(kit_data.get("install_mode", "") or "").strip()
    if (not isinstance(resources, dict) or not resources) and install_mode == "register":
        try:
            from ..utils.kit_model import load_kit_model
            from ..utils.manifest import resolve_resource_bindings_with_errors

            # @cpt-begin:cpt-studio-algo-kit-info-model-output:p1:inst-info-kitmodel-source
            kit_dir, _kit_rel_path = _resolve_registered_kit_metadata_target(
                studio_dir,
                kit_slug,
                kit_entry,
            )
            if kit_dir is None:
                return {}
            model = load_kit_model(kit_dir, kit_slug=kit_slug)
            # @cpt-end:cpt-studio-algo-kit-info-model-output:p1:inst-info-kitmodel-source
            bindings, _binding_errors = resolve_resource_bindings_with_errors(
                studio_dir / "config",
                kit_slug,
                studio_dir,
            )
            resources = {}
            public_by_id = {
                str(getattr(component, "id", "")): component
                for component in getattr(model, "public_components", []) or []
            }
            for resource_id, binding_path in bindings.items():
                component = public_by_id.get(str(resource_id))
                if component is None:
                    continue
                resources[str(resource_id)] = {
                    "path": _serialize_manifest_binding_path(binding_path, studio_dir),
                    "kind": str(getattr(component, "kind", "") or ""),
                    "public": True,
                }
        except (OSError, ValueError):
            resources = {}
    if not isinstance(resources, dict) or not resources:
        kit_dir, kit_rel_path = _resolve_registered_kit_metadata_target(
            studio_dir,
            kit_slug,
            kit_entry,
        )
        return _collect_kit_metadata(kit_dir, kit_slug, kit_rel_path)

    result: Dict[str, str] = {"skill_nav": "", "agents_content": ""}
    agents_parts: List[str] = []
    for _res_id, raw_binding in sorted(resources.items()):
        if not isinstance(raw_binding, dict):
            raw_binding = {"path": raw_binding} if isinstance(raw_binding, str) else {}
        binding_path = _extract_registered_binding_path(raw_binding)
        if not binding_path:
            continue
        kind = str(raw_binding.get("kind") or "").strip()
        if not kind:
            name = PurePosixPath(binding_path).name
            if name == _KIT_SKILL_FILE:
                kind = "skill"
            elif name == _KIT_AGENTS_FILE:
                kind = "rule"
        if kind not in {"skill", "rule"}:
            continue
        if not _binding_is_public_metadata_resource(raw_binding, kind):
            continue
        binding_abs = _resolve_registered_kit_dir(studio_dir, binding_path)
        if binding_abs is None or not binding_abs.is_file():
            continue
        if kind == "skill":
            continue
        if kind == "rule":
            try:
                agents_parts.append(binding_abs.read_text(encoding="utf-8"))
            except OSError:
                pass
    result["agents_content"] = "\n\n".join(part for part in agents_parts if part)
    return result


# ---------------------------------------------------------------------------
# .gen/ aggregation — single source of truth for all callers
# ---------------------------------------------------------------------------

# @cpt-algo:cpt-studio-algo-kit-regen-gen:p1
# @cpt-begin:cpt-studio-algo-kit-regen-gen:p1:inst-regen-fn
def regenerate_gen_aggregates(studio_dir: Path) -> Dict[str, Any]:
    """Regenerate .gen/AGENTS.md and .gen/README.md from all installed kits.

    Reads registered kits from core.toml, collects AGENTS.md metadata from each
    registered kit, and writes the aggregate files into .gen/.

    This is the canonical function — called by cmd_kit_install, cmd_kit_update,
    cmd_init, and cmd_update.

    Returns dict with keys: gen_agents and gen_readme (action strings), and
    gen_skill when a legacy generated skill aggregate is removed.
    """
    config_dir = studio_dir / "config"
    gen_dir = studio_dir / ".gen"
    gen_dir.mkdir(parents=True, exist_ok=True)

    result: Dict[str, Any] = {}

    # @cpt-begin:cpt-studio-algo-kit-regen-gen:p1:inst-scan-kits
    # Collect metadata from all installed kits
    gen_agents_parts: List[str] = []
    kits_map = _read_kits_from_core_toml(config_dir)
    for kit_slug in sorted(kits_map):
        # @cpt-begin:cpt-studio-algo-kit-regen-gen:p1:inst-collect-all-metadata
        meta = _collect_registered_kit_metadata(studio_dir, kit_slug, kits_map.get(kit_slug, {}))
        if meta["agents_content"]:
            gen_agents_parts.append(meta["agents_content"])
        # @cpt-end:cpt-studio-algo-kit-regen-gen:p1:inst-collect-all-metadata
    # @cpt-end:cpt-studio-algo-kit-regen-gen:p1:inst-scan-kits

    # @cpt-begin:cpt-studio-algo-kit-regen-gen:p1:inst-read-project-name
    # Read project name from artifacts.toml (ADR-0014)
    project_name = _read_project_name_from_registry(config_dir) or "Studio"
    # @cpt-end:cpt-studio-algo-kit-regen-gen:p1:inst-read-project-name

    # @cpt-begin:cpt-studio-algo-kit-regen-gen:p1:inst-write-gen-agents
    # Write .gen/AGENTS.md
    gen_agents_content = "\n".join([
        f"# Studio: {project_name}",
        "",
        "## Navigation Rules",
        "",
        "ALWAYS open and follow `{cf-studio-path}/config/artifacts.toml` WHEN working with artifacts or codebase",
        "",
        "ALWAYS open and follow `{cf-studio-path}/.core/schemas/artifacts.schema.json` WHEN working with artifacts.toml",
        "",
        "ALWAYS open and follow `{cf-studio-path}/.core/architecture/specs/artifacts-registry.md` WHEN working with artifacts.toml",
        "",
    ])
    if gen_agents_parts:
        gen_agents_content = gen_agents_content.rstrip() + "\n\n" + "\n\n".join(gen_agents_parts) + "\n"
    gen_dir.mkdir(parents=True, exist_ok=True)
    (gen_dir / _KIT_AGENTS_FILE).write_text(gen_agents_content, encoding="utf-8")
    result["gen_agents"] = "updated"
    # @cpt-end:cpt-studio-algo-kit-regen-gen:p1:inst-write-gen-agents

    legacy_gen_skill = gen_dir / _KIT_SKILL_FILE
    if legacy_gen_skill.exists():
        legacy_gen_skill.unlink()
        result["gen_skill"] = "deleted"

    # @cpt-begin:cpt-studio-algo-kit-regen-gen:p1:inst-write-gen-readme
    # Write .gen/README.md
    from .init import _gen_readme
    (gen_dir / "README.md").write_text(_gen_readme(), encoding="utf-8")
    result["gen_readme"] = "updated"
    # @cpt-end:cpt-studio-algo-kit-regen-gen:p1:inst-write-gen-readme

    return result
# @cpt-end:cpt-studio-algo-kit-regen-gen:p1:inst-regen-fn


# @cpt-begin:cpt-studio-algo-kit-regen-gen:p1:inst-read-project-name-fn
def _read_project_name_from_registry(config_dir: Path) -> Optional[str]:
    """Read project name from config/artifacts.toml [[systems]][0].name.

    Per ADR-0014 (cpt-studio-adr-remove-system-from-core-toml),
    artifacts.toml is the single source of truth for system identity.
    """
    artifacts_toml = config_dir / "artifacts.toml"
    if not artifacts_toml.is_file():
        return None
    try:
        with open(artifacts_toml, "rb") as f:
            data = tomllib.load(f)
        systems = data.get("systems", [])
        if isinstance(systems, list) and systems:
            first = systems[0]
            if isinstance(first, dict):
                name = first.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"kit: warning: cannot read project name from {artifacts_toml}: {exc}\n")
    return None
# @cpt-end:cpt-studio-algo-kit-regen-gen:p1:inst-read-project-name-fn


def _input_stderr(prompt: str) -> str:
    # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-resolve-local-install-mode
    sys.stderr.write(prompt)
    sys.stderr.flush()
    try:
        return input("").strip()
    except EOFError:
        return ""
    # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-resolve-local-install-mode


def _prompt_git_tracking_for_installed_kit(core_toml_path: Path, kit_slug: str) -> str:
    # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-resolve-local-install-mode
    from .init import _prompt_kit_tracking_policy, _read_kit_tracking

    default_policy = _read_kit_tracking(core_toml_path, default="tracked")
    return _prompt_kit_tracking_policy(kit_slug, default_policy, None, interactive=True)
    # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-resolve-local-install-mode


def _persist_installed_kit_tracking(
    project_root: Path,
    studio_dir: Path,
    kit_slug: str,
    tracking: str,
) -> None:
    # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-delegate-install
    from .init import _persist_install_metadata, _read_install_tracking, _read_kit_tracking, _write_gitignore_block

    core_toml_path = studio_dir / "config" / _KIT_CORE_TOML
    default_kit_tracking = _read_kit_tracking(core_toml_path, default="tracked")
    runtime_tracking = _read_install_tracking(core_toml_path, "runtime_tracking", default="ignored")
    agent_tracking = _read_install_tracking(core_toml_path, "agent_tracking", default="ignored")
    _persist_install_metadata(
        core_toml_path,
        default_kit_tracking,
        runtime_tracking=runtime_tracking,
        agent_tracking=agent_tracking,
        kit_tracking_overrides={kit_slug: tracking},
    )
    install_rel = studio_dir.resolve().relative_to(project_root.resolve()).as_posix()
    _write_gitignore_block(
        project_root,
        install_rel,
        core_toml_path,
        default_kit_tracking,
    )
    # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-delegate-install


def _resolve_manifest_user_path(base: Path, raw_path: str) -> Path:
    # @cpt-begin:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-register-containment
    user_path = Path(raw_path)
    if user_path.is_absolute():
        return user_path.resolve()
    return (base / user_path).resolve()
    # @cpt-end:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-register-containment


def _path_is_within(path: Path, root: Path) -> bool:
    # @cpt-begin:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-register-containment
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
    # @cpt-end:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-register-containment


def _manifest_resource_target(
    kit_root: Path,
    res: Any,
    resource_overrides: Dict[str, Path],
) -> Path:
    if res.id in resource_overrides:
        return resource_overrides[res.id]
    return (kit_root / _resource_install_path(res)).resolve()


def _manifest_resource_binding_entry(
    *,
    res: Any,
    path: str,
) -> Dict[str, Any]:
    # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-register-bindings
    entry: Dict[str, Any] = {"path": path}
    kind = str(getattr(res, "kind", "") or "").strip()
    if kind:
        entry["kind"] = kind
    artifact_bindings = getattr(res, "artifact_bindings", None)
    if isinstance(artifact_bindings, dict) and artifact_bindings:
        entry["artifacts"] = artifact_bindings
    entry["public"] = bool(getattr(res, "public", False))
    return entry
    # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-register-bindings


def _manifest_resource_bindings(
    studio_dir: Path,
    kit_root: Path,
    resources: List[Any],
    resource_overrides: Dict[str, Path],
) -> Dict[str, Dict[str, Any]]:
    # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-register-bindings
    bindings: Dict[str, Dict[str, Any]] = {}
    for res in resources:
        entry = _manifest_resource_binding_entry(
            res=res,
            path=_serialize_manifest_binding_path(
                _manifest_resource_target(kit_root, res, resource_overrides),
                studio_dir,
            ),
        )
        bindings[res.id] = entry
    return bindings
    # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-register-bindings


def _manifest_register_resource_bindings(
    studio_dir: Path,
    kit_source: Path,
    resources: List[Any],
) -> Dict[str, Dict[str, Any]]:
    # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-register-bindings
    bindings: Dict[str, Dict[str, Any]] = {}
    for res in resources:
        entry = _manifest_resource_binding_entry(
            res=res,
            path=_serialize_manifest_binding_path(
                (kit_source / res.source).resolve(),
                studio_dir,
            ),
        )
        bindings[res.id] = entry
    return bindings
    # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-register-bindings


# @cpt-begin:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-hashes
# @cpt-begin:cpt-studio-algo-kit-public-component-generation:p1:inst-public-prefix
def _kit_model_public_component_names(model: Any) -> Dict[str, str]:
    names: Dict[str, str] = {}
    for component in getattr(model, "public_components", []) or []:
        name = str(getattr(component, "generated_name", "") or "").strip()
        base_component_id = str(getattr(component, "id", "") or "")
        if name:
            names[name] = base_component_id
        if str(getattr(component, "kind", "") or "") != "agent":
            continue
        for subagent in getattr(component, "subagents", []) or []:
            if not isinstance(subagent, dict):
                continue
            subagent_id = str(subagent.get("id", "") or "").strip()
            if not subagent_id:
                continue
            prefix_generated_name = bool(subagent.get("prefix_generated_name", True))
            if prefix_generated_name:
                prefix = f"cf-{model.slug}-"
                subagent_name = subagent_id if subagent_id == f"cf-{model.slug}" or subagent_id.startswith(prefix) else f"{prefix}{subagent_id}"
            else:
                subagent_name = subagent_id
            names[subagent_name] = f"{base_component_id}.subagents.{subagent_id}"
    return names
# @cpt-end:cpt-studio-algo-kit-public-component-generation:p1:inst-public-prefix
# @cpt-end:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-hashes


# @cpt-begin:cpt-studio-algo-kit-public-component-generation:p1:inst-public-prefix
def _public_component_name_conflicts(
    studio_dir: Path,
    installing_slug: str,
    installing_model: Any,
) -> List[str]:
    incoming = _kit_model_public_component_names(installing_model)
    if not incoming:
        return []

    errors: List[str] = []
    seen: Dict[str, str] = {}
    for component in getattr(installing_model, "public_components", []) or []:
        name = str(getattr(component, "generated_name", "") or "").strip()
        base_component_id = str(getattr(component, "id", "") or "")
        if not name:
            continue
        component_id = base_component_id
        if name in seen:
            errors.append(
                f"Public component name conflict in kit '{installing_slug}': "
                f"'{name}' is produced by resources '{seen[name]}' and '{component_id}'",
            )
        else:
            seen[name] = component_id
        if str(getattr(component, "kind", "") or "") != "agent":
            continue
        for subagent in getattr(component, "subagents", []) or []:
            if not isinstance(subagent, dict):
                continue
            subagent_id = str(subagent.get("id", "") or "").strip()
            if not subagent_id:
                continue
            prefix_generated_name = bool(subagent.get("prefix_generated_name", True))
            if prefix_generated_name:
                prefix = f"cf-{installing_slug}-"
                name = subagent_id if subagent_id == f"cf-{installing_slug}" or subagent_id.startswith(prefix) else f"{prefix}{subagent_id}"
            else:
                name = subagent_id
            subagent_component_id = f"{base_component_id}.subagents.{subagent_id}"
            if name in seen:
                errors.append(
                    f"Public component name conflict in kit '{installing_slug}': "
                    f"'{name}' is produced by '{seen[name]}' and '{subagent_component_id}'",
                )
            else:
                seen[name] = subagent_component_id
    if errors:
        return errors

    try:
        from ..utils.kit_model import load_kit_model
    except ImportError:
        return []

    config_dir = studio_dir / "config"
    for existing_slug, kit_entry in sorted(_read_kits_from_core_toml(config_dir).items()):
        existing_slug_str = str(existing_slug)
        if existing_slug_str == str(installing_slug):
            continue
        if not isinstance(kit_entry, dict):
            continue
        existing_path = str(kit_entry.get("path") or f"config/kits/{existing_slug_str}")
        existing_root = _resolve_registered_kit_dir(studio_dir, existing_path)
        if existing_root is None or not existing_root.is_dir():
            continue
        try:
            existing_model = load_kit_model(existing_root)
        except (OSError, ValueError):
            continue
        for name, resource_id in incoming.items():
            existing_names = _kit_model_public_component_names(existing_model)
            if name in existing_names:
                errors.append(
                    f"Public component name conflict: kit '{installing_slug}' resource "
                    f"'{resource_id}' generates '{name}', already generated by kit "
                    f"'{existing_slug_str}' resource '{existing_names[name]}'",
                )
    return errors
# @cpt-end:cpt-studio-algo-kit-public-component-generation:p1:inst-public-prefix


def _local_path_provenance(kit_source: Path, install_mode: str, studio_dir: Path) -> Dict[str, str]:
    # @cpt-begin:cpt-studio-state-kit-authority:p1:inst-local-authority-state
    return {
        "source_type": "local_path",
        "resolver_mode": install_mode,
        "resolution_basis": "local_path",
        "effective_source": _serialize_manifest_binding_path(kit_source.resolve(), studio_dir),
        "verified": "local",
        "freshness": "local",
    }
    # @cpt-end:cpt-studio-state-kit-authority:p1:inst-local-authority-state


def _load_manifest_install_adapter(kit_source: Path, kit_slug: str = "") -> Optional[Manifest]:
    """Load a manifest installer adapter only through a manifest-backed KitModel."""
    from ..utils.kit_model import load_kit_model
    from ..utils.manifest import load_manifest, resolve_kit_manifest_path

    if resolve_kit_manifest_path(kit_source) is None:
        return None

    model = load_kit_model(kit_source, source_hint="manifest", kit_slug=kit_slug)
    if getattr(model, "manifest_source", "") not in {"canonical", "legacy_manifest"}:
        return None
    return load_manifest(kit_source, kit_slug=kit_slug)


def _validate_register_manifest_containment(
    project_root: Optional[Path],
    studio_dir: Path,
    kit_source: Path,
    kit_slug: str,
    manifest: Manifest,
) -> List[str]:
    # @cpt-begin:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-register-containment
    # @cpt-begin:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-register-reject-escape
    if project_root is None:
        return ["Register install mode requires a resolved project root"]
    root = project_root.resolve()
    errors: List[str] = []
    source_root = kit_source.resolve()
    if not _path_is_within(source_root, root):
        errors.append(f"Kit source '{kit_source}' must be inside project root '{root}' for register mode")
    from ..utils.manifest import resolve_kit_manifest_path

    manifest_file = resolve_kit_manifest_path(kit_source)
    if manifest_file is None or not manifest_file.is_file() or not _path_is_within(manifest_file, root):
        errors.append("Kit manifest must be inside the project root for register mode")
    manifest_root_value = manifest.root.replace(
        "{cf-studio-path}", ".",
    ).replace(
        "{slug}", kit_slug,
    )
    manifest_root = _resolve_registered_kit_dir(studio_dir, manifest_root_value)
    if manifest_root is None or not _path_is_within(manifest_root, root):
        errors.append(f"Manifest root '{manifest.root}' must resolve inside project root '{root}' for register mode")
    for res in manifest.resources:
        raw_source = Path(res.source)
        if raw_source.is_absolute():
            errors.append(f"Resource '{res.id}': source '{res.source}' must be relative for register mode")
            continue
        source_path = (kit_source / res.source).resolve()
        if not _path_is_within(source_path, root):
            errors.append(f"Resource '{res.id}': source '{res.source}' escapes the project root")
    return errors
    # @cpt-end:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-register-reject-escape
    # @cpt-end:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-register-containment


# @cpt-begin:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-mode-always-ask
def _prompt_local_manifest_install_mode(
    project_root: Path,
    studio_dir: Path,
    kit_source: Path,
    kit_slug: str,
    manifest: Manifest,
) -> str:
    """Ask an interactive local manifest install to copy or register resources."""
    register_errors = _validate_register_manifest_containment(
        project_root,
        studio_dir,
        kit_source,
        kit_slug,
        manifest,
    )
    register_available = not register_errors
    default_mode = "register" if register_available else "copy"
    while True:
        sys.stderr.write("\n")
        sys.stderr.write(f"  Local kit install mode: {kit_slug}\n")
        sys.stderr.write("  - copy: copy resources into Studio-managed storage\n")
        if register_available:
            sys.stderr.write("  - register: leave in-project resources in place and bind them\n")
        else:
            sys.stderr.write("  - register: unavailable for this source\n")
        answer = _input_stderr(
            f"  Install mode [copy/register] (default {default_mode}): "
        ).lower()
        if not answer:
            return default_mode
        if answer in {"c", "copy"}:
            return "copy"
        if answer in {"r", "register"}:
            if register_available:
                return "register"
            sys.stderr.write("  Register mode is unavailable:\n")
            for error in register_errors:
                sys.stderr.write(f"  - {error}\n")
# @cpt-end:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-mode-always-ask


def _emit_manifest_install_plan(
    kit_slug: str,
    kit_root: Path,
    resources: List[Any],
    resource_overrides: Dict[str, Path],
) -> None:
    sys.stderr.write("\n")
    sys.stderr.write(f"  Kit install plan: {kit_slug}\n")
    sys.stderr.write(f"  - Kit root: {kit_root}\n")
    if not resources:
        sys.stderr.write("  - Resources: none declared\n")
    else:
        sys.stderr.write("  - Files to write:\n")
        for idx, res in enumerate(resources, start=1):
            target = _manifest_resource_target(kit_root, res, resource_overrides)
            mod = "editable" if res.user_modifiable else "locked"
            sys.stderr.write(
                f"    [{idx}] {res.id} ({res.type}, {mod}): "
                f"{res.source} -> {target}\n"
            )
    sys.stderr.write("\n")


def _prompt_manifest_install_plan(
    kit_slug: str,
    studio_dir: Path,
    kit_root: Path,
    manifest: Manifest,
    *,
    resources: Optional[List[Any]] = None,
    registered_kit_root_rel: Optional[str] = None,
    interactive: bool,
) -> tuple[Path, str, Dict[str, Dict[str, str]]]:
    resource_overrides: Dict[str, Path] = {}
    resources = list(resources if resources is not None else manifest.resources)
    can_edit = manifest.user_modifiable or any(
        bool(getattr(res, "user_modifiable", True)) for res in resources
    )
    root_changed = False

    def _kit_root_rel() -> str:
        if registered_kit_root_rel is not None and not root_changed:
            return registered_kit_root_rel
        return _serialize_manifest_binding_path(kit_root, studio_dir)

    if not interactive or not sys.stdin.isatty():
        kit_root_rel = _kit_root_rel()
        return (
            kit_root,
            kit_root_rel,
            _manifest_resource_bindings(studio_dir, kit_root, resources, resource_overrides),
        )

    # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-prompt-path
    while True:
        _emit_manifest_install_plan(kit_slug, kit_root, resources, resource_overrides)
        if not can_edit:
            kit_root_rel = _kit_root_rel()
            return (
                kit_root,
                kit_root_rel,
                _manifest_resource_bindings(studio_dir, kit_root, resources, resource_overrides),
            )
        answer = _input_stderr("  Change kit install paths? [y/N]: ").lower()
        if answer not in ("y", "yes"):
            kit_root_rel = _kit_root_rel()
            return (
                kit_root,
                kit_root_rel,
                _manifest_resource_bindings(studio_dir, kit_root, resources, resource_overrides),
            )

        sys.stderr.write("\n")
        sys.stderr.write("  Select path to change\n")
        menu: List[tuple[str, str, Optional[Any]]] = []
        if manifest.user_modifiable:
            menu.append(("root", f"Kit root -> {kit_root}", None))
        for res in resources:
            if not res.user_modifiable:
                continue
            label = f"{res.id} -> {_manifest_resource_target(kit_root, res, resource_overrides)}"
            menu.append(("resource", label, res))
        for idx, (_, label, _res) in enumerate(menu, start=1):
            sys.stderr.write(f"  [{idx}] {label}\n")
        done_idx = len(menu) + 1
        sys.stderr.write(f"  [{done_idx}] Done\n")
        choice_raw = _input_stderr("  Choice: ").lower()
        if choice_raw in ("", "d", "done", str(done_idx)):
            kit_root_rel = _kit_root_rel()
            return (
                kit_root,
                kit_root_rel,
                _manifest_resource_bindings(studio_dir, kit_root, resources, resource_overrides),
            )
        try:
            choice = int(choice_raw)
        except ValueError:
            continue
        if choice < 1 or choice > len(menu):
            continue
        kind, _, res = menu[choice - 1]
        if kind == "root":
            new_root = _input_stderr(f"  Kit root directory [{kit_root}]: ")
            if new_root:
                kit_root = _resolve_manifest_user_path(studio_dir, new_root)
                root_changed = True
        elif res is not None:
            current_target = _manifest_resource_target(kit_root, res, resource_overrides)
            new_target = _input_stderr(f"  Resource '{res.id}' path [{current_target}]: ")
            if new_target:
                resource_overrides[res.id] = _resolve_manifest_user_path(kit_root, new_target)
    # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-prompt-path


# ---------------------------------------------------------------------------
# Core kit installation logic (used by both cmd_kit_install and init)
# ---------------------------------------------------------------------------

# @cpt-dod:cpt-studio-dod-kit-install:p1
# @cpt-state:cpt-studio-state-kit-installation:p1
# @cpt-algo:cpt-studio-algo-kit-install:p1
def install_kit(
    kit_source: Path,
    studio_dir: Path,
    kit_slug: str,
    kit_version: str = "",
    source: str = "",
    *,
    interactive: bool = False,
    install_mode: str = "copy",
    project_root: Optional[Path] = None,
    authority_metadata: Optional[Dict[str, Any]] = None,
    approved_overwrites: Optional[List[str]] = None,
    approved_tool_risks: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Install a kit: copy ready files from source into config/kits/{slug}/.

    Kits are direct file packages — no blueprint processing.
    Caller is responsible for validation and dry-run checks.

    Args:
        kit_source: Kit source directory.
        studio_dir: Resolved project studio directory.
        kit_slug: Kit identifier.
        kit_version: Kit version string.
        source: Source identifier for registration (e.g. "github:owner/repo").
        interactive: If True and stdin is a tty, show the install plan and allow path edits.

    Returns:
        Dict with: status, kit, version, files_copied,
        errors, actions, skill_nav, agents_content.
    """
    config_dir = studio_dir / "config"
    config_kit_dir, config_kit_rel, kit_entry, has_registered_kit_path = _resolve_installed_kit_root(
        studio_dir, config_dir, kit_slug,
    )

    actions: Dict[str, str] = {}
    errors: List[str] = []

    if config_kit_dir is None:
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "errors": [
                f"Kit '{kit_slug}' is registered at absolute path '{config_kit_rel}' which is not accessible on this OS",
            ],
        }

    # @cpt-begin:cpt-studio-algo-kit-install:p1:inst-validate-source
    if not kit_source.is_dir():
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "errors": [f"Kit source not found: {kit_source}"],
        }
    # @cpt-end:cpt-studio-algo-kit-install:p1:inst-validate-source

    # @cpt-begin:cpt-studio-algo-kit-install:p1:inst-manifest-install
    # Check for manifest-driven installation
    try:
        manifest = _load_manifest_install_adapter(kit_source, kit_slug=kit_slug)
    except (OSError, ValueError) as exc:
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "errors": [str(exc)],
        }
    if manifest is not None:
        # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-manifest-install
        return install_kit_with_manifest(
            kit_source, studio_dir, kit_slug, kit_version,
            manifest, interactive=interactive, source=source,
            install_mode=install_mode,
            project_root=project_root,
            authority_metadata=authority_metadata,
            approved_overwrites=approved_overwrites,
            approved_tool_risks=approved_tool_risks,
            kit_path=(
                kit_entry.get("path", "")
                if has_registered_kit_path and isinstance(kit_entry, dict)
                else ""
            ),
        )
        # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-manifest-install
    # @cpt-end:cpt-studio-algo-kit-install:p1:inst-manifest-install

    if install_mode != "copy":
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "errors": [f"Unsupported install mode: {install_mode}"],
        }

    # @cpt-begin:cpt-studio-algo-kit-install:p1:inst-copy-content
    # Copy kit content → config/kits/{slug}/ (legacy path)
    copy_actions = _copy_kit_content(kit_source, config_kit_dir)
    actions.update(copy_actions)
    # @cpt-end:cpt-studio-algo-kit-install:p1:inst-copy-content

    # @cpt-begin:cpt-studio-algo-kit-install:p1:inst-read-version
    # Read version from source conf.toml (conf.toml is NOT copied into installed kit)
    local_metadata: Dict[str, str] = {}
    src_conf = kit_source / _KIT_CONF_FILE
    if src_conf.is_file():
        conf_version = _read_kit_version(src_conf)
        if conf_version:
            local_metadata["conf_version"] = conf_version
            if not kit_version:
                kit_version = conf_version
    # @cpt-end:cpt-studio-algo-kit-install:p1:inst-read-version

    # @cpt-begin:cpt-studio-algo-kit-install:p1:inst-seed-configs
    # Seed kit config files into config/ (only if missing)
    scripts_dir = config_kit_dir / "scripts"
    if scripts_dir.is_dir():
        _seed_kit_config_files(scripts_dir, config_dir, actions)
    # @cpt-end:cpt-studio-algo-kit-install:p1:inst-seed-configs

    # @cpt-begin:cpt-studio-algo-kit-install:p1:inst-register-core
    # Register in core.toml
    registration_errors = _register_kit_in_core_toml(
        config_dir,
        kit_slug,
        kit_version,
        studio_dir,
        source=source,
        install_mode=install_mode,
        authority_metadata=authority_metadata,
        local_metadata=local_metadata or None,
    )
    if registration_errors:
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "version": kit_version,
            "install_mode": install_mode,
            "files_copied": sum(1 for v in copy_actions.values() if v == "copied"),
            "errors": registration_errors,
            "actions": actions,
        }
    # @cpt-end:cpt-studio-algo-kit-install:p1:inst-register-core

    # @cpt-begin:cpt-studio-algo-kit-install:p1:inst-collect-meta
    # Collect metadata for .gen/ aggregation
    meta = _collect_registered_kit_metadata(
        studio_dir,
        kit_slug,
        {"path": config_kit_rel},
    )
    # @cpt-end:cpt-studio-algo-kit-install:p1:inst-collect-meta

    # @cpt-begin:cpt-studio-algo-kit-install:p1:inst-return-result
    files_copied = sum(1 for v in copy_actions.values() if v == "copied")

    return {
        "status": "PASS" if not errors else "WARN",
        "action": "installed",
        "kit": kit_slug,
        "version": kit_version,
        "install_mode": install_mode,
        "files_copied": files_copied,
        "local_metadata": local_metadata,
        "errors": errors,
        "skill_nav": meta["skill_nav"],
        "agents_content": meta["agents_content"],
        "actions": actions,
    }
    # @cpt-end:cpt-studio-algo-kit-install:p1:inst-return-result


# ---------------------------------------------------------------------------
# Manifest-driven kit installation
# ---------------------------------------------------------------------------

# @cpt-algo:cpt-studio-algo-kit-manifest-install:p1
def install_kit_with_manifest(
    kit_source: Path,
    studio_dir: Path,
    kit_slug: str,
    kit_version: str,
    manifest: Manifest,
    *,
    interactive: bool = True,
    install_mode: str = "copy",
    project_root: Optional[Path] = None,
    source: str = "",
    kit_path: str = "",
    authority_metadata: Optional[Dict[str, Any]] = None,
    approved_overwrites: Optional[List[str]] = None,
    approved_tool_risks: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Install a kit using its manifest.toml — manifest-driven installation.

    Each declared resource is copied from kit source to a resolved target path.
    Resource bindings are registered in core.toml under ``[kits.{slug}.resources]``.

    Args:
        kit_source: Kit source directory (containing manifest.toml).
        studio_dir: Resolved project studio directory.
        kit_slug: Kit identifier.
        kit_version: Kit version string.
        manifest: Parsed Manifest object.
        interactive: If True and stdin is a tty, prompt for user_modifiable paths.
        source: Source identifier for registration (e.g. "github:owner/repo").

    Returns:
        Dict with: status, kit, version, files_copied, resource_bindings,
        errors, skill_nav, agents_content.
    """
    from ..utils.manifest import validate_manifest

    config_dir = studio_dir / "config"
    errors: List[str] = []  # collects non-fatal warnings (copy/template failures)
    files_copied = 0

    # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-read
    # Validate manifest against kit source
    validation_errors = validate_manifest(manifest, kit_source)
    if validation_errors:
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "errors": validation_errors,
        }
    # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-read

    try:
        from ..utils.kit_model import load_kit_model
        kit_model = load_kit_model(kit_source, kit_slug=kit_slug)
    except (OSError, ValueError) as exc:
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "errors": [str(exc)],
        }
    model_resources = list(getattr(kit_model, "resources", []))
    risk_errors = _tool_risk_approval_errors(
        kit_model,
        interactive=interactive,
        approved_tool_risks=approved_tool_risks,
    )
    if risk_errors:
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "install_mode": install_mode,
            "errors": risk_errors,
        }
    # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-public-name-conflict
    name_conflicts = _public_component_name_conflicts(studio_dir, kit_slug, kit_model)
    if name_conflicts:
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "install_mode": install_mode,
            "errors": name_conflicts,
        }
    # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-public-name-conflict

    # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-resolve-install-mode
    if install_mode not in {"copy", "register"}:
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "errors": [f"Unsupported install mode: {install_mode}"],
        }
    # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-resolve-install-mode

    if install_mode == "register":
        # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-register-resource-in-place
        # @cpt-begin:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-register-core-only
        containment_errors = _validate_register_manifest_containment(
            project_root,
            studio_dir,
            kit_source,
            kit_slug,
            manifest,
        )
        if containment_errors:
            return {
                "status": "FAIL",
                "kit": kit_slug,
                "install_mode": install_mode,
                "errors": containment_errors,
            }
        resource_bindings = _manifest_register_resource_bindings(
            studio_dir,
            kit_source,
            model_resources,
        )
        kit_root = kit_source.resolve()
        kit_root_rel = _serialize_manifest_binding_path(kit_root, studio_dir)
        local_metadata: Dict[str, str] = {}
        src_conf = kit_source / _KIT_CONF_FILE
        if src_conf.is_file():
            conf_version = _read_kit_version(src_conf)
            if conf_version:
                local_metadata["conf_version"] = conf_version
                if not kit_version:
                    kit_version = conf_version
        registration_errors = _register_kit_in_core_toml(
            config_dir, kit_slug, kit_version, studio_dir,
            source=source, resources=resource_bindings, kit_path=kit_root_rel,
            install_mode=install_mode,
            source_provenance=_local_path_provenance(kit_source, install_mode, studio_dir),
            authority_metadata=authority_metadata,
            local_metadata=local_metadata or None,
            tool_risk_fingerprint=str(getattr(kit_model, "tool_risk_fingerprint", "") or ""),
        )
        if registration_errors:
            return {
                "status": "FAIL",
                "kit": kit_slug,
                "install_mode": install_mode,
                "errors": registration_errors,
            }
        meta = _collect_registered_kit_metadata(
            studio_dir,
            kit_slug,
            {"path": kit_root_rel, "resources": resource_bindings},
        )
        # @cpt-end:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-register-core-only
        # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-register-resource-in-place
        return {
            "status": "PASS",
            "action": "installed",
            "kit": kit_slug,
            "version": kit_version,
            "install_mode": install_mode,
            "files_copied": 0,
            "files_registered": len(resource_bindings),
            "resource_bindings": {k: v["path"] for k, v in resource_bindings.items()},
            "local_metadata": local_metadata,
            "errors": errors,
            "skill_nav": meta["skill_nav"],
            "agents_content": meta["agents_content"],
        }

    # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-root-prompt
    # Resolve kit root directory from manifest template
    if kit_path:
        kit_root_rel = _normalize_registered_kit_path(kit_path, kit_slug)
        kit_root = _resolve_registered_kit_dir(studio_dir, kit_path)
        if kit_root is None:
            return {
                "status": "FAIL",
                "kit": kit_slug,
                "errors": [
                    f"Kit '{kit_slug}' is registered at absolute path '{kit_root_rel}' which is not accessible on this OS",
                ],
            }
    else:
        kit_root_template = manifest.root
        kit_root_rel = kit_root_template.replace(
            "{cf-studio-path}", "."
        ).replace(
            "{slug}", kit_slug
        )
        kit_root = (studio_dir / kit_root_rel).resolve()
    # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-root-prompt

    # @cpt-begin:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-copy-resources
    kit_root, kit_root_rel, resource_bindings = _prompt_manifest_install_plan(
        kit_slug,
        studio_dir,
        kit_root,
        manifest,
        resources=model_resources,
        registered_kit_root_rel=kit_root_rel,
        interactive=interactive,
    )
    # @cpt-begin:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-copy-no-silent-overwrite
    overwrite_errors = _preflight_manifest_copy_overwrites(
        kit_source,
        studio_dir,
        model_resources,
        resource_bindings,
        interactive=interactive,
        approved_overwrites=approved_overwrites or [],
    )
    if overwrite_errors:
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "install_mode": install_mode,
            "errors": overwrite_errors,
        }
    # @cpt-end:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-copy-no-silent-overwrite
    kit_root.mkdir(parents=True, exist_ok=True)

    # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-foreach-resource
    for res in model_resources:
        # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-default-path
        binding_path = resource_bindings[res.id]["path"]
        target_abs = (studio_dir / binding_path).resolve()
        # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-default-path

        # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-copy-resource
        _copy_manifest_resource(kit_source, res, target_abs)
        # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-copy-resource
        files_copied += 1
    # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-foreach-resource
    # @cpt-end:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-copy-resources

    # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-resolve-vars
    _preserve_template_variables(kit_root, resource_bindings)
    # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-resolve-vars

    # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-register-bindings
    # Read version from source conf.toml if not provided
    local_metadata: Dict[str, str] = {}
    src_conf = kit_source / _KIT_CONF_FILE
    if src_conf.is_file():
        conf_version = _read_kit_version(src_conf)
        if conf_version:
            local_metadata["conf_version"] = conf_version
            if not kit_version:
                kit_version = conf_version

    # Seed kit config files into config/ (only if missing)
    scripts_dir = kit_root / "scripts"
    if scripts_dir.is_dir():
        _seed_kit_config_files(scripts_dir, config_dir, {})

    # Register in core.toml with resource bindings
    registration_errors = _register_kit_in_core_toml(
        config_dir, kit_slug, kit_version, studio_dir,
        source=source, resources=resource_bindings, kit_path=kit_root_rel,
        install_mode=install_mode,
        authority_metadata=authority_metadata,
        local_metadata=local_metadata or None,
        tool_risk_fingerprint=str(getattr(manifest, "tool_risk_fingerprint", "") or ""),
    )
    if registration_errors:
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "install_mode": install_mode,
            "files_copied": files_copied,
            "errors": registration_errors,
        }
    # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-register-bindings

    # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-collect-meta
    # Collect metadata for .gen/ aggregation
    meta = _collect_registered_kit_metadata(
        studio_dir,
        kit_slug,
        {"path": kit_root_rel, "resources": resource_bindings},
    )
    # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-collect-meta

    # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-return
    return {
        "status": "PASS" if not errors else "WARN",
        "action": "installed",
        "kit": kit_slug,
        "version": kit_version,
        "install_mode": install_mode,
        "files_copied": files_copied,
        "resource_bindings": {k: v["path"] for k, v in resource_bindings.items()},
        "local_metadata": local_metadata,
        "errors": errors,
        "skill_nav": meta["skill_nav"],
        "agents_content": meta["agents_content"],
    }
    # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-return


# @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-copy-manifest-resource
def _copy_manifest_resource(
    kit_source: Path,
    res: Any,
    target_abs: Path,
) -> None:
    """Copy a single manifest resource from kit source to target path.

    Note: For directory resources, the existing target is removed before copying.
    Callers are responsible for ensuring *target_abs* is within the expected
    kit root directory (validated by ``validate_manifest`` for default paths;
    user-provided interactive paths are trusted as local CLI input).
    """
    src = kit_source / res.source
    if res.type == "directory":
        if target_abs.exists():
            shutil.rmtree(target_abs)
        shutil.copytree(src, target_abs)
    else:
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target_abs)
# @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-copy-manifest-resource


# @cpt-begin:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-copy-no-silent-overwrite
def _manifest_resource_changed(
    kit_source: Path,
    res: Any,
    target_abs: Path,
) -> bool:
    """Return True when copying *res* would replace different target content."""
    source_abs = kit_source / res.source
    if not target_abs.exists():
        return False
    if res.type == "file":
        if not target_abs.is_file() or not source_abs.is_file():
            return True
        try:
            return source_abs.read_bytes() != target_abs.read_bytes()
        except OSError:
            return True

    if not target_abs.is_dir() or not source_abs.is_dir():
        return True
    source_files = {
        path.relative_to(source_abs).as_posix(): path
        for path in source_abs.rglob("*")
        if path.is_file()
    }
    target_files = {
        path.relative_to(target_abs).as_posix(): path
        for path in target_abs.rglob("*")
        if path.is_file()
    }
    if set(source_files) != set(target_files):
        return True
    for rel_path, source_file in source_files.items():
        try:
            if source_file.read_bytes() != target_files[rel_path].read_bytes():
                return True
        except OSError:
            return True
    return False


def _preflight_manifest_copy_overwrites(
    kit_source: Path,
    studio_dir: Path,
    resources: List[Any],
    resource_bindings: Dict[str, Dict[str, str]],
    *,
    interactive: bool,
    approved_overwrites: List[str],
) -> List[str]:
    """Require approval before replacing changed user-modifiable resources."""
    approvals = {token.strip() for token in approved_overwrites if token.strip()}
    errors: List[str] = []
    for res in resources:
        if not res.user_modifiable:
            continue
        binding_path = resource_bindings[res.id]["path"]
        target_abs = (studio_dir / binding_path).resolve()
        if not _manifest_resource_changed(kit_source, res, target_abs):
            continue
        approval_tokens = {
            res.id,
            binding_path,
            target_abs.as_posix(),
        }
        if approvals.intersection(approval_tokens):
            continue
        if interactive and sys.stdin.isatty():
            answer = _input_stderr(
                f"Overwrite changed user-modifiable resource '{res.id}' at {target_abs}? [y/N]: "
            ).lower()
            if answer in {"y", "yes"}:
                continue
        errors.append(
            "Refusing to overwrite changed user-modifiable resource "
            f"'{res.id}' at {binding_path}; rerun with "
            f"--approve-overwrite {res.id} or --approve-overwrite {binding_path}"
        )
    return errors
# @cpt-end:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-copy-no-silent-overwrite


# @cpt-begin:cpt-studio-algo-kit-tool-permission-risk:p1:inst-risk-interactive-confirm
# @cpt-begin:cpt-studio-algo-kit-tool-permission-risk:p1:inst-risk-noninteractive-fingerprint
def _tool_risk_approval_errors(
    kit_model: Any,
    *,
    installed_kit_entry: Optional[Dict[str, Any]] = None,
    interactive: bool,
    approved_tool_risks: Optional[List[str]] = None,
) -> List[str]:
    summary = getattr(kit_model, "tool_risk_summary", {}) or {}
    fingerprint = str(getattr(kit_model, "tool_risk_fingerprint", "") or "")
    approvals = {token.strip() for token in (approved_tool_risks or []) if token.strip()}
    installed_fingerprint = ""
    if isinstance(installed_kit_entry, dict):
        installed_fingerprint = str(installed_kit_entry.get("tool_risk_fingerprint", "") or "")
    if not fingerprint and installed_fingerprint and isinstance(installed_kit_entry, dict):
        installed_kit_entry.pop("tool_risk_fingerprint", None)
    if not summary.get("requires_confirmation"):
        return []
    if fingerprint and installed_fingerprint and fingerprint == installed_fingerprint:
        return []
    if fingerprint in approvals:
        return []
    dangerous = summary.get("dangerous_tools", {})
    if interactive and sys.stdin.isatty():
        sys.stderr.write("\n  Dangerous tool permissions changed:\n")
        for resource_id, tools in sorted(dangerous.items()):
            sys.stderr.write(f"  - {resource_id}: {', '.join(tools)}\n")
        answer = _input_stderr(
            f"  Approve tool risk fingerprint {fingerprint}? [y/N]: "
        ).lower()
        if answer in {"y", "yes"}:
            return []
    return [
        "Dangerous tool permissions require approval; rerun with "
        f"--approve-tool-risk {fingerprint}",
    ]
# @cpt-end:cpt-studio-algo-kit-tool-permission-risk:p1:inst-risk-noninteractive-fingerprint
# @cpt-end:cpt-studio-algo-kit-tool-permission-risk:p1:inst-risk-interactive-confirm


# @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-resolve-template-vars
def _preserve_template_variables(
    kit_root: Path,
    resource_bindings: Dict[str, Dict[str, str]],
) -> None:
    """Keep copied kit resources byte-for-byte and resolve variables only at read time.

    The bindings are persisted in ``core.toml`` and consumed by commands such as
    ``resolve-vars``. Installation must not rewrite workflow, skill, rule, or
    template source content because those files are part of the kit source.
    """
    _ = (kit_root, resource_bindings)
# @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-resolve-template-vars


# ---------------------------------------------------------------------------
# Legacy Install Migration — auto-populate resource bindings from disk
# ---------------------------------------------------------------------------

# @cpt-algo:cpt-studio-algo-kit-manifest-legacy-migration:p1
def migrate_legacy_kit_to_manifest(
    kit_source: Path,
    studio_dir: Path,
    kit_slug: str,
    *,
    interactive: bool = True,
) -> Dict[str, Any]:
    """Migrate a legacy kit install to manifest-driven resource bindings.

    When ``cfs update`` runs and the kit source now contains ``manifest.toml``
    but ``core.toml`` has no ``[kits.{slug}.resources]``, this function
    auto-populates resource bindings from existing files on disk.

    For each manifest resource:
    - If the file/directory already exists at the expected path → register silently.
    - If it does not exist (truly new resource) → copy from source and register.

    Args:
        kit_source: Kit source directory (containing ``manifest.toml``).
        studio_dir: Resolved project studio directory.
        kit_slug: Kit identifier.
        interactive: If True and stdin is a tty, prompt for new resource paths.

    Returns:
        Dict with: status, kit, migrated_count, new_count, resource_bindings.
    """
    from ..utils.manifest import validate_manifest

    config_dir = studio_dir / "config"
    resource_bindings: Dict[str, Dict[str, str]] = {}
    migrated_count = 0  # existing files registered silently
    new_count = 0       # new files copied from source

    # @cpt-begin:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-read-manifest
    try:
        manifest = _load_manifest_install_adapter(kit_source, kit_slug=kit_slug)
    except (OSError, ValueError) as exc:
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "errors": [str(exc)],
        }
    if manifest is None:
        return {
            "status": "SKIP",
            "kit": kit_slug,
            "message": "No manifest-backed kit source",
        }

    validation_errors = validate_manifest(manifest, kit_source)
    if validation_errors:
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "errors": validation_errors,
        }
    # @cpt-end:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-read-manifest

    # @cpt-begin:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-read-root
    kit_root, kit_root_rel, _kit_entry, _has_registered_path = _resolve_installed_kit_root(
        studio_dir,
        config_dir,
        kit_slug,
    )
    if kit_root is None:
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "errors": [
                f"Kit '{kit_slug}' is registered at absolute path '{kit_root_rel}' which is not accessible on this OS",
            ],
        }
    # @cpt-end:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-read-root

    # @cpt-begin:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-foreach-resource
    for res in manifest.resources:
        # @cpt-begin:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-compute-path
        expected_path = kit_root / res.default_path
        # @cpt-end:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-compute-path

        # @cpt-begin:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-register-existing
        if expected_path.exists():
            # File/directory already on disk — register silently
            binding_path = _serialize_manifest_binding_path(expected_path, studio_dir)
            resource_bindings[res.id] = _manifest_resource_binding_entry(res=res, path=binding_path)
            migrated_count += 1
            continue
        # @cpt-end:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-register-existing

        # @cpt-begin:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-prompt-new
        # Truly new resource — copy from source and register
        target_abs = expected_path
        if interactive and res.user_modifiable and sys.stdin.isatty():
            try:
                user_input = input(
                    "Why this input is needed: choose where this resource should be installed.\n"
                    "Press Enter to accept the suggested path, or type a different absolute path or a path relative to the kit root.\n"
                    "Suggested: keep the default unless this resource must live somewhere else in your project.\n"
                    f"New resource '{res.id}' path [{expected_path}]: "
                ).strip()
                if user_input:
                    user_path = Path(user_input)
                    if user_path.is_absolute():
                        target_abs = user_path
                    else:
                        target_abs = (kit_root / user_path).resolve()
            except (EOFError, KeyboardInterrupt):
                pass

        _copy_manifest_resource(kit_source, res, target_abs)
        binding_path = _serialize_manifest_binding_path(target_abs, studio_dir)
        resource_bindings[res.id] = _manifest_resource_binding_entry(res=res, path=binding_path)
        new_count += 1
    # @cpt-end:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-prompt-new
    # @cpt-end:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-foreach-resource

    # @cpt-begin:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-write-bindings
    # Write all resource bindings to core.toml [kits.{slug}.resources]
    registration_errors = _register_kit_in_core_toml(
        config_dir, kit_slug, "", studio_dir,
        resources=resource_bindings,
        kit_path=_resolve_manifest_kit_root_rel(manifest, resource_bindings, kit_slug),
        tool_risk_fingerprint=str(getattr(manifest, "tool_risk_fingerprint", "") or ""),
    )
    if registration_errors:
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "errors": registration_errors,
        }
    _preserve_template_variables(kit_root, resource_bindings)
    # @cpt-end:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-write-bindings

    # @cpt-begin:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-return
    return {
        "status": "PASS",
        "kit": kit_slug,
        "migrated_count": migrated_count,
        "new_count": new_count,
        "resource_bindings": {k: v["path"] for k, v in resource_bindings.items()},
    }
    # @cpt-end:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-return


# ---------------------------------------------------------------------------
# Kit Install CLI
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-resolve-github-source
def _resolve_install_source_github(
    source_arg: str,
    requested_ref: str = "",
) -> Optional[Tuple[Path, str, str, str, Optional[Path], Optional[int], Optional[Dict[str, Any]]]]:
    """Parse and download a GitHub kit source for ``cmd_kit_install``.

    Returns ``(kit_source, kit_slug, kit_version, github_source, tmp_dir, None)``
    on success, or a tuple whose last element is a non-zero exit code on failure.
    Returns ``None`` if source parsing fails (caller should return 2).
    """
    try:
        owner, repo, version = _parse_github_source(source_arg)
    except ValueError as exc:
        ui.result({
            "status": "FAIL",
            "message": str(exc),
            "hint": "Expected format: owner/repo or owner/repo@version",
        })
        return None

    ui.step(f"Downloading {owner}/{repo}" + (f"@{version}" if version else " (latest)") + "...")
    try:
        kit_source, resolved_version, authority_metadata = _download_kit_from_github_with_authority(
            owner,
            repo,
            requested_ref or version,
        )
    except RuntimeError as exc:
        ui.result({"status": "FAIL", "message": str(exc)})
        return (Path("."), "", "", "", None, 1, None)

    kit_slug = _read_kit_slug(kit_source)
    if not kit_slug and not _has_canonical_kit_models(kit_source):
        ui.result({"status": "FAIL", "message": f"Kit at {kit_source} is missing manifest.toml; cannot resolve slug."})
        return (Path("."), "", "", "", kit_source.parent, 1, None)
    kit_version = resolved_version
    github_source = f"github:{owner}/{repo}"
    ui.substep(f"Resolved: {(kit_slug or '(select kit)')}@{kit_version or '(dev)'}")
    return (kit_source, kit_slug, kit_version, github_source, kit_source.parent, None, authority_metadata)
# @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-resolve-github-source


def _resolve_install_source_git(
    source_arg: str,
    requested_ref: str = "",
) -> Optional[Tuple[Path, str, str, str, Optional[Path], Optional[int], Optional[Dict[str, Any]]]]:
    """Parse and materialize a generic Git kit source for ``cmd_kit_install``."""
    try:
        parsed = parse_git_kit_source(source_arg)
        resolution = materialize_git_kit_source(parsed, requested_ref=requested_ref)
    except GitSourceError as exc:
        ui.result({
            "status": "FAIL",
            "message": str(exc),
            **exc.to_result(),
        })
        return None
    except RuntimeError as exc:
        ui.result({"status": "FAIL", "message": f"Git source resolution failed: {exc}"})
        return (Path("."), "", "", "", None, 1, None)

    kit_source = resolution.kit_source_dir
    resolved_slug = _read_kit_slug(kit_source)
    kit_slug = parsed.kit_identity or resolved_slug
    if not kit_slug and not _has_canonical_kit_models(kit_source):
        ui.result({"status": "FAIL", "message": f"Kit at {kit_source} is missing conf.toml slug."})
        shutil.rmtree(resolution.tmp_dir, ignore_errors=True)
        return (Path("."), "", "", "", None, 1, None)
    if parsed.kit_identity and resolved_slug not in ("", parsed.kit_identity):
        ui.result({
            "status": "FAIL",
            "message": f"Git source selected kit '{parsed.kit_identity}' but package slug is '{resolved_slug}'",
        })
        shutil.rmtree(resolution.tmp_dir, ignore_errors=True)
        return (Path("."), "", "", "", None, 1, None)
    kit_version = str(resolution.authority_metadata.get("installed_version") or "")
    ui.substep(f"Resolved: {(kit_slug or '(select kit)')}@{kit_version[:12] or '(git)'}")
    return (
        kit_source,
        kit_slug,
        kit_version,
        parsed.canonical_source,
        resolution.tmp_dir,
        None,
        resolution.authority_metadata,
    )


# @cpt-flow:cpt-studio-flow-kit-install-cli:p1
def cmd_kit_install(argv: List[str]) -> int:
    """Install a kit from GitHub or a local path.

    Delegates to install_kit() for the actual work, then regenerates
    .gen/ aggregates.

    Usage:
        cfs kit install owner/repo[@version]                          (GitHub)
        cfs kit install git/<url>[//<subdir>][@<kit>]                 (generic Git)
        cfs kit install path/<dir>                                    (local directory)
        cfs kit install --path /local/dir                             (local directory)
    """
    # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-parse-args
    p = argparse.ArgumentParser(
        prog="kit install",
        description="Install a kit package from GitHub or a local directory",
    )
    p.add_argument(
        "source", nargs="?", default=None,
        help="GitHub owner/repo[@version], generic Git git/<url>[//<subdir>][@<kit>], or local path/<dir>",
    )
    p.add_argument(
        "--path", dest="local_path", default=None,
        help="Install from a local directory instead of GitHub",
    )
    p.add_argument(
        "--version", dest="version", default="",
        help="For GitHub and generic Git sources, resolve this tag, branch, or full 40-character commit SHA",
    )
    p.add_argument(
        "--install-mode",
        choices=("copy", "register"),
        default="",
        help="For local manifest installs, choose copy into Studio storage or register in place",
    )
    p.add_argument(
        "--kit",
        action="append",
        default=[],
        metavar="SLUG",
        help="Select a kit from a multi-kit .cf-studio-kit.toml; repeat, use comma-separated slugs, or use 'all'",
    )
    p.add_argument(
        "--approve-overwrite",
        action="append",
        default=[],
        metavar="RESOURCE_OR_PATH",
        help="Approve overwriting one changed user-modifiable manifest resource by id or effective path; repeat per resource",
    )
    p.add_argument(
        "--approve-tool-risk",
        action="append",
        default=[],
        metavar="FINGERPRINT",
        help="Approve one dangerous tool-risk fingerprint; repeat when needed",
    )
    p.add_argument("--force", action="store_true", help="Overwrite existing kit")
    p.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = p.parse_args(argv)

    args.source, args.local_path, local_path_error = _normalize_local_path_source_arg(
        source_value=args.source,
        local_path=args.local_path,
        arg_name="source",
    )
    if local_path_error:
        ui.result(local_path_error)
        return 2

    if not args.source and not args.local_path:
        p.error("Provide a GitHub source (owner/repo) or --path for a local directory")
    if args.source and args.local_path:
        p.error("Cannot use both positional source and --path")
    # @cpt-begin:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-register-local-only
    if args.install_mode and not args.local_path:
        ui.result({
            "status": "FAIL",
            "message": "--install-mode is only valid with local --path installs",
            "hint": "Remote GitHub and generic Git installs always copy managed artifacts",
        })
        return 2
    # @cpt-end:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-register-local-only
    if args.local_path:
        # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-validate-source-mode
        conflict = _validate_kit_source_mode(
            local_path=args.local_path,
            version=args.version,
        )
        if conflict:
            ui.result(conflict)
            return 2
        # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-validate-source-mode
    # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-parse-args

    # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-validate-source
    source_registration = ""  # "github:owner/repo" or "git:<encoded-url>" for registration
    authority_metadata: Optional[Dict[str, Any]] = None
    tmp_dir_to_clean: Optional[Path] = None

    if args.local_path:
        # @cpt-begin:cpt-studio-algo-kit-manifest-normalize:p1:inst-rollout-path-install
        kit_source = Path(args.local_path).resolve()
        if not kit_source.is_dir():
            ui.result({
                "status": "FAIL",
                "message": f"Kit source directory not found: {kit_source}",
                "hint": "Provide a path to a valid kit directory",
            })
            return 2
        # @cpt-begin:cpt-studio-state-kit-install-mode:p1:inst-mode-required
        # @cpt-begin:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-mode-noninteractive-required
        if not args.dry_run and not args.install_mode and not sys.stdin.isatty():
            ui.result({
                "status": "FAIL",
                "message": "Non-interactive local installs require --install-mode copy|register",
                "hint": "Use --install-mode copy to copy resources into Studio storage, or --install-mode register for eligible in-project sources",
            })
            return 2
        # @cpt-end:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-mode-noninteractive-required
        # @cpt-end:cpt-studio-state-kit-install-mode:p1:inst-mode-required
        # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-load-kit-model
        # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-read-slug-version
        kit_slug = _read_kit_slug(kit_source) or kit_source.name
        kit_version = _read_kit_source_version(kit_source)
        # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-read-slug-version
        # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-load-kit-model
        # @cpt-end:cpt-studio-algo-kit-manifest-normalize:p1:inst-rollout-path-install
    else:
        if source_is_generic_git(args.source):
            resolved_source = _resolve_install_source_git(args.source, args.version)
        else:
            # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-resolve-github-authority
            resolved_source = _resolve_install_source_github(args.source, args.version)
            # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-resolve-github-authority
        if resolved_source is None:
            return 2
        # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-read-slug-version
        kit_source, kit_slug, kit_version, source_registration, tmp_dir_to_clean, exit_code, authority_metadata = resolved_source
        # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-read-slug-version
        if exit_code is not None:
            if tmp_dir_to_clean:
                shutil.rmtree(tmp_dir_to_clean, ignore_errors=True)
            return exit_code

    effective_requested_kits = list(args.kit)
    if (
        not effective_requested_kits
        and authority_metadata
        and str(authority_metadata.get("kit_identity") or "").strip()
    ):
        effective_requested_kits = [str(authority_metadata.get("kit_identity") or "").strip()]

    selected_models, selection_error = _select_canonical_kit_models_for_install(
        kit_source,
        effective_requested_kits,
        interactive=sys.stdin.isatty(),
    )
    if selection_error is not None:
        ui.result(selection_error)
        return 2
    selected_specs: List[Tuple[str, str]] = [
        (str(model.slug), str(model.version or kit_version))
        for model in selected_models
    ]
    if selected_specs:
        kit_slug, kit_version = selected_specs[0]
    else:
        selected_specs = [(kit_slug, kit_version)]
    # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-validate-source

    try:
        # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-resolve-project
        resolved = _resolve_studio_dir()
        if resolved is None:
            return 1
        project_root, studio_dir = resolved
        config_dir = studio_dir / "config"

        # @cpt-begin:cpt-studio-state-kit-install-mode:p1:inst-mode-copy-or-register
        selected_install_mode = args.install_mode or "copy"
        # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-resolve-local-install-mode
        # @cpt-begin:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-mode-always-ask
        if args.local_path and not args.install_mode and sys.stdin.isatty():
            try:
                local_manifest = _load_manifest_install_adapter(kit_source, kit_slug=kit_slug)
            except (OSError, ValueError):
                local_manifest = None
            if local_manifest is not None:
                selected_install_mode = _prompt_local_manifest_install_mode(
                    project_root,
                    studio_dir,
                    kit_source,
                    kit_slug,
                    local_manifest,
                )
        # @cpt-end:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-mode-always-ask
        # @cpt-end:cpt-studio-state-kit-install-mode:p1:inst-mode-copy-or-register
        # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-resolve-local-install-mode
        # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-resolve-local-install-mode
        selected_tracking: Optional[str] = None
        if selected_install_mode != "register" and not args.dry_run and sys.stdin.isatty():
            selected_tracking = _prompt_git_tracking_for_installed_kit(
                config_dir / _KIT_CORE_TOML,
                kit_slug,
            )
        # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-resolve-local-install-mode

        if len(selected_specs) > 1:
            preflight_errors: List[str] = []
            dry_run_results: List[Dict[str, Any]] = []
            for selected_slug, selected_version in selected_specs:
                selected_dir, _, _, _ = _resolve_installed_kit_root(
                    studio_dir, config_dir, selected_slug,
                )
                if selected_dir is None:
                    preflight_errors.append(
                        f"Kit '{selected_slug}' is registered at an absolute path that is not accessible on this OS",
                    )
                    continue
                if selected_dir.exists() and not args.force:
                    preflight_errors.append(
                        f"Kit '{selected_slug}' is already installed at {selected_dir}",
                    )
                dry_run_results.append({
                    "kit": selected_slug,
                    "version": selected_version,
                    "target": selected_dir.as_posix(),
                })
            if preflight_errors:
                ui.result({
                    "status": "FAIL",
                    "message": "One or more selected kits cannot be installed",
                    "errors": preflight_errors,
                })
                return 2
            if args.dry_run:
                ui.result({
                    "status": "DRY_RUN",
                    "kits": dry_run_results,
                    "source": source_registration or kit_source.as_posix(),
                })
                return 0

            results: List[Dict[str, Any]] = []
            failed = False
            for selected_slug, selected_version in selected_specs:
                result = install_kit(
                    kit_source,
                    studio_dir,
                    selected_slug,
                    selected_version,
                    source=source_registration,
                    interactive=True,
                    install_mode=selected_install_mode,
                    project_root=project_root,
                    authority_metadata=authority_metadata,
                    approved_overwrites=args.approve_overwrite,
                    approved_tool_risks=args.approve_tool_risk,
                )
                if str(result.get("status", "")).upper() == "FAIL":
                    failed = True
                # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-delegate-install
                elif selected_tracking is not None:
                    _persist_installed_kit_tracking(project_root, studio_dir, selected_slug, selected_tracking)
                # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-delegate-install
                results.append({
                    "status": result.get("status", "PASS"),
                    "action": result.get("action", "installed"),
                    "kit": selected_slug,
                    "version": selected_version,
                    "install_mode": result.get("install_mode", selected_install_mode),
                    "files_written": result.get("files_copied", 0),
                    "files_registered": result.get("files_registered", 0),
                    "errors": result.get("errors", []),
                })
            if not failed:
                regenerate_gen_aggregates(studio_dir)
            ui.result({
                "status": "FAIL" if failed else "PASS",
                "action": "installed",
                "kits_installed": 0 if failed else len(results),
                "results": results,
                "source": source_registration or kit_source.as_posix(),
            })
            return 2 if failed else 0

        config_kit_dir, _, _, _ = _resolve_installed_kit_root(
            studio_dir, config_dir, kit_slug,
        )
        if config_kit_dir is None:
            ui.result(
                {
                    "status": "FAIL",
                    "kit": kit_slug,
                    "message": f"Kit '{kit_slug}' is registered at an absolute path that is not accessible on this OS",
                },
                human_fn=_human_kit_install,
            )
            return 2
        # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-resolve-project

        # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-check-existing
        if config_kit_dir.exists() and not args.force:
            ui.result(
                {
                    "status": "FAIL",
                    "kit": kit_slug,
                    "message": f"Kit '{kit_slug}' is already installed at {config_kit_dir}",
                    "hint": f"Use 'cfs kit update' to update, or 'cfs kit install {args.source or args.local_path} --force' to reinstall",
                },
                human_fn=_human_kit_install,
            )
            return 2
        # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-check-existing

        # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-dry-run
        if args.dry_run:
            ui.result({
                "status": "DRY_RUN",
                "kit": kit_slug,
                "version": kit_version,
                "source": source_registration or kit_source.as_posix(),
                "target": config_kit_dir.as_posix(),
            })
            return 0
        # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-dry-run

        # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-delegate-install
        result = install_kit(
            kit_source,
            studio_dir,
            kit_slug,
            kit_version,
            source=source_registration,
            interactive=True,
            install_mode=selected_install_mode,
            project_root=project_root,
            authority_metadata=authority_metadata,
            approved_overwrites=args.approve_overwrite,
            approved_tool_risks=args.approve_tool_risk,
        )
        # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-delegate-install
        # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-delegate-install
        if str(result.get("status", "")).upper() != "FAIL" and selected_tracking is not None:
            _persist_installed_kit_tracking(project_root, studio_dir, kit_slug, selected_tracking)
        # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-delegate-install

        if str(result.get("status", "")).upper() == "FAIL":
            output = {
                "status": result.get("status", "FAIL"),
                "action": result.get("action", "installed"),
                "kit": kit_slug,
                "version": kit_version,
                "install_mode": result.get("install_mode", selected_install_mode),
                "files_written": result.get("files_copied", 0),
            }
            if result.get("files_registered") is not None:
                output["files_registered"] = result.get("files_registered", 0)
            if result.get("errors"):
                output["errors"] = result["errors"]
            ui.result(output, human_fn=_human_kit_install)
            return 2

        # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-regen-gen
        regenerate_gen_aggregates(studio_dir)
        # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-regen-gen

        # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-output-result
        output: Dict[str, Any] = {
            "status": result["status"],
            "action": result.get("action", "installed"),
            "kit": kit_slug,
            "version": kit_version,
            "install_mode": result.get("install_mode", selected_install_mode),
            "files_written": result.get("files_copied", 0),
        }
        if result.get("files_registered") is not None:
            output["files_registered"] = result.get("files_registered", 0)
        if source_registration:
            output["source"] = source_registration
        if authority_metadata:
            output["authority"] = _authority_result_summary(authority_metadata) or authority_metadata
        if result.get("local_metadata"):
            output["local_metadata"] = result["local_metadata"]
        if result.get("errors"):
            output["errors"] = result["errors"]

        ui.result(output, human_fn=_human_kit_install)
        return 0
        # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-output-result

    finally:
        # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-cleanup-tmp
        if tmp_dir_to_clean:
            shutil.rmtree(tmp_dir_to_clean, ignore_errors=True)
        # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-cleanup-tmp

# @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-human-output
def _human_kit_install(data: dict) -> None:
    status = data.get("status", "")
    kit_slug = data.get("kit", "?")
    version = data.get("version", "?")
    action = data.get("action", "installed")

    ui.header("Kit Install")
    ui.detail("Kit", kit_slug)
    ui.detail("Version", str(version))
    ui.detail("Action", action)

    if status == "DRY_RUN":
        ui.detail("Source", data.get("source", "?"))
        ui.detail("Target", data.get("target", "?"))
        ui.success("Dry run — no files written.")
        ui.blank()
        return

    fw = data.get("files_written", 0)
    kinds = data.get("artifact_kinds", [])
    ui.detail("Files written", str(fw))
    if kinds:
        ui.detail("Artifact kinds", ", ".join(kinds))

    errs = data.get("errors", [])
    if errs:
        ui.blank()
        for e in errs:
            ui.warn(str(e))

    if status == "PASS":
        ui.success(f"Kit '{kit_slug}' installed.")
    elif status == "FAIL":
        msg = data.get("message", "")
        hint = data.get("hint", "")
        ui.error(msg or "Install failed.")
        if hint:
            ui.hint(hint)
    else:
        ui.info(f"Status: {status}")
    ui.blank()
# @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-human-output

# ---------------------------------------------------------------------------
# Kit Update
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-resolve-github-targets
def _resolve_github_update_targets(
    kits_map: Dict[str, Dict[str, Any]],
) -> Tuple[List[Tuple[str, Path, str, Optional[Path], Optional[Dict[str, Any]]]], List[Dict[str, Any]]]:
    """Download GitHub kit sources and return update targets list.

    For each kit with a ``github:`` source, downloads the tarball and appends
    ``(slug, source_dir, source_str, tmp_dir)`` to the result list.
    Kits with missing or unsupported sources emit warnings and are recorded
    as structured failures.

    Returns:
        Tuple of (targets, failures) where failures are dicts with
        kit, action="ERROR", message, and optionally source.
    """
    targets: List[Tuple[str, Path, str, Optional[Path], Optional[Dict[str, Any]]]] = []
    failures: List[Dict[str, Any]] = []
    for slug, kit_data in kits_map.items():
        source_str = kit_data.get("source", "")
        if not source_str:
            msg = f"Kit '{slug}' has no registered source — skipping"
            ui.warn(msg)
            failures.append({"kit": slug, "action": "ERROR", "message": msg})
            continue
        if not source_str.startswith("github:"):
            msg = f"Kit '{slug}': unsupported source type '{source_str}' — skipping"
            ui.warn(msg)
            failures.append({"kit": slug, "action": "ERROR", "message": msg, "source": source_str})
            continue

        owner_repo = source_str.removeprefix("github:")
        try:
            owner, repo, version = _parse_github_source(owner_repo)
        except ValueError as exc:
            msg = f"Kit '{slug}': invalid source '{source_str}': {exc}"
            ui.warn(msg)
            failures.append({"kit": slug, "action": "ERROR", "message": msg, "source": source_str})
            continue

        ui.step(f"Downloading {owner}/{repo}...")
        try:
            kit_source_dir, _resolved, authority_metadata = _download_kit_from_github_with_authority(
                owner,
                repo,
                version,
                previous_entry=kit_data,
            )
            targets.append((slug, kit_source_dir, source_str, kit_source_dir.parent, authority_metadata))
        except RuntimeError as exc:
            msg = f"Kit '{slug}': download failed: {exc}"
            ui.warn(msg)
            try:
                authority_metadata = _resolve_github_ref(
                    owner,
                    repo,
                    version,
                    previous_entry=kit_data,
                )
            except RuntimeError:
                authority_metadata = None
            if authority_metadata and authority_metadata.get("freshness") == "last_known":
                current_version = str(kit_data.get("version") or "")
                last_known_ref = str(authority_metadata.get("resolved_ref") or "")
                if current_version and current_version == last_known_ref:
                    msg = (
                        f"Kit '{slug}': GitHub unavailable; installed version "
                        f"{current_version} matches last-known release authority"
                    )
                    ui.warn(msg)
                    failures.append({
                        "kit": slug,
                        "action": "current",
                        "message": msg,
                        "source": source_str,
                        "authority": authority_metadata,
                    })
                    continue
            failures.append({"kit": slug, "action": "failed", "message": msg, "source": source_str})
    return targets, failures
# @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-resolve-github-targets


def _resolve_registered_update_targets(
    kits_map: Dict[str, Dict[str, Any]],
    *,
    requested_ref_override: str = "",
) -> Tuple[List[Tuple[str, Path, str, Optional[Path], Optional[Dict[str, Any]]]], List[Dict[str, Any]]]:
    """Resolve registered kit update targets across supported source types."""
    # @cpt-begin:cpt-studio-algo-kit-update:p1:inst-read-source-version
    github_map: Dict[str, Dict[str, Any]] = {}
    targets: List[Tuple[str, Path, str, Optional[Path], Optional[Dict[str, Any]]]] = []
    failures: List[Dict[str, Any]] = []
    for slug, kit_data in kits_map.items():
        source_str = kit_data.get("source", "")
        if source_str.startswith("github:"):
            github_map[slug] = kit_data
            continue
        if not source_str.startswith("git:"):
            if not source_str:
                install_mode = str(kit_data.get("install_mode") or "").strip().lower()
                if install_mode == "register":
                    msg = f"Kit '{slug}' is registered in place and has no remote source — current"
                    ui.warn(msg)
                    failures.append({
                        "kit": slug,
                        "action": "current",
                        "message": msg,
                        "source": source_str,
                    })
                    continue
                msg = f"Kit '{slug}' has no registered source — skipping"
            else:
                msg = f"Kit '{slug}': unsupported source type '{source_str}' — skipping"
            ui.warn(msg)
            failures.append({"kit": slug, "action": "ERROR", "message": msg, "source": source_str})
            continue

        try:
            parsed = parse_git_kit_source(source_str)
            provenance = kit_data.get("source_provenance", {})
            requested_ref = requested_ref_override or str(
                provenance.get("requested_ref")
                if isinstance(provenance, dict)
                else ""
            )
            if requested_ref == "HEAD":
                requested_ref = ""
            resolution = materialize_git_kit_source(
                parsed,
                requested_ref=requested_ref,
                previous_metadata=kit_data,
            )
        except GitSourceError as exc:
            msg = f"Kit '{slug}': invalid Git source: {exc}"
            ui.warn(msg)
            failures.append({
                "kit": slug,
                "action": "ERROR",
                "message": msg,
                "source": source_str,
                **exc.to_result(),
            })
            continue
        except RuntimeError as exc:
            msg = f"Kit '{slug}': Git source resolution failed: {exc}"
            ui.warn(msg)
            failures.append({"kit": slug, "action": "failed", "message": msg, "source": source_str})
            continue
        targets.append((
            slug,
            resolution.kit_source_dir,
            parsed.canonical_source,
            resolution.tmp_dir,
            resolution.authority_metadata,
        ))

    if github_map:
        # @cpt-begin:cpt-studio-algo-kit-source-mode-validation:p1:inst-github-mode-authority
        github_targets, github_failures = _resolve_github_update_targets(github_map)
        targets.extend(github_targets)
        failures.extend(github_failures)
        # @cpt-end:cpt-studio-algo-kit-source-mode-validation:p1:inst-github-mode-authority
    return targets, failures
    # @cpt-end:cpt-studio-algo-kit-update:p1:inst-read-source-version


def _kit_installed_resolved_ref(kit_data: Dict[str, Any]) -> str:
    # @cpt-begin:cpt-studio-algo-kit-update:p1:inst-read-source-version
    provenance = kit_data.get("source_provenance", {})
    if isinstance(provenance, dict):
        resolved_ref = str(provenance.get("resolved_ref") or "")
        if resolved_ref:
            return resolved_ref
    return str(kit_data.get("version") or "")
    # @cpt-end:cpt-studio-algo-kit-update:p1:inst-read-source-version


def _kit_installed_commit_sha(kit_data: Dict[str, Any]) -> str:
    # @cpt-begin:cpt-studio-algo-kit-update:p1:inst-read-source-version
    provenance = kit_data.get("source_provenance", {})
    if isinstance(provenance, dict):
        return str(provenance.get("commit_sha") or "")
    return str(kit_data.get("commit_sha") or "")
    # @cpt-end:cpt-studio-algo-kit-update:p1:inst-read-source-version


def _kit_update_check_result(
    slug: str,
    kit_data: Dict[str, Any],
    authority_metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a non-mutating update-check result from resolved authority metadata."""
    # @cpt-begin:cpt-studio-algo-kit-update:p1:inst-version-check
    authority = _authority_result_summary(authority_metadata) or authority_metadata or {}
    source_type = str(authority.get("source_type") or "")
    result: Dict[str, Any] = {
        "kit": slug,
        "action": "current",
        "source": kit_data.get("source", ""),
        "command": f"cfs kit update {slug}",
    }
    if authority:
        result["authority"] = authority

    if source_type == "github":
        installed_ref = _kit_installed_resolved_ref(kit_data)
        installed_commit = _kit_installed_commit_sha(kit_data)
        latest_ref = str(authority.get("resolved_ref") or "")
        latest_commit = str(authority.get("commit_sha") or "")
        result["installed_ref"] = installed_ref
        result["latest_ref"] = latest_ref
        result["installed_commit"] = installed_commit
        result["latest_commit"] = latest_commit
        ref_changed = bool(installed_ref and latest_ref and installed_ref != latest_ref)
        commit_changed = bool(
            installed_commit and latest_commit and installed_commit != latest_commit
        )
        if ref_changed or commit_changed:
            result["action"] = "update_available"
        return result

    if source_type == "git":
        installed_commit = _kit_installed_commit_sha(kit_data)
        latest_commit = str(authority.get("commit_sha") or authority.get("resolved_ref") or "")
        result["installed_commit"] = installed_commit
        result["latest_commit"] = latest_commit
        if installed_commit and latest_commit and installed_commit != latest_commit:
            result["action"] = "update_available"
        return result

    result["action"] = "failed"
    result["message"] = "No comparable source authority metadata"
    return result
    # @cpt-end:cpt-studio-algo-kit-update:p1:inst-version-check


def _check_registered_kit_updates(
    kits_map: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Check remote kit authorities without writing installed kit files."""
    # @cpt-begin:cpt-studio-algo-kit-update:p1:inst-version-check
    update_targets, source_failures = _resolve_registered_update_targets(kits_map)
    results: List[Dict[str, Any]] = []
    for failure in source_failures:
        result = {
            "kit": failure.get("kit", ""),
            "action": _normalize_kit_update_action(failure.get("action")) or "failed",
            "source": failure.get("source", ""),
            "message": failure.get("message", ""),
        }
        if failure.get("authority"):
            result["authority"] = _authority_result_summary(failure.get("authority")) or failure["authority"]
        results.append(result)

    for update_target in update_targets:
        if len(update_target) == 4:
            slug, _kit_source, _source, tmp_dir = update_target
            authority_metadata = None
        else:
            slug, _kit_source, _source, tmp_dir, authority_metadata = update_target
        try:
            results.append(_kit_update_check_result(
                slug,
                kits_map.get(slug, {}),
                authority_metadata,
            ))
        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)
    return results, source_failures
    # @cpt-end:cpt-studio-algo-kit-update:p1:inst-version-check


# @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-build-update-result
def _normalize_kit_update_action(action: Any) -> str:
    normalized = str(action or "").strip().lower()
    if normalized in {"error", "fail", "failed"}:
        return "failed"
    return normalized


def _build_kit_update_result(kit_slug: str, kit_r: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a normalised result entry from update_kit() output."""
    ver = kit_r.get("version", {})
    ver_status = _normalize_kit_update_action(
        ver.get("status", "") if isinstance(ver, dict) else str(ver),
    )
    gen = kit_r.get("gen", {})
    accepted = gen.get("accepted_files", []) if isinstance(gen, dict) else []
    declined = kit_r.get("gen_rejected", [])
    files_written = gen.get("files_written", 0) if isinstance(gen, dict) else 0
    unchanged = gen.get("unchanged", 0) if isinstance(gen, dict) else 0
    result = {
        "kit": kit_slug,
        "action": ver_status,
        "accepted": accepted,
        "declined": declined,
        "files_written": files_written,
        "unchanged": unchanged,
    }
    if kit_r.get("errors"):
        result["errors"] = list(kit_r.get("errors", []))
    if kit_r.get("authority"):
        result["authority"] = kit_r["authority"]
    if kit_r.get("prune_required"):
        result["prune_required"] = list(kit_r.get("prune_required", []))
    return result
# @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-build-update-result


# @cpt-flow:cpt-studio-flow-kit-update-cli:p1
def cmd_kit_update(argv: List[str]) -> int:
    """Update installed kits from their registered sources or a local path.

    Without arguments, updates all installed kits that have a registered
    source in core.toml.  With a slug, updates only that kit.
    With --path, updates from a local directory.

    Usage:
        cfs kit update                          (all kits from sources)
        cfs kit update sdlc                     (specific kit from source)
        cfs kit update path/<dir>               (from local directory)
        cfs kit update --path /local/dir        (from local directory)
    """
    # @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-parse-args
    p = argparse.ArgumentParser(
        prog="kit update",
        description="Update installed kits from GitHub sources or a local directory",
    )
    p.add_argument(
        "slug", nargs="?", default=None,
        help="Kit slug to update, or local directory alias path/<dir> (default: all installed kits)",
    )
    p.add_argument(
        "--path", dest="local_path", default=None,
        help="Update from a local directory instead of registered source",
    )
    p.add_argument("--project-root", default=None, help="Project root directory")
    p.add_argument("--force", action="store_true",
                   help="Skip version check and force update")
    p.add_argument(
        "--version", dest="version", default="",
        help="For generic Git sources, resolve this tag, branch, or full 40-character commit SHA",
    )
    p.add_argument("--dry-run", action="store_true", help="Show what would be done")
    p.add_argument("--no-interactive", action="store_true",
                   help="Disable interactive prompts (auto-decline changes)")
    p.add_argument("-y", "--yes", action="store_true",
                   help="Auto-approve all prompts (no interaction)")
    p.add_argument(
        "--approve-overwrite",
        action="append",
        default=[],
        metavar="RESOURCE_OR_PATH",
        help="Approve overwriting one changed user-modifiable manifest resource by id or effective path; repeat per resource",
    )
    p.add_argument(
        "--approve-tool-risk",
        action="append",
        default=[],
        metavar="FINGERPRINT",
        help="Approve one dangerous tool-risk fingerprint; repeat when needed",
    )
    p.add_argument(
        "--prune",
        action="store_true",
        help="Allow explicit pruning of manifest-bound resources removed upstream",
    )
    p.add_argument(
        "--approve-prune",
        action="append",
        default=[],
        metavar="FINGERPRINT",
        help="Approve one manifest-bound resource deletion by prune fingerprint; repeat per path",
    )
    args = p.parse_args(argv)
    args.slug, args.local_path, local_path_error = _normalize_local_path_source_arg(
        source_value=args.slug,
        local_path=args.local_path,
        arg_name="slug",
    )
    if local_path_error:
        ui.result(local_path_error)
        return 2
    if args.local_path:
        conflict = _validate_kit_source_mode(
            local_path=args.local_path,
            version=args.version,
        )
        if conflict:
            ui.result(conflict)
            return 2
    # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-parse-args

    # @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-resolve-project
    project_root_arg = Path(args.project_root) if args.project_root else None
    resolved = _resolve_studio_dir(project_root_arg)
    if resolved is None:
        return 1
    project_root, studio_dir = resolved
    config_dir = studio_dir / "config"
    # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-resolve-project

    interactive = not args.no_interactive and sys.stdin.isatty()

    # @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-validate-source
    # Build list of (slug, source_dir, github_source, tmp_dir) to update
    update_targets: List[Tuple[str, Path, str, Optional[Path], Optional[Dict[str, Any]]]] = []
    source_failures: List[Dict[str, Any]] = []

    if args.local_path:
        kit_source = Path(args.local_path).resolve()
        if not kit_source.is_dir():
            ui.result({
                "status": "FAIL",
                "message": f"Kit source directory not found: {kit_source}",
                "hint": "Provide a path to a valid kit directory",
            })
            return 2
        # @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-read-slug
        kit_slug = (
            args.slug
            or _registered_slug_for_local_kit_path(config_dir, studio_dir, kit_source)
            or _read_kit_slug(kit_source)
            or kit_source.name
        )
        # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-read-slug
        update_targets.append((kit_slug, kit_source, "", None, None))
    else:
        kits_map = _read_kits_from_core_toml(config_dir)
        if not kits_map:
            ui.result({
                "status": "FAIL",
                "message": "No kits registered in core.toml",
                "hint": "Install a kit first: cfs kit install owner/repo",
            })
            return 2

        if args.slug:
            if args.slug not in kits_map:
                ui.result({
                    "status": "FAIL",
                    "message": f"Kit '{args.slug}' not found in core.toml",
                    "hint": f"Registered kits: {', '.join(kits_map.keys())}",
                })
                return 2
            kits_map = {args.slug: kits_map[args.slug]}

        update_targets, source_failures = _resolve_registered_update_targets(
            kits_map,
            requested_ref_override=args.version,
        )
        if not update_targets:
            source_failure_actions = {
                _normalize_kit_update_action(sf.get("action"))
                for sf in source_failures
            }
            if source_failures and source_failure_actions <= {"current"}:
                current_results = []
                for sf in source_failures:
                    result = {
                        "kit": sf.get("kit", ""),
                        "action": "current",
                        "accepted": [],
                        "declined": [],
                        "files_written": 0,
                        "unchanged": 0,
                    }
                    if sf.get("authority"):
                        result["authority"] = _authority_result_summary(sf.get("authority")) or sf["authority"]
                    current_results.append(result)
                ui.result({
                    "status": "PASS",
                    "kits_updated": 0,
                    "results": current_results,
                    "message": "All kits are up to date",
                }, human_fn=_human_kit_update)
                return 0
            if source_failures:
                ui.result({
                    "status": "FAIL",
                    "message": "All kits failed source resolution",
                    "results": source_failures,
                    "errors": [f"{sf['kit']}: {sf['message']}" for sf in source_failures],
                })
            else:
                ui.result({
                    "status": "FAIL",
                    "message": "No kits to update (no valid sources found)",
                })
            return 2
    # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-validate-source

    # @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-delegate-update
    all_results: List[Dict[str, Any]] = []
    errors: List[str] = []

    for sf in source_failures:
        normalized_source_failure = dict(sf)
        normalized_source_failure["action"] = _normalize_kit_update_action(
            normalized_source_failure.get("action"),
        )
        all_results.append(normalized_source_failure)
        if normalized_source_failure["action"] != "current":
            errors.append(f"{sf['kit']}: {sf['message']}")

    for update_target in update_targets:
        if len(update_target) == 4:
            kit_slug, kit_source, github_source, tmp_dir = update_target
            authority_metadata = None
        else:
            kit_slug, kit_source, github_source, tmp_dir, authority_metadata = update_target
        # @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-show-whatsnew
        if not args.dry_run:
            installed_version = _read_kit_version_from_core(config_dir, kit_slug)
            ack = show_kit_whatsnew(
                kit_source,
                installed_version,
                kit_slug,
                interactive=interactive and not args.yes,
            )
            if not ack:
                all_results.append({
                    "kit": kit_slug,
                    "action": "aborted",
                    "accepted": [],
                    "declined": [],
                    "files_written": 0,
                })
                if tmp_dir:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                continue
        # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-show-whatsnew

        try:
            # @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-legacy-migration
            kit_r = update_kit(
                kit_slug, kit_source, studio_dir,
                dry_run=args.dry_run,
                interactive=interactive,
                auto_approve=args.yes,
                force=args.force,
                source=github_source,
                authority_metadata=authority_metadata,
                approved_overwrites=args.approve_overwrite,
                approved_tool_risks=args.approve_tool_risk,
                prune_mode=args.prune,
                approved_prunes=args.approve_prune,
                project_root=project_root,
            )
            # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-legacy-migration
        except Exception as exc:  # pylint: disable=broad-exception-caught  # per-kit safety net — must not crash the update loop
            kit_r = {"kit": kit_slug, "version": {"status": "failed"}, "gen": {}}
            errors.append(f"{kit_slug}: {exc}")
        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        if kit_r.get("errors"):
            errors.extend(f"{kit_slug}: {err}" for err in kit_r.get("errors", []))
        all_results.append(_build_kit_update_result(kit_slug, kit_r))
    # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-delegate-update

    # @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-regen-gen
    has_failed_updates = any(
        _normalize_kit_update_action(r.get("action")) == "failed"
        for r in all_results
    )
    if not args.dry_run and not has_failed_updates:
        regenerate_gen_aggregates(studio_dir)
    # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-regen-gen

    # @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-format-output
    n_updated = sum(
        1
        for r in all_results
        if _normalize_kit_update_action(r.get("action"))
        not in ("current", "dry_run", "aborted", "failed")
    )
    command_failed = has_failed_updates
    if command_failed:
        status = "FAIL"
    elif not errors:
        status = "PASS"
    else:
        status = "WARN"
    output: Dict[str, Any] = {
        "status": status,
        "kits_updated": n_updated,
        "results": all_results,
    }
    if errors:
        output["errors"] = errors
    if not n_updated and not errors:
        output["message"] = "All kits are up to date"

    ui.result(output, human_fn=_human_kit_update)
    return 2 if command_failed else 0
    # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-format-output

# @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-human-output
def _human_kit_update(data: dict) -> None:
    status = data.get("status", "")
    n = data.get("kits_updated", 0)

    ui.header("Kit Update")
    ui.detail("Kits updated", str(n))

    for r in data.get("results", []):
        kit_slug = r.get("kit", "?")
        action = r.get("action", "?")
        accepted = r.get("accepted", [])
        declined = r.get("declined", [])
        unchanged = r.get("unchanged", 0)
        parts = [f"{kit_slug}: {action}"]
        if accepted:
            parts.append(f"{len(accepted)} accepted")
        if declined:
            parts.append(f"{len(declined)} declined")
        if unchanged:
            parts.append(f"{unchanged} unchanged")
        ui.step("  ".join(parts))
        authority = r.get("authority", {})
        if isinstance(authority, dict) and authority:
            authority_parts = []
            basis = authority.get("resolution_basis") or authority.get("resolver_mode")
            resolved_ref = authority.get("resolved_ref")
            commit_sha = authority.get("commit_sha")
            freshness = authority.get("freshness")
            if basis:
                authority_parts.append(f"basis={basis}")
            if resolved_ref:
                authority_parts.append(f"ref={resolved_ref}")
            if commit_sha:
                authority_parts.append(f"commit={commit_sha}")
            if freshness:
                authority_parts.append(f"freshness={freshness}")
            if authority_parts:
                ui.substep("  authority: " + ", ".join(authority_parts))
        for fp in accepted:
            ui.substep(f"  ~ {fp}")
        for fp in declined:
            ui.substep(f"  ✗ {fp} (declined)")

    errs = data.get("errors", [])
    if errs:
        ui.blank()
        for e in errs:
            ui.warn(str(e))

    if status == "PASS":
        ui.success("Kit update complete.")
    elif status == "WARN":
        ui.warn("Kit update finished with warnings.")
    else:
        ui.info(f"Status: {status}")
    ui.blank()
# @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-human-output


def cmd_kit_check_updates(argv: List[str]) -> int:
    """Check registered git/GitHub kit sources for newer remote versions."""
    # @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-format-output
    p = argparse.ArgumentParser(
        prog="kit check-updates",
        description="Check registered git/GitHub kit sources for updates without writing files",
    )
    p.add_argument(
        "slug", nargs="?", default=None,
        help="Kit slug to check (default: all registered kits)",
    )
    p.add_argument("--project-root", default=None, help="Project root directory")
    args = p.parse_args(argv)

    project_root_arg = Path(args.project_root) if args.project_root else None
    resolved = _resolve_studio_dir(project_root_arg)
    if resolved is None:
        return 1
    _project_root, studio_dir = resolved
    config_dir = studio_dir / "config"

    kits_map = _read_kits_from_core_toml(config_dir)
    if not kits_map:
        ui.result({
            "status": "FAIL",
            "message": "No kits registered in core.toml",
            "hint": "Install a kit first: cfs kit install owner/repo",
        })
        return 2

    if args.slug:
        if args.slug not in kits_map:
            ui.result({
                "status": "FAIL",
                "message": f"Kit '{args.slug}' not found in core.toml",
                "hint": f"Registered kits: {', '.join(kits_map.keys())}",
            })
            return 2
        kits_map = {args.slug: kits_map[args.slug]}

    results, _failures = _check_registered_kit_updates(kits_map)
    updates = [r for r in results if r.get("action") == "update_available"]
    failures = [
        r for r in results
        if _normalize_kit_update_action(r.get("action")) == "failed"
    ]
    output: Dict[str, Any] = {
        "status": "WARN" if failures else "PASS",
        "updates_available": len(updates),
        "results": results,
    }
    if updates:
        output["commands"] = [r["command"] for r in updates if r.get("command")]
        output["message"] = "Kit updates available"
    else:
        output["message"] = "All checked kits are up to date"
    if failures:
        output["errors"] = [
            f"{r.get('kit')}: {r.get('message', 'update check failed')}"
            for r in failures
        ]
    ui.result(output, human_fn=_human_kit_check_updates)
    return 0
    # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-format-output


def _human_kit_check_updates(data: dict) -> None:
    # @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-human-output
    ui.header("Kit Update Check")
    ui.detail("Updates available", str(data.get("updates_available", 0)))

    for result in data.get("results", []):
        slug = result.get("kit", "?")
        action = result.get("action", "?")
        if action == "update_available":
            ui.step(f"{slug}: update available")
            installed_ref = result.get("installed_ref") or result.get("installed_commit")
            latest_ref = result.get("latest_ref") or result.get("latest_commit")
            if installed_ref or latest_ref:
                ui.substep(f"  installed={installed_ref or '?'} latest={latest_ref or '?'}")
            ui.hint(f"Run `{result.get('command')}`")
        elif _normalize_kit_update_action(action) == "failed":
            ui.warn(f"{slug}: {result.get('message', 'update check failed')}")
        else:
            ui.step(f"{slug}: up to date")

    if data.get("updates_available", 0):
        ui.warn("Kit updates are available.")
    elif data.get("status") == "PASS":
        ui.success("All checked kits are up to date.")
    ui.blank()
    # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-human-output

# ---------------------------------------------------------------------------
# Kit Normalize
# ---------------------------------------------------------------------------

# @cpt-flow:cpt-studio-flow-kit-normalize-cli:p1
def cmd_kit_normalize(argv: List[str]) -> int:
    """Generate a canonical .cf-studio-kit.toml from a kit source."""
    # @cpt-begin:cpt-studio-flow-kit-normalize-cli:p1:inst-normalize-parse-args
    p = argparse.ArgumentParser(
        prog="kit normalize",
        description="Generate a canonical .cf-studio-kit.toml from a kit source",
    )
    p.add_argument("path", help="Kit source directory to normalize")
    p.add_argument(
        "--from",
        dest="source_hint",
        choices=("manifest", "layout", "core"),
        default="",
        help="Limit normalization to a specific legacy source type",
    )
    p.add_argument(
        "--output",
        default="",
        help="Output path for .cf-studio-kit.toml (default: <path>/.cf-studio-kit.toml)",
    )
    p.add_argument("--dry-run", action="store_true", help="Print the generated manifest without writing it")
    p.add_argument("--stdout", action="store_true", help="Write only the generated canonical manifest TOML to stdout")
    args = p.parse_args(argv)
    if args.stdout and args.output:
        p.error("--stdout cannot be combined with --output")
    # @cpt-end:cpt-studio-flow-kit-normalize-cli:p1:inst-normalize-parse-args

    # @cpt-begin:cpt-studio-flow-kit-normalize-cli:p1:inst-normalize-validate-source
    kit_source = Path(args.path).resolve()
    if not kit_source.is_dir():
        ui.result({
            "status": "FAIL",
            "message": f"Kit source directory not found: {kit_source}",
            "hint": "Provide a path to a valid kit directory",
        })
        return 2
    output_path = Path(args.output).resolve() if args.output else kit_source / ".cf-studio-kit.toml"
    # @cpt-end:cpt-studio-flow-kit-normalize-cli:p1:inst-normalize-validate-source

    try:
        from ..utils.kit_model import normalize_kit_source

        # @cpt-begin:cpt-studio-flow-kit-normalize-cli:p1:inst-normalize-load-source
        model, manifest_text = normalize_kit_source(kit_source, args.source_hint)
        # @cpt-end:cpt-studio-flow-kit-normalize-cli:p1:inst-normalize-load-source
    except ValueError as exc:
        ui.result({
            "status": "FAIL",
            "message": str(exc),
        })
        return 2

    # @cpt-begin:cpt-studio-algo-kit-manifest-normalize:p1:inst-normalize-report-ambiguity
    report = _kit_normalize_report(model)
    # @cpt-end:cpt-studio-algo-kit-manifest-normalize:p1:inst-normalize-report-ambiguity

    if args.stdout:
        sys.stdout.write(manifest_text)
        if not manifest_text.endswith("\n"):
            sys.stdout.write("\n")
        return 0

    # @cpt-begin:cpt-studio-flow-kit-normalize-cli:p1:inst-normalize-dry-run
    if args.dry_run:
        ui.result({
            "status": "PASS",
            "action": "normalized",
            "dry_run": True,
            "kit": model.slug,
            "output": output_path.as_posix(),
            "report": report,
            "manifest": manifest_text,
        }, human_fn=_human_kit_normalize)
        return 0
    # @cpt-end:cpt-studio-flow-kit-normalize-cli:p1:inst-normalize-dry-run

    # @cpt-begin:cpt-studio-flow-kit-normalize-cli:p1:inst-normalize-write-output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(manifest_text, encoding="utf-8")
    ui.result({
        "status": "PASS",
        "action": "normalized",
        "dry_run": False,
        "kit": model.slug,
        "output": output_path.as_posix(),
        "report": report,
    }, human_fn=_human_kit_normalize)
    return 0
    # @cpt-end:cpt-studio-flow-kit-normalize-cli:p1:inst-normalize-write-output


def _kit_normalize_report(model: Any) -> Dict[str, Any]:
    """Build the migration report for normalized kit output."""
    def _subagent_previews(component: Any) -> List[Dict[str, str]]:
        previews: List[Dict[str, str]] = []
        for subagent in getattr(component, "subagents", []) or []:
            if not isinstance(subagent, dict):
                continue
            subagent_id = str(subagent.get("id", "") or "").strip()
            if not subagent_id:
                continue
            prefix_generated_name = bool(subagent.get("prefix_generated_name", True))
            if prefix_generated_name:
                prefix = f"cf-{model.slug}-"
                generated_name = subagent_id if subagent_id == f"cf-{model.slug}" or subagent_id.startswith(prefix) else f"{prefix}{subagent_id}"
            else:
                generated_name = subagent_id
            previews.append({
                "id": subagent_id,
                "kind": "subagent",
                "generated_name": generated_name,
                "name_mode": "prefixed" if prefix_generated_name and generated_name != subagent_id else "as_is",
            })
        return previews

    # @cpt-begin:cpt-studio-algo-kit-manifest-normalize:p1:inst-normalize-preserve-fields
    report = {
        "manifest_source": model.manifest_source,
        "resources": len(model.resources),
        "public_resources": len([r for r in model.resources if r.public]),
        # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-public-name-preview
        "public_components": [
            {
                "id": component.id,
                "kind": component.kind,
                "source": component.source,
                "generated_name": component.generated_name,
                "name_mode": "prefixed" if component.generated_name != component.id else "as_is",
                "generated_targets": component.generated_targets,
                "aliases": component.aliases,
                "origin": component.origin,
                "subagents": _subagent_previews(component),
            }
            for component in model.public_components
        ],
        # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-public-name-preview
        "warnings": list(model.warnings),
    }
    # @cpt-end:cpt-studio-algo-kit-manifest-normalize:p1:inst-normalize-preserve-fields
    return report


def _human_kit_normalize(data: dict) -> None:
    ui.header("Kit Normalize")
    ui.detail("Kit", str(data.get("kit", "?")))
    ui.detail("Output", str(data.get("output", "?")))
    report = data.get("report", {})
    if isinstance(report, dict):
        ui.detail("Source", str(report.get("manifest_source", "?")))
        ui.detail("Resources", str(report.get("resources", 0)))
        warnings = report.get("warnings", [])
        for warning in warnings if isinstance(warnings, list) else []:
            ui.warn(str(warning))
    if data.get("dry_run"):
        ui.success("Dry run - no files written.")
        manifest = str(data.get("manifest") or "")
        if manifest:
            ui.blank()
            ui.info("Generated .cf-studio-kit.toml preview:")
            sys.stderr.write(manifest)
            if not manifest.endswith("\n"):
                sys.stderr.write("\n")
    else:
        ui.success("Canonical manifest written.")
    ui.blank()

# ---------------------------------------------------------------------------
# Kit Migrate — conf.toml helpers
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-kit-config-helpers:p1:inst-read-conf-version
def _read_conf_version(conf_path: Path) -> int:
    """Read top-level 'version' from conf.toml. Returns 0 if missing."""
    if not conf_path.is_file():
        return 0
    try:
        with open(conf_path, "rb") as f:
            data = tomllib.load(f)
        ver = data.get("version")
        return int(ver) if ver is not None else 0
    except (OSError, ValueError):
        return 0
    # @cpt-end:cpt-studio-algo-kit-config-helpers:p1:inst-read-conf-version

# ---------------------------------------------------------------------------
# Layout migration — old (kits/ + .gen/kits/) → new (config/kits/ only, no kits/)
# @cpt-algo:cpt-studio-algo-version-config-layout-restructure:p1
# ---------------------------------------------------------------------------

_LEGACY_SKIP_NAMES = frozenset(("blueprints", "blueprint_hashes.toml", "__pycache__", ".prev"))


def _copy_legacy_kit_item(item: Path, dst: Path) -> None:
    if item.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(item, dst)
        return
    if not dst.exists():
        shutil.copy2(item, dst)


def _backup_existing_config_kit(config_kit: Path, kit_backup: Path) -> Path:
    config_backup = kit_backup / "config_kit"
    if config_backup.exists():
        shutil.rmtree(config_backup)
    if config_kit.is_dir():
        config_backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(config_kit, config_backup)
    return config_backup


def _restore_existing_config_kit(config_backup: Path, config_kit: Path) -> None:
    if config_kit.exists():
        shutil.rmtree(config_kit)
    if not config_backup.is_dir():
        return
    config_kit.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(config_backup), str(config_kit))


# @cpt-begin:cpt-studio-algo-version-config-layout-restructure:p1:inst-migrate-kits-entry
def _migrate_single_kits_dir_entry(
    kit_dir: Path,
    config_kits: Path,
    backup_dir: Path,
) -> str:
    """Copy one kits/{slug}/ entry into config/kits/{slug}/, with backup/rollback.

    Returns ``"migrated"`` on success or ``"FAILED: <msg>"`` on error.
    """
    slug = kit_dir.name
    config_kit = config_kits / slug
    kit_backup = backup_dir / slug / "kits_entry"
    config_backup = kit_backup / "config_kit"
    config_kit_tmp = config_kits / f".{slug}.tmp"

    try:
        _backup_existing_config_kit(config_kit, kit_backup)

        if config_kit_tmp.exists():
            shutil.rmtree(config_kit_tmp)
        config_kit_tmp.mkdir(parents=True, exist_ok=True)
        for item in kit_dir.iterdir():
            if item.name in _LEGACY_SKIP_NAMES:
                continue
            dst = config_kit_tmp / item.name
            _copy_legacy_kit_item(item, dst)
        if config_kit.exists():
            shutil.rmtree(config_kit)
        os.replace(config_kit_tmp, config_kit)
        return "migrated"
    except OSError as exc:
        if config_kit_tmp.exists():
            shutil.rmtree(config_kit_tmp, ignore_errors=True)
        _restore_existing_config_kit(config_backup, config_kit)
        return f"FAILED: {exc}"
# @cpt-end:cpt-studio-algo-version-config-layout-restructure:p1:inst-migrate-kits-entry


# @cpt-begin:cpt-studio-algo-version-config-layout-restructure:p1:inst-migrate-gen-entry
def _migrate_single_gen_kit_entry(gen_kit: Path, config_kits: Path, backup_dir: Path) -> str:
    """Copy one .gen/kits/{slug}/ entry into config/kits/{slug}/ (no-overwrite).

    Returns ``"migrated"`` on success or ``"FAILED: <msg>"`` on error.
    """
    slug = gen_kit.name
    config_kit = config_kits / slug
    kit_backup = backup_dir / slug / "gen_entry"
    config_backup = kit_backup / "config_kit"
    config_kit_tmp = config_kits / f".{slug}.gen.tmp"

    try:
        _backup_existing_config_kit(config_kit, kit_backup)

        if config_kit_tmp.exists():
            shutil.rmtree(config_kit_tmp)
        if config_kit.is_dir():
            shutil.copytree(config_kit, config_kit_tmp)
        else:
            config_kit_tmp.mkdir(parents=True, exist_ok=True)
        for item in gen_kit.iterdir():
            dst = config_kit_tmp / item.name
            if item.is_dir():
                if not dst.exists():
                    shutil.copytree(item, dst)
            elif not dst.exists():
                shutil.copy2(item, dst)
        if config_kit.exists():
            shutil.rmtree(config_kit)
        os.replace(config_kit_tmp, config_kit)
        return "migrated"
    except OSError as exc:
        if config_kit_tmp.exists():
            shutil.rmtree(config_kit_tmp, ignore_errors=True)
        _restore_existing_config_kit(config_backup, config_kit)
        return f"FAILED: {exc}"
# @cpt-end:cpt-studio-algo-version-config-layout-restructure:p1:inst-migrate-gen-entry


# @cpt-begin:cpt-studio-algo-version-config-layout-restructure:p1:inst-update-core-paths
def _update_core_toml_kit_paths(config_dir: Path) -> None:
    """Rewrite legacy .gen/kits/ and kits/ paths in core.toml to config/kits/."""
    core_toml = config_dir / _KIT_CORE_TOML
    if not core_toml.is_file():
        return
    with open(core_toml, "rb") as f:
        data = tomllib.load(f)
    kits_conf = data.get("kits", {})
    updated = False
    for kit_entry in kits_conf.values():
        if not isinstance(kit_entry, dict):
            continue
        old_path = kit_entry.get("path", "")
        if old_path.startswith(".gen/kits/") or old_path.startswith("kits/"):
            slug = old_path.rsplit("/", 1)[-1]
            kit_entry["path"] = f"config/kits/{slug}"
            updated = True
    if updated:
        from ..utils import toml_utils
        toml_utils.dump(data, core_toml, header_comment="Constructor Studio project configuration")
# @cpt-end:cpt-studio-algo-version-config-layout-restructure:p1:inst-update-core-paths


def _detect_and_migrate_layout(
    studio_dir: Path,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Detect old directory layout and migrate to the new flat model.

    Handles two legacy layouts:

    Layout A (oldest):
        config/kits/{slug}/blueprints/  — user blueprints
        .gen/kits/{slug}/               — generated outputs
        kits/{slug}/                    — reference copies

    Layout B (intermediate):
        kits/{slug}/blueprints/         — user blueprints
        kits/{slug}/conf.toml           — kit config
        config/kits/{slug}/             — generated outputs

    New layout (direct file packages):
        config/kits/{slug}/             — all kit content (no blueprints)
        (no kits/ directory)

    Migration merges non-blueprint content into config/kits/{slug}/,
    updates core.toml paths, then removes kits/ and .gen/kits/.

    Returns dict with migrated kit slugs or empty if no migration needed.
    """
    config_kits = studio_dir / "config" / "kits"
    gen_kits = studio_dir / ".gen" / "kits"
    kits_dir = studio_dir / "kits"

    # Detect: old layout exists when kits/ directory is present
    has_kits_dir = kits_dir.is_dir() and any(kits_dir.iterdir())
    has_gen_kits = gen_kits.is_dir() and any(gen_kits.iterdir())
    if not has_kits_dir and not has_gen_kits:
        return {}

    migrated: Dict[str, Any] = {}
    backup_dir = studio_dir / ".layout_backup"

    # ── Migrate kits/{slug}/ content into config/kits/{slug}/ ──────────
    # @cpt-begin:cpt-studio-algo-version-config-layout-restructure:p1:inst-layout-backup
    if has_kits_dir:
        for kit_dir in sorted(kits_dir.iterdir()):
            if not kit_dir.is_dir():
                continue
            slug = kit_dir.name
            if dry_run:
                migrated[slug] = "would_migrate"
                continue
            migrated[slug] = _migrate_single_kits_dir_entry(kit_dir, config_kits, backup_dir)
    # @cpt-end:cpt-studio-algo-version-config-layout-restructure:p1:inst-layout-backup

    # @cpt-begin:cpt-studio-algo-version-config-layout-restructure:p1:inst-layout-move-gen
    # ── Migrate .gen/kits/{slug}/ into config/kits/{slug}/ ─────────────
    if has_gen_kits:
        for gen_kit in sorted(gen_kits.iterdir()):
            if not gen_kit.is_dir():
                continue
            slug = gen_kit.name
            if dry_run:
                migrated.setdefault(slug, "would_migrate")
                continue
            result = _migrate_single_gen_kit_entry(gen_kit, config_kits, backup_dir)
            # Failure must override any earlier success for the same slug
            if isinstance(result, str) and result.startswith("FAILED"):
                migrated[slug] = result
            else:
                migrated.setdefault(slug, result)
    # @cpt-end:cpt-studio-algo-version-config-layout-restructure:p1:inst-layout-move-gen

    if dry_run:
        return migrated

    _finalize_layout_migration(migrated, studio_dir, kits_dir, gen_kits, backup_dir)
    return migrated


def _finalize_layout_migration(
    migrated: Dict[str, Any],
    studio_dir: Path,
    kits_dir: Path,
    gen_kits: Path,
    backup_dir: Path,
) -> None:
    """Post-migration cleanup: update core.toml, remove legacy dirs, clean backups."""
    # @cpt-begin:cpt-studio-algo-version-config-layout-restructure:p1:inst-layout-rollback
    has_failures = any(isinstance(s, str) and s.startswith("FAILED") for s in migrated.values())

    # @cpt-begin:cpt-studio-algo-version-config-layout-restructure:p1:inst-layout-update-core
    # ── Update core.toml kit paths (only when all migrations succeeded) ──
    if not has_failures:
        _update_core_toml_kit_paths(studio_dir / "config")
    # @cpt-end:cpt-studio-algo-version-config-layout-restructure:p1:inst-layout-update-core

    # @cpt-begin:cpt-studio-algo-version-config-layout-restructure:p1:inst-layout-remove-refs
    # ── Remove legacy directories (only when all migrations succeeded) ───
    if not has_failures and kits_dir.is_dir():
        shutil.rmtree(kits_dir)
    # @cpt-end:cpt-studio-algo-version-config-layout-restructure:p1:inst-layout-remove-refs

    # @cpt-begin:cpt-studio-algo-version-config-layout-restructure:p1:inst-layout-clean-gen
    if not has_failures and gen_kits.is_dir():
        shutil.rmtree(gen_kits, ignore_errors=True)
    # @cpt-end:cpt-studio-algo-version-config-layout-restructure:p1:inst-layout-clean-gen

    # Clean up backups for successful migrations; preserve failed ones
    if backup_dir.is_dir():
        for slug, status in migrated.items():
            kit_backup = backup_dir / slug
            if status == "migrated" and kit_backup.is_dir():
                shutil.rmtree(kit_backup, ignore_errors=True)
        try:
            backup_dir.rmdir()
        except OSError:
            pass
    # @cpt-end:cpt-studio-algo-version-config-layout-restructure:p1:inst-layout-rollback


# @cpt-begin:cpt-studio-algo-kit-update:p1:inst-perform-first-install
def _perform_first_install_kit(
    source_dir: Path,
    config_kit_dir: Path,
    config_dir: Path,
    kit_slug: str,
    source_version: str,
    studio_dir: Path,
    source: str = "",
    authority_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Copy kit content, seed configs, and register in core.toml for a first install.

    Returns a result dict matching the install_kit status shape.
    """
    copy_actions = _copy_kit_content(source_dir, config_kit_dir)
    scripts_dir = config_kit_dir / "scripts"
    if scripts_dir.is_dir():
        _seed_kit_config_files(scripts_dir, config_dir, {})
    local_metadata = {}
    src_conf = source_dir / _KIT_CONF_FILE
    if src_conf.is_file():
        conf_version = _read_kit_version(src_conf)
        if conf_version:
            local_metadata["conf_version"] = conf_version
    _register_kit_in_core_toml(
        config_dir,
        kit_slug,
        source_version,
        studio_dir,
        source=source,
        authority_metadata=authority_metadata,
        local_metadata=local_metadata or None,
    )
    return {
        "status": "PASS",
        "action": "installed",
        "kit": kit_slug,
        "version": source_version,
        "files_copied": sum(1 for v in copy_actions.values() if v == "copied"),
        "errors": [],
        "actions": copy_actions,
    }
# @cpt-end:cpt-studio-algo-kit-update:p1:inst-perform-first-install


def _resolve_manifest_root_from_binding(
    binding_path: Optional[str],
    default_path: str,
) -> Optional[str]:
    if not isinstance(binding_path, str) or not binding_path.strip():
        return None
    binding_parts = PurePosixPath(binding_path).parts
    default_parts = PurePosixPath(default_path).parts
    if len(binding_parts) < len(default_parts):
        return None
    if tuple(binding_parts[-len(default_parts):]) != tuple(default_parts):
        return None
    prefix_parts = binding_parts[:-len(default_parts)]
    if prefix_parts:
        return PurePosixPath(*prefix_parts).as_posix()
    return ""


def _resource_install_path(res: Any) -> str:
    return str(getattr(res, "install_path", getattr(res, "default_path", "")))


def _resolve_declared_manifest_root(manifest: Any, kit_slug: str) -> str:
    manifest_root = getattr(manifest, "root", "")
    if isinstance(manifest_root, str) and manifest_root.strip():
        resolved_root = manifest_root.replace("{cf-studio-path}", ".").replace("{slug}", kit_slug).strip()
        if resolved_root and resolved_root != ".":
            return PurePosixPath(resolved_root).as_posix()
    return f"config/kits/{kit_slug}"


def _resolve_manifest_kit_root_rel(
    manifest: Any,
    merged: Dict[str, Dict[str, str]],
    kit_slug: str,
) -> str:
    for res in getattr(manifest, "resources", []):
        binding = merged.get(res.id, {})
        binding_path = binding.get("path") if isinstance(binding, dict) else None
        binding_root = _resolve_manifest_root_from_binding(binding_path, _resource_install_path(res))
        if binding_root is not None:
            return binding_root

    return _resolve_declared_manifest_root(manifest, kit_slug)


# @cpt-begin:cpt-studio-algo-kit-update:p1:inst-sync-manifest-bindings
def _sync_manifest_resource_bindings(
    manifest: Any,
    config_dir: Path,
    kit_slug: str,
) -> Optional[Dict[str, Dict[str, Any]]]:
    """Merge existing resource bindings with any new manifest resources.

    Returns merged bindings dict, or None if there is no manifest.
    """
    if manifest is None:
        return None
    existing_raw = _read_kits_from_core_toml(config_dir).get(kit_slug, {}).get("resources", {})
    merged: Dict[str, Dict[str, Any]] = {}
    for res_id, binding in existing_raw.items():
        if isinstance(binding, dict):
            merged[res_id] = binding
        elif isinstance(binding, str):
            merged[res_id] = {"path": binding}
    kit_root_rel = _resolve_manifest_kit_root_rel(manifest, merged, kit_slug)
    for res in getattr(manifest, "resources", []):
        if res.id not in merged:
            install_path = _resource_install_path(res)
            if kit_root_rel:
                resource_path = (PurePosixPath(kit_root_rel) / install_path).as_posix()
            else:
                resource_path = PurePosixPath(install_path).as_posix()
            merged[res.id] = {"path": resource_path}
        kind = str(getattr(res, "kind", "") or "").strip()
        if kind:
            merged[res.id]["kind"] = kind
        merged[res.id]["public"] = bool(getattr(res, "public", False))
        artifact_bindings = getattr(res, "artifact_bindings", None)
        if isinstance(artifact_bindings, dict) and artifact_bindings:
            merged[res.id]["artifacts"] = artifact_bindings
        else:
            merged[res.id].pop("artifacts", None)
    return merged
# @cpt-end:cpt-studio-algo-kit-update:p1:inst-sync-manifest-bindings


def _project_root_from_core_toml(config_dir: Path, studio_dir: Path) -> Optional[Path]:
    core_toml = config_dir / _KIT_CORE_TOML
    if not core_toml.is_file():
        return None
    try:
        with open(core_toml, "rb") as f:
            data = tomllib.load(f)
    except (OSError, ValueError):
        return None
    raw_root = data.get("project_root")
    if not isinstance(raw_root, str) or not raw_root.strip():
        return None
    root_path = Path(raw_root)
    if root_path.is_absolute():
        return root_path.resolve()
    return (studio_dir / root_path).resolve()


# @cpt-dod:cpt-studio-dod-kit-update:p1
# @cpt-algo:cpt-studio-algo-kit-update:p1
def update_kit(
    kit_slug: str,
    source_dir: Path,
    studio_dir: Path,
    *,
    dry_run: bool = False,
    interactive: bool = True,
    auto_approve: bool = False,
    force: bool = False,
    source: str = "",
    authority_metadata: Optional[Dict[str, Any]] = None,
    approved_overwrites: Optional[List[str]] = None,
    approved_tool_risks: Optional[List[str]] = None,
    prune_mode: bool = False,
    approved_prunes: Optional[List[str]] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Full update cycle for a single kit.

    Kits are direct file packages.  On first install the kit content is
    copied wholesale.  On subsequent runs a file-level diff is shown and
    the user decides per-file.

    Args:
        kit_slug: Kit identifier (e.g. "sdlc").
        source_dir: New kit data (e.g. cache/kits/{slug}/ or local dir).
        studio_dir: Project adapter directory.
        dry_run: If True, don't write files.
        interactive: If True, prompt user for confirmation before writing.
        auto_approve: If True, skip all prompts (accept all).
        force: If True, skip version check and force-overwrite all files.
        source: Source identifier for registration (e.g. "github:owner/repo").

    Layout:
        config/kits/{slug}/     — installed kit files (user-editable)

    Returns dict consumed by update.py / cmd_kit_update:
        kit, version, gen, skill_nav?, agents_content?, gen_errors?
    """
    # @cpt-begin:cpt-studio-algo-kit-update:p1:inst-resolve-config
    config_dir = studio_dir / "config"

    result: Dict[str, Any] = {"kit": kit_slug}
    authority_summary = _authority_result_summary(authority_metadata)
    if authority_summary:
        result["authority"] = authority_summary
    # @cpt-end:cpt-studio-algo-kit-update:p1:inst-resolve-config

    installed_kit_dir, installed_kit_rel, installed_kit_entry, has_registered_kit_path = _resolve_installed_kit_root(
        studio_dir, config_dir, kit_slug,
    )
    registered_kit_path = (
        installed_kit_entry.get("path", "")
        if isinstance(installed_kit_entry, dict)
        else ""
    )

    if installed_kit_dir is None:
        result["version"] = {"status": "failed"}
        result["gen"] = {"files_written": 0}
        result["errors"] = [
            f"Kit '{kit_slug}' is registered at absolute path '{installed_kit_rel}' which is not accessible on this OS",
        ]
        return result

    # @cpt-begin:cpt-studio-algo-kit-update:p1:inst-dry-run-check
    if dry_run:
        result["version"] = {"status": "dry_run"}
        result["gen"] = "dry_run"
        return result
    # @cpt-end:cpt-studio-algo-kit-update:p1:inst-dry-run-check

    # @cpt-begin:cpt-studio-algo-kit-update:p1:inst-read-source-version
    # Read source version
    src_conf = source_dir / _KIT_CONF_FILE
    local_conf_version = _read_kit_version(src_conf) if src_conf.is_file() else ""
    local_source_version = _read_kit_source_version(source_dir)
    if authority_metadata and authority_metadata.get("resolved_ref"):
        source_version = str(authority_metadata.get("resolved_ref") or "")
    elif authority_metadata and authority_metadata.get("installed_version"):
        source_version = str(authority_metadata.get("installed_version") or "")
    else:
        source_version = local_source_version
    # @cpt-end:cpt-studio-algo-kit-update:p1:inst-read-source-version

    # @cpt-begin:cpt-studio-algo-kit-manifest-normalize:p1:inst-rollout-update-drift
    try:
        _manifest = _load_manifest_install_adapter(source_dir, kit_slug=kit_slug)
    except (OSError, ValueError) as exc:
        result["version"] = {"status": "failed"}
        result["gen"] = {"files_written": 0}
        result["errors"] = [str(exc)]
        return result
    _risk_model = None
    _risk_changed = False
    if _manifest is not None:
        try:
            from ..utils.kit_model import load_kit_model
            _risk_model = load_kit_model(source_dir, kit_slug=kit_slug)
        except (OSError, ValueError) as exc:
            result["version"] = {"status": "failed"}
            result["gen"] = {"files_written": 0}
            result["errors"] = [str(exc)]
            return result
        _risk_summary = getattr(_risk_model, "tool_risk_summary", {}) or {}
        installed_fingerprint = str(installed_kit_entry.get("tool_risk_fingerprint", "") or "")
        current_fingerprint = str(getattr(_risk_model, "tool_risk_fingerprint", "") or "")
        _risk_changed = bool(
            _risk_summary.get("requires_confirmation")
            and current_fingerprint
            and current_fingerprint != installed_fingerprint
        )
        risk_errors = _tool_risk_approval_errors(
            _risk_model,
            installed_kit_entry=installed_kit_entry,
            interactive=interactive,
            approved_tool_risks=approved_tool_risks,
        )
        if risk_errors:
            result["version"] = {"status": "failed"}
            result["gen"] = {"files_written": 0}
            result["errors"] = risk_errors
            return result

    # @cpt-begin:cpt-studio-algo-kit-update-drift-prune:p1:inst-update-register-reread
    if (
        _manifest is not None
        and isinstance(installed_kit_entry, dict)
        and installed_kit_entry.get("install_mode") == "register"
    ):
        effective_project_root = project_root or _project_root_from_core_toml(config_dir, studio_dir)
        containment_errors = _validate_register_manifest_containment(
            effective_project_root,
            studio_dir,
            source_dir,
            kit_slug,
            _manifest,
        )
        if containment_errors:
            result["version"] = {"status": "failed"}
            result["gen"] = {"files_written": 0}
            result["errors"] = containment_errors
            return result

        kit_model = _risk_model
        if kit_model is None:
            try:
                from ..utils.kit_model import load_kit_model
                # @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-update-path-load-kitmodel
                kit_model = load_kit_model(source_dir, kit_slug=kit_slug)
                # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-update-path-load-kitmodel
            except (OSError, ValueError) as exc:
                result["version"] = {"status": "failed"}
                result["gen"] = {"files_written": 0}
                result["errors"] = [str(exc)]
                return result

        previous_version = str(installed_kit_entry.get("version") or "")
        resource_bindings = _manifest_register_resource_bindings(
            studio_dir,
            source_dir,
            list(getattr(kit_model, "resources", [])),
        )
        local_metadata: Dict[str, str] = {}
        if local_conf_version:
            local_metadata["conf_version"] = local_conf_version
        registration_errors = _register_kit_in_core_toml(
            config_dir,
            kit_slug,
            source_version,
            studio_dir,
            source=source or str(installed_kit_entry.get("source") or ""),
            resources=resource_bindings,
            kit_path=_serialize_manifest_binding_path(source_dir.resolve(), studio_dir),
            install_mode="register",
            source_provenance=_local_path_provenance(source_dir, "register", studio_dir),
            authority_metadata=authority_metadata,
            local_metadata=local_metadata or None,
            tool_risk_fingerprint=str(getattr(kit_model, "tool_risk_fingerprint", "") or ""),
        )
        if registration_errors:
            result["version"] = {"status": "failed"}
            result["gen"] = {"files_written": 0}
            result["errors"] = registration_errors
            return result
        version_changed = bool(source_version and source_version != previous_version)
        result["version"] = {
            "status": "updated" if version_changed else "current",
        }
        result["gen"] = {"files_written": 0}
        result["drift"] = {
            "install_mode": "register",
            "version_changed": version_changed,
        }
        result["resource_bindings"] = {
            key: value["path"] for key, value in resource_bindings.items()
        }
        _meta_entry = _read_kits_from_core_toml(config_dir).get(kit_slug, {})
        meta = _collect_registered_kit_metadata(studio_dir, kit_slug, _meta_entry)
        if meta["skill_nav"]:
            result["skill_nav"] = meta["skill_nav"]
        if meta["agents_content"]:
            result["agents_content"] = meta["agents_content"]
        return result
    # @cpt-end:cpt-studio-algo-kit-update-drift-prune:p1:inst-update-register-reread
    # @cpt-end:cpt-studio-algo-kit-manifest-normalize:p1:inst-rollout-update-drift

    # @cpt-begin:cpt-studio-algo-kit-update:p1:inst-version-check
    # ── Version check (skip update if same version, unless force) ────────
    if not force and source_version and installed_kit_dir.is_dir():
        installed_version = _read_kit_version_from_core(config_dir, kit_slug)
        if (
            installed_version
            and installed_version == source_version
            and not _authority_commit_changed(authority_metadata, installed_kit_entry)
            and not _risk_changed
        ):
            if _manifest is not None and not installed_kit_entry.get("resources"):
                _mig_result = migrate_legacy_kit_to_manifest(
                    source_dir, studio_dir, kit_slug, interactive=interactive,
                )
                result["manifest_migration"] = _mig_result
                if _mig_result.get("status") == "FAIL":
                    sys.stderr.write(
                        f"kit: warning: manifest migration for '{kit_slug}' failed: "
                        f"{_mig_result.get('errors', [])}\n"
                    )
                    result["version"] = {"status": "failed"}
                    result["gen"] = {"files_written": 0}
                    result["errors"] = _mig_result.get("errors", [])
                    return result
                installed_kit_entry = _read_kits_from_core_toml(config_dir).get(kit_slug, installed_kit_entry)
            synced_resources = _sync_manifest_resource_bindings(_manifest, config_dir, kit_slug)
            resources_changed = False
            if synced_resources is not None:
                current_resources = installed_kit_entry.get("resources", {})
                resources_changed = current_resources != synced_resources
                if resources_changed:
                    registration_errors = _register_kit_in_core_toml(
                        config_dir,
                        kit_slug,
                        source_version,
                        studio_dir,
                        source=source or str(installed_kit_entry.get("source") or ""),
                        resources=synced_resources,
                        kit_path=_resolve_manifest_kit_root_rel(_manifest, synced_resources, kit_slug),
                    )
                    if registration_errors:
                        result["version"] = {"status": "failed"}
                        result["gen"] = {"files_written": 0}
                        result["errors"] = registration_errors
                        return result
            result["version"] = {"status": "updated" if resources_changed else "current"}
            result["gen"] = {"files_written": 0}
            authority_source_type = str(authority_metadata.get("source_type") or "") if authority_metadata else ""
            authority_freshness = str(authority_metadata.get("freshness") or "") if authority_metadata else ""
            if (
                authority_metadata
                and source
                and (authority_source_type == "git" or authority_freshness != "last_known")
            ):
                registration_errors = _register_kit_in_core_toml(
                    config_dir,
                    kit_slug,
                    source_version,
                    studio_dir,
                        source=source,
                        authority_metadata=authority_metadata,
                        local_metadata=(
                            {"conf_version": local_conf_version}
                            if local_conf_version else None
                        ),
                        tool_risk_fingerprint=str(
                            getattr(
                                (_risk_model if _risk_model is not None else _manifest),
                                "tool_risk_fingerprint",
                                "",
                            ) or ""
                        ),
                    )
                if registration_errors:
                    result["version"] = {"status": "failed"}
                    result["gen"] = {"files_written": 0}
                    result["errors"] = registration_errors
                    return result
            # Still collect metadata for .gen/ aggregation
            _current_entry = _read_kits_from_core_toml(config_dir).get(kit_slug, installed_kit_entry)
            meta = _collect_registered_kit_metadata(studio_dir, kit_slug, _current_entry)
            if meta["skill_nav"]:
                result["skill_nav"] = meta["skill_nav"]
            if meta["agents_content"]:
                result["agents_content"] = meta["agents_content"]
            return result
    # @cpt-end:cpt-studio-algo-kit-update:p1:inst-version-check

    # @cpt-begin:cpt-studio-algo-kit-update:p1:inst-legacy-manifest-migration
    # Before file-level diff, check for legacy → manifest migration
    if _manifest is not None and installed_kit_dir.is_dir():
        if not installed_kit_entry.get("resources"):
            _mig_result = migrate_legacy_kit_to_manifest(
                source_dir, studio_dir, kit_slug, interactive=interactive,
            )
            result["manifest_migration"] = _mig_result
            if _mig_result.get("status") == "FAIL":
                sys.stderr.write(
                    f"kit: warning: manifest migration for '{kit_slug}' failed: "
                    f"{_mig_result.get('errors', [])}\n"
                )
    # @cpt-end:cpt-studio-algo-kit-update:p1:inst-legacy-manifest-migration

    # @cpt-begin:cpt-studio-algo-kit-update:p1:inst-resolve-resource-bindings
    # Build source-to-resource-id mapping and resolve resource bindings
    _resource_bindings = None
    _source_to_resource_id = None
    _resource_info = None
    _preseeded_resources = None
    if _manifest is not None:
        from ..utils.manifest import (
            build_source_to_resource_mapping,
            resolve_resource_bindings,
        )
        try:
            _preseeded_resources = _sync_manifest_resource_bindings(
                _risk_model if _risk_model is not None else _manifest,
                config_dir,
                kit_slug,
            )
            if _preseeded_resources is not None and not installed_kit_entry.get("resources"):
                registration_errors = _register_kit_in_core_toml(
                    config_dir,
                    kit_slug,
                    _read_kit_version_from_core(config_dir, kit_slug) or source_version,
                    studio_dir,
                    source=source or str(installed_kit_entry.get("source") or ""),
                    resources=_preseeded_resources,
                    kit_path=(
                        registered_kit_path
                        if has_registered_kit_path
                        else _resolve_manifest_kit_root_rel(
                            _risk_model if _risk_model is not None else _manifest,
                            _preseeded_resources,
                            kit_slug,
                        )
                    ),
                    install_mode=str(installed_kit_entry.get("install_mode") or ""),
                    local_metadata=(
                        {"conf_version": local_conf_version}
                        if local_conf_version else None
                    ),
                    tool_risk_fingerprint=str(getattr(_risk_model, "tool_risk_fingerprint", "") or ""),
                )
                if registration_errors:
                    result["version"] = {"status": "failed"}
                    result["gen"] = {"files_written": 0}
                    result["errors"] = registration_errors
                    return result
                installed_kit_entry = _read_kits_from_core_toml(config_dir).get(kit_slug, installed_kit_entry)
            _source_to_resource_id, _resource_info = build_source_to_resource_mapping(
                source_dir,
                kit_slug=kit_slug,
            )
            _resource_bindings = resolve_resource_bindings(config_dir, kit_slug, studio_dir)
        except ValueError as exc:
            result["version"] = {"status": "failed"}
            result["gen"] = {"files_written": 0}
            result["errors"] = [str(exc)]
            return result
        if not _resource_bindings or not _source_to_resource_id or not _resource_info:
            result["version"] = {"status": "failed"}
            result["gen"] = {"files_written": 0}
            result["errors"] = [
                (
                    f"Manifest-backed update for kit '{kit_slug}' could not resolve resource bindings "
                    "from the source and installed metadata; refusing to treat all files as deleted upstream."
                ),
            ]
            return result
    # @cpt-end:cpt-studio-algo-kit-update:p1:inst-resolve-resource-bindings

    # @cpt-begin:cpt-studio-algo-kit-update:p1:inst-first-install
    # ── 1. First-install or file-level update ────────────────────────
    if not installed_kit_dir.is_dir():
        if _manifest is not None:
            _install_result = install_kit_with_manifest(
                source_dir, studio_dir, kit_slug, source_version,
                _manifest,
                interactive=interactive and not auto_approve,
                source=source,
                authority_metadata=authority_metadata,
                kit_path=registered_kit_path if has_registered_kit_path else "",
                approved_overwrites=approved_overwrites,
                approved_tool_risks=approved_tool_risks,
            )
            files_written = _install_result.get("files_copied", 0)
        else:
            _install_result = _perform_first_install_kit(
                source_dir, installed_kit_dir, config_dir, kit_slug, source_version, studio_dir,
                source=source,
                authority_metadata=authority_metadata,
            )
            files_written = _install_result.get("files_copied", 0)
        install_status = str(_install_result.get("status", "PASS")).upper()
        if install_status == "FAIL":
            result["version"] = {"status": "failed", "source_status": install_status}
        else:
            result["version"] = {"status": "created", "source_status": install_status}
        result["gen"] = {"files_written": files_written}
        if _install_result.get("errors"):
            result["errors"] = list(_install_result.get("errors", []))
        if _install_result.get("actions"):
            result["actions"] = _install_result.get("actions")
        if _install_result.get("status") == "FAIL":
            return result
    # @cpt-end:cpt-studio-algo-kit-update:p1:inst-first-install
    else:
        # @cpt-begin:cpt-studio-algo-kit-update:p1:inst-file-level-diff
        from ..utils.diff_engine import file_level_kit_update

        # @cpt-begin:cpt-studio-algo-kit-update-drift-prune:p1:inst-update-copy-diff
        report = file_level_kit_update(
            source_dir, installed_kit_dir,
            interactive=interactive,
            auto_approve=auto_approve,
            content_dirs=None if _manifest is not None else _KIT_CONTENT_DIRS,
            content_files=None if _manifest is not None else _KIT_CONTENT_FILES,
            resource_bindings=_resource_bindings,
            source_to_resource_id=_source_to_resource_id,
            resource_info=_resource_info,
            strict_resource_files=_manifest is not None,
            approved_overwrites=approved_overwrites,
            prune_mode=prune_mode,
            approved_prunes=approved_prunes,
        )
        # @cpt-end:cpt-studio-algo-kit-update-drift-prune:p1:inst-update-copy-diff
        accepted = report.get("accepted", [])
        declined = report.get("declined", [])

        if accepted:
            ver_status = "updated"
        elif declined:
            ver_status = "partial"
        else:
            ver_status = "current"

        result["version"] = {"status": ver_status}
        result["gen"] = {
            "files_written": len(accepted),
            "accepted_files": accepted,
            "unchanged": report.get("unchanged", 0),
        }
        if declined:
            result["gen_rejected"] = declined
        prune_required = [
            entry for entry in report.get("removed", [])
            if entry.get("prune_fingerprint") and entry.get("action") == "declined"
        ]
        if prune_required:
            result["prune_required"] = prune_required
        # @cpt-end:cpt-studio-algo-kit-update:p1:inst-file-level-diff

        # @cpt-begin:cpt-studio-algo-kit-update:p1:inst-update-core-toml
        _merged_resources = _sync_manifest_resource_bindings(
            _risk_model if _risk_model is not None else _manifest, config_dir, kit_slug,
        )
        # Bump core.toml version only when at least one diff was accepted —
        # OR when there was nothing to diff in the first place (the kit was
        # already current and the call exists to refresh manifest-derived
        # resource bindings). Bumping after `partial` (everything declined)
        # would mark the kit "current" against a remote it does not match,
        # silently hiding the pending update on the next `cfs kit update`.
        bumped_safe_to_record = ver_status != "partial"
        if (source_version and bumped_safe_to_record) or _merged_resources:
            _kit_root_rel = registered_kit_path if _manifest is not None else ""
            # When all changes were declined, preserve the previously
            # registered version so the next update sees the kit as
            # outdated and re-prompts. Resource bindings still propagate.
            if not bumped_safe_to_record:
                _existing = _read_kits_from_core_toml(config_dir).get(kit_slug, {})
                preserved_version = str(_existing.get("version") or "") or source_version
            else:
                preserved_version = source_version
            registration_errors = _register_kit_in_core_toml(
                config_dir, kit_slug, preserved_version, studio_dir,
                source=source, resources=_merged_resources, kit_path=_kit_root_rel,
                authority_metadata=authority_metadata,
                local_metadata=(
                    {"conf_version": local_conf_version}
                    if local_conf_version else None
                ),
                tool_risk_fingerprint=str(
                    getattr((_risk_model if _risk_model is not None else _manifest), "tool_risk_fingerprint", "") or ""
                ),
            )
            if registration_errors:
                result["version"] = {"status": "failed"}
                result["gen"] = {"files_written": 0}
                result["errors"] = registration_errors
                return result
        # @cpt-end:cpt-studio-algo-kit-update:p1:inst-update-core-toml

    # @cpt-begin:cpt-studio-algo-kit-update:p1:inst-collect-metadata
    # ── 2. Collect metadata for .gen/ aggregation ────────────────────
    _meta_entry = _read_kits_from_core_toml(config_dir).get(kit_slug, {})
    meta = _collect_registered_kit_metadata(studio_dir, kit_slug, _meta_entry)
    if meta["skill_nav"]:
        result["skill_nav"] = meta["skill_nav"]
    if meta["agents_content"]:
        result["agents_content"] = meta["agents_content"]
    # @cpt-end:cpt-studio-algo-kit-update:p1:inst-collect-metadata

    # @cpt-begin:cpt-studio-algo-kit-update:p1:inst-return-result
    return result
    # @cpt-end:cpt-studio-algo-kit-update:p1:inst-return-result

# @cpt-begin:cpt-studio-flow-kit-dispatch:p1:inst-migrate-deprecated
def cmd_kit_migrate(_argv: List[str]) -> int:
    """Deprecated — use 'cfs kit update <path>' instead.

    The migrate command was part of the blueprint-based three-way merge system
    which has been removed.  File-level updates are now handled by 'kit update'.
    """
    sys.stderr.write(
        "WARNING: 'cfs kit migrate' is deprecated.\n"
        "         Use 'cfs kit update <path>' instead.\n"
    )
    return 1
# @cpt-end:cpt-studio-flow-kit-dispatch:p1:inst-migrate-deprecated

# ---------------------------------------------------------------------------
# Kit CLI dispatcher (handles `cfs kit <subcommand>`)
# ---------------------------------------------------------------------------

# @cpt-flow:cpt-studio-flow-kit-dispatch:p1
def cmd_kit(argv: List[str]) -> int:
    """Kit management command dispatcher.

    Usage: cfs kit <install|update|check-updates|validate|normalize|migrate> [options]
    """
    # @cpt-begin:cpt-studio-flow-kit-dispatch:p1:inst-parse-subcmd
    subcommands = ["install", "update", "check-updates", "validate", "normalize", "migrate"]
    usage = "cfs kit <install|update|check-updates|validate|normalize|migrate> [options]"
    descriptions = {
        "install": [
            ("<owner/repo[@ref]>", "Install a kit from GitHub"),
            ("git/<url>[//<subdir>][@<kit>]", "Install a kit from generic Git"),
            ("path/<dir>", "Install a kit from a local directory"),
            ("--path <dir>", "Install a kit from a local directory"),
        ],
        "update": [("[slug|path/<dir>|--path <dir>]", "Update installed kit files")],
        "check-updates": [("[slug]", "Check git/GitHub kit sources for updates")],
        "validate": [("", "Validate kit structure and examples")],
        "normalize": [("<path> [--dry-run]", "Generate .cf-studio-kit.toml from a kit source")],
        "migrate": [("", "Deprecated; use update")],
    }

    def human_fn(_d: dict) -> tuple:
        writes = [
            sys.stderr.write(f"Usage: {usage}\n\n"),
            sys.stderr.write("Subcommands:\n"),
        ]
        for name in subcommands:
            for args, description in descriptions.get(name, [("", "")]):
                command = f"{name} {args}".rstrip()
                writes.append(sys.stderr.write(f"  {command:<30} {description}\n"))
        return tuple(writes)

    if not argv or argv[0] in ("-h", "--help"):
        ui.result(
            {
                "status": "PASS" if argv else "ERROR",
                "message": "Kit management commands" if argv else "Missing kit subcommand",
                "subcommands": subcommands,
                "usage": usage,
            },
            human_fn=human_fn,
        )
        return 0 if argv else 1

    subcmd = argv[0]
    rest = argv[1:]
    # @cpt-end:cpt-studio-flow-kit-dispatch:p1:inst-parse-subcmd

    # @cpt-begin:cpt-studio-flow-kit-dispatch:p1:inst-route
    if subcmd == "install":
        return cmd_kit_install(rest)
    if subcmd == "update":
        return cmd_kit_update(rest)
    if subcmd == "check-updates":
        return cmd_kit_check_updates(rest)
    if subcmd == "validate":
        from .validate_kits import cmd_validate_kits
        return cmd_validate_kits(rest)
    if subcmd == "normalize":
        return cmd_kit_normalize(rest)
    if subcmd == "migrate":
        return cmd_kit_migrate(rest)
    ui.result({"status": "ERROR", "message": f"Unknown kit subcommand: {subcmd}", "subcommands": subcommands})
    return 1
    # @cpt-end:cpt-studio-flow-kit-dispatch:p1:inst-route

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-kit-config-helpers:p1:inst-read-kits-core
def _read_kits_from_core_toml(config_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Read all kit entries from config/core.toml [kits] section.

    Returns dict of {slug: {format, path, source?, version?}}.
    """
    core_toml = config_dir / _KIT_CORE_TOML
    if not core_toml.is_file():
        return {}
    try:
        with open(core_toml, "rb") as f:
            data = tomllib.load(f)
    except (OSError, ValueError):
        return {}
    kits = data.get("kits", {})
    if not isinstance(kits, dict):
        return {}
    return {k: v for k, v in kits.items() if isinstance(v, dict)}
# @cpt-end:cpt-studio-algo-kit-config-helpers:p1:inst-read-kits-core


# @cpt-algo:cpt-studio-algo-kit-source-mode-validation:p1
def _validate_kit_source_mode(
    *,
    local_path: Optional[str],
    version: str = "",
) -> Optional[Dict[str, str]]:
    """Return a CLI error when source-mode arguments conflict."""
    # @cpt-begin:cpt-studio-algo-kit-source-mode-validation:p1:inst-classify-source-mode
    mode = "local_path" if local_path else "github"
    # @cpt-end:cpt-studio-algo-kit-source-mode-validation:p1:inst-classify-source-mode

    # @cpt-begin:cpt-studio-algo-kit-source-mode-validation:p1:inst-reject-mode-conflicts
    if mode == "local_path" and version:
        return {
            "status": "FAIL",
            "message": "--version can only be used with Git or GitHub kit sources, not --path",
            "hint": "For local --path installs or updates, omit --version; conf.toml version is treated as local metadata only.",
        }
    # @cpt-end:cpt-studio-algo-kit-source-mode-validation:p1:inst-reject-mode-conflicts

    # @cpt-begin:cpt-studio-algo-kit-source-mode-validation:p1:inst-local-path-outside-authority
    return None
    # @cpt-end:cpt-studio-algo-kit-source-mode-validation:p1:inst-local-path-outside-authority


# @cpt-algo:cpt-studio-algo-kit-config-helpers:p1
# @cpt-begin:cpt-studio-algo-kit-config-helpers:p1:inst-read-slug-fn
def _read_kit_slug(kit_source: Path) -> str:
    """Read kit slug from canonical manifest or source conf.toml."""
    # @cpt-begin:cpt-studio-algo-kit-config-helpers:p1:inst-read-slug
    try:
        from ..utils.kit_model import load_canonical_kit_models
        canonical_models = load_canonical_kit_models(kit_source)
        if len(canonical_models) == 1 and canonical_models[0].slug:
            return canonical_models[0].slug
        if len(canonical_models) > 1:
            return ""
    except ValueError as exc:
        sys.stderr.write(f"kit: warning: cannot read canonical kit metadata from {kit_source}: {exc}\n")

    conf_toml = kit_source / "conf.toml"
    if not conf_toml.is_file():
        return ""
    try:
        with open(conf_toml, "rb") as f:
            data = tomllib.load(f)
        slug = data.get("slug")
        if isinstance(slug, str) and slug.strip():
            return slug.strip()
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"kit: warning: cannot read {conf_toml}: {exc}\n")
    return ""
    # @cpt-end:cpt-studio-algo-kit-config-helpers:p1:inst-read-slug
# @cpt-end:cpt-studio-algo-kit-config-helpers:p1:inst-read-slug-fn


def _read_kit_source_version(kit_source: Path) -> str:
    """Read kit version from canonical manifest or source conf.toml."""
    try:
        from ..utils.kit_model import load_canonical_kit_models
        canonical_models = load_canonical_kit_models(kit_source)
        if len(canonical_models) == 1 and canonical_models[0].version:
            return canonical_models[0].version
        if len(canonical_models) > 1:
            return ""
    except ValueError as exc:
        sys.stderr.write(f"kit: warning: cannot read canonical kit metadata from {kit_source}: {exc}\n")

    conf_toml = kit_source / _KIT_CONF_FILE
    return _read_kit_version(conf_toml) if conf_toml.is_file() else ""


def _has_canonical_kit_models(kit_source: Path) -> bool:
    """Return True when the source contains a valid canonical kit manifest."""
    try:
        from ..utils.kit_model import load_canonical_kit_models
        return bool(load_canonical_kit_models(kit_source))
    except ValueError:
        return False


def _split_kit_selectors(raw_values: List[str]) -> List[str]:
    selectors: List[str] = []
    for raw_value in raw_values:
        for part in str(raw_value).split(","):
            value = part.strip()
            if value:
                selectors.append(value)
    return selectors


def _select_canonical_kit_models_for_install(
    kit_source: Path,
    requested_kits: List[str],
    *,
    interactive: bool,
) -> Tuple[List[Any], Optional[Dict[str, Any]]]:
    """Return selected canonical KitModels, or [] for non-canonical sources."""
    # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-install-select-kit
    try:
        from ..utils.kit_model import load_canonical_kit_models
        models = load_canonical_kit_models(kit_source)
    except ValueError as exc:
        return [], {"status": "FAIL", "message": str(exc)}
    if not models:
        if requested_kits:
            return [], {
                "status": "FAIL",
                "message": "--kit can only select kits declared in .cf-studio-kit.toml",
            }
        return [], None

    by_slug = {str(model.slug): model for model in models}
    requested = _split_kit_selectors(requested_kits)
    if requested:
        if any(value == "all" for value in requested):
            return models, None
        missing = [value for value in requested if value not in by_slug]
        if missing:
            return [], {
                "status": "FAIL",
                "message": f"Unknown kit selection: {', '.join(missing)}",
                "available_kits": sorted(by_slug),
                "hint": "Use --kit <slug>, repeat --kit, or --kit all",
            }
        selected: List[Any] = []
        seen: set[str] = set()
        for value in requested:
            if value not in seen:
                selected.append(by_slug[value])
                seen.add(value)
        return selected, None

    if len(models) == 1:
        return models, None

    if not interactive:
        return [], {
            "status": "FAIL",
            "message": ".cf-studio-kit.toml declares multiple kits; choose which to install",
            "available_kits": sorted(by_slug),
            "hint": "Use --kit <slug>, repeat --kit, or --kit all",
        }

    sys.stderr.write("\n  Multiple kits are declared:\n")
    for idx, model in enumerate(models, start=1):
        sys.stderr.write(f"  [{idx}] {model.slug}  {model.version or ''}\n")
    answer = _input_stderr("  Install which kits? (number/slug, comma-separated, or all): ")
    requested = _split_kit_selectors([answer])
    if not requested:
        return [], {
            "status": "FAIL",
            "message": "No kits selected",
            "available_kits": sorted(by_slug),
        }
    normalized: List[str] = []
    for value in requested:
        if value == "all":
            return models, None
        if value.isdigit():
            idx = int(value)
            if idx < 1 or idx > len(models):
                return [], {
                    "status": "FAIL",
                    "message": f"Kit selection index out of range: {value}",
                    "available_kits": sorted(by_slug),
                }
            normalized.append(str(models[idx - 1].slug))
        else:
            normalized.append(value)
    return _select_canonical_kit_models_for_install(
        kit_source,
        normalized,
        interactive=False,
    )
    # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-install-select-kit

# @cpt-begin:cpt-studio-algo-kit-config-helpers:p1:inst-read-version-core-fn
def _read_kit_version_from_core(config_dir: Path, kit_slug: str) -> str:
    """Read installed kit version from config/core.toml [kits.{slug}].version."""
    # @cpt-begin:cpt-studio-algo-kit-config-helpers:p1:inst-read-version-from-core
    core_toml = config_dir / _KIT_CORE_TOML
    if not core_toml.is_file():
        return ""
    try:
        with open(core_toml, "rb") as f:
            data = tomllib.load(f)
        kit_entry = data.get("kits", {}).get(kit_slug, {})
        ver = kit_entry.get("version")
        if ver is not None:
            return str(ver)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"kit: warning: cannot read version for '{kit_slug}' from {core_toml}: {exc}\n")
    return ""
    # @cpt-end:cpt-studio-algo-kit-config-helpers:p1:inst-read-version-from-core
# @cpt-end:cpt-studio-algo-kit-config-helpers:p1:inst-read-version-core-fn

# @cpt-begin:cpt-studio-algo-kit-config-helpers:p1:inst-read-kit-version-fn
def _read_kit_version(conf_path: Path) -> str:
    """Read kit version from conf.toml."""
    # @cpt-begin:cpt-studio-algo-kit-config-helpers:p1:inst-read-kit-version
    try:
        with open(conf_path, "rb") as f:
            data = tomllib.load(f)
        ver = data.get("version")
        if ver is not None:
            return str(ver)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"kit: warning: cannot read version from {conf_path}: {exc}\n")
    return ""
    # @cpt-end:cpt-studio-algo-kit-config-helpers:p1:inst-read-kit-version
# @cpt-end:cpt-studio-algo-kit-config-helpers:p1:inst-read-kit-version-fn

# @cpt-begin:cpt-studio-algo-kit-config-helpers:p1:inst-register-core-fn
def _register_kit_in_core_toml(
    config_dir: Path,
    kit_slug: str,
    kit_version: str,
    _studio_dir: Path,  # reserved for future studio-dir-relative path computation
    source: str = "",
    resources: Optional[Dict[str, Dict[str, Any]]] = None,
    kit_path: str = "",
    install_mode: str = "",
    authority_metadata: Optional[Dict[str, Any]] = None,
    source_provenance: Optional[Dict[str, Any]] = None,
    local_metadata: Optional[Dict[str, Any]] = None,
    tool_risk_fingerprint: str = "",
) -> List[str]:
    """Register or update a kit entry in config/core.toml."""
    # @cpt-begin:cpt-studio-algo-kit-config-helpers:p1:inst-register-core
    core_toml = config_dir / _KIT_CORE_TOML
    if not core_toml.is_file():
        return [f"Cannot register kit '{kit_slug}': missing {core_toml}"]

    try:
        with open(core_toml, "rb") as f:
            data = tomllib.load(f)
    except (OSError, ValueError) as exc:
        return [f"Cannot register kit '{kit_slug}' in {core_toml}: {exc}"]
    project_root = _project_root_for_core_paths(config_dir, _studio_dir, data)

    kits = data.setdefault("kits", {})
    # Merge into existing entry to preserve fields like 'source'
    existing = kits.get(kit_slug, {})
    if not isinstance(existing, dict):
        existing = {}
    existing["format"] = "CFS"
    if kit_path:
        normalized_kit_path = _normalize_registered_kit_path(kit_path, kit_slug)
        existing_path = existing.get("path")
        preserve_legacy_absolute = (
            isinstance(existing_path, str)
            and _normalize_path_string(existing_path) == normalized_kit_path
        )
        path_error = _validate_persisted_core_path(
            f"Kit '{kit_slug}' path",
            normalized_kit_path,
            _studio_dir,
            project_root,
            allow_same_os_absolute=preserve_legacy_absolute,
        )
        if path_error:
            return [path_error]
        if (
            isinstance(existing_path, str)
            and _normalize_path_string(existing_path) == normalized_kit_path
        ):
            existing["path"] = existing_path
        else:
            existing["path"] = normalized_kit_path
    elif not existing.get("path"):
        existing["path"] = f"config/kits/{kit_slug}"
    if source:
        existing["source"] = source
    if install_mode:
        existing["install_mode"] = install_mode
    if source_provenance:
        existing["source_provenance"] = {
            key: value for key, value in source_provenance.items() if value
        }
    if authority_metadata:
        # @cpt-begin:cpt-studio-algo-kit-github-version-authority:p1:inst-persist-authority-metadata
        source_type = "github" if source.startswith("github:") else ("git" if source.startswith("git:") else "unknown")
        source_provenance = {
            "source_type": authority_metadata.get("source_type", source_type),
            "resolver_mode": authority_metadata.get("resolver_mode", ""),
            "resolution_basis": authority_metadata.get("resolution_basis", ""),
            "requested_ref": authority_metadata.get("requested_ref", ""),
            "resolved_ref": authority_metadata.get("resolved_ref", ""),
            "commit_sha": authority_metadata.get("commit_sha", ""),
            "canonical_source": authority_metadata.get("canonical_source", source),
            "effective_source": authority_metadata.get("effective_source", source),
            "original_source": authority_metadata.get("original_source", ""),
            "decoded_remote_url": authority_metadata.get("decoded_remote_url", ""),
            "decoded_remote_url_hash": authority_metadata.get("decoded_remote_url_hash", ""),
            "selected_subdirectory": authority_metadata.get("selected_subdirectory", ""),
            "kit_identity": authority_metadata.get("kit_identity", ""),
            "transport": authority_metadata.get("transport", ""),
            "cache_remote_hash": authority_metadata.get("cache_remote_hash", ""),
            "cache_requested_ref_hash": authority_metadata.get("cache_requested_ref_hash", ""),
            "cache_subdir_hash": authority_metadata.get("cache_subdir_hash", ""),
            "cache_kit_hash": authority_metadata.get("cache_kit_hash", ""),
            "verified": authority_metadata.get("verified", "unknown"),
            "freshness": authority_metadata.get("freshness", "unknown"),
        }
        existing["source_provenance"] = {
            key: value for key, value in source_provenance.items() if value
        }
        authority_version = (
            authority_metadata.get("installed_version")
            or authority_metadata.get("version")
            or authority_metadata.get("resolved_ref")
            or kit_version
        )
        if authority_version:
            existing["version"] = str(authority_version)
        # @cpt-end:cpt-studio-algo-kit-github-version-authority:p1:inst-persist-authority-metadata
    elif kit_version:
        existing["version"] = kit_version
    existing.pop("content_identity", None)
    if local_metadata:
        existing["local_metadata"] = local_metadata
    # @cpt-begin:cpt-studio-algo-kit-tool-permission-risk:p1:inst-risk-noninteractive-fingerprint
    if tool_risk_fingerprint:
        existing["tool_risk_fingerprint"] = tool_risk_fingerprint
    else:
        existing.pop("tool_risk_fingerprint", None)
    # @cpt-end:cpt-studio-algo-kit-tool-permission-risk:p1:inst-risk-noninteractive-fingerprint
    if install_mode == "register":
        existing.pop("resources", None)
    elif resources is not None:
        resource_errors: List[str] = []
        for res_id, binding in resources.items():
            path_value = binding.get("path") if isinstance(binding, dict) else binding
            if not isinstance(path_value, str) or not path_value.strip():
                continue
            path_error = _validate_persisted_core_path(
                f"Kit '{kit_slug}' resource '{res_id}' path",
                path_value,
                _studio_dir,
                project_root,
                allowed_absolute_root=str(existing.get("path", "") or ""),
            )
            if path_error:
                resource_errors.append(path_error)
        if resource_errors:
            return resource_errors
        existing["resources"] = resources
    kits[kit_slug] = existing

    # Write back using our TOML serializer
    try:
        from ..utils import toml_utils
        toml_utils.dump(data, core_toml, header_comment="Constructor Studio project configuration")
    except (OSError, ValueError) as exc:
        message = f"kit: warning: failed to register {kit_slug} in {core_toml}: {exc}"
        sys.stderr.write(f"{message}\n")
        return [message]
    return []
    # @cpt-end:cpt-studio-algo-kit-config-helpers:p1:inst-register-core
# @cpt-end:cpt-studio-algo-kit-config-helpers:p1:inst-register-core-fn
