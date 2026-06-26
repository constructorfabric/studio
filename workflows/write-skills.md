---
cf: true
type: workflow
name: cf-write-skills
description: "Invoke when the user explicitly asks for `write-skills` or `cf-write-skills` by name."
version: 0.1
---
# cf-write-skills
This workflow is a compatibility alias. The canonical thin prompt-generation
entrypoint is `cf-prompting-gen`.

```pdsl
UNIT WriteSkillsAlias
PURPOSE: Redirect legacy cf-write-skills invocations into the canonical thin prompt-generation workflow.
DO:
  LOAD {cf-studio-path}/.core/workflows/prompting-gen.md as the controlling generation workflow
  CONTINUE PromptingGenBootstrap
RULES:
  ALWAYS preserve caller intent and ORIGINAL_INTENT when redirecting to the target workflow
  NEVER introduce new gates, menus, or behavior changes in the alias itself
  NEVER silently continue when the target workflow LOAD fails; EMIT an error and STOP_TURN
```
