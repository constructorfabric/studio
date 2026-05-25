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

> **⛔ CRITICAL CONSTRAINTS** — enforced in the phase sub-files below; do NOT duplicate the full constraint text here.
>
> | Constraint | Authoritative file |
> |---|---|
> | This workflow ONLY generates execution plans (does not implement) | workflows/plan/phase-2-decompose.md |
> | Complete coverage, compact loading | workflows/plan/phase-1-assess.md |
> | Kit rules are law | workflows/plan/phase-1-assess.md |
> | Deterministic first | workflows/plan/phase-3-compile.md |
> | Interactive questions completeness | workflows/plan/phase-1-assess.md |
> | Brief before compile | workflows/plan/phase-3-compile.md |

Bootstrap order:

1. Open and follow `{cf-studio-path}/.core/skills/studio/SKILL.md`
   first when `{cfs_mode}` is `off`.
2. Then open and follow `{cf-studio-path}/.core/skills/studio/protocol.md`
   before any workflow-local phase work.
3. Then open and follow `workflows/shared/stop-token-policy.md` before any
   prompt that relies on stop-token behavior.

**Type**: Operation

ALWAYS open and follow `{cf-studio-path}/.core/requirements/plan-template.md` WHEN compiling phase files

ALWAYS open and follow `{cf-studio-path}/.core/requirements/plan-decomposition.md` WHEN decomposing tasks into phases

OPEN and follow `{cf-studio-path}/.core/requirements/prompt-engineering.md` WHEN compiling phase files (phase files ARE agent instructions)

OPEN and follow `{cf-studio-path}/.core/requirements/plan-checklist.md` WHEN validating plans (Phase 4.1 self-validation or /cf-analyze on plan)

For context compaction recovery during multi-phase workflows, follow
`{cf-studio-path}/.core/skills/studio/protocol.md` Section "Compaction Recovery".

## Overview

This workflow generates execution plans, not direct results. Use it when work exceeds a single-context window, requires a long checklist, or involves multi-block implementation. Do **not** use it for small edits, direct execution, or work that fits in ~500 compiled lines. Output: `plan.toml` + `N` phase files in `{cf-studio-path}/.plans/{task-slug}/`.

## Context Budget & Overflow Prevention (CRITICAL)

- Open every applicable dependency file to inspect required sections, but do NOT retain full file bodies once the needed slices are extracted.
- Do NOT load all kit dependencies at once; load incrementally per phase.
- Do NOT hold all phase files in context simultaneously; compile and write one at a time.
- If a phase compilation would exceed current context budget, checkpoint and use Compaction Recovery.
- The plan manifest (`plan.toml`) is the recovery checkpoint and MUST be written before compilation.
- If the raw task input itself exceeds `500` lines, materialize it under `{cf-studio-path}/.plans/{task-slug}/input/`, chunk it to `<= 300` lines per file, and treat the resulting chunk files as the authoritative raw-input package for the plan. When the source includes direct prompt text, preserve that raw prompt as `input/direct-prompt.md` before chunking. (Open, load, and follow `{cf-studio-path}/.core/requirements/raw-input-overflow.md` for the shared overflow rule.)

Budget targets: Phase 0-1 `~200` lines, Phase 2 `~300`, Phase 3 `~500` per phase file, Phase 4 `~50`. The reference appendices below are runtime guidance only and do not consume plan-generation budget unless the user explicitly asks about execution behavior.

## Phase 0: Resolve Variables & Discover Tools

Open, load, and follow `workflows/plan/phase-0-discover.md` to resolve runtime variables and build the dynamic tool map from the CLISPEC.

## Phase 1: Assess Scope

Open, load, and follow `workflows/plan/phase-1-assess.md` to identify task type, extract target-workflow navigation rules, estimate compiled size, scan for all user interaction points, and identify the target artifact and its slug.

## Phase 2: Decompose

Open, load, and follow `workflows/plan/phase-2-decompose.md` to select the plan lifecycle, run intermediate-results analysis, add review gates, and predict execution-context budget per phase.

## Phase 3: Compile Phase Files

Open, load, and follow `workflows/plan/phase-3-compile.md` to write the plan manifest (`plan.toml`), generate compilation briefs, present the post-brief choice menu, produce phase files or phase-generation prompts, and validate compiled phase files. The Phase 3.3 dispatch payload MUST include `git_commit_mode`, `contributing_guide`, and `git_constraint` as specified in `phase-3-compile.md` § 3.3.

## Phase 4: Finalize Plan

Open, load, and follow `workflows/plan/phase-4-finalize.md` WHEN the user selected option `[1]` or `[3]` in Phase 3.2A and all `phase-*` files were produced. Contains Phase 4.1 self-validation, the gated Phase 4.2 next-steps menu (native-execution branch `[1]`–`[5]`, fallback branch `[1]`–`[4]`), and the New-Chat Startup Prompt.

## Plan Lifecycle

Open and follow `workflows/plan/plan-lifecycle.md` WHEN Phase 2.1 requires the user to select a plan lifecycle strategy.

## Plan Reference

Open and follow `workflows/plan/plan-reference.md` WHEN the user asks about plan execution, status, storage format, or the execution log (post-plan-creation reference).

## Completion Invariants

Open and follow `{cf-studio-path}/.core/skills/studio/SKILL.md` § Completion Invariants before ending any response.
(A /cf-plan run that compiled phase files MUST end with the Phase 4 next-steps menu or the Phase 3 brief-checkpoint menu.)
