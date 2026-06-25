"""
Update command — refresh an existing Constructor Studio installation in-place.

Safety rules for config/:
- .core/  → full replace from cache (read-only reference)
- whatsnew.toml, version.toml → install-root metadata refreshed from cache
- .gen/   → aggregate files only (AGENTS.md, SKILL.md, README.md)
- config/ → kit source files + user config:
  - core.toml, artifacts.toml   → only via migration when version is higher
  - AGENTS.md, SKILL.md, README.md → only create if missing
  - kits/{slug}/                → skipped by default; updated only with --with-kits yes|true
Pipeline:
1. Replace .core/ and install-root metadata from cache
2. Update kits only when explicitly requested
3. Write aggregate .gen/ files
4. Ensure config/ scaffold files exist (create only if missing)
5. Run self-check to verify kit integrity

@cpt-flow:cpt-studio-flow-version-config-update:p1
@cpt-algo:cpt-studio-algo-version-config-update-pipeline:p1
@cpt-algo:cpt-studio-algo-version-config-compare-versions:p1
@cpt-algo:cpt-studio-algo-version-config-layout-restructure:p1
@cpt-state:cpt-studio-state-version-config-installation:p1
@cpt-dod:cpt-studio-dod-version-config-update:p1
"""
# pylint: disable=protected-access  # _with_core_toml_lock is the canonical lock API for this package

# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-update-imports
import argparse
import logging
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils._tomllib_compat import tomllib
from .init import (
    CACHE_DIR,
    COPY_ROOT_FILES,
    CORE_SUBDIR,
    DEFAULT_INSTALL_DIR,
    _CONFIG_README_PREAMBLE,
    _add_legacy_migration_args,
    _copy_from_cache,
    _core_readme,
    _cache_allows_root_metadata,
    _dry_run_copy_results,
    _persist_install_metadata,
    _read_install_tracking,
    _read_kit_tracking,
    _read_kit_tracking_state,
    _render_error_entries,
    _run_default_legacy_migration,
    _inject_root_agents,
    _inject_root_claude,
    _write_gitignore_block,
)
from ..utils.ui import ui
from ..utils.whatsnew import read_whatsnew, show_core_whatsnew, show_kit_whatsnew
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-update-imports

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _KitSourceResolution:
    """Resolved source inputs for one kit update attempt."""

    kit_src: Optional[Path]
    tmp_to_clean: Optional[Path]
    authority_metadata: Optional[Dict[str, Any]]
    dry_run_result: Optional[Dict[str, Any]]

def _parse_update_args(argv: List[str]) -> argparse.Namespace:
    """Build and parse the update CLI arguments."""
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-parse-update-args
    p = argparse.ArgumentParser(
        prog="update",
        description="Update Constructor Studio installation (refresh .core, regenerate .gen)",
    )
    p.add_argument("--project-root", default=None, help="Project root directory")
    p.add_argument(
        "--from-dir",
        default=None,
        help="Constructor Studio directory relative to project root when migrating",
    )
    p.add_argument("--dry-run", action="store_true", help="Show what would be done")
    p.add_argument("--no-interactive", action="store_true",
                   help="Disable interactive prompts (auto-skip customized markers)")
    p.add_argument("-y", "--yes", action="store_true",
                   help="Auto-approve all prompts (no interaction)")
    p.add_argument(
        "--with-kits",
        choices=("yes", "true", "no", "false"),
        default="no",
        metavar="{yes,true,no,false}",
        help="Update project kit files too. Defaults to no; bare --with-kits is invalid.",
    )
    _add_legacy_migration_args(p)
    return p.parse_args(argv)
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-parse-update-args


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-resolve-project
def _no_project_root_result() -> Dict[str, Any]:
    return {"status": "ERROR", "message": "No project root found. Run 'cfs init' first."}


def _render_no_project_root(_data: Dict[str, Any]) -> tuple[None, None, None]:
    return (
        ui.error("No project root found."),
        ui.hint("Initialize Constructor Studio first:  cfs init"),
        ui.blank(),
    )


def _not_initialized_result(project_root: Path) -> Dict[str, Any]:
    return {
        "status": "ERROR",
        "message": "Constructor Studio not initialized in this project. Run 'cfs init' first.",
        "project_root": project_root.as_posix(),
    }


def _render_not_initialized(project_root: Path) -> tuple[None, None, None, None]:
    return (
        ui.error("Constructor Studio is not initialized in this project."),
        ui.detail("Project root", project_root.as_posix()),
        ui.hint("Initialize first:  cfs init"),
        ui.blank(),
    )


def _missing_studio_dir_result(project_root: Path, studio_dir: Path) -> Dict[str, Any]:
    return {
        "status": "ERROR",
        "message": f"Constructor Studio directory not found: {studio_dir}",
        "project_root": project_root.as_posix(),
    }


def _render_missing_studio_dir(studio_dir: Path) -> tuple[None, None, None]:
    return (
        ui.error(f"Constructor Studio directory not found: {studio_dir}"),
        ui.hint("Reinitialize:  cfs init --force"),
        ui.blank(),
    )


def _missing_cache_result() -> Dict[str, Any]:
    return {
        "status": "ERROR",
        "message": f"Cache not found at {CACHE_DIR}. Run 'cfs update' (proxy downloads first).",
    }


def _render_missing_cache(_data: Dict[str, Any]) -> tuple[None, None, None, None]:
    return (
        ui.error("Constructor Studio cache not found."),
        ui.detail("Expected at", str(CACHE_DIR)),
        ui.hint("The proxy layer downloads the cache before forwarding to this command."),
        ui.hint("If running directly, ensure cache exists at the path above."),
    )
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-resolve-project


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-resolve-project
@dataclass
class _UpdateProjectResolution:
    rc: int
    result: Optional[Dict[str, Any]] = None
    project_root: Optional[Path] = None
    studio_dir: Optional[Path] = None
    install_rel: Optional[str] = None
    legacy_migration_declined: bool = False


@dataclass
class _PostCoreUpdateContext:
    project_root: Path
    studio_dir: Path
    install_rel: str
    config_dir: Path
    core_toml_path: Path
    kit_tracking: str


@dataclass
class _UpdateRunContext:
    project_root: Path
    studio_dir: Path
    install_rel: str
    core_dir: Path
    installed_whatsnew_path: Path
    config_dir: Path
    core_toml_path: Path
    kit_tracking: str
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-resolve-project


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-resolve-project
def _failed_update_resolution(
    result: Optional[Dict[str, Any]] = None,
) -> tuple[int, Optional[Dict[str, Any]], Optional[Path], Optional[Path], Optional[str], bool]:
    resolution = _UpdateProjectResolution(rc=1, result=result)
    return (
        resolution.rc,
        resolution.result,
        resolution.project_root,
        resolution.studio_dir,
        resolution.install_rel,
        resolution.legacy_migration_declined,
    )


def _successful_update_resolution(
    *,
    project_root: Path,
    studio_dir: Path,
    install_rel: str,
    legacy_migration_declined: bool,
) -> tuple[int, Optional[Dict[str, Any]], Optional[Path], Optional[Path], Optional[str], bool]:
    resolution = _UpdateProjectResolution(
        rc=0,
        project_root=project_root,
        studio_dir=studio_dir,
        install_rel=install_rel,
        legacy_migration_declined=legacy_migration_declined,
    )
    return (
        resolution.rc,
        resolution.result,
        resolution.project_root,
        resolution.studio_dir,
        resolution.install_rel,
        resolution.legacy_migration_declined,
    )


def _resolve_existing_project_root(args: argparse.Namespace) -> Optional[Path]:
    from ..utils.files import find_project_root
    from .migrate_from_cypilot import resolve_cypilot_project_root

    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-resolve-existing-project-root
    cwd = Path.cwd().resolve()
    project_root = Path(args.project_root).resolve() if args.project_root else find_project_root(cwd)
    return project_root or resolve_cypilot_project_root(args.project_root)
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-resolve-existing-project-root


