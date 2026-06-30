# Commit Preflight Check

```pdsl
UNIT CommitPreflightCheckContract
PURPOSE: Validate shared commit prerequisites before git delegation or commit authoring finalization.
STATE:
  SET COMMIT_INTENT: object | unset (default unset, scope workflow_run)
  SET COMMIT_POLICY_SOURCES: list | unset (default unset, scope workflow_run)
  SET PREPARED_COMMIT_TRAILERS: list | unset (default unset, scope workflow_run)
  SET COMMIT_PREFLIGHT_STATUS: ready | blocked | failed | unset (default unset, scope workflow_run)
  SET GIT_COMMIT_MODE: commit | stage | none | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/commit-policy-load.md WHEN CommitPolicyLoadContract is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/commit-trailer-prepare.md WHEN CommitTrailerPrepareContract is not yet loaded
  RUN CommitPreflightInputContract
  RUN CommitPreflightOutcomeContract
RULES:
  ALWAYS use this module before a git-commit thin skill executes or an authoring workflow delegates commit finalization
  ALWAYS keep commit preflight separate from the actual git commit operation
  NEVER use this module to mutate the worktree or synthesize missing commit inputs silently
```

```pdsl
UNIT CommitPreflightInputContract
PURPOSE: Define the minimum machine-readable inputs for commit readiness checks.
RULES:
  ALWAYS require COMMIT_INTENT to be explicit before preflight may report ready
  ALWAYS require any active COMMIT_POLICY_SOURCES to be loaded before preflight may report ready
  ALWAYS require required PREPARED_COMMIT_TRAILERS to be present before preflight may report ready
  ALWAYS allow optional PHASE_CLOSE_STATE and REQUIRED_REPORT_REFS inputs so callers can enforce project-specific closure policy
  NEVER treat an implicit future intent to commit as equivalent to COMMIT_INTENT
```

```pdsl
UNIT CommitPreflightOutcomeContract
PURPOSE: Keep commit preflight outcomes canonical and machine-readable.
DO:
  SET COMMIT_PREFLIGHT_STATUS = failed WHEN GIT_COMMIT_MODE == none
  SET COMMIT_PREFLIGHT_STATUS = blocked WHEN COMMIT_PREFLIGHT_STATUS == unset AND COMMIT_INTENT == unset
  SET COMMIT_PREFLIGHT_STATUS = blocked WHEN COMMIT_PREFLIGHT_STATUS == unset AND COMMIT_POLICY_SOURCES == unset
  SET COMMIT_PREFLIGHT_STATUS = blocked WHEN COMMIT_PREFLIGHT_STATUS == unset AND GIT_COMMIT_MODE == commit AND PREPARED_COMMIT_TRAILERS == unset
  SET COMMIT_PREFLIGHT_STATUS = blocked WHEN COMMIT_PREFLIGHT_STATUS == unset AND GIT_COMMIT_MODE == commit AND one or more required PREPARED_COMMIT_TRAILERS entries still have trailer_value unset
  SET COMMIT_PREFLIGHT_STATUS = ready WHEN COMMIT_PREFLIGHT_STATUS == unset AND GIT_COMMIT_MODE == stage AND PREPARED_COMMIT_TRAILERS is provided
  SET COMMIT_PREFLIGHT_STATUS = ready WHEN COMMIT_PREFLIGHT_STATUS == unset AND GIT_COMMIT_MODE == commit
RULES:
  ALWAYS require COMMIT_PREFLIGHT_STATUS to be one of ready, blocked, or failed
  ALWAYS use ready only when all declared commit prerequisites are satisfied
  ALWAYS use blocked when required inputs are missing, unresolved, or intentionally deferred
  ALWAYS use failed when explicit loaded policy is violated by the available inputs
  ALWAYS keep missing or violating prerequisites addressable as explicit machine-readable entries chosen by the caller
  NEVER emit completed or completed-with-assumptions from commit preflight
```
