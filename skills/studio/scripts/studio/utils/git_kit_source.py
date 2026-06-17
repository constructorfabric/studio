"""
Generic Git kit source resolution.

Parses ``git/<url>[//<subdir>][@<kit>]`` CLI sources and persisted
``git:<encoded-url>[//<subdir>][@<kit>]`` sources, then materializes the
selected commit into a temporary worktree for the kit installer. CLI URLs may
be pasted raw from Git hosts; persisted sources keep the canonical encoded form.

@cpt-algo:cpt-studio-algo-generic-git-kit-installer-source-parse:p1
@cpt-algo:cpt-studio-algo-generic-git-kit-installer-source-policy:p1
@cpt-algo:cpt-studio-algo-generic-git-kit-installer-ref-resolution:p1
@cpt-algo:cpt-studio-algo-generic-git-kit-installer-url-normalization:p1
@cpt-algo:cpt-studio-algo-generic-git-kit-installer-auth-runtime:p1
@cpt-algo:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1
@cpt-state:cpt-studio-state-generic-git-kit-installer-source:p1
@cpt-dod:cpt-studio-dod-generic-git-kit-installer-source-grammar:p1
@cpt-dod:cpt-studio-dod-generic-git-kit-installer-version-ref:p1
@cpt-dod:cpt-studio-dod-generic-git-kit-installer-provenance:p1
@cpt-dod:cpt-studio-dod-generic-git-kit-installer-cache-offline:p1
@cpt-dod:cpt-studio-dod-generic-git-kit-installer-auth-redaction:p1
"""

from __future__ import annotations

# @cpt-begin:cpt-studio-state-generic-git-kit-installer-source:p1:inst-git-prov-schema-source
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional
from urllib.parse import quote, unquote, urlsplit, urlunsplit


