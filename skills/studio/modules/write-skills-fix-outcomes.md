# Write Skills Fix Outcomes
```pdsl
UNIT WriteSkillsCleanExitGate
PURPOSE: Centralize the completion gate for authored or review-fixed skill files.
WHEN:
  REQUIRE SKILL_FILE_WRITTEN == true OR REVIEW_FIXES_APPLIED == true
DO:
  RUN verify VALIDATION_STATUS == pass before any authored or review-fixed skill file is declared complete
  RUN verify REVIEW_FINDINGS_REMAINING == 0 before any authored or review-fixed skill file is declared complete
RULES:
  NEVER declare an authored or review-fixed skill file done until BOTH the deterministic PDSL check passes AND the semantic review has no remaining findings
```
```pdsl
UNIT WriteSkillsFixOutcome
PURPOSE: Verify the fix manifest, update remaining-findings count, and route to validate or completion.
DO:
  RUN verify the returned fix manifest accounts for every APPROVED_REVIEW_FINDING_IDS entry as applied or not-fixable; SET REVIEW_FIXES_APPLIED = true WHEN one or more approved fixes changed skill/prompt/workflow files; SET REVIEW_FIXES_APPLIED = false WHEN no files changed; SET REVIEW_FINDINGS_REMAINING = count of findings not yet resolved after this fix iteration
  CONTINUE WriteSkillsValidate WHEN REVIEW_FIXES_APPLIED == true
  CONTINUE WriteSkillsFixOutcomeNoChanges WHEN findings remain but no fixes were applied this iteration (none approved, none applicable, or the ReviewFixApprovalGate resolved to none)
  CONTINUE WriteSkillsFixOutcomeDeterministicBlocker WHEN REVIEW_FINDINGS_REMAINING == 0 AND VALIDATION_STATUS == fail
  RUN WriteSkillsCleanExitGate WHEN REVIEW_FINDINGS_REMAINING == 0 AND (SKILL_FILE_WRITTEN == true OR REVIEW_FIXES_APPLIED == true)
  CONTINUE WriteSkillsCompletion WHEN REVIEW_FINDINGS_REMAINING == 0 AND VALIDATION_STATUS == pass
```
```pdsl
UNIT WriteSkillsFixOutcomeNoChanges
PURPOSE: Stop when no approved fixes were applied and findings still remain.
DO:
  STOP_TURN and report the remaining findings WHEN findings remain but no fixes were applied this iteration — re-reviewing unchanged skill files cannot change the result
RULES:
  NEVER re-loop the review after an iteration with no applied fixes
```
```pdsl
UNIT WriteSkillsFixOutcomeClean
PURPOSE: Route a clean review report without requiring a fix manifest.
WHEN:
  REQUIRE REVIEW_FINDINGS_REMAINING == 0
DO:
  CONTINUE WriteSkillsCompletion WHEN SKILL_FILE_WRITTEN == false AND REVIEW_FIXES_APPLIED != true
  RUN WriteSkillsCleanExitGate WHEN SKILL_FILE_WRITTEN == true OR REVIEW_FIXES_APPLIED == true
  CONTINUE WriteSkillsCompletion WHEN VALIDATION_STATUS == pass
```
```pdsl
UNIT WriteSkillsFixOutcomeDeterministicBlocker
PURPOSE: Stop when semantic findings are clear but deterministic validation still fails.
DO:
  STOP_TURN and report that deterministic blockers remain
```