def _missing_install_update_result(
    args: argparse.Namespace,
    project_root: Path,
    legacy_rel: Optional[str],
) -> tuple[int, Optional[Dict[str, Any]], Optional[Path], Optional[Path], Optional[str], bool]:
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-handle-missing-install
    if legacy_rel:
        return _handle_missing_install_update(args, project_root, legacy_rel)
    ui.result(
        _not_initialized_result(project_root),
        human_fn=lambda _data: _render_not_initialized(project_root),
    )
    return _failed_update_resolution()
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-handle-missing-install


def _resolve_update_project(
    args: argparse.Namespace,
) -> tuple[int, Optional[Dict[str, Any]], Optional[Path], Optional[Path], Optional[str], bool]:
    """Resolve update context or return an early result."""
    from ..utils.files import _read_studio_var
    from .migrate_from_cypilot import detect_legacy_cypilot_install

    project_root = _resolve_existing_project_root(args)
    if project_root is None:
        ui.result(_no_project_root_result(), human_fn=_render_no_project_root)
        return _failed_update_resolution()

    install_rel = _read_studio_var(project_root)
    if not install_rel:
        return _missing_install_update_result(
            args,
            project_root,
            args.from_dir or detect_legacy_cypilot_install(project_root),
        )

    legacy_result = _handle_existing_install_legacy_migration(args, project_root, install_rel)
    if legacy_result is not None:
        return legacy_result

    legacy_rel = args.from_dir or detect_legacy_cypilot_install(project_root)
    legacy_migration_declined = bool(legacy_rel)
    studio_dir = (project_root / install_rel).resolve()
    if not studio_dir.is_dir():
        ui.result(
            _missing_studio_dir_result(project_root, studio_dir),
            human_fn=lambda _data: _render_missing_studio_dir(studio_dir),
        )
        return _failed_update_resolution()
    if not CACHE_DIR.is_dir():
        ui.result(_missing_cache_result(), human_fn=_render_missing_cache)
        ui.blank()
        return _failed_update_resolution()
    return _successful_update_resolution(
        project_root=project_root,
        studio_dir=studio_dir,
        install_rel=install_rel,
        legacy_migration_declined=legacy_migration_declined,
    )


def _build_update_run_context(
    *,
    project_root: Path,
    studio_dir: Path,
    install_rel: str,
) -> _UpdateRunContext:
    config_dir = studio_dir / "config"
    core_toml_path = config_dir / "core.toml"
    return _UpdateRunContext(
        project_root=project_root,
        studio_dir=studio_dir,
        install_rel=install_rel,
        core_dir=studio_dir / CORE_SUBDIR,
        installed_whatsnew_path=studio_dir / "whatsnew.toml",
        config_dir=config_dir,
        core_toml_path=core_toml_path,
        kit_tracking=_read_kit_tracking(core_toml_path, default="tracked"),
    )
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-resolve-project


def _handle_missing_install_update(
    args: argparse.Namespace,
    project_root: Path,
    legacy_rel: str,
) -> tuple[int, Optional[Dict[str, Any]], Optional[Path], Optional[Path], Optional[str], bool]:
    from .migrate_from_cypilot import (
        ensure_supported_legacy_version,
        migration_declined_result,
        should_migrate_from_cypilot,
        _human_migrate_ok,
    )

    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-handle-missing-install
    migrate = should_migrate_from_cypilot(
        args.migrate_from_cypilot,
        interactive=not args.no_interactive and not args.yes,
        project_root=project_root,
        legacy_rel=legacy_rel,
        decline_hint="Press N to abort update.",
    )
    if not migrate:
        result = migration_declined_result(project_root, legacy_rel, dry_run=args.dry_run)
        ui.result(result)
        return 1, result, None, None, None, False

    supported, preflight = ensure_supported_legacy_version(
        project_root=project_root,
        legacy_rel=legacy_rel,
        update_choice=args.update_legacy_studio,
        interactive=not args.no_interactive and not args.yes,
        dry_run=args.dry_run,
    )
    if not supported:
        ui.result(preflight)
        return 1, preflight, None, None, None, False

    rc = _run_default_legacy_migration(
        args=args,
        project_root=project_root,
        from_dir=legacy_rel,
        to_dir=DEFAULT_INSTALL_DIR,
        preflight=preflight,
        human_fn=_human_migrate_ok,
    )
    result = None
    return rc, result, None, None, None, False
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-handle-missing-install


def _handle_existing_install_legacy_migration(
    args: argparse.Namespace,
    project_root: Path,
    install_rel: str,
) -> Optional[tuple[int, Optional[Dict[str, Any]], Optional[Path], Optional[Path], Optional[str], bool]]:
    from .migrate_from_cypilot import (
        detect_legacy_cypilot_install,
        ensure_supported_legacy_version,
        should_migrate_from_cypilot,
        _human_migrate_ok,
    )

    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-handle-existing-install-legacy-migration
    legacy_rel = args.from_dir or detect_legacy_cypilot_install(project_root)
    if not legacy_rel:
        return None
    migrate = should_migrate_from_cypilot(
        args.migrate_from_cypilot,
        interactive=not args.no_interactive and not args.yes,
        project_root=project_root,
        legacy_rel=legacy_rel,
        heading="Cyber Pilot (cypilot) detected alongside Constructor Studio.",
        prompt="Migrate it into the current Constructor Studio install now? [y/N] ",
        decline_hint="Press N to continue regular Constructor Studio update.",
    )
    if not migrate:
        return None

    supported, preflight = ensure_supported_legacy_version(
        project_root=project_root,
        legacy_rel=legacy_rel,
        update_choice=args.update_legacy_studio,
        interactive=not args.no_interactive and not args.yes,
        dry_run=args.dry_run,
    )
    if not supported:
        ui.result(preflight)
        return 1, preflight, None, None, None, False

    rc = _run_default_legacy_migration(
        args=args,
        project_root=project_root,
        from_dir=legacy_rel,
        to_dir=install_rel,
        preflight=preflight,
        human_fn=_human_migrate_ok,
        force=True,
    )
    result = None
    return rc, result, None, None, None, False
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-handle-existing-install-legacy-migration


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-update-helpers
def _show_update_whatsnew(
    *,
    args: argparse.Namespace,
    core_dir: Path,
    installed_whatsnew_path: Path,
) -> bool:
    """Show core whatsnew and report whether update should continue."""
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-show-update-whatsnew
    if args.dry_run or not _cache_allows_root_metadata(CACHE_DIR):
        return True
    cache_whatsnew = read_whatsnew(CACHE_DIR / "whatsnew.toml")
    core_whatsnew = read_whatsnew(installed_whatsnew_path) or read_whatsnew(core_dir / "whatsnew.toml")
    if not cache_whatsnew:
        return True
    ack = show_core_whatsnew(
        cache_whatsnew,
        core_whatsnew,
        interactive=not args.no_interactive and not args.yes and sys.stdin.isatty(),
    )
    if ack:
        return True
    ui.result({"status": "ABORTED", "message": "Update aborted by user."})
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-show-update-whatsnew
    return False
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-update-helpers


