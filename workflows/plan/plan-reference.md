---
cf: true
type: reference
name: plan-reference
description: "Invoke when consulting the downstream runtime contract for generated plans (execute-phases, status checks, plan-storage format, execution log)."
purpose: Reference-only documentation for plan execution downstream from cf-plan
loaded_by: workflows/plan.md
version: 1.0
---

# Plan Reference

<!-- toc -->

- [Appendix A: Execute Phases (Reference Only)](#appendix-a-execute-phases-reference-only)
  - [5.1 Load Phase](#51-load-phase)
  - [5.2 Execute](#52-execute)
  - [5.3 Save Intermediate Results](#53-save-intermediate-results)
  - [5.4 Report](#54-report)
  - [5.5 Update Status](#55-update-status)
  - [5.6 Phase Handoff](#56-phase-handoff)
  - [5.7 Abandoned Plan Recovery](#57-abandoned-plan-recovery)
- [Appendix B: Check Status (Reference Only)](#appendix-b-check-status-reference-only)
- [Plan Storage Format](#plan-storage-format)
- [Execution Log](#execution-log)

<!-- /toc -->

## Appendix A: Execute Phases (Reference Only)

This appendix is the downstream runtime contract for generated plans. It is not a plan-creation phase.

```pdsl
UNIT PlanExecutePhaseDispatch

PURPOSE:
  Gate same-chat native phase execution with a fresh inline-fallback re-probe.

WHEN:
  - REQUIRE User requests same-chat native phase execution

DO:
  - RUN OPEN {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md
  - RUN RE-RUN inline-fallback-probe.md

  - REQUIRE SUB_AGENT_SESSION_APPROVED == true AND INLINE_FALLBACK == false:
    - SET CF_PHASE_GATE = released_for_dispatch
    - DISPATCH {cf-studio-path}/.core/skills/studio/agents/cf-phase-runner.md
      with payload:
        plan_dir = {plan_dir}
        target_phase = {target_phase}
        git_commit_mode = GIT_COMMIT_MODE
        contributing_guide = CONTRIBUTING_GUIDE
        git_constraint = mode-matched block from workflows/generate/phase-4-write.md § Git constraint blocks
    - SET CF_PHASE_GATE = armed  (immediately after dispatch returns — success, error, or no-response)

RULES:
  - ALWAYS set CF_PHASE_GATE = released_for_dispatch immediately before dispatch
  - ALWAYS reset CF_PHASE_GATE = armed immediately after dispatch returns
  - ALWAYS Payload ALWAYS carry plan_dir, target_phase, git_commit_mode, contributing_guide, and git_constraint
```

### 5.1 Load Phase

```pdsl
UNIT PlanLoadPhase

PURPOSE:
  Select the correct phase to execute using plan.toml as source of truth, not chat memory.

DO:
  - RUN READ plan.toml
  - RUN USE manifest state (not chat memory) as source of truth

  - REQUIRE plan.execution_status == "briefs_only":
    DO NOT read a phase file yet
    - RETURN to Phase 3.2 post-brief choice set (inline / downstream prompts / cf-phase-compiler)

  - REQUIRE plan.execution_status == "prompts_emitted":
    DO NOT attempt native phase execution (no phase-* files guaranteed to exist)
    - RETURN to Phase 3.2 post-brief choice set OR instruct operator to use emitted downstream prompts first

  - RUN SELECT earliest executable phase whose dependencies are all done

  - RUN AUDIT upstream output_files, declared outputs, and downstream inputs
    EXCEPTION: when lifecycle = "cleanup" AND plan.lifecycle_status = "done",
               intentional Cleanup removals of brief-*, phase-*, and out/ are EXEMPT

  - REQUIRE audit reopens work:
    REPAIR lifecycle state before proceeding

  - RUN MARK chosen phase in_progress
  - RUN READ only that phase file
  - RUN FOLLOW phase file exactly
```

### 5.2 Execute

```pdsl
UNIT PlanExecute

PURPOSE:
  Execute the phase task exactly as specified.

DO:
  - RUN FOLLOW the phase Task section exactly
```

### 5.3 Save Intermediate Results

```pdsl
UNIT PlanSaveIntermediateResults

PURPOSE:
  Verify all intermediate artifacts are written before reporting.

DO:
  - RUN BEFORE reporting:
    VERIFY every file in the phase outputs list was created or updated

NOTES:
  out/ remains the data contract between phases.
```

### 5.4 Report

```pdsl
UNIT PlanReport

PURPOSE:
  Emit completion report in the phase file's Output Format.

DO:
  - RUN PRODUCE completion report in the phase file's Output Format
```

### 5.5 Update Status

```pdsl
UNIT PlanUpdateStatus

PURPOSE:
  Set phase status in plan.toml based on acceptance criteria.

DO:
  - REQUIRE all acceptance criteria pass:
    - SET phase.status = "done"
  - RUN otherwise
    - SET phase.status = "failed"
    RECORD reason in manifest
```

### 5.6 Phase Handoff

```pdsl
UNIT PlanPhaseHandoff

PURPOSE:
  Transition to the next phase or complete the plan.

DO:
  - REQUIRE phase file already includes a handoff prompt:
    DO NOT duplicate it
  - RUN otherwise
    - EMIT single fenced next-phase prompt
    OFFER same-chat continuation versus new-chat execution

  - REQUIRE same-chat continuation chosen:
    RE-ENTER from plan.toml
    RE-AUDIT dependencies
    IGNORE prior chat memory

  - REQUIRE last phase completes:
    REPORT all phases complete
    - SET plan.execution_status = "done"
    - RUN lifecycle action exactly once per strategy:
      gitignore -> per PlanLifecycleGitignore
      cleanup   -> per PlanLifecycleCleanup
      archive   -> per PlanLifecycleArchive
      manual    -> present exactly one keep/archive/delete prompt
    OPTIONALLY offer deterministic validation or semantic review
      only when validator applicability is proven for the completed target
```

### 5.7 Abandoned Plan Recovery

```pdsl
UNIT PlanAbandonedRecovery

PURPOSE:
  Recover from abandoned or context-lost plan runs using plan.toml as checkpoint.

DO:
  - RUN READ plan.toml
  - RUN AUDIT every phase marked done in dependency order against:
       - declared output_files
       - declared outputs
       - intermediate artifacts required by downstream inputs
     EXCEPTION: when lifecycle = "cleanup" AND plan.lifecycle_status = "done",
                intentional Cleanup removals of brief-*, phase-*, and out/ are EXEMPT
                and NEVER count as inconsistency
  - REQUIRE a completed phase is inconsistent:
       DOWNGRADE phase.status from done to pending or failed as appropriate
       DOWNGRADE every downstream dependent phase to pending
  - REQUIRE any phase was reopened:
       REPAIR lifecycle state:
         gitignore:            KEEP plan.lifecycle_status = "done"
         cleanup (in_progress): DO NOT reset to pending
                                - SET plan.lifecycle_status = "partial"
                                SURFACE residual file list to user
         otherwise:            SET plan.lifecycle_status = "pending"
                                CANCEL stale manual_action_required | ready | in_progress
  - RUN RECOMPUTE plan.execution_status from the downgraded manifest
  - RUN RESUME from the earliest executable phase after the audit
     (not merely the first phase that was previously pending)

- EMIT recovery prompt:
  - RUN I have an incomplete Constructor Studio execution plan at:
    {cf-studio-path}/.plans/{task-slug}/plan.toml
  - RUN Please read the plan manifest, audit completed phases against their declared
  - RUN `output_files`, declared `outputs`, and downstream `inputs`, repair stale
  - RUN lifecycle state if work is reopened, and resume from the earliest executable phase.
```

## Appendix B: Check Status (Reference Only)

```pdsl
UNIT PlanCheckStatus

PURPOSE:
  Report plan status when the user asks.

DO:
  - RUN READ plan.toml
  - RUN REPORT: task, type, target, execution_status, lifecycle_status,
          active_plan_dir, per-phase progress

  - REQUIRE lifecycle_status == "manual_action_required":
    DIRECT operator back to the execution flow that presents the single lifecycle choice
    - NEVER duplicating that menu in a status-only response

  - REQUIRE lifecycle handling failed OR any phase failed:
    SUGGEST retry, reopen, or manual recovery
```

## Plan Storage Format

```pdsl
NOTES:
  All plan data lives in {cf-studio-path}/.plans/{task-slug}/:

    .plans/
      generate-prd-myapp/
        plan.toml
        input/
          manifest.json
          direct-prompt.md
          001-01-request-part-01.md
        brief-01-overview.md
        brief-02-requirements.md
        phase-01-overview.md
        phase-02-requirements.md
        out/
          phase-01-actors.md
          phase-01-id-scheme.md
          phase-02-req-ids.md

  Compute plan.target_key first for deterministic naming, but use it for plan-directory
  reuse only together with the current raw-input identity. Equality/reuse checks compare
  type + plan.target_key + plan.input_signature whenever raw-input packaging is in scope.

  Naming conventions:
    generate:  {type}-{artifact_kind}-{artifact_slug}
               use explicit artifact name when available; otherwise use output path stem
    analyze:   {type}-{artifact_kind}-{artifact_slug} for artifact-oriented reviews
               {type}-path-{target_path_slug} for file/directory path targets
               (strip {project_root}/ first if under project_root, then normalize)
    implement: {type}-feature-{feature_slug}
               derive feature_slug from FEATURE ID first, then FEATURE title, then file stem
    normalization: lowercase; replace path separators / spaces / punctuation with -;
                   collapse repeated -; trim leading/trailing -
    collision:  if existing non-archived plan has same type + plan.target_key + plan.input_signature
                (or both plans have no raw-input package): REUSE its directory
                otherwise: append -2, -3, ... using lowest available suffix
    phase file: phase-{NN}-{slug}.md
    manifest:   always plan.toml

  Lifecycle behavior controlled by strategy in plan.toml; if archived, active_plan_dir
  points to archive path; if cleaned up, plan.toml remains as terminal receipt.
```

## Execution Log

```pdsl
NOTES:
  Keep a brief plan-generation-only observable log in chat (not on disk).
  Runtime execution/status examples belong to Appendix A and Appendix B only.

  Example format:
    [plan] Assessing scope: generate PRD for myapp
    [plan] Estimated size: ~1200 lines → plan needed
    [plan] Strategy: generate (by template sections)
    [plan] Decomposition: 4 phases
    [plan] Compiling phase 1/4: Overview and Actors
    [plan] Phase 1 compiled: 380 lines (within budget)
    [plan] ...
    [plan] Plan written: .plans/generate-prd-myapp/ (4 phases)
```
