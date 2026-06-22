"""Initialize Constructor Studio project files."""

# @cpt-begin:cpt-studio-flow-core-infra-project-init:p1:inst-init-helpers
import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..constants import ROOT_AGENTS_PIPELINE_INSTRUCTION
from ..utils._tomllib_compat import tomllib
from ..utils.artifacts_meta import create_backup, generate_default_registry, generate_slug
from ..utils.files import read_root_agents_marked_text
from ..utils import toml_utils
from ..utils.ui import ui
from .agents import list_managed_agent_output_paths

# Cache-managed install content: core directories go into .core/, root files go into the install root.
# Full directories (copied entirely)
COPY_DIRS = ["requirements", "schemas", "workflows", "skills"]
# Selective items from architecture/ (only specs needed by agents)
COPY_ARCHITECTURE_ITEMS = [
    "specs/traceability.md",   # ID formats, code traceability — used by kit rules
    "specs/CDSL.md",           # Behavioral spec language — referenced by traceability.md
    "specs/PDSL.md",           # PDSL prompt contract spec — used by cf-pdsl
    "specs/cli.md",            # CLI commands — referenced by traceability.md, kit/rules.md
    "specs/CLISPEC.md",        # CLI spec (detailed command definitions)
    "specs/artifacts-registry.md",  # Artifacts config — used by .gen/AGENTS.md
    "specs/kit/constraints.md",     # Constraints spec — used by ADR, PRD, DESIGN rules
    "specs/kit/kit.md",             # Kit structure — referenced by kit/rules.md
]
COPY_ROOT_DIRS: list[str] = []
COPY_ROOT_FILES = ["whatsnew.toml", "version.toml"]
CACHE_DIR = Path.home() / ".cf-studio" / "cache"
CORE_SUBDIR = ".core"
GEN_SUBDIR = ".gen"
DEFAULT_INSTALL_DIR = ".cf-studio"
KIT_TRACKING_POLICIES = ("tracked", "ignored")
KIT_TRACKING_ALIASES = {"untracked": "ignored"}
GITIGNORE_MARKER_START = "# BEGIN Constructor Studio"
GITIGNORE_MARKER_END = "# END Constructor Studio"
LEGACY_MIGRATION_CHOICES = ("ask", "yes", "no")
_CONFIG_README_PREAMBLE = (
    "# config -- User Configuration\n"
    "\n"
    "This directory contains **user-editable** configuration files.\n"
    "\n"
    "## Files\n"
    "\n"
)


def _warn_init(message: str) -> None:
    sys.stderr.write(f"init: warning: {message}\n")


def _cache_allows_root_metadata(cache_dir: Path) -> bool:
    """Return False for local/path cache sources where version metadata is not authoritative."""
    provenance_path = cache_dir / ".provenance.json"
    if not provenance_path.is_file():
        return True
    try:
        data = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _warn_init(f"failed to read cache provenance from {provenance_path}: {exc}")
        return True
    source_type = str(data.get("source_type") or "").strip().lower()
    return source_type not in {"local", "local_path", "path"}


def _pre_force_existing_names(core_dir: Path, target_dir: Path) -> set[str]:
    existing: set[str] = set()
    for name in COPY_DIRS:
        if (core_dir / name).exists():
            existing.add(name)
    for name in COPY_ROOT_DIRS:
        if (target_dir / name).exists():
            existing.add(name)
    for name in COPY_ROOT_FILES:
        if (target_dir / name).exists():
            existing.add(name)
    return existing


def _copy_cache_dir(
    *,
    src: Path,
    dst: Path,
    name: str,
    force: bool,
    pre_force_existed: set[str],
    results: Dict[str, str],
) -> None:
    if not src.is_dir():
        results[name] = "missing_in_cache"
        return
    if dst.exists():
        if not force:
            results[name] = "skipped"
            return
        shutil.rmtree(dst)
        results[name] = "updated"
    else:
        results[name] = "updated" if force and name in pre_force_existed else "created"
    shutil.copytree(src, dst)


def _remove_existing_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
        return
    path.unlink()


def _copy_cache_file(
    *,
    src: Path,
    dst: Path,
    name: str,
    force: bool,
    pre_force_existed: set[str],
    results: Dict[str, str],
) -> None:
    if not src.is_file():
        if force and name in COPY_ROOT_FILES and (dst.exists() or dst.is_symlink()):
            _remove_existing_path(dst)
        results[name] = "missing_in_cache"
        return
    if dst.is_symlink():
        if not force:
            results[name] = "skipped"
            return
        dst.unlink()
        results[name] = "updated"
    if dst.exists():
        if not force:
            results[name] = "skipped"
            return
        _remove_existing_path(dst)
        results[name] = "updated"
    else:
        results[name] = "updated" if force and name in pre_force_existed else "created"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_architecture_items(
    *,
    cache_dir: Path,
    core_dir: Path,
    force: bool,
    pre_force_existed: set[str],
    results: Dict[str, str],
) -> None:
    arch_src = cache_dir / "architecture"
    arch_dst = core_dir / "architecture"
    for item in COPY_ARCHITECTURE_ITEMS:
        name = f"architecture/{item}"
        src = arch_src / item
        dst = arch_dst / item
        if src.is_dir():
            _copy_cache_dir(
                src=src,
                dst=dst,
                name=name,
                force=force,
                pre_force_existed=pre_force_existed,
                results=results,
            )
            continue
        if src.is_file():
            _copy_cache_file(
                src=src,
                dst=dst,
                name=name,
                force=force,
                pre_force_existed=pre_force_existed,
                results=results,
            )
            continue
        results[name] = "missing_in_cache"


def _copy_root_metadata_files(
    *,
    cache_dir: Path,
    target_dir: Path,
    force: bool,
    pre_force_existed: set[str],
    results: Dict[str, str],
) -> None:
    if not _cache_allows_root_metadata(cache_dir):
        for name in COPY_ROOT_FILES:
            results[name] = "skipped_local_path_source"
        return
    for name in COPY_ROOT_FILES:
        _copy_cache_file(
            src=cache_dir / name,
            dst=target_dir / name,
            name=name,
            force=force,
            pre_force_existed=pre_force_existed,
            results=results,
        )


def _copy_from_cache(cache_dir: Path, target_dir: Path, force: bool = False) -> Dict[str, str]:
    """Copy cache content into the project install directory.

    Core directories go into .core/ (read-only reference content).
    Managed metadata files go into the install root.
    User-editable content lives in config/.

    When force=True, .core/ is fully cleared before copying to ensure no stale
    core files remain from previous versions. Managed root metadata files are
    individually replaced or removed when absent from cache.

    Returns dict of {item_name: action}.
    """
    core_dir = target_dir / CORE_SUBDIR
    results: Dict[str, str] = {}
    pre_force_existed = _pre_force_existing_names(core_dir, target_dir) if force else set()

    # Full cleanup of .core/ when force=True (ensures no stale files)
    # This is the mode used by `cfs update` which always passes force=True
    if force and core_dir.exists():
        shutil.rmtree(core_dir)

    core_dir.mkdir(parents=True, exist_ok=True)

    for name in COPY_DIRS:
        _copy_cache_dir(
            src=cache_dir / name,
            dst=core_dir / name,
            name=name,
            force=force,
            pre_force_existed=pre_force_existed,
            results=results,
        )

    _copy_architecture_items(
        cache_dir=cache_dir,
        core_dir=core_dir,
        force=force,
        pre_force_existed=pre_force_existed,
        results=results,
    )

    for name in COPY_ROOT_DIRS:
        _copy_cache_dir(
            src=cache_dir / name,
            dst=target_dir / name,
            name=name,
            force=force,
            pre_force_existed=pre_force_existed,
            results=results,
        )

    _copy_root_metadata_files(
        cache_dir=cache_dir,
        target_dir=target_dir,
        force=force,
        pre_force_existed=pre_force_existed,
        results=results,
    )

    return results


def _dry_run_copy_results(
    cache_dir: Optional[Path] = None,
    target_dir: Optional[Path] = None,
    force: bool = False,
) -> Dict[str, str]:
    """Return the same copy-result shape as _copy_from_cache without writing."""
    results = {d: "dry_run" for d in COPY_DIRS}
    for item in COPY_ARCHITECTURE_ITEMS:
        results[f"architecture/{item}"] = "dry_run"
    if cache_dir is not None and not _cache_allows_root_metadata(cache_dir):
        for name in COPY_ROOT_FILES:
            results[name] = "skipped_local_path_source"
        return results
    for name in COPY_ROOT_FILES:
        if cache_dir is not None and not (cache_dir / name).is_file():
            dst = target_dir / name if target_dir is not None else None
            if force and dst is not None and (dst.exists() or dst.is_symlink()):
                results[name] = "would_remove"
            else:
                results[name] = "missing_in_cache"
            continue
        results[name] = "dry_run"
    return results


def _core_readme() -> str:
    """README.md content for .core/ directory."""
    return (
        "# .core — Constructor Studio Core Files\n"
        "\n"
        "**Do NOT edit files in this directory.**\n"
        "\n"
        "These files are copied from the Constructor Studio cache (`~/.cf-studio/cache/`) during\n"
        "`cfs init` or `cfs kit install`. They are the read-only reference copies of:\n"
        "\n"
        "- `skills/` — Constructor Studio skill scripts and CLI entry points\n"
        "- `workflows/` — workflow definitions\n"
        "- `requirements/` — validation requirements\n"
        "- `schemas/` — JSON schemas for configuration files\n"
        "- `architecture/specs/` — traceability, CDSL, PDSL, CLI, and kit specifications\n"
        "\n"
        "To update these files, run `cfs init --force` or `cfs kit update`.\n"
        "Any manual changes **will be overwritten** on the next update.\n"
    )

