# Write Docs Review Run

```pdsl
UNIT WriteDocsReviewRun
PURPOSE: Dispatch reviewer sub-agents and aggregate their findings into one report.
WHEN:
  REQUIRE REVIEW_TARGET_PATHS != unset
  REQUIRE REVIEW_TARGET_SLICES != unset
DO:
  RUN WriteDocsReviewerDispatchPolicy
  RUN SubAgentDispatch for SELECTED_REVIEWER_DISPATCH_GROUP before launching reviewer instances
  RUN SELECTED_REVIEWER_DISPATCH_GROUP with REVIEWER_SCOPE_MANIFEST
  RUN aggregation of every reviewer's findings into one deduplicated ReviewFindingsReport with stable finding IDs and every ReviewFindingContract field
  CONTINUE WriteDocsReviewFixGate
RULES:
  ALWAYS scope each reviewer to only its assigned slice and run independent reviewers in parallel
```

```pdsl
UNIT WriteDocsReviewFixGate
PURPOSE: Present review findings, gate fix approval, and route to fix dispatch or outcome.
WHEN:
  REQUIRE REVIEW_TARGET_PATHS != unset
  REQUIRE REVIEW_TARGET_SLICES != unset
DO:
  RUN SemanticReviewFixApprovalGate WHEN findings remain and fixes are applicable
  CONTINUE WriteDocsReviewFixDispatch WHEN REVIEW_FIX_APPROVED == true
  CONTINUE WriteDocsReviewFixOutcome
```

```pdsl
UNIT WriteDocsReviewFixDispatch
PURPOSE: Resolve shared write policy before dispatching approved document review fixes.
WHEN:
  REQUIRE REVIEW_FIX_APPROVED == true
DO:
  SET WRITE_DISPATCH_KIND = review-fix
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-write-policy-fix.md
  CONTINUE WriteDocsWritePolicySetup
```
