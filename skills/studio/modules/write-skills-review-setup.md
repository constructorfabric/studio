# Write Skills Review Setup
```pdsl
UNIT WriteSkillsReviewSetup
PURPOSE: Load review modules, enforce anti-spin rules, and resolve review target paths before any reviewer is dispatched.
WHEN:
  REQUIRE SKILL_FILE_WRITTEN == true OR REVIEW_LOOP_REQUESTED == true
DO:
  RUN WriteSkillsReviewSetupLoadModules
  RUN SemanticReviewNoSpinRules
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-review-targets.md
  RUN WriteSkillsReviewTargetResolve
  CONTINUE WriteSkillsReviewSetupMissingTargets WHEN REVIEW_LOOP_REQUESTED == true AND (REVIEW_TARGET_PATHS == unset OR REVIEW_TARGET_SLICES == unset)
  CONTINUE WriteSkillsReviewRun
RULES:
  NEVER skip SemanticReviewNoSpinRules
```
```pdsl
UNIT WriteSkillsReviewSetupLoadModules
PURPOSE: Load the review references required before any reviewer dispatch.
DO:
  LOAD {cf-studio-path}/.core/requirements/prompt-bug-finding.md
  LOAD {cf-studio-path}/.core/requirements/consistency-checklist.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/finding-contract.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/semantic-loop-skeleton.md
```
