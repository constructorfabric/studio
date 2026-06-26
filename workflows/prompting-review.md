---
cf: true
type: workflow
name: cf-prompting-review
description: "Invoke when the user or another skill or workflow needs or asks to review prompts, skills, workflows, agent instructions, or system prompts for logic bugs, unclear routing, missing cases, risky behavior, or prompt-quality problems and report findings without applying fixes."
version: 0.1
---

# cf-prompting-review

This workflow is the canonical thin semantic review entrypoint for prompt
artifacts.

```pdsl
UNIT PromptingReviewPreset
PURPOSE: Run semantic prompt review and stop at findings.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default true, scope workflow_run)
DO:
  SET ORIGINAL_INTENT = the user's triggering prompting-review request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  SET REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-bootstrap-refs.md
  RUN WriteSkillsExecutionContextPrep
  RUN WriteSkillsExecutionReferenceLoad
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-review-setup.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-review-run-fix.md
  CONTINUE WriteSkillsReviewSetup
```

```pdsl
UNIT WriteSkillsFixGate
PURPOSE: Present findings in the browser, then stop at next-actions without applying fixes.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  CONTINUE WriteSkillsFixOutcomeClean WHEN REVIEW_FINDINGS_REMAINING == 0
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md
  RUN ReviewFindingsReportBrowser
  RUN NextActionsOffer
RULES:
  - NEVER apply fixes from prompting-review
```
