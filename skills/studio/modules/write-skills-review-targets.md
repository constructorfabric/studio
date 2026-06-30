# Write Skills Review Targets
```pdsl
UNIT WriteSkillsReviewSetupMissingTargets
PURPOSE: Stop when review target paths or slices were not resolved.
STATE:
  SET REVIEW_TARGET_CAPTURE_STATE: resume | unset (default unset, scope workflow_run)
DO:
  SET REVIEW_TARGET_CAPTURE_STATE = resume
  EMIT "Review target resolution is required before reviewer dispatch. Provide the reviewed target path(s) and declared content slice(s) for the existing skill/prompt/workflow/agent instruction/system prompt under review."
  WAIT user.reply
  STOP_TURN
```
```pdsl
UNIT WriteSkillsReviewTargetResume
PURPOSE: Resume review target capture after the user supplies missing review paths or slices.
STATE:
  SET REVIEW_TARGET_CAPTURE_STATE: resume | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_PATHS: list | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_SLICES: list | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE REVIEW_TARGET_CAPTURE_STATE == resume
  REQUIRE user.reply exists
DO:
  SET REVIEW_TARGET_PATHS = file paths parsed from user.reply WHEN user.reply names one or more files
  SET REVIEW_TARGET_SLICES = slice declarations parsed from user.reply WHEN user.reply names line ranges, sections, or other narrower content slices
  SET REVIEW_TARGET_PATHS = existing REVIEW_TARGET_PATHS WHEN REVIEW_TARGET_PATHS != unset AND user.reply provides slices only
  SET REVIEW_TARGET_SLICES = full-file slices for REVIEW_TARGET_PATHS WHEN REVIEW_TARGET_PATHS != unset AND user.reply does not provide narrower slice declarations
  SET REVIEW_TARGET_CAPTURE_STATE = unset WHEN REVIEW_TARGET_PATHS != unset AND REVIEW_TARGET_SLICES != unset
  CONTINUE WriteSkillsReviewSetup WHEN REVIEW_TARGET_CAPTURE_STATE == unset
  CONTINUE WriteSkillsReviewSetupMissingTargets WHEN REVIEW_TARGET_CAPTURE_STATE == resume
```
```pdsl
UNIT WriteSkillsReviewTargetResolve
PURPOSE: Resolve concrete review target paths and slices before reviewer or fix dispatch.
STATE:
  SET REVIEW_TARGET_CAPTURE_STATE: resume | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_PATHS: list | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_SLICES: list | unset (default unset, scope workflow_run)
  SET PATHS_WRITTEN: list | unset (default unset, scope workflow_run)
DO:
  SET REVIEW_TARGET_PATHS = PATHS_WRITTEN WHEN REVIEW_TARGET_PATHS == unset AND PATHS_WRITTEN != unset
  SET REVIEW_TARGET_PATHS = target paths from NEXT_ACTION_PAYLOAD WHEN REVIEW_TARGET_PATHS == unset AND NEXT_ACTION_PAYLOAD contains target paths
  SET REVIEW_TARGET_SLICES = target slices from NEXT_ACTION_PAYLOAD WHEN REVIEW_TARGET_SLICES == unset AND NEXT_ACTION_PAYLOAD contains target slices
  SET REVIEW_TARGET_PATHS = file paths explicitly named in ORIGINAL_INTENT WHEN REVIEW_TARGET_PATHS == unset AND ORIGINAL_INTENT names one or more existing files
  SET REVIEW_TARGET_PATHS = file paths from RESOURCE_CONTEXT_REF or resource_context path map that match ORIGINAL_INTENT WHEN REVIEW_TARGET_PATHS == unset AND resource_context contains matching target files
  SET REVIEW_TARGET_SLICES = full-file slices for every REVIEW_TARGET_PATHS entry WHEN REVIEW_TARGET_PATHS != unset AND REVIEW_TARGET_SLICES == unset
RULES:
  ALWAYS produce full-file slices when paths are known and no narrower slices were explicitly requested
  ALWAYS preserve caller-provided slices from NEXT_ACTION_PAYLOAD over generated full-file fallback slices
  ALWAYS prefer explicit user-named paths over resource_context-derived paths
  NEVER dispatch a reviewer or approved fix worker with unset target paths or unset target slices
```
