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
  LOAD {cf-studio-path}/.core/workflows/prompting-review.md as the controlling review workflow
  CONTINUE PromptingReviewPreset
```
