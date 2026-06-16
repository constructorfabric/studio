# Workspace Validate

```pdsl
UNIT WorkspaceValidate
PURPOSE: Verify reachability, adapters, and cross-repo behavior after config is written (Phase 4).
DO:
  RUN `{cfs_cmd} --json workspace-info` (status)
  RUN per-source health — path exists; adapter found if expected; artifacts.toml valid when an adapter exists
  RUN `{cfs_cmd} --json list-ids` (cross-repo IDs)
  RUN `{cfs_cmd} --json validate` (cross-repo validation)
  RUN WorkspaceValidateSummarize
  LOAD {cf-studio-path}/.core/skills/studio/modules/workspace-next-dispatch.md
  EMIT_MENU ValidationFailureMenu WHEN critical failures are detected
  CONTINUE WorkspaceNextSteps WHEN no critical failures
INVARIANTS:
  ALWAYS apply graceful degradation — missing repos emit warnings not errors and available sources keep working
RULES:
  ALWAYS report all four checks before routing; critical failures = expected adapters not found OR cross-repo validation FAIL (distinct from expected degradation)
```

```pdsl
UNIT WorkspaceValidateSummarize
PURPOSE: Emit the validation summary and return the validation record before routing.
DO:
  EMIT the report — total sources, reachable, with adapters, available cross-repo IDs
  RETURN a WORKSPACE_VALIDATION record
MENU ValidationFailureMenu
TITLE: Critical validation failures detected. Suggested: 1, since failures usually mean fixable source paths/adapters. Reply with a number.
OPTIONS:
  1 fix -> diagnose and fix source paths, then CONTINUE WorkspaceValidate
  2 continue -> CONTINUE WorkspaceNextSteps despite failures
  3 stop -> RETURN a WORKSPACE_FAILURE record and STOP_TURN
  INVALID -> EMIT_MENU ValidationFailureMenu
```
