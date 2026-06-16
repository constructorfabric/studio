---
cf: true
type: workflow
name: cf-coding
description: "Invoke when user intent is writing, implementing, refactoring, fixing, or reviewing source code."
version: 0.1
---

# cf-coding

This skill authors and reviews source code using the code-checklist, bug-finding, and consistency-checklist methodologies. After bootstrap it optionally discovers task-relevant project context via cf-explore, runs a deterministic gate (tests, lint, typecheck, build), and runs a semantic review-fix loop at a selectable depth — single-pass, per-methodology, or per-layer — driven by coding and reviewer sub-agents.

```pdsl
UNIT CodingBootstrap
PURPOSE: Load the methodologies needed to author and review source code.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/skill-invocation-art.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/pdsl-execution-card.md
  RUN SkillInvocationArt
  LOAD and REMEMBER rules from {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/studio-instructions-memory.md
  RUN StudioInstructionsMemoryGate
  SET ORIGINAL_INTENT = the user's triggering coding request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/command-resolution.md
  RUN CommandResolution to resolve {cfs_cmd} and remember CLI capabilities
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md
  LOAD {cf-studio-path}/.core/requirements/code-checklist.md
  LOAD {cf-studio-path}/.core/requirements/bug-finding.md
  LOAD {cf-studio-path}/.core/requirements/consistency-checklist.md
  RUN verify the references loaded; EMIT "Required reference not found (code-checklist, bug-finding, or consistency-checklist methodology under {cf-studio-path}/.core) — cannot author or review code; reinstall or sync the studio kit, then retry." and STOP_TURN WHEN any load fails
  CONTINUE CodingIntentCapture WHEN ORIGINAL_INTENT == unset
  CONTINUE CodingIntentClassify WHEN ORIGINAL_INTENT != unset
RULES:
  ALWAYS run StudioInstructionsMemoryGate before coding context discovery, authoring, validation, or review
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, authoring, git use, or delegation
  ALWAYS load the code-checklist, bug-finding, and consistency-checklist methodologies before authoring or reviewing code
  ALWAYS load command-resolution before using remembered {cfs_cmd}/project commands in deterministic gates
  ALWAYS load context-memory before carrying resource_context or rule references into coder/reviewer dispatches
  ALWAYS capture ORIGINAL_INTENT before offering cf-explore, cf-brainstorm, or any write/review dispatch
  NEVER author or review code after a required reference load failure
```

```pdsl
UNIT CodingIntentCapture
PURPOSE: Capture the coding target before any context discovery or design gate runs.
DO:
  EMIT "Describe the code work you want done: the behavior, bug, refactor, review target, or files if known. I need that target before cf-explore or brainstorm can search usefully."
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS on the resumed reply set ORIGINAL_INTENT = user.reply, then CONTINUE CodingIntentClassify
  NEVER offer cf-explore, cf-brainstorm, or dispatch coder/reviewer agents while ORIGINAL_INTENT == unset
```

```pdsl
UNIT CodingIntentClassify
PURPOSE: Classify ORIGINAL_INTENT to set review-first routing, then hand off to companion skill offer.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  RUN classify ORIGINAL_INTENT by requested operation plus whether it evaluates existing code; SET REVIEW_LOOP_REQUESTED = true WHEN ORIGINAL_INTENT asks to review, audit, critique, inspect, check, validate, verify, analyze, compare behavior, or find issues/findings, bugs, risks, failures, regressions, bypasses, defects, root causes, routing problems, or behavioral-analysis concerns in existing code, including review-and-fix wording
  RUN default REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset AND ORIGINAL_INTENT primarily evaluates existing code rather than creating or changing it
  RUN classify ORIGINAL_INTENT; SET REVIEW_LOOP_REQUESTED = false WHEN REVIEW_LOOP_REQUESTED == unset
  SET PLAN_FIRST_CONTINUE = CodingDispatch
  SET CURRENT_WORKFLOW = cf-coding
  SET COMPANION_CONTINUE = CodingExploreGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md
  CONTINUE CompanionSkillOffer
RULES:
  ALWAYS derive REVIEW_LOOP_REQUESTED from ORIGINAL_INTENT before offering cf-explore, cf-brainstorm, planning, coder dispatch, reviewer dispatch, or validation
  ALWAYS default to review-first routing when the request evaluates existing code rather than creating or changing it
  ALWAYS route review/audit/critique/inspect/check/validate/verify/analyze/behavior-comparison/find-issues/bug-risk-failure-regression-bypass-defect-root-cause-routing-analysis intents through CodingReviewLoop first; any fixes must be gated by ReviewFindingsReportBrowser and ReviewFixApprovalGate, not by direct coder dispatch
  NEVER run when ORIGINAL_INTENT == unset
```

