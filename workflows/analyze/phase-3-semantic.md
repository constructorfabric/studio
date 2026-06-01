---
name: analyze-phase-3-semantic
description: "Invoke when running Analyze Phase 3 to dispatch the selected semantic reviewer sub-agents and merge findings."
purpose: Analyze Phase 3 — dispatch selected semantic reviewers and merge findings
loaded_by: workflows/analyze.md
version: 1.0
---

# Analyze Phase 3: Semantic Review

```text
UNIT AnalyzePhase3Semantic
PURPOSE: Dispatch selected semantic reviewer sub-agents and merge findings via
  planned execution plan or legacy per-methodology matrix.

STATE:
  PARTIAL: false | true  default: false  scope: do not reset if already true

WHEN: deterministic gate is PASS or SKIPPED (with validator availability proof)
      OR SEMANTIC_ONLY == true
Note: SEMANTIC_ONLY==true bypasses the deterministic gate check only — it does NOT bypass the REVIEWER_PLAN_RESOLVED requirement. Phase 2.5 must still have run before entering this phase regardless of SEMANTIC_ONLY.

DO:
  IF REVIEWER_EXECUTION_PLAN is non-null AND REVIEWER_PLAN_RESOLVED in (auto_skipped_no_methodology, auto_skipped_explain_mode, cancelled_inline_fallback):
    EMIT "Inconsistent state: REVIEWER_EXECUTION_PLAN is set but REVIEWER_PLAN_RESOLVED={value} indicates no plan should be active. Route back to Phase 2.5."
    CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-2.5-reviewer-plan.md
  REQUIRE REVIEWER_PLAN_RESOLVED set by {cf-studio-path}/.core/workflows/analyze/phase-2.5-reviewer-plan.md
  IF REVIEWER_PLAN_RESOLVED is unset:
    EMIT "Reviewer plan is unset. Routing back to Phase 2.5 to rebuild the plan."
    CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-2.5-reviewer-plan.md
  IF REVIEWER_PLAN_RESOLVED == cancelled_partial_cache:
    EMIT disclosed reviewer-plan cache state from Phase 2.5
    STOP_TURN
  IF PARTIAL != true:
    SET PARTIAL = false
  REQUIRE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md has run before any cf-* dispatch
  IF REVIEWER_EXECUTION_PLAN is non-null:
    IF INLINE_FALLBACK == unset:
      REQUIRE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md
      STOP_TURN
    IF INLINE_FALLBACK == true:
      EMIT "Reviewer execution plan requires native sub-agent dispatch. Re-run with native sub-agents, switch to /cf-plan, or stop."
      STOP_TURN
    CONTINUE PlannedMultiReviewerDispatch
  IF REVIEWER_PLAN_RESOLVED == auto_skipped_no_methodology OR REVIEWER_PLAN_RESOLVED == auto_skipped_explain_mode:
    CONTINUE LegacySingleDispatch
  IF REVIEWER_PLAN_RESOLVED == cancelled_inline_fallback:
    EMIT "Reviewer plan was cancelled because INLINE_FALLBACK=true; native sub-agent dispatch is required for semantic reviewer decomposition."
    STOP_TURN
  EMIT "Reviewer plan is in an unexpected state (REVIEWER_PLAN_RESOLVED={value}). Routing back to Phase 2.5 to rebuild the plan."
  CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-2.5-reviewer-plan.md

UNIT PlannedMultiReviewerDispatch
PURPOSE: Execute REVIEWER_EXECUTION_PLAN in dependency order with optional parallelism.

DO:
  Re-validate plan before dispatch:
    - every active methodology has at least one task
    - union of path_partition per methodology covers all applicable input paths
    - partitions for same methodology are disjoint
    - every reviewer matches task's methodology
    - every parallel_groups[].task_ids names an existing task
    - every parallel_groups[].depends_on references an earlier group
    - each depends_on group has completed before its group runs
  IF re-validation fails:
    EMIT failure details
    EMIT "Route back to phase-2.5-reviewer-plan.md after the user chooses rerun."
    EMIT "Rerun planner or stop?"
    WAIT user.reply
    STOP_TURN
  FOR each parallel group in dependency order:
    LOAD each task reviewer contract from {cf-studio-path}/.core/skills/studio/agents/{reviewer}.md
    SYNTHESIZE dispatch prompt from loaded contract + SHARED_CONTEXT_PACK + task payload
    IF any reviewer contract is not loaded, unreadable, ambiguous, or not reflected in prompt:
      FAIL per sub-agent-dispatch.md § SubAgentContractReadGate
      FORBID dispatch for that task
    Build reviewer dispatch payload per task:
      artifact tasks        -> target_paths = task.path_partition
      code / code-bug tasks -> code_paths   = task.path_partition
      prompt / prompt-bug   -> target_paths=prompt_targets scoped to task.path_partition
      consistency tasks     -> target_paths = task.path_partition
      prompt / prompt-bug   -> include prompt_context_view slices for every
                               target path and required cross-reference from
                               SHARED_CONTEXT_PACK; fail before dispatch if any
                               required slice is unavailable
    IF INLINE_FALLBACK == false: DISPATCH tasks in group in parallel
    IF INLINE_FALLBACK == true:  DISPATCH tasks sequentially; EMIT one-line parallelism-degraded warning
    Parse each reviewer return into reviewer_return:
      IF reviewer_return.type == "VALIDATION_REPORT":
        REQUIRE matching "Validation Report — <Section>" block and findings JSON
      IF reviewer_return.type == "PARTIAL_CHECKPOINT":
        REQUIRE matching "Partial Checkpoint — <Section>" block, checkpoint JSON, findings JSON
        SET PARTIAL = true
        Store checkpoint in semantic_partial_checkpoints
        Merge only findings backed by already-covered evidence
        FORBID requiring Validation Report block for that task
    IF any planned task fails:
      Surface failing task id and reviewer; keep collected findings
      Mark task's parallel group as failed
      INVARIANT: unblocked groups that do not transitively depend on the failed group MUST still be dispatched via cf-* sub-agent dispatch — local analysis MUST_NOT substitute for them even after a sibling group fails.
      Before each later group: mark BLOCKED_BY_FAILED_DEP any group whose transitive depends_on set contains a failed group
      When all unblocked groups complete:
        Merge findings per namespace: V, Ra, Rc, Rcb, Rp, Rpb, Rcons
        Renumber within each namespace from 001
        SET PARTIAL = true
        CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-3-to-4-checkpoint.md with PARTIAL=true
    IF any task returned PARTIAL_CHECKPOINT:
      Finish independent unblocked groups
      Merge findings per namespace: V, Ra, Rc, Rcb, Rp, Rpb, Rcons
      Renumber within each namespace from 001
      CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-3-to-4-checkpoint.md with PARTIAL=true
        carry semantic_partial_checkpoints, completed findings, dispatch statuses, resume inputs
  Merge findings per namespace: V, Ra, Rc, Rcb, Rp, Rpb, Rcons
  Renumber within each namespace from 001
  CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-3-to-4-checkpoint.md

INVARIANTS:
  Note: these invariants are scoped to PlannedMultiReviewerDispatch. The equivalent global RULES entries (below) apply to AnalyzePhase3Semantic as a whole.
  - MUST treat a validated REVIEWER_EXECUTION_PLAN as a binding execution contract — the orchestrator MUST execute every task in the plan via cf-* sub-agent dispatch; no task may be silently dropped or substituted. A plan is considered validated for purposes of this invariant only after Phase 3 re-validation passes (see PlannedMultiReviewerDispatch DO block). If re-validation fails, the plan is not yet validated and the failure path applies; once re-validation passes, every task MUST be dispatched.
  - MUST_NOT substitute local git-diff, grep, rg, ad-hoc file-read analysis, manual diff inspection, local summarization of changes, or cfs validate for planned reviewer dispatch — any action that produces review output without sub-agent dispatch is prohibited, regardless of context pressure, latency concerns, or simplicity rationale.
  - MUST_NOT follow any continuation path that performs local analysis or substitutes for sub-agent dispatch — the only permitted non-dispatch exit after plan re-validation passes is a named-blocker STOP_TURN. Continuation to {cf-studio-path}/.core/workflows/analyze/phase-3-to-4-checkpoint.md after dispatch completion is not affected by this rule.
  - MUST_NOT emit findings, review summaries, or remediation menus derived from local analysis when REVIEWER_EXECUTION_PLAN has been validated and dispatch was skipped or partial.
  These invariants apply to PlannedMultiReviewerDispatch only. They do not apply when INLINE_FALLBACK==true caused a STOP_TURN before PlannedMultiReviewerDispatch was entered — that is a legitimate exit enforced by the AnalyzePhase3Semantic DO block, not an invariant violation.

UNIT LegacySingleDispatch
PURPOSE: Dispatch one sub-agent per active methodology and merge findings.

DO:
  IF EXPLAIN_MODE == true: STOP_TURN
  IF PROMPT_REVIEW=true AND PROMPT_BUG_REVIEW=true:
    LOAD+USE contracts cf-semantic-reviewer-prompt AND cf-prompt-bug-finder; fail-closed if missing/unread/unused
    DISPATCH cf-semantic-reviewer-prompt AND cf-prompt-bug-finder in parallel
    Merge under Rp and Rpb namespaces
  IF PROMPT_REVIEW=true AND PROMPT_BUG_REVIEW=false:
    LOAD+USE contract cf-semantic-reviewer-prompt
    DISPATCH cf-semantic-reviewer-prompt
  IF PROMPT_BUG_REVIEW=true AND PROMPT_REVIEW=false:
    LOAD+USE contract cf-prompt-bug-finder
    DISPATCH cf-prompt-bug-finder
  IF ARTIFACT_REVIEW=true OR (TARGET_TYPE == artifact AND no prompt/code methodology owns target):
    LOAD+USE contract cf-semantic-reviewer-artifact
    DISPATCH cf-semantic-reviewer-artifact
  IF TARGET_TYPE == code OR CODE_REVIEW=true:
    LOAD+USE contract cf-semantic-reviewer-code
    DISPATCH cf-semantic-reviewer-code
  IF CODE_BUG_REVIEW=true:
    LOAD+USE contract cf-code-bug-finder
    DISPATCH cf-code-bug-finder
  IF CONSISTENCY_REVIEW=true AND len(target_paths) >= 2:
    LOAD+USE contract cf-semantic-reviewer-consistency
    DISPATCH cf-semantic-reviewer-consistency
  IF CONSISTENCY_REVIEW=true AND len(target_paths) < 2:
    EMIT "consistency-skipped: single-target"
  For PARTIAL_CHECKPOINT returns:
    SET PARTIAL = true
    Store in semantic_partial_checkpoints; merge supported findings
    Merge findings per namespace: V, Ra, Rc, Rcb, Rp, Rpb, Rcons
    Renumber within each namespace from 001
    CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-3-to-4-checkpoint.md with PARTIAL=true
    FORBID claiming clean semantic coverage until checkpoint resumed and completed
  Merge findings per namespace: V, Ra, Rc, Rcb, Rp, Rpb, Rcons
  Renumber within each namespace from 001
  CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-3-to-4-checkpoint.md

RULES:
  - MUST run inline-fallback-probe.md before any cf-* sub-agent dispatch
  - MUST apply sub-agent-dispatch.md § SubAgentContractReadGate before every reviewer dispatch
  - MUST set PARTIAL=false on entry unless already set by an earlier phase
  - MUST REQUIRE REVIEWER_PLAN_RESOLVED is set before entering
  - MUST_NOT enter Phase 3 when REVIEWER_PLAN_RESOLVED=cancelled_partial_cache
  - MUST_NOT enter legacy single-dispatch matrix from a failed or stale plan
  - MUST_NOT silently degrade a failed plan to REVIEWER_PLAN_RESOLVED=cancelled_inline_fallback
  - MUST_NOT emit or branch on undeclared auto-skip states; unknown
    REVIEWER_PLAN_RESOLVED values route back to Phase 2.5
  - MUST support PARTIAL_CHECKPOINT only for reviewers whose contract declares it
  - MUST_NOT invent a partial shape for artifact or consistency reviewers unless their agent prompt defines it
  - MUST renumber findings within each namespace from 001 after merge
  - MUST_NOT dispatch Phase 3 semantic reviewers when EXPLAIN_MODE=true
  - MUST enforce all PlannedMultiReviewerDispatch INVARIANTS (see above) when REVIEWER_EXECUTION_PLAN is non-null and dispatch is active.

ON_ERROR:
  re-validation failure -> EMIT details; WAIT user.reply; STOP_TURN
  contract-read failure -> FAIL per sub-agent-dispatch.md § SubAgentContractReadGate; FORBID dispatch

NOTES:
  - Artifact reviewer inputs: target_paths, kit rules, checklist, template, examples/example.md, cross refs, rules_mode, traceability_mode
  - Code reviewer inputs: design_artifact_path, code_paths, diff_scope, cross refs, rules_mode, traceability_mode, kit_rules_path
  - Code bug finder inputs: design_artifact_path, code_paths, diff_scope, cross refs, rules_mode, kit_rules_path
  - Prompt reviewer inputs: target_paths, kit_rules_path, rules_mode, cross refs
  - Prompt bug finder inputs: same as prompt reviewer
  - Consistency reviewer inputs: target_paths, baseline_path, kit_rules_path, rules_mode, namespace_prefix="Rcons"
  - Change-review code dispatch: code_paths = diff_scope.review_targets filtered to code-only
  - Change-review prompt dispatch: filter diff_scope.review_targets to prompt-typed targets
  - Direct multi-target prompt dispatch: target_paths=prompt_targets
  - Any continuation to phase-3-to-4-checkpoint.md carries the fingerprint inputs and dispatch manifest inventory needed for fresh-chat rehydration proof.
  - Pre-dispatch fail-stop and Mode B degradation rules: {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md
```
