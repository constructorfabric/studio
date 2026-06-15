---
cf: true
type: workflow
name: cf-write-docs
description: "Invoke when user intent is writing, revising, or reviewing documentation, guides, reports, READMEs, or other project documents."
version: 0.1
---

# cf-write-docs

This skill authors and reviews project documents using the consistency-checklist and artifact-checklist semantic review methodologies. After bootstrap it optionally discovers task-relevant project context via cf-explore, applies language-complexity as bootstrap/output policy and as a deterministic gate (artifact validation, TOC, language checks), and runs a semantic review-fix loop at a selectable depth — single-pass, per-methodology, or per-layer — driven by author and reviewer sub-agents.

```pdsl
UNIT WriteDocsBootstrap
PURPOSE: Load the methodologies needed to author and review project documents.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default unset, scope workflow_run)
  SET DOC_AUDIENCE_DIMENSION: resolved | unset (default unset, scope workflow_run)
  SET DOC_NARRATOR_DIMENSION: resolved | unset (default unset, scope workflow_run)
  SET DOC_DIAGRAM_DIMENSION: resolved | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/skill-invocation-art.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/pdsl-execution-card.md
  RUN SkillInvocationArt
  LOAD and REMEMBER rules from {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/studio-instructions-memory.md
  RUN StudioInstructionsMemoryGate
  SET ORIGINAL_INTENT = the user's triggering write-docs request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md
  LOAD {cf-studio-path}/.core/requirements/consistency-checklist.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/language-complexity.md
  RUN LanguageComplexityLoad
  LOAD {cf-studio-path}/.core/requirements/storytelling-dimensions.md
  RUN AudienceResolution, NarratorResolution, and DiagramResolution for the cf-write-docs flow class; SET DOC_AUDIENCE_DIMENSION = resolved, SET DOC_NARRATOR_DIMENSION = resolved, and SET DOC_DIAGRAM_DIMENSION = resolved before any author or reviewer dispatch
  RUN verify the references loaded; EMIT "Required reference not found (consistency-checklist, language-complexity, or storytelling-dimensions reference under {cf-studio-path}/.core) — cannot author or review docs; reinstall or sync the studio kit, then retry." and STOP_TURN WHEN any load fails
  CONTINUE WriteDocsIntentCapture WHEN ORIGINAL_INTENT == unset
  RUN classify ORIGINAL_INTENT by requested operation plus whether it evaluates an existing document, guide, report, README, or documentation artifact; SET REVIEW_LOOP_REQUESTED = true WHEN ORIGINAL_INTENT asks to review, audit, critique, inspect, check, validate, verify, analyze, compare behavior, or find issues/findings, bugs, risks, failures, regressions, bypasses, defects, root causes, routing problems, or behavioral-analysis concerns in an existing target, including review-and-fix wording
  RUN default REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset AND ORIGINAL_INTENT primarily evaluates an existing document, guide, report, README, or documentation artifact rather than creating one
  RUN classify ORIGINAL_INTENT; SET REVIEW_LOOP_REQUESTED = false WHEN REVIEW_LOOP_REQUESTED == unset
  SET PLAN_FIRST_CONTINUE = WriteDocsDispatch, SET CURRENT_WORKFLOW = cf-write-docs, SET COMPANION_CONTINUE = WriteDocsExploreGate, LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE CompanionSkillOffer WHEN ORIGINAL_INTENT != unset
RULES:
  ALWAYS run StudioInstructionsMemoryGate before document context discovery, authoring, validation, or review
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, authoring, git use, or delegation
  ALWAYS load the consistency-checklist methodology, the language-complexity bootstrap/output policy and deterministic gate, and the storytelling-dimensions reference before authoring or reviewing docs
  ALWAYS load context-memory before carrying resource_context or rule references into author/reviewer dispatches
  ALWAYS capture ORIGINAL_INTENT before offering cf-explore, cf-brainstorm, or any write/review dispatch
  ALWAYS derive REVIEW_LOOP_REQUESTED from ORIGINAL_INTENT before offering cf-explore, cf-brainstorm, planning, author dispatch, reviewer dispatch, or validation
  ALWAYS default to review-first routing when the request evaluates an existing document, guide, report, README, or documentation artifact rather than creating one
  ALWAYS route review/audit/critique/inspect/check/validate/verify/analyze/behavior-comparison/find-issues/bug-risk-failure-regression-bypass-defect-root-cause-routing-analysis intents through WriteDocsReviewLoop first; any fixes must be gated by ReviewFindingsReportBrowser and ReviewFixApprovalGate, not by direct author dispatch
  ALWAYS apply the resolved language-complexity level to every chat message and document write, rewriting breaching drafts before emitting them (source quotes verbatim/exempt)
  ALWAYS resolve and apply the audience dimension per {cf-studio-path}/.core/requirements/storytelling-dimensions.md at Bootstrap — the review flow class scopes emphasis, the authoring flow class sets the document level — never as a gate on the verdict
  ALWAYS resolve and apply the narrator dimension per {cf-studio-path}/.core/requirements/storytelling-dimensions.md at Bootstrap — map it onto the selected reviewer/author sub-agents and the document voice — never overriding the verdict
  ALWAYS resolve and apply the diagram dimension per {cf-studio-path}/.core/requirements/storytelling-dimensions.md at Bootstrap — the review flow class flags a missing or unclear diagram, the authoring flow class embeds a warranted one — never auto-generating outside the authored document
  NEVER author or review docs after a required reference load failure
```

