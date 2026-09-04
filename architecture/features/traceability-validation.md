# Feature: Traceability & Validation

<!-- toc -->

- [1. Feature Context](#1-feature-context)
  - [1. Overview](#1-overview)
  - [2. Purpose](#2-purpose)
  - [3. Actors](#3-actors)
  - [4. References](#4-references)
- [2. Actor Flows (CDSL)](#2-actor-flows-cdsl)
  - [Validate Artifacts](#validate-artifacts)
  - [Check Language](#check-language)
  - [Query Traceability](#query-traceability)
- [3. Processes / Business Logic (CDSL)](#3-processes--business-logic-cdsl)
  - [Scan Artifact IDs](#scan-artifact-ids)
  - [Scan CDSL Instructions](#scan-cdsl-instructions)
  - [Validate Artifact Structure](#validate-artifact-structure)
  - [Cross-Validate Artifacts](#cross-validate-artifacts)
  - [Scan Code Markers](#scan-code-markers)
  - [Cross-Validate Code](#cross-validate-code)
  - [List ID Kinds](#list-id-kinds)
  - [Validate TOC](#validate-toc)
  - [TOC Utilities](#toc-utilities)
  - [Document Index](#document-index)
  - [TF-IDF Scoring](#tf-idf-scoring)
  - [OKF Bundle](#okf-bundle)
  - [Atomic File I/O](#atomic-file-io)
  - [Heading-Nav Search](#heading-nav-search)
  - [JIT-Retrieval Cascade](#jit-retrieval-cascade)
  - [Read Gate](#read-gate)
  - [Markdown Parsing Utilities](#markdown-parsing-utilities)
  - [Fixing Prompt Enrichment](#fixing-prompt-enrichment)
  - [Headings Contract Validation](#headings-contract-validation)
  - [Load Constraints](#load-constraints)
  - [Content Language Scan](#content-language-scan)
  - [Check Language Scan Execution](#check-language-scan-execution)
  - [Language Configuration](#language-configuration)
- [4. States (CDSL)](#4-states-cdsl)
  - [Validation Report Lifecycle](#validation-report-lifecycle)
- [5. Definitions of Done](#5-definitions-of-done)
  - [Artifact Structural Validation](#artifact-structural-validation)
  - [Cross-Artifact Reference Validation](#cross-artifact-reference-validation)
  - [Code Traceability Validation](#code-traceability-validation)
  - [Traceability Query Commands](#traceability-query-commands)
  - [CDSL Instruction Tracking](#cdsl-instruction-tracking)
- [6. Implementation Modules](#6-implementation-modules)
- [7. Acceptance Criteria](#7-acceptance-criteria)

<!-- /toc -->

- [ ] `p1` - **ID**: `cpt-studio-featstatus-traceability-validation`

## 1. Feature Context

- [ ] `p1` - `cpt-studio-feature-traceability-validation`

### 1. Overview

Deterministic quality gate that scans artifacts for ID definitions and references, scans code for `@cpt-*` traceability markers, validates structural contracts and cross-references, and provides query commands for navigating the ID graph. All checks are single-pass, stdlib-only, and produce machine-readable JSON reports with file paths, line numbers, and actionable fixing prompts.

### 2. Purpose

Catches structural and traceability issues that AI agents miss or hallucinate — without relying on an LLM. Ensures that every design element has a unique ID, every reference resolves to a definition, every checked reference implies a checked definition, and every `to_code` ID has a matching code marker. Addresses PRD requirements for ID and traceability (`cpt-studio-fr-core-traceability`) and CDSL instruction tracking (`cpt-studio-fr-core-cdsl`). Artifact validation and cross-artifact consistency capabilities are provided generically by the core Validator for any installed kit.

### 3. Actors

| Actor | Role in Feature |
|-------|-----------------|
| `cpt-studio-actor-user` | Invokes validation and traceability query commands from CLI |
| `cpt-studio-actor-ai-agent` | Invokes validation after artifact/code generation; uses query commands for navigation |
| `cpt-studio-actor-ci-pipeline` | Runs validation as a CI gate to enforce quality floor |

### 4. References

- **PRD**: [PRD.md](../PRD.md) — `cpt-studio-fr-core-traceability`, `cpt-studio-fr-core-cdsl`
- **Design**: [DESIGN.md](../DESIGN.md) — `cpt-studio-component-validator`, `cpt-studio-component-traceability-engine`
- **Specs**: [traceability.md](../specs/traceability.md), [CDSL.md](../specs/CDSL.md), [constraints.md](../specs/kit/constraints.md)
- **Dependencies**: `cpt-studio-feature-core-infra`

## 2. Actor Flows (CDSL)

### Validate Artifacts

- [ ] `p1` - **ID**: `cpt-studio-flow-traceability-validation-validate`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User runs `cfs validate` → all registered artifacts validated, cross-references checked, code traceability verified, PASS with coverage report
- User runs `cfs validate --artifact <path>` → single artifact validated against its constraints, cross-references checked against all artifacts

**Error Scenarios**:
- Artifact not found in registry → ERROR with message
- Template structure mismatch → FAIL with heading contract details
- Cross-reference to undefined ID → FAIL with definition hint
- Code marker references non-existent artifact ID → FAIL with orphan details
- Codebase entry registered with FULL traceability but resolving to no files → WARN naming the entry, so a run that checked nothing says so
- Checked `to_code = true` ID with no code marker anywhere → FAIL, independent of how many files the scan resolved
- No checked `to_code = true` ID and no code → PASS; nothing is claimed, so nothing is owed

**Steps**:
1. [x] - `p1` - User invokes `cfs validate [--artifact <path>] [--skip-code] [--verbose]` - `inst-user-validate`
2. [x] - `p1` - Load project context: studio config, registry, systems, kits, constraints - `inst-load-context`
3. [x] - `p1` - Resolve artifacts to validate: if `--artifact` specified resolve single artifact from registry, otherwise collect all registered Studio-format artifacts - `inst-resolve-artifacts`
4. [x] - `p1` - **IF** registry-level errors detected **RETURN** FAIL report immediately - `inst-if-registry-fail`
5. [x] - `p1` - Run self-check: validate kit examples against templates to ensure kit integrity - `inst-self-check`
6. [ ] - `p1` - **FOR EACH** kit: resolve resource paths — for manifest-driven kits, resolve constraints, templates, and examples from resource bindings in `core.toml`; for legacy kits, use default directory structure - `inst-resolve-kit-resources`
7. [x] - `p1` - **FOR EACH** artifact to validate - `inst-foreach-artifact`
   1. [x] - `p1` - Load kind-specific constraints from kit (using resolved resource paths) - `inst-load-constraints`
   2. [x] - `p1` - Validate artifact structure using `cpt-studio-algo-traceability-validation-validate-structure` - `inst-validate-structure`
7. [x] - `p1` - **IF** per-artifact errors exist **RETURN** FAIL report (stop before cross-validation) - `inst-if-structure-fail`
8. [x] - `p1` - Cross-validate references across all artifacts using `cpt-studio-algo-traceability-validation-cross-validate` - `inst-cross-validate`
9. [x] - `p1` - **IF** `--skip-code` is not set, validate code traceability using `cpt-studio-algo-traceability-validation-cross-validate-code` - `inst-if-code`
10. [x] - `p1` - Enrich errors with fixing prompts for LLM agents - `inst-enrich-errors`
11. [x] - `p1` - **RETURN** JSON report (status, artifact count, error/warning counts, coverage stats, next step hint) - `inst-return-report`

**Supporting**:
- [x] - `p1` - Imports and module setup for validate command - `inst-validate-imports`
- [x] - `p1` - Internal helpers: attach issue to artifact report, enrich target artifact paths, find artifact in system, suggest path from autodetect - `inst-validate-helpers`
- [x] - `p1` - Human-friendly formatter: issue location, issue formatting, validate report display - `inst-validate-format`
- [x] - `p1` - Parse validate CLI arguments and merge kit-defined known kinds into the active validation context - `inst-validate-cli-setup`
- [x] - `p1` - Build the validate session: load context, collect workspace config errors, and run the validate-kits self-check gate - `inst-validate-session`
- [x] - `p1` - Emit validate results to stdout or file output, including the empty-registry fast path - `inst-validate-output`
- [x] - `p1` - Resolve explicit or registry-derived artifact targets for validation - `inst-validate-artifact-resolution`
- [x] - `p1` - Resolve per-artifact constraints and emit early registry-level failures before downstream validation - `inst-validate-constraint-resolution`
- [x] - `p1` - Build per-artifact validate reports, traceability counts, and aggregated issue attachments - `inst-validate-artifact-report`
- [x] - `p1` - Build the full artifact set used for cross-validation, including eligible cross-repo workspace artifacts - `inst-validate-cross-context`
- [x] - `p1` - Collect reachable cross-repo workspace artifacts as reference-only validation context, skipping unreachable, duplicate, and non-artifact sources - `inst-validate-cross-repo-artifacts`
- [x] - `p1` - Run cross-artifact validation and merge only issues that apply to the actively validated artifacts - `inst-validate-cross-run`
- [x] - `p1` - Resolve code scan targets and collect code marker state from configured codebase entries - `inst-validate-code-scan`
- [x] - `p1` - Execute recursive system code scanning and strict code cross-validation against artifact expectations - `inst-validate-code-run`
- [x] - `p1` - Warn for each FULL codebase entry that is registered but resolves to no files, so a run that checked nothing says so - `inst-warn-empty-codebase-entry`
- [x] - `p1` - Build traceability lookup indexes for artifact paths, FULL-traceability IDs, and reference coverage - `inst-validate-traceability-index`
- [x] - `p1` - Apply fallback reference coverage rules for unconstrained artifact kinds - `inst-validate-reference-coverage`
- [x] - `p1` - Load language-validation configuration from workspace settings - `inst-validate-language-config`
- [x] - `p1` - Scan artifact content for language-policy violations - `inst-validate-language-scan`
- [x] - `p1` - Run artifact language validation across all selected markdown artifacts - `inst-validate-language-run`
- [x] - `p1` - Format issue-location, header, and extra-field details for human validate output - `inst-validate-issue-format`

### Check Language

- [x] `p1` - **ID**: `cpt-studio-flow-traceability-validation-check-language`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User runs `cfs check-language` → all .md artifacts scanned for disallowed Unicode characters, PASS if none found
- User runs `cfs check-language --languages en,ru <path>` → specified path scanned with given language policy
- User runs `cfs check-language --exclude "translations/**"` → matching paths skipped, skipped count reported
- File contains `<!-- cpt-lang: ignore -->` anywhere → file is skipped entirely by the scanner

**Error Scenarios**:
- Unknown language code passed via `--languages` → ERROR exit code 1
- Specified path does not exist → ERROR exit code 1
- Violations found → FAIL exit code 2

**Steps**:
1. [x] - `p1` - User invokes `cfs check-language [paths...] [--languages CODES] [--ignore PATTERN] [--quiet]` - `inst-user-check-language`
2. [x] - `p1` - Build the command parser and parse CLI arguments into the active check-language request - `inst-check-lang-parse-args`
3. [x] - `p1` - Execute the scan pipeline using `cpt-studio-algo-traceability-validation-check-language-scan` - `inst-check-lang-run-scan`
4. [x] - `p1` - **IF** argument, workspace-config, path, or scanner setup fails, **RETURN** ERROR result with message - `inst-check-lang-error`
5. [x] - `p1` - **IF** no violations are found, build PASS result with allowed languages and scanned file count - `inst-check-lang-pass`
6. [x] - `p1` - **ELSE** build FAIL result with grouped violations, file count, and violation count - `inst-check-lang-fail`
7. [x] - `p1` - Emit machine-readable result with human-friendly output for the selected status and exit code - `inst-check-lang-human-output`

**Supporting**:
- [x] - `p1` - Imports, argument parsing setup, and module-level constants - `inst-check-lang-imports`
- [x] - `p1` - Workspace-config readers and default-root fallback helpers - `inst-check-lang-support`

### Query Traceability

- [x] `p1` - **ID**: `cpt-studio-flow-traceability-validation-query`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User runs `cfs list-ids` → all ID definitions listed with kind, file, line, checked status
- User runs `cfs where-defined --id <id>` → definition location returned with file path and line
- User runs `cfs where-used --id <id>` → all reference locations returned across artifacts and code
- User runs `cfs get-content --id <id>` → content block under the ID heading returned

**Error Scenarios**:
- ID not found in any artifact → empty result with exit code 2

**Steps**:
1. [x] - `p1` - User invokes one of: `list-ids [--kind K] [--pattern P]`, `where-defined --id <id>`, `where-used --id <id>`, `get-content --id <id>` - `inst-user-query`
2. [x] - `p1` - Load project context and resolve all registered artifacts - `inst-query-load-context`
3. [x] - `p1` - Scan all artifacts using `cpt-studio-algo-traceability-validation-scan-ids` to build ID index - `inst-scan-all`
4. [x] - `p1` - **IF** `list-ids --include-code`: scan codebase files for marker references - `inst-if-list-code`
5. [x] - `p1` - **IF** `list-ids`: filter index by `--kind` and `--pattern`, return definitions - `inst-if-list`
6. [x] - `p1` - **IF** `where-defined`: find definition entries for the given ID - `inst-if-where-def`
7. [x] - `p1` - **IF** `where-used`: find reference entries for the given ID across artifacts and code - `inst-if-where-used`
8. [x] - `p1` - **IF** `get-content`: locate ID definition, extract content block from heading scope - `inst-if-get-content`
9. [x] - `p1` - **RETURN** JSON result - `inst-return-query`

**Supporting**:
- [x] - `p1` - Imports and module setup for query commands (list-ids, where-defined, where-used) - `inst-query-imports`
- [x] - `p1` - Resolve the code files one registered codebase entry covers, applying the shared exclusion policy and returning how many candidates were excluded - `inst-query-resolve-entry-files`
- [x] - `p1` - Refuse a candidate that is a symlink or resolves outside the project root, so a link cannot re-open an excluded tree - `inst-query-escapes-project`
- [x] - `p1` - Argument parsing, context resolution, and artifact collection for query commands - `inst-query-resolve`
- [x] - `p1` - Deduplicate scan hits per ID, preferring a definition record and surfacing conflicting duplicate definitions - `inst-scan-dedupe`
- [x] - `p1` - Human-friendly formatters for list-ids, where-defined, and where-used output - `inst-query-format`

## 3. Processes / Business Logic (CDSL)

### Scan Artifact IDs

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-scan-ids`

**Input**: Path to a Markdown artifact file

**Output**: List of ID hits: `{id, line, type (definition|reference), checked, has_task, has_priority, priority}`

**Steps**:
1. [x] - `p1` - Read file as UTF-8 lines - `inst-read-file`
2. [x] - `p1` - **FOR EACH** line (skipping fenced code blocks) - `inst-foreach-line`
   1. [x] - `p1` - Match ID definition pattern: `**ID**: \`cpt-...\`` with optional checkbox and priority - `inst-match-def`
   2. [x] - `p1` - **IF** definition matched, extract id, checked, has_task, priority and append as definition hit - `inst-if-def`
   3. [x] - `p1` - **ELSE** match standalone reference pattern: `\`cpt-...\`` with optional checkbox - `inst-match-ref`
   4. [x] - `p1` - **ELSE** scan for inline backticked `cpt-*` references - `inst-match-inline`
3. [x] - `p1` - **RETURN** ordered list of hits - `inst-return-hits`
4. [x] - `p1` - Parse a `cpt-{system}-{kind}-{slug}` identifier: extract system, kind, slug with composite ID support - `inst-parse-cpt`

**Supporting**:
- [x] - `p1` - Imports, regex constants (ID definition, reference, backtick, heading, fence patterns), and ID normalization helper - `inst-scan-ids-datamodel`
- [x] - `p1` - Heading-by-line index builder for document scope resolution - `inst-scan-ids-headings`
- [x] - `p1` - Content scoped extraction: hash-fence blocks, heading scopes, ID-definition scopes - `inst-scan-ids-get-content`
- [x] - `p1` - File I/O utilities: safe text reader, text file iterator, relative path converter - `inst-scan-ids-file-utils`
- [x] - `p1` - Wrapper function for `parse_cpt` identifier parser - `inst-parse-cpt-fn`

### Scan CDSL Instructions

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-scan-cdsl`

**Input**: Path to a Markdown artifact file

**Output**: List of CDSL instruction records: `{parent_id, inst, checked, line, priority}`

**Steps**:
1. [x] - `p1` - Read file as UTF-8 lines - `inst-read-file`
2. [x] - `p1` - Track current parent ID by scanning ID definitions at heading level - `inst-track-parent`
3. [x] - `p1` - **FOR EACH** line matching CDSL instruction pattern (numbered list item with `inst-{slug}` suffix) - `inst-foreach-cdsl`
   1. [x] - `p1` - Extract checked status, priority, instruction slug - `inst-extract-inst`
   2. [x] - `p1` - Associate with current parent ID - `inst-associate-parent`
4. [x] - `p1` - **RETURN** list of instruction records - `inst-return-cdsl`

**Supporting**:
- [x] - `p1` - CDSL line regex and phase number parsing constants - `inst-scan-cdsl-datamodel`

### Validate Artifact Structure

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-validate-structure`

**Input**: Artifact path, artifact kind, kind-specific constraints, registered systems

**Output**: `{errors, warnings}` lists

**Steps**:
1. [x] - `p1` - **IF** constraints have headings contract, validate heading patterns (required sections, levels, ordering) - `inst-check-headings`
2. [x] - `p1` - **IF** headings errors exist **RETURN** early (IDs depend on correct structure) - `inst-if-headings-fail`
3. [x] - `p1` - Scan IDs using `cpt-studio-algo-traceability-validation-scan-ids` - `inst-scan-ids`
4. [x] - `p1` - Scan CDSL instructions using `cpt-studio-algo-traceability-validation-scan-cdsl` - `inst-scan-cdsl`
5. [x] - `p1` - **FOR EACH** CDSL step where parent ID is checked but step is unchecked - `inst-foreach-cdsl-mismatch`
   1. [x] - `p1` - Emit error: CDSL step unchecked but parent already checked - `inst-emit-cdsl-error`
6. [x] - `p1` - **FOR EACH** parent-child ID pair (heading scope) - `inst-foreach-parent-child`
   1. [x] - `p1` - **IF** all children checked AND parent unchecked, emit error - `inst-if-all-done-parent-not`
   2. [x] - `p1` - **IF** parent checked AND any child unchecked, emit error - `inst-if-parent-done-child-not`
7. [x] - `p1` - Validate ID format and heading scoping per constraints - `inst-validate-id-format`
8. [x] - `p1` - **FOR EACH** CDSL step candidate item (numbered/dash item inside a `**Steps**:` or `**Transitions**:` block, with continuation lines joined) - `inst-foreach-cdsl-candidate`
   1. [x] - `p1` - **IF** the checkbox, phase token, or inst-id token is missing, emit missing-token warnings (CDSL.md S.3/S.4/S.5) and an incomplete-step-line warning (CO.4) - `inst-if-cdsl-missing-token`
   2. [x] - `p1` - **IF** the step's description reads like code rather than plain English, emit the matching CDSL.md rule errors (S.6/CL.3, S.7, CL.2, CL.1/CL.4) - `inst-if-cdsl-prohibited-syntax`
   3. [x] - `p1` - **IF** an `inst-{id}` repeats under the same parent ID within a `**Steps**:`/`**Transitions**:` block, emit duplicate-instruction-id error (CO.5) - `inst-if-cdsl-duplicate-inst`
   4. [x] - `p1` - **IF** the step contains an unresolved placeholder marker, emit placeholder error (CO.6) - `inst-if-cdsl-placeholder`
9. [x] - `p1` - **RETURN** accumulated errors and warnings - `inst-return-structure`

**Supporting**:
- [x] - `p1` - Imports, dataclasses (ReferenceRule, HeadingConstraint, IdConstraint, ArtifactKindConstraints, KitConstraints, ArtifactRecord, ParsedStudioId), error factory, and optional-bool parser - `inst-structure-datamodel`
- [x] - `p1` - Entry point for `validate_artifact_file`: load constraints, dispatch validation phases - `inst-check-ids-entry`
- [x] - `p1` - Helper functions for task/priority and ID/heading constraint validation - `inst-check-ids-helpers`
- [x] - `p1` - TOC validation phase within artifact validation - `inst-check-toc`
- [x] - `p1` - Build definitions-by-ID index from scanned artifact IDs - `inst-build-defs-index`
- [x] - `p1` - Heading context resolution for CDSL instruction line matching - `inst-check-cdsl-heading-ctx`
- [x] - `p1` - `constraint_hint`: generate human-readable constraint hint string from an `IdConstraint` - `inst-constraint-hint`
- [x] - `p1` - `normalize_heading_id_for_check`: strip numbering prefix and canonicalize heading text for matching - `inst-normalize-heading-id`
- [x] - `p1` - `validate_task_priority`: check task-checkbox and priority-marker presence/prohibition against constraints - `inst-validate-task-priority`
- [x] - `p1` - `validate_id_heading_constraint`: verify an ID definition sits under an allowed heading pattern - `inst-validate-id-heading-constraint`
- [x] - `p1` - `validate_id_format` kind-hint branch: emit DISALLOWED_KIND / MISSING_KIND errors per constraint - `inst-validate-id-kind-hint`
- [x] - `p1` - `validate_id_format` heading-description branch: emit WRONG_HEADING error when ID is under wrong heading - `inst-validate-id-heading-desc`
- [x] - `p1` - `validate_id_format` system-match branch: emit WRONG_SYSTEM error for IDs with unexpected system prefix - `inst-validate-id-match-system`
- [x] - `p1` - `validate_id_format` composite-nested branch: handle nested IDs within composite parent scopes - `inst-validate-id-composite-nested`
- [x] - `p1` - `validate_id_format` kind-extractor: parse kind token from ID slug for constraint lookup - `inst-validate-id-extract-kind`
- [x] - `p1` - `validate_id_format` definitions loop: iterate all scanned ID definitions and dispatch per-ID checks - `inst-validate-id-defs-loop`
- [x] - `p1` - `validate_id_format` required-check: emit MISSING_REQUIRED_KIND error for required kinds absent from artifact - `inst-validate-id-required-check`
- [x] - `p1` - `_validate_cdsl_structure`: detect CDSL step candidates, classify missing tokens, prohibited syntax, duplicate inst-ids, and placeholders per CDSL.md's FAIL rules - `inst-validate-cdsl-structure`

### Cross-Validate Artifacts

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-cross-validate`

**Input**: List of all artifact records (path, kind, constraints)

**Output**: `{errors, warnings}` lists

**Steps**:
1. [x] - `p1` - Scan all artifacts to build definition index (`defs_by_id`) and reference index (`refs_by_id`) - `inst-build-index`
2. [x] - `p1` - **FOR EACH** ID with definitions in multiple different artifact files, emit error: duplicate definition listing conflicting files - `inst-duplicate-defs`
3. [x] - `p1` - **FOR EACH** reference to an internal-system ID - `inst-foreach-ref`
   1. [x] - `p1` - **IF** no matching definition exists, emit error: reference to undefined ID - `inst-if-no-def`
4. [x] - `p1` - **FOR EACH** reference with checked task marker - `inst-foreach-checked-ref`
   1. [x] - `p1` - **IF** corresponding definition has task marker AND is unchecked, emit error: ref done but def not done - `inst-if-ref-done-def-not`
5. [x] - `p1` - **FOR EACH** definition with checked task marker - `inst-foreach-checked-def`
   1. [x] - `p1` - **IF** any task-tracked reference is unchecked, emit error: def done but ref not done - `inst-if-def-done-ref-not`
6. [x] - `p1` - Enforce coverage rules from constraints (required cross-references between artifact kinds) - `inst-enforce-coverage`
7. [x] - `p1` - **RETURN** accumulated errors and warnings - `inst-return-cross`

**Supporting**:
- [x] - `p1` - Setup helpers: system matcher, kind extractor, external-system detector, heading-info builder, constraint indexing - `inst-cross-datamodel`
- [x] - `p1` - `cross_datamodel` constraints-index builder: map system→kind→ArtifactKindConstraints for fast lookup - `inst-cross-build-constraints-index`
- [x] - `p1` - `cross_datamodel` kind-tokens collector: aggregate all ID kind tokens seen across artifacts - `inst-cross-collect-kind-tokens`
- [x] - `p1` - `cross_datamodel` system-matcher helper: check whether an ID's system prefix matches a registered system - `inst-cross-match-system`
- [x] - `p1` - `cross_datamodel` kind-extractor helper: parse kind token from a `cpt-{sys}-{kind}-{slug}` ID string - `inst-cross-extract-kind`
- [x] - `p1` - `cross_datamodel` external-ref detector: determine whether a reference ID belongs to an external system - `inst-cross-external-ref`
- [x] - `p1` - `cross_datamodel` headings-info builder: produce per-artifact heading context map for coverage rules - `inst-cross-headings-info`
- [x] - `p1` - `enforce_coverage` reference-coverage rules loop: check required cross-references between artifact kinds per constraint - `inst-cross-ref-coverage-rules`

### Scan Code Markers

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-scan-code`

**Input**: Path to a code file

**Output**: Parsed code file: scope markers, block markers, references, structural errors

**Steps**:
1. [x] - `p1` - Read file lines - `inst-read-code`
2. [x] - `p1` - **FOR EACH** line matching `@cpt-{kind}:{id}:p{N}` - `inst-match-scope`
   1. [x] - `p1` - Extract kind, id, phase; add to scope markers list - `inst-extract-scope`
3. [x] - `p1` - **FOR EACH** line matching `@cpt-begin:{id}:p{N}:inst-{local}` - `inst-match-begin`
   1. [x] - `p1` - Push onto open block stack - `inst-push-block`
4. [x] - `p1` - **FOR EACH** line matching `@cpt-end:{id}:p{N}:inst-{local}` - `inst-match-end`
   1. [x] - `p1` - Pop from stack, validate matching begin marker - `inst-pop-block`
   2. [x] - `p1` - **IF** no matching begin or id/inst mismatch, emit structural error - `inst-if-mismatch`
5. [x] - `p1` - **IF** unclosed blocks remain on stack, emit errors - `inst-if-unclosed`
6. [x] - `p1` - **RETURN** parsed code file with markers and structural errors - `inst-return-code`
7. [x] - `p1` - Define code data model: regex patterns, ScopeMarker, BlockMarker, CodeReference, CodeFile dataclasses, error factory - `inst-code-datamodel`
8. [x] - `p1` - Query and validation methods: list_ids, get by ID/inst, validate duplicate scopes - `inst-code-query-validate`
9. [x] - `p1` - Convenience wrappers: load_code_file, validate_code_file entry points - `inst-code-wrappers`
10. [x] - `p1` - Read a code file's text with the size ceiling applied to the bytes actually read rather than to a prior stat, reporting too-large under its own error code so a caller can branch on it instead of measuring the file again - `inst-code-read-bounded`
11. [x] - `p1` - Parse already-read text as a code file, so a caller holding one snapshot can hand the same bytes to a second parser instead of reopening a file that may have changed in between - `inst-code-from-text`

### Cross-Validate Code

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-cross-validate-code`

**Input**: Parsed code files, artifact ID set, `to_code` ID set, forbidden IDs (unchecked task), CDSL instruction map

**Output**: `{errors, warnings}` lists

**Steps**:
1. [x] - `p1` - **IF** traceability mode is DOCS-ONLY and markers found, emit error: markers prohibited - `inst-if-docs-only`
2. [x] - `p1` - Collect all IDs referenced in code markers - `inst-collect-code-ids`
3. [x] - `p1` - **FOR EACH** code marker referencing an ID not in artifact definitions - `inst-foreach-orphan`
   1. [x] - `p1` - Emit error: orphaned code marker (ID not defined in any artifact) - `inst-emit-orphan`
4. [x] - `p1` - **FOR EACH** code marker referencing a `to_code` ID whose task checkbox is unchecked - `inst-foreach-forbidden`
   1. [x] - `p1` - Emit error: code marker exists but artifact task not checked - `inst-emit-forbidden`
5. [x] - `p1` - **FOR EACH** `to_code` ID without any code marker - `inst-foreach-missing`
   1. [x] - `p1` - Emit error: missing code marker for `to_code` ID - `inst-emit-missing`
6. [x] - `p1` - **FOR EACH** CDSL instruction in artifacts with code block markers - `inst-foreach-inst`
   1. [x] - `p1` - **IF** artifact instruction has no matching `@cpt-begin/@cpt-end` block, emit error - `inst-if-inst-missing`
   2. [x] - `p1` - **IF** code block has no matching CDSL step in artifact, emit error - `inst-if-inst-orphan`
7. [x] - `p1` - **RETURN** accumulated errors and warnings - `inst-return-code-cross`

### List ID Kinds

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-list-id-kinds`

**Input**: Optional artifact path, project context

**Output**: JSON with kind list, counts, kind↔template mappings

**Steps**:
1. [x] - `p1` - Parse arguments: `--artifact` - `inst-kinds-parse-args`
2. [x] - `p1` - Resolve artifacts to scan (single or all registered) - `inst-kinds-resolve-artifacts`
3. [x] - `p1` - **IF** no artifacts found **RETURN** empty result or error - `inst-kinds-if-no-artifacts`
4. [x] - `p1` - Build known kinds set from kit constraints - `inst-kinds-build-known`
5. [x] - `p1` - **FOR EACH** artifact, scan ID definitions and infer kind tokens from ID slugs - `inst-kinds-scan-ids`
6. [x] - `p1` - Aggregate kind counts and kind↔template mappings - `inst-kinds-aggregate`
7. [x] - `p1` - **RETURN** JSON: `{kinds, kind_counts, kind_to_templates, template_to_kinds}` - `inst-kinds-return`

**Supporting**:
- [x] - `p1` - Imports and module setup for list-id-kinds command - `inst-kinds-imports`
- [x] - `p1` - Human-friendly formatter for list-id-kinds output - `inst-kinds-format`

### Validate TOC

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-validate-toc`

**Input**: List of file paths (or all registered artifacts)

**Output**: JSON with per-file TOC validation results

**Steps**:
1. [x] - `p1` - Parse arguments: positional files or `--all` - `inst-toc-parse-args`
2. [x] - `p1` - Resolve file list (explicit paths or all registered artifacts) - `inst-toc-resolve-files`
3. [x] - `p1` - **FOR EACH** file - `inst-toc-foreach-file`
   1. [x] - `p1` - Parse existing TOC block between `<!-- toc -->` markers - `inst-toc-parse-existing`
   2. [x] - `p1` - Generate expected TOC from headings - `inst-toc-generate-expected`
   3. [x] - `p1` - Compare existing vs expected: check anchor validity, heading coverage, staleness - `inst-toc-compare`
   4. [x] - `p1` - **IF** mismatch, record error with diff details - `inst-toc-if-mismatch`
4. [x] - `p1` - **RETURN** JSON: `{status, files_validated, error_count, warning_count, results}`, each `results[]` entry `{file, status, error_count, warning_count}` plus `errors`/`warnings` arrays when `--verbose` or non-empty - `inst-toc-return`

**Supporting**:
- [x] - `p1` - Imports and module setup for validate-toc command - `inst-toc-imports`
- [x] - `p1` - Validate a single file, never raising: a missing file or a read failure (permission denied, binary/non-UTF-8 content, a TOCTOU race) is reported as its own ERROR result rather than aborting the whole batch and discarding results already collected for earlier files - `inst-toc-validate-one`
- [x] - `p1` - Human-friendly formatter for validate-toc output: a WARN-only file prints its warnings the same way a FAIL file prints its errors, not just the bare status - `inst-toc-format`

### TOC Utilities

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-toc-utils`

**Input**: Markdown content string, optional file path

1. [x] - `p1` - Parse headings from markdown lines (respecting fenced code blocks, min/max level, skip options) - `inst-toc-util-parse-headings`
2. [x] - `p1` - Build TOC string from heading tuples (numbered or bulleted, GitHub-compatible anchors) - `inst-toc-util-build-toc`
3. [x] - `p1` - Insert/update TOC using HTML markers (`<!-- toc -->`) for CLI command - `inst-toc-util-insert-markers`
4. [x] - `p1` - Insert/update TOC using heading-based insertion (`## Table of Contents`) for kit file generator - `inst-toc-util-insert-heading`
5. [x] - `p1` - Process file: strip manual TOC, insert marker-based TOC, write if changed - `inst-toc-util-process-file`
6. [x] - `p1` - Validate TOC: check existence, anchor validity, completeness, staleness - `inst-toc-util-validate`
7. [x] - `p1` - Parse headings with line numbers, fence-aware and front-matter-aware (skips a leading YAML block so a `#`-prefixed front-matter line is never mistaken for a heading); shared by doc-index and the JIT-retrieval readiness checks, which need section boundaries the plain heading list doesn't carry -- `parse_headings` itself now delegates here, stripping the line number, so both share one fence/heading-match implementation - `inst-toc-util-parse-headings-lines`
8. [x] - `p1` - Collect JIT-retrieval readiness warnings for a document: gathers all four signals below over *every* heading level, independent of whatever level cap the caller configured for TOC-completeness checking - `inst-toc-jit-readiness-collect`
9. [x] - `p1` - Compute the four JIT-retrieval readiness signals -- duplicate heading titles (compared case-insensitively, with internal whitespace collapsed and Unicode-normalized, though the original text is still shown in the warning), heading depth jumps, oversized sections (`--max-section-lines`, default 300, validated against non-finite/non-positive input independent of the CLI's own argparse guard), and a missing top-of-file description/frontmatter block -- all warning-only, never errors (see constructorfabric/studio#104) - `inst-toc-jit-readiness`

**Supporting**:
- [x] - `p1` - Imports, constants, fence tracking, GitHub anchor slug generation - `inst-toc-util-datamodel`
- [x] - `p1` - Internal helpers: unique slug, next heading finder, manual TOC stripping, TOC section finder, entry extraction, anchor building, heading line finder - `inst-toc-util-helpers`
- [x] - `p1` - Fence-state update helper used by heading parser and TOC inserters - `inst-toc-util-fence-update`
- [x] - `p1` - HTML marker constants for `<!-- toc -->` / `<!-- /toc -->` fence detection - `inst-toc-util-markers-constants`
- [x] - `p1` - GitHub-compatible anchor slug generator: lowercase, strip special chars, preserve literal underscores in heading text, replace spaces with hyphens - `inst-toc-util-github-anchor`
- [x] - `p1` - Unique-slug deduplicator: append `-N` suffix on collision - `inst-toc-util-unique-slug`
- [x] - `p1` - Manual TOC stripper: remove leading list lines before any heading - `inst-toc-util-strip-manual`
- [x] - `p1` - Link regex constant for matching `[text](anchor)` TOC entries - `inst-toc-util-link-re`
- [x] - `p1` - TOC section finder: locate `<!-- toc -->` / `<!-- /toc -->` marker bounds in content lines - `inst-toc-util-find-section`
- [x] - `p1` - TOC entry extractor: parse existing `[text](#anchor)` lines from a TOC block - `inst-toc-util-extract-entries`
- [x] - `p1` - Anchor builder: map heading text to expected GitHub anchor slugs for comparison - `inst-toc-util-build-anchors`
- [x] - `p1` - Heading line finder: locate the line index of a given heading text in content lines - `inst-toc-util-find-heading-line`
- [x] - `p1` - Numbered TOC builder: generate `1. [text](#anchor)` lines from parsed heading tuples - `inst-toc-util-build-toc-numbered`
- [x] - `p1` - Bulleted TOC builder: generate `- [text](#anchor)` lines with indentation from heading level - `inst-toc-util-build-toc-bullets`
- [x] - `p1` - Marker-based TOC replace branch: overwrite content between existing `<!-- toc -->` / `<!-- /toc -->` markers - `inst-toc-util-insert-markers-replace`
- [x] - `p1` - Heading-based TOC replace branch: overwrite content under existing `## Table of Contents` heading - `inst-toc-util-insert-heading-replace`
- [x] - `p1` - Heading-based TOC new-insert branch: inject `## Table of Contents` before first heading when absent - `inst-toc-util-insert-heading-new`
- [x] - `p1` - TOC validate init: build heading list and expected TOC string before comparison checks - `inst-toc-util-validate-init`

### Document Index

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-doc-index`

**Input**: Markdown file path

**Output**: `cfs doc-index`'s JSON is `{file, cache_hit, total_lines, section_count, sections, section_level, retrieval_section_count, retrieval_sections}` -- every heading's own line range in `sections[]` (`{level, heading, line_start, line_end, summary}`), plus a coarser "one chunk per real section" grouping in `retrieval_sections[]` at an inferred heading level, each with a content hash and a summary slot. The underlying cached index dict additionally carries `schema_version`, `path`, and `etag`.

A cached, read-once-per-file structural index for Markdown JIT retrieval (see
constructorfabric/studio#104): parsing a file's headings/section boundaries
happens once, not once per query, until its stat fingerprint (`mtime_ns` +
size) changes.
The cache-validity fingerprint is deliberately metadata-only (`mtime` + file
size via `Path.stat()`), never a content hash — the point of the cache is to
avoid reading the file at all on a hit, and a content hash would defeat that
by requiring the read it's meant to save. A build reads the content and
takes that fingerprint bracketed by a stat snapshot on each side: when the
two snapshots agree, the fingerprint saved is provably the one that
matches what was actually parsed even if a write lands in the narrow
window during the read; under sustained contention past a bounded retry
limit, it falls back to the last read paired with its own trailing,
unverified fingerprint -- safe because that content will simply be
detected as stale again on the very next check, never silently wrong.

1. [x] - `p1` - Build a fresh structural index: parse headings + line ranges from current content, compute the stat-based fingerprint, stamp the current schema version - `inst-doc-index-build`
2. [x] - `p1` - Load a cached index for a file, validated against current stat metadata (no content read on a hit) and against the required-field shape at the current schema version; returns `None` if missing, stale, corrupt, or an incomplete/outdated shape - `inst-doc-index-load`
3. [x] - `p1` - Persist an index to its cache location atomically (temp file + `os.replace`, so a concurrent reader never observes a torn write); no-ops silently outside a Studio-adapted project - `inst-doc-index-save`
4. [x] - `p1` - Return the cached index or build-and-cache a fresh one; reports cache hit/miss for benchmarking - `inst-doc-index-get-or-build`
5. [x] - `p1` - Attach a one-line, LLM-authored summary to a cached section by its `line_start`, only once the caller's `expected_hash` matches that section's current hash -- rejecting the write on mismatch instead of silently attaching the summary to whatever content now occupies that position - `inst-doc-index-annotate`
6. [x] - `p1` - Infer which heading level represents one retrievable section: the most-recurring level wins over a level that appears only once (however shallow), since PDF-conversion heading levels don't reliably encode true nesting depth — a fixed level assumption silently produces a degenerate mega-section on such documents - `inst-doc-index-infer-level`
7. [x] - `p1` - Group headings at exactly the inferred level into retrieval sections (off-level headings stay inside whichever section they fall under, never split one apart); hash each section's own text, trailing-whitespace-stripped per line, for section-granularity staleness detection; flag a section with nothing between it and the next same-level heading as `empty`; when real content (not just blank lines) precedes the first section-level heading, capture it as a leading synthetic entry (`heading=None`) instead of leaving it invisible to every entry here - `inst-doc-index-retrieval-sections`
8. [x] - `p1` - Diff the current file against its last cached build at section granularity: which retrieval sections are unchanged vs. changed, or whether the section count itself changed (a structural change). Matched primarily by content hash (a multiset match, so duplicate-content sections pair up correctly) rather than position, so a pure reorder with no text edits reports every section unchanged instead of misreporting the whole document as edited; a returned entry's `line_start` (not its hash) is what a caller uses to address "this specific section" afterwards, since duplicate heading titles are real - `inst-doc-index-diff-stale`

**Supporting**:
- [x] - `p1` - Stat-based cache-validity fingerprint (`mtime_ns` + size); resolved from the file's own path, never a content hash - `inst-doc-index-etag`
- [x] - `p1` - Resolve the cache file location within the Studio directory owning the indexed file, resolved from the file's own path (not the process's working directory) - `inst-doc-index-cache-path`
- [x] - `p1` - `cfs doc-index` CLI wrapper: parse arguments, build the JSON output payload, reporting a clean error for a missing or unreadable file - `inst-doc-index-cmd`
- [x] - `p1` - Human-friendly formatter for `cfs doc-index` output - `inst-doc-index-cmd-format`
- [x] - `p1` - Read a file's content bracketed by an etag snapshot on each side, retrying on mismatch: closes the window where a write between the read and the fingerprint could save stale headings under a fresh-looking etag - `inst-doc-index-stable-read`
- [x] - `p1` - Re-parse a file's current content into retrieval sections for staleness comparison, and build the `(heading, line_start)` identity pair that disambiguates a duplicate heading title in a diff result - `inst-doc-index-diff-stale-helpers`
- [x] - `p1` - Slice a retrieval section's own raw text out of a file's lines by its `line_start`/`line_end` -- the one shared implementation every consumer needing a section's actual content (not just its boundaries) reuses instead of re-deriving the slice - `inst-doc-index-section-text`
- [x] - `p1` - `cfs doc-index` CLI wrapper: parse arguments, build the JSON output payload - `inst-doc-index-cmd`
- [x] - `p1` - Human-friendly formatter for `cfs doc-index` output - `inst-doc-index-cmd-format`

### TF-IDF Scoring

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-tfidf`

**Input**: Markdown file path, query text

**Output**: Retrieval sections ranked by TF-IDF score against the query, plus a confidence signal

Purely mechanical, no LLM call: reuses the Document Index's `retrieval_sections` for section boundaries (read once per file, same as every other JIT-retrieval consumer), then scores each section as sum(term-frequency x inverse-document-frequency) over the query's own terms. A rare, distinctive term scores its one relevant section far above every other (verified against a real document: 0.0016 vs. 0.0000 everywhere else); a common term whose real answer lives in a longer, more thoroughly-covered section can still lose to a shorter section with a single coincidental mention, since term frequency is normalized by section length — a real, measured, and documented failure mode of this method on its own, not a defect in the implementation (see the "zero-shot" case in the source findings document: margin 1.06x, wrong section on top). This is exactly why a margin/unambiguous confidence signal is returned alongside the ranking rather than just the ranking alone — a routing layer built on top of this needs to know when the ranking itself isn't trustworthy, not just what it is.

1. [x] - `p1` - Tokenize text: lowercase, alphanumeric-only, dropping tokens shorter than 3 characters - `inst-tfidf-tokenize`
2. [x] - `p1` - Score every retrieval section against a query: build the document's inverse-document-frequency table, rank sections by term-frequency x idf, and compute a margin/unambiguous confidence signal from the top two scores - `inst-tfidf-score`

**Supporting**:
- [x] - `p1` - Inverse-document-frequency table builder, section ranker, and margin/unambiguous confidence calculator - `inst-tfidf-score-helpers`
- [x] - `p1` - `cfs tfidf-score` CLI wrapper: parse arguments, build the JSON output payload - `inst-tfidf-cmd`
- [x] - `p1` - Human-friendly formatter for `cfs tfidf-score` output - `inst-tfidf-cmd-format`

### OKF Bundle

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-okf`

**Input**: Markdown file path; a written section's `line_start`, description, and body text (from an external caller)

**Output**: A local, regenerable bundle of concept files + `index.md`, and a per-section missing/stale/current status report

Deterministic infrastructure only, matching `doc_index.py`/`tfidf.py`: no LLM call happens in this module. Writing an actual section summary is an external caller's job (an agent, dispatched outside this codebase) -- this module tracks which concept files should exist relative to the document's *current* retrieval sections, detects when a written one is stale (its recorded `built_from_hash` no longer matches the section's current hash from the Document Index), and persists whatever the caller writes. The whole bundle is local-only and gitignored (`.cache/okf/` — see `.gitignore`): unlike the content of a summary, which is expensive to regenerate (real LLM tokens), the bundle not surviving a fresh clone just means it rebuilds from scratch the same way `doc_index.py`'s own cache does — nothing here assumes it survives across clones, only across calls on the same machine.

1. [x] - `p1` - Resolve the local bundle directory for a source file within its Studio directory, resolved from the file's own path - `inst-okf-bundle-dir`
2. [x] - `p1` - Load/persist the bundle manifest (`manifest.json`) atomically; loading validates the decoded shape (a dict, an `entries` list, each entry carrying `line_start`/`concept_file`/`built_from_hash`), treating a malformed/pre-schema manifest as absent rather than returned broken - `inst-okf-manifest-io`
3. [x] - `p1` - Report the bundle's state against the document's *current* retrieval sections: missing (never summarized, or its concept file was deleted out from under it), stale (source changed since summary was written), or current. Matched primarily by content *hash*, not `line_start` -- inserting or reordering other sections shifts `line_start` without touching a section's own text, so a manifest entry is reconciled to whichever current section now carries its recorded hash (consumed one at a time per hash, preserving that entry's own `concept_file`) before falling back to `line_start` to distinguish a genuine edit (stale) from never-summarized (missing) - `inst-okf-status`
4. [x] - `p1` - Write (or overwrite) one section's concept file (YAML frontmatter values safely quoted against embedded colons/quotes/newlines) and its manifest entry under one exclusive lock spanning the whole read-modify-write-and-reindex cycle, then regenerate `index.md` from the bundle's real current status (not the raw manifest), so a deleted concept file drops out instead of becoming a dead link and a stale entry is visibly marked - `inst-okf-write-concept`

**Supporting**:
- [x] - `p1` - YAML double-quoted-scalar escaper for frontmatter values, safe against caller-supplied content (an LLM's own summary text) containing colons, quotes, backslashes, or an embedded block-close sequence - `inst-okf-yaml-quote`
- [x] - `p1` - Concept-file frontmatter builder: title/description/resource/generated-by, every value safely quoted - `inst-okf-build-frontmatter`
- [x] - `p1` - Deterministic `index.md` template driven by real per-section status (missing/stale/current), not just the raw manifest, so it never disagrees with `cfs okf-status` - `inst-okf-render-index`
- [x] - `p1` - `cfs okf-status` CLI wrapper: parse arguments, build the JSON output payload - `inst-okf-cmd`
- [x] - `p1` - Human-friendly formatter for `cfs okf-status` output, including the concept file path - `inst-okf-cmd-format`

### Atomic File I/O

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-atomic-io`

**Input**: A file path and content to write; a lock path and a read-modify-write callback

**Output**: A file written without any observable torn/partial state; a callback run with cross-call exclusivity

Shared by every local cache/bundle writer in this package (`doc_index.py`, `okf.py`) once a second consumer needed the exact same two behaviors a first implementation had already solved once -- extracted rather than reimplemented a second time. Mirrors the fallback shape `decision_log.py`'s own locking already established for this codebase (exclusive `fcntl` lock where available, unlocked elsewhere), kept separate since that module also bakes in log-rotation behavior these callers don't need.

1. [x] - `p1` - Write text to a path atomically: temp file + `os.replace`, so a reader racing a concurrent writer sees either the old complete file or the new complete one, never a torn write - `inst-atomic-write`
2. [x] - `p1` - Run a read-modify-write callback under an exclusive lock on a sibling lock file, serializing concurrent callers so two overlapping cycles can't each read the same base state and have whichever writes last silently discard the other's update - `inst-atomic-lock`

### Heading-Nav Search

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-heading-nav`

**Input**: Markdown file path, query text

**Output**: Every retrieval section containing the query literally, plus the first (document-order) hit

Purely mechanical, no LLM call: a case-insensitive literal-substring search of the query against each retrieval section's own raw text, mirroring a real `grep -i "<query>"` against the content -- deliberately not tokenized or word-split, and sharing the Document Index's `retrieval_sections` for boundaries so this reads no more of the file than every other JIT-retrieval consumer already does. Has no semantic fallback by design: a query phrased differently than the source's own vocabulary returns zero hits everywhere, even when a related concept exists under different wording (a real, documented failure mode of this method on its own, not a defect) -- that hard failure is itself the useful signal a caller needs to decide whether to escalate past this method.

1. [x] - `p1` - Find every retrieval section containing a query's literal text (case-insensitive), in document order, plus the first match; excludes fenced code blocks from the match so an incidental code-sample hit can't count as a prose match - `inst-heading-nav-search`

**Supporting**:
- [x] - `p1` - Blank out fenced-code-block lines before counting hits, reusing `toc.py`'s own fence-tracking - `inst-heading-nav-strip-fences`
- [x] - `p1` - `cfs heading-nav` CLI wrapper: parse arguments, build the JSON output payload - `inst-heading-nav-cmd`
- [x] - `p1` - Human-friendly formatter for `cfs heading-nav` output - `inst-heading-nav-cmd-format`

### JIT-Retrieval Cascade

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-cascade`

**Input**: Markdown file path, query text; optional numeric margin threshold and expected future query volume

**Output**: A routing decision -- resolved at Tier 1, resolved with multiple candidates, or escalated to a Tier 2 OKF-vs-baseline recommendation (plus a large-read gate check when that recommendation is baseline)

Combines Heading-Nav Search and TF-IDF Scoring into the two-tier routing decision neither mechanical method answers on its own (see constructorfabric/studio#104): heading-nav's zero-hit case and TF-IDF's own agreement/margin against heading-nav's pick determine whether a query resolves for free at Tier 1, needs both methods' candidates read, or must escalate to a Tier 2 choice between the local OKF bundle and a full baseline read. Tier 1's large-margin resolution is deliberately restricted to TF-IDF's `unambiguous` signal rather than a numeric cutoff -- of the two real margins measured while designing this cascade, only an infinite (unambiguous) one was on a correct pick; every finite margin measured, however large, was on a documented wrong pick -- so a numeric `margin_threshold` exists as an explicit, off-by-default opt-in rather than a built-in assumption. Tier 2 never recommends an OKF concept file it knows is stale or missing for the section Tier 1 named as its escalation candidate: since nothing in this codebase can perform a background rebuild (no job runner, and by design no LLM call anywhere in this module or the ones it composes), falling back to baseline is the only choice that doesn't risk silently serving a known-wrong summary.

1. [x] - `p1` - Apply the Tier 1 routing table: heading-nav zero hits escalates; agreement with TF-IDF's top pick resolves when unambiguous (or past an explicit margin threshold), else escalates as a diffuse margin; disagreement between the two resolves with both candidates - `inst-cascade-tier1`
2. [x] - `p1` - Choose OKF vs. baseline once Tier 1 escalates: an available bundle with no summarized sections yet counts as "no usable bundle"; otherwise every section that could actually be selected -- Tier 1's named candidate, or the whole bundle when there's no candidate to narrow to -- must be current, else recommend baseline with a rebuild flag - `inst-cascade-tier2`
3. [x] - `p1` - Route one query end to end: run Tier 1, and only when it escalates run Tier 2 and -- if Tier 2 recommends baseline -- the large-read confirmation gate against the document's real line count - `inst-cascade-route`

**Supporting**:
- [x] - `p1` - `cfs retrieve` CLI wrapper: parse arguments, build the JSON output payload - `inst-cascade-cmd`
- [x] - `p1` - Human-friendly formatter for `cfs retrieve` output - `inst-cascade-cmd-format`

### Read Gate

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-read-gate`

**Input**: A document's total line count; an optional line-count threshold

**Output**: `{needs_confirmation, total_lines, threshold}` -- a structured verdict for an external caller to act on, not an interactive prompt

Pure decision logic, no I/O: this is a deterministic CLI, not the caller that actually reads a file and answers a query, so it produces the structured flag that decision depends on rather than blocking on its own `input()` call. The default threshold (5,000 lines) is the real number measured during this design's own token-tracking prototype -- the only read among nine real candidate targets against a 166-page source document that crossed it was a whole-document baseline read.

1. [x] - `p1` - Decide whether a read of a given line count should pause for confirmation against a threshold - `inst-read-gate-check`

**Supporting**:
- [x] - `p1` - `cfs read-gate` CLI wrapper: build the document index, extract its total line count, apply the gate check - `inst-read-gate-cmd`
- [x] - `p1` - Human-friendly formatter for `cfs read-gate` output - `inst-read-gate-cmd-format`

### Markdown Parsing Utilities

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-parsing-utils`

**Input**: Markdown text, section regex patterns

1. [x] - `p1` - Parse required sections from requirements file (section ID → title mapping) - `inst-parse-required-sections`
2. [x] - `p1` - Find present section IDs in artifact text (e.g., A, B, C letter headings) - `inst-parse-find-sections`
3. [x] - `p1` - Split text by lettered sections with optional line offsets - `inst-parse-split-sections`
4. [x] - `p1` - Extract field blocks from markdown (`**Field Name**: value` patterns) - `inst-parse-field-block`
5. [x] - `p1` - Extract backticked IDs matching a pattern from text - `inst-parse-extract-ids`

**Supporting**:
- [x] - `p1` - Imports, constants, field header termination heuristic, and list item detection helper - `inst-parse-datamodel`

### Fixing Prompt Enrichment

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-fixing-prompts`

**Input**: List of validation issues (errors/warnings), optional project root

1. [x] - `p1` - Define probable reasons registry mapping error codes to human-readable templates - `inst-fix-define-reasons`
2. [x] - `p1` - Build actionable fixing prompt per error code with location, ID, and constraint context - `inst-fix-build-prompt`
3. [x] - `p1` - Enrich each issue in-place: resolve reasons, attach fixing prompt, normalize location - `inst-fix-enrich`

**Supporting**:
- [x] - `p1` - Imports, SafeDict formatter, reason resolver, and prompt helper functions (location, kind context, headings hint, relative path) - `inst-fix-datamodel`
- [x] - `p1` - Fixing prompts for task/checkbox consistency errors (CDSL step unchecked, parent unchecked when all done, parent checked with nested unchecked) - `inst-fix-task-consistency`
- [x] - `p1` - Fixing prompts for reference errors (undefined ID, ref done but def not, def done but ref not, ref task with no def task, unreferenced ID) - `inst-fix-references`
- [x] - `p1` - Fixing prompt for non-consecutive heading number sequence errors - `inst-fix-heading-numbering`
- [x] - `p1` - Fixing prompts for ID kind presence errors (missing constraints, disallowed kind, required kind missing) - `inst-fix-id-kind-presence`
- [x] - `p1` - Fixing prompts for task/priority definition errors (missing/prohibited task checkbox, missing/prohibited priority marker) - `inst-fix-task-priority-defs`
- [x] - `p1` - Fixing prompt for ID definition placed under wrong headings - `inst-fix-heading-placement`
- [x] - `p1` - Fixing prompts for heading contract violations (missing heading, duplicate, requires multiple, numbering mismatch) - `inst-fix-heading-contract`
- [x] - `p1` - Fixing prompts for cross-reference coverage rule violations (target not in scope, missing from kind, wrong headings, missing/prohibited task or priority on reference) - `inst-fix-cross-ref-coverage`
- [x] - `p1` - Fixing prompts for code marker structural and cross-validation errors (duplicate begin, end without begin, empty block, unclosed block, duplicate scope, DOCS-ONLY, orphan ref, unchecked task, missing marker, orphaned inst block) - `inst-fix-marker-errors`
- [x] - `p1` - Fixing prompts for TOC validation errors (missing TOC, broken anchor, heading not in TOC, stale TOC) - `inst-fix-toc`
- [x] - `p1` - Probable-reasons templates for all 10 CDSL structure error codes - `inst-fix-define-cdsl-reasons`
- [x] - `p1` - Fixing prompts for CDSL structure violations (missing checkbox/phase/inst token, prohibited code/type/operator syntax, not-plain-English, duplicate inst-id, placeholder) - `inst-fix-cdsl-structure`
- [x] - `p1` - Fixing prompt for unreferenced ID warning (no scope) and final None fallback - `inst-fix-warnings`

### Headings Contract Validation

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-headings-contract`

**Input**: Artifact path, artifact kind constraints (headings list), registered systems

**Output**: `{errors, warnings}` lists

**Steps**:
1. [x] - `p1` - Resolve heading constraint IDs by line: match each document heading to a constraint pattern, build per-line active scope stack - `inst-resolve-scope`
2. [x] - `p1` - Scan headings from markdown lines: parse level, title, numbering prefix (respecting fenced code blocks) - `inst-scan-headings`
3. [x] - `p1` - Initialize validation context: load heading constraints, build helper lookups, scan document headings - `inst-validate-init`
4. [x] - `p1` - Check numbering sequence: enforce that sibling sections under the same numeric parent progress consecutively - `inst-check-numbering`
5. [x] - `p1` - Match headings against constraints: hierarchical scope matching, required/multiple/numbered enforcement, emit errors for missing/duplicate/misnumbered headings - `inst-match-headings`

**Supporting**:
- [x] - `p1` - Heading line regex, number prefix regex, and module exports - `inst-headings-datamodel`
- [x] - `p1` - Helper functions for heading pattern compilation, wildcard mapping, and best-match selection - `inst-match-headings-helpers`
- [x] - `p1` - Entry-point function signature for `validate_headings_contract` - `inst-validate-headings-entry`
- [x] - `p1` - `resolve_scope` init: set up per-constraint scope stacks before match loop - `inst-resolve-scope-init`
- [x] - `p1` - `resolve_scope` match loop: iterate headings and assign each to a matching constraint scope - `inst-resolve-scope-match-loop`
- [x] - `p1` - `resolve_scope` stack management: push/pop active constraint IDs based on heading level - `inst-resolve-scope-stack`
- [x] - `p1` - `validate_init` helpers: pre-build lookup tables and heading index for the validation context - `inst-validate-hc-helpers`
- [x] - `p1` - `check_numbering` inner function definition: closure over context for sibling-numbering enforcement - `inst-check-numbering-fn`
- [x] - `p1` - `match_headings` inner function definition: closure over context for hierarchical pattern matching - `inst-match-headings-fn`
- [x] - `p1` - `match_headings` scope resolver: determine which constraint scope applies to current heading - `inst-match-headings-scope`
- [x] - `p1` - `match_headings` main loop: iterate document headings and emit errors for violations - `inst-match-headings-loop`

### Load Constraints

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-load-constraints`

**Input**: Kit root path or raw TOML data

**Output**: `KitConstraints` object or list of parse errors

**Steps**:
1. [x] - `p1` - Load `constraints.toml` from kit root (or from resolved resource binding path for manifest-driven kits), parse TOML, delegate to `parse_kit_constraints` - `inst-load-toml`
2. [x] - `p1` - Parse kit constraints: iterate artifact kinds, parse headings, identifiers, TOC flag, normalize heading IDs and prev/next references - `inst-parse-kit`
3. [x] - `p1` - Parse individual ID constraint: validate kind, required, name, template, examples, task, priority, to_code, headings, references - `inst-parse-id-constraint`
4. [x] - `p1` - Parse heading constraint: validate level, pattern, description, required, multiple, numbered, id, prev/next, pointer - `inst-parse-heading`
5. [x] - `p1` - Parse reference rule: validate coverage, task, priority, headings fields - `inst-parse-ref-rule`

**Supporting**:
- [x] - `p1` - Examples parser, heading-constraint ID slugifier, and references map parser - `inst-constraints-helpers`
- [x] - `p1` - Normalize heading IDs and validate prev/next references in parsed constraints - `inst-constraints-normalize`
- [x] - `p1` - `slugify_heading_id`: convert heading pattern text to a stable constraint slug - `inst-slugify-heading-id`
- [x] - `p1` - `parse_references_map`: build reference rules dict from TOML `[[references]]` array - `inst-parse-references-map`
- [x] - `p1` - `parse_kit_constraints` main loop: iterate artifact kinds and accumulate parsed constraints - `inst-parse-kit-loop`
- [x] - `p1` - `assign_heading_ids`: assign auto-generated IDs to heading constraints that lack explicit IDs - `inst-assign-heading-ids`
- [x] - `p1` - `link_heading_prev_next`: wire `prev` / `next` back-references between adjacent heading constraints - `inst-link-heading-prev-next`
- [x] - `p1` - `normalize_heading_ids`: top-level entry point that calls assign and link in order - `inst-normalize-heading-ids`
- [x] - `p1` - `normalize_id_entry`: resolve `headings` field strings to HeadingConstraint objects within an ID constraint - `inst-normalize-id-entry`
- [x] - `p1` - `parse_identifier_entry`: parse a single `[[identifiers]]` TOML table into an `IdConstraint` - `inst-parse-identifier-entry`
- [x] - `p1` - `parse_identifiers_block`: iterate the `[[identifiers]]` array and collect parsed `IdConstraint` objects - `inst-parse-identifiers-block`

### Content Language Scan

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-lang-scan`

**Input**: List of file/directory paths, list of allowed language codes

1. [x] - `p1` - Define Unicode script ranges for each supported language code (Latin, Cyrillic, Arabic, CJK, etc.) - `inst-script-ranges`
2. [x] - `p1` - Expose `SUPPORTED_LANGUAGES` constant — sorted list of all recognized language codes - `inst-supported-langs`
3. [x] - `p1` - Define always-allowed common ranges (emoji, zero-width markers, BOM) - `inst-common-ranges`
4. [x] - `p1` - Define skip patterns for fenced code blocks, HTML comments, and `@cpt` markers - `inst-skip-patterns`
5. [x] - `p1` - Build merged sorted list of allowed Unicode ranges for the given language codes (`build_allowed_ranges`, `is_allowed`) - `inst-range-helpers`
6. [x] - `p1` - Scan single file: skip fences and structural lines; **IF** file contains `<!-- cpt-lang: ignore -->` skip file entirely; collect lines with characters outside allowed ranges - `inst-scan-file`
7. [x] - `p1` - Scan paths recursively: filter by extension (default `.md`), match each candidate path against optional `ignore_globs` (fnmatch), aggregate violations from non-ignored files - `inst-scan-paths`

**Supporting**:
- [x] - `p1` - Imports and module-level type aliases - `inst-lang-scan-imports`
- [x] - `p1` - `LangScanError` and `LangViolation` dataclass with `bad_chars_preview` and `line_preview` helpers - `inst-violation-datamodel`

### Check Language Scan Execution

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-check-language-scan`

**Input**: Parsed check-language CLI arguments, supported language codes

**Output**: `{allowed_languages, files_scanned, violations, grouped_violations, violation_items}`

1. [x] - `p1` - Resolve allowed languages from CLI override or workspace validation config - `inst-check-lang-resolve-languages`
2. [x] - `p1` - Merge CLI ignore patterns with workspace-config ignore paths - `inst-check-lang-resolve-ignore`
3. [x] - `p1` - Resolve scan roots from explicit paths or the default project architecture root - `inst-check-lang-resolve-roots`
4. [x] - `p1` - Build allowed Unicode ranges and run the markdown scanner across resolved roots - `inst-check-lang-scan-execution`
5. [x] - `p1` - Count scanned markdown files for the result payload - `inst-check-lang-count-files`
6. [x] - `p1` - Group violations by file and convert them into machine-readable result items - `inst-check-lang-group-violations`
7. [x] - `p1` - **RETURN** scan result payload with allowed languages, scanned files, grouped violations, and violation items - `inst-check-lang-return-scan`

### Language Configuration

- [x] `p1` - **ID**: `cpt-studio-algo-traceability-validation-language-config`

**Input**: Optional start path for project config lookup

1. [x] - `p1` - Define extension-based comment format defaults for all supported languages - `inst-lang-define-defaults`
2. [x] - `p1` - Load language config from project core.toml `codeScanning` section (with fallback to defaults) - `inst-lang-load-config`
3. [x] - `p1` - Build regex patterns for `@cpt-begin`/`@cpt-end` markers using language-specific comment syntax - `inst-lang-build-regex`

**Supporting**:
- [x] - `p1` - Imports, default constants, LanguageConfig class, default config factory, and extension-based comment merging helper - `inst-lang-datamodel`

## 4. States (CDSL)

### Validation Report Lifecycle

- [x] `p1` - **ID**: `cpt-studio-state-traceability-validation-report`

**States**: NOT_RUN, PASS, FAIL, ERROR

**Initial State**: NOT_RUN

**Transitions**:
1. [x] - `p1` - **FROM** NOT_RUN **TO** PASS **WHEN** validation completes with zero errors (exit code 0) - `inst-pass`
2. [x] - `p1` - **FROM** NOT_RUN **TO** FAIL **WHEN** validation completes with structural or traceability errors (exit code 2) - `inst-fail`
3. [x] - `p1` - **FROM** NOT_RUN **TO** ERROR **WHEN** validation cannot run (no studio, missing config, exit code 1) - `inst-error`

## 5. Definitions of Done

### Artifact Structural Validation

- [x] `p1` - **ID**: `cpt-studio-dod-traceability-validation-structure`

The system **MUST** validate each artifact against its kit-defined constraints: heading contract (required sections, levels, patterns), ID format (`cpt-{system}-{kind}-{slug}`), priority marker presence, CDSL step consistency (checked parent implies checked steps), and parent-child checkbox consistency. Validation **MUST** produce errors with file path, line number, and actionable fixing prompts. Self-check **MUST** verify kit examples pass template validation before proceeding.

**Implements**:
- `cpt-studio-flow-traceability-validation-validate`
- `cpt-studio-algo-traceability-validation-validate-structure`

**Covers (PRD)**:
- `cpt-studio-fr-core-traceability`

**Covers (DESIGN)**:
- `cpt-studio-component-validator`
- `cpt-studio-principle-determinism-first`

### Cross-Artifact Reference Validation

- [x] `p1` - **ID**: `cpt-studio-dod-traceability-validation-cross-refs`

The system **MUST** validate cross-artifact relationships: every ID reference resolves to a definition, checked references imply checked definitions, checked definitions imply checked references, and coverage rules from `constraints.toml` are enforced (required cross-references between artifact kinds). All consistency violations **MUST** include line numbers and artifact paths.

**Implements**:
- `cpt-studio-algo-traceability-validation-cross-validate`

**Covers (PRD)**:
- `cpt-studio-fr-core-traceability`

**Covers (DESIGN)**:
- `cpt-studio-component-validator`
- `cpt-studio-component-traceability-engine`
- `cpt-studio-principle-traceability-by-design`

### Code Traceability Validation

- [x] `p1` - **ID**: `cpt-studio-dod-traceability-validation-code`

The system **MUST** scan code files for `@cpt-*` markers (scope markers and block markers), validate marker structure (pairing, no empty blocks, proper nesting), and cross-validate against artifact IDs: orphaned markers (code references non-existent ID), missing markers (`to_code` IDs without code markers), forbidden markers (`to_code` ID with unchecked task checkbox), and CDSL instruction-level cross-validation. DOCS-ONLY traceability mode **MUST** prohibit all code markers. Single-pass scanning **MUST** complete in ≤ 3 seconds per artifact.

**Implements**:
- `cpt-studio-algo-traceability-validation-scan-code`
- `cpt-studio-algo-traceability-validation-cross-validate-code`

**Covers (PRD)**:
- `cpt-studio-fr-core-traceability`
- `cpt-studio-fr-core-cdsl`

**Covers (DESIGN)**:
- `cpt-studio-component-traceability-engine`
- `cpt-studio-component-validator`
- `cpt-studio-principle-ci-automation-first`
- `cpt-studio-constraint-no-weakening`

### Traceability Query Commands

- [x] `p1` - **ID**: `cpt-studio-dod-traceability-validation-queries`

The system **MUST** provide CLI commands for navigating the ID graph: `list-ids [--kind K] [--pattern P]` (list definitions matching criteria), `where-defined --id <id>` (find definition location), `where-used --id <id>` (find all references), `get-content --id <id>` (extract content block). All commands **MUST** output JSON, scan all registered artifacts, and use exit codes 0 (found) / 2 (not found).

**Implements**:
- `cpt-studio-flow-traceability-validation-query`
- `cpt-studio-algo-traceability-validation-scan-ids`

**Covers (PRD)**:
- `cpt-studio-fr-core-traceability`

**Covers (DESIGN)**:
- `cpt-studio-component-traceability-engine`
- `cpt-studio-seq-traceability-query`

### CDSL Instruction Tracking

- [x] `p1` - **ID**: `cpt-studio-dod-traceability-validation-cdsl`

The system **MUST** scan CDSL instruction markers (`inst-{slug}` suffixes in numbered list items) from FEATURE artifacts, associate each instruction with its parent ID, track checked/unchecked status, and cross-validate against `@cpt-begin/@cpt-end` block markers in code. Missing implementations and orphaned code blocks **MUST** both produce errors.

**Implements**:
- `cpt-studio-algo-traceability-validation-scan-cdsl`

**Covers (PRD)**:
- `cpt-studio-fr-core-cdsl`

**Covers (DESIGN)**:
- `cpt-studio-component-validator`
- `cpt-studio-component-traceability-engine`

## 6. Implementation Modules

| Module | Path | Responsibility |
|--------|------|----------------|
| Validate Command | `skills/.../commands/validate.py` | Main validation orchestration, context loading, report generation |
| Validate TOC | `skills/.../commands/validate_toc.py` | TOC consistency validation |
| List IDs | `skills/.../commands/list_ids.py` | List ID definitions matching criteria |
| List ID Kinds | `skills/.../commands/list_id_kinds.py` | List all ID kind tokens found in artifacts |
| Get Content | `skills/.../commands/get_content.py` | Extract content block for a specific ID |
| Where Defined | `skills/.../commands/where_defined.py` | Find where an ID is defined |
| Where Used | `skills/.../commands/where_used.py` | Find all references to an ID |
| Document Utils | `skills/.../utils/document.py` | ID scanning, CDSL instruction scanning |
| Constraints Utils | `skills/.../utils/constraints.py` | Constraint loading, heading validation, cross-validation |
| Codebase Utils | `skills/.../utils/codebase.py` | Code file scanning, `@cpt-*` marker validation |
| Error Codes | `skills/.../utils/error_codes.py` | Stable error codes for validation issues |
| Fixing Utils | `skills/.../utils/fixing.py` | Fixing prompt generation for LLM agents |
| Language Config | `skills/.../utils/language_config.py` | Language-specific file extensions and comment patterns |
| Parsing Utils | `skills/.../utils/parsing.py` | Markdown structure parsing, section extraction |
| Heading-Nav Utils | `skills/.../utils/heading_nav.py` | Literal-substring section search for JIT retrieval |
| Cascade Utils | `skills/.../utils/cascade.py` | Two-tier JIT-retrieval routing (heading-nav + TF-IDF, OKF vs. baseline) |
| Read Gate Utils | `skills/.../utils/read_gate.py` | Large-read confirmation threshold check |

## 7. Acceptance Criteria

- [x] `cfs validate` validates all registered artifacts and produces JSON report with PASS/FAIL status
- [x] `cfs validate --artifact <path>` validates a single artifact against its constraints
- [x] Heading contract validation catches missing required sections and wrong heading levels
- [x] ID format validation catches malformed `cpt-*` identifiers with line numbers
- [x] Cross-artifact validation catches undefined references, checked/unchecked mismatches, and coverage gaps
- [x] Code traceability validation catches orphaned markers, missing `to_code` markers, and unchecked-task markers
- [x] CDSL instruction tracking catches missing `@cpt-begin/@cpt-end` blocks and orphaned code blocks
- [x] DOCS-ONLY mode prohibits all `@cpt-*` code markers
- [x] `cfs list-ids`, `where-defined`, `where-used`, `get-content` return correct JSON results
- [x] Validation of a single artifact completes in ≤ 3 seconds
- [x] Full project validation (all artifacts + code) completes in ≤ 10 seconds for typical repositories
- [x] All validation errors include file path, line number, and actionable fixing prompt
- [x] All commands output JSON to stdout and use exit codes 0/1/2
