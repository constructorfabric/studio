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
  SET REVIEW_FINDINGS_REPORT_STATE: supported | unsupported | missing | unset (default unset, scope workflow_run)
  SET REVIEW_FINDINGS_REMAINING: integer | unset (default unset, scope workflow_run)
  SET APPROVED_REVIEW_FINDING_IDS: list | all-critical-major | all | empty | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_SCOPE: critical-major | all | partial | none | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_APPROVED: true | false | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_PATHS: list | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_SLICES: list | unset (default unset, scope workflow_run)
  SET SKILL_CLASS: planning | authoring | fix | explore | brainstorm | review | ci | unset (default unset, scope workflow_run)
  SET OVERRIDE_ALLOWED: true | false | unset (default unset, scope workflow_run)
  SET OVERRIDE_REQUESTED: explicit-user-approval | unset (default unset, scope workflow_run)
  SET FIX_PREREQUISITE_OVERRIDE_ACTIVE: true | false | unset (default false, scope workflow_run)
  SET ASSUMPTIONS: list | unset (default unset, scope workflow_run)
  SET missing_artifacts: list | unset (default unset, scope workflow_run)
  SET suggested_next_skills: list | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/blocked-report.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/assumption-override.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-fix-outcomes.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-review-run-fix.md
  SET SKILL_CLASS = fix WHEN SKILL_CLASS == unset
  SET REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset
  SET ReviewFindingsReport = ReviewFindingsReport from NEXT_ACTION_PAYLOAD WHEN ReviewFindingsReport == unset AND NEXT_ACTION_PAYLOAD contains ReviewFindingsReport
  SET REVIEW_FINDINGS_REMAINING = ReviewFindingsReport.total_count WHEN REVIEW_FINDINGS_REMAINING == unset AND ReviewFindingsReport contains total_count
  SET REVIEW_FINDINGS_REMAINING = number of entries in ReviewFindingsReport.findings WHEN REVIEW_FINDINGS_REMAINING == unset AND ReviewFindingsReport contains findings AND ReviewFindingsReport.findings is a list
  SET REVIEW_FINDINGS_REMAINING = number of entries in ReviewFindingsReport WHEN REVIEW_FINDINGS_REMAINING == unset AND ReviewFindingsReport is a list
  SET APPROVED_REVIEW_FINDING_IDS = APPROVED_REVIEW_FINDING_IDS from NEXT_ACTION_PAYLOAD WHEN APPROVED_REVIEW_FINDING_IDS == unset AND NEXT_ACTION_PAYLOAD contains APPROVED_REVIEW_FINDING_IDS
  SET REVIEW_FIX_SCOPE = REVIEW_FIX_SCOPE from NEXT_ACTION_PAYLOAD WHEN REVIEW_FIX_SCOPE == unset AND NEXT_ACTION_PAYLOAD contains REVIEW_FIX_SCOPE
  SET REVIEW_FIX_APPROVED = REVIEW_FIX_APPROVED from NEXT_ACTION_PAYLOAD WHEN REVIEW_FIX_APPROVED == unset AND NEXT_ACTION_PAYLOAD contains REVIEW_FIX_APPROVED
  SET REVIEW_TARGET_PATHS = REVIEW_TARGET_PATHS from NEXT_ACTION_PAYLOAD WHEN REVIEW_TARGET_PATHS == unset AND NEXT_ACTION_PAYLOAD contains REVIEW_TARGET_PATHS
  SET REVIEW_TARGET_SLICES = REVIEW_TARGET_SLICES from NEXT_ACTION_PAYLOAD WHEN REVIEW_TARGET_SLICES == unset AND NEXT_ACTION_PAYLOAD contains REVIEW_TARGET_SLICES
  SET OVERRIDE_REQUESTED = OVERRIDE_REQUESTED from NEXT_ACTION_PAYLOAD WHEN OVERRIDE_REQUESTED == unset AND NEXT_ACTION_PAYLOAD contains OVERRIDE_REQUESTED
  SET ASSUMPTIONS = ASSUMPTIONS from NEXT_ACTION_PAYLOAD WHEN ASSUMPTIONS == unset AND NEXT_ACTION_PAYLOAD contains ASSUMPTIONS
  SET REVIEW_TARGET_SLICES = full-file slices for every REVIEW_TARGET_PATHS entry WHEN REVIEW_TARGET_PATHS != unset AND REVIEW_TARGET_SLICES == unset
  SET suggested_next_skills = [cf-prompting-review]
  SET REVIEW_FINDINGS_REPORT_STATE = missing WHEN ReviewFindingsReport == unset
  SET REVIEW_FINDINGS_REPORT_STATE = supported WHEN ReviewFindingsReport.report_type == review-findings AND ReviewFindingsReport contains findings AND ReviewFindingsReport.findings is a list AND REVIEW_FINDINGS_REMAINING != unset
  SET REVIEW_FINDINGS_REPORT_STATE = supported WHEN ReviewFindingsReport contains findings AND ReviewFindingsReport.findings is a list AND REVIEW_FINDINGS_REMAINING != unset
  SET REVIEW_FINDINGS_REPORT_STATE = supported WHEN ReviewFindingsReport is a list AND REVIEW_FINDINGS_REMAINING != unset
  SET REVIEW_FINDINGS_REPORT_STATE = unsupported WHEN ReviewFindingsReport != unset AND REVIEW_FINDINGS_REPORT_STATE == unset
  SET missing_artifacts = review-findings with why_needed "A findings report keeps prompt fixes bounded to reviewed issues; override only for an explicitly accepted manual degraded fix scope", accepted_shapes findings-report or findings-list, suggested_producers cf-prompting-review, override_allowed true, override_summary "Explicit user approval may bypass the missing or unsupported findings report for a manually scoped degraded prompt fix run"; relevant-files-map with why_needed "Concrete target paths are required to keep prompt edits bounded", accepted_shapes path-map or path-list, suggested_producers cf-prompting-review and cf-explore, override_allowed false WHEN (REVIEW_FINDINGS_REPORT_STATE == missing OR REVIEW_FINDINGS_REPORT_STATE == unsupported OR REVIEW_FINDINGS_REMAINING == 0) AND REVIEW_TARGET_PATHS == unset
  SET missing_artifacts = review-findings with why_needed "A findings report keeps prompt fixes bounded to reviewed issues; override only for an explicitly accepted manual degraded fix scope", accepted_shapes findings-report or findings-list, suggested_producers cf-prompting-review, override_allowed true, override_summary "Explicit user approval may bypass the missing or unsupported findings report for a manually scoped degraded prompt fix run" WHEN (REVIEW_FINDINGS_REPORT_STATE == missing OR REVIEW_FINDINGS_REPORT_STATE == unsupported OR REVIEW_FINDINGS_REMAINING == 0) AND REVIEW_TARGET_PATHS != unset
  SET missing_artifacts = relevant-files-map with why_needed "Concrete target paths are required to keep prompt edits bounded", accepted_shapes path-map or path-list, suggested_producers cf-prompting-review and cf-explore, override_allowed false WHEN REVIEW_TARGET_PATHS == unset AND REVIEW_FINDINGS_REPORT_STATE == supported AND REVIEW_FINDINGS_REMAINING != 0
  SET OVERRIDE_ALLOWED = true WHEN missing_artifacts != unset AND one or more missing_artifacts entries declare override_allowed == true
  SET OVERRIDE_ALLOWED = false WHEN OVERRIDE_ALLOWED == unset
  SET FIX_PREREQUISITE_OVERRIDE_ACTIVE = true WHEN OVERRIDE_REQUESTED == explicit-user-approval AND missing_artifacts != unset AND every missing_artifacts entry declares override_allowed == true
  SET REVIEW_FIX_APPROVED = true WHEN FIX_PREREQUISITE_OVERRIDE_ACTIVE == true AND REVIEW_FIX_APPROVED == unset
  SET REVIEW_FIX_SCOPE = all WHEN FIX_PREREQUISITE_OVERRIDE_ACTIVE == true AND REVIEW_FIX_SCOPE == unset
  SET APPROVED_REVIEW_FINDING_IDS = empty WHEN FIX_PREREQUISITE_OVERRIDE_ACTIVE == true AND APPROVED_REVIEW_FINDING_IDS == unset
  SET ASSUMPTIONS = one entry with artifact_or_gate = review-findings, summary = "Proceed from explicit user-approved degraded prompt-fix scope without a canonical review findings report", risk = "The prompt fix can drift beyond independently reviewed findings and may miss routing or validation regressions" WHEN FIX_PREREQUISITE_OVERRIDE_ACTIVE == true AND ASSUMPTIONS == unset
  RUN AssumptionOverrideContract WHEN FIX_PREREQUISITE_OVERRIDE_ACTIVE == true
  RUN BlockedReportContract WHEN missing_artifacts != unset AND FIX_PREREQUISITE_OVERRIDE_ACTIVE != true
  CONTINUE WriteSkillsFixDispatch WHEN FIX_PREREQUISITE_OVERRIDE_ACTIVE == true
  CONTINUE WriteSkillsFixDispatch WHEN REVIEW_FIX_APPROVED == true AND APPROVED_REVIEW_FINDING_IDS != empty AND REVIEW_FIX_SCOPE != unset
  CONTINUE WriteSkillsFixGate
