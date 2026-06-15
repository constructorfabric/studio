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
PURPOSE: Ensure the cf skill is loaded, then load the methodologies needed to author and review source code.
STATE:
  SET CFS_INIT: true | false (default false, scope session)
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
DO:
  SET ORIGINAL_INTENT = the user's triggering coding request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  EMIT_MENU LoadCfSkillConfirm WHEN CFS_INIT != true
  STOP_TURN WHEN CFS_INIT != true
  LOAD {cf-studio-path}/.core/requirements/code-checklist.md
  LOAD {cf-studio-path}/.core/requirements/bug-finding.md
  LOAD {cf-studio-path}/.core/requirements/consistency-checklist.md
  RUN verify the references loaded; EMIT "Required reference not found (code-checklist, bug-finding, or consistency-checklist methodology under {cf-studio-path}/.core) — cannot author or review code; reinstall or sync the studio kit, then retry." and STOP_TURN WHEN any load fails
  CONTINUE CodingIntentCapture WHEN ORIGINAL_INTENT == unset
  CONTINUE CodingExploreGate WHEN ORIGINAL_INTENT != unset
RULES:
  ALWAYS verify the cf skill is loaded, CFS_INIT == true, before authoring or reviewing code
  ALWAYS treat CFS_INIT as false when its value is unknown, ambiguous, or unset
  NEVER proceed past CodingBootstrap unless CFS_INIT == true is positively confirmed
  ALWAYS load the code-checklist, bug-finding, and consistency-checklist methodologies before authoring or reviewing code
  ALWAYS capture ORIGINAL_INTENT before offering cf-explore, cf-brainstorm, or any write/review dispatch
  NEVER author or review code when a required reference failed to load
MENU LoadCfSkillConfirm
TITLE: The cf skill is not loaded. It is the Constructor Studio core that loads the shared rules and routes to cf-* skills, so coding cannot run without it. Load it now to continue?
OPTIONS:
  1 load -> INVOKE skill `cf` and CONTINUE CodingBootstrap
  2 stop -> STOP_TURN
  INVALID -> EMIT_MENU LoadCfSkillConfirm
```

```pdsl
UNIT CodingIntentCapture
PURPOSE: Capture the coding target before any context discovery or design gate runs.
DO:
  EMIT "Describe the code work you want done: the behavior, bug, refactor, review target, or files if known. I need that target before cf-explore or brainstorm can search usefully."
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS on the resumed reply set ORIGINAL_INTENT = user.reply and CONTINUE CodingExploreGate
  NEVER offer cf-explore, cf-brainstorm, or dispatch coder/reviewer agents while ORIGINAL_INTENT == unset
```

```pdsl
UNIT CodingExploreGate
PURPOSE: Offer task-relevant context discovery before any code is authored or reviewed, after Bootstrap and before the first edit.
STATE:
  SET RESOURCE_CONTEXT: unset | provided (default unset, scope workflow_run)
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  EMIT_MENU CodingExploreMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer cf-explore context discovery before authoring or reviewing code, and ALWAYS let the user skip it
  ALWAYS default to skip when the coding target and its surrounding context are already fully specified
  ALWAYS carry any returned resource_context into every coder and reviewer dispatch payload as read-only context, NEVER as a gate on a verdict
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
  EMIT_MENU CodingBrainstormMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer cf-brainstorm decision exploration after the explore gate and before authoring or reviewing code, and ALWAYS let the user skip it
  ALWAYS default to skip when the coding approach and its decisions are already clear and unambiguous
  ALWAYS carry any brainstorm decisions into every coder and reviewer dispatch payload as read-only context, NEVER as a gate on a verdict
