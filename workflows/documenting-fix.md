---
cf: true
type: workflow
name: cf-documenting-fix
description: "Invoke when the user or another skill or workflow needs or asks to fix documentation issues from review, address doc findings, apply approved document fixes, resolve comments on a spec or guide, or patch a known set of documentation problems."
version: 0.1
---

# cf-documenting-fix

This workflow is the canonical thin document-fixing entrypoint.

```pdsl
UNIT DocumentingFixBootstrap
PURPOSE: Initialize thin document fixing and route into approved-finding application.
STATE:
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default true, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-write-policy-fix.md
  SET REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset
  SET WRITE_DISPATCH_KIND = review-fix
  CONTINUE WriteDocsWritePolicySetup
RULES:
  - ALWAYS require explicit review findings before applying document fixes
  - NEVER run semantic review from documenting-fix
```

```pdsl
UNIT WriteDocsValidate
PURPOSE: Terminate the thin document-fix workflow after approved fixes are applied.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT a concise document-fix result with applied-fix scope and changed artifacts
  RUN NextActionsOffer
```
