---
cf: true
type: workflow
name: cf-docs-review
description: "Invoke when the user explicitly asks for `docs-review` or `cf-docs-review` by name."
version: 0.1
purpose: Delegate document review requests to the document-review workflow.
---

# cf-docs-review

This workflow is a compatibility alias. The canonical thin document review
entrypoint is `cf-documenting-review`.

```pdsl
UNIT DocsReviewAlias
PURPOSE: Redirect legacy docs-review invocations into the canonical thin document review workflow.
DO:
  EMIT "Note: docs-review is now an alias for documenting-review. Continuing with the canonical workflow."
  LOAD {cf-studio-path}/.core/workflows/documenting-review.md as the controlling review workflow
  CONTINUE DocumentingReviewPreset
RULES:
  ALWAYS preserve caller intent and ORIGINAL_INTENT when redirecting to the target workflow
  NEVER introduce new gates, menus, or behavior changes in the alias itself
  NEVER silently continue when the target workflow LOAD fails; EMIT an error and STOP_TURN
```
