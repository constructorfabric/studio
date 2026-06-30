# Write Skills Fix Outcomes

```pdsl
UNIT WriteSkillsCleanExitGate
PURPOSE: Centralize the completion gate for authored or review-fixed skill files.
STATE:
  SET REVIEW_FINDINGS_REMAINING: integer | unset (default unset, scope workflow_run)
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
STATE:
  SET REVIEW_FINDINGS_REMAINING: integer | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-completion.md
  RUN verify the returned fix manifest accounts for every APPROVED_REVIEW_FINDING_IDS entry as applied or not-fixable; SET REVIEW_FIXES_APPLIED = true WHEN one or more approved fixes changed skill/prompt/workflow files; SET REVIEW_FIXES_APPLIED = false WHEN no files changed; SET REVIEW_FINDINGS_REMAINING = count of findings not yet resolved after this fix iteration
  CONTINUE WriteSkillsValidate WHEN REVIEW_FIXES_APPLIED == true
  CONTINUE WriteSkillsFixOutcomeNoChanges WHEN findings remain but no fixes were applied this iteration (none approved, none applicable, or the ReviewFixApprovalGate resolved to none)
  CONTINUE WriteSkillsValidate WHEN REVIEW_FINDINGS_REMAINING == 0 AND VALIDATION_STATUS == unset
  CONTINUE WriteSkillsFixOutcomeDeterministicBlocker WHEN REVIEW_FINDINGS_REMAINING == 0 AND VALIDATION_STATUS == fail
  RUN WriteSkillsCleanExitGate WHEN REVIEW_FINDINGS_REMAINING == 0 AND (SKILL_FILE_WRITTEN == true OR REVIEW_FIXES_APPLIED == true)
```

```pdsl
UNIT WriteSkillsFixOutcomeNoChanges
PURPOSE: Report remaining findings and offer next actions when no approved fixes were applied.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md WHEN NextActionsOffer is not yet loaded
  EMIT a summary of remaining findings: count, IDs, and severities
  RUN NextActionsOffer
RULES:
  NEVER re-loop the review after an iteration with no applied fixes
  ALWAYS run NextActionsOffer before returning control to the user
```

```pdsl
UNIT WriteSkillsFixOutcomeClean
PURPOSE: Route a clean review report without requiring a fix manifest.
STATE:
  SET REVIEW_FINDINGS_REMAINING: integer | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE REVIEW_FINDINGS_REMAINING == 0
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-completion.md
  RUN WriteSkillsCleanExitGate WHEN SKILL_FILE_WRITTEN == true OR REVIEW_FIXES_APPLIED == true
  CONTINUE WriteSkillsCompletion WHEN REVIEW_LOOP_REQUESTED == true AND SKILL_FILE_WRITTEN != true AND REVIEW_FIXES_APPLIED != true
  CONTINUE WriteSkillsCompletion WHEN SKILL_FILE_WRITTEN == false AND REVIEW_FIXES_APPLIED != true
  CONTINUE WriteSkillsCompletion WHEN VALIDATION_STATUS == pass
```

```pdsl
UNIT WriteSkillsFixOutcomeDeterministicBlocker
PURPOSE: Report deterministic blockers and offer next actions when validation fails after all semantic findings are resolved.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md WHEN NextActionsOffer is not yet loaded
  EMIT a summary of deterministic blockers that remain after semantic fix application
  RUN NextActionsOffer with cf-prompting-ci or cf-coding-ci marked (suggested) depending on the target domain
RULES:
  ALWAYS run NextActionsOffer before returning control to the user
```
