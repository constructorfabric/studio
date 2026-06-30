---
cf: true
type: workflow
name: cf-skills-review
description: "Invoke when the user explicitly asks for `skills-review` or `cf-skills-review` by name."
version: 0.1
purpose: Delegate prompt review requests to the prompt-review workflow.
---

# cf-skills-review

This workflow is a compatibility alias. The canonical thin prompt review
entrypoint is `cf-prompting-review`.

```pdsl
UNIT SkillsReviewAlias
PURPOSE: Redirect legacy skills-review invocations into the canonical thin prompt review workflow.
DO:
  EMIT "Note: skills-review is now an alias for prompting-review. Continuing with the canonical workflow."
  LOAD {cf-studio-path}/.core/workflows/prompting-review.md as the controlling review workflow
  CONTINUE PromptingReviewPreset
RULES:
  ALWAYS preserve caller intent and ORIGINAL_INTENT when redirecting to the target workflow
  NEVER introduce new gates, menus, or behavior changes in the alias itself
  NEVER silently continue when the target workflow LOAD fails; EMIT an error and STOP_TURN
```
