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
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  SET ORIGINAL_INTENT = the user's triggering coding request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  RUN WorkflowBootstrapCommandContext
  RUN CodingBootstrapMethodologies
  CONTINUE CodingIntentCapture WHEN ORIGINAL_INTENT == unset
  CONTINUE CodingIntentClassify WHEN ORIGINAL_INTENT != unset
RULES:
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, authoring, git use, or delegation
  NEVER author or review code after a required reference load failure
```

```pdsl
UNIT CodingBootstrapMethodologies
PURPOSE: Load and verify the code review methodologies used by cf-coding.
DO:
  LOAD {cf-studio-path}/.core/requirements/code-checklist.md
  LOAD {cf-studio-path}/.core/requirements/bug-finding.md
  LOAD {cf-studio-path}/.core/requirements/consistency-checklist.md
  RUN verify the references loaded; EMIT "Required reference not found (code-checklist, bug-finding, or consistency-checklist methodology under {cf-studio-path}/.core) — cannot author or review code; reinstall or sync the studio kit, then retry." and STOP_TURN WHEN any load fails
```

```pdsl
UNIT CodingIntentCapture
PURPOSE: Capture the coding target before any context discovery or design gate runs.
DO:
  EMIT "Describe the code work you want done: the behavior, bug, refactor, review target, or files if known. I need that target before cf-explore or brainstorm can search usefully."
  CONTINUE CodingIntentResume after user.reply
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER offer cf-explore, cf-brainstorm, or dispatch coder/reviewer agents while ORIGINAL_INTENT == unset
```

```pdsl
UNIT CodingIntentResume
PURPOSE: Resume the workflow after the user provides the coding target.
WHEN:
  REQUIRE user.reply exists
DO:
  SET ORIGINAL_INTENT = user.reply
  CONTINUE CodingIntentClassify
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
  RUN CodingCompanionSetup
RULES:
  ALWAYS route review/audit/critique/inspect/check/validate/verify/analyze/behavior-comparison/find-issues/bug-risk-failure-regression-bypass-defect-root-cause-routing-analysis intents through CodingReviewLoop first; any fixes must be gated by ReviewFindingsReportBrowser and ReviewFixApprovalGate, not by direct coder dispatch
  NEVER run when ORIGINAL_INTENT == unset
```

```pdsl
UNIT CodingCompanionSetup
PURPOSE: Prepare the companion-skill and plan-first routing handoff for cf-coding.
DO:
  SET PLAN_FIRST_CONTINUE = CodingDispatch
  SET CURRENT_WORKFLOW = cf-coding
  SET COMPANION_CONTINUE = CodingExploreGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md
  CONTINUE CompanionSkillOffer
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
  NEVER treat code as done while any deterministic gate (tests/lint/typecheck/build) reports failures or errors; loop fixes until all pass
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
```

```pdsl
UNIT CodingReviewerDispatchPolicy
PURPOSE: Prepare scoped reviewer payloads for the selected coding review granularity.
STATE:
  SET SELECTED_REVIEWER_DISPATCH_GROUP: dispatch-group | unset (default unset, scope workflow_run)
  SET REVIEWER_SCOPE_MANIFEST: manifest | unset (default unset, scope workflow_run)
DO:
  RUN read each methodology's current category/layer map (code-checklist categories, bug-finding layers, consistency-checklist categories) before a per-layer or per-methodology dispatch, so added layers are covered automatically and never a fixed count
  SET REVIEWER_SCOPE_MANIFEST = each reviewer instance with only its assigned methodology/category/layer slice and any CodingExploreGate-resolved resource_context as read-only context (an absolute path or reference, never inline prompt text)
  SET SELECTED_REVIEWER_DISPATCH_GROUP for REVIEW_GRANULARITY: single-pass = cf-semantic-reviewer-code, cf-code-bug-finder, and cf-semantic-reviewer-consistency in one combined dispatch group; per-methodology = one reviewer per methodology; per-layer = one reviewer per category/layer for every category/layer each methodology defines, run in parallel
