"""
Delegate Command — ralphex delegation from a Studio plan.

Compiles a Studio plan into ralphex-compatible format, resolves the
ralphex executable, and orchestrates the delegation flow. Respects
the bootstrap gate: missing ``.ralphex/config`` is a blocking error
(exit code 2) with opt-in guidance.

@cpt-flow:cpt-studio-flow-ralphex-delegation-execute:p1
@cpt-dod:cpt-studio-dod-ralphex-delegation-modes:p1
"""

import argparse
import logging
from pathlib import Path
from typing import List

from ..utils.ui import ui, is_json_mode, set_json_mode

logger = logging.getLogger(__name__)


def _build_delegate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="delegate",
        description="Compile a Studio plan and delegate to ralphex",
    )
    parser.add_argument(
        "plan_dir",
        help="Path to the Studio plan directory containing plan.toml",
    )
    parser.add_argument(
        "--mode",
        choices=["execute", "tasks-only", "review"],
        default="execute",
        help="Delegation mode (default: execute)",
    )
    parser.add_argument(
        "--worktree",
        action="store_true",
        help="Request worktree isolation (execute and tasks-only only)",
    )
    serve_group = parser.add_mutually_exclusive_group()
    serve_group.add_argument(
        "--serve",
        dest="serve",
        action="store_true",
        help="Request dashboard serving (default)",
    )
    serve_group.add_argument(
        "--no-serve",
        dest="serve",
        action="store_false",
        help="Disable dashboard serving",
    )
    parser.set_defaults(serve=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Assemble the command without invoking ralphex",
    )
    parser.add_argument(
        "--default-branch",
        default="main",
        help="Default branch for review precondition (default: main)",
    )
    parser.add_argument(
        "--plans-dir",
        default=None,
        help="Override plans directory (highest precedence)",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Project root (default: current directory)",
    )
    return parser


def _emit_delegate_error(message: str) -> int:
    ui.result(
        {"status": "error", "error": message},
        human_fn=lambda data: ui.error(data["error"]),
    )
    return 1


def _resolve_delegate_paths(args) -> tuple[Path, Path] | None:
    project_root = Path(args.root).resolve()
    if not project_root.is_dir():
        _emit_delegate_error(f"Project root not found or not a directory: {project_root}")
        return None
    raw_plan_dir = Path(args.plan_dir)
    plan_dir = raw_plan_dir.resolve() if raw_plan_dir.is_absolute() else (project_root / raw_plan_dir).resolve()
    if not plan_dir.is_dir():
        _emit_delegate_error(f"Plan directory not found: {plan_dir}")
        return None
    if not (plan_dir / "plan.toml").is_file():
        _emit_delegate_error(f"plan.toml not found in {plan_dir}")
        return None
    return project_root, plan_dir


def _run_delegate(args, project_root: Path, plan_dir: Path, json_was_enabled: bool) -> dict:
    from ._core_config import find_core_toml, load_core_config
    from ..ralphex_export import run_delegation

    config = load_core_config(project_root)
    config_path = find_core_toml(project_root)
    if json_was_enabled:
        set_json_mode(False)
    return run_delegation(
        config=config,
        plan_dir=str(plan_dir),
        repo_root=str(project_root),
        mode=args.mode,
        worktree=args.worktree,
        serve=args.serve,
        default_branch=args.default_branch,
        config_path=config_path,
        dry_run=args.dry_run,
        plans_dir_override=args.plans_dir,
        stream_output=not json_was_enabled,
    )


# @cpt-begin:cpt-studio-flow-ralphex-delegation-execute:p1:inst-invoke-execute
def cmd_delegate(argv: List[str]) -> int:
    """Run ralphex delegation from a Studio plan."""
    json_was_enabled = is_json_mode()
    try:
        args = _build_delegate_parser().parse_args(argv)
        resolved = _resolve_delegate_paths(args)
        if resolved is None:
            return 1
        project_root, plan_dir = resolved
        result = _run_delegate(args, project_root, plan_dir, json_was_enabled)

        if json_was_enabled:
            set_json_mode(True)

        bootstrap = result.get("bootstrap")
        if bootstrap and bootstrap.get("needed"):
            ui.step("[WARN] " + bootstrap["message"])

        exit_code = _result_to_exit_code(result)

        ui.result(
            result,
            human_fn=_print_human,
        )

        return exit_code
    finally:
        if json_was_enabled:
            set_json_mode(True)
# @cpt-end:cpt-studio-flow-ralphex-delegation-execute:p1:inst-invoke-execute


# @cpt-begin:cpt-studio-dod-ralphex-delegation-modes:p1:inst-determine-mode
def _result_to_exit_code(result: dict) -> int:
    """Map delegation result status to CLI exit code."""
    status = result.get("status", "error")
    if status in ("ready", "delegated"):
        return 0
    # error status
    return 2


def _print_human(result: dict) -> None:
    """Print human-readable delegation result."""
    status = result.get("status", "error")
    dashboard_url = result.get("dashboard_url")

    if status == "error":
        ui.error(f"Delegation failed: {result.get('error', 'unknown error')}")
        return

    if status == "ready":
        ui.step("[DRY RUN] Command assembled (not invoked):")
        command = result.get("command", [])
        if command:
            ui.info(f"  {' '.join(command)}")
        plan_file = result.get("plan_file")
        if plan_file:
            ui.info(f"  Exported plan: {plan_file}")
        if dashboard_url:
            ui.info(f"  Dashboard: {dashboard_url}")
        ui.info(f"  Lifecycle: {result.get('lifecycle_state', 'unknown')}")
        return

    if status == "delegated":
        lifecycle = result.get("lifecycle_state", "unknown")
        header = "Delegation completed:" if lifecycle == "completed" else "Delegation started:"
        ui.step(header)
        command = result.get("command", [])
        if command:
            ui.info(f"  {' '.join(command)}")
        ui.info(f"  Mode: {result.get('mode', 'unknown')}")
        if dashboard_url:
            ui.info(f"  Dashboard: {dashboard_url}")
        ui.info(f"  Lifecycle: {result.get('lifecycle_state', 'unknown')}")
# @cpt-end:cpt-studio-dod-ralphex-delegation-modes:p1:inst-determine-mode
