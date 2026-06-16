# Write Docs Review Setup

```pdsl
UNIT WriteDocsReviewSetup
PURPOSE: Load review modules and anti-spin rules before reviewer dispatch.
WHEN:
  REQUIRE edits have been applied to the document OR REVIEW_LOOP_REQUESTED == true
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/finding-contract.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/semantic-loop-skeleton.md
  RUN SemanticReviewNoSpinRules
  CONTINUE WriteDocsReviewTargetResolution
```

```pdsl
UNIT WriteDocsReviewTargetResolution
PURPOSE: Resolve review target paths and reviewed slices before reviewer or approved-fix dispatch.
WHEN:
  REQUIRE edits have been applied to the document OR REVIEW_LOOP_REQUESTED == true
DO:
  RUN resolve REVIEW_TARGET_PATHS to the declared read-only document path or paths under review, and REVIEW_TARGET_SLICES to the declared reviewed content slices for those targets, before reviewer dispatch or approved review-fix dispatch
  EMIT "Review target resolution is required before document review can continue. Provide the reviewed document path(s) and declared content slice(s) for the target under review." and STOP_TURN WHEN REVIEW_TARGET_PATHS == unset OR REVIEW_TARGET_SLICES == unset
  CONTINUE WriteDocsReviewRun
RULES:
  NEVER dispatch reviewers or approved review-fix writers while REVIEW_TARGET_PATHS == unset OR REVIEW_TARGET_SLICES == unset
```

```pdsl
UNIT WriteDocsReviewerDispatchPolicy
PURPOSE: Prepare scoped reviewer payloads for the selected documentation review granularity.
STATE:
  SET REVIEW_GRANULARITY: single-pass | per-methodology | per-layer (default unset, scope workflow_run)
  SET SELECTED_REVIEWER_DISPATCH_GROUP: dispatch-group | unset (default unset, scope workflow_run)
  SET REVIEWER_SCOPE_MANIFEST: manifest | unset (default unset, scope workflow_run)
DO:
  RUN WriteDocsExecutionContextPrep
  RUN WriteDocsReviewReferenceLoad
  SET REVIEW_GRANULARITY_SCOPE = "Docs review scope: single-pass covers consistency-checklist and artifact-checklist together; per-methodology dispatches cf-semantic-reviewer-consistency and cf-semantic-reviewer-artifact separately, plus cf-semantic-reviewer-freeform only for a custom review prompt; per-layer dispatches one reviewer per current category."
  RUN SemanticReviewGranularityGate WHEN REVIEW_GRANULARITY == unset
  RUN read the current consistency-checklist category map and the preset-bound ARTIFACT_CHECKLIST_PATH category map WHEN ARTIFACT_CHECKLIST_CONTEXT == preset-bound before a per-layer or per-methodology dispatch, so added categories/sections are covered automatically and never a fixed count
  RUN mark cf-semantic-reviewer-artifact scope as RELAXED/PARTIAL for generic documentation targets WHEN ARTIFACT_CHECKLIST_CONTEXT == unavailable
  SET REVIEWER_SCOPE_MANIFEST = each reviewer instance with only its assigned methodology/category slice plus REVIEW_TARGET_PATHS, REVIEW_TARGET_SLICES, kind=ARTIFACT_REVIEW_KIND, template_path=ARTIFACT_TEMPLATE_PATH, checklist_path=ARTIFACT_CHECKLIST_PATH, example_path=ARTIFACT_EXAMPLE_PATH, kit_rules_path=ARTIFACT_RULES_PATH, rules_mode STRICT when ARTIFACT_CHECKLIST_CONTEXT == preset-bound else RELAXED, any WriteDocsExploreGate-resolved resource_context as read-only context (an absolute path or reference, never inline prompt text) when RESOURCE_CONTEXT is available, otherwise no resource_context attachment, and the execution-prep-resolved audience/narrator/diagram policy data scoped per {cf-studio-path}/.core/requirements/storytelling-dimensions.md review flow-class rules; when WriteDocsExploreGate is skipped, reviewers still proceed from those execution-prep-resolved policy dimensions plus artifact/checklist policy data, and reviewers flag a warranted-but-missing or unclear diagram as a finding
  SET SELECTED_REVIEWER_DISPATCH_GROUP for REVIEW_GRANULARITY: single-pass = cf-semantic-reviewer-consistency and cf-semantic-reviewer-artifact in one combined dispatch group, plus cf-semantic-reviewer-freeform only when the user supplied a custom review prompt; per-methodology = cf-semantic-reviewer-consistency and cf-semantic-reviewer-artifact in parallel, plus cf-semantic-reviewer-freeform only when the user supplied a custom review prompt; per-layer = one reviewer per current category for each applicable methodology
RULES:
  ALWAYS preserve the selected REVIEW_GRANULARITY for the remainder of the workflow run unless the user explicitly resets it
  ALWAYS keep workflow-specific reviewer dispatches in this workflow
  NEVER let resource_context or storytelling dimensions gate a reviewer verdict
```
