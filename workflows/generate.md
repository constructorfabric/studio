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

```text
UNIT GenerateReverseEngineering

PURPOSE:
  Evaluate auto-config / storytelling-package gates before Phase 0 on BROWNFIELD projects.

WHEN:
  project is BROWNFIELD

DO:
  REQUIRE {cf-studio-path}/.core/workflows/generate/reverse-engineering.md is loaded and followed
```

## Overview

```text
UNIT GenerateOverview

PURPOSE:
  Define generation mode defaults and key variables.

RULES:
  - Artifact generation mode: template + example by default; load checklist up front
    only when current rules explicitly require it before writing
  - Code generation mode: design/spec context first; load checklist during validation/review
    unless current rules explicitly require it during implementation
  - Config mode: create/update config files
  - After protocol.md: TARGET_TYPE, RULES, KIND, PATH, MODE, and resolved
    phase-appropriate dependencies are known
  - Key variables: {cf-studio-path}/config/, {ARTIFACTS_REGISTRY}, {KITS_PATH}, {PATH}
  - Use {KITS_PATH}/artifacts/{KIND}/examples/ for style and quality guidance
```

```text
UNIT GenerateSharedContextPack

PURPOSE:
  Keep generate-phase prompt loading controller-owned and pack-aware.

RULES:
  - Workflow fragments referenced by generate are controller-owned prompt
    assets loaded from {cf-studio-path}/.core/workflows/...
  - Before any downstream author or reviewer dispatch, the controller MUST
    reuse or extend SHARED_CONTEXT_PACK and derive prompt_context_view that
    satisfies the dispatched agent's prompt_context_requirements
  - Generate MUST NOT rely on prompt-consuming sub-agents reopening workflow,
    requirement, spec, or AGENTS prompt files directly
```

## Context Budget & Overflow Prevention (CRITICAL)

```text
UNIT GenerateContextBudget

PURPOSE:
  Enforce context budget throughout generation phases.

RULES:
  - MUST estimate size before loading large docs (e.g. wc -l) and state the budget for this turn
  - MUST load only generation-phase sections required for the current KIND
  - MUST defer checklist loading to validation/review unless current rules explicitly require it earlier
  - MUST use read_file ranges, summarize each chunk, and keep only extracted criteria
  - MUST stop and output a checkpoint in chat only (do not proceed to writing files)
    if required steps cannot fit in context
  - Plan escalation: Phase 0.1 is mandatory after dependencies load
  - WHEN SUB_AGENT_SESSION_APPROVED=true AND INLINE_FALLBACK=false:
      gate logs the estimate and proceeds without proposing /cf-plan;
      decomposition is handled in-workflow by Phase 1.5 (mandatory in that branch)
  - OTHERWISE: legacy size-based escalation menu fires when budget is exceeded
```

## Agent Anti-Patterns (STRICT mode)

```text
UNIT GenerateAntiPatterns

PURPOSE:
  Identify and prevent critical generation failures in STRICT mode.

RULES:
  - Reference: {cf-studio-path}/.core/requirements/agent-compliance.md for full list
  - Critical failures: SKIP_TEMPLATE, SKIP_EXAMPLE, SKIP_CHECKLIST, PLACEHOLDER_SHIP,
    NO_CONFIRMATION, SIMULATED_VALIDATION
  - MUST self-check before writing files (MANDATORY in STRICT mode):
      template loaded, example referenced, no placeholders, explicit `yes` received
  - Checklist self-review required before writing only when current rules explicitly require it;
    otherwise defer to Phase 5
  - MUST stop and fix before proceeding if any required answer fails
  - MUST include self-check results in Phase 3 Summary output (STRICT mode)
```

## Rules Mode Behavior

```text
UNIT GenerateRulesMode

PURPOSE:
  Load canonical STRICT/RELAXED and stop-token behavior.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/shared/mode-resolution.md is loaded and followed
  REQUIRE {cf-studio-path}/.core/workflows/shared/stop-token-policy.md is loaded and followed
```

## Phase 0: Ensure Dependencies

```text
UNIT GeneratePhase0

PURPOSE:
  Resolve dependencies after protocol.md loads.

WHEN:
  workflow enters dependency resolution after
  {cf-studio-path}/.core/skills/studio/protocol.md

DO:
  REQUIRE {cf-studio-path}/.core/workflows/generate/phase-0-dependencies.md is loaded and followed

NOTES:
  {cf-studio-path}/.core/workflows/generate/phase-0-dependencies.md delegates
  the INLINE_FALLBACK probe to
  {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md
  (canonical block reused by analyze.md).
```

## Phase 0.1: Plan Escalation Gate

```text
UNIT GeneratePhase01

PURPOSE:
  Run plan escalation gate after dependencies load.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/shared/plan-escalation-gate.md is loaded and followed
```

## Phase 0.2: Review-Loop Configuration

```text
UNIT GeneratePhase02

PURPOSE:
  Load COLLECTOR_MAX_ITER configuration.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/generate/phase-0.2-review-loop-cfg.md is loaded and followed

NOTES:
  MAX_ITER prompt + parser live in {cf-studio-path}/.core/workflows/generate/phase-5/index.md
  § Pre-Phase-Setup (also the analyze.md external-entry point).
```

## Phase 0.x: GIT_COMMIT_MODE Probe

