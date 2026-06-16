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
  ALWAYS count changed lines for the granularity suggestion as the total review-surface delta across the target set: additions + deletions + modified lines, including comments and blank-line changes when they are part of the diff, aggregated across files rather than per-file; when a tiny textual diff hides a structural semantic rewrite, prefer the larger structural bucket
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
PURPOSE: Enforce the shared post-aggregation sequence ReviewFindingsReportBrowser -> ReviewFixApprovalGate before any workflow-owned fix dispatch.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md WHEN findings remain and fixes are applicable
  RUN ReviewFindingsReportBrowser WHEN findings remain and fixes are applicable
RULES:
  ALWAYS aggregate and deduplicate all findings into one ReviewFindingsReport before this unit runs
  ALWAYS treat the next visible user-facing step after aggregation as ReviewFindingsReportBrowser from fix-approval.md, never a fix-scope menu or direct fix dispatch
  ALWAYS allow ReviewFixApprovalGate to run only through the browser-owned `fix-menu` one-use continuation guard for the current ReviewFindingsReport
  ALWAYS leave workflow-owned fix dispatch and continuation targets in the owning workflow
```

```pdsl
UNIT SemanticReviewNoSpinRules
PURPOSE: State shared review-loop invariants that prevent repeated review of unchanged files.
RULES:
  ALWAYS aggregate and deduplicate all findings into one report before iterating fixes
  ALWAYS preserve the sequence reviewers -> aggregate -> ReviewFindingsReportBrowser -> ReviewFixApprovalGate -> workflow-owned fix dispatch for each fixable iteration
  ALWAYS iterate the review-fix loop until no findings remain
  NEVER enter SemanticReviewFixApprovalGate when the aggregated ReviewFindingsReport is empty; instead treat the review as complete and continue to workflow completion
  NEVER collapse aggregation directly into ReviewFixApprovalGate or a fix-scope approval menu before ReviewFindingsReportBrowser for the current ReviewFindingsReport
  NEVER re-loop the review when no fixes were applied this iteration; only an applied fix may continue to the workflow-specific validation or review continuation
```
