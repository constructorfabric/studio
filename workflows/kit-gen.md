---
cf: true
type: workflow
name: cf-kit-gen
description: "Invoke when the user or another skill or workflow needs or asks to write or update scoped kit prompt, document, or code assets for an approved phase contract."
version: 0.1
purpose: Route approved kit prompt, document, or code authoring work into the correct specialist workflow instead of duplicating specialist generation logic.
---

# cf-kit-gen

This workflow is the canonical thin generation entrypoint for kit prompt,
document, and code work.

```pdsl
UNIT KitGenBootstrap
PURPOSE: Initialize thin kit generation and route into prerequisite-aware specialist delegation.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default false, scope workflow_run)
  SET AVAILABLE_ARTIFACTS: list | unset (default unset, scope workflow_run)
  SET REQUIRED_ARTIFACT_SPECS: list | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/thin-skill-contracts.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/skill-io-contract-load.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/artifact-contract-load.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/prerequisite-check.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/blocked-report.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/handoff-suggestions.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/assumption-override.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-thin-domain-routing.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  SET ORIGINAL_INTENT = the user's triggering kit-gen request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  SET REVIEW_LOOP_REQUESTED = false WHEN REVIEW_LOOP_REQUESTED == unset
  CONTINUE KitGenPrerequisites
RULES:
  - ALWAYS keep this workflow authoring-only
  - NEVER route review requests into this workflow
```

```pdsl
UNIT KitGenPrerequisites
PURPOSE: Require the phase-scoped contract needed for thin kit generation and report missing artifacts explicitly.
DO:
  SET AVAILABLE_ARTIFACTS = any caller-supplied artifact descriptors, remembered resource_context artifacts, remembered design artifacts, and preset-bound references available to this kit run
  SET REQUIRED_ARTIFACT_SPECS = phase-plan with why_needed "Defines the approved kit-authoring scope and sequencing for this phase", accepted_shapes phase-plan-doc or phase-plan-bundle, suggested_producers planning and kit-planning, override_allowed true, override_summary "Explicit user approval is required to proceed without a phase plan"; phase-dod with why_needed "Defines the phase completion criteria for the kit work", accepted_shapes dod-list or phase-dod-doc, suggested_producers planning and kit-planning, override_allowed true, override_summary "Explicit user approval is required to proceed without a phase DoD"; acceptance-criteria with why_needed "Defines the expected kit behavior, structure, or generated artifacts for this phase", accepted_shapes criteria-list or doc-bundle, suggested_producers planning and brainstorm, override_allowed true, override_summary "Explicit user approval is required to proceed without acceptance criteria"
  RUN PrerequisiteCheckContract
  CONTINUE KitGenDispatch WHEN PREREQUISITE_STATUS == ready
```

```pdsl
UNIT KitGenDispatch
PURPOSE: Route scoped kit authoring into the correct specialist workflow.
DO:
  RUN KitThinDomainClassify
  CONTINUE KitThinRouteBlocked WHEN KIT_WORK_DOMAIN == mixed OR KIT_WORK_DOMAIN == unset OR KIT_WORK_DOMAIN == manifest
  LOAD {cf-studio-path}/.core/workflows/prompting-gen.md as the controlling kit prompt-generation workflow WHEN KIT_WORK_DOMAIN == prompting
  CONTINUE PromptingGenBootstrap WHEN KIT_WORK_DOMAIN == prompting
  LOAD {cf-studio-path}/.core/workflows/documenting-gen.md as the controlling kit document-generation workflow WHEN KIT_WORK_DOMAIN == documenting
  CONTINUE DocumentingGenBootstrap WHEN KIT_WORK_DOMAIN == documenting
  LOAD {cf-studio-path}/.core/workflows/coding-gen.md as the controlling kit code-generation workflow WHEN KIT_WORK_DOMAIN == coding
  CONTINUE CodingGenBootstrap WHEN KIT_WORK_DOMAIN == coding
RULES:
  - ALWAYS route prompt files, skills, workflows, agent instructions, and similar prompt-contract assets through prompting-gen
  - ALWAYS route documentation, checklists, examples, README files, guides, and human-facing templates through documenting-gen
  - ALWAYS route scripts, tests, generators, validators, and utilities through coding-gen
  - ALWAYS route manifest and kit-layout work through cf-kit outside this thin generation family
  - NEVER duplicate specialist authoring logic inside kit-gen
```
