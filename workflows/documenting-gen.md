---
cf: true
type: workflow
name: cf-documenting-gen
description: "Invoke when the user or another skill or workflow needs or asks to write or update documentation such as a README, guide, spec, ADR, design doc, feature doc, report, or other project document within an approved scope."
version: 0.1
purpose: Write or update document artifacts under explicit prerequisite and result contracts, without running review or deterministic validation.
---

# cf-documenting-gen

This workflow is the canonical thin document-generation skill. It writes or
updates document artifacts only.

```pdsl
UNIT DocumentingGenBootstrap
PURPOSE: Initialize thin document generation and route into prerequisite-aware authoring.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default false, scope workflow_run)
  SET AVAILABLE_ARTIFACTS: list | unset (default unset, scope workflow_run)
  SET REQUIRED_ARTIFACT_SPECS: list | unset (default unset, scope workflow_run)
  SET AUTHOR_TARGET_PATHS: list | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_PATHS: list | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_SLICES: list | unset (default unset, scope workflow_run)
  SET ARTIFACT_CHECKLIST_CONTEXT: preset-bound | unavailable | unset (default unset, scope workflow_run)
  SET ARTIFACT_REVIEW_KIND: string | null | unset (default unset, scope workflow_run)
  SET ARTIFACT_TEMPLATE_PATH: path | null | unset (default unset, scope workflow_run)
  SET ARTIFACT_RULES_PATH: path | null | unset (default unset, scope workflow_run)
  SET ARTIFACT_CHECKLIST_PATH: path | null | unset (default unset, scope workflow_run)
  SET ARTIFACT_EXAMPLE_PATH: path | null | unset (default unset, scope workflow_run)
  SET DOC_AUDIENCE_DIMENSION: resolved | unset (default unset, scope workflow_run)
  SET DOC_NARRATOR_DIMENSION: resolved | unset (default unset, scope workflow_run)
  SET DOC_DIAGRAM_DIMENSION: resolved | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/skill-io-contract-load.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/handoff-suggestions.md
  RUN SkillIoContractLoad
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-bootstrap-intent.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  RUN WriteDocsBootstrapIntentContext
  SET REVIEW_LOOP_REQUESTED = false WHEN REVIEW_LOOP_REQUESTED == unset
  CONTINUE DocumentingGenPrerequisites
RULES:
  - ALWAYS keep this workflow authoring-only
  - NEVER route review requests into this workflow
```

```pdsl
UNIT DocumentingGenPrerequisites
PURPOSE: Require the phase-scoped contract needed for thin document generation and report missing artifacts explicitly.
DO:
  SET AVAILABLE_ARTIFACTS = any caller-supplied artifact descriptors, remembered resource_context artifacts, remembered design artifacts, and preset-bound references available to this documenting run
  SET REQUIRED_ARTIFACT_SPECS = phase-plan with why_needed "Defines the approved document scope and sequencing for this phase", accepted_shapes phase-plan-doc or phase-plan-bundle, suggested_producers planning and documenting-planning, override_allowed true, override_summary "Explicit user approval is required to proceed without a phase plan"; phase-dod with why_needed "Defines the phase completion criteria for the document work", accepted_shapes dod-list or phase-dod-doc, suggested_producers planning and documenting-planning, override_allowed true, override_summary "Explicit user approval is required to proceed without a phase DoD"; acceptance-criteria with why_needed "Defines the content and behavior expectations the document must satisfy", accepted_shapes criteria-list or doc-bundle, suggested_producers planning and brainstorm, override_allowed true, override_summary "Explicit user approval is required to proceed without acceptance criteria"
  RUN PrerequisiteCheckContract
  CONTINUE DocumentingGenDispatch WHEN PREREQUISITE_STATUS == ready
```

```pdsl
UNIT DocumentingGenDispatch
PURPOSE: Author or update document artifacts only.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-execution-refs.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-author-dispatch.md
  CONTINUE WriteDocsAuthorDispatch
RULES:
  - NEVER continue into deterministic validation from this workflow
  - NEVER continue into semantic review from this workflow
```

```pdsl
UNIT WriteDocsValidate
PURPOSE: Terminate the thin document-generation workflow after authoring output is produced.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT a completed SKILL_RESULT envelope with skill = cf-documenting-gen, status = completed, produced_artifacts = doc-changes describing PATHS_WRITTEN when document paths were captured or a doc-changes summary of the authored document scope otherwise, report_outputs = [], missing_artifacts = [], assumptions = [], and suggested_next_skills = []
  RUN NextActionsOffer
```