def _gen_readme() -> str:
    """README.md content for .gen/ directory."""
    return (
        "# .gen — Generated Files\n"
        "\n"
        "**Do NOT edit files in this directory.**\n"
        "\n"
        "These files are auto-generated by Constructor Studio during\n"
        "`cfs init`, `cfs kit install`, or `cfs update`.\n"
        "\n"
        "Contents:\n"
        "\n"
        "- `SKILL.md` — aggregated skill navigation (routes to per-kit skills)\n"
        "- `AGENTS.md` — generated agent navigation rules\n"
        "- `README.md` — this file\n"
        "\n"
        "Per-kit files are in `config/kits/{slug}/`.\n"
        "To update: `cfs update` or `cfs kit update`.\n"
        "Any manual changes to generated files **will be overwritten** on the next update.\n"
    )

def _config_readme() -> str:
    """README.md content for config/ directory."""
    return (
        _CONFIG_README_PREAMBLE +
        "- `core.toml` — project settings (system name, slug, kit references)\n"
        "- `artifacts.toml` — artifacts registry (systems, ignore patterns)\n"
        "- `AGENTS.md` — custom agent navigation rules (add your own WHEN rules here)\n"
        "- `SKILL.md` — custom skill extensions (add your own skill instructions here)\n"
        "\n"
        "## Directories\n"
        "\n"
        "- `kits/{slug}/` — kit files (SKILL.md, AGENTS.md, artifacts/, codebase/, workflows/, scripts/).\n"
        "  These are updated via `cfs update` or `cfs kit update`.\n"
        "\n"
        "## Tips\n"
        "\n"
        "- `AGENTS.md` and `SKILL.md` start empty. Add any project-specific rules or\n"
        "  skill instructions here — they will be picked up alongside the kit ones.\n"
        "- Kit files can be edited directly; `cfs kit update` shows a diff for changes.\n"
    )


