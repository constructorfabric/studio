"""
Studio Validator - CLI Entry Point

Command-line interface for the Studio validation tool.

IMPORTANT: This module MUST NOT contain business logic.

- The CLI is responsible only for argv parsing and command dispatch.
- All validation, scanning, and transformation logic MUST live in dedicated
  modules under studio.utils or command modules.
"""

# @cpt-algo:cpt-studio-algo-core-infra-route-command:p1
import sys
import logging
from pathlib import Path
from typing import Callable, List, Optional

_CLI_STDERR_HANDLER_NAME = "studio-cli-stderr"


# @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-route-helpers
def _configure_studio_logging() -> None:
    """Route studio diagnostics to stderr with a stable handler."""
    studio_logger = logging.getLogger("studio")
    managed_handlers = [
        handler
        for handler in studio_logger.handlers
        if getattr(handler, "name", "") == _CLI_STDERR_HANDLER_NAME
    ]
    for handler in managed_handlers:
        studio_logger.removeHandler(handler)
        handler.close()
    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(_CLI_STDERR_HANDLER_NAME)
    handler.setFormatter(logging.Formatter("%(message)s"))
    studio_logger.addHandler(handler)
    studio_logger.setLevel(logging.WARNING)
    studio_logger.propagate = False


def _cmd_agents(argv: List[str]) -> int:
    from .commands.agents import cmd_agents
    return cmd_agents(argv)

def _cmd_generate_agents(argv: List[str]) -> int:
    from .commands.agents import cmd_generate_agents
    return cmd_generate_agents(argv)

def _cmd_init(argv: List[str]) -> int:
    from .commands.init import cmd_init
    return cmd_init(argv)

def _cmd_update(argv: List[str]) -> int:
    from .commands.update import cmd_update
    return cmd_update(argv)

# =============================================================================
def _cmd_validate(argv: List[str]) -> int:
    from .commands.validate import cmd_validate
    return cmd_validate(argv)

# =============================================================================
# SEARCH COMMANDS
# =============================================================================

def _cmd_list_ids(argv: List[str]) -> int:
    from .commands.list_ids import cmd_list_ids
    return cmd_list_ids(argv)

def _cmd_list_id_kinds(argv: List[str]) -> int:
    from .commands.list_id_kinds import cmd_list_id_kinds
    return cmd_list_id_kinds(argv)

def _cmd_get_content(argv: List[str]) -> int:
    from .commands.get_content import cmd_get_content
    return cmd_get_content(argv)

def _cmd_where_defined(argv: List[str]) -> int:
    from .commands.where_defined import cmd_where_defined
    return cmd_where_defined(argv)

def _cmd_where_used(argv: List[str]) -> int:
    from .commands.where_used import cmd_where_used
    return cmd_where_used(argv)

# =============================================================================
# KIT VALIDATION COMMAND
# =============================================================================

def _cmd_validate_kits(argv: List[str]) -> int:
    from .commands.validate_kits import cmd_validate_kits
    return cmd_validate_kits(argv)

# =============================================================================
# KIT MANAGEMENT COMMANDS
# =============================================================================

def _cmd_kit(argv: List[str]) -> int:
    from .commands.kit import cmd_kit
    return cmd_kit(argv)

def _cmd_generate_resources(_argv: List[str]) -> int:
    from .utils.ui import ui

    ui.warn("'generate-resources' is deprecated.")
    ui.hint("Kits are direct file packages; use 'cfs kit update <path>' instead.")
    return 1

# =============================================================================
# TOC COMMANDS
# =============================================================================

def _cmd_toc(argv: List[str]) -> int:
    from .commands.toc import cmd_toc
    return cmd_toc(argv)

def _cmd_validate_toc(argv: List[str]) -> int:
    from .commands.validate_toc import cmd_validate_toc
    return cmd_validate_toc(argv)

def _cmd_spec_coverage(argv: List[str]) -> int:
    from .commands.spec_coverage import cmd_spec_coverage
    return cmd_spec_coverage(argv)

def _cmd_chunk_input(argv: List[str]) -> int:
    from .commands.chunk_input import cmd_chunk_input
    return cmd_chunk_input(argv)

# =============================================================================
# ADAPTER COMMAND
# =============================================================================

def _cmd_studio_info(argv: List[str]) -> int:
    from .commands.adapter_info import cmd_adapter_info
    return cmd_adapter_info(argv)

def _cmd_resolve_vars(argv: List[str]) -> int:
    from .commands.resolve_vars import cmd_resolve_vars
    return cmd_resolve_vars(argv)

# =============================================================================
# WORKSPACE COMMANDS
# =============================================================================

def _cmd_workspace_init(argv: List[str]) -> int:
    from .commands.workspace_init import cmd_workspace_init
    return cmd_workspace_init(argv)

def _cmd_workspace_add(argv: List[str]) -> int:
    from .commands.workspace_add import cmd_workspace_add
    return cmd_workspace_add(argv)

def _cmd_workspace_info(argv: List[str]) -> int:
    from .commands.workspace_info import cmd_workspace_info
    return cmd_workspace_info(argv)

