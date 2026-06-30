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
  SET SKILL_FILE_WRITTEN: true | false | unset (default false, scope workflow_run)
  SET REVIEW_ONLY_FINDINGS_GATE: true | false | unset (default true, scope workflow_run)
  SET REVIEW_ONLY_FINDINGS_CONTINUE: unit-name | unset (default PromptingReviewFindingsGate, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapStudioInstructionsMemory
  RUN WorkflowBootstrapCommandResolution
  SET ORIGINAL_INTENT = the user's triggering prompting-review request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  SET REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset
  SET SKILL_FILE_WRITTEN = false WHEN SKILL_FILE_WRITTEN == unset
  SET REVIEW_ONLY_FINDINGS_GATE = true WHEN REVIEW_ONLY_FINDINGS_GATE == unset
  SET REVIEW_ONLY_FINDINGS_CONTINUE = PromptingReviewFindingsGate WHEN REVIEW_ONLY_FINDINGS_CONTINUE == unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-bootstrap-refs.md
  RUN WriteSkillsExecutionContextPrep
  RUN WriteSkillsExecutionReferenceLoad
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-review-setup.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-review-run-fix.md
  CONTINUE WriteSkillsReviewSetup
```

```pdsl
UNIT PromptingReviewFindingsGate
PURPOSE: Present findings in the browser, then stop at next-actions without applying fixes.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  CONTINUE WriteSkillsFixOutcomeClean WHEN REVIEW_FINDINGS_REMAINING == 0
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md
  RUN ReviewFindingsReportBrowser
  CONTINUE PromptingReviewFixHandoff WHEN REVIEW_FIX_APPROVED == true
  RUN NextActionsOffer
  STOP_TURN
RULES:
  - NEVER apply fixes from prompting-review
  - NEVER continue to shared WriteSkillsFixDispatch from this review-only gate
```

```pdsl
UNIT PromptingReviewFixHandoff
PURPOSE: Route to NextActionsOffer after the user approves a fix scope in prompting-review, with cf-prompting-fix as the suggested next action carrying approved finding context.
DO:
  SET NEXT_ACTION_PINNED_SKILL = cf-prompting-fix
  SET NEXT_ACTION_PAYLOAD = APPROVED_REVIEW_FINDING_IDS, REVIEW_FIX_SCOPE, REVIEW_FIX_APPROVED, REVIEW_TARGET_PATHS, REVIEW_TARGET_SLICES, ReviewFindingsReport
  EMIT "Fix scope approved. To apply these fixes, continue with cf-prompting-fix." with NEXT_ACTION_PAYLOAD as handoff context
  RUN NextActionsOffer
RULES:
  ALWAYS mark cf-prompting-fix as (suggested) through NEXT_ACTION_PINNED_SKILL when APPROVED_REVIEW_FINDING_IDS is non-empty
  ALWAYS preserve APPROVED_REVIEW_FINDING_IDS, REVIEW_FIX_SCOPE, REVIEW_FIX_APPROVED, REVIEW_TARGET_PATHS, REVIEW_TARGET_SLICES, and ReviewFindingsReport in NEXT_ACTION_PAYLOAD for the cf-prompting-fix handoff
  NEVER apply fixes from this unit
```
