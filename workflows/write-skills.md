---
cf: true
type: workflow
name: cf-write-skills
description: "Invoke when user intent is writing, revising, or reviewing skills, prompts, agentic workflows, sub agents, system prompts"
version: 0.1
---
# cf-write-skills
This skill authors and reviews skill/prompt files written in PDSL. It loads the PDSL spec and prompt-engineering guidance, optionally discovers task-relevant project context via cf-explore after bootstrap, validates authored files, and runs a semantic review-fix loop at a selectable depth — single-pass, per-methodology, or per-layer (one reviewer sub-agent per layer, every layer each methodology defines, L1 through its last) — over the prompt-engineering, prompt-bug-finding, and consistency-checklist methodologies, driven by author and reviewer sub-agents.

```pdsl
UNIT WriteSkillsBootstrap
PURPOSE: Load the references needed to author and review PDSL skills.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_PATHS: list | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_SLICES: list | unset (default unset, scope workflow_run)
  SET SKILL_FILE_WRITTEN: true | false (default false, scope workflow_run)
  SET REVIEW_FINDINGS_REMAINING: integer | unset (default unset, scope workflow_run)
  SET VALIDATION_STATUS: pass | fail | not-run (default not-run, scope workflow_run)
  SET REVIEW_GRANULARITY: single-pass | per-methodology | per-layer (default unset, scope workflow_run)
  SET SELECTED_REVIEW_FIX_AGENT: cf-generate-prompt-engineer-casual | cf-generate-prompt-engineer-smart | unset (default unset, scope workflow_run)
  SET REVIEW_FIXES_APPLIED: true | false | unset (default unset, scope workflow_run)
  SET WRITE_SKILLS_INTENT_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
  SET PATHS_WRITTEN: list | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  SET ORIGINAL_INTENT = the user's triggering write-skills request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  RUN WorkflowBootstrapCommandDispatchContext
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-bootstrap-refs.md
  RUN WriteSkillsBootstrapReferences
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-intent-routing.md
  CONTINUE WriteSkillsIntentCapture WHEN ORIGINAL_INTENT == unset
  CONTINUE WriteSkillsIntentClassify WHEN ORIGINAL_INTENT != unset
RULES:
  ALWAYS default to review-first routing when the request evaluates an existing skill, prompt, workflow, agent instruction, or system prompt rather than creating one
  ALWAYS route review/audit/critique/inspect/check/validate/verify/analyze/behavior-comparison/find-issues/bug-risk-failure-regression-bypass-defect-root-cause-routing-analysis intents through WriteSkillsReviewLoop first; any fixes must be gated by ReviewFindingsReportBrowser and ReviewFixApprovalGate, not by direct author dispatch
  ALWAYS apply current PDSL compactness and anti-duplication rules when authoring or reviewing: compactness counts top-level DO actions per UNIT, and redundant restatement in the same behavior path should be removed or factored when practical
  NEVER author or review a skill after a required reference load failure
```

```pdsl
UNIT WriteSkillsValidate
PURPOSE: Validate authored PDSL with the deterministic validator.
WHEN:
  REQUIRE SKILL_FILE_WRITTEN == true OR REVIEW_FIXES_APPLIED == true
DO:
  RUN SubAgentDispatch for the cf-deterministic-validator dispatch group before launching deterministic PDSL validation
  RUN the deterministic PDSL check — dispatch cf-deterministic-validator for `{cfs_cmd} pdsl validate` on REVIEW_TARGET_PATHS; author dispatch and later fix phases populate REVIEW_TARGET_PATHS before validation runs
  EMIT the validation findings
  SET VALIDATION_STATUS = fail and CONTINUE WriteSkillsReviewLoop to fix them before proceeding WHEN validation reports fail or error
  SET VALIDATION_STATUS = pass and CONTINUE WriteSkillsReviewLoop WHEN validation passes
RULES:
  ALWAYS re-run WriteSkillsValidate after any fix before re-reviewing
  ALWAYS continue to WriteSkillsReviewLoop when validation passes
  NEVER stop after content generation or deterministic validation before the semantic review-fix loop is offered
```

```pdsl
UNIT WriteSkillsReviewLoop
PURPOSE: Run a semantic review at the user-chosen granularity and iterate fixes until the skill is clean.
WHEN:
  REQUIRE SKILL_FILE_WRITTEN == true OR REVIEW_LOOP_REQUESTED == true
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-review-setup.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-review-run-fix.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-fix-outcomes.md
  CONTINUE WriteSkillsReviewSetup
```

```pdsl
UNIT WriteSkillsCompletion
PURPOSE: Emit a concise completion report, then offer context-grounded next actions after skill authoring/review completes cleanly.
WHEN:
  REQUIRE REVIEW_FINDINGS_REMAINING == 0
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT a concise completion report covering work done, deterministic validation outcome (including review-only flows with no deterministic validation run), and semantic review outcome with no remaining findings
  RUN NextActionsOffer
RULES:
  ALWAYS use this unit only after the skill author/review loop is complete and control is about to return to the user
  ALWAYS reach WriteSkillsCompletion only when no review findings remain
  NEVER bypass NextActionsOffer on a clean terminal path that returns control to the user
```

```pdsl
UNIT WriteSkillsDispatch
PURPOSE: Route to review loop or author git setup.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  CONTINUE WriteSkillsReviewLoop WHEN REVIEW_LOOP_REQUESTED == true
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-author-dispatch.md
  CONTINUE WriteSkillsAuthorGitSetup
```