RULES:
  ALWAYS require explicit review findings before applying prompt fixes unless the user explicitly approved a degraded override for the missing or unsupported findings gate
  ALWAYS hydrate ReviewFindingsReport, approved finding IDs, fix scope, approval state, target paths, and target slices from NEXT_ACTION_PAYLOAD before checking for missing findings or missing target scope
  ALWAYS classify ReviewFindingsReport as supported, unsupported, or missing before deciding whether degraded override is legal
  NEVER run semantic review from prompting-fix
  ALWAYS block missing target paths through the shared blocked-report contract
  ALWAYS record assumption summaries and risks when the findings gate is bypassed
```

```pdsl
UNIT WriteSkillsValidate
PURPOSE: Run deterministic prompt validation after approved fixes before completion.
STATE:
  SET VALIDATION_STATUS: pass | fail | unset (default unset, scope workflow_run)
  SET CI_RESULT_STATUS: completed | failed | blocked | unset (default unset, scope workflow_run)
  SET FINDINGS_REPORT_TYPE: review-findings | ci-findings | other | unset (default unset, scope workflow_run)
  SET FINDINGS_RESULT_STATUS: completed | failed | blocked | unset (default unset, scope workflow_run)
  SET FINDINGS: list | unset (default unset, scope workflow_run)
  SET FINDINGS_REPORT_REF: ref | unset (default unset, scope workflow_run)
  SET REVIEW_FINDINGS_REMAINING: integer | unset (default unset, scope workflow_run)
  SET report_outputs: list | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/command-resolution.md
  RUN CommandResolution to resolve {cfs_cmd}
  RUN deterministic PDSL validation via `{cfs_cmd} pdsl validate` on REVIEW_TARGET_PATHS
  SET VALIDATION_STATUS = fail WHEN validation reports errors
  SET VALIDATION_STATUS = pass WHEN validation passes
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/findings-render.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/ci-report-render.md
  SET CI_RESULT_STATUS = failed WHEN VALIDATION_STATUS == fail
  SET CI_RESULT_STATUS = completed WHEN VALIDATION_STATUS == pass
  SET FINDINGS_REPORT_TYPE = ci-findings
  SET FINDINGS_RESULT_STATUS = completed WHEN CI_RESULT_STATUS == completed
  SET FINDINGS_RESULT_STATUS = failed WHEN CI_RESULT_STATUS == failed
  SET FINDINGS = normalized CI findings from the executed validation results
  SET FINDINGS = [] WHEN FINDINGS == unset
  SET FINDINGS_REPORT_REF = a stable ci-findings report ref derived from the current deterministic validation run
  RUN FindingsRenderContract
  SET report_outputs = deterministic-report describing the executed PDSL validation gate plus report_outputs from FINDINGS_REPORT
  RUN CiReportRenderContract
  CONTINUE WriteSkillsFixOutcomeDeterministicBlocker WHEN VALIDATION_STATUS == fail
  CONTINUE WriteSkillsFixOutcomeNoChanges WHEN VALIDATION_STATUS == pass AND REVIEW_FINDINGS_REMAINING != 0
  RUN WriteSkillsCleanExitGate WHEN VALIDATION_STATUS == pass AND REVIEW_FINDINGS_REMAINING == 0
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-completion.md
  CONTINUE WriteSkillsCompletion WHEN VALIDATION_STATUS == pass AND REVIEW_FINDINGS_REMAINING == 0
RULES:
  ALWAYS rerun deterministic PDSL validation after approved prompt fixes before completion
  ALWAYS emit deterministic-report plus ci-findings outputs for the post-fix validation command, including the zero-findings case
  NEVER continue to WriteSkillsCompletion unless VALIDATION_STATUS == pass and REVIEW_FINDINGS_REMAINING == 0
```
