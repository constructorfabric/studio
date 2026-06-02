---
cf: true
type: workflow
parent: workflows/workspace.md
description: "Invoke when the workspace workflow enters Phase 3 to write standalone or inline workspace configuration via CLI."
---

<!-- toc -->

- [Phase 3: Generate](#phase-3-generate)

<!-- /toc -->

## Phase 3: Generate

```pdsl
UNIT WorkspaceGenerate

PURPOSE:
  Write the workspace config via CLI after all confirmation gates pass.

NOTES:
  CF_PHASE_GATE is defined session-scoped in SKILL.md § Phase-Skip Gate; only armed and released_for_orchestrator_write are used here.

WHEN:
  - REQUIRE WORKSPACE_ALL_SOURCES_CONFIRMED == true
  - AND final workspace location is resolved and valid

DO:
  - RUN Resolve workspace_config_path:
    standalone mode -> {project_root}/.studio-workspace.toml
    inline mode    -> {project_root}/config/core.toml
  - SET CF_PHASE_GATE = released_for_orchestrator_write
    scope: {workspace_config_path}
  - RUN Invoke CLI:
    Initialize: `{cfs_cmd} --json workspace-init [--root <super-root>] [--output <path>] [--inline] [--force] [--dry-run]`
    Add source:  `{cfs_cmd} --json workspace-add --name <name> (--path <path> | --url <url>) [--branch <branch>] [--role <role>] [--adapter <path>] [--inline]`
  - SET CF_PHASE_GATE = armed
  - REQUIRE CLI succeeded:
    - CONTINUE workflows/workspace/phase-4-validate.md
  - RUN otherwise
    - CONTINUE WorkspaceGenerateFailureMenu

RULES:
  - ALWAYS check WORKSPACE_ALL_SOURCES_CONFIRMED == true before invoking CLI
  - ALWAYS check final workspace location is resolved and valid for selected source set before invoking CLI
  - NEVER attempt Phase 3 with --inline against a Git URL source set
  - ALWAYS SET CF_PHASE_GATE = released_for_orchestrator_write with named scope before CLI invocation
  - ALWAYS SET CF_PHASE_GATE = armed immediately after CLI returns (success or failure)
  - ALWAYS The logical [workspace] TOML section is part of the inline write target; it is NOT a valid gate scope
  - NEVER infer WORKSPACE_ALL_SOURCES_CONFIRMED from partially edited source proposals
```

```pdsl
UNIT WorkspaceGeneratePrerequisiteCheck

PURPOSE:
  Fail-stop Phase 3 entry when confirmation gate or location is not satisfied.

WHEN:
  - REQUIRE WORKSPACE_ALL_SOURCES_CONFIRMED != true
  - OR final workspace location is unresolved or invalid

DO:
  - EMIT summary of missing prerequisite
  - CONTINUE workflows/workspace/phase-2-configure.md

RULES:
  - NEVER proceed to CLI invocation under any prerequisite failure
```

```pdsl
UNIT WorkspaceGenerateFailureMenu

PURPOSE:
  Offer structured recovery choices after CLI failure.

DO:
  - RUN Report CLI exit code and error message
  - EMIT_MENU GenerateFailureMenu
  - WAIT user.reply
  - STOP_TURN

MENU GenerateFailureMenu:
  TITLE: |
    Reply 1, 2, or 3.
    Suggested: 1 if the error mentions a path collision or locked file (transient);
               2 if the error references invalid config values or missing required fields.
  OPTIONS:
    1 -> Retry the workspace generate CLI command
         CONTINUE WorkspaceGenerate
    2 -> Return to Phase 2 to adjust the workspace config
         CONTINUE workflows/workspace/phase-2-configure.md
    3 -> Stop workspace setup
         STOP_TURN
  STOP_TOKEN:
    treat as option 3; leave partial state for user inspection
  INVALID:
    EMIT "Reply with 1, 2, or 3."
    WAIT user.reply
    STOP_TURN

NOTES:
  See workflows/shared/stop-token-policy.md for stop-token routing.
  No manual partial-write rollback is needed — the CLI is responsible for atomicity.
  workspace-init writes standalone config by default; --inline writes [workspace] into config/core.toml.
  workspace-add auto-detects workspace type unless --inline forces inline mode.
  Git URL sources are not supported inline.
```