```pdsl
UNIT CodingExploreGate
PURPOSE: Offer task-relevant context discovery before any code is authored or reviewed, after Bootstrap and before the first edit.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  SET WORKFLOW_PREP_EXPLORE_MENU = CodingExploreMenu
  SET WORKFLOW_PREP_BRAINSTORM_GATE = CodingBrainstormGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/workflow-prep.md
  CONTINUE WorkflowPrepExploreGate
RULES:
  ALWAYS use WorkflowPrepExploreGate for the shared explore prompt mechanics
MENU CodingExploreMenu
TITLE: Before writing or reviewing code, discover task-relevant project context (existing conventions, related modules, call sites) with cf-explore — or skip? Skip is the default when the target and its context are already clear; explore for unfamiliar or cross-cutting code. Reply with a number.
OPTIONS:
  1 explore -> INVOKE skill `cf-explore` with intent=workflow-prep, task=ORIGINAL_INTENT, return_context=true; require it to return resource_context only and not perform review/authoring, SET RESOURCE_CONTEXT = provided, then CONTINUE CodingBrainstormGate
  2 skip -> CONTINUE CodingBrainstormGate
  INVALID -> EMIT_MENU CodingExploreMenu
```

```pdsl
UNIT CodingBrainstormGate
PURPOSE: Offer decision/design exploration via cf-brainstorm as the next step after the explore gate, before any code is authored or reviewed.
DO:
  SET WORKFLOW_PREP_BRAINSTORM_MENU = CodingBrainstormMenu
  SET WORKFLOW_PREP_DISPATCH_UNIT = PlanFirstGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/workflow-prep.md
  CONTINUE WorkflowPrepBrainstormGate
RULES:
  ALWAYS use WorkflowPrepBrainstormGate for the shared brainstorm prompt mechanics
MENU CodingBrainstormMenu
TITLE: Before writing or reviewing code, brainstorm ambiguous decisions or design options with cf-brainstorm — or skip? Skip is the default when the approach is already clear; brainstorm for ambiguous requirements or open design questions. Reply with a number.
OPTIONS:
  1 brainstorm -> INVOKE skill `cf-brainstorm`; require it to return brainstorm_decisions, SET BRAINSTORM_DECISIONS = provided, then SET PLAN_FIRST_CONTINUE = CodingDispatch, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE PlanFirstGate
  2 skip -> SET PLAN_FIRST_CONTINUE = CodingDispatch, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE PlanFirstGate
  INVALID -> EMIT_MENU CodingBrainstormMenu
```

```pdsl
UNIT CodingValidate
PURPOSE: Run the project's deterministic gate over authored or edited code.
STATE:
  SET GATE_STATUS: pass | fail (default unset, scope workflow_run)
WHEN:
  REQUIRE code has been written or edited
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  RUN SubAgentDispatch for the cf-deterministic-validator dispatch group before launching studio-applicable deterministic validation
  RUN the project's deterministic gate — resolve the test, lint, typecheck, and build commands from the project's config (package.json / Makefile / pyproject.toml / build files) or the remembered {cfs_cmd}/project commands, run them in order, and dispatch cf-deterministic-validator for studio-applicable checks (validate / validate-toc / check-language)
  EMIT the gate results
  SET GATE_STATUS = fail and CONTINUE CodingReviewLoop to fix them before proceeding WHEN any gate reports failures or errors
  SET GATE_STATUS = pass and CONTINUE CodingReviewLoop WHEN the deterministic gate passes
RULES:
  ALWAYS run tests, lint, typecheck, and build after writing or editing code
  NEVER treat code as done while any deterministic gate (tests/lint/typecheck/build) reports failures or errors; loop fixes until all pass
  ALWAYS run the deterministic gate via cf-deterministic-validator from {cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md plus the project's test/lint/typecheck/build commands
  ALWAYS prefer the project's configured commands and skip only gates that the project genuinely lacks (state which)
```

