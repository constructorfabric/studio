---
cf: true
type: workflow
name: cf-kit-planning
description: "Invoke when the user or another skill or workflow needs or asks to build a phase plan for kit prompt, document, or code work with explicit authoring, review, CI, git, and phase-close checklists."
version: 0.1
purpose: Bind the default kit-planning contract, require kit-scoped context, and delegate planning to the integrable cf-planning workflow.
---

# cf-kit-planning

This workflow is the canonical thin planning preset for kit prompt, document,
and code work.

```pdsl
UNIT KitPlanningPreset
PURPOSE: Bind the default kit-planning contract, then delegate to cf-planning.
STATE:
  SET PLANNING_DOMAIN: kits (default kits, scope workflow_run)
DO:
  SET PLANNING_DOMAIN = kits
  SET RESOURCE_CONTEXT_REQUIREMENT = required
  SET DESIGN_REQUIRED_INPUT_SPECS = design-doc accepted as doc-ref or doc-bundle, design-decisions accepted as decision-list or doc-bundle, acceptance-criteria accepted as criteria-list or doc-bundle, and constraints accepted as constraint-list or doc-bundle
  SET PHASE_CHECKLIST_CONTRACT = authoring required true summary "Author or revise only the scoped kit prompt, document, or code assets for the phase, and route each phase through kit-gen so prompt assets use prompting-gen, document assets use documenting-gen, and code assets use coding-gen", deterministic-validation required true summary "Run kit-ci and produce deterministic-report or ci-findings", semantic-review required true summary "Run kit-review and resolve or report findings", git required true summary "Prepare commit-intent and satisfy git-commit preflight when git finalization is in scope", phase-close required true summary "Mark phase status and closure outcome explicitly"
  SET PHASE_OUTPUT_CONTRACT = phase-plan, phase-dod, skill-changes, doc-changes, code-changes, deterministic-report, review-findings, commit-intent, phase-status
  LOAD {cf-studio-path}/.core/workflows/planning.md as the controlling integrable planning workflow
  CONTINUE PlanningBootstrap
RULES:
  - ALWAYS decompose mixed kit changes into domain-scoped phases before execution
  - ALWAYS use the existing prompting and documenting and coding workflows instead of inventing kit-local authoring or review loops
  - ALWAYS route manifest or kit-configuration work through cf-kit outside this thin planning family
  - NEVER keep unrelated prompt, document, and code edits in one opaque execution phase
```
