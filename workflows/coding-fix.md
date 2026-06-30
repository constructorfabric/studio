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
  SET REVIEW_TARGET_PATHS: list | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_SLICES: list | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-review-fix.md
  SET REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset
  EMIT "No review findings are loaded. Run cf-coding-review first to identify issues, then return here to apply fixes." WHEN ReviewFindingsReport == unset OR REVIEW_FINDINGS_REMAINING == 0
  STOP_TURN WHEN ReviewFindingsReport == unset OR REVIEW_FINDINGS_REMAINING == 0
  EMIT "No review target paths or slices are set. Run cf-coding-review first to identify the review scope." WHEN REVIEW_TARGET_PATHS == unset OR REVIEW_TARGET_SLICES == unset
  EMIT suggested_next_skills = [cf-coding-review] WHEN REVIEW_TARGET_PATHS == unset OR REVIEW_TARGET_SLICES == unset
  STOP_TURN WHEN REVIEW_TARGET_PATHS == unset OR REVIEW_TARGET_SLICES == unset
  CONTINUE CodingReviewFixGate
RULES:
  - ALWAYS require explicit review findings before applying code fixes
  - NEVER run semantic review from coding-fix
  - ALWAYS check REVIEW_FINDINGS_REMAINING > 0 before proceeding to fix dispatch; block with explicit message and suggested_producers on missing findings
```

```pdsl
UNIT CodingValidate
PURPOSE: Terminate the thin code-fix workflow after approved fixes are applied.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT a concise code-fix result with applied-fix scope and changed artifacts
  RUN NextActionsOffer
```
