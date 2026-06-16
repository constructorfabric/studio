# Write Skills Review Run
```pdsl
UNIT WriteSkillsReviewRun
PURPOSE: Gate review granularity, dispatch reviewer sub-agents, and aggregate their findings into one deduplicated report.
WHEN:
  REQUIRE REVIEW_TARGET_PATHS != unset
DO:
  SET REVIEW_GRANULARITY_SCOPE = "Skill/prompt review scope: single-pass covers prompt-engineering, prompt-bug-finding, and consistency-checklist together; per-methodology dispatches cf-pdsl-reviewer for prompt-engineering plus prompt-bug-finding and cf-semantic-reviewer-consistency separately; per-layer dispatches one reviewer per current layer/category."
  RUN SemanticReviewGranularityGate WHEN REVIEW_GRANULARITY == unset
  RUN SubAgentDispatch for the selected reviewer dispatch group before launching reviewer instances
  RUN prepare reviewer inputs for the chosen granularity: read each methodology's current Layer Map before per-layer or per-methodology dispatch, and synthesize into each reviewer instance only its assigned slice, declared REVIEW_TARGET_PATHS, REVIEW_TARGET_SLICES, BRAINSTORM_DECISIONS, and explicit read-only resource_context references
  RUN the chosen review at REVIEW_GRANULARITY: single-pass = dispatch cf-pdsl-reviewer from {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-reviewer.md and cf-semantic-reviewer-consistency from {cf-studio-path}/.core/skills/studio/agents/cf-semantic-reviewer-consistency.md in one combined dispatch group, then aggregate one report; per-methodology = dispatch cf-pdsl-reviewer over prompt-engineering plus prompt-bug-finding layers and cf-semantic-reviewer-consistency over all consistency-checklist categories in parallel; per-layer = dispatch one reviewer per layer/category for every layer each methodology defines (L1 through its last), never a fixed count
  RUN aggregate every reviewer's findings into one deduplicated ReviewFindingsReport with stable finding IDs and every ReviewFindingContract field, then SET REVIEW_FINDINGS_REMAINING = count of findings in the deduplicated ReviewFindingsReport
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-skills-fix-outcomes.md
  CONTINUE WriteSkillsFixGate
RULES:
  ALWAYS scope each reviewer to only its assigned slice (all methodologies / one methodology / one layer) and run independent reviewers in parallel
  ALWAYS keep workflow-specific reviewer dispatches in this workflow
  ALWAYS run SubAgentDispatch before every native author, validator, reviewer, or review-fix dispatch group
```
```pdsl
UNIT WriteSkillsFixGate
PURPOSE: Present review findings, gate fix approval, and route to fix dispatch or outcome.
WHEN:
  REQUIRE REVIEW_TARGET_PATHS != unset
DO:
  CONTINUE WriteSkillsFixOutcomeClean WHEN REVIEW_FINDINGS_REMAINING == 0
  RUN SemanticReviewFixApprovalGate WHEN findings remain and fixes are applicable
  CONTINUE WriteSkillsFixDispatch WHEN REVIEW_FIX_APPROVED == true
  CONTINUE WriteSkillsFixOutcomeNoChanges WHEN REVIEW_FIX_APPROVED != true
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
  DISPATCH SELECTED_REVIEW_FIX_AGENT with mode=fix, kind=prompt, target_paths=REVIEW_TARGET_PATHS, REVIEW_TARGET_SLICES, APPROVED_REVIEW_FINDING_IDS, REVIEW_FIX_SCOPE, BRAINSTORM_DECISIONS, git_commit_mode=GIT_COMMIT_MODE, contributing_guide=CONTRIBUTING_GUIDE, git_constraint=GIT_CONSTRAINT, commit_footer_contract=COMMIT_FOOTER_CONTRACT, and explicit read-only resource_context references to apply only approved review fixes
```
