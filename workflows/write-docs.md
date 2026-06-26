---
cf: true
type: workflow
name: cf-write-docs
description: "Invoke when the user explicitly asks for `write-docs` or `cf-write-docs` by name."
version: 0.1
---
# cf-write-docs
This workflow is a compatibility alias. The canonical thin document-generation
entrypoint is `cf-documenting-gen`.

```pdsl
UNIT WriteDocsAlias
PURPOSE: Redirect legacy cf-write-docs invocations into the canonical thin document-generation workflow.
DO:
  LOAD {cf-studio-path}/.core/workflows/documenting-gen.md as the controlling generation workflow
  CONTINUE DocumentingGenBootstrap
RULES:
  ALWAYS preserve caller intent and ORIGINAL_INTENT when redirecting to the target workflow
  NEVER introduce new gates, menus, or behavior changes in the alias itself
  NEVER silently continue when the target workflow LOAD fails; EMIT an error and STOP_TURN
```
