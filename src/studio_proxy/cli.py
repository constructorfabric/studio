"""
Constructor Studio Global CLI Proxy — Main Entry Point

Thin proxy that resolves skill target (project or cache) and forwards commands.
All actual logic lives in the skill engine — this proxy only routes.

@cpt-flow:cpt-studio-flow-core-infra-cli-invocation:p1
@cpt-algo:cpt-studio-algo-core-infra-route-command:p1
@cpt-dod:cpt-studio-dod-core-infra-cli-routes:p1
@cpt-dod:cpt-studio-dod-core-infra-global-package:p1
@cpt-state:cpt-studio-state-core-infra-project-install:p1
"""

# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-imports
import os
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from studio_proxy.stderr import write_stderr, write_stderr_lines

from studio_proxy.resolve import (
    find_cached_skill,
    find_project_skill,
    get_cache_provenance,
    get_cached_version,
    get_project_pinned_cache_request,
    get_project_provenance,
    get_project_version,
    resolve_skill,
)
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-imports


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-configure-logging
def _configure_proxy_logging() -> None:
    """Ensure proxy diagnostics are emitted to stderr in unmanaged environments."""
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return
    logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stderr)
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-configure-logging


def _extract_version_param(args: List[str]) -> Optional[str]:
    """
    Extract and remove --version VERSION from args list.

    Supports: --version VALUE, --version=VALUE
    Mutates args in place, returns the version string or None.
    """
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-extract-version-param
    i = 0
    while i < len(args):
        if args[i] == "--version" and i + 1 < len(args):
            value = args[i + 1]
            del args[i:i + 2]
            return value
        if args[i].startswith("--version="):
            value = args[i].split("=", 1)[1]
            del args[i]
            return value
        i += 1
    return None
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-extract-version-param


def _extract_named_param(args: List[str], name: str) -> Optional[str]:
    """
    Extract and remove a named parameter from args list.

    Supports: NAME VALUE, NAME=VALUE
    Mutates args in place, returns the value string or None.
    """
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-extract-named-param
    i = 0
    while i < len(args):
        if args[i] == name and i + 1 < len(args):
            value = args[i + 1]
            del args[i:i + 2]
            return value
        if args[i].startswith(f"{name}="):
            value = args[i].split("=", 1)[1]
            del args[i]
            return value
        i += 1
    return None
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-extract-named-param


def _peek_named_param(args: List[str], name: str) -> Optional[str]:
    """Read a named parameter without mutating the forwarded args."""
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-peek-named-param
    i = 0
    while i < len(args):
        if args[i] == name and i + 1 < len(args):
            return args[i + 1]
        if args[i].startswith(f"{name}="):
            return args[i].split("=", 1)[1]
        i += 1
    return None
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-peek-named-param


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-routing-datamodel
@dataclass
class _ProxyCommandOptions:
    target_version: Optional[str] = None
    force_update: bool = False
    skip_cache: bool = False
    source_dir: Optional[str] = None
    custom_url: Optional[str] = None


@dataclass(frozen=True)
class _ResolvedSkillTarget:
    path: Path
    source: str
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-routing-datamodel


def _mirror_override(args: List[str], set_override: Any) -> int:
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-proxy-helpers
    if len(args) < 3:
        write_stderr("Usage: cfs mirror override <old-url> <new-url>")
        return 1
    old_url, new_url = args[1], args[2]
    path = set_override(old_url, new_url)
    print(f"Registered: {old_url} -> {new_url}  (wrote: {path})")
    return 0
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-proxy-helpers


def _mirror_list(list_overrides: Any) -> int:
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-proxy-helpers
    entries = list_overrides()
    if not entries:
        print("(no overrides)")
        return 0
    for from_url, to_url, source_path in entries:
        print(f"{from_url}  ->  {to_url}      [{source_path}]")
    return 0
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-proxy-helpers


