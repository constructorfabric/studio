---
cf: true
type: workflow
name: cf-documenting-planning
description: "Invoke when the user or another skill or workflow needs or asks to plan documentation work, break a doc task into steps, define a writing and review sequence, or spell out the checklist and definition of done for document changes."
version: 0.1
---

# cf-documenting-planning

This workflow is the canonical thin planning preset for document work.

```pdsl
UNIT DocumentingPlanningPreset
PURPOSE: Bind the default documenting-planning contract, then delegate to cf-planning.
STATE:
  SET PLANNING_DOMAIN: docs (default docs, scope workflow_run)
DO:
  SET PLANNING_DOMAIN = docs
  SET RESOURCE_CONTEXT_REQUIREMENT = optional
  SET DESIGN_REQUIRED_INPUT_SPECS = design-doc accepted as doc-ref or doc-bundle, design-decisions accepted as decision-list or doc-bundle, acceptance-criteria accepted as criteria-list or doc-bundle, and constraints accepted as constraint-list or doc-bundle
  SET PHASE_CHECKLIST_CONTRACT = authoring required true summary "Author or revise only the scoped document artifacts for the phase", deterministic-validation required true summary "Run documenting-ci and produce deterministic-report or ci-findings", semantic-review required true summary "Run documenting-review and resolve or report findings", git required true summary "Prepare commit-intent and satisfy git-commit preflight when git finalization is in scope", phase-close required true summary "Mark phase status and closure outcome explicitly"
  SET PHASE_OUTPUT_CONTRACT = phase-plan, phase-dod, doc-changes, deterministic-report, review-findings, commit-intent, phase-status
  LOAD {cf-studio-path}/.core/workflows/planning.md as the controlling integrable planning workflow
  CONTINUE PlanningBootstrap
```