MENU CodingBrainstormMenu
TITLE: Before writing or reviewing code, brainstorm ambiguous decisions or design options with cf-brainstorm — or skip? Skip is the default when the approach is already clear; brainstorm for ambiguous requirements or open design questions. Reply with a number.
OPTIONS:
  1 brainstorm -> INVOKE skill `cf-brainstorm`, then CONTINUE CodingDispatch
  2 skip -> CONTINUE CodingDispatch
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
  RUN the project's deterministic gate — resolve the test, lint, typecheck, and build commands from the project's config (package.json / Makefile / pyproject.toml / build files) or the remembered {cfs_cmd}/project commands, run them in order, and dispatch cf-deterministic-validator for studio-applicable checks (validate / validate-toc / check-language)
  EMIT the gate results
  SET GATE_STATUS = fail and CONTINUE CodingReviewLoop to fix them before proceeding WHEN any gate reports failures or errors
  SET GATE_STATUS = pass and CONTINUE CodingReviewLoop WHEN the deterministic gate passes
RULES:
  ALWAYS run tests, lint, typecheck, and build after writing or editing code
  NEVER treat code as done while any deterministic gate (tests/lint/typecheck/build) reports failures or errors; loop fixes until all pass
  ALWAYS prefer the project's configured commands and skip a gate only when the project genuinely lacks it (state which)
```

```pdsl
UNIT CodingReviewLoop
PURPOSE: Run a semantic review at the user-chosen granularity and iterate fixes until the code is clean.
STATE:
  SET REVIEW_GRANULARITY: single-pass | per-methodology | per-layer (default unset, scope workflow_run)
WHEN:
  REQUIRE edits have been applied to the code OR the user requested review of existing code without edits
DO:
  EMIT_MENU ReviewGranularityMenu WHEN REVIEW_GRANULARITY == unset
  RUN the chosen review at REVIEW_GRANULARITY, dispatching cf-semantic-reviewer-code (code-checklist), cf-code-bug-finder (bug-finding), and cf-semantic-reviewer-consistency (consistency-checklist — cross-checks the change against surrounding docs/specs/comments, not the code logic) instances in parallel
  RUN aggregation of every reviewer's findings into one deduplicated review report
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md and RUN ReviewFixApprovalGate WHEN findings remain and fixes are applicable
  RUN selected coding author/fix agent to apply the ReviewFixApprovalGate-approved review fixes WHEN review fixes were approved; CONTINUE CodingValidate WHEN review fixes were approved and applied this iteration (re-run the deterministic gate before re-reviewing)
  STOP_TURN and report the remaining findings WHEN findings remain but no fixes were applied this iteration (none approved, none applicable, or the ReviewFixApprovalGate resolved to none) — re-reviewing unchanged code cannot change the result
  STOP_TURN WHEN no review findings remain AND (the user requested review of existing code without edits OR GATE_STATUS == pass)
  STOP_TURN WHEN no review findings remain
RULES:
  ALWAYS offer the granularity choice with a suggested level by change size: tiny edit (≤10 changed lines) -> single-pass, moderate edit (11–50 changed lines) -> per-methodology, new module or large/structural change (>50 changed lines) -> per-layer
  ALWAYS read each methodology's current category/layer map (code-checklist categories, bug-finding layers, consistency-checklist categories) before a per-layer or per-methodology dispatch, so added layers are covered automatically and never a fixed count
  ALWAYS scope each reviewer to only its assigned slice (all methodologies / one methodology / one category-or-layer) and run independent reviewers in parallel
  ALWAYS aggregate and deduplicate all findings into one report before iterating fixes
  ALWAYS iterate the review-fix loop until no findings remain
  NEVER declare authored or edited code done until BOTH the deterministic gate (tests/lint/typecheck/build) passes AND the semantic review has no remaining findings; ALWAYS re-run CodingValidate after any fix before re-reviewing
  NEVER re-loop the review when no fixes were applied this iteration — STOP_TURN reporting the remaining findings so the loop cannot spin on unchanged code; only an applied fix re-runs CodingValidate and re-reviews