def _add_legacy_migration_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared Cyber Pilot migration flags to a parser."""
    parser.add_argument(
        "--migrate-from-cypilot",
        choices=LEGACY_MIGRATION_CHOICES,
        default="ask",
        metavar="{ask,yes,no}",
        help=(
            "Migrate an existing Cyber Pilot (cypilot) project. Use "
            "--migrate-from-cypilot={ask,yes,no} (default: ask)"
        ),
    )
    parser.add_argument(
        "--update-legacy-studio",
        choices=LEGACY_MIGRATION_CHOICES,
        default="ask",
        metavar="{ask,yes,no}",
        help=(
            "Update unsupported Constructor Studio installs to the migration "
            "baseline first. Use --update-legacy-studio={ask,yes,no} "
            "(default: ask)"
        ),
    )


def _emit_legacy_migration_result(
    result: Dict[str, Any],
    preflight: Dict[str, Any],
    *,
    human_fn: Any,
) -> None:
    """Merge legacy preflight details into the migration result and render it."""
    from .migrate_from_cypilot import merge_legacy_preflight_result

    merge_legacy_preflight_result(result, preflight)
    ui.result(result, human_fn=human_fn)


def _run_legacy_migration(
    *,
    project_root: Path,
    from_dir: str,
    to_dir: str,
    dry_run: bool,
    force: bool,
    yes: bool,
) -> tuple[int, Dict[str, Any]]:
    """Run the shared Cyber Pilot migration command."""
    from .migrate_from_cypilot import migrate_from_cypilot

    options = {
        "project_root": project_root,
        "from_dir": from_dir,
        "to_dir": to_dir,
        "dry_run": dry_run,
        "force": force,
        "yes": yes,
    }
    return _legacy_migration_kwargs(
        migrate_from_cypilot=migrate_from_cypilot,
        **options,
    )


def _legacy_migration_kwargs(
    *,
    migrate_from_cypilot,
    project_root: Path,
    from_dir: str,
    to_dir: str,
    dry_run: bool,
    force: bool,
    yes: bool,
) -> tuple[int, Dict[str, Any]]:
    options = {
        "project_root": project_root,
        "from_dir": from_dir,
        "to_dir": to_dir,
        "dry_run": dry_run,
        "force": force,
        "yes": yes,
        "skip_update": False,
    }
    return migrate_from_cypilot(**options)


def _run_and_emit_legacy_migration(
    *,
    project_root: Path,
    from_dir: str,
    to_dir: str,
    dry_run: bool,
    force: bool,
    yes: bool,
    preflight: Dict[str, Any],
    human_fn: Any,
) -> tuple[int, Dict[str, Any]]:
    """Run the migration command and emit the merged result."""
    migration_args = {
        "project_root": project_root,
        "from_dir": from_dir,
        "to_dir": to_dir,
        "dry_run": dry_run,
        "force": force,
        "yes": yes,
    }
    rc, result = _run_legacy_migration(**migration_args)
    _emit_legacy_migration_result(result, preflight, human_fn=human_fn)
    return rc, result


def _run_default_legacy_migration(
    *,
    args: argparse.Namespace,
    project_root: Path,
    from_dir: str,
    to_dir: str,
    preflight: Dict[str, Any],
    human_fn: Any,
    force: bool = False,
) -> int:
    """Run the standard legacy migration flow using CLI defaults."""
    rc, _result = _run_and_emit_legacy_migration(
        project_root=project_root,
        from_dir=from_dir,
        to_dir=to_dir,
        dry_run=args.dry_run,
        force=force,
        yes=args.yes or args.migrate_from_cypilot == "yes",
        preflight=preflight,
        human_fn=human_fn,
    )
    return rc


def _render_error_entries(errors: object) -> None:
    """Render a mixed list of string/dict errors."""
    for err in errors if isinstance(errors, list) else []:
        if isinstance(err, dict):
            ui.substep(f"• {err.get('path', '?')}: {err.get('error', '?')}")
        else:
            ui.substep(f"• {err}")


@dataclass
class _InitState:
    project_root: Path
    install_rel: str
    project_name: str
    runtime_tracking: str
    agent_tracking: str
    default_kit_tracking: str
    kit_tracking_overrides: Dict[str, str]
    root_system: Dict[str, str]
    install_options_prompted: bool = False
    legacy_migration_declined: bool = False
    legacy_install_rel: Optional[str] = None


@dataclass
class _InitLayout:
    studio_dir: Path
    config_dir: Path
    gen_dir: Path
    core_dir: Path
    core_toml_path: Path
    config_agents_path: Path


@dataclass
class _InitTrackingOptions:
    default_kit_tracking: str
    kit_tracking_overrides: Dict[str, str]
    runtime_tracking: str
    agent_tracking: str


@dataclass
class _InstallTrackingSettings:
    kit_tracking: str
    runtime_tracking: str
    agent_tracking: str


@dataclass
class _InitRunState:
    actions: Dict[str, str] = field(default_factory=dict)
    errors: List[Dict[str, str]] = field(default_factory=list)
    backups: List[str] = field(default_factory=list)


def _parse_init_args(
    argv: List[str],
) -> Tuple[argparse.Namespace, _InitTrackingOptions]:
    p = argparse.ArgumentParser(prog="init", description="Initialize Constructor Studio in a project")
    p.add_argument("--project-root", default=None, help="Project root directory")
    p.add_argument(
        "--install-dir",
        default=None,
        help="Constructor Studio directory relative to project root (default: .cf-studio)",
    )
    p.add_argument(
        "--from-dir",
        default=None,
        help="Constructor Studio directory relative to project root when migrating",
    )
    p.add_argument("--project-name", default=None, help="Project name (default: project root folder name)")
    p.add_argument(
        "--runtime-tracking",
        default="ignored",
        metavar="tracked|ignored",
        help="Git tracking policy for .core/.gen runtime files (default: ignored; alias: untracked)",
    )
    p.add_argument(
        "--agent-tracking",
        default="ignored",
        metavar="tracked|ignored",
        help="Git tracking policy for generated agent integration files (default: ignored; alias: untracked)",
    )
    p.add_argument(
        "--kit-tracking",
        action="append",
        default=None,
        metavar="tracked|ignored|KIT=tracked|ignored",
        help=(
            "Kit git tracking policy. Use tracked/ignored as the default, or "
            "KIT=tracked|ignored for a specific kit. May be repeated. "
            "Alias: untracked=ignored."
        ),
    )
    p.add_argument("--yes", action="store_true", help="Do not prompt; accept defaults")
    p.add_argument("--dry-run", action="store_true", help="Compute changes without writing files")
    p.add_argument("--force", action="store_true", help="Overwrite existing files")
    _add_legacy_migration_args(p)
    args = p.parse_args(argv)
    try:
        default_kit_tracking, kit_tracking_overrides = _parse_kit_tracking_args(args.kit_tracking)
        runtime_tracking = _normalize_kit_tracking(args.runtime_tracking)
        agent_tracking = _normalize_kit_tracking(args.agent_tracking)
        if runtime_tracking is None:
            raise ValueError("--runtime-tracking must be tracked, ignored, or untracked")
        if agent_tracking is None:
            raise ValueError("--agent-tracking must be tracked, ignored, or untracked")
    except ValueError as exc:
        p.error(str(exc))
    return args, _InitTrackingOptions(
        default_kit_tracking=default_kit_tracking,
        kit_tracking_overrides=kit_tracking_overrides,
        runtime_tracking=runtime_tracking,
        agent_tracking=agent_tracking,
    )


def _show_init_welcome(interactive: bool) -> None:
    if not interactive:
        return
    sys.stderr.write("\n")
    sys.stderr.write("  \033[1mWelcome to Constructor Studio\033[0m\n")
    sys.stderr.write("  Set up AI-powered architecture traceability for your project.\n")
    sys.stderr.write("  Constructor Studio will create a configuration directory with design artifacts,\n")
    sys.stderr.write("  validation rules, and agent integration files.\n")
    sys.stderr.write("\n")


def _resolve_init_project_root(args: argparse.Namespace, cwd: Path, interactive: bool) -> Path:
    default_project_root = cwd
    if args.project_root is None and interactive:
        sys.stderr.write("  \033[2mThe project root is the top-level directory of your repository.\033[0m\n")
        sys.stderr.write("  \033[2mPress Enter to use the current directory.\033[0m\n")
        raw_root = _prompt_path("Project root directory?", default_project_root.as_posix())
        return _resolve_user_path(raw_root, cwd)
    raw_root = args.project_root or default_project_root.as_posix()
    return _resolve_user_path(raw_root, cwd)


def _build_init_state(
    *,
    args: argparse.Namespace,
    project_root: Path,
    existing_install_rel: Optional[str],
    default_kit_tracking: str,
    kit_tracking_overrides: Dict[str, str],
    runtime_tracking: str,
    agent_tracking: str,
) -> _InitState:
    default_install_dir = existing_install_rel or DEFAULT_INSTALL_DIR
    install_rel = (args.install_dir or default_install_dir).strip() or default_install_dir
    root_system = _define_root_system(project_root)
    project_name = str(args.project_name).strip() if args.project_name else root_system["name"]
    return _InitState(
        project_root=project_root,
        install_rel=install_rel,
        project_name=project_name,
        runtime_tracking=runtime_tracking,
        agent_tracking=agent_tracking,
        default_kit_tracking=default_kit_tracking,
        kit_tracking_overrides=dict(kit_tracking_overrides),
        root_system=root_system,
    )


def _maybe_run_init_legacy_migration(
    *,
    args: argparse.Namespace,
    interactive: bool,
    existing_install_rel: Optional[str],
    state: _InitState,
) -> Optional[int]:
    if existing_install_rel is not None:
        return None
    from .migrate_from_cypilot import (
        detect_legacy_cypilot_install,
        ensure_supported_legacy_version,
        should_migrate_from_cypilot,
        _human_migrate_ok,
    )

    legacy_rel = args.from_dir or detect_legacy_cypilot_install(state.project_root)
    if not legacy_rel:
        return None

    state.legacy_install_rel = legacy_rel
    migrate = should_migrate_from_cypilot(
        args.migrate_from_cypilot,
        interactive=interactive,
        project_root=state.project_root,
        legacy_rel=legacy_rel,
        decline_hint="Press N to initialize Constructor Studio side-by-side and keep Cyber Pilot unchanged.",
    )
    if not migrate:
        state.legacy_migration_declined = True
        return None

    supported, preflight = ensure_supported_legacy_version(
        project_root=state.project_root,
        legacy_rel=legacy_rel,
        update_choice=args.update_legacy_studio,
        interactive=interactive,
        dry_run=args.dry_run,
    )
    if not supported:
        ui.result(preflight)
        return 1

    migration_was_interactive = (
        args.migrate_from_cypilot == "ask"
        and interactive
        and sys.stdin.isatty()
    )
    if args.install_dir is None and migration_was_interactive:
        state.install_rel = legacy_rel.strip() or state.install_rel
    if migration_was_interactive:
        (
            state.install_rel,
            state.project_name,
            state.runtime_tracking,
            state.agent_tracking,
            state.default_kit_tracking,
            state.kit_tracking_overrides,
        ) = _prompt_install_options(
            state.project_root,
            state.install_rel,
            state.project_name,
            state.runtime_tracking,
            state.agent_tracking,
            state.default_kit_tracking,
            state.kit_tracking_overrides,
            interactive,
        )
        state.install_options_prompted = True

    return _run_default_legacy_migration(
        args=args,
        project_root=state.project_root,
        from_dir=legacy_rel,
        to_dir=state.install_rel,
        preflight=preflight,
        human_fn=_human_migrate_ok,
    )


def _prompt_remaining_init_options(interactive: bool, state: _InitState) -> None:
    if not interactive or state.install_options_prompted:
        return
    (
        state.install_rel,
        state.project_name,
        state.runtime_tracking,
        state.agent_tracking,
        state.default_kit_tracking,
        state.kit_tracking_overrides,
    ) = _prompt_install_options(
        state.project_root,
        state.install_rel,
        state.project_name,
        state.runtime_tracking,
        state.agent_tracking,
        state.default_kit_tracking,
        state.kit_tracking_overrides,
        interactive,
    )


def _emit_declined_legacy_install_dir_error(
    *,
    project_root: Path,
    install_rel: str,
    legacy_dir: Path,
) -> int:
    ui.result(
        {
            "status": "ERROR",
            "message": (
                "Migration was declined, but --install-dir resolves to the existing Constructor Studio "
                "directory. Choose a different --install-dir or approve migration."
            ),
            "project_root": project_root.as_posix(),
            "install_dir": install_rel,
            "legacy_studio_dir": legacy_dir.as_posix(),
            "actions": {
                "legacy_studio": "detected",
                "migration": "declined",
                "migration_decline_action": "rejected_legacy_install_dir",
            },
        },
        human_fn=lambda d: (
            ui.error(str(d["message"])),
            ui.detail("Legacy Constructor Studio directory", str(d["legacy_studio_dir"])),
            ui.blank(),
            ui.hint("Choose a side-by-side directory:  cfs init --install-dir .cf-studio --migrate-from-cypilot=no"),
            ui.hint("Or approve migration:             cfs init --install-dir .cf-studio --migrate-from-cypilot=yes"),
            ui.blank(),
        ),
    )
    return 1


def _validate_declined_legacy_target(state: _InitState, studio_dir: Path) -> Optional[int]:
    if not state.legacy_migration_declined or not state.legacy_install_rel:
        return None
    legacy_dir = (state.project_root / state.legacy_install_rel).resolve()
    if studio_dir != legacy_dir:
        return None
    return _emit_declined_legacy_install_dir_error(
        project_root=state.project_root,
        install_rel=state.install_rel,
        legacy_dir=legacy_dir,
    )

def _default_core_toml() -> dict:
    """Build default core.toml data for a new project.

    System identity (name, slug, kit) is defined in artifacts.toml only
    (see ADR-0014: cpt-studio-adr-remove-system-from-core-toml).

    Kits are registered dynamically via install_kit() when user accepts
    installation — not hardcoded here.
    """
    return {
        "version": "1.0",
        "project_root": "..",
        "install": {
            "version_source": "project_config",
            "runtime_tracking": "ignored",
            "agent_tracking": "ignored",
            "kit_tracking": "tracked",
        },
        "kits": {},
    }


def _normalize_kit_tracking(value: object) -> Optional[str]:
    normalized = str(value).strip().lower()
    normalized = KIT_TRACKING_ALIASES.get(normalized, normalized)
    if normalized in KIT_TRACKING_POLICIES:
        return normalized
    return None


def _parse_kit_tracking_args(values: Optional[List[str]]) -> tuple[str, Dict[str, str]]:
    default_policy = "tracked"
    overrides: Dict[str, str] = {}
    for raw in values or []:
        if "=" not in raw:
            policy = _normalize_kit_tracking(raw)
            if policy is None:
                raise ValueError(
                    "--kit-tracking must be tracked, ignored, untracked, or <kit>=tracked|ignored"
                )
            default_policy = policy
            continue
        slug, policy_raw = raw.split("=", 1)
        slug = slug.strip()
        policy = _normalize_kit_tracking(policy_raw)
        if not slug or policy is None:
            raise ValueError(
                "--kit-tracking per-kit values must use <kit>=tracked|ignored"
            )
        overrides[slug] = policy
    return default_policy, overrides


def _kit_entry_path(slug: str, entry: object) -> str:
    if isinstance(entry, dict):
        raw_path = entry.get("path")
        if isinstance(raw_path, str) and raw_path.strip():
            return raw_path.strip()
    return f"config/kits/{slug}"


def _read_kit_tracking_state(
    core_toml_path: Path,
    default: str = "tracked",
) -> tuple[str, Dict[str, str], Dict[str, str]]:
    try:
        data = toml_utils.load(core_toml_path)
    except (OSError, ValueError):
        return default, {}, {}
    install_data = data.get("install", {})
    default_policy = default
    if isinstance(install_data, dict):
        value = _normalize_kit_tracking(install_data.get("kit_tracking"))
        if value is not None:
            default_policy = value
    kits_data = data.get("kits")
    if not isinstance(kits_data, dict):
        return default_policy, {}, {}
    kit_tracking: Dict[str, str] = {}
    kit_paths: Dict[str, str] = {}
    for slug, entry in kits_data.items():
        if not isinstance(slug, str):
            continue
        tracking = default_policy
        if isinstance(entry, dict):
            value = _normalize_kit_tracking(entry.get("tracking"))
            if value is not None:
                tracking = value
        kit_tracking[slug] = tracking
        kit_paths[slug] = _kit_entry_path(slug, entry)
    return default_policy, kit_tracking, kit_paths


def _normalize_ignored_kit_path(
    project_root: Path,
    studio_root: Path,
    raw_path: str,
) -> Optional[str]:
    """Return a clean project-relative gitignore path for an ignored kit."""
    normalized = raw_path.strip().replace("\\", "/")
    if not normalized:
        return None
    candidate = Path(normalized)
    if not candidate.is_absolute():
        candidate = studio_root / candidate
    try:
        resolved = candidate.resolve()
        project_resolved = project_root.resolve()
    except OSError:
        resolved = candidate
        project_resolved = project_root
    try:
        return resolved.relative_to(project_resolved).as_posix()
    except ValueError:
        return resolved.as_posix()


# @cpt-begin:cpt-studio-algo-core-infra-gitignore-footprint:p1:inst-ignore-kits-by-policy
def _ignored_kit_paths(
    project_root: Path,
    core_toml_path: Path,
    default: str = "tracked",
) -> List[str]:
    _, kit_tracking, kit_paths = _read_kit_tracking_state(core_toml_path, default=default)
    studio_root = core_toml_path.parent.parent
    ignored: List[str] = []
    for slug, tracking in sorted(kit_tracking.items()):
        if tracking != "ignored":
            continue
        normalized = _normalize_ignored_kit_path(project_root, studio_root, kit_paths[slug])
        if normalized:
            ignored.append(normalized)
    return ignored
# @cpt-end:cpt-studio-algo-core-infra-gitignore-footprint:p1:inst-ignore-kits-by-policy


def _gitignore_patterns(
    project_root: Path,
    install_dir: str,
    ignored_kit_paths: List[str],
    runtime_tracking: str = "ignored",
    agent_tracking: str = "ignored",
) -> List[str]:
    install_rel = install_dir.strip().replace("\\", "/").strip("/")
    patterns: List[str] = []
    if runtime_tracking == "ignored":
        patterns.extend([
            f"{install_rel}/{CORE_SUBDIR}/",
            f"{install_rel}/{GEN_SUBDIR}/",
        ])
    if agent_tracking == "ignored":
        patterns.extend(
            list_managed_agent_output_paths(project_root, project_root / install_rel)
        )
    for kit_path in ignored_kit_paths:
        kit_rel = kit_path.strip().replace("\\", "/").strip("/")
        if kit_rel:
            patterns.append(kit_rel if kit_rel.endswith("/") else f"{kit_rel}/")
    return patterns


def _compute_gitignore_block(
    project_root: Path,
    install_dir: str,
    ignored_kit_paths: List[str],
    runtime_tracking: str = "ignored",
    agent_tracking: str = "ignored",
) -> str:
    # @cpt-begin:cpt-studio-algo-core-infra-gitignore-footprint:p1:inst-write-overwrite-warning
    lines = [
        GITIGNORE_MARKER_START,
        "# Generated Constructor Studio runtime and agent integration files.",
        "# Files matched here are owned by Constructor Studio and may be overwritten.",
        *_gitignore_patterns(
            project_root,
            install_dir,
            ignored_kit_paths,
            runtime_tracking=runtime_tracking,
            agent_tracking=agent_tracking,
        ),
        GITIGNORE_MARKER_END,
    ]
    # @cpt-end:cpt-studio-algo-core-infra-gitignore-footprint:p1:inst-write-overwrite-warning
    return "\n".join(lines)


def _rewrite_managed_block_content(
    content: str,
    expected_block: str,
    *,
    marker_start: str,
    marker_end: str,
    insert_mode: str,
    malformed_label: Optional[str] = None,
    validate_order: bool = False,
) -> Tuple[str, Optional[str]]:
    """Return the action and rewritten content for a managed text block."""
    has_start = marker_start in content
    has_end = marker_end in content
    if malformed_label and has_start != has_end:
        raise ValueError(f"{malformed_label} contains a malformed Constructor Studio managed block")
    if has_start and has_end:
        start_idx = content.index(marker_start)
        end_idx = content.index(marker_end)
        if validate_order and end_idx < start_idx:
            raise ValueError(f"{malformed_label} contains a malformed Constructor Studio managed block")
        end_idx += len(marker_end)
        current_block = content[start_idx:end_idx]
        if current_block == expected_block:
            return "unchanged", None
        return "updated", content[:start_idx] + expected_block + content[end_idx:]
    if insert_mode == "append":
        prefix = content.rstrip("\n")
        return "updated", (prefix + "\n\n" if prefix else "") + expected_block + "\n"
    if insert_mode == "prepend":
        return "updated", expected_block + "\n\n" + content
    raise ValueError(f"unsupported managed block insert mode: {insert_mode}")


def _write_managed_block_file(
    target_file: Path,
    expected_block: str,
    *,
    marker_start: str,
    marker_end: str,
    insert_mode: str,
    dry_run: bool = False,
    malformed_label: Optional[str] = None,
    validate_order: bool = False,
) -> str:
    """Create or update a file that contains a managed Constructor Studio block."""
    if not target_file.is_file():
        if not dry_run:
            target_file.write_text(expected_block + "\n", encoding="utf-8")
        return "created"

    content = target_file.read_text(encoding="utf-8")
    action, new_content = _rewrite_managed_block_content(
        content,
        expected_block,
        marker_start=marker_start,
        marker_end=marker_end,
        insert_mode=insert_mode,
        malformed_label=malformed_label,
        validate_order=validate_order,
    )
    if action == "unchanged":
        return action
    if not dry_run and new_content is not None:
        target_file.write_text(new_content, encoding="utf-8")
    return action


def _write_gitignore_block(
    project_root: Path,
    install_dir: str,
    core_toml_path: Path,
    default_kit_tracking: str,
    dry_run: bool = False,
) -> str:
    gitignore_path = project_root / ".gitignore"
    expected_block = _compute_gitignore_block(
        project_root,
        install_dir,
        _ignored_kit_paths(project_root, core_toml_path, default=default_kit_tracking),
        runtime_tracking=_read_install_tracking(core_toml_path, "runtime_tracking", default="ignored"),
        agent_tracking=_read_install_tracking(core_toml_path, "agent_tracking", default="ignored"),
    )
    return _write_managed_block_file(
        gitignore_path,
        expected_block,
        marker_start=GITIGNORE_MARKER_START,
        marker_end=GITIGNORE_MARKER_END,
        insert_mode="append",
        dry_run=dry_run,
        malformed_label=".gitignore",
        validate_order=True,
    )


def _persist_install_metadata(
    core_toml_path: Path,
    kit_tracking: str,
    runtime_tracking: str = "ignored",
    agent_tracking: str = "ignored",
    dry_run: bool = False,
    kit_tracking_overrides: Optional[Dict[str, str]] = None,
    apply_default_to_missing_kits: bool = False,
) -> str:
    # @cpt-begin:cpt-studio-flow-core-infra-project-init:p1:inst-persist-kit-tracking
    data: Dict[str, Any]
    existed = core_toml_path.is_file()
    if existed:
        try:
            data = toml_utils.load(core_toml_path)
        except (OSError, ValueError):
            data = _default_core_toml()
    else:
        data = _default_core_toml()
    install_data = data.get("install")
    if not isinstance(install_data, dict):
        install_data = {}
    install_data["version_source"] = "project_config"
    install_data["runtime_tracking"] = runtime_tracking
    install_data["agent_tracking"] = agent_tracking
    install_data["kit_tracking"] = kit_tracking
    data["install"] = install_data
    if "kits" not in data or not isinstance(data.get("kits"), dict):
        data["kits"] = {}
    kits_data = data["kits"]
    for slug, entry in list(kits_data.items()):
        if not isinstance(entry, dict):
            continue
        if kit_tracking_overrides and slug in kit_tracking_overrides:
            entry["tracking"] = kit_tracking_overrides[slug]
        elif apply_default_to_missing_kits and _normalize_kit_tracking(entry.get("tracking")) is None:
            entry["tracking"] = kit_tracking
    if not dry_run:
        core_toml_path.parent.mkdir(parents=True, exist_ok=True)
        toml_utils.dump(data, core_toml_path, header_comment="Constructor Studio project configuration")
    # @cpt-end:cpt-studio-flow-core-infra-project-init:p1:inst-persist-kit-tracking
    return "updated" if existed else "created"


def _read_kit_tracking(core_toml_path: Path, default: str = "tracked") -> str:
    default_policy, _, _ = _read_kit_tracking_state(core_toml_path, default=default)
    return default_policy


def _read_install_tracking(core_toml_path: Path, key: str, default: str = "ignored") -> str:
    try:
        data = toml_utils.load(core_toml_path)
    except (OSError, ValueError):
        return default
    install_data = data.get("install")
    if isinstance(install_data, dict):
        value = _normalize_kit_tracking(install_data.get(key))
        if value is not None:
            return value
    return default

def _prompt_path(question: str, default: Optional[str]) -> str:
    prompt = f"{question}"
    if default is not None and str(default).strip():
        prompt += f" [{default}]"
    prompt += ": "
    try:
        sys.stderr.write(prompt)
        sys.stderr.flush()
        ans = input().strip()
    except EOFError:
        ans = ""
    if ans:
        return ans
    return default or ""


def _emit_install_options(
    project_root: Path,
    install_rel: str,
    project_name: str,
    runtime_tracking: str,
    agent_tracking: str,
    kit_tracking: str,
    kit_tracking_overrides: Dict[str, str],
) -> None:
    sys.stderr.write("\n")
    sys.stderr.write("  Installation options\n")
    sys.stderr.write(f"  - Project root: {project_root.as_posix()}\n")
    sys.stderr.write(f"  - Project name: {project_name}\n")
    sys.stderr.write(f"  - Constructor Studio directory: {install_rel}/\n")
    sys.stderr.write(f"  - Runtime files (.core/.gen) git tracking: {runtime_tracking}\n")
    sys.stderr.write(f"  - Agent integration files git tracking: {agent_tracking}\n")
    sys.stderr.write(f"  - Default kit git tracking: {kit_tracking}\n")
    if kit_tracking_overrides:
        for slug, policy in sorted(kit_tracking_overrides.items()):
            sys.stderr.write(f"  - Kit {slug} git tracking: {policy}\n")
    else:
        sys.stderr.write("  - Per-kit git tracking: ask when installing each kit\n")
    sys.stderr.write("  - Runtime files: ignored files may be overwritten by repair/update\n")
    sys.stderr.write("  - Agent integration files: ignored files may be regenerated by Constructor Studio\n")
    sys.stderr.write("  - Kit files: tracked or ignored per kit; ignored kit files may be overwritten\n")
    sys.stderr.write("\n")


def _prompt_kit_tracking_policy(
    kit_slug: str,
    default_policy: str,
    explicit_policy: Optional[str],
    interactive: bool,
) -> str:
    if explicit_policy is not None:
        return explicit_policy
    if interactive and sys.stdin.isatty():
        if kit_slug == "default":
            sys.stderr.write("\n  Default git tracking for kits?\n")
        elif kit_slug in ("runtime files (.core/.gen)", "agent integration files"):
            sys.stderr.write(f"\n  Git tracking for {kit_slug}?\n")
        else:
            sys.stderr.write(f"\n  Git tracking for kit '{kit_slug}'?\n")
        sys.stderr.write("  `tracked` keeps these files in git so you can review and commit them.\n")
        sys.stderr.write("  `ignored` keeps these files out of git; Constructor Studio owns and may overwrite them.\n")
        sys.stderr.write(f"  Press Enter to use default: {default_policy}.\n")
        sys.stderr.write("  [t]racked / [i]gnored: ")
        sys.stderr.flush()
        try:
            answer = input().strip().lower()
        except EOFError:
            answer = ""
        if answer in ("t", "track", "tracked"):
            return "tracked"
        if answer in ("i", "ignore", "ignored", "untracked"):
            return "ignored"
    return default_policy


def _prompt_install_options(
    project_root: Path,
    install_rel: str,
    project_name: str,
    runtime_tracking: str,
    agent_tracking: str,
    kit_tracking: str,
    kit_tracking_overrides: Dict[str, str],
    interactive: bool,
) -> tuple[str, str, str, str, str, Dict[str, str]]:
    if not interactive or not sys.stdin.isatty():
        return install_rel, project_name, runtime_tracking, agent_tracking, kit_tracking, kit_tracking_overrides

    while True:
        _emit_install_options(
            project_root,
            install_rel,
            project_name,
            runtime_tracking,
            agent_tracking,
            kit_tracking,
            kit_tracking_overrides,
        )
        sys.stderr.write("  Review or change installation options? [y/N]: ")
        sys.stderr.flush()
        try:
            answer = input().strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            return install_rel, project_name, runtime_tracking, agent_tracking, kit_tracking, kit_tracking_overrides

        sys.stderr.write("\n")
        sys.stderr.write("  Select installation option\n")
        sys.stderr.write("  [1] Constructor Studio directory\n")
        sys.stderr.write("  [2] Project name\n")
        sys.stderr.write("  [3] Runtime files (.core/.gen) git tracking\n")
        sys.stderr.write("  [4] Agent integration files git tracking\n")
        sys.stderr.write("  [5] Default kit git tracking\n")
        sys.stderr.write("  [6] SDLC kit git tracking\n")
        sys.stderr.write("  [7] Done\n")
        sys.stderr.write("  Choice: ")
        sys.stderr.flush()
        try:
            choice = input().strip().lower()
        except EOFError:
            choice = ""

        if choice in ("1", "dir", "directory", "install-dir"):
            install_rel = _prompt_path(
                "Constructor Studio directory (relative to project root)?",
                install_rel,
            ).strip() or install_rel
        elif choice in ("2", "name", "project-name"):
            project_name = _prompt_path("Project name?", project_name).strip() or project_name
        elif choice in ("3", "runtime", "core", "gen", ".core", ".gen"):
            runtime_tracking = _prompt_kit_tracking_policy(
                "runtime files (.core/.gen)",
                runtime_tracking,
                None,
                interactive,
            )
        elif choice in ("4", "agents", "agent", "agent-integration"):
            agent_tracking = _prompt_kit_tracking_policy(
                "agent integration files",
                agent_tracking,
                None,
                interactive,
            )
        elif choice in ("5", "default", "tracking", "kit-tracking"):
            kit_tracking = _prompt_kit_tracking_policy(
                "default",
                kit_tracking,
                None,
                interactive,
            )
        elif choice in ("6", "sdlc"):
            kit_tracking_overrides["sdlc"] = _prompt_kit_tracking_policy(
                "sdlc",
                kit_tracking,
                None,
                interactive,
            )
        elif choice in ("7", "done", "d", ""):
            return install_rel, project_name, runtime_tracking, agent_tracking, kit_tracking, kit_tracking_overrides

def _resolve_user_path(raw: str, base: Path) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = base / p
    return p.resolve()

def _slug_to_pascal_case(slug: str) -> str:
    """Convert a slug like 'my-app' to PascalCase like 'MyApp'."""
    return "".join(word.capitalize() for word in slug.split("-")) if slug else "Unnamed"
# @cpt-end:cpt-studio-flow-core-infra-project-init:p1:inst-init-helpers

def _define_root_system(project_root: Path) -> Dict[str, str]:
    """
    Define root system from project directory.

    Returns dict with 'name' (PascalCase) and 'slug' (lowercase-hyphenated).
    """
    # @cpt-begin:cpt-studio-algo-core-infra-define-root-system:p1:inst-extract-basename
    basename = project_root.name
    # @cpt-end:cpt-studio-algo-core-infra-define-root-system:p1:inst-extract-basename

    # @cpt-begin:cpt-studio-algo-core-infra-define-root-system:p1:inst-derive-slug
    slug = generate_slug(basename)
    # @cpt-end:cpt-studio-algo-core-infra-define-root-system:p1:inst-derive-slug

    # @cpt-begin:cpt-studio-algo-core-infra-define-root-system:p1:inst-derive-name
    name = _slug_to_pascal_case(slug)
    # @cpt-end:cpt-studio-algo-core-infra-define-root-system:p1:inst-derive-name

    # @cpt-begin:cpt-studio-algo-core-infra-define-root-system:p1:inst-return-system-def
    return {"name": name, "slug": slug}
    # @cpt-end:cpt-studio-algo-core-infra-define-root-system:p1:inst-return-system-def

_TOML_FENCE_RE = re.compile(r"```toml\s*\n(.*?)```", re.DOTALL)
MARKER_START = "<!-- @cf:root-agents -->"
MARKER_END = "<!-- /@cf:root-agents -->"
_AGENTS_FILENAME = "AGENTS.md"
_README_FILENAME = "README.md"

# @cpt-begin:cpt-studio-flow-core-infra-project-init:p1:inst-init-detect-existing
def _read_existing_install(project_root: Path) -> Optional[str]:
    """
    Check if project already has Constructor Studio installed by reading AGENTS.md TOML block.

    Returns install dir relative path if found, None otherwise.
    """
    content = read_root_agents_marked_text(project_root)
    if content is None:
        return None
    for m in _TOML_FENCE_RE.finditer(content):
        try:
            data = tomllib.loads(m.group(1))
            # Canonical key is `cf-studio-path`; `cf-path` is a legacy alias
            # retained for backwards compat with installs generated by older
            # versions of `cfs init`.
            val = data.get("cf-studio-path") or data.get("cf-path")
            if isinstance(val, str) and val.strip():
                adapter_dir = project_root / val.strip()
                if adapter_dir.is_dir():
                    return val.strip()
        except (OSError, ValueError, KeyError) as exc:
            _warn_init(f"failed to inspect existing AGENTS.md TOML block: {exc}")
            continue
    return None
# @cpt-end:cpt-studio-flow-core-infra-project-init:p1:inst-init-detect-existing

def _compute_managed_block(install_dir: str) -> str:
    # @cpt-begin:cpt-studio-algo-core-infra-inject-root-agents:p1:inst-compute-block
    return (
        f"{MARKER_START}\n"
        f"```toml\n"
        f'cf-studio-path = "{install_dir}"\n'
        f"```\n"
        f"\n"
        f"{ROOT_AGENTS_PIPELINE_INSTRUCTION}\n"
        f"{MARKER_END}"
    )
    # @cpt-end:cpt-studio-algo-core-infra-inject-root-agents:p1:inst-compute-block

def _inject_managed_block(
    target_file: Path,
    install_dir: str,
    dry_run: bool = False,
    *,
    project_root: Optional[Path] = None,
) -> str:
    """Inject or update a managed block into *target_file*. Returns action taken."""
    # @cpt-begin:cpt-studio-algo-core-infra-inject-root-agents:p1:inst-validate-path
    resolved_target = target_file.resolve()
    if project_root is not None:
        resolved_root = project_root.resolve()
        if resolved_root not in resolved_target.parents and resolved_target != resolved_root:
            raise ValueError(f"Refusing to write outside project root: {resolved_target}")
    # @cpt-end:cpt-studio-algo-core-infra-inject-root-agents:p1:inst-validate-path
    expected_block = _compute_managed_block(install_dir)
    return _write_managed_block_file(
        target_file,
        expected_block,
        marker_start=MARKER_START,
        marker_end=MARKER_END,
        insert_mode="prepend",
        dry_run=dry_run,
    )

_DEFAULT_KIT_SOURCE = "constructorfabric/studio-kit-sdlc"


def _prompt_kit_install_flag(interactive: bool) -> bool:
    """Return True if the user accepted kit installation (or --yes mode)."""
    # @cpt-begin:cpt-studio-flow-core-infra-project-init:p1:inst-prompt-kit
    if interactive and sys.stdin.isatty():
        sys.stderr.write(f"\n  Install SDLC kit ({_DEFAULT_KIT_SOURCE})?\n")
        sys.stderr.write(
            "  This adds the default Constructor Studio SDLC templates, "
            "workflows, and rules for typical project setup.\n"
        )
        sys.stderr.write("  Reply with `a` to install it now or `d` to skip it.\n")
        sys.stderr.write(
            "  Suggested: `a` for first-time setup; `d` only if you want to "
            "install or manage kits manually.\n"
        )
        sys.stderr.write(
            "  `a` = download and install the default kit now. `d` = continue "
            "without installing the kit.\n"
        )
        sys.stderr.write("  [a]ccept / [d]ecline: ")
        sys.stderr.flush()
        try:
            answer = input().strip().lower()
        except EOFError:
            answer = "d"
        return answer in ("a", "accept")
    return not interactive
    # @cpt-end:cpt-studio-flow-core-infra-project-init:p1:inst-prompt-kit


def _record_default_kit_actions(
    *,
    actions: Dict[str, str],
    errors: List[Dict[str, str]],
    kit_slug: str,
    kit_result: Dict[str, Any],
) -> None:
    kit_status = kit_result.get("status", "")
    if kit_result.get("errors") and kit_status not in ("PASS", "WARN"):
        errors.extend({"path": kit_slug, "error": error} for error in kit_result["errors"])
    for key, val in kit_result.get("actions", {}).items():
        actions[f"kit_{kit_slug}_{key}"] = val
    if kit_status == "WARN":
        ui.warn(f"Kit '{kit_slug}' installed with warnings")
    elif kit_status and kit_status != "PASS":
        ui.warn(f"Kit '{kit_slug}' installed with status: {kit_status}")


def _download_default_kit_bundle() -> tuple[str, str, Optional[str], Path]:
    from .kit import _download_kit_from_github, _parse_github_source

    owner, repo, version = _parse_github_source(_DEFAULT_KIT_SOURCE)
    ui.step(f"Downloading {_DEFAULT_KIT_SOURCE}...")
    kit_source_dir, resolved_version = _download_kit_from_github(owner, repo, version)
    github_source = f"github:{owner}/{repo}"
    return github_source, resolved_version, version, kit_source_dir


def _build_default_kit_summary(studio_dir: Path, kit_result: Dict[str, Any]) -> Dict[str, Any]:
    art_dir = studio_dir / "config" / "kits" / "sdlc" / "artifacts"
    artifact_kinds = (
        sorted(d.name for d in art_dir.iterdir() if d.is_dir())
        if art_dir.is_dir() else []
    )
    return {
        "files_written": kit_result.get("files_copied", 0),
        "errors": kit_result.get("errors", []),
        "artifact_kinds": artifact_kinds,
    }


def _install_default_kit(
    studio_dir: Path,
    interactive: bool,
    actions: Dict[str, str],
    errors: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Download and install the default SDLC kit. Returns kit_results dict."""
    from .kit import _InstallContext, install_kit

    kit_results: Dict[str, Any] = {}
    # @cpt-begin:cpt-studio-flow-core-infra-project-init:p1:inst-install-kit-accepted
    tmp_to_clean: Optional[Path] = None
    try:
        github_source, resolved_version, _version, kit_source_dir = _download_default_kit_bundle()
        tmp_to_clean = kit_source_dir.parent

        kit_slug = "sdlc"
        kit_result = install_kit(
            kit_source_dir, studio_dir, kit_slug,
            kit_version=resolved_version,
            install_context=_InstallContext(
                interactive=interactive,
                source=github_source,
            ),
        )
        kit_results[kit_slug] = _build_default_kit_summary(studio_dir, kit_result)
        _record_default_kit_actions(
            actions=actions,
            errors=errors,
            kit_slug=kit_slug,
            kit_result=kit_result,
        )
        if kit_result.get("status", "") in ("", "PASS"):
            ui.substep(f"Kit '{kit_slug}' installed (v{resolved_version or 'dev'})")
    except (OSError, ValueError, RuntimeError) as exc:
        ui.warn(f"Kit installation failed: {exc}")
        errors.append({"path": "kit", "error": str(exc)})
    finally:
        if tmp_to_clean is not None:
            shutil.rmtree(tmp_to_clean, ignore_errors=True)
    # @cpt-end:cpt-studio-flow-core-infra-project-init:p1:inst-install-kit-accepted
    return kit_results


