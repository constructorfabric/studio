---
cf: true
type: reference
name: plan-reference
description: "Invoke when consulting the downstream runtime contract for generated plans (execute-phases, status checks, plan-storage format, execution log)."
purpose: Reference-only documentation for plan execution downstream from /cf-plan
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

When the user requests same-chat native phase execution, re-run
`workflows/shared/inline-fallback-probe.md`, set `CF_PHASE_GATE=released_for_dispatch`
immediately before dispatch, and route to
`{cf-studio-path}/.core/skills/studio/agents/cf-phase-runner.md`
only when the re-probe resolves to `SUB_AGENT_SESSION_APPROVED=true` and
`INLINE_FALLBACK=false`. The dispatch payload MUST carry `plan_dir`,
`target_phase`, `git_commit_mode`, `contributing_guide`, and the mode-matched
`git_constraint` block. Reset `CF_PHASE_GATE=armed` immediately after the
dispatch returns — success, error, or no-response.

### 5.1 Load Phase

1. Read `plan.toml` and use manifest state, not chat memory, as the source of truth.
2. If `plan.execution_status = "briefs_only"`, do not read a phase file yet; instead return to the Phase 3.2 post-brief choice set so the user can compile phases via inline generation, downstream prompts, or `cf-phase-compiler`.
3. If `plan.execution_status = "prompts_emitted"`, do not attempt native phase execution yet because no `phase-*` files are guaranteed to exist. Return to the same Phase 3.2 post-brief choice set, or instruct the operator to use the emitted downstream compilation prompts first.
4. Select the earliest executable phase whose dependencies are all `done`.
5. Audit upstream `output_files`, declared `outputs`, and downstream `inputs`; when `lifecycle = "cleanup"` and `plan.lifecycle_status = "done"`, the intentional cleanup removal of `brief-*`, `phase-*`, and `out/` is exempt.
6. If the audit reopens work, repair lifecycle state before proceeding.
7. Mark the chosen phase `in_progress`, then read only that phase file and follow it exactly.

### 5.2 Execute

Follow the phase Task section exactly.

### 5.3 Save Intermediate Results

Before reporting, verify every file in the phase `outputs` list was created or updated. `out/` remains the data contract between phases.

### 5.4 Report

Produce the completion report in the phase file's Output Format.

### 5.5 Update Status

Set the phase status to `done` only when all acceptance criteria pass; otherwise set it to `failed` with the reason recorded in the manifest.

### 5.6 Phase Handoff

If the phase file already includes a handoff prompt, do not duplicate it. Otherwise emit a single fenced next-phase prompt, then offer same-chat continuation versus new-chat execution. Same-chat continuation MUST re-enter from `plan.toml`, re-audit dependencies, and ignore prior chat memory.

If the last phase completes:
- report all phases complete and set `plan.execution_status = "done"`
- run the lifecycle action exactly once according to `gitignore`, `cleanup`, `archive`, or `manual`
- if lifecycle is `manual`, present exactly one keep/archive/delete prompt
- optionally offer deterministic validation or semantic review only when validator applicability is proven for the completed target

### 5.7 Abandoned Plan Recovery

If a plan is abandoned or same-chat continuation loses state: `plan.toml` is the checkpoint, but recovery MUST audit completed work before resuming.

