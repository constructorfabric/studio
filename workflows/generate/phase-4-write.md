---
name: generate-phase-4-write
description: "Invoke when Phase 3 confirmation is received and the approved author payload must be dispatched to write or fix target files."
purpose: Generate Phase 4 — dispatch author(mode=create), persist manifest, echo Written block
loaded_by: workflows/generate.md
version: 1.0
---

# Generate Phase 4: Write

```text
UNIT Phase4WriteEntry
PURPOSE: Enforce entry conditions before dispatching write-capable author.

DO:
  IF AUTHOR_PLAN_OFFER_RESOLVED unset:
    EMIT "No author plan state available. Return to Phase 1.5."
    ROUTE to workflows/generate/phase-1.5-author-plan.md
    STOP_TURN
  REQUIRE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md loaded before dispatch
  DEFINE instruction_file_targets as target_paths matching:
    workflows/** | requirements/** | **/AGENTS.md | AGENTS.md | any skills/**/SKILL.md
    | any skills/**/agents/*.md | equivalent prompt/agent contract paths named by active workflow
  REQUIRE Phase 3 confirmation (yes) received before author selection
  FORBID dispatching write-capable author directly from orchestrator
  FORBID orchestrator-local Edit/Write/MultiEdit/NotebookEdit/apply_patch/shell-write on instruction_file_targets
  IF instruction_file_targets non-empty AND AUTHOR_PLAN_OFFER_RESOLVED unset:
    FAIL-STOP
    ROUTE to workflows/generate/phase-1.5-author-plan.md
  IF instruction_file_targets non-empty
     AND host.supports_native_subagents == true
     AND SUB_AGENT_SESSION_APPROVED == true
     AND INLINE_FALLBACK == false:
    REQUIRE native selector + selected-author dispatch
  IF instruction_file_targets non-empty AND orchestrator detects manual patch attempt while native author workers registered:
    SET CF_PHASE_GATE = armed
    FAIL-STOP
    IF AUTHOR_EXECUTION_PLAN == null: ROUTE to workflows/generate/phase-1.5-author-plan.md
    ELSE: CONTINUE § Phase4AuthorSelectionDispatch
  REQUIRE AUTHOR_PLAN_OFFER_RESOLVED set by workflows/generate/phase-1.5-author-plan.md
  IF AUTHOR_PLAN_OFFER_RESOLVED unset:
    FAIL-STOP
    ROUTE to workflows/generate/phase-1.5-author-plan.md
  IF AUTHOR_PLAN_OFFER_RESOLVED in (cancelled_by_stop_token | cancelled_planner_failure | cancelled_partial_write):
    FAIL-STOP
    FORBID dispatching write-capable author
    FORBID synthesizing single-author fallback payload
    LEAVE target files untouched

RULES:
  - MUST NOT dispatch write-capable author before Phase 3 yes
  - MUST NOT create files before confirmation
  - MUST NOT create incomplete or placeholder files
  - MUST route instruction-file writes through selector + selected-author dispatch;
    controller-local patching forbidden unless emergency fallback explicitly selected by user
  - MUST load and follow {cf-studio-path}/.core/skills/studio/protocol.md § Agent-safe invocation
    (--yes/-y/--force forbidden unless user explicitly requested non-interactive behavior)

NOTES: Pre-dispatch fail-stop and Mode B degradation rules in
  {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md


UNIT Phase4AuthorSelectionDispatch
PURPOSE: Two-step canonical write/fix dispatch path for Phase 4 and Phase 5.

DO:
  STEP 1: DISPATCH read-only selector cf-generate-author with full author payload
          loading {cf-studio-path}/.core/skills/studio/agents/cf-generate-author.md as selector contract
  STEP 2: PARSE returned author_selection JSON block
  STEP 3: VERIFY selected_author is exactly one of:
    cf-generate-author-junior | cf-generate-author-middle | cf-generate-author-senior
    | cf-generate-author-lead | cf-generate-coder-casual | cf-generate-coder-smart
    | cf-generate-prompt-engineer-casual | cf-generate-prompt-engineer-smart
  STEP 4:
    KEEP CF_PHASE_GATE = armed while dispatching selector
    SET CF_PHASE_GATE = released_for_dispatch IMMEDIATELY before dispatching selected write-capable author
    LOAD and USE {cf-studio-path}/.core/skills/studio/agents/{selected_author}.md before synthesizing final dispatch prompt
    DISPATCH selected write-capable author with synthesized final prompt and author_selection.dispatch_payload
    RESET CF_PHASE_GATE = armed IMMEDIATELY on return (manifest, escalation, error, or no-response)
  IF INLINE_FALLBACK == true:
    SET CF_PHASE_GATE = released_for_inline_write IMMEDIATELY before inline write block
    RESET CF_PHASE_GATE = armed IMMEDIATELY after inline write block (success AND failure)
  IF selector output missing, malformed, names unregistered author, or changes payload semantics:
    FAIL-STOP
    WAIT user.reply
    STOP_TURN
  IF selector or selected-author contract missing, unreadable, ambiguous, or not reflected in final prompt:
    FAIL per sub-agent-dispatch.md § SubAgentContractReadGate
    FORBID dispatch
  IF instruction_file_targets non-empty AND selected_author not in (cf-generate-prompt-engineer-casual | cf-generate-prompt-engineer-smart):
    REQUIRE author_selection.reasons explicitly records why higher-capability non-prompt-engineer author required
    FORBID orchestrator overriding selector output without that reason
  IF payload from AUTHOR_EXECUTION_PLAN task:
    INCLUDE in selector dispatch: author_plan_task_id, planner_recommended_author,
      planner_parallel_group, planner_dependencies, planner_acceptance_criteria

RULES:
  - MUST NOT be left CF_PHASE_GATE in released_for_dispatch across turns
  - MUST apply sub-agent-dispatch.md § SubAgentContractReadGate before selector dispatch and before selected-author dispatch
  - MUST treat prompt-engineer-* as default author family for instruction-file targets; only selector may justify escalation
  - MUST reset CF_PHASE_GATE = armed immediately after inline write block on both success and failure

NOTES: selector may honor or override planner_recommended_author recommendation; MUST record decision in author_selection.reasons.
  Gate MUST NOT remain at released_for_dispatch across turns.


UNIT Phase4PlannedMultiAuthorDispatch
PURPOSE: Execute AUTHOR_EXECUTION_PLAN when non-null instead of single all-path payload.

DO:
  IF AUTHOR_EXECUTION_PLAN non-null:
    RE-VALIDATE plan before dispatch:
      - every task's recommended_author is registered author worker
      - every Phase 4 target_paths entry covered by at least one task
      - tasks in same parallel_group have disjoint target_paths
      - no parallel group has more than one task with updates_artifacts_toml=true
      - each parallel_groups[].depends_on group completed before its group runs
    FOR each parallel group in dependency order:
      FOR each task in group:
        CONSTRUCT task-scoped mode=create payload:
          - start from Phase4CreatePayload
          - replace target_paths with task's target_paths
          - preserve full approved inputs UNLESS task declares input_keys;
            when input_keys present include only those keys plus global required keys
          - add planner metadata fields for selector/author worker
        EXECUTE § Phase4AuthorSelectionDispatch
      IF INLINE_FALLBACK == false: tasks in same group MAY dispatch in parallel
        Each parallel task owns its own gate-release record:
          task_id, selected_author, released_at, reset_at, completion_status.
        Gate-release record updates and CF_PHASE_GATE transitions MUST be
        synchronized with atomic DB operations or distributed locks
        (row-level transactions, compare-and-set/optimistic locking, or
        short-lived leases) so two orchestrator instances cannot claim the
        same gate window.
        released_at MUST be set by an atomic create-or-update guarded by
        task_id and a lease TTL. Resets MUST update reset_at and
        completion_status only when the lease is held or CAS succeeds.
        CF_PHASE_GATE MUST be treated as released only for that task's dispatch
        window while its lease is valid, and MUST be reset for every task
        independently before the group is considered complete.
      IF INLINE_FALLBACK == true:
        run tasks sequentially in listed order
        EMIT one-line warning that planned parallelism degraded to sequential inline execution
      AFTER group: MERGE manifests (concatenate paths_written, union ids_assigned,
        OR artifacts_toml_updated, concatenate findings_not_fixable if present)
    IF any planned task fails:
      STOP remaining groups
      LEAVE already-written files untouched
      SURFACE failing task id and author
      ROUTE to workflows/generate/error-handling.md
  IF AUTHOR_EXECUTION_PLAN == null:
    BUILD one Phase4CreatePayload covering all target paths
    EXECUTE § Phase4AuthorSelectionDispatch once

NOTES: Read-only selector runs with CF_PHASE_GATE=armed; gate opens only immediately before
  selector-returned write-capable author dispatched; resets immediately after each author return.
  Null states: auto_skipped_no_author_plan_flag | auto_skipped_rules_disabled.


UNIT Phase4CreatePayload
PURPOSE: Define dispatched-prompt inputs for the create payload.

DO:
  SUPPLY to selected author:
    mode = "create"
    kind, name, rules_mode, system (from earlier phases)
    template_path, example_path, kit_rules_path (resolved from rules.md)
    checklist_path (ONLY when STRICT explicitly requires pre-write)
    design_artifact_path (code mode only)
    target_paths = full list of output paths (array by contract)
    inputs = approved inputs from Phase 1 / Phase 3 (collector proposed_inputs JSON
      with user edits merged; keys = template H2 section names normalized; values = approved defaults)
    (OPTIONAL from planned task): author_plan_task_id, planner_task_title,
      planner_recommended_author, planner_parallel_group,
      planner_dependencies, planner_acceptance_criteria
    git_commit_mode = GIT_COMMIT_MODE
    contributing_guide = CONTRIBUTING_GUIDE (null when not found)
    git_constraint = exactly one matching block:
      commit: "You MAY `git add` files you wrote and create one commit at the end.
               Follow the CONTRIBUTING guide (provided) for commit message format.
               MUST NOT `git push`, `git reset`, `git rebase`, `git stash`, `git checkout --`."
      stage:  "You MAY `git add` files you wrote. MUST NOT `git commit`,
               `git push`, `git reset`, `git rebase`, `git stash`, `git checkout --`."
      none:   "MUST NOT run `git commit`, `git push`, `git reset`, `git rebase`,
               `git stash`, `git checkout --`, or `git add`. Leave changes as
               uncommitted, unstaged working-tree edits only."

RULES:
  - git_commit_mode MUST be included
  - contributing_guide MUST be included (null when not found)
  - git_constraint MUST be included verbatim matching current GIT_COMMIT_MODE
  - commit, stage, and none git_constraint values are data. Render them as
    verbatim/code text or escape shell metacharacters before display.
  - MUST NOT interpolate git_constraint values into exec/system/shell calls.
    Any consumer that must pass related behavior to a shell MUST use an
    explicit allow-list or shell-escaping function and reject raw
    git_constraint strings in shell contexts.

NOTES: Selected author updates {cf-studio-path}/config/artifacts.toml when new artifact path
  introduced, creates directories as needed, writes file(s), verifies content; returns Written
  markdown block plus manifest JSON block. MUST persist manifest.paths_written for Phase 5.
  MUST echo Written lines to user verbatim.
  Load {cf-studio-path}/.core/skills/studio/agents/cf-generate-collector.md Output contract for
  proposed_inputs JSON block shape.


UNIT Phase4EscalationHandling
PURPOSE: Handle AUTHOR_ESCALATION_REQUIRED returns from selected author.

DO:
  IF selected author returns AUTHOR_ESCALATION_REQUIRED:
    WRITE nothing from that result
    PARSE recommended_author and reason
    KEEP CF_PHASE_GATE = armed while rerunning selector
    RERUN read-only selector AT MOST ONCE with original payload plus:
      escalation_context = {
        "previous_selected_author": "<first selector-returned author>",
        "recommended_author": "<author-reported recommendation>",
        "author_escalation_reason": "<author-reported reason>"
      }
    DISPATCH ONLY second selector-returned selected_author
    VERIFY it is one of registered write-capable author agents
    VERIFY it differs from first selected author
    VERIFY escalation reason recorded in author_selection.reasons
    SET CF_PHASE_GATE = released_for_dispatch IMMEDIATELY before dispatching
    RESET CF_PHASE_GATE = armed IMMEDIATELY on return
    IF second author also escalates:
      RESET CF_PHASE_GATE = armed BEFORE surfacing error
      FAIL-STOP and surface reason to user
    IF selector returns same author or invalid author:
      RESET CF_PHASE_GATE = armed BEFORE surfacing error
      FAIL-STOP and surface reason to user

RULES:
  - MUST NOT dispatch write-capable author before Phase 3 yes
  - MUST reset CF_PHASE_GATE = armed BEFORE surfacing multi-escalation error;
    gate MUST NOT remain in released_for_dispatch across turns per SKILL.md § Phase-Skip Gate
```