def _cmd_workspace_sync(argv: List[str]) -> int:
    from .commands.workspace_sync import cmd_workspace_sync
    return cmd_workspace_sync(argv)

# =============================================================================
# DIAGNOSTICS COMMANDS
# =============================================================================

def _cmd_doctor(argv: List[str]) -> int:
    from .commands.doctor import cmd_doctor
    return cmd_doctor(argv)

def _cmd_delegate(argv: List[str]) -> int:
    from .commands.delegate import cmd_delegate
    return cmd_delegate(argv)

def _cmd_check_language(argv: List[str]) -> int:
    from .commands.check_language import cmd_check_language
    return cmd_check_language(argv)

def _cmd_pdsl(argv: List[str]) -> int:
    from .commands.pdsl import cmd_pdsl
    return cmd_pdsl(argv)

# =============================================================================
# VISUALIZATION COMMANDS
# =============================================================================

def _cmd_map(argv: List[str]) -> int:
    from .commands.map.cli import cmd_map
    return cmd_map(argv)

CommandHandler = Callable[[List[str]], int]

_COMMAND_DESCRIPTIONS = {
    "validate": "Validate artifacts and code traceability",
    "validate-kits": "Validate kit structure, templates, and examples",
    "validate-toc": "Validate Table of Contents in Markdown files",
    "spec-coverage": "Measure CDSL marker coverage in code",
    "check-language": "Check artifacts for disallowed Unicode scripts (LANG001)",
    "kit": "Kit management (install, update)",
    "init": "Initialize Constructor Studio in a project",
    "update": "Update Constructor Studio to the latest version",
    "agents": "Show generated agent integration status",
    "generate-agents": "Generate/update IDE agent integration files",
    "list-ids": "List all artifact IDs",
    "list-id-kinds": "List ID kinds with counts",
    "get-content": "Get content block for an ID",
    "where-defined": "Find where an ID is defined",
    "where-used": "Find all references to an ID",
    "info": "Show project configuration",
    "resolve-vars": "Resolve template variables to absolute paths",
    "toc": "Generate/update Table of Contents",
    "chunk-input": "Chunk oversized workflow input into line-bounded Markdown files",
    "pdsl": "Validate PDSL prompt blocks",
    "workspace-init": "Initialize multi-repo workspace",
    "workspace-add": "Add a source to workspace config",
    "workspace-info": "Show workspace config and source status",
    "workspace-sync": "Fetch and update Git URL source worktrees",
    "delegate": "Compile and delegate a plan to ralphex",
    "doctor": "Run environment health checks",
    "map": "Build interactive markdown↔source dependency map via cpt identifiers",
}

_COMMAND_SECTIONS = [
    ("Setup & Configuration", ["init", "update", "info", "resolve-vars", "generate-agents", "agents"]),
    ("Validation", ["validate", "validate-kits", "validate-toc", "spec-coverage", "check-language"]),
    ("Search & Navigation", ["list-ids", "list-id-kinds", "get-content", "where-defined", "where-used"]),
    ("Kit Management", ["kit"]),
    ("Utility", ["toc", "chunk-input", "pdsl"]),
    ("Workspace", ["workspace-init", "workspace-add", "workspace-info", "workspace-sync"]),
    ("Delegation", ["delegate"]),
    ("Diagnostics", ["doctor"]),
    ("Visualization", ["map"]),
]

_COMMAND_HANDLERS: dict[str, str] = {
    "validate": "_cmd_validate",
    "validate-code": "_cmd_validate",
    "validate-kits": "_cmd_validate_kits",
    "validate-rules": "_cmd_validate_kits",
    "self-check": "_cmd_validate_kits",
    "init": "_cmd_init",
    "update": "_cmd_update",
    "list-ids": "_cmd_list_ids",
    "list-id-kinds": "_cmd_list_id_kinds",
    "get-content": "_cmd_get_content",
    "where-defined": "_cmd_where_defined",
    "where-used": "_cmd_where_used",
    "info": "_cmd_studio_info",
    "resolve-vars": "_cmd_resolve_vars",
    "agents": "_cmd_agents",
    "generate-agents": "_cmd_generate_agents",
    "kit": "_cmd_kit",
    "generate-resources": "_cmd_generate_resources",
    "toc": "_cmd_toc",
    "validate-toc": "_cmd_validate_toc",
    "spec-coverage": "_cmd_spec_coverage",
    "chunk-input": "_cmd_chunk_input",
    "workspace-init": "_cmd_workspace_init",
    "workspace-add": "_cmd_workspace_add",
    "workspace-info": "_cmd_workspace_info",
    "workspace-sync": "_cmd_workspace_sync",
    "delegate": "_cmd_delegate",
    "doctor": "_cmd_doctor",
    "check-language": "_cmd_check_language",
    "pdsl": "_cmd_pdsl",
    "map": "_cmd_map",
}

