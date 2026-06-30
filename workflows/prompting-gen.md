---
cf: true
type: workflow
name: cf-prompting-gen
description: "Invoke when the user or another skill or workflow needs or asks to write or update a prompt, skill, workflow, agent instruction, system prompt, or other prompt-driven artifact within an approved scope."
version: 0.1
purpose: Write or update prompt artifacts under explicit prerequisite and result contracts, without running review or deterministic validation.
---

# cf-prompting-gen

This workflow is the canonical thin generation skill for prompts, skills,
workflows, agents, and system instructions.

```pdsl
UNIT PromptingGenBootstrap
PURPOSE: Initialize thin prompt generation and route into prerequisite-aware authoring.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default false, scope workflow_run)
  SET AVAILABLE_ARTIFACTS: list | unset (default unset, scope workflow_run)
  SET REQUIRED_ARTIFACT_SPECS: list | unset (default unset, scope workflow_run)
  SET PATHS_WRITTEN: list | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/skill-io-contract-load.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/handoff-suggestions.md
  RUN SkillIoContractLoad
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  SET ORIGINAL_INTENT = the user's triggering prompting-gen request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  SET REVIEW_LOOP_REQUESTED = false WHEN REVIEW_LOOP_REQUESTED == unset
  CONTINUE PromptingGenPrerequisites
RULES:
  - ALWAYS keep this workflow authoring-only
  - NEVER route review requests into this workflow
```

```pdsl
UNIT PromptingGenPrerequisites
PURPOSE: Require the phase-scoped contract needed for thin prompt generation and report missing artifacts explicitly.
DO:
  SET AVAILABLE_ARTIFACTS = any caller-supplied artifact descriptors, remembered resource_context artifacts, remembered design artifacts, and preset-bound references available to this prompting run
  SET REQUIRED_ARTIFACT_SPECS = phase-plan with why_needed "Defines the approved prompt or skill scope and sequence for this phase", accepted_shapes phase-plan-doc or phase-plan-bundle, suggested_producers planning and prompting-planning, override_allowed true, override_summary "Explicit user approval is required to proceed without a phase plan"; phase-dod with why_needed "Defines the phase completion criteria for the prompt work", accepted_shapes dod-list or phase-dod-doc, suggested_producers planning and prompting-planning, override_allowed true, override_summary "Explicit user approval is required to proceed without a phase DoD"; acceptance-criteria with why_needed "Defines the routing, behavior, and output expectations the prompt artifact must satisfy", accepted_shapes criteria-list or doc-bundle, suggested_producers planning and brainstorm, override_allowed true, override_summary "Explicit user approval is required to proceed without acceptance criteria"
  RUN PrerequisiteCheckContract
  CONTINUE PromptingGenDispatch WHEN PREREQUISITE_STATUS == ready
```

```pdsl
UNIT PromptingGenDispatch
PURPOSE: Author or update prompt artifacts only.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-bootstrap-refs.md
  RUN WriteSkillsExecutionContextPrep
  RUN WriteSkillsExecutionReferenceLoad
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-author-dispatch.md
  CONTINUE WriteSkillsAuthorGitSetup
RULES:
  - NEVER continue into deterministic validation from this workflow
  - NEVER continue into semantic review from this workflow
```

```pdsl
UNIT WriteSkillsValidate
PURPOSE: Terminate the thin prompt-generation workflow after authoring output is produced.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-completion.md
  CONTINUE WriteSkillsCompletion
```