```pdsl
UNIT WriteDocsIntentCapture
PURPOSE: Capture the documentation target before any context discovery or framing gate runs.
DO:
  EMIT "Describe the documentation work you want done: the document, audience, goal, and any source material you already know. I need that target before cf-explore or brainstorm can search usefully."
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS on the resumed reply set ORIGINAL_INTENT = user.reply, derive REVIEW_LOOP_REQUESTED from ORIGINAL_INTENT using the Bootstrap review-intent classification, SET PLAN_FIRST_CONTINUE = WriteDocsDispatch, SET CURRENT_WORKFLOW = cf-write-docs, SET COMPANION_CONTINUE = WriteDocsExploreGate, LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE CompanionSkillOffer
  NEVER offer cf-explore, cf-brainstorm, or dispatch author/reviewer agents while ORIGINAL_INTENT == unset
```

```pdsl
UNIT WriteDocsExploreGate
PURPOSE: Offer task-relevant context discovery before any document is authored or reviewed, after Bootstrap and before the first edit.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  SET WORKFLOW_PREP_EXPLORE_MENU = WriteDocsExploreMenu
  SET WORKFLOW_PREP_BRAINSTORM_GATE = WriteDocsBrainstormGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/workflow-prep.md
  CONTINUE WorkflowPrepExploreGate
RULES:
  ALWAYS use WorkflowPrepExploreGate for the shared explore prompt mechanics
MENU WriteDocsExploreMenu
TITLE: Before writing or reviewing docs, discover task-relevant project context (existing docs, related guides, source material, conventions) with cf-explore — or skip? Skip is the default when the target and its context are already clear; explore for unfamiliar or cross-cutting documentation. Reply with a number.
OPTIONS:
  1 explore -> INVOKE skill `cf-explore` with intent=workflow-prep, task=ORIGINAL_INTENT, return_context=true; require it to return resource_context only and not perform review/authoring, SET RESOURCE_CONTEXT = provided, then CONTINUE WriteDocsBrainstormGate
  2 skip -> CONTINUE WriteDocsBrainstormGate
  INVALID -> EMIT_MENU WriteDocsExploreMenu
```

