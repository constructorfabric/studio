---
cf: true
type: workflow
name: cf-plan
description: Invoke when the user asks to plan, create a plan, decompose, break down, or organize a large or multi-step task into phases — produces self-contained phase files with brief + compiled forms.
version: 1.0
purpose: Universal workflow for generating execution plans with phased delivery
---

# Plan

<!-- toc -->

- [Overview](#overview)
- [Context Budget & Overflow Prevention (CRITICAL)](#context-budget--overflow-prevention-critical)
- [Phase 0: Resolve Variables & Discover Tools](#phase-0-resolve-variables--discover-tools)
- [Phase 1: Assess Scope](#phase-1-assess-scope)
- [Phase 2: Decompose](#phase-2-decompose)
- [Phase 3: Compile Phase Files](#phase-3-compile-phase-files)
- [Phase 4: Finalize Plan](#phase-4-finalize-plan)
- [Plan Lifecycle](#plan-lifecycle)
- [Plan Reference](#plan-reference)
- [Completion Invariants](#completion-invariants)

<!-- /toc -->

```text
UNIT PlanBootstrap

PURPOSE:
  Load required files in order before any phase work begins.

DO:
  IF {cfs_mode} == off:
    REQUIRE {cf-studio-path}/.core/skills/studio/SKILL.md is loaded and followed FIRST
  REQUIRE {cf-studio-path}/.core/skills/studio/protocol.md is loaded and followed
    before any workflow-local phase work
  REQUIRE {cf-studio-path}/.core/workflows/shared/stop-token-policy.md is loaded and followed
    before any prompt that relies on stop-token behavior

RULES:
  - MUST load SKILL.md first when cfs_mode is off
  - MUST load protocol.md before any phase work
  - MUST load stop-token-policy.md before any stop-token-dependent prompt
  - MUST load {cf-studio-path}/.core/requirements/plan-template.md WHEN compiling phase files
  - MUST load {cf-studio-path}/.core/requirements/plan-decomposition.md WHEN decomposing tasks into phases
  - MUST load {cf-studio-path}/.core/requirements/prompt-engineering.md WHEN compiling phase files
    (phase files ARE agent instructions)
  - MUST load {cf-studio-path}/.core/requirements/plan-checklist.md WHEN validating plans
    (Phase 4.1 self-validation or /cf-analyze on plan)

NOTES:
  Type: Operation.
  Constraint summary (authoritative sources in phase sub-files):
    This workflow ONLY generates execution plans (does not implement) — phase-2-decompose.md
    Complete coverage, compact loading — phase-1-assess.md
    Kit rules are law — phase-1-assess.md
    Deterministic first — phase-3-compile.md
    Interactive questions completeness — phase-1-assess.md
    Brief before compile — phase-3-compile.md
  For context compaction recovery during multi-phase workflows, follow
  {cf-studio-path}/.core/skills/studio/protocol.md § Compaction Recovery.
```

```text
UNIT PlanSharedContextPack

PURPOSE:
  Keep plan-phase prompt loading controller-owned and pack-aware.

RULES:
  - Plan workflow prompt assets are controller-owned runtime loads and MUST use
    {cf-studio-path}-prefixed runtime paths when mirrors exist
  - The controller MUST reuse or extend SHARED_CONTEXT_PACK before any
    downstream phase compiler, phase runner, or other prompt-consuming dispatch
    that depends on plan prompt assets
  - Plan MUST NOT rely on prompt-consuming sub-agents reopening workflow,
    requirement, spec, or AGENTS prompt files directly
```

## Overview

```text
UNIT PlanOverview

PURPOSE:
  Define when and how to use the plan workflow.

RULES:
  - MUST use this workflow when work exceeds a single-context window, requires a long
    checklist, or involves multi-block implementation
  - MUST NOT use for small edits, direct execution, or work that fits in ~500 compiled lines
  - Output: plan.toml + N phase files in {cf-studio-path}/.plans/{task-slug}/
```

## Context Budget & Overflow Prevention (CRITICAL)

```text
UNIT PlanContextBudget

PURPOSE:
  Enforce context budget across all plan phases.

RULES:
  - MUST open every applicable dependency file to inspect required sections,
    but MUST NOT retain full file bodies once needed slices are extracted
  - MUST NOT load all kit dependencies at once; load incrementally per phase
  - MUST NOT hold all phase files in context simultaneously; compile and write one at a time
  - MUST checkpoint and use Compaction Recovery if a phase compilation would exceed context budget
  - MUST write plan.toml (recovery checkpoint) before compilation
  - IF raw task input > 500 lines:
      materialize under {cf-studio-path}/.plans/{task-slug}/input/
      chunk to <= 300 lines per file
      treat resulting chunk files as authoritative raw-input package
      IF source includes direct prompt text:
        preserve raw prompt as input/direct-prompt.md before chunking
      REQUIRE {cf-studio-path}/.core/requirements/raw-input-overflow.md is loaded and followed

NOTES:
  Budget targets: Phase 0-1 ~200 lines, Phase 2 ~300, Phase 3 ~500 per phase file, Phase 4 ~50.
  Reference appendices below are runtime guidance only and do not consume plan-generation
  budget unless the user explicitly asks about execution behavior.
```

## Phase 0: Resolve Variables & Discover Tools

```text
UNIT PlanPhase0

PURPOSE:
  Resolve runtime variables and build the dynamic tool map from the CLISPEC.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/plan/phase-0-discover.md is loaded and followed
```

## Phase 1: Assess Scope

```text
UNIT PlanPhase1

PURPOSE:
  Identify task type, extract target-workflow navigation rules, estimate compiled
  size, scan for all user interaction points, and identify the target artifact and slug.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/plan/phase-1-assess.md is loaded and followed
```

## Phase 2: Decompose

```text
UNIT PlanPhase2

PURPOSE:
  Select plan lifecycle, run intermediate-results analysis, add review gates,
  and predict execution-context budget per phase.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/plan/phase-2-decompose.md is loaded and followed
```

## Phase 3: Compile Phase Files

```text
UNIT PlanPhase3

PURPOSE:
  Write plan manifest, generate compilation briefs, present post-brief choice menu,
  produce phase files or phase-generation prompts, and validate compiled phase files.

DO:
  REQUIRE {cf-studio-path}/.core/workflows/plan/phase-3-compile.md is loaded and followed

RULES:
  - Phase 3.3 dispatch payload MUST include git_commit_mode, contributing_guide,
    and git_constraint as specified in phase-3-compile.md § 3.3
```

## Phase 4: Finalize Plan

```text
UNIT PlanPhase4

PURPOSE:
  Run self-validation and emit gated next-steps menu after all phase files are produced.

WHEN:
  user selected option [1] or [3] in Phase 3.2A
  AND all phase-* files were produced
  AND plan.execution_status != "prompts_emitted"

DO:
  REQUIRE {cf-studio-path}/.core/workflows/plan/phase-4-finalize.md is loaded and followed

NOTES:
  Contains Phase 4.1 self-validation, gated Phase 4.2 next-steps menu
  (native-execution branch [1]–[5], fallback branch [1]–[4]), and New-Chat Startup Prompt.
```

## Plan Lifecycle

```text
UNIT PlanLifecycle

PURPOSE:
  Load lifecycle strategy when Phase 2.1 requires user selection.

WHEN:
  Phase 2.1 requires the user to select a plan lifecycle strategy

DO:
  REQUIRE {cf-studio-path}/.core/workflows/plan/plan-lifecycle.md is loaded and followed
```

## Plan Reference

```text
UNIT PlanReference

PURPOSE:
  Load execution, status, storage format, or execution log reference on demand.

WHEN:
  user asks about plan execution, status, storage format, or the execution log
  (post-plan-creation reference)

DO:
  REQUIRE {cf-studio-path}/.core/workflows/plan/plan-reference.md is loaded and followed
```

## Completion Invariants

```text
UNIT PlanCompletionInvariants

PURPOSE:
  Enforce terminal block requirement before ending any plan response.

DO:
  REQUIRE {cf-studio-path}/.core/skills/studio/SKILL.md § Completion Invariants
    is loaded and followed before ending any response

INVARIANTS:
  - MUST end with Phase 4 next-steps menu OR Phase 3 brief-checkpoint menu
    when a /cf-plan run compiled phase files
```
