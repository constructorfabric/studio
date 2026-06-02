---
cf: true
type: requirement
name: Plan Decomposition Strategies
version: 1.0
purpose: Define how to split tasks into phases by type — generate, analyze, implement
---

# Plan Decomposition Strategies


<!-- toc -->

- [Overview](#overview)
- [Strategy Selection](#strategy-selection)
- [Strategy 1: Generate (by Template Sections)](#strategy-1-generate-by-template-sections)
- [Strategy 2: Analyze Artifacts (by Checklist Categories)](#strategy-2-analyze-artifacts-by-checklist-categories)
- [Strategy 2b: Analyze Codebase (by Scope + Runtime Reading)](#strategy-2b-analyze-codebase-by-scope--runtime-reading)
- [Strategy 3: Implement (by CDSL Blocks)](#strategy-3-implement-by-cdsl-blocks)
- [Budget Enforcement](#budget-enforcement)
- [Execution Context Prediction](#execution-context-prediction)
- [Phase Dependencies](#phase-dependencies)
- [Single-Context Bypass](#single-context-bypass)

<!-- /toc -->

## Overview

The plan workflow must choose a decomposition strategy by task type. Every phase must be independently executable, self-contained except for declared runtime reads, and small enough to fit the context budget.

## Strategy Selection

| Task type | Detect when | Strategy |
|-----------|-------------|----------|
| `generate` | create, generate, write, update, draft | split by template sections |
| `analyze` | validate, review, check, audit, analyze | split by checklist categories |
| `implement` | implement, code, build, develop | split by CDSL blocks |

```pdsl
UNIT DecompositionStrategySelection

PURPOSE:
  Select the decomposition strategy based on detected task type.

WHEN:
  - REQUIRE plan generation begins

DO:
  - SET strategy: generate when task type matches create/generate/write/update/draft
  - SET strategy: analyze when task type matches validate/review/check/audit/analyze
  - SET strategy: implement when task type matches implement/code/build/develop
  - WAIT user.reply when intent is ambiguous; ask user to clarify task type

RULES:
  - ALWAYS choose a decomposition strategy before generating phases
  - ALWAYS make every phase independently executable and self-contained except for declared runtime reads
```

## Strategy 1: Generate (by Template Sections)

```pdsl
UNIT GenerateStrategy

PURPOSE:
  Split generate tasks into phases by template section groups.

WHEN:
  - REQUIRE strategy = generate

DO:
  - LOAD the target template
  - SET section_list: all H2 sections from the template
  - SET phase_groups: group adjacent sections into phases of 2-4 sections each
  - RUN each phase to create or update one section group

RULES:
  - ALWAYS group sections with dependencies together
  - ALWAYS keep the first and final synthesis groups small
  - ALWAYS give any section that would exceed 300 compiled lines its own phase
```

## Strategy 2: Analyze Artifacts (by Checklist Categories)

> For codebase analysis, use Strategy 2b.

```pdsl
UNIT AnalyzeArtifactsStrategy

PURPOSE:
  Split analyze tasks into phases by checklist category groups following the validation pipeline.

WHEN:
  - REQUIRE strategy = analyze
  - AND target is an artifact (not a codebase)

DO:
  - LOAD the target checklist
  - SET category_list: checklist categories identified by heading group
  - SET phase_groups: group categories following Structural -> Semantic -> Cross-reference -> Traceability -> Synthesis
  - RUN each phase to produce a partial report

RULES:
  - ALWAYS order validation pipeline: Structural -> Semantic -> Cross-reference -> Traceability -> Synthesis
  - ALWAYS make Synthesis the final phase
  - ALWAYS use 2 phases (checks + synthesis) when checklist has fewer than 15 items
  - ALWAYS combine Structural and Semantic when checklist size is fewer than 20 items
  - ALWAYS combine Cross-reference and Traceability when external references are few
```

## Strategy 2b: Analyze Codebase (by Scope + Runtime Reading)

> **⚠️ EXCEPTION TO SELF-CONTAINMENT**: code analysis is the one case where runtime file reading is permitted because code is too large to inline.

| Phase | Scope | Inline | Runtime read |
|------|-------|--------|--------------|
| 1 | Setup | Checklist, file patterns | Design artifact, directory listing |
| 2 | File-level | Naming/style checks | Source files |
| 3 | Module-level | Boundary/interface checks | Design artifact, module entry points |
| 4 | Cross-module | Contract/interface checks | Import graphs, related modules |
| 5 | Traceability | `@cpt-*` rules, ID rules | Design IDs, marked files |
| 6 | Synthesis | Acceptance criteria | Partial reports |

```pdsl
UNIT AnalyzeCodebaseStrategy

PURPOSE:
  Split codebase analysis into phases using runtime file reading for source code.

WHEN:
  - REQUIRE strategy = analyze
  - AND target is a codebase

DO:
  - RUN Phase 1 (Setup): inline checklist and file patterns; runtime-read design artifact and directory listing
  - RUN Phase 2 (File-level): inline naming/style checks; runtime-read source files
  - RUN Phase 3 (Module-level): inline boundary/interface checks; runtime-read design artifact and module entry points
  - RUN Phase 4 (Cross-module): inline contract/interface checks; runtime-read import graphs and related modules
  - RUN Phase 5 (Traceability): inline @cpt-* rules and ID rules; runtime-read design IDs and marked files
  - RUN Phase 6 (Synthesis): inline acceptance criteria; runtime-read partial reports from out/

RULES:
  - ALWAYS inline checklist criteria, codebase rules, @cpt-* format, file-pattern metadata, and acceptance criteria
  - ALWAYS runtime-read DESIGN/FEATURE artifacts, source files, directory listings, import graphs, and prior out/ results
  - ALWAYS keep Traceability as a separate phase
  - ALWAYS make Synthesis the final phase
  - ALWAYS combine file-level and module-level when codebase has fewer than 10 files
  - ALWAYS split file-level by top-level directory when codebase has more than 50 files
```

## Strategy 3: Implement (by CDSL Blocks)

```pdsl
UNIT ImplementStrategy

PURPOSE:
  Split implement tasks into phases by CDSL block with tests.

WHEN:
  - REQUIRE strategy = implement

DO:
  - LOAD the FEATURE spec
  - SET block_list: CDSL blocks — flows, algorithms, state machines
  - SET phases: one phase per CDSL block plus its tests
  - RUN final integration phase after all block phases

RULES:
  - ALWAYS make each flow/algorithm/state machine its own phase
  - ALWAYS keep tests with their implementation phase
  - ALWAYS add a final integration phase
  - ALWAYS combine blocks with fewer than 3 steps with related blocks
  - ALWAYS split blocks that would exceed 500 lines into step-group sub-phases
  - NEVER implement business logic in scaffolding phases
  - NEVER introduce new business logic in the integration phase
```

## Budget Enforcement

| Metric | Target | Maximum | Action |
|--------|--------|---------|--------|
| Compiled phase file | ≤ 500 | ≤ 1000 | Split into sub-phases |
| Rules section | ≤ 200 | ≤ 300 | Narrow phase scope |
| Input section | ≤ 300 | ≤ 500 | Split input |
| Task steps | 3-7 | 10 | Split task |

```pdsl
UNIT BudgetEnforcement

PURPOSE:
  Enforce phase size budgets and apply splitting rules when limits are exceeded.

WHEN:
  - REQUIRE a phase is compiled

DO:
  - SET compiled_size: count lines in compiled phase file
  - CONTINUE when compiled_size <= 500
  - EMIT warning when compiled_size is 501-1000
  - REQUIRE split into sub-phases when compiled_size > 1000

RULES:
  - ALWAYS distribute raw-input chunk files across phases explicitly through input_files when plan includes input/ package; never hide them in generic context estimates
  - NEVER trim or summarize rules when Rules section is the largest contributor; narrow phase scope instead
  - ALWAYS split input across more phases when Input section is the largest contributor
  - ALWAYS split task into sequential phases with explicit handoff when Task section is the largest contributor

INVARIANTS:
  - ALWAYS cover 100% of the target rules.md across the union of all phase Rules sections
```

## Execution Context Prediction

Phase files inline stable kit content while reading dynamic project content at runtime.

```text
execution_context = phase_file_lines
                   + sum(runtime_artifact_lines)
                   + sum(runtime_code_lines)
                   + sum(intermediate_input_lines)
                   + estimated_output_lines
```

Heuristics: `phase_file_lines` = compiled phase size; `runtime_artifact_lines` = artifacts in `input_files`; `runtime_code_lines` = file count × average size; `intermediate_input_lines` = prior `out/` files; `estimated_output_lines` = expected generated/report output.

```pdsl
UNIT ExecutionContextPrediction

PURPOSE:
  Predict execution context per phase and split phases that would overflow.

WHEN:
  - REQUIRE a phase is estimated during decomposition

DO:
  - SET execution_context: phase_file_lines + sum(runtime_artifact_lines) + sum(runtime_code_lines) + sum(intermediate_input_lines) + estimated_output_lines
  - CONTINUE when execution_context <= 1500
  - EMIT warning when execution_context is 1501-2000
  - REQUIRE split when execution_context > 2000
  - RUN split strategy based on largest contributor: runtime artifacts -> split by artifact; runtime code -> split by directory/module; intermediate inputs -> add consolidation phase; phase file -> narrow scope
  - RUN re-estimation after each split; repeat until every phase is within budget

RULES:
  - ALWAYS estimate every phase during decomposition
  - ALWAYS flag warning and overflow phases in decomposition summary
  - ALWAYS auto-split overflow phases before compilation

NOTES:
  Example: Analyze PRD + DESIGN consistency
  phase_file_lines: 600, runtime_artifacts: 1200, intermediate_inputs: 50, estimated_output: 200
  total: 2050 → OVERFLOW → split into one PRD-focused phase and one DESIGN-focused phase
```

## Phase Dependencies

```pdsl
UNIT PhaseDependencies

PURPOSE:
  Define how phases declare and respect execution-order dependencies.

WHEN:
  - REQUIRE a plan is generated

DO:
  - SET depends_on: [] for Phase 1
  - SET depends_on: [phase_number] for each later phase that requires the output of that phase
  - SET depends_on: [all_required_prior_phases] for the final synthesis/integration phase

RULES:
  - ALWAYS declare phase dependencies in TOML frontmatter
  - ALWAYS allow independent phases to run in parallel
  - ALWAYS present phases sequentially by default even when parallel execution is possible
  - NEVER interpret dependencies on prior out/ artifacts as a requirement that those files exist during brief generation or phase compilation
```

## Single-Context Bypass

```pdsl
UNIT SingleContextBypass

PURPOSE:
  Redirect to direct workflow when total compiled content fits within 500 lines, unless an approved raw-input package is already in effect.

WHEN:
  - REQUIRE plan generation begins
  - AND total compiled content would fit within 500 lines

DO:
  - LOAD {cf-studio-path}/.plans/{task-slug}/input/manifest.json when it exists
  - CONTINUE plan generation when manifest.json exists with input_signature matching current direct prompt text plus provided file contents; do NOT redirect
  - SET estimated_size: total compiled size when no matching manifest exists
  - DISPATCH to Invoke skill cf-generate or cf-analyze when estimated_size <= 500
  - CONTINUE plan generation when estimated_size > 500

RULES:
  - NEVER redirect to direct workflow when an approved raw-input package with matching input_signature is already in effect
```