```pdsl
UNIT CodingReviewSetup
PURPOSE: Load review modules and anti-spin rules before reviewer dispatch.
WHEN:
  REQUIRE edits have been applied to the code OR REVIEW_LOOP_REQUESTED == true
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/finding-contract.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/semantic-loop-skeleton.md
  RUN SemanticReviewNoSpinRules
  CONTINUE CodingReviewRun
RULES:
  ALWAYS run before any reviewer dispatch in this workflow
  NEVER skip SemanticReviewNoSpinRules
```

```pdsl
UNIT CodingReviewRun
PURPOSE: Gate review granularity, dispatch reviewer sub-agents, and aggregate their findings into one report.
STATE:
  SET REVIEW_GRANULARITY: single-pass | per-methodology | per-layer (default unset, scope workflow_run)
WHEN:
  REQUIRE edits have been applied to the code OR REVIEW_LOOP_REQUESTED == true
DO:
  SET REVIEW_GRANULARITY_SCOPE = "Coding review scope: single-pass covers code-checklist, bug-finding, and consistency-checklist together; per-methodology dispatches cf-semantic-reviewer-code, cf-code-bug-finder, and cf-semantic-reviewer-consistency separately; per-layer dispatches one reviewer per current category/layer from those methodologies."
  RUN SemanticReviewGranularityGate WHEN REVIEW_GRANULARITY == unset
  RUN SubAgentDispatch for the selected code reviewer dispatch group before launching reviewer instances
  RUN the chosen review at REVIEW_GRANULARITY: single-pass = dispatch cf-semantic-reviewer-code, cf-code-bug-finder, and cf-semantic-reviewer-consistency in one combined dispatch group, then aggregate one report; per-methodology = dispatch cf-semantic-reviewer-code (code-checklist), cf-code-bug-finder (bug-finding), and cf-semantic-reviewer-consistency (consistency-checklist — cross-checks the change against surrounding docs/specs/comments, not the code logic) in parallel; per-layer = dispatch one reviewer per current category/layer for each applicable methodology
  RUN aggregation of every reviewer's findings into one deduplicated ReviewFindingsReport with stable finding IDs and every ReviewFindingContract field
  CONTINUE CodingReviewFixGate
RULES:
  ALWAYS read each methodology's current category/layer map (code-checklist categories, bug-finding layers, consistency-checklist categories) before a per-layer or per-methodology dispatch, so added layers are covered automatically and never a fixed count
  ALWAYS scope each reviewer to only its assigned slice (all methodologies / one methodology / one category-or-layer) and run independent reviewers in parallel
  ALWAYS keep workflow-specific reviewer dispatches in this workflow
  ALWAYS run SubAgentDispatch before every reviewer dispatch group
  ALWAYS dispatch cf-semantic-reviewer-code (code-checklist), cf-code-bug-finder (bug-finding), and cf-semantic-reviewer-consistency (consistency-checklist) from {cf-studio-path}/.core/skills/studio/agents/ per the chosen REVIEW_GRANULARITY: single-pass = all three methodology reviewers in one combined dispatch group with one aggregated report; per-methodology = one cf-semantic-reviewer-code over all code-checklist categories, one cf-code-bug-finder over all bug-finding layers, and one cf-semantic-reviewer-consistency over all consistency-checklist categories; per-layer = one reviewer per category/layer for every category/layer each methodology defines, run in parallel, never a fixed count — read each methodology's current category/layer map before dispatch
  ALWAYS synthesize into each reviewer instance only its assigned methodology/category/layer slice, never more than its scope
  ALWAYS include any CodingExploreGate-resolved resource_context in every reviewer dispatch payload as read-only context (an absolute path or reference, never inline prompt text), NEVER as a gate on a reviewer verdict
```