# Keep explicit references so dead-code scanners see dynamic dispatch targets.
_COMMAND_HANDLER_REFERENCES: tuple[CommandHandler, ...] = (
    _cmd_validate,
    _cmd_validate_kits,
    _cmd_init,
    _cmd_update,
    _cmd_list_ids,
    _cmd_list_id_kinds,
    _cmd_get_content,
    _cmd_where_defined,
    _cmd_where_used,
    _cmd_studio_info,
    _cmd_resolve_vars,
    _cmd_agents,
    _cmd_generate_agents,
    _cmd_kit,
    _cmd_generate_resources,
    _cmd_toc,
    _cmd_validate_toc,
    _cmd_spec_coverage,
    _cmd_chunk_input,
    _cmd_workspace_init,
    _cmd_workspace_add,
    _cmd_workspace_info,
    _cmd_workspace_sync,
    _cmd_delegate,
    _cmd_doctor,
    _cmd_check_language,
    _cmd_pdsl,
    _cmd_map,
)

_ALL_COMMANDS = list(_COMMAND_HANDLERS)

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main(argv: Optional[List[str]] = None) -> int:
    """Run the command-line entry point."""
    _configure_studio_logging()
    argv_list = list(argv) if argv is not None else sys.argv[1:]

    # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-parse-args
    from .utils.ui import is_json_mode, set_json_mode
    previous_json_mode = is_json_mode()
    json_mode = "--json" in argv_list
    if json_mode:
        set_json_mode(True)
        while "--json" in argv_list:
            argv_list.remove("--json")
    # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-parse-args
    try:
        return _main_impl(argv_list)
    finally:
        set_json_mode(previous_json_mode)


def _main_impl(argv_list: List[str]) -> int:
    """Dispatch a command after global flags have been handled."""
    _load_startup_context()
    if not argv_list or argv_list[0] in ("-h", "--help"):
        # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-return-code
        help_result = _render_top_level_help()
        return help_result
        # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-return-code

    cmd, rest = _parse_command(argv_list)
    handler = _resolve_command_handler(cmd)
    # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-if-no-handler
    if handler is None:
        return _report_unknown_command(cmd)
    # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-if-no-handler
    # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-execute-handler
    handler_result = handler(rest)
    return handler_result
    # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-execute-handler


def _load_startup_context() -> None:
    """Best-effort context loading for commands that rely on Studio state."""
    from .utils.context import ensure_context, set_context

    set_context(None)
    ensure_context(Path.cwd())


def _emit_help_json_payload() -> None:
    """Emit the top-level help payload in JSON mode."""
    from .utils.ui import ui

    # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-serialize-json
    payload = {
        "usage": "cfs <command> [options]",
        "commands": _COMMAND_DESCRIPTIONS,
        "sections": dict(_COMMAND_SECTIONS),
    }
    ui.result(payload)
    # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-serialize-json


def _render_top_level_help() -> int:
    """Render top-level CLI help in human or JSON format."""
    from .utils.ui import is_json_mode, ui

    if is_json_mode():
        _emit_help_json_payload()
        return 0

    ui.header("Constructor Studio CLI")
    ui.info("Artifact validation, traceability, and kit management tool.")
    ui.blank()
    for section_name, commands in _COMMAND_SECTIONS:
        ui.step(section_name)
        for command in commands:
            ui.substep(f"  {command:<22} {_COMMAND_DESCRIPTIONS.get(command, '')}")
        ui.blank()
    ui.info("Global flags:")
    ui.substep(f"  {'--json':<22} Machine-readable JSON output (for AI agents)")
    ui.blank()
    ui.hint("Run 'cfs <command> --help' for command-specific options.")
    ui.hint("Legacy aliases: validate-code -> validate, validate-rules/self-check -> validate-kits")
    ui.blank()
    return 0


def _parse_command(argv_list: List[str]) -> tuple[str, List[str]]:
    """Resolve the requested command and remaining args."""
    # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-parse-command
    if argv_list[0].startswith("-"):
        return "validate", argv_list
    return argv_list[0], argv_list[1:]
    # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-parse-command


def _resolve_command_handler(cmd: str) -> Optional[CommandHandler]:
    """Resolve a command handler from the dispatch table."""
    # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-lookup-handler
    handler_name = _COMMAND_HANDLERS.get(cmd)
    if handler_name is None:
        return None
    return globals()[handler_name]
    # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-lookup-handler


def _emit_unknown_command_payload(cmd: str) -> None:
    """Emit the unknown-command payload."""
    from .utils.ui import ui

    # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-serialize-json
    payload = {
        "status": "ERROR",
        "message": f"Unknown command: {cmd}",
        "available": _ALL_COMMANDS,
    }
    ui.result(
        payload,
        human_fn=lambda _data: (
            ui.error(f"Unknown command: {cmd}"),
            ui.hint(f"Available commands: {', '.join(_ALL_COMMANDS)}"),
            ui.hint("Run 'cfs --help' for usage."),
        ),
    )
    # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-serialize-json


def _report_unknown_command(cmd: str) -> int:
    """Emit the standard unknown-command error payload."""
    # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-return-unknown
    _emit_unknown_command_payload(cmd)
    return 1
    # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-return-unknown

if __name__ == "__main__":
    raise SystemExit(main())

__all__ = ["main"]
# @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-route-helpers
