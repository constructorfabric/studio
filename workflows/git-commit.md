---
cf: true
type: workflow
name: cf-git-commit
description: "Invoke when the user or another skill or workflow needs or asks to make a commit, stage specific files, finalize scoped changes in git, or prepare a policy-compliant commit for a known set of paths."
version: 0.1
purpose: Provide a thin git finalization entrypoint that reuses the session git policy gate plus shared commit contracts, without embedding domain-specific authoring or planning logic.
---

# cf-git-commit

This workflow is the thin standalone git finalization skill. It expects an
explicit commit intent and target paths, reuses the shared session git policy
gate, and applies the commit preflight contracts before any staging or commit
action.

```pdsl
UNIT GitCommitBootstrap
PURPOSE: Load the shared runtime and commit-policy rules before git finalization begins.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET COMMIT_INTENT: object | unset (default unset, scope workflow_run)
  SET COMMIT_TARGET_PATHS: list | unset (default unset, scope workflow_run)
  SET COMMIT_POLICY_SOURCES: list | unset (default unset, scope workflow_run)
  SET COMMIT_TRAILER_REQUIREMENTS: list | unset (default unset, scope workflow_run)
  SET PREPARED_COMMIT_TRAILERS: list | unset (default unset, scope workflow_run)
  SET COMMIT_PREFLIGHT_STATUS: ready | blocked | failed | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/commit-policy-load.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/commit-trailer-prepare.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/commit-preflight-check.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/blocked-report.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/blocked-next-actions.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  SET ORIGINAL_INTENT = the user's triggering git-commit request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  CONTINUE GitCommitResolve
RULES:
  ALWAYS keep this workflow focused on git finalization only
  ALWAYS reuse GitCommitModeGate as the authoritative session git policy source
  NEVER embed authoring, review, CI, or planning behavior in this workflow
```

```pdsl
UNIT GitCommitResolve
PURPOSE: Resolve git policy, commit prerequisites, and preflight inputs before any git mutation.
DO:
  RUN GitCommitModeGate
  RUN CommitPolicyLoadContract
  SET COMMIT_POLICY_SOURCES = contributing-guide from CONTRIBUTING_GUIDE when present, trailer-requirements from COMMIT_FOOTER_CONTRACT when present, and commit-mode from GIT_COMMIT_MODE when present
  SET COMMIT_TRAILER_REQUIREMENTS = required and optional trailers derived from COMMIT_FOOTER_CONTRACT when COMMIT_FOOTER_CONTRACT is present
  RUN CommitTrailerPrepareContract
  CONTINUE GitCommitBlocked WHEN COMMIT_INTENT == unset OR COMMIT_TARGET_PATHS == unset OR COMMIT_TARGET_PATHS is empty
  RUN CommitPreflightCheckContract
  CONTINUE GitCommitBlocked WHEN COMMIT_PREFLIGHT_STATUS == blocked
  CONTINUE GitCommitFailed WHEN COMMIT_PREFLIGHT_STATUS == failed
  CONTINUE GitCommitExecute WHEN COMMIT_PREFLIGHT_STATUS == ready
RULES:
  ALWAYS require explicit COMMIT_INTENT and COMMIT_TARGET_PATHS before git finalization may proceed
  ALWAYS keep commit policy sources and prepared trailers machine-readable
  NEVER infer commit scope from unrelated changed files when COMMIT_TARGET_PATHS is absent
```

```pdsl
UNIT GitCommitBlocked
PURPOSE: Emit an explicit blocked result when git finalization prerequisites are missing.
STATE:
  SET COMMIT_PATH_CAPTURE_STATE: prompt | unset (default unset, scope workflow_run)
DO:
  WHEN COMMIT_TARGET_PATHS == unset OR COMMIT_TARGET_PATHS is empty:
    WHEN COMMIT_PATH_CAPTURE_STATE == prompt:
      SET COMMIT_TARGET_PATHS from user.reply
      SET COMMIT_PATH_CAPTURE_STATE = unset
      CONTINUE GitCommitResolve WHEN COMMIT_TARGET_PATHS != unset AND COMMIT_TARGET_PATHS is not empty
    EMIT "Which files should be committed? Reply with file paths (e.g. src/foo.py src/bar.py) or 'all staged' to commit all staged changes."
    SET COMMIT_PATH_CAPTURE_STATE = prompt
    WAIT user.reply
    STOP_TURN
  RUN BlockedReportContract
RULES:
  ALWAYS handle missing COMMIT_TARGET_PATHS with a direct recovery prompt before running BlockedReportContract
  ALWAYS keep missing commit prerequisites explicit and user-visible
  NEVER mutate git state from this path
```

```pdsl
UNIT GitCommitFailed
PURPOSE: Emit an explicit failed result when loaded policy is violated.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md WHEN not yet loaded
  EMIT a SKILL_RESULT envelope with skill = cf-git-commit, status = failed, produced_artifacts = [], report_outputs = commit preflight failure details, missing_artifacts = [], assumptions = [], and suggested_next_skills = contextual list derived from the failure reason (e.g. fix-lint when lint failed, add-trailer when trailer missing, resolve-conflict when merge conflict detected)
  RUN NextActionsOffer
RULES:
  ALWAYS use this path only when explicit commit policy or trailer rules are violated
  NEVER stage or commit after a failed preflight
```