```pdsl
UNIT CodingReviewFixGate
PURPOSE: Present review findings, gate fix approval, and route to fix dispatch or outcome.
WHEN:
  REQUIRE edits have been applied to the code OR REVIEW_LOOP_REQUESTED == true
DO:
  RUN SemanticReviewFixApprovalGate WHEN findings remain and fixes are applicable
  CONTINUE CodingReviewFixDispatch WHEN REVIEW_FIX_APPROVED == true
  CONTINUE CodingReviewFixOutcome
RULES:
  ALWAYS render the interactive ReviewFindingsReportBrowser from fix-approval before any fix-scope menu, so the user can inspect findings one by one, move next/previous, mark findings for fix, switch to a full table, and then choose a clear fix scope
```

```pdsl
UNIT CodingReviewFixDispatch
PURPOSE: Select the approved-fix coder, enforce git write policy, and dispatch only the approved fixes.
STATE:
  SET SELECTED_REVIEW_FIX_AGENT: cf-codegen | cf-generate-coder-smart | cf-generate-coder-casual | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE REVIEW_FIX_APPROVED == true
DO:
  RUN GitCommitModeGate before preparing git policy for approved review-fix dispatch
  RUN resolve git_commit_mode (probe once per session), contributing_guide (discover; use null for no discovered guide), and the mode-matched git_constraint before approved review-fix dispatch
  RUN select SELECTED_REVIEW_FIX_AGENT from approved findings and target code paths using CodingAuthorDispatch priority
  RUN SubAgentDispatch for the SELECTED_REVIEW_FIX_AGENT review-fix dispatch group
  DISPATCH SELECTED_REVIEW_FIX_AGENT with mode=fix, target_paths, APPROVED_REVIEW_FINDING_IDS, REVIEW_FIX_SCOPE, git_commit_mode, contributing_guide, git_constraint, commit_footer_contract, and resource_context to apply only approved review fixes
  CONTINUE CodingReviewFixOutcome
RULES:
  ALWAYS after REVIEW_FIX_APPROVED == true, select a concrete write-capable coder and pass APPROVED_REVIEW_FINDING_IDS plus REVIEW_FIX_SCOPE so approvals cannot widen silently
  ALWAYS run GitCommitModeGate before any write-capable coder dispatch, including approved review-fix dispatch
  ALWAYS resolve git_commit_mode (probe once per session), contributing_guide (discover; use null for no discovered guide), and the mode-matched git_constraint before approved review-fix dispatch, and ALWAYS include all three in that dispatch payload
  ALWAYS run SubAgentDispatch before every review-fix dispatch group
  ALWAYS include any CodingExploreGate-resolved resource_context in the review-fix dispatch payload as read-only context (an absolute path or reference, never inline prompt text), NEVER as a gate on the fix verdict
  NEVER rely on a stale or implicit coder selection for approved review fixes
```

```pdsl
UNIT CodingReviewFixOutcome
PURPOSE: Verify fix application, prevent no-spin loops, and route to validation or completion.
STATE:
  SET REVIEW_FIXES_APPLIED: true | false | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE edits have been applied to the code OR REVIEW_LOOP_REQUESTED == true
DO:
  RUN verify the returned fix manifest accounts for every APPROVED_REVIEW_FINDING_IDS entry as applied or not-fixable; SET REVIEW_FIXES_APPLIED = true WHEN one or more approved fixes changed code; SET REVIEW_FIXES_APPLIED = false WHEN no code changed
  CONTINUE CodingValidate WHEN REVIEW_FIXES_APPLIED == true
  STOP_TURN and report the remaining findings WHEN findings remain but no fixes were applied this iteration (none approved, none applicable, or the ReviewFixApprovalGate resolved to none)
  STOP_TURN and report deterministic blockers WHEN no review findings remain AND GATE_STATUS == fail
  CONTINUE CodingCompletion WHEN no review findings remain AND (REVIEW_LOOP_REQUESTED == true OR GATE_STATUS == pass)
RULES:
  NEVER declare authored or edited code done until BOTH the deterministic gate (tests/lint/typecheck/build) passes AND the semantic review has no remaining findings
  ALWAYS re-run CodingValidate after any fix before re-reviewing
  NEVER re-loop the review after an iteration with no applied fixes — STOP_TURN reporting the remaining findings so the loop cannot spin on unchanged code; only an applied fix re-runs CodingValidate and re-reviews
```

