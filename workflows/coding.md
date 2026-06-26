---
cf: true
type: workflow
name: cf-coding
description: "Invoke when the user explicitly asks for `coding` or `cf-coding` by name."
version: 0.1
---

# cf-coding

This workflow is a compatibility alias. The canonical thin code-generation
entrypoint is `cf-coding-gen`.

```pdsl
UNIT CodingAlias
PURPOSE: Redirect legacy cf-coding invocations into the canonical thin code-generation workflow.
DO:
  LOAD {cf-studio-path}/.core/workflows/coding-gen.md as the controlling generation workflow
  CONTINUE CodingGenBootstrap
RULES:
  ALWAYS preserve the caller intent and workflow state when redirecting
  NEVER reintroduce review or CI orchestration in this alias
  NEVER silently continue when the target workflow LOAD fails; EMIT an error and STOP_TURN
```
