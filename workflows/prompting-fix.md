---
cf: true
type: workflow
name: cf-prompting-fix
description: "Invoke when the user or another skill or workflow needs or asks to fix prompt issues from review, address skill or workflow findings, apply approved prompt fixes, resolve prompt review comments, or patch a known set of prompt or PDSL problems."
version: 0.1
---

# cf-prompting-fix

This workflow is the canonical thin prompt-fixing entrypoint.

```pdsl
UNIT PromptingFixBootstrap
PURPOSE: Initialize thin prompt fixing and route into approved-finding application.
STATE:
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default true, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-fix-outcomes.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-review-run-fix.md
  SET REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset
  WHEN ReviewFindingsReport == unset OR REVIEW_FINDINGS_REMAINING == 0:
    EMIT "No review findings are loaded. Run cf-prompting-review first to identify issues, then return here to apply fixes."
    EMIT suggested_next_skills = [cf-prompting-review]
    STOP_TURN
  WHEN REVIEW_TARGET_PATHS == unset OR REVIEW_TARGET_SLICES == unset:
    EMIT "No review target paths or slices are set. Run cf-prompting-review first to identify the review scope."
    EMIT suggested_next_skills = [cf-prompting-review]
    STOP_TURN
  CONTINUE WriteSkillsFixGate
RULES:
  - ALWAYS require explicit review findings before applying prompt fixes
  - NEVER run semantic review from prompting-fix
  - ALWAYS check REVIEW_FINDINGS_REMAINING > 0 before proceeding to fix dispatch; block with explicit message and suggested_producers on missing findings
```

```pdsl
UNIT WriteSkillsValidate
PURPOSE: Terminate the thin prompt-fix workflow after approved fixes are applied.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-completion.md
  CONTINUE WriteSkillsCompletion
```
