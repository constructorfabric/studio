"""
Cyber Pilot -> Constructor Studio migration command.

This command is intentionally small and mechanical: it copies the legacy
cypilot install directory to the Constructor Studio directory, rewrites the
root AGENTS/CLAUDE managed blocks, updates kit sources, then delegates normal
core and kit refresh to ``cfs update``.
"""

# @cpt-flow:cpt-studio-flow-core-infra-migrate-from-cypilot:p1
# @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-migration-module
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..utils.artifacts_meta import create_backup
from ..utils import toml_utils
from ..utils._tomllib_compat import tomllib
from ..utils.ui import is_json_mode, ui
from .init import DEFAULT_INSTALL_DIR, _inject_root_agents, _inject_root_claude

LEGACY_MARKER_START = "<!-- @cpt:root-agents -->"
LEGACY_MARKER_END = "<!-- /@cpt:root-agents -->"
CF_MARKER_START = "<!-- @cf:root-agents -->"
# Source: legacy cypilot kit; Target: Constructor Studio kit
LEGACY_KIT_SOURCE = "github:cyberfabric/cyber-pilot-kit-sdlc"
CONSTRUCTOR_KIT_SOURCE = "github:constructorfabric/studio-kit-sdlc"
LEGACY_KIT_PATH = "config/kits/cypilot-sdlc"
CONSTRUCTOR_KIT_PATH = "config/kits/sdlc"
LEGACY_BASELINE_VERSION = "3.9.0"
SUPPORTED_LEGACY_MIGRATION_VERSIONS = {"3.9.0", "3.10.0"}
# Sentinel kit version written into core.toml during migration. Any
# pre-rebrand kit version is rewritten to "0", which guarantees the
# follow-up ``cfs kit update`` invocation treats the local install as
# outdated and pulls the latest release tag from the renamed
# ``constructorfabric/studio-kit-sdlc`` repo through the normal
# diff-engine update flow (same UX as a user-initiated kit update).
CONSTRUCTOR_KIT_VERSION = "0"
# @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-migration-module


