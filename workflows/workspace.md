---
cf: true
type: workflow
name: cf-workspace
description: "Invoke when the user asks to set up, configure, or modify a multi-repo workspace — discover repos, configure sources, generate workspace config, validate, and add/sync cross-repo references."
version: 0.1
purpose: Drive the cfs workspace CLI to set up multi-repo federation for cross-repo traceability, confirming every source and write before touching config.
---

# cf-workspace

This skill drives the `{cfs_cmd}` workspace CLI to set up multi-repo federation for cross-repo traceability — discover candidate repos, confirm source settings, write standalone or inline config, and validate reachability, with confirmation before any write. Quick read/add/sync commands skip the setup phases.

```pdsl
UNIT WorkspaceBootstrap
PURPOSE: Ensure the cf skill is loaded before any workspace work begins.
STATE:
  SET CFS_INIT: true | false (default false, scope session)
DO:
  EMIT_MENU LoadCfSkillConfirm WHEN CFS_INIT != true
  LOAD {cf-studio-path}/.core/requirements/workspace-setup.md as the setup detail reference (framing, source fields, storage modes, validation checks, terminal-record shapes)
  CONTINUE WorkspaceIntentRouter WHEN CFS_INIT == true
RULES:
  ALWAYS verify the cf skill is loaded, CFS_INIT == true, before any workspace work
  ALWAYS treat CFS_INIT as false when its value is unknown, ambiguous, or unset
  NEVER proceed past WorkspaceBootstrap unless CFS_INIT == true is positively confirmed
  ALWAYS load and follow the workspace-setup reference for field lists, decision framing, suggested defaults, and terminal-record shapes
MENU LoadCfSkillConfirm
TITLE: The cf skill is not loaded. Load it now to continue?
OPTIONS:
  1 load -> INVOKE skill `cf` and CONTINUE WorkspaceBootstrap
  2 stop -> STOP_TURN
  INVALID -> EMIT_MENU LoadCfSkillConfirm
```
```pdsl
UNIT WorkspaceIntentRouter
PURPOSE: Route the workspace request by user intent.
DO:
  EMIT_MENU WorkspaceIntentMenu
  WAIT user.reply
  STOP_TURN
MENU WorkspaceIntentMenu
TITLE: What would you like to do — setup, quick-command, or status? (see loaded setup reference for what each does) Reply with a number or the option name.
OPTIONS:
  1 setup -> CONTINUE WorkspaceDiscover
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
```pdsl
UNIT WorkspaceDiscover
PURPOSE: Find candidate repos, then collect repo selection and storage mode (Phase 1).
STATE:
  SET location: standalone | inline (default standalone, scope workflow_run)
DO:
  RUN `{cfs_cmd} --json info` to identify the root
  RUN `{cfs_cmd} --json workspace-init --dry-run` to scan nested repos
  EMIT the discovered repos — name/path, adapter found or missing, inferred role
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
  3 stop -> RETURN a WORKSPACE_STATUS record (status=pending) and STOP_TURN
  INVALID -> EMIT_MENU ZeroResultsMenu
MENU RepoSelectionMenu
TITLE: Which repos should be included as workspace sources? Reply with numbers/names or `all` (see loaded reference for the suggested default).
OPTIONS:
  1 select -> parse the selection into the included-sources list, then EMIT_MENU StorageModeMenu
  2 cancel -> RETURN a WORKSPACE_STATUS record (status=pending) and STOP_TURN
  INVALID -> EMIT_MENU RepoSelectionMenu
MENU StorageModeMenu
TITLE: Where should the workspace config live — standalone (.studio-workspace.toml) or inline ([workspace] in config/core.toml)? (see loaded reference; inline is unavailable with Git URL sources)
OPTIONS:
  1 standalone -> SET location = standalone, RETURN a WORKSPACE_STATUS record (phase=discover, status=complete, next_route=configure), then CONTINUE WorkspaceConfigure
  2 inline -> EMIT "Inline storage is not supported for Git URL sources; please choose standalone storage or change the selected repos." and EMIT_MENU StorageModeMenu WHEN any selected source is a Git URL, else SET location = inline, RETURN a WORKSPACE_STATUS record (phase=discover, status=complete, next_route=configure), then CONTINUE WorkspaceConfigure
  3 cancel -> RETURN a WORKSPACE_STATUS record (status=pending) and STOP_TURN
  INVALID -> EMIT_MENU StorageModeMenu
```
```pdsl
UNIT WorkspaceConfigure
PURPOSE: Confirm every selected source's settings and the final location before generating (Phase 2).
STATE:
  SET all_sources_confirmed: unset | true (default unset, scope workflow_run; any source edit re-requires re-confirmation)
