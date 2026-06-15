---
cf: true
type: workflow
name: cf-write-docs
description: "Invoke when user intent is writing, revising, or reviewing documentation, guides, reports, READMEs, or other project documents."
version: 0.1
---

# cf-write-docs

This skill authors and reviews project documents using the consistency-checklist and language-complexity methodologies. After bootstrap it optionally discovers task-relevant project context via cf-explore, runs a deterministic gate (artifact validation, TOC, language checks), and runs a semantic review-fix loop at a selectable depth — single-pass, per-methodology, or per-layer — driven by author and reviewer sub-agents.

```pdsl
UNIT WriteDocsBootstrap
PURPOSE: Ensure the cf skill is loaded, then load the methodologies needed to author and review project documents.
STATE:
  SET CFS_INIT: true | false (default false, scope session)
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
DO:
  SET ORIGINAL_INTENT = the user's triggering write-docs request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  EMIT_MENU LoadCfSkillConfirm WHEN CFS_INIT != true
  STOP_TURN WHEN CFS_INIT != true
  LOAD {cf-studio-path}/.core/requirements/consistency-checklist.md
  LOAD {cf-studio-path}/.core/requirements/language-complexity.md
  LOAD {cf-studio-path}/.core/requirements/storytelling-dimensions.md
  RUN verify the references loaded; EMIT "Required reference not found (consistency-checklist, language-complexity, or storytelling-dimensions reference under {cf-studio-path}/.core) — cannot author or review docs; reinstall or sync the studio kit, then retry." and STOP_TURN WHEN any load fails
  CONTINUE WriteDocsIntentCapture WHEN ORIGINAL_INTENT == unset
  CONTINUE WriteDocsExploreGate WHEN ORIGINAL_INTENT != unset
RULES:
  ALWAYS verify the cf skill is loaded, CFS_INIT == true, before authoring or reviewing docs
  ALWAYS treat CFS_INIT as false when its value is unknown, ambiguous, or unset
  NEVER proceed past WriteDocsBootstrap unless CFS_INIT == true is positively confirmed
  ALWAYS load the consistency-checklist and language-complexity methodologies and the storytelling-dimensions reference before authoring or reviewing docs
  ALWAYS capture ORIGINAL_INTENT before offering cf-explore, cf-brainstorm, or any write/review dispatch
  ALWAYS apply the resolved language-complexity level to every chat message and document write, rewriting before emitting when a draft breaches it (source quotes verbatim/exempt)
  ALWAYS resolve and apply the audience dimension per {cf-studio-path}/.core/requirements/storytelling-dimensions.md at Bootstrap — the review flow class scopes emphasis, the authoring flow class sets the document level — never as a gate on the verdict
  ALWAYS resolve and apply the narrator dimension per {cf-studio-path}/.core/requirements/storytelling-dimensions.md at Bootstrap — map it onto the selected reviewer/author sub-agents and the document voice — never overriding the verdict
  ALWAYS resolve and apply the diagram dimension per {cf-studio-path}/.core/requirements/storytelling-dimensions.md at Bootstrap — the review flow class flags a missing or unclear diagram, the authoring flow class embeds a warranted one — never auto-generating outside the authored document
  NEVER author or review docs when a required reference failed to load
MENU LoadCfSkillConfirm
TITLE: The cf skill is not loaded. It is the Constructor Studio core that loads the shared rules and routes to cf-* skills, so writing docs cannot run without it. Load it now to continue?
OPTIONS:
  1 load -> INVOKE skill `cf` and CONTINUE WriteDocsBootstrap
  2 stop -> STOP_TURN
  INVALID -> EMIT_MENU LoadCfSkillConfirm
```

```pdsl
UNIT WriteDocsIntentCapture
PURPOSE: Capture the documentation target before any context discovery or framing gate runs.
DO:
  EMIT "Describe the documentation work you want done: the document, audience, goal, and any source material you already know. I need that target before cf-explore or brainstorm can search usefully."
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS on the resumed reply set ORIGINAL_INTENT = user.reply and CONTINUE WriteDocsExploreGate
  NEVER offer cf-explore, cf-brainstorm, or dispatch author/reviewer agents while ORIGINAL_INTENT == unset
```