MENU ReviewGranularityMenu
TITLE: Choose review depth — the suggested level fits the change size.
OPTIONS:
  1 single-pass -> SET REVIEW_GRANULARITY = single-pass; the code-checklist, bug-finding, and consistency-checklist methodologies are reviewed in one combined pass (fastest; may miss cross-methodology interactions; suggested for tiny edits)
  2 per-methodology -> SET REVIEW_GRANULARITY = per-methodology; one cf-semantic-reviewer-code over all code-checklist categories, one cf-code-bug-finder over all bug-finding layers, and one cf-semantic-reviewer-consistency over all consistency-checklist categories (balanced; methodology-specific coverage; suggested for moderate edits)
  3 per-layer -> SET REVIEW_GRANULARITY = per-layer; one reviewer per category/layer of each methodology, run in parallel (most thorough but slowest; catches subtle per-layer issues; suggested for new modules or structural changes)
  INVALID -> EMIT_MENU ReviewGranularityMenu
NOTES:
  ConditionalModuleLoading loads {cf-studio-path}/.core/skills/studio/modules/review/finding-contract.md before findings are emitted and {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md before fixes are applied. Aggregation merges every reviewer's findings into one report, dedupes by (LOCATION, category, ROOT_CAUSE), keeps the highest SEVERITY and CONFIDENCE when collapsing duplicates, preserves each ReviewFindingContract field, and gates fixes through ReviewFixApprovalGate (CRIT+MAJOR / all / partial / none).
```

```pdsl
UNIT CodingDispatch
PURPOSE: Dispatch the sub-agents that write, fix, review, and gate source code.
DO:
  CONTINUE CodingReviewLoop WHEN the user requested review of existing code without edits
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md WHEN requested code writes or fixes; RUN GitCommitModeGate before preparing git policy for coder dispatch WHEN requested code writes or fixes
  RUN selected coding author/fix agent for requested code writes or fixes WHEN requested code writes or fixes
  CONTINUE CodingValidate WHEN code has been written or edited
RULES:
  ALWAYS select the coding author/fix agent under {cf-studio-path}/.core/skills/studio/agents/ by this priority order (first match wins): (1) cf-codegen.md when the task is fully specified and can be implemented in an isolated context with no clarification; else (2) cf-generate-coder-smart.md when the change involves behavior changes, tests, refactors, API boundaries, or any security/concurrency/data-model implication; else (3) cf-generate-coder-casual.md when it is a small code-only task touching at most two source/test files with no security/concurrency/data-model risk; else cf-generate-coder-smart.md as the default
  ALWAYS run GitCommitModeGate before any write-capable coder dispatch, even when the task itself did not ask to commit; ALWAYS after any coder/fix dispatch changes code, run the deterministic gate and then offer ReviewGranularityMenu before semantic review; NEVER stop after code generation or deterministic validation before the semantic review-fix loop is offered
  ALWAYS resolve git_commit_mode (probe once per session), contributing_guide (discover; null when none found), and the mode-matched git_constraint before any write-capable coder dispatch, and ALWAYS include all three in that dispatch payload
  ALWAYS include the CodingExploreGate-resolved resource_context (when RESOURCE_CONTEXT == provided) in every coder and reviewer dispatch payload as read-only context (an absolute path or reference, never inline prompt text), NEVER as a gate on a coder or reviewer verdict
  ALWAYS dispatch cf-semantic-reviewer-code (code-checklist), cf-code-bug-finder (bug-finding), and cf-semantic-reviewer-consistency (consistency-checklist) from {cf-studio-path}/.core/skills/studio/agents/ per the chosen REVIEW_GRANULARITY: single-pass = one reviewer covering all three methodologies in a single pass; per-methodology = one cf-semantic-reviewer-code over all code-checklist categories, one cf-code-bug-finder over all bug-finding layers, and one cf-semantic-reviewer-consistency over all consistency-checklist categories; per-layer = one reviewer per category/layer for every category/layer each methodology defines, run in parallel, never a fixed count — read each methodology's current category/layer map before dispatch
  ALWAYS run the deterministic gate via cf-deterministic-validator from {cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md plus the project's test/lint/typecheck/build commands
  ALWAYS synthesize into each reviewer instance only its assigned methodology/category/layer slice, never more than its scope
  NEVER let a sub-agent reopen prompt or instruction files from disk
```
