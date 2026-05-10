# Feature: ralphex Delegation


<!-- toc -->

- [1. Feature Context](#1-feature-context)
  - [1.1 Overview](#11-overview)
  - [1.2 Purpose](#12-purpose)
  - [1.3 Actors](#13-actors)
  - [1.4 References](#14-references)
  - [1.5 Non-Applicability](#15-non-applicability)
  - [1.6 Out of Scope](#16-out-of-scope)
- [2. Actor Flows (CDSL)](#2-actor-flows-cdsl)
  - [Discover and Validate ralphex](#discover-and-validate-ralphex)
  - [Export Plan for Delegation](#export-plan-for-delegation)
  - [Delegate Execution to ralphex](#delegate-execution-to-ralphex)
  - [Post-Run Handoff](#post-run-handoff)
- [3. Processes / Business Logic (CDSL)](#3-processes--business-logic-cdsl)
  - [Discover ralphex Executable](#discover-ralphex-executable)
  - [Validate ralphex Availability](#validate-ralphex-availability)
  - [Compile Delegation Plan](#compile-delegation-plan)
  - [Map Phase to ralphex Tasks](#map-phase-to-ralphex-tasks)
- [4. States (CDSL)](#4-states-cdsl)
  - [Delegation Lifecycle](#delegation-lifecycle)
- [5. Definitions of Done](#5-definitions-of-done)
  - [ralphex Discovery and Persistence](#ralphex-discovery-and-persistence)
  - [Diagnostics and Availability Validation](#diagnostics-and-availability-validation)
  - [Optional Bootstrap](#optional-bootstrap)
  - [Bounded Plan Export](#bounded-plan-export)
  - [Delegation Modes](#delegation-modes)
  - [Post-Run Handoff](#post-run-handoff-1)
- [6. Implementation Modules](#6-implementation-modules)
- [7. Acceptance Criteria](#7-acceptance-criteria)

<!-- /toc -->

- [ ] `p1` - **ID**: `cpt-cypilot-featstatus-ralphex-delegation`

## 1. Feature Context

- [ ] `p1` - `cpt-cypilot-feature-ralphex-delegation`

### 1.1 Overview

Dedicated delegation skill that integrates Cypilot with ralphex (`https://ralphex.com/`), an external standalone terminal CLI for autonomous plan execution with Claude Code. The skill owns the entire ralphex-aware integration surface: executable discovery, availability diagnostics, optional project bootstrap, bounded plan export from canonical Cypilot sources, delegation invocation with mode flags, and post-run handoff with status and validation continuity. Cypilot remains the source of truth for SDLC guidance, decomposition, and validation contracts; ralphex becomes the optional autonomous execution backend for compiled plans.

### 1.2 Purpose

Without this feature, users must manually copy Cypilot plans and rules into ralphex format, breaking determinism and risking stale or incomplete SDLC context. This feature provides a first-class "delegate to ralphex" path that compiles Cypilot planning output into ralphex-compatible artifacts and manages the full delegation lifecycle.

**Requirements**: `cpt-cypilot-fr-core-workflows`, `cpt-cypilot-fr-core-execution-plans`, `cpt-cypilot-fr-core-agents`

**Principles**: `cpt-cypilot-principle-determinism-first`, `cpt-cypilot-principle-skill-documented`, `cpt-cypilot-principle-occams-razor`

### 1.3 Actors

| Actor | Role in Feature |
|-------|-----------------|
| `cpt-cypilot-actor-user` | Requests delegation to ralphex, reviews handoff results |
| `cpt-cypilot-actor-ai-agent` | Discovers ralphex, compiles export plan, invokes delegation, reports handoff |
| `cpt-cypilot-actor-cypilot-cli` | Routes delegation commands for the `cf-constructor-ralphex` skill |

### 1.4 References

- **PRD**: [PRD.md](../PRD.md) — `cpt-cypilot-fr-core-workflows`, `cpt-cypilot-fr-core-execution-plans`, `cpt-cypilot-fr-core-agents`
- **Design**: [DESIGN.md](../DESIGN.md) — `cpt-cypilot-component-skill-engine`, `cpt-cypilot-component-config-manager`, `cpt-cypilot-seq-ralphex-delegation`
- **ADR**: [ADR-0018](../ADR/0018-cpt-cypilot-adr-ralphex-delegation-skill-v1.md) — `cpt-cypilot-adr-ralphex-delegation-skill`
- **Dependencies**: `cpt-cypilot-feature-execution-plans`, `cpt-cypilot-feature-version-config`

### 1.5 Non-Applicability

The following quality domains are not applicable to this feature:

- **PERF**: This feature orchestrates CLI subprocess invocation and file export; no performance-critical algorithms or hot paths
- **DATA**: No persistent business-data model or migration strategy; config persistence is delegated to `cpt-cypilot-feature-version-config`
- **COMPL**: No direct regulatory requirements; internal tool integration only
- **UX**: CLI-only interaction with JSON output; no graphical UI

### 1.6 Out of Scope

The following are explicitly out of scope for this feature:

- Vendoring ralphex into the Cypilot Python package or making it a required runtime dependency
- Copying the SDLC kit (rules.md, checklist.md, kit workflows) into `.ralphex/` as a source of truth
- Replacing Cypilot generate/analyze/plan workflows with ralphex equivalents
- Replacing host-tool-native subagents (`cpt-cypilot-feature-subagent-registration`) with ralphex
- Managing ralphex internal configuration, dashboard, or review pipeline beyond what Cypilot needs for delegation handoff
- Implementing ralphex slash commands (`/ralphex`, `/ralphex-plan`, `/ralphex-update`) — these are ralphex-owned convenience shims

## 2. Actor Flows (CDSL)

### Discover and Validate ralphex

- [x] `p1` - **ID**: `cpt-cypilot-flow-ralphex-delegation-discover`

**Actor**: `cpt-cypilot-actor-ai-agent`

**Success Scenarios**:
- ralphex found on PATH → path persisted to `core.toml` `[integrations.ralphex]`, diagnostics pass
- ralphex found via persisted path in `core.toml` → reused, diagnostics pass
- ralphex not found → guided installation instructions provided (Homebrew, `go install`, binary releases)

**Error Scenarios**:
- Persisted path stale (binary removed) → re-discover on PATH, update or clear config
- ralphex found but incompatible version → WARN with version requirement and upgrade guidance

**Steps**:
1. [x] - `p1` - Agent checks for `ralphex` executable on `PATH` using `which ralphex` or equivalent - `inst-check-path`
2. [x] - `p1` - **IF** not found on PATH, check `core.toml` `[integrations.ralphex].executable_path` for persisted path - `inst-check-persisted`
3. [x] - `p1` - **IF** found, run `ralphex --version` to validate availability and compatibility - `inst-validate-version`
4. [x] - `p1` - **IF** validation passes, persist resolved absolute path to `core.toml` `[integrations.ralphex].executable_path` - `inst-persist-path`
5. [x] - `p1` - **IF** not found anywhere, provide guided installation instructions for the user's platform - `inst-guide-install`
6. [x] - `p1` - **RETURN** discovery result: path, version, or installation guidance - `inst-return-discovery`

### Export Plan for Delegation

- [ ] `p1` - **ID**: `cpt-cypilot-flow-ralphex-delegation-export`

**Actor**: `cpt-cypilot-actor-user`

**Success Scenarios**:
- User requests delegation of a Cypilot plan → plan compiled into ralphex Markdown plan under `docs/plans/`
- User requests delegation of a single phase → phase compiled into a focused ralphex plan

**Error Scenarios**:
- No active Cypilot plan for the target task → error with hint to run `cypilot-plan` first
- Export target directory not writable → filesystem error

**Steps**:
1. [ ] - `p1` - User requests delegation: "delegate this task/plan to ralphex" - `inst-user-delegate`
2. [ ] - `p1` - Agent loads plan manifest from `{cypilot_path}/.plans/{task-slug}/plan.toml` - `inst-load-manifest`
3. [ ] - `p1` - Agent runs `cpt-cypilot-algo-ralphex-delegation-compile-plan` to produce ralphex-compatible Markdown plan - `inst-compile-plan`
4. [ ] - `p1` - Agent resolves the active plans directory from ralphex config precedence (CLI flags > `.ralphex/` > `~/.config/ralphex/` > default `docs/plans/`) and writes exported plan to `{plans_dir}/{task-slug}.md` - `inst-write-plan`
5. [ ] - `p1` - **IF** Cypilot needs custom ralphex review prompts or agents, generate bounded `.ralphex/` overrides as derived artifacts - `inst-generate-overrides`
6. [ ] - `p1` - **RETURN** export summary: plan path, task count, validation commands included - `inst-return-export`

### Delegate Execution to ralphex

- [ ] `p1` - **ID**: `cpt-cypilot-flow-ralphex-delegation-execute`

**Actor**: `cpt-cypilot-actor-user`

**Success Scenarios**:
- User delegates exported plan → `ralphex {plans_dir}/{task}.md` invoked with appropriate mode flags
- User requests review-only → `ralphex --review` invoked (requires committed changes on current feature branch; ralphex diffs against default branch)
- User requests worktree isolation → `--worktree` flag appended (valid only for full mode and `--tasks-only`)

**Error Scenarios**:
- ralphex unavailable → error with discovery guidance
- Exported plan file missing → error with hint to re-export
- ralphex exits with non-zero → delegation failure reported with output refs
- Review mode requested but no committed changes on feature branch → error with precondition guidance

**Steps**:
1. [ ] - `p1` - Agent validates ralphex availability via `cpt-cypilot-algo-ralphex-delegation-validate` - `inst-validate-ralphex`
2. [ ] - `p1` - Agent determines delegation mode from user intent - `inst-determine-mode`
3. [ ] - `p1` - **IF** mode is `execute` → invoke `ralphex {plans_dir}/{task}.md [--tasks-only] [--worktree] [--serve]`; `--worktree` is valid only for full mode and `--tasks-only` (silently ignored by ralphex for `--review`, `--external-only`, `--plan`) - `inst-invoke-execute`
4. [ ] - `p1` - **IF** mode is `review` → verify current branch has committed changes diffable against the default branch; invoke `ralphex --review [{plans_dir}/{task}.md]` (plan file is optional supplemental context, not required; ralphex reviews committed diff against default branch) - `inst-invoke-review`
5. [ ] - `p1` - **RETURN** delegation status: invocation command, mode, plan file - `inst-return-delegation`

### Post-Run Handoff

- [x] `p1` - **ID**: `cpt-cypilot-flow-ralphex-delegation-handoff`

**Actor**: `cpt-cypilot-actor-ai-agent`

**Success Scenarios**:
- ralphex completes all tasks → agent reports success, completed plan moved to `{plans_dir}/completed/` (managed by ralphex), validation commands available
- ralphex partially completes → agent reports partial status with remaining tasks

**Error Scenarios**:
- ralphex fails mid-execution → agent reports failure point, remaining tasks, output refs

**Steps**:
1. [x] - `p1` - Agent reads ralphex exit status and output references - `inst-read-status`
2. [x] - `p1` - Agent checks `{plans_dir}/completed/` for completed plan lifecycle artifacts (path is ralphex-managed, resolved from the same config precedence used during export) - `inst-check-completed`
3. [x] - `p1` - Agent runs deterministic validation commands from the original Cypilot plan against the current working tree - `inst-run-validation`
4. [x] - `p1` - Agent reports delegation summary: status (success/partial/failed), output refs, validation outcome, next-step options - `inst-report-handoff`
5. [x] - `p1` - **RETURN** handoff result with validation continuity data - `inst-return-handoff`

## 3. Processes / Business Logic (CDSL)

### Discover ralphex Executable

- [x] `p1` - **ID**: `cpt-cypilot-algo-ralphex-delegation-discover`

**Input**: Current PATH, `core.toml` integrations section

**Output**: Resolved absolute path to `ralphex` binary or None

**Steps**:
1. [x] - `p1` - Search `PATH` for `ralphex` executable - `inst-search-path`
2. [x] - `p1` - **IF** not on PATH, read `core.toml` `[integrations.ralphex].executable_path` - `inst-read-config`
3. [x] - `p1` - **IF** persisted path exists, verify binary exists at that path - `inst-verify-persisted`
4. [x] - `p1` - **IF** binary verified, **RETURN** absolute path - `inst-return-path`
5. [x] - `p1` - **ELSE RETURN** None - `inst-return-none`

### Validate ralphex Availability

- [x] `p1` - **ID**: `cpt-cypilot-algo-ralphex-delegation-validate`

**Input**: Resolved ralphex executable path

**Output**: Validation result (available, unavailable, incompatible) with version info

**Steps**:
1. [x] - `p1` - **IF** path is None, **RETURN** unavailable with installation guidance - `inst-if-none`
2. [x] - `p1` - Run `ralphex --version` subprocess - `inst-run-version`
3. [x] - `p1` - Parse version output - `inst-parse-version`
4. [x] - `p1` - **IF** version satisfies compatibility requirements, **RETURN** available with version - `inst-return-available`
5. [x] - `p1` - **ELSE RETURN** incompatible with version and guidance - `inst-return-incompatible`

### Compile Delegation Plan

- [ ] `p1` - **ID**: `cpt-cypilot-algo-ralphex-delegation-compile-plan`

**Input**: Cypilot plan manifest (`plan.toml`), phase files, kit dependencies

**Output**: ralphex-compatible Markdown plan file content

**Steps**:
1. [ ] - `p1` - Read plan manifest and enumerate target phases - `inst-read-manifest`
2. [ ] - `p1` - Generate plan title and compact overview from plan metadata - `inst-gen-title`
3. [ ] - `p1` - Generate `## Validation Commands` section from Cypilot's deterministic validation contract (collected from phase acceptance criteria and kit constraints) - `inst-gen-validation`
4. [ ] - `p1` - **FOR EACH** target phase, run `cpt-cypilot-algo-ralphex-delegation-map-phase` to produce `### Task N:` block - `inst-loop-phases`
5. [ ] - `p1` - Assemble plan sections in ralphex grammar order: title, overview, Validation Commands, Task blocks - `inst-assemble`
6. [ ] - `p1` - Resolve all file paths to project-root-relative forms - `inst-resolve-paths`
7. [ ] - `p1` - **RETURN** compiled plan content - `inst-return-plan`

### Map Phase to ralphex Tasks

- [ ] `p1` - **ID**: `cpt-cypilot-algo-ralphex-delegation-map-phase`

**Input**: Single Cypilot phase file content, phase metadata

**Output**: `### Task N:` block content with checkboxes

**Steps**:
1. [ ] - `p1` - Extract task title from phase scope description - `inst-extract-title`
2. [ ] - `p1` - Flatten phase task steps into ralphex checkboxes (`- [ ] step description`) - `inst-flatten-steps`
3. [ ] - `p1` - Flatten phase acceptance criteria into additional checkboxes - `inst-flatten-criteria`
4. [ ] - `p1` - Distill task-local guidance from phase rules (include only SDLC constraints needed for this specific task) - `inst-distill-guidance`
5. [ ] - `p1` - Include resolved file paths relevant to the task - `inst-include-paths`
6. [ ] - `p1` - **RETURN** formatted `### Task N:` block - `inst-return-task`

## 4. States (CDSL)

### Delegation Lifecycle

- [x] `p1` - **ID**: `cpt-cypilot-state-ralphex-delegation-lifecycle`

**States**: not_exported, exported, delegated, completed, failed

**Initial State**: not_exported

**Transitions**:
1. [x] - `p1` - **FROM** not_exported **TO** exported **WHEN** plan compiled and written to `docs/plans/` - `inst-export`
2. [x] - `p1` - **FROM** exported **TO** delegated **WHEN** `ralphex` invoked with the exported plan - `inst-delegate`
3. [x] - `p1` - **FROM** delegated **TO** completed **WHEN** ralphex exits successfully and validation passes - `inst-complete`
4. [x] - `p1` - **FROM** delegated **TO** failed **WHEN** ralphex exits with error or validation fails - `inst-fail`
5. [x] - `p1` - **FROM** failed **TO** exported **WHEN** user re-exports after fixing issues - `inst-re-export`

## 5. Definitions of Done

### ralphex Discovery and Persistence

- [x] `p1` - **ID**: `cpt-cypilot-dod-ralphex-delegation-discovery`

The skill MUST discover `ralphex` on PATH or via persisted config, validate availability with `ralphex --version`, and persist the resolved absolute path in `core.toml` `[integrations.ralphex].executable_path` for reuse.

**Implements**:
- `cpt-cypilot-flow-ralphex-delegation-discover`
- `cpt-cypilot-algo-ralphex-delegation-discover`

### Diagnostics and Availability Validation

- [x] `p1` - **ID**: `cpt-cypilot-dod-ralphex-delegation-diagnostics`

The skill MUST validate ralphex availability before any delegation attempt. If ralphex is missing or incompatible, the skill MUST provide diagnostic output with platform-appropriate installation guidance (Homebrew on macOS, `go install`, binary releases) without altering baseline Cypilot behavior.

**Implements**:
- `cpt-cypilot-algo-ralphex-delegation-validate`

### Optional Bootstrap

- [x] `p1` - **ID**: `cpt-cypilot-dod-ralphex-delegation-bootstrap`

The skill MUST support bootstrapping project-local `.ralphex/` configuration via `ralphex --init` when local customization is needed. Generated `.ralphex/` files are treated as derived overrides, not canonical SDLC sources. Bootstrap rules:

- `ralphex --init` MUST NOT run automatically as a side effect of delegation or any other Cypilot workflow.
- If delegation detects that required local configuration (e.g., `.ralphex/config`) is missing, the agent MUST inform the user and request explicit approval before running `ralphex --init`.
- `ralphex --init` is always an opt-in action: it executes only on explicit user request or after explicit user approval of a bootstrap prompt.

**Implements**:
- `cpt-cypilot-flow-ralphex-delegation-discover`

### Bounded Plan Export

- [ ] `p1` - **ID**: `cpt-cypilot-dod-ralphex-delegation-export`

The skill MUST compile Cypilot plan outputs into ralphex-compatible Markdown plans. The export target directory is resolved from ralphex's own config precedence (CLI flags > local `.ralphex/` config > global `~/.config/ralphex/` config > default `docs/plans/`); Cypilot does not maintain a separate `plans_dir` setting. Exported plans MUST satisfy ralphex's documented plan grammar: `## Validation Commands` for test/lint commands, `### Task N:` headers for executable work units, and checkboxes only inside task sections. Export MUST NOT copy the entire SDLC kit — only bounded slices needed for the delegated task.

**Implements**:
- `cpt-cypilot-flow-ralphex-delegation-export`
- `cpt-cypilot-algo-ralphex-delegation-compile-plan`
- `cpt-cypilot-algo-ralphex-delegation-map-phase`

**Constraints**: `cpt-cypilot-constraint-markdown-contract`

**Touches**:
- Directory: `{plans_dir}/` (exported plans; path resolved from ralphex config, default `docs/plans/`)
- Directory: `.ralphex/prompts/`, `.ralphex/agents/` (optional derived overrides)

### Delegation Modes

- [ ] `p1` - **ID**: `cpt-cypilot-dod-ralphex-delegation-modes`

The skill MUST support the following delegation modes through ralphex CLI flags:

- **Execute exported plan**: `ralphex {plans_dir}/{task}.md` — autonomous task execution (full mode: tasks + review)
- **Tasks-only execution**: `ralphex {plans_dir}/{task}.md --tasks-only` — execute tasks, skip review phases
- **Review-only mode**: `ralphex --review [plan.md]` — review committed changes on the current feature branch against the default branch (`git diff master...HEAD`); the optional plan file provides supplemental context only; precondition: changes must be committed on the feature branch. When review mode is delegated via `run_delegation()`, a Cypilot-derived review override is automatically generated at `.ralphex/prompts/cypilot-review-override.md` before invoking ralphex. This override routes review work into Cypilot analyze methodology (code-review and prompt/instruction-review branches) with bounded scope, completion gates, residual-risk reporting, and remediation-prompt obligations. The override references canonical Cypilot sources by path and is regenerated on every review-mode delegation.
- **Worktree isolation**: `--worktree` flag runs execution in an isolated git worktree at `.ralphex/worktrees/<branch>`; valid only for full mode and `--tasks-only` (silently ignored by ralphex for `--review`, `--external-only`, `--plan`)
- **Dashboard serving**: `--serve` flag for web dashboard monitoring

**Implements**:
- `cpt-cypilot-flow-ralphex-delegation-execute`

### Post-Run Handoff

- [x] `p1` - **ID**: `cpt-cypilot-dod-ralphex-delegation-handoff`

The skill MUST report delegation results after ralphex completes: exit status, output references, completed plan location (`{plans_dir}/completed/`, managed by ralphex), and validation outcome. The skill MUST run the deterministic validation commands originally supplied by Cypilot for the delegated task to verify execution correctness independently of ralphex's own validation.

**Implements**:
- `cpt-cypilot-flow-ralphex-delegation-handoff`

## 6. Implementation Modules

| Module | Path | Responsibility |
|--------|------|----------------|
| ralphex Delegation Skill | `skills/.../agents/cf-constructor-ralphex.md` (skill entry point) | Discovery, export, delegation, handoff orchestration |
| Plan Export Compiler | `skills/.../scripts/cypilot/ralphex_export.py` | Cypilot plan → ralphex Markdown plan compilation |

## 7. Acceptance Criteria

- [ ] `cf-constructor-ralphex` skill discovers `ralphex` on PATH and persists resolved path in `core.toml`
- [ ] Previously persisted path is reused on subsequent invocations without re-discovery
- [ ] Missing `ralphex` produces diagnostic output with installation guidance, not a hard error
- [ ] `ralphex --init` can be invoked for project-local `.ralphex/` bootstrap on user request
- [ ] Cypilot plan outputs are exported into ralphex-compatible Markdown plans with `## Validation Commands` and `### Task N:` sections
- [ ] Export target directory is resolved from ralphex config precedence, not hardcoded or Cypilot-owned
- [ ] Exported plans contain only bounded SDLC slices, not the entire kit
- [ ] One Cypilot phase maps to one `### Task N:` block (or small contiguous group)
- [ ] Delegation invokes `ralphex` with correct mode flags (execute, review, worktree, serve, tasks-only)
- [ ] `--worktree` is only appended for full mode and `--tasks-only` delegation; not for review-only
- [ ] Review-only delegation verifies committed changes exist on the feature branch before invoking `ralphex --review`
- [ ] Post-run handoff reports status, output refs, and re-runs Cypilot validation commands
- [ ] Integration is fully optional: projects without `ralphex` use normal Cypilot workflows with zero behavioral change
- [ ] No Cypilot SDLC assets (rules.md, checklist.md, kit workflows) are duplicated into `.ralphex/` as a parallel source of truth
