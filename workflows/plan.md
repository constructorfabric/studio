---
cf: true
type: workflow
name: cf-plan
description: Invoke when the user asks to plan, create a plan, decompose, break down, or organize a large or multi-step task into phases — produces self-contained phase files with brief + compiled forms.
version: 1.0
purpose: Universal workflow for generating execution plans with phased delivery
---

# Plan

```pdsl
UNIT PlanRootSkillEntrypointBootstrap
PURPOSE: Load the shared root cf skill entrypoint bootstrap and preserve plan routing invariants.
DO:
  - LOAD {cf-studio-path}/.core/workflows/shared/root-skill-entrypoint-bootstrap.md
  - CONTINUE RootSkillEntrypointBootstrap
RULES:
  - ALWAYS follow routing.md § CanonicalRoutingPrecedenceState for workflow
    entry, fallback dispatch state, and prompt-context ownership.
```

```pdsl
UNIT PlanBootstrap

PURPOSE:
  Load required files in order before any phase work begins.

DO:
  - REQUIRE {cfs_mode} == off:
    - REQUIRE {cf-studio-path}/.core/skills/studio/SKILL.md is loaded and followed FIRST
  - REQUIRE {cf-studio-path}/.core/skills/studio/protocol.md is loaded and followed
    before any workflow-local phase work
  - REQUIRE {cf-studio-path}/.core/workflows/shared/stop-token-policy.md is loaded and followed
    before any prompt that relies on stop-token behavior

RULES:
  - ALWAYS load {cf-studio-path}/.core/skills/studio/SKILL.md first when cfs_mode is off
  - ALWAYS load {cf-studio-path}/.core/skills/studio/protocol.md before any phase work
  - ALWAYS load {cf-studio-path}/.core/workflows/shared/stop-token-policy.md before any stop-token-dependent prompt
  - ALWAYS load {cf-studio-path}/.core/requirements/plan-template.md WHEN compiling phase files
  - ALWAYS load {cf-studio-path}/.core/requirements/plan-decomposition.md WHEN decomposing tasks into phases
  - ALWAYS load {cf-studio-path}/.core/requirements/prompt-engineering.md WHEN compiling phase files
    (phase files ARE agent instructions)
  - ALWAYS load {cf-studio-path}/.core/requirements/plan-checklist.md WHEN validating plans
    (Phase 4.1 self-validation or Invoke skill `cf-analyze` on plan)

NOTES:
  Type: Operation.
  Constraint summary (authoritative sources in phase sub-files):
    This workflow ONLY generates execution plans (does not implement) — phase-2-decompose.md
    Complete coverage, compact loading — phase-1-assess.md
    Kit rules are law — phase-1-assess.md
    Gate order: explore/brainstorm (Phase 0.a) → assess (Phase 1) → decompose (Phase 2) → compile (Phase 3) — see phase sub-files
    Interactive questions completeness — phase-1-assess.md
    Brief before compile — phase-3-compile.md
  For context compaction recovery during multi-phase workflows, follow
  {cf-studio-path}/.core/skills/studio/protocol.md § Compaction Recovery.
```

```pdsl
UNIT PlanSharedContextPack

PURPOSE:
  Keep plan-phase prompt loading controller-owned and pack-aware.

RULES:
  - ALWAYS Plan workflow prompt assets are controller-owned runtime loads and ALWAYS use
    {cf-studio-path}-prefixed runtime paths when mirrors exist
  - ALWAYS The controller ALWAYS reuse or extend SHARED_CONTEXT_PACK before any
    downstream phase compiler, phase runner, or other prompt-consuming dispatch
    that depends on plan prompt assets
  - ALWAYS Plan NEVER rely on prompt-consuming sub-agents reopening workflow,
    requirement, spec, or AGENTS prompt files directly
```

## Overview

```pdsl
UNIT PlanOverview

PURPOSE:
  Define when and how to use the plan workflow.

RULES:
  - ALWAYS use this workflow when work exceeds a single-context window, requires a long
    checklist, or involves multi-block implementation
  - NEVER use for small edits, direct execution, or work that fits in ~500 compiled lines
  - ALWAYS Output: plan.toml + N phase files in {cf-studio-path}/.plans/{task-slug}/
```

## Context Budget & Overflow Prevention (CRITICAL)

```pdsl
UNIT PlanContextBudget

PURPOSE:
  Enforce context budget across all plan phases.

RULES:
  - ALWAYS open every applicable dependency file to inspect required sections,
    but NEVER retain full file bodies once needed slices are extracted
  - NEVER load all kit dependencies at once; load incrementally per phase
  - NEVER hold all phase files in context simultaneously; compile and write one at a time
  - ALWAYS checkpoint and use Compaction Recovery if a phase compilation would exceed context budget
  - ALWAYS write plan.toml (recovery checkpoint) before compilation
  - ALWAYS IF raw task input > 500 lines:
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

```pdsl
UNIT PlanPhase0