```pdsl
UNIT GitCommitExecute
PURPOSE: Stage or commit the explicit target paths under the resolved session git policy.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  RUN stage only COMMIT_TARGET_PATHS when GIT_COMMIT_MODE == stage or GIT_COMMIT_MODE == commit
  EMIT a completed SKILL_RESULT envelope with skill = cf-git-commit, status = completed, produced_artifacts = commit-result describing the staged-path set when GIT_COMMIT_MODE == stage, report_outputs = [], missing_artifacts = [], assumptions = [], and suggested_next_skills = []
  RUN NextActionsOffer WHEN GIT_COMMIT_MODE == stage
  RUN prepare PLANNED_GIT_COMMIT_INVOCATION from COMMIT_INTENT, COMMIT_TARGET_PATHS, CONTRIBUTING_GUIDE requirements, and PREPARED_COMMIT_TRAILERS WHEN GIT_COMMIT_MODE == commit
  EMIT the planned commit message, trailer set, and scoped paths for review WHEN GIT_COMMIT_MODE == commit
  EMIT "Proceed with this commit? Reply 'yes' to commit, 'edit' to change the message, or 'cancel' to stop." WHEN GIT_COMMIT_MODE == commit
  WAIT user.reply WHEN GIT_COMMIT_MODE == commit
  STOP_TURN WHEN GIT_COMMIT_MODE == commit
  CONTINUE GitCommitExecuteConfirm
RULES:
  ALWAYS honor GIT_COMMIT_MODE strictly: stage means no commit; commit means stage plus commit; none never reaches this unit
```

```pdsl
UNIT GitCommitExecuteConfirm
PURPOSE: Route the user's confirmation reply and execute the commit on 'yes'.
DO:
  STOP_TURN WHEN user.reply == "cancel"
  CONTINUE GitCommitMessageEdit WHEN user.reply == "edit"
  EMIT "Please reply 'yes' to confirm the commit, 'edit' to change the message, or 'cancel' to stop." WHEN user.reply != "yes"
  WAIT user.reply WHEN user.reply != "yes"
  STOP_TURN WHEN user.reply != "yes"
  CONTINUE GitCommitExecuteConfirm WHEN user.reply != "yes"
  SET GIT_COMMIT_AUDIT_PHASE = preflight
  RUN GitCommitCommitAudit
  RUN create the git commit for COMMIT_TARGET_PATHS using COMMIT_INTENT plus required project-policy and Studio trailers
  SET STUDIO_CREATED_COMMIT_SHA = the created commit sha
  SET GIT_COMMIT_AUDIT_PHASE = postcommit
  RUN GitCommitCommitAudit
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT a completed SKILL_RESULT envelope with skill = cf-git-commit, status = completed, produced_artifacts = commit-result describing the created commit sha and scoped paths, report_outputs = [], missing_artifacts = [], assumptions = [], and suggested_next_skills = []
  RUN NextActionsOffer
RULES:
  ALWAYS scope git mutations to COMMIT_TARGET_PATHS only
  ALWAYS run trailer audit before and after the commit
  NEVER execute the commit unless user.reply == "yes"; re-prompt on any unrecognized reply
```

```pdsl
UNIT GitCommitMessageEdit
PURPOSE: Let the user revise the planned commit message before the commit is created.
DO:
  EMIT the current PLANNED_GIT_COMMIT_INVOCATION message and trailers for review
  EMIT "Enter your revised commit message, or reply 'cancel' to stop."
  WAIT user.reply
  STOP_TURN
  CONTINUE GitCommitMessageEditExecute
RULES:
  ALWAYS stop the turn after emitting the message prompt; execution happens in GitCommitMessageEditExecute on resume
```

```pdsl
UNIT GitCommitMessageEditExecute
PURPOSE: Execute the commit with the user's revised message.
DO:
  STOP_TURN WHEN user.reply == "cancel"
  SET PLANNED_GIT_COMMIT_INVOCATION = updated commit message from user.reply
  SET GIT_COMMIT_AUDIT_PHASE = preflight
  RUN GitCommitCommitAudit
  RUN create the git commit for COMMIT_TARGET_PATHS using PLANNED_GIT_COMMIT_INVOCATION
  SET STUDIO_CREATED_COMMIT_SHA = the created commit sha
  SET GIT_COMMIT_AUDIT_PHASE = postcommit
  RUN GitCommitCommitAudit
  EMIT a completed SKILL_RESULT envelope with skill = cf-git-commit, status = completed, produced_artifacts = commit-result describing the created commit sha and scoped paths, report_outputs = [], missing_artifacts = [], assumptions = [], and suggested_next_skills = []
  RUN NextActionsOffer
RULES:
  ALWAYS use the user-supplied revised message verbatim; NEVER auto-append trailers that were not in the original PLANNED_GIT_COMMIT_INVOCATION
  NEVER commit without a non-empty commit message
  ALWAYS scope git mutations to COMMIT_TARGET_PATHS only
  ALWAYS run trailer audit before and after a Studio-created commit
  ALWAYS show the planned commit message, trailers, and file scope to the user before executing the git commit; wait for explicit confirmation
  NEVER stage or commit files outside the explicit commit scope
```
