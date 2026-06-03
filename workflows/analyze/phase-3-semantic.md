---
name: analyze-phase-3-semantic
description: "Invoke when running Analyze Phase 3 to dispatch the selected semantic reviewer sub-agents and merge findings."
purpose: Analyze Phase 3 — dispatch selected semantic reviewers and merge findings
loaded_by: workflows/analyze.md
version: 1.0
---

# Analyze Phase 3: Semantic Review

```pdsl
UNIT AnalyzePhase3Semantic
PURPOSE: Dispatch selected semantic reviewer sub-agents and merge findings via
  planned execution plan or legacy per-methodology matrix.

STATE:
  - SET PARTIAL: false | true  default: false  scope: do not reset if already true

WHEN:
  - REQUIRE deterministic gate is PASS or SKIPPED (with validator availability proof)
      OR SEMANTIC_ONLY == true
- REQUIRE Note: SEMANTIC_ONLY==true bypasses the deterministic gate check only — it does NOT bypass the REVIEWER_PLAN_RESOLVED requirement. Phase 2.5 must still have run before entering this phase regardless of SEMANTIC_ONLY.

DO:
  - REQUIRE REVIEWER_EXECUTION_PLAN is non-null AND REVIEWER_PLAN_RESOLVED in (auto_skipped_no_methodology, auto_skipped_explain_mode, cancelled_inline_fallback):
    - EMIT "Inconsistent state: REVIEWER_EXECUTION_PLAN is set but REVIEWER_PLAN_RESOLVED={value} indicates no plan should be active. Route back to Phase 2.5."
    - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-2.5-reviewer-plan.md
  - REQUIRE REVIEWER_PLAN_RESOLVED set by {cf-studio-path}/.core/workflows/analyze/phase-2.5-reviewer-plan.md
  - REQUIRE REVIEWER_PLAN_RESOLVED is unset:
    - EMIT "Reviewer plan is unset. Routing back to Phase 2.5 to rebuild the plan."
    - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-2.5-reviewer-plan.md
  - REQUIRE REVIEWER_PLAN_RESOLVED == cancelled_partial_cache:
    - EMIT disclosed reviewer-plan cache state from Phase 2.5
    - STOP_TURN
  - REQUIRE PARTIAL != true:
    - SET PARTIAL = false
  - REQUIRE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md has run before any cf-* dispatch
  - CONTINUE AnalyzePhase3DispatchRouter

UNIT AnalyzePhase3DispatchRouter
PURPOSE: Select planned reviewer execution or explicit legacy auto-skip dispatch.

DO:
  - REQUIRE REVIEWER_EXECUTION_PLAN is non-null:
    - REQUIRE REVIEWER_PLAN_APPROVED != true:
      FAIL-STOP
      EMIT "Reviewer execution plan exists but is not approved. Return to Phase 2.5 approval before Phase 3 dispatch."
      CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-2.5-reviewer-plan.md
      STOP_TURN
    IF INLINE_FALLBACK == unset:
      - REQUIRE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md
      - STOP_TURN
    IF INLINE_FALLBACK == true:
      - EMIT "Reviewer execution plan requires native sub-agent dispatch; semantic review has not started in this branch."
      - EMIT_MENU SemanticDispatchRecoveryMenu
      - WAIT user.reply
      - STOP_TURN
    - CONTINUE PlannedMultiReviewerDispatch
    - RETURN
  - REQUIRE REVIEWER_PLAN_RESOLVED in (memory | disk):
    FAIL-STOP
    EMIT "Reviewer planning was selected, but REVIEWER_EXECUTION_PLAN is missing. Return to Phase 2.5 before Phase 3 dispatch."
    CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-2.5-reviewer-plan.md
    STOP_TURN
  - REQUIRE REVIEWER_PLAN_RESOLVED == auto_skipped_no_methodology OR REVIEWER_PLAN_RESOLVED == auto_skipped_explain_mode:
    - CONTINUE LegacySingleDispatch
    - RETURN
  - REQUIRE REVIEWER_PLAN_RESOLVED == cancelled_inline_fallback:
    - EMIT "Reviewer plan was cancelled because INLINE_FALLBACK=true; semantic reviewer decomposition cannot proceed locally."
    - EMIT_MENU SemanticDispatchRecoveryMenu
    - WAIT user.reply
    - STOP_TURN
  - EMIT "Reviewer plan is in an unexpected state (REVIEWER_PLAN_RESOLVED={value}). Routing back to Phase 2.5 to rebuild the plan."
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-2.5-reviewer-plan.md

RULES:
  - NEVER enter LegacySingleDispatch when REVIEWER_PLAN_RESOLVED is memory or disk
  - NEVER enter LegacySingleDispatch when REVIEWER_EXECUTION_PLAN is non-null
  - NEVER emit semantic findings from local/controller analysis when planned
    reviewer dispatch is available, missing, stale, or unapproved
  - ALWAYS PlannedMultiReviewerDispatch is the only Phase 3 path for approved
    REVIEWER_EXECUTION_PLAN
  - ALWAYS LegacySingleDispatch is allowed only for explicit Phase 2.5 auto-skip
    states: auto_skipped_no_methodology or auto_skipped_explain_mode

MENU SemanticDispatchRecoveryMenu:
  TITLE: |
    Native sub-agent dispatch is required before semantic review can continue.
    No semantic findings were completed on this branch.

    Suggested: 1 when you can re-run with native sub-agents; 2 when you want a
    decomposed fallback plan instead of continuing locally.
  OPTIONS:
    1 -> EMIT "Re-run this analyze request with native sub-agents enabled, then resume Phase 3 semantic review."
         STOP_TURN
    2 -> EMIT "Switch to Invoke skill `cf-plan` to decompose the remaining review work."
         STOP_TURN
    3 -> EMIT "Stopped before semantic review dispatch."
         STOP_TURN
  INVALID:
    EMIT "Reply `1`, `2`, or `3`."
    WAIT user.reply
    STOP_TURN

UNIT PlannedMultiReviewerDispatch
PURPOSE: Execute REVIEWER_EXECUTION_PLAN in dependency order with optional parallelism.

DO:
  - RUN Re-validate plan before dispatch:
    - RUN every active methodology has at least one task
    - union of path_partition per methodology covers all applicable input paths
    - partitions for same methodology are disjoint
    - every reviewer matches task's methodology
    - every parallel_groups[].task_ids names an existing task
    - every task.parallel_group is a string id matching an existing parallel_groups[].id
    - every parallel_groups[].depends_on references an earlier group
    - every parallel_groups[] entry includes id, task_ids, depends_on, execution, and reason
    - every parallel_groups[].execution is "parallel" or "sequential"
    - each depends_on group has completed before its group runs
  - REQUIRE re-validation fails:
    - EMIT failure details
    - EMIT_MENU SemanticPlanRevalidationFailureMenu
    - WAIT user.reply
    - STOP_TURN
  - RUN FOR each parallel group in dependency order:
    - LOAD each task reviewer contract from {cf-studio-path}/.core/skills/studio/agents/{reviewer}.md
    SYNTHESIZE dispatch prompt from loaded contract + SHARED_CONTEXT_PACK + task payload
    IF any reviewer contract is not loaded, unreadable, ambiguous, or not reflected in prompt:
      FAIL per sub-agent-dispatch.md § SubAgentContractReadGate
      - NEVER dispatch for that task
    Build reviewer dispatch payload per task:
      artifact tasks        -> target_paths = task.path_partition
      code / code-bug tasks -> code_paths   = task.path_partition
      freeform tasks        -> target_paths = task.path_partition,
                               freeform_prompt = task.freeform_prompt (= work_request),
                               resource_context = RESOURCE_CONTEXT (verbatim JSON or null)
      prompt / prompt-bug   -> target_paths=prompt_targets scoped to task.path_partition
      consistency tasks     -> target_paths = task.path_partition
      prompt / prompt-bug   -> include prompt_context_view slices only for
                               methodology/instruction assets from
                               SHARED_CONTEXT_PACK; include target paths and
                               cross-reference paths as allowed resources the
                               reviewer must read directly; fail before dispatch
                               if any instruction slice is unavailable or any
                               target/cross-reference resource is not allowed
    IF INLINE_FALLBACK == false: DISPATCH tasks in group in parallel
    IF INLINE_FALLBACK == true:
      - EMIT "Dispatch blocked: planned reviewer execution requires native sub-agent dispatch."
      - EMIT_MENU SemanticDispatchRecoveryMenu
      - WAIT user.reply
      - STOP_TURN
    Parse each reviewer return into reviewer_return:
      IF reviewer_return.type == "VALIDATION_REPORT":
        - REQUIRE matching "Validation Report — <Section>" block and findings JSON
      IF reviewer_return.type == "PARTIAL_CHECKPOINT":
        - REQUIRE matching "Partial Checkpoint — <Section>" block, checkpoint JSON, findings JSON
        - SET PARTIAL = true
        Store checkpoint in semantic_partial_checkpoints
        Merge only findings backed by already-covered evidence
        - NEVER requiring Validation Report block for that task
    IF any planned task fails:
      Surface failing task id and reviewer; keep collected findings
      Mark task's parallel group as failed
      INVARIANT: unblocked groups that do not transitively depend on the failed group ALWAYS still be dispatched via cf-* sub-agent dispatch — local analysis NEVER substitute for them even after a sibling group fails.
      Before each later group: mark BLOCKED_BY_FAILED_DEP any group whose transitive depends_on set contains a failed group
      When all unblocked groups complete:
        Merge findings per namespace: V, Ra, Rc, Rcb, Rp, Rpb, Rcons, Rf
        Renumber within each namespace from 001
        - SET PARTIAL = true
        - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-3-to-4-checkpoint.md with PARTIAL=true
    IF any task returned PARTIAL_CHECKPOINT:
      Finish independent unblocked groups
      Merge findings per namespace: V, Ra, Rc, Rcb, Rp, Rpb, Rcons, Rf
      Renumber within each namespace from 001
      - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-3-to-4-checkpoint.md with PARTIAL=true
        carry semantic_partial_checkpoints, completed findings, dispatch statuses, resume inputs
  - RUN Merge findings per namespace: V, Ra, Rc, Rcb, Rp, Rpb, Rcons, Rf
  - RUN Renumber within each namespace from 001
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-3-to-4-checkpoint.md

INVARIANTS:
  - ALWAYS Note: these invariants are scoped to PlannedMultiReviewerDispatch. The equivalent global RULES entries (below) apply to AnalyzePhase3Semantic as a whole.
  - ALWAYS treat a validated REVIEWER_EXECUTION_PLAN as a binding execution contract — the orchestrator ALWAYS execute every task in the plan via cf-* sub-agent dispatch; no task may be silently dropped or substituted. A plan is considered validated for purposes of this invariant only after Phase 3 re-validation passes (see PlannedMultiReviewerDispatch DO block). If re-validation fails, the plan is not yet validated and the failure path applies; once re-validation passes, every task ALWAYS be dispatched.
  - NEVER substitute local git-diff, grep, rg, ad-hoc file-read analysis, manual diff inspection, local summarization of changes, or cfs validate for planned reviewer dispatch — any action that produces review output without sub-agent dispatch is prohibited, regardless of context pressure, latency concerns, or simplicity rationale.
  - NEVER follow any continuation path that performs local analysis or substitutes for sub-agent dispatch — the only permitted non-dispatch exit after plan re-validation passes is a named-blocker STOP_TURN. Continuation to {cf-studio-path}/.core/workflows/analyze/phase-3-to-4-checkpoint.md after dispatch completion is not affected by this rule.
  - NEVER emit findings, review summaries, or remediation menus derived from local analysis when REVIEWER_EXECUTION_PLAN has been validated and dispatch was skipped or partial.
  - ALWAYS These invariants apply to PlannedMultiReviewerDispatch only. They do not apply when INLINE_FALLBACK==true caused a STOP_TURN before PlannedMultiReviewerDispatch was entered — that is a legitimate exit enforced by the AnalyzePhase3Semantic DO block, not an invariant violation.

UNIT LegacySingleDispatch
PURPOSE: Dispatch one sub-agent per active methodology and merge findings.

DO:
  - REQUIRE EXPLAIN_MODE == true:
    - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-4-output/index.md
  - REQUIRE PROMPT_REVIEW=true AND PROMPT_BUG_REVIEW=true:
    - LOAD+USE contracts cf-semantic-reviewer-prompt AND cf-prompt-bug-finder; fail-closed if missing/unread/unused
    - DISPATCH cf-semantic-reviewer-prompt AND cf-prompt-bug-finder in parallel
    Merge under Rp and Rpb namespaces
  - REQUIRE PROMPT_REVIEW=true AND PROMPT_BUG_REVIEW=false:
    - LOAD+USE contract cf-semantic-reviewer-prompt
    - DISPATCH cf-semantic-reviewer-prompt
  - REQUIRE PROMPT_BUG_REVIEW=true AND PROMPT_REVIEW=false:
    - LOAD+USE contract cf-prompt-bug-finder
    - DISPATCH cf-prompt-bug-finder
  - REQUIRE ARTIFACT_REVIEW=true OR (TARGET_TYPE == artifact AND no prompt/code methodology owns target):
    - LOAD+USE contract cf-semantic-reviewer-artifact
    - DISPATCH cf-semantic-reviewer-artifact
  - REQUIRE TARGET_TYPE == code OR CODE_REVIEW=true:
    - LOAD+USE contract cf-semantic-reviewer-code
    - DISPATCH cf-semantic-reviewer-code
  - REQUIRE CODE_BUG_REVIEW=true:
    - LOAD+USE contract cf-code-bug-finder
    - DISPATCH cf-code-bug-finder
  - REQUIRE CONSISTENCY_REVIEW=true AND len(target_paths) >= 2:
    - LOAD+USE contract cf-semantic-reviewer-consistency
    - DISPATCH cf-semantic-reviewer-consistency
  - REQUIRE CONSISTENCY_REVIEW=true AND len(target_paths) < 2:
    - EMIT "consistency-skipped: single-target"
  - REQUIRE FREEFORM_REVIEW=true:
    - LOAD+USE contract cf-semantic-reviewer-freeform; fail-closed if missing/unread/unused
    - DISPATCH cf-semantic-reviewer-freeform with:
        freeform_prompt = ORIGINAL_INTENT
        target_paths    = target_paths
        resource_context = RESOURCE_CONTEXT (pass verbatim JSON, or null if explore was skipped)
        kit_rules_path  = kit_rules_path
        rules_mode      = rules_mode
        cross_ref_paths = cross_refs
    findings under Rf namespace
  - RUN For PARTIAL_CHECKPOINT returns:
    - SET PARTIAL = true
    Store in semantic_partial_checkpoints; merge supported findings
    Merge findings per namespace: V, Ra, Rc, Rcb, Rp, Rpb, Rcons, Rf
    Renumber within each namespace from 001
    - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-3-to-4-checkpoint.md with PARTIAL=true
    - NEVER claiming clean semantic coverage until checkpoint resumed and completed
  - RUN Merge findings per namespace: V, Ra, Rc, Rcb, Rp, Rpb, Rcons, Rf
  - RUN Renumber within each namespace from 001
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-3-to-4-checkpoint.md

RULES:
  - ALWAYS run inline-fallback-probe.md before any cf-* sub-agent dispatch
  - ALWAYS apply sub-agent-dispatch.md § SubAgentContractReadGate before every reviewer dispatch
  - ALWAYS set PARTIAL=false on entry unless already set by an earlier phase
  - ALWAYS REQUIRE REVIEWER_PLAN_RESOLVED is set before entering
  - NEVER enter Phase 3 when REVIEWER_PLAN_RESOLVED=cancelled_partial_cache
  - NEVER enter legacy single-dispatch matrix from a failed or stale plan
  - NEVER silently degrade a failed plan to REVIEWER_PLAN_RESOLVED=cancelled_inline_fallback
  - NEVER emit or branch on undeclared auto-skip states; unknown
    REVIEWER_PLAN_RESOLVED values route back to Phase 2.5
  - ALWAYS INLINE_FALLBACK/cancelled_inline_fallback exits ALWAYS use
    SemanticDispatchRecoveryMenu or an equivalent recovery menu; bare dead-end
    messages are not sufficient
  - ALWAYS support PARTIAL_CHECKPOINT only for reviewers whose contract declares it
  - NEVER invent a partial shape for artifact or consistency reviewers unless their agent prompt defines it
  - ALWAYS renumber findings within each namespace from 001 after merge
  - NEVER dispatch Phase 3 semantic reviewers when EXPLAIN_MODE=true

MENU SemanticPlanRevalidationFailureMenu:
  TITLE: "Reviewer execution plan failed Phase 3 re-validation. Route back to phase-2.5-reviewer-plan.md or stop."
  OPTIONS:
    1 rerun -> CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-2.5-reviewer-plan.md
    2 stop -> STOP_TURN
  INVALID:
    EMIT "Reply `1` to rerun the planner or `2` to stop."
    WAIT user.reply
    STOP_TURN
  - ALWAYS enforce all PlannedMultiReviewerDispatch INVARIANTS (see above) when REVIEWER_EXECUTION_PLAN is non-null and dispatch is active.

ON_ERROR:
  re-validation failure -> EMIT details; WAIT user.reply; STOP_TURN
  contract-read failure -> FAIL per sub-agent-dispatch.md § SubAgentContractReadGate; NEVER dispatch

NOTES:
  - Artifact reviewer inputs: target_paths, kit rules, checklist, template, examples/example.md, cross refs, rules_mode, traceability_mode
  - Code reviewer inputs: design_artifact_path, code_paths, diff_scope, cross refs, rules_mode, traceability_mode, kit_rules_path
  - Code bug finder inputs: design_artifact_path, code_paths, diff_scope, cross refs, rules_mode, kit_rules_path
  - Prompt reviewer inputs: target_paths, kit_rules_path, rules_mode, cross refs
  - Prompt bug finder inputs: same as prompt reviewer
  - Consistency reviewer inputs: target_paths, baseline_path, kit_rules_path, rules_mode, namespace_prefix="Rcons"
  - Freeform reviewer inputs: freeform_prompt (=ORIGINAL_INTENT/work_request), target_paths, resource_context (RESOURCE_CONTEXT JSON from cf-explorer or null), kit_rules_path, rules_mode, cross_ref_paths; namespace_prefix="Rf"
  - Change-review code dispatch: code_paths = diff_scope.review_targets filtered to code-only
  - Change-review prompt dispatch: filter diff_scope.review_targets to prompt-typed targets
  - Direct multi-target prompt dispatch: target_paths=prompt_targets
  - Any continuation to phase-3-to-4-checkpoint.md carries the fingerprint inputs and dispatch manifest inventory needed for fresh-chat rehydration proof.
  - Pre-dispatch fail-stop and Mode B degradation rules: {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md
```