PURPOSE:
  Resolve runtime variables and build the dynamic tool map from the CLISPEC.

DO:
  - REQUIRE {cf-studio-path}/.core/workflows/plan/phase-0-discover.md is loaded and followed
```

## Phase 0.a: Explore / Brainstorm Applicability

```pdsl
UNIT PlanExploreBrainstormGate

PURPOSE:
  Decide whether planning needs resource discovery or decision exploration
  before scope assessment and decomposition.

WHEN:
  - REQUIRE PlanPhase0 completed
  - AND before PlanPhase1

DO:
  - REQUIRE {cf-studio-path}/.core/workflows/shared/explore-brainstorm-gate.md is loaded and followed

RULES:
  - ALWAYS delegate explore/brainstorm applicability, replacement, and skip
    decisions to shared/explore-brainstorm-gate.md
  - ALWAYS include RESOURCE_CONTEXT and BRAINSTORM_CONTEXT in Phase 1 assessment
    when either exists
```

## Phase 1: Assess Scope

```pdsl
UNIT PlanPhase1

PURPOSE:
  Identify task type, extract target-workflow navigation rules, estimate compiled
  size, scan for all user interaction points, and identify the target artifact and slug.

DO:
  - REQUIRE {cf-studio-path}/.core/workflows/plan/phase-1-assess.md is loaded and followed
```

## Phase 2: Decompose

```pdsl
UNIT PlanPhase2

PURPOSE:
  Select plan lifecycle, run intermediate-results analysis, add review gates,
  and predict execution-context budget per phase.

DO:
  - REQUIRE {cf-studio-path}/.core/workflows/plan/phase-2-decompose.md is loaded and followed
```

## Phase 3: Compile Phase Files

```pdsl
UNIT PlanPhase3

PURPOSE:
  Write plan manifest, generate compilation briefs, present post-brief choice menu,
  produce phase files or phase-generation prompts, and validate compiled phase files.

DO:
  - REQUIRE {cf-studio-path}/.core/workflows/plan/phase-3-compile.md is loaded and followed

RULES:
  - ALWAYS Phase 3.3 dispatch payload ALWAYS include git_commit_mode, contributing_guide,
    and git_constraint as specified in phase-3-compile.md § 3.3
```

## Phase 4: Finalize Plan

```pdsl
UNIT PlanPhase4

PURPOSE:
  Run self-validation and emit the canonical final Phase 4 menu after all phase files are produced.

WHEN:
  - REQUIRE user selected option [1] or [3] in Phase 3.2A
  - AND all phase-* files were produced
  - AND plan.execution_status != "prompts_emitted"

DO:
  - REQUIRE {cf-studio-path}/.core/workflows/plan/phase-4-finalize.md is loaded and followed

NOTES:
  Contains Phase 4.1 self-validation, gated Phase 4.2 final menu
  (validation / next task / end), native-execution branch [1]-[5],
  fallback branch [1]-[4], and New-Chat Startup Prompt.
```

## Plan Lifecycle

```pdsl
UNIT PlanLifecycle

PURPOSE:
  Load lifecycle strategy when Phase 2.1 requires user selection.

WHEN:
  - REQUIRE Phase 2.1 requires the user to select a plan lifecycle strategy

DO:
  - REQUIRE {cf-studio-path}/.core/workflows/plan/plan-lifecycle.md is loaded and followed
```

## Plan Reference

```pdsl
UNIT PlanReference

PURPOSE:
  Load execution, status, storage format, or execution log reference on demand.

WHEN:
  - REQUIRE user asks about plan execution, status, storage format, or the execution log
  - REQUIRE (post-plan-creation reference)

DO:
  - REQUIRE {cf-studio-path}/.core/workflows/plan/plan-reference.md is loaded and followed
```

## Completion Invariants

```pdsl
UNIT PlanCompletionInvariants

PURPOSE:
  Enforce terminal block requirement before ending any plan response.

DO:
  - REQUIRE root cf skill Completion Invariants already loaded by
    RootSkillEntrypointBootstrap are followed before ending any response
  - NEVER make prompt-consuming sub-agents reopen SKILL.md from disk for this
    terminal check; pass any needed invariant slice through prompt_context_view

INVARIANTS:
  - ALWAYS end with the Phase 4 final menu when a cf-plan run compiled phase files
  - ALWAYS may end with the Phase 3 brief-checkpoint menu only for briefs_only or
    incomplete compilation checkpoints before all phase files are produced
  - ALWAYS Phase 3 brief-checkpoint output ALWAYS still require the Phase 4 final menu
    after full compilation
```
