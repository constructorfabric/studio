# Feature: Developer Experience

<!-- toc -->

- [1. Feature Context](#1-feature-context)
  - [1. Overview](#1-overview)
  - [2. Purpose](#2-purpose)
  - [3. Actors](#3-actors)
  - [4. References](#4-references)
- [2. Actor Flows (CDSL)](#2-actor-flows-cdsl)
  - [Environment Health Check](#environment-health-check)
  - [Self-Check](#self-check)
  - [Pre-Commit Hooks](#pre-commit-hooks)
  - [TOC Generation](#toc-generation)
  - [Resolve Variables](#resolve-variables)
  - [Shell Completions](#shell-completions)
  - [Change Summary Digest](#change-summary-digest)
- [3. Processes / Business Logic (CDSL)](#3-processes--business-logic-cdsl)
  - [Run Doctor Checks](#run-doctor-checks)
  - [Run Self-Check](#run-self-check)
  - [Resolve Variables](#resolve-variables-1)
  - [Pylint Rollout Phase 0](#pylint-rollout-phase-0)
  - [Change Summary Window And Events](#change-summary-window-and-events)
  - [Change Summary Digest Composition](#change-summary-digest-composition)
- [4. States (CDSL)](#4-states-cdsl)
  - [Developer Experience State](#developer-experience-state)
- [5. Definitions of Done](#5-definitions-of-done)
  - [Doctor Command](#doctor-command)
  - [Self-Check Command](#self-check-command)
  - [Resolve Variables Command](#resolve-variables-command)
  - [Pre-Commit Hooks](#pre-commit-hooks-1)
  - [Shell Completions](#shell-completions-1)
  - [Change Summary Command](#change-summary-command)
- [6. Implementation Modules](#6-implementation-modules)
- [7. Acceptance Criteria](#7-acceptance-criteria)

<!-- /toc -->

- [ ] `p2` - **ID**: `cpt-studio-featstatus-developer-experience`

## 1. Feature Context

- [ ] `p2` - `cpt-studio-feature-developer-experience`

### 1. Overview

Enhances developer productivity with environment health checks, template QA, git pre-commit hooks, and shell completions. The `self-check` command validates that kit examples pass their own template constraints — ensuring kit integrity. The `doctor` command checks the development environment for required dependencies and configuration issues.

### 2. Purpose

Reduces friction in daily Studio usage. `doctor` catches environment issues before they cause cryptic errors. `self-check` catches kit regressions (template/example drift). Hooks enforce validation in CI. Completions improve CLI discoverability. Addresses PRD requirements for template QA (`cpt-studio-fr-core-template-qa`), environment diagnostics (`cpt-studio-fr-core-doctor`), pre-commit hooks (`cpt-studio-fr-core-hooks`), and shell completions (`cpt-studio-fr-core-completions`).

### 3. Actors

| Actor | Role in Feature |
|-------|-----------------|
| `cpt-studio-actor-user` | Runs `cfs doctor`, `cfs self-check`, installs hooks/completions |
| `cpt-studio-actor-ai-agent` | Invokes `cfs resolve-vars` and `cfs info` to resolve template variables for kit file substitution |
| `cpt-studio-actor-ci-pipeline` | Runs validation via pre-commit hooks |

### 4. References

- **PRD**: [PRD.md](../PRD.md) — `cpt-studio-fr-core-template-qa`, `cpt-studio-fr-core-doctor`, `cpt-studio-fr-core-hooks`, `cpt-studio-fr-core-completions`
- **Design**: [DESIGN.md](../DESIGN.md) — `cpt-studio-component-validator`
- **Dependencies**: `cpt-studio-feature-traceability-validation`

## 2. Actor Flows (CDSL)

### Environment Health Check

- [x] `p2` - **ID**: `cpt-studio-flow-developer-experience-doctor`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User runs `cfs doctor` → all checks pass, environment is healthy

**Error Scenarios**:
- Registered doctor check raises an exception → FAIL with exception detail
- `ralphex` not installed → WARN with installation guidance
- `ralphex` installed but incompatible → WARN with version compatibility detail

**Steps**:
1. [x] - `p2` - User invokes `cfs doctor [--root PATH]` and the command resolves the project root - `inst-user-doctor`
2. [x] - `p2` - Run each registered doctor check and convert unexpected exceptions into FAIL records - `inst-run-checks`
3. [x] - `p2` - Render each check result as PASS, WARN, or FAIL in the human output stream - `inst-render-checks`
4. [x] - `p2` - **RETURN** the overall health summary and exit code after all checks complete - `inst-return-health`

### Self-Check

- [x] `p1` - **ID**: `cpt-studio-flow-developer-experience-self-check`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User runs `cfs self-check` → all kit examples validate against their templates/constraints
- User runs `cfs self-check --kit sdlc` → only SDLC kit checked

**Error Scenarios**:
- Example fails template validation → FAIL with specific heading/constraint mismatch details
- constraints.toml missing → ERROR with hint to regenerate

**Steps**:
1. [x] - `p1` - User invokes `cfs self-check [--kit K] [--verbose]` - `inst-user-self-check`
2. [x] - `p1` - Load artifacts registry and kit metadata - `inst-load-registry`
3. [x] - `p1` - **FOR EACH** kit (or filtered by `--kit`) - `inst-for-each-kit`
   1. [x] - `p1` - Load constraints.toml for the kit - `inst-load-constraints`
   2. [x] - `p1` - **FOR EACH** artifact kind in kit - `inst-for-each-kind`
      1. [x] - `p1` - Validate template against heading constraints - `inst-validate-template`
      2. [x] - `p1` - Validate example against heading constraints - `inst-validate-example`
      3. [x] - `p1` - Check template/example consistency - `inst-check-consistency`
4. [x] - `p1` - **RETURN** self-check report with per-kind results - `inst-return-self-check`

### Pre-Commit Hooks

- [ ] `p3` - **ID**: `cpt-studio-flow-developer-experience-hooks`

**Steps**:
1. - `p3` - User invokes `cfs hook install` - `inst-install-hook`
2. - `p3` - Write pre-commit hook script to `.git/hooks/pre-commit` - `inst-write-hook`
3. - `p3` - Hook runs `cfs validate` on staged artifact files - `inst-hook-validate`

### TOC Generation

- [x] `p1` - **ID**: `cpt-studio-flow-developer-experience-toc`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User runs `cfs toc <files>` → TOC generated/updated in each file
- User runs `cfs toc --dry-run <files>` → changes shown without writing

**Error Scenarios**:
- File not found → ERROR per file
- Post-generation validation fails → VALIDATION_FAIL with details

**Steps**:
1. [x] - `p1` - User invokes `cfs toc <files> [--max-level N] [--indent N] [--dry-run] [--skip-validate]` - `inst-toc-gen-parse-args`
2. [x] - `p1` - **FOR EACH** file - `inst-toc-gen-foreach-file`
   1. [x] - `p1` - Process file: extract headings, generate TOC, insert/update between `<!-- toc -->` markers - `inst-toc-gen-process`
   2. [x] - `p1` - **IF** not dry-run and not skip-validate, validate generated TOC - `inst-toc-gen-validate`
3. [x] - `p1` - **RETURN** JSON: `{status, files_processed, results}` - `inst-toc-gen-return`

**Supporting**:
- [x] - `p1` - Imports and module setup for toc command - `inst-toc-gen-imports`
- [x] - `p1` - Human-friendly formatter for toc command output - `inst-toc-gen-format`

### Resolve Variables

- [x] `p1` - **ID**: `cpt-studio-flow-developer-experience-resolve-vars`

**Actor**: `cpt-studio-actor-ai-agent`

**Success Scenarios**:
- Agent runs `cfs resolve-vars` → all template variables resolved to absolute paths
- Agent runs `cfs resolve-vars --kit sdlc` → only SDLC kit variables returned
- Agent runs `cfs info` → `variables_by_kit` included in output for automatic per-kit resolution during Protocol Guard

**Error Scenarios**:
- No project root → ERROR with searched path
- Studio not initialized → ERROR with project_root
- Kit not found (with `--kit`) → ERROR with available kits list

**Steps**:
1. [x] - `p1` - User/agent invokes `cfs resolve-vars [--root P] [--kit K] [--flat]` - `inst-resolve-vars-parse-args`
2. [x] - `p1` - Discover project root and studio directory - `inst-resolve-vars-discover`
3. [x] - `p1` - Load core.toml for kit resource bindings - `inst-resolve-vars-load-core`
4. [x] - `p1` - Collect system variables (studio_path, project_root) - `inst-resolve-vars-system`
5. [x] - `p1` - **FOR EACH** installed kit with effective resources (persisted bindings or register-mode manifest resources) - `inst-resolve-vars-foreach-kit`
   1. [x] - `p1` - Resolve each resource binding to absolute path - `inst-resolve-vars-resolve-binding`
6. [x] - `p1` - Merge system + kit variables into flat dict - `inst-resolve-vars-merge`
7. [x] - `p1` - **IF** `--kit` filter, restrict to that kit - `inst-resolve-vars-filter-kit`
8. [x] - `p1` - **RETURN** JSON: `{status, system, kits, variables, counts}` - `inst-resolve-vars-return`
9. [x] - `p1` - Reuse the shared resolver from `cfs info` to populate `variables_by_kit` metadata without duplicating binding scans - `inst-info-load-variables`
10. [x] - `p1` - **IF** shared variable resolution degrades in `cfs info`, store error metadata; **ELSE** attach `variables_by_kit` plus collision details - `inst-info-store-variables`

**Supporting**:
- [x] - `p1` - Render resolved variables in human-friendly `info` output per kit - `inst-info-render-variables`
- [x] - `p1` - Human-friendly flat variable formatter - `inst-resolve-vars-human-flat`
- [x] - `p1` - Human-friendly structured variable formatter - `inst-resolve-vars-human-structured`

### Shell Completions

- [ ] `p3` - **ID**: `cpt-studio-flow-developer-experience-completions`

**Steps**:
1. - `p3` - User invokes `cfs completions install` - `inst-install-completions`
2. - `p3` - Detect shell (bash/zsh/fish) and write completion script - `inst-write-completions`

### Change Summary Digest

- [x] `p1` - **ID**: `cpt-studio-flow-developer-experience-change-summary`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User runs `cfs change-summary` on a branch → a digest of at most ten lines: the window it covers, the changed files with their marker denominator, the requirements they serve, and the decisions recorded while the work was done; exit 0
- User runs `cfs change-summary --json` → the same lines plus the full data behind each of them, as JSON

**Error Scenarios**:
- Not a git repository · git unavailable · decision log disabled, absent or unreadable · corrupt log lines · no changes against the base · not a Studio project → each states its own reason and denominator, and the exit code is still 0
- Unknown flag → usage error, exit 2 — the only non-zero exit the command has

**Steps**:
1. [x] - `p1` - User invokes `cfs change-summary [--root P] [--base REF] [--since TS]`; the digest is composed from the window, the changed-file linkage and the decision-log selection, and a usage error is the only path that returns non-zero — a stage that raises yields a stated reason, not a traceback - `inst-change-summary-cmd`
2. [x] - `p1` - Render the digest's lines for a human — the lines and nothing else, so they paste cleanly — or the full payload as JSON, and return 0 - `inst-change-summary-cmd-format`

## 3. Processes / Business Logic (CDSL)

### Run Doctor Checks

- [x] `p2` - **ID**: `cpt-studio-algo-developer-experience-doctor`

1. - `p2` - Check `python3 --version` ≥ 3.11 - `inst-check-python-version`
2. - `p2` - Check `git --version` available - `inst-check-git-version`
3. - `p2` - Check `gh --version` and `gh auth status` - `inst-check-gh-status`
4. - `p2` - Check Studio installation: `.core/`, `.gen/`, `config/` exist - `inst-check-installation`
5. - `p2` - Attempt to parse `core.toml` and `artifacts.toml` - `inst-check-parseable`
6. [x] - `p2` - Check `ralphex` availability: discover on `PATH` or via persisted `core.toml` `[integrations.ralphex].executable_path`; if found, run `ralphex --version` to verify compatibility; if missing, WARN with installation guidance (Homebrew, `go install`, binary releases) — ralphex is optional, so missing is WARN not FAIL (see `cpt-studio-adr-ralphex-delegation-skill`) - `inst-check-ralphex`

### Run Self-Check

- [x] `p1` - **ID**: `cpt-studio-algo-developer-experience-self-check`

1. [x] - `p1` - Load constraints.toml for each kit - `inst-load-kit-constraints`
2. [x] - `p1` - For each artifact kind, locate template and example paths - `inst-locate-files`
3. [x] - `p1` - Validate template headings match constraints heading contract - `inst-validate-headings`
4. [x] - `p1` - Validate example artifacts against the same heading and constraint contract used for user artifacts - `inst-validate-example`
5. [x] - `p1` - Check that template defines all required ID kinds from constraints - `inst-check-id-kinds`

### Resolve Variables

- [x] `p1` - **ID**: `cpt-studio-algo-developer-experience-resolve-vars`

1. [x] - `p1` - Collect system variables: studio_path (adapter dir), project_root - `inst-collect-system-vars`
2. [x] - `p1` - For each kit in core_data.kits, extract resources dict - `inst-extract-kit-resources`
3. [x] - `p1` - For each resource binding, resolve relative path to absolute via adapter_dir - `inst-resolve-binding-path`
4. [x] - `p1` - Merge system + all kit variables into flat dict (kit IDs are globally unique) - `inst-merge-flat-dict`
5. [x] - `p1` - Return structured result: {status, system, kits, variables, counts} - `inst-return-structured`

### Pylint Rollout Phase 0

- [ ] `p2` - **ID**: `cpt-studio-algo-developer-experience-pylint-rollout-phase-0`

**Input**: Prioritized Pylint backlog in `pyproject.toml`

**Output**: Docs-first rollout scope for the initial architectural refactor tranche

**Rules**:
1. - `p2` - Treat Phase 0 as the planning and advisory baseline for the rollout: document the target backlog ordering first, then stage code cleanup and plugin wiring without enabling the deferred message set in `pyproject.toml` yet - `inst-pylint-phase-0-docs-only`
2. - `p2` - Scope the first rollout tranche to the first half of the prioritized backlog: `R0911`, `R0914`, `R0801`, `R0912`, `R0915`, and `R0913` - `inst-pylint-phase-0-first-half`
3. - `p2` - Keep the remaining backlog deferred for later rollout phases, starting with `R0917`, `R0902`, `C0302`, `C0415`, `R0401`, and `C0301` - `inst-pylint-phase-0-deferred-half`
4. - `p2` - Keep the rollout aligned with `cpt-studio-nfr-zero-harm`: stage advisory cleanup before enabling additional checks - `inst-pylint-phase-0-zero-harm`

### Change Summary Window And Events

- [x] `p1` - **ID**: `cpt-studio-algo-developer-experience-change-summary`

**Input**: A project root, plus an optional base ref or explicit lower-bound timestamp

**Output**: The span of work a change digest covers, and the decision-log events recorded inside it

**Rules**:
1. [x] - `p1` - Define the window and selection result types as immutable records, and the reason vocabulary shared by producer and renderer so an unavailable dimension is always named rather than shown as empty - `inst-change-summary-datamodel`
2. [x] - `p1` - Answer read-only git queries as one line of output or nothing, keeping a tool failure apart from a valid negative so a timeout is never reported as a conclusion about history - `inst-change-summary-git-query`
3. [x] - `p1` - Detect whether the project root sits inside a git work tree, telling not-a-repository apart from a repository without a working tree and from git itself failing to answer - `inst-change-summary-detect-repo`
4. [x] - `p1` - Resolve the base ref, preferring the canonical remote over a fork's lagging default, and honour or refuse an explicitly requested ref rather than substituting a fallback - `inst-change-summary-default-base`
5. [x] - `p1` - Resolve the merge-base between HEAD and the base ref, treating unrelated histories as no window - `inst-change-summary-merge-base`
6. [x] - `p1` - Read the base commit's commit time as the window's lower bound, accepting that the boundary moves with the merge-base and that an explicit lower bound is how a caller pins it - `inst-change-summary-base-time`
7. [x] - `p1` - Assemble the window, short-circuiting git when the caller supplies an explicit lower bound, and returning a stated reason on every failure path instead of raising - `inst-change-summary-resolve-window`
8. [x] - `p1` - Parse ISO-8601 timestamps to aware datetimes, normalising a trailing Z and refusing naive values rather than assuming an offset that would move events across the boundary - `inst-change-summary-parse-ts`
9. [x] - `p1` - Read the decision log once and take readability, the events and the corruption count from that single snapshot, keeping absent apart from unreadable, so nothing appended or rotated between separate reads is reported as this window's state - `inst-change-summary-log-state`
10. [x] - `p1` - Select events at or after the window boundary, excluding and counting undated events rather than guessing them into or out of the window - `inst-change-summary-select-events`
11. [x] - `p1` - Group selected events by run id in first-seen order, so one invocation is a subdivision of the branch's span and never the whole story - `inst-change-summary-group-runs`
12. [x] - `p1` - Resolve the decision log belonging to the window's own project rather than to the current working directory, following a process-wide override where the environment sets one but reporting that it did, so a digest never presents another project's decisions as this one's - `inst-change-summary-default-log`
13. [x] - `p1` - Walk a known-good base ref down to a window, letting a git tool failure take precedence over a historical reading and keeping whatever was already learned on the returned window - `inst-change-summary-window-from-base`
14. [x] - `p1` - Reduce a run id to a canonical form, casefolding and stripping so one logical run is not split and a non-string does not merge with its own text, while not rejecting an unrecognised-but-real identifier - `inst-change-summary-canonical-run`
15. [x] - `p1` - Resolve the decision log a window should be read from, returning either a usable path and whether the environment chose it, or the reason no log is usable - `inst-change-summary-resolve-log`
16. [x] - `p1` - Define the per-file link and report types as immutable records, keeping referenced IDs separate from declared IDs so a changed specification is never reported as tracing to nothing - `inst-change-summary-link-datamodel`
17. [x] - `p1` - Answer read-only multi-record git queries by splitting NUL-delimited output, since a path may legally contain any byte except NUL, running with the same sanitised environment as the single-line query so an ambient redirect cannot list another repository's files - `inst-change-summary-git-lines`
18. [x] - `p1` - Parse a name-status line into status and path, taking the new path for renames and copies so a rename keeps its requirement link - `inst-change-summary-parse-name-status`
19. [x] - `p1` - Judge whether a changed path is one this project owns, delegating to the single shared exclusion policy rather than re-deriving containment - `inst-change-summary-classify-path`
20. [x] - `p1` - Report what one file does with requirement IDs, asking both directions because a suffix is not a reliable guide — a document's citation of an ID it does not itself declare is a reference too — reading the file once so both directions describe one snapshot, telling too-large from unreadable by the loader's own error code, and separating could-not-read from could-not-parse from carries-no-markers - `inst-change-summary-file-markers`
21. [x] - `p1` - List everything changed since the base commit against the working tree, including untracked files, so newly written work is never absent from the digest; pin rename detection rather than inherit the ambient git setting; count every entry but materialise no more than the report will examine; and report the whole listing as unavailable when either query fails rather than presenting a partial list as complete - `inst-change-summary-collect-changed`
22. [x] - `p1` - Resolve every changed file to what it declares, taking the root from the window so the report describes the project the window was built for, counting excluded, unreadable, deleted and not-a-file separately over the entries examined so the report always carries its denominator, and confining one entry's unforeseen failure to its own row - `inst-change-summary-link-changed`
23. [x] - `p1` - Classify one changed entry into its report row and its tally, keeping could-not-determine apart from excluded-by-policy and from not-a-regular-file, and listing every entry that existed even when nothing could be read from it - `inst-change-summary-classify-entry`

### Change Summary Digest Composition

- [x] `p1` - **ID**: `cpt-studio-algo-developer-experience-change-summary-digest`

**Input**: A project root, plus an optional base ref or explicit lower-bound timestamp

**Output**: At most ten lines, each backed by data and each degraded dimension stating its reason and denominator, together with the JSON payload behind them

**Rules**:
1. [x] - `p1` - Define the line ceiling, the caps on names listed inline, and the telemetry event kinds that are recorded cost rather than decisions, so every later rule shares one vocabulary - `inst-digest-datamodel`
2. [x] - `p1` - Refuse to summarise outside a Studio project with one stated reason, rather than three dimensions each reporting unavailable, and say when the check itself failed rather than report a machine fault as a fact about the directory - `inst-digest-project-gate`
3. [x] - `p1` - State the window as the base ref and commit it was measured from, or the reason no window exists together with the flag that scopes decisions by time without git - `inst-digest-window-line`
4. [x] - `p1` - State what changed with its denominator on every line: how many files, how many carry markers, and every excluded, deleted, unreadable, not-a-file or unexamined file, naming a tally only when it is non-zero and naming the examined population when the scan was capped so a breakdown never reads as one of the whole - `inst-digest-changes-lines`
5. [x] - `p1` - Name the requirements the changed files reference or declare, capped and counted rather than truncated silently, and emit no line at all when there are none - `inst-digest-requirements-line`
6. [x] - `p1` - State the decisions recorded in the window by kind and by run, excluding telemetry events and this command's own invocations so a digest never counts itself, and give every skipped line, undated event and shared-log condition a line of its own - `inst-digest-decision-lines`
7. [x] - `p1` - Enforce the ceiling by omitting lines and saying how many were omitted, never by padding to fill it - `inst-digest-ceiling`
8. [x] - `p1` - Carry the data behind every line in a payload that names no absolute path, so nothing a home directory or username could reach a review through is present - `inst-digest-payload`
9. [x] - `p1` - Compose the digest: one line when there is no window and one when there are no changes, since repeating a reason or consulting the log for nothing to review would be padding, and the full set otherwise - `inst-digest-compose`

## 4. States (CDSL)

### Developer Experience State

No feature-specific state machines. Self-check is stateless (run → report).

## 5. Definitions of Done

### Doctor Command

- [x] `p2` - **ID**: `cpt-studio-dod-developer-experience-doctor`

1. [x] - `p2` - `cfs doctor` emits a documented JSON payload with overall `status`, normalized per-check `status`, and `summary` text - `inst-json-result`
2. [x] - `p2` - Each implemented check reports pass/fail/warn with actionable remediation when available
3. [x] - `p2` - Exit code 0 if all checks pass, 2 if any fail (WARN-only does not fail)

### Self-Check Command

- [x] `p1` - **ID**: `cpt-studio-dod-developer-experience-self-check`

- [x] - `p1` - `cfs self-check` validates all kit examples against their templates/constraints
- [x] - `p1` - `--kit` flag filters to a single kit
- [x] - `p1` - Reports per-kind pass/fail with specific issues
- [x] - `p1` - Integrated into `cfs validate` as a fail-fast pre-check

### Resolve Variables Command

- [x] `p1` - **ID**: `cpt-studio-dod-developer-experience-resolve-vars`

- [x] - `p1` - `cfs resolve-vars` resolves all template variables to absolute paths
- [x] - `p1` - `--kit` flag filters to a single kit
- [x] - `p1` - `--flat` flag outputs plain variable→path dict
- [x] - `p1` - `cfs info` includes `variables` dict in output for Protocol Guard
- [x] - `p1` - System variables (studio_path, project_root) always present
- [x] - `p1` - Kit resource bindings resolved from core.toml registrations

### Pre-Commit Hooks

- [ ] `p3` - **ID**: `cpt-studio-dod-developer-experience-hooks`

- [ ] - `p3` - `cfs hook install` writes pre-commit hook
- [ ] - `p3` - `cfs hook uninstall` removes pre-commit hook
- [ ] - `p3` - Hook only validates staged artifact files

### Shell Completions

- [ ] `p3` - **ID**: `cpt-studio-dod-developer-experience-completions`

- [ ] - `p3` - `cfs completions install` writes shell-appropriate completion script
- [ ] - `p3` - Supports bash, zsh, and fish

### Change Summary Command

- [x] `p1` - **ID**: `cpt-studio-dod-developer-experience-change-summary`

- [x] - `p1` - `cfs change-summary` renders at most ten lines, each backed by data; when the ceiling bites, the last line says how many were omitted
- [x] - `p1` - Every degraded dimension states its own reason and its denominator
- [x] - `p1` - Exit 0 on every path except a usage error (2), enforced by tests that force each failure the behaviour matrix names and by a last-resort guard that turns an unforeseen exception into a stated reason - `inst-advisory-exit-zero`
- [x] - `p1` - `--json` carries the full payload behind every line, with no absolute path in it
- [x] - `p1` - Wired into no Makefile target, CI gate or required status check

## 6. Implementation Modules

| Module | Path | Responsibility |
|--------|------|----------------|
| Self-Check Command | `skills/.../commands/self_check.py` | Kit example validation against templates/constraints |
| TOC Command | `skills/.../commands/toc.py` | CLI wrapper for TOC generation |
| TOC Utils | `skills/.../utils/toc.py` | Unified TOC generation, anchor slugs, code block awareness |
| Resolve Vars Command | `skills/.../commands/resolve_vars.py` | Template variable resolution to absolute paths |
| Change Summary Core | `skills/.../utils/change_summary.py` | Window resolution from git, decision-log event selection inside it, and resolution of the changed files in that window to the requirement IDs they reference or declare |
| Change Summary Command | `skills/.../commands/change_summary.py` | Advisory digest: composes at most ten data-backed lines from the window, the changed-file linkage and the decision log, and exits non-zero only on a usage error |

## 7. Acceptance Criteria

- [x] `cfs self-check` validates kit integrity and reports per-kind results
- [x] `cfs resolve-vars` resolves all template variables to absolute paths
- [x] `cfs info` includes `variables` in output for agent variable resolution
- [x] `cfs change-summary` prints an advisory digest that states a reason and denominator on every degraded path, exits 0 everywhere except a usage error, and is wired into no gate
- [ ] Architecture records the Phase 0 Pylint rollout scope before enabling any of `R0911`, `R0914`, `R0801`, `R0912`, `R0915`, or `R0913`
- [ ] `cfs doctor` reports environment health with pass/fail/warn per check (including optional `ralphex` availability)
- [ ] Pre-commit hooks enforce validation on staged artifacts
- [ ] Shell completions work for all documented commands
