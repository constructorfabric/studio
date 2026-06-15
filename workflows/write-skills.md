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
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/skill-invocation-art.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/pdsl-execution-card.md
  RUN SkillInvocationArt
  LOAD and REMEMBER rules from {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/studio-instructions-memory.md
  RUN StudioInstructionsMemoryGate
  SET ORIGINAL_INTENT = the user's triggering write-skills request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/command-resolution.md
  RUN CommandResolution to resolve {cfs_cmd} and remember CLI capabilities
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md
  LOAD {cf-studio-path}/.core/architecture/specs/PDSL.md
  LOAD {cf-studio-path}/.core/requirements/prompt-engineering.md
  RUN verify both references loaded; EMIT "Required reference not found (PDSL spec or prompt-engineering methodology under {cf-studio-path}/.core) — cannot author or review; reinstall or sync the studio kit, then retry." and STOP_TURN WHEN either load fails
  CONTINUE WriteSkillsIntentCapture WHEN ORIGINAL_INTENT == unset
  RUN classify ORIGINAL_INTENT by requested operation plus whether it evaluates an existing skill, prompt, workflow, agent instruction, or system prompt; SET REVIEW_LOOP_REQUESTED = true WHEN ORIGINAL_INTENT asks to review, audit, critique, inspect, check, validate, verify, analyze, compare behavior, or find issues/findings, bugs, risks, failures, regressions, bypasses, defects, root causes, routing problems, or behavioral-analysis concerns in an existing target, including review-and-fix wording
  RUN default REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset AND ORIGINAL_INTENT primarily evaluates an existing skill, prompt, workflow, agent instruction, or system prompt rather than creating one
  RUN classify ORIGINAL_INTENT; SET REVIEW_LOOP_REQUESTED = false WHEN REVIEW_LOOP_REQUESTED == unset
  SET PLAN_FIRST_CONTINUE = WriteSkillsDispatch, SET CURRENT_WORKFLOW = cf-write-skills, SET COMPANION_CONTINUE = WriteSkillsExploreGate, LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE CompanionSkillOffer WHEN ORIGINAL_INTENT != unset
RULES:
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, authoring, git use, or delegation
  ALWAYS default to review-first routing when the request evaluates an existing skill, prompt, workflow, agent instruction, or system prompt rather than creating one
  ALWAYS route review/audit/critique/inspect/check/validate/verify/analyze/behavior-comparison/find-issues/bug-risk-failure-regression-bypass-defect-root-cause-routing-analysis intents through WriteSkillsReviewLoop first; any fixes must be gated by ReviewFindingsReportBrowser and ReviewFixApprovalGate, not by direct author dispatch
  NEVER author or review a skill after a required reference load failure
```

```pdsl
UNIT WriteSkillsIntentCapture
PURPOSE: Capture the skill-writing target before any context discovery or design gate runs.
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
  REQUIRE ORIGINAL_INTENT == unset
DO:
  SET ORIGINAL_INTENT = user.reply
  RUN derive REVIEW_LOOP_REQUESTED from ORIGINAL_INTENT using the Bootstrap review-intent classification
  SET PLAN_FIRST_CONTINUE = WriteSkillsDispatch
  SET CURRENT_WORKFLOW = cf-write-skills
  SET COMPANION_CONTINUE = WriteSkillsExploreGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md
  CONTINUE CompanionSkillOffer
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
STATE:
  SET VALIDATION_STATUS: pass | fail | not-run (default not-run, scope workflow_run)
WHEN:
  REQUIRE a skill file has been written or edited
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  RUN SubAgentDispatch for the cf-deterministic-validator dispatch group before launching deterministic PDSL validation
  RUN the deterministic PDSL check — dispatch cf-deterministic-validator for `{cfs_cmd} pdsl validate` on the written skill file
  EMIT the validation findings
  SET VALIDATION_STATUS = fail and CONTINUE WriteSkillsReviewLoop to fix them before proceeding WHEN validation reports fail or error
  SET VALIDATION_STATUS = pass and CONTINUE WriteSkillsReviewLoop WHEN validation passes
RULES:
  NEVER treat a skill as done before BOTH the deterministic PDSL check `{cfs_cmd} pdsl validate` passes AND the semantic review-fix loop has been offered and completed
```

```pdsl
UNIT WriteSkillsReviewLoop
PURPOSE: Run a semantic review at the user-chosen granularity and iterate fixes until the skill is clean.
STATE:
  SET REVIEW_GRANULARITY: single-pass | per-methodology | per-layer (default unset, scope workflow_run)
  SET SELECTED_REVIEW_FIX_AGENT: cf-generate-prompt-engineer-casual | cf-generate-prompt-engineer-smart | unset (default unset, scope workflow_run)
  SET REVIEW_FIXES_APPLIED: true | false | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE edits have been applied to the skill file OR REVIEW_LOOP_REQUESTED == true
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  LOAD {cf-studio-path}/.core/requirements/prompt-bug-finding.md
  LOAD {cf-studio-path}/.core/requirements/consistency-checklist.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/finding-contract.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/semantic-loop-skeleton.md
  RUN SemanticReviewNoSpinRules
  RUN resolve REVIEW_TARGET_PATHS to the declared read-only file path or paths under review, and REVIEW_TARGET_SLICES to the declared reviewed content slices for those targets, before reviewer dispatch or approved-fix dispatch
  EMIT "Review target resolution is required before reviewer dispatch. Provide the reviewed target path(s) and declared content slice(s) for the existing skill/prompt/workflow/agent instruction/system prompt under review." and STOP_TURN WHEN REVIEW_LOOP_REQUESTED == true AND (REVIEW_TARGET_PATHS == unset OR REVIEW_TARGET_SLICES == unset)
  SET REVIEW_GRANULARITY_SCOPE = "Skill/prompt review scope: single-pass covers prompt-engineering, prompt-bug-finding, and consistency-checklist together; per-methodology dispatches cf-pdsl-reviewer for prompt-engineering plus prompt-bug-finding and cf-semantic-reviewer-consistency separately; per-layer dispatches one reviewer per current layer/category."
  RUN SemanticReviewGranularityGate WHEN REVIEW_GRANULARITY == unset
  RUN SubAgentDispatch for the selected reviewer dispatch group before launching reviewer instances
  RUN read each methodology's current Layer Map (prompt-engineering layers, prompt-bug-finding layers, consistency-checklist categories) before per-layer or per-methodology dispatch, so added layers are covered automatically and never a fixed count
  RUN the chosen review at REVIEW_GRANULARITY: single-pass = dispatch cf-pdsl-reviewer from {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-reviewer.md and cf-semantic-reviewer-consistency from {cf-studio-path}/.core/skills/studio/agents/cf-semantic-reviewer-consistency.md in one combined dispatch group, then aggregate one report; per-methodology = dispatch cf-pdsl-reviewer over prompt-engineering plus prompt-bug-finding layers and cf-semantic-reviewer-consistency over all consistency-checklist categories in parallel; per-layer = dispatch one reviewer per layer/category for every layer each methodology defines (L1 through its last), never a fixed count
  RUN aggregation of every reviewer's findings into one deduplicated ReviewFindingsReport with stable finding IDs and every ReviewFindingContract field
  RUN render the interactive ReviewFindingsReportBrowser from fix-approval before any fix-scope menu WHEN findings remain and fixes are applicable
  RUN SemanticReviewFixApprovalGate WHEN findings remain and fixes are applicable
  RUN select SELECTED_REVIEW_FIX_AGENT from the approved findings and REVIEW_TARGET_PATHS using the cf-generate-author prompt-workflow selection rules; choose cf-generate-prompt-engineer-smart when fixes affect state, routing, handoffs, validation, sub-agent dispatch, or output contracts WHEN REVIEW_FIX_APPROVED == true
  RUN SubAgentDispatch for the SELECTED_REVIEW_FIX_AGENT review-fix dispatch group WHEN REVIEW_FIX_APPROVED == true
  DISPATCH SELECTED_REVIEW_FIX_AGENT with mode=fix, kind=prompt, target_paths=REVIEW_TARGET_PATHS, REVIEW_TARGET_SLICES, APPROVED_REVIEW_FINDING_IDS, REVIEW_FIX_SCOPE, git_commit_mode, contributing_guide, git_constraint, commit_footer_contract, and resource_context to apply only approved review fixes WHEN REVIEW_FIX_APPROVED == true
  RUN verify the returned fix manifest accounts for every APPROVED_REVIEW_FINDING_IDS entry as applied or not-fixable; SET REVIEW_FIXES_APPLIED = true WHEN one or more approved fixes changed skill/prompt/workflow files; SET REVIEW_FIXES_APPLIED = false WHEN no files changed
  CONTINUE WriteSkillsValidate WHEN REVIEW_FIXES_APPLIED == true
  STOP_TURN and report the remaining findings WHEN findings remain but no fixes were applied this iteration (none approved, none applicable, or the ReviewFixApprovalGate resolved to none) — re-reviewing unchanged skill files cannot change the result
  STOP_TURN and report that deterministic blockers remain WHEN no review findings remain AND VALIDATION_STATUS == fail
  CONTINUE WriteSkillsCompletion WHEN no review findings remain AND REVIEW_LOOP_REQUESTED == true
  CONTINUE WriteSkillsCompletion WHEN no review findings remain AND VALIDATION_STATUS == pass
RULES:
  ALWAYS scope each reviewer to only its assigned slice (all methodologies / one methodology / one layer) and run independent reviewers in parallel
  ALWAYS keep workflow-specific reviewer dispatches in this workflow
  ALWAYS select a concrete write-capable prompt-engineer worker inside WriteSkillsReviewLoop after REVIEW_FIX_APPROVED == true; NEVER dispatch cf-pdsl-author as a generic review-fix worker because its contract is for new PDSL authoring
  NEVER declare an authored or edited skill done until BOTH the deterministic PDSL check `{cfs_cmd} pdsl validate` passes AND the semantic review has no remaining findings; ALWAYS re-run WriteSkillsValidate after any fix before re-reviewing
```

```pdsl
UNIT WriteSkillsCompletion
PURPOSE: Emit a concise completion report, then offer context-grounded next actions after skill authoring/review completes cleanly.
WHEN:
  REQUIRE no review findings remain
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
PURPOSE: Dispatch the sub-agents that write, fix, and review skills.
DO:
  CONTINUE WriteSkillsReviewLoop WHEN REVIEW_LOOP_REQUESTED == true
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md WHEN requested skill/prompt/workflow/agent instruction writes or fixes OR reviewer dispatch is needed
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md WHEN requested skill/prompt/workflow/agent instruction writes or fixes
  RUN GitCommitModeGate before preparing git policy for author dispatch WHEN requested skill/prompt/workflow/agent instruction writes or fixes
  RUN resolve git_commit_mode (probe once per session), contributing_guide (discover; use null for no discovered guide), and the mode-matched git_constraint WHEN requested skill/prompt/workflow/agent instruction writes or fixes
  RUN SubAgentDispatch for the selected cf-pdsl-author dispatch group WHEN requested skill/prompt/workflow/agent instruction writes or fixes
  DISPATCH cf-pdsl-author from {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-author.md with git_commit_mode, contributing_guide, git_constraint, commit_footer_contract, and any WriteSkillsExploreGate-resolved resource_context as read-only context (absolute path or reference, never inline prompt text) for requested skill/prompt/workflow/agent instruction writes or fixes WHEN requested skill/prompt/workflow/agent instruction writes or fixes
  CONTINUE WriteSkillsValidate WHEN a skill file has been written or edited
RULES:
  ALWAYS use a concrete cf-generate-prompt-engineer-* worker for approved review fixes to existing prompt/workflow/agent instruction files
  ALWAYS run SubAgentDispatch before every native author, validator, reviewer, or review-fix dispatch group; inline fallback executes the same selected contract without native dispatch
  NEVER stop after content generation or deterministic validation before the semantic review-fix loop is offered
  ALWAYS synthesize into each reviewer instance only its assigned slice for the chosen granularity, never more than its scope
  NEVER let a sub-agent rediscover or reopen prompt or instruction assets from disk outside the declared REVIEW_TARGET_PATHS, REVIEW_TARGET_SLICES, and any explicit read-only resource_context
```
