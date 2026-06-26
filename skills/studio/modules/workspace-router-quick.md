# Workspace Router

```pdsl
UNIT WorkspaceIntentRouter
PURPOSE: Route the workspace request directly by intent, using menus only when the request is ambiguous or under-specified.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/workspace-discover.md
  CONTINUE WorkspaceSetupEntry WHEN the intent asks to create, initialize, discover, reinitialize, or migrate a workspace layout
  CONTINUE WorkspaceInspectEntry WHEN the intent is read-only: status, config inspection, source health, ID visibility, path lookup, usage lookup, validation, or map
  CONTINUE WorkspaceSyncEntry WHEN the intent asks to sync, fetch, update, refresh, or dry-run Git URL workspace sources
  CONTINUE WorkspaceWriteEntry WHEN the intent asks to add, replace, remove, rename, move, or edit sources or workspace config sections
  EMIT_MENU WorkspaceIntentMenu
  WAIT user.reply
  STOP_TURN
MENU WorkspaceIntentMenu
TITLE: Workspace intent is ambiguous. Choose the closest route or restate the request with the target source/section.
OPTIONS:
  1 setup -> CONTINUE WorkspaceSetupEntry
  2 inspect -> CONTINUE WorkspaceInspectEntry
  3 edit -> CONTINUE WorkspaceWriteEntry
  4 sync -> CONTINUE WorkspaceSyncEntry
  5 diagnose -> CONTINUE WorkspaceInspectEntry
  INVALID -> EMIT_MENU WorkspaceIntentMenu
```

```pdsl
UNIT WorkspaceSetupEntry
PURPOSE: Decide whether setup should run directly or fall back to guided discovery.
DO:
  RUN `{cfs_cmd} --json workspace-init --dry-run [--root <root>] [--inline] [--max-depth <n>]` and present the discovered sources WHEN the user asks to discover candidates, preview setup, or choose from scan results
  RUN `{cfs_cmd} --json workspace-init [--root <root>] [--output <path>] [--inline] [--force] [--max-depth <n>]` directly WHEN the user explicitly asked to initialize or reinitialize a workspace and supplied the needed inputs
  SET PLAN_FIRST_CONTINUE = WorkspaceDiscover, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE PlanFirstGate WHEN inputs are incomplete, the user wants a guided selection flow, or source discovery must precede a write
RULES:
  ALWAYS prefer direct `workspace-init` when the request is explicit and low-ambiguity
  NEVER require the guided discovery wizard for a complete, explicit init request unless `--force` or storage migration risk must be confirmed
```

```pdsl
UNIT WorkspaceInspectEntry
PURPOSE: Use the narrowest read-only workspace-aware command that answers the request.
DO:
  RUN `{cfs_cmd} --json workspace-info` WHEN the user asks for workspace status, current config shape, source health, reachability, adapter presence, or traceability settings
  RUN `{cfs_cmd} --json list-ids [--source <name>]` WHEN the user asks which IDs are visible from the workspace or from a specific source
  RUN `{cfs_cmd} --json where-defined --id <id>` WHEN the user asks where an ID is defined across the workspace
  RUN `{cfs_cmd} --json where-used --id <id>` WHEN the user asks where an ID is referenced across the workspace
  RUN `{cfs_cmd} --json validate [--source <name> | --local-only]` WHEN the user asks to validate workspace-wide behavior, validate one source, or compare local-only vs cross-repo validation
  RUN `{cfs_cmd} --json map [--local-only]` WHEN the user asks for workspace-aware dependency or traceability mapping
  RETURN a WORKSPACE_STATUS record (phase=inspect, status=complete, next_route=null), then STOP_TURN
RULES:
  ALWAYS prefer read-only CLI over manual config reading when a CLI command already answers the question
  ALWAYS include `workspace-info` before or after another read-only command when config context is needed to interpret the result
  NEVER gate read-only inspection behind an approval menu
```

```pdsl
UNIT WorkspaceSyncEntry
PURPOSE: Sync the smallest sufficient set of Git URL sources, preferring targeted refresh over full sync.
DO:
  RUN `{cfs_cmd} --json workspace-sync --dry-run [--source <name>]` WHEN the user asks what would sync or wants a safe preview
  RUN `{cfs_cmd} --json workspace-sync --source <name>` WHEN the user names a source, repo, URL, branch, or path that maps to one Git URL source
  RUN `{cfs_cmd} --json workspace-sync` WHEN the user explicitly asks to sync all Git URL sources or no narrower target can be inferred
  EMIT the planned force command and EMIT_MENU WorkspaceForceSyncConfirm WHEN the user requests `--force` or a dirty worktree makes force the only viable path
  RETURN a WORKSPACE_STATUS record (phase=sync, status=complete, next_route=null), then STOP_TURN
RULES:
  ALWAYS prefer `workspace-sync --source <name>` over full sync when a targeted source is available
  ALWAYS inspect `workspace-info` first when source targeting is ambiguous and needs disambiguation
  NEVER use `workspace-sync --force` without an explicit destructive confirmation because it may discard local changes
MENU WorkspaceForceSyncConfirm
TITLE: `workspace-sync --force` may discard uncommitted changes in the target worktree. Continue?
OPTIONS:
  1 confirm -> RUN the planned force sync CLI, RETURN a WORKSPACE_STATUS record (phase=sync, status=complete, next_route=null), then STOP_TURN
  2 cancel -> RETURN a WORKSPACE_STATUS record (phase=sync, status=pending, next_route=null), then STOP_TURN
  INVALID -> EMIT_MENU WorkspaceForceSyncConfirm
```

```pdsl
UNIT WorkspaceWriteEntry
PURPOSE: Choose between workspace CLI writes and direct workspace config edits, with minimal gates for safe explicit requests.
DO:
  RUN `{cfs_cmd} --json workspace-add --name <name> (--path <path> | --url <url>) [--branch <branch>] [--role <role>] [--adapter <path>] [--inline] [--force]` WHEN the user is adding a new source and the CLI fully covers the requested write
  LOAD the current workspace config, schema, and setup reference; then edit the smallest matching config section WHEN the user asks to change source fields, remove or rename a source, migrate between inline and standalone storage, or edit `[traceability]`, `[resolve]`, or `[validation]`
  RUN `{cfs_cmd} --json workspace-info` after every successful write
  RUN `{cfs_cmd} --json list-ids [--source <name>]`, `{cfs_cmd} --json validate [--source <name>]`, or `{cfs_cmd} --json where-defined --id <id>` when the edit changes cross-repo resolution, source targeting, or remote-ID visibility
  RETURN a WORKSPACE_STATUS record (phase=write, status=complete, next_route=null), then STOP_TURN
RULES:
  ALWAYS prefer workspace CLI for `workspace-init`, `workspace-add`, `workspace-info`, and `workspace-sync`
  ALWAYS prefer direct config edits for mutations the CLI does not expose: source removal, source rename, source field rewrites, storage migration, `[traceability]`, `[resolve]`, and `[validation]`
  ALWAYS preserve unrelated sections, source entries, comments, and storage mode unless the user explicitly asks to change them
  ALWAYS choose the correct config surface before editing: standalone workspace file, inline `[workspace]` in `config/core.toml`, or external file referenced by `workspace = "<path>"`
  NEVER require a confirmation menu for a non-destructive config edit when the user explicitly requested it and all required values are known
  NEVER use `--force` for source replacement, reinitialization, or storage migration without an explicit confirmation step
```
