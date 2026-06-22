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
import logging
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
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
from ..utils.stderr_logging import emit_stderr_message
# @cpt-end:cpt-studio-algo-kit-github-helpers:p1:inst-kit-imports

if TYPE_CHECKING:
    from ..utils.manifest import Manifest, ManifestResource

logger = logging.getLogger(__name__)


def _warn_kit(message: str) -> None:
    logger.warning("kit: %s", message)


def _warn_user(message: str) -> None:
    _warn_kit(message)
    ui.warn(message)


def _ui_lines(*lines: str, blank_before: bool = False, blank_after: bool = False) -> None:
    if blank_before:
        ui.blank()
    for line in lines:
        ui.info(line)
    if blank_after:
        ui.blank()


def _emit_stdout_text(text: str) -> None:
    print(  # pylint: disable=stdout-bypass
        text,
        end="" if text.endswith("\n") else "\n",
    )


def _emit_stderr_text(text: str) -> None:
    emit_stderr_message(text, logger_name=f"{__name__}.stderr")


@dataclass(frozen=True)
class _InstallContext:
    interactive: bool = False
    install_mode: str = "copy"
    project_root: Optional[Path] = None
    source: str = ""
    authority_metadata: Optional[Dict[str, Any]] = None
    approved_overwrites: List[str] = field(default_factory=list)
    approved_tool_risks: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class _UpdateContext:
    dry_run: bool = False
    interactive: bool = True
    auto_approve: bool = False
    force: bool = False
    source: str = ""
    authority_metadata: Optional[Dict[str, Any]] = None
    approved_overwrites: List[str] = field(default_factory=list)
    approved_tool_risks: List[str] = field(default_factory=list)
    prune_mode: bool = False
    approved_prunes: List[str] = field(default_factory=list)
    project_root: Optional[Path] = None


@dataclass(frozen=True)
class _RegisterKitContext:
    source: str = ""
    resources: Optional[Dict[str, Dict[str, Any]]] = None
    kit_path: str = ""
    install_mode: str = ""
    authority_metadata: Optional[Dict[str, Any]] = None
    source_provenance: Optional[Dict[str, Any]] = None
    local_metadata: Optional[Dict[str, Any]] = None
    tool_risk_fingerprint: str = ""


@dataclass(frozen=True)
class _InstallSuccessContext:
    studio_dir: Path
    kit_slug: str
    kit_version: str
    install_mode: str
    config_kit_rel: str
    kit_source: Path
    local_metadata: Dict[str, str]
    actions: Dict[str, str]
    copy_actions: Dict[str, str]


@dataclass(frozen=True)
class _ManifestInstallArtifacts:
    kit_model: Any
    model_resources: List[Any]
    extra_subagent_sources: List[str]


@dataclass(frozen=True)
class _ManifestInstallPlan:
    kit_root: Path
    kit_root_rel: str
    resource_bindings: Dict[str, Dict[str, Any]]


@dataclass(frozen=True)
class _KitInstallSourceState:
    kit_source: Path
    kit_slug: str
    kit_version: str
    source_registration: str
    tmp_dir_to_clean: Optional[Path]
    authority_metadata: Optional[Dict[str, Any]]


@dataclass(frozen=True)
class _KitInstallExecution:
    studio_dir: Path
    config_dir: Path
    project_root: Path
    selected_install_mode: str
    selected_tracking: Optional[str]
    source_registration: str
    authority_metadata: Optional[Dict[str, Any]]


@dataclass(frozen=True)
class _KitUpdateSourceTarget:
    kit_slug: str
    kit_source: Path
    github_source: str
    tmp_dir: Optional[Path]
    authority_metadata: Optional[Dict[str, Any]]


@dataclass(frozen=True)
class _KitUpdateResolution:
    project_root: Path
    studio_dir: Path
    config_dir: Path
    interactive: bool
    update_targets: List[_KitUpdateSourceTarget]
    source_failures: List[Dict[str, Any]]


@dataclass(frozen=True)
class _ManifestUpdateResolution:
    manifest: Optional[Any]
    risk_model: Optional[Any]
    risk_changed: bool
    source_version: str
    local_conf_version: str
    registered_kit_path: str
    has_registered_kit_path: bool


@dataclass(frozen=True)
class _KitUpdateRunContext:
    kit_slug: str
    source_dir: Path
    studio_dir: Path
    config_dir: Path
    installed_kit_dir: Path
    installed_kit_entry: Dict[str, Any]
    update_context: _UpdateContext
    manifest_state: _ManifestUpdateResolution
    result: Dict[str, Any]


def _merge_install_context(
    install_context: Optional[_InstallContext],
    *,
    interactive: Optional[bool] = None,
    install_mode: Optional[str] = None,
    project_root: Optional[Path] = None,
    source: Optional[str] = None,
    authority_metadata: Optional[Dict[str, Any]] = None,
    approved_overwrites: Optional[List[str]] = None,
    approved_tool_risks: Optional[List[str]] = None,
) -> _InstallContext:
    """Preserve the legacy install_kit* kwargs contract."""
    base = install_context or _InstallContext()
    return _InstallContext(
        interactive=base.interactive if interactive is None else interactive,
        install_mode=base.install_mode if install_mode is None else install_mode,
        project_root=base.project_root if project_root is None else project_root,
        source=base.source if source is None else source,
        authority_metadata=(
            base.authority_metadata if authority_metadata is None else authority_metadata
        ),
        approved_overwrites=(
            list(base.approved_overwrites)
            if approved_overwrites is None else list(approved_overwrites)
        ),
        approved_tool_risks=(
            list(base.approved_tool_risks)
            if approved_tool_risks is None else list(approved_tool_risks)
        ),
    )


def _merge_update_context(  # pylint: disable=too-many-arguments
    update_context: Optional[_UpdateContext],
    *,
    dry_run: Optional[bool] = None,
    interactive: Optional[bool] = None,
    auto_approve: Optional[bool] = None,
    force: Optional[bool] = None,
    source: Optional[str] = None,
    authority_metadata: Optional[Dict[str, Any]] = None,
    approved_overwrites: Optional[List[str]] = None,
    approved_tool_risks: Optional[List[str]] = None,
    prune_mode: Optional[bool] = None,
    approved_prunes: Optional[List[str]] = None,
    project_root: Optional[Path] = None,
) -> _UpdateContext:
    """Preserve the legacy update_kit kwargs contract."""
    base = update_context or _UpdateContext()
    return _UpdateContext(
        dry_run=base.dry_run if dry_run is None else dry_run,
        interactive=base.interactive if interactive is None else interactive,
        auto_approve=base.auto_approve if auto_approve is None else auto_approve,
        force=base.force if force is None else force,
        source=base.source if source is None else source,
        authority_metadata=(
            base.authority_metadata if authority_metadata is None else authority_metadata
        ),
        approved_overwrites=(
            list(base.approved_overwrites)
            if approved_overwrites is None else list(approved_overwrites)
        ),
        approved_tool_risks=(
            list(base.approved_tool_risks)
            if approved_tool_risks is None else list(approved_tool_risks)
        ),
        prune_mode=base.prune_mode if prune_mode is None else prune_mode,
        approved_prunes=(
            list(base.approved_prunes)
            if approved_prunes is None else list(approved_prunes)
        ),
        project_root=base.project_root if project_root is None else project_root,
    )


def _result_with_failure(
    result: Dict[str, Any],
    errors: List[str],
    *,
    version_status: str = "failed",
    gen: Any = None,
) -> Dict[str, Any]:
    result["version"] = {"status": version_status}
    result["gen"] = {"files_written": 0} if gen is None else gen
    result["errors"] = errors
    return result


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


def _append_release_notes_whatsnew_lines(
    lines: List[str],
    release: Dict[str, Any],
) -> None:
    tag = str(release.get("tag_name") or "").strip()
    if not tag:
        return
    summary = str(release.get("name") or "").strip() or tag
    details = str(release.get("body") or "").strip()
    lines.append(f'[whatsnew.{_toml_string(tag)}]')
    lines.append(f"summary = {_toml_string(summary)}")
    lines.append(f"details = {_toml_string(details)}")
    lines.append("")


