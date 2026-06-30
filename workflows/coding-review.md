---
cf: true
type: workflow
name: cf-coding-review
description: "Invoke when the user or another skill or workflow needs or asks to review code for bugs, gaps, regressions, design mismatches, risky behavior, security issues, or implementation problems and report findings without applying fixes."
version: 0.1
purpose: Run semantic review for code changes without owning authoring or deterministic validation.
---

# cf-coding-review

This workflow is a thin entrypoint for semantic code review. It produces
findings only and does not apply fixes or run deterministic validation.

```pdsl
UNIT CodingReviewEntry
PURPOSE: Run semantic code review and stop at findings.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default true, scope workflow_run)
DO:
  SET ORIGINAL_INTENT = the user's triggering coding-review request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  SET REVIEW_LOOP_REQUESTED = true
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-bootstrap-methodologies.md
  RUN CodingExecutionContextPrep
  RUN CodingReviewReferenceLoad
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-review-setup-run.md
  CONTINUE CodingReviewSetup
RULES:
  - ALWAYS use this workflow only for semantic review of code changes
  - ALWAYS keep deterministic validation and authoring outside this thin entrypoint
  - NEVER dispatch production code authoring from this workflow
```

```pdsl
UNIT CodingReviewBrowserAndDone
PURPOSE: Present findings in the browser, then stop at next-actions without applying fixes.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  WHEN REVIEW_FINDINGS_REMAINING == 0:
    EMIT "Review complete — no findings. Your code passed all checks."
    RUN NextActionsOffer
    STOP_TURN
  WHEN REVIEW_FINDINGS_REMAINING > 0:
    LOAD {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md
    RUN ReviewFindingsReportBrowser
    SET NEXT_ACTION_PINNED_SKILL = cf-coding-fix WHEN REVIEW_FIX_APPROVED == true
    SET NEXT_ACTION_PAYLOAD = APPROVED_REVIEW_FINDING_IDS, REVIEW_FIX_SCOPE, REVIEW_FIX_APPROVED, REVIEW_TARGET_PATHS, REVIEW_TARGET_SLICES, ReviewFindingsReport WHEN REVIEW_FIX_APPROVED == true
    RUN NextActionsOffer
    STOP_TURN
RULES:
  - NEVER apply fixes from coding-review
  - ALWAYS preserve approved finding IDs, fix scope, approval state, target paths, target slices, and ReviewFindingsReport in NEXT_ACTION_PAYLOAD when handing off to cf-coding-fix
```