def _inject_root_agents(project_root: Path, install_dir: str, dry_run: bool = False) -> str:
    """Inject or update root AGENTS.md managed block. Returns action taken."""
    return _inject_managed_block(project_root / _AGENTS_FILENAME, install_dir, dry_run, project_root=project_root)

# @cpt-begin:cpt-studio-flow-core-infra-project-init:p1:inst-init-inject-claude
def _inject_root_claude(project_root: Path, install_dir: str, dry_run: bool = False) -> str:
    """Inject or update root CLAUDE.md managed block. Returns action taken."""
    return _inject_managed_block(project_root / "CLAUDE.md", install_dir, dry_run, project_root=project_root)
# @cpt-end:cpt-studio-flow-core-infra-project-init:p1:inst-init-inject-claude


def _ensure_repair_config_files(
    *,
    config_dir: Path,
    actions: Dict[str, object],
) -> None:
    config_agents_path = config_dir / _AGENTS_FILENAME
    if not config_agents_path.is_file():
        config_agents_path.write_text(
            "# Custom Agent Navigation Rules\n\n"
            "Add your project-specific WHEN rules here.\n"
            "These rules are loaded alongside the generated rules in `{cf-studio-path}/.gen/"
            + _AGENTS_FILENAME
            + "`.\n",
            encoding="utf-8",
        )
        actions["config_agents"] = "created"
    config_skill_path = config_dir / "SKILL.md"
    if not config_skill_path.is_file():
        config_skill_path.write_text(
            "# Custom Skill Extensions\n\n"
            "Add your project-specific skill instructions here.\n"
            "Agent-facing skills and workflows are generated into agent integration files.\n",
            encoding="utf-8",
        )
        actions["config_skill"] = "created"