def migrate_from_cypilot(
    *,
    project_root: Path,
    from_dir: Optional[str] = None,
    to_dir: str = DEFAULT_INSTALL_DIR,
    dry_run: bool = False,
    force: bool = False,
    yes: bool = False,
    skip_update: bool = False,
    force_overwrite_root: bool = False,
) -> tuple[int, Dict[str, Any]]:
    """Migrate a Cyber Pilot project in *project_root* to Constructor Studio.

    Note: Successful or partial migrations create timestamped
    {name}.{YYYYMMDD-HHMMSS}.backup files and directories alongside
    the target directory, the root AGENTS.md / CLAUDE.md, and the
    config Markdown files. These backups are not removed automatically.
    The full list of created backup paths is returned in
    ``result["backups"]`` and surfaced in the human output. Verify the
    migration succeeded and manually remove them when no longer needed.

    Set ``force_overwrite_root`` to skip the AGENTS.md / CLAUDE.md
    uncommitted-changes probe and rewrite their managed blocks anyway.
    """
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-resolve-dirs
    project_root = project_root.resolve()
    legacy_rel = from_dir or detect_legacy_cypilot_install(project_root)
    if not legacy_rel:
        return 1, {
            "status": "ERROR",
            "message": "Cyber Pilot install directory was not found",
            "project_root": project_root.as_posix(),
        }

    legacy_rel = str(legacy_rel).strip()
    target_rel = str(to_dir).strip() or DEFAULT_INSTALL_DIR
    legacy_dir, legacy_error = _resolve_project_child_dir(project_root, legacy_rel, "--from-dir")
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-resolve-dirs

    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-validate-dirs
    if legacy_error:
        return 1, {
            "status": "ERROR",
            "message": legacy_error,
            "project_root": project_root.as_posix(),
            "from_dir": legacy_rel,
        }

    target_dir, target_error = _resolve_project_child_dir(project_root, target_rel, "--to-dir")
    if target_error:
        return 1, {
            "status": "ERROR",
            "message": target_error,
            "project_root": project_root.as_posix(),
            "to_dir": target_rel,
        }

    if not legacy_dir.is_dir():
        return 1, {
            "status": "ERROR",
            "message": f"Cyber Pilot directory not found: {legacy_dir}",
            "project_root": project_root.as_posix(),
        }

    actions: Dict[str, Any] = {}
    backups: List[str] = []
    warnings: List[str] = []
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-validate-dirs

    if not dry_run and not force_overwrite_root:
        # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-probe-root-dirty
        dirty = _probe_root_files_dirty(
            project_root,
            [project_root / "AGENTS.md", project_root / "CLAUDE.md"],
        )
        if dirty:
            return 1, _dirty_root_files_result(
                project_root=project_root,
                legacy_rel=legacy_rel,
                target_dir=target_dir,
                actions=actions,
                backups=backups,
                dirty=dirty,
            )
        # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-probe-root-dirty

    if legacy_dir != target_dir:
        if target_dir.exists():
            # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-target-exists
            if not force:
                return 1, {
                    "status": "ERROR",
                    "message": f"Target directory already exists: {target_dir}",
                    "hint": "Re-run with --force to replace it, or pass --to-dir to choose another directory.",
                    "project_root": project_root.as_posix(),
                }
            # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-target-exists
            if not dry_run:
                # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-replace-target
                backup_path = create_backup(target_dir)
                if backup_path is None:
                    return 1, {
                        "status": "ERROR",
                        "message": f"Failed to create backup before replacing target directory: {target_dir}",
                        "project_root": project_root.as_posix(),
                        "from_dir": legacy_rel,
                        "studio_dir": target_dir.as_posix(),
                        "actions": {"target_dir": "backup_failed"},
                    }
                backups.append(backup_path.as_posix())
                try:
                    shutil.rmtree(target_dir)
                    shutil.copytree(legacy_dir, target_dir)
                except (OSError, shutil.Error) as exc:
                    restore_action, restore_error = _restore_target_backup_after_replace_failure(
                        backup_path,
                        target_dir,
                    )
                    error_result: Dict[str, Any] = {
                        "status": "ERROR",
                        "message": f"Failed to replace target directory after backup: {target_dir}",
                        "project_root": project_root.as_posix(),
                        "from_dir": legacy_rel,
                        "studio_dir": target_dir.as_posix(),
                        "actions": {
                            "target_dir": "replace_failed",
                            "target_dir_restore": restore_action,
                        },
                        "backups": backups,
                        "error": str(exc),
                    }
                    if restore_error:
                        error_result["restore_error"] = restore_error
                    return 1, error_result
                actions["target_dir"] = "replaced"
                # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-replace-target
            else:
                # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-replace-target
                actions["target_dir"] = "replaced"
                # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-replace-target
        else:
            # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-create-target
            actions["target_dir"] = "created"
            if not dry_run:
                try:
                    shutil.copytree(legacy_dir, target_dir)
                except (OSError, shutil.Error) as exc:
                    cleanup_action = "not_needed"
                    cleanup_error: Optional[str] = None
                    if target_dir.exists():
                        try:
                            shutil.rmtree(target_dir)
                            cleanup_action = "removed"
                        except (OSError, shutil.Error) as cleanup_exc:
                            cleanup_action = "cleanup_failed"
                            cleanup_error = str(cleanup_exc)
                    error_result: Dict[str, Any] = {
                        "status": "ERROR",
                        "message": f"Failed to create target directory from legacy directory: {target_dir}",
                        "project_root": project_root.as_posix(),
                        "from_dir": legacy_rel,
                        "studio_dir": target_dir.as_posix(),
                        "actions": {
                            "target_dir": "create_failed",
                            "target_dir_cleanup": cleanup_action,
                        },
                        "error": str(exc),
                    }
                    if cleanup_error:
                        error_result["cleanup_error"] = cleanup_error
                    return 1, error_result
            # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-create-target
    else:
        # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-reuse-target
        actions["target_dir"] = "reused"
        # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-reuse-target

    if not dry_run:
        # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-post-copy-rewrites
        rewrite_error = _run_post_copy_rewrites(
            project_root=project_root,
            legacy_rel=legacy_rel,
            target_rel=target_rel,
            target_dir=target_dir,
            actions=actions,
            backups=backups,
            warnings=warnings,
        )
        if rewrite_error is not None:
            return 1, rewrite_error
        # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-post-copy-rewrites
    else:
        # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-dry-run-actions
        actions["core_toml"] = "dry_run"
        actions["artifacts_toml"] = "dry_run"
        actions["config_toml_template_vars"] = "dry_run"
        actions["config_markdown"] = "dry_run"
        actions["root_agents"] = "dry_run"
        actions["root_claude"] = "dry_run"
        # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-dry-run-actions

    update_rc: Optional[int] = None
    update_result: Optional[Any] = None
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-followup-update
    if not skip_update and not dry_run:
        update_rc, update_result = _run_followup_update(project_root, yes=yes)
        actions["update"] = "PASS" if update_rc == 0 else "FAIL"
        if update_rc != 0:
            warnings.append("follow-up update failed")
    elif skip_update:
        actions["update"] = "skipped"
    else:
        actions["update"] = "dry_run"
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-followup-update

    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-followup-kit-update
    # Kits previously flavoured as cypilot got their `version` reset to "0"
    # in `_migrate_core_toml`. Running `cfs kit update` here triggers the
    # standard diff-engine update path against each kit's (now renamed)
    # source, pulling the latest release tag from
    # `constructorfabric/studio-kit-sdlc` (or the user's mirror) and
    # presenting any file-level conflicts through the same UX the user
    # sees on a manual `cfs kit update`.
    if not skip_update and not dry_run:
        kit_update_rc = _run_followup_kit_update(project_root=project_root, yes=yes)
        actions["kit_update"] = "PASS" if kit_update_rc == 0 else "FAIL"
        if kit_update_rc != 0:
            warnings.append("follow-up kit update failed")
    elif skip_update:
        actions["kit_update"] = "skipped"
    else:
        actions["kit_update"] = "dry_run"
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-followup-kit-update

    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-return-result
    result: Dict[str, Any] = {
        "status": "PASS" if update_rc in (None, 0) else "WARN",
        "project_root": project_root.as_posix(),
        "from_dir": legacy_rel,
        "studio_dir": target_dir.as_posix(),
        "dry_run": bool(dry_run),
        "actions": actions,
    }
    if update_result is not None:
        result["update_result"] = update_result
    if backups:
        result["backups"] = backups
    if warnings:
        result["warnings"] = warnings
    return 0 if update_rc in (None, 0) else update_rc, result
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-return-result


def detect_legacy_cypilot_install(project_root: Path) -> Optional[str]:
    """Return the legacy Cyber Pilot install dir relative to *project_root*, if any."""
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-detect-legacy
    return _read_legacy_install_dir(project_root)
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-detect-legacy


def resolve_cypilot_project_root(project_root_arg: Optional[str]) -> Optional[Path]:
    """Resolve a project root that may contain either Constructor Studio or Cyber Pilot markers."""
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-resolve-project-root
    return _resolve_project_root(project_root_arg)
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-resolve-project-root


