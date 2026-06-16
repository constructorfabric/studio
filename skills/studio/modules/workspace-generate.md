# Workspace Generate

```pdsl
UNIT WorkspaceGenerate
PURPOSE: Write the workspace config via CLI after all confirmation gates pass (Phase 3).
WHEN:
  REQUIRE all_sources_confirmed == true
  AND the workspace location is resolved and valid
DO:
  RUN resolve workspace_config_path — standalone -> {project_root}/.studio-workspace.toml; inline -> {project_root}/config/core.toml
  EMIT the write plan and confirm
  RUN WorkspaceGenerateWrite
  LOAD {cf-studio-path}/.core/skills/studio/modules/workspace-validate.md
  CONTINUE WorkspaceGenerateSuccess WHEN the CLI succeeded
  EMIT_MENU GenerateFailureMenu WHEN the CLI failed
RULES:
  NEVER invoke the write CLI unless all_sources_confirmed == true and the location is valid; NEVER use --inline against a Git URL source set
  ALWAYS set CF_PHASE_GATE (an external protocol var; see the loaded reference) to released_for_orchestrator_write (scoped) before the CLI and armed immediately after it returns
```

```pdsl
UNIT WorkspaceGenerateWrite
PURPOSE: Open the write gate, run the workspace generation CLIs, and re-arm the gate.
DO:
  SET CF_PHASE_GATE = released_for_orchestrator_write (scope: workspace_config_path)
  RUN `{cfs_cmd} --json workspace-init [--root <super-root>] [--output <path>] [--inline] [--force] [--dry-run]`
  RUN `{cfs_cmd} --json workspace-add --name <name> (--path <path> | --url <url>) [--branch <branch>] [--role <role>] [--adapter <path>] [--inline]` per source
  SET CF_PHASE_GATE = armed
```

```pdsl
UNIT WorkspaceGenerateSuccess
PURPOSE: Return the generate-phase success record and continue to validation.
DO:
  RETURN a WORKSPACE_STATUS record (phase=generate, status=complete, next_route=validate)
  CONTINUE WorkspaceValidate
MENU GenerateFailureMenu
TITLE: The workspace generate CLI failed. Suggested: 1 for transient path-collision/locked-file errors; 2 for invalid config values. Reply with a number.
OPTIONS:
  1 retry -> CONTINUE WorkspaceGenerate
  2 back -> LOAD {cf-studio-path}/.core/skills/studio/modules/workspace-configure.md; CONTINUE WorkspaceConfigure
  3 stop -> RETURN a WORKSPACE_FAILURE record and STOP_TURN
  INVALID -> EMIT_MENU GenerateFailureMenu
```
