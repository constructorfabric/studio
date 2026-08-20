# Feature: Workflow Eval-Harness

<!-- toc -->

- [1. Feature Context](#1-feature-context)
  - [1. Overview](#1-overview)
  - [2. Purpose](#2-purpose)
  - [3. Actors](#3-actors)
  - [4. References](#4-references)
- [2. Actor Flows (CDSL)](#2-actor-flows-cdsl)
  - [Run Eval Harness](#run-eval-harness)
- [3. Processes / Business Logic (CDSL)](#3-processes--business-logic-cdsl)
  - [Run Eval Suite](#run-eval-suite)
  - [Score Structural Compliance](#score-structural-compliance)
- [4. States (CDSL)](#4-states-cdsl)
  - [Eval Report Lifecycle](#eval-report-lifecycle)
- [5. Definitions of Done](#5-definitions-of-done)
  - [Compliance Report](#compliance-report)
- [6. Implementation Modules](#6-implementation-modules)
- [7. Acceptance Criteria](#7-acceptance-criteria)

<!-- /toc -->

- [x] `p1` - **ID**: `cpt-studio-featstatus-eval-harness`

## 1. Feature Context

- [x] `p1` - `cpt-studio-feature-eval-harness`

### 1. Overview

Scores completed workflow runs for how faithfully they followed their own plan. The
harness is a scaffold: it discovers **scenarios** (a completed run plus metadata), feeds
each run to a set of pluggable **scorers**, and aggregates the results into a JSON report
with a compliance verdict per scenario. Two scorer families plug into the same seam — a
deterministic structural scorer (which may affect the exit code) and an advisory
LLM-judge (which may never). This feature provides the scaffold and a placeholder
reference scorer; the real scorers are separate work.

### 2. Purpose

Studio's structural gates check that code is traceable, but nothing measures whether a
workflow *run* obeyed its recipe — step numbering, declared phase outputs, dependency
order. Without a harness the reasoning layer is a black box. The harness makes runs
scoreable and regression-checkable, while keeping the honest-signal discipline of the rest
of the tool: a run that cannot be scored reports `UNKNOWN`, never a silent zero, and an
advisory verdict can never gate a build.

### 3. Actors

| Actor | Role in Feature |
|-------|-----------------|
| `cpt-studio-actor-user` | Invokes `cfs eval` to score a suite of workflow-run scenarios |
| `cpt-studio-actor-ci-pipeline` | Runs `cfs eval` as a regression check against a baseline report |

### 4. References

- **PRD**: [PRD.md](../PRD.md) — `cpt-studio-fr-core-traceability`
- **Design**: [DESIGN.md](../DESIGN.md) — `cpt-studio-component-validator`
- **Dependencies**: `cpt-studio-feature-traceability-validation`

## 2. Actor Flows (CDSL)

### Run Eval Harness

- [x] `p1` - **ID**: `cpt-studio-flow-eval-harness-run`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User runs `cfs eval` → every scenario under `<project>/eval` is scored, JSON report emitted, exit 0 (gating is off by default — eval reports, it does not fail the build)
- User runs `cfs eval --scenarios-dir DIR` → scenarios discovered under `DIR`
- User runs `cfs eval --baseline report.json` → same, plus a per-scenario regression diff; the exit code is unchanged unless `--check` is also given
- User runs `cfs eval --check [--min N]` → exit 2 when structural compliance is below `--min`, **or** when `--baseline` shows a per-scenario compliance regression
- The JSON report always carries a `gate` field (`pass`/`fail`) matching the exit code, so a CI step can cross-check from `--json` alone

**Error Scenarios**:
- Constructor Studio not initialized, or the scenarios directory does not exist → ERROR, exit 1
- With `--check`: structural compliance below `--min`, or a baseline regression (a compliance drop, or a scenario that broke while still in the suite) → exit 2. A scenario removed from the suite entirely (`no_longer_scoreable`), or a `--baseline` that cannot be loaded (surfaced via the regression `error` field), is reported but does not by itself gate.

**Steps**:
1. [x] - `p1` - User invokes `cfs eval [--scenarios-dir DIR] [--baseline FILE]` - `inst-user-eval`
2. [x] - `p1` - Load project context; if absent, emit ERROR and exit 1 - `inst-load-context`
3. [x] - `p1` - Resolve the scenarios directory, run the suite through the deterministic structural scorer, attach an optional regression diff, emit the JSON report, and return the harness exit code - `inst-run-and-report`

**Supporting**:
- [x] - `p1` - Imports and module setup for the eval command - `inst-eval-imports`
- [x] - `p1` - Build the CLI parser for the scenarios directory, gating, baseline, and save flags - `inst-build-parser`
- [x] - `p1` - Load an optional baseline report JSON, degrading to no-diff on error - `inst-load-baseline`
- [x] - `p1` - Save this run's report JSON to serve as a later baseline - `inst-save-report`
- [x] - `p1` - Render a short human-readable summary when not in JSON mode - `inst-human-report`

## 3. Processes / Business Logic (CDSL)

### Run Eval Suite

- [x] `p1` - **ID**: `cpt-studio-algo-eval-harness-run`

Loads scenarios and completed-run artifacts, applies scorers, and aggregates the results
under the gate contract (only deterministic verdicts affect the exit code).

**Steps**:
1. [x] - `p1` - Discover scenarios by globbing `*/scenario.toml` under the root, skipping malformed or escaping descriptors - `inst-load-scenarios`
2. [x] - `p1` - Load a completed run's `plan.toml` and phase files, returning `None` (UNKNOWN) instead of raising on a missing or malformed plan - `inst-load-run`
3. [x] - `p1` - Load one scenario's run and apply every scorer to it, isolating a raising scorer as UNKNOWN - `inst-run-scenario`
4. [x] - `p1` - Run every scenario under the root through the scorers and aggregate into a report - `inst-run-suite`
5. [x] - `p1` - Compute structural compliance (deterministic pass ratio) per scenario and in aggregate, `None` when nothing was scored - `inst-compliance`
6. [x] - `p1` - Derive the exit code: gate only under `--check` when compliance is below the floor; advisory verdicts never gate - `inst-gate`
7. [x] - `p1` - Serialise the report: per-scenario compliance, a failing-check histogram, and an UNKNOWN-aware coverage-stating summary - `inst-report-json`
8. [x] - `p1` - Bucket per-scenario compliance changes against a baseline (regressed / improved / newly- and no-longer-scoreable) - `inst-diff-reports`

**Supporting**:
- [x] - `p1` - Imports and module setup for the harness - `inst-harness-imports`
- [x] - `p1` - Scorer kinds, verdicts, the scorer protocol, and the result/scenario/report data model - `inst-eval-datamodel`
- [x] - `p1` - A placeholder deterministic reference scorer that checks run presence, used to exercise the seam - `inst-reference-scorer`

### Score Structural Compliance

- [x] `p1` - **ID**: `cpt-studio-algo-eval-structural`

The real deterministic scorer plugged into the `Scorer` seam. It reads a completed run's
`plan.toml` manifest plus each phase file's `[phase]` frontmatter and runs a registry of
independent structural checks (numbering, manifest agreement, dependency order, declared
outputs, required sections). Verdict is `PASS` when every active check passes, `FAIL` when
any fails, and `UNKNOWN` when the run cannot be loaded or no phase carries parseable
frontmatter — "unscoreable is not zero". The scorer is pure over the in-memory run
artifacts: it touches no filesystem.

**Steps**:
1. [x] - `p1` - Parse each phase file's `[phase]` frontmatter into a number-keyed table, recording files that re-declare a number as duplicates - `inst-structural-parse`
2. [x] - `p1` - Run the phase-file validity and numbering-uniqueness checks over the parsed phases - `inst-structural-checks`
3. [x] - `p1` - Run the manifest-agreement and numbering checks over the parsed phases - `inst-structural-checks-manifest`
4. [x] - `p1` - Aggregate into a `ScorerResult`: compliance %, per-check findings, and the UNKNOWN discipline when nothing is scoreable - `inst-structural-scorer`

**Supporting**:
- [x] - `p1` - Module imports and the logger - `inst-structural-imports`
- [x] - `p1` - The frontmatter pattern and the per-workflow required-sections configuration - `inst-structural-config`
- [x] - `p1` - The `StructuralInput` data model the checks read from - `inst-structural-datamodel`
- [x] - `p1` - Shared reducers over the manifest and phases (declared numbers, totals, capped detail formatting) that the checks build on - `inst-structural-check-helpers`
- [x] - `p1` - Dependency-graph helpers: resolve/forward problems and misspelled-key detection - `inst-structural-deps`
- [x] - `p1` - The per-phase checks — total consistency, dependency order, declared outputs - `inst-structural-checks-phase`
- [x] - `p1` - Reduce a phase body to real Markdown prose (frontmatter and fenced code blocks removed) before heading detection - `inst-structural-prose`
- [x] - `p1` - The required-body-sections check over that prose - `inst-structural-checks-sections`
- [x] - `p1` - The check dataclass and the registry list binding each check name and tags to its predicate - `inst-structural-registry`

## 4. States (CDSL)

### Eval Report Lifecycle

Each scenario result carries one verdict. `NOT_SCORED` is the initial state before scoring.
A run transitions to `SCORED` when a scorer returns `PASS` or `FAIL`, or to `UNKNOWN` when
its artifacts cannot be loaded. The harness never transitions a run out of `UNKNOWN` into a
numeric score — "unscoreable" is terminal for that run, not a zero.

## 5. Definitions of Done

### Compliance Report

- [x] `p1` - **ID**: `cpt-studio-dod-eval-harness-report`

The scaffold is done when `cfs eval` emits a JSON report scoring every discovered scenario;
only deterministic scorer verdicts affect the exit code; a run whose artifacts cannot be
loaded reports `UNKNOWN` with a `null` score and is counted separately; and `--baseline`
yields a per-scenario regression diff without changing the exit code.

**Implements**:
- `cpt-studio-flow-eval-harness-run`
- `cpt-studio-algo-eval-harness-run`

## 6. Implementation Modules

| Module | Path | Responsibility |
|--------|------|----------------|
| Eval Command | `skills/studio/scripts/studio/commands/eval.py` | CLI entry point, arg parsing, context, exit code |
| Eval Harness | `skills/studio/scripts/studio/utils/eval_harness.py` | Scenario/run loading, scorer seam, runner, report, regression diff |
| Structural Scorer | `skills/studio/scripts/studio/utils/eval_structural.py` | Deterministic structural checks over a run's manifest + phase frontmatter |

## 7. Acceptance Criteria

- [x] `p1` - `cfs eval` scores every scenario under the resolved directory and emits a JSON report with a `gate` field consistent with the exit code
- [x] `p1` - Only deterministic scorer verdicts affect the exit code; an advisory FAIL never does
- [x] `p1` - A run that cannot be loaded, or whose phases declare no checkable file, scores `UNKNOWN` with a `null` score, never `0`, and is counted separately in the summary
- [x] `p1` - `--baseline` alone (without `--check`) produces a per-scenario regression diff without changing the exit code; a removed/unavailable scenario is surfaced but does not gate
- [x] `p1` - When `--baseline` is given, the `regression` key is always present (a diff object, or an `error` object when the baseline is unusable)
- [x] `p1` - `cfs eval` scores structural compliance via a registry of deterministic checks over each run's manifest and phase frontmatter; any failing check makes the scenario verdict `FAIL` while the per-scenario `score_pct` still reports the fraction of checks passed
- [x] `p1` - A run whose phase files carry no parseable `[phase]` frontmatter scores `UNKNOWN`, never 0; the scorer touches no filesystem and is a pure function of the in-memory run artifacts
