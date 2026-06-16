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
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  SET ORIGINAL_INTENT = the user's triggering write-skills request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  RUN WorkflowBootstrapCommandDispatchContext
  RUN WriteSkillsBootstrapReferences
  CONTINUE WriteSkillsIntentCapture WHEN ORIGINAL_INTENT == unset
  CONTINUE WriteSkillsIntentClassify WHEN ORIGINAL_INTENT != unset
RULES:
  ALWAYS default to review-first routing when the request evaluates an existing skill, prompt, workflow, agent instruction, or system prompt rather than creating one
  ALWAYS route review/audit/critique/inspect/check/validate/verify/analyze/behavior-comparison/find-issues/bug-risk-failure-regression-bypass-defect-root-cause-routing-analysis intents through WriteSkillsReviewLoop first; any fixes must be gated by ReviewFindingsReportBrowser and ReviewFixApprovalGate, not by direct author dispatch
  ALWAYS apply current PDSL compactness and anti-duplication rules when authoring or reviewing: compactness counts top-level DO actions per UNIT, and redundant restatement in the same behavior path should be removed or factored when practical
  NEVER author or review a skill after a required reference load failure
```

```pdsl
UNIT WriteSkillsBootstrapReferences
PURPOSE: Load and verify the PDSL authoring references used by cf-write-skills.
DO:
  LOAD {cf-studio-path}/.core/architecture/specs/PDSL.md
  LOAD {cf-studio-path}/.core/requirements/prompt-engineering.md
  RUN verify both references loaded; EMIT "Required reference not found (PDSL spec or prompt-engineering methodology under {cf-studio-path}/.core) — cannot author or review; reinstall or sync the studio kit, then retry." and STOP_TURN WHEN either load fails
```

```pdsl
UNIT WriteSkillsIntentClassify
PURPOSE: Classify ORIGINAL_INTENT to set REVIEW_LOOP_REQUESTED, then set up routing vars and hand off to companion skill offer.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  RUN classify ORIGINAL_INTENT; SET REVIEW_LOOP_REQUESTED = true WHEN ORIGINAL_INTENT asks to review, audit, critique, inspect, check, validate, verify, analyze, compare behavior, or find issues/findings, bugs, risks, failures, regressions, bypasses, defects, root causes, routing problems, or behavioral-analysis concerns in an existing target (including review-and-fix wording), OR WHEN ORIGINAL_INTENT primarily evaluates an existing skill, prompt, workflow, agent instruction, or system prompt rather than creating one; SET REVIEW_LOOP_REQUESTED = false otherwise
  RUN WriteSkillsCompanionSetup
RULES:
  ALWAYS run after ORIGINAL_INTENT is set and before companion routing
  NEVER run when ORIGINAL_INTENT == unset
```

```pdsl
UNIT WriteSkillsCompanionSetup
PURPOSE: Prepare the companion-skill and plan-first routing handoff for cf-write-skills.
DO:
  SET PLAN_FIRST_CONTINUE = WriteSkillsDispatch
  SET CURRENT_WORKFLOW = cf-write-skills
  SET COMPANION_CONTINUE = WriteSkillsExploreGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md
  CONTINUE CompanionSkillOffer
```

```pdsl
UNIT WriteSkillsIntentCapture
PURPOSE: Capture the skill-writing target before any context discovery or design gate runs.
WHEN:
  REQUIRE ORIGINAL_INTENT == unset
DO:
  EMIT "Describe the skill, prompt, workflow, agent instruction, or system prompt work you want done. I need the target and goal before cf-explore or brainstorm can search usefully."
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER offer cf-explore, cf-brainstorm, or dispatch author/reviewer agents while ORIGINAL_INTENT == unset
```

```pdsl
UNIT WriteSkillsIntentResume
PURPOSE: Resume the workflow after the user provides the skill-writing target.
WHEN:
  REQUIRE user.reply exists
DO:
  SET ORIGINAL_INTENT = user.reply
  CONTINUE WriteSkillsIntentClassify
```

```pdsl
UNIT WriteSkillsExploreGate
PURPOSE: Offer task-relevant context discovery before any skill file is authored or reviewed, after Bootstrap and before the first edit.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  SET WORKFLOW_PREP_EXPLORE_MENU = WriteSkillsExploreMenu
  SET WORKFLOW_PREP_BRAINSTORM_GATE = WriteSkillsBrainstormGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/workflow-prep.md
  CONTINUE WorkflowPrepExploreGate
MENU WriteSkillsExploreMenu
TITLE: Before writing or reviewing a skill, discover task-relevant project context (sibling skills, workflows, agent contracts, referenced requirements, PDSL conventions) with cf-explore — or skip? Skip is the default when the target and its context are already clear; explore for unfamiliar or cross-cutting prompt work. Reply with a number.
OPTIONS:
  1 explore -> INVOKE skill `cf-explore` with intent=workflow-prep, task=ORIGINAL_INTENT, return_context=true; require it to return resource_context only and not perform review/authoring, SET RESOURCE_CONTEXT = provided, then CONTINUE WriteSkillsBrainstormGate
  2 skip -> CONTINUE WriteSkillsBrainstormGate
  INVALID -> EMIT_MENU WriteSkillsExploreMenu