def _emit_missing_cache_error(project_root: Path, *, studio_dir: Optional[Path] = None) -> int:
    payload: Dict[str, object] = {
        "status": "ERROR",
        "message": f"Constructor Studio cache not found at {CACHE_DIR}. Run 'cfs update' first.",
        "project_root": project_root.as_posix(),
    }
    if studio_dir is not None:
        payload["studio_dir"] = studio_dir.as_posix()
    ui.result(
        payload,
        human_fn=lambda d: (
            ui.error("Constructor Studio cache not found."),
            ui.detail("Expected at", str(CACHE_DIR)),
            ui.blank(),
            ui.hint(
                "Install Constructor Studio first:  "
                "pipx install git+https://github.com/constructorfabric/studio.git "
                "&& cfs update"
            ),
            ui.blank(),
        ),
    )
    return 1


def _prepare_init_layout(studio_dir: Path, args: argparse.Namespace, actions: Dict[str, str]) -> _InitLayout:
    if not args.dry_run:
        studio_dir.mkdir(parents=True, exist_ok=True)
        copy_results = _copy_from_cache(CACHE_DIR, studio_dir, force=args.force)
    else:
        copy_results = _dry_run_copy_results(CACHE_DIR, studio_dir, force=args.force)
    actions["copy"] = json.dumps(copy_results)

    config_dir = studio_dir / "config"
    gen_dir = studio_dir / GEN_SUBDIR
    core_dir = studio_dir / CORE_SUBDIR
    if not args.dry_run:
        config_dir.mkdir(parents=True, exist_ok=True)
        gen_dir.mkdir(parents=True, exist_ok=True)
        (core_dir / _README_FILENAME).write_text(_core_readme(), encoding="utf-8")
        (gen_dir / _README_FILENAME).write_text(_gen_readme(), encoding="utf-8")
        (config_dir / _README_FILENAME).write_text(_config_readme(), encoding="utf-8")
    actions["readmes"] = "created"
    return _InitLayout(
        studio_dir=studio_dir,
        config_dir=config_dir,
        gen_dir=gen_dir,
        core_dir=core_dir,
        core_toml_path=(config_dir / "core.toml").resolve(),
        config_agents_path=(config_dir / _AGENTS_FILENAME).resolve(),
    )


