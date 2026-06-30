---
cf: true
type: workflow
name: cf-prompting-planning
description: "Invoke when the user or another skill or workflow needs or asks to plan prompt or skill work, break a workflow or agent task into steps, define the authoring and review sequence, or spell out the checklist and definition of done for prompt artifacts."
version: 0.1
---

# cf-prompting-planning

This workflow is the canonical thin planning preset for prompt work.

```pdsl
UNIT PromptingPlanningPreset
PURPOSE: Bind the default prompting-planning contract, then delegate to cf-planning.
STATE:
  SET PLANNING_DOMAIN: skills (default skills, scope workflow_run)
DO:
  SET PLANNING_DOMAIN = skills
  SET RESOURCE_CONTEXT_REQUIREMENT = required
  SET DESIGN_REQUIRED_INPUT_SPECS = design-doc accepted as doc-ref or doc-bundle, design-decisions accepted as decision-list or doc-bundle, acceptance-criteria accepted as criteria-list or doc-bundle, and constraints accepted as constraint-list or doc-bundle
  SET PHASE_CHECKLIST_CONTRACT = authoring required true summary "Author or revise only the scoped skill, prompt, workflow, or agent files for the phase", deterministic-validation required true summary "Run prompting-ci and produce deterministic-report or ci-findings", semantic-review required true summary "Run prompting-review and resolve or report findings", git required true summary "Prepare commit-intent and satisfy git-commit preflight when git finalization is in scope", phase-close required true summary "Mark phase status and closure outcome explicitly"
  SET PHASE_OUTPUT_CONTRACT = phase-plan, phase-dod, skill-changes, deterministic-report, review-findings, commit-intent, phase-status
  LOAD {cf-studio-path}/.core/workflows/planning.md as the controlling integrable planning workflow
  CONTINUE PlanningBootstrap
```
