---
cf: true
type: workflow
name: cf-skills-planning
description: "Invoke when the user explicitly asks for `skills-planning` or `cf-skills-planning` by name."
version: 0.1
purpose: Thin preset that binds skill/prompt-planning prerequisites and default phase checklist sections, then delegates planning to the integrable cf-planning workflow.
---

# cf-skills-planning

This workflow is a thin preset over `cf-planning`. It binds skills-planning
prerequisites and a default prompt/skill/workflow phase checklist contract.

```pdsl
UNIT SkillsPlanningPreset
PURPOSE: Bind the default skills-planning contract, then delegate to cf-planning.
STATE:
  SET PLANNING_DOMAIN: skills (default skills, scope workflow_run)
DO:
  SET PLANNING_DOMAIN = skills
  SET RESOURCE_CONTEXT_REQUIREMENT = required
  SET DESIGN_REQUIRED_INPUT_SPECS = design-doc accepted as doc-ref or doc-bundle, design-decisions accepted as decision-list or doc-bundle, acceptance-criteria accepted as criteria-list or doc-bundle, and constraints accepted as constraint-list or doc-bundle
  SET PHASE_CHECKLIST_CONTRACT = authoring required true summary "Author or revise only the scoped skill, prompt, workflow, or agent files for the phase", deterministic-validation required true summary "Run skills-ci and produce deterministic-report or ci-findings", semantic-review required true summary "Run skills-review and resolve or report findings", git required true summary "Prepare commit-intent and satisfy git-commit preflight when git finalization is in scope", phase-close required true summary "Mark phase status and closure outcome explicitly"
  SET PHASE_OUTPUT_CONTRACT = phase-plan, phase-dod, skill-changes, deterministic-report, review-findings, commit-intent, phase-status
  LOAD {cf-studio-path}/.core/workflows/planning.md as the controlling integrable planning workflow
  CONTINUE PlanningBootstrap
RULES:
  - ALWAYS require resource-context or relevant-files-map for skills planning because workflow and module boundaries matter to prompt changes
  - ALWAYS keep skills-ci and skills-review explicit in the checklist so authoring stays thin
  - NEVER plan hidden fix loops outside the declared phase sequence
```
