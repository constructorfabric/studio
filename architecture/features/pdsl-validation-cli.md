# Feature: PDSL Validation CLI

- [ ] `p1` - **ID**: `cpt-studio-featstatus-pdsl-validation-cli`

## Table of Contents

1. [1. Feature Context](#1-feature-context)
   - [1. Overview](#1-overview)
   - [2. Purpose](#2-purpose)
   - [3. Requirements](#3-requirements)
   - [4. Principles](#4-principles)
   - [5. Actors](#5-actors)
   - [6. References](#6-references)
2. [2. Actor Flows (CDSL)](#2-actor-flows-cdsl)
   - [Validate PDSL Inputs](#validate-pdsl-inputs)
   - [Inspect PDSL Command Scope](#inspect-pdsl-command-scope)
3. [3. Processes / Business Logic (CDSL)](#3-processes--business-logic-cdsl)
   - [Scan PDSL Sources](#scan-pdsl-sources)
   - [Validate PDSL Blocks](#validate-pdsl-blocks)
   - [Build Validation Summary](#build-validation-summary)
4. [4. States (CDSL)](#4-states-cdsl)
   - [Validation Result Status](#validation-result-status)
5. [5. Definitions of Done](#5-definitions-of-done)
   - [Validate-Only Command Surface](#validate-only-command-surface)
   - [Shared Helper Source Of Truth](#shared-helper-source-of-truth)
   - [Stable Output And Exit Contract](#stable-output-and-exit-contract)
   - [MVP Gates](#mvp-gates)
6. [6. Acceptance Criteria](#6-acceptance-criteria)

## 1. Feature Context

### 1. Overview

Deliver a validate-only MVP for a first-class `cfs pdsl` command family. In v1 the surface area is intentionally limited to `cfs pdsl validate`, which validates PDSL content from `--text`, stdin `-`, or one or more file paths, defaults to human-readable output, and exposes machine-readable JSON only under `--json`.

### 2. Purpose

Provide a deterministic validation path for developers and agents authoring or transforming PDSL without coupling the workflow to scaffold generation. The MVP establishes a stable rule catalog, normalized findings, predictable PASS/FAIL/ERROR semantics, and reusable helper behavior in `studio.utils.pdsl`, while explicitly deferring scaffold and any alias surface such as `cfs validate --pdsl`.

### 3. Requirements

**Requirements**:
- `cpt-studio-fr-core-traceability` - extends deterministic validation coverage to PDSL prompt blocks while preserving file/line-oriented, actionable reports
- `cpt-studio-fr-core-cdsl` - supports agent-authored instruction contracts that need deterministic validation before downstream implementation or review
- `cpt-studio-nfr-security-integrity` - keeps validation read-only and treats input text as data, with no eval, exec, shell execution, or side effects beyond reads and reports
- `cpt-studio-nfr-ci-automation-first` - provides deterministic CLI behavior, stable exit semantics, and JSON output suitable for non-interactive CI usage

### 4. Principles

**Principles**:
- `cpt-studio-principle-determinism-first` - every PDSL validation rule in the MVP is deterministic and local
- `cpt-studio-principle-machine-readable` - `--json` exposes a stable envelope for automated consumers while human output remains the default UI
- `cpt-studio-principle-dry` - `studio.utils.pdsl` is the single production owner of parsing, validation, findings, ordering, and summary semantics
- `cpt-studio-principle-ci-automation-first` - PASS/FAIL/ERROR states and exit behavior are explicit enough for CI gates
- `cpt-studio-principle-zero-harm` - validation never modifies inputs and never emits scaffold, autofix patches, or rewrite templates

### 5. Actors

| Actor | Role in Feature |
|-------|-----------------|
| `cpt-studio-actor-user` | Invokes `cfs pdsl validate` and `cfs pdsl --help` from the CLI |
| `cpt-studio-actor-ai-agent` | Validates generated or transformed PDSL before emitting artifact changes |
| `cpt-studio-actor-ci-pipeline` | Runs deterministic validation as a non-interactive quality gate |

### 6. References

- **PRD**: [PRD.md](../PRD.md)
- **Design**: [DESIGN.md](../DESIGN.md)
- **Dependencies**: `cpt-studio-feature-traceability-validation`

## 2. Actor Flows (CDSL)

### Validate PDSL Inputs

- [x] `p1` - **ID**: `cpt-studio-flow-pdsl-validation-cli-validate-input`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User runs `cfs pdsl validate --text <payload>` and receives PASS, FAIL, or ERROR output for the inline source
- User runs `cfs pdsl validate -` and validates stdin content with the same rules and output contract
- User runs `cfs pdsl validate <file-a> <file-b>` and receives ordered per-source results plus an aggregate summary
- User adds `--json` and receives the stable envelope `{command, ok, summary, results}`

**Error Scenarios**:
- User provides more than one input selector class (`--text`, stdin `-`, file paths) in the same invocation and the command returns ERROR
- A source cannot be read, parsed, or processed and the affected result returns ERROR
- Validation findings exist for one or more sources and the command returns FAIL rather than success

**Input Safety Boundaries**:
- File path inputs are treated as literal local source selectors; the command reads file content as text and reports normalized read errors for inaccessible paths
- Inline, stdin, and file content are always treated as data for parsing and validation; PDSL text is never evaluated, executed, shell-expanded, or used to run commands
- Validation has no side effects beyond reading selected sources and writing output to stdout/stderr; it never modifies input files or emits scaffold/autofix patches

**Steps**:
1. [x] - `p1` - User invokes `cfs pdsl validate` with exactly one selector class from `--text`, stdin `-`, or one-or-more file paths, plus optional `--json` and `--verbose` - `inst-user-validate`
2. [x] - `p1` - Parse CLI arguments and enforce the validate-only command contract with no alias forms outside `cfs pdsl validate` - `inst-parse-args`
3. [x] - `p1` - Normalize selected sources into an ordered input list with stable source labels and source text while treating file paths as literal read targets and all content as non-executable data - `inst-normalize-sources`
4. [x] - `p1` - **FOR EACH** normalized source - `inst-foreach-source`
   1. [x] - `p1` - Extract candidate PDSL blocks and source coordinates using `cpt-studio-algo-pdsl-validation-cli-helper-scan` - `inst-source-scan`
   2. [x] - `p1` - Validate extracted blocks using `cpt-studio-algo-pdsl-validation-cli-helper-validate` - `inst-source-validate`
5. [x] - `p1` - Build aggregate summary and ordered result payload using `cpt-studio-algo-pdsl-validation-cli-helper-summary` - `inst-build-summary`
6. [x] - `p1` - **IF** `--json` is set prepare the stable JSON envelope, otherwise prepare human-readable output; `--verbose` expands payload detail only - `inst-select-output`
7. [x] - `p1` - **IF** any result status is ERROR - `inst-if-error`
   1. [x] - `p1` - **RETURN** overall ERROR with ordered per-source results and non-success exit semantics - `inst-return-error`
8. [x] - `p1` - **ELSE IF** any result status is FAIL - `inst-else-if-fail`
   1. [x] - `p1` - **RETURN** overall FAIL with ordered per-source results and failure exit semantics - `inst-return-fail`
9. [x] - `p1` - **ELSE** - `inst-else-pass`
   1. [x] - `p1` - **RETURN** overall PASS only when every checked source is PASS - `inst-return-pass`

**Supporting**:
- [x] - `p1` - CLI wrappers stay thin: argparse, source reading, and rendering only - `inst-cli-thin-wrapper`
- [x] - `p1` - Source reading never performs command execution, shell expansion, validation-time file mutation, scaffold generation, or autofix patch emission - `inst-input-safety`

### Inspect PDSL Command Scope

- [x] `p1` - **ID**: `cpt-studio-flow-pdsl-validation-cli-command-help`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User runs `cfs pdsl --help` and sees `validate` as the only available subcommand in v1
- Help text explains that scaffold is deferred and that future `cfs pdsl` expansion is outside the MVP boundary

**Error Scenarios**:
- User attempts an unimplemented alias or future-oriented command and receives usage guidance instead of hidden behavior

**Steps**:
1. [x] - `p1` - User invokes `cfs pdsl --help` or an unsupported command in the `cfs pdsl` family - `inst-user-help`
2. [x] - `p1` - Render help output that lists `validate` as the only supported subcommand in v1 - `inst-render-help`
3. [x] - `p1` - State explicitly that scaffold is deferred and aliases such as `cfs validate --pdsl` are not part of the MVP - `inst-state-boundary`
4. [x] - `p1` - **RETURN** exit 0 for help output or ERROR usage guidance for unsupported invocations - `inst-return-help`

## 3. Processes / Business Logic (CDSL)

### Scan PDSL Sources

- [x] `p2` - **ID**: `cpt-studio-algo-pdsl-validation-cli-helper-scan`

**Input**: Normalized source record `{source_path, source_name, selector_kind, text}`

**Output**: Ordered block records `{source, block_index, text, line, column, end_line, end_column}` or source-level extraction errors

**Steps**:
1. [x] - `p1` - Receive normalized source text and stable source metadata from the CLI wrapper - `inst-scan-input`
2. [x] - `p1` - Scan the source in discovery order for candidate PDSL blocks and capture start and end coordinates for each block - `inst-scan-blocks`
3. [x] - `p1` - **IF** no explicit PDSL block delimiters are present - `inst-if-no-delimiters`
   1. [x] - `p1` - Treat the full normalized source text as a single candidate block so direct validation remains available for inline and file inputs - `inst-use-whole-source`
4. [x] - `p1` - Assign deterministic zero-based `block_index` values in the order blocks were discovered - `inst-assign-block-index`
5. [x] - `p1` - **RETURN** ordered block records or a normalized extraction error with source coordinates - `inst-scan-return`

**Supporting**:
- [x] - `p1` - Helper logic lives in `studio.utils.pdsl` and is reused by CLI validation and `cf-pdsl` preflight or postflight hooks that emit or transform PDSL text - `inst-scan-reuse`

### Validate PDSL Blocks

- [x] `p2` - **ID**: `cpt-studio-algo-pdsl-validation-cli-helper-validate`

**Input**: Ordered block records for one source plus verbosity mode

**Output**: Source result `{source, status, findings, errors}`

**Steps**:
1. [x] - `p1` - Load the rule registry from `studio.utils.pdsl` using stable `PDSL100`, `PDSL200`, `PDSL300`, `PDSL400`, and `PDSL500` rule bands - `inst-load-rule-registry`
2. [x] - `p1` - **FOR EACH** block in source order - `inst-foreach-block`
   1. [x] - `p1` - Parse block structure and capture parse or operational failures as normalized source errors - `inst-parse-block`
   2. [x] - `p1` - Run structural checks for fences, starters, keywords, duplicate names, and menu numbering using deterministic local rules only - `inst-run-structural-checks`
   3. [x] - `p1` - Run deterministic local semantic checks, including undefined local `matches()` references, without any cross-file registry lookup - `inst-run-local-semantics`
   4. [x] - `p1` - Normalize every finding with `rule_id`, `severity`, `message`, `source_path`, `block_index`, `line`, `column`, `end_line`, `end_column`, and deterministic `hint`; include `snippet` or `context` only when verbosity requests it - `inst-normalize-findings`
3. [x] - `p1` - Sort findings deterministically by source order, block index, line, column, and rule identifier - `inst-sort-findings`
4. [x] - `p1` - **IF** any invocation, read, parse, or operational errors were captured for the source - `inst-if-source-error`
   1. [x] - `p1` - **RETURN** source result with status ERROR, ordered errors, and retained findings - `inst-return-source-error`
5. [x] - `p1` - **ELSE IF** normalized findings exist - `inst-if-findings`
   1. [x] - `p1` - **RETURN** source result with status FAIL and ordered findings - `inst-return-source-fail`
6. [x] - `p1` - **ELSE** - `inst-else-source-pass`
   1. [x] - `p1` - **RETURN** source result with status PASS and empty findings or errors - `inst-return-source-pass`

**Supporting**:
- [x] - `p1` - `studio.utils.pdsl` remains the sole production owner of parser behavior, validation rules, normalized findings, and summary semantics - `inst-validate-source-of-truth`
- [x] - `p1` - No autofix patches, scaffold text, or rewrite templates are emitted by validation results - `inst-no-scaffold-output`

### Build Validation Summary

- [x] `p2` - **ID**: `cpt-studio-algo-pdsl-validation-cli-helper-summary`

**Input**: Ordered list of per-source validation results plus output mode flags

**Output**: Stable envelope `{command, ok, summary, results}`

**Steps**:
1. [x] - `p1` - Preserve per-source result order exactly as the CLI received the source inputs - `inst-preserve-input-order`
2. [x] - `p1` - Count PASS, FAIL, and ERROR results and derive `ok=true` only when every result status is PASS - `inst-count-statuses`
3. [x] - `p1` - Build a stable summary object with aggregate counts and overall command outcome text - `inst-build-summary-object`
4. [x] - `p1` - **IF** verbose mode is enabled include expanded helper-provided snippets and contexts without changing status, ordering, or rule identifiers - `inst-apply-verbose`
5. [x] - `p1` - **RETURN** the stable envelope with `command`, `ok`, `summary`, and ordered `results` - `inst-return-envelope`

**Supporting**:
- [x] - `p1` - `cf-pdsl` consumers attach or block on helper findings without redefining parsing behavior, finding schema, or success semantics - `inst-summary-cf-pdsl-reuse`

## 4. States (CDSL)

### Validation Result Status

- [x] `p2` - **ID**: `cpt-studio-state-pdsl-validation-cli-result-status`

**States**: NOT_EVALUATED, PASS, FAIL, ERROR

**Initial State**: NOT_EVALUATED

**Transitions**:
1. [x] - `p1` - **FROM** NOT_EVALUATED **TO** ERROR **WHEN** invocation, read, parse, or operational errors exist for a source or the overall command - `inst-state-error`
2. [x] - `p1` - **FROM** NOT_EVALUATED **TO** FAIL **WHEN** no operational error exists and one or more normalized findings are emitted - `inst-state-fail`
3. [x] - `p1` - **FROM** NOT_EVALUATED **TO** PASS **WHEN** no findings or errors are emitted for the evaluated source - `inst-state-pass`

## 5. Definitions of Done

### Validate-Only Command Surface

- [x] `p1` - **ID**: `cpt-studio-dod-pdsl-validation-cli-command-surface`

The system **MUST** expose only `cfs pdsl validate` in the v1 command family, keep `cfs pdsl --help` explicit about current validate-only scope, reject alias forms such as `cfs validate --pdsl`, and keep scaffold outside the implemented MVP surface.

**Implements**:
- `cpt-studio-flow-pdsl-validation-cli-validate-input`
- `cpt-studio-flow-pdsl-validation-cli-command-help`

**Constraints**:
- `cpt-studio-fr-core-traceability`
- `cpt-studio-nfr-ci-automation-first`
- `cpt-studio-principle-zero-harm`

**Touches**:
- CLI command routing for `cfs pdsl validate` and `cfs pdsl --help`
- Human-readable CLI renderer
- JSON CLI renderer

### Shared Helper Source Of Truth

- [ ] `p1` - **ID**: `cpt-studio-dod-pdsl-validation-cli-helper-source-of-truth`

The system **MUST** implement `studio.utils.pdsl` as the only production source of truth for PDSL parsing, structural validation, deterministic local semantic checks, rule registry, normalized findings, ordering, and summary generation. CLI command modules **MUST** remain thin wrappers for argparse, input reading, and rendering. `cf-pdsl` preflight may reuse helper findings broadly, and postflight flows that emit or transform PDSL text **MUST** use the same helper without defining separate rule identifiers or parsing rules.

**Implements**:
- `cpt-studio-algo-pdsl-validation-cli-helper-scan`
- `cpt-studio-algo-pdsl-validation-cli-helper-validate`
- `cpt-studio-algo-pdsl-validation-cli-helper-summary`

**Constraints**:
- `cpt-studio-fr-core-cdsl`
- `cpt-studio-principle-determinism-first`
- `cpt-studio-principle-dry`

**Touches**:
- `studio.utils.pdsl`
- `cf-pdsl` preflight and postflight validation reuse
- CLI command modules that call the helper

### Stable Output And Exit Contract

- [ ] `p1` - **ID**: `cpt-studio-dod-pdsl-validation-cli-output-contract`

The system **MUST** default to human-readable output, emit JSON only under `--json`, treat `--verbose` as payload expansion only, preserve input order for multi-source results, and return success only when every checked source is PASS. The stable JSON envelope **MUST** contain `command`, `ok`, `summary`, and `results`; each result **MUST** contain `source`, `status`, `findings`, and `errors`; each finding **MUST** contain `rule_id`, `severity`, `message`, `source_path`, `block_index`, `line`, `column`, `end_line`, and `end_column`, and may include `snippet`, `context`, and deterministic `hint` when requested or applicable.

**Implements**:
- `cpt-studio-flow-pdsl-validation-cli-validate-input`
- `cpt-studio-algo-pdsl-validation-cli-helper-validate`
- `cpt-studio-algo-pdsl-validation-cli-helper-summary`
- `cpt-studio-state-pdsl-validation-cli-result-status`

**Constraints**:
- `cpt-studio-nfr-ci-automation-first`
- `cpt-studio-principle-machine-readable`
- `cpt-studio-principle-determinism-first`

**Touches**:
- JSON output contract for `cfs pdsl validate --json`
- Human-readable output contract for default CLI output
- Exit code mapping for PASS, FAIL, and ERROR

### MVP Gates

- [ ] `p1` - **ID**: `cpt-studio-dod-pdsl-validation-cli-mvp-gates`

The system **MUST** ship helper unit tests for scanner extraction, structural checks, and local semantic checks; CLI integration tests for `--text`, stdin `-`, single-file, multi-file, human output, and `--json`; PASS/FAIL/ERROR exit semantics coverage; JSON contract or snapshot coverage; deterministic ordering coverage; mixed PASS/FAIL/ERROR multi-file matrix coverage; `cfs pdsl --help` acceptance coverage; non-scaffold-output regression coverage; and `cf-pdsl` reuse tests proving normalized findings and rule identifiers come from `studio.utils.pdsl`.

**Implements**:
- `cpt-studio-flow-pdsl-validation-cli-validate-input`
- `cpt-studio-flow-pdsl-validation-cli-command-help`
- `cpt-studio-algo-pdsl-validation-cli-helper-scan`
- `cpt-studio-algo-pdsl-validation-cli-helper-validate`
- `cpt-studio-algo-pdsl-validation-cli-helper-summary`
- `cpt-studio-state-pdsl-validation-cli-result-status`

**Constraints**:
- `cpt-studio-fr-core-traceability`
- `cpt-studio-fr-core-cdsl`
- `cpt-studio-nfr-security-integrity`
- `cpt-studio-nfr-ci-automation-first`

**Touches**:
- Helper unit tests for `studio.utils.pdsl`
- CLI integration tests for `cfs pdsl validate`
- `cf-pdsl` reuse tests
- JSON contract or snapshot tests

## 6. Acceptance Criteria

- [ ] `cfs pdsl --help` lists `validate` as the only v1 subcommand and states that scaffold is deferred beyond the MVP boundary
- [ ] `cfs pdsl validate` accepts exactly one selector class from `--text`, stdin `-`, or one-or-more file paths and rejects mixed selector usage as ERROR
- [ ] CLI wrappers handle only argument parsing, input reading, and rendering while `studio.utils.pdsl` owns parsing, structural validation, deterministic local semantic checks, rule registry, normalized findings, ordering, and summary generation
- [ ] Validation emits PASS only when every evaluated source has no findings or errors, FAIL when validation findings exist, and ERROR for invocation, read, parse, or operational failures
- [ ] Multi-source validation preserves CLI input order and returns per-source `PASS`, `FAIL`, or `ERROR` status with ordered findings and errors
- [ ] Human-readable output is the default; JSON is emitted only with `--json`; `--verbose` expands payload fields only and does not change status or rule evaluation
- [ ] The JSON envelope is stable and contains `command`, `ok`, `summary`, and `results`, and each result contains `source`, `status`, `findings`, and `errors`
- [ ] Findings use stable rule bands `PDSL100` for fences, `PDSL200` for starters or keywords, `PDSL300` for duplicate names, `PDSL400` for menu numbering, and `PDSL500` for deterministic local semantics
- [ ] Deterministic local semantic checks include undefined local `matches()` references, and cross-file registry lookup remains explicitly deferred from the MVP
- [ ] Validation outputs deterministic hints only and never emit autofix patches, scaffold text, or rewrite templates
- [ ] `cf-pdsl` preflight and applicable postflight flows reuse normalized helper findings and do not define separate parsing rules, rule identifiers, or success semantics
- [ ] File path inputs are read as literal local sources, PDSL content is treated only as data, and validation performs no eval, exec, shell execution, shell expansion, source mutation, scaffold generation, or autofix patch emission
