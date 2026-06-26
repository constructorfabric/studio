---
cf: true
type: workflow
name: cf-planning
description: "Invoke when the user or another skill or workflow needs or asks to plan work inside a workflow, break a task into reusable phases, define phase checklists, or produce an integrable plan and DoD that other skills can consume directly."
version: 0.1
purpose: Build reusable phase-plan and phase-dod outputs that fit directly into thin-skill pipelines and prerequisite-driven workflows.
---

# cf-planning

This skill is the thin integrable planner. It validates planning prerequisites,
uses caller-owned phase checklist contracts, and produces reusable planning
artifacts. It does not package standalone execution plans.

```pdsl
UNIT PlanningBootstrap
PURPOSE: Load the shared runtime rules needed before integrable planning begins.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET AVAILABLE_ARTIFACTS: list | unset (default unset, scope workflow_run)
  SET DESIGN_INPUT_STATUS: ready | blocked | unset (default unset, scope workflow_run)
  SET RESOURCE_CONTEXT_STATUS: ready | blocked | skipped | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/planning-runtime.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  SET ORIGINAL_INTENT = the user's triggering planning request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  CONTINUE PlanningDispatch
RULES:
  - ALWAYS keep this workflow planning-only
  - ALWAYS treat planning outputs as reusable pipeline artifacts, not as standalone execution packages
  - NEVER write plan.toml, phase briefs, or compiled phase files from this workflow
```

```pdsl
UNIT PlanningDispatch
PURPOSE: Resolve caller-owned planning inputs, check prerequisites, and branch to blocked or build paths.
DO:
  RUN PlanningRuntimeContractLoad
  SET AVAILABLE_ARTIFACTS = any caller-supplied artifact descriptors, remembered resource_context artifacts, remembered design artifacts, and preset-bound references available to this planning run
  RUN PlanningInputContract
  RUN PlanningPrerequisiteResolution
  CONTINUE PlanningBlocked WHEN DESIGN_INPUT_STATUS == blocked OR RESOURCE_CONTEXT_STATUS == blocked
  CONTINUE PlanningBuild WHEN DESIGN_INPUT_STATUS == ready AND RESOURCE_CONTEXT_STATUS != blocked
RULES:
  - ALWAYS allow RESOURCE_CONTEXT_STATUS == skipped or ready on the build path when the caller declared resource context optional or not-needed
  - NEVER continue to planning synthesis while a required prerequisite remains blocked
```

```pdsl
UNIT PlanningBlocked
PURPOSE: Emit the canonical blocked result when integrable planning lacks required inputs.
DO:
  RUN BlockedReportContract
RULES:
  - ALWAYS keep the blocked recovery path explicit and skill-oriented
  - NEVER auto-run a suggested producer skill from this path
```

```pdsl
UNIT PlanningBuild
PURPOSE: Build reusable planning artifacts from caller-owned phase checklist and output contracts.
DO:
  RUN PlanningPhaseContract
  RUN PlanningChecklistContract
  RUN PlanningLegacySeparationContract
  RUN synthesize a phase-plan whose phases are defined by the requested outcome, the available artifacts, and PHASE_CHECKLIST_CONTRACT, with each phase expressing explicit prerequisites, skill_sequence, expected_outputs, checklist items, and completion_signal
  RUN synthesize a phase-dod artifact that normalizes per-phase completion expectations, checklist requirements, and expected outputs for downstream execution skills
  CONTINUE PlanningCompletion
RULES:
  - ALWAYS structure phases around reusable standalone skills and canonical artifacts
  - ALWAYS prefer explicit phase boundaries that can be resumed, reviewed, or marked complete independently
  - NEVER compile the plan into standalone prompts or execution files
```

```pdsl
UNIT PlanningCompletion
PURPOSE: Emit the canonical planning result envelope with reusable planning artifacts.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT a SKILL_RESULT envelope with type = SKILL_RESULT, skill = cf-planning, status = completed or completed-with-assumptions when assumptions were used, produced_artifacts = phase-plan and phase-dod descriptors, report_outputs = [], missing_artifacts = [], assumptions = any explicit planning assumptions, and suggested_next_skills = the first executable skills implied by the phase sequence
  RUN NextActionsOffer
RULES:
  - ALWAYS keep planning outputs artifact-oriented and machine-readable
  - ALWAYS use completed-with-assumptions only when the plan depended on explicit unresolved assumptions
  - NEVER claim semantic review or CI completion from this workflow
  - NEVER include cf-explain as a suggested next action when produced_artifacts are of type phase-plan or phase-dod; instead always surface the first executable skill from the phase sequence as the suggested action
```
