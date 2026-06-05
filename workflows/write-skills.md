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
PURPOSE: Ensure the cf skill is loaded, then load the references needed to author and review PDSL skills.
STATE:
  SET CFS_INIT: true | false (default false, scope session)
DO:
  EMIT_MENU LoadCfSkillConfirm WHEN CFS_INIT != true
  STOP_TURN WHEN CFS_INIT != true
  LOAD {cf-studio-path}/.core/architecture/specs/PDSL.md
  LOAD {cf-studio-path}/.core/requirements/prompt-engineering.md
  RUN verify both references loaded; EMIT "Required reference not found (PDSL spec or prompt-engineering methodology under {cf-studio-path}/.core) — cannot author or review; reinstall or sync the studio kit, then retry." and STOP_TURN WHEN either load fails
  CONTINUE WriteSkillsExploreGate WHEN CFS_INIT == true AND both references loaded
RULES:
  ALWAYS verify the cf skill is loaded, CFS_INIT == true, before authoring or reviewing a skill
  ALWAYS treat CFS_INIT as false when its value is unknown, ambiguous, or unset
  NEVER proceed past WriteSkillsBootstrap unless CFS_INIT == true is positively confirmed
  ALWAYS load the PDSL spec and the prompt-engineering requirement before authoring or reviewing a skill
  NEVER author or review a skill when a required reference failed to load
MENU LoadCfSkillConfirm
TITLE: The cf skill is not loaded. It is the Constructor Studio core that loads the shared rules and routes to cf-* skills, so authoring/reviewing skills cannot run without it. Load it now to continue?
OPTIONS:
  1 load -> INVOKE skill `cf` and CONTINUE WriteSkillsBootstrap
  2 stop -> STOP_TURN
  INVALID -> EMIT_MENU LoadCfSkillConfirm
```

```pdsl
UNIT WriteSkillsExploreGate
PURPOSE: Offer task-relevant context discovery before any skill file is authored or reviewed, after Bootstrap and before the first edit.
STATE:
  SET RESOURCE_CONTEXT: unset | provided (default unset, scope workflow_run)
DO:
  EMIT_MENU WriteSkillsExploreMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer cf-explore context discovery before authoring or reviewing a skill, and ALWAYS let the user skip it
  ALWAYS default to skip when the skill target and its surrounding context are already fully specified
  ALWAYS carry any returned resource_context into every author and reviewer dispatch payload as read-only context, NEVER as a gate on a verdict
MENU WriteSkillsExploreMenu
TITLE: Before writing or reviewing a skill, discover task-relevant project context (sibling skills, workflows, agent contracts, referenced requirements, PDSL conventions) with cf-explore — or skip? Skip is the default when the target and its context are already clear; explore for unfamiliar or cross-cutting prompt work. Reply with a number.
OPTIONS:
  1 explore -> INVOKE skill `cf-explore` with intent=generate and return_context=true, SET RESOURCE_CONTEXT = provided, then CONTINUE WriteSkillsBrainstormGate
  2 skip -> CONTINUE WriteSkillsBrainstormGate
  INVALID -> EMIT_MENU WriteSkillsExploreMenu
```

```pdsl
UNIT WriteSkillsBrainstormGate
PURPOSE: Offer decision/design exploration via cf-brainstorm as the next step after the explore gate, before any skill file is authored or reviewed.
DO:
  EMIT_MENU WriteSkillsBrainstormMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer cf-brainstorm decision exploration after the explore gate and before authoring or reviewing a skill, and ALWAYS let the user skip it
  ALWAYS default to skip when the skill approach and its decisions are already clear and unambiguous
  ALWAYS carry any brainstorm decisions into every author and reviewer dispatch payload as read-only context, NEVER as a gate on a verdict
MENU WriteSkillsBrainstormMenu
TITLE: Before writing or reviewing a skill, brainstorm ambiguous decisions or design options with cf-brainstorm — or skip? Skip is the default when the approach is already clear; brainstorm for ambiguous requirements or open design questions. Reply with a number.
OPTIONS:
  1 brainstorm -> INVOKE skill `cf-brainstorm`, then CONTINUE WriteSkillsDispatch
  2 skip -> CONTINUE WriteSkillsDispatch
  INVALID -> EMIT_MENU WriteSkillsBrainstormMenu
```

```pdsl
UNIT WriteSkillsValidate
PURPOSE: Validate authored PDSL with the deterministic validator.
WHEN:
  REQUIRE a skill file has been written or edited
DO:
  RUN `{cfs_cmd} pdsl validate` on the written skill file
  EMIT the validation findings and CONTINUE WriteSkillsReviewLoop to fix them before proceeding WHEN validation reports fail or error