def _github_release_notes_to_whatsnew_toml(releases: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for release in releases:
        _append_release_notes_whatsnew_lines(lines, release)
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
# @cpt-end:cpt-studio-algo-kit-content-mgmt:p1:inst-collect-metadata-fn


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


def _serialize_public_component(
    component: Any,
    *,
    disabled: Optional[bool] = None,
    include_name_mode: bool = False,
    subagents: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    serialized: Dict[str, Any] = {
        "id": component.id,
        "kind": component.kind,
        "source": component.source,
        "generated_name": component.generated_name,
    }
    if include_name_mode:
        serialized["name_mode"] = "prefixed" if component.generated_name != component.id else "as_is"
    serialized["generated_targets"] = component.generated_targets
    serialized["aliases"] = component.aliases
    serialized["origin"] = component.origin
    if subagents is not None:
        serialized["subagents"] = subagents
    if disabled is not None:
        serialized["disabled"] = disabled
    return serialized


def _project_root_for_core_paths(_config_dir: Path, studio_dir: Path, data: Dict[str, Any]) -> Path:
    from ..utils.manifest import resolve_project_root_from_core_data

    resolved_root = resolve_project_root_from_core_data(
        data,
        Path(studio_dir),
        default_to_parent=True,
    )
    return resolved_root or Path(studio_dir).parent.resolve()


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
    if _is_registered_kit_path_absolute(normalized):
        return _validate_absolute_persisted_core_path(
            label,
            normalized,
            allow_same_os_absolute=allow_same_os_absolute,
            allowed_absolute_root=allowed_absolute_root,
        )
    return _validate_relative_persisted_core_path(
        label,
        normalized,
        studio_dir,
        project_root,
    )
    # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-persist-relative-only


def _validate_absolute_persisted_core_path(
    label: str,
    normalized_path: str,
    *,
    allow_same_os_absolute: bool,
    allowed_absolute_root: str,
) -> Optional[str]:
    resolved_absolute = _resolve_same_os_absolute_path(normalized_path)
    if resolved_absolute is None:
        return (
            f"{label} '{normalized_path}' is not accessible on this OS; "
            "use project-relative paths for persisted core.toml state"
        )
    if allow_same_os_absolute:
        return None
    resolved_allowed_root = _resolve_allowed_absolute_root(allowed_absolute_root)
    if resolved_allowed_root is not None and _path_is_within(
        resolved_absolute, resolved_allowed_root
    ):
        return None
    return (
        f"{label} '{normalized_path}' is invalid state: "
        "absolute paths must not be persisted in core.toml; use project-relative paths"
    )


def _resolve_allowed_absolute_root(allowed_absolute_root: str) -> Optional[Path]:
    normalized_allowed_root = _normalize_path_string(allowed_absolute_root)
    if not normalized_allowed_root:
        return None
    return _resolve_same_os_absolute_path(normalized_allowed_root)


def _validate_relative_persisted_core_path(
    label: str,
    normalized_path: str,
    studio_dir: Path,
    project_root: Path,
) -> Optional[str]:
    resolved_path = _resolve_registered_kit_dir(studio_dir, normalized_path)
    if resolved_path is None:
        return (
            f"{label} '{normalized_path}' is not accessible on this OS; "
            "use project-relative paths for persisted core.toml state"
        )
    if _path_is_within(resolved_path, project_root):
        return None
    return (
        f"{label} '{normalized_path}' escapes the current project root '{project_root}'; "
        "core.toml may persist only in-project relative paths"
    )


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


def _binding_is_public_metadata_resource(binding: Dict[str, Any], kind: str) -> bool:
    public_value = binding.get("public")
    if isinstance(public_value, bool):
        return public_value
    if isinstance(public_value, str):
        return public_value.strip().lower() in {"1", "true", "yes", "on"}
    return kind in {"skill", "rule"}


def _load_registered_metadata_resources(
    studio_dir: Path,
    kit_slug: str,
    kit_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    resources = kit_data.get("resources")
    install_mode = str(kit_data.get("install_mode", "") or "").strip()
    if isinstance(resources, dict) and resources:
        return resources
    if install_mode != "register":
        return None
    try:
        from ..utils.kit_model import load_installed_kit_model
        from ..utils.manifest import resolve_resource_bindings_with_errors

        kit_dir, _kit_rel_path = _resolve_registered_kit_metadata_target(
            studio_dir,
            kit_slug,
            kit_data,
        )
        if kit_dir is None:
            return {}
        model = load_installed_kit_model(kit_dir, kit_data, kit_slug=kit_slug)
        bindings, _binding_errors = resolve_resource_bindings_with_errors(
            studio_dir / "config",
            kit_slug,
            studio_dir,
        )
    except (OSError, ValueError) as exc:
        _warn_kit(f"failed to load registered metadata resources for kit '{kit_slug}': {exc}")
        return {}
    public_by_id = {
        str(getattr(component, "id", "")): component
        for component in getattr(model, "public_components", []) or []
    }
    return {
        str(resource_id): {
            "path": _serialize_manifest_binding_path(binding_path, studio_dir),
            "kind": str(getattr(component, "kind", "") or ""),
            "public": True,
        }
        for resource_id, binding_path in bindings.items()
        for component in [public_by_id.get(str(resource_id))]
        if component is not None
    }


def _metadata_binding_kind(binding_path: str, raw_binding: Dict[str, Any]) -> str:
    kind = str(raw_binding.get("kind") or "").strip()
    if kind:
        return kind
    name = PurePosixPath(binding_path).name
    if name == _KIT_SKILL_FILE:
        return "skill"
    if name == _KIT_AGENTS_FILE:
        return "rule"
    return ""


# @cpt-begin:cpt-studio-algo-kit-content-mgmt:p1:inst-collect-metadata
def _collect_registered_kit_metadata(
    studio_dir: Path,
    kit_slug: str,
    kit_entry: Any,
) -> Dict[str, str]:
    kit_data = kit_entry if isinstance(kit_entry, dict) else {}
    resources = _load_registered_metadata_resources(studio_dir, kit_slug, kit_data)
    if not isinstance(resources, dict) or not resources:
        return {}

    result: Dict[str, str] = {"skill_nav": "", "agents_content": ""}
    agents_parts: List[str] = []
    for _res_id, raw_binding in sorted(resources.items()):
        if not isinstance(raw_binding, dict):
            raw_binding = {"path": raw_binding} if isinstance(raw_binding, str) else {}
        binding_path = _extract_registered_binding_path(raw_binding)
        if not binding_path:
            continue
        kind = _metadata_binding_kind(binding_path, raw_binding)
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
            except OSError as exc:
                _warn_kit(f"failed to read metadata resource {binding_abs}: {exc}")
    result["agents_content"] = "\n\n".join(part for part in agents_parts if part)
    return result
# @cpt-end:cpt-studio-algo-kit-content-mgmt:p1:inst-collect-metadata


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
        if meta.get("agents_content"):
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
        (
            "ALWAYS open and follow `{cf-studio-path}/.core/schemas/artifacts.schema.json` "
            "WHEN working with artifacts.toml"
        ),
        "",
        (
            "ALWAYS open and follow `{cf-studio-path}/.core/architecture/specs/"
            "artifacts-registry.md` WHEN working with artifacts.toml"
        ),
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
        _warn_kit(f"cannot read project name from {artifacts_toml}: {exc}")
    return None
# @cpt-end:cpt-studio-algo-kit-regen-gen:p1:inst-read-project-name-fn


def _input_stderr(prompt: str) -> str:
    # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-resolve-local-install-mode
    try:
        _emit_stderr_text(prompt)
        return input().strip()
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
    except ValueError as exc:
        _warn_kit(f"path {path} is not within {root}: {exc}")
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
    optional_strings = [
        ("description", "", None),
        ("origin", "", None),
        ("model", "", None),
        ("color", "", None),
        ("memory_dir", "", None),
        ("mode", "readwrite", "readwrite"),
        ("role", "any", "any"),
        ("target", "any", "any"),
        ("provider", "anthropic", "anthropic"),
    ]
    for key, default, skip_value in optional_strings:
        value = str(getattr(res, key, default) or default).strip()
        if value and value != skip_value:
            entry[key] = value
    for key, attr in (
        ("aliases", "aliases"),
        ("generated_targets", "generated_targets"),
        ("tools", "tools"),
        ("disallowed_tools", "disallowed_tools"),
        ("skills", "skills"),
        ("subagents", "subagents"),
    ):
        value = list(getattr(res, attr, []) or [])
        if value:
            entry[key] = value
    for key, attr in (
        ("reasoning_effort", "reasoning_effort"),
        ("context_window", "context_window"),
    ):
        value = getattr(res, attr, None)
        if value:
            entry[key] = value
    targets = dict(getattr(res, "target_configs", {}) or {})
    if targets:
        entry["targets"] = targets
    if not bool(getattr(res, "user_modifiable", True)):
        entry["user_modifiable"] = False
    if not bool(getattr(res, "prefix_generated_name", True)):
        entry["prefix_generated_name"] = False
    if bool(getattr(res, "isolation", False)):
        entry["isolation"] = True
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


def _manifest_public_subagent_sources(resources: List[Any]) -> List[str]:
    """Return unique relative prompt sources declared by canonical public subagents."""
    sources: List[str] = []
    seen: set[str] = set()
    for res in resources:
        if str(getattr(res, "kind", "") or "") != "agent":
            continue
        for subagent in getattr(res, "subagents", []) or []:
            normalized = _normalize_manifest_public_subagent_source(subagent)
            if normalized is None:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            sources.append(normalized)
    return sources


def _validate_manifest_public_subagent_sources(
    kit_source: Path,
    subagent_sources: List[str],
) -> Optional[str]:
    """Return the first manifest public subagent source validation error, if any."""
    for subagent_source in subagent_sources:
        source_abs = kit_source / Path(PurePosixPath(subagent_source))
        if not source_abs.exists():
            return f"Manifest subagent source '{subagent_source}' does not exist in kit source"
        if not source_abs.is_file():
            return f"Manifest subagent source '{subagent_source}' is not a file"
    return None


def _augment_manifest_subagent_update_bindings(
    model: Any,
    installed_kit_dir: Path,
    source_to_resource_id: Dict[str, str],
    resource_info: Dict[str, Any],
    resource_bindings: Dict[str, Path],
) -> None:
    """Teach manifest-backed updates to treat copied public subagent prompts as managed files."""
    for res in list(getattr(model, "resources", []) or []):
        if str(getattr(res, "kind", "") or "") != "agent":
            continue
        for subagent in getattr(res, "subagents", []) or []:
            normalized = _normalize_manifest_public_subagent_source(subagent)
            if normalized is None:
                continue
            synthetic_id = source_to_resource_id.get(normalized) or f"{res.id}.__subagent__.{normalized}"
            source_to_resource_id[normalized] = synthetic_id
            if synthetic_id not in resource_info:
                resource_info[synthetic_id] = type(
                    "SyntheticResourceInfo",
                    (),
                    {
                        "type": "file",
                        "source_base": normalized,
                        "user_modifiable": bool(getattr(res, "user_modifiable", True)),
                    },
                )()
            if synthetic_id not in resource_bindings:
                resource_bindings[synthetic_id] = (installed_kit_dir / Path(PurePosixPath(normalized))).resolve()


def _normalize_manifest_public_subagent_source(subagent: Any) -> Optional[str]:
    if not isinstance(subagent, dict):
        return None
    raw_source = str(subagent.get("source", "") or "").strip().replace("\\", "/")
    if not raw_source:
        return None
    source_path = PurePosixPath(raw_source)
    if source_path.is_absolute() or ".." in source_path.parts:
        return None
    return source_path.as_posix()


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
                subagent_name = (
                    subagent_id
                    if subagent_id == f"cf-{model.slug}" or subagent_id.startswith(prefix)
                    else f"{prefix}{subagent_id}"
                )
            else:
                subagent_name = subagent_id
            names[subagent_name] = f"{base_component_id}.subagents.{subagent_id}"
    return names
# @cpt-end:cpt-studio-algo-kit-public-component-generation:p1:inst-public-prefix
# @cpt-end:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-hashes


def _iter_public_component_names(model: Any, slug: str) -> List[Tuple[str, str]]:
    component_names: List[Tuple[str, str]] = []
    prefix = f"cf-{slug}-"
    for component in getattr(model, "public_components", []) or []:
        base_component_id = str(getattr(component, "id", "") or "")
        name = str(getattr(component, "generated_name", "") or "").strip()
        if name:
            component_names.append((name, base_component_id))
        if str(getattr(component, "kind", "") or "") != "agent":
            continue
        for subagent in getattr(component, "subagents", []) or []:
            if not isinstance(subagent, dict):
                continue
            subagent_id = str(subagent.get("id", "") or "").strip()
            if not subagent_id:
                continue
            if bool(subagent.get("prefix_generated_name", True)):
                generated_name = (
                    subagent_id
                    if subagent_id == f"cf-{slug}" or subagent_id.startswith(prefix)
                    else f"{prefix}{subagent_id}"
                )
            else:
                generated_name = subagent_id
            component_names.append((generated_name, f"{base_component_id}.subagents.{subagent_id}"))
    return component_names


def _append_public_component_conflicts(
    errors: List[str],
    seen: Dict[str, str],
    names: List[Tuple[str, str]],
    slug: str,
) -> None:
    for name, component_id in names:
        if name in seen:
            errors.append(
                f"Public component name conflict in kit '{slug}': "
                f"'{name}' is produced by '{seen[name]}' and '{component_id}'",
            )
            continue
        seen[name] = component_id


def _append_installed_public_component_conflicts(
    errors: List[str],
    incoming: Dict[str, str],
    studio_dir: Path,
    installing_slug: str,
) -> None:
    try:
        from ..utils.kit_model import load_installed_kit_model
    except ImportError as exc:
        logger.debug(
            "kit: installed kit model unavailable while checking public component conflicts",
            exc_info=exc,
        )
        return

    for existing_slug, kit_entry in sorted(
        _read_kits_from_core_toml(studio_dir / "config").items()
    ):
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
            existing_model = load_installed_kit_model(
                existing_root,
                kit_entry,
                kit_slug=existing_slug_str,
            )
        except (OSError, ValueError) as exc:
            _warn_kit(f"failed to inspect installed kit model for '{existing_slug_str}': {exc}")
            continue
        for name, existing_component_id in _kit_model_public_component_names(existing_model).items():
            incoming_component_id = incoming.get(name)
            if incoming_component_id is None:
                continue
            errors.append(
                f"Public component name conflict: kit '{installing_slug}' resource "
                f"'{incoming_component_id}' generates '{name}', already generated by kit "
                f"'{existing_slug_str}' resource '{existing_component_id}'",
            )


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
    _append_public_component_conflicts(
        errors,
        seen,
        _iter_public_component_names(installing_model, installing_slug),
        installing_slug,
    )
    if errors:
        return errors

    _append_installed_public_component_conflicts(
        errors,
        incoming,
        studio_dir,
        installing_slug,
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


def _legacy_manifest_install_warning(kit_source: Path) -> Optional[str]:
    """Return a migration warning when install does not use canonical kit metadata."""
    # @cpt-begin:cpt-studio-algo-kit-install:p1:inst-validate-source
    canonical_manifest = kit_source / ".cf-studio-kit.toml"
    if canonical_manifest.is_file():
        return None
    legacy_manifest = kit_source / "manifest.toml"
    if legacy_manifest.is_file():
        return (
            "Kit uses legacy manifest 'manifest.toml'. "
            "Please ask the kit authors to migrate to '.cf-studio-kit.toml'."
        )
    return (
        "Kit uses a legacy layout without '.cf-studio-kit.toml'. "
        "Please ask the kit authors to migrate to '.cf-studio-kit.toml'."
    )
    # @cpt-end:cpt-studio-algo-kit-install:p1:inst-validate-source


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
        _ui_lines(
            f"Local kit install mode: {kit_slug}",
            "  - copy: copy resources into Studio-managed storage",
            blank_before=True,
        )
        if register_available:
            ui.info("  - register: leave in-project resources in place and bind them")
        else:
            ui.info("  - register: unavailable for this source")
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
            ui.info("  Register mode is unavailable:")
            for error in register_errors:
                ui.info(f"  - {error}")
# @cpt-end:cpt-studio-algo-kit-local-path-install-mode:p1:inst-local-mode-always-ask


def _emit_manifest_install_plan(
    kit_slug: str,
    kit_root: Path,
    resources: List[Any],
    resource_overrides: Dict[str, Path],
) -> None:
    _ui_lines(
        f"Kit install plan: {kit_slug}",
        f"  - Kit root: {kit_root}",
        blank_before=True,
    )
    if not resources:
        ui.info("  - Resources: none declared")
    else:
        ui.info("  - Files to write:")
        for idx, res in enumerate(resources, start=1):
            target = _manifest_resource_target(kit_root, res, resource_overrides)
            mod = "editable" if res.user_modifiable else "locked"
            ui.info(
                f"    [{idx}] {res.id} ({res.type}, {mod}): {res.source} -> {target}"
            )
    ui.blank()


def _manifest_install_plan_result(
    studio_dir: Path,
    kit_root: Path,
    kit_root_rel: str,
    resources: List[Any],
    resource_overrides: Dict[str, Path],
) -> tuple[Path, str, Dict[str, Dict[str, str]]]:
    return (
        kit_root,
        kit_root_rel,
        _manifest_resource_bindings(studio_dir, kit_root, resources, resource_overrides),
    )


def _manifest_install_plan_snapshot(
    studio_dir: Path,
    kit_root: Path,
    resources: List[Any],
    resource_overrides: Dict[str, Path],
    registered_kit_root_rel: Optional[str],
    root_changed: bool,
) -> tuple[Path, str, Dict[str, Dict[str, str]]]:
    kit_root_rel = (
        registered_kit_root_rel
        if registered_kit_root_rel is not None and not root_changed
        else _serialize_manifest_binding_path(kit_root, studio_dir)
    )
    return _manifest_install_plan_result(
        studio_dir,
        kit_root,
        kit_root_rel,
        resources,
        resource_overrides,
    )


def _manifest_install_edit_menu(
    manifest: Manifest,
    kit_root: Path,
    resources: List[Any],
    resource_overrides: Dict[str, Path],
) -> List[tuple[str, str, Optional[Any]]]:
    menu: List[tuple[str, str, Optional[Any]]] = []
    if manifest.user_modifiable:
        menu.append(("root", f"Kit root -> {kit_root}", None))
    for res in resources:
        if not res.user_modifiable:
            continue
        target = _manifest_resource_target(kit_root, res, resource_overrides)
        menu.append(("resource", f"{res.id} -> {target}", res))
    return menu


def _manifest_install_can_edit(
    manifest: Manifest,
    resources: List[Any],
) -> bool:
    return manifest.user_modifiable or any(
        bool(getattr(res, "user_modifiable", True)) for res in resources
    )


def _apply_manifest_install_plan_change(  # pylint: disable=too-many-locals
    studio_dir: Path,
    kit_root: Path,
    resource_overrides: Dict[str, Path],
    choice_item: tuple[str, str, Optional[Any]],
) -> tuple[Path, bool]:
    kind, _, res = choice_item
    if kind == "root":
        new_root = _input_stderr(f"  Kit root directory [{kit_root}]: ")
        if new_root:
            return _resolve_manifest_user_path(studio_dir, new_root), True
        return kit_root, False
    if res is None:
        return kit_root, False
    current_target = _manifest_resource_target(kit_root, res, resource_overrides)
    new_target = _input_stderr(f"  Resource '{res.id}' path [{current_target}]: ")
    if new_target:
        resource_overrides[res.id] = _resolve_manifest_user_path(kit_root, new_target)
    return kit_root, False


def _prompt_manifest_install_plan_interactive(  # pylint: disable=too-many-locals
    kit_slug: str,
    studio_dir: Path,
    kit_root: Path,
    manifest: Manifest,
    resources: List[Any],
    registered_kit_root_rel: Optional[str],
    resource_overrides: Dict[str, Path],
) -> tuple[Path, str, Dict[str, Dict[str, str]]]:
    root_changed = False
    can_edit = _manifest_install_can_edit(manifest, resources)

    while True:
        _emit_manifest_install_plan(kit_slug, kit_root, resources, resource_overrides)
        if not can_edit:
            return _manifest_install_plan_snapshot(
                studio_dir,
                kit_root,
                resources,
                resource_overrides,
                registered_kit_root_rel,
                root_changed,
            )
        answer = _input_stderr("  Change kit install paths? [y/N]: ").lower()
        if answer not in ("y", "yes"):
            return _manifest_install_plan_snapshot(
                studio_dir,
                kit_root,
                resources,
                resource_overrides,
                registered_kit_root_rel,
                root_changed,
            )

        _ui_lines("Select path to change", blank_before=True)
        menu = _manifest_install_edit_menu(
            manifest,
            kit_root,
            resources,
            resource_overrides,
        )
        for idx, (_, label, _res) in enumerate(menu, start=1):
            ui.info(f"  [{idx}] {label}")
        done_idx = len(menu) + 1
        ui.info(f"  [{done_idx}] Done")
        choice_raw = _input_stderr("  Choice: ").lower()
        if choice_raw in ("", "d", "done", str(done_idx)):
            return _manifest_install_plan_snapshot(
                studio_dir,
                kit_root,
                resources,
                resource_overrides,
                registered_kit_root_rel,
                root_changed,
            )
        try:
            choice = int(choice_raw)
        except ValueError as exc:
            _warn_kit(f"ignoring non-numeric manifest install selection {choice_raw!r}: {exc}")
            continue
        if choice < 1 or choice > len(menu):
            continue
        kit_root, root_choice_changed = _apply_manifest_install_plan_change(
            studio_dir,
            kit_root,
            resource_overrides,
            menu[choice - 1],
        )
        root_changed = root_changed or root_choice_changed


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

    if not interactive or not sys.stdin.isatty():
        return _manifest_install_plan_snapshot(
            studio_dir,
            kit_root,
            resources,
            resource_overrides,
            registered_kit_root_rel,
            False,
        )

    # @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-prompt-path
    return _prompt_manifest_install_plan_interactive(
        kit_slug,
        studio_dir,
        kit_root,
        manifest,
        resources,
        registered_kit_root_rel,
        resource_overrides,
    )
    # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-prompt-path


def _install_result_fail(
    kit_slug: str,
    errors: List[str],
    **extra: Any,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {"status": "FAIL", "kit": kit_slug, "errors": errors}
    result.update(extra)
    return result


def _prepare_manifest_copy_install(
    studio_dir: Path,
    kit_slug: str,
    manifest: Manifest,
    kit_path: str,
    artifacts: _ManifestInstallArtifacts,
    interactive: bool,
) -> Tuple[Optional[_ManifestInstallPlan], Optional[Dict[str, Any]]]:
    install_plan, install_plan_error = _resolve_manifest_install_plan(
        kit_slug,
        studio_dir,
        manifest,
        kit_path,
        artifacts.model_resources,
        interactive,
    )
    if install_plan_error is not None or install_plan is None:
        return None, install_plan_error
    return install_plan, None


def _load_manifest_install_artifacts_or_error(
    kit_source: Path,
    studio_dir: Path,
    kit_slug: str,
    install_context: _InstallContext,
) -> Tuple[Optional[_ManifestInstallArtifacts], Optional[Dict[str, Any]]]:
    artifacts, artifact_error = _load_manifest_install_artifacts(
        kit_source,
        studio_dir,
        kit_slug,
        install_context,
    )
    if artifact_error is not None or artifacts is None:
        return None, artifact_error
    return artifacts, None


def _prepare_install_kit_state(
    kit_source: Path,
    studio_dir: Path,
    kit_slug: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[Manifest], Path, Path, str]:
    config_dir = studio_dir / "config"
    config_kit_dir, config_kit_rel, kit_entry, has_registered_kit_path = _resolve_installed_kit_root(
        studio_dir,
        config_dir,
        kit_slug,
    )
    if config_kit_dir is None:
        return (
            _install_result_fail(
                kit_slug,
                [
                    (
                        f"Kit '{kit_slug}' is registered at absolute path "
                        f"'{config_kit_rel}' which is not accessible on this OS"
                    )
                ],
            ),
            None,
            config_dir,
            config_dir / "kits" / kit_slug,
            config_kit_rel,
        )
    if not kit_source.is_dir():
        return (
            _install_result_fail(kit_slug, [f"Kit source not found: {kit_source}"]),
            None,
            config_dir,
            config_kit_dir,
            config_kit_rel,
        )
    try:
        manifest = _load_manifest_install_adapter(kit_source, kit_slug=kit_slug)
    except (OSError, ValueError) as exc:
        return (
            _install_result_fail(kit_slug, [str(exc)]),
            None,
            config_dir,
            config_kit_dir,
            config_kit_rel,
        )
    if manifest is not None:
        return None, manifest, config_dir, config_kit_dir, (
            kit_entry.get("path", "")
            if has_registered_kit_path and isinstance(kit_entry, dict)
            else ""
        )
    return None, None, config_dir, config_kit_dir, config_kit_rel


def _read_install_local_metadata(
    kit_source: Path,
    kit_version: str,
) -> Tuple[Dict[str, str], str]:
    local_metadata: Dict[str, str] = {}
    src_conf = kit_source / _KIT_CONF_FILE
    if not src_conf.is_file():
        return local_metadata, kit_version
    conf_version = _read_kit_version(src_conf)
    if not conf_version:
        return local_metadata, kit_version
    local_metadata["conf_version"] = conf_version
    return local_metadata, kit_version or conf_version


def _build_install_success_result(
    success_context: _InstallSuccessContext,
) -> Dict[str, Any]:
    errors: List[str] = []
    meta = _collect_registered_kit_metadata(
        success_context.studio_dir,
        success_context.kit_slug,
        {"path": success_context.config_kit_rel},
    )
    legacy_manifest_warning = _legacy_manifest_install_warning(success_context.kit_source)
    if legacy_manifest_warning:
        errors.append(legacy_manifest_warning)
    return {
        "status": "PASS",
        "action": "installed",
        "kit": success_context.kit_slug,
        "version": success_context.kit_version,
        "install_mode": success_context.install_mode,
        "files_copied": sum(
            1 for value in success_context.copy_actions.values() if value == "copied"
        ),
        "local_metadata": success_context.local_metadata,
        "errors": errors,
        "skill_nav": meta.get("skill_nav", ""),
        "agents_content": meta.get("agents_content", ""),
        "actions": success_context.actions,
    }


def _install_manifest_kit(
    kit_source: Path,
    studio_dir: Path,
    kit_slug: str,
    kit_version: str,
    manifest: Manifest,
    install_context: _InstallContext,
    config_kit_rel: str,
) -> Dict[str, Any]:
    install_result = install_kit_with_manifest(
        kit_source,
        studio_dir,
        kit_slug,
        kit_version,
        manifest,
        install_context=install_context,
        kit_path=config_kit_rel,
    )
    legacy_manifest_warning = _legacy_manifest_install_warning(kit_source)
    if legacy_manifest_warning:
        install_result.setdefault("errors", [])
        install_result["errors"] = list(install_result.get("errors", []))
        install_result["errors"].append(legacy_manifest_warning)
    return install_result


def _install_legacy_kit_copy(
    kit_source: Path,
    studio_dir: Path,
    kit_slug: str,
    kit_version: str,
    install_context: _InstallContext,
    config_dir: Path,
    config_kit_dir: Path,
    config_kit_rel: str,
) -> Dict[str, Any]:
    actions: Dict[str, str] = {}
    copy_actions = _copy_kit_content(kit_source, config_kit_dir)
    actions.update(copy_actions)
    local_metadata, kit_version = _read_install_local_metadata(kit_source, kit_version)
    scripts_dir = config_kit_dir / "scripts"
    if scripts_dir.is_dir():
        _seed_kit_config_files(scripts_dir, config_dir, actions)
    registration_errors = _register_kit_in_core_toml(
        config_dir,
        kit_slug,
        kit_version,
        studio_dir,
        _RegisterKitContext(
            source=install_context.source,
            install_mode=install_context.install_mode,
            authority_metadata=install_context.authority_metadata,
            local_metadata=local_metadata or None,
        ),
    )
    if registration_errors:
        return _install_result_fail(
            kit_slug,
            registration_errors,
            version=kit_version,
            install_mode=install_context.install_mode,
            files_copied=sum(1 for value in copy_actions.values() if value == "copied"),
            actions=actions,
        )
    return _build_install_success_result(
        _InstallSuccessContext(
            studio_dir=studio_dir,
            kit_slug=kit_slug,
            kit_version=kit_version,
            install_mode=install_context.install_mode,
            config_kit_rel=config_kit_rel,
            kit_source=kit_source,
            local_metadata=local_metadata,
            actions=actions,
            copy_actions=copy_actions,
        ),
    )


def _load_manifest_install_artifacts(
    kit_source: Path,
    studio_dir: Path,
    kit_slug: str,
    install_context: _InstallContext,
) -> Tuple[Optional[_ManifestInstallArtifacts], Optional[Dict[str, Any]]]:
    try:
        from ..utils.kit_model import load_kit_model

        kit_model = load_kit_model(kit_source, kit_slug=kit_slug)
    except (OSError, ValueError) as exc:
        return None, _install_result_fail(kit_slug, [str(exc)])
    risk_errors = _tool_risk_approval_errors(
        kit_model,
        interactive=install_context.interactive,
        approved_tool_risks=install_context.approved_tool_risks,
    )
    if risk_errors:
        return None, _install_result_fail(
            kit_slug,
            risk_errors,
            install_mode=install_context.install_mode,
        )
    name_conflicts = _public_component_name_conflicts(studio_dir, kit_slug, kit_model)
    if name_conflicts:
        return None, _install_result_fail(
            kit_slug,
            name_conflicts,
            install_mode=install_context.install_mode,
        )
    model_resources = list(getattr(kit_model, "resources", []))
    return _ManifestInstallArtifacts(
        kit_model=kit_model,
        model_resources=model_resources,
        extra_subagent_sources=_manifest_public_subagent_sources(model_resources),
    ), None


def _prepare_manifest_install_state(
    kit_source: Path,
    studio_dir: Path,
    kit_slug: str,
    manifest: Manifest,
    install_context: _InstallContext,
) -> Tuple[Optional[_ManifestInstallArtifacts], Optional[Dict[str, Any]], Path]:
    from ..utils.manifest import validate_manifest

    config_dir = studio_dir / "config"
    validation_errors = validate_manifest(manifest, kit_source)
    if validation_errors:
        return None, _install_result_fail(kit_slug, validation_errors), config_dir
    if install_context.install_mode not in {"copy", "register"}:
        return None, _install_result_fail(
            kit_slug,
            [f"Unsupported install mode: {install_context.install_mode}"],
        ), config_dir
    artifacts, artifact_error = _load_manifest_install_artifacts_or_error(
        kit_source,
        studio_dir,
        kit_slug,
        install_context,
    )
    return artifacts, artifact_error, config_dir


def _install_manifest_copy_mode(  # pylint: disable=too-many-arguments
    kit_source: Path,
    studio_dir: Path,
    _config_dir: Path,
    kit_slug: str,
    kit_version: str,
    manifest: Manifest,
    artifacts: _ManifestInstallArtifacts,
    install_context: _InstallContext,
    kit_path: str,
) -> Dict[str, Any]:
    install_plan, install_error = _prepare_manifest_copy_install(
        studio_dir,
        kit_slug,
        manifest,
        kit_path,
        artifacts,
        install_context.interactive,
    )
    if install_error is not None:
        return install_error
    assert install_plan is not None

    overwrite_errors = _preflight_manifest_copy_overwrites(
        kit_source,
        studio_dir,
        artifacts.model_resources,
        install_plan.resource_bindings,
        interactive=install_context.interactive,
        approved_overwrites=install_context.approved_overwrites,
    )
    if overwrite_errors:
        return _install_result_fail(
            kit_slug,
            overwrite_errors,
            install_mode=install_context.install_mode,
        )
    subagent_source_error = _validate_manifest_public_subagent_sources(
        kit_source,
        artifacts.extra_subagent_sources,
    )
    if subagent_source_error:
        return _install_result_fail(
            kit_slug,
            [subagent_source_error],
            install_mode=install_context.install_mode,
        )
    files_copied = _copy_manifest_install_payload(
        kit_source,
        studio_dir,
        artifacts,
        install_plan,
    )
    _preserve_template_variables(
        install_plan.kit_root,
        install_plan.resource_bindings,
    )
    return _finalize_manifest_copy_install(
        kit_source,
        studio_dir,
        kit_slug,
        kit_version,
        manifest,
        install_context,
        install_plan,
        files_copied,
    )


def _register_manifest_install_in_place(
    kit_source: Path,
    studio_dir: Path,
    config_dir: Path,
    kit_slug: str,
    kit_version: str,
    manifest: Manifest,
    artifacts: _ManifestInstallArtifacts,
    install_context: _InstallContext,
) -> Dict[str, Any]:
    containment_errors = _validate_register_manifest_containment(
        install_context.project_root,
        studio_dir,
        kit_source,
        kit_slug,
        manifest,
    )
    if containment_errors:
        return _install_result_fail(
            kit_slug,
            containment_errors,
            install_mode=install_context.install_mode,
        )
    resource_bindings = _manifest_register_resource_bindings(
        studio_dir,
        kit_source,
        artifacts.model_resources,
    )
    kit_root_rel = _serialize_manifest_binding_path(kit_source.resolve(), studio_dir)
    local_metadata, resolved_version = _read_install_local_metadata(kit_source, kit_version)
    registration_errors = _register_kit_in_core_toml(
        config_dir,
        kit_slug,
        resolved_version,
        studio_dir,
        _RegisterKitContext(
            source=install_context.source,
            resources=resource_bindings,
            kit_path=kit_root_rel,
            install_mode=install_context.install_mode,
            source_provenance=_local_path_provenance(
                kit_source,
                install_context.install_mode,
                studio_dir,
            ),
            authority_metadata=install_context.authority_metadata,
            local_metadata=local_metadata or None,
            tool_risk_fingerprint=str(
                getattr(artifacts.kit_model, "tool_risk_fingerprint", "") or ""
            ),
        ),
    )
    if registration_errors:
        return _install_result_fail(
            kit_slug,
            registration_errors,
            install_mode=install_context.install_mode,
        )
    meta = _collect_registered_kit_metadata(
        studio_dir,
        kit_slug,
        {"path": kit_root_rel, "resources": resource_bindings},
    )
    return {
        "status": "PASS",
        "action": "installed",
        "kit": kit_slug,
        "version": resolved_version,
        "install_mode": install_context.install_mode,
        "files_copied": 0,
        "files_registered": len(resource_bindings),
        "resource_bindings": {key: value["path"] for key, value in resource_bindings.items()},
        "local_metadata": local_metadata,
        "errors": [],
        "skill_nav": meta.get("skill_nav", ""),
        "agents_content": meta.get("agents_content", ""),
    }


def _resolve_manifest_install_plan(
    kit_slug: str,
    studio_dir: Path,
    manifest: Manifest,
    kit_path: str,
    model_resources: List[Any],
    interactive: bool,
) -> Tuple[Optional[_ManifestInstallPlan], Optional[Dict[str, Any]]]:
    if kit_path:
        kit_root_rel = _normalize_registered_kit_path(kit_path, kit_slug)
        kit_root = _resolve_registered_kit_dir(studio_dir, kit_path)
        if kit_root is None:
            return None, _install_result_fail(
                kit_slug,
                [
                    (
                        f"Kit '{kit_slug}' is registered at absolute path "
                        f"'{kit_root_rel}' which is not accessible on this OS"
                    )
                ],
            )
    else:
        kit_root_rel = manifest.root.replace("{cf-studio-path}", ".").replace(
            "{slug}",
            kit_slug,
        )
        kit_root = (studio_dir / kit_root_rel).resolve()
    planned_root, planned_root_rel, resource_bindings = _prompt_manifest_install_plan(
        kit_slug,
        studio_dir,
        kit_root,
        manifest,
        resources=model_resources,
        registered_kit_root_rel=kit_root_rel,
        interactive=interactive,
    )
    return _ManifestInstallPlan(
        kit_root=planned_root,
        kit_root_rel=planned_root_rel,
        resource_bindings=resource_bindings,
    ), None


def _copy_manifest_install_payload(
    kit_source: Path,
    studio_dir: Path,
    artifacts: _ManifestInstallArtifacts,
    install_plan: _ManifestInstallPlan,
) -> int:
    files_copied = 0
    install_plan.kit_root.mkdir(parents=True, exist_ok=True)
    for res in artifacts.model_resources:
        binding_path = install_plan.resource_bindings[res.id]["path"]
        _copy_manifest_resource(kit_source, res, (studio_dir / binding_path).resolve())
        files_copied += 1
    for subagent_source in artifacts.extra_subagent_sources:
        source_abs = kit_source / Path(PurePosixPath(subagent_source))
        target_abs = (
            install_plan.kit_root / Path(PurePosixPath(subagent_source))
        ).resolve()
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_abs, target_abs)
        files_copied += 1
    return files_copied


def _finalize_manifest_copy_install(  # pylint: disable=too-many-locals,too-many-return-statements
    kit_source: Path,
    studio_dir: Path,
    kit_slug: str,
    kit_version: str,
    manifest: Manifest,
    install_context: _InstallContext,
    install_plan: _ManifestInstallPlan,
    files_copied: int,
) -> Dict[str, Any]:
    config_dir = studio_dir / "config"
    local_metadata, resolved_version = _read_install_local_metadata(kit_source, kit_version)
    scripts_dir = install_plan.kit_root / "scripts"
    if scripts_dir.is_dir():
        _seed_kit_config_files(scripts_dir, config_dir, {})
    registration_errors = _register_kit_in_core_toml(
        config_dir,
        kit_slug,
        resolved_version,
        studio_dir,
        _RegisterKitContext(
            source=install_context.source,
            resources=install_plan.resource_bindings,
            kit_path=install_plan.kit_root_rel,
            install_mode=install_context.install_mode,
            authority_metadata=install_context.authority_metadata,
            local_metadata=local_metadata or None,
            tool_risk_fingerprint=str(
                getattr(manifest, "tool_risk_fingerprint", "") or ""
            ),
        ),
    )
    if registration_errors:
        return _install_result_fail(
            kit_slug,
            registration_errors,
            install_mode=install_context.install_mode,
            files_copied=files_copied,
        )
    meta = _collect_registered_kit_metadata(
        studio_dir,
        kit_slug,
        {"path": install_plan.kit_root_rel, "resources": install_plan.resource_bindings},
    )
    return {
        "status": "PASS",
        "action": "installed",
        "kit": kit_slug,
        "version": resolved_version,
        "install_mode": install_context.install_mode,
        "files_copied": files_copied,
        "resource_bindings": {
            key: value["path"] for key, value in install_plan.resource_bindings.items()
        },
        "local_metadata": local_metadata,
        "errors": [],
        "skill_nav": meta.get("skill_nav", ""),
        "agents_content": meta.get("agents_content", ""),
    }


# ---------------------------------------------------------------------------
# Core kit installation logic (used by both cmd_kit_install and init)
# ---------------------------------------------------------------------------

# @cpt-dod:cpt-studio-dod-kit-install:p1
# @cpt-state:cpt-studio-state-kit-installation:p1
# @cpt-algo:cpt-studio-algo-kit-install:p1
def install_kit(  # pylint: disable=too-many-arguments,too-many-locals
    kit_source: Path,
    studio_dir: Path,
    kit_slug: str,
    kit_version: str = "",
    install_context: Optional[_InstallContext] = None,
    *,
    interactive: Optional[bool] = None,
    install_mode: Optional[str] = None,
    project_root: Optional[Path] = None,
    source: Optional[str] = None,
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
    install_context = _merge_install_context(
        install_context,
        interactive=interactive,
        install_mode=install_mode,
        project_root=project_root,
        source=source,
        authority_metadata=authority_metadata,
        approved_overwrites=approved_overwrites,
        approved_tool_risks=approved_tool_risks,
    )
    kit_source = kit_source.resolve()
    studio_dir = studio_dir.resolve()
    install_error, manifest, config_dir, config_kit_dir, config_kit_rel = _prepare_install_kit_state(
        kit_source,
        studio_dir,
        kit_slug,
    )
    if install_error is not None:
        return install_error
    if manifest is not None:
        return _install_manifest_kit(
            kit_source,
            studio_dir,
            kit_slug,
            kit_version,
            manifest,
            install_context,
            config_kit_rel,
        )
    # @cpt-end:cpt-studio-algo-kit-install:p1:inst-manifest-install

    if install_context.install_mode != "copy":
        return _install_result_fail(
            kit_slug,
            [f"Unsupported install mode: {install_context.install_mode}"],
        )
    return _install_legacy_kit_copy(
        kit_source,
        studio_dir,
        kit_slug,
        kit_version,
        install_context,
        config_dir,
        config_kit_dir,
        config_kit_rel,
    )


# ---------------------------------------------------------------------------
# Manifest-driven kit installation
# ---------------------------------------------------------------------------

# @cpt-algo:cpt-studio-algo-kit-manifest-install:p1
def install_kit_with_manifest(  # pylint: disable=too-many-arguments,too-many-locals
    kit_source: Path,
    studio_dir: Path,
    kit_slug: str,
    kit_version: str,
    manifest: Manifest,
    kit_path: str = "",
    install_context: Optional[_InstallContext] = None,
    *,
    interactive: Optional[bool] = None,
    install_mode: Optional[str] = None,
    project_root: Optional[Path] = None,
    source: Optional[str] = None,
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
    install_context = _merge_install_context(
        install_context,
        interactive=interactive,
        install_mode=install_mode,
        project_root=project_root,
        source=source,
        authority_metadata=authority_metadata,
        approved_overwrites=approved_overwrites,
        approved_tool_risks=approved_tool_risks,
    )
    kit_source = kit_source.resolve()
    studio_dir = studio_dir.resolve()
    artifacts, install_error, config_dir = _prepare_manifest_install_state(
        kit_source,
        studio_dir,
        kit_slug,
        manifest,
        install_context,
    )
    if install_error is not None:
        return install_error
    assert artifacts is not None

    if install_context.install_mode == "register":
        return _register_manifest_install_in_place(
            kit_source,
            studio_dir,
            config_dir,
            kit_slug,
            kit_version,
            manifest,
            artifacts,
            install_context,
        )
    return _install_manifest_copy_mode(
        kit_source,
        studio_dir,
        config_dir,
        kit_slug,
        kit_version,
        manifest,
        artifacts,
        install_context,
        kit_path,
    )


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


def _directory_resource_changed(source_abs: Path, target_abs: Path) -> bool:
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
    return _directory_resource_changed(source_abs, target_abs)


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
        _ui_lines("Dangerous tool permissions changed:", blank_before=True)
        for resource_id, tools in sorted(dangerous.items()):
            ui.info(f"  - {resource_id}: {', '.join(tools)}")
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


def _load_manifest_for_legacy_migration(  # pylint: disable=too-many-locals
    kit_source: Path,
    kit_slug: str,
) -> Tuple[Optional[Manifest], Optional[Dict[str, Any]]]:
    from ..utils.manifest import validate_manifest

    try:
        manifest = _load_manifest_install_adapter(kit_source, kit_slug=kit_slug)
    except (OSError, ValueError) as exc:
        return None, {
            "status": "FAIL",
            "kit": kit_slug,
            "errors": [str(exc)],
        }
    if manifest is None:
        return None, {
            "status": "SKIP",
            "kit": kit_slug,
            "message": "No manifest-backed kit source",
        }
    validation_errors = validate_manifest(manifest, kit_source)
    if validation_errors:
        return None, {
            "status": "FAIL",
            "kit": kit_slug,
            "errors": validation_errors,
        }
    return manifest, None


def _migrate_legacy_manifest_resource(
    kit_source: Path,
    studio_dir: Path,
    kit_root: Path,
    res: Any,
    *,
    interactive: bool,
) -> Tuple[Dict[str, Dict[str, str]], int, int]:
    expected_path = kit_root / res.default_path
    if expected_path.exists():
        binding_path = _serialize_manifest_binding_path(expected_path, studio_dir)
        return {str(res.id): _manifest_resource_binding_entry(res=res, path=binding_path)}, 1, 0

    target_abs = expected_path
    if interactive and res.user_modifiable and sys.stdin.isatty():
        try:
            user_input = input(
                "Why this input is needed: choose where this resource should be installed.\n"
                "Press Enter to accept the suggested path, or type a different absolute "
                "path or a path relative to the kit root.\n"
                "Suggested: keep the default unless this resource must live somewhere else in your project.\n"
                f"New resource '{res.id}' path [{expected_path}]: "
            ).strip()
            if user_input:
                user_path = Path(user_input)
                target_abs = user_path if user_path.is_absolute() else (kit_root / user_path).resolve()
        except (EOFError, KeyboardInterrupt):
            pass

    _copy_manifest_resource(kit_source, res, target_abs)
    binding_path = _serialize_manifest_binding_path(target_abs, studio_dir)
    return {str(res.id): _manifest_resource_binding_entry(res=res, path=binding_path)}, 0, 1


def _resolve_legacy_manifest_kit_root(
    studio_dir: Path,
    config_dir: Path,
    kit_slug: str,
) -> Tuple[Optional[Path], Optional[Dict[str, Any]]]:
    kit_root, kit_root_rel, _kit_entry, _has_registered_path = _resolve_installed_kit_root(
        studio_dir,
        config_dir,
        kit_slug,
    )
    if kit_root is None:
        return None, {
            "status": "FAIL",
            "kit": kit_slug,
            "errors": [
                f"Kit '{kit_slug}' is registered at absolute path '{kit_root_rel}' which is not accessible on this OS",
            ],
        }
    return kit_root, None


def _register_legacy_manifest_bindings(
    config_dir: Path,
    kit_slug: str,
    studio_dir: Path,
    manifest: Manifest,
    resource_bindings: Dict[str, Dict[str, str]],
    kit_root: Path,
) -> Optional[Dict[str, Any]]:
    registration_errors = _register_kit_in_core_toml(
        config_dir,
        kit_slug,
        "",
        studio_dir,
        _RegisterKitContext(
            resources=resource_bindings,
            kit_path=_resolve_manifest_kit_root_rel(
                manifest,
                resource_bindings,
                kit_slug,
            ),
            tool_risk_fingerprint=str(
                getattr(manifest, "tool_risk_fingerprint", "") or ""
            ),
        ),
    )
    if registration_errors:
        return {
            "status": "FAIL",
            "kit": kit_slug,
            "errors": registration_errors,
        }
    _preserve_template_variables(kit_root, resource_bindings)
    return None


# ---------------------------------------------------------------------------
# Legacy Install Migration — auto-populate resource bindings from disk
# ---------------------------------------------------------------------------

# @cpt-algo:cpt-studio-algo-kit-manifest-legacy-migration:p1
def migrate_legacy_kit_to_manifest(  # pylint: disable=too-many-locals
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
    config_dir = studio_dir / "config"
    resource_bindings: Dict[str, Dict[str, str]] = {}
    migrated_count = 0  # existing files registered silently
    new_count = 0       # new files copied from source

    manifest, manifest_error = _load_manifest_for_legacy_migration(kit_source, kit_slug)
    if manifest_error is not None:
        return manifest_error
    assert manifest is not None

    kit_root, root_error = _resolve_legacy_manifest_kit_root(
        studio_dir,
        config_dir,
        kit_slug,
    )
    if root_error is not None:
        return root_error
    assert kit_root is not None

    for res in manifest.resources:
        migrated_binding, migrated_delta, new_delta = _migrate_legacy_manifest_resource(
            kit_source,
            studio_dir,
            kit_root,
            res,
            interactive=interactive,
        )
        resource_bindings.update(migrated_binding)
        migrated_count += migrated_delta
        new_count += new_delta

    registration_error = _register_legacy_manifest_bindings(
        config_dir,
        kit_slug,
        studio_dir,
        manifest,
        resource_bindings,
        kit_root,
    )
    if registration_error is not None:
        return registration_error

    return {
        "status": "PASS",
        "kit": kit_slug,
        "migrated_count": migrated_count,
        "new_count": new_count,
        "resource_bindings": {k: v["path"] for k, v in resource_bindings.items()},
    }


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
        logger.warning("Invalid GitHub kit source %r: %s", source_arg, exc)
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
        logger.exception("Failed to download GitHub kit source for %s/%s", owner, repo)
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
        logger.warning("Invalid Git kit source %r: %s", source_arg, exc)
        ui.result({
            "status": "FAIL",
            "message": str(exc),
            **exc.to_result(),
        })
        return None
    except RuntimeError as exc:
        logger.exception("Failed to resolve Git kit source %r", source_arg)
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


def _resolve_cmd_kit_install_source(args: argparse.Namespace) -> Tuple[Optional[_KitInstallSourceState], int]:
    source_registration = ""
    authority_metadata: Optional[Dict[str, Any]] = None
    tmp_dir_to_clean: Optional[Path] = None
    if args.local_path:
        kit_source = Path(args.local_path).resolve()
        if not kit_source.is_dir():
            ui.result({
                "status": "FAIL",
                "message": f"Kit source directory not found: {kit_source}",
                "hint": "Provide a path to a valid kit directory",
            })
            return None, 2
        if not args.dry_run and not args.install_mode and not sys.stdin.isatty():
            ui.result({
                "status": "FAIL",
                "message": "Non-interactive local installs require --install-mode copy|register",
                "hint": (
                    "Use --install-mode copy to copy resources into Studio storage, or "
                    "--install-mode register for eligible in-project sources"
                ),
            })
            return None, 2
        return _KitInstallSourceState(
            kit_source=kit_source,
            kit_slug=_read_kit_slug(kit_source) or kit_source.name,
            kit_version=_read_kit_source_version(kit_source),
            source_registration="",
            tmp_dir_to_clean=None,
            authority_metadata=None,
        ), 0
    if source_is_generic_git(args.source):
        resolved_source = _resolve_install_source_git(args.source, args.version)
    else:
        resolved_source = _resolve_install_source_github(args.source, args.version)
    if resolved_source is None:
        return None, 2
    (
        kit_source,
        kit_slug,
        kit_version,
        source_registration,
        tmp_dir_to_clean,
        exit_code,
        authority_metadata,
    ) = resolved_source
    if exit_code is not None:
        if tmp_dir_to_clean:
            shutil.rmtree(tmp_dir_to_clean, ignore_errors=True)
        return None, exit_code
    return _KitInstallSourceState(
        kit_source=kit_source,
        kit_slug=kit_slug,
        kit_version=kit_version,
        source_registration=source_registration,
        tmp_dir_to_clean=tmp_dir_to_clean,
        authority_metadata=authority_metadata,
    ), 0


def _build_install_context_from_args(
    args: argparse.Namespace,
    execution: _KitInstallExecution,
) -> _InstallContext:
    return _InstallContext(
        interactive=True,
        install_mode=execution.selected_install_mode,
        project_root=execution.project_root,
        source=execution.source_registration,
        authority_metadata=execution.authority_metadata,
        approved_overwrites=list(args.approve_overwrite),
        approved_tool_risks=list(args.approve_tool_risk),
    )


def _run_multi_kit_install(
    args: argparse.Namespace,
    execution: _KitInstallExecution,
    kit_source: Path,
    selected_specs: List[Tuple[str, str]],
) -> int:
    preflight_errors: List[str] = []
    dry_run_results: List[Dict[str, Any]] = []
    for selected_slug, selected_version in selected_specs:
        selected_dir, _, _, _ = _resolve_installed_kit_root(
            execution.studio_dir, execution.config_dir, selected_slug,
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
            "source": execution.source_registration or kit_source.as_posix(),
        })
        return 0
    install_context = _build_install_context_from_args(args, execution)
    results: List[Dict[str, Any]] = []
    failed = False
    for selected_slug, selected_version in selected_specs:
        result = install_kit(
            kit_source,
            execution.studio_dir,
            selected_slug,
            selected_version,
            install_context,
        )
        if str(result.get("status", "")).upper() == "FAIL":
            failed = True
        elif execution.selected_tracking is not None:
            _persist_installed_kit_tracking(
                execution.project_root,
                execution.studio_dir,
                selected_slug,
                execution.selected_tracking,
            )
        results.append({
            "status": result.get("status", "PASS"),
            "action": result.get("action", "installed"),
            "kit": selected_slug,
            "version": selected_version,
            "install_mode": result.get("install_mode", execution.selected_install_mode),
            "files_written": result.get("files_copied", 0),
            "files_registered": result.get("files_registered", 0),
            "errors": result.get("errors", []),
        })
    if not failed:
        regenerate_gen_aggregates(execution.studio_dir)
    ui.result({
        "status": "FAIL" if failed else "PASS",
        "action": "installed",
        "kits_installed": 0 if failed else len(results),
        "results": results,
        "source": execution.source_registration or kit_source.as_posix(),
    })
    return 2 if failed else 0


def _run_single_kit_install(
    args: argparse.Namespace,
    execution: _KitInstallExecution,
    kit_source: Path,
    kit_slug: str,
    kit_version: str,
) -> int:
    config_kit_dir, _, _, _ = _resolve_installed_kit_root(
        execution.studio_dir,
        execution.config_dir,
        kit_slug,
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
    if config_kit_dir.exists() and not args.force:
        ui.result(
            {
                "status": "FAIL",
                "kit": kit_slug,
                "message": f"Kit '{kit_slug}' is already installed at {config_kit_dir}",
                "hint": (
                    "Use 'cfs kit update' to update, or "
                    f"'cfs kit install {args.source or args.local_path} --force' "
                    "to reinstall"
                ),
            },
            human_fn=_human_kit_install,
        )
        return 2
    if args.dry_run:
        ui.result({
            "status": "DRY_RUN",
            "kit": kit_slug,
            "version": kit_version,
            "source": execution.source_registration or kit_source.as_posix(),
            "target": config_kit_dir.as_posix(),
        })
        return 0
    result = install_kit(
        kit_source,
        execution.studio_dir,
        kit_slug,
        kit_version,
        _build_install_context_from_args(args, execution),
    )
    if (
        str(result.get("status", "")).upper() != "FAIL"
        and execution.selected_tracking is not None
    ):
        _persist_installed_kit_tracking(
            execution.project_root,
            execution.studio_dir,
            kit_slug,
            execution.selected_tracking,
        )
    output: Dict[str, Any] = {
        "status": result.get("status", "FAIL"),
        "action": result.get("action", "installed"),
        "kit": kit_slug,
        "version": kit_version,
        "install_mode": result.get("install_mode", execution.selected_install_mode),
        "files_written": result.get("files_copied", 0),
    }
    if result.get("files_registered") is not None:
        output["files_registered"] = result.get("files_registered", 0)
    if execution.source_registration:
        output["source"] = execution.source_registration
    if execution.authority_metadata:
        output["authority"] = (
            _authority_result_summary(execution.authority_metadata)
            or execution.authority_metadata
        )
    if result.get("local_metadata"):
        output["local_metadata"] = result["local_metadata"]
    if result.get("errors"):
        output["errors"] = result["errors"]
    ui.result(output, human_fn=_human_kit_install)
    if str(result.get("status", "")).upper() == "FAIL":
        return 2
    regenerate_gen_aggregates(execution.studio_dir)
    return 0


def _build_kit_install_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kit install",
        description="Install a kit package from GitHub or a local directory",
    )
    parser.add_argument(
        "source", nargs="?", default=None,
        help="GitHub owner/repo[@version], generic Git git/<url>[//<subdir>][@<kit>], or local path/<dir>",
    )
    parser.add_argument(
        "--path", dest="local_path", default=None,
        help="Install from a local directory instead of GitHub",
    )
    parser.add_argument(
        "--version", dest="version", default="",
        help="For GitHub and generic Git sources, resolve this tag, branch, or full 40-character commit SHA",
    )
    parser.add_argument(
        "--install-mode",
        choices=("copy", "register"),
        default="",
        help="For local manifest installs, choose copy into Studio storage or register in place",
    )
    parser.add_argument(
        "--kit",
        action="append",
        default=[],
        metavar="SLUG",
        help="Select a kit from a multi-kit .cf-studio-kit.toml; repeat, use comma-separated slugs, or use 'all'",
    )
    parser.add_argument(
        "--approve-overwrite",
        action="append",
        default=[],
        metavar="RESOURCE_OR_PATH",
        help=(
            "Approve overwriting one changed user-modifiable manifest resource by id "
            "or effective path; repeat per resource"
        ),
    )
    parser.add_argument(
        "--approve-tool-risk",
        action="append",
        default=[],
        metavar="FINGERPRINT",
        help="Approve one dangerous tool-risk fingerprint; repeat when needed",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing kit")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    return parser


def _validate_cmd_kit_install_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> int:
    args.source, args.local_path, local_path_error = _normalize_local_path_source_arg(
        source_value=args.source,
        local_path=args.local_path,
        arg_name="source",
    )
    if local_path_error:
        ui.result(local_path_error)
        return 2
    if not args.source and not args.local_path:
        parser.error("Provide a GitHub source (owner/repo) or --path for a local directory")
    if args.source and args.local_path:
        parser.error("Cannot use both positional source and --path")
    if args.install_mode and not args.local_path:
        ui.result({
            "status": "FAIL",
            "message": "--install-mode is only valid with local --path installs",
            "hint": "Remote GitHub and generic Git installs always copy managed artifacts",
        })
        return 2
    if not args.local_path:
        return 0
    conflict = _validate_kit_source_mode(
        local_path=args.local_path,
        version=args.version,
    )
    if conflict:
        ui.result(conflict)
        return 2
    return 0


def _selected_install_specs(
    args: argparse.Namespace,
    source_state: _KitInstallSourceState,
) -> Tuple[List[Tuple[str, str]], Optional[Dict[str, Any]]]:
    requested_kits = list(args.kit)
    authority_metadata = source_state.authority_metadata
    if (
        not requested_kits
        and authority_metadata
        and str(authority_metadata.get("kit_identity") or "").strip()
    ):
        requested_kits = [str(authority_metadata.get("kit_identity") or "").strip()]
    selected_models, selection_error = _select_canonical_kit_models_for_install(
        source_state.kit_source,
        requested_kits,
        interactive=sys.stdin.isatty(),
    )
    if selection_error is not None:
        return [], selection_error
    selected_specs = [
        (str(model.slug), str(model.version or source_state.kit_version))
        for model in selected_models
    ]
    if selected_specs:
        return selected_specs, None
    return [(source_state.kit_slug, source_state.kit_version)], None


def _resolve_selected_install_mode(
    args: argparse.Namespace,
    project_root: Path,
    studio_dir: Path,
    kit_source: Path,
    kit_slug: str,
) -> str:
    selected_install_mode = args.install_mode or "copy"
    if args.local_path and not args.install_mode and sys.stdin.isatty():
        try:
            local_manifest = _load_manifest_install_adapter(kit_source, kit_slug=kit_slug)
        except (OSError, ValueError) as exc:
            logger.debug(
                "kit: failed to inspect manifest install adapter for %s",
                kit_source,
                exc_info=exc,
            )
            local_manifest = None
        if local_manifest is not None:
            selected_install_mode = _prompt_local_manifest_install_mode(
                project_root,
                studio_dir,
                kit_source,
                kit_slug,
                local_manifest,
            )
    return selected_install_mode


def _resolve_kit_install_execution(
    args: argparse.Namespace,
    source_state: _KitInstallSourceState,
    kit_slug: str,
) -> Tuple[Optional[_KitInstallExecution], int]:
    resolved = _resolve_studio_dir()
    if resolved is None:
        return None, 1
    project_root, studio_dir = resolved
    config_dir = studio_dir / "config"
    selected_install_mode = _resolve_selected_install_mode(
        args,
        project_root,
        studio_dir,
        source_state.kit_source,
        kit_slug,
    )
    selected_tracking: Optional[str] = None
    if selected_install_mode != "register" and not args.dry_run and sys.stdin.isatty():
        selected_tracking = _prompt_git_tracking_for_installed_kit(
            config_dir / _KIT_CORE_TOML,
            kit_slug,
        )
    return _KitInstallExecution(
        studio_dir=studio_dir,
        config_dir=config_dir,
        project_root=project_root,
        selected_install_mode=selected_install_mode,
        selected_tracking=selected_tracking,
        source_registration=source_state.source_registration,
        authority_metadata=source_state.authority_metadata,
    ), 0


# @cpt-flow:cpt-studio-flow-kit-install-cli:p1
def cmd_kit_install(argv: List[str]) -> int:  # pylint: disable=too-many-locals
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
    p = _build_kit_install_parser()
    args = p.parse_args(argv)
    validation_code = _validate_cmd_kit_install_args(args, p)
    if validation_code:
        return validation_code
    # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-parse-args

    source_state, source_exit_code = _resolve_cmd_kit_install_source(args)
    if source_state is None:
        return source_exit_code
    selected_specs, selection_error = _selected_install_specs(args, source_state)
    if selection_error is not None:
        ui.result(selection_error)
        return 2
    kit_slug, kit_version = selected_specs[0]
    # @cpt-end:cpt-studio-flow-kit-install-cli:p1:inst-validate-source

    try:
        execution, execution_code = _resolve_kit_install_execution(
            args,
            source_state,
            kit_slug,
        )
        if execution is None:
            return execution_code
        if len(selected_specs) > 1:
            return _run_multi_kit_install(
                args,
                execution,
                kit_source=source_state.kit_source,
                selected_specs=selected_specs,
            )

        return _run_single_kit_install(
            args,
            execution,
            kit_source=source_state.kit_source,
            kit_slug=kit_slug,
            kit_version=kit_version,
        )

    finally:
        # @cpt-begin:cpt-studio-flow-kit-install-cli:p1:inst-cleanup-tmp
        if source_state.tmp_dir_to_clean:
            shutil.rmtree(source_state.tmp_dir_to_clean, ignore_errors=True)
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
        target, failure = _resolve_github_update_target(slug, kit_data)
        if failure is not None:
            failures.append(failure)
            continue
        assert target is not None
        targets.append(target)
    return targets, failures
# @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-resolve-github-targets


def _resolve_github_update_target(
    slug: str,
    kit_data: Dict[str, Any],
) -> Tuple[
    Optional[Tuple[str, Path, str, Optional[Path], Optional[Dict[str, Any]]]],
    Optional[Dict[str, Any]],
]:
    source_str = kit_data.get("source", "")
    if not source_str:
        msg = f"Kit '{slug}' has no registered source — skipping"
        ui.warn(msg)
        return None, {"kit": slug, "action": "ERROR", "message": msg}
    if not source_str.startswith("github:"):
        msg = f"Kit '{slug}': unsupported source type '{source_str}' — skipping"
        ui.warn(msg)
        return None, {"kit": slug, "action": "ERROR", "message": msg, "source": source_str}

    owner_repo = source_str.removeprefix("github:")
    try:
        owner, repo, version = _parse_github_source(owner_repo)
    except ValueError as exc:
        msg = f"Kit '{slug}': invalid source '{source_str}': {exc}"
        logger.warning("Kit '%s' has invalid GitHub source %r: %s", slug, source_str, exc)
        ui.warn(msg)
        return None, {"kit": slug, "action": "ERROR", "message": msg, "source": source_str}

    ui.step(f"Downloading {owner}/{repo}...")
    try:
        kit_source_dir, _resolved, authority_metadata = _download_kit_from_github_with_authority(
            owner,
            repo,
            version,
            previous_entry=kit_data,
        )
    except RuntimeError as exc:
        msg = f"Kit '{slug}': download failed: {exc}"
        logger.warning("Kit '%s' GitHub download failed", slug, exc_info=exc)
        ui.warn(msg)
        return None, _github_update_download_failure(
            slug,
            source_str,
            kit_data,
            owner,
            repo,
            version,
            msg,
        )
    return (slug, kit_source_dir, source_str, kit_source_dir.parent, authority_metadata), None


def _github_update_download_failure(
    slug: str,
    source_str: str,
    kit_data: Dict[str, Any],
    owner: str,
    repo: str,
    version: str,
    message: str,
) -> Dict[str, Any]:
    try:
        authority_metadata = _resolve_github_ref(
            owner,
            repo,
            version,
            previous_entry=kit_data,
        )
    except RuntimeError as exc:
        logger.debug(
            "kit: failed to refresh GitHub authority metadata for %s/%s@%s",
            owner,
            repo,
            version,
            exc_info=exc,
        )
        authority_metadata = None
    if authority_metadata and authority_metadata.get("freshness") == "last_known":
        current_version = str(kit_data.get("version") or "")
        last_known_ref = str(authority_metadata.get("resolved_ref") or "")
        if current_version and current_version == last_known_ref:
            current_message = (
                f"Kit '{slug}': GitHub unavailable; installed version "
                f"{current_version} matches last-known release authority"
            )
            ui.warn(current_message)
            return {
                "kit": slug,
                "action": "current",
                "message": current_message,
                "source": source_str,
                "authority": authority_metadata,
            }
    return {"kit": slug, "action": "failed", "message": message, "source": source_str}


def _resolve_local_update_target_failure(
    slug: str,
    kit_data: Dict[str, Any],
    source_str: str,
) -> Optional[Dict[str, Any]]:
    if source_str.startswith("git:"):
        return None
    if not source_str:
        install_mode = str(kit_data.get("install_mode") or "").strip().lower()
        if install_mode == "register":
            msg = f"Kit '{slug}' is registered in place and has no remote source — current"
            return {
                "kit": slug,
                "action": "current",
                "message": msg,
                "source": source_str,
            }
        msg = f"Kit '{slug}' has no registered source — skipping"
    else:
        msg = f"Kit '{slug}': unsupported source type '{source_str}' — skipping"
    return {"kit": slug, "action": "ERROR", "message": msg, "source": source_str}


def _resolve_git_update_target(
    slug: str,
    kit_data: Dict[str, Any],
    source_str: str,
    *,
    requested_ref_override: str,
) -> Tuple[Optional[Tuple[str, Path, str, Optional[Path], Optional[Dict[str, Any]]]], Optional[Dict[str, Any]]]:
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
        return None, {
            "kit": slug,
            "action": "ERROR",
            "message": f"Kit '{slug}': invalid Git source: {exc}",
            "source": source_str,
            **exc.to_result(),
        }
    except RuntimeError as exc:
        return None, {
            "kit": slug,
            "action": "failed",
            "message": f"Kit '{slug}': Git source resolution failed: {exc}",
            "source": source_str,
        }
    return (
        slug,
        resolution.kit_source_dir,
        parsed.canonical_source,
        resolution.tmp_dir,
        resolution.authority_metadata,
    ), None


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
        local_failure = _resolve_local_update_target_failure(slug, kit_data, source_str)
        if local_failure is not None:
            ui.warn(str(local_failure["message"]))
            failures.append(local_failure)
            continue

        target, target_error = _resolve_git_update_target(
            slug,
            kit_data,
            source_str,
            requested_ref_override=requested_ref_override,
        )
        if target_error is not None:
            ui.warn(str(target_error["message"]))
            failures.append(target_error)
            continue
        assert target is not None
        targets.append(target)

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


# @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-parse-args
def _collect_kit_update_partial_reasons(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Summarize non-pass kit update outcomes for JSON/human output."""
    # @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-build-update-result
    partials: List[Dict[str, Any]] = []
    for result in results:
        action = _normalize_kit_update_action(result.get("action"))
        if action in {"current", "updated", "created", "dry_run"}:
            continue
        kit_slug = str(result.get("kit") or "?")
        categories: List[str] = []
        entry: Dict[str, Any] = {"kit": kit_slug}
        _append_kit_update_partial_errors(result, entry, categories)
        _append_kit_update_partial_declined(result, entry, categories)
        _append_kit_update_partial_prunes(result, entry, categories)
        _append_kit_update_action_category(action, categories)
        entry["categories"] = categories or ["unspecified"]
        partials.append(entry)
    # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-build-update-result
    return partials


def _append_kit_update_partial_errors(result: Dict[str, Any], entry: Dict[str, Any], categories: List[str]) -> None:
    errors = result.get("errors") or []
    if errors:
        categories.append("errors")
        entry["errors"] = [str(err) for err in errors]


def _append_kit_update_partial_declined(result: Dict[str, Any], entry: Dict[str, Any], categories: List[str]) -> None:
    declined = result.get("declined") or []
    if declined:
        categories.append("declined_files")
        entry["declined"] = list(declined)


def _append_kit_update_partial_prunes(result: Dict[str, Any], entry: Dict[str, Any], categories: List[str]) -> None:
    prune_required = result.get("prune_required") or []
    if prune_required:
        categories.append("declined_prunes")
        entry["declined_prunes"] = [
            str(item.get("path") or "")
            for item in prune_required
            if isinstance(item, dict) and item.get("path")
        ]


def _append_kit_update_action_category(action: str, categories: List[str]) -> None:
    if action == "aborted":
        categories.append("aborted")
    elif action == "failed":
        categories.append("failed")
    elif action == "partial":
        categories.append("partial_update")
# @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-parse-args


# @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-resolve-project
def _count_kit_update_actions(
    results: List[Dict[str, Any]],
    *actions: str,
) -> int:
    """Count normalized kit update actions in ``results``."""
    # @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-build-update-result
    wanted = {action.strip().lower() for action in actions}
    return sum(
        1
        for result in results
        if _normalize_kit_update_action(result.get("action")) in wanted
    )
    # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-build-update-result
# @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-resolve-project


def _build_current_source_failure_results(
    source_failures: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    current_results: List[Dict[str, Any]] = []
    for source_failure in source_failures:
        result = {
            "kit": source_failure.get("kit", ""),
            "action": "current",
            "accepted": [],
            "declined": [],
            "files_written": 0,
            "unchanged": 0,
        }
        if source_failure.get("authority"):
            result["authority"] = (
                _authority_result_summary(source_failure.get("authority"))
                or source_failure["authority"]
            )
        current_results.append(result)
    return current_results


def _local_update_resolution(
    args: argparse.Namespace,
    project_root: Path,
    studio_dir: Path,
    config_dir: Path,
    interactive: bool,
) -> Tuple[Optional[_KitUpdateResolution], int]:
    kit_source = Path(args.local_path).resolve()
    if not kit_source.is_dir():
        ui.result({
            "status": "FAIL",
            "message": f"Kit source directory not found: {kit_source}",
            "hint": "Provide a path to a valid kit directory",
        })
        return None, 2
    return _KitUpdateResolution(
        project_root=project_root,
        studio_dir=studio_dir,
        config_dir=config_dir,
        interactive=interactive,
        update_targets=[
            _KitUpdateSourceTarget(
                kit_slug=(
                    args.slug
                    or _registered_slug_for_local_kit_path(config_dir, studio_dir, kit_source)
                    or _read_kit_slug(kit_source)
                    or kit_source.name
                ),
                kit_source=kit_source,
                github_source="",
                tmp_dir=None,
                authority_metadata=None,
            ),
        ],
        source_failures=[],
    ), 0


def _emit_empty_update_target_result(source_failures: List[Dict[str, Any]]) -> int:
    source_failure_actions = {
        _normalize_kit_update_action(source_failure.get("action"))
        for source_failure in source_failures
    }
    if source_failures and source_failure_actions <= {"current"}:
        ui.result({
            "status": "PASS",
            "kits_updated": 0,
            "results": _build_current_source_failure_results(source_failures),
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
        return 2
    ui.result({
        "status": "FAIL",
        "message": "No kits to update (no valid sources found)",
    })
    return 2


def _kit_update_source_targets(
    raw_update_targets: List[Tuple[str, Path, str, Optional[Path], Optional[Dict[str, Any]]]],
) -> List[_KitUpdateSourceTarget]:
    update_targets: List[_KitUpdateSourceTarget] = []
    for raw_target in raw_update_targets:
        if len(raw_target) == 4:
            kit_slug, kit_source, github_source, tmp_dir = raw_target
            authority_metadata = None
        else:
            kit_slug, kit_source, github_source, tmp_dir, authority_metadata = raw_target
        update_targets.append(
            _KitUpdateSourceTarget(
                kit_slug=kit_slug,
                kit_source=kit_source,
                github_source=github_source,
                tmp_dir=tmp_dir,
                authority_metadata=authority_metadata,
            ),
        )
    return update_targets


def _resolve_cmd_kit_update_targets(
    args: argparse.Namespace,
    project_root: Path,
    studio_dir: Path,
    config_dir: Path,
) -> Tuple[Optional[_KitUpdateResolution], int]:
    interactive = not args.no_interactive and sys.stdin.isatty()
    if args.local_path:
        return _local_update_resolution(
            args,
            project_root,
            studio_dir,
            config_dir,
            interactive,
        )

    kits_map = _read_kits_from_core_toml(config_dir)
    if not kits_map:
        ui.result({
            "status": "FAIL",
            "message": "No kits registered in core.toml",
            "hint": "Install a kit first: cfs kit install owner/repo",
        })
        return None, 2
    if args.slug:
        if args.slug not in kits_map:
            ui.result({
                "status": "FAIL",
                "message": f"Kit '{args.slug}' not found in core.toml",
                "hint": f"Registered kits: {', '.join(kits_map.keys())}",
            })
            return None, 2
        kits_map = {args.slug: kits_map[args.slug]}
    raw_update_targets, source_failures = _resolve_registered_update_targets(
        kits_map,
        requested_ref_override=args.version,
    )
    if not raw_update_targets:
        return None, _emit_empty_update_target_result(source_failures)
    return _KitUpdateResolution(
        project_root=project_root,
        studio_dir=studio_dir,
        config_dir=config_dir,
        interactive=interactive,
        update_targets=_kit_update_source_targets(raw_update_targets),
        source_failures=source_failures,
    ), 0


def _run_cmd_kit_update_targets(
    args: argparse.Namespace,
    resolution: _KitUpdateResolution,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    all_results: List[Dict[str, Any]] = []
    errors: List[str] = []
    for source_failure in resolution.source_failures:
        normalized_source_failure = dict(source_failure)
        normalized_source_failure["action"] = _normalize_kit_update_action(
            normalized_source_failure.get("action"),
        )
        all_results.append(normalized_source_failure)
        if normalized_source_failure["action"] != "current":
            errors.append(f"{source_failure['kit']}: {source_failure['message']}")
    for update_target in resolution.update_targets:
        if not args.dry_run:
            installed_version = _read_kit_version_from_core(
                resolution.config_dir,
                update_target.kit_slug,
            )
            acknowledged = show_kit_whatsnew(
                update_target.kit_source,
                installed_version,
                update_target.kit_slug,
                interactive=resolution.interactive and not args.yes,
            )
            if not acknowledged:
                all_results.append({
                    "kit": update_target.kit_slug,
                    "action": "aborted",
                    "accepted": [],
                    "declined": [],
                    "files_written": 0,
                })
                if update_target.tmp_dir:
                    shutil.rmtree(update_target.tmp_dir, ignore_errors=True)
                continue
        try:
            kit_result = update_kit(
                update_target.kit_slug,
                update_target.kit_source,
                resolution.studio_dir,
                _UpdateContext(
                    dry_run=args.dry_run,
                    interactive=resolution.interactive,
                    auto_approve=args.yes,
                    force=args.force,
                    source=update_target.github_source,
                    authority_metadata=update_target.authority_metadata,
                    approved_overwrites=list(args.approve_overwrite),
                    approved_tool_risks=list(args.approve_tool_risk),
                    prune_mode=args.prune,
                    approved_prunes=list(args.approve_prune),
                    project_root=resolution.project_root,
                ),
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            kit_result = {"kit": update_target.kit_slug, "version": {"status": "failed"}, "gen": {}}
            errors.append(f"{update_target.kit_slug}: {exc}")
        finally:
            if update_target.tmp_dir:
                shutil.rmtree(update_target.tmp_dir, ignore_errors=True)
        if kit_result.get("errors"):
            errors.extend(
                f"{update_target.kit_slug}: {err}"
                for err in kit_result.get("errors", [])
            )
        all_results.append(_build_kit_update_result(update_target.kit_slug, kit_result))
    return all_results, errors


def _build_cmd_kit_update_output(
    args: argparse.Namespace,
    all_results: List[Dict[str, Any]],
    errors: List[str],
    interactive: bool,
    studio_dir: Path,
) -> Tuple[Dict[str, Any], bool, bool]:
    has_failed_updates = any(
        _normalize_kit_update_action(result.get("action")) == "failed"
        for result in all_results
    )
    if not args.dry_run and not has_failed_updates:
        regenerate_gen_aggregates(studio_dir)
    n_updated = _count_kit_update_actions(all_results, "updated", "created")
    n_partial = _count_kit_update_actions(all_results, "partial")
    n_aborted = _count_kit_update_actions(all_results, "aborted")
    command_failed = has_failed_updates
    command_incomplete = n_partial > 0 or n_aborted > 0
    interactive_partial_success = bool(
        interactive and command_incomplete and not command_failed
    )
    if command_failed:
        status = "FAIL"
    elif interactive_partial_success:
        status = "PASS"
    elif command_incomplete or errors:
        status = "WARN"
    else:
        status = "PASS"
    output: Dict[str, Any] = {
        "status": status,
        "kits_updated": n_updated,
        "kits_partially_updated": n_partial,
        "kits_aborted": n_aborted,
        "results": all_results,
    }
    partial_reasons = _collect_kit_update_partial_reasons(all_results)
    if partial_reasons:
        output["partial_reasons"] = partial_reasons
    if errors:
        output["errors"] = errors
    if not n_updated and not errors and not n_aborted:
        output["message"] = "All kits are up to date"
    return output, command_failed, interactive_partial_success


def _build_kit_update_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kit update",
        description="Update installed kits from GitHub sources or a local directory",
    )
    parser.add_argument(
        "slug", nargs="?", default=None,
        help="Kit slug to update, or local directory alias path/<dir> (default: all installed kits)",
    )
    parser.add_argument(
        "--path", dest="local_path", default=None,
        help="Update from a local directory instead of registered source",
    )
    parser.add_argument("--project-root", default=None, help="Project root directory")
    parser.add_argument("--force", action="store_true",
                       help="Skip version check and force update")
    parser.add_argument(
        "--version", dest="version", default="",
        help="For generic Git sources, resolve this tag, branch, or full 40-character commit SHA",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--no-interactive", action="store_true",
                       help="Disable interactive prompts (auto-decline changes)")
    parser.add_argument("-y", "--yes", action="store_true",
                       help="Auto-approve all prompts (no interaction)")
    parser.add_argument(
        "--approve-overwrite",
        action="append",
        default=[],
        metavar="RESOURCE_OR_PATH",
        help=(
            "Approve overwriting one changed user-modifiable manifest resource by id "
            "or effective path; repeat per resource"
        ),
    )
    parser.add_argument(
        "--approve-tool-risk",
        action="append",
        default=[],
        metavar="FINGERPRINT",
        help="Approve one dangerous tool-risk fingerprint; repeat when needed",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Allow explicit pruning of manifest-bound resources removed upstream",
    )
    parser.add_argument(
        "--approve-prune",
        action="append",
        default=[],
        metavar="FINGERPRINT",
        help="Approve one manifest-bound resource deletion by prune fingerprint; repeat per path",
    )
    return parser


def _validate_cmd_kit_update_args(args: argparse.Namespace) -> int:
    args.slug, args.local_path, local_path_error = _normalize_local_path_source_arg(
        source_value=args.slug,
        local_path=args.local_path,
        arg_name="slug",
    )
    if local_path_error:
        ui.result(local_path_error)
        return 2
    if not args.local_path:
        return 0
    conflict = _validate_kit_source_mode(
        local_path=args.local_path,
        version=args.version,
    )
    if conflict:
        ui.result(conflict)
        return 2
    return 0


def _resolve_cmd_kit_update_project(
    args: argparse.Namespace,
) -> Tuple[Optional[Tuple[Path, Path, Path]], int]:
    project_root_arg = Path(args.project_root) if args.project_root else None
    resolved = _resolve_studio_dir(project_root_arg)
    if resolved is None:
        return None, 1
    project_root, studio_dir = resolved
    return (project_root, studio_dir, studio_dir / "config"), 0


def _complete_cmd_kit_update(
    args: argparse.Namespace,
    resolution: _KitUpdateResolution,
) -> int:
    all_results, errors = _run_cmd_kit_update_targets(args, resolution)
    output, command_failed, interactive_partial_success = _build_cmd_kit_update_output(
        args,
        all_results,
        errors,
        resolution.interactive,
        resolution.studio_dir,
    )
    ui.result(output, human_fn=_human_kit_update)
    command_incomplete = bool(
        output.get("kits_partially_updated", 0) or output.get("kits_aborted", 0)
    )
    if command_failed or (command_incomplete and not interactive_partial_success):
        return 2
    return 0


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
    p = _build_kit_update_parser()
    args = p.parse_args(argv)
    validation_code = _validate_cmd_kit_update_args(args)
    if validation_code:
        return validation_code
    # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-parse-args

    # @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-resolve-project
    project_data, project_code = _resolve_cmd_kit_update_project(args)
    if project_data is None:
        return project_code
    project_root, studio_dir, config_dir = project_data
    # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-resolve-project

    resolution, resolution_code = _resolve_cmd_kit_update_targets(
        args,
        project_root,
        studio_dir,
        config_dir,
    )
    if resolution is None:
        return resolution_code
    return _complete_cmd_kit_update(args, resolution)


def _kit_update_authority_parts(authority: Dict[str, Any]) -> List[str]:
    authority_parts: List[str] = []
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
    return authority_parts


def _emit_human_kit_update_result(result: Dict[str, Any]) -> None:
    kit_slug = result.get("kit", "?")
    action = result.get("action", "?")
    accepted = result.get("accepted", [])
    declined = result.get("declined", [])
    unchanged = result.get("unchanged", 0)
    parts = [f"{kit_slug}: {action}"]
    if accepted:
        parts.append(f"{len(accepted)} accepted")
    if declined:
        parts.append(f"{len(declined)} declined")
    if unchanged:
        parts.append(f"{unchanged} unchanged")
    ui.step("  ".join(parts))
    authority = result.get("authority", {})
    if isinstance(authority, dict) and authority:
        authority_parts = _kit_update_authority_parts(authority)
        if authority_parts:
            ui.substep("  authority: " + ", ".join(authority_parts))
    for fingerprint in accepted:
        ui.substep(f"  ~ {fingerprint}")
    for fingerprint in declined:
        ui.substep(f"  ✗ {fingerprint} (declined)")


def _emit_human_kit_update_partial_reasons(partial_reasons: List[Any]) -> None:
    if not partial_reasons:
        return
    ui.blank()
    for item in partial_reasons:
        if not isinstance(item, dict):
            continue
        kit_slug = str(item.get("kit") or "?")
        categories = item.get("categories") or []
        category_text = ", ".join(str(category) for category in categories) if categories else "unspecified"
        ui.warn(f"  partial reason for {kit_slug}: {category_text}")


# @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-human-output
def _human_kit_update(data: dict) -> None:
    status = data.get("status", "")
    n = data.get("kits_updated", 0)

    ui.header("Kit Update")
    ui.detail("Kits updated", str(n))

    for result in data.get("results", []):
        _emit_human_kit_update_result(result)

    errs = data.get("errors", [])
    if errs:
        ui.blank()
        for err in errs:
            ui.warn(str(err))
    _emit_human_kit_update_partial_reasons(data.get("partial_reasons", []))

    if status == "PASS":
        ui.success("Kit update complete.")
    elif status == "WARN":
        ui.warn("Kit update finished with warnings.")
    else:
        ui.info(f"Status: {status}")
    ui.blank()
# @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-human-output


# @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-build-update-result
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
        "status": "FAIL" if failures else "PASS",
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
    return 2 if failures else 0
    # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-format-output
    # @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-build-update-result


# @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-parse-args
# @cpt-begin:cpt-studio-flow-kit-update-cli:p1:inst-build-update-result
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
# @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-build-update-result
# @cpt-end:cpt-studio-flow-kit-update-cli:p1:inst-parse-args

# ---------------------------------------------------------------------------
# Kit Normalize
# ---------------------------------------------------------------------------


def _build_kit_normalize_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kit normalize",
        description="Generate a canonical .cf-studio-kit.toml from a kit source",
    )
    parser.add_argument("path", help="Kit source directory to normalize")
    parser.add_argument(
        "--from",
        dest="source_hint",
        choices=("manifest", "layout", "core"),
        default="",
        help="Limit normalization to a specific legacy source type",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output path for .cf-studio-kit.toml (default: <path>/.cf-studio-kit.toml)",
    )
    parser.add_argument(
        "--kit",
        action="append",
        default=[],
        help="Select canonical kit slug(s) from a multi-kit manifest; repeat, comma-separate, or use 'all'",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the generated manifest without writing it")
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write only the generated canonical manifest TOML to stdout",
    )
    return parser


def _resolve_kit_normalize_source(
    args: argparse.Namespace,
) -> Tuple[Optional[Tuple[Path, Path]], int]:
    kit_source = Path(args.path).resolve()
    if not kit_source.is_dir():
        ui.result({
            "status": "FAIL",
            "message": f"Kit source directory not found: {kit_source}",
            "hint": "Provide a path to a valid kit directory",
        })
        return None, 2
    output_path = Path(args.output).resolve() if args.output else kit_source / ".cf-studio-kit.toml"
    return (kit_source, output_path), 0


def _select_normalize_models(
    all_canonical_models: List[Any],
    requested_kits: List[str],
) -> List[Any]:
    by_slug = {str(model.slug): model for model in all_canonical_models}
    if requested_kits and not any(value == "all" for value in requested_kits):
        missing = [value for value in requested_kits if value not in by_slug]
        if missing:
            raise ValueError(
                f"Unknown kit selection: {', '.join(missing)}; available kits: {', '.join(sorted(by_slug))}",
            )
        selected_models: List[Any] = []
        seen: set[str] = set()
        for value in requested_kits:
            if value in seen:
                continue
            selected_models.append(by_slug[value])
            seen.add(value)
        return selected_models
    return list(all_canonical_models)


def _load_kit_normalize_output(
    args: argparse.Namespace,
    kit_source: Path,
) -> Tuple[List[Any], str]:
    from ..utils.kit_model import (
        load_canonical_kit_models,
        normalize_kit_source,
        render_canonical_manifest_models,
    )

    all_canonical_models: List[Any] = []
    if args.source_hint in ("", "manifest"):
        all_canonical_models = load_canonical_kit_models(kit_source)
    requested_kits = _split_kit_selectors(args.kit)
    if all_canonical_models:
        selected_models = _select_normalize_models(all_canonical_models, requested_kits)
        manifest_text = render_canonical_manifest_models(selected_models)
    else:
        if requested_kits:
            raise ValueError("--kit can only select kits declared in .cf-studio-kit.toml")
        model, manifest_text = normalize_kit_source(kit_source, args.source_hint)
        selected_models = [model]
    if (
        all_canonical_models
        and len(selected_models) < len(all_canonical_models)
        and not args.dry_run
        and not args.stdout
        and not args.output
    ):
        raise ValueError(
            "Refusing to overwrite the source multi-kit manifest with only the selected subset. "
            "Use --stdout to print just that subset, --dry-run to preview it without writing, "
            "or --output <path> to write it to a different file.",
        )
    return selected_models, manifest_text


def _normalize_report(selected_models: List[Any]) -> Dict[str, Any]:
    if len(selected_models) == 1:
        return _kit_normalize_report(selected_models[0])
    return {
        "manifest_source": "canonical",
        "resources": sum(len(model.resources) for model in selected_models),
        "public_resources": sum(len([r for r in model.resources if r.public]) for model in selected_models),
        "warnings": [warning for model in selected_models for warning in model.warnings],
        "kits": [
            {
                "slug": model.slug,
                "name": model.name,
                "version": model.version,
                "report": _kit_normalize_report(model),
            }
            for model in selected_models
        ],
    }


def _emit_kit_normalize_result(
    args: argparse.Namespace,
    selected_models: List[Any],
    output_path: Path,
    report: Dict[str, Any],
    manifest_text: str,
) -> int:
    if args.stdout:
        _emit_stdout_text(manifest_text)
        return 0
    payload: Dict[str, Any] = {
        "status": "PASS",
        "action": "normalized",
        "dry_run": bool(args.dry_run),
        "kit": selected_models[0].slug if len(selected_models) == 1 else "",
        "kits": [model.slug for model in selected_models],
        "kits_normalized": len(selected_models),
        "output": output_path.as_posix(),
        "report": report,
    }
    if args.dry_run:
        payload["manifest"] = manifest_text
        ui.result(payload, human_fn=_human_kit_normalize)
        return 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(manifest_text, encoding="utf-8")
    ui.result(payload, human_fn=_human_kit_normalize)
    return 0


# @cpt-flow:cpt-studio-flow-kit-normalize-cli:p1
def cmd_kit_normalize(argv: List[str]) -> int:
    """Generate a canonical .cf-studio-kit.toml from a kit source."""
    # @cpt-begin:cpt-studio-flow-kit-normalize-cli:p1:inst-normalize-parse-args
    p = _build_kit_normalize_parser()
    args = p.parse_args(argv)
    if args.stdout and args.output:
        p.error("--stdout cannot be combined with --output")
    # @cpt-end:cpt-studio-flow-kit-normalize-cli:p1:inst-normalize-parse-args

    # @cpt-begin:cpt-studio-flow-kit-normalize-cli:p1:inst-normalize-validate-source
    source_data, source_code = _resolve_kit_normalize_source(args)
    if source_data is None:
        return source_code
    kit_source, output_path = source_data
    # @cpt-end:cpt-studio-flow-kit-normalize-cli:p1:inst-normalize-validate-source

    try:
        selected_models, manifest_text = _load_kit_normalize_output(args, kit_source)
    except ValueError as exc:
        logger.warning("Failed to load kit normalize output from %s: %s", kit_source, exc)
        ui.result({
            "status": "FAIL",
            "message": str(exc),
        })
        return 2

    # @cpt-begin:cpt-studio-algo-kit-manifest-normalize:p1:inst-normalize-report-ambiguity
    report = _normalize_report(selected_models)
    # @cpt-end:cpt-studio-algo-kit-manifest-normalize:p1:inst-normalize-report-ambiguity

    return _emit_kit_normalize_result(
        args,
        selected_models,
        output_path,
        report,
        manifest_text,
    )


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
                generated_name = (
                    subagent_id
                    if subagent_id == f"cf-{model.slug}" or subagent_id.startswith(prefix)
                    else f"{prefix}{subagent_id}"
                )
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
            _serialize_public_component(
                component,
                include_name_mode=True,
                subagents=_subagent_previews(component),
            )
            for component in model.public_components
        ],
        # @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-public-name-preview
        "warnings": list(model.warnings),
    }
    # @cpt-end:cpt-studio-algo-kit-manifest-normalize:p1:inst-normalize-preserve-fields
    return report


def _human_kit_normalize(data: dict) -> None:
    ui.header("Kit Normalize")
    kits = data.get("kits", [])
    if isinstance(kits, list) and len(kits) > 1:
        ui.detail("Kits", ", ".join(str(kit) for kit in kits))
    else:
        ui.detail("Kit", str(data.get("kit") or (kits[0] if isinstance(kits, list) and kits else "?")))
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
            _emit_stdout_text(manifest)
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
    except (OSError, ValueError) as exc:
        _warn_kit(f"failed to read kit version from {conf_path}: {exc}")
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
        except OSError as exc:
            _warn_kit(f"failed to remove empty backup directory {backup_dir}: {exc}")
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
        _RegisterKitContext(
            source=source,
            authority_metadata=authority_metadata,
            local_metadata=local_metadata or None,
        ),
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


def _binding_path_for_manifest_resource(
    res: Any,
    merged: Dict[str, Dict[str, Any]],
    kit_root_rel: str,
) -> str:
    binding_path = str(merged.get(res.id, {}).get("path", "") or "")
    if binding_path:
        return binding_path
    install_path = _resource_install_path(res)
    if kit_root_rel:
        return (PurePosixPath(kit_root_rel) / install_path).as_posix()
    return PurePosixPath(install_path).as_posix()


# @cpt-begin:cpt-studio-algo-kit-update:p1:inst-sync-manifest-bindings
def _sync_manifest_resource_bindings(
    manifest: Any,
    config_dir: Path,
    kit_slug: str,
) -> Optional[Dict[str, Dict[str, Any]]]:
    """Sync resource bindings to the current manifest declaration set.

    Returns synced bindings dict, or None if there is no manifest.
    """
    if manifest is None:
        return None
    existing_raw = _read_kits_from_core_toml(config_dir).get(kit_slug, {}).get("resources", {})
    existing: Dict[str, Dict[str, Any]] = {}
    for res_id, binding in existing_raw.items():
        if isinstance(binding, dict):
            existing[res_id] = dict(binding)
        elif isinstance(binding, str):
            existing[res_id] = {"path": binding}
    merged: Dict[str, Dict[str, Any]] = {}
    for res in getattr(manifest, "resources", []):
        if getattr(res, "id", None) in existing:
            merged[str(res.id)] = dict(existing[str(res.id)])
    kit_root_rel = _resolve_manifest_kit_root_rel(manifest, merged, kit_slug)
    for res in getattr(manifest, "resources", []):
        binding_path = _binding_path_for_manifest_resource(res, merged, kit_root_rel)
        merged[res.id] = _manifest_resource_binding_entry(res=res, path=binding_path)
    return merged
# @cpt-end:cpt-studio-algo-kit-update:p1:inst-sync-manifest-bindings


def _project_root_from_core_toml(config_dir: Path, studio_dir: Path) -> Optional[Path]:
    from ..utils.manifest import load_project_root_from_core_toml

    return load_project_root_from_core_toml(
        config_dir / _KIT_CORE_TOML,
        Path(studio_dir),
        default_to_parent=False,
    )


def _init_update_result(
    kit_slug: str,
    update_context: _UpdateContext,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {"kit": kit_slug}
    authority_summary = _authority_result_summary(update_context.authority_metadata)
    if authority_summary:
        result["authority"] = authority_summary
    return result


def _resolve_update_source_version(
    source_dir: Path,
    update_context: _UpdateContext,
) -> Tuple[str, str]:
    src_conf = source_dir / _KIT_CONF_FILE
    local_conf_version = _read_kit_version(src_conf) if src_conf.is_file() else ""
    local_source_version = _read_kit_source_version(source_dir)
    authority = update_context.authority_metadata or {}
    if authority.get("resolved_ref"):
        return str(authority.get("resolved_ref") or ""), local_conf_version
    if authority.get("installed_version"):
        return str(authority.get("installed_version") or ""), local_conf_version
    if local_conf_version:
        return local_conf_version, local_conf_version
    return local_source_version, local_conf_version


def _load_manifest_update_risk_model(
    source_dir: Path,
    kit_slug: str,
    result: Dict[str, Any],
) -> Optional[Any]:
    try:
        from ..utils.kit_model import load_kit_model

        return load_kit_model(source_dir, kit_slug=kit_slug)
    except (OSError, ValueError) as exc:
        _result_with_failure(result, [str(exc)])
        return None


def _manifest_update_risk_state(
    risk_model: Any,
    installed_kit_entry: Dict[str, Any],
    update_context: _UpdateContext,
    result: Dict[str, Any],
) -> Tuple[bool, Optional[List[str]]]:
    risk_summary = getattr(risk_model, "tool_risk_summary", {}) or {}
    installed_fingerprint = str(installed_kit_entry.get("tool_risk_fingerprint", "") or "")
    current_fingerprint = str(getattr(risk_model, "tool_risk_fingerprint", "") or "")
    risk_changed = bool(
        risk_summary.get("requires_confirmation")
        and current_fingerprint
        and current_fingerprint != installed_fingerprint
    )
    risk_errors = _tool_risk_approval_errors(
        risk_model,
        installed_kit_entry=installed_kit_entry,
        interactive=update_context.interactive,
        approved_tool_risks=update_context.approved_tool_risks,
    )
    if risk_errors:
        _result_with_failure(result, risk_errors)
        return risk_changed, risk_errors
    return risk_changed, None


def _resolve_manifest_update_context(
    kit_slug: str,
    source_dir: Path,
    installed_kit_entry: Dict[str, Any],
    update_context: _UpdateContext,
    result: Dict[str, Any],
    has_registered_kit_path: bool,
) -> Optional[_ManifestUpdateResolution]:
    source_version, local_conf_version = _resolve_update_source_version(
        source_dir,
        update_context,
    )
    registered_kit_path = str(installed_kit_entry.get("path") or "") if isinstance(installed_kit_entry, dict) else ""
    try:
        manifest = _load_manifest_install_adapter(source_dir, kit_slug=kit_slug)
    except (OSError, ValueError) as exc:
        _result_with_failure(result, [str(exc)])
        return None
    risk_model = None
    risk_changed = False
    if manifest is not None:
        risk_model = _load_manifest_update_risk_model(source_dir, kit_slug, result)
        if risk_model is None:
            return None
        risk_changed, risk_errors = _manifest_update_risk_state(
            risk_model,
            installed_kit_entry,
            update_context,
            result,
        )
        if risk_errors:
            return None
    return _ManifestUpdateResolution(
        manifest=manifest,
        risk_model=risk_model,
        risk_changed=risk_changed,
        source_version=source_version,
        local_conf_version=local_conf_version,
        registered_kit_path=registered_kit_path,
        has_registered_kit_path=has_registered_kit_path,
    )


def _append_registered_kit_metadata(
    result: Dict[str, Any],
    studio_dir: Path,
    config_dir: Path,
    kit_slug: str,
    fallback_entry: Dict[str, Any],
) -> Dict[str, Any]:
    current_entry = _read_kits_from_core_toml(config_dir).get(kit_slug, fallback_entry)
    meta = _collect_registered_kit_metadata(studio_dir, kit_slug, current_entry)
    if meta.get("skill_nav"):
        result["skill_nav"] = meta["skill_nav"]
    if meta.get("agents_content"):
        result["agents_content"] = meta["agents_content"]
    return result


def _load_registered_manifest_update_model(
    source_dir: Path,
    kit_slug: str,
    manifest_state: _ManifestUpdateResolution,
    result: Dict[str, Any],
) -> Optional[Any]:
    if manifest_state.risk_model is not None:
        return manifest_state.risk_model
    return _load_manifest_update_risk_model(source_dir, kit_slug, result)


def _registered_manifest_local_metadata(
    manifest_state: _ManifestUpdateResolution,
) -> Dict[str, str]:
    if manifest_state.local_conf_version:
        return {"conf_version": manifest_state.local_conf_version}
    return {}


def _handle_registered_manifest_update(
    kit_slug: str,
    source_dir: Path,
    studio_dir: Path,
    config_dir: Path,
    installed_kit_entry: Dict[str, Any],
    update_context: _UpdateContext,
    manifest_state: _ManifestUpdateResolution,
    result: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not (
        manifest_state.manifest is not None
        and isinstance(installed_kit_entry, dict)
        and installed_kit_entry.get("install_mode") == "register"
    ):
        return None
    effective_project_root = (
        update_context.project_root or _project_root_from_core_toml(config_dir, studio_dir)
    )
    containment_errors = _validate_register_manifest_containment(
        effective_project_root,
        studio_dir,
        source_dir,
        kit_slug,
        manifest_state.manifest,
    )
    if containment_errors:
        return _result_with_failure(result, containment_errors)
    kit_model = _load_registered_manifest_update_model(
        source_dir,
        kit_slug,
        manifest_state,
        result,
    )
    if kit_model is None:
        return result
    previous_version = str(installed_kit_entry.get("version") or "")
    resource_bindings = _manifest_register_resource_bindings(
        studio_dir,
        source_dir,
        list(getattr(kit_model, "resources", [])),
    )
    registration_errors = _register_kit_in_core_toml(
        config_dir,
        kit_slug,
        manifest_state.source_version,
        studio_dir,
        _RegisterKitContext(
            source=update_context.source or str(installed_kit_entry.get("source") or ""),
            resources=resource_bindings,
            kit_path=_serialize_manifest_binding_path(source_dir.resolve(), studio_dir),
            install_mode="register",
            source_provenance=_local_path_provenance(source_dir, "register", studio_dir),
            authority_metadata=update_context.authority_metadata,
            local_metadata=_registered_manifest_local_metadata(manifest_state) or None,
            tool_risk_fingerprint=str(getattr(kit_model, "tool_risk_fingerprint", "") or ""),
        ),
    )
    if registration_errors:
        return _result_with_failure(result, registration_errors)
    version_changed = bool(
        manifest_state.source_version and manifest_state.source_version != previous_version
    )
    result["version"] = {"status": "updated" if version_changed else "current"}
    result["gen"] = {"files_written": 0}
    result["drift"] = {"install_mode": "register", "version_changed": version_changed}
    result["resource_bindings"] = {
        key: value["path"] for key, value in resource_bindings.items()
    }
    return _append_registered_kit_metadata(
        result,
        studio_dir,
        config_dir,
        kit_slug,
        installed_kit_entry,
    )


def _maybe_migrate_legacy_manifest_install(
    result: Dict[str, Any],
    source_dir: Path,
    studio_dir: Path,
    kit_slug: str,
    interactive: bool,
) -> Optional[Dict[str, Any]]:
    migration_result = migrate_legacy_kit_to_manifest(
        source_dir,
        studio_dir,
        kit_slug,
        interactive=interactive,
    )
    result["manifest_migration"] = migration_result
    if migration_result.get("status") != "FAIL":
        return None
    _warn_user(
        f"manifest migration for '{kit_slug}' failed: "
        f"{migration_result.get('errors', [])}"
    )
    return _result_with_failure(
        result,
        list(migration_result.get("errors", [])),
    )


def _maybe_finalize_current_version_update(
    ctx: _KitUpdateRunContext,
) -> Optional[Dict[str, Any]]:
    if (
        ctx.update_context.force
        or not ctx.manifest_state.source_version
        or not ctx.installed_kit_dir.is_dir()
    ):
        return None
    installed_version = _read_kit_version_from_core(ctx.config_dir, ctx.kit_slug)
    if not (
        installed_version
        and installed_version == ctx.manifest_state.source_version
        and not _authority_commit_changed(
            ctx.update_context.authority_metadata,
            ctx.installed_kit_entry,
        )
        and not ctx.manifest_state.risk_changed
    ):
        return None
    if ctx.manifest_state.manifest is not None and not ctx.installed_kit_entry.get("resources"):
        failure_result = _maybe_migrate_legacy_manifest_install(
            ctx.result,
            ctx.source_dir,
            ctx.studio_dir,
            ctx.kit_slug,
            ctx.update_context.interactive,
        )
        if failure_result is not None:
            return failure_result
        current_entry = _read_kits_from_core_toml(ctx.config_dir).get(
            ctx.kit_slug,
            ctx.installed_kit_entry,
        )
        ctx.installed_kit_entry.update(current_entry)
    sync_manifest_model = ctx.manifest_state.risk_model or ctx.manifest_state.manifest
    synced_resources = _sync_manifest_resource_bindings(
        sync_manifest_model,
        ctx.config_dir,
        ctx.kit_slug,
    )
    resources_changed = False
    if synced_resources is not None:
        current_resources = ctx.installed_kit_entry.get("resources", {})
        resources_changed = current_resources != synced_resources
        if resources_changed:
            registration_errors = _register_kit_in_core_toml(
                ctx.config_dir,
                ctx.kit_slug,
                ctx.manifest_state.source_version,
                ctx.studio_dir,
                _RegisterKitContext(
                    source=ctx.update_context.source or str(ctx.installed_kit_entry.get("source") or ""),
                    resources=synced_resources,
                    kit_path=_resolve_manifest_kit_root_rel(
                        ctx.manifest_state.manifest,
                        synced_resources,
                        ctx.kit_slug,
                    ),
                ),
            )
            if registration_errors:
                return _result_with_failure(ctx.result, registration_errors)
    ctx.result["version"] = {"status": "updated" if resources_changed else "current"}
    ctx.result["gen"] = {"files_written": 0}
    authority = ctx.update_context.authority_metadata or {}
    authority_source_type = str(authority.get("source_type") or "")
    authority_freshness = str(authority.get("freshness") or "")
    if (
        ctx.update_context.authority_metadata
        and ctx.update_context.source
        and (authority_source_type == "git" or authority_freshness != "last_known")
    ):
        registration_errors = _register_kit_in_core_toml(
            ctx.config_dir,
            ctx.kit_slug,
            ctx.manifest_state.source_version,
            ctx.studio_dir,
            _RegisterKitContext(
                source=ctx.update_context.source,
                authority_metadata=ctx.update_context.authority_metadata,
                local_metadata=(
                    {"conf_version": ctx.manifest_state.local_conf_version}
                    if ctx.manifest_state.local_conf_version else None
                ),
                tool_risk_fingerprint=str(
                    getattr(sync_manifest_model, "tool_risk_fingerprint", "") or ""
                ),
            ),
        )
        if registration_errors:
            return _result_with_failure(ctx.result, registration_errors)
    return _append_registered_kit_metadata(
        ctx.result,
        ctx.studio_dir,
        ctx.config_dir,
        ctx.kit_slug,
        ctx.installed_kit_entry,
    )


def _resolve_manifest_update_bindings(
    ctx: _KitUpdateRunContext,
) -> Tuple[Optional[Dict[str, Path]], Optional[Dict[str, str]], Optional[Dict[str, Any]]]:
    if ctx.manifest_state.manifest is None:
        return None, None, None
    from ..utils.manifest import build_source_to_resource_mapping, resolve_resource_bindings

    try:
        preseeded_resources = _sync_manifest_resource_bindings(
            ctx.manifest_state.risk_model or ctx.manifest_state.manifest,
            ctx.config_dir,
            ctx.kit_slug,
        )
        if preseeded_resources is not None and not ctx.installed_kit_entry.get("resources"):
            registration_errors = _register_kit_in_core_toml(
                ctx.config_dir,
                ctx.kit_slug,
                _read_kit_version_from_core(ctx.config_dir, ctx.kit_slug)
                or ctx.manifest_state.source_version,
                ctx.studio_dir,
                _RegisterKitContext(
                    source=ctx.update_context.source or str(ctx.installed_kit_entry.get("source") or ""),
                    resources=preseeded_resources,
                    kit_path=(
                        ctx.manifest_state.registered_kit_path
                        if ctx.manifest_state.has_registered_kit_path
                        else _resolve_manifest_kit_root_rel(
                            ctx.manifest_state.risk_model or ctx.manifest_state.manifest,
                            preseeded_resources,
                            ctx.kit_slug,
                        )
                    ),
                    install_mode=str(ctx.installed_kit_entry.get("install_mode") or ""),
                    local_metadata=(
                        {"conf_version": ctx.manifest_state.local_conf_version}
                        if ctx.manifest_state.local_conf_version else None
                    ),
                    tool_risk_fingerprint=str(
                        getattr(ctx.manifest_state.risk_model, "tool_risk_fingerprint", "") or ""
                    ),
                ),
            )
            if registration_errors:
                _result_with_failure(ctx.result, registration_errors)
                return None, None, None
            ctx.installed_kit_entry.update(
                _read_kits_from_core_toml(ctx.config_dir).get(
                    ctx.kit_slug,
                    ctx.installed_kit_entry,
                )
            )
        source_to_resource_id, resource_info = build_source_to_resource_mapping(
            ctx.source_dir,
            kit_slug=ctx.kit_slug,
        )
        resource_bindings = resolve_resource_bindings(
            ctx.config_dir,
            ctx.kit_slug,
            ctx.studio_dir,
        )
        _augment_manifest_subagent_update_bindings(
            ctx.manifest_state.risk_model or ctx.manifest_state.manifest,
            ctx.installed_kit_dir,
            source_to_resource_id,
            resource_info,
            resource_bindings,
        )
    except ValueError as exc:
        _result_with_failure(ctx.result, [str(exc)])
        return None, None, None
    if not resource_bindings or not source_to_resource_id or not resource_info:
        _result_with_failure(
            ctx.result,
            [
                (
                    f"Manifest-backed update for kit '{ctx.kit_slug}' could not resolve resource bindings "
                    "from the source and installed metadata; refusing to treat all files as deleted upstream."
                ),
            ],
        )
        return None, None, None
    return resource_bindings, source_to_resource_id, resource_info


def _run_first_install_update(
    ctx: _KitUpdateRunContext,
) -> Optional[Dict[str, Any]]:
    if ctx.installed_kit_dir.is_dir():
        return None
    if ctx.manifest_state.manifest is not None:
        install_result = install_kit_with_manifest(
            ctx.source_dir,
            ctx.studio_dir,
            ctx.kit_slug,
            ctx.manifest_state.source_version,
            ctx.manifest_state.manifest,
            kit_path=(
                ctx.manifest_state.registered_kit_path
                if ctx.manifest_state.has_registered_kit_path else ""
            ),
            install_context=_InstallContext(
                interactive=ctx.update_context.interactive and not ctx.update_context.auto_approve,
                source=ctx.update_context.source,
                authority_metadata=ctx.update_context.authority_metadata,
                approved_overwrites=list(ctx.update_context.approved_overwrites),
                approved_tool_risks=list(ctx.update_context.approved_tool_risks),
            ),
        )
    else:
        install_result = _perform_first_install_kit(
            ctx.source_dir,
            ctx.installed_kit_dir,
            ctx.config_dir,
            ctx.kit_slug,
            ctx.manifest_state.source_version,
            ctx.studio_dir,
            source=ctx.update_context.source,
            authority_metadata=ctx.update_context.authority_metadata,
        )
    files_written = install_result.get("files_copied", 0)
    install_status = str(install_result.get("status", "PASS")).upper()
    ctx.result["version"] = {
        "status": "failed" if install_status == "FAIL" else "created",
        "source_status": install_status,
    }
    ctx.result["gen"] = {"files_written": files_written}
    if install_result.get("errors"):
        ctx.result["errors"] = list(install_result.get("errors", []))
    if install_result.get("actions"):
        ctx.result["actions"] = install_result.get("actions")
    return ctx.result if install_result.get("status") == "FAIL" else None


def _run_file_level_update(
    ctx: _KitUpdateRunContext,
    resource_bindings: Optional[Dict[str, Path]],
    source_to_resource_id: Optional[Dict[str, str]],
    resource_info: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    from ..utils.diff_engine import file_level_kit_update

    report = file_level_kit_update(
        ctx.source_dir,
        ctx.installed_kit_dir,
        interactive=ctx.update_context.interactive,
        auto_approve=ctx.update_context.auto_approve,
        content_dirs=None if ctx.manifest_state.manifest is not None else _KIT_CONTENT_DIRS,
        content_files=None if ctx.manifest_state.manifest is not None else _KIT_CONTENT_FILES,
        resource_bindings=resource_bindings,
        source_to_resource_id=source_to_resource_id,
        resource_info=resource_info,
        strict_resource_files=ctx.manifest_state.manifest is not None,
        approved_overwrites=ctx.update_context.approved_overwrites,
        prune_mode=ctx.update_context.prune_mode,
        approved_prunes=ctx.update_context.approved_prunes,
    )
    accepted = report.get("accepted", [])
    declined = report.get("declined", [])
    ver_status = "partial" if declined else "updated" if accepted else "current"
    ctx.result["version"] = {"status": ver_status}
    ctx.result["gen"] = {
        "files_written": len(accepted),
        "accepted_files": accepted,
        "unchanged": report.get("unchanged", 0),
    }
    if declined:
        ctx.result["gen_rejected"] = declined
    prune_required = [
        entry for entry in report.get("removed", [])
        if entry.get("prune_fingerprint") and entry.get("action") == "declined"
    ]
    if prune_required:
        ctx.result["prune_required"] = prune_required
    merged_resources = _sync_manifest_resource_bindings(
        ctx.manifest_state.risk_model or ctx.manifest_state.manifest,
        ctx.config_dir,
        ctx.kit_slug,
    )
    bumped_safe_to_record = ver_status != "partial"
    if not ((ctx.manifest_state.source_version and bumped_safe_to_record) or merged_resources):
        return None
    preserved_version = ctx.manifest_state.source_version
    if not bumped_safe_to_record:
        existing = _read_kits_from_core_toml(ctx.config_dir).get(ctx.kit_slug, {})
        preserved_version = (
            str(existing.get("version") or "") or ctx.manifest_state.source_version
        )
    registration_errors = _register_kit_in_core_toml(
        ctx.config_dir,
        ctx.kit_slug,
        preserved_version,
        ctx.studio_dir,
        _RegisterKitContext(
            source=ctx.update_context.source,
            resources=merged_resources,
            kit_path=(
                ctx.manifest_state.registered_kit_path
                if ctx.manifest_state.manifest is not None else ""
            ),
            authority_metadata=ctx.update_context.authority_metadata,
            local_metadata=(
                {"conf_version": ctx.manifest_state.local_conf_version}
                if ctx.manifest_state.local_conf_version else None
            ),
            tool_risk_fingerprint=str(
                getattr(
                    ctx.manifest_state.risk_model or ctx.manifest_state.manifest,
                    "tool_risk_fingerprint",
                    "",
                ) or ""
            ),
        ),
    )
    if registration_errors:
        return _result_with_failure(ctx.result, registration_errors)
    return None


def _prepare_kit_update_run_context(
    kit_slug: str,
    source_dir: Path,
    studio_dir: Path,
    update_context: _UpdateContext,
) -> Tuple[Optional[_KitUpdateRunContext], Dict[str, Any]]:
    config_dir = studio_dir / "config"
    result = _init_update_result(kit_slug, update_context)
    installed_kit_dir, installed_kit_rel, installed_kit_entry, has_registered_kit_path = _resolve_installed_kit_root(
        studio_dir,
        config_dir,
        kit_slug,
    )
    if installed_kit_dir is None:
        _result_with_failure(
            result,
            [
                (
                    f"Kit '{kit_slug}' is registered at absolute path "
                    f"'{installed_kit_rel}' which is not accessible on this OS"
                ),
            ],
        )
        return None, result
    manifest_state = _resolve_manifest_update_context(
        kit_slug,
        source_dir,
        installed_kit_entry,
        update_context,
        result,
        has_registered_kit_path,
    )
    if manifest_state is None:
        return None, result
    return _KitUpdateRunContext(
        kit_slug=kit_slug,
        source_dir=source_dir,
        studio_dir=studio_dir,
        config_dir=config_dir,
        installed_kit_dir=installed_kit_dir,
        installed_kit_entry=installed_kit_entry,
        update_context=update_context,
        manifest_state=manifest_state,
        result=result,
    ), result


def _run_nonregistered_kit_update(
    ctx: _KitUpdateRunContext,
) -> Dict[str, Any]:
    if (
        ctx.manifest_state.manifest is not None
        and ctx.installed_kit_dir.is_dir()
        and not ctx.installed_kit_entry.get("resources")
    ):
        _maybe_migrate_legacy_manifest_install(
            ctx.result,
            ctx.source_dir,
            ctx.studio_dir,
            ctx.kit_slug,
            ctx.update_context.interactive,
        )
    resource_bindings, source_to_resource_id, resource_info = _resolve_manifest_update_bindings(ctx)
    if ctx.result.get("errors"):
        return ctx.result
    was_installed = ctx.installed_kit_dir.is_dir()
    first_install_result = _run_first_install_update(ctx)
    if first_install_result is not None:
        return first_install_result
    if not was_installed:
        return _append_registered_kit_metadata(
            ctx.result,
            ctx.studio_dir,
            ctx.config_dir,
            ctx.kit_slug,
            ctx.installed_kit_entry,
        )
    failed_update = _run_file_level_update(
        ctx,
        resource_bindings,
        source_to_resource_id,
        resource_info,
    )
    if failed_update is not None:
        return failed_update
    return _append_registered_kit_metadata(
        ctx.result,
        ctx.studio_dir,
        ctx.config_dir,
        ctx.kit_slug,
        ctx.installed_kit_entry,
    )


# @cpt-dod:cpt-studio-dod-kit-update:p1
# @cpt-algo:cpt-studio-algo-kit-update:p1
def update_kit(  # pylint: disable=too-many-arguments,too-many-locals
    kit_slug: str,
    source_dir: Path,
    studio_dir: Path,
    update_context: Optional[_UpdateContext] = None,
    *,
    dry_run: Optional[bool] = None,
    interactive: Optional[bool] = None,
    auto_approve: Optional[bool] = None,
    force: Optional[bool] = None,
    source: Optional[str] = None,
    authority_metadata: Optional[Dict[str, Any]] = None,
    approved_overwrites: Optional[List[str]] = None,
    approved_tool_risks: Optional[List[str]] = None,
    prune_mode: Optional[bool] = None,
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
    update_context = _merge_update_context(
        update_context,
        dry_run=dry_run,
        interactive=interactive,
        auto_approve=auto_approve,
        force=force,
        source=source,
        authority_metadata=authority_metadata,
        approved_overwrites=approved_overwrites,
        approved_tool_risks=approved_tool_risks,
        prune_mode=prune_mode,
        approved_prunes=approved_prunes,
        project_root=project_root,
    )
    source_dir = source_dir.resolve()
    studio_dir = studio_dir.resolve()
    if update_context.dry_run:
        result = _init_update_result(kit_slug, update_context)
        result["version"] = {"status": "dry_run"}
        result["gen"] = "dry_run"
        return result
    run_ctx, result = _prepare_kit_update_run_context(
        kit_slug,
        source_dir,
        studio_dir,
        update_context,
    )
    if run_ctx is None:
        return result
    registered_result = _handle_registered_manifest_update(
        kit_slug,
        source_dir,
        studio_dir,
        run_ctx.config_dir,
        run_ctx.installed_kit_entry,
        update_context,
        run_ctx.manifest_state,
        result,
    )
    if registered_result is not None:
        return registered_result
    current_version_result = _maybe_finalize_current_version_update(run_ctx)
    if current_version_result is not None:
        return current_version_result
    return _run_nonregistered_kit_update(run_ctx)

# @cpt-begin:cpt-studio-flow-kit-dispatch:p1:inst-migrate-deprecated
def cmd_kit_migrate(_argv: List[str]) -> int:
    """Deprecated — use 'cfs kit update <path>' instead.

    The migrate command was part of the blueprint-based three-way merge system
    which has been removed.  File-level updates are now handled by 'kit update'.
    """
    _ui_lines(
        "WARNING: 'cfs kit migrate' is deprecated.",
        "         Use 'cfs kit update <path>' instead.",
    )
    return 1
# @cpt-end:cpt-studio-flow-kit-dispatch:p1:inst-migrate-deprecated

# ---------------------------------------------------------------------------
# Kit CLI dispatcher (handles `cfs kit <subcommand>`)
# ---------------------------------------------------------------------------

def _emit_kit_command_help(
    subcommands: List[str],
    usage: str,
    descriptions: Dict[str, List[Tuple[str, str]]],
) -> tuple:
    lines = [f"Usage: {usage}", "", "Subcommands:"]
    for name in subcommands:
        for args, description in descriptions.get(name, [("", "")]):
            command = f"{name} {args}".rstrip()
            lines.append(f"  {command:<30} {description}")
    _ui_lines(*lines)
    return tuple(lines)


def _dispatch_kit_subcommand(subcmd: str, rest: List[str]) -> int:
    handlers = {
        "install": cmd_kit_install,
        "update": cmd_kit_update,
        "check-updates": cmd_kit_check_updates,
        "normalize": cmd_kit_normalize,
        "migrate": cmd_kit_migrate,
    }
    handler = handlers.get(subcmd)
    if handler is not None:
        return handler(rest)
    if subcmd == "validate":
        from .validate_kits import cmd_validate_kits

        return cmd_validate_kits(rest)
    return -1


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
        return _emit_kit_command_help(subcommands, usage, descriptions)

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
    exit_code = _dispatch_kit_subcommand(subcmd, rest)
    if exit_code >= 0:
        return exit_code
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
    except (OSError, ValueError) as exc:
        _warn_kit(f"failed to read installed kits from {core_toml}: {exc}")
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
            "hint": (
                "For local --path installs or updates, omit --version; conf.toml "
                "version is treated as local metadata only."
            ),
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
        _warn_kit(f"cannot read canonical kit metadata from {kit_source}: {exc}")

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
        _warn_kit(f"cannot read {conf_toml}: {exc}")
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
        _warn_kit(f"cannot read canonical kit metadata from {kit_source}: {exc}")

    conf_toml = kit_source / _KIT_CONF_FILE
    return _read_kit_version(conf_toml) if conf_toml.is_file() else ""


def _has_canonical_kit_models(kit_source: Path) -> bool:
    """Return True when the source contains a valid canonical kit manifest."""
    try:
        from ..utils.kit_model import load_canonical_kit_models
        return bool(load_canonical_kit_models(kit_source))
    except ValueError as exc:
        _warn_kit(f"failed to validate canonical kit metadata in {kit_source}: {exc}")
        return False


def _split_kit_selectors(raw_values: List[str]) -> List[str]:
    selectors: List[str] = []
    for raw_value in raw_values:
        for part in str(raw_value).split(","):
            value = part.strip()
            if value:
                selectors.append(value)
    return selectors


def _validate_requested_kit_models(
    models: List[Any],
    requested_kits: List[str],
) -> Tuple[Optional[List[Any]], Optional[Dict[str, Any]]]:
    by_slug = {str(model.slug): model for model in models}
    requested = _split_kit_selectors(requested_kits)
    if not requested:
        return None, None
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
        if value in seen:
            continue
        selected.append(by_slug[value])
        seen.add(value)
    return selected, None


def _prompt_for_canonical_kit_selection(models: List[Any]) -> List[str]:
    _ui_lines("Multiple kits are declared:", blank_before=True)
    for idx, model in enumerate(models, start=1):
        ui.info(f"  [{idx}] {model.slug}  {model.version or ''}")
    answer = _input_stderr("  Install which kits? (number/slug, comma-separated, or all): ")
    requested = _split_kit_selectors([answer])
    if not requested:
        raise ValueError("No kits selected")
    normalized: List[str] = []
    for value in requested:
        if value == "all":
            return ["all"]
        if value.isdigit():
            idx = int(value)
            if idx < 1 or idx > len(models):
                raise IndexError(value)
            normalized.append(str(models[idx - 1].slug))
        else:
            normalized.append(value)
    return normalized


def _canonical_kit_selection_error(
    message: str,
    available_kits: List[str],
) -> Tuple[List[Any], Dict[str, Any]]:
    return [], {
        "status": "FAIL",
        "message": message,
        "available_kits": available_kits,
    }


def _prompt_canonical_kit_models_for_install(
    kit_source: Path,
    models: List[Any],
    available_kits: List[str],
) -> Tuple[List[Any], Optional[Dict[str, Any]]]:
    try:
        normalized = _prompt_for_canonical_kit_selection(models)
    except ValueError:
        return _canonical_kit_selection_error("No kits selected", available_kits)
    except IndexError as exc:
        return _canonical_kit_selection_error(
            f"Kit selection index out of range: {exc}",
            available_kits,
        )
    return _select_canonical_kit_models_for_install(
        kit_source,
        normalized,
        interactive=False,
    )


def _select_loaded_canonical_kit_models(
    kit_source: Path,
    models: List[Any],
    requested_kits: List[str],
    interactive: bool,
) -> Tuple[List[Any], Optional[Dict[str, Any]]]:
    if not models:
        if requested_kits:
            return [], {
                "status": "FAIL",
                "message": "--kit can only select kits declared in .cf-studio-kit.toml",
            }
        return [], None
    selected, selection_error = _validate_requested_kit_models(models, requested_kits)
    if selection_error is not None:
        return [], selection_error
    if selected is not None or len(models) == 1:
        return list(selected or models), None
    available_kits = sorted(str(model.slug) for model in models)
    if not interactive:
        return [], {
            "status": "FAIL",
            "message": ".cf-studio-kit.toml declares multiple kits; choose which to install",
            "available_kits": available_kits,
            "hint": "Use --kit <slug>, repeat --kit, or --kit all",
        }
    return _prompt_canonical_kit_models_for_install(
        kit_source,
        models,
        available_kits,
    )


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
    return _select_loaded_canonical_kit_models(
        kit_source,
        models,
        requested_kits,
        interactive,
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
        _warn_kit(f"cannot read version for '{kit_slug}' from {core_toml}: {exc}")
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
        _warn_kit(f"cannot read version from {conf_path}: {exc}")
    return ""
    # @cpt-end:cpt-studio-algo-kit-config-helpers:p1:inst-read-kit-version
# @cpt-end:cpt-studio-algo-kit-config-helpers:p1:inst-read-kit-version-fn


def _load_core_toml_registration_data(
    core_toml: Path,
    kit_slug: str,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    if not core_toml.is_file():
        return None, [f"Cannot register kit '{kit_slug}': missing {core_toml}"]
    try:
        with open(core_toml, "rb") as f:
            return tomllib.load(f), []
    except (OSError, ValueError) as exc:
        return None, [f"Cannot register kit '{kit_slug}' in {core_toml}: {exc}"]


def _apply_registered_kit_path(
    existing: Dict[str, Any],
    kit_slug: str,
    kit_path: str,
    studio_dir: Path,
    project_root: Path,
) -> Optional[str]:
    if not kit_path:
        if not existing.get("path"):
            existing["path"] = f"config/kits/{kit_slug}"
        return None
    normalized_kit_path = _normalize_registered_kit_path(kit_path, kit_slug)
    existing_path = existing.get("path")
    preserve_legacy_absolute = (
        isinstance(existing_path, str)
        and _normalize_path_string(existing_path) == normalized_kit_path
    )
    path_error = _validate_persisted_core_path(
        f"Kit '{kit_slug}' path",
        normalized_kit_path,
        studio_dir,
        project_root,
        allow_same_os_absolute=preserve_legacy_absolute,
    )
    if path_error:
        return path_error
    if (
        isinstance(existing_path, str)
        and _normalize_path_string(existing_path) == normalized_kit_path
    ):
        existing["path"] = existing_path
    else:
        existing["path"] = normalized_kit_path
    return None


def _source_type_for_registration(source: str) -> str:
    if source.startswith("github:"):
        return "github"
    if source.startswith("git:"):
        return "git"
    return "unknown"


def _build_registration_provenance(
    source: str,
    authority_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    source_provenance = {
        "source_type": authority_metadata.get("source_type", _source_type_for_registration(source)),
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
    return {key: value for key, value in source_provenance.items() if value}


def _apply_registration_metadata(
    existing: Dict[str, Any],
    kit_version: str,
    register_context: _RegisterKitContext,
) -> None:
    if register_context.source:
        existing["source"] = register_context.source
    if register_context.install_mode:
        existing["install_mode"] = register_context.install_mode
    if register_context.source_provenance:
        existing["source_provenance"] = {
            key: value
            for key, value in register_context.source_provenance.items()
            if value
        }
    if register_context.authority_metadata:
        existing["source_provenance"] = _build_registration_provenance(
            register_context.source,
            register_context.authority_metadata,
        )
        authority_version = (
            register_context.authority_metadata.get("installed_version")
            or register_context.authority_metadata.get("version")
            or register_context.authority_metadata.get("resolved_ref")
            or kit_version
        )
        if authority_version:
            existing["version"] = str(authority_version)
    elif kit_version:
        existing["version"] = kit_version
    existing.pop("content_identity", None)
    if register_context.local_metadata:
        existing["local_metadata"] = register_context.local_metadata
    if register_context.tool_risk_fingerprint:
        existing["tool_risk_fingerprint"] = register_context.tool_risk_fingerprint
    else:
        existing.pop("tool_risk_fingerprint", None)


def _validate_registration_resources(
    resources: Dict[str, Dict[str, Any]],
    *,
    kit_slug: str,
    studio_dir: Path,
    project_root: Path,
    existing_path: Any,
) -> List[str]:
    resource_errors: List[str] = []
    for res_id, binding in resources.items():
        path_value = binding.get("path") if isinstance(binding, dict) else binding
        if not isinstance(path_value, str) or not path_value.strip():
            continue
        path_error = _validate_persisted_core_path(
            f"Kit '{kit_slug}' resource '{res_id}' path",
            path_value,
            studio_dir,
            project_root,
            allowed_absolute_root=str(existing_path or ""),
        )
        if path_error:
            resource_errors.append(path_error)
    return resource_errors


def _persist_core_registration(core_toml: Path, data: Dict[str, Any], kit_slug: str) -> List[str]:
    try:
        from ..utils import toml_utils

        toml_utils.dump(
            data,
            core_toml,
            header_comment="Constructor Studio project configuration",
        )
    except (OSError, ValueError) as exc:
        message = f"kit: warning: failed to register {kit_slug} in {core_toml}: {exc}"
        _warn_kit(f"failed to register {kit_slug} in {core_toml}: {exc}")
        return [message]
    return []


# @cpt-begin:cpt-studio-algo-kit-config-helpers:p1:inst-register-core-fn
def _register_kit_in_core_toml(  # pylint: disable=too-many-arguments,too-many-locals
    config_dir: Path,
    kit_slug: str,
    kit_version: str,
    _studio_dir: Path,  # reserved for future studio-dir-relative path computation
    register_context: Optional[_RegisterKitContext] = None,
    *,
    source: Optional[str] = None,
    resources: Optional[Dict[str, Dict[str, Any]]] = None,
    kit_path: Optional[str] = None,
    install_mode: Optional[str] = None,
    authority_metadata: Optional[Dict[str, Any]] = None,
    source_provenance: Optional[Dict[str, Any]] = None,
    local_metadata: Optional[Dict[str, Any]] = None,
    tool_risk_fingerprint: Optional[str] = None,
) -> List[str]:
    """Register or update a kit entry in config/core.toml."""
    # @cpt-begin:cpt-studio-algo-kit-config-helpers:p1:inst-register-core
    base_context = register_context or _RegisterKitContext()
    register_context = _RegisterKitContext(
        source=base_context.source if source is None else source,
        resources=base_context.resources if resources is None else resources,
        kit_path=base_context.kit_path if kit_path is None else kit_path,
        install_mode=base_context.install_mode if install_mode is None else install_mode,
        authority_metadata=(
            base_context.authority_metadata
            if authority_metadata is None else authority_metadata
        ),
        source_provenance=(
            base_context.source_provenance
            if source_provenance is None else source_provenance
        ),
        local_metadata=(
            base_context.local_metadata
            if local_metadata is None else local_metadata
        ),
        tool_risk_fingerprint=(
            base_context.tool_risk_fingerprint
            if tool_risk_fingerprint is None else tool_risk_fingerprint
        ),
    )
    core_toml = config_dir / _KIT_CORE_TOML
    data, load_errors = _load_core_toml_registration_data(core_toml, kit_slug)
    if load_errors:
        return load_errors
    assert data is not None
    project_root = _project_root_for_core_paths(config_dir, _studio_dir, data)

    kits = data.setdefault("kits", {})
    # Merge into existing entry to preserve fields like 'source'
    existing = kits.get(kit_slug, {})
    if not isinstance(existing, dict):
        existing = {}
    existing["format"] = "CFS"
    path_error = _apply_registered_kit_path(
        existing,
        kit_slug,
        register_context.kit_path,
        _studio_dir,
        project_root,
    )
    if path_error:
        return [path_error]
    _apply_registration_metadata(existing, kit_version, register_context)
    if register_context.install_mode == "register":
        existing.pop("resources", None)
    elif register_context.resources is not None:
        resource_errors = _validate_registration_resources(
            register_context.resources,
            kit_slug=kit_slug,
            studio_dir=_studio_dir,
            project_root=project_root,
            existing_path=existing.get("path", ""),
        )
        if resource_errors:
            return resource_errors
        existing["resources"] = register_context.resources
    kits[kit_slug] = existing
    return _persist_core_registration(core_toml, data, kit_slug)
    # @cpt-end:cpt-studio-algo-kit-config-helpers:p1:inst-register-core
# @cpt-end:cpt-studio-algo-kit-config-helpers:p1:inst-register-core-fn