def should_migrate_from_cypilot(
    choice: str,
    *,
    interactive: bool,
    project_root: Path,
    legacy_rel: str,
    heading: Optional[str] = None,
    prompt: Optional[str] = None,
    decline_hint: Optional[str] = None,
) -> bool:
    """Resolve ask/yes/no migration choice."""
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-should-migrate
    normalized = (choice or "ask").strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    if interactive and sys.stdin.isatty():
        return _prompt_migrate_from_cypilot(
            project_root,
            legacy_rel,
            heading=heading,
            prompt=prompt,
            decline_hint=decline_hint,
        )
    return False
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-should-migrate


def migration_declined_result(project_root: Path, legacy_rel: str, *, dry_run: bool = False) -> Dict[str, Any]:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-declined-result
    return {
        "status": "ABORTED",
        "message": "Cyber Pilot migration declined; Constructor Studio not initialized.",
        "project_root": project_root.as_posix(),
        "from_dir": legacy_rel,
        "dry_run": bool(dry_run),
        "actions": {"migration": "declined"},
    }
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-declined-result


def ensure_supported_legacy_version(
    *,
    project_root: Path,
    legacy_rel: str,
    update_choice: str,
    interactive: bool,
    dry_run: bool,
) -> tuple[bool, Dict[str, Any]]:
    """Ensure the legacy Cyber Pilot install is at a supported migration version.

    Note: when ``dry_run`` is True AND ``update_choice`` is not "no" AND
    the legacy version is NOT already in
    ``SUPPORTED_LEGACY_MIGRATION_VERSIONS``, this function takes a
    short-circuit path that returns PASS without invoking
    ``should_update_legacy_cypilot``, ``_run_legacy_update_to_baseline``,
    or the post-bump version verify. The real run remains authoritative:
    a dry-run PASS may still surface a real-run failure (``cpt`` not on
    PATH, non-tty ``"ask"`` declined, legacy install missing). This is
    intentional — dry-run is fast, real-run is exhaustive.
    """
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-check-legacy-version
    legacy_dir = (project_root / legacy_rel).resolve()
    version = read_legacy_cypilot_version(legacy_dir)
    normalized = _normalize_legacy_version(version)
    if normalized in SUPPORTED_LEGACY_MIGRATION_VERSIONS:
        return True, {
            "status": "PASS",
            "legacy_version": version,
            "normalized_legacy_version": normalized,
            "actions": {"legacy_version": "supported"},
        }
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-check-legacy-version

    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-preflight-dry-run
    if dry_run and (update_choice or "ask").strip().lower() != "no":
        return True, {
            "status": "PASS",
            "legacy_version": version,
            "target_legacy_version": LEGACY_BASELINE_VERSION,
            "dry_run": True,
            "actions": {"legacy_update": "dry_run"},
        }
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-preflight-dry-run

    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-prompt-legacy-update
    update = should_update_legacy_cypilot(
        update_choice,
        interactive=interactive,
        project_root=project_root,
        legacy_rel=legacy_rel,
        version=version,
    )
    if not update:
        return False, unsupported_legacy_version_result(project_root, legacy_rel, version, declined=True)
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-prompt-legacy-update

    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-run-legacy-update
    update_result = _run_legacy_update_to_baseline(project_root)
    if update_result.get("status") != "PASS":
        return False, {
            "status": "ERROR",
            "message": f"Failed to update Cyber Pilot skill to {LEGACY_BASELINE_VERSION}; migration not run.",
            "project_root": project_root.as_posix(),
            "from_dir": legacy_rel,
            "legacy_version": version,
            "target_legacy_version": LEGACY_BASELINE_VERSION,
            "actions": {"legacy_update": "failed"},
            "update_result": update_result,
        }
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-run-legacy-update

    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-check-updated-version
    new_version = read_legacy_cypilot_version(legacy_dir)
    new_normalized = _normalize_legacy_version(new_version)
    if new_normalized not in SUPPORTED_LEGACY_MIGRATION_VERSIONS:
        return False, {
            "status": "ERROR",
            "message": "Cyber Pilot skill update did not reach a supported migration version; migration not run.",
            "project_root": project_root.as_posix(),
            "from_dir": legacy_rel,
            "legacy_version": new_version,
            "supported_legacy_versions": sorted(SUPPORTED_LEGACY_MIGRATION_VERSIONS),
            "actions": {"legacy_update": "version_mismatch"},
            "update_result": update_result,
        }

    return True, {
        "status": "PASS",
        "legacy_version": new_version,
        "normalized_legacy_version": new_normalized,
        "target_legacy_version": LEGACY_BASELINE_VERSION,
        "actions": {"legacy_update": "updated"},
        "update_result": update_result,
    }
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-check-updated-version


def merge_legacy_preflight_result(result: Dict[str, Any], preflight: Dict[str, Any]) -> Dict[str, Any]:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-merge-preflight
    for key in ("legacy_version", "normalized_legacy_version", "target_legacy_version"):
        if key in preflight:
            result[key] = preflight[key]
    preflight_actions = preflight.get("actions")
    if isinstance(preflight_actions, dict):
        actions = result.setdefault("actions", {})
        if isinstance(actions, dict):
            for key, value in preflight_actions.items():
                actions.setdefault(key, value)
    if "update_result" in preflight:
        result["legacy_update_result"] = preflight["update_result"]
    return result
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-merge-preflight


def read_legacy_cypilot_version(legacy_dir: Path) -> Optional[str]:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-read-version
    for init_file in (
        legacy_dir / ".core" / "skills" / "cypilot" / "scripts" / "cypilot" / "__init__.py",
        legacy_dir / "skills" / "cypilot" / "scripts" / "cypilot" / "__init__.py",
        legacy_dir / "scripts" / "cypilot" / "__init__.py",
    ):
        version = _read_version_from_init(init_file)
        if version:
            return version
    return None
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-read-version