```

```pdsl
UNIT WriteSkillsBrainstormGate
PURPOSE: Offer decision/design exploration via cf-brainstorm as the next step after the explore gate, before any skill file is authored or reviewed.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  SET WORKFLOW_PREP_BRAINSTORM_MENU = WriteSkillsBrainstormMenu
  SET WORKFLOW_PREP_DISPATCH_UNIT = PlanFirstGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/workflow-prep.md
  CONTINUE WorkflowPrepBrainstormGate
MENU WriteSkillsBrainstormMenu
TITLE: Before writing or reviewing a skill, brainstorm ambiguous decisions or design options with cf-brainstorm — or skip? Skip is the default when the approach is already clear; brainstorm for ambiguous requirements or open design questions. Reply with a number.
OPTIONS:
  1 brainstorm -> INVOKE skill `cf-brainstorm`; require it to return brainstorm_decisions, SET BRAINSTORM_DECISIONS = provided, then SET PLAN_FIRST_CONTINUE = WriteSkillsDispatch, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE PlanFirstGate
  2 skip -> SET PLAN_FIRST_CONTINUE = WriteSkillsDispatch, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE PlanFirstGate
  INVALID -> EMIT_MENU WriteSkillsBrainstormMenu
```

```pdsl
UNIT WriteSkillsValidate
PURPOSE: Validate authored PDSL with the deterministic validator.
WHEN:
  REQUIRE SKILL_FILE_WRITTEN == true
DO:
  RUN SubAgentDispatch for the cf-deterministic-validator dispatch group before launching deterministic PDSL validation
  RUN the deterministic PDSL check — dispatch cf-deterministic-validator for `{cfs_cmd} pdsl validate` on the written skill file
  EMIT the validation findings
  SET VALIDATION_STATUS = fail and CONTINUE WriteSkillsReviewLoop to fix them before proceeding WHEN validation reports fail or error
  SET VALIDATION_STATUS = pass and CONTINUE WriteSkillsReviewLoop WHEN validation passes
RULES:
  ALWAYS re-run WriteSkillsValidate after any fix before re-reviewing
```

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
UNIT WriteSkillsReviewSetup
PURPOSE: Load review modules, enforce anti-spin rules, and resolve review target paths before any reviewer is dispatched.
WHEN:
  REQUIRE SKILL_FILE_WRITTEN == true OR REVIEW_LOOP_REQUESTED == true
DO:
  RUN WriteSkillsReviewSetupLoadModules
  RUN SemanticReviewNoSpinRules
  RUN resolve REVIEW_TARGET_PATHS to the declared read-only file path or paths under review, and REVIEW_TARGET_SLICES to the declared reviewed content slices for those targets, before reviewer dispatch or approved-fix dispatch
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

```pdsl
UNIT WriteSkillsReviewSetupMissingTargets
PURPOSE: Stop when review target paths or slices were not resolved.
DO:
  EMIT "Review target resolution is required before reviewer dispatch. Provide the reviewed target path(s) and declared content slice(s) for the existing skill/prompt/workflow/agent instruction/system prompt under review."
  STOP_TURN
```

```pdsl
UNIT WriteSkillsReviewRun
PURPOSE: Gate review granularity, dispatch reviewer sub-agents, and aggregate their findings into one deduplicated report.
WHEN:
  REQUIRE REVIEW_TARGET_PATHS != unset