```pdsl
UNIT WriteDocsBrainstormGate
PURPOSE: Offer decision/design exploration via cf-brainstorm as the next step after the explore gate, before any document is authored or reviewed.
DO:
  SET WORKFLOW_PREP_BRAINSTORM_MENU = WriteDocsBrainstormMenu
  SET WORKFLOW_PREP_DISPATCH_UNIT = PlanFirstGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/workflow-prep.md
  CONTINUE WorkflowPrepBrainstormGate
RULES:
  ALWAYS use WorkflowPrepBrainstormGate for the shared brainstorm prompt mechanics
MENU WriteDocsBrainstormMenu
TITLE: Before writing or reviewing docs, brainstorm ambiguous decisions or framing options with cf-brainstorm — or skip? Skip is the default when the approach is already clear; brainstorm for ambiguous requirements or open framing questions. Reply with a number.
OPTIONS:
  1 brainstorm -> INVOKE skill `cf-brainstorm`; require it to return brainstorm_decisions, SET BRAINSTORM_DECISIONS = provided, then SET PLAN_FIRST_CONTINUE = WriteDocsDispatch, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE PlanFirstGate
  2 skip -> SET PLAN_FIRST_CONTINUE = WriteDocsDispatch, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE PlanFirstGate
  INVALID -> EMIT_MENU WriteDocsBrainstormMenu
```

```pdsl
UNIT WriteDocsValidate
PURPOSE: Run the deterministic gate over authored or edited documents.
STATE:
  SET GATE_STATUS: pass | fail (default unset, scope workflow_run)
WHEN:
  REQUIRE a document has been written or edited
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  RUN SubAgentDispatch for the cf-deterministic-validator dispatch group before launching deterministic validation
  RUN the deterministic gate — dispatch cf-deterministic-validator for the applicable checks (validate --artifact / validate-toc / check-language) plus any project doc checks
  EMIT the gate results
  SET GATE_STATUS = fail and CONTINUE WriteDocsReviewLoop to fix them before proceeding WHEN any check reports failures or errors
  SET GATE_STATUS = pass and CONTINUE WriteDocsReviewLoop WHEN the deterministic gate passes
RULES:
  ALWAYS run the applicable deterministic checks after writing or editing a document
  NEVER treat a document as done while any deterministic check reports failures or errors; loop fixes until all pass
  ALWAYS prefer the project's configured checks and skip only checks that the target genuinely lacks (state which)
```