def _write_init_core_toml(
    *,
    layout: _InitLayout,
    args: argparse.Namespace,
    state: _InitState,
    actions: Dict[str, str],
) -> None:
    desired_core = _default_core_toml()
    core_toml_existed = layout.core_toml_path.is_file()
    if core_toml_existed and not args.force:
        actions["core_toml"] = "unchanged"
        actions["core_toml_metadata"] = _persist_install_metadata(
            layout.core_toml_path,
            state.default_kit_tracking,
            runtime_tracking=state.runtime_tracking,
            agent_tracking=state.agent_tracking,
            dry_run=args.dry_run,
        )
        return
    desired_core["install"]["runtime_tracking"] = state.runtime_tracking
    desired_core["install"]["agent_tracking"] = state.agent_tracking
    desired_core["install"]["kit_tracking"] = state.default_kit_tracking
    if not args.dry_run:
        toml_utils.dump(desired_core, layout.core_toml_path, header_comment="Constructor Studio project configuration")
    actions["core_toml"] = "updated" if core_toml_existed else "created"


def _ensure_init_config_agents(
    *,
    layout: _InitLayout,
    args: argparse.Namespace,
    actions: Dict[str, str],
) -> None:
    config_agents_existed = layout.config_agents_path.is_file()
    if config_agents_existed and not args.force:
        actions["config_agents"] = "unchanged"
    else:
        if not config_agents_existed and not args.dry_run:
            layout.config_agents_path.write_text(
                "# Custom Agent Navigation Rules\n"
                "\n"
                "Add your project-specific WHEN rules here.\n"
                "These rules are loaded alongside the generated rules in "
                f"`{{cf-studio-path}}/.gen/{_AGENTS_FILENAME}`.\n",
                encoding="utf-8",
            )
        actions["config_agents"] = "unchanged" if config_agents_existed else "created"
    actions["config_agents_path"] = layout.config_agents_path.as_posix()


