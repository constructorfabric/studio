"""
Studio Validator - CLI Entry Point

Command-line interface for the Studio validation tool.

IMPORTANT: This module MUST NOT contain business logic.

- The CLI is responsible only for argv parsing and command dispatch.
- All validation, scanning, and transformation logic MUST live in dedicated modules under studio.utils or command modules.
"""

# @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-route-helpers
import sys
from pathlib import Path
from typing import List, Optional


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
    sys.stderr.write(
        "WARNING: 'generate-resources' is deprecated.\n"
        "         Kits are direct file packages — use 'cfs kit update <path>' instead.\n"
    )
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

# =============================================================================
# VISUALIZATION COMMANDS
# =============================================================================

def _cmd_map(argv: List[str]) -> int:
    from .commands.map.cli import cmd_map
    return cmd_map(argv)
# @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-route-helpers

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

# @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-route-helpers
def main(argv: Optional[List[str]] = None) -> int:
    argv_list = list(argv) if argv is not None else sys.argv[1:]

    # Extract global --json flag (must come before command dispatch)
    from .utils.ui import set_json_mode
    if "--json" in argv_list:
        set_json_mode(True)
        while "--json" in argv_list:
            argv_list.remove("--json")

    # Load base Studio context on startup (templates, systems, etc.)
    # Workspace upgrade is deferred — get_context() will lazily attempt it
    # on first access, so commands like --help and init avoid network I/O.
    from .utils.context import StudioContext, set_context
    ctx = StudioContext.load()
    set_context(ctx)
    # Context may be None if Constructor Studio not initialized - that's OK for some commands like init

    # Define all available commands
    analysis_commands = ["validate", "validate-kits", "validate-toc", "spec-coverage", "check-language"]
    legacy_aliases = ["validate-code", "validate-rules"]
    kit_commands = ["kit"]
    utility_commands = ["toc", "chunk-input"]
    search_commands = [
        "init", "update",
        "list-ids", "list-id-kinds",
        "get-content",
        "where-defined", "where-used",
        "info", "resolve-vars",
        "agents",
        "generate-agents",
    ]
    workspace_commands = [
        "workspace-init", "workspace-add", "workspace-info", "workspace-sync",
    ]
    delegation_commands = ["delegate"]
    diagnostics_commands = ["doctor"]
    visualization_commands = ["map"]
    all_commands = (
        analysis_commands + kit_commands + search_commands
        + workspace_commands + utility_commands + delegation_commands
        + diagnostics_commands + visualization_commands + legacy_aliases
    )

    # Handle --help / -h at top level (or no subcommand)
    if not argv_list or argv_list[0] in ("-h", "--help"):
        from .utils.ui import ui, is_json_mode
        _cmd_descriptions = {
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
            "workspace-init": "Initialize multi-repo workspace",
            "workspace-add": "Add a source to workspace config",
            "workspace-info": "Show workspace config and source status",
            "workspace-sync": "Fetch and update Git URL source worktrees",
            "delegate": "Compile and delegate a plan to ralphex",
            "doctor": "Run environment health checks",
            "map": "Build interactive markdown↔source dependency map via cpt identifiers",
        }
        _sections = [
            ("Setup & Configuration", ["init", "update", "info", "resolve-vars", "generate-agents", "agents"]),
            ("Validation", ["validate", "validate-kits", "validate-toc", "spec-coverage", "check-language"]),
            ("Search & Navigation", ["list-ids", "list-id-kinds", "get-content", "where-defined", "where-used"]),
            ("Kit Management", ["kit"]),
            ("Utility", ["toc", "chunk-input"]),
            ("Workspace", ["workspace-init", "workspace-add", "workspace-info", "workspace-sync"]),
            ("Delegation", ["delegate"]),
            ("Diagnostics", ["doctor"]),
            ("Visualization", ["map"]),
        ]
        if is_json_mode():
            import json  # pylint: disable=import-outside-toplevel  # lazy: only needed in JSON output mode
            print(json.dumps({
                "usage": "cfs <command> [options]",
                "commands": _cmd_descriptions,
                "sections": {name: cmds for name, cmds in _sections},
            }, indent=2, ensure_ascii=False))
        else:
            ui.header("Constructor Studio CLI")
            ui.info("Artifact validation, traceability, and kit management tool.")
            ui.blank()
            for section_name, cmds in _sections:
                ui.step(section_name)
                for c in cmds:
                    desc = _cmd_descriptions.get(c, "")
                    sys.stderr.write(f"      {c:<22} {desc}\n")
                ui.blank()
            ui.info("Global flags:")
            sys.stderr.write(f"      {'--json':<22} Machine-readable JSON output (for AI agents)\n")
            ui.blank()
            ui.hint("Run 'cfs <command> --help' for command-specific options.")
            ui.hint("Legacy aliases: validate-code → validate, validate-rules/self-check → validate-kits")
            ui.blank()
        return 0
    # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-route-helpers

    # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-parse-command
    # Backward compatibility: if first arg starts with --, assume validate command
    if argv_list[0].startswith("-"):
        cmd = "validate"
        rest = argv_list
    else:
        cmd = argv_list[0]
        rest = argv_list[1:]
    # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-parse-command

    # @cpt-dod:cpt-studio-dod-core-infra-agents-integrity:p1
    # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-verify-agents
    # Verify root AGENTS.md and CLAUDE.md integrity on every invocation (silent re-inject if stale)
    if ctx is not None and cmd not in ("init", "update"):
        try:
            from .commands.init import _inject_root_agents, _inject_root_claude
            from .utils.files import find_project_root, _read_studio_var
            project_root = find_project_root(Path.cwd())
            if project_root is not None:
                install_rel = _read_studio_var(project_root)
                if install_rel:
                    _inject_root_agents(project_root, install_rel)
                    _inject_root_claude(project_root, install_rel)
        except (OSError, ValueError, KeyError):
            pass  # Non-fatal: don't block command execution
    # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-verify-agents

    # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-lookup-handler
    # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-parse-args
    # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-execute-handler
    # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-serialize-json
    # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-return-code
    # Dispatch to appropriate command handler
    if cmd == "validate":
        return _cmd_validate(rest)
    elif cmd == "validate-code":
        # Legacy alias: keep for compatibility.
        return _cmd_validate(rest)
    elif cmd in ("validate-kits", "validate-rules", "self-check"):
        return _cmd_validate_kits(rest)
    elif cmd == "init":
        return _cmd_init(rest)
    elif cmd == "update":
        return _cmd_update(rest)
    elif cmd == "list-ids":
        return _cmd_list_ids(rest)
    elif cmd == "list-id-kinds":
        return _cmd_list_id_kinds(rest)
    elif cmd == "get-content":
        return _cmd_get_content(rest)
    elif cmd == "where-defined":
        return _cmd_where_defined(rest)
    elif cmd == "where-used":
        return _cmd_where_used(rest)
    elif cmd == "info":
        return _cmd_studio_info(rest)
    elif cmd == "resolve-vars":
        return _cmd_resolve_vars(rest)
    elif cmd == "agents":
        return _cmd_agents(rest)
    elif cmd == "generate-agents":
        return _cmd_generate_agents(rest)
    elif cmd == "kit":
        return _cmd_kit(rest)
    elif cmd == "generate-resources":
        return _cmd_generate_resources(rest)
    elif cmd == "toc":
        return _cmd_toc(rest)
    elif cmd == "validate-toc":
        return _cmd_validate_toc(rest)
    elif cmd == "spec-coverage":
        return _cmd_spec_coverage(rest)
    elif cmd == "chunk-input":
        return _cmd_chunk_input(rest)
    elif cmd == "workspace-init":
        return _cmd_workspace_init(rest)
    elif cmd == "workspace-add":
        return _cmd_workspace_add(rest)
    elif cmd == "workspace-info":
        return _cmd_workspace_info(rest)
    elif cmd == "workspace-sync":
        return _cmd_workspace_sync(rest)
    elif cmd == "delegate":
        return _cmd_delegate(rest)
    elif cmd == "doctor":
        return _cmd_doctor(rest)
    elif cmd == "check-language":
        return _cmd_check_language(rest)
    elif cmd == "map":
        return _cmd_map(rest)
    else:
        # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-if-no-handler
        # @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-return-unknown
        from .utils.ui import ui
        ui.result(
            {"status": "ERROR", "message": f"Unknown command: {cmd}", "available": all_commands},
            human_fn=lambda d: (
                ui.error(f"Unknown command: {cmd}"),
                ui.hint(f"Available commands: {', '.join(all_commands)}"),
                ui.hint("Run 'cfs --help' for usage."),
            ),
        )
        return 1
        # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-return-unknown
        # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-if-no-handler
    # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-return-code
    # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-serialize-json
    # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-execute-handler
    # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-parse-args
    # @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-lookup-handler

# @cpt-begin:cpt-studio-algo-core-infra-route-command:p1:inst-route-helpers
if __name__ == "__main__":
    raise SystemExit(main())

__all__ = ["main"]
# @cpt-end:cpt-studio-algo-core-infra-route-command:p1:inst-route-helpers
