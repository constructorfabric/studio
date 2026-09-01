# Feature: Spec Coverage

<!-- toc -->

- [1. Feature Context](#1-feature-context)
  - [1. Overview](#1-overview)
  - [2. Purpose](#2-purpose)
  - [3. Actors](#3-actors)
  - [4. References](#4-references)
- [2. Actor Flows (CDSL)](#2-actor-flows-cdsl)
  - [Run Spec Coverage Report](#run-spec-coverage-report)
- [3. Processes / Business Logic (CDSL)](#3-processes--business-logic-cdsl)
  - [Scan Code Coverage](#scan-code-coverage)
  - [Calculate Coverage Metrics](#calculate-coverage-metrics)
  - [Calculate Granularity Score](#calculate-granularity-score)
  - [Generate Coverage Report](#generate-coverage-report)
  - [Assess Semantic Coverage (advisory)](#assess-semantic-coverage-advisory)
- [4. States (CDSL)](#4-states-cdsl)
  - [Coverage Report Lifecycle](#coverage-report-lifecycle)
- [5. Definitions of Done](#5-definitions-of-done)
  - [Coverage Percentage Metric](#coverage-percentage-metric)
  - [Granularity Quality Metric](#granularity-quality-metric)
  - [Coverage Report Output](#coverage-report-output)
- [6. Implementation Modules](#6-implementation-modules)
- [7. Acceptance Criteria](#7-acceptance-criteria)

<!-- /toc -->

- [x] `p1` - **ID**: `cpt-studio-featstatus-spec-coverage`

## 1. Feature Context

- [x] `p1` - `cpt-studio-feature-spec-coverage`

### 1. Overview

Measures how much of a project's codebase is covered by CDSL specification markers (`@cpt-*`), analogous to test coverage reports. Produces two metrics: **coverage percentage** (ratio of spec-covered lines to total lines) and **granularity score** (instruction density — approximately 1 instruction per 10 lines of code). The command outputs a machine-readable JSON report similar to standard `coverage.py` reports, with per-file and summary statistics.

### 2. Purpose

Without spec coverage, teams have no visibility into which parts of the codebase are formally specified and traceable. A file with only a scope marker at the top and bottom appears "covered" but provides no meaningful traceability. The granularity metric catches this anti-pattern by measuring instruction density. Addresses the need for quantitative spec quality assessment beyond binary PASS/FAIL validation.

### 3. Actors

| Actor | Role in Feature |
|-------|-----------------|
| `cpt-studio-actor-user` | Invokes `cfs spec-coverage` from CLI to generate coverage report |
| `cpt-studio-actor-ai-agent` | Uses coverage report to identify unspecified code during reverse-engineering |
| `cpt-studio-actor-ci-pipeline` | Runs spec-coverage as a CI gate to enforce minimum coverage thresholds |

### 4. References

- **PRD**: [PRD.md](../PRD.md) — `cpt-studio-fr-core-traceability`, `cpt-studio-fr-core-cdsl`
- **Design**: [DESIGN.md](../DESIGN.md) — `cpt-studio-component-traceability-engine`, `cpt-studio-component-validator`
- **Dependencies**: `cpt-studio-feature-traceability-validation`

## 2. Actor Flows (CDSL)

### Run Spec Coverage Report

- [x] `p1` - **ID**: `cpt-studio-flow-spec-coverage-report`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User runs `cfs spec-coverage` → all registered codebase files scanned, coverage report generated with per-file and summary statistics
- User runs `cfs spec-coverage --min-coverage 80` → same as above, exit code 2 if coverage below threshold
- User runs `cfs spec-coverage --min-granularity 0.7` → same as above, exit code 2 if granularity below threshold
- User runs `cfs spec-coverage --min-file-granularity 0.3` → same as above, exit code 2 if any **block-traced** file's granularity is below threshold. A file whose coverage rests on a whole-file scope marker scores 0.0 by definition rather than by measurement, so it is reported under its own heading instead of judged against this floor — judging it would make any positive floor reject every re-export module and entry point, which is what made this threshold unusable as a gate

**Error Scenarios**:
- No codebase entries registered → report with `applicable: false` and a hint to configure artifacts.toml; exit code 2 only if a positive threshold was demanded
- No code files found → report with `applicable: false` naming how many registered entries resolved to no files, and 0% coverage

**Steps**:
1. [x] - `p1` - User invokes `cfs spec-coverage [--min-coverage N] [--min-file-coverage N] [--min-granularity N] [--min-file-granularity N] [--verbose] [--semantic]` - `inst-user-spec-coverage`
2. [x] - `p1` - Load project context: studio config, registry, systems, codebase entries - `inst-load-context`
3. [x] - `p1` - Resolve all code files from registered codebase entries - `inst-resolve-code-files`
4. [x] - `p1` - **FOR EACH** code file, scan for `@cpt-*` markers using `cpt-studio-algo-spec-coverage-scan` - `inst-foreach-file`
5. [x] - `p1` - Calculate coverage metrics using `cpt-studio-algo-spec-coverage-metrics` - `inst-calc-metrics`
6. [x] - `p1` - Calculate granularity scores using `cpt-studio-algo-spec-coverage-granularity` - `inst-calc-granularity`
7. [x] - `p1` - Generate report using `cpt-studio-algo-spec-coverage-report` - `inst-gen-report`
8. [x] - `p1` - **IF** any positive threshold flag set AND (metric below threshold OR nothing was assessed) → exit code 2 - `inst-if-threshold`
9. [x] - `p1` - **RETURN** JSON report (summary, per-file stats, uncovered files) - `inst-return-report`

**Supporting**:
- [x] - `p1` - Imports and module setup for spec-coverage command - `inst-coverage-imports`
- [x] - `p1` - Build CLI parser for threshold, system, verbosity, and output flags - `inst-build-parser`
- [x] - `p1` - Collect known system slugs from nested system tree for selector validation - `inst-collect-system-slugs`
- [x] - `p1` - Collect codebase file paths from registered entries and recurse into child systems - `inst-collect-codebase-files`
- [x] - `p1` - Validate selected `--system` values and build unknown-system failure payloads - `inst-validate-systems`
- [x] - `p1` - Filter ignored and out-of-root files before scanning - `inst-filter-ignored-files`
- [x] - `p1` - Build empty coverage result when registry yields no code files - `inst-empty-report`
- [x] - `p1` - Count codebase entries registered by the selected systems and recurse into child systems, including the default all-systems selection, so an unregistered registry is distinguishable from one that resolves to no files - `inst-count-registered-entries`
- [x] - `p1` - Detect which threshold flags demand an enforceable guarantee, ignoring non-positive values that any scope satisfies - `inst-detect-requested-thresholds`
- [x] - `p1` - Apply per-report threshold checks and accumulate failure messages - `inst-apply-thresholds`
- [x] - `p1` - Resolve paths relative to project root for human-readable output - `inst-rel-path`
- [x] - `p1` - Route JSON report to file or terminal UI - `inst-output-report`
- [x] - `p1` - Format uncovered ranges and render human-friendly per-file/status sections - `inst-human-report-helpers`
- [x] - `p1` - Name the files whose coverage rests on a whole-file scope marker, largest first, with their count and total claimed lines - `inst-human-report-claims`
- [x] - `p1` - When `--semantic` is set, run the advisory semantic pass (`cpt-studio-algo-semantic-coverage-pass`) and attach its section to the report **after** status/exit are computed, so it can never gate - `inst-attach-semantic`

## 3. Processes / Business Logic (CDSL)

### Scan Code Coverage

- [x] `p1` - **ID**: `cpt-studio-algo-spec-coverage-scan`

**Input**: Code file path, language configuration

**Output**: `{path, total_lines, covered_lines, covered_ranges, markers, block_markers}`

**Steps**:
1. [x] - `p1` - Read file and count total non-blank, non-comment lines (effective lines) - `inst-scan-count-lines`
2. [x] - `p1` - Scan for `@cpt-algo`, `@cpt-flow`, `@cpt-dod` scope markers (file-level coverage) - `inst-scan-scope-markers`
3. [x] - `p1` - Scan for `@cpt-begin`/`@cpt-end` block markers (range-level coverage) - `inst-scan-block-markers`
4. [x] - `p1` - Calculate covered line ranges: lines between block marker pairs are covered; file-level scope markers cover all lines - `inst-scan-calc-ranges`
5. [x] - `p1` - **RETURN** file coverage record with ranges and marker counts - `inst-scan-return`
6. [x] - `p1` - Define coverage data model: FileCoverage and CoverageReport dataclasses, imports - `inst-scan-datamodel`
7. [x] - `p1` - Helper functions: blank/comment line detection, contiguous range building - `inst-scan-helpers`
8. [x] - `p1` - File scan initialization: read file, detect markers in loop, count scope/block markers - `inst-scan-init`

### Calculate Coverage Metrics

- [x] `p1` - **ID**: `cpt-studio-algo-spec-coverage-metrics`

**Input**: List of per-file coverage records

**Output**: `{total_lines, covered_lines, coverage_pct, per_file_coverage}`

**Steps**:
1. [x] - `p1` - Sum total effective lines across all files - `inst-metrics-sum-total`
2. [x] - `p1` - Sum covered lines across all files - `inst-metrics-sum-covered`
3. [x] - `p1` - Calculate overall coverage percentage: `covered / total * 100` - `inst-metrics-calc-pct`
4. [x] - `p1` - **RETURN** metrics with per-file breakdown - `inst-metrics-return`

### Calculate Granularity Score

- [x] `p1` - **ID**: `cpt-studio-algo-spec-coverage-granularity`

**Input**: List of per-file coverage records

**Output**: `{granularity_score, per_file_granularity, flagged_files}`

A file with good granularity has approximately 1 CDSL instruction (`@cpt-begin`/`@cpt-end` block) per 10 lines of code. Files with only scope markers at file level (no block markers) get a granularity score of 0 even if nominally 100% covered. This prevents the anti-pattern of wrapping an entire file with a single begin/end pair.

**Steps**:
1. [x] - `p1` - **FOR EACH** covered file - `inst-gran-foreach`
2. [x] - `p1` - Count block marker pairs (instruction-level markers) in file - `inst-gran-count-blocks`
3. [x] - `p1` - Calculate ideal block count: `effective_lines / 10` - `inst-gran-ideal`
4. [x] - `p1` - Calculate file granularity: `min(1.0, actual_blocks / ideal_blocks)` — capped at 1.0 - `inst-gran-calc`
5. [x] - `p1` - Flag files where granularity < 0.5 (fewer than 1 instruction per 20 lines) - `inst-gran-flag`
6. [x] - `p1` - Calculate overall granularity: weighted average across covered files (weighted by line count) - `inst-gran-overall`
7. [x] - `p1` - **RETURN** granularity scores with flagged files - `inst-gran-return`

### Generate Coverage Report

- [x] `p1` - **ID**: `cpt-studio-algo-spec-coverage-report`

**Input**: Coverage metrics, granularity scores, verbosity flag

**Output**: JSON report matching `coverage.py` structure

**Steps**:
1. [x] - `p1` - Build summary section: total files, covered files, coverage %, granularity score - `inst-report-summary`
2. [x] - `p1` - Build per-file section: path, total lines, covered lines, coverage %, granularity, uncovered ranges - `inst-report-per-file`
3. [x] - `p1` - **IF** verbose, include marker details per file - `inst-report-verbose`
4. [x] - `p1` - **RETURN** formatted JSON report - `inst-report-return`

**Supporting**:
- [x] - `p1` - Report function signature and relative path helper - `inst-report-datamodel`

### Assess Semantic Coverage (advisory)

- [x] `p1` - **ID**: `cpt-studio-algo-semantic-coverage-pass`

**Input**: registered artifacts (for id→doc resolution), the scanned code files, the coverage report (for scope)

**Output**: an advisory `semantic` report section — never affects status/exit. Success shape: `assessed` / `presumed_covered` / `unjudgeable[]` / `findings[]` / `skipped_excluded` / `schema_version` / `advisory`. If the pass raises, it degrades to `{advisory: true, error: <message>}` instead.

**Steps**:
1. [x] - `p1` - Build the id→declaring-artifact map from cpt definition hits across the registered artifacts - `inst-scov-defmap`
2. [x] - `p1` - Build one pairing per marked block: code = the block's lines, requirement = the algo declaration resolved from the block's id (unjudgeable when unresolved) - `inst-scov-pairings`
3. [x] - `p1` - Run the advisory engine (`assess`) over the pairings, passing the coverage report for scope, and serialise the result as the `semantic` section (`advisory: true`) - `inst-scov-run`
4. [x] - `p1` - Render a one-line advisory human summary (counts + weak/wrong tally) - `inst-scov-summary`

**Supporting**:
- [x] - `p1` - Module imports and setup for the semantic-coverage pass - `inst-scov-imports`

## 4. States (CDSL)

### Coverage Report Lifecycle

- [x] `p1` - **ID**: `cpt-studio-state-spec-coverage-report`

**States**: NOT_RUN, COVERED, PARTIAL, UNCOVERED

**Transitions**:
1. [x] - `p1` - **FROM** NOT_RUN **TO** COVERED **WHEN** coverage ≥ threshold AND granularity ≥ threshold - `inst-state-covered`
2. [x] - `p1` - **FROM** NOT_RUN **TO** PARTIAL **WHEN** coverage > 0 but below threshold OR granularity below threshold - `inst-state-partial`
3. [x] - `p1` - **FROM** NOT_RUN **TO** UNCOVERED **WHEN** no CDSL markers found in any code file - `inst-state-uncovered`

## 5. Definitions of Done

### Coverage Percentage Metric

- [x] `p1` - **ID**: `cpt-studio-dod-spec-coverage-percentage`

The system **MUST** calculate what percentage of effective code lines (non-blank, non-comment) are within the scope of at least one CDSL marker. Lines between `@cpt-begin`/`@cpt-end` pairs are covered. Lines in files with only scope markers (`@cpt-algo`, `@cpt-flow`) are covered at file level. The metric **MUST** be reported as a float 0.0–100.0.

**Implements**:
- `cpt-studio-algo-spec-coverage-scan`
- `cpt-studio-algo-spec-coverage-metrics`

**Covers (PRD)**:
- `cpt-studio-fr-core-traceability`

**Covers (DESIGN)**:
- `cpt-studio-component-traceability-engine`

### Granularity Quality Metric

- [x] `p1` - **ID**: `cpt-studio-dod-spec-coverage-granularity`

The system **MUST** calculate instruction density per covered file: `min(1.0, block_marker_count / (effective_lines / 10))`. Files with only scope markers and no block markers **MUST** receive granularity 0.0. The overall granularity **MUST** be the line-weighted average across covered files. Files with granularity < 0.5 **MUST** be flagged in the report.

**Implements**:
- `cpt-studio-algo-spec-coverage-granularity`

**Covers (PRD)**:
- `cpt-studio-fr-core-cdsl`

**Covers (DESIGN)**:
- `cpt-studio-component-traceability-engine`

### Coverage Report Output

- [x] `p1` - **ID**: `cpt-studio-dod-spec-coverage-report`

The system **MUST** output a JSON report with: summary (total files, covered files, coverage %, granularity score), per-file statistics (path, total lines, covered lines, coverage %, granularity, uncovered line ranges), and list of completely uncovered files. The report format **MUST** mirror `coverage.py` JSON output structure. The report **MUST** state whether there was anything to assess, so a scope that yielded no code files is distinguishable from a fully covered one. Exit code 0 when at or above thresholds, 2 when below or when a positive threshold was demanded over a scope that could not be assessed.

**Implements**:
- `cpt-studio-flow-spec-coverage-report`
- `cpt-studio-algo-spec-coverage-report`

**Covers (PRD)**:
- `cpt-studio-fr-core-traceability`

**Covers (DESIGN)**:
- `cpt-studio-component-validator`

## 6. Implementation Modules

| Module | Path | Responsibility |
|--------|------|----------------|
| Spec Coverage Command | `skills/.../commands/spec_coverage.py` | CLI entry point, argument parsing, threshold checks |
| Coverage Scanner | `skills/.../utils/coverage.py` | Code file scanning, line counting, marker detection |
| Coverage Metrics | `skills/.../utils/coverage.py` | Coverage % and granularity calculation |
| Report Generator | `skills/.../utils/coverage.py` | JSON report assembly |
| Codebase Utils | `skills/.../utils/codebase.py` | Existing code scanning infrastructure (reused) |
| Language Config | `skills/.../utils/language_config.py` | Language-specific comment patterns (reused) |
| Semantic Coverage Pass | `skills/.../utils/semantic_coverage.py` | Advisory: build pairings, run the semantic engine, serialise the `semantic` section (never gates) |

## 7. Acceptance Criteria

- [x] `cfs spec-coverage` scans all registered codebase files and produces JSON report
- [x] Coverage percentage correctly identifies lines within `@cpt-begin`/`@cpt-end` blocks
- [x] Scope-only files (no block markers) are reported with granularity 0.0
- [x] Granularity metric correctly penalizes files with few instructions relative to their size
- [x] `--min-coverage N` flag causes exit code 2 when coverage is below threshold
- [x] `--min-granularity N` flag causes exit code 2 when granularity is below threshold
- [x] `--min-file-granularity N` flag causes exit code 2 when any block-traced file's granularity is below threshold; files whose coverage rests on a whole-file scope marker are outside this floor and are listed under "Whole-file scope claims" instead
- [x] Whole-file scope claims are reported with their count, total claimed lines, and paths ordered largest first, so an untraced claim is visible rather than averaged away
- [x] `--min-file-coverage N` flag causes exit code 2 when any file's coverage is below threshold
- [x] `--verbose` flag includes per-file marker details in report
- [x] Report format mirrors `coverage.py` JSON structure (summary + per-file)
- [x] Scanning completes in ≤ 5 seconds for typical repositories
- [x] An empty scope reports `applicable: false` and says why, on both the JSON and human surfaces
- [x] A positive `--min-*` threshold over an empty scope exits 2; a non-positive one exits 0
- [x] JSON mode emits valid JSON to stdout and human mode emits formatted text, with exit codes 0/1/2 on both
