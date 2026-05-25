---
cf: true
type: workflow
name: cf-analyze
description: Invoke when the user asks to analyze, validate, review, inspect, audit, check, or compare any artifact, code, or instruction document — read-only, tool invocations are validate-only.
version: 1.0
purpose: Universal workflow for analysing any Constructor Studio artifact or code
---

# Analyze

<!-- toc -->

- [Preamble](#preamble)
- [Rules Mode Behavior](#rules-mode-behavior)
- [Rules](#rules)
- [Overview](#overview)
- [Context Budget & Overflow Prevention (CRITICAL)](#context-budget--overflow-prevention-critical)
- [Phase 0: Ensure Dependencies](#phase-0-ensure-dependencies)
- [Phase 0.5: Clarify Analysis Scope](#phase-05-clarify-analysis-scope)
- [Phase 1: File Existence Check](#phase-1-file-existence-check)
- [Phase 2: Deterministic Gate](#phase-2-deterministic-gate)
- [Phase 2.5: Reviewer Plan](#phase-25-reviewer-plan)
- [Phase 3: Semantic Review (Conditional)](#phase-3-semantic-review-conditional)
- [Phase 3 → Phase 4 Checkpoint](#phase-3--phase-4-checkpoint)
- [Phase 4: Output](#phase-4-output)
- [Phase 5: Offer Next Steps](#phase-5-offer-next-steps)
- [Terminal Block Invariant](#terminal-block-invariant)
- [State Summary](#state-summary)
- [Key Principles](#key-principles)
- [Agent Self-Test (STRICT mode — AFTER completing work)](#agent-self-test-strict-mode--after-completing-work)
- [Validation Criteria](#validation-criteria)

<!-- /toc -->

## Preamble
Open, load, and follow `workflows/analyze/preamble.md` FIRST — it is an instruction file, not a reference. It performs route-only methodology selection plus storytelling trigger handling; code, bug-finding, consistency, and prompt methodologies are loaded only inside matched Phase 3 sub-agents.

## Rules Mode Behavior
ALWAYS open, load, and follow `workflows/shared/mode-resolution.md` for the canonical STRICT/RELAXED behavioral block.
ALWAYS open, load, and follow `workflows/shared/stop-token-policy.md` for the canonical stop-token policy.

## Rules
ALWAYS open, load, and follow `workflows/analyze/rules.md` — the completion contract and pre-output self-check are mandatory; this file is unconditionally required.

## Overview
ALWAYS open, load, and follow `workflows/analyze/overview.md` — mode resolution, command surface, prompt-review trigger semantics, and the actionable-findings → Remediation Handoff contract MUST be known before any phase executes.

## Context Budget & Overflow Prevention (CRITICAL)
Open, load, and follow `workflows/analyze/context-budget.md` WHEN Phase 0 is about to load large documents OR when the estimated total context would exceed 1200 lines.

## Phase 0: Ensure Dependencies
Open, load, and follow `workflows/analyze/phase-0-dependencies.md` for Phase 0 + Phase 0.5 dependency resolution and the Mode Detection matrix.

## Phase 0.5: Clarify Analysis Scope
`workflows/analyze/phase-0.5-scope.md` is the canonical scope-clarification file. It is loaded conditionally by `workflows/analyze/phase-0-dependencies.md` (after the plan-escalation gate resolves, when scope, traceability, registry consistency, cross-refs, or consistency paths are unclear); do not load independently from the router.

## Phase 1: File Existence Check
Open, load, and follow `workflows/analyze/phase-1-file-check.md` for the existence-check rule across `{PATHS}`.

## Phase 2: Deterministic Gate
Open, load, and follow `workflows/analyze/phase-2-det-gate.md` for the deterministic-validator dispatch and gate behavior. Skipped when `SEMANTIC_ONLY=true` (sub-file enforces; router proceeds directly to Phase 3 semantic review).

## Phase 2.5: Reviewer Plan
Open, load, and follow `workflows/analyze/phase-2.5-reviewer-plan.md` for the mandatory reviewer-decomposition step that runs when `SUB_AGENT_SESSION_APPROVED=true` AND `INLINE_FALLBACK=false`. The sub-file enforces its own auto-skip conditions (`INLINE_FALLBACK=true`, `EXPLAIN_MODE=true`, no active methodology flag). It produces `REVIEWER_EXECUTION_PLAN`, which Phase 3 consumes for parallel methodology × path-partition dispatch.

## Phase 3: Semantic Review (Conditional)
Open, load, and follow `workflows/analyze/phase-3-semantic.md` for the reviewer dispatch matrix, namespaced finding IDs, rules-mode behavior, and the EXPLAIN_MODE boundary.

## Phase 3 → Phase 4 Checkpoint
Open, load, and follow `workflows/analyze/phase-3-to-4-checkpoint.md` for the context-budget recovery checkpoint between semantic review and output.

## Phase 4: Output
Open, load, and follow `workflows/analyze/phase-4-output/index.md` WHEN semantic review (or deterministic-gate FAIL) is ready to emit output; the dispatcher selects the schema sub-file by mode and routes the `Remediation Handoff` menu when actionable findings exist.

## Phase 5: Offer Next Steps
Open, load, and follow `workflows/analyze/phase-5-next-steps.md` WHEN overall result is PASS and EXPLAIN_MODE=false.

## Terminal Block Invariant
The analyze response MUST NOT end without one of: the `Remediation Handoff` menu (when actionable findings exist or deterministic gate FAIL) or the Phase 5 `next-steps` menu (PASS path, `EXPLAIN_MODE=false`). If neither `workflows/analyze/phase-4-output/index.md` nor `workflows/analyze/phase-5-next-steps.md` is loadable, STOP and surface the missing file before emitting any final response.

## State Summary
Open, load, and follow `workflows/analyze/state-summary.md` for the target-type × template / checklist / design matrix.

## Key Principles
Open, load, and follow `workflows/analyze/key-principles.md` WHEN finalizing the response.

## Agent Self-Test (STRICT mode — AFTER completing work)
Open, load, and follow `workflows/analyze/agent-self-test.md` WHEN STRICT mode finalization must answer the canonical self-test questions (also referenced from Standard Analysis Output section 4).

## Validation Criteria
Open, load, and follow `workflows/analyze/validation-criteria.md` WHEN the post-flight checklist must be verified before ending the response.