def _copy_core_from_cache(
    *,
    args: argparse.Namespace,
    actions: Dict[str, Any],
    studio_dir: Path,
    core_dir: Path,
) -> Dict[str, str]:
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-copy-core-from-cache
    ui.step("Updating core files and install metadata from cache...")
    if not args.dry_run:
        studio_dir.mkdir(parents=True, exist_ok=True)
        copy_results = _copy_from_cache(CACHE_DIR, studio_dir, force=True)
        core_dir.mkdir(parents=True, exist_ok=True)
        (core_dir / "README.md").write_text(_core_readme(), encoding="utf-8")
        legacy_core_whatsnew = core_dir / "whatsnew.toml"
        if legacy_core_whatsnew.exists():
            legacy_core_whatsnew.unlink()
        _cache_provenance = CACHE_DIR / ".provenance.json"
        if _cache_provenance.is_file():
            shutil.copy2(_cache_provenance, core_dir / ".provenance.json")
            actions["install_provenance"] = "updated"
    else:
        copy_results = _dry_run_copy_results(CACHE_DIR, studio_dir, force=True)
        actions["install_provenance"] = "dry_run"
    actions["core_update"] = copy_results
    for name, action in copy_results.items():
        ui.file_action(name if name in COPY_ROOT_FILES else f".core/{name}/", action)
    return copy_results
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-copy-core-from-cache


# @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-record-layout-migration
def _record_layout_migration(actions: Dict[str, Any], studio_dir: Path) -> None:
    from .kit import _detect_and_migrate_layout

    layout_migrated = _detect_and_migrate_layout(studio_dir, dry_run=False)
    if not layout_migrated:
        return
    ui.step("Migrating directory layout...")
    for slug, status in layout_migrated.items():
        ui.substep(f"{slug}: {status}")
    actions["layout_migration"] = layout_migrated
# @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-record-layout-migration


# @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-persist-post-update-metadata
def _persist_post_update_metadata(
    *,
    context: _PostCoreUpdateContext,
    actions: Dict[str, Any],
) -> None:
    runtime_tracking = _read_install_tracking(
        context.core_toml_path,
        "runtime_tracking",
        default="ignored",
    )
    agent_tracking = _read_install_tracking(
        context.core_toml_path,
        "agent_tracking",
        default="ignored",
    )
    actions["core_toml_metadata"] = _persist_install_metadata(
        context.core_toml_path,
        context.kit_tracking,
        runtime_tracking=runtime_tracking,
        agent_tracking=agent_tracking,
        dry_run=False,
    )
# @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-persist-post-update-metadata


# @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-record-core-toml-migrations
def _record_core_toml_migrations(actions: Dict[str, Any], config_dir: Path) -> None:
    # @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-remove-system-section-algo
    removed_system = _remove_system_from_core_toml(config_dir)
    if removed_system:
        ui.step("Removed [system] section from core.toml (ADR-0014: system identity lives in artifacts.toml)")
        actions["core_toml_system_removed"] = True
    # @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-remove-system-section-algo
    deduped = _deduplicate_legacy_kits(config_dir)
    if deduped:
        ui.step("Deduplicating legacy kit slugs...")
        for legacy, canonical in deduped.items():
            ui.substep(f"{legacy} -> {canonical}")
        actions["kit_dedup"] = deduped
    # @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-migrate-kit-sources-algo
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-migrate-kit-sources
    migrated_kits = _migrate_kit_sources(config_dir)
    if not migrated_kits:
        return
    ui.step("Migrating kit sources to GitHub...")
    for slug, src in migrated_kits.items():
        ui.substep(f"{slug}: source -> {src}")
    actions["kit_source_migration"] = migrated_kits
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-migrate-kit-sources
    # @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-migrate-kit-sources-algo
# @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-record-core-toml-migrations


# @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-run-post-core-update-steps
def _run_post_core_update_steps(
    *,
    args: argparse.Namespace,
    actions: Dict[str, Any],
    errors: List[Dict[str, str]],
    context: _PostCoreUpdateContext,
) -> bool:
    """Run layout, metadata, and migration phases after core copy."""
    if args.dry_run:
        # @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-migrate-config-algo
        # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-migrate-config
        actions["core_toml_metadata"] = "dry_run"
        # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-migrate-config
        # @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-migrate-config-algo
        # @cpt-begin:cpt-studio-flow-core-infra-project-update:p1:inst-update-gitignore
        actions["gitignore"] = "dry_run"
        # @cpt-end:cpt-studio-flow-core-infra-project-update:p1:inst-update-gitignore
        return True
    # @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-detect-layout-algo
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-detect-layout
    _record_layout_migration(actions, context.studio_dir)
    _cleanup_legacy_blueprint_dirs(context.config_dir)
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-detect-layout
    # @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-detect-layout-algo
    # @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-migrate-config-algo
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-migrate-config
    _persist_post_update_metadata(context=context, actions=actions)
    # @cpt-begin:cpt-studio-flow-core-infra-project-update:p1:inst-update-gitignore
    try:
        actions["gitignore"] = _write_gitignore_block(
            context.project_root,
            context.install_rel,
            context.core_toml_path,
            context.kit_tracking,
            dry_run=False,
        )
    except (OSError, ValueError) as exc:
        errors.append({"path": ".gitignore", "error": str(exc)})
        return False
    # @cpt-end:cpt-studio-flow-core-infra-project-update:p1:inst-update-gitignore
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-migrate-config
    # @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-migrate-config-algo
    _record_core_toml_migrations(actions, context.config_dir)
    return True
# @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-run-post-core-update-steps


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-render-update-result
def _gitignore_failure_result(
    *,
    args: argparse.Namespace,
    actions: Dict[str, Any],
    errors: List[Dict[str, str]],
    project_root: Path,
    studio_dir: Path,
) -> Dict[str, Any]:
    return {
        "status": "ERROR",
        "project_root": project_root.as_posix(),
        "studio_dir": studio_dir.as_posix(),
        "dry_run": bool(args.dry_run),
        "actions": actions,
        "errors": errors,
    }


def _dry_run_github_kit_result(kit_slug: str) -> Dict[str, Any]:
    return {
        "kit": kit_slug,
        "version": {"status": "dry_run"},
        "gen": {"files_written": 0},
        "gen_rejected": [],
    }
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-render-update-result


# @cpt-begin:cpt-studio-algo-version-config-github-authority:p1:inst-build-offline-github-authority
def _cached_github_authority_metadata(  # pylint: disable=too-many-locals
    *,
    previous_provenance: Dict[str, Any],
    source_str: str,
    owner: str,
    repo: str,
    version: str,
    kit_data: Dict[str, Any],
) -> Dict[str, Any]:
    resolved_ref = str(
        previous_provenance.get("resolved_ref")
        or kit_data.get("version")
        or ""
    )
    return {
        "source_type": "github",
        "requested_ref": previous_provenance.get("requested_ref", version or "latest"),
        "resolved_ref": resolved_ref,
        "installed_version": resolved_ref,
        "commit_sha": previous_provenance.get("commit_sha", ""),
        "canonical_source": previous_provenance.get(
            "canonical_source",
            f"github:{owner}/{repo}" if owner and repo else source_str,
        ),
        "effective_source": previous_provenance.get("effective_source", source_str),
        "resolver_mode": "offline_last_known",
        "resolution_basis": "last_known_core_toml",
        "verified": "stale",
        "freshness": "last_known",
    }
# @cpt-end:cpt-studio-algo-version-config-github-authority:p1:inst-build-offline-github-authority


