# Coding Review Setup

```pdsl
UNIT CodingReviewSetup
PURPOSE: Load review modules and anti-spin rules before reviewer dispatch.
WHEN:
  REQUIRE edits have been applied to the code OR REVIEW_LOOP_REQUESTED == true
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/finding-contract.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/semantic-loop-skeleton.md
  RUN SemanticReviewNoSpinRules
  CONTINUE CodingReviewRun
```

```pdsl
UNIT CodingReviewerDispatchPolicy
PURPOSE: Prepare scoped reviewer payloads for the selected coding review granularity.
STATE:
  SET SELECTED_REVIEWER_DISPATCH_GROUP: dispatch-group | unset (default unset, scope workflow_run)
  SET REVIEWER_SCOPE_MANIFEST: manifest | unset (default unset, scope workflow_run)
DO:
  RUN read each methodology's current category/layer map (code-checklist categories, bug-finding layers, consistency-checklist categories) before a per-layer or per-methodology dispatch, so added layers are covered automatically and never a fixed count
  SET REVIEWER_SCOPE_MANIFEST = each reviewer instance with only its assigned methodology/category/layer slice and any CodingExploreGate-resolved resource_context as read-only context (an absolute path or reference, never inline prompt text)
  SET SELECTED_REVIEWER_DISPATCH_GROUP for REVIEW_GRANULARITY: single-pass = cf-semantic-reviewer-code, cf-code-bug-finder, and cf-semantic-reviewer-consistency in one combined dispatch group; per-methodology = one reviewer per methodology; per-layer = one reviewer per category/layer for every category/layer each methodology defines, run in parallel
RULES:
  ALWAYS keep workflow-specific reviewer dispatches in this workflow
  NEVER let resource_context gate a reviewer verdict
```

```pdsl
UNIT CodingReviewRun
PURPOSE: Gate review granularity, dispatch reviewer sub-agents, and aggregate their findings into one report.
STATE:
  SET REVIEW_GRANULARITY: single-pass | per-methodology | per-layer (default unset, scope workflow_run)
WHEN:
  REQUIRE edits have been applied to the code OR REVIEW_LOOP_REQUESTED == true
DO:
  SET REVIEW_GRANULARITY_SCOPE = "Coding review scope: single-pass covers code-checklist, bug-finding, and consistency-checklist together; per-methodology dispatches cf-semantic-reviewer-code, cf-code-bug-finder, and cf-semantic-reviewer-consistency separately; per-layer dispatches one reviewer per current category/layer from those methodologies."
  RUN SemanticReviewGranularityGate WHEN REVIEW_GRANULARITY == unset
  RUN CodingReviewerDispatchPolicy
  RUN SubAgentDispatch for SELECTED_REVIEWER_DISPATCH_GROUP before launching reviewer instances
  RUN SELECTED_REVIEWER_DISPATCH_GROUP with REVIEWER_SCOPE_MANIFEST
  RUN AggregateReviewFindings
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-review-fix.md
  CONTINUE CodingReviewFixGate
RULES:
  ALWAYS scope each reviewer to only its assigned slice (all methodologies / one methodology / one category-or-layer) and run independent reviewers in parallel
```

```pdsl
UNIT AggregateReviewFindings
PURPOSE: Merge reviewer outputs into one deduplicated ReviewFindingsReport with stable finding IDs.
DO:
  RUN collect every finding emitted by the active reviewer dispatch group
  RUN normalize each finding to ReviewFindingContract fields before merge, preserving agent-provided location, evidence, impact, verification, confidence, and any applicable mechanical classification fields
  RUN deduplicate materially identical findings across reviewers by path, location, category, evidence, and root cause
  RUN assign stable finding IDs in deterministic sorted order using ReviewFindingContract's ID format rules
  RUN set ReviewFindingsReport = the deduplicated findings plus any aggregated metadata needed by ReviewFindingsReportBrowser and ReviewFixApprovalGate
RULES:
  ALWAYS preserve every surviving finding's ReviewFindingContract fields after deduplication
  NEVER emit duplicate finding IDs inside the aggregated ReviewFindingsReport
```