def should_update_legacy_cypilot(
    choice: str,
    *,
    interactive: bool,
    project_root: Path,
    legacy_rel: str,
    version: Optional[str],
) -> bool:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-prompt-legacy-update
    normalized = (choice or "ask").strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    if interactive and sys.stdin.isatty():
        return _prompt_update_legacy_cypilot(project_root, legacy_rel, version)
    return False
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-prompt-legacy-update


def unsupported_legacy_version_result(
    project_root: Path,
    legacy_rel: str,
    version: Optional[str],
    *,
    declined: bool,
) -> Dict[str, Any]:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-prompt-legacy-update
    status = "ABORTED" if declined else "ERROR"
    version_label = version or "unknown"
    return {
        "status": status,
        "message": (
            f"Cyber Pilot version {version_label} is not directly migratable. "
            f"Update project Cyber Pilot skill to {LEGACY_BASELINE_VERSION} first; migration not run."
        ),
        "project_root": project_root.as_posix(),
        "from_dir": legacy_rel,
        "legacy_version": version,
        "supported_legacy_versions": sorted(SUPPORTED_LEGACY_MIGRATION_VERSIONS),
        "target_legacy_version": LEGACY_BASELINE_VERSION,
        "actions": {"legacy_update": "declined" if declined else "required"},
    }
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-prompt-legacy-update


def _read_version_from_init(init_file: Path) -> Optional[str]:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-read-version
    if not init_file.is_file():
        return None
    try:
        content = init_file.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("__version__") and "=" in stripped:
            return stripped.split("=", 1)[1].strip().strip("\"'")
    return None
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-read-version


def _normalize_legacy_version(version: Optional[str]) -> Optional[str]:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-normalize-version
    if not version:
        return None
    value = version.strip()
    if value.startswith("v"):
        value = value[1:]
    return value
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-normalize-version


def _prompt_update_legacy_cypilot(project_root: Path, legacy_rel: str, version: Optional[str]) -> bool:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-prompt-update-ui
    sys.stderr.write("\n")
    sys.stderr.write(
        f"  Cyber Pilot version {version or 'unknown'} is not directly migratable.\n"
    )
    sys.stderr.write(f"  Project root: {project_root.as_posix()}\n")
    sys.stderr.write(f"  Legacy dir:   {legacy_rel}\n")
    sys.stderr.write(f"  Update project Cyber Pilot skill to {LEGACY_BASELINE_VERSION} first, then migrate? [y/N] ")
    sys.stderr.flush()
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = ""
    return answer in ("y", "yes")
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-prompt-update-ui