def _emit_init_error(
    *,
    project_root: Path,
    studio_dir: Path,
    dry_run: bool,
    errors: List[Dict[str, str]],
    backups: List[str],
) -> int:
    err_result: Dict[str, object] = {
        "status": "ERROR",
        "message": "Init failed",
        "project_root": project_root.as_posix(),
        "studio_dir": studio_dir.as_posix(),
        "dry_run": dry_run,
        "errors": errors,
    }
    if backups:
        err_result["backups"] = backups
    ui.result(err_result, human_fn=_human_init_error)
    return 1


def _load_install_tracking_settings(
    core_toml_path: Path,
    default_kit_tracking: str,
) -> _InstallTrackingSettings:
    return _InstallTrackingSettings(
        kit_tracking=_read_kit_tracking(core_toml_path, default=default_kit_tracking),
        runtime_tracking=_read_install_tracking(
            core_toml_path,
            "runtime_tracking",
            default="ignored",
        ),
        agent_tracking=_read_install_tracking(
            core_toml_path,
            "agent_tracking",
            default="ignored",
        ),
    )


def _maybe_install_default_kit_for_init(
    *,
    args: argparse.Namespace,
    interactive: bool,
    studio_dir: Path,
    project_root: Path,
    state: _InitState,
    run_state: _InitRunState,
) -> tuple[Dict[str, Any], Optional[int]]:
    if args.dry_run:
        return {}, None
    install_kit_flag = _prompt_kit_install_flag(interactive)
    if not install_kit_flag:
        ui.info(f"Skipped kit installation. Install later: cfs kit install {_DEFAULT_KIT_SOURCE}")
        return {}, None
    state.kit_tracking_overrides["sdlc"] = _prompt_kit_tracking_policy(
        "sdlc",
        state.default_kit_tracking,
        state.kit_tracking_overrides.get("sdlc"),
        interactive,
    )
    kit_results = _install_default_kit(studio_dir, interactive, run_state.actions, run_state.errors)
    if "sdlc" in kit_results:
        kit_results["sdlc"]["tracking"] = state.kit_tracking_overrides["sdlc"]
    if run_state.errors:
        return kit_results, _emit_init_error(
            project_root=project_root,
            studio_dir=studio_dir,
            dry_run=bool(args.dry_run),
            errors=run_state.errors,
            backups=run_state.backups,
        )
    return kit_results, None


def _finalize_init_files(
    *,
    args: argparse.Namespace,
    layout: _InitLayout,
    state: _InitState,
    kit_results: Dict[str, Any],
    actions: Dict[str, str],
) -> None:
    from .kit import regenerate_gen_aggregates

    installed_kit_slug = next(iter(kit_results), "") if kit_results else ""
    desired_registry = generate_default_registry(state.project_name, kit_slug=installed_kit_slug)
    registry_path = (layout.config_dir / "artifacts.toml").resolve()
    registry_existed_before = registry_path.is_file()
    if registry_existed_before and not args.force:
        actions["artifacts_registry"] = "unchanged"
    else:
        if not args.dry_run:
            toml_utils.dump(desired_registry, registry_path, header_comment="Constructor Studio artifacts registry")
        actions["artifacts_registry"] = "updated" if registry_existed_before else "created"
    if not args.dry_run:
        actions.update(regenerate_gen_aggregates(layout.studio_dir))
        config_skill_path = layout.config_dir / "SKILL.md"
        if not config_skill_path.is_file():
            config_skill_path.write_text(
                "# Custom Skill Extensions\n"
                "\n"
                "Add your project-specific skill instructions here.\n"
                "Agent-facing skills and workflows are generated into agent integration files.\n",
                encoding="utf-8",
            )
            actions["config_skill"] = "created"
        else:
            actions["config_skill"] = "unchanged"
    actions["kits"] = json.dumps(kit_results)
    actions["core_toml_metadata"] = _persist_install_metadata(
        layout.core_toml_path,
        state.default_kit_tracking,
        runtime_tracking=state.runtime_tracking,
        agent_tracking=state.agent_tracking,
        dry_run=args.dry_run,
        kit_tracking_overrides=state.kit_tracking_overrides,
        apply_default_to_missing_kits=True,
    )
    actions["root_agents"] = _inject_root_agents(
        state.project_root,
        state.install_rel,
        dry_run=args.dry_run,
    )
    actions["root_claude"] = _inject_root_claude(
        state.project_root,
        state.install_rel,
        dry_run=args.dry_run,
    )
    actions["gitignore"] = _write_gitignore_block(
        state.project_root,
        state.install_rel,
        layout.core_toml_path,
        state.default_kit_tracking,
        dry_run=args.dry_run,
    )


def _build_init_result(
    *,
    args: argparse.Namespace,
    project_root: Path,
    studio_dir: Path,
    layout: _InitLayout,
    state: _InitState,
    actions: Dict[str, str],
    backups: List[str],
) -> Dict[str, object]:
    result: Dict[str, object] = {
        "status": "PASS",
        "project_root": project_root.as_posix(),
        "studio_dir": studio_dir.as_posix(),
        "core_toml": layout.core_toml_path.as_posix(),
        "dry_run": bool(args.dry_run),
        "actions": actions,
        "root_system": state.root_system,
        "runtime_tracking": state.runtime_tracking,
        "agent_tracking": state.agent_tracking,
        "kit_tracking": {
            "default": state.default_kit_tracking,
            "kits": _read_kit_tracking_state(layout.core_toml_path, default=state.default_kit_tracking)[1],
        },
    }
    if backups:
        result["backups"] = backups
    return result


def _repair_existing_install(
    project_root: Path,
    install_rel: str,
    kit_tracking: str,
    dry_run: bool = False,
) -> int:
    """Restore generated runtime files for an already initialized project."""
    if not CACHE_DIR.is_dir():
        return _emit_missing_cache_error(project_root, studio_dir=(project_root / install_rel).resolve())

    studio_dir = (project_root / install_rel).resolve()
    config_dir = studio_dir / "config"
    gen_dir = studio_dir / GEN_SUBDIR
    core_dir = studio_dir / CORE_SUBDIR
    actions: Dict[str, object] = {}
    errors: List[Dict[str, str]] = []
    core_toml_path = (config_dir / "core.toml").resolve()
    tracking = _load_install_tracking_settings(core_toml_path, kit_tracking)

    try:
        from .kit import regenerate_gen_aggregates

        if not dry_run:
            studio_dir.mkdir(parents=True, exist_ok=True)
            copy_results = _copy_from_cache(CACHE_DIR, studio_dir, force=True)
            config_dir.mkdir(parents=True, exist_ok=True)
            gen_dir.mkdir(parents=True, exist_ok=True)
            (core_dir / _README_FILENAME).write_text(_core_readme(), encoding="utf-8")
            (gen_dir / _README_FILENAME).write_text(_gen_readme(), encoding="utf-8")
            (config_dir / _README_FILENAME).write_text(_config_readme(), encoding="utf-8")
        else:
            copy_results = _dry_run_copy_results(CACHE_DIR, studio_dir, force=True)
        actions["copy"] = copy_results
        actions["readmes"] = "updated" if not dry_run else "dry_run"
        actions["core_toml"] = _persist_install_metadata(
            core_toml_path,
            tracking.kit_tracking,
            runtime_tracking=tracking.runtime_tracking,
            agent_tracking=tracking.agent_tracking,
            dry_run=dry_run,
        )

        if not dry_run:
            actions.update(regenerate_gen_aggregates(studio_dir))
            _ensure_repair_config_files(config_dir=config_dir, actions=actions)

        actions["root_agents"] = _inject_root_agents(project_root, install_rel, dry_run=dry_run)
        actions["root_claude"] = _inject_root_claude(project_root, install_rel, dry_run=dry_run)
        # @cpt-begin:cpt-studio-flow-core-infra-init-repair:p1:inst-restore-gitignore
        actions["gitignore"] = _write_gitignore_block(
            project_root,
            install_rel,
            core_toml_path,
            tracking.kit_tracking,
            dry_run=dry_run,
        )
        # @cpt-end:cpt-studio-flow-core-infra-init-repair:p1:inst-restore-gitignore
    except (OSError, ValueError, RuntimeError) as exc:
        errors.append({"path": install_rel, "error": str(exc)})

    if errors:
        ui.result(
            {
                "status": "ERROR",
                "message": "Init repair failed",
                "project_root": project_root.as_posix(),
                "studio_dir": studio_dir.as_posix(),
                "dry_run": bool(dry_run),
                "errors": errors,
                "actions": actions,
            },
            human_fn=_human_init_error,
        )
        return 1

    ui.result(
        {
            "status": "REPAIRED",
            "message": "Constructor Studio already initialized; generated runtime files repaired.",
            "project_root": project_root.as_posix(),
            "studio_dir": studio_dir.as_posix(),
            "core_toml": core_toml_path.as_posix(),
            "dry_run": bool(dry_run),
            "version_changed": False,
            "version_source": "project_config",
            "runtime_tracking": tracking.runtime_tracking,
            "agent_tracking": tracking.agent_tracking,
            "kit_tracking": {
                "default": tracking.kit_tracking,
                "kits": _read_kit_tracking_state(core_toml_path, default=tracking.kit_tracking)[1],
            },
            "actions": actions,
        },
        human_fn=lambda d: (
            ui.step("Constructor Studio already initialized; repaired generated runtime files."),
            ui.detail("Directory", str(studio_dir)),
            ui.detail("Runtime tracking", str(d.get("runtime_tracking", "ignored"))),
            ui.detail("Agent tracking", str(d.get("agent_tracking", "ignored"))),
            ui.detail("Kit tracking", tracking.kit_tracking),
            ui.blank(),
        ),
    )
    return 0


