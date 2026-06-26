# Workspace Discover

```pdsl
UNIT WorkspaceDiscover
PURPOSE: Find candidate repos, then collect repo selection and storage mode (Phase 1).
STATE:
  SET location: standalone | inline (default standalone, scope workflow_run)
DO:
  RUN `{cfs_cmd} --json info` to identify the root
  RUN `{cfs_cmd} --json workspace-init --dry-run` to scan nested repos
  LOAD {cf-studio-path}/.core/skills/studio/modules/workspace-configure.md
  EMIT the discovered repos — name/path, adapter found or missing, inferred role
  EMIT_MENU ZeroResultsMenu WHEN no repos were discovered; EMIT_MENU RepoSelectionMenu WHEN one or more repos were discovered
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER proceed to configure or write any config when zero repos are discovered, and NEVER infer sources from unrelated directories
  ALWAYS force standalone when any selected source is a Git URL
  ALWAYS emit the suggested selection derived from discovered repo data before the RepoSelectionMenu (e.g. "Suggested: all N repos — adapters detected in each."); NEVER defer the suggestion to 'see loaded reference'
  NEVER show the inline option in StorageModeMenu when any source is a Git URL; preemptively remove it from the menu and note the reason
MENU ZeroResultsMenu
TITLE: No workspace sources were discovered under the scan root. Reply with a number.
OPTIONS:
  1 new-root -> WAIT a new scan root and re-scan, then CONTINUE WorkspaceDiscover
  2 manual -> WAIT a manual source (name + path or URL), add it to candidates, then EMIT_MENU StorageModeMenu
  3 stop -> EMIT "Workspace discovery stopped with no sources selected."; RETURN a WORKSPACE_STATUS record (status=pending) and STOP_TURN
  INVALID -> EMIT_MENU ZeroResultsMenu
MENU RepoSelectionMenu
TITLE: Which repos should be included as workspace sources? Reply with numbers/names or `all`.
OPTIONS:
  1 all — include all N discovered repos (suggested) -> parse the selection as all repos into the included-sources list, then EMIT_MENU StorageModeMenu
  2 select -> parse the selection into the included-sources list, then EMIT_MENU StorageModeMenu
  3 cancel -> EMIT "Workspace discovery cancelled before source selection was completed."; RETURN a WORKSPACE_STATUS record (status=pending) and STOP_TURN
  INVALID -> EMIT_MENU RepoSelectionMenu
MENU StorageModeMenu
TITLE: Where should the workspace config live — standalone (.studio-workspace.toml) or inline ([workspace] in config/core.toml)? standalone works with all source types and is easier to version independently. Choose inline only if all sources are local paths and you need config colocated with your core project.
OPTIONS:
  1 standalone (suggested) -> SET location = standalone, RETURN a WORKSPACE_STATUS record (phase=discover, status=complete, next_route=configure), then CONTINUE WorkspaceConfigure
  2 inline -> EMIT "Inline storage is not supported for Git URL sources; please choose standalone storage or change the selected repos." and EMIT_MENU StorageModeMenu WHEN any selected source is a Git URL, else SET location = inline, RETURN a WORKSPACE_STATUS record (phase=discover, status=complete, next_route=configure), then CONTINUE WorkspaceConfigure
  3 cancel -> EMIT "Workspace setup cancelled before choosing a storage mode."; RETURN a WORKSPACE_STATUS record (status=pending) and STOP_TURN
  INVALID -> EMIT_MENU StorageModeMenu
```