def _run_legacy_update_to_baseline(project_root: Path) -> Dict[str, Any]:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-run-legacy-update
    env = dict(os.environ)
    env["CYPILOT_LEGACY_UPDATE_TO_BASELINE"] = "1"
    cmd = ["cpt", "update", "--version", LEGACY_BASELINE_VERSION, "-y"]
    sys.stderr.write(
        f"Updating Cyber Pilot to the migration baseline ({LEGACY_BASELINE_VERSION}) "
        "— this may take ~30-90s.\n"
        "Press Ctrl+C to cancel; if interrupted, your Cyber Pilot install "
        "may be in a partial state. Re-run cfs init or cfs update to retry.\n"
    )
    try:
        proc = subprocess.run(
            cmd,
            cwd=project_root.as_posix(),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
    except (OSError, ValueError) as exc:
        return {"status": "ERROR", "command": cmd, "error": str(exc)}
    except KeyboardInterrupt:
        sys.stderr.write(
            "\nInterrupted by user (Ctrl+C). Your Cyber Pilot install may be "
            "in a partial state; re-run cfs init or cfs update to retry.\n"
        )
        return {
            "status": "ERROR",
            "command": cmd,
            "returncode": 130,
            "error": "Interrupted by user (Ctrl+C)",
        }
    return {
        "status": "PASS" if proc.returncode == 0 else "ERROR",
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-run-legacy-update


def _prompt_migrate_from_cypilot(
    project_root: Path,
    legacy_rel: str,
    *,
    heading: Optional[str] = None,
    prompt: Optional[str] = None,
    decline_hint: Optional[str] = None,
) -> bool:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-prompt-migration-ui
    sys.stderr.write("\n")
    sys.stderr.write(f"  {heading or 'Existing Cyber Pilot project detected.'}\n")
    sys.stderr.write(f"  Project root: {project_root.as_posix()}\n")
    sys.stderr.write(f"  Legacy dir:   {legacy_rel}\n")
    if decline_hint:
        sys.stderr.write(f"  {decline_hint}\n")
    sys.stderr.write(f"  {prompt or 'Migrate it to Constructor Studio now? [y/N] '}")
    sys.stderr.flush()
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = ""
    return answer in ("y", "yes")
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-prompt-migration-ui


def _run_followup_kit_update(*, project_root: Path, yes: bool) -> int:
    """Invoke ``cfs kit update`` to pull the latest kit release.

    The migrator has just reset every cypilot-flavoured kit's ``version``
    to ``"0"`` so the local install is guaranteed outdated. Running the
    standard kit-update command here applies the normal diff-engine flow:
    it queries each kit's (now renamed) source for the latest tag,
    downloads, and walks the user through any file-level conflicts.

    Returns the exit code from :func:`cmd_kit_update`. A non-zero return
    is surfaced as a migration warning rather than a hard failure — the
    rest of the migration has already landed and the user can re-run
    ``cfs kit update`` manually.

    In JSON mode the sub-command's own JSON payload is suppressed from
    stdout so the outer migration result stays the sole JSON document on
    the wire. Sub-stdout is discarded — its only purpose is to drive the
    diff-engine UX, which is not part of the JSON contract.
    """
    from .kit import cmd_kit_update

    args: List[str] = ["--project-root", project_root.as_posix()]
    if yes:
        args.append("--yes")
    if not is_json_mode():
        return cmd_kit_update(args)
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        return cmd_kit_update(args)


def _run_followup_update(project_root: Path, *, yes: bool) -> tuple[int, Optional[Any]]:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-run-followup-update
    from .update import cmd_update

    update_args = ["--project-root", project_root.as_posix()]
    if yes:
        # When the user opted into the migration with --yes the entire flow
        # should auto-accept every diff (kit-update changes included). The
        # legacy combination of `--no-interactive` + `--yes` caused the
        # embedded kit-update sub-flow to auto-decline every file because
        # `--no-interactive` was treated as a hard "decline all" upstream.
        # Pass `--yes` alone so accept-everything wins.
        update_args.append("--yes")
    else:
        # User did not request `--yes`. We still need a non-blocking run
        # (the migrator is not interactive past its own prompts), so
        # suppress interactive prompts; any pending kit-diff is left to the
        # follow-up `cfs kit update` step the migrator runs next.
        update_args.append("--no-interactive")

    if not is_json_mode():
        return cmd_update(update_args), None

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = cmd_update(update_args)
    raw = stdout.getvalue().strip()
    if not raw:
        return rc, None
    try:
        return rc, json.loads(raw)
    except json.JSONDecodeError:
        return rc, raw
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-run-followup-update


def _restore_target_backup_after_replace_failure(backup_path: Path, target_dir: Path) -> tuple[str, Optional[str]]:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-restore-target
    try:
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(backup_path, target_dir)
    except (OSError, shutil.Error) as exc:
        return "restore_failed", str(exc)
    return "restored", None
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-restore-target


def _run_post_copy_rewrites(
    *,
    project_root: Path,
    legacy_rel: str,
    target_rel: str,
    target_dir: Path,
    actions: Dict[str, Any],
    backups: List[str],
    warnings: List[str],
) -> Optional[Dict[str, Any]]:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-backup-root-files
    root_agents_path = project_root / "AGENTS.md"
    root_claude_path = project_root / "CLAUDE.md"
    root_agents_backup = (
        create_backup(root_agents_path) if root_agents_path.is_file() else None
    )
    root_claude_backup = (
        create_backup(root_claude_path) if root_claude_path.is_file() else None
    )
    if root_agents_backup is not None:
        backups.append(root_agents_backup.as_posix())
        actions["root_agents_backup"] = "created"
    if root_claude_backup is not None:
        backups.append(root_claude_backup.as_posix())
        actions["root_claude_backup"] = "created"

    config_md_names = ("AGENTS.md", "SKILL.md", "README.md")
    config_md_dir = target_dir / "config"
    config_md_paths: Dict[str, Path] = {
        name: config_md_dir / name for name in config_md_names
    }
    config_md_backups: Dict[str, Optional[Path]] = {}
    for name, path in config_md_paths.items():
        backup = create_backup(path) if path.is_file() else None
        config_md_backups[name] = backup
        if backup is not None:
            backups.append(backup.as_posix())
            actions.setdefault("config_md_backup", {})[name] = "created"
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-backup-root-files

    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-run-rewrite-steps
    rewrites: List[tuple[str, Callable[[], Any]]] = [
        ("core_toml",
         lambda: _migrate_core_toml(
             target_dir / "config" / "core.toml",
             warnings=warnings,
         )),
        ("artifacts_toml",
         lambda: _migrate_artifacts_toml(
             target_dir / "config" / "artifacts.toml",
             warnings=warnings,
         )),
        ("config_toml_template_vars",
         lambda: _migrate_config_toml_template_vars(target_dir / "config")),
        ("config_markdown", lambda: _migrate_config_markdown(target_dir / "config")),
        ("root_agents", lambda: _replace_root_block_with_warnings(project_root / "AGENTS.md", target_rel, warnings)),
        ("root_claude", lambda: _replace_root_block_with_warnings(project_root / "CLAUDE.md", target_rel, warnings)),
        ("host_integrations", lambda: _cleanup_legacy_host_integrations(project_root, warnings, studio_dir=target_dir)),
    ]

    for rewrite_step, rewrite in rewrites:
        try:
            actions[rewrite_step] = rewrite()
        except OSError as exc:
            result: Dict[str, Any] = {
                "status": "ERROR",
                "message": f"Failed post-copy rewrite step: {rewrite_step}",
                "project_root": project_root.as_posix(),
                "from_dir": legacy_rel,
                "studio_dir": target_dir.as_posix(),
                "rewrite_step": rewrite_step,
                "actions": dict(actions),
                "error": str(exc),
            }
            if backups:
                result["backups"] = list(backups)
            if warnings:
                result["warnings"] = list(warnings)
            restore_actions: Dict[str, str] = {}
            for label, backup_path, dest_path in (
                ("root_agents", root_agents_backup, root_agents_path),
                ("root_claude", root_claude_backup, root_claude_path),
            ):
                if backup_path is None:
                    restore_actions[label] = "no_backup"
                    continue
                try:
                    shutil.copy2(backup_path, dest_path)
                    restore_actions[label] = "restored"
                except (OSError, shutil.Error) as restore_exc:
                    restore_actions[label] = f"restore_failed: {restore_exc}"
            actions["root_files_restore"] = restore_actions
            md_restore_actions: Dict[str, str] = {}
            for md_name, md_backup_path in config_md_backups.items():
                if md_backup_path is None:
                    md_restore_actions[md_name] = "no_backup"
                    continue
                try:
                    shutil.copy2(md_backup_path, config_md_paths[md_name])
                    md_restore_actions[md_name] = "restored"
                except (OSError, shutil.Error) as restore_exc:
                    md_restore_actions[md_name] = f"restore_failed: {restore_exc}"
            actions["config_md_restore"] = md_restore_actions
            result["actions"] = dict(actions)
            return result
    return None
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-run-rewrite-steps


def _resolve_project_root(project_root_arg: Optional[str]) -> Optional[Path]:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-resolve-project-root
    if project_root_arg:
        return Path(project_root_arg).resolve()

    current = Path.cwd().resolve()
    for parent in [current, *current.parents]:
        agents = parent / "AGENTS.md"
        if not agents.is_file():
            continue
        try:
            head = agents.read_text(encoding="utf-8")[:1024]
        except OSError:
            continue
        if LEGACY_MARKER_START in head or CF_MARKER_START in head:
            return parent
    return current if (current / ".git").exists() else None
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-resolve-project-root


def _resolve_project_child_dir(project_root: Path, rel_path: str, option_name: str) -> tuple[Path, Optional[str]]:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-child-dir-guard
    candidate = Path(rel_path)
    if candidate.is_absolute():
        return project_root, f"{option_name} must be a relative path inside the project root"

    resolved_root = project_root.resolve()
    resolved_dir = (resolved_root / candidate).resolve()
    if resolved_dir == resolved_root or not resolved_dir.is_relative_to(resolved_root):
        return project_root, f"{option_name} must resolve to a child directory inside the project root"

    return resolved_dir, None
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-child-dir-guard


def _read_legacy_install_dir(project_root: Path) -> Optional[str]:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-read-legacy-install
    content = ""
    agents_file = project_root / "AGENTS.md"
    if agents_file.is_file():
        try:
            content = agents_file.read_text(encoding="utf-8")
        except OSError:
            content = ""
        data = toml_utils.parse_toml_from_markdown(content)
        # Legacy cypilot installs used cypilot_path or cypilot key
        for key in ("cypilot_path", "cypilot"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-read-legacy-install

    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-read-legacy-install
    if CF_MARKER_START in content and LEGACY_MARKER_START not in content:
        return None

    # Legacy cypilot candidate directory names
    for candidate in ("cypilot", ".bootstrap", ".cypilot", ".cpt"):
        candidate_dir = project_root / candidate
        if candidate_dir.is_dir() and (
            (candidate_dir / "config" / "core.toml").is_file()
            or (candidate_dir / "core.toml").is_file()
        ):
            return candidate
    return None
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-read-legacy-install


def _probe_root_files_dirty(project_root: Path, paths: List[Path]) -> List[str]:
    """Return root-file names that are dirty/untracked per ``git status --porcelain``.

    Advisory only: returns ``[]`` when git is unavailable, when *project_root*
    is not a git repo, on subprocess timeout, or when no probed path is a
    tracked file. The probe never raises.
    """
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-probe-git-dirty
    names = [p.name for p in paths if p.is_file()]
    if not names:
        return []
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--"] + names,
            cwd=project_root.as_posix(),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
    if proc.returncode != 0:
        return []
    dirty: List[str] = []
    for line in proc.stdout.splitlines():
        if len(line) > 3:
            dirty.append(line[3:].strip())
    return dirty
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-probe-git-dirty


def _dirty_root_files_result(
    *,
    project_root: Path,
    legacy_rel: str,
    target_dir: Path,
    actions: Dict[str, Any],
    backups: List[str],
    dirty: List[str],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "status": "ERROR",
        "message": (
            "Refusing to rewrite root managed block: AGENTS.md "
            "and/or CLAUDE.md have uncommitted changes. Commit or stash "
            "them first, then re-run the migration."
        ),
        "project_root": project_root.as_posix(),
        "from_dir": legacy_rel,
        "studio_dir": target_dir.as_posix(),
        "actions": dict(actions),
        "root_files_dirty": dirty,
    }
    if backups:
        result["backups"] = list(backups)
    return result


def _replace_root_block_with_warnings(target_file: Path, install_dir: str, warnings: List[str]) -> str:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-replace-root-blocks
    if target_file.is_file():
        content = target_file.read_text(encoding="utf-8")
        _, malformed_legacy_block = _remove_legacy_block(content)
        if malformed_legacy_block:
            warnings.append(
                f"{target_file.name} contains a preserved malformed legacy root block "
                f"({LEGACY_MARKER_START} without {LEGACY_MARKER_END}); manual cleanup may be needed"
            )
    return _replace_root_block(target_file, install_dir)
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-replace-root-blocks


def _replace_root_block(target_file: Path, install_dir: str) -> str:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-replace-root-blocks
    if target_file.is_file():
        content = target_file.read_text(encoding="utf-8")
        stripped, _ = _remove_legacy_block(content)
        if stripped != content:
            target_file.write_text(stripped, encoding="utf-8")
    if target_file.name == "CLAUDE.md":
        return _inject_root_claude(target_file.parent, install_dir)
    return _inject_root_agents(target_file.parent, install_dir)
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-replace-root-blocks


def _remove_legacy_block(content: str) -> tuple[str, bool]:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-remove-legacy-block
    if LEGACY_MARKER_START not in content:
        return content, False
    parts: List[str] = []
    cursor = 0
    changed = False
    malformed = False
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-remove-legacy-block

    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-remove-legacy-block
    while True:
        start = content.find(LEGACY_MARKER_START, cursor)
        if start == -1:
            parts.append(content[cursor:])
            break
        end = content.find(LEGACY_MARKER_END, start + len(LEGACY_MARKER_START))
        if end == -1:
            malformed = True
            parts.append(content[cursor:])
            break
        parts.append(content[cursor:start])
        cursor = end + len(LEGACY_MARKER_END)
        changed = True
    if not changed:
        return content, malformed
    return "".join(parts).lstrip("\n"), malformed
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-remove-legacy-block


def _migrate_core_toml(core_toml: Path, warnings: Optional[List[str]] = None) -> str:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-migrate-core-toml
    if not core_toml.is_file():
        if warnings is not None:
            warnings.append(
                f"core.toml not found at {core_toml}; migration "
                f"skipped this file."
            )
        return "missing"
    try:
        with open(core_toml, "rb") as f:
            data = tomllib.load(f)
    except (OSError, ValueError) as exc:
        if warnings is not None:
            warnings.append(
                f"core.toml could not be parsed ({exc}); migration did "
                f"not update this file. Manual review required."
            )
        return "invalid"

    changed = False
    kits = data.get("kits")
    if isinstance(kits, dict):
        # Remove legacy cypilot-sdlc kit slug, promote to sdlc
        legacy = kits.pop("cypilot-sdlc", None)
        if legacy is not None:
            changed = True
            if "sdlc" not in kits:
                kits["sdlc"] = legacy
        for kit_data in kits.values():
            if not isinstance(kit_data, dict):
                continue
            had_legacy_kit_signal = (
                kit_data.get("path") == LEGACY_KIT_PATH
                or kit_data.get("source") == LEGACY_KIT_SOURCE
                or kit_data.get("format") == "Cypilot"
            )
            if kit_data.get("path") == LEGACY_KIT_PATH:
                kit_data["path"] = CONSTRUCTOR_KIT_PATH
                changed = True
            if kit_data.get("source") == LEGACY_KIT_SOURCE:
                kit_data["source"] = CONSTRUCTOR_KIT_SOURCE
                changed = True
            # Kit-bundle format identifier rename: Cypilot -> CFS
            if kit_data.get("format") == "Cypilot":
                kit_data["format"] = "CFS"
                changed = True
            # Reset pre-rebrand kit version to the sentinel "0". Any kit
            # that was previously cypilot-flavoured (legacy path / source /
            # format) gets `version = "0"` so the follow-up `cfs kit update`
            # invocation sees the install as outdated and pulls the latest
            # release of the renamed kit repo through the normal diff-engine
            # update flow.
            if had_legacy_kit_signal and kit_data.get("version") != CONSTRUCTOR_KIT_VERSION:
                kit_data["version"] = CONSTRUCTOR_KIT_VERSION
                changed = True
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-migrate-core-toml

    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-migrate-core-toml
    if "system" in data:
        del data["system"]
        changed = True
        if warnings is not None:
            warnings.append(
                "Removed legacy [system] table from core.toml. "
                "If your install had custom data there, recover it "
                "from the timestamped .backup directory under project_root."
            )

    if changed:
        toml_utils.dump(data, core_toml, header_comment="Constructor Studio project configuration")
        return "updated"
    return "unchanged"
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-migrate-core-toml


def _migrate_artifacts_toml(
    artifacts_toml: Path,
    warnings: Optional[List[str]] = None,
) -> str:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-migrate-artifacts-toml
    if not artifacts_toml.is_file():
        if warnings is not None:
            warnings.append(
                f"artifacts.toml not found at {artifacts_toml}; migration "
                f"skipped this file."
            )
        return "missing"
    try:
        with open(artifacts_toml, "rb") as f:
            data = tomllib.load(f)
    except (OSError, ValueError) as exc:
        if warnings is not None:
            warnings.append(
                f"artifacts.toml could not be parsed ({exc}); migration "
                f"did not update this file. Manual review required."
            )
        return "invalid"

    changed = False
    for system in data.get("systems", []):
        if _migrate_system_kit_refs(system):
            changed = True

    if changed:
        toml_utils.dump(data, artifacts_toml, header_comment="Constructor Studio artifacts registry")
        return "updated"
    return "unchanged"
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-migrate-artifacts-toml


def _migrate_system_kit_refs(system: Any) -> bool:
    changed = False
    if not isinstance(system, dict):
        return False
    # Legacy cypilot-sdlc kit slug -> sdlc
    if system.get("kit") == "cypilot-sdlc":
        system["kit"] = "sdlc"
        changed = True
    for child in system.get("children", []):
        if _migrate_system_kit_refs(child):
            changed = True
    return changed


def _migrate_config_toml_template_vars(config_dir: Path) -> List[str]:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-migrate-config-toml-template-vars
    # Rewrite the single template placeholder {cypilot_path} -> {cf-studio-path}
    # in all *.toml files under config_dir (e.g. pr-review.toml). Structured
    # fields that do not contain the placeholder are untouched. Skip files with
    # OSError and continue.
    changed: List[str] = []
    for path in sorted(config_dir.rglob("*.toml")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        new_text = text.replace("{cypilot_path}", "{cf-studio-path}")
        if new_text != text:
            try:
                path.write_text(new_text, encoding="utf-8")
            except OSError:
                continue
            changed.append(path.relative_to(config_dir).as_posix())
    return changed
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-migrate-config-toml-template-vars


def _migrate_config_markdown(config_dir: Path) -> List[str]:
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-migrate-config-markdown
    # Conservative rewriter: only rewrite well-known mechanical tokens across
    # all *.md files under config_dir (recursively, including config/rules/*.md
    # and any other subdirectory).  Applies four substitution rules unchanged:
    #   {cypilot_path}  ->  {cf-studio-path}
    #   `cpt            ->  `cfs
    #    cpt            ->   cfs   (space-surrounded token only)
    #   Cypilot         ->  Constructor Studio
    # Preserves cpt. (punctuated) and line-start cpt per
    # project_markdown_rewriter_conservative rule.  Tolerates per-file OSError
    # gracefully (skips the file, continues).  Returns paths relative to
    # config_dir (e.g. 'rules/foo.md', 'AGENTS.md').
    changed: List[str] = []
    for path in sorted(config_dir.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        new_text = (
            text
            .replace("{cypilot_path}", "{cf-studio-path}")
            .replace("`cpt ", "`cfs ")
            .replace(" cpt ", " cfs ")
            .replace("Cypilot", "Constructor Studio")
        )
        if new_text != text:
            try:
                path.write_text(new_text, encoding="utf-8")
            except OSError:
                continue
            changed.append(path.relative_to(config_dir).as_posix())
    return changed
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-migrate-config-markdown


def _cleanup_legacy_host_integrations(
    project_root: Path,
    warnings: List[str],
    studio_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Delete pre-rebrand host-integration artifacts AND regenerate fresh ones.

    Sweeps every supported host (``claude``, ``windsurf``, ``cursor``,
    ``copilot``, ``openai``) and:
      1. removes legacy ``cypilot-*`` / ``cf-constructor-*`` agent /
         command / workflow files;
      2. removes legacy per-workflow skill directories (e.g.
         ``.claude/skills/cypilot``, ``.claude/skills/cypilot-analyze``);
      3. removes legacy install markers (``.codex/.cypilot-installed`` etc.);
      4. regenerates fresh ``cf-*`` host-integration files for every host
         that had at least one legacy artifact (so a user that previously
         had Claude/Windsurf/Cursor/Codex set up gets the new integration
         layout produced for them automatically).

    Only files whose body is a pure generator stub are removed; user-edited
    files are preserved. Returns ``{"removed": {agent: [relpath, ...]},
    "regenerated": [agent, ...]}``.
    """
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-cleanup-legacy-host-import
    # Defer the import: agents.py owns the cleanup constants and helpers; the
    # migrator borrows them so there is exactly one source of truth for
    # legacy-artifact recognition.
    try:
        from .agents import (
            _cleanup_studio_legacy_subagents,
            _cleanup_studio_legacy_markers,
            _cleanup_legacy_skill_dirs,
            _is_legacy_generator_stub,
            _LEGACY_TOOL_SKILL_PATHS,
            _process_single_agent,
            _default_agents_config,
        )
    except ImportError as exc:
        warnings.append(f"host-integration cleanup skipped (import failed: {exc})")
        return {"removed": {}, "regenerated": []}
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-cleanup-legacy-host-import

    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-cleanup-legacy-host-sweep
    removed_by_agent: Dict[str, List[str]] = {}
    for agent in ("claude", "windsurf", "cursor", "copilot", "openai"):
        removed: List[str] = []
        removed.extend(_cleanup_studio_legacy_subagents(agent, project_root, dry_run=False))
        removed.extend(_cleanup_studio_legacy_markers(agent, project_root, dry_run=False))
        removed.extend(_cleanup_legacy_skill_dirs(agent, project_root, dry_run=False))
        # Per-tool single-file legacy skill paths (bare `cypilot.md`,
        # `cypilot.mdc`, etc.) — only delete when the content is a pure
        # legacy generator stub. Files with user-added content are kept.
        for legacy_rel in _LEGACY_TOOL_SKILL_PATHS.get(agent, []):
            legacy_file = project_root / legacy_rel
            if not legacy_file.is_file():
                continue
            try:
                content = legacy_file.read_text(encoding="utf-8")
            except OSError:
                continue
            if not _is_legacy_generator_stub(content):
                continue
            try:
                legacy_file.unlink()
                removed.append(legacy_rel)
            except OSError:
                pass
        if removed:
            removed_by_agent[agent] = removed
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-cleanup-legacy-host-sweep

    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-cleanup-legacy-host-regen
    # Regenerate every host that had at least one legacy artifact. The
    # presence of any cleaned-up file proves the host was set up
    # previously; the user expects an equivalent install in the new
    # layout, so we run the generator inline rather than waiting for the
    # next manual `cfs generate-agents` invocation.
    regenerated: List[str] = []
    if studio_dir is not None and removed_by_agent:
        cfg = _default_agents_config()
        for agent in removed_by_agent:
            try:
                _process_single_agent(
                    agent, project_root, studio_dir, cfg, None, dry_run=False,
                )
                regenerated.append(agent)
            except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                # Surface failure as warning — host regen is best-effort.
                warnings.append(f"failed to regenerate {agent} integration: {exc}")

    return {"removed": removed_by_agent, "regenerated": regenerated}
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-cleanup-legacy-host-regen


def _human_migrate_ok(data: Dict[str, Any]) -> None:  # pyright: ignore
    # @cpt-begin:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-human-output
    prefix = "[dry-run] " if data.get("dry_run") else ""
    ui.header(f"{prefix}Cyber Pilot -> Constructor Studio Migration")
    ui.detail("Project root", str(data.get("project_root", "")))
    ui.detail("From", str(data.get("from_dir", "")))
    ui.detail("To", str(data.get("studio_dir", "")))
    for key, value in (data.get("actions") or {}).items():
        ui.file_action(key, str(value))
    if data.get("warnings"):
        for warning in data["warnings"]:
            ui.warn(str(warning))
    if data.get("backups"):
        ui.detail("Backups created", "")
        for backup_path in data["backups"]:
            ui.detail("  ", str(backup_path))
    if data.get("status") in ("PASS", None) and not data.get("dry_run"):
        ui.blank()
        ui.warn(
            "Strongly recommended next step:\n"
            "    In your IDE chat: cf migrate from cypilot\n"
            "    Runs Scanner -> Planner -> Migrator -> Verifier with your\n"
            "    approval before each agent. Catches residual cypilot/cpt\n"
            "    references in source code, CI, docs, agent configs, and\n"
            "    workspaces -- files the deterministic migration did not touch."
        )
    # @cpt-end:cpt-studio-flow-core-infra-migrate-from-cypilot:p1:inst-human-output
