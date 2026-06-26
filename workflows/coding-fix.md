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
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-review-fix.md
  SET REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset
  CONTINUE CodingReviewFixGate
RULES:
  - ALWAYS require explicit review findings before applying code fixes
  - NEVER run semantic review from coding-fix
```

```pdsl
UNIT CodingValidate
PURPOSE: Terminate the thin code-fix workflow after approved fixes are applied.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT a concise code-fix result with applied-fix scope and changed artifacts
  RUN NextActionsOffer
```