```text
UNIT GeneratePhase0x

PURPOSE:
  Probe GIT_COMMIT_MODE before Phase 0.5.

WHEN:
  GIT_COMMIT_MODE == unset
  AND Phase 0.5 has not yet started

DO:
  REQUIRE {cf-studio-path}/.core/workflows/generate/phase-0-git-commit-mode.md is loaded and followed

RULES:
  - MUST skip if GIT_COMMIT_MODE is already set from an earlier run in this chat session
```

## Phase 0.5: Clarify Output & Context

```text
UNIT GeneratePhase05

PURPOSE:
  Clarify output destination or system context when unclear.

WHEN:
  system context or output destination is unclear
  AND before Phase 0.7 / Phase 1

DO:
  REQUIRE {cf-studio-path}/.core/workflows/generate/phase-0.5-clarify.md is loaded and followed
```

## Phase 0.7: Brainstorm

```text
UNIT GeneratePhase07

PURPOSE:
  Run brainstorm phase when applicable.

WHEN:
  Phase 0.5 is complete
  AND --no-brainstorm was NOT passed
  AND active KIND's rules.md does NOT set brainstorm = "disabled"

DO:
  REQUIRE {cf-studio-path}/.core/workflows/generate/phase-0.7/index.md is loaded and followed
```

## Phase 1: Collect Information

```text
UNIT GeneratePhase1

PURPOSE:
  Gather Inputs for Phase 4.

WHEN:
  dependency resolution and Phase 0.5 / 0.7 are complete

DO:
  REQUIRE {cf-studio-path}/.core/workflows/generate/phase-1-collect.md is loaded and followed
```

## Phase 1.5: Author Plan

```text
UNIT GeneratePhase15

PURPOSE:
  Present author plan offer gate before Phase 3 summary.

WHEN:
  Phase 1 inputs are approved
  AND before Phase 3 summary

DO:
  REQUIRE {cf-studio-path}/.core/workflows/generate/phase-1.5-author-plan.md is loaded and followed

RULES:
  - The author plan is optional for the user
  - The offer gate is MANDATORY unless an explicit auto-skip condition in that file applies
```

## Phase 2 / Phase 2.5

```text
UNIT GeneratePhase2

PURPOSE:
  Emit Phase 2 no-op or Phase 2.5 checkpoint for long-running generation.

WHEN:
  orchestrator passes through Phase 2 no-op
  OR must emit a Phase 2.5 checkpoint for a long-running generation

DO:
  REQUIRE {cf-studio-path}/.core/workflows/generate/phase-2-checkpoint.md is loaded and followed
```

## Phase 3: Summary

```text
UNIT GeneratePhase3

PURPOSE:
  Present summary and obtain user confirmation before any files are written.

WHEN:
  Phase 1 inputs are approved
  AND Phase 1.5 has set AUTHOR_PLAN_OFFER_RESOLVED
  AND user must confirm yes/no/modify before any files are written

DO:
  REQUIRE {cf-studio-path}/.core/workflows/generate/phase-3-summary.md is loaded and followed
```

## Phase 4: Write

```text
UNIT GeneratePhase4

PURPOSE:
  Dispatch author to write files atomically.

WHEN:
  Phase 3 returned yes
  AND author must be dispatched (mode=create) to write files atomically

DO:
  REQUIRE {cf-studio-path}/.core/workflows/generate/phase-4-write.md is loaded and followed
```

## Phase 5: Review Loop

```text
UNIT GeneratePhase5

PURPOSE:
  Run bounded review loop after files are written.

WHEN:
  Phase 4 has written files
  OR analyze.md Remediation Handoff option 1 routes external entry into Phase 5.3

DO:
  REQUIRE {cf-studio-path}/.core/workflows/generate/phase-5/index.md is loaded and followed
```

## Phase 6: Offer Next Steps

```text
UNIT GeneratePhase6

PURPOSE:
  Assemble next-steps and handoff menus after Phase 5 exits.

WHEN:
  Phase 5 exits

DO:
  REQUIRE {cf-studio-path}/.core/workflows/generate/phase-6/index.md is loaded and followed

RULES:
  - Remediation Handoff: conditional on non-empty remaining_findings
  - Post-Write Review Handoff: mandatory when files were written
```

## Error Handling

```text
UNIT GenerateErrorHandling

PURPOSE:
  Handle tool/dispatch failures, user abandonment, and validation-failure loops.

WHEN:
  tool/dispatch failure occurs
  OR user abandonment occurs
  OR validation-failure loop reaches 3+ failed iterations
  (during any generate phase)

DO:
  REQUIRE {cf-studio-path}/.core/workflows/generate/error-handling.md is loaded and followed
```

## State Summary & Validation Criteria

```text
UNIT GenerateStateSummary

PURPOSE:
  Track generation state and run post-flight checklist.

STATE:
  Generating artifact: TARGET_TYPE=artifact, Has Template=true, Has Checklist=phase-dependent, Has Example=true
  Generating code:     TARGET_TYPE=code,     Has Template=false, Has Checklist=phase-dependent, Has Example=false

WHEN:
  post-flight checklist must be verified before ending the response

DO:
  REQUIRE {cf-studio-path}/.core/workflows/generate/validation-criteria.md is loaded and followed
```

## Agent Self-Test (STRICT mode — AFTER completing work)

```text
UNIT GenerateSelfTest

PURPOSE:
  Answer canonical self-test questions in STRICT mode after completing work.

WHEN:
  STRICT mode finalization requires self-test

DO:
  REQUIRE {cf-studio-path}/.core/workflows/generate/validation-criteria.md § Agent Self-Test
    (STRICT mode — AFTER completing work) is loaded and followed
```
