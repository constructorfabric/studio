# Write Skills Completion
```pdsl
UNIT WriteSkillsCompletion
PURPOSE: Emit the canonical thin-skill completion envelope, then offer context-grounded next actions after prompt/skill/workflow authoring or review completes cleanly.
WHEN:
  REQUIRE REVIEW_FINDINGS_REMAINING == 0 OR REVIEW_LOOP_REQUESTED != true OR SKILL_FILE_WRITTEN == true OR REVIEW_FIXES_APPLIED == true
STATE:
  SET COMPLETION_PATHS_WRITTEN: list | unset (default unset, scope unit_run)
  SET COMPLETION_PATHS_CONFIRMED: true | false | unset (default unset, scope unit_run)
  SET COMPLETION_REPORT_OUTPUTS: list | unset (default unset, scope unit_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  SET COMPLETION_PATHS_WRITTEN = PATHS_WRITTEN WHEN PATHS_WRITTEN != unset
  SET COMPLETION_PATHS_WRITTEN = paths_written from the current review-fix manifest WHEN COMPLETION_PATHS_WRITTEN == unset AND REVIEW_FIXES_APPLIED == true
  SET COMPLETION_PATHS_CONFIRMED = true WHEN COMPLETION_PATHS_WRITTEN != unset
  SET COMPLETION_PATHS_WRITTEN = [] WHEN COMPLETION_PATHS_WRITTEN == unset AND FIX_PREREQUISITE_OVERRIDE_ACTIVE == true
  SET COMPLETION_PATHS_CONFIRMED = false WHEN COMPLETION_PATHS_CONFIRMED == unset AND FIX_PREREQUISITE_OVERRIDE_ACTIVE == true
  SET COMPLETION_PATHS_CONFIRMED = false WHEN COMPLETION_PATHS_CONFIRMED == unset
  SET COMPLETION_REPORT_OUTPUTS = report_outputs WHEN report_outputs != unset
  SET COMPLETION_REPORT_OUTPUTS = review-findings describing ReviewFindingsReport WHEN COMPLETION_REPORT_OUTPUTS == unset AND REVIEW_LOOP_REQUESTED == true AND REVIEW_FIXES_APPLIED != true AND SKILL_FILE_WRITTEN != true
  SET COMPLETION_REPORT_OUTPUTS = [] WHEN COMPLETION_REPORT_OUTPUTS == unset
  EMIT a completed SKILL_RESULT envelope with skill = cf-prompting-review, status = completed, produced_artifacts = [], report_outputs = COMPLETION_REPORT_OUTPUTS, missing_artifacts = [], assumptions = [], and suggested_next_skills = [] WHEN REVIEW_LOOP_REQUESTED == true AND REVIEW_FIXES_APPLIED != true AND SKILL_FILE_WRITTEN != true
  EMIT a completed-with-assumptions SKILL_RESULT envelope with skill = cf-prompting-fix when REVIEW_FIXES_APPLIED == true and REVIEW_LOOP_REQUESTED == true, otherwise cf-prompting-gen, status = completed-with-assumptions, produced_artifacts = skill-changes describing COMPLETION_PATHS_WRITTEN, report_outputs = COMPLETION_REPORT_OUTPUTS, missing_artifacts = [], assumptions = ASSUMPTIONS, and suggested_next_skills = [] WHEN FIX_PREREQUISITE_OVERRIDE_ACTIVE == true AND COMPLETION_PATHS_CONFIRMED == true AND NOT (REVIEW_LOOP_REQUESTED == true AND REVIEW_FIXES_APPLIED != true AND SKILL_FILE_WRITTEN != true)
  EMIT a completed-with-assumptions SKILL_RESULT envelope with skill = cf-prompting-fix when REVIEW_FIXES_APPLIED == true and REVIEW_LOOP_REQUESTED == true, otherwise cf-prompting-gen, status = completed-with-assumptions, produced_artifacts = [], report_outputs = COMPLETION_REPORT_OUTPUTS, missing_artifacts = [], assumptions = ASSUMPTIONS, and suggested_next_skills = [] WHEN FIX_PREREQUISITE_OVERRIDE_ACTIVE == true AND COMPLETION_PATHS_CONFIRMED != true AND NOT (REVIEW_LOOP_REQUESTED == true AND REVIEW_FIXES_APPLIED != true AND SKILL_FILE_WRITTEN != true)
  EMIT a completed SKILL_RESULT envelope with skill = cf-prompting-fix when REVIEW_FIXES_APPLIED == true and REVIEW_LOOP_REQUESTED == true, otherwise cf-prompting-gen, status = completed, produced_artifacts = skill-changes describing COMPLETION_PATHS_WRITTEN, report_outputs = COMPLETION_REPORT_OUTPUTS, missing_artifacts = [], assumptions = [], and suggested_next_skills = [] WHEN FIX_PREREQUISITE_OVERRIDE_ACTIVE != true AND NOT (REVIEW_LOOP_REQUESTED == true AND REVIEW_FIXES_APPLIED != true AND SKILL_FILE_WRITTEN != true)
  RUN NextActionsOffer
RULES:
  ALWAYS use this unit only after prompt/skill/workflow authoring, validation, or review is complete and control is about to return to the user
  ALWAYS prefer actual written paths captured from author output or fix manifests over REVIEW_TARGET_PATHS
  NEVER substitute REVIEW_TARGET_PATHS for produced_artifacts
  ALWAYS emit produced_artifacts = [] when no actual written paths were captured
  NEVER emit cf-prompting-review with status = completed-with-assumptions
  NEVER bypass NextActionsOffer on a clean terminal path that returns control to the user
```
