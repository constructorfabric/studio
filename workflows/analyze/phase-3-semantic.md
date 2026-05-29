---
name: analyze-phase-3-semantic
description: "Invoke when running Analyze Phase 3 to dispatch the selected semantic reviewer sub-agents and merge their findings."
purpose: Analyze Phase 3 — dispatch selected semantic reviewers and merge findings
loaded_by: workflows/analyze.md
version: 1.0
---

<!-- toc -->
<!-- /toc -->

```text
UNIT AnalyzePhase3Semantic

PURPOSE:
  Dispatch selected semantic reviewer sub-agents and merge findings, using
  either a planned execution plan or the legacy per-methodology matrix.

STATE:
  PARTIAL: false | true
    default: false
    note: may be set by an earlier phase; do not reset to false if already true

WHEN:
  deterministic gate is PASS OR SKIPPED (with validator availability proof)
  OR SEMANTIC_ONLY == true

DO:
  REQUIRE REVIEWER_PLAN_RESOLVED is set by {cf-studio-path}/.core/workflows/analyze/phase-2.5-reviewer-plan.md
    IF REVIEWER_PLAN_RESOLVED is unset:
      EMIT "Reviewer plan is unset. Routing back to Phase 2.5 to rebuild the plan."
      CONTINUE workflows/analyze/phase-2.5-reviewer-plan.md § Storage Choice
  IF REVIEWER_PLAN_RESOLVED == cancelled_partial_cache:
    EMIT disclosed reviewer-plan cache state from Phase 2.5
    STOP_TURN (do not enter Phase 3)
  IF PARTIAL != true:
    SET PARTIAL = false
  REQUIRE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md has run before any cf-* dispatch
  IF REVIEWER_EXECUTION_PLAN is non-null:
    CONTINUE PlannedMultiReviewerDispatch
  IF REVIEWER_PLAN_RESOLVED is one of:
      auto_skipped_inline_fallback | auto_skipped_no_methodology | auto_skipped_explain_mode:
    CONTINUE LegacySingleDispatch
  ELSE:
    EMIT "Reviewer plan is in an unexpected state (REVIEWER_PLAN_RESOLVED={value}). Routing back to Phase 2.5 to rebuild the plan."
    CONTINUE workflows/analyze/phase-2.5-reviewer-plan.md

UNIT PlannedMultiReviewerDispatch

PURPOSE:
  Execute REVIEWER_EXECUTION_PLAN in dependency order with optional parallelism.

DO:
  Re-validate plan immediately before dispatch:
    - every active methodology has at least one task
    - union of path_partition per methodology covers every applicable input path
    - partitions for same methodology are disjoint
    - every reviewer matches task's methodology
    - every parallel_groups[].task_ids names an existing task
    - every parallel_groups[].depends_on references an earlier group
    - each parallel_groups[].depends_on group has completed before its group runs
  IF re-validation fails:
    EMIT failure details
    Route back to phase-2.5-reviewer-plan.md: ask whether to rerun planner or stop
    FORBID entering legacy single-dispatch matrix from a failed or stale plan
    STOP_TURN
  FOR each parallel group in dependency order:
    Build one reviewer dispatch payload per task (replace path inputs with task's path_partition):
      artifact tasks          -> target_paths = task.path_partition
      code / code-bug tasks   -> code_paths   = task.path_partition
      prompt / prompt-bug     -> target_paths = task.path_partition (already filtered)
      consistency tasks       -> target_paths = task.path_partition (planner emits at most one)
    IF INLINE_FALLBACK == false: dispatch tasks in same group in parallel
    IF INLINE_FALLBACK == true:  run tasks sequentially; EMIT one-line parallelism-degraded warning
    Parse each reviewer return:
      IF review_result.type == "VALIDATION_REPORT":
        REQUIRE matching "Validation Report — <Section>" block and findings JSON
      IF checkpoint.type == "PARTIAL_CHECKPOINT":
        REQUIRE matching "Partial Checkpoint — <Section>" block, checkpoint JSON, findings JSON
        Mark task partial; SET PARTIAL = true
        Store checkpoint in semantic_partial_checkpoints
        Merge only findings backed by already-covered evidence
        FORBID requiring Validation Report block for that task
        FORBID treating missing validation-report block as reviewer failure
    IF any planned task fails:
      Surface failing task id and reviewer; keep collected findings
      Mark task's parallel group as failed
      Before dispatching each later group:
        Compute transitive dependency set from parallel_groups[].depends_on
        Mark BLOCKED_BY_FAILED_DEP any group depending on a failed group
        Continue only with groups whose transitive dependency set has no failed group
      When all unblocked groups complete:
        CONTINUE workflows/analyze/phase-3-to-4-checkpoint.md with PARTIAL=true
    IF any task returned PARTIAL_CHECKPOINT:
      Finish independent unblocked groups
      CONTINUE workflows/analyze/phase-3-to-4-checkpoint.md with PARTIAL=true
        carry semantic_partial_checkpoints, completed findings, dispatch statuses, resume inputs
  Merge findings per namespace: V, Ra, Rc, Rcb, Rp, Rpb, Rcons
  Renumber within each namespace from 001 after merge (contiguous IDs)
  CONTINUE workflows/analyze/phase-3-to-4-checkpoint.md

UNIT LegacySingleDispatch

PURPOSE:
  Dispatch one sub-agent per active methodology and merge findings.

DO:
  For each applicable condition, dispatch the named sub-agent and merge findings:
    PROMPT_REVIEW=true AND PROMPT_BUG_REVIEW=true ->
      DISPATCH cf-semantic-reviewer-prompt AND cf-prompt-bug-finder in parallel
      Merge under Rp (prompt-reviewer) and Rpb (bug-finder) namespaces
    PROMPT_REVIEW=true AND PROMPT_BUG_REVIEW=false ->
      DISPATCH cf-semantic-reviewer-prompt
    PROMPT_BUG_REVIEW=true AND PROMPT_REVIEW=false ->
      DISPATCH cf-prompt-bug-finder
    ARTIFACT_REVIEW=true OR (TARGET_TYPE == artifact AND no prompt/code methodology owns target) ->
      DISPATCH cf-semantic-reviewer-artifact
    TARGET_TYPE == code OR CODE_REVIEW=true ->
      DISPATCH cf-semantic-reviewer-code
    CODE_BUG_REVIEW=true ->
      DISPATCH cf-code-bug-finder
    CONSISTENCY_REVIEW=true AND len(target_paths) >= 2 ->
      DISPATCH cf-semantic-reviewer-consistency
      IF fewer than two paths available:
        EMIT "consistency-skipped: single-target"
  For PARTIAL_CHECKPOINT returns:
    SET PARTIAL = true
    Store in semantic_partial_checkpoints; merge supported findings
    CONTINUE workflows/analyze/phase-3-to-4-checkpoint.md with PARTIAL=true
    FORBID claiming clean semantic coverage until checkpoint resumed and completed
  Merge findings per namespace: V, Ra, Rc, Rcb, Rp, Rpb, Rcons (numbering from 001)

RULES:
  - MUST run inline-fallback-probe.md before any cf-* sub-agent dispatch
  - MUST set PARTIAL=false on entry unless already set by an earlier phase
  - MUST REQUIRE REVIEWER_PLAN_RESOLVED is set before entering
  - MUST_NOT enter Phase 3 when REVIEWER_PLAN_RESOLVED=cancelled_partial_cache
  - MUST_NOT enter legacy single-dispatch matrix from a failed or stale plan
  - MUST_NOT silently degrade a failed plan to REVIEWER_PLAN_RESOLVED=auto_skipped_inline_fallback
  - MUST support PARTIAL_CHECKPOINT only for reviewers whose contract declares it
  - MUST_NOT invent a partial shape for artifact or consistency reviewers unless
    their agent prompt defines it
  - MUST renumber findings within each namespace from 001 after merge
  - MUST_NOT dispatch Phase 3 semantic reviewers when EXPLAIN_MODE=true

NOTES:
  Dispatch inputs per methodology:
    artifact reviewer:  target_paths={PATHS}, kit rules, checklist, template,
                        examples/example.md, cross refs, rules_mode, traceability_mode
    code reviewer:      design_artifact_path, code_paths=code_targets,
                        diff_scope, cross refs, rules_mode, traceability_mode, kit_rules_path
    code bug finder:    design_artifact_path, code_paths, diff_scope, cross refs,
                        rules_mode, kit_rules_path
    prompt reviewer:    target_paths=prompt_targets, kit_rules_path, rules_mode, cross refs
    prompt bug finder:  same prompt_targets, kit_rules_path, rules_mode, cross refs
    consistency:        target_paths={PATHS}, baseline_path, kit_rules_path,
                        rules_mode, namespace_prefix="Rcons"

  For change-review code dispatch: code_paths = diff_scope.review_targets filtered to code-only.
  For change-review prompt dispatch: filter diff_scope.review_targets to prompt-typed targets.

  Pre-dispatch fail-stop and Mode B degradation rules:
    {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md
```