def _resolve_github_update_source(
    *,
    errors: List[Dict[str, str]],
    kit_slug: str,
    kit_data: Dict[str, Any],
    source_str: str,
) -> _KitSourceResolution:
    from .kit import _download_kit_from_github_with_authority, _parse_github_source

    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-resolve-github-update-source
    owner = repo = version = ""
    try:
        owner, repo, version = _parse_github_source(source_str.removeprefix("github:"))
        kit_src, _resolved_version, authority_metadata = _download_kit_from_github_with_authority(
            owner,
            repo,
            version,
            previous_entry=kit_data,
        )
        return _KitSourceResolution(kit_src, kit_src.parent, authority_metadata, None)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        cache_kit = CACHE_DIR / "kits" / kit_slug
        if not cache_kit.is_dir():
            errors.append({"path": kit_slug, "error": f"Download failed: {exc}"})
            logger.warning("%s: download failed without cached kit fallback", kit_slug, exc_info=exc)
            ui.warn(f"{kit_slug}: download failed: {exc}")
            return _KitSourceResolution(None, None, None, None)
        authority_metadata = None
        previous_provenance = kit_data.get("source_provenance", {})
        if isinstance(previous_provenance, dict):
            authority_metadata = _cached_github_authority_metadata(
                previous_provenance=previous_provenance,
                source_str=source_str,
                owner=owner,
                repo=repo,
                version=version,
                kit_data=kit_data,
            )
        logger.warning("%s: download failed, using cached kit", kit_slug, exc_info=exc)
        ui.warn(f"{kit_slug}: download failed, using cached kit: {exc}")
        return _KitSourceResolution(cache_kit, None, authority_metadata, None)
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-resolve-github-update-source


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-resolve-update-kit-source
def _resolve_update_kit_source(
    *,
    args: argparse.Namespace,
    errors: List[Dict[str, str]],
    kit_slug: str,
    kit_data: Dict[str, Any],
) -> _KitSourceResolution:
    source_str = kit_data.get("source", "")
    if source_str.startswith("github:"):
        if args.dry_run:
            return _KitSourceResolution(None, None, None, _dry_run_github_kit_result(kit_slug))
        return _resolve_github_update_source(
            errors=errors,
            kit_slug=kit_slug,
            kit_data=kit_data,
            source_str=source_str,
        )
    if not source_str:
        cache_kit = CACHE_DIR / "kits" / kit_slug
        if cache_kit.is_dir():
            return _KitSourceResolution(cache_kit, None, None, None)
    return _KitSourceResolution(None, None, None, None)
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-resolve-update-kit-source


# @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-record-manifest-migration-result
def _record_manifest_migration_result(
    *,
    args: argparse.Namespace,
    errors: List[Dict[str, str]],
    kit_slug: str,
    kit_src: Optional[Path],
    studio_dir: Path,
    config_dir: Path,
    interactive: bool,
    kit_result: Dict[str, Any],
) -> None:
    if args.dry_run or kit_src is None:
        return
    try:
        # @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-manifest-legacy-migration-algo
        migration = _maybe_migrate_legacy_to_manifest(
            kit_slug, kit_src, studio_dir, config_dir, interactive,
        )
        if migration is None:
            return
        kit_result["manifest_migration"] = migration
        # @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-manifest-legacy-migration-algo
        migration_status = migration.get("status", "")
        if migration_status == "PASS":
            migrated_count = migration.get("migrated_count", 0)
            new_count = migration.get("new_count", 0)
            ui.substep(
                f"{kit_slug}: manifest migration - "
                f"{migrated_count} existing + {new_count} new resource(s)"
            )
        elif migration_status == "FAIL":
            ui.warn(
                f"{kit_slug}: manifest migration failed: "
                f"{migration.get('errors', [])}"
            )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        mig_error = (
            "manifest migration raised unexpected exception "
            f"(kit update was not aborted): {exc}"
        )
        errors.append({"path": kit_slug, "error": mig_error})
        logger.exception("%s: manifest migration raised unexpected exception", kit_slug)
# @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-record-manifest-migration-result


def _report_updated_kit_progress(kit_slug: str, kit_result: Dict[str, Any]) -> None:  # pylint: disable=too-many-locals
    ver = kit_result.get("version", {})
    ver_status = ver.get("status", "") if isinstance(ver, dict) else ver
    gen = kit_result.get("gen", {})
    files_written = gen.get("files_written", 0) if isinstance(gen, dict) else 0

    if ver_status == "created":
        ui.substep(f"{kit_slug}: first install, {files_written} files written")
        return
    if ver_status == "updated":
        ui.substep(f"{kit_slug}: updated, {files_written} file(s) accepted")
        for fp in gen.get("accepted_files", []):
            ui.substep(f"      ~ {fp}")
        for fp in kit_result.get("gen_rejected", []):
            ui.substep(f"      x {fp} (declined)")
        return
    if ver_status == "partial":
        rejected = kit_result.get("gen_rejected", [])
        ui.substep(f"{kit_slug}: partial, {files_written} accepted, {len(rejected)} declined")
        for fp in gen.get("accepted_files", []):
            ui.substep(f"      ~ {fp}")
        for fp in rejected:
            ui.substep(f"      x {fp} (declined)")
        return
    if ver_status == "aborted":
        ui.substep(f"{kit_slug}: skipped by user")
        return
    if ver_status == "current":
        ui.substep(f"{kit_slug}: up to date")


def _aborted_kit_update_result(kit_slug: str) -> Dict[str, Any]:
    return {
        "kit": kit_slug,
        "version": {"status": "aborted"},
        "gen": {"files_written": 0},
        "gen_rejected": [],
    }


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-confirm-kit-update
def _confirm_kit_update(
    *,
    args: argparse.Namespace,
    config_dir: Path,
    interactive: bool,
    kit_slug: str,
    kit_src: Path,
    read_kit_version_from_core,
) -> bool:
    """Return whether the current kit update should proceed."""
    if args.dry_run:
        return True
    installed_version = read_kit_version_from_core(config_dir, kit_slug)
    return show_kit_whatsnew(
        kit_src,
        installed_version,
        kit_slug,
        interactive=interactive and not args.yes,
    )
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-confirm-kit-update


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-perform-registered-kit-update
def _perform_registered_kit_update(  # pylint: disable=too-many-arguments,too-many-locals
    *,
    args: argparse.Namespace,
    authority_metadata: Optional[Dict[str, Any]],
    config_dir: Path,
    errors: List[Dict[str, str]],
    interactive: bool,
    kit_data: Dict[str, Any],
    kit_slug: str,
    kit_src: Path,
    studio_dir: Path,
    update_context_cls,
    update_kit,
) -> Dict[str, Any]:
    """Run one registered kit update and attach manifest-migration details."""
    update_context = update_context_cls(
        dry_run=args.dry_run,
        interactive=interactive,
        auto_approve=args.yes,
        source=str(kit_data.get("source", "") or ""),
        authority_metadata=authority_metadata,
    )
    kit_result = update_kit(
        kit_slug,
        kit_src,
        studio_dir,
        update_context=update_context,
    )
    _record_manifest_migration_result(
        args=args,
        errors=errors,
        kit_slug=kit_slug,
        kit_src=kit_src,
        studio_dir=studio_dir,
        config_dir=config_dir,
        interactive=interactive,
        kit_result=kit_result,
    )
    return kit_result
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-perform-registered-kit-update


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-update-single-registered-kit
def _update_single_registered_kit(  # pylint: disable=too-many-arguments
    *,
    args: argparse.Namespace,
    errors: List[Dict[str, str]],
    kit_slug: str,
    kit_data: Dict[str, Any],
    studio_dir: Path,
    config_dir: Path,
    interactive: bool,
    update_context_cls,
    update_kit,
    _read_kit_version_from_core,
) -> Optional[Dict[str, Any]]:
    resolution = _resolve_update_kit_source(
        args=args,
        errors=errors,
        kit_slug=kit_slug,
        kit_data=kit_data,
    )
    if resolution.dry_run_result is not None:
        return resolution.dry_run_result
    if resolution.kit_src is None:
        return None
    if not _confirm_kit_update(
        args=args,
        config_dir=config_dir,
        interactive=interactive,
        kit_slug=kit_slug,
        kit_src=resolution.kit_src,
        read_kit_version_from_core=_read_kit_version_from_core,
    ):
        return _aborted_kit_update_result(kit_slug)
    try:
        return _perform_registered_kit_update(
            args=args,
            authority_metadata=resolution.authority_metadata,
            config_dir=config_dir,
            errors=errors,
            interactive=interactive,
            kit_data=kit_data,
            kit_slug=kit_slug,
            kit_src=resolution.kit_src,
            studio_dir=studio_dir,
            update_context_cls=update_context_cls,
            update_kit=update_kit,
        )
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        errors.append({"path": kit_slug, "error": str(exc)})
        return {
            "kit": kit_slug,
            "status": "ERROR",
            "error": str(exc),
        }
    finally:
        if resolution.tmp_to_clean:
            shutil.rmtree(resolution.tmp_to_clean, ignore_errors=True)
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-update-single-registered-kit


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-update-registered-kits
def _update_registered_kits(  # pylint: disable=too-many-locals
    *,
    args: argparse.Namespace,
    actions: Dict[str, Any],
    errors: List[Dict[str, str]],
    studio_dir: Path,
    config_dir: Path,
    core_toml_path: Path,
    kit_tracking: str,
) -> Dict[str, Any]:
    from .kit import (
        _UpdateContext,
        _read_kits_from_core_toml,
        _read_kit_version_from_core,
        update_kit,
    )

    kit_results: Dict[str, Any] = {}
    interactive = not args.no_interactive and sys.stdin.isatty()
    with_kits = str(args.with_kits).lower() in ("yes", "true")
    if not with_kits:
        ui.step("Skipping kit updates (pass --with-kits yes to update project kit files).")
        actions["kits"] = _skipped_kit_updates_action(core_toml_path, kit_tracking)
        return {}

    ui.step("Updating kits...")
    installed_kits = _read_kits_from_core_toml(config_dir)
    for kit_slug, kit_data in installed_kits.items():
        _record_single_kit_update(
            args=args,
            errors=errors,
            kit_results=kit_results,
            kit_slug=kit_slug,
            kit_result=_update_single_registered_kit(
                args=args,
                errors=errors,
                kit_slug=kit_slug,
                kit_data=kit_data,
                studio_dir=studio_dir,
                config_dir=config_dir,
                interactive=interactive,
                update_context_cls=_UpdateContext,
                update_kit=update_kit,
                _read_kit_version_from_core=_read_kit_version_from_core,
            ),
        )
    actions["kits"] = kit_results
    return kit_results
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-update-registered-kits


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-update-registered-kits
def _skipped_kit_updates_action(core_toml_path: Path, kit_tracking: str) -> Dict[str, Any]:
    """Build the action payload for a run that skips kit updates."""
    return {
        "status": "skipped",
        "reason": "--with-kits not enabled",
        "kit_tracking": {
            "default": kit_tracking,
            "kits": _read_kit_tracking_state(core_toml_path, default=kit_tracking)[1],
        },
    }
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-update-registered-kits


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-record-single-kit-update
def _record_single_kit_update(  # pylint: disable=too-many-locals
    *,
    args: argparse.Namespace,
    errors: List[Dict[str, str]],
    kit_results: Dict[str, Any],
    kit_slug: str,
    kit_result: Optional[Dict[str, Any]],
) -> None:
    """Store and report one completed kit update result."""
    if kit_result is None:
        return
    kit_results[kit_slug] = kit_result
    if args.dry_run:
        return
    if kit_result.get("gen_errors"):
        errors.extend({"path": kit_slug, "error": error} for error in kit_result["gen_errors"])
    _report_updated_kit_progress(kit_slug, kit_result)
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-record-single-kit-update


