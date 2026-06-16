# Workspace Configure

```pdsl
UNIT WorkspaceConfigure
PURPOSE: Confirm every selected source's settings and the final location before generating (Phase 2).
STATE:
  SET all_sources_confirmed: unset | true (default unset, scope workflow_run; any source edit re-requires re-confirmation)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/workspace-generate.md
  EMIT a batched confirmation proposal for the next unconfirmed source — name, relative path or url, role, adapter, cross_repo, resolve_remote_ids, workspace location
  EMIT_MENU SourceConfirmMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS confirm every source field listed in the loaded reference and track confirmation per source individually (defaults, incl. cross_repo/resolve_remote_ids, come from the reference)
  NEVER enter generate until every source is confirmed and the location is final; the primary source is always the cwd (no `primary` field), and NEVER allow inline location with any Git URL source
MENU SourceConfirmMenu
TITLE: Confirm source settings (fields + suggested defaults in the loaded reference). Reply approve or list fields to change.
OPTIONS:
  1 approve -> mark the source confirmed, then CONTINUE WorkspaceConfigure WHEN unconfirmed sources remain, else SET all_sources_confirmed = true, RETURN a WORKSPACE_STATUS record (phase=configure, status=complete, next_route=generate), then CONTINUE WorkspaceGenerate
  2 field-edits | edit -> apply edits to the named fields; SET all_sources_confirmed = unset (the edited source must be re-confirmed); reject and reset to standalone WHEN the edit changes location to inline AND any source is a Git URL; re-show the proposal and EMIT_MENU SourceConfirmMenu
  3 cancel -> RETURN a WORKSPACE_STATUS record (status=pending) and STOP_TURN
  INVALID -> EMIT_MENU SourceConfirmMenu
```
