---
name: analyze-phase-2.5-reviewer-plan
description: "Invoke when building the reviewer execution plan (methodology × path partition) for parallel Phase 3 dispatch."
purpose: Analyze Phase 2.5 — build a reviewer execution plan so Phase 3 can dispatch reviewer sub-agents in parallel across methodology × path-partition; mandatory when SUB_AGENT_SESSION_APPROVED=true.
loaded_by: workflows/analyze.md
version: 1.0
---

# Phase 2.5: Reviewer Plan

```text
UNIT AnalyzeReviewerPlan

PURPOSE: Decompose the analyze task into reviewer sub-agent tasks partitioned by
  methodology and path so Phase 3 can dispatch them in parallel.

STATE:
  PLANNER_RETRY_COUNT: integer  default: 0  scope: entry to this phase
  REVIEWER_PLAN_RESOLVED: unset | memory | disk | cancelled_partial_cache |
    cancelled_inline_fallback | auto_skipped_no_methodology |
    auto_skipped_explain_mode  default: unset
  REVIEWER_EXECUTION_PLAN: null | parsed reviewer_plan JSON  default: null
  REVIEWER_PLAN_CACHE_DIR: null | directory path  default: null
  PLANNER_RETRY_MAX: 2

NOTES:
  CF_PHASE_GATE is defined session-scoped in SKILL.md § Phase-Skip Gate.

WHEN: After Phase 2 (Deterministic Gate) and before Phase 3 (Semantic Review)

DO:
  SET PLANNER_RETRY_COUNT = 0
  IF INLINE_FALLBACK == true:
    SET REVIEWER_PLAN_RESOLVED = cancelled_inline_fallback
    SET REVIEWER_EXECUTION_PLAN = null
    EMIT "Reviewer decomposition requires native sub-agent dispatch. Inline fallback cannot silently continue to semantic review. Re-run with native sub-agents, switch to Invoke skill `cf-plan`, or stop."
    STOP_TURN
  IF EXPLAIN_MODE == true:
    SET REVIEWER_PLAN_RESOLVED = auto_skipped_explain_mode
    SET REVIEWER_EXECUTION_PLAN = null
    CONTINUE workflows/analyze/phase-3-semantic.md
  IF no semantic methodology flag is active:
    SET REVIEWER_PLAN_RESOLVED = auto_skipped_no_methodology
    SET REVIEWER_EXECUTION_PLAN = null
    CONTINUE workflows/analyze/phase-3-semantic.md
  EMIT_MENU StorageChoiceMenu
  WAIT user.reply
  STOP_TURN

MENU StorageChoiceMenu:
  TITLE: "Reviewer plan storage (disk = resumable after compaction; memory = in-context only):"
  OPTIONS:
    empty|enter|memory|1 ->
      SET REVIEWER_PLAN_RESOLVED = memory
      EMIT "(Note: a memory plan is NOT recoverable if context is compacted before Phase 3 completes — choose disk for long/context-heavy sessions.)"
      CONTINUE PlannerDispatch
    disk|save|2 ->
      SET REVIEWER_PLAN_RESOLVED = disk
      CONTINUE PlannerDispatch
    stop_token ->
      LOAD {cf-studio-path}/.core/workflows/shared/stop-token-policy.md
      STOP_TURN
    no|skip|3 ->
      EMIT "Decomposition is mandatory while sub-agents are approved. Reply enter/memory or disk."
      WAIT user.reply
      STOP_TURN
  INVALID:
    EMIT "Reply not recognized. Expected enter/memory or disk."
    WAIT user.reply
    STOP_TURN

UNIT PlannerDispatch

PURPOSE: Dispatch cf-analyze-planner and validate the returned reviewer execution plan.

DO:
  REQUIRE `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md` has run
  LOAD {cf-studio-path}/.core/skills/studio/agents/cf-analyze-planner.md
    as the analyze-planner source contract
  SYNTHESIZE final dispatch prompt from the loaded planner contract plus
    SHARED_CONTEXT_PACK and the payload below
  IF planner source contract is not loaded, unreadable, ambiguous, or not
     reflected in the final dispatch prompt:
    FAIL per sub-agent-dispatch.md § SubAgentContractReadGate
    FORBID dispatch
  DISPATCH cf-analyze-planner (read-only) with:
    plan_mode             = "memory" or "disk"
    work_request          = original analyze request / approved statement of what must be reviewed or analyzed
    target_type, mode, kind, rules_mode, system
    kit_rules_path, checklist_path, template_path, example_path, design_artifact_path
    target_paths          = resolved analyze target set
    code_targets          = Phase 0 typed code targets
    prompt_targets        = Phase 0 typed prompt targets
    cross_refs            = related cross-reference paths
    diff_scope            = Phase 0 diff scope or null
    methodology_flags     = current values of PROMPT_REVIEW, PROMPT_BUG_REVIEW,
                            CODE_BUG_REVIEW, CONSISTENCY_REVIEW, ARTIFACT_REVIEW, CODE_REVIEW
    available_reviewers   = reviewer sub-agents from phase-3-semantic.md
    size_estimate_lines   = Phase 0.1 estimate
  Parse marker <!-- reviewer_plan --> and following JSON block.
  Validate:
    - every active methodology has at least one task
    - work_request is present, non-empty, and preserves what the user asked to analyze
    - union of path_partition per methodology covers every applicable input path
    - partitions for same methodology are disjoint
    - every reviewer matches task's methodology
    - every parallel_groups[].task_ids names an existing task
    - every task.parallel_group is a string id matching an existing parallel_groups[].id
    - every parallel_groups[].depends_on references an earlier group
    - every parallel_groups[] entry includes id, task_ids, depends_on, execution, and reason
    - every parallel_groups[].execution is "parallel" or "sequential"
  IF validation fails OR planner returns checkpoint.type=PARTIAL_CHECKPOINT:
    INCREMENT PLANNER_RETRY_COUNT
    IF PLANNER_RETRY_COUNT >= PLANNER_RETRY_MAX:
      EMIT "Planner returned PARTIAL_CHECKPOINT twice in this run — manual intervention required. Stopping."
      EMIT_MENU PlannerRecoveryMenu
      WAIT user.reply
      STOP_TURN
    EMIT validation errors
    EMIT_MENU PlannerRecoveryMenu
    WAIT user.reply
    STOP_TURN
  SET REVIEWER_EXECUTION_PLAN = parsed reviewer_plan JSON
  IF REVIEWER_PLAN_RESOLVED == disk:
    CONTINUE DiskModeRendering
  CONTINUE workflows/analyze/phase-3-semantic.md

UNIT DiskModeRendering

PURPOSE: Write validated REVIEWER_EXECUTION_PLAN to cache files when disk mode selected.

DO:
  SET CF_PHASE_GATE = released_for_orchestrator_write
    scope: {cf-studio-path}/.cache/analyze-plans/{slug}-{ISO}/**
  Write cache files:
    {cf-studio-path}/.cache/analyze-plans/{slug}-{ISO}/index.md
      (work_request, summary, risk flags, ordered parallel groups, task table)
    {cf-studio-path}/.cache/analyze-plans/{slug}-{ISO}/plan.json
      (exact parsed REVIEWER_EXECUTION_PLAN including work_request)
    {cf-studio-path}/.cache/analyze-plans/{slug}-{ISO}/reviewers/{reviewer}.md
      (reviewer task subset grouped by methodology, parallel group, and dependency order)
    {cf-studio-path}/.cache/analyze-plans/{slug}-{ISO}/tasks/{task_id}.md
      (task title, work_request, methodology, reviewer, path partition,
       dependencies, parallel group, rationale, acceptance criteria)
  IF all writes succeed:
    SET CF_PHASE_GATE = armed
    SET REVIEWER_PLAN_CACHE_DIR = directory path
    EMIT "Reviewer plan saved: {REVIEWER_PLAN_CACHE_DIR}"
    CONTINUE workflows/analyze/phase-3-semantic.md
  IF any write fails:
    EMIT_MENU PartialCacheMenu
    WAIT user.reply
    STOP_TURN

MENU PartialCacheMenu:
  TITLE: |
    Partial cache write failure.
    Written: {list of successfully written files, or "none"}
    Failed:  {list of failed files with error reason}
    Suggested: 1
  OPTIONS:
    1 ->
      SET CF_PHASE_GATE = released_for_orchestrator_write
      Re-attempt only the failed writes; do not re-write already successful files.
      SET CF_PHASE_GATE = armed
      IF retry fails: EMIT_MENU PartialCacheMenu
    2 ->
      SET REVIEWER_PLAN_RESOLVED = memory
      SET CF_PHASE_GATE = released_for_orchestrator_write
      Delete only files created during this DiskModeRendering attempt and
        listed in Written above; leave pre-existing files untouched
      SET REVIEWER_PLAN_CACHE_DIR = null
      SET CF_PHASE_GATE = armed
      CONTINUE workflows/analyze/phase-3-semantic.md
    3 ->
      SET REVIEWER_PLAN_RESOLVED = cancelled_partial_cache
      SET REVIEWER_PLAN_CACHE_DIR = null
      SET CF_PHASE_GATE = armed
      STOP_TURN
    stop_token -> treat as 3
  INVALID:
    EMIT "Reply `1`, `2`, or `3`."
    WAIT user.reply
    STOP_TURN

MENU PlannerRecoveryMenu:
  TITLE: Reviewer planner failed validation or returned PARTIAL_CHECKPOINT.
  OPTIONS:
    1 ->
      CONTINUE PlannerDispatch
    2 ->
      SET REVIEWER_PLAN_RESOLVED = cancelled_partial_cache
      SET REVIEWER_EXECUTION_PLAN = null
      SET CF_PHASE_GATE = armed
      STOP_TURN
  INVALID:
    EMIT "Reply `1` to rerun the planner or `2` to stop."
    WAIT user.reply
    STOP_TURN

INVARIANTS:
  - MUST apply sub-agent-dispatch.md § SubAgentContractReadGate before
    dispatching cf-analyze-planner
  - MUST_NOT set REVIEWER_PLAN_RESOLVED=cancelled_inline_fallback after
    planner dispatch has already failed validation
  - MUST_NOT introduce undeclared reviewer-plan resolution states after planner
    dispatch has already failed validation
  - MUST_NOT clear plan into fallback path after sub-agent decomposition selected
  - MUST reset CF_PHASE_GATE=armed after named writes complete or fail
  - MUST_NOT write files while CF_PHASE_GATE == armed
```