# @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-scaffold-algo
# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-ensure-scaffold
def _ensure_update_scaffold(
    *,
    args: argparse.Namespace,
    actions: Dict[str, Any],
    config_dir: Path,
    project_root: Path,
    install_rel: str,
) -> None:
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-ensure-update-scaffold
    ui.step("Ensuring config/ scaffold...")
    if args.dry_run:
        return
    config_dir.mkdir(parents=True, exist_ok=True)
    _ensure_file(config_dir / "README.md", _config_readme_content(), actions, "config_readme")
    _ensure_file(
        config_dir / "AGENTS.md",
        "# Custom Agent Navigation Rules\n\n"
        "Add your project-specific WHEN rules here.\n"
        "These rules are loaded alongside the generated rules in `{cf-studio-path}/.gen/AGENTS.md`.\n",
        actions, "config_agents",
    )
    _ensure_file(
        config_dir / "SKILL.md",
        "# Custom Skill Extensions\n\n"
        "Add your project-specific skill instructions here.\n"
        "Agent-facing skills and workflows are generated into agent integration files.\n",
        actions, "config_skill",
    )
    actions["root_agents"] = _inject_root_agents(project_root, install_rel)
    actions["root_claude"] = _inject_root_claude(project_root, install_rel)
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-ensure-update-scaffold
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-ensure-scaffold
# @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-scaffold-algo


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-self-check
# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-run-update-validation
def _run_update_validation(
    *,
    args: argparse.Namespace,
    errors: List[Dict[str, str]],
    warnings: List[str],
    project_root: Path,
    studio_dir: Path,
) -> Optional[Dict[str, Any]]:
    if args.dry_run:
        return None
    try:
        from .validate_kits import run_validate_kits

        vk_rc, vk_report = run_validate_kits(
            project_root=project_root,
            adapter_dir=studio_dir,
        )
        vk_status = str(vk_report.get("status", ""))
        if vk_rc or vk_status != "PASS":
            warnings.append(f"validate-kits: {vk_status}")
            ui.warn(f"Validate kits: {vk_status}")
            _show_validate_kits_failures(vk_report)
        else:
            ui.step("Validate kits: PASS")
        return vk_report
    except (OSError, ValueError, KeyError) as exc:
        errors.append({"path": "validate-kits", "error": f"validate-kits failed to run: {exc}"})
        return None
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-run-update-validation
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-self-check


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-return-report
def _ensure_core_toml_lock_sidecar(core_toml_path: Path) -> None:
    """Create the advisory lock sidecar expected by update filesystem contracts."""
    if not core_toml_path.is_file():
        return
    lock_path = core_toml_path.with_suffix(core_toml_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)


