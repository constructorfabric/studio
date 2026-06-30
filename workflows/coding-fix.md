---
cf: true
type: workflow
name: cf-coding-fix
description: "Invoke when the user or another skill or workflow needs or asks to fix code issues from a review, address reported findings, apply approved fixes, resolve review comments, or patch a scoped set of known code problems."
version: 0.1
---

# cf-coding-fix

This workflow is the canonical thin code-fixing entrypoint. It consumes review
findings and applies only the approved fix scope.

```pdsl
UNIT CodingFixBootstrap
PURPOSE: Initialize thin code fixing and route into approved-finding application.
STATE:
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default true, scope workflow_run)
  SET ReviewFindingsReport: object | unset (default unset, scope workflow_run)
  SET REVIEW_FINDINGS_REMAINING: integer | unset (default unset, scope workflow_run)
  SET APPROVED_REVIEW_FINDING_IDS: list | all-critical-major | all | empty | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_SCOPE: critical-major | all | partial | none | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_APPROVED: true | false | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_PATHS: list | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_SLICES: list | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-review-fix.md
  SET REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset
  SET ReviewFindingsReport = ReviewFindingsReport from NEXT_ACTION_PAYLOAD WHEN ReviewFindingsReport == unset AND NEXT_ACTION_PAYLOAD contains ReviewFindingsReport
  SET REVIEW_FINDINGS_REMAINING = ReviewFindingsReport.total_count WHEN REVIEW_FINDINGS_REMAINING == unset AND ReviewFindingsReport != unset
  SET APPROVED_REVIEW_FINDING_IDS = APPROVED_REVIEW_FINDING_IDS from NEXT_ACTION_PAYLOAD WHEN APPROVED_REVIEW_FINDING_IDS == unset AND NEXT_ACTION_PAYLOAD contains APPROVED_REVIEW_FINDING_IDS
  SET REVIEW_FIX_SCOPE = REVIEW_FIX_SCOPE from NEXT_ACTION_PAYLOAD WHEN REVIEW_FIX_SCOPE == unset AND NEXT_ACTION_PAYLOAD contains REVIEW_FIX_SCOPE
  SET REVIEW_FIX_APPROVED = REVIEW_FIX_APPROVED from NEXT_ACTION_PAYLOAD WHEN REVIEW_FIX_APPROVED == unset AND NEXT_ACTION_PAYLOAD contains REVIEW_FIX_APPROVED
  SET REVIEW_TARGET_PATHS = REVIEW_TARGET_PATHS from NEXT_ACTION_PAYLOAD WHEN REVIEW_TARGET_PATHS == unset AND NEXT_ACTION_PAYLOAD contains REVIEW_TARGET_PATHS
  SET REVIEW_TARGET_SLICES = REVIEW_TARGET_SLICES from NEXT_ACTION_PAYLOAD WHEN REVIEW_TARGET_SLICES == unset AND NEXT_ACTION_PAYLOAD contains REVIEW_TARGET_SLICES
  EMIT "No review findings are loaded. Run cf-coding-review first to identify issues, then return here to apply fixes." WHEN ReviewFindingsReport == unset OR REVIEW_FINDINGS_REMAINING == 0
  STOP_TURN WHEN ReviewFindingsReport == unset OR REVIEW_FINDINGS_REMAINING == 0
  EMIT "No review target paths or slices are set. Run cf-coding-review first to identify the review scope." WHEN REVIEW_TARGET_PATHS == unset OR REVIEW_TARGET_SLICES == unset
  EMIT suggested_next_skills = [cf-coding-review] WHEN REVIEW_TARGET_PATHS == unset OR REVIEW_TARGET_SLICES == unset
  STOP_TURN WHEN REVIEW_TARGET_PATHS == unset OR REVIEW_TARGET_SLICES == unset
  CONTINUE CodingReviewFixGate
RULES:
  ALWAYS require explicit review findings before applying code fixes
  ALWAYS hydrate ReviewFindingsReport, approved finding IDs, fix scope, approval state, target paths, and target slices from NEXT_ACTION_PAYLOAD before checking for missing findings or missing target scope
  NEVER run semantic review from coding-fix
  ALWAYS check REVIEW_FINDINGS_REMAINING > 0 before proceeding to fix dispatch; block with explicit message and suggested_next_skills on missing findings
```

```pdsl
UNIT CodingValidate
PURPOSE: Terminate the thin code-fix workflow after approved fixes are applied.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT a concise code-fix result with applied-fix scope and changed artifacts
  RUN NextActionsOffer
```
