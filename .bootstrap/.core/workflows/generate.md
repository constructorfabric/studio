---
cf: true
type: workflow
name: cf-generate
description: Invoke when the user asks to create, update, edit, fix, implement, refactor, add, set up, configure, or build any artifact or code — universal create-or-modify workflow.
version: 1.0
purpose: Universal workflow for creating or updating any artifact or code
---

# Generate

<!-- toc -->

- [Reverse Engineering Prerequisite (BROWNFIELD only)](#reverse-engineering-prerequisite-brownfield-only)
- [Overview](#overview)
- [Context Budget & Overflow Prevention (CRITICAL)](#context-budget--overflow-prevention-critical)
- [Agent Anti-Patterns (STRICT mode)](#agent-anti-patterns-strict-mode)
- [Rules Mode Behavior](#rules-mode-behavior)
- [Phase 0: Ensure Dependencies](#phase-0-ensure-dependencies)
- [Phase 0.1: Plan Escalation Gate](#phase-01-plan-escalation-gate)
- [Phase 0.2: Review-Loop Configuration](#phase-02-review-loop-configuration)
- [Phase 0.x: GIT_COMMIT_MODE Probe](#phase-0x-git_commit_mode-probe)
- [Phase 0.5: Clarify Output & Context](#phase-05-clarify-output--context)
- [Phase 0.7: Brainstorm](#phase-07-brainstorm)
- [Phase 1: Collect Information](#phase-1-collect-information)
- [Phase 1.5: Author Plan](#phase-15-author-plan)
- [Phase 2 / Phase 2.5](#phase-2--phase-25)
- [Phase 3: Summary](#phase-3-summary)
- [Phase 4: Write](#phase-4-write)
- [Phase 5: Review Loop](#phase-5-review-loop)
- [Phase 6: Offer Next Steps](#phase-6-offer-next-steps)
- [Error Handling](#error-handling)
- [State Summary & Validation Criteria](#state-summary--validation-criteria)
- [Agent Self-Test (STRICT mode — AFTER completing work)](#agent-self-test-strict-mode--after-completing-work)

<!-- /toc -->

## Reverse Engineering Prerequisite (BROWNFIELD only)

Open, load, and follow `workflows/generate/reverse-engineering.md` WHEN the project is BROWNFIELD and the auto-config / storytelling-package gates must be evaluated before Phase 0.

## Overview

Artifact generation mode = template + example by default; load checklist up front only when the current rules explicitly require it before writing. Code generation mode = design/spec context first; load checklist during validation/review unless the current rules explicitly require it during implementation. Config mode = create/update config files. After `skills/studio/protocol.md`, you have `TARGET_TYPE`, `RULES`, `KIND`, `PATH`, `MODE`, and resolved phase-appropriate dependencies. Key variables: `{cf-studio-path}/config/`, `{ARTIFACTS_REGISTRY}`, `{KITS_PATH}`, `{PATH}`. Use `{KITS_PATH}/artifacts/{KIND}/examples/` for style and quality guidance.

## Context Budget & Overflow Prevention (CRITICAL)

- Budget first: estimate size before loading large docs (for example with `wc -l`) and state the budget for this turn.
- Load only what you need: prefer only the generation-phase sections required for the current `KIND`; defer checklist loading to validation/review unless the current rules explicitly require it earlier.
- Chunk reads and summarize-and-drop: use `read_file` ranges, summarize each chunk, and keep only extracted criteria.
- Fail-safe: if required steps cannot fit in context, stop and output a checkpoint in chat only; do not proceed to writing files.
- Plan escalation: [Phase 0.1](#phase-01-plan-escalation-gate) is mandatory after dependencies load. When `SUB_AGENT_SESSION_APPROVED=true` AND `INLINE_FALLBACK=false`, the gate logs the estimate and proceeds without proposing `/cf-plan`; decomposition is handled in-workflow by Phase 1.5 (author plan, mandatory in that branch). Otherwise the legacy size-based escalation menu fires when budget is exceeded.

## Agent Anti-Patterns (STRICT mode)

**Reference**: `{cf-studio-path}/.core/requirements/agent-compliance.md` for the full list.

Critical failures: `SKIP_TEMPLATE`, `SKIP_EXAMPLE`, `SKIP_CHECKLIST`, `PLACEHOLDER_SHIP`, `NO_CONFIRMATION`, `SIMULATED_VALIDATION`.

Self-check before writing files (MANDATORY in STRICT mode): template loaded, example referenced, no placeholders, and explicit `yes` received. Checklist self-review is required here only when the current rules explicitly require checklist use before writing; otherwise defer checklist review to Phase 5. If any required answer fails → STOP and fix before proceeding. STRICT mode MUST include self-check results in Phase 3 Summary output.

## Rules Mode Behavior

Open, load, and follow `workflows/shared/mode-resolution.md` for the canonical block. Open, load, and follow `workflows/shared/stop-token-policy.md` for the canonical Stop-Token Policy.

## Phase 0: Ensure Dependencies

Open, load, and follow `workflows/generate/phase-0-dependencies.md` WHEN the workflow enters dependency resolution after `skills/studio/protocol.md`. (That file delegates the `INLINE_FALLBACK` probe to `workflows/shared/inline-fallback-probe.md`, the canonical block reused by `analyze.md`.)

## Phase 0.1: Plan Escalation Gate

Open, load, and follow `workflows/shared/plan-escalation-gate.md` for the canonical block.

## Phase 0.2: Review-Loop Configuration

Open, load, and follow `workflows/generate/phase-0.2-review-loop-cfg.md` for `COLLECTOR_MAX_ITER`; the `MAX_ITER` prompt + parser live in `workflows/generate/phase-5/index.md` § Pre-Phase-Setup (also the analyze.md external-entry point).

## Phase 0.x: GIT_COMMIT_MODE Probe

Open, load, and follow `workflows/generate/phase-0-git-commit-mode.md` WHEN `GIT_COMMIT_MODE` is unset and before Phase 0.5. Skip if `GIT_COMMIT_MODE` is already set from an earlier run in this chat session.

## Phase 0.5: Clarify Output & Context

Open, load, and follow `workflows/generate/phase-0.5-clarify.md` WHEN system context or output destination is unclear before Phase 0.7 / Phase 1.

## Phase 0.7: Brainstorm

Open, load, and follow `workflows/generate/phase-0.7/index.md` WHEN Phase 0.5 is complete, `--no-brainstorm` was not passed, and the active KIND's `rules.md` does not set `brainstorm = "disabled"`.

## Phase 1: Collect Information

Open, load, and follow `workflows/generate/phase-1-collect.md` WHEN dependency resolution and Phase 0.5 / 0.7 are complete and the collector must gather Inputs for Phase 4.

## Phase 1.5: Author Plan

Open, load, and follow `workflows/generate/phase-1.5-author-plan.md` WHEN Phase 1 inputs are approved and before Phase 3 summary. The author plan itself is optional for the user, but the offer gate is mandatory unless an explicit auto-skip condition in that file applies.

## Phase 2 / Phase 2.5

Open, load, and follow `workflows/generate/phase-2-checkpoint.md` WHEN the orchestrator passes through the Phase 2 no-op or must emit a Phase 2.5 checkpoint for a long-running generation.

## Phase 3: Summary

Open, load, and follow `workflows/generate/phase-3-summary.md` WHEN Phase 1 inputs are approved, Phase 1.5 has set `AUTHOR_PLAN_OFFER_RESOLVED`, and the user must confirm `yes`/`no`/`modify` before any files are written.

## Phase 4: Write

Open, load, and follow `workflows/generate/phase-4-write.md` WHEN Phase 3 returned `yes` and the author must be dispatched (`mode=create`) to write files atomically.

## Phase 5: Review Loop

Open, load, and follow `workflows/generate/phase-5/index.md` WHEN Phase 4 has written files (or `analyze.md` Remediation Handoff option 1 routes external entry into Phase 5.3) and the bounded review loop must run.

## Phase 6: Offer Next Steps

Open, load, and follow `workflows/generate/phase-6/index.md` WHEN Phase 5 exits and the next-steps + handoff menus must be assembled (Remediation Handoff conditional on non-empty `remaining_findings`; Post-Write Review Handoff mandatory when files were written).

## Error Handling

Open, load, and follow `workflows/generate/error-handling.md` WHEN a tool/dispatch failure, user abandonment, or validation-failure loop (3+ failed iterations) occurs during any generate phase.

## State Summary & Validation Criteria

| State | TARGET_TYPE | Has Template | Has Checklist | Has Example |
|-------|-------------|--------------|---------------|-------------|
| Generating artifact | artifact | ✓ | phase-dependent | ✓ |
| Generating code | code | ✗ | phase-dependent | ✗ |

Open, load, and follow `workflows/generate/validation-criteria.md` WHEN the post-flight checklist must be verified before ending the response.

## Agent Self-Test (STRICT mode — AFTER completing work)

Open, load, and follow `workflows/generate/validation-criteria.md` § Agent Self-Test (STRICT mode — AFTER completing work) WHEN STRICT mode finalization must answer the canonical self-test questions before ending the response.
