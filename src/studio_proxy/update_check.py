"""Non-blocking update advisory checks for the global cfs proxy."""

# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-proxy-helpers
from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


_DEFAULT_TTL_SECONDS = 6 * 60 * 60
_ALLOWED_SKILL_ENTRYPOINTS = {"studio.py", "cypilot.py"}
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-proxy-helpers


def _warn(message: str) -> None:
    sys.stderr.write(f"Warning: {message}\n")


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-bg-version-check
def update_check_file() -> Path:
    """Return the cache file path for update checks."""
    configured = os.environ.get("CFS_UPDATE_CHECK_FILE", "")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cf-studio" / "update-check.json"


def read_cached_update_check() -> Optional[Dict[str, Any]]:
    """Read cached update check."""
    path = update_check_file()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _warn(f"unable to read cached update check from {path}: {exc}")
        return None


def write_cached_update_check(data: Dict[str, Any]) -> None:
    """Write cached update check."""
    path = update_check_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def should_refresh(cache: Optional[Dict[str, Any]], ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> bool:
    """Return whether the cached update check is stale."""
    if not cache:
        return True
    try:
        checked_at = int(cache.get("checked_at", 0))
    except (TypeError, ValueError):
        return True
    return int(time.time()) - checked_at >= ttl_seconds
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-bg-version-check


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-if-version-mismatch
def _version_key(version: str) -> tuple:
    cleaned = version.strip().lstrip("v")
    parts = []
    for chunk in cleaned.replace("-", ".").split("."):
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            break
    return tuple(parts) if parts else (0,)


def _is_newer(latest: str, current: str) -> bool:
    if not latest or not current:
        return False
    latest_key = _version_key(latest)
    current_key = _version_key(current)
    if latest_key != (0,) or current_key != (0,):
        return latest_key > current_key
    return latest != current
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-if-version-mismatch


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-show-update-notice
def _proxy_current_version() -> str:
    from studio_proxy import __version__
    return __version__


def _proxy_latest_version() -> str:
    req = Request(
        "https://pypi.org/pypi/constructor-studio/json",
        headers={"User-Agent": "constructor-studio-update-check/1.0"},
    )
    with urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return str(data.get("info", {}).get("version") or "")


def check_proxy() -> Dict[str, Any]:
    """Check whether the installed proxy package has an update."""
    current = _proxy_current_version()
    result: Dict[str, Any] = {
        "component": "constructor-studio-proxy",
        "current_version": current,
        "command": "pipx upgrade constructor-studio",
        "action": "current",
    }
    try:
        latest = _proxy_latest_version()
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        result.update({"action": "unknown", "message": str(exc)})
        return result
    result["latest_version"] = latest
    if _is_newer(latest, current):
        result["action"] = "update_available"
    return result
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-show-update-notice


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-bg-version-check
def check_skill_engine(skill_path: Optional[Path]) -> Dict[str, Any]:
    """Check whether the installed skill engine has an update."""
    result: Dict[str, Any] = {
        "component": "skill-engine",
        "command": "cfs update",
        "action": "current",
    }
    try:
        from studio_proxy.cache import _resolve_latest_version_with_metadata
        from studio_proxy.resolve import get_cached_version, get_project_version

        installed = get_project_version(skill_path) if skill_path else None
        installed = installed or get_cached_version() or ""
        result["current_version"] = installed
        with open(os.devnull, "w", encoding="utf-8") as devnull:
            with contextlib.redirect_stderr(devnull):
                latest, _asset_url, metadata = _resolve_latest_version_with_metadata()
        latest = latest or ""
        result["latest_version"] = latest
        if not latest:
            result.update({
                "action": "unknown",
                "message": "Latest skill-engine version unavailable",
            })
            return result
        if metadata:
            result["authority"] = metadata
        if _is_newer(latest, installed):
            result["action"] = "update_available"
    except (OSError, ValueError, RuntimeError) as exc:
        result.update({"action": "unknown", "message": str(exc)})
    return result
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-bg-version-check


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-if-version-mismatch
def check_kits(skill_path: Optional[Path], project_root: str = "") -> Dict[str, Any]:
    """Check whether configured kits have updates."""
    result: Dict[str, Any] = {
        "component": "kits",
        "action": "unknown",
        "updates_available": 0,
        "results": [],
    }
    if skill_path is None:
        result["message"] = "Skill engine not found"
        return result
    validation_error = _validate_skill_entrypoint(skill_path)
    if validation_error:
        result["message"] = validation_error
        return result

    args = [sys.executable, str(skill_path), "--json", "kit", "check-updates"]
    if project_root:
        args.extend(["--project-root", project_root])
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["message"] = str(exc)
        return result
    if proc.returncode:
        message = (proc.stderr or proc.stdout or f"kit check-updates exited {proc.returncode}").strip()
        result["message"] = message
        result["returncode"] = proc.returncode
        return result
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        result["message"] = (proc.stderr or proc.stdout or "kit check failed").strip()
        result["error"] = str(exc)
        return result
    result.update({
        "action": "update_available" if int(payload.get("updates_available", 0) or 0) else "current",
        "updates_available": int(payload.get("updates_available", 0) or 0),
        "results": payload.get("results", []),
        "commands": payload.get("commands", []),
        "status": payload.get("status", ""),
    })
    return result
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-if-version-mismatch


def _validate_skill_entrypoint(skill_path: Path) -> Optional[str]:
    """Validate that a subprocess target matches the expected skill entrypoint shape."""
    try:
        resolved = skill_path.expanduser().resolve(strict=True)
    except OSError as exc:
        return f"Skill engine entry point is not accessible: {skill_path} ({exc})"
    if not resolved.is_file():
        return f"Skill engine entry point is not a file: {resolved}"
    if resolved.name not in _ALLOWED_SKILL_ENTRYPOINTS:
        return f"Skill engine entry point is not trusted: {resolved}"
    package_dir = resolved.parent / resolved.stem
    if not (package_dir / "__init__.py").is_file():
        return f"Skill engine package is incomplete next to entry point: {resolved}"
    return None


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-bg-version-check
def run_update_check(
    *,
    skill_path: Optional[Path] = None,
    project_root: str = "",
    include_kits: bool = True,
    write_cache: bool = False,
) -> Dict[str, Any]:
    """Run all configured update checks."""
    checks = {
        "proxy": check_proxy(),
        "skill_engine": check_skill_engine(skill_path),
    }
    if include_kits:
        checks["kits"] = check_kits(skill_path, project_root=project_root)
    updates = []
    for check in checks.values():
        if check.get("action") == "update_available":
            updates.append(check)
    data = {
        "status": "PASS",
        "checked_at": int(time.time()),
        "updates_available": len(updates),
        "checks": checks,
    }
    if updates:
        data["message"] = "Updates available"
    else:
        data["message"] = "All checked components are up to date"
    if write_cache:
        write_cached_update_check(data)
    return data
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-bg-version-check


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-show-update-notice
def main(argv: Optional[list[str]] = None) -> int:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser(prog="studio-proxy-update-check")
    parser.add_argument("--skill-path", default="")
    parser.add_argument("--project-root", default="")
    parser.add_argument("--no-kits", action="store_true")
    parser.add_argument("--write-cache", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    data = run_update_check(
        skill_path=Path(args.skill_path) if args.skill_path else None,
        project_root=args.project_root,
        include_kits=not args.no_kits,
        write_cache=args.write_cache,
    )
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    return 0
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-show-update-notice


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-bg-version-check
if __name__ == "__main__":
    raise SystemExit(main())
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-bg-version-check