DO:
  SET REVIEW_GRANULARITY_SCOPE = "Skill/prompt review scope: single-pass covers prompt-engineering, prompt-bug-finding, and consistency-checklist together; per-methodology dispatches cf-pdsl-reviewer for prompt-engineering plus prompt-bug-finding and cf-semantic-reviewer-consistency separately; per-layer dispatches one reviewer per current layer/category."
  RUN SemanticReviewGranularityGate WHEN REVIEW_GRANULARITY == unset
  RUN SubAgentDispatch for the selected reviewer dispatch group before launching reviewer instances
  RUN prepare reviewer inputs for the chosen granularity: read each methodology's current Layer Map before per-layer or per-methodology dispatch, and synthesize into each reviewer instance only its assigned slice, declared REVIEW_TARGET_PATHS, REVIEW_TARGET_SLICES, and explicit read-only resource_context references
  RUN the chosen review at REVIEW_GRANULARITY: single-pass = dispatch cf-pdsl-reviewer from {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-reviewer.md and cf-semantic-reviewer-consistency from {cf-studio-path}/.core/skills/studio/agents/cf-semantic-reviewer-consistency.md in one combined dispatch group, then aggregate one report; per-methodology = dispatch cf-pdsl-reviewer over prompt-engineering plus prompt-bug-finding layers and cf-semantic-reviewer-consistency over all consistency-checklist categories in parallel; per-layer = dispatch one reviewer per layer/category for every layer each methodology defines (L1 through its last), never a fixed count
  RUN aggregate every reviewer's findings into one deduplicated ReviewFindingsReport with stable finding IDs and every ReviewFindingContract field, then SET REVIEW_FINDINGS_REMAINING = count of findings in the deduplicated ReviewFindingsReport
  CONTINUE WriteSkillsFixGate
RULES:
  ALWAYS scope each reviewer to only its assigned slice (all methodologies / one methodology / one layer) and run independent reviewers in parallel
  ALWAYS keep workflow-specific reviewer dispatches in this workflow
```

```pdsl
UNIT WriteSkillsFixGate
PURPOSE: Present review findings, gate fix approval, and route to fix dispatch or outcome.
WHEN:
  REQUIRE REVIEW_TARGET_PATHS != unset
DO:
  RUN SemanticReviewFixApprovalGate WHEN findings remain and fixes are applicable
  CONTINUE WriteSkillsFixDispatch WHEN REVIEW_FIX_APPROVED == true
  CONTINUE WriteSkillsFixOutcome
RULES:
  NEVER dispatch cf-pdsl-author as a generic review-fix worker because its contract is for new PDSL authoring
```

```pdsl
UNIT WriteSkillsFixDispatch
PURPOSE: Select the fix agent, dispatch it, and pass control to outcome verification.
DO:
  RUN select a concrete write-capable SELECTED_REVIEW_FIX_AGENT from the approved findings and REVIEW_TARGET_PATHS using the cf-generate-author prompt-workflow selection rules; choose cf-generate-prompt-engineer-smart when fixes affect state, routing, handoffs, validation, sub-agent dispatch, or output contracts
  RUN GitWriteDispatchPolicyResolve
  RUN SubAgentDispatch for the SELECTED_REVIEW_FIX_AGENT review-fix dispatch group
  RUN WriteSkillsFixDispatchRun
  CONTINUE WriteSkillsFixOutcome
```

```pdsl
UNIT WriteSkillsFixDispatchRun
PURPOSE: Launch the selected review-fix agent with only the approved fix scope.
DO:
  DISPATCH SELECTED_REVIEW_FIX_AGENT with mode=fix, kind=prompt, target_paths=REVIEW_TARGET_PATHS, REVIEW_TARGET_SLICES, APPROVED_REVIEW_FINDING_IDS, REVIEW_FIX_SCOPE, git_commit_mode=GIT_COMMIT_MODE, contributing_guide=CONTRIBUTING_GUIDE, git_constraint=GIT_CONSTRAINT, commit_footer_contract=COMMIT_FOOTER_CONTRACT, and explicit read-only resource_context references to apply only approved review fixes
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
  CONTINUE WriteSkillsCompletion WHEN REVIEW_FINDINGS_REMAINING == 0 AND REVIEW_LOOP_REQUESTED == true AND VALIDATION_STATUS == not-run
```

```pdsl
UNIT WriteSkillsFixOutcomeNoChanges
PURPOSE: Stop when no approved fixes were applied and findings still remain.
DO:
  STOP_TURN and report the remaining findings — re-reviewing unchanged skill files cannot change the result
```

```pdsl
UNIT WriteSkillsFixOutcomeDeterministicBlocker
PURPOSE: Stop when semantic findings are clear but deterministic validation still fails.
DO:
  STOP_TURN and report that deterministic blockers remain
```

```pdsl
UNIT WriteSkillsReviewLoop
PURPOSE: Run a semantic review at the user-chosen granularity and iterate fixes until the skill is clean.
WHEN:
  REQUIRE SKILL_FILE_WRITTEN == true OR REVIEW_LOOP_REQUESTED == true
DO:
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
  NEVER bypass NextActionsOffer on a clean terminal path that returns control to the user
```

```pdsl
UNIT WriteSkillsDispatch
PURPOSE: Route to review loop or author git setup.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  CONTINUE WriteSkillsReviewLoop WHEN REVIEW_LOOP_REQUESTED == true
  CONTINUE WriteSkillsAuthorGitSetup
```

```pdsl
UNIT WriteSkillsAuthorGitSetup
PURPOSE: Resolve git write policy before author dispatch.
DO:
  RUN GitWriteDispatchPolicyResolve
  CONTINUE WriteSkillsAuthorDispatch
```

```pdsl
UNIT WriteSkillsAuthorDispatch
PURPOSE: Run SubAgentDispatch, dispatch cf-pdsl-author, and mark the file as written.
DO:
  RUN SubAgentDispatch for the selected cf-pdsl-author dispatch group
  DISPATCH cf-pdsl-author from {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-author.md with git_commit_mode=GIT_COMMIT_MODE, contributing_guide=CONTRIBUTING_GUIDE, git_constraint=GIT_CONSTRAINT, commit_footer_contract=COMMIT_FOOTER_CONTRACT, and any WriteSkillsExploreGate-resolved resource_context as read-only context (absolute path or reference, never inline prompt text)
  SET SKILL_FILE_WRITTEN = true WHEN the author dispatch returned one or more paths in paths_written
  CONTINUE WriteSkillsValidate WHEN SKILL_FILE_WRITTEN == true
  STOP_TURN and report that the author sub-agent produced no output — request clarification or retry WHEN SKILL_FILE_WRITTEN == false
```
