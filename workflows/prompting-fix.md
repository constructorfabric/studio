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
  SET ReviewFindingsReport: object | unset (default unset, scope workflow_run)
  SET REVIEW_FINDINGS_REMAINING: integer | unset (default unset, scope workflow_run)
  SET APPROVED_REVIEW_FINDING_IDS: list | all-critical-major | all | empty | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_SCOPE: critical-major | all | partial | none | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_APPROVED: true | false | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_PATHS: list | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_SLICES: list | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-fix-outcomes.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-review-run-fix.md
  SET REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset
  SET ReviewFindingsReport = ReviewFindingsReport from NEXT_ACTION_PAYLOAD WHEN ReviewFindingsReport == unset AND NEXT_ACTION_PAYLOAD contains ReviewFindingsReport
  SET REVIEW_FINDINGS_REMAINING = ReviewFindingsReport.total_count WHEN REVIEW_FINDINGS_REMAINING == unset AND ReviewFindingsReport != unset
  SET APPROVED_REVIEW_FINDING_IDS = APPROVED_REVIEW_FINDING_IDS from NEXT_ACTION_PAYLOAD WHEN APPROVED_REVIEW_FINDING_IDS == unset AND NEXT_ACTION_PAYLOAD contains APPROVED_REVIEW_FINDING_IDS
  SET REVIEW_FIX_SCOPE = REVIEW_FIX_SCOPE from NEXT_ACTION_PAYLOAD WHEN REVIEW_FIX_SCOPE == unset AND NEXT_ACTION_PAYLOAD contains REVIEW_FIX_SCOPE
  SET REVIEW_FIX_APPROVED = REVIEW_FIX_APPROVED from NEXT_ACTION_PAYLOAD WHEN REVIEW_FIX_APPROVED == unset AND NEXT_ACTION_PAYLOAD contains REVIEW_FIX_APPROVED
  SET REVIEW_TARGET_PATHS = REVIEW_TARGET_PATHS from NEXT_ACTION_PAYLOAD WHEN REVIEW_TARGET_PATHS == unset AND NEXT_ACTION_PAYLOAD contains REVIEW_TARGET_PATHS
  SET REVIEW_TARGET_SLICES = REVIEW_TARGET_SLICES from NEXT_ACTION_PAYLOAD WHEN REVIEW_TARGET_SLICES == unset AND NEXT_ACTION_PAYLOAD contains REVIEW_TARGET_SLICES
  WHEN ReviewFindingsReport == unset OR REVIEW_FINDINGS_REMAINING == 0:
    EMIT "No review findings are loaded. Run cf-prompting-review first to identify issues, then return here to apply fixes."
    EMIT suggested_next_skills = [cf-prompting-review]
    STOP_TURN
  WHEN REVIEW_TARGET_PATHS == unset OR REVIEW_TARGET_SLICES == unset:
    EMIT "No review target paths or slices are set. Run cf-prompting-review first to identify the review scope."
    EMIT suggested_next_skills = [cf-prompting-review]
    STOP_TURN
  CONTINUE WriteSkillsFixDispatch WHEN REVIEW_FIX_APPROVED == true AND APPROVED_REVIEW_FINDING_IDS != empty AND REVIEW_FIX_SCOPE != unset
  CONTINUE WriteSkillsFixGate
RULES:
  - ALWAYS require explicit review findings before applying prompt fixes
  - ALWAYS hydrate ReviewFindingsReport, approved finding IDs, fix scope, approval state, target paths, and target slices from NEXT_ACTION_PAYLOAD before checking for missing findings or missing target scope
  - NEVER run semantic review from prompting-fix
  - ALWAYS check REVIEW_FINDINGS_REMAINING > 0 before proceeding to fix dispatch; block with explicit message and suggested_next_skills on missing findings
```

```pdsl
UNIT WriteSkillsValidate
PURPOSE: Run deterministic prompt validation after approved fixes before completion.
STATE:
  SET VALIDATION_STATUS: pass | fail | unset (default unset, scope workflow_run)
  SET REVIEW_FINDINGS_REMAINING: integer | unset (default unset, scope workflow_run)
  SET report_outputs: list | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/command-resolution.md
  RUN CommandResolution to resolve {cfs_cmd}
  RUN deterministic PDSL validation via `{cfs_cmd} pdsl validate` on REVIEW_TARGET_PATHS
  SET VALIDATION_STATUS = fail WHEN validation reports errors
  SET VALIDATION_STATUS = pass WHEN validation passes
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/ci-report-render.md
  SET report_outputs = deterministic-report and ci-findings entries for the post-fix PDSL validation command, REVIEW_TARGET_PATHS, and VALIDATION_STATUS
  RUN CiReportRenderContract
  CONTINUE WriteSkillsFixOutcomeDeterministicBlocker WHEN VALIDATION_STATUS == fail
  CONTINUE WriteSkillsFixOutcomeNoChanges WHEN VALIDATION_STATUS == pass AND REVIEW_FINDINGS_REMAINING != 0
  RUN WriteSkillsCleanExitGate WHEN VALIDATION_STATUS == pass AND REVIEW_FINDINGS_REMAINING == 0
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-completion.md
  CONTINUE WriteSkillsCompletion WHEN VALIDATION_STATUS == pass AND REVIEW_FINDINGS_REMAINING == 0
RULES:
  - ALWAYS rerun deterministic PDSL validation after approved prompt fixes before completion
  - NEVER continue to WriteSkillsCompletion unless VALIDATION_STATUS == pass and REVIEW_FINDINGS_REMAINING == 0
```