DO:
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
```pdsl
UNIT WorkspaceGenerate
PURPOSE: Write the workspace config via CLI after all confirmation gates pass (Phase 3).
WHEN:
  REQUIRE all_sources_confirmed == true
  AND the workspace location is resolved and valid
DO:
  RUN resolve workspace_config_path — standalone -> {project_root}/.studio-workspace.toml; inline -> {project_root}/config/core.toml
  EMIT the write plan and confirm
  SET CF_PHASE_GATE = released_for_orchestrator_write (scope: workspace_config_path)
  RUN `{cfs_cmd} --json workspace-init [--root <super-root>] [--output <path>] [--inline] [--force] [--dry-run]`
  RUN `{cfs_cmd} --json workspace-add --name <name> (--path <path> | --url <url>) [--branch <branch>] [--role <role>] [--adapter <path>] [--inline]` per source
  SET CF_PHASE_GATE = armed
  RETURN a WORKSPACE_STATUS record (phase=generate, status=complete, next_route=validate) and CONTINUE WorkspaceValidate WHEN the CLI succeeded
  EMIT_MENU GenerateFailureMenu WHEN the CLI failed
RULES:
  NEVER invoke the write CLI unless all_sources_confirmed == true and the location is valid; NEVER use --inline against a Git URL source set
  ALWAYS set CF_PHASE_GATE (an external protocol var; see the loaded reference) to released_for_orchestrator_write (scoped) before the CLI and armed immediately after it returns
MENU GenerateFailureMenu
TITLE: The workspace generate CLI failed. Suggested: 1 for transient path-collision/locked-file errors; 2 for invalid config values. Reply with a number.
OPTIONS:
  1 retry -> CONTINUE WorkspaceGenerate
  2 back -> CONTINUE WorkspaceConfigure
  3 stop -> RETURN a WORKSPACE_FAILURE record and STOP_TURN
  INVALID -> EMIT_MENU GenerateFailureMenu
```
```pdsl
UNIT WorkspaceValidate
PURPOSE: Verify reachability, adapters, and cross-repo behavior after config is written (Phase 4).
DO:
  RUN `{cfs_cmd} --json workspace-info` (status)
  RUN per-source health — path exists; adapter found if expected; artifacts.toml valid when an adapter exists
  RUN `{cfs_cmd} --json list-ids` (cross-repo IDs)
  RUN `{cfs_cmd} --json validate` (cross-repo validation)
  EMIT the report — total sources, reachable, with adapters, available cross-repo IDs
  RETURN a WORKSPACE_VALIDATION record
  EMIT_MENU ValidationFailureMenu WHEN critical failures are detected
  CONTINUE WorkspaceNextSteps WHEN no critical failures
INVARIANTS:
  ALWAYS apply graceful degradation — missing repos emit warnings not errors and available sources keep working
RULES:
  ALWAYS report all four checks before routing; critical failures = expected adapters not found OR cross-repo validation FAIL (distinct from expected degradation)
MENU ValidationFailureMenu
TITLE: Critical validation failures detected. Suggested: 1, since failures usually mean fixable source paths/adapters. Reply with a number.
OPTIONS:
  1 fix -> diagnose and fix source paths, then CONTINUE WorkspaceValidate
  2 continue -> CONTINUE WorkspaceNextSteps despite failures
  3 stop -> RETURN a WORKSPACE_FAILURE record and STOP_TURN
  INVALID -> EMIT_MENU ValidationFailureMenu
```
```pdsl
UNIT WorkspaceNextSteps
PURPOSE: Present post-setup next steps after successful workspace setup (Phase 5).
DO:
  EMIT_MENU WorkspaceNextStepsMenu
  WAIT user.reply
  RETURN a WORKSPACE_STATUS record (phase=next-steps, status=complete, next_route=null) and STOP_TURN
MENU WorkspaceNextStepsMenu
TITLE: What would you like to do next? Option 1 is the suggested default. Reply with a number or a short custom instruction.
OPTIONS:
  1 validate-repos -> RUN `{cfs_cmd} validate` from each participating repo (verifies cross-repo ID resolution), RETURN a WORKSPACE_STATUS record (phase=next-steps, status=complete, next_route=null), then STOP_TURN
  2 list-ids -> RUN `{cfs_cmd} list-ids` to confirm artifacts from all sources are visible, RETURN a WORKSPACE_STATUS record (phase=next-steps, status=complete, next_route=null), then STOP_TURN
  3 review-edit -> WAIT the workspace/source field to review or edit, RETURN a WORKSPACE_STATUS record (phase=next-steps, status=complete, next_route=null), then STOP_TURN
  4 other -> WAIT the user's next workspace action, RETURN a WORKSPACE_STATUS record (phase=next-steps, status=complete, next_route=null), then STOP_TURN
  INVALID -> EMIT_MENU WorkspaceNextStepsMenu
```
```pdsl
UNIT WorkspaceDispatch
PURPOSE: Name how phases are driven and guard the workspace safety rails.
RULES:
  ALWAYS drive the cfs workspace CLI (no sub-agents)
  ALWAYS run the setup phases in order (discover -> configure -> generate -> validate -> next-steps) and route status-only requests to analyze instead of loading all phases
  ALWAYS emit a terminal record at each phase boundary — when a phase ends in STOP_TURN or hands off to a different phase — using the record shapes (WORKSPACE_STATUS, WORKSPACE_VALIDATION, WORKSPACE_FAILURE) in the loaded setup reference; intra-phase recovery loops (a failure menu's retry/back, or re-emitting the same phase's menu) do NOT require their own record
  NEVER write workspace config without all-sources-confirmed and explicit write confirmation
  NEVER use inline storage with Git URL sources
```
