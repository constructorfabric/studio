"""
Generic Git kit source resolution.

Parses ``git/<encoded-url>[//<subdir>][@<kit>]`` CLI sources and persisted
``git:<encoded-url>[//<subdir>][@<kit>]`` sources, then materializes the
selected commit into a temporary worktree for the kit installer.

@cpt-algo:cpt-studio-algo-generic-git-kit-installer-source-parse:p1
@cpt-algo:cpt-studio-algo-generic-git-kit-installer-source-policy:p1
@cpt-algo:cpt-studio-algo-generic-git-kit-installer-ref-resolution:p1
@cpt-algo:cpt-studio-algo-generic-git-kit-installer-url-normalization:p1
@cpt-algo:cpt-studio-algo-generic-git-kit-installer-auth-runtime:p1
@cpt-dod:cpt-studio-dod-generic-git-kit-installer-source-grammar:p1
@cpt-dod:cpt-studio-dod-generic-git-kit-installer-version-ref:p1
@cpt-dod:cpt-studio-dod-generic-git-kit-installer-provenance:p1
@cpt-dod:cpt-studio-dod-generic-git-kit-installer-auth-redaction:p1
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional
from urllib.parse import quote, unquote, urlsplit, urlunsplit


_KIT_SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_SCP_LIKE_RE = re.compile(r"^[A-Za-z0-9._-]+@([A-Za-z0-9._-]+):(.+)$")
_HEX_ESCAPE_RE = re.compile(r"%[0-9a-fA-F]{2}")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_GIT_TIMEOUT = int(os.environ.get("GIT_TIMEOUT", "300"))


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


@dataclass(frozen=True)
class GitKitSource:
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
    kit_source_dir: Path
    tmp_dir: Path
    authority_metadata: Dict[str, Any]


def _hash_display(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _canonical_encoded_url(decoded_url: str) -> str:
    return quote(decoded_url, safe="")


def _decode_once(encoded_url: str) -> str:
    if not encoded_url:
        raise GitSourceError("GIT_SOURCE_INVALID_URL", "Git source URL is empty")
    decoded = unquote(encoded_url)
    if decoded == encoded_url and (
        "://" in encoded_url or encoded_url.startswith("git@") or encoded_url.startswith("file:")
    ):
        raise GitSourceError(
            "GIT_SOURCE_INVALID_URL",
            "Git source transport URL must be percent-encoded",
        )
    if "%" in decoded and _HEX_ESCAPE_RE.search(decoded):
        raise GitSourceError(
            "GIT_SOURCE_INVALID_URL",
            "Git source URL must not contain nested percent-encoded data",
        )
    if _CONTROL_RE.search(decoded):
        raise GitSourceError("GIT_SOURCE_INVALID_URL", "Git source URL contains control characters")
    return decoded


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


def _split_source_body(body: str) -> tuple[str, str, str]:
    kit_identity = ""
    body_without_kit = body
    if "@" in body:
        maybe_body, maybe_kit = body.rsplit("@", 1)
        if _KIT_SLUG_RE.fullmatch(maybe_kit):
            body_without_kit = maybe_body
            kit_identity = maybe_kit
        else:
            raise GitSourceError("GIT_SOURCE_INVALID_KIT", "Git source kit identity must be a registry-safe slug")

    encoded_url = body_without_kit
    subdir = ""
    if "//" in body_without_kit:
        encoded_url, subdir = body_without_kit.split("//", 1)
        subdir = _validate_subdir(subdir)
    return encoded_url, subdir, kit_identity


def _sanitize_standard_url(parts: Any) -> str:
    netloc = parts.hostname or ""
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path, "", ""))


def _transport_and_policy(decoded_url: str) -> tuple[str, str, str]:
    scp_match = _SCP_LIKE_RE.match(decoded_url)
    if scp_match:
        host = scp_match.group(1).lower()
        path = scp_match.group(2)
        if not path or path.startswith("/") or ".." in PurePosixPath(path).parts:
            raise GitSourceError("GIT_SOURCE_INVALID_URL", "Git scp-like source path is invalid")
        return "scp", host, f"git@{host}:{path}"

    parts = urlsplit(decoded_url)
    scheme = parts.scheme.lower()
    if scheme not in {"https", "ssh", "file"}:
        raise GitSourceError("GIT_SOURCE_INVALID_URL", "Git source transport must be https, ssh, scp-like, or file")
    if parts.username or parts.password:
        sanitized = _sanitize_standard_url(parts)
        raise GitSourceError(
            "GIT_SOURCE_CREDENTIALS_IN_URL",
            "Git source URL must not contain credentials; use Git credential helpers, GIT_ASKPASS, or SSH config",
            component="userinfo",
            transport=scheme,
            host_hash=_hash_display(parts.hostname or ""),
            sanitized_url_display=sanitized,
        )
    if parts.query:
        sanitized = _sanitize_standard_url(parts)
        raise GitSourceError(
            "GIT_SOURCE_QUERY_UNSUPPORTED",
            "Git source URL query strings are not supported",
            component="query",
            transport=scheme,
            host_hash=_hash_display(parts.hostname or ""),
            sanitized_url_display=sanitized,
        )
    if parts.fragment:
        sanitized = _sanitize_standard_url(parts)
        raise GitSourceError(
            "GIT_SOURCE_FRAGMENT_UNSUPPORTED",
            "Git source URL fragments are not supported",
            component="fragment",
            transport=scheme,
            host_hash=_hash_display(parts.hostname or ""),
            sanitized_url_display=sanitized,
        )
    if scheme != "file" and not parts.netloc:
        raise GitSourceError("GIT_SOURCE_INVALID_URL", "Git source URL must include a host")
    sanitized = _sanitize_standard_url(parts)
    host = (parts.hostname or "local").lower()
    return scheme, host, sanitized


def parse_git_kit_source(source: str) -> GitKitSource:
    """Parse and validate a generic Git kit source string."""
    if source.startswith("git/"):
        body = source.removeprefix("git/")
    elif source.startswith("git:"):
        body = source.removeprefix("git:")
    else:
        raise GitSourceError("GIT_SOURCE_INVALID_PREFIX", "Git source must start with git/ or git:")

    encoded_url, subdir, kit_identity = _split_source_body(body)
    decoded_url = _decode_once(encoded_url)
    transport, host, safe_display = _transport_and_policy(decoded_url)
    canonical = "git:" + _canonical_encoded_url(decoded_url)
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
    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "git command failed").strip()
        raise RuntimeError(stderr)
    return proc.stdout.strip()


def _selector_classification(requested_ref: str, resolution_basis: str) -> str:
    if requested_ref and _FULL_SHA_RE.fullmatch(requested_ref):
        return "pinned_commit"
    if resolution_basis == "default_branch":
        return "default_branch"
    return "mutable_ref"


def _checkout_ref(repo_dir: Path, requested_ref: str) -> str:
    if requested_ref:
        _run_git(["checkout", "--quiet", requested_ref], cwd=repo_dir)
        return "git_ref"
    return "default_branch"


def materialize_git_kit_source(
    parsed: GitKitSource,
    *,
    requested_ref: str = "",
    git_auth: Optional[Dict[str, Any]] = None,
) -> GitKitResolution:
    """Clone, checkout, and return a selected generic Git kit source directory."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="studio-git-kit-"))
    repo_dir = tmp_dir / "repo"
    env = {}
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

    try:
        _run_git(["clone", "--quiet", "--no-checkout", parsed.decoded_remote_url, str(repo_dir)], env=env)
        resolution_basis = _checkout_ref(repo_dir, requested_ref)
        commit_sha = _run_git(["rev-parse", "HEAD"], cwd=repo_dir, env=env)
        kit_source_dir = repo_dir
        if parsed.selected_subdirectory:
            kit_source_dir = repo_dir / parsed.selected_subdirectory
            if not kit_source_dir.is_dir():
                raise RuntimeError(f"Git source subdirectory not found: {parsed.selected_subdirectory}")
    except Exception:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    selector = requested_ref or "HEAD"
    identity = f"{parsed.canonical_source}@{selector}#{commit_sha}"
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
        "content_identity": {
            "vcs": "git",
            "commit_sha": commit_sha,
            "subdirectory": parsed.selected_subdirectory,
            "identity": identity,
        },
    }
    return GitKitResolution(
        kit_source_dir=kit_source_dir,
        tmp_dir=tmp_dir,
        authority_metadata=authority,
    )


def source_is_generic_git(source: str) -> bool:
    return source.startswith("git/") or source.startswith("git:")
