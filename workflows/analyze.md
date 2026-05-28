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

```text
UNIT AnalyzePreamble

PURPOSE:
  Load preamble before any other analyze phase work.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/preamble.md is loaded and followed FIRST
```

NOTES: preamble.md performs route-only methodology selection plus storytelling
trigger handling; code, bug-finding, consistency, and prompt methodologies are
loaded only inside matched Phase 3 sub-agents.

## Rules Mode Behavior

```text
UNIT AnalyzeRulesMode

PURPOSE:
  Load canonical STRICT/RELAXED and stop-token behavior before any phase.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/shared/mode-resolution.md is loaded and followed
  REQUIRE {cf-studio-path}/.core/workflows/shared/stop-token-policy.md is loaded and followed
```

```text
UNIT AnalyzeSharedContextPack

PURPOSE:
  Keep analyze-phase prompt loading controller-owned and pack-aware.

RULES:
  - Workflow fragments referenced by analyze are controller-owned prompt assets
    loaded from {cf-studio-path}/.core/workflows/...
  - Before any reviewer dispatch, the controller MUST reuse or extend
    SHARED_CONTEXT_PACK and derive prompt_context_view that satisfies the
    dispatched agent's prompt_context_requirements
  - Analyze MUST NOT rely on prompt-consuming sub-agents reopening workflow,
    requirement, spec, or AGENTS prompt files directly
```

## Rules

```text
UNIT AnalyzeRules

PURPOSE:
  Load completion contract and pre-output self-check.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/rules.md is loaded and followed

RULES:
  - MUST load {cf-studio-path}/.core/workflows/analyze/rules.md — unconditionally required
```

## Overview

```text
UNIT AnalyzeOverview

PURPOSE:
  Load mode resolution, command surface, prompt-review trigger semantics,
  and actionable-findings contract before any phase executes.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/overview.md is loaded and followed

RULES:
  - MUST load {cf-studio-path}/.core/workflows/analyze/overview.md before any phase executes
```

## Context Budget & Overflow Prevention (CRITICAL)

```text
UNIT AnalyzeContextBudget

PURPOSE:
  Enforce context budget before loading large documents.

WHEN:
  Phase 0 is about to load large documents
  OR estimated total context > 1200 lines

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/context-budget.md is loaded and followed
```

## Phase 0: Ensure Dependencies

```text
UNIT AnalyzePhase0

PURPOSE:
  Resolve dependencies and run Mode Detection matrix.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/phase-0-dependencies.md is loaded and followed
```

NOTES: Phase 0 + Phase 0.5 dependency resolution and the Mode Detection matrix
are fully defined in
{cf-studio-path}/.core/workflows/analyze/phase-0-dependencies.md.

## Phase 0.5: Clarify Analysis Scope

```text
UNIT AnalyzePhase05

PURPOSE:
  Clarify scope when required by Phase 0 dependency resolution.

WHEN:
  phase-0-dependencies.md routes scope clarification

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/phase-0.5-scope.md is loaded and followed

RULES:
  - MUST NOT load {cf-studio-path}/.core/workflows/analyze/phase-0.5-scope.md independently from the router
  - MUST load it only when phase-0-dependencies.md triggers it (after plan-escalation
    gate resolves, when scope/traceability/registry-consistency/cross-refs paths are unclear)
```

## Phase 1: File Existence Check

```text
UNIT AnalyzePhase1

PURPOSE:
  Run existence check across {PATHS}.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/phase-1-file-check.md is loaded and followed
```

## Phase 2: Deterministic Gate

```text
UNIT AnalyzePhase2

PURPOSE:
  Dispatch deterministic validators and enforce gate behavior.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/phase-2-det-gate.md is loaded and followed

RULES:
  - MUST skip Phase 2 when SEMANTIC_ONLY=true (sub-file enforces; router proceeds to Phase 3)
```

## Phase 2.5: Reviewer Plan

```text
UNIT AnalyzePhase25

PURPOSE:
  Produce REVIEWER_EXECUTION_PLAN for parallel dispatch in Phase 3.

WHEN:
  SUB_AGENT_SESSION_APPROVED == true
  AND INLINE_FALLBACK == false

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/phase-2.5-reviewer-plan.md is loaded and followed

RULES:
  - MUST auto-skip when INLINE_FALLBACK=true, EXPLAIN_MODE=true, or no active methodology flag
    (sub-file enforces its own auto-skip conditions)

NOTES:
  SUB_AGENT_SESSION_APPROVED and INLINE_FALLBACK are declared in {cf-studio-path}/.core/skills/studio/SKILL.md § Session Sub-Agent Approval Gate.
```

## Phase 3: Semantic Review (Conditional)

```text
UNIT AnalyzePhase3

PURPOSE:
  Run reviewer dispatch matrix, namespaced finding IDs, rules-mode behavior,
  and EXPLAIN_MODE boundary.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/phase-3-semantic.md is loaded and followed
```

## Phase 3 → Phase 4 Checkpoint

```text
UNIT AnalyzePhase3to4

PURPOSE:
  Run context-budget recovery checkpoint between semantic review and output.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/phase-3-to-4-checkpoint.md is loaded and followed
```

## Phase 4: Output

```text
UNIT AnalyzePhase4

PURPOSE:
  Emit output when semantic review or deterministic-gate FAIL is ready.

WHEN:
  semantic review is complete
  OR deterministic gate returned FAIL

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/phase-4-output/index.md is loaded and followed

NOTES:
  Dispatcher selects schema sub-file by mode and routes Remediation Handoff
  menu when actionable findings exist.
```

## Phase 5: Offer Next Steps

```text
UNIT AnalyzePhase5

PURPOSE:
  Offer next steps when overall result is PASS and not in EXPLAIN mode.

WHEN:
  overall result == PASS
  AND EXPLAIN_MODE == false

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/phase-5-next-steps.md is loaded and followed
```

## Terminal Block Invariant

```text
UNIT AnalyzeTerminal

PURPOSE:
  Enforce that every analyze response ends with the correct terminal block.

INVARIANTS:
  - MUST NOT end response without one of:
      Remediation Handoff menu (when actionable findings exist or deterministic gate FAIL)
      Phase 5 next-steps menu (PASS path, EXPLAIN_MODE=false)
  - IF {cf-studio-path}/.core/workflows/analyze/phase-4-output/index.md OR {cf-studio-path}/.core/workflows/analyze/phase-5-next-steps.md
    is not loadable:
      STOP and surface the missing file before emitting any final response
```

## State Summary

```text
UNIT AnalyzeStateSummary

PURPOSE:
  Load target-type × template / checklist / design matrix.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/state-summary.md is loaded and followed
```

## Key Principles

```text
UNIT AnalyzeKeyPrinciples

PURPOSE:
  Load key principles when finalizing the response.

WHEN:
  finalizing the response

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/key-principles.md is loaded and followed
```

## Agent Self-Test (STRICT mode — AFTER completing work)

```text
UNIT AnalyzeSelfTest

PURPOSE:
  Answer canonical self-test questions in STRICT mode after completing work.

WHEN:
  STRICT mode finalization requires self-test

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/agent-self-test.md is loaded and followed
```

NOTES: Also referenced from Standard Analysis Output section 4.

## Validation Criteria

```text
UNIT AnalyzeValidation

PURPOSE:
  Verify post-flight checklist before ending the response.

WHEN:
  post-flight checklist must be verified before ending the response

DO:
  REQUIRE {cf-studio-path}/.core/workflows/analyze/validation-criteria.md is loaded and followed
```