RULES:
  ALWAYS run `{cfs_cmd} pdsl validate` after writing or editing a skill file
  NEVER treat a skill as done while `{cfs_cmd} pdsl validate` reports fail or error; loop fixes until it passes
```

```pdsl
UNIT WriteSkillsReviewLoop
PURPOSE: After edits, run a semantic review at the user-chosen granularity and iterate fixes until the skill is clean.
STATE:
  SET REVIEW_GRANULARITY: single-pass | per-methodology | per-layer (default unset, scope workflow_run)
WHEN:
  REQUIRE edits have been applied to the skill file
DO:
  LOAD {cf-studio-path}/.core/requirements/prompt-bug-finding.md
  LOAD {cf-studio-path}/.core/requirements/consistency-checklist.md
  EMIT_MENU ReviewGranularityMenu WHEN REVIEW_GRANULARITY == unset
  RUN the chosen review at REVIEW_GRANULARITY, dispatching cf-pdsl-reviewer (prompt-engineering + prompt-bug-finding) and cf-semantic-reviewer-consistency (consistency-checklist) instances in parallel
  RUN aggregation of every reviewer's findings into one deduplicated review report
  CONTINUE WriteSkillsReviewLoop WHEN review findings remain
  STOP_TURN WHEN no review findings remain
RULES:
  ALWAYS offer the granularity choice with a suggested level by change size: tiny edit (≤10 changed lines) -> single-pass, moderate edit (11–50 changed lines) -> per-methodology, new file or large/structural change (>50 changed lines) -> per-layer
  ALWAYS read each methodology's current Layer Map (prompt-engineering layers, prompt-bug-finding layers, consistency-checklist categories) to determine its full set of layers before a per-layer or per-methodology dispatch, so added layers are covered automatically and never a fixed count
  ALWAYS scope each reviewer to only its assigned slice (all methodologies / one methodology / one layer) and run independent reviewers in parallel
  ALWAYS aggregate and deduplicate all findings into one report before iterating fixes
  ALWAYS iterate the review-fix loop until no findings remain
MENU ReviewGranularityMenu
TITLE: Choose review depth — the suggested level fits the change size.
OPTIONS:
  1 single-pass -> SET REVIEW_GRANULARITY = single-pass; all three methodologies (prompt-engineering, prompt-bug-finding, consistency-checklist) are reviewed in one combined pass (fastest; suggested for tiny edits)
  2 per-methodology -> SET REVIEW_GRANULARITY = per-methodology; one cf-pdsl-reviewer for all prompt-engineering + prompt-bug-finding layers and one cf-semantic-reviewer-consistency for all consistency-checklist categories (balanced; suggested for moderate edits)
  3 per-layer -> SET REVIEW_GRANULARITY = per-layer; one reviewer per layer/category of each methodology, L1 through each methodology's last, in parallel (most thorough; suggested for new files or structural changes)
  INVALID -> EMIT_MENU ReviewGranularityMenu
NOTES:
  Aggregation merges every reviewer's findings into one report, dedupes by (LOCATION, category, ROOT_CAUSE), keeps the highest SEVERITY and CONFIDENCE when collapsing duplicates, and preserves each finding's full ReviewFindingContract fields.
```

```pdsl
UNIT WriteSkillsDispatch
PURPOSE: Dispatch the sub-agents that write, fix, and review skills.
RULES:
  ALWAYS dispatch cf-pdsl-author from {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-author.md to write skills and apply review fixes
  ALWAYS resolve git_commit_mode (probe once per session), contributing_guide (discover; null when none found), and the mode-matched git_constraint before any write-capable cf-pdsl-author dispatch, and ALWAYS include all three in that dispatch payload
  ALWAYS include the WriteSkillsExploreGate-resolved resource_context (when RESOURCE_CONTEXT == provided) in every cf-pdsl-author and reviewer dispatch payload as read-only context (an absolute path or reference, never inline prompt text), NEVER as a gate on an author or reviewer verdict
  ALWAYS dispatch cf-pdsl-reviewer from {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-reviewer.md (prompt-engineering + prompt-bug-finding) and cf-semantic-reviewer-consistency from {cf-studio-path}/.core/skills/studio/agents/cf-semantic-reviewer-consistency.md (consistency-checklist) per the chosen REVIEW_GRANULARITY: single-pass = one reviewer over all three methodologies; per-methodology = cf-pdsl-reviewer over its prompt-engineering + prompt-bug-finding layers and cf-semantic-reviewer-consistency over all consistency-checklist categories; per-layer = one reviewer per layer/category for every layer each methodology defines (L1 through its last), never a fixed count
  ALWAYS synthesize into each reviewer instance only its assigned slice for the chosen granularity, never more than its scope
```