RULES:
  ALWAYS keep workflow-specific reviewer dispatches in this workflow
  NEVER let resource_context gate a reviewer verdict
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
  RUN CodingReviewerDispatchPolicy
  RUN SubAgentDispatch for SELECTED_REVIEWER_DISPATCH_GROUP before launching reviewer instances
  RUN SELECTED_REVIEWER_DISPATCH_GROUP with REVIEWER_SCOPE_MANIFEST
  RUN aggregation of every reviewer's findings into one deduplicated ReviewFindingsReport with stable finding IDs and every ReviewFindingContract field
  CONTINUE CodingReviewFixGate
RULES:
  ALWAYS scope each reviewer to only its assigned slice (all methodologies / one methodology / one category-or-layer) and run independent reviewers in parallel
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
```

```pdsl
UNIT CodingReviewFixDispatch
PURPOSE: Select the approved-fix coder, enforce git write policy, and dispatch only the approved fixes.
STATE:
  SET SELECTED_REVIEW_FIX_AGENT: cf-codegen | cf-generate-coder-smart | cf-generate-coder-casual | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE REVIEW_FIX_APPROVED == true
DO:
  RUN GitWriteDispatchPolicyResolve
  RUN select SELECTED_REVIEW_FIX_AGENT from approved findings and target code paths using CodingAuthorDispatch priority
  RUN SubAgentDispatch for the SELECTED_REVIEW_FIX_AGENT review-fix dispatch group
  DISPATCH SELECTED_REVIEW_FIX_AGENT with mode=fix, target_paths, APPROVED_REVIEW_FINDING_IDS, REVIEW_FIX_SCOPE, git_commit_mode=GIT_COMMIT_MODE, contributing_guide=CONTRIBUTING_GUIDE, git_constraint=GIT_CONSTRAINT, commit_footer_contract=COMMIT_FOOTER_CONTRACT, and resource_context to apply only approved review fixes
  CONTINUE CodingReviewFixOutcome
RULES:
  NEVER let approvals widen silently beyond APPROVED_REVIEW_FINDING_IDS and REVIEW_FIX_SCOPE
  NEVER let resource_context gate the fix verdict
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
```

```pdsl
UNIT CodingCompletion
PURPOSE: Emit a concise completion report, then offer context-grounded next actions after code authoring/review completes cleanly.
WHEN:
  REQUIRE no review findings remain
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT a concise completion report covering work done, deterministic gate outcome (or "not run" when GATE_STATUS is unset), and semantic review outcome
  RUN NextActionsOffer
RULES:
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
  RUN GitWriteDispatchPolicyResolve
  CONTINUE CodingAuthorDispatch
```

```pdsl
UNIT CodingAuthorDispatch
PURPOSE: Select the coding author, dispatch it, and route written code into validation.
STATE:
  SET SELECTED_CODING_AGENT: cf-codegen | cf-generate-coder-smart | cf-generate-coder-casual | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  SET SELECTED_CODING_AGENT by this priority order (first match wins): (1) cf-codegen for fully specified tasks implementable in an isolated context with no clarification; else (2) cf-generate-coder-smart for changes involving behavior, tests, refactors, API boundaries, or any security/concurrency/data-model implication; else (3) cf-generate-coder-casual for small code-only tasks touching at most two source/test files with no security/concurrency/data-model risk; else cf-generate-coder-smart as the default
  RUN SubAgentDispatch for SELECTED_CODING_AGENT dispatch group
  DISPATCH SELECTED_CODING_AGENT with git_commit_mode=GIT_COMMIT_MODE, contributing_guide=CONTRIBUTING_GUIDE, git_constraint=GIT_CONSTRAINT, commit_footer_contract=COMMIT_FOOTER_CONTRACT, and any CodingExploreGate-resolved resource_context as read-only context (absolute path or reference, never inline prompt text)
  CONTINUE CodingValidate WHEN code has been written or edited
RULES:
  NEVER let resource_context gate a coder verdict
```