```pdsl
UNIT WriteDocsExploreGate
PURPOSE: Offer task-relevant context discovery before any document is authored or reviewed, after Bootstrap and before the first edit.
STATE:
  SET RESOURCE_CONTEXT: unset | provided (default unset, scope workflow_run)
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  EMIT_MENU WriteDocsExploreMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer cf-explore context discovery before authoring or reviewing docs, and ALWAYS let the user skip it
  ALWAYS default to skip when the document target and its surrounding context are already fully specified
  ALWAYS carry any returned resource_context into every author and reviewer dispatch payload as read-only context, NEVER as a gate on a verdict
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
  EMIT_MENU WriteDocsBrainstormMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer cf-brainstorm decision exploration after the explore gate and before authoring or reviewing docs, and ALWAYS let the user skip it
  ALWAYS default to skip when the document approach and its decisions are already clear and unambiguous
  ALWAYS carry any brainstorm decisions into every author and reviewer dispatch payload as read-only context, NEVER as a gate on a verdict
MENU WriteDocsBrainstormMenu
TITLE: Before writing or reviewing docs, brainstorm ambiguous decisions or framing options with cf-brainstorm — or skip? Skip is the default when the approach is already clear; brainstorm for ambiguous requirements or open framing questions. Reply with a number.
OPTIONS:
  1 brainstorm -> INVOKE skill `cf-brainstorm`, then CONTINUE WriteDocsDispatch
  2 skip -> CONTINUE WriteDocsDispatch
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
  RUN the deterministic gate — dispatch cf-deterministic-validator for the applicable checks (validate --artifact / validate-toc / check-language) plus any project doc checks
  EMIT the gate results
  SET GATE_STATUS = fail and CONTINUE WriteDocsReviewLoop to fix them before proceeding WHEN any check reports failures or errors
  SET GATE_STATUS = pass and CONTINUE WriteDocsReviewLoop WHEN the deterministic gate passes
RULES:
  ALWAYS run the applicable deterministic checks after writing or editing a document
  NEVER treat a document as done while any deterministic check reports failures or errors; loop fixes until all pass
  ALWAYS prefer the project's configured checks and skip one only when the target genuinely lacks it (state which)
```

```pdsl
UNIT WriteDocsReviewLoop
PURPOSE: Run a semantic review at the user-chosen granularity and iterate fixes until the document is clean.
STATE:
  SET REVIEW_GRANULARITY: single-pass | per-methodology | per-layer (default unset, scope workflow_run)
WHEN:
  REQUIRE edits have been applied to the document OR the user requested review of an existing document without edits
DO:
  EMIT_MENU ReviewGranularityMenu WHEN REVIEW_GRANULARITY == unset
  RUN the chosen review at REVIEW_GRANULARITY, dispatching cf-semantic-reviewer-consistency and cf-semantic-reviewer-artifact instances in parallel (and cf-semantic-reviewer-freeform only when the user supplied a custom review prompt)
  RUN scoping of this review dispatch by the Bootstrap-resolved storytelling dimensions per {cf-studio-path}/.core/requirements/storytelling-dimensions.md review flow-class rules — scope each reviewer's emphasis by the resolved audience, map the resolved narrator onto the selected reviewer set, and instruct each reviewer to flag a warranted-but-missing or unclear diagram as a finding
  RUN aggregation of every reviewer's findings into one deduplicated review report
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md and RUN ReviewFixApprovalGate WHEN findings remain and fixes are applicable
  RUN cf-generate-author to apply the ReviewFixApprovalGate-approved review fixes WHEN review fixes were approved
  CONTINUE WriteDocsValidate WHEN review fixes were approved and applied this iteration (re-run the deterministic gate before re-reviewing)
  STOP_TURN and report the remaining findings WHEN findings remain but no fixes were applied this iteration (none approved, none applicable, or the ReviewFixApprovalGate resolved to none) — re-reviewing unchanged content cannot change the result
  STOP_TURN WHEN no review findings remain AND the user requested review of an existing document without edits
  STOP_TURN WHEN no review findings remain AND GATE_STATUS == pass
  STOP_TURN WHEN no review findings remain
RULES:
  ALWAYS offer the granularity choice with a suggested level by change size: tiny edit (≤10 changed lines) -> single-pass, moderate edit (11–50 changed lines) -> per-methodology, new document or large/structural change (>50 changed lines) -> per-layer
  ALWAYS read each methodology's current category/section map (consistency-checklist categories, the kit/artifact checklist categories) before a per-layer or per-methodology dispatch, so added sections are covered automatically and never a fixed count
  ALWAYS scope each reviewer to only its assigned slice and run independent reviewers in parallel
  ALWAYS aggregate and deduplicate all findings into one report before iterating fixes
  NEVER declare an authored or edited document done until BOTH the deterministic gate passes AND the semantic review has no remaining findings; ALWAYS re-run WriteDocsValidate after any fix before re-reviewing
  NEVER re-loop the review when no fixes were applied this iteration — STOP_TURN reporting the remaining findings so the loop cannot spin on unchanged content; only an applied fix re-runs WriteDocsValidate and re-reviews
  ALWAYS apply the resolved audience and narrator only to scope reviewer emphasis and map the narrator onto the selected reviewer set per storytelling-dimensions review flow-class rules, NEVER to change a finding's severity or the review verdict and NEVER as a separate storytelling reviewer
  ALWAYS have reviewers flag a warranted-but-missing or unclear diagram as a finding, and NEVER auto-generate a diagram in the review loop
MENU ReviewGranularityMenu
TITLE: Choose review depth — the suggested level fits the change size.
OPTIONS:
  1 single-pass -> SET REVIEW_GRANULARITY = single-pass; the consistency-checklist and artifact-checklist methodologies are reviewed in one combined pass (fastest; may miss cross-methodology interactions; suggested for tiny edits)
  2 per-methodology -> SET REVIEW_GRANULARITY = per-methodology; one cf-semantic-reviewer-consistency over all consistency-checklist categories and one cf-semantic-reviewer-artifact over all artifact-checklist categories (balanced; suggested for moderate edits)
  3 per-layer -> SET REVIEW_GRANULARITY = per-layer; one reviewer per category of each methodology, run in parallel (most thorough but slowest; suggested for new documents or structural changes)
  INVALID -> EMIT_MENU ReviewGranularityMenu
NOTES:
  ConditionalModuleLoading loads {cf-studio-path}/.core/skills/studio/modules/review/finding-contract.md before findings are emitted and {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md before fixes are applied. Aggregation merges every reviewer's findings into one report, dedupes by (LOCATION, category, ROOT_CAUSE), keeps the highest SEVERITY and CONFIDENCE when collapsing duplicates, preserves each ReviewFindingContract field, and gates fixes through ReviewFixApprovalGate (CRIT+MAJOR / all / partial / none). cf-semantic-reviewer-freeform is added only when the user supplies a custom review prompt.
```

