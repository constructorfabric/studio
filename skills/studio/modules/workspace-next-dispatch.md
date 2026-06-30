# Workspace Next

```pdsl
UNIT WorkspaceNextSteps
PURPOSE: Present post-setup next steps after successful workspace setup (Phase 5).
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md WHEN NextActionsOffer is not yet loaded
  EMIT_MENU WorkspaceNextStepsMenu
  WAIT user.reply
  STOP_TURN
MENU WorkspaceNextStepsMenu
TITLE: What would you like to do next?
OPTIONS:
  1 validate-repos (suggested) — verify cross-repo ID resolution across participating repos -> EMIT "Running workspace validation across the participating repos."; RUN `{cfs_cmd} validate` from each participating repo (verifies cross-repo ID resolution), RETURN a WORKSPACE_STATUS record (phase=next-steps, status=complete, next_route=null), then RUN NextActionsOffer
  2 list-ids -> EMIT "Checking that artifacts from all workspace sources are visible."; RUN `{cfs_cmd} list-ids` to confirm artifacts from all sources are visible, RETURN a WORKSPACE_STATUS record (phase=next-steps, status=complete, next_route=null), then RUN NextActionsOffer
  3 other — describe the next workspace action you want -> EMIT "Reply with the next workspace action you want to take."; WAIT the user's next workspace action, RETURN a WORKSPACE_STATUS record (phase=next-steps, status=complete, next_route=null), then RUN NextActionsOffer
  INVALID -> EMIT_MENU WorkspaceNextStepsMenu
```

```pdsl
UNIT WorkspaceDispatch
PURPOSE: Name how phases are driven and guard the workspace safety rails.
RULES:
  ALWAYS drive the cfs workspace CLI (no sub-agents)
  ALWAYS run the setup phases in order (discover -> configure -> generate -> validate -> next-steps) and route status-only requests to WorkspaceInspectEntry instead of loading all setup phases
  ALWAYS emit a terminal record at each phase boundary — when a phase ends in STOP_TURN or hands off to a different phase — using the record shapes (WORKSPACE_STATUS, WORKSPACE_VALIDATION, WORKSPACE_FAILURE) in the loaded setup reference; intra-phase recovery loops (a failure menu's retry/back, or re-emitting the same phase's menu) do NOT require their own record
  NEVER write workspace config without all-sources-confirmed and explicit write confirmation
  NEVER use inline storage with Git URL sources
```