```pdsl
UNIT CodingReviewLoop
PURPOSE: Run a semantic review at the user-chosen granularity and iterate fixes until the code is clean.
WHEN:
  REQUIRE edits have been applied to the code OR REVIEW_LOOP_REQUESTED == true
DO:
  CONTINUE CodingReviewSetup
RULES:
  NEVER declare authored or edited code done until BOTH the deterministic gate (tests/lint/typecheck/build) passes AND the semantic review has no remaining findings
  ALWAYS re-run CodingValidate after any fix before re-reviewing
```

```pdsl
UNIT CodingCompletion
PURPOSE: Emit a concise completion report, then offer context-grounded next actions after code authoring/review completes cleanly.
WHEN:
  REQUIRE no review findings remain
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT a concise completion report covering work done, gate outcome, and semantic review outcome
  RUN NextActionsOffer
RULES:
  ALWAYS use this unit only after code validation/review is complete, report the deterministic gate outcome (including review-only flows with no deterministic gate run), and state semantic review has no remaining findings before NextActionsOffer
  NEVER bypass NextActionsOffer on a clean terminal path
```

```pdsl
UNIT CodingDispatch
PURPOSE: Route to review-first or author-first code execution paths.
DO:
  CONTINUE CodingReviewLoop WHEN REVIEW_LOOP_REQUESTED == true
  CONTINUE CodingAuthorGitSetup
RULES:
  ALWAYS prefer REVIEW_LOOP_REQUESTED == true over coder routing, so review-and-fix requests produce findings first and only apply fixes after the review fix-approval gate
  NEVER stop after code generation or deterministic validation before the semantic review-fix loop is offered
  NEVER let a sub-agent reopen prompt or instruction files from disk
```

```pdsl
UNIT CodingAuthorGitSetup
PURPOSE: Resolve git write policy before author dispatch.
DO:
  RUN GitCommitModeGate before preparing git policy for coder dispatch
  RUN resolve git_commit_mode (probe once per session), contributing_guide (discover; use null for no discovered guide), and the mode-matched git_constraint
  CONTINUE CodingAuthorDispatch
RULES:
  ALWAYS run GitCommitModeGate before any write-capable coder dispatch, even for tasks that did not ask to commit
  ALWAYS resolve git_commit_mode, contributing_guide, and the mode-matched git_constraint before any write-capable coder dispatch
```

```pdsl
UNIT CodingAuthorDispatch
PURPOSE: Select the coding author, dispatch it, and route written code into validation.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  RUN SubAgentDispatch for the selected coding author dispatch group
  RUN selected coding author/fix agent for requested code writes or fixes
  CONTINUE CodingValidate WHEN code has been written or edited
RULES:
  ALWAYS select the coding author/fix agent under {cf-studio-path}/.core/skills/studio/agents/ by this priority order (first match wins): (1) cf-codegen.md for fully specified tasks implementable in an isolated context with no clarification; else (2) cf-generate-coder-smart.md for changes involving behavior, tests, refactors, API boundaries, or any security/concurrency/data-model implication; else (3) cf-generate-coder-casual.md for small code-only tasks touching at most two source/test files with no security/concurrency/data-model risk; else cf-generate-coder-smart.md as the default
  ALWAYS run SubAgentDispatch before every native coder dispatch group; inline fallback executes the same selected contract without native dispatch
  ALWAYS include git_commit_mode, contributing_guide, and git_constraint in every write-capable coder dispatch payload
  ALWAYS include any CodingExploreGate-resolved resource_context in every coder dispatch payload as read-only context (an absolute path or reference, never inline prompt text), NEVER as a gate on a coder verdict
  ALWAYS after any coder dispatch changes code, run the deterministic gate and then offer review granularity before semantic review
```
