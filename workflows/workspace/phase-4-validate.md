---
cf: true
type: workflow
parent: workflows/workspace.md
description: "Invoke when the workspace workflow enters Phase 4 to validate workspace reachability, adapters, and cross-repo behavior."
---

<!-- toc -->

- [Phase 4: Validate](#phase-4-validate)

<!-- /toc -->

## Phase 4: Validate

```pdsl
UNIT WorkspaceValidate

PURPOSE:
  Verify reachability, adapters, and cross-repo behavior after workspace config is written.

DO:
  Run `{cfs_cmd} --json workspace-info`      (workspace status)
  Run path-exists check + adapter check + artifacts.toml check per source (source health)
  Run `{cfs_cmd} --json list-ids`            (cross-repo IDs)
  Run `{cfs_cmd} --json validate`            (cross-repo validation)
  Report: total sources, reachable sources, sources with adapters, available cross-repo IDs
  IF critical failures detected:
    CONTINUE WorkspaceValidateFailureMenu
  ELSE:
    CONTINUE workflows/workspace/next-steps.md

RULES:
  - MUST report all four checks before routing
  - Source health check: path exists; adapter found if expected; artifacts.toml valid when adapter exists; at least one system if adapter exists

INVARIANTS:
  - MUST apply graceful degradation: missing repos emit warnings not errors; available sources continue working

NOTES:
  - remote IDs from missing sources are unavailable
  - explicit `source` entries targeting missing repos resolve to None
  - scan failures warn on stderr without blocking the operation
```

```pdsl
UNIT WorkspaceValidateFailureMenu

PURPOSE:
  Offer structured recovery choices when critical validation failures are found.

DO:
  EMIT_MENU ValidationFailureMenu
  WAIT user.reply
  STOP_TURN

MENU ValidationFailureMenu:
  TITLE: |
    Reply with 1, 2, or 3.
    Suggested: 1 because validation failures usually indicate misconfigured source paths or missing adapters that are quickly fixable.
  OPTIONS:
    1 -> Diagnose and fix source paths, then re-run validation
         CONTINUE WorkspaceValidate
    2 -> Continue to next-steps despite failures (workspace may behave unexpectedly)
         CONTINUE workflows/workspace/next-steps.md
    3 -> Stop and preserve the current workspace state
         STOP_TURN
  STOP_TOKEN:
    cancel validation; report partial result
  INVALID:
    EMIT "Reply with 1, 2, or 3."
    WAIT user.reply
    STOP_TURN

NOTES:
  Critical failures: sources with expected adapters not found, or cross-repo validation FAIL.
  See workflows/shared/stop-token-policy.md for stop-token routing.
  Graceful degradation applies to missing repos; critical failures are distinct from expected degradation.
```