def _build_update_result(
    *,
    args: argparse.Namespace,
    actions: Dict[str, Any],
    errors: List[Dict[str, str]],
    warnings: List[str],
    project_root: Path,
    studio_dir: Path,
    validate_kits_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    status = "ERROR" if errors else "WARN" if warnings else "PASS"
    update_result: Dict[str, Any] = {
        "status": status,
        "project_root": project_root.as_posix(),
        "studio_dir": studio_dir.as_posix(),
        "dry_run": bool(args.dry_run),
        "actions": actions,
    }
    if errors:
        update_result["errors"] = errors
    if warnings:
        update_result["warnings"] = warnings
    if validate_kits_result is not None:
        update_result["validate_kits"] = validate_kits_result
    return update_result


def _initialize_update_outcome(
    legacy_migration_declined: bool,
) -> tuple[Dict[str, Any], List[Dict[str, str]], List[str]]:
    """Create mutable result collections for one update run."""
    actions: Dict[str, Any] = {}
    if legacy_migration_declined:
        actions["legacy_studio"] = "detected"
        actions["migration"] = "declined"
        actions["migration_decline_action"] = "regular_update"
    return actions, [], []
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-return-report


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-regenerate-agents
def _update_agent_regeneration_action(
    *,
    args: argparse.Namespace,
    actions: Dict[str, Any],
    copy_results: Dict[str, Any],
    context: _UpdateRunContext,
    kit_results: Dict[str, Any],
) -> None:
    """Record agent regeneration metadata when the update changed live files."""
    if args.dry_run:
        return
    agents_regen = _maybe_regenerate_agents(
        copy_results, kit_results, context.project_root, context.studio_dir,
    )
    if agents_regen:
        actions["agents_regenerated"] = agents_regen
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-regenerate-agents


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-render-update-result
def _render_update_result(
    *,
    args: argparse.Namespace,
    actions: Dict[str, Any],
    errors: List[Dict[str, str]],
    warnings: List[str],
    context: _UpdateRunContext,
    validate_kits_result: Optional[Dict[str, Any]],
) -> int:
    """Emit the final update report and return the command exit code."""
    update_result = _build_update_result(
        args=args,
        actions=actions,
        errors=errors,
        warnings=warnings,
        project_root=context.project_root,
        studio_dir=context.studio_dir,
        validate_kits_result=validate_kits_result,
    )
    # @cpt-begin:cpt-studio-state-core-infra-project-install:p1:inst-update-complete
    ui.result(update_result, human_fn=_human_update_ok)
    return 1 if errors else 0
    # @cpt-end:cpt-studio-state-core-infra-project-install:p1:inst-update-complete
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-render-update-result


def cmd_update(argv: List[str]) -> int:  # pylint: disable=too-many-locals
    """Update an existing Constructor Studio installation.

    Refreshes .core/ and install-root metadata from cache, updates kit files,
    regenerates .gen/ aggregates.
    Never overwrites user config files.
    """
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-user-update
    args = _parse_update_args(argv)

    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-resolve-project
    rc, _early_result, project_root, studio_dir, install_rel, legacy_migration_declined = _resolve_update_project(args)
    if rc or project_root is None or studio_dir is None or install_rel is None:
        return rc
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-resolve-project
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-user-update

    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-whatsnew
    actions, errors, warnings = _initialize_update_outcome(legacy_migration_declined)
    context = _build_update_run_context(
        project_root=project_root,
        studio_dir=studio_dir,
        install_rel=install_rel,
    )
    if not _show_update_whatsnew(
        args=args,
        core_dir=context.core_dir,
        installed_whatsnew_path=context.installed_whatsnew_path,
    ):
        return 0
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-whatsnew

    # @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-replace-core-algo
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-replace-core
    # ── Step 1: Replace .core/ and install metadata from cache (always force) ──
    copy_results = _copy_core_from_cache(
        args=args,
        actions=actions,
        studio_dir=context.studio_dir,
        core_dir=context.core_dir,
    )

    post_core_context = _PostCoreUpdateContext(
        project_root=context.project_root,
        studio_dir=context.studio_dir,
        install_rel=context.install_rel,
        config_dir=context.config_dir,
        core_toml_path=context.core_toml_path,
        kit_tracking=context.kit_tracking,
    )
    if not _run_post_core_update_steps(
        args=args,
        actions=actions,
        errors=errors,
        context=post_core_context,
    ):
        ui.result(
            _gitignore_failure_result(
                args=args,
                actions=actions,
                errors=errors,
                project_root=context.project_root,
                studio_dir=context.studio_dir,
            ),
            human_fn=_human_update_ok,
        )
        return 1
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-replace-core
    # @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-replace-core-algo

    from .kit import regenerate_gen_aggregates

    kit_results = _update_registered_kits(
        args=args,
        actions=actions,
        errors=errors,
        studio_dir=context.studio_dir,
        config_dir=context.config_dir,
        core_toml_path=context.core_toml_path,
        kit_tracking=context.kit_tracking,
    )

    # ── Step 3: Regenerate .gen/ aggregates ────────────────────────────
    if not args.dry_run:
        gen_result = regenerate_gen_aggregates(context.studio_dir)
        actions.update(gen_result)
    # (end kit updates)

    # @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-regen-algo
    # Removed — no separate regen step; kit files are updated directly by update_kit.
    # @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-regen-algo

    # ── Step 5: Ensure config/ scaffold (create only if missing) ─────────
    _ensure_update_scaffold(
        args=args,
        actions=actions,
        config_dir=context.config_dir,
        project_root=context.project_root,
        install_rel=context.install_rel,
    )

    # ── Auto-regenerate agent integrations if real changes happened ────
    _update_agent_regeneration_action(
        args=args,
        actions=actions,
        copy_results=copy_results,
        context=context,
        kit_results=kit_results,
    )

    # ── Run validate-kits to verify kit integrity after update ───────────
    validate_kits_result = _run_update_validation(
        args=args,
        errors=errors,
        warnings=warnings,
        project_root=context.project_root,
        studio_dir=context.studio_dir,
    )

    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-return-report
    # ── Report ───────────────────────────────────────────────────────────
    if not args.dry_run:
        _ensure_core_toml_lock_sidecar(context.core_toml_path)
    return _render_update_result(
        args=args,
        actions=actions,
        errors=errors,
        warnings=warnings,
        context=context,
        validate_kits_result=validate_kits_result,
    )
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-return-report

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-update-helpers
def _ensure_file(path: Path, content: str, actions: Dict, key: str) -> None:
    """Create file only if it doesn't exist."""
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-ensure-update-scaffold
    if path.is_file():
        actions[key] = "preserved"
    else:
        path.write_text(content, encoding="utf-8")
        actions[key] = "created"
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-ensure-update-scaffold
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-update-helpers

# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-update-helpers
def _config_readme_content() -> str:
    """README.md content for config/ directory."""
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-ensure-update-scaffold
    return (
        _CONFIG_README_PREAMBLE +
        "- `core.toml` — project settings (kit references, version)\n"
        "- `artifacts.toml` — artifacts registry (systems, artifacts, ignore patterns)\n"
        "- `AGENTS.md` — custom agent navigation rules (add your own WHEN rules here)\n"
        "- `SKILL.md` — custom skill extensions (add your own skill instructions here)\n"
        "\n"
        "## Directories\n"
        "\n"
        "- `kits/{slug}/` — kit files (artifacts/, codebase/, workflows/, scripts/, SKILL.md)\n"
        "- `rules/` — project rules (auto-configured or user-defined)\n"
        "\n"
        "**These files are never overwritten by `cfs update`.**\n"
    )
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-ensure-update-scaffold
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-update-helpers


# @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-manifest-legacy-migration-helper
def _maybe_migrate_legacy_to_manifest(
    kit_slug: str,
    kit_src: Path,
    studio_dir: Path,
    config_dir: Path,
    interactive: bool,
) -> Optional[Dict[str, Any]]:
    """Auto-migrate a legacy kit to manifest-driven bindings if needed.

    Checks two conditions:
    1. Kit source contains ``manifest.toml``
    2. ``core.toml`` does NOT have ``[kits.{slug}.resources]``

    If both are true, triggers ``migrate_legacy_kit_to_manifest()``.
    Returns the migration result dict, or ``None`` if migration was not needed.

    @cpt-algo:cpt-studio-algo-kit-manifest-legacy-migration:p1
    """
    from ..utils.manifest import load_manifest
    from .kit import migrate_legacy_kit_to_manifest, _read_kits_from_core_toml

    # @cpt-begin:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-read-manifest
    try:
        manifest = load_manifest(kit_src)
    except FileNotFoundError:
        logger.info("No manifest.toml found for kit '%s' at %s; skipping manifest migration", kit_slug, kit_src)
        return None
    except (ValueError, OSError) as exc:
        logger.warning(
            "Skipping manifest migration for kit '%s' at %s: %s",
            kit_slug,
            kit_src,
            exc,
        )
        return None

    if manifest is None:
        return None
    # @cpt-end:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-read-manifest

    # @cpt-begin:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-read-root
    kit_data = _read_kits_from_core_toml(config_dir).get(kit_slug, {})
    if kit_data.get("resources"):
        return None  # Already has resource bindings
    # @cpt-end:cpt-studio-algo-kit-manifest-legacy-migration:p1:inst-legacy-read-root

    return migrate_legacy_kit_to_manifest(
        kit_src, studio_dir, kit_slug, interactive=interactive,
    )
# @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-manifest-legacy-migration-helper


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-update-helpers
def _maybe_regenerate_agents(
    copy_results: Dict[str, str],
    kit_results: Dict[str, Any],
    project_root: Path,
    studio_dir: Path,
) -> List[str]:
    """Auto-regenerate agent integration files when a real update happened.

    Triggers when core dirs were updated/created or any kit was created/migrated.
    Only regenerates agents whose skill output files already exist on disk.
    Returns list of agent names that were regenerated.
    """
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-regenerate-agents
    core_changed = any(v in ("updated", "created") for v in copy_results.values())
    kits_changed = any(
        isinstance(kr, dict)
        and isinstance(kr.get("version"), dict)
        and kr["version"].get("status") in ("created", "migrated", "updated")
        for kr in kit_results.values()
    )
    if not core_changed and not kits_changed:
        return []

    from .agents import (
        _ALL_RECOGNIZED_AGENTS,
        _default_agents_config,
        _is_agent_installed,
        _process_single_agent,
    )

    cfg = _default_agents_config()
    regenerated: List[str] = []

    for agent in _ALL_RECOGNIZED_AGENTS:
        if not _is_agent_installed(agent, project_root):
            continue
        result = _process_single_agent(
            agent, project_root, studio_dir, cfg, None, dry_run=False,
        )
        n_changed = _count_agent_output_changes(result)
        if n_changed:
            regenerated.append(agent)

    if regenerated:
        ui.step("Regenerating agent integrations...")
        for agent in regenerated:
            ui.substep(f"{agent}: updated")

    return regenerated
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-regenerate-agents
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-update-helpers


# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-update-helpers
def _count_agent_output_changes(result: Dict[str, Any]) -> int:
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-regenerate-agents
    total = 0
    for section_name in ("workflows", "skills", "subagents"):
        section = result.get(section_name, {})
        total += len(section.get("updated", []))
        total += len(section.get("created", []))
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-regenerate-agents
    return total
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-update-helpers

# ---------------------------------------------------------------------------
# core.toml [system] removal migration (ADR-0014)
# ---------------------------------------------------------------------------


# @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-run-post-core-update-steps
def _cleanup_legacy_blueprint_dirs(config_dir: Path) -> None:
    """Remove leftover blueprints/ directories from config/kits/*/.

    Per ADR-0001, the blueprint system was removed.  Old projects may
    still have config/kits/{slug}/blueprints/ lingering even after
    layout migration (which only skips copying them, never deletes).
    """
    kits_dir = config_dir / "kits"
    if not kits_dir.is_dir():
        return
    for kit_dir in kits_dir.iterdir():
        if not kit_dir.is_dir():
            continue
        bp = kit_dir / "blueprints"
        if bp.is_dir():
            shutil.rmtree(bp, ignore_errors=True)
# @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-run-post-core-update-steps


# @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-remove-system-section-algo
def _remove_system_from_core_toml(config_dir: Path) -> bool:
    """Remove the [system] section from core.toml if present.

    Per ADR-0014 (cpt-studio-adr-remove-system-from-core-toml), system
    identity lives exclusively in artifacts.toml.  This migration step
    cleans up legacy core.toml files that still carry the section.

    Returns True if the section was found and removed.
    """
    core_toml = config_dir / "core.toml"
    if not core_toml.is_file():
        return False

    try:
        from ..utils import toml_utils
        with toml_utils._with_core_toml_lock(core_toml):
            try:
                with open(core_toml, "rb") as f:
                    data = tomllib.load(f)
            except (OSError, ValueError, TypeError) as exc:
                logger.warning("Cannot read %s while removing legacy [system]: %s", core_toml, exc)
                return False

            if "system" not in data:
                return False

            del data["system"]
            toml_utils.dump(data, core_toml, header_comment="Constructor Studio project configuration")
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Cannot write %s while removing legacy [system]: %s", core_toml, exc)
        return False

    return True
# @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-remove-system-section-algo


# ---------------------------------------------------------------------------
# Bundled kit source migration (ADR-0013)
# ---------------------------------------------------------------------------

# Legacy slug → canonical slug mapping
_LEGACY_SLUG_RENAMES: Dict[str, str] = {
    "studio-sdlc": "sdlc",
}


# @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-record-core-toml-migrations
def _merge_duplicate_legacy_kit(
    kits: Dict[str, Any],
    renamed: Dict[str, str],
    legacy: str,
    canonical: str,
) -> None:
    legacy_data = kits.get(legacy, {})
    canonical_data = kits.get(canonical, {})
    if not isinstance(legacy_data, dict) or not isinstance(canonical_data, dict):
        return
    if legacy_data.get("path") != canonical_data.get("path"):
        return
    for key, value in legacy_data.items():
        if key not in canonical_data or not canonical_data[key]:
            canonical_data[key] = value
    del kits[legacy]
    renamed[legacy] = canonical


def _rewrite_artifacts_legacy_kit_refs(
    *,
    artifacts_toml: Path,
    renamed: Dict[str, str],
    toml_utils,
) -> Dict[str, str]:
    if not artifacts_toml.is_file():
        return {}
    changed_renames: Dict[str, str] = {}
    try:
        with open(artifacts_toml, "rb") as f:
            reg = tomllib.load(f)
        changed = False
        for sys_entry in reg.get("systems", []):
            if not isinstance(sys_entry, dict):
                continue
            kit_ref = sys_entry.get("kit", "")
            canonical = renamed.get(kit_ref)
            if not canonical:
                continue
            sys_entry["kit"] = canonical
            changed = True
            changed_renames[kit_ref] = canonical
        if changed:
            toml_utils.dump(reg, artifacts_toml, header_comment="Constructor Studio artifacts registry")
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Legacy kit dedup write failed for %s: %s", artifacts_toml, exc)
        return {}
    return changed_renames


def _deduplicate_legacy_kits(config_dir: Path) -> Dict[str, str]:
    """Deduplicate legacy kit slugs in core.toml and artifacts.toml.

    If both legacy and canonical slugs exist with the same path,
    merge into canonical and remove legacy. Updates:
    - core.toml [kits] section
    - artifacts.toml [[systems]].kit references

    Returns dict of {legacy_slug: canonical_slug} for deduplicated kits.
    """
    core_toml = config_dir / "core.toml"
    if not core_toml.is_file():
        return {}

    renamed: Dict[str, str] = {}
    artifacts_renamed: Dict[str, str] = {}

    try:
        from ..utils import toml_utils
        with toml_utils._with_core_toml_lock(core_toml):
            try:
                with open(core_toml, "rb") as f:
                    data = tomllib.load(f)
            except (OSError, ValueError, TypeError) as exc:
                logger.warning("Cannot parse %s while deduplicating legacy kits: %s", core_toml, exc)
                return {}

            kits = data.get("kits", {})
            if not isinstance(kits, dict):
                return {}

            safe_artifact_renames: Dict[str, str] = {}
            for legacy, canonical in _LEGACY_SLUG_RENAMES.items():
                if canonical not in kits:
                    continue
                if legacy not in kits:
                    safe_artifact_renames[legacy] = canonical
                    continue
                _merge_duplicate_legacy_kit(kits, renamed, legacy, canonical)
                if legacy in renamed:
                    safe_artifact_renames[legacy] = canonical

            if renamed:
                toml_utils.dump(data, core_toml, header_comment="Constructor Studio project configuration")

            # Update artifacts.toml inside the lock so both TOML files are
            # mutated atomically with respect to other processes holding the
            # same core.toml advisory lock, but only for legacy slugs that were
            # actually merged safely in this run.
            artifacts_renamed = _rewrite_artifacts_legacy_kit_refs(
                artifacts_toml=config_dir / "artifacts.toml",
                renamed=safe_artifact_renames,
                toml_utils=toml_utils,
            )

    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Legacy kit dedup write failed for %s: %s", core_toml, exc)

    return {**renamed, **artifacts_renamed}
# @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-record-core-toml-migrations


# Known bundled kits and their GitHub sources
_KNOWN_KIT_SOURCES: Dict[str, str] = {
    "sdlc": "github:constructorfabric/studio-kit-sdlc",
}

# @cpt-begin:cpt-studio-algo-version-config-update-pipeline:p1:inst-migrate-kit-sources-algo
def _migrate_kit_sources(config_dir: Path) -> Dict[str, str]:
    """Add 'source' field to installed kits that lack one (metadata-only).

    For projects upgrading from versions where kits were bundled in cache,
    this adds the GitHub source reference so that Step 2 can download and
    update the kit with interactive diff.

    Returns dict of {slug: source} for migrated kits. Empty if nothing changed.
    """
    core_toml = config_dir / "core.toml"
    if not core_toml.is_file():
        return {}

    migrated: Dict[str, str] = {}
    try:
        from ..utils import toml_utils
        with toml_utils._with_core_toml_lock(core_toml):
            try:
                with open(core_toml, "rb") as f:
                    data = tomllib.load(f)
            except (OSError, ValueError, TypeError) as exc:
                logger.warning("Cannot parse %s while migrating kit sources: %s", core_toml, exc)
                return {}

            kits = data.get("kits", {})
            if not isinstance(kits, dict):
                return {}

            for slug, kit_data in kits.items():
                if not isinstance(kit_data, dict):
                    continue
                if kit_data.get("source"):
                    continue  # Already has a source — skip
                known_source = _KNOWN_KIT_SOURCES.get(slug, "")
                if known_source:
                    kit_data["source"] = known_source
                    migrated[slug] = known_source

            if not migrated:
                return {}

            toml_utils.dump(
                data, core_toml,
                header_comment="Constructor Studio project configuration",
            )
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Kit source migration write failed for %s: %s", core_toml, exc)
        return {}

    return migrated
# @cpt-end:cpt-studio-algo-version-config-update-pipeline:p1:inst-migrate-kit-sources-algo


# Re-exported from kit.py — tests import it from here
from .kit import _read_conf_version  # noqa: F401  # pylint: disable=unused-import,wrong-import-position


def _show_validate_kits_failures(vk_report: Dict[str, Any]) -> None:
    """Render a compact validate-kits failure summary."""
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-update-format-output
    for err in (vk_report.get("errors") or [])[:5]:
        if not isinstance(err, dict):
            ui.substep(f"  ✗ {err}")
            continue
        msg = err.get("message", "")
        path = err.get("path", "")
        if path:
            msg = f"{path}: {msg}"
        ui.substep(f"  ✗ {msg}")
        for detail in (err.get("errors") or []):
            ui.substep(f"      {detail}")
    n_err = int(vk_report.get("error_count", 0))
    if n_err > 5:
        ui.substep(f"  ... and {n_err - 5} more error(s)")
    ui.hint("Run 'cfs validate-kits --verbose' for full details.")
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-update-format-output


def _show_file_action_group(title: str, values: List[str], action: str) -> None:
    """Render a grouped list of file actions."""
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-update-format-output
    if not values:
        return
    ui.blank()
    ui.step(f"{title} ({len(values)})")
    for key in values:
        ui.file_action(key, action)
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-update-format-output


def _show_update_action_groups(actions: Dict[str, Any]) -> None:
    """Render simple created, updated, and unchanged action groups."""
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-update-format-output
    created = [k for k, v in actions.items() if v == "created"]
    updated = [k for k, v in actions.items() if v == "updated"]
    unchanged = [k for k, v in actions.items() if v in ("unchanged", "preserved")]

    _show_file_action_group("Created", created, "created")
    _show_file_action_group("Updated", updated, "updated")
    if unchanged:
        ui.blank()
        ui.step(f"Unchanged ({len(unchanged)})")
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-update-format-output


def _show_core_update_actions(actions: Dict[str, Any]) -> None:
    """Render core update action details."""
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-update-format-output
    core_update = actions.get("core_update")
    if not isinstance(core_update, dict):
        return
    ui.blank()
    ui.step("Core:")
    for sub_k, sub_v in core_update.items():
        ui.file_action(sub_k, str(sub_v))
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-update-format-output


def _show_kit_update_actions(kits_data: Dict[str, Any]) -> None:
    """Render kit update action details."""
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-update-format-output
    ui.blank()
    if kits_data.get("status") == "skipped":
        ui.step("Kits: skipped")
        reason = kits_data.get("reason")
        if reason:
            ui.substep(f"  {reason}")
        tracking = kits_data.get("kit_tracking")
        if tracking:
            ui.substep(f"  kit_tracking={tracking}")
        return

    ui.step(f"Kits ({len(kits_data)})")
    for slug, kr in kits_data.items():
        if not isinstance(kr, dict):
            ui.substep(f"  {slug}: {kr}")
            continue
        ver = kr.get("version", {})
        ver_status = ver.get("status", "") if isinstance(ver, dict) else str(ver)
        gen = kr.get("gen", {})
        fw = gen.get("files_written", 0) if isinstance(gen, dict) else 0
        accepted_files = gen.get("accepted_files", []) if isinstance(gen, dict) else []
        rejected = kr.get("gen_rejected", [])

        if ver_status == "current":
            ui.substep(f"  {slug}: up to date")
            continue
        parts = [f"{slug}: {ver_status}"]
        if fw:
            parts.append(f"{fw} file(s) accepted")
        if rejected:
            parts.append(f"{len(rejected)} declined")
        ui.substep(f"  {'  '.join(parts)}")
        for fp in accepted_files:
            ui.substep(f"    ~ {fp}")
        for fp in rejected:
            ui.substep(f"    ✗ {fp} (declined)")
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-update-format-output


def _show_complex_update_actions(actions: Dict[str, Any]) -> None:
    """Render remaining non-scalar update actions."""
    # @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-update-format-output
    skip = {"core_update", "kits", "agents_regenerated"}
    for key, value in actions.items():
        if key in skip or isinstance(value, str):
            continue
        ui.blank()
        ui.step(f"{key}:")
        if isinstance(value, dict):
            for sub_k, sub_v in value.items():
                label = "..." if isinstance(sub_v, (dict, list)) else sub_v
                ui.substep(f"  {sub_k}: {label}")
        elif isinstance(value, list):
            for item in value:
                ui.substep(f"  {item}")
    # @cpt-end:cpt-studio-flow-version-config-update:p1:inst-update-format-output


# ---------------------------------------------------------------------------
# Human-friendly formatter
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-flow-version-config-update:p1:inst-update-format-output
def _human_update_ok(data: Dict[str, Any]) -> None:
    dry = data.get("dry_run", False)
    status = data.get("status", "")
    errors = data.get("errors", [])
    warnings = data.get("warnings", [])
    prefix = "[dry-run] " if dry else ""

    ui.header(f"{prefix}Constructor Studio Update")
    ui.detail("Project root", str(data.get("project_root", "?")))
    ui.detail("Constructor Studio dir", str(data.get("studio_dir", "?")))

    actions = data.get("actions", {})
    if actions:
        # Summarize file actions
        _show_update_action_groups(actions)

        # Core update details
        _show_core_update_actions(actions)

        # Kit results
        kits_data = actions.get("kits")
        if isinstance(kits_data, dict):
            _show_kit_update_actions(kits_data)

        # Remaining dict/list actions (not already handled)
        _show_complex_update_actions(actions)

        agents_regen = actions.get("agents_regenerated")
        if isinstance(agents_regen, list) and agents_regen:
            ui.blank()
            ui.step(f"Agent integrations regenerated: {', '.join(agents_regen)}")

    if errors:
        ui.blank()
        ui.warn(f"Errors ({len(errors)}):")
        _render_error_entries(errors)
    if warnings:
        ui.blank()
        for w in warnings:
            ui.warn(w)

    if dry:
        ui.success("Dry run complete — no files were written.")
    elif status == "PASS":
        ui.success("Update complete!")
    else:
        ui.warn("Update finished with warnings (see above).")
    ui.blank()
# @cpt-end:cpt-studio-flow-version-config-update:p1:inst-update-format-output
