# Write Skills Completion
```pdsl
UNIT WriteSkillsCompletion
PURPOSE: Emit the canonical thin-skill completion envelope, then offer context-grounded next actions after prompt/skill/workflow authoring or review completes cleanly.
WHEN:
  REQUIRE REVIEW_FINDINGS_REMAINING == 0 OR REVIEW_LOOP_REQUESTED != true OR SKILL_FILE_WRITTEN == true OR REVIEW_FIXES_APPLIED == true
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT a completed SKILL_RESULT envelope with skill = cf-prompting-fix when REVIEW_FIXES_APPLIED == true and REVIEW_LOOP_REQUESTED == true, skill = cf-prompting-review when REVIEW_LOOP_REQUESTED == true and REVIEW_FIXES_APPLIED != true, otherwise cf-prompting-gen, status = completed, produced_artifacts = skill-changes describing PATHS_WRITTEN when author output paths were captured or REVIEW_TARGET_PATHS when only fix target paths are available, report_outputs = [], missing_artifacts = [], assumptions = [], and suggested_next_skills = []
  RUN NextActionsOffer
RULES:
  ALWAYS use this unit only after prompt/skill/workflow authoring, validation, or review is complete and control is about to return to the user
  NEVER bypass NextActionsOffer on a clean terminal path that returns control to the user
```