```pdsl
UNIT WriteDocsReviewLoop
PURPOSE: Run a semantic review at the user-chosen granularity and iterate fixes until the document is clean.
STATE:
  SET REVIEW_GRANULARITY: single-pass | per-methodology | per-layer (default unset, scope workflow_run)
  SET SELECTED_REVIEW_FIX_AGENT: cf-generate-author-junior | cf-generate-author-middle | cf-generate-author-senior | cf-generate-author-lead | unset (default unset, scope workflow_run)
  SET REVIEW_FIXES_APPLIED: true | false | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE edits have been applied to the document OR REVIEW_LOOP_REQUESTED == true
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/finding-contract.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/semantic-loop-skeleton.md
  RUN SemanticReviewNoSpinRules
  SET REVIEW_GRANULARITY_SCOPE = "Docs review scope: single-pass covers consistency-checklist and artifact-checklist together; per-methodology dispatches cf-semantic-reviewer-consistency and cf-semantic-reviewer-artifact separately, plus cf-semantic-reviewer-freeform only for a custom review prompt; per-layer dispatches one reviewer per current category."
  RUN SemanticReviewGranularityGate WHEN REVIEW_GRANULARITY == unset
  RUN SubAgentDispatch for the selected document reviewer dispatch group before launching reviewer instances
  RUN scoping of this review dispatch by the Bootstrap-resolved storytelling dimensions per {cf-studio-path}/.core/requirements/storytelling-dimensions.md review flow-class rules — scope each reviewer's emphasis by the resolved audience, map the resolved narrator onto the selected reviewer set, and instruct each reviewer to flag a warranted-but-missing or unclear diagram as a finding
  RUN the chosen review at REVIEW_GRANULARITY: single-pass = dispatch cf-semantic-reviewer-consistency and cf-semantic-reviewer-artifact in one combined dispatch group, plus cf-semantic-reviewer-freeform only when the user supplied a custom review prompt, then aggregate one report; per-methodology = dispatch cf-semantic-reviewer-consistency and cf-semantic-reviewer-artifact in parallel (plus freeform only when the user supplied a custom review prompt); per-layer = dispatch one reviewer per current category for each applicable methodology
  RUN aggregation of every reviewer's findings into one deduplicated ReviewFindingsReport with stable finding IDs and every ReviewFindingContract field
  RUN SemanticReviewFixApprovalGate WHEN findings remain and fixes are applicable
  RUN select SELECTED_REVIEW_FIX_AGENT from the approved findings and target document paths using the cf-generate-author selection rules; choose only a concrete write-capable cf-generate-author-* worker tier WHEN REVIEW_FIX_APPROVED == true
  RUN SubAgentDispatch for the SELECTED_REVIEW_FIX_AGENT review-fix dispatch group WHEN REVIEW_FIX_APPROVED == true
  DISPATCH SELECTED_REVIEW_FIX_AGENT with mode=fix, target_paths, APPROVED_REVIEW_FINDING_IDS, REVIEW_FIX_SCOPE, git_commit_mode, contributing_guide, git_constraint, commit_footer_contract, resource_context, and the resolved audience/narrator/diagram policy data to apply only approved review fixes WHEN REVIEW_FIX_APPROVED == true
  RUN verify the returned fix manifest accounts for every APPROVED_REVIEW_FINDING_IDS entry as applied or not-fixable; SET REVIEW_FIXES_APPLIED = true WHEN one or more approved fixes changed content; SET REVIEW_FIXES_APPLIED = false WHEN no content changed
  CONTINUE WriteDocsValidate WHEN REVIEW_FIXES_APPLIED == true (re-run the deterministic gate before re-reviewing)
  STOP_TURN and report the remaining findings WHEN findings remain but no fixes were applied this iteration (none approved, none applicable, or the ReviewFixApprovalGate resolved to none) — re-reviewing unchanged content cannot change the result
  STOP_TURN and report that deterministic blockers remain WHEN no review findings remain AND GATE_STATUS == fail
  CONTINUE WriteDocsCompletion WHEN no review findings remain AND (REVIEW_LOOP_REQUESTED == true OR GATE_STATUS == pass)
RULES:
  ALWAYS read each methodology's current category/section map (consistency-checklist categories, the kit/artifact checklist categories) before a per-layer or per-methodology dispatch, so added sections are covered automatically and never a fixed count
  ALWAYS scope each reviewer to only its assigned slice and run independent reviewers in parallel
  ALWAYS keep workflow-specific reviewer dispatches in this workflow
  ALWAYS render the interactive ReviewFindingsReportBrowser from fix-approval before any fix-scope menu, so the user can inspect findings one by one, move next/previous, mark findings for fix, switch to a full table, and then choose a clear fix scope
  ALWAYS select a concrete write-capable cf-generate-author-* worker inside WriteDocsReviewLoop after REVIEW_FIX_APPROVED == true; NEVER dispatch the read-only cf-generate-author selector itself to write or fix documents
  ALWAYS pass APPROVED_REVIEW_FINDING_IDS and REVIEW_FIX_SCOPE to the selected fixer so partial and severity-scoped approvals cannot widen silently
  NEVER declare an authored or edited document done until BOTH the deterministic gate passes AND the semantic review has no remaining findings; ALWAYS re-run WriteDocsValidate after any fix before re-reviewing
  NEVER re-loop the review after an iteration with no applied fixes — STOP_TURN reporting the remaining findings so the loop cannot spin on unchanged content; only an applied fix re-runs WriteDocsValidate and re-reviews
  ALWAYS apply the resolved audience and narrator only to scope reviewer emphasis and map the narrator onto the selected reviewer set per storytelling-dimensions review flow-class rules, NEVER to change a finding's severity or the review verdict and NEVER as a separate storytelling reviewer
  ALWAYS have reviewers flag a warranted-but-missing or unclear diagram as a finding, and NEVER auto-generate a diagram in the review loop
```

```pdsl
UNIT WriteDocsCompletion
PURPOSE: Emit a concise completion report, then offer context-grounded next actions after document authoring/review completes cleanly.
WHEN:
  REQUIRE no review findings remain
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT a concise completion report covering work done, gate outcome, and semantic review outcome
  RUN NextActionsOffer
RULES:
  ALWAYS use this unit only after document validation/review is complete and control is about to return to the user
  ALWAYS report the deterministic gate outcome, including review-only flows with no deterministic gate run
  ALWAYS state that semantic review completed with no remaining findings before offering next actions
  NEVER bypass NextActionsOffer on a clean terminal path that returns control to the user
```

