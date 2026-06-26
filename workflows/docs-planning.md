---
cf: true
type: workflow
name: cf-docs-planning
description: "Invoke when the user explicitly asks for `docs-planning` or `cf-docs-planning` by name."
version: 0.1
purpose: Thin preset that binds document-planning prerequisites and default phase checklist sections, then delegates planning to the integrable cf-planning workflow.
---

# cf-docs-planning

This workflow is a thin preset over `cf-planning`. It binds docs-planning
prerequisites and a default document-phase checklist contract.

```pdsl
UNIT DocsPlanningAlias
PURPOSE: Redirect legacy docs-planning invocations into the canonical thin document planning workflow.
DO:
  LOAD {cf-studio-path}/.core/workflows/documenting-planning.md as the controlling planning workflow
  CONTINUE DocumentingPlanningPreset
RULES:
  ALWAYS preserve caller intent and ORIGINAL_INTENT when redirecting to the target workflow
  NEVER introduce new gates, menus, or behavior changes in the alias itself
```