def _mirror_sources(mirror_sources: Any) -> int:
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-proxy-helpers
    sources = mirror_sources()
    any_changed = False
    for name, original, effective in sources:
        marker = "  " if original == effective else "* "
        if original != effective:
            any_changed = True
            print(f"{marker}{name:32}  {original}")
            print(f"  {'':32}  -> {effective}")
        else:
            print(f"{marker}{name:32}  {original}")
    print("")
    print("Substring overrides also affect any URL containing a registered `from` token.")
    if any_changed:
        print("Lines marked `*` are currently rewritten by active overrides.")
    return 0
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-proxy-helpers


def _mirror_remove(args: List[str], remove_override: Any) -> int:
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-proxy-helpers
    if len(args) < 2:
        write_stderr("Usage: cfs mirror remove <old-url>")
        return 1
    old_url = args[1]
    if remove_override(old_url):
        print(f"Removed: {old_url}")
        return 0
    write_stderr(f"Not found: {old_url}")
    return 1
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-proxy-helpers


def _confirm_mirror_clear(args: List[str]) -> bool:
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-proxy-helpers
    if "--yes" in args or "-y" in args:
        return True
    if not sys.stdin.isatty():
        write_stderr("Pass --yes to confirm clearing all overrides in non-interactive mode.")
        return False
    try:
        answer = input("Clear all mirror overrides? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"
    if answer in ("y", "yes"):
        return True
    write_stderr("Aborted.")
    return False
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-proxy-helpers


def _mirror_clear(args: List[str], clear_overrides: Any) -> int:
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-proxy-helpers
    if not _confirm_mirror_clear(args):
        return 1
    count = clear_overrides()
    print(f"Cleared {count} override(s).")
    return 0
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-proxy-helpers


def _print_mirror_help() -> int:
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-proxy-helpers
    print("Usage: cfs mirror <subcommand> [args]")
    print("")
    print("Subcommands:")
    print("  override <from> <to>           Register or update a URL override (substring replacement)")
    print("  list                           Print current overrides")
    print("  sources                        List default URLs that can be mirrored (with current effective form)")
    print("  remove <from>                  Delete an override")
    print("  clear [--yes]                  Delete all overrides")
    print("")
    print("Match semantics: `from` is replaced wherever it occurs in any URL the proxy or")
    print("skill engine resolves. Examples:")
    print("  cfs mirror override github.com/constructorfabric/studio github.com/ainetx/studio")
    print("  cfs mirror override constructorfabric ainetx   # rewrites all constructorfabric/* URLs")
    return 0
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-proxy-helpers

def _handle_mirror(args: List[str]) -> int:
    """
    Handle the 'mirror' subcommand family.

    Dispatches to: override, list, remove, clear.
    Pure proxy-local — never touches cache or skill engine.
    """
    from studio_proxy.mirrors import (
        set_override,
        list_overrides,
        remove_override,
        clear_overrides,
        mirror_sources,
    )

    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-mirror-dispatch
    sub = args[0] if args else None
    handlers = {
        "override": lambda: _mirror_override(args, set_override),
        "list": lambda: _mirror_list(list_overrides),
        "sources": lambda: _mirror_sources(mirror_sources),
        "remove": lambda: _mirror_remove(args, remove_override),
        "clear": lambda: _mirror_clear(args, clear_overrides),
    }
    return handlers.get(sub, _print_mirror_help)()
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-mirror-dispatch


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-bg-version-check
def _handle_check_updates(args: List[str]) -> int:
    """Run a foreground full update check for proxy, skill engine, and kits."""
    import argparse
    import json
    from studio_proxy.update_check import run_update_check

    parser = argparse.ArgumentParser(
        prog="cfs check-updates",
        description="Check constructor-studio proxy, skill engine, and installed kits for updates",
    )
    parser.add_argument("--project-root", default="")
    parser.add_argument("--json", action="store_true")
    parsed = parser.parse_args(args)

    skill_path, _source = resolve_skill()
    data = run_update_check(
        skill_path=skill_path,
        project_root=parsed.project_root,
        include_kits=True,
        write_cache=True,
    )
    if parsed.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0
    _print_update_check_human(data)
    return 0
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-bg-version-check


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-show-update-notice
def _print_update_check_human(data: Dict[str, Any]) -> None:
    print("Constructor Studio Update Check")
    print(f"Updates available: {data.get('updates_available', 0)}")
    checks = data.get("checks", {})
    for name in ("proxy", "skill_engine", "kits"):
        check = checks.get(name, {})
        if not isinstance(check, dict):
            continue
        action = check.get("action", "unknown")
        component = check.get("component", name)
        if action == "update_available":
            print(f"- {component}: update available")
            current = check.get("current_version", "")
            latest = check.get("latest_version", "")
            if current or latest:
                print(f"  installed: {current or '?'}")
                if latest:
                    print(f"  latest:    {latest}")
            command = check.get("command")
            if command:
                print(f"  run: {command}")
            for command in check.get("commands", []) or []:
                print(f"  run: {command}")
        elif action == "current":
            print(f"- {component}: up to date")
        else:
            print(f"- {component}: unknown ({check.get('message', 'check failed')})")
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-show-update-notice


# @cpt-begin:cpt-studio-dod-core-infra-cli-routes:p1:inst-print-version-provenance
def _print_version_provenance(provenance: Optional[Dict[str, Any]], default_unknown: bool = False) -> None:
    if not provenance:
        if default_unknown:
            print("  verified: unknown")
        return
    source_type = provenance.get("source_type")
    effective_source = provenance.get("effective_source")
    resolved_ref = provenance.get("resolved_ref")
    verified = provenance.get("verified")
    if source_type:
        print(f"  source: {source_type}")
    if effective_source:
        print(f"  effective source: {effective_source}")
    if resolved_ref:
        print(f"  resolved ref: {resolved_ref}")
    if verified:
        print(f"  verified: {verified}")
# @cpt-end:cpt-studio-dod-core-infra-cli-routes:p1:inst-print-version-provenance


# @cpt-begin:cpt-studio-dod-core-infra-global-package:p1:inst-report-installed-versions
def _handle_version_info(args: List[str]) -> Optional[int]:
    if not (args and args[0] == "--version" and len(args) == 1):
        return None
    from studio_proxy import __version__

    print(f"package: constructor-studio {__version__}")
    cached = get_cached_version()
    if cached:
        print(f"skill cache: {cached}")
        _print_version_provenance(get_cache_provenance())
    project_skill = find_project_skill()
    if project_skill:
        project_version = get_project_version(project_skill)
        if project_version:
            print(f"skill project: {project_version}")
            print(f"  path: {project_skill}")
            _print_version_provenance(get_project_provenance(project_skill), default_unknown=True)
    return 0
# @cpt-end:cpt-studio-dod-core-infra-global-package:p1:inst-report-installed-versions


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-extract-proxy-options
def _extract_proxy_command_options(args: List[str]) -> _ProxyCommandOptions:
    options = _ProxyCommandOptions()
    if not (args and args[0] in ("init", "update")):
        return options
    options.target_version = _extract_version_param(args)
    options.source_dir = _extract_named_param(args, "--source")
    options.custom_url = _extract_named_param(args, "--url")
    if (
        args[0] == "init"
        and options.target_version is None
        and options.source_dir is None
        and options.custom_url is None
    ):
        project_root = _peek_named_param(args, "--project-root")
        pinned_request = get_project_pinned_cache_request(Path(project_root) if project_root else None)
        if pinned_request is not None:
            options.target_version, options.custom_url = pinned_request
    if "--force" in args:
        options.force_update = True
        args.remove("--force")
    if "--no-cache" in args:
        options.skip_cache = True
        args.remove("--no-cache")
    return options
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-extract-proxy-options


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-explicit-cache-update
def _run_cache_update(
    source_dir: Optional[str],
    target_version: Optional[str],
    force_update: bool,
    custom_url: Optional[str],
    args: List[str],
) -> tuple[bool, str]:
    if source_dir is not None:
        from studio_proxy.cache import copy_from_local

        return copy_from_local(source_dir=source_dir, force=force_update)
    from studio_proxy.cache import download_and_cache

    explicit = target_version
    if explicit is None and len(args) > 1 and not args[1].startswith("-"):
        explicit = args[1]
    return download_and_cache(version=explicit, force=force_update, url=custom_url)
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-explicit-cache-update


def _handle_update_command(args: List[str], options: _ProxyCommandOptions) -> Optional[int]:
    if not (args and args[0] == "update"):
        return None
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-if-update-cache
    if not options.skip_cache and "--help" not in args and "-h" not in args:
        success, message = _run_cache_update(
            options.source_dir,
            options.target_version,
            options.force_update,
            options.custom_url,
            args,
        )
        write_stderr(message)
        if not success:
            return 1
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-if-update-cache
    skill_path = find_cached_skill()
    if skill_path is None:
        write_stderr("Cache not found. Run 'cfs update' without --no-cache first.")
        return 1
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-return-cache-update
    write_stderr("Updating project...")
    forwarded_args = list(args)
    if options.target_version is None and len(args) > 1 and not args[1].startswith("-"):
        forwarded_args = ["update"] + args[2:]
    return _forward_to_skill(skill_path, forwarded_args)
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-return-cache-update


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-auto-download
def _maybe_prepare_init_cache(args: List[str], options: _ProxyCommandOptions) -> Optional[int]:
    if options.force_update and args and args[0] == "init":
        args.append("--force")
    should_prepare = (
        args and args[0] == "init"
        and not options.skip_cache
        and "--help" not in args and "-h" not in args
    )
    if not should_prepare:
        return None
    if options.source_dir is not None:
        from studio_proxy.cache import copy_from_local

        write_stderr("Updating cache from local source...")
        success, message = copy_from_local(source_dir=options.source_dir, force=options.force_update)
    else:
        from studio_proxy.cache import download_and_cache

        if options.target_version:
            write_stderr(f"Updating cache to version {options.target_version}...")
        else:
            write_stderr("Updating cache to latest version...")
        success, message = download_and_cache(
            version=options.target_version,
            force=options.force_update,
            url=options.custom_url,
        )
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-if-download-failed
    write_stderr(message)
    if not success:
        return 1
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-if-download-failed
    return None
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-auto-download


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-check-project-skill
def _resolve_skill_for_command(args: List[str], skip_cache: bool) -> Optional[_ResolvedSkillTarget]:
    use_cache_for_init = (
        args and args[0] == "init"
        and not skip_cache
        and "--help" not in args and "-h" not in args
    )
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-check-project-skill
    if use_cache_for_init:
        # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-check-cache
        cached_skill = find_cached_skill()
        cache_missing = cached_skill is None
        # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-check-cache
        # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-if-cache
        if not cache_missing:
            return _ResolvedSkillTarget(cached_skill, "cache")
        # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-if-cache
        return None

    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-if-project-skill
    resolved_skill, resolved_source = resolve_skill()
    if resolved_skill is not None and resolved_source in ("project", "cache"):
        return _ResolvedSkillTarget(resolved_skill, resolved_source)
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-if-project-skill

    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-else-no-project
    return None
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-else-no-project


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-auto-download
def _ensure_skill_available(skill_path: Optional[Path]) -> Optional[Path]:
    if skill_path is not None:
        return skill_path
    from studio_proxy.cache import download_and_cache

    write_stderr_lines(
        "",
        "  Constructor Studio skill engine not found.",
        "",
        "  Constructor Studio is a two-part tool:",
        "    • This CLI proxy (already installed)",
        "    • The skill engine (templates, validators, generators)",
        "",
        "  The skill engine needs to be downloaded once from GitHub",
        "  and cached at ~/.cf-studio/cache/.",
        "",
    )

    if sys.stdin.isatty():
        try:
            answer = input("  Download now? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer and answer not in ("y", "yes"):
            write_stderr_lines("", "  To download later, run: cfs update", "")
            return None
    else:
        write_stderr("  Downloading automatically (non-interactive mode)...")

    write_stderr("")
    success, message = download_and_cache()
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-if-download-failed
    if not success:
        # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-return-download-error
        write_stderr_lines(f"  Error: {message}", "  Retry: cfs update", "")
        return None
        # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-return-download-error
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-if-download-failed
    write_stderr_lines(f"  {message}", "")
    return find_cached_skill()
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-auto-download


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-else-no-project
def _resolve_invocation_target(
    args: List[str],
    skip_cache: bool,
) -> Optional[_ResolvedSkillTarget]:
    resolved = _resolve_skill_for_command(args, skip_cache)
    if resolved is not None:
        return resolved
    skill_path = _ensure_skill_available(None)
    if skill_path is None:
        return None
    target = _ResolvedSkillTarget(skill_path, "fresh-cache")
    return target
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-else-no-project


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-early-proxy-command
def _handle_proxy_command(args: List[str]) -> tuple[Optional[int], _ProxyCommandOptions]:
    version_result = _handle_version_info(args)
    if version_result is not None:
        return version_result, _ProxyCommandOptions()
    options = _extract_proxy_command_options(args)
    update_result = _handle_update_command(args, options)
    if update_result is not None:
        return update_result, options
    init_result = _maybe_prepare_init_cache(args, options)
    if init_result is not None:
        return init_result, options
    return None, options
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-early-proxy-command


def main(argv: Optional[List[str]] = None) -> int:
    """
    Main entry point for the cfs / constructor-studio command.
    """
    _configure_proxy_logging()
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-user-invokes
    args = argv if argv is not None else sys.argv[1:]
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-user-invokes

    # Mirror subcommand — pure proxy-local, never triggers skill engine or cache download
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-mirror-dispatch
    if args and args[0] == "mirror":
        return _handle_mirror(args[1:])
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-mirror-dispatch

    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-telemetry
    from studio_proxy.telemetry import track_invocation
    track_invocation(args)
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-telemetry

    if args and args[0] == "check-updates":
        return _handle_check_updates(args[1:])

    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-early-proxy-command
    early_result, options = _handle_proxy_command(args)
    if early_result is not None:
        return early_result
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-early-proxy-command

    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-else-no-cache
    target = _resolve_invocation_target(args, options.skip_cache)
    if target is None:
        return 1
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-else-no-cache

    if target.source == "fresh-cache":
        # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-forward-fresh-cache
        skill_path = target.path
        forwarded_args = list(args)
        result = _forward_to_skill(skill_path, forwarded_args)
        # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-forward-fresh-cache
    elif target.source == "project":
        # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-forward-project
        skill_path = target.path
        forwarded_args = list(args)
        result = _forward_to_skill(skill_path, forwarded_args)
        # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-forward-project
    else:
        # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-forward-cache
        skill_path = target.path
        forwarded_args = list(args)
        result = _forward_to_skill(skill_path, forwarded_args)
        # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-forward-cache

    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-bg-version-check
    if not os.environ.get("CFS_NO_VERSION_CHECK"):
        _background_version_check(target.path, args)
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-bg-version-check

    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-return-exit
    return result
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-return-exit

# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-forward-subprocess
def _forward_to_skill(skill_path: Path, args: List[str]) -> int:
    """
    Forward command to the resolved skill engine via subprocess.

    Uses the same Python interpreter that's running this proxy.
    """
    cmd = [sys.executable, str(skill_path)] + args

    try:
        # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-engine-execute
        proc = subprocess.run(
            cmd,
            stdin=sys.stdin,
            stdout=sys.stdout,
            check=False,
        )
        return proc.returncode
        # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-engine-execute
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-forward-subprocess-errors
    except FileNotFoundError:
        write_stderr(f"Error: Skill entry point not found: {skill_path}")
        return 1
    except OSError as exc:
        write_stderr(f"Error: Failed to execute skill: {exc}")
        return 1
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-forward-subprocess-errors
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-forward-subprocess

# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-bg-version-check
def _background_version_check(project_skill_path: Path, args: Optional[List[str]] = None) -> None:
    """
    Non-blocking background version check.

    Prints cached update notices, then refreshes the cache in a detached
    subprocess. The foreground cfs command never waits for network I/O.

    """
    args = args or []
    if "--json" in args:
        return
    try:
        # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-bg-check-cache
        from studio_proxy.update_check import read_cached_update_check, should_refresh
        cached = read_cached_update_check()
        # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-bg-check-cache
        _print_cached_update_notices(cached)
        # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-bg-check-refresh
        if should_refresh(cached):
            _spawn_update_check_worker(project_skill_path, args)
        # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-bg-check-refresh
    except (OSError, ValueError) as exc:
        write_stderr(f"Warning: background update check unavailable: {exc}")
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-bg-version-check


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-show-update-notice
def _print_cached_update_notices(cached: Optional[Dict[str, Any]]) -> None:
    # @cpt-begin:cpt-studio-state-core-infra-project-install:p1:inst-version-mismatch
    if not cached or not cached.get("updates_available"):
        return
    checks = cached.get("checks", {})
    if not isinstance(checks, dict):
        return
    proxy = checks.get("proxy", {})
    if isinstance(proxy, dict) and proxy.get("action") == "update_available":
        write_stderr(
            "cfs: constructor-studio proxy update available "
            f"({proxy.get('current_version', '?')} -> {proxy.get('latest_version', '?')}). "
            "Run: pipx upgrade constructor-studio"
        )
    skill = checks.get("skill_engine", {})
    if isinstance(skill, dict) and skill.get("action") == "update_available":
        write_stderr(
            "cfs: skill engine update available "
            f"({skill.get('current_version', '?')} -> {skill.get('latest_version', '?')}). "
            "Run: cfs update"
        )
    kits = checks.get("kits", {})
    if isinstance(kits, dict) and kits.get("updates_available"):
        commands = kits.get("commands") or []
        command_hint = ", ".join(str(command) for command in commands[:3])
        if not command_hint:
            command_hint = "cfs kit update"
        write_stderr(
            f"cfs: {kits.get('updates_available')} kit update(s) available. Run: {command_hint}"
        )
    # @cpt-end:cpt-studio-state-core-infra-project-install:p1:inst-version-mismatch
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-show-update-notice


def _spawn_update_check_worker(project_skill_path: Path, args: List[str]) -> None:
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-spawn-update-worker
    project_root = _peek_named_param(args, "--project-root") or ""
    cmd = [
        sys.executable,
        "-m",
        "studio_proxy.update_check",
        "--skill-path",
        str(project_skill_path),
        "--write-cache",
    ]
    if project_root:
        cmd.extend(["--project-root", project_root])
    try:
        with open(os.devnull, "w", encoding="utf-8") as devnull:
            subprocess.Popen(  # pylint: disable=consider-using-with  # detached advisory worker
                cmd,
                stdin=devnull,
                stdout=devnull,
                stderr=devnull,
                close_fds=True,
            )
    except OSError as exc:
        write_stderr(f"Warning: unable to start update-check worker: {exc}")
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-spawn-update-worker


# @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-normalize-version
def _normalize_version_for_compare(version: str) -> str:
    """Normalize local cache display versions for project/cache equality checks."""
    if version.startswith("local:"):
        return version.removeprefix("local:")
    return version
# @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-normalize-version