1. Read `plan.toml`.
2. Audit every phase marked `done` in dependency order against its declared `output_files`, its declared `outputs`, and any intermediate artifacts required by downstream `inputs`, except that when `lifecycle = "cleanup"` and `plan.lifecycle_status = "done"`, the intentional Cleanup removals of `brief-*`, `phase-*`, and `out/` are exempt and MUST NOT count as inconsistency.
3. If a completed phase is inconsistent, reopen it by downgrading `status` from `done` to `pending` or `failed` as appropriate, and also downgrade every downstream dependent phase to `pending`.
4. If any phase was reopened, repair lifecycle state before resuming: keep `plan.lifecycle_status = "done"` only for `gitignore`; otherwise set `plan.lifecycle_status = "pending"` and cancel any stale `manual_action_required`, `ready`, or `in_progress` lifecycle state from the prior completion attempt. For `cleanup` strategy with `plan.lifecycle_status = 'in_progress'`, do NOT reset to `pending` (re-execution would attempt to delete already-deleted files and produce spurious errors). Instead set `plan.lifecycle_status = 'partial'` and surface the residual file list to the user.
5. Recompute `plan.execution_status` from the downgraded manifest.
6. Resume from the earliest executable phase after the audit — not merely the first phase that was previously `pending`.

Recovery prompt:
```text
I have an incomplete Constructor Studio execution plan at:
  {cf-studio-path}/.plans/{task-slug}/plan.toml
Please read the plan manifest, audit completed phases against their declared `output_files`, declared `outputs`, and downstream `inputs`, repair stale lifecycle state if work is reopened, and resume from the earliest executable phase.
```

## Appendix B: Check Status (Reference Only)

This appendix defines status reporting after plan creation.

When the user asks for plan status, read `plan.toml` and report the task, type, target, execution status, lifecycle status, active location, and per-phase progress from the manifest. If `lifecycle_status = manual_action_required`, direct the operator back to the execution flow that presents the single lifecycle choice instead of duplicating that menu in a status-only response. If lifecycle handling failed or any phase failed, suggest retry, reopen, or manual recovery.

## Plan Storage Format

All plan data lives in `{cf-studio-path}/.plans/{task-slug}/`:
```text
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
```

Compute `plan.target_key` first for deterministic naming, but use it for plan-directory reuse only together with the current raw-input identity. Directory naming stays human-readable; equality/reuse checks compare `type + plan.target_key + plan.input_signature` whenever raw-input packaging is in scope.

Naming conventions:
- generate: `{type}-{artifact_kind}-{artifact_slug}`. Use the explicit artifact name when available; otherwise use the output path stem.
- analyze: `{type}-{artifact_kind}-{artifact_slug}` for artifact-oriented reviews, or `{type}-path-{target_path_slug}` when the primary target is a file or directory path. For path targets, if the absolute target path is under `{project_root}`, strip `{project_root}/` first and normalize that relative path (`{project_root}/src/api/users.py` → `analyze-path-src-api-users-py`); otherwise normalize the absolute-path segments.
- implement: `{type}-feature-{feature_slug}`. Derive `{feature_slug}` from the FEATURE ID first; if no ID exists, use the FEATURE title; if neither exists, use the FEATURE file stem.
- normalization: lowercase, replace path separators / spaces / punctuation with `-`, collapse repeated `-`, trim leading/trailing `-`.
- collision handling: if an existing non-archived plan has the same `type`, the same `plan.target_key`, and the same `plan.input_signature` (or both plans have no raw-input package), reuse its directory; otherwise append `-2`, `-3`, ... using the lowest available suffix.
- phase file: `phase-{NN}-{slug}.md`
- plan manifest: always `plan.toml`

Lifecycle behavior is controlled by the strategy selected in Phase 2.1 and recorded in `plan.toml`; if archived, `active_plan_dir` points to the archive path, and if cleaned up, `plan.toml` remains as the terminal receipt even after compiled plan artifacts are removed.

## Execution Log

Keep a brief **plan-generation-only** observable log in chat, not on disk. Runtime execution/status examples belong to Appendix A and Appendix B only.
```text
[plan] Assessing scope: generate PRD for myapp
[plan] Estimated size: ~1200 lines → plan needed
[plan] Strategy: generate (by template sections)
[plan] Decomposition: 4 phases
[plan] Compiling phase 1/4: Overview and Actors
[plan] Phase 1 compiled: 380 lines (within budget)
[plan] ...
[plan] Plan written: .plans/generate-prd-myapp/ (4 phases)
...
```