_KIT_SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_SAFE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/+@-]{0,254}$")
_SCP_LIKE_RE = re.compile(r"^([A-Za-z0-9._-]+)@([A-Za-z0-9._-]+):(.+)$")
_SSH_SHORTHAND_RE = re.compile(r"^ssh:([A-Za-z0-9._-]+):(.+)$")
_SSH_SHORTHAND_WITH_PORT_RE = re.compile(r"^ssh:([A-Za-z0-9._-]+):([0-9]+)/(.+)$")
_SSH_URL_USER_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_HEX_ESCAPE_RE = re.compile(r"%[0-9a-fA-F]{2}")
_MALFORMED_PERCENT_ESCAPE_RE = re.compile(r"%(?![0-9a-fA-F]{2})")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_GIT_TIMEOUT = int(os.environ.get("GIT_TIMEOUT", "300"))
# @cpt-end:cpt-studio-state-generic-git-kit-installer-source:p1:inst-git-prov-schema-source


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-source-policy:p1:inst-git-policy-safe-diagnostics
class GitSourceError(ValueError):
    """Stable, redaction-safe generic Git source error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        component: str = "",
        transport: str = "",
        host_hash: str = "",
        sanitized_url_display: str = "",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.component = component
        self.transport = transport
        self.host_hash = host_hash
        self.sanitized_url_display = sanitized_url_display

    def to_result(self) -> Dict[str, str]:
        """Return a serializable error result."""
        result = {"error_code": self.code, "message": str(self)}
        if self.component:
            result["component"] = self.component
        if self.transport:
            result["transport"] = self.transport
        if self.host_hash:
            result["host_hash"] = self.host_hash
        if self.sanitized_url_display:
            result["sanitized_url_display"] = self.sanitized_url_display
        return result
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-source-policy:p1:inst-git-policy-safe-diagnostics


# @cpt-begin:cpt-studio-state-generic-git-kit-installer-source:p1:inst-git-prov-schema-source
@dataclass(frozen=True)
class GitKitSource:
    """Canonicalized git-backed kit source descriptor."""

    original_source: str
    canonical_source: str
    decoded_remote_url: str
    selected_subdirectory: str
    kit_identity: str
    transport: str
    sanitized_url_display: str
    remote_hash: str


@dataclass(frozen=True)
class GitKitResolution:
    """Resolved local checkout and source authority metadata."""

    kit_source_dir: Path
    tmp_dir: Path
    authority_metadata: Dict[str, Any]
# @cpt-end:cpt-studio-state-generic-git-kit-installer-source:p1:inst-git-prov-schema-source


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-cache-hash-components
def _hash_display(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _hash_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-cache-hash-components


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-cache-namespace
def _cache_root() -> Path:
    configured = os.environ.get("CFS_GIT_KIT_CACHE_DIR", "")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cf-studio" / "cache" / "git"
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-cache-namespace


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-source-parse:p1:inst-git-parse-canonical-source
def _canonical_encoded_url(decoded_url: str) -> str:
    return quote(decoded_url, safe="")
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-source-parse:p1:inst-git-parse-canonical-source


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-source-parse:p1:inst-git-parse-decode-once
def _decode_once(encoded_url: str) -> str:
    if not encoded_url:
        raise GitSourceError("GIT_SOURCE_INVALID_URL", "Git source URL is empty")
    if "%" in encoded_url and _MALFORMED_PERCENT_ESCAPE_RE.search(encoded_url):
        raise GitSourceError(
            "GIT_SOURCE_INVALID_URL",
            "Git source URL contains malformed percent-escapes",
        )
    decoded = unquote(encoded_url)
    if "%" in decoded and _HEX_ESCAPE_RE.search(decoded):
        raise GitSourceError(
            "GIT_SOURCE_INVALID_URL",
            "Git source URL must not contain nested percent-encoded data",
        )
    if _CONTROL_RE.search(decoded):
        raise GitSourceError("GIT_SOURCE_INVALID_URL", "Git source URL contains control characters")
    return decoded
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-source-parse:p1:inst-git-parse-decode-once


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-source-parse:p1:inst-git-parse-subdir
def _validate_subdir(subdir: str) -> str:
    if not subdir:
        return ""
    normalized = PurePosixPath(subdir.replace("\\", "/"))
    parts = normalized.parts
    if (
        subdir.startswith("/")
        or any(part in ("", ".", "..") for part in parts)
        or normalized.as_posix() != subdir
    ):
        raise GitSourceError("GIT_SOURCE_INVALID_SUBDIR", "Git source subdirectory must be a clean relative path")
    return normalized.as_posix()
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-source-parse:p1:inst-git-parse-subdir


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-source-parse:p1:inst-git-parse-transports
def _looks_like_raw_git_url(value: str) -> bool:
    return bool(
        _SCP_LIKE_RE.match(value)
        or _SSH_SHORTHAND_RE.match(value)
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value)
    )
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-source-parse:p1:inst-git-parse-transports


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-source-parse:p1:inst-git-parse-kit-identity
def _split_source_body(body: str) -> tuple[str, str, str]:
    kit_identity = ""
    body_without_kit = body
    if "@" in body:
        maybe_body, maybe_kit = body.rsplit("@", 1)
        if _KIT_SLUG_RE.fullmatch(maybe_kit):
            body_without_kit = maybe_body
            kit_identity = maybe_kit
        elif not _looks_like_raw_git_url(body):
            raise GitSourceError("GIT_SOURCE_INVALID_KIT", "Git source kit identity must be a registry-safe slug")

    encoded_url = body_without_kit
    subdir = ""
    if ".git//" in body_without_kit:
        encoded_url, subdir = body_without_kit.split(".git//", 1)
        encoded_url += ".git"
        subdir = _validate_subdir(subdir)
    elif "//" in body_without_kit and not _looks_like_raw_git_url(body_without_kit):
        encoded_url, subdir = body_without_kit.split("//", 1)
        subdir = _validate_subdir(subdir)
    return encoded_url, subdir, kit_identity
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-source-parse:p1:inst-git-parse-kit-identity


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-url-normalization:p1:inst-git-url-normalize-display
def _normalize_standard_url(parts: Any) -> str:
    scheme = parts.scheme.lower()
    userinfo = ""
    if scheme == "ssh" and parts.username:
        userinfo = f"{quote(parts.username, safe='._-')}@"
    netloc = userinfo + (parts.hostname or "")
    default_port = (
        (scheme == "https" and parts.port == 443)
        or (scheme == "ssh" and parts.port == 22)
    )
    if parts.port and not default_port:
        netloc += f":{parts.port}"
    return urlunsplit((scheme, netloc, parts.path, "", ""))
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-url-normalization:p1:inst-git-url-normalize-display


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-url-normalization:p1:inst-git-url-normalize-display
def _normalize_raw_input_url(decoded_url: str) -> str:
    ssh_port_match = _SSH_SHORTHAND_WITH_PORT_RE.match(decoded_url)
    if ssh_port_match:
        host = ssh_port_match.group(1).lower()
        port = int(ssh_port_match.group(2))
        path = ssh_port_match.group(3)
        if port < 1 or port > 65535:
            raise GitSourceError("GIT_SOURCE_INVALID_URL", "Git ssh shorthand port is invalid")
        if not path or path.startswith("/") or ".." in PurePosixPath(path).parts:
            raise GitSourceError("GIT_SOURCE_INVALID_URL", "Git ssh shorthand source path is invalid")
        return f"ssh://git@{host}:{port}/{path}"

    ssh_short_match = _SSH_SHORTHAND_RE.match(decoded_url)
    if not ssh_short_match:
        return decoded_url
    host = ssh_short_match.group(1).lower()
    path = ssh_short_match.group(2)
    if not path or path.startswith("/") or ".." in PurePosixPath(path).parts:
        raise GitSourceError("GIT_SOURCE_INVALID_URL", "Git ssh shorthand source path is invalid")
    return f"git@{host}:{path}"
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-url-normalization:p1:inst-git-url-normalize-display


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-source-policy:p1:inst-git-policy-safe-diagnostics
def _transport_and_policy(decoded_url: str) -> tuple[str, str, str]:
    scp_match = _SCP_LIKE_RE.match(decoded_url)
    if scp_match:
        user = scp_match.group(1)
        host = scp_match.group(2).lower()
        path = scp_match.group(3)
        if not path or path.startswith("/") or ".." in PurePosixPath(path).parts:
            raise GitSourceError("GIT_SOURCE_INVALID_URL", "Git scp-like source path is invalid")
        return "scp", host, f"{user}@{host}:{path}"

    parts = urlsplit(decoded_url)
    scheme = parts.scheme.lower()
    if scheme not in {"https", "ssh", "file"}:
        raise GitSourceError("GIT_SOURCE_INVALID_URL", "Git source transport must be https, ssh, scp-like, or file")
    sanitized = _normalize_standard_url(parts)
    # @cpt-begin:cpt-studio-algo-generic-git-kit-installer-source-policy:p1:inst-git-policy-reject-userinfo
    if parts.password or (parts.username and scheme != "ssh"):
        raise GitSourceError(
            "GIT_SOURCE_CREDENTIALS_IN_URL",
            "Git source URL must not contain credentials; use Git credential helpers, GIT_ASKPASS, or SSH config",
            component="userinfo",
            transport=scheme,
            host_hash=_hash_display(parts.hostname or ""),
            sanitized_url_display=sanitized,
        )
    if parts.username and not _SSH_URL_USER_RE.fullmatch(parts.username):
        raise GitSourceError("GIT_SOURCE_INVALID_URL", "Git ssh source user is invalid")
    # @cpt-end:cpt-studio-algo-generic-git-kit-installer-source-policy:p1:inst-git-policy-reject-userinfo
    # @cpt-begin:cpt-studio-algo-generic-git-kit-installer-source-policy:p1:inst-git-policy-reject-query
    if parts.query:
        raise GitSourceError(
            "GIT_SOURCE_QUERY_UNSUPPORTED",
            "Git source URL query strings are not supported",
            component="query",
            transport=scheme,
            host_hash=_hash_display(parts.hostname or ""),
            sanitized_url_display=sanitized,
        )
    # @cpt-end:cpt-studio-algo-generic-git-kit-installer-source-policy:p1:inst-git-policy-reject-query
    # @cpt-begin:cpt-studio-algo-generic-git-kit-installer-source-policy:p1:inst-git-policy-reject-fragment
    if parts.fragment:
        raise GitSourceError(
            "GIT_SOURCE_FRAGMENT_UNSUPPORTED",
            "Git source URL fragments are not supported",
            component="fragment",
            transport=scheme,
            host_hash=_hash_display(parts.hostname or ""),
            sanitized_url_display=sanitized,
        )
    # @cpt-end:cpt-studio-algo-generic-git-kit-installer-source-policy:p1:inst-git-policy-reject-fragment
    if scheme != "file" and not parts.netloc:
        raise GitSourceError("GIT_SOURCE_INVALID_URL", "Git source URL must include a host")
    host = (parts.hostname or "local").lower()
    return scheme, host, sanitized
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-source-policy:p1:inst-git-policy-safe-diagnostics


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-source-parse:p1:inst-git-parse-canonical-source
def parse_git_kit_source(source: str) -> GitKitSource:
    """Parse and validate a generic Git kit source string."""
    if source.startswith("git/"):
        body = source.removeprefix("git/")
    elif source.startswith("git:"):
        body = source.removeprefix("git:")
    else:
        raise GitSourceError("GIT_SOURCE_INVALID_PREFIX", "Git source must start with git/ or git:")

    encoded_url, subdir, kit_identity = _split_source_body(body)
    decoded_url = _normalize_raw_input_url(_decode_once(encoded_url))
    transport, host, safe_display = _transport_and_policy(decoded_url)
    canonical = "git:" + _canonical_encoded_url(safe_display)
    if subdir:
        canonical += f"//{subdir}"
    if kit_identity:
        canonical += f"@{kit_identity}"
    return GitKitSource(
        original_source=source,
        canonical_source=canonical,
        decoded_remote_url=decoded_url,
        selected_subdirectory=subdir,
        kit_identity=kit_identity,
        transport=transport,
        sanitized_url_display=safe_display,
        remote_hash=_hash_display(f"{transport}:{host}:{safe_display}"),
    )
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-source-parse:p1:inst-git-parse-canonical-source


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-install-fetch-cache
def _run_git(args: List[str], *, cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> str:
    runtime_env = os.environ.copy()
    if env:
        runtime_env.update(env)
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            env=runtime_env,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git command not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"git command timed out after {_GIT_TIMEOUT}s") from exc
    if proc.returncode:
        stderr = (proc.stderr or proc.stdout or "git command failed").strip()
        raise RuntimeError(stderr)
    return proc.stdout.strip()
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-install-fetch-cache


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-ref-resolution:p1:inst-git-ref-version-opaque
def _selector_classification(requested_ref: str, resolution_basis: str) -> str:
    if requested_ref and _FULL_SHA_RE.fullmatch(requested_ref):
        return "pinned_commit"
    if resolution_basis == "default_branch":
        return "default_branch"
    return "mutable_ref"
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-ref-resolution:p1:inst-git-ref-version-opaque


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-ref-resolution:p1:inst-git-ref-store-selector-identity
def _requested_ref_display(requested_ref: str) -> str:
    return requested_ref or "HEAD"
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-ref-resolution:p1:inst-git-ref-store-selector-identity


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-ref-resolution:p1:inst-git-ref-version-opaque
def _ref_contains_control_chars(value: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in value)


def _ref_uses_forbidden_sequences(value: str) -> bool:
    return any(token in value for token in ("..", "@{", "\\", "//"))


def _ref_violates_name_rules(value: str) -> bool:
    return (
        value in {".", ".."}
        or value.startswith("-")
        or value.endswith(".")
        or value.endswith(".lock")
    )


def _validate_requested_ref(requested_ref: str) -> str:
    normalized = str(requested_ref or "").strip()
    if not normalized:
        return ""
    if normalized == "HEAD":
        return ""
    if _FULL_SHA_RE.fullmatch(normalized):
        return normalized
    if (
        not _SAFE_REF_RE.fullmatch(normalized)
        or _ref_violates_name_rules(normalized)
        or _ref_uses_forbidden_sequences(normalized)
        or _ref_contains_control_chars(normalized)
    ):
        raise GitSourceError(
            "GIT_SOURCE_INVALID_REF",
            "Git source ref must be a branch/tag-style name or full 40-character commit SHA",
        )
    return normalized
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-ref-resolution:p1:inst-git-ref-version-opaque


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-cache-hash-components
def _subdir_hash(subdir: str) -> str:
    return _hash_key(subdir or "__root__")


def _kit_hash(kit_identity: str) -> str:
    return _hash_key(kit_identity or "__default__")


def _ref_hash(requested_ref: str) -> str:
    return _hash_key(_requested_ref_display(requested_ref))
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-cache-hash-components


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-cache-artifact-layout
def _cache_artifact_dir(
    parsed: GitKitSource,
    commit_sha: str,
) -> Path:
    return (
        _cache_root()
        / "remotes"
        / parsed.remote_hash
        / "commits"
        / commit_sha
        / "subdirs"
        / _subdir_hash(parsed.selected_subdirectory)
        / "kits"
        / _kit_hash(parsed.kit_identity)
    )
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-cache-artifact-layout


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-cache-ref-layout
def _cache_ref_manifest_path(parsed: GitKitSource, requested_ref: str) -> Path:
    return _cache_root() / "remotes" / parsed.remote_hash / "refs" / f"{_ref_hash(requested_ref)}.json"
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-cache-ref-layout


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-cache-manifest
def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-cache-manifest


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-cache-manifest
def _cache_artifact(
    parsed: GitKitSource,
    kit_source_dir: Path,
    requested_ref: str,
    commit_sha: str,
    resolution_basis: str,
) -> Dict[str, str]:
    artifact_dir = _cache_artifact_dir(parsed, commit_sha)
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = artifact_dir.with_name(artifact_dir.name + ".tmp")
    backup_dir = artifact_dir.with_name(artifact_dir.name + ".old")
    shutil.rmtree(temp_dir, ignore_errors=True)
    shutil.rmtree(backup_dir, ignore_errors=True)
    shutil.copytree(kit_source_dir, temp_dir, ignore=shutil.ignore_patterns(".git"))
    manifest = {
        "schema_version": "1.0",
        "source_type": "git",
        "decoded_remote_url_hash": parsed.remote_hash,
        "selected_subdirectory": parsed.selected_subdirectory,
        "kit_identity": parsed.kit_identity,
        "requested_ref": _requested_ref_display(requested_ref),
        "requested_ref_hash": _ref_hash(requested_ref),
        "resolved_commit_sha": commit_sha,
        "artifact_kind": "kit",
        "created_at": int(time.time()),
        "validation_basis": resolution_basis,
        "remote_display": parsed.sanitized_url_display,
    }
    try:
        _write_json(temp_dir / "artifact-manifest.json", manifest)
        old_artifact_moved = False
        if artifact_dir.exists():
            os.replace(artifact_dir, backup_dir)
            old_artifact_moved = True
        try:
            os.replace(temp_dir, artifact_dir)
        except Exception:
            if old_artifact_moved and not artifact_dir.exists() and backup_dir.exists():
                os.replace(backup_dir, artifact_dir)
            raise
        if old_artifact_moved:
            shutil.rmtree(backup_dir, ignore_errors=True)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    _write_json(
        _cache_ref_manifest_path(parsed, requested_ref),
        {
            "schema_version": "1.0",
            "source_type": "git",
            "decoded_remote_url_hash": parsed.remote_hash,
            "selected_subdirectory": parsed.selected_subdirectory,
            "kit_identity": parsed.kit_identity,
            "requested_ref": _requested_ref_display(requested_ref),
            "requested_ref_hash": _ref_hash(requested_ref),
            "resolved_commit_sha": commit_sha,
            "artifact_path_hash": _hash_key(str(artifact_dir)),
        },
    )
    return {
        "cache_remote_hash": parsed.remote_hash,
        "cache_requested_ref_hash": _ref_hash(requested_ref),
        "cache_subdir_hash": _subdir_hash(parsed.selected_subdirectory),
        "cache_kit_hash": _kit_hash(parsed.kit_identity),
    }
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-cache-manifest


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-ref-resolution:p1:inst-git-ref-offline-last-known
def _metadata_value(metadata: Dict[str, Any], key: str) -> str:
    provenance = metadata.get("source_provenance", {})
    if isinstance(provenance, dict):
        return str(provenance.get(key) or metadata.get(key) or "")
    return str(metadata.get(key) or "")
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-ref-resolution:p1:inst-git-ref-offline-last-known


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-ref-resolution:p1:inst-git-ref-offline-last-known
def _materialize_offline_last_known(
    parsed: GitKitSource,
    requested_ref: str,
    previous_metadata: Dict[str, Any],
    failure: RuntimeError,
) -> Optional[GitKitResolution]:
    commit_sha = _metadata_value(previous_metadata, "commit_sha")
    previous_remote_hash = _metadata_value(previous_metadata, "decoded_remote_url_hash")
    previous_subdir = _metadata_value(previous_metadata, "selected_subdirectory")
    previous_kit = _metadata_value(previous_metadata, "kit_identity")
    previous_requested_ref = _metadata_value(previous_metadata, "requested_ref")
    effective_requested_ref = _requested_ref_display(requested_ref)
    if effective_requested_ref == "HEAD":
        effective_requested_ref = previous_requested_ref or "HEAD"
    if (
        not commit_sha
        or previous_remote_hash != parsed.remote_hash
        or previous_subdir != parsed.selected_subdirectory
        or previous_kit != parsed.kit_identity
        or previous_requested_ref != effective_requested_ref
    ):
        return None
    artifact_dir = _cache_artifact_dir(parsed, commit_sha)
    manifest_path = artifact_dir / "artifact-manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if (
        manifest.get("decoded_remote_url_hash") != parsed.remote_hash
        or manifest.get("selected_subdirectory") != parsed.selected_subdirectory
        or manifest.get("kit_identity") != parsed.kit_identity
        or manifest.get("requested_ref") != effective_requested_ref
        or manifest.get("resolved_commit_sha") != commit_sha
    ):
        return None
    tmp_dir = Path(tempfile.mkdtemp(prefix="studio-git-kit-offline-"))
    kit_source_dir = tmp_dir / "kit"
    shutil.copytree(artifact_dir, kit_source_dir, ignore=shutil.ignore_patterns("artifact-manifest.json"))
    identity = f"{parsed.canonical_source}@{effective_requested_ref}#{commit_sha}"
    authority = {
        "source_type": "git",
        "original_source": parsed.original_source,
        "canonical_source": parsed.canonical_source,
        "effective_source": parsed.canonical_source,
        "decoded_remote_url": parsed.decoded_remote_url,
        "decoded_remote_url_hash": parsed.remote_hash,
        "requested_ref": effective_requested_ref,
        "resolved_ref": commit_sha,
        "commit_sha": commit_sha,
        "installed_version": commit_sha,
        "identity": identity,
        "resolver_mode": _selector_classification("" if effective_requested_ref == "HEAD" else effective_requested_ref, "offline_last_known"),
        "resolution_basis": "offline_last_known",
        "offline_reason": str(failure),
        "verified": "stale",
        "freshness": "last_known",
        "selected_subdirectory": parsed.selected_subdirectory,
        "kit_identity": parsed.kit_identity,
        "transport": parsed.transport,
        "sanitized_url_display": parsed.sanitized_url_display,
        "cache_remote_hash": parsed.remote_hash,
        "cache_requested_ref_hash": _ref_hash(effective_requested_ref),
        "cache_subdir_hash": _subdir_hash(parsed.selected_subdirectory),
        "cache_kit_hash": _kit_hash(parsed.kit_identity),
    }
    return GitKitResolution(kit_source_dir=kit_source_dir, tmp_dir=tmp_dir, authority_metadata=authority)
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-ref-resolution:p1:inst-git-ref-offline-last-known


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-ref-resolution:p1:inst-git-ref-checkout
def _checkout_ref(repo_dir: Path, requested_ref: str) -> str:
    if requested_ref:
        _run_git(["checkout", "--quiet", requested_ref], cwd=repo_dir)
        return "git_ref"
    return "default_branch"
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-ref-resolution:p1:inst-git-ref-checkout


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-install-fetch-cache
def materialize_git_kit_source(
    parsed: GitKitSource,
    *,
    requested_ref: str = "",
    git_auth: Optional[Dict[str, Any]] = None,
    previous_metadata: Optional[Dict[str, Any]] = None,
) -> GitKitResolution:
    """Clone, checkout, and return a selected generic Git kit source directory."""
    requested_ref = _validate_requested_ref(requested_ref)
    tmp_dir = Path(tempfile.mkdtemp(prefix="studio-git-kit-"))
    repo_dir = tmp_dir / "repo"
    env = {}
    # @cpt-begin:cpt-studio-algo-generic-git-kit-installer-auth-runtime:p1:inst-git-auth-runtime-object
    if isinstance(git_auth, dict):
        env_data = git_auth.get("env", {})
        if isinstance(env_data, dict):
            env.update({str(k): str(v) for k, v in env_data.items()})
        ssh_command = git_auth.get("ssh_command")
        if isinstance(ssh_command, str) and ssh_command:
            env["GIT_SSH_COMMAND"] = ssh_command
        askpass_command = git_auth.get("askpass_command")
        if isinstance(askpass_command, str) and askpass_command:
            env["GIT_ASKPASS"] = askpass_command
    # @cpt-end:cpt-studio-algo-generic-git-kit-installer-auth-runtime:p1:inst-git-auth-runtime-object

    try:
        # @cpt-begin:cpt-studio-algo-generic-git-kit-installer-ref-resolution:p1:inst-git-ref-store-selector-identity
        _run_git(["clone", "--quiet", parsed.decoded_remote_url, str(repo_dir)], env=env)
        resolution_basis = _checkout_ref(repo_dir, requested_ref)
        commit_sha = _run_git(["rev-parse", "HEAD"], cwd=repo_dir, env=env)
        # @cpt-end:cpt-studio-algo-generic-git-kit-installer-ref-resolution:p1:inst-git-ref-store-selector-identity
        kit_source_dir = repo_dir
        if parsed.selected_subdirectory:
            kit_source_dir = repo_dir / parsed.selected_subdirectory
            if not kit_source_dir.is_dir():
                raise RuntimeError(f"Git source subdirectory not found: {parsed.selected_subdirectory}")
    except RuntimeError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if previous_metadata:
            offline = _materialize_offline_last_known(parsed, requested_ref, previous_metadata, exc)
            if offline is not None:
                return offline
        raise
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    selector = requested_ref or "HEAD"
    identity = f"{parsed.canonical_source}@{selector}#{commit_sha}"
    cache_metadata = _cache_artifact(parsed, kit_source_dir, requested_ref, commit_sha, resolution_basis)
    # @cpt-begin:cpt-studio-state-generic-git-kit-installer-source:p1:inst-git-prov-schema-content
    authority = {
        "source_type": "git",
        "original_source": parsed.original_source,
        "canonical_source": parsed.canonical_source,
        "effective_source": parsed.canonical_source,
        "decoded_remote_url": parsed.decoded_remote_url,
        "decoded_remote_url_hash": parsed.remote_hash,
        "requested_ref": selector,
        "resolved_ref": commit_sha,
        "commit_sha": commit_sha,
        "installed_version": commit_sha,
        "identity": identity,
        "resolver_mode": _selector_classification(requested_ref, resolution_basis),
        "resolution_basis": resolution_basis,
        "verified": "verified",
        "freshness": "fresh",
        "selected_subdirectory": parsed.selected_subdirectory,
        "kit_identity": parsed.kit_identity,
        "transport": parsed.transport,
        "sanitized_url_display": parsed.sanitized_url_display,
        **cache_metadata,
    }
    # @cpt-end:cpt-studio-state-generic-git-kit-installer-source:p1:inst-git-prov-schema-content
    return GitKitResolution(
        kit_source_dir=kit_source_dir,
        tmp_dir=tmp_dir,
        authority_metadata=authority,
    )
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-fetch-cache:p1:inst-git-install-fetch-cache


# @cpt-begin:cpt-studio-algo-generic-git-kit-installer-source-parse:p1:inst-git-parse-prefix
def source_is_generic_git(source: str) -> bool:
    """Return whether a source string uses the generic git transport."""
    return source.startswith("git/") or source.startswith("git:")
# @cpt-end:cpt-studio-algo-generic-git-kit-installer-source-parse:p1:inst-git-parse-prefix
