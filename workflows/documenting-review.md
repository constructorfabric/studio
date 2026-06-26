---
cf: true
type: workflow
name: cf-documenting-review
description: "Invoke when the user or another skill or workflow needs or asks to review documentation for gaps, ambiguity, inconsistency, missing context, bad structure, design mismatch, or other content problems and report findings without applying fixes."
version: 0.1
---

# cf-documenting-review

This workflow is the canonical thin semantic review entrypoint for document
artifacts.

```pdsl
UNIT DocumentingReviewPreset
PURPOSE: Run semantic document review and stop at findings.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default true, scope workflow_run)
DO:
  SET ORIGINAL_INTENT = the user's triggering documenting-review request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  SET REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-execution-refs.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-review-setup.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-review-run.md
  CONTINUE WriteDocsReviewSetup
RULES:
  - ALWAYS treat this workflow as semantic review only
```

```pdsl
UNIT WriteDocsReviewFixGate
PURPOSE: Present findings in the browser, then stop at next-actions without applying fixes.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  RUN NextActionsOffer WHEN REVIEW_FINDINGS_REMAINING == 0
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md
  RUN ReviewFindingsReportBrowser
  RUN NextActionsOffer
RULES:
  - NEVER apply fixes from documenting-review
```
