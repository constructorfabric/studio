# Workspace Discover

```pdsl
UNIT WorkspaceDiscover
PURPOSE: Find candidate repos, then collect repo selection and storage mode (Phase 1).
STATE:
  SET location: standalone | inline (default standalone, scope workflow_run)
DO:
  RUN `{cfs_cmd} --json info` to identify the root
  RUN `{cfs_cmd} --json workspace-init --dry-run` to scan nested repos
  EMIT the discovered repos — name/path, adapter found or missing, inferred role
  LOAD {cf-studio-path}/.core/skills/studio/modules/workspace-configure.md
  EMIT_MENU ZeroResultsMenu WHEN no repos were discovered
  EMIT_MENU RepoSelectionMenu WHEN one or more repos were discovered
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER proceed to configure or write any config when zero repos are discovered, and NEVER infer sources from unrelated directories
  ALWAYS force standalone when any selected source is a Git URL
MENU ZeroResultsMenu
TITLE: No workspace sources were discovered under the scan root. Reply with a number.
OPTIONS:
  1 new-root -> WAIT a new scan root and re-scan, then CONTINUE WorkspaceDiscover
  2 manual -> WAIT a manual source (name + path or URL), add it to candidates, then EMIT_MENU StorageModeMenu
  3 stop -> EMIT "Workspace discovery stopped with no sources selected."; RETURN a WORKSPACE_STATUS record (status=pending) and STOP_TURN
  INVALID -> EMIT_MENU ZeroResultsMenu
MENU RepoSelectionMenu
TITLE: Which repos should be included as workspace sources? Reply with numbers/names or `all` (see loaded reference for the suggested default).
OPTIONS:
  1 select -> parse the selection into the included-sources list, then EMIT_MENU StorageModeMenu
  2 cancel -> EMIT "Workspace discovery cancelled before source selection was completed."; RETURN a WORKSPACE_STATUS record (status=pending) and STOP_TURN
  INVALID -> EMIT_MENU RepoSelectionMenu
MENU StorageModeMenu
TITLE: Where should the workspace config live — standalone (.studio-workspace.toml) or inline ([workspace] in config/core.toml)? (see loaded reference; inline is unavailable with Git URL sources)
OPTIONS:
  1 standalone -> SET location = standalone, RETURN a WORKSPACE_STATUS record (phase=discover, status=complete, next_route=configure), then CONTINUE WorkspaceConfigure
  2 inline -> EMIT "Inline storage is not supported for Git URL sources; please choose standalone storage or change the selected repos." and EMIT_MENU StorageModeMenu WHEN any selected source is a Git URL, else SET location = inline, RETURN a WORKSPACE_STATUS record (phase=discover, status=complete, next_route=configure), then CONTINUE WorkspaceConfigure
  3 cancel -> EMIT "Workspace setup cancelled before choosing a storage mode."; RETURN a WORKSPACE_STATUS record (status=pending) and STOP_TURN
  INVALID -> EMIT_MENU StorageModeMenu
```
