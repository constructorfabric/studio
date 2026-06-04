---
cf: true
type: workflow
name: cf-write-docs
description: "Invoke when user intent is writing, revising, or reviewing documentation, guides, reports, READMEs, or other project documents."
version: 0.1
---

# cf-write-docs

This skill authors and reviews project documents using the consistency-checklist and language-complexity methodologies, runs a deterministic gate (artifact validation, TOC, language checks), and runs a semantic review-fix loop at a selectable depth — single-pass, per-methodology, or per-layer — driven by author and reviewer sub-agents.

```pdsl
UNIT WriteDocsBootstrap
PURPOSE: Ensure the cf skill is loaded, then load the methodologies needed to author and review project documents.
STATE:
  SET CFS_INIT: true | false (default false, scope session)
DO:
  EMIT_MENU LoadCfSkillConfirm WHEN CFS_INIT != true
  LOAD {cf-studio-path}/.core/requirements/consistency-checklist.md
  LOAD {cf-studio-path}/.core/requirements/language-complexity.md
  RUN verify both references loaded; EMIT "Required reference not found (consistency-checklist or language-complexity methodology under {cf-studio-path}/.core) — cannot author or review docs; reinstall or sync the studio kit, then retry." and STOP_TURN WHEN either load fails
RULES:
  ALWAYS verify the cf skill is loaded, CFS_INIT == true, before authoring or reviewing docs
  ALWAYS load the consistency-checklist and language-complexity methodologies before authoring or reviewing docs
  ALWAYS apply the resolved language-complexity level to every chat message and document write, rewriting before emitting when a draft breaches it (source quotes verbatim/exempt)
  NEVER author or review docs when a required reference failed to load
MENU LoadCfSkillConfirm
TITLE: The cf skill is not loaded. It is the Constructor Studio core that loads the shared rules and routes to cf-* skills, so writing docs cannot run without it. Load it now to continue?
OPTIONS:
  1 load -> INVOKE skill `cf` and CONTINUE WriteDocsBootstrap
  2 stop -> STOP_TURN
  INVALID -> EMIT_MENU LoadCfSkillConfirm
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
PURPOSE: After edits, run a semantic review at the user-chosen granularity and iterate fixes until the document is clean.
STATE:
  SET REVIEW_GRANULARITY: single-pass | per-methodology | per-layer (default unset, scope workflow_run)
WHEN:
  REQUIRE edits have been applied to the document
DO:
  EMIT_MENU ReviewGranularityMenu WHEN REVIEW_GRANULARITY == unset
  RUN the chosen review at REVIEW_GRANULARITY, dispatching cf-semantic-reviewer-consistency and cf-semantic-reviewer-artifact instances in parallel (and cf-semantic-reviewer-freeform only when the user supplied a custom review prompt)
  RUN aggregation of every reviewer's findings into one deduplicated review report
  CONTINUE WriteDocsValidate WHEN review fixes were applied this iteration (re-run the deterministic gate before re-reviewing)
  STOP_TURN and report the remaining findings WHEN findings remain but no fixes were applied this iteration (none approved, none applicable, or the ReviewFixApprovalGate resolved to none) — re-reviewing unchanged content cannot change the result
  STOP_TURN WHEN no review findings remain AND GATE_STATUS == pass
RULES:
  ALWAYS offer the granularity choice with a suggested level by change size: tiny edit (≤10 changed lines) -> single-pass, moderate edit (11–50 changed lines) -> per-methodology, new document or large/structural change (>50 changed lines) -> per-layer
  ALWAYS read each methodology's current category/section map (consistency-checklist categories, the kit/artifact checklist categories) before a per-layer or per-methodology dispatch, so added sections are covered automatically and never a fixed count
  ALWAYS scope each reviewer to only its assigned slice and run independent reviewers in parallel
  ALWAYS aggregate and deduplicate all findings into one report before iterating fixes
  NEVER declare a document done until BOTH the deterministic gate passes AND the semantic review has no remaining findings; ALWAYS re-run WriteDocsValidate after any fix before re-reviewing
  NEVER re-loop the review when no fixes were applied this iteration — STOP_TURN reporting the remaining findings so the loop cannot spin on unchanged content; only an applied fix re-runs WriteDocsValidate and re-reviews
MENU ReviewGranularityMenu
TITLE: Choose review depth — the suggested level fits the change size.
OPTIONS:
  1 single-pass -> SET REVIEW_GRANULARITY = single-pass; the consistency-checklist and artifact-checklist methodologies are reviewed in one combined pass (fastest; may miss cross-methodology interactions; suggested for tiny edits)
  2 per-methodology -> SET REVIEW_GRANULARITY = per-methodology; one cf-semantic-reviewer-consistency over all consistency-checklist categories and one cf-semantic-reviewer-artifact over all artifact-checklist categories (balanced; suggested for moderate edits)
  3 per-layer -> SET REVIEW_GRANULARITY = per-layer; one reviewer per category of each methodology, run in parallel (most thorough but slowest; suggested for new documents or structural changes)
  INVALID -> EMIT_MENU ReviewGranularityMenu
NOTES:
  Aggregation merges every reviewer's findings into one report, dedupes by (LOCATION, category, ROOT_CAUSE), keeps the highest SEVERITY and CONFIDENCE when collapsing duplicates, and preserves each finding's full ReviewFindingContract fields. The session-wide ReviewFixApprovalGate gates whether fixes are applied (CRIT+MAJOR / all / partial / none). cf-semantic-reviewer-freeform is added only when the user supplies a custom review prompt.
```

```pdsl
UNIT WriteDocsDispatch
PURPOSE: Dispatch the sub-agents that write, fix, review, and gate project documents.
RULES:
  ALWAYS author and apply review fixes via cf-generate-author from {cf-studio-path}/.core/skills/studio/agents/cf-generate-author.md — the read-only selector that classifies task domain and complexity and routes generic artifact/prose work to the cheapest capable tier (cf-generate-author-junior for simple one-file low-risk prose, cf-generate-author-middle for standard artifacts with moderate cross-references, cf-generate-author-senior for complex multi-file or strict-rule docs, cf-generate-author-lead for high-risk or broad cross-system documentation)
  ALWAYS resolve git_commit_mode (probe once per session), contributing_guide (discover; null when none found), and the mode-matched git_constraint before any write-capable author dispatch, and ALWAYS include all three in that dispatch payload
  ALWAYS dispatch cf-semantic-reviewer-consistency from {cf-studio-path}/.core/skills/studio/agents/cf-semantic-reviewer-consistency.md (consistency-checklist) and cf-semantic-reviewer-artifact from {cf-studio-path}/.core/skills/studio/agents/cf-semantic-reviewer-artifact.md (kit/artifact checklist) per the chosen REVIEW_GRANULARITY: single-pass = one reviewer covering both methodologies; per-methodology = one reviewer per methodology; per-layer = one reviewer per category for every category each methodology defines, run in parallel, never a fixed count
  ALWAYS dispatch cf-semantic-reviewer-freeform from {cf-studio-path}/.core/skills/studio/agents/cf-semantic-reviewer-freeform.md only when the user supplies a custom review prompt/question
  ALWAYS run the deterministic gate via cf-deterministic-validator from {cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md
  ALWAYS synthesize into each reviewer instance only its assigned methodology/category slice, never more than its scope
  NEVER let a sub-agent reopen prompt or instruction files from disk
```
