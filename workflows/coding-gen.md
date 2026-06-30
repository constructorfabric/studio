---
cf: true
type: workflow
name: cf-coding-gen
description: "Invoke when the user or another skill or workflow needs or asks to write code, implement a feature, fix a bug in production code, change behavior, refactor implementation, wire a new path, or update existing source files to satisfy an approved implementation scope."
version: 0.1
purpose: Write or update production code under explicit prerequisite and result contracts, without running review or deterministic validation.
---

# cf-coding-gen

This workflow is the canonical thin code-generation skill. It writes or updates
production code only. It does not own semantic review, deterministic
validation, planning, or git finalization.

```pdsl
UNIT CodingGenBootstrap
PURPOSE: Initialize the thin code-generation workflow and route into prerequisite-aware authoring.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default false, scope workflow_run)
  SET AVAILABLE_ARTIFACTS: list | unset (default unset, scope workflow_run)
  SET REQUIRED_ARTIFACT_SPECS: list | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/skill-io-contract-load.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/handoff-suggestions.md
  RUN SkillIoContractLoad
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  SET ORIGINAL_INTENT = the user's triggering coding-gen request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  SET REVIEW_LOOP_REQUESTED = false WHEN REVIEW_LOOP_REQUESTED == unset
  CONTINUE CodingGenPrerequisites
RULES:
  - ALWAYS keep this workflow authoring-only
  - NEVER route review requests into this workflow
```

```pdsl
UNIT CodingGenPrerequisites
PURPOSE: Require the phase-scoped contract needed for thin code generation and report missing artifacts explicitly.
DO:
  SET AVAILABLE_ARTIFACTS = any caller-supplied artifact descriptors, remembered resource_context artifacts, remembered design artifacts, test artifacts, and preset-bound references available to this coding run
  SET REQUIRED_ARTIFACT_SPECS = phase-plan with why_needed "Defines the approved implementation scope and sequence for code generation", accepted_shapes phase-plan-doc or phase-plan-bundle, suggested_producers planning and code-planning, override_allowed true, override_summary "Without a phase plan the system has no approved scope — changes may be unbounded. Proceed only if you have explicit intent."; phase-dod with why_needed "Defines the phase completion criteria for the implementation work", accepted_shapes dod-list or phase-dod-doc, suggested_producers planning and code-planning, override_allowed true, override_summary "Without a phase DoD completion cannot be verified after implementation."; acceptance-criteria with why_needed "Defines the behavioral requirements the implementation must satisfy", accepted_shapes criteria-list or doc-bundle, suggested_producers planning and brainstorm, override_allowed true, override_summary "Without acceptance criteria correctness cannot be checked against requirements."; relevant-files-map with why_needed "Identifies the concrete files and code surfaces that the change may touch", accepted_shapes path-map or path-list, suggested_producers explore, override_allowed true, override_summary "Without a files map edits may touch more files than intended."
  RUN PrerequisiteCheckContract
  CONTINUE CodingGenDispatch WHEN PREREQUISITE_STATUS == ready
  CONTINUE CodingGenBlocked WHEN PREREQUISITE_STATUS == blocked
RULES:
  - ALWAYS accept a phase-plan as the primary execution contract
  - ALWAYS treat tests as strongly expected authoring inputs even when the user overrides missing test artifacts
```

```pdsl
UNIT CodingGenBlocked
PURPOSE: Emit an explicit blocked result when coding-gen prerequisites are missing.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/blocked-report.md
  RUN BlockedReportContract
RULES:
  - ALWAYS keep the blocked recovery path explicit and skill-oriented
  - NEVER auto-run a suggested producer skill from this path
```

```pdsl
UNIT CodingGenDispatch
PURPOSE: Author or update production code only.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-bootstrap-methodologies.md
  RUN CodingExecutionContextPrep
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-author-dispatch.md
  CONTINUE CodingAuthorGitSetup
RULES:
  - NEVER continue into deterministic validation from this workflow
  - NEVER continue into semantic review from this workflow
  - ALWAYS stop after authoring output is produced
```

```pdsl
UNIT CodingValidate
PURPOSE: Terminate the thin code-generation workflow after authoring output is produced.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT a completed SKILL_RESULT envelope with skill = cf-coding-gen, status = completed, produced_artifacts = code-changes summarizing the authored workspace diff or returned change scope, report_outputs = [], missing_artifacts = [], assumptions = [], and suggested_next_skills = [cf-coding-ci, cf-coding-review] by default, or derive from REVIEW_LOOP_REQUESTED state when set
  RUN NextActionsOffer
  STOP_TURN
RULES:
  - NEVER run deterministic validation from coding-gen
```
