---
cf: true
type: workflow
name: cf-code-planning
description: "Invoke when the user or another skill or workflow needs or asks to plan code work, break implementation into steps, define a coding phase plan, sequence tests before implementation, or spell out the implementation checklist and definition of done for a code change."
version: 0.1
purpose: Thin preset that binds code-planning prerequisites and default phase checklist sections, then delegates planning to the integrable cf-planning workflow.
---

# cf-code-planning

This workflow is a thin preset over `cf-planning`. It binds code-planning
prerequisites and a default implementation-phase checklist contract. It does
not compile standalone phase packages.

```pdsl
UNIT CodePlanningPreset
PURPOSE: Bind the default code-planning contract, then delegate to cf-planning.
STATE:
  SET PLANNING_DOMAIN: code (default code, scope workflow_run)
DO:
  SET PLANNING_DOMAIN = code
  SET RESOURCE_CONTEXT_REQUIREMENT = required
  SET DESIGN_REQUIRED_INPUT_SPECS = design-doc accepted as doc-ref or doc-bundle, design-decisions accepted as decision-list or doc-bundle, acceptance-criteria accepted as criteria-list or doc-bundle, and constraints accepted as constraint-list or doc-bundle
  SET PHASE_CHECKLIST_CONTRACT = tests required true summary "Define or update unit-tests, e2e-tests, or test-spec before implementation", implementation required true summary "Implement only the scoped behavior for the phase", deterministic-validation required true summary "Run project CI gates and produce deterministic-report or ci-findings", semantic-review required true summary "Run coding-review and resolve or report findings", git required true summary "Prepare commit-intent and satisfy git-commit preflight when git finalization is in scope", phase-close required true summary "Mark phase status and closure outcome explicitly"
  SET PHASE_OUTPUT_CONTRACT = phase-plan, phase-dod, unit-tests, e2e-tests, test-spec, code-changes, deterministic-report, review-findings, commit-intent, phase-status
  LOAD {cf-studio-path}/.core/workflows/planning.md as the controlling integrable planning workflow
  CONTINUE PlanningBootstrap
RULES:
  - ALWAYS require resource-context or relevant-files-map for code planning unless the caller explicitly supplies a narrower accepted contract
  - ALWAYS make test-first execution visible in the default phase checklist
  - NEVER plan hidden implementation work outside explicit phase skill sequences
```