```pdsl
UNIT WriteDocsDispatch
PURPOSE: Dispatch the sub-agents that write, fix, review, and gate project documents.
DO:
  CONTINUE WriteDocsReviewLoop WHEN the user requested review of an existing document without edits
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md WHEN requested document writes or fixes
  RUN GitCommitModeGate before preparing git policy for author dispatch WHEN requested document writes or fixes
  RUN cf-generate-author for requested document writes or fixes WHEN requested document writes or fixes
  CONTINUE WriteDocsValidate WHEN a document has been written or edited
RULES:
  ALWAYS author and apply review fixes via cf-generate-author from {cf-studio-path}/.core/skills/studio/agents/cf-generate-author.md — the read-only selector that classifies task domain and complexity and routes generic artifact/prose work to the cheapest capable tier (cf-generate-author-junior for simple one-file low-risk prose, cf-generate-author-middle for standard artifacts with moderate cross-references, cf-generate-author-senior for complex multi-file or strict-rule docs, cf-generate-author-lead for high-risk or broad cross-system documentation)
  ALWAYS run GitCommitModeGate before any write-capable author dispatch, even when the task itself did not ask to commit
  ALWAYS after any author/fix dispatch changes content, run the deterministic gate and then offer ReviewGranularityMenu before semantic review
  NEVER stop after content generation or deterministic validation before the semantic review-fix loop is offered
  ALWAYS resolve git_commit_mode (probe once per session), contributing_guide (discover; null when none found), and the mode-matched git_constraint before any write-capable author dispatch, and ALWAYS include all three in that dispatch payload
  ALWAYS include the WriteDocsExploreGate-resolved resource_context (when RESOURCE_CONTEXT == provided) in every author and reviewer dispatch payload as read-only context (an absolute path or reference, never inline prompt text), NEVER as a gate on an author or reviewer verdict
  ALWAYS include the Bootstrap-resolved audience, narrator, and diagram dimensions in every reviewer and author dispatch payload as read-only policy data, scoped per {cf-studio-path}/.core/requirements/storytelling-dimensions.md review and authoring flow-class rules
  NEVER pass any storytelling dimension as a gate on a reviewer or author verdict
  ALWAYS dispatch cf-semantic-reviewer-consistency from {cf-studio-path}/.core/skills/studio/agents/cf-semantic-reviewer-consistency.md (consistency-checklist) and cf-semantic-reviewer-artifact from {cf-studio-path}/.core/skills/studio/agents/cf-semantic-reviewer-artifact.md (kit/artifact checklist) per the chosen REVIEW_GRANULARITY: single-pass = one reviewer covering both methodologies; per-methodology = one reviewer per methodology; per-layer = one reviewer per category for every category each methodology defines, run in parallel, never a fixed count
  ALWAYS dispatch cf-semantic-reviewer-freeform from {cf-studio-path}/.core/skills/studio/agents/cf-semantic-reviewer-freeform.md only when the user supplies a custom review prompt/question
  ALWAYS run the deterministic gate via cf-deterministic-validator from {cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md
  ALWAYS synthesize into each reviewer instance only its assigned methodology/category slice, never more than its scope
  NEVER let a sub-agent reopen prompt or instruction files from disk
```