```pdsl
UNIT WriteDocsDispatch
PURPOSE: Dispatch the sub-agents that write, fix, review, and gate project documents.
DO:
  CONTINUE WriteDocsReviewLoop WHEN REVIEW_LOOP_REQUESTED == true
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md WHEN requested document writes or fixes OR reviewer dispatch is needed OR deterministic validation is needed
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md WHEN requested document writes or fixes
  RUN GitCommitModeGate before preparing git policy for author dispatch WHEN requested document writes or fixes
  RUN select a concrete write-capable cf-generate-author-* worker using the cf-generate-author selection rules WHEN requested document writes or fixes
  RUN SubAgentDispatch for the selected concrete cf-generate-author-* worker dispatch group WHEN requested document writes or fixes
  DISPATCH the selected concrete cf-generate-author-* worker for requested document writes or fixes WHEN requested document writes or fixes
  CONTINUE WriteDocsValidate WHEN a document has been written or edited
RULES:
  ALWAYS use cf-generate-author from {cf-studio-path}/.core/skills/studio/agents/cf-generate-author.md only as controller-side selection rules, then author and apply review fixes via the selected concrete write-capable worker tier (cf-generate-author-junior for simple one-file low-risk prose, cf-generate-author-middle for standard artifacts with moderate cross-references, cf-generate-author-senior for complex multi-file or strict-rule docs, cf-generate-author-lead for high-risk or broad cross-system documentation)
  NEVER dispatch cf-generate-author itself to write or fix documents because it is a read-only selector, not a write-capable worker
  ALWAYS run GitCommitModeGate before any write-capable author dispatch, even for tasks that did not ask to commit
  ALWAYS run SubAgentDispatch before every native author, validator, reviewer, or review-fix dispatch group; inline fallback executes the same selected contract without native dispatch
  ALWAYS after any author/fix dispatch changes content, run the deterministic gate and then offer ReviewGranularityMenu before semantic review
  ALWAYS prefer REVIEW_LOOP_REQUESTED == true over author/fix routing, so review-and-fix requests produce findings first and only apply fixes after the review fix-approval gate
  NEVER stop after content generation or deterministic validation before the semantic review-fix loop is offered
  ALWAYS resolve git_commit_mode (probe once per session), contributing_guide (discover; use null for no discovered guide), and the mode-matched git_constraint before any write-capable author dispatch, and ALWAYS include all three in that dispatch payload
  ALWAYS include any WriteDocsExploreGate-resolved resource_context in every author and reviewer dispatch payload as read-only context (an absolute path or reference, never inline prompt text), NEVER as a gate on an author or reviewer verdict
  ALWAYS include the Bootstrap-resolved audience, narrator, and diagram dimensions in every reviewer and author dispatch payload as read-only policy data, scoped per {cf-studio-path}/.core/requirements/storytelling-dimensions.md review and authoring flow-class rules
  NEVER pass any storytelling dimension as a gate on a reviewer or author verdict
  ALWAYS dispatch cf-semantic-reviewer-consistency from {cf-studio-path}/.core/skills/studio/agents/cf-semantic-reviewer-consistency.md (consistency-checklist) and cf-semantic-reviewer-artifact from {cf-studio-path}/.core/skills/studio/agents/cf-semantic-reviewer-artifact.md (kit/artifact checklist) per the chosen REVIEW_GRANULARITY: single-pass = both methodology reviewers in one combined dispatch group with one aggregated report; per-methodology = one reviewer per methodology; per-layer = one reviewer per category for every category each methodology defines, run in parallel, never a fixed count
  ALWAYS dispatch cf-semantic-reviewer-freeform from {cf-studio-path}/.core/skills/studio/agents/cf-semantic-reviewer-freeform.md only for user-supplied custom review prompts/questions
  ALWAYS run the deterministic gate via cf-deterministic-validator from {cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md
  ALWAYS synthesize into each reviewer instance only its assigned methodology/category slice, never more than its scope
  NEVER let a sub-agent reopen prompt or instruction files from disk
```