def _prepare_init_state(
    *,
    args: argparse.Namespace,
    tracking: _InitTrackingOptions,
) -> tuple[Optional[int], Path, bool, _InitState]:
    cwd = Path.cwd().resolve()
    interactive = not args.yes
    _show_init_welcome(interactive)
    project_root = _resolve_init_project_root(args, cwd, interactive)
    existing_install_rel = _read_existing_install(project_root)
    if existing_install_rel is not None and not args.force:
        return (
            _repair_existing_install(
                project_root,
                existing_install_rel,
                tracking.default_kit_tracking,
                dry_run=args.dry_run,
            ),
            project_root,
            interactive,
            _build_init_state(
                args=args,
                project_root=project_root,
                existing_install_rel=existing_install_rel,
                default_kit_tracking=tracking.default_kit_tracking,
                kit_tracking_overrides=tracking.kit_tracking_overrides,
                runtime_tracking=tracking.runtime_tracking,
                agent_tracking=tracking.agent_tracking,
            ),
        )

    state = _build_init_state(
        args=args,
        project_root=project_root,
        existing_install_rel=existing_install_rel,
        default_kit_tracking=tracking.default_kit_tracking,
        kit_tracking_overrides=tracking.kit_tracking_overrides,
        runtime_tracking=tracking.runtime_tracking,
        agent_tracking=tracking.agent_tracking,
    )
    legacy_migration_rc = _maybe_run_init_legacy_migration(
        args=args,
        interactive=interactive,
        existing_install_rel=existing_install_rel,
        state=state,
    )
    if legacy_migration_rc is not None:
        return legacy_migration_rc, project_root, interactive, state
    _prompt_remaining_init_options(interactive, state)
    return None, project_root, interactive, state


def cmd_init(argv: List[str]) -> int:
    """Run the init command."""
    # @cpt-dod:cpt-studio-dod-core-infra-init-config:p1
    # @cpt-begin:cpt-studio-flow-core-infra-project-init:p1:inst-user-init
    args, tracking = _parse_init_args(argv)
    # @cpt-end:cpt-studio-flow-core-infra-project-init:p1:inst-kit-tracking-policy
    # @cpt-end:cpt-studio-flow-core-infra-project-init:p1:inst-user-init

    early_rc, project_root, interactive, state = _prepare_init_state(
        args=args,
        tracking=tracking,
    )
    if early_rc is not None:
        return early_rc

    studio_dir = (project_root / state.install_rel).resolve()
    declined_target_error = _validate_declined_legacy_target(state, studio_dir)
    if declined_target_error is not None:
        return declined_target_error

    # @cpt-begin:cpt-studio-flow-core-infra-project-init:p1:inst-prompt-agents
    # Stub: agent selection not yet needed (single kit); will prompt when multi-kit support lands
    # @cpt-end:cpt-studio-flow-core-infra-project-init:p1:inst-prompt-agents

    # Verify cache exists
    if not CACHE_DIR.is_dir():
        return _emit_missing_cache_error(project_root)

    run_state = _InitRunState()
    if state.legacy_migration_declined:
        run_state.actions["legacy_studio"] = "detected"
        run_state.actions["migration"] = "declined"
        run_state.actions["migration_decline_action"] = "side_by_side_init"

    # Create backup before --force overwrites
    if args.force and studio_dir.exists() and not args.dry_run:
        backup_path = create_backup(studio_dir)
        if backup_path:
            run_state.backups.append(backup_path.as_posix())

    # @cpt-begin:cpt-studio-flow-core-infra-project-init:p1:inst-copy-skill
    layout = _prepare_init_layout(studio_dir, args, run_state.actions)
    # @cpt-end:cpt-studio-flow-core-infra-project-init:p1:inst-copy-skill

    _write_init_core_toml(
        layout=layout,
        args=args,
        state=state,
        actions=run_state.actions,
    )

    # Write user-editable AGENTS.md to config/ (preserve existing)
    # @cpt-begin:cpt-studio-flow-core-infra-project-init:p1:inst-create-config-agents
    # @cpt-begin:cpt-studio-algo-core-infra-create-config-agents:p1:inst-gen-when-rules
    _ensure_init_config_agents(
        layout=layout,
        args=args,
        actions=run_state.actions,
    )
    # @cpt-end:cpt-studio-algo-core-infra-create-config-agents:p1:inst-return-config-agents-path
    # @cpt-end:cpt-studio-flow-core-infra-project-init:p1:inst-create-config-agents

    # @cpt-begin:cpt-studio-algo-core-infra-create-config:p1:inst-validate-schemas
    # Stub: schema validation deferred to p2
    # @cpt-end:cpt-studio-algo-core-infra-create-config:p1:inst-validate-schemas

    # @cpt-begin:cpt-studio-algo-core-infra-create-config:p1:inst-return-config-paths
    # (paths reported in final JSON output)
    # @cpt-end:cpt-studio-algo-core-infra-create-config:p1:inst-return-config-paths

    # @cpt-begin:cpt-studio-algo-core-infra-create-config:p1:inst-mkdir-kits
    # Kit installation via GitHub prompt (ADR-0013)
    kit_results, kit_rc = _maybe_install_default_kit_for_init(
        args=args,
        interactive=interactive,
        studio_dir=studio_dir,
        project_root=project_root,
        state=state,
        run_state=run_state,
    )
    if kit_rc is not None:
        return kit_rc
    _finalize_init_files(
        args=args,
        layout=layout,
        state=state,
        kit_results=kit_results,
        actions=run_state.actions,
    )
    # @cpt-end:cpt-studio-algo-core-infra-create-config:p1:inst-mkdir-kits

    # @cpt-begin:cpt-studio-flow-core-infra-project-init:p1:inst-delegate-agents
    # Stub: Agent Generator (Feature 5 boundary) — agent entry points generated separately
    # @cpt-end:cpt-studio-flow-core-infra-project-init:p1:inst-delegate-agents

    if run_state.errors:
        return _emit_init_error(
            project_root=project_root,
            studio_dir=studio_dir,
            dry_run=bool(args.dry_run),
            errors=run_state.errors,
            backups=run_state.backups,
        )

    # @cpt-begin:cpt-studio-flow-core-infra-project-init:p1:inst-return-init-ok
    # @cpt-begin:cpt-studio-state-core-infra-project-install:p1:inst-init-complete
    init_result = _build_init_result(
        args=args,
        project_root=project_root,
        studio_dir=studio_dir,
        layout=layout,
        state=state,
        actions=run_state.actions,
        backups=run_state.backups,
    )
    ui.result(
        init_result,
        human_fn=lambda d: _human_init_ok(
            d,
            project_root,
            studio_dir,
            state.install_rel,
            state.project_name,
            kit_results,
        ),
    )
    return 0
    # @cpt-end:cpt-studio-state-core-infra-project-install:p1:inst-init-complete
    # @cpt-end:cpt-studio-flow-core-infra-project-init:p1:inst-return-init-ok

# ---------------------------------------------------------------------------
# Human-friendly formatters
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-flow-core-infra-project-init:p1:inst-init-format-output
def _human_init_ok(
    data: Dict[str, object],
    project_root: Path,
    _studio_dir: Path,
    install_rel: str,
    project_name: str,
    kit_results: Dict[str, Any],
) -> None:
    dry = data.get("dry_run", False)
    prefix = "[dry-run] " if dry else ""

    ui.header(f"{prefix}Constructor Studio Init")
    ui.detail("Project", project_name)
    ui.detail("Root", project_root.as_posix())
    ui.detail("Constructor dir", f"{install_rel}/")
    ui.detail("Runtime tracking", str(data.get("runtime_tracking", "ignored")))
    ui.detail("Agent tracking", str(data.get("agent_tracking", "ignored")))
    kit_tracking = data.get("kit_tracking")
    if isinstance(kit_tracking, dict):
        ui.detail("Default kit tracking", str(kit_tracking.get("default", "tracked")))
    ui.blank()

    ui.step("Core files copied to .core/")
    ui.step("Config created in config/")
    ui.substep("core.toml      — project settings")
    ui.substep("artifacts.toml — artifact registry")
    ui.substep("AGENTS.md      — custom agent rules (edit freely)")
    ui.substep("SKILL.md       — custom skill extensions (edit freely)")

    if kit_results:
        ui.step("Kits installed:")
        for slug, kr in kit_results.items():
            n = kr.get("files_written", 0)
            kinds = kr.get("artifact_kinds", [])
            tracking = kr.get("tracking")
            suffix = f"; git tracking: {tracking}" if tracking else ""
            ui.substep(f"{slug}: {n} files generated ({', '.join(kinds)}){suffix}")

    ui.step("AGENTS.md navigation block injected into project root")

    if dry:
        ui.success("Dry run complete — no files were written.")
    else:
        ui.success("Constructor Studio initialized!")
        ui.blank()
        ui.info("Next steps:")
        ui.hint("1. Set up your IDE:  cfs generate-agents")
        ui.hint("2. Review config:    open " + install_rel + "/config/core.toml")
        ui.hint("3. Start using:      type '/cf' in your IDE chat")
    ui.blank()

def _human_init_error(data: Dict[str, object]) -> None:
    ui.error("Initialization failed")
    _render_error_entries(data.get("errors", []))
    ui.blank()
# @cpt-end:cpt-studio-flow-core-infra-project-init:p1:inst-init-format-output
