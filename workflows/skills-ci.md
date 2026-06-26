---
cf: true
type: workflow
name: cf-skills-ci
description: "Invoke when the user explicitly asks for `skills-ci` or `cf-skills-ci` by name."
version: 0.1
purpose: Delegate prompt CI requests to the prompt-validation workflow.
---

# cf-skills-ci

This workflow is a compatibility alias. The canonical thin prompt CI entrypoint
is `cf-prompting-ci`.

```pdsl
UNIT SkillsCiAlias
PURPOSE: Redirect legacy skills-ci invocations into the canonical thin prompt CI workflow.
DO:
  LOAD {cf-studio-path}/.core/workflows/prompting-ci.md as the controlling CI workflow
  CONTINUE PromptingCiPreset
```
