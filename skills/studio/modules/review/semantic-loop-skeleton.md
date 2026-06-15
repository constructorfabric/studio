# Semantic Review Loop Skeleton

```pdsl
UNIT SemanticReviewGranularityGate
PURPOSE: Ask the user to choose semantic review depth using a shared three-level contract.
STATE:
  SET REVIEW_GRANULARITY: single-pass | per-methodology | per-layer (default unset, scope workflow_run)
  SET REVIEW_GRANULARITY_SCOPE: string (default unset, scope workflow_run)
WHEN:
  REQUIRE REVIEW_GRANULARITY == unset
  REQUIRE REVIEW_GRANULARITY_SCOPE is set
DO:
  EMIT REVIEW_GRANULARITY_SCOPE
  EMIT_MENU ReviewGranularityMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer the granularity choice with a suggested level by change size: tiny edit (≤10 changed lines) -> single-pass, moderate edit (11–50 changed lines) -> per-methodology, new file/module/document or large/structural change (>50 changed lines) -> per-layer
  ALWAYS explain the owning workflow's concrete methodologies or reviewer groups before showing the shared menu
  ALWAYS treat single-pass as fastest, per-methodology as balanced, and per-layer as most thorough
MENU ReviewGranularityMenu
TITLE: Choose review depth — the suggested level fits the change size.
OPTIONS:
  1 single-pass -> SET REVIEW_GRANULARITY = single-pass; review all applicable methodologies in one combined pass (fastest; suggested for tiny edits)
  2 per-methodology -> SET REVIEW_GRANULARITY = per-methodology; review one dispatch group per applicable methodology (balanced; suggested for moderate edits)
  3 per-layer -> SET REVIEW_GRANULARITY = per-layer; review every category/layer each methodology defines, in parallel when available (most thorough; suggested for new files/modules/documents or structural changes)
  INVALID -> EMIT_MENU ReviewGranularityMenu
```

```pdsl
UNIT SemanticReviewFixApprovalGate
PURPOSE: Load and run the shared fix-approval gate after workflow-specific review aggregation.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md and RUN ReviewFindingsReportBrowser before ReviewFixApprovalGate WHEN findings remain and fixes are applicable
  RUN ReviewFixApprovalGate WHEN findings remain and fixes are applicable
RULES:
  ALWAYS aggregate and deduplicate all findings into one report before this unit runs
  ALWAYS present ReviewFindingsReportBrowser from fix-approval before the fix-scope menu so the user can inspect, page through, and mark findings
  ALWAYS leave workflow-specific author/fix dispatch and continuation targets in the owning workflow
```

```pdsl
UNIT SemanticReviewNoSpinRules
PURPOSE: State shared review-loop invariants that prevent repeated review of unchanged files.
RULES:
  ALWAYS aggregate and deduplicate all findings into one report before iterating fixes
  ALWAYS iterate the review-fix loop until no findings remain
  NEVER re-loop the review when no fixes were applied this iteration; only an applied fix may continue to the workflow-specific validation or review continuation
```
