# Workspace Router

```pdsl
UNIT WorkspaceIntentRouter
PURPOSE: Route the workspace request by user intent.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/workspace-discover.md
  EMIT_MENU WorkspaceIntentMenu
  WAIT user.reply
  STOP_TURN
MENU WorkspaceIntentMenu
TITLE: What would you like to do — setup, quick-command, or status? (see loaded setup reference for what each does) Reply with a number or the option name.
OPTIONS:
  1 setup -> SET PLAN_FIRST_CONTINUE = WorkspaceDiscover, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE PlanFirstGate
  2 quick-command | quick -> CONTINUE WorkspaceQuickCommand
  3 status -> CONTINUE {cf-studio-path}/.core/workflows/analyze.md with the workspace as target
  INVALID -> EMIT_MENU WorkspaceIntentMenu
```

```pdsl
UNIT WorkspaceQuickCommand
PURPOSE: Narrow CLI fast path for read-only status, single-source add, or sync — skips the setup phases.
DO:
  RUN `{cfs_cmd} --json workspace-info` for a read-only status request, RETURN a WORKSPACE_STATUS record, then STOP_TURN
  EMIT the planned write command (`{cfs_cmd} --json workspace-add --name <name> (--path <path> | --url <url>) [--branch <branch>] [--role <role>] [--adapter <path>] [--inline]` or `{cfs_cmd} --json workspace-sync`) and EMIT_MENU QuickWriteConfirm for a write-capable request
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS skip the setup phases for quick commands
  NEVER run a write-capable quick command (workspace-add, workspace-sync) without confirmation, and NEVER require workspace setup prompt assets for a read-only workspace-info
MENU QuickWriteConfirm
TITLE: Run the planned write command shown above?
OPTIONS:
  1 confirm -> RUN the planned write CLI, RETURN a WORKSPACE_STATUS record, then STOP_TURN
  2 cancel -> RETURN a WORKSPACE_STATUS record (status=pending) and STOP_TURN
  INVALID -> EMIT_MENU QuickWriteConfirm
```
