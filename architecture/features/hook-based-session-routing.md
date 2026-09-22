---
version: 0.2.0
significant_changes:
  - version: 0.2.0
    date: 2026-09-22
    summary: Review fixes — reconcile with ADR-0016 (Cursor has no hook support; project-level SessionStart deferral resolved here), scope out generated shim-file payload copies and Windsurf, document AGENTS.md/CLAUDE.md marker as shared across harnesses, add terminology/naming notes, replace stale brainstorm decision references with DoD IDs, add migration-from-file-injection criterion, and add non-applicable checklist domains.
  - version: 0.1.0
    date: 2026-09-22
    summary: Initial FEATURE draft for hook-based session routing (issue #143), covering per-harness hook install, file-injection fallback, disablement switch, and install-outcome reporting.
---

# Feature: Hook-Based Session Routing

<!-- toc -->

- [1. Feature Context](#1-feature-context)
  - [1.1 Overview](#11-overview)
  - [1.2 Purpose](#12-purpose)
  - [1.3 Actors](#13-actors)
  - [1.4 References](#14-references)
- [2. Actor Flows (CDSL)](#2-actor-flows-cdsl)
  - [Install Routing For a Project](#install-routing-for-a-project)
  - [Inspect Routing State](#inspect-routing-state)
- [3. Processes / Business Logic (CDSL)](#3-processes--business-logic-cdsl)
  - [Compile Harness Routing Delivery](#compile-harness-routing-delivery)
  - [Verify Hook Install](#verify-hook-install)
  - [Render Install-Outcome Summary](#render-install-outcome-summary)
  - [Read Current Routing State](#read-current-routing-state)
- [4. States (CDSL)](#4-states-cdsl)
  - [Per-Harness Routing State](#per-harness-routing-state)
- [5. Definitions of Done](#5-definitions-of-done)
  - [Cross-Harness Hook Abstraction](#cross-harness-hook-abstraction)
  - [Per-Harness Install State File](#per-harness-install-state-file)
  - [File-Injection Fallback Retained](#file-injection-fallback-retained)
  - [Single Disablement Switch](#single-disablement-switch)
  - [Minimal, Swappable Hook Payload](#minimal-swappable-hook-payload)
  - [Per-Harness Install-Outcome Summary](#per-harness-install-outcome-summary)
  - [Fallback Warning Visibility](#fallback-warning-visibility)
  - [Relative Hook-Path Disclosure](#relative-hook-path-disclosure)
  - [Fixed-Enum Fallback Reasons](#fixed-enum-fallback-reasons)
- [6. Acceptance Criteria](#6-acceptance-criteria)
- [7. Open Implementation Questions](#7-open-implementation-questions)
- [8. Applicability](#8-applicability)
- [Additional Context (optional)](#additional-context-optional)
  - [Per-Harness Install / Verify / Fallback / Disablement Flow](#per-harness-install--verify--fallback--disablement-flow)

<!-- /toc -->

## 1. Feature Context

- [ ] `p1` - **ID**: `cpt-studio-featstatus-hook-based-session-routing`

### 1.1 Overview

This feature moves delivery of Studio's routing precondition from unconditional `AGENTS.md`/`CLAUDE.md` file injection to harness session hooks, where a harness supports them. File injection remains as a documented, verified fallback, and a single switch turns routing on or off per harness.

**Terminology**: "Harness" in this document is the same entity that `cpt-studio-feature-agent-integration` and `cpt-studio-feature-subagent-registration` call a "tool" or an "agent" — the `--agent <name>` target of `cfs generate-agents`. No new entity is introduced; the term is used here only because this feature is about the host program that starts a session, not about the agent definitions generated for it.

**Harness naming**: this document uses `codex` for the OpenAI Codex harness because that is the key used by `_TOOL_PROVIDER_SUPPORT` (`skills/studio/scripts/studio/commands/agents.py`), the matrix this feature extends. The same harness is called `openai` (`--agent openai`, "OpenAI") in `cpt-studio-feature-agent-integration` and `cpt-studio-feature-subagent-registration`, where `.codex/agents` is only an output path. `codex` and `openai` refer to one and the same harness throughout.

### 1.2 Purpose

GitHub issue #143 ("Studio Routing — Use Harness Session Hooks Instead of Writing Into AGENTS.md / CLAUDE.md") reports that `cfs generate-agents` writes the routing precondition into every project's own `AGENTS.md`/`CLAUDE.md`, regardless of whether the target harness offers a native session-start hook. This feature gives harnesses that support session hooks a cleaner delivery path, while preserving today's file-injection behavior as a fallback for harnesses that do not, so the routing precondition (`ROOT_AGENTS_PIPELINE_INSTRUCTION`, `skills/studio/scripts/studio/constants.py`) is still reliably delivered to every harness in scope.

**Scope of "everywhere"**: this feature governs the four harnesses in `_TOOL_PROVIDER_SUPPORT` (claude, codex, cursor, copilot). Windsurf — a fifth host in the default selected set of `cpt-studio-feature-agent-integration` — is explicitly out of scope and keeps today's unconditional `AGENTS.md`/`CLAUDE.md` file injection unchanged (see Section 1.4).

**Requirements**: deliver the routing precondition (`ROOT_AGENTS_PIPELINE_INSTRUCTION`, `skills/studio/scripts/studio/constants.py`) to a supported harness via that harness's native on-session-start hook whenever the harness offers one, falling back to today's file injection into `AGENTS.md`/`CLAUDE.md` for harnesses that do not; and keep switching a harness's routing delivery mode (hook, file, or off) fully reversible per harness, with no residual hook files, file markers, or partial-downgrade state left behind for that harness or any other.

**Principles**: routing delivery for a harness is governed by exactly one disablement switch per harness — for the `AGENTS.md`/`CLAUDE.md` and hook-file delivery paths — which flips hook install and file-marker state atomically, so within those two paths there is never more than one place that determines whether a harness receives the routing precondition. Copies of `ROOT_AGENTS_PIPELINE_INSTRUCTION` embedded in generated per-harness workflow/skill shim files are a separate, out-of-scope concern (see Section 1.4).

### 1.3 Actors

| Actor | Role in Feature |
|-------|-----------------|
| Project maintainer | Runs `cfs generate-agents` to install or refresh routing delivery for a project, and reads the printed install-outcome summary. |
| CLI operator | Runs `cfs agents` later to re-check current routing install state without re-running install. |

### 1.4 References

- **PRD**: [PRD.md](../PRD.md)
- **Design**: [DESIGN.md](../DESIGN.md)
- **Dependencies**: `cpt-studio-feature-agent-integration` (per-(tool,provider) matrix pattern this feature reuses), `cpt-studio-feature-subagent-registration` (adjacent agent-integration surface, not duplicated here)
- **ADR**: `cpt-studio-adr-ai-cli-extensibility-subagents` ([ADR-0016](../ADR/0016-cpt-studio-adr-ai-cli-extensibility-subagents-v1.md)) — accepted; scopes hooks to subagent-level only and defers project-level `SessionStart` hooks to a future decision
- **Source issue**: GitHub issue #143, constructorfabric/studio — "Studio Routing — Use Harness Session Hooks Instead of Writing Into AGENTS.md / CLAUDE.md"
- **Out of scope**:
  - Changing the payload content of the routing instruction itself (tracked separately in issue #144).
  - **Windsurf**: Windsurf is not covered by this feature. It is not in `_TOOL_PROVIDER_SUPPORT`, and — mirroring the explicit-exclusion pattern `cpt-studio-feature-subagent-registration` uses for Windsurf subagents — it continues to receive today's unconditional `AGENTS.md`/`CLAUDE.md` file injection, unchanged and ungoverned by the disablement switch. Bringing Windsurf under this feature would require adding it to the tool/provider matrix first and is a separate change.
  - **Generated shim-file copies of the routing precondition**: `_follow_protocol_lines()` (`skills/studio/scripts/studio/commands/agents.py`) bakes `ROOT_AGENTS_PIPELINE_INSTRUCTION` into every generated per-harness workflow/skill shim file. That is a second, independent delivery channel, separate from the `AGENTS.md`/`CLAUDE.md` channel this feature models. It is **out of scope** for this feature's disablement switch: those embedded copies persist regardless of switch state, so "routing off" for a harness removes its hook and its file marker but does **not** remove the routing text already present in that harness's generated shim files. This is a known, named residual-state exception; gating the shim-file channel is deliberately left to a future iteration.
  - A dedicated ADR restating the hook-vs-file architectural choice; ADR-0016 already owns the deferral this document resolves (see below).

**Reconciliation with ADR-0016**: ADR-0016 deferred project-level `SessionStart` hooks for injecting Studio context into all sessions, pending three prerequisites. This document addresses that deferral and supplies the design for the routing-precondition slice of it:

- **Config merging** — `cpt-studio-dod-hook-based-session-routing-state-file` keeps hook-install bookkeeping in a dedicated per-harness state file rather than in the harness config, and `cpt-studio-algo-hook-based-session-routing-verify-hook` re-parses the harness's own config format after writing, so Studio's entry can be added to and removed from a shared config (e.g. `.claude/settings.json`) idempotently without clobbering user-defined hooks.
- **Fail-open semantics** — `cpt-studio-algo-hook-based-session-routing-compile-harness` never fails the run on hook trouble: an unwritable or unverifiable hook degrades to the existing file-injection path with a warning, so routing delivery is preserved rather than blocked.
- **Multi-tool format divergence** — `cpt-studio-dod-hook-based-session-routing-hook-abstraction` defines one cross-harness `on_session_start` abstraction compiled per harness through the existing per-(tool, provider) matrix, with the fallback path covering harnesses that have no hook API at all.

ADR-0016 also records that **Cursor has no hook support at all**. This document takes that as current fact (no contrary evidence exists in the repository today): Cursor is permanently file-fallback-only under this design. ADR-0016's other deferred items — project-level `PreToolUse`/`PostToolUse` validation hooks and a `cfs hooks install` / `uninstall` CLI command — remain deferred and are not addressed here.

## 2. Actor Flows (CDSL)

### Install Routing For a Project

- [ ] `p1` - **ID**: `cpt-studio-flow-hook-based-session-routing-install`

**Actor**: Project maintainer

**Success Scenarios**:
- Every hook-capable harness among the 4 supported (Claude, Codex, Copilot) installs via hook; Cursor — which has no hook API (`cpt-studio-adr-ai-cli-extensibility-subagents`) — installs via the file fallback and is flagged with its one-clause reason. This is the expected steady state, not an error.
- A mix of hook-capable and hook-incapable harnesses installs, with fallback harnesses clearly flagged.

**Error Scenarios**:
- A harness's hook file is written but fails syntactic verification; that harness falls back to file injection and is reported with a warning.
- Routing is disabled for a harness (via the disablement switch); no hook and no file marker are written for it.

**Steps**:
1. [ ] - `p1` - Project maintainer runs `cfs generate-agents` (optionally with `--json`) - `inst-run-generate-agents`
2. [ ] - `p1` - **FOR EACH** supported harness (claude, codex, cursor, copilot) - `inst-for-each-harness`
   1. [ ] - `p1` - Algorithm: compile on-session-start routing delivery for harness using `cpt-studio-algo-hook-based-session-routing-compile-harness` - `inst-compile-harness`
3. [ ] - `p1` - Algorithm: render per-harness install-outcome summary using `cpt-studio-algo-hook-based-session-routing-render-summary` - `inst-render-summary`
4. [ ] - `p1` - **IF** `--json` was passed - `inst-if-json-flag`
   1. [ ] - `p1` - CLI: emit summary as the existing global `--json` structured payload (same fields as the human table) - `inst-emit-json-summary`
5. [ ] - `p1` - **ELSE** - `inst-else-human-table`
   1. [ ] - `p1` - CLI: print summary as a short human-readable table, one row per harness - `inst-emit-human-summary`
6. [ ] - `p1` - **RETURN** per-harness install outcome (routing_mode, hook_path or file_marker_path, warnings) - `inst-return-install-outcome`

### Inspect Routing State

- [ ] `p2` - **ID**: `cpt-studio-flow-hook-based-session-routing-inspect`

**Actor**: CLI operator

**Success Scenarios**:
- Operator runs `cfs agents` after install and sees the same per-harness routing state that `generate-agents` last printed, re-derived rather than replayed.

**Error Scenarios**:
- Per-harness state file (`cpt-studio-dod-hook-based-session-routing-state-file`) is missing or unreadable for a harness; that harness is reported as "routing state unknown", not silently omitted.

**Steps**:
1. [ ] - `p1` - CLI operator runs `cfs agents` (the existing "show generated agent integration status" command) - `inst-run-cfs-agents`
2. [ ] - `p1` - **FOR EACH** supported harness - `inst-inspect-for-each-harness`
   1. [ ] - `p1` - Algorithm: re-derive current routing state from the per-harness state file using `cpt-studio-algo-hook-based-session-routing-read-state` - `inst-read-state`
3. [ ] - `p1` - **RETURN** current per-harness routing state (not a cached copy of the last `generate-agents` run) - `inst-return-current-state`

## 3. Processes / Business Logic (CDSL)

### Compile Harness Routing Delivery

- [ ] `p1` - **ID**: `cpt-studio-algo-hook-based-session-routing-compile-harness`

**Input**: harness identifier (one of: claude, codex, cursor, copilot), current disablement-switch value for that harness, `ROOT_AGENTS_PIPELINE_INSTRUCTION` payload

**Output**: per-harness install outcome record (routing_mode: `hook` | `file` | `off`, hook_path or file_marker_path relative to project root, warning entry if fallback occurred)

**Shared-resource note (file-fallback marker)**: the file-fallback marker is **not** a per-harness resource. `_inject_root_agents()`/`_inject_root_claude()` (`skills/studio/scripts/studio/commands/init.py`) write one managed block into exactly two shared, project-wide files — root `AGENTS.md` and root `CLAUDE.md` — which multiple harnesses read by convention. There is no per-harness marker file. Consequently the marker is owned collectively: it is created or kept whenever **any** in-scope harness needs the file fallback, and it is removed only when **no** in-scope harness still depends on it (that is, every file-fallback-dependent harness is either "routing off" or in `HookInstalled`). Hook files, by contrast, are genuinely per-harness and are always removed with their own harness. The steps below reflect this asymmetry.

**Steps**:
1. [ ] - `p1` - **IF** disablement switch for this harness is "routing off" - `inst-check-disabled`
   1. [ ] - `p1` - Remove this harness's own hook install, if any - `inst-remove-hook-file`
   2. [ ] - `p1` - **IF** no other in-scope harness still depends on the shared `AGENTS.md`/`CLAUDE.md` marker (every other harness is "routing off" or hook-installed) - `inst-check-shared-marker-unused`
      1. [ ] - `p1` - Remove the shared `AGENTS.md`/`CLAUDE.md` marker, atomically with the hook removal above (no partial-downgrade state) - `inst-remove-shared-marker`
   3. [ ] - `p1` - **ELSE** keep the shared marker in place, because it is still serving at least one other harness; record that this harness's `off` state is hook-level only and the shared marker remains - `inst-keep-shared-marker`
   4. [ ] - `p1` - **RETURN** routing_mode = `off` - `inst-return-off`
2. [ ] - `p1` - **IF** harness supports an on-session-start hook (per the existing per-(tool, provider) matrix pattern in `skills/studio/scripts/studio/commands/agents.py`) - `inst-check-hook-support`
   1. [ ] - `p1` - Write the harness-specific hook file (e.g. an entry under `.claude/settings.json` for the `claude` harness), sourcing its payload from `ROOT_AGENTS_PIPELINE_INSTRUCTION` without duplicating or hardcoding the text - `inst-write-hook-file`
   2. [ ] - `p1` - Algorithm: verify the hook install using `cpt-studio-algo-hook-based-session-routing-verify-hook` - `inst-verify-hook`
   3. [ ] - `p1` - **IF** verification succeeds - `inst-if-verified`
      1. [ ] - `p1` - Stop depending on the shared file-injection fallback for this harness; remove the shared `AGENTS.md`/`CLAUDE.md` marker only if no other in-scope harness still depends on it, otherwise leave it in place untouched (per the rollback-path precedent in `skills/studio/scripts/studio/commands/migrate_from_cypilot.py`) - `inst-stop-fallback`
      2. [ ] - `p1` - Persist per-harness install state to the harness's dedicated state file (separate from `init.py`'s `MARKER_START`/`MARKER_END` scan) - `inst-persist-hook-state`
      3. [ ] - `p1` - **RETURN** routing_mode = `hook`, hook_path (relative to project root) - `inst-return-hook-mode`
   4. [ ] - `p1` - **ELSE** - `inst-else-verify-failed`
      1. [ ] - `p1` - **GOTO** file-injection fallback (step 3) - `inst-goto-fallback`
3. [ ] - `p1` - Fall back to file injection: ensure the shared managed block is present in the two project-wide files, reusing existing `_compute_managed_block`/`_inject_managed_block`-style marker injection into root `AGENTS.md`/`CLAUDE.md` (`skills/studio/scripts/studio/commands/init.py`); the operation is idempotent because the marker is shared, so a second harness reaching this step finds it already written rather than writing a second copy - `inst-file-fallback-inject`
4. [ ] - `p1` - Append a warning-level entry to the outcome record, reusing the CLI's existing `warnings` array shape (as in `cfs info --json`), with a one-clause reason drawn from the fixed limitation-reason enum (see Section 7, item c) - `inst-append-fallback-warning`
5. [ ] - `p1` - **RETURN** routing_mode = `file`, file_marker_path (relative to project root) - `inst-return-file-mode`

### Verify Hook Install

- [ ] `p1` - **ID**: `cpt-studio-algo-hook-based-session-routing-verify-hook`

**Input**: harness identifier, written hook file path

**Output**: verified (boolean)

**Steps**:
1. [ ] - `p1` - **IF** hook file does not exist at the expected path - `inst-verify-missing`
   1. [ ] - `p1` - **RETURN** verified = false - `inst-verify-return-false-missing`
2. [ ] - `p1` - **TRY** - `inst-verify-try`
   1. [ ] - `p1` - Parse the hook file with the harness's own config format (e.g. JSON for `.claude/settings.json`) and confirm the routing entry is syntactically well-formed - `inst-verify-parse`
3. [ ] - `p1` - **CATCH** parse error - `inst-verify-catch`
   1. [ ] - `p1` - **RETURN** verified = false - `inst-verify-return-false-parse-error`
4. [ ] - `p1` - **RETURN** verified = true - `inst-verify-return-true`

### Render Install-Outcome Summary

- [ ] `p1` - **ID**: `cpt-studio-algo-hook-based-session-routing-render-summary`

**Input**: list of per-harness install outcome records

**Output**: human-readable table (default) or `--json` structured payload

**Steps**:
1. [ ] - `p1` - **FOR EACH** install outcome record - `inst-summary-for-each`
   1. [ ] - `p1` - Render harness name, routing_mode, and the hook file path or file marker path expressed relative to project root (never absolute, for `--json` stability across machines/CI) - `inst-render-row`
   2. [ ] - `p1` - **IF** routing_mode = `file` (fallback occurred) - `inst-render-if-fallback`
      1. [ ] - `p1` - Render the row as a visually distinct warning-level line, including the one-clause limitation reason - `inst-render-fallback-warning-line`
2. [ ] - `p1` - **RETURN** rendered summary (table or `--json`, same underlying data) - `inst-return-rendered-summary`

### Read Current Routing State

- [ ] `p2` - **ID**: `cpt-studio-algo-hook-based-session-routing-read-state`

**Input**: harness identifier

**Output**: current install outcome record (re-derived, not cached)

**Steps**:
1. [ ] - `p1` - Read the harness's dedicated state file (`cpt-studio-dod-hook-based-session-routing-state-file`) if present - `inst-read-state-file`
2. [ ] - `p1` - **IF** state file is missing or unreadable - `inst-read-state-missing`
   1. [ ] - `p1` - **RETURN** routing_mode = "unknown" (never silently omitted) - `inst-return-unknown-state`
3. [ ] - `p1` - **RETURN** current install outcome record for this harness - `inst-return-current-outcome`

## 4. States (CDSL)

### Per-Harness Routing State

- [ ] `p1` - **ID**: `cpt-studio-state-hook-based-session-routing-per-harness`

**States**: Off, FileFallback, HookInstalled

**Initial State**: Off for a project that has never had the routing precondition delivered. For a project already managed by Studio before this feature ships, the initial state is **FileFallback**, not Off — see the migration note below.

**Transitions**:
1. [ ] - `p1` - **FROM** Off **TO** FileFallback **WHEN** disablement switch is set to "routing on" and the harness has no supported session-hook API, or hook write/verify fails - `inst-transition-off-to-file`
2. [ ] - `p1` - **FROM** Off **TO** HookInstalled **WHEN** disablement switch is set to "routing on" and hook write + verify succeed - `inst-transition-off-to-hook`
3. [ ] - `p1` - **FROM** FileFallback **TO** HookInstalled **WHEN** a later `generate-agents` run finds hook support has become available and hook write + verify succeed - `inst-transition-file-to-hook`
4. [ ] - `p1` - **FROM** HookInstalled **TO** FileFallback **WHEN** a later `generate-agents` run finds the previously-verified hook no longer verifies - `inst-transition-hook-to-file`
5. [ ] - `p1` - **FROM** FileFallback **TO** Off **WHEN** disablement switch is set to "routing off"; the shared `AGENTS.md`/`CLAUDE.md` marker is removed only if no other in-scope harness still depends on it, and is otherwise left in place - `inst-transition-file-to-off`
6. [ ] - `p1` - **FROM** HookInstalled **TO** Off **WHEN** disablement switch is set to "routing off" (this harness's hook file removed; shared marker removed in the same atomic operation only if no other in-scope harness still depends on it) - `inst-transition-hook-to-off`

No partial-downgrade state exists: a harness is always in exactly one of Off, FileFallback, or HookInstalled; the disablement switch (`cpt-studio-dod-hook-based-session-routing-disablement`) flips this harness's hook state and its dependence on the file marker atomically.

**Shared marker, not per-harness state**: Off means "this harness receives no routing precondition from the hook or file channel". Because the file marker lives in two shared, project-wide files (root `AGENTS.md`/`CLAUDE.md`) rather than one file per harness, an Off harness may coexist with a marker that is still on disk for another harness's sake. That is not residual state for the Off harness — it is another harness's live state — but it does mean disabling one harness does not necessarily empty the shared files.

**Cursor never reaches HookInstalled**: per `cpt-studio-adr-ai-cli-extensibility-subagents`, Cursor has no hook support at all. Cursor's reachable states are therefore Off and FileFallback only; transitions 2, 3 and 4 do not apply to it. This is a permanent property of the current Cursor surface, not a transient failure, and its fallback warning carries the corresponding fixed-enum reason rather than an error. Should Cursor gain a session-hook API, no change to this state machine is needed — only the tool/provider matrix entry.

**Migration from pre-existing file injection**: every Studio-managed project created before this feature already has the routing precondition injected unconditionally into root `AGENTS.md`/`CLAUDE.md` (per `cpt-studio-feature-agent-integration`). On the first post-upgrade `cfs generate-agents` run, such a project MUST be read as starting in FileFallback for every in-scope harness — the existing marker is recognised as the file-fallback state, not ignored or re-injected — and each harness then proceeds through the normal transitions from there (transition 3 to HookInstalled for hook-capable harnesses, or staying in FileFallback). Upgrading MUST NOT require the project to pass through Off, and MUST NOT produce a duplicate marker.

## 5. Definitions of Done

### Cross-Harness Hook Abstraction

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-hook-abstraction`

The system **MUST** implement a single cross-harness "on_session_start" abstraction, compiled per harness inside `cfs generate-agents` (`skills/studio/scripts/studio/commands/agents.py`), reusing the existing per-(tool, provider) matrix pattern (`_TOOL_PROVIDER_SUPPORT`, `_TOOL_PROVIDER_DEFAULT`) already used there for model/tier mapping.

**Implements**:
- `cpt-studio-flow-hook-based-session-routing-install`
- `cpt-studio-algo-hook-based-session-routing-compile-harness`

**Touches**:
- Entities: `HarnessRoutingOutcome`

### Per-Harness Install State File

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-state-file`

The system **MUST** persist hook-install state in a new, small, per-harness state file that is separate from `init.py`'s `MARKER_START`/`MARKER_END` AGENTS.md/CLAUDE.md scan, since hook installs live in harness-specific config (e.g. `.claude/settings.json`) rather than in AGENTS.md/CLAUDE.md.

**Implements**:
- `cpt-studio-algo-hook-based-session-routing-compile-harness`
- `cpt-studio-algo-hook-based-session-routing-read-state`

**Touches**:
- Entities: `HarnessRoutingState`

### File-Injection Fallback Retained

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-fallback`

The system **MUST** keep file injection (`_compute_managed_block`/`_inject_managed_block` and related marker-rewrite helpers in `skills/studio/scripts/studio/commands/init.py`) as the default fallback for a harness, and **MUST** only stop injecting for that harness once its hook install is verified (hook file written and syntactically valid), mirroring the rollback-path precedent in `skills/studio/scripts/studio/commands/migrate_from_cypilot.py`.

The system **MUST** treat the injected marker as a **shared, project-wide** resource — one managed block in root `AGENTS.md` and one in root `CLAUDE.md`, written by `_inject_root_agents()`/`_inject_root_claude()` and consumed by multiple harnesses by convention — and **MUST NOT** model it as harness-owned. Accordingly the system **MUST** remove the shared marker only when no in-scope harness still depends on it, and **MUST** leave it in place when disabling or hook-upgrading a single harness while another in-scope harness is still in FileFallback.

**Implements**:
- `cpt-studio-algo-hook-based-session-routing-compile-harness`
- `cpt-studio-algo-hook-based-session-routing-verify-hook`

### Single Disablement Switch

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-disablement`

The system **MUST** provide exactly one disablement switch per harness with exactly two states — "routing on" (hook if supported, else file) and "routing off" (neither hook nor file for that harness) — and **MUST** flip that harness's hook install and its dependence on the shared file marker atomically, so no silent partial-downgrade state can occur.

**Scope of the guarantee**: this single-switch, no-residual-state guarantee covers the `AGENTS.md`/`CLAUDE.md` and hook-file delivery paths only. Two named exceptions are deliberately outside it:

- **Generated shim-file copies (out of scope)**: `_follow_protocol_lines()` (`skills/studio/scripts/studio/commands/agents.py`) embeds `ROOT_AGENTS_PIPELINE_INSTRUCTION` into every generated per-harness workflow/skill shim file over a second, independent channel. Those copies **MUST** be documented as persisting regardless of switch state, and the switch **MUST NOT** claim to remove them. Gating that channel belongs to a future iteration.
- **Shared marker retention**: because the file marker is project-wide rather than harness-owned (`cpt-studio-dod-hook-based-session-routing-fallback`), "routing off" for one harness **MUST NOT** remove the marker while another in-scope harness still depends on it.

**Implements**:
- `cpt-studio-algo-hook-based-session-routing-compile-harness`
- `cpt-studio-state-hook-based-session-routing-per-harness`

### Minimal, Swappable Hook Payload

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-payload-scope`

The system **MUST** source the hook payload directly from `ROOT_AGENTS_PIPELINE_INSTRUCTION` (`skills/studio/scripts/studio/constants.py`) as today, without duplicating or hardcoding the routing text separately, so a future change to the payload (tracked in issue #144, out of scope here) does not require reworking the hook delivery mechanism.

**Implements**:
- `cpt-studio-algo-hook-based-session-routing-compile-harness`

### Per-Harness Install-Outcome Summary

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-summary`

The system **MUST** print a per-harness install-outcome summary at the end of `cfs generate-agents`, as a short human table by default and as the same data via the CLI's existing global `--json` flag convention. The system **MUST** make the same data queryable later via `cfs agents`, re-derived live from the per-harness state file rather than replayed from a cache.

**Implements**:
- `cpt-studio-flow-hook-based-session-routing-install`
- `cpt-studio-flow-hook-based-session-routing-inspect`
- `cpt-studio-algo-hook-based-session-routing-render-summary`

### Fallback Warning Visibility

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-fallback-warning`

The system **MUST** flag any harness that falls back to file injection with a warning-level, visually distinct line in the summary, reusing the CLI's existing `warnings` array shape (as already used in, e.g., `cfs info --json` output).

**Implements**:
- `cpt-studio-algo-hook-based-session-routing-compile-harness`
- `cpt-studio-algo-hook-based-session-routing-render-summary`

### Relative Hook-Path Disclosure

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-relative-paths`

The system **MUST** express the hook file path written per harness relative to the project root (never absolute) in the summary, so `--json` output stays stable across machines and CI.

**Implements**:
- `cpt-studio-algo-hook-based-session-routing-render-summary`

### Fixed-Enum Fallback Reasons

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-reason-enum`

The system **MUST** attach a one-clause fallback reason (e.g. "Codex CLI has no session-hook API yet") to each fallback warning, drawn from a fixed, stable enum of known limitation reasons rather than free text. The exact enum values are an open implementation question (Section 7, item c).

**Implements**:
- `cpt-studio-algo-hook-based-session-routing-compile-harness`
- `cpt-studio-algo-hook-based-session-routing-render-summary`

## 6. Acceptance Criteria

- [ ] All 4 supported harnesses (claude, codex, cursor, copilot) go through the compile-harness process and end in exactly one of the three states (Off, FileFallback, HookInstalled) with no partial-downgrade state observable. Windsurf is not processed by this path and keeps its existing unconditional file injection.
- [ ] A harness with no session-hook support falls back to file injection and appears in the summary with a warning-level line and a one-clause reason.
- [ ] With routing on for all 4 harnesses, cursor ends in FileFallback (never HookInstalled) and is reported with the "no hook API" reason rather than as an error, matching `cpt-studio-adr-ai-cli-extensibility-subagents`.
- [ ] A harness with verified hook support stops depending on the shared file marker and appears in the summary with routing_mode = hook and a project-root-relative hook path.
- [ ] Disabling routing for a harness removes that harness's hook install, and removes the shared root `AGENTS.md`/`CLAUDE.md` marker in the same atomic operation **only when** no other in-scope harness still depends on it; when another in-scope harness is still in FileFallback, the shared marker is verifiably left in place and the disabled harness is still reported as `off`.
- [ ] Disabling routing for every in-scope harness removes the shared root `AGENTS.md`/`CLAUDE.md` marker and all hook files, leaving no residual marker or hook file — while the routing text embedded in generated shim files by `_follow_protocol_lines()` is expected to remain (documented out-of-scope exception, not a defect).
- [ ] A project that already has the pre-existing file-injected marker from before this feature is read as starting in FileFallback (not Off) on its first post-upgrade `cfs generate-agents` run, is not re-injected or duplicated, and then transitions normally to HookInstalled for each hook-capable harness.
- [ ] `cfs generate-agents --json` and the default human table expose the same underlying per-harness data (routing_mode, path, warnings).
- [ ] `cfs agents` re-derives and reports the same per-harness routing state as the most recent `generate-agents` run, without relying on a cached replay.
- [ ] The hook payload text is sourced from `ROOT_AGENTS_PIPELINE_INSTRUCTION` and is not duplicated elsewhere in the hook-writing code path.

## 7. Open Implementation Questions

These three side-topics were raised during design brainstorming and are deliberately left open. They **MUST** be resolved before or during implementation, not silently decided by this FEATURE document:

- [ ] **(a) Hook verification signal**: What exact verification signal proves a hook install succeeded, before file-fallback is turned off for that harness? `cpt-studio-algo-hook-based-session-routing-verify-hook` currently specifies "hook file exists and parses under the harness's config format" as a placeholder verification step; the precise signal (e.g. a harness-reported round-trip check, a dry-run invocation, or parse-only validation) needs a decision.
- [ ] **(b) Disablement switch surface**: Should the disablement switch (Section 5, `cpt-studio-dod-hook-based-session-routing-disablement`) be a CLI flag, a config-file setting, or both? This affects how `cfs generate-agents` and `cfs agents` read and expose the switch value.
- [ ] **(c) Fallback-reason enum values**: What is the fixed enum of harness-limitation reasons referenced by `cpt-studio-dod-hook-based-session-routing-reason-enum` (e.g. `no-hook-api`, `unsupported-tool-version`)? The full enumeration and its exact string values need a decision before the summary rendering can be finalized.

## 8. Applicability

This feature is a CLI-command change: `cfs generate-agents` and `cfs agents` writing and reading local files in the project working tree. The following checklist domains are therefore not applicable, each for the stated reason:

- **SEC**: Not applicable because there is no authentication or authorization surface — this is a local filesystem CLI operating with the invoking user's existing permissions, and the hook payload is Studio's own static routing text, not user-supplied input.
- **COMPL**: Not applicable because no regulated data is read, stored, or transmitted.
- **UX / accessibility**: Not applicable because there is no UI — output is CLI/terminal text plus the existing global `--json` payload.
- **DATA privacy**: Not applicable because no PII is touched; the only data written is harness config entries, a marker block, and a small per-harness state file.
- **PERF**: Not applicable because there are no response-time or throughput targets — the work is bounded local file I/O over at most 4 harnesses during a one-shot command, not a running service.

## Additional Context (optional)

### Per-Harness Install / Verify / Fallback / Disablement Flow

The diagram below shows how a single harness moves through compile-harness processing during one `cfs generate-agents` run — first checking the disablement switch, then hook support, then hook verification, with file injection as the fallback path whenever hook delivery is unavailable or unverified.

```
                         ┌─────────────────────────┐
                         │  cfs generate-agents     │
                         │  for harness H           │
                         └───────────┬──────────────┘
                                     │
                                     v
                    ┌────────────────────────────────┐
                    │ Disablement switch for H?       │
                    └───────────┬──────────┬───────────┘
                     routing off│          │routing on
                                v          v
                  ┌──────────────────┐   ┌───────────────────────────┐
                  │ Remove hook file  │   │ H supports on_session_start│
                  │ AND file marker   │   │ hook? (tool/provider matrix)│
                  │ atomically        │   └───────────┬────────┬───────┘
                  │ → state: Off      │            yes│        │no
                  └──────────────────┘                v        v
                                          ┌───────────────────┐ │
                                          │ Write hook file,   │ │
                                          │ payload from       │ │
                                          │ ROOT_AGENTS_       │ │
                                          │ PIPELINE_          │ │
                                          │ INSTRUCTION         │ │
                                          └─────────┬───────────┘ │
                                                     v             │
                                          ┌───────────────────┐   │
                                          │ Verify hook: file  │   │
                                          │ exists + parses OK?│   │
                                          └───────┬────┬────────┘   │
                                          verified│    │not verified│
                                                  v    v            v
                               ┌────────────────────┐ ┌─────────────────────────┐
                               │ Stop file fallback   │ │ Inject/keep file marker │
                               │ for H; persist state │ │ (AGENTS.md / CLAUDE.md) │
                               │ → state: HookInstalled│ │ via _inject_managed_    │
                               │ (hook path relative   │ │ block; attach warning + │
                               │ to project root)      │ │ one-clause reason       │
                               └────────────────────┘ │ → state: FileFallback   │
                                                        └─────────────────────────┘
                                                                     │
                                     ┌───────────────────────────────┘
                                     v
                       ┌───────────────────────────────┐
                       │ Append H's outcome to summary   │
                       │ (table + --json, same data)     │
                       └───────────────────────────────┘
```

This flow is not applicable to harnesses outside the 4 currently supported by `_TOOL_PROVIDER_SUPPORT` (claude, codex, cursor, copilot) — notably Windsurf, which stays on unconditional file injection (Section 1.4); adding a new harness extends that existing matrix rather than this flow. Cursor always takes the "no" branch at the hook-support decision, since it has no hook API at all.

In the diagram, "Inject/keep file marker (AGENTS.md / CLAUDE.md)" and "Remove hook file AND file marker" both act on the two shared, project-wide files rather than on a per-harness file: the inject step is idempotent across harnesses, and the remove step drops the shared marker only when no other in-scope harness still depends on it.
