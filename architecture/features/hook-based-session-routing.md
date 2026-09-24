---
version: 0.7.0
significant_changes:
  - version: 0.7.0
    date: 2026-09-24
    summary: Sixth-round PR review fixes — register the Claude hook with no `SessionStart` source restriction (covering `startup`, `resume`, `clear`, `compact`, `fork`), matching the correction already made for Codex; count a configured Windsurf as a permanent dependent of the shared `AGENTS.md`/`CLAUDE.md` marker (detected via the existing `_is_agent_installed("windsurf", …)` signal) so the marker is never removed out from under the one harness that depends on it forever; broaden the promotion-before-removal persist from `file`→`hook` only to any harness whose state file does not already durably record `hook`; name the hook command's execution-time read target (`<harness-config-dir>/.cf-studio-routing-state.json`), require atomic same-directory-temp-plus-rename writes so a concurrent read never sees a partial file, and make an unparseable or unrecognised-`schema_version` read fail closed to receipt-only; decide explicitly that repeated delivery across multiple session-start firings in one continuing session is intentional with no session-level dedup and no use of `session_id`; document `--dry-run` as write-free for routing and disclose that `--agent` does not scope routing-state writes; and state unambiguously that "Off" guarantees no hook entry, no receipt, and no counted marker dependence, but never per-harness isolation from the shared fallback files.
  - version: 0.6.0
    date: 2026-09-24
    summary: Fourth-round PR review fixes — cross-reference `DESIGN.md`'s new `HarnessRoutingOutcome` field-level schema (type and presence rule per `routing_mode` value, including a unified `warnings` array shape with `level`/`reason`) instead of leaving it implicit, and add the same `errored`-outcome pattern already used for shared-marker failures to the two disablement-time removals that previously had no failure branch (own hook-entry removal, own execution-receipt removal) plus a distinct report-only pattern for the final per-harness state-file persistence step, whose own write failure cannot be persisted into itself.
  - version: 0.5.0
    date: 2026-09-23
    summary: Third-round PR review fixes — register the Codex hook with no `SessionStart` matcher restriction (covering `startup`, `resume`, `clear`, and `compact`) so no restart source is silently left without routing delivery once the harness is promoted to `HookInstalled`, and add a read-state rule that reports the persisted `file` value (not `unknown`) during the expected receipt-only pending-first-run window instead of treating it as drift.
  - version: 0.4.0
    date: 2026-09-23
    summary: Second-round PR review fixes — correct the Codex hook capability claim (hooks are enabled by default via `[features].hooks`; `codex_hooks` is a deprecated alias Studio neither writes nor depends on), pick `.codex/hooks.json` as the single Codex config location Studio writes, add a per-harness native hook-entry shape table plus an open question for the exact vendor schemas, resolve the persist-vs-delete contradiction in favour of retaining the state file on disablement (recording `off`) while still removing the hook entry and receipt, add `unknown` as a report-only outcome value and an inspection rule that re-tests a persisted `errored`, mark harnesses `errored` when a shared-marker removal fails, persist final state for every affected harness rather than only the selected ones, make the hook receipt-only during the pending-first-run window to prevent duplicate delivery, and state that hook delivery is unconditional per session.
  - version: 0.3.0
    date: 2026-09-23
    summary: PR review fixes — record verified per-harness hook capability (all four in-scope harnesses now expose a session-start hook, including Cursor, which supersedes ADR-0016's "Cursor has no hook support" claim), note Codex's experimental `codex_hooks` opt-in, split the compile step into an order-independent two-pass algorithm with a dedicated shared-marker reconciliation, persist state for every mode, re-derive read-state from installed resources instead of trusting the state file, add a Studio-owned hook-entry identifier plus repeat-install replace and failed-hook cleanup, add an Errored state for write failures, name the concrete per-harness state-file path and its schema version, define payload transport and an execution-receipt gate before file fallback is dropped, and treat root AGENTS.md/CLAUDE.md as one atomic pair.
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
  - [Reconcile Shared Fallback Marker](#reconcile-shared-fallback-marker)
  - [Verify Hook Install](#verify-hook-install)
  - [Render Install-Outcome Summary](#render-install-outcome-summary)
  - [Read Current Routing State](#read-current-routing-state)
- [4. States (CDSL)](#4-states-cdsl)
  - [Per-Harness Routing State](#per-harness-routing-state)
- [5. Definitions of Done](#5-definitions-of-done)
  - [Cross-Harness Hook Abstraction](#cross-harness-hook-abstraction)
  - [Studio-Owned Hook Entry Identity](#studio-owned-hook-entry-identity)
  - [Hook Payload Transport](#hook-payload-transport)
  - [Per-Harness Install State File](#per-harness-install-state-file)
  - [File-Injection Fallback Retained](#file-injection-fallback-retained)
  - [Write-Failure Error Outcome](#write-failure-error-outcome)
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

This feature moves delivery of Studio's routing precondition from unconditional `AGENTS.md`/`CLAUDE.md` file injection to harness session-start hooks. All four in-scope harnesses expose such a hook today (see the capability table in Section 1.4), so the hook path is the normal path rather than the exception. File injection remains as a documented, verified fallback for the cases where a hook cannot be installed, verified, or confirmed to have run, and a single switch turns routing on or off per harness.

**Terminology**: "Harness" in this document is the same entity that `cpt-studio-feature-agent-integration` and `cpt-studio-feature-subagent-registration` call a "tool" or an "agent" — the `--agent <name>` target of `cfs generate-agents`. No new entity is introduced; the term is used here only because this feature is about the host program that starts a session, not about the agent definitions generated for it.

**Harness naming**: this document uses `codex` for the OpenAI Codex harness because that is the key used by `_TOOL_PROVIDER_SUPPORT` (`skills/studio/scripts/studio/commands/agents.py`), the matrix that enumerates this feature's in-scope harnesses. The same harness is called `openai` (`--agent openai`, "OpenAI") in `cpt-studio-feature-agent-integration` and `cpt-studio-feature-subagent-registration`, where `.codex/agents` is only an output path. `codex` and `openai` refer to one and the same harness throughout.

**State vocabulary**: this feature uses one set of lifecycle state names and one set of serialized values, with a fixed one-to-one mapping used identically here and in `DESIGN.md`:

| Lifecycle state (`HarnessRoutingState`) | Serialized `routing_mode` value | Meaning |
|---|---|---|
| `Off` | `off` | Routing is intentionally disabled for this harness; no hook entry and no dependence on the shared marker. |
| `FileFallback` | `file` | The shared `AGENTS.md`/`CLAUDE.md` marker is what actually delivers the precondition to this harness. |
| `HookInstalled` | `hook` | This harness's own verified hook entry delivers the precondition and has been confirmed to run. |
| `Errored` | `errored` | Studio could not establish either channel for this harness on the last run; delivery is not guaranteed. |

`unknown` is a fifth **report-only** `routing_mode` value with no corresponding lifecycle state: inspection emits it when the persisted state and the state derived from installed resources disagree (`cpt-studio-algo-hook-based-session-routing-read-state`). It is never persisted and a harness is never *in* `unknown`; it describes the reader's confidence, not the harness. `DESIGN.md`'s `HarnessRoutingOutcome.routing_mode` enum therefore carries five values (`off`, `file`, `hook`, `errored`, `unknown`) while `HarnessRoutingState` carries four.

**Outcome record schema**: `HarnessRoutingOutcome` is a `DESIGN.md` entity, not redefined here. The field-level presence, type, and cardinality rules referenced throughout Sections 2–6 below — for example, when `hook_path`, `file_marker_paths`, and `warnings` are present versus omitted for a given `routing_mode`, and how the `warnings` array is shaped (`level` + `reason`) — are the single, authoritative definition in `DESIGN.md`'s `HarnessRoutingOutcome` field schema; this document only describes the behavior that produces each field's value.

### 1.2 Purpose

GitHub issue #143 ("Studio Routing — Use Harness Session Hooks Instead of Writing Into AGENTS.md / CLAUDE.md") reports that `cfs generate-agents` writes the routing precondition into every project's own `AGENTS.md`/`CLAUDE.md`, regardless of whether the target harness offers a native session-start hook. This feature gives every harness that supports session hooks a cleaner delivery path, while preserving today's file-injection behavior as a fallback, so the routing precondition (`ROOT_AGENTS_PIPELINE_INSTRUCTION`, `skills/studio/scripts/studio/constants.py`) is still reliably delivered to every harness in scope.

**Scope of "everywhere"**: this feature governs the four harnesses enumerated by `_TOOL_PROVIDER_SUPPORT` (claude, codex, cursor, copilot). That matrix is used here only to decide **which** harnesses to iterate over; it maps tools to model providers and says nothing about hook capability, which is tracked separately in Section 1.4. Windsurf — a fifth host in the default selected set of `cpt-studio-feature-agent-integration` — is explicitly out of scope and keeps today's unconditional `AGENTS.md`/`CLAUDE.md` file injection unchanged (see Section 1.4).

**Requirements**: deliver the routing precondition (`ROOT_AGENTS_PIPELINE_INSTRUCTION`, `skills/studio/scripts/studio/constants.py`) to a supported harness via that harness's native on-session-start hook whenever that hook is available and usable, falling back to today's file injection into `AGENTS.md`/`CLAUDE.md` whenever it is not; and keep switching a harness's routing delivery mode (hook, file, or off) fully reversible per harness, subject to the three named exceptions below.

**Reversibility, and its three named exceptions**: turning routing off for a harness leaves no residual **delivery** state for that harness — no hook entry and no execution receipt. It does not always empty the two shared fallback files, it does not remove the harness's own state file, and it does not touch generated shim files. Specifically:

- The `AGENTS.md`/`CLAUDE.md` managed block is a single project-wide resource shared by all harnesses, so it is retained while **any** harness still depends on it — any in-scope harness still in `FileFallback` (for example a harness whose hook entry has been written but not yet observed to run), or Windsurf whenever Windsurf is configured for the project, since Windsurf has no hook path and depends on the marker permanently (Section 1.4). It is removed only when no such dependent exists. This is another harness's live state, not residual state for the disabled harness — but because it is one physical pair of files rather than one file per harness, a disabled harness that happens to read those same files at session start still sees the retained block. See "What 'Off' guarantees, and what it cannot" below.
- The harness's own state file (`cpt-studio-dod-hook-based-session-routing-state-file`) **persists by design** and is rewritten to record `routing_mode: off`. It is bookkeeping, not a delivery channel: keeping it is what lets a later `cfs agents` report a deliberately disabled harness as `off` instead of guessing from an absent file. Deleting it would make "intentionally off" indistinguishable from "never installed" only by luck of derivation.
- Copies of `ROOT_AGENTS_PIPELINE_INSTRUCTION` embedded in generated per-harness workflow/skill shim files are a separate, out-of-scope delivery channel and persist regardless of switch state (see Section 1.4).

All three exceptions are restated verbatim in `cpt-studio-dod-hook-based-session-routing-disablement`; this summary and that DoD are intentionally the same claim.

**Principles**: routing delivery for a harness is governed by exactly one disablement switch per harness — for the `AGENTS.md`/`CLAUDE.md` and hook-entry delivery paths — which flips hook install and file-marker dependence atomically, so within those two paths there is never more than one place that determines whether a harness receives the routing precondition. That switch governs what **Studio installs and maintains** for a harness; it is not, and cannot be, a guarantee about what that harness's own process chooses to read from disk (see immediately below).

**What "Off" guarantees, and what it cannot**: "routing off" for a harness guarantees exactly three things: Studio writes **no new hook entry** for it, keeps **no execution receipt** for it, and stops counting it as a dependent of the shared marker. It does **not** guarantee that the harness's own process never sees the routing text. Root `AGENTS.md` and root `CLAUDE.md` are two shared, project-wide files that harnesses read by their own convention, not files Studio hands to one harness — so while any other harness still depends on them (an in-scope harness in `FileFallback`, or Windsurf, which depends on them permanently), the block stays on disk and a nominally-off harness that reads those same files at session start still reads it. This is an inherent property of **reusing the pre-existing project-wide file-injection mechanism** (`_inject_root_agents()`/`_inject_root_claude()`) rather than introducing per-harness fallback files, and it is a deliberate, accepted constraint of this feature — not a defect and not an unfixed bug. Achieving true per-harness isolation of the fallback channel would mean replacing the shared-file mechanism with per-harness fallback files project-wide, which is out of scope here. **Nothing in this document may be read as promising per-harness isolation of the shared fallback files**; every statement about "off", reversibility, or residual state is scoped to the hook entry, the execution receipt, and marker *dependence*, never to the physical contents of the two shared files.

### 1.3 Actors

| Actor | Role in Feature |
|-------|-----------------|
| Project maintainer | Runs `cfs generate-agents` to install or refresh routing delivery for a project, and reads the printed install-outcome summary. |
| CLI operator | Runs `cfs agents` later to re-check current routing install state without re-running install. |

### 1.4 References

- **PRD**: [PRD.md](../PRD.md)
- **Design**: [DESIGN.md](../DESIGN.md)
- **CLI contract**: [specs/cli.md](../specs/cli.md) — global output conventions (including the human-default stdout exception that covers this feature's summary), and the existing `agents` / `generate-agents` command contracts this feature extends
- **Dependencies**: `cpt-studio-feature-agent-integration` (per-(tool,provider) matrix and generation pipeline this feature reuses), `cpt-studio-feature-subagent-registration` (adjacent agent-integration surface, not duplicated here)
- **ADR**: `cpt-studio-adr-ai-cli-extensibility-subagents` ([ADR-0016](../ADR/0016-cpt-studio-adr-ai-cli-extensibility-subagents-v1.md)) — accepted; scopes hooks to subagent-level only and defers project-level `SessionStart` hooks to a future decision
- **Source issue**: GitHub issue #143, constructorfabric/studio — "Studio Routing — Use Harness Session Hooks Instead of Writing Into AGENTS.md / CLAUDE.md"
- **Out of scope**:
  - Changing the payload content of the routing instruction itself (tracked separately in issue #144).
  - **Windsurf**: Windsurf is not covered by this feature. It is not in `_TOOL_PROVIDER_SUPPORT`, no session-hook mechanism for it was found during the capability survey below, and — mirroring the explicit-exclusion pattern `cpt-studio-feature-subagent-registration` uses for Windsurf subagents — it continues to receive today's unconditional `AGENTS.md`/`CLAUDE.md` file injection, unchanged and ungoverned by the disablement switch. Keeping that promise has one active requirement on this feature rather than none: because Windsurf reads the same two shared files, this feature **MUST** count a configured Windsurf as a permanent dependent of the shared marker so it is never removed out from under it — see the Windsurf marker-dependency decision below. Bringing Windsurf under this feature as a hook target would require adding it to the tool/provider matrix first and is a separate change.
  - **Generated shim-file copies of the routing precondition**: `_follow_protocol_lines()` (`skills/studio/scripts/studio/commands/agents.py`) bakes `ROOT_AGENTS_PIPELINE_INSTRUCTION` into every generated per-harness workflow/skill shim file. That is a second, independent delivery channel, separate from the `AGENTS.md`/`CLAUDE.md` channel this feature models. It is **out of scope** for this feature's disablement switch: those embedded copies persist regardless of switch state, so "routing off" for a harness removes its hook entry and its dependence on the file marker but does **not** remove the routing text already present in that harness's generated shim files. This is a known, named residual-state exception; gating the shim-file channel is deliberately left to a future iteration.
  - A dedicated ADR restating the hook-vs-file architectural choice; ADR-0016 already owns the deferral this document resolves (see below).

**Harness hook capability (surveyed 2026-09-23)**: hook capability is a per-harness property of the harness's own extensibility surface. It is **not** derivable from `_TOOL_PROVIDER_SUPPORT`, which maps tools to model providers for model/tier selection only. The table below is the authoritative capability input for `cpt-studio-algo-hook-based-session-routing-compile-harness`; implementation reads it as a dedicated table, not by reusing the provider matrix.

| Harness | Session-start hook event | Hook configuration location Studio writes | Availability |
|---------|--------------------------|-------------------------------------------|--------------|
| `claude` | `SessionStart` (all sources — see decision below) | `.claude/settings.json` | Generally available. |
| `codex` | `SessionStart` (all matchers — see decision below) | `.codex/hooks.json` | Generally available; hooks are **enabled by default** (see the Codex note below). |
| `cursor` | `sessionStart` | `.cursor/hooks.json` | Generally available. |
| `copilot` | `sessionStart` | `.github/hooks/<name>.json` | Generally available. |
| `windsurf` | None found | Not applicable | No hook mechanism found; out of scope for this feature regardless, and therefore a **permanent** dependent of the shared `AGENTS.md`/`CLAUDE.md` marker whenever it is configured for the project (see the Windsurf marker-dependency decision below). |

Capability sources: [Codex hooks](https://developers.openai.com/codex/hooks), [ChatGPT hooks reference](https://learn.chatgpt.com/docs/hooks), [Copilot CLI session lifecycle hooks](https://docs.github.com/en/copilot/how-tos/copilot-sdk/use-hooks/session-lifecycle), [Cursor hooks](https://cursor.com/docs/hooks).

**Codex hook availability — correction and decision**: Codex hooks are no longer experimental and are **enabled by default**. The canonical configuration key is `[features].hooks` (default `true`) in the user's `config.toml`, or in `requirements.toml` for administrators; the older `codex_hooks` key is a **deprecated but still-working alias** that Studio **MUST NOT** rely on going forward. Studio therefore neither writes nor requires this flag, and `codex` is treated exactly like the other three in-scope harnesses for capability-detection purposes: it takes the ordinary hook path. The only defensive case is a Codex client old enough to have hooks disabled by default (pre-promotion) or a project that has explicitly set `[features].hooks = false` — that installation simply produces no verified hook and no execution receipt, so it degrades to `FileFallback` by the ordinary rules, the same as any other harness with an unusable hook. How Studio detects that case is Section 7, item (d).

**Codex `SessionStart` matchers — decision**: Codex's `SessionStart` hook filters by a `matcher` field with four documented values — `startup` (a fresh session), `resume` (an existing session reopened), `clear` (a session manually cleared/reset), and `compact` (a session resumed after context compaction) — and omitting the matcher (or setting it to `"*"`) fires the hook for every `SessionStart` source regardless of which one initiated it ([Codex hooks](https://developers.openai.com/codex/hooks)). Registering only `startup` would mean any of the other three restart sources never fires the hook at all: because `HookInstalled` removes the file-fallback delivery path entirely once a harness is promoted (`cpt-studio-dod-hook-based-session-routing-fallback`), a session that resumes, is cleared, or is restored after compaction would silently receive no routing delivery through either channel. Enumerating a subset risks missing a source Studio doesn't currently know matters. Studio therefore **MUST** register the Codex hook entry with no matcher restriction (omitted matcher, or the explicit `"*"` form if Codex's schema requires a value), so it fires on every `SessionStart` source and promotion to `HookInstalled` never creates a delivery gap for any restart path. The exact native shape for an unfiltered/wildcard matcher entry is deferred to Section 7, item (g), alongside the rest of Codex's exact schema.

**Claude `SessionStart` sources — decision**: Claude Code's `SessionStart` hook fires with a `source` field carrying one of five documented values — `startup` (a fresh session), `resume` (an existing session reopened, e.g. `--resume`/`--continue`), `clear` (a session reset with `/clear`, which issues a new session id and a new transcript), `compact` (a session continuing after context compaction, which keeps the same session id), and `fork` (a session branched from an existing one) — and an entry registered without a source/matcher restriction fires for every one of them. Registering only `startup`, which is the effective result of leaving the matcher unstated, has exactly the same defect already corrected for Codex above: because `HookInstalled` removes the file-fallback delivery path entirely once a harness is promoted (`cpt-studio-dod-hook-based-session-routing-fallback`), a session that resumes, is cleared, is restored after compaction, or is forked would silently receive no routing delivery through either channel. Enumerating a subset risks missing a source Studio does not currently know matters. Studio therefore **MUST** register the Claude hook entry with no `SessionStart` source restriction (an omitted matcher, or the explicit `"*"` form if Claude's schema requires a value), so it fires on every one of `startup`, `resume`, `clear`, `compact`, and `fork`, and promotion to `HookInstalled` never creates a delivery gap for any restart path. The exact native shape for an unfiltered/wildcard `SessionStart` entry in `.claude/settings.json` is deferred to Section 7, item (g), alongside the rest of Claude's exact schema.

**Windsurf's permanent marker dependency — decision**: Windsurf is out of scope for this feature (see Out of scope above) and keeps today's unconditional `AGENTS.md`/`CLAUDE.md` file injection, "unchanged and ungoverned by the disablement switch". But it reads the **same two shared files** as the in-scope harnesses' fallback path, so a dependency set computed from only the four in-scope harnesses would remove the marker out from under Windsurf as soon as all four reached `HookInstalled` or `Off` — silently breaking exactly the unchanged behavior this feature promises Windsurf keeps. Windsurf is therefore treated as a **permanent marker dependent whenever it is configured for the project**: it has no hook path it could ever be promoted to, so its dependency never clears. Whether Windsurf is configured for the current project is **not** a new detection mechanism — it is the project's existing per-agent install detection in `skills/studio/scripts/studio/commands/agents.py` (`_is_agent_installed("windsurf", project_root)`, which checks the `_AGENT_MARKERS["windsurf"]` entries `.windsurf/workflows/cf.md` / `.windsurf/workflows/studio.md` and then the legacy fallback `_legacy_windsurf_install_detected()`), the same signal that already decides whether `generate-agents` writes Windsurf's surfaces at all. When that signal is true the shared marker is never removed by this feature regardless of the four in-scope harnesses' states; when it is false the existing four-harness-only dependency logic applies unchanged. This is stated as an explicit step in `cpt-studio-algo-hook-based-session-routing-reconcile-marker` and required by `cpt-studio-dod-hook-based-session-routing-fallback`.

**Codex config location — decision**: Codex accepts hook definitions in either `.codex/hooks.json` or a `[hooks]` table in `config.toml`. Studio writes to **`.codex/hooks.json` only**, for consistency with the other harnesses (each writes to a dedicated hooks file rather than sharing a general-purpose config file) and to keep Studio's writes out of a file that carries unrelated user settings. Studio **MUST NOT** write hook entries into `config.toml`.

**Native hook-entry shape (what Studio writes per harness)**: each harness's native format differs, so the cross-harness `on_session_start` abstraction (`cpt-studio-dod-hook-based-session-routing-hook-abstraction`) compiles down to the following per-harness entry shapes. Every shape carries the same three elements: the **ownership identifier** required by `cpt-studio-dod-hook-based-session-routing-hook-ownership`, the **command** to run, and the **event/matcher** binding it to session start.

| Harness | Entry container | Event/matcher binding | Command field | Ownership identifier |
|---------|-----------------|-----------------------|---------------|----------------------|
| `claude` | An entry appended under the `SessionStart` event key of the `hooks` object in `.claude/settings.json` (exact wildcard-matcher field shape — Section 7, item (g)) | The `SessionStart` event key with **no** source restriction (omitted matcher or `"*"`), so every source — `startup`, `resume`, `clear`, `compact`, `fork` — is covered | A command-type entry whose command invokes Studio's reserved hook script | The reserved Studio-owned hook-script path the command invokes — this format has no per-entry name field, so the reserved path is the identifier |
| `codex` | A single entry in the session-start array of `.codex/hooks.json` (exact wildcard-matcher field shape — Section 7, item (g)) | The `SessionStart` event with no matcher restriction (omitted or `"*"`), so every restart source — `startup`, `resume`, `clear`, `compact` — is covered | A command-type entry whose command invokes Studio's reserved hook script | The entry's own name/id field, set to Studio's fixed reserved value |
| `cursor` | An entry in the `sessionStart` array of `.cursor/hooks.json` | The `sessionStart` array it sits in | The entry's command field, invoking Studio's reserved hook script | The entry's own name/id field, set to Studio's fixed reserved value |
| `copilot` | A dedicated file `.github/hooks/<reserved-studio-name>.json` (one file per hook) | The `sessionStart` event declared inside that file | The command declared inside that file, invoking Studio's reserved hook script | The reserved filename itself |

In every shape the command invokes one Studio-owned hook script rather than an inline shell pipeline, so the ownership identifier, the payload transport (`cpt-studio-dod-hook-based-session-routing-payload-transport`), and the receipt stamp all have a single implementation per harness. The **exact native field names and nesting** of each harness's format are not pinned down by this document and must be verified against each harness's current schema at implementation time — that is Section 7, item (g).

**Reconciliation with ADR-0016**: ADR-0016 deferred project-level `SessionStart` hooks for injecting Studio context into all sessions, pending three prerequisites. This document addresses that deferral and supplies the design for the routing-precondition slice of it:

- **Config merging** — `cpt-studio-dod-hook-based-session-routing-state-file` keeps hook-install bookkeeping in a dedicated per-harness state file rather than in the harness config, and `cpt-studio-dod-hook-based-session-routing-hook-ownership` gives Studio's entry a stable owned identifier, so it can be added to and removed from a shared config (e.g. `.claude/settings.json`) idempotently without clobbering user-defined hooks.
- **Fail-open semantics** — `cpt-studio-algo-hook-based-session-routing-compile-harness` never fails the run on hook trouble: an unwritable or unverifiable hook degrades to the existing file-injection path with a warning, so routing delivery is preserved rather than blocked. Only a failure of the fallback channel itself is escalated (`cpt-studio-dod-hook-based-session-routing-write-failure`).
- **Multi-tool format divergence** — `cpt-studio-dod-hook-based-session-routing-hook-abstraction` defines one cross-harness `on_session_start` abstraction compiled per harness from the capability table above, with the fallback path covering harnesses whose hook cannot currently be used.

**ADR-0016 correction required (follow-up)**: ADR-0016 records that **Cursor has no hook support at all**. The 2026-09-23 survey above supersedes that: Cursor ships a `sessionStart` hook configured in `.cursor/hooks.json`. This document therefore treats all four in-scope harnesses as hook-capable. Amending ADR-0016's Cursor claim is a **follow-up change outside this feature's diff** and is tracked as Section 7, item (e); no design here depends on the stale claim. ADR-0016's other deferred items — project-level `PreToolUse`/`PostToolUse` validation hooks and a `cfs hooks install` / `uninstall` CLI command — remain deferred and are not addressed here.

## 2. Actor Flows (CDSL)

### Install Routing For a Project

- [ ] `p1` - **ID**: `cpt-studio-flow-hook-based-session-routing-install`

**Actor**: Project maintainer

**Success Scenarios**:
- Every in-scope harness (claude, codex, cursor, copilot) has a session-start hook, so each one installs via its own hook entry and, once that entry is confirmed to have run, stops depending on the shared file marker. This is the expected steady state.
- A harness whose hook cannot currently be used — for example an installation old enough that its hook API is unavailable, or one where the entry cannot be written — installs via the file fallback and is flagged with its one-clause reason. This is an expected outcome, not an error.
- A harness whose hook entry was written this run but has not yet been observed to run stays in `FileFallback` for one more cycle and is promoted on a later run.
- A project that also has Windsurf configured reaches the same per-harness outcomes, but keeps the shared `AGENTS.md`/`CLAUDE.md` marker even when all four in-scope harnesses are on hooks, because Windsurf permanently depends on it. This is the expected outcome for such projects, not a failure to clean up.
- The maintainer runs with `--dry-run` and sees the routing summary that a real run would produce, with nothing written — no hook entry, no receipt, no state file, no marker change.

**Error Scenarios**:
- A harness's hook entry is written but fails verification; the failed entry is cleaned up and that harness falls back to file injection with a warning.
- The file-fallback write itself fails (permissions, read-only tree, full disk); that harness is reported as `errored` with the underlying OS error, not silently as `off` or `file`.
- Routing is disabled for a harness (via the disablement switch); no hook entry and no receipt are kept for it, its state file is rewritten to record `off`, and the shared marker is dropped only if no other in-scope harness still needs it.

**Steps**:
1. [ ] - `p1` - Project maintainer runs `cfs generate-agents` (optionally with `--json`, optionally scoped with `--agent <name>`, optionally with `--dry-run`) - `inst-run-generate-agents`
   1. [ ] - `p1` - **IF** `--dry-run` is given, compute every step below and render the same `routing` summary, but write no hook entry, no execution receipt, no per-harness state file, and no change to the shared marker - `inst-dry-run-write-free`
2. [ ] - `p1` - **FOR EACH** in-scope harness selected by the run (all of claude, codex, cursor, copilot by default; exactly the named harness when `--agent` is given) - `inst-for-each-harness`
   1. [ ] - `p1` - Algorithm: resolve the harness's target routing mode and apply its hook-level changes using `cpt-studio-algo-hook-based-session-routing-compile-harness` - `inst-compile-harness`
3. [ ] - `p1` - Algorithm: reconcile the shared `AGENTS.md`/`CLAUDE.md` marker once, against the complete target-mode set, using `cpt-studio-algo-hook-based-session-routing-reconcile-marker` - `inst-reconcile-marker`
4. [ ] - `p1` - Algorithm: render per-harness install-outcome summary using `cpt-studio-algo-hook-based-session-routing-render-summary` - `inst-render-summary`
5. [ ] - `p1` - **RETURN** per-harness install outcome (routing_mode, hook_path or file_marker_paths, warnings) as a new top-level `routing` section alongside the command's existing result fields - `inst-return-install-outcome`

### Inspect Routing State

- [ ] `p2` - **ID**: `cpt-studio-flow-hook-based-session-routing-inspect`

**Actor**: CLI operator

**Success Scenarios**:
- Operator runs `cfs agents` after install and sees the per-harness routing state derived from what is actually installed on disk, not replayed from the last run's output.
- Operator runs `cfs agents` after an unrelated tool or a manual edit removed Studio's hook entry; the harness is reported as `unknown` rather than as the stale `hook` value the state file still holds.
- Operator runs `cfs agents` in the receipt-only window between the run that wrote a harness's hook entry and the later run that promotes it — the hook entry and receipt are already verified, but the state file still records `file`; the harness is reported as `file`, matching the pending promotion, not as `unknown`.

**Error Scenarios**:
- The persisted state for a harness disagrees with the resources actually installed for it; that harness is reported as `unknown` with the disagreement named, not silently trusted.
- The persisted state file for a harness is unparseable or carries an unrecognised schema version; it is treated as absent and the state is re-derived from installed resources.
- The persisted state for a harness is `errored` from an earlier failed write; the read re-tests it against the resources installed now, reporting the freshly derived mode when they resolve cleanly and `errored` with the recorded reason when they still do not.

**Steps**:
1. [ ] - `p1` - CLI operator runs `cfs agents` (the existing "show generated agent integration status" command) - `inst-run-cfs-agents`
2. [ ] - `p1` - **FOR EACH** in-scope harness selected by the run - `inst-inspect-for-each-harness`
   1. [ ] - `p1` - Algorithm: derive current routing state from installed resources and cross-check it against the persisted state file using `cpt-studio-algo-hook-based-session-routing-read-state` - `inst-read-state`
3. [ ] - `p1` - **RETURN** current per-harness routing state as a new top-level `routing` section, derived live rather than replayed from a cache - `inst-return-current-state`

## 3. Processes / Business Logic (CDSL)

### Compile Harness Routing Delivery

- [ ] `p1` - **ID**: `cpt-studio-algo-hook-based-session-routing-compile-harness`

**Input**: harness identifier (one of: claude, codex, cursor, copilot), current disablement-switch value for that harness, the harness's row from the hook-capability table (Section 1.4), `ROOT_AGENTS_PIPELINE_INSTRUCTION` payload

**Output**: provisional per-harness outcome record (target_mode: `hook` | `file` | `off` | `errored`, hook_path relative to project root when a hook entry is present, warning or error entry with its fixed-enum reason)

**Two-pass contract**: this algorithm is **pass 1** and is deliberately confined to resources owned by the single harness it is given — that harness's hook entry, that harness's state file. It never creates or removes the shared `AGENTS.md`/`CLAUDE.md` marker, and it never inspects other harnesses' target modes. All shared-resource decisions are deferred to pass 2 (`cpt-studio-algo-hook-based-session-routing-reconcile-marker`), which runs once per `generate-agents` invocation against the complete target-mode set. This is what makes the run's result independent of the order harnesses are processed in.

**Failures pass 1 can independently produce**: because this pass owns the harness's own hook entry and execution receipt, a filesystem failure removing either of those during disablement is this pass's failure to report, not pass 2's — it is not a shared-resource failure. Pass 1 therefore returns `target_mode = errored` for those failures itself (see the disablement branch below), distinct from the shared-marker `errored` outcomes pass 2 produces (`cpt-studio-dod-hook-based-session-routing-write-failure`).

**Shared-resource note (file-fallback marker)**: the file-fallback marker is **not** a per-harness resource. `_inject_root_agents()`/`_inject_root_claude()` (`skills/studio/scripts/studio/commands/init.py`) write one managed block into exactly two shared, project-wide files — root `AGENTS.md` and root `CLAUDE.md` — which multiple harnesses read by convention. There is no per-harness marker file, and the two files are treated as one logical resource. Hook entries, by contrast, are genuinely per-harness and are always added and removed with their own harness.

**Steps**:
1. [ ] - `p1` - **IF** disablement switch for this harness is "routing off" - `inst-check-disabled`
   1. [ ] - `p1` - **TRY** remove this harness's Studio-owned hook entry, matched by the stable identifier from `cpt-studio-dod-hook-based-session-routing-hook-ownership`, leaving any user-authored entries in the same config untouched - `inst-remove-hook-entry`
      1. [ ] - `p1` - **IF** the removal fails (permission denied, read-only tree, or any other filesystem error) - `inst-if-remove-hook-entry-failed`
         1. [ ] - `p1` - Record the underlying OS error and **RETURN** target_mode = `errored` — not `off` — since a hook entry that could not be removed is still on disk and this harness's disablement did not actually take effect - `inst-return-errored-hook-removal-failed`
   2. [ ] - `p1` - **TRY** remove this harness's execution receipt, so no residual delivery state remains; the harness's own state file is **retained** and is rewritten to record `routing_mode: off` by pass 2, since it is bookkeeping rather than a delivery channel - `inst-remove-receipt`
      1. [ ] - `p1` - **IF** the removal fails (permission denied, read-only tree, or any other filesystem error) - `inst-if-remove-receipt-failed`
         1. [ ] - `p1` - Record the underlying OS error and **RETURN** target_mode = `errored` — not `off` — since a residual receipt that could not be removed means the prior hook install cannot be treated as cleanly retracted; this step and `inst-remove-hook-entry` above are independent, non-compensating removals — if hook-entry removal already succeeded, this failure is reported as `errored` with that partial physical state left as-is (hook entry gone, receipt present) rather than an attempt to restore the removed hook entry (`cpt-studio-dod-hook-based-session-routing-write-failure`) - `inst-return-errored-receipt-removal-failed`
   3. [ ] - `p1` - **RETURN** target_mode = `off` (the shared marker is not touched here; pass 2 decides it) - `inst-return-off`
2. [ ] - `p1` - **IF** the harness's capability row reports no usable session-start hook — either no hook event at all, or an installed client whose hook API is unavailable (e.g. a pre-promotion Codex client, or a project that has explicitly disabled hooks) - `inst-check-hook-support`
   1. [ ] - `p1` - Record the matching fixed-enum reason and **RETURN** target_mode = `file` - `inst-return-file-no-hook`
3. [ ] - `p1` - Locate any existing Studio-owned hook entry in the harness's hook config by its stable identifier - `inst-find-owned-entry`
4. [ ] - `p1` - **IF** a Studio-owned entry already exists - `inst-if-entry-exists`
   1. [ ] - `p1` - Replace that entry in place with the freshly compiled one, so repeat runs update rather than duplicate it; any additional entries carrying the same identifier are collapsed to one - `inst-replace-owned-entry`
5. [ ] - `p1` - **ELSE** append a new Studio-owned entry to the harness's hook config, preserving every entry Studio does not own - `inst-append-owned-entry`
6. [ ] - `p1` - Embed the payload using the harness's transport rule from `cpt-studio-dod-hook-based-session-routing-payload-transport`, sourcing the text from `ROOT_AGENTS_PIPELINE_INSTRUCTION` without duplicating or hardcoding it - `inst-embed-payload`
7. [ ] - `p1` - Algorithm: verify the hook install using `cpt-studio-algo-hook-based-session-routing-verify-hook` - `inst-verify-hook`
8. [ ] - `p1` - **IF** verification fails - `inst-if-verify-failed`
   1. [ ] - `p1` - Remove the unverified Studio-owned entry that was just written, restoring the config to its pre-run content, so no orphaned hook entry is left beside the file fallback - `inst-cleanup-failed-entry`
   2. [ ] - `p1` - Record the matching fixed-enum reason and **RETURN** target_mode = `file` - `inst-return-file-verify-failed`
9. [ ] - `p1` - **IF** the harness's execution receipt does not show this exact hook entry having run at least once since it was written - `inst-check-receipt`
   1. [ ] - `p1` - Record the "hook installed, first run not yet observed" fixed-enum reason and **RETURN** target_mode = `file`, so the fallback keeps delivering for one more cycle while the hook proves itself - `inst-return-file-pending-receipt`
   2. [ ] - `p1` - The entry written this run is in its **receipt-only** window: because the file fallback is still delivering, the hook's command stamps the receipt but **MUST NOT** also emit the payload, so the harness cannot receive the routing text twice in one session (`cpt-studio-dod-hook-based-session-routing-payload-transport`) - `inst-receipt-only-window`
10. [ ] - `p1` - **RETURN** target_mode = `hook`, hook_path relative to project root - `inst-return-hook-mode`

### Reconcile Shared Fallback Marker

- [ ] `p1` - **ID**: `cpt-studio-algo-hook-based-session-routing-reconcile-marker`

**Input**: the complete set of target modes produced by pass 1 for the harnesses this run touched, plus the last known mode of every in-scope harness this run did **not** touch (from `cpt-studio-algo-hook-based-session-routing-read-state`), plus whether Windsurf — an out-of-scope but marker-reading harness — is configured for this project (the project's existing per-agent install detection, `_is_agent_installed("windsurf", project_root)` in `skills/studio/scripts/studio/commands/agents.py`)

**Output**: final per-harness outcome records (routing_mode, hook_path or the pair of file_marker_paths, warnings and errors — field schema in `DESIGN.md`'s `HarnessRoutingOutcome`), with state persisted for every harness where the persistence write itself succeeds, and a `level: error` `warnings` entry reported where it does not — except a harness being **newly promoted** to `hook` this run (one whose state file does not already durably record `hook`), whose `routing_mode` is itself revised back to `file` when that specific persist fails (see the promotion-before-removal ordering below)

**Order independence**: this algorithm runs exactly once per `generate-agents` invocation, after every selected harness has been through pass 1. It reads the complete target-mode set rather than a partially-processed one, so the outcome does not depend on the order harnesses were iterated in.

**Dependents are not limited to the four in-scope harnesses**: the two shared files are read by every harness that follows the `AGENTS.md`/`CLAUDE.md` convention, not only by the four harnesses this feature governs. Windsurf is out of scope for hook install but reads the same two files and has no hook path it could ever be promoted to, so a dependency set built from the four in-scope harnesses alone would remove the marker as soon as all four reached `hook` or `off` — breaking Windsurf's delivery, which Section 1.4 promises stays unchanged. Step 4 below therefore adds a configured Windsurf to the dependency set as a **permanent** dependent that never clears. Detection is the project's existing per-agent install signal (`_is_agent_installed("windsurf", project_root)`), not a new mechanism; when that signal is false, the dependency set is exactly the four-harness set as before.

**Two files, one resource**: root `AGENTS.md` and root `CLAUDE.md` are treated as a single logical resource. They are always written together and always cleared together. If they have diverged — one carries the managed block and the other does not — this algorithm restores **both** to whichever target it computes, rather than preserving the divergence.

**Promotion-before-removal ordering**: a harness being **newly promoted** to HookInstalled this run is the one case where the shared-marker decision and state-file persistence are coupled. If the marker were removed before that harness's `hook` state is durably on disk, the harness would sit in a window where neither channel delivers: the marker is gone, and the hook stays receipt-only (silent) because the persisted mode the hook command reads at execution time does not yet say `hook` (`cpt-studio-dod-hook-based-session-routing-payload-transport`). Step 1 below therefore durably persists such a promotion **before** the dependency set (step 2) is built, and revises the target mode back to `file` — keeping the harness a marker dependent — whenever that specific persist fails, so an undurable promotion can never cause the marker to be removed out from under it.

**What counts as "newly promoted"** — the trigger is the **state of the file on disk**, not the specific previous mode. Step 1 applies to every harness whose pass-1 target mode is `hook` and whose state file does **not** already durably record `routing_mode: hook` — that is, the persisted mode going into this run was `file`, `off`, or `errored`, **or** the state file was absent, unparseable, or carried an unrecognised `schema_version` (all of which the hook command's own execution-time read treats as "not `hook`", so the hook would not emit). A `file` → `hook` promotion is only the most common of these; a harness re-enabled from `off`, recovering from `errored`, or whose state file was deleted or corrupted outside Studio needs the same ordering for the same reason. The converse is equally important: a harness whose state file **already** records `hook` from a prior successful run is deliberately **not** in step 1's set — its correct `hook` value is already durably on disk, so a failed re-persist in step 8 cannot change what the hook command reads at execution time and cannot open a delivery gap. That case is a bookkeeping-only failure, reported under step 8's `inst-report-persist-failure` rule without touching `routing_mode`.

**Steps**:
1. [ ] - `p1` - **FOR EACH** in-scope harness whose pass-1 target mode is `hook` **AND** whose state file does not already durably record `routing_mode: hook` — persisted `file`, `off`, or `errored`, or an absent, unparseable, or unrecognised-`schema_version` file (i.e. this run is newly promoting it to HookInstalled) - `inst-promote-persist-first`
   1. [ ] - `p1` - **TRY** persist `routing_mode: hook` to that harness's own state file now, before any shared-marker decision is made - `inst-promote-persist-attempt`
      1. [ ] - `p1` - **IF** the persist write fails (permission denied, read-only tree, no space, or any other filesystem error) - `inst-if-promote-persist-failed`
         1. [ ] - `p1` - Revise this harness's target mode for the remainder of this run from `hook` back to `file` — the promotion did not durably take effect, so the harness still depends on the shared marker and MUST NOT be reported as `hook` - `inst-revise-target-file`
         2. [ ] - `p1` - Append a `level: error` entry to the outcome record's `warnings` array with `reason` carrying the underlying OS error text, reusing the same array shape as the general persistence-failure warning below, so the failed promotion is surfaced directly rather than silently retried - `inst-promote-persist-error-warning`
         3. [ ] - `p1` - Contribute this failure to the command's existing `PARTIAL` result contract - `inst-promote-persist-partial`
         4. [ ] - `p1` - Leave the freshly written and verified hook entry and its receipt in place on disk (they are **not** rolled back); pass 1 will independently re-derive `target_mode = hook` again on a later run while the receipt is still present, so the promotion is retried automatically once the state-file write can succeed - `inst-promote-persist-retry-later`
      2. [ ] - `p1` - **ELSE** the harness's `routing_mode: hook` is now durably persisted; step 8 below re-affirms the same value for it (idempotent) rather than persisting it again for the first time - `inst-promote-persist-succeeded`
2. [ ] - `p1` - Build the dependency set: every in-scope harness whose target mode for this run is `file` — using the mode as revised by step 1, so a harness whose promotion could not be durably persisted this run still counts as a dependent - `inst-build-dependency-set`
3. [ ] - `p1` - **FOR EACH** in-scope harness not selected by this run (e.g. when `--agent` scoped the run to one harness) - `inst-for-each-untouched`
   1. [ ] - `p1` - **IF** that harness's last known mode cannot be determined — state file missing, unparseable, or inconsistent with its installed resources - `inst-if-sibling-unknown`
      1. [ ] - `p1` - Treat it conservatively as still depending on the shared marker and add it to the dependency set, so an undeterminable sibling can never cause the marker to be removed out from under it - `inst-assume-dependency`
   2. [ ] - `p1` - **ELSE** add it to the dependency set only when its last known mode is `file` - `inst-add-known-dependency`
4. [ ] - `p1` - **IF** Windsurf is configured for this project, per the existing per-agent install detection (`_is_agent_installed("windsurf", project_root)`: the `_AGENT_MARKERS["windsurf"]` files `.windsurf/workflows/cf.md` / `.windsurf/workflows/studio.md`, then the legacy `_legacy_windsurf_install_detected()` fallback) - `inst-if-windsurf-configured`
   1. [ ] - `p1` - Add Windsurf to the dependency set as a **permanent** dependent that no state of the four in-scope harnesses can clear, since Windsurf reads the same two shared files, has no hook channel to be promoted to, and is not governed by this feature's disablement switch — so the marker is never removed while Windsurf is configured - `inst-add-windsurf-dependency`
   2. [ ] - `p1` - Do **NOT** create, read, or write a routing state file for Windsurf, and do **NOT** emit a `HarnessRoutingOutcome` record for it; Windsurf remains out of scope and participates in this algorithm only as a marker dependent - `inst-windsurf-not-a-harness-record`
5. [ ] - `p1` - **ELSE** leave the dependency set as computed from the in-scope harnesses alone, so a project without Windsurf behaves exactly as before - `inst-else-no-windsurf`
6. [ ] - `p1` - **IF** the dependency set is empty - `inst-if-no-dependents`
   1. [ ] - `p1` - Remove the managed block from **both** root `AGENTS.md` and root `CLAUDE.md` as one operation, using the existing marker-rewrite helpers in `skills/studio/scripts/studio/commands/init.py` - `inst-remove-shared-marker`
   2. [ ] - `p1` - **IF** removing the block from either file fails (permission denied, read-only tree, or any other filesystem error) - `inst-if-remove-failed`
      1. [ ] - `p1` - Roll the pair back to its pre-run content where possible, and set routing_mode = `errored` — not `off` — for every harness this run resolved to `off`, attaching the underlying OS error text, so a removal that did not actually happen is never finalized as a clean disablement - `inst-mark-remove-error`
7. [ ] - `p1` - **ELSE** - `inst-else-has-dependents`
   1. [ ] - `p1` - Ensure the managed block is present and identical in **both** root `AGENTS.md` and root `CLAUDE.md`, reusing the existing `_compute_managed_block`/`_inject_managed_block` marker injection; the operation is idempotent, so several dependent harnesses produce one block, not several - `inst-ensure-shared-marker`
   2. [ ] - `p1` - **IF** writing either file fails (permission denied, read-only tree, no space, or any other filesystem error) - `inst-if-file-write-failed`
      1. [ ] - `p1` - Roll the pair back to its pre-run content where possible, and set routing_mode = `errored` for every harness in the dependency set, attaching the underlying OS error text so the maintainer sees the real cause rather than a bare `off` or `file` - `inst-mark-write-error`
8. [ ] - `p1` - **FOR EACH** harness affected by this run — every harness the run touched, **plus** every in-scope harness the run did not select whose state this run's shared-marker outcome changed (e.g. an unselected dependent marked `errored` by a failed shared-marker write on an `--agent`-scoped run); Windsurf is never in this set, since it has no state file and no outcome record - `inst-for-each-finalize`
   1. [ ] - `p1` - Resolve its final routing_mode from its (possibly step-1-revised) target mode and the marker outcome above - `inst-resolve-final-mode`
   2. [ ] - `p1` - **TRY** persist that final state to the harness's own state file for **every** mode — `off`, `file`, `hook`, and `errored` alike — so a later inspection never has to guess from a missing file; for a harness already durably persisted by step 1, this re-affirms the same `hook` value rather than persisting it for the first time - `inst-persist-state-all-modes`
      1. [ ] - `p1` - **IF** the state-file write itself fails (permission denied, read-only tree, or any other filesystem error) - `inst-if-persist-failed`
         1. [ ] - `p1` - Do **NOT** attempt to persist an `errored` state into the file that just proved it cannot be written — there is no on-disk state to persist that failure into - `inst-persist-no-recursive-error`
         2. [ ] - `p1` - Keep this run's already-resolved `routing_mode` for the harness unchanged — the channel-establishment outcome is unaffected by a bookkeeping write failure, and this is delivery-safe precisely because step 1 has already excluded the only mode where it would not be: any harness reported `hook` at this point already had `hook` durably on disk before this step ran (step 1 wrote it, or a prior run did), so the hook command's execution-time read is unaffected by this failed rewrite - `inst-persist-failure-mode-unchanged`
         3. [ ] - `p1` - Append a `level: error` entry to the outcome record's `warnings` array, reusing the same array shape as the fallback warning, with `reason` carrying the underlying OS error text, so the failure is surfaced directly to the caller in this run's summary and `--json` output rather than silently dropped - `inst-report-persist-failure`
         4. [ ] - `p1` - Contribute this failure to the command's existing `PARTIAL` result contract, exactly as other `errored`-class failures do, even though `routing_mode` itself is not downgraded - `inst-persist-failure-partial`
         5. [ ] - `p1` - **REPORTING ONLY** — for `cfs agents` output, `cpt-studio-algo-hook-based-session-routing-read-state` re-derives this harness's state from installed resources rather than trusting the stale on-disk file, so inspection does not report the stale value and the file is rewritten on the next successful run; this re-derivation governs what the **CLI reports** and never what the **hook command reads at execution time**, which always reads the state file itself (`cpt-studio-dod-hook-based-session-routing-payload-transport`) — delivery safety across a failed persist comes from step 1's ordering, not from this re-derivation - `inst-persist-failure-selfcorrects`
   3. [ ] - `p1` - **IF** routing_mode = `file` - `inst-if-final-file`
      1. [ ] - `p1` - Append a `level: warning` entry to the outcome record's `warnings` array, reusing the CLI's existing `warnings` array shape (as in `cfs info --json`), with a one-clause `reason` drawn from the fixed limitation-reason enum (see Section 7, item c) - `inst-append-fallback-warning`
9. [ ] - `p1` - **RETURN** the finalized outcome records - `inst-return-final-outcomes`

### Verify Hook Install

- [ ] `p1` - **ID**: `cpt-studio-algo-hook-based-session-routing-verify-hook`

**Input**: harness identifier, hook config path, the payload text that was supposed to be embedded

**Output**: verified (boolean)

**What this proves, and what it does not**: these checks prove that Studio's own entry is present in the harness's config, well-formed under that config's format, and carrying the payload intact. They do **not** prove the harness has registered the entry or will execute it. That gap is closed separately, outside this algorithm, by the execution-receipt gate in `cpt-studio-algo-hook-based-session-routing-compile-harness`: file fallback is retained until the hook is observed to have actually run. Verification alone never authorises dropping the fallback.

**Steps**:
1. [ ] - `p1` - **IF** the hook config file does not exist at the expected path - `inst-verify-missing`
   1. [ ] - `p1` - **RETURN** verified = false - `inst-verify-return-false-missing`
2. [ ] - `p1` - **TRY** - `inst-verify-try`
   1. [ ] - `p1` - Parse the hook config with the harness's own format (e.g. JSON for `.claude/settings.json`, `.cursor/hooks.json`, `.codex/hooks.json`) - `inst-verify-parse`
   2. [ ] - `p1` - Locate exactly one entry bearing Studio's stable ownership identifier, and confirm it is bound to that harness's session-start event as named in the capability table - `inst-verify-locate-owned-entry`
   3. [ ] - `p1` - Compare the payload recovered from the entry, after reversing the harness's transport encoding, against the payload text that was supposed to be embedded; confirm it round-trips byte-for-byte so quoting, escaping, and newlines survived - `inst-verify-payload-fidelity`
3. [ ] - `p1` - **CATCH** parse error, missing or duplicated owned entry, or payload mismatch - `inst-verify-catch`
   1. [ ] - `p1` - **RETURN** verified = false - `inst-verify-return-false-parse-error`
4. [ ] - `p1` - **RETURN** verified = true - `inst-verify-return-true`

### Render Install-Outcome Summary

- [ ] `p1` - **ID**: `cpt-studio-algo-hook-based-session-routing-render-summary`

**Input**: list of finalized per-harness outcome records

**Output**: a `routing` section rendered through the CLI's shared result helper — a human-readable table by default, the same data as structured output under `--json`

**Steps**:
1. [ ] - `p1` - **FOR EACH** outcome record - `inst-summary-for-each`
   1. [ ] - `p1` - Render harness name, routing_mode, and either the hook config path or the pair of shared file-marker paths, all expressed relative to project root (never absolute, for `--json` stability across machines/CI) - `inst-render-row`
   2. [ ] - `p1` - **IF** routing_mode = `file` (fallback in effect) - `inst-render-if-fallback`
      1. [ ] - `p1` - Render the row as a visually distinct warning-level line, including the one-clause limitation reason - `inst-render-fallback-warning-line`
   3. [ ] - `p1` - **IF** routing_mode = `errored` - `inst-render-if-errored`
      1. [ ] - `p1` - Render the row as an error-level line carrying the underlying filesystem error, and contribute to the command's existing `PARTIAL` result contract rather than being reported as a successful install - `inst-render-error-line`
2. [ ] - `p1` - Attach the rendered section under a new top-level `routing` key, leaving the command's existing result fields (`status`, `agents`, `project_root`, `studio_root`, `results`) unchanged - `inst-attach-routing-section`
3. [ ] - `p1` - **RETURN** rendered summary (table or structured payload, same underlying data) - `inst-return-rendered-summary`

### Read Current Routing State

- [ ] `p2` - **ID**: `cpt-studio-algo-hook-based-session-routing-read-state`

**Input**: harness identifier

**Output**: current routing state, derived from installed resources and cross-checked against the persisted state file

**Derivation precedence**: the installed resources are the source of truth and the state file is a cross-check, not an oracle. Derived state resolves as `HookInstalled` when a verified Studio-owned hook entry and a confirming receipt are both present; otherwise `FileFallback` when the shared marker is present; otherwise `Off`. `unknown` is reserved for a genuine disagreement between derived and persisted state — it is never the answer merely because a file is absent.

**Why `Errored` needs its own inspection rule**: `Errored` is the one persisted state derivation cannot produce. It is set at the moment of a failed write, and nothing on disk afterwards says "the last write failed" — so a later read that only ran the precedence rule above would either silently downgrade a genuinely broken harness to `off`/`file`, or report it as `unknown` merely because derivation cannot express it. Inspection therefore treats a persisted `errored` as a **claim to re-test**, not as a disagreement: it re-attempts derivation against the resources as they are now, reports the freshly derived mode when the resources resolve cleanly (the error was transient or has since been fixed by hand), and keeps reporting `errored` with the reason recorded in the state file when they still do not.

**Why the pending-first-run window needs its own inspection rule**: `cpt-studio-dod-hook-based-session-routing-payload-transport` makes the hook receipt-only until a later `generate-agents` run promotes the harness to `HookInstalled` — so between the run that writes the hook entry and receipt and the run that persists `routing_mode: hook`, there is a window where derivation (a verified hook entry plus an observed receipt) would independently derive `hook` while the persisted state still reads `file`. That disagreement is **expected and benign**, not drift: it is exactly the receipt-only handoff working as designed, and promotion to `hook` is deliberately deferred to the later run, not to this read. Inspection therefore treats this specific combination — a verified Studio-owned hook entry and its confirming receipt both present, **and** the persisted `routing_mode` is `file` — as a known transitional state, not a disagreement, and reports the persisted `file` value rather than `unknown`. This is narrower than the general disagreement rule below: it applies only when the derived and persisted values are exactly `hook` (derived) vs. `file` (persisted) with both the hook entry and receipt intact. Any other mismatch — including a persisted `hook` whose hook entry or receipt is now missing, or a persisted `file` where the derived value is `off` — is still a genuine disagreement and still resolves to `unknown` by the rule below.

**Steps**:
1. [ ] - `p1` - Derive the harness's actual state from installed resources: presence and verifiability of its Studio-owned hook entry, presence of its execution receipt, and presence of the shared `AGENTS.md`/`CLAUDE.md` managed block - `inst-derive-from-resources`
2. [ ] - `p1` - Read the harness's own state file, treating it as absent when it is missing, unparseable, or carries a `schema_version` this Studio version does not recognise - `inst-read-state-file`
3. [ ] - `p1` - **IF** the state file is absent by that definition - `inst-read-state-missing`
   1. [ ] - `p1` - **RETURN** the derived state, and repair the state file by rewriting it from that derivation on the next `generate-agents` run; a fresh project with nothing installed therefore reports `off`, matching the initial state in Section 4, rather than `unknown` - `inst-return-derived-state`
4. [ ] - `p1` - **IF** the persisted state is `errored` - `inst-if-persisted-errored`
   1. [ ] - `p1` - Re-attempt derivation from the resources actually installed now, treating the persisted `errored` as a claim to re-test rather than as a disagreement - `inst-reattempt-derivation`
   2. [ ] - `p1` - **IF** the resources resolve cleanly — the derived state is one of `off`, `file`, or `hook` with no half-installed evidence (no unverifiable Studio-owned hook entry, and the shared managed block either present in both root files or absent from both) - `inst-if-errored-resolved`
      1. [ ] - `p1` - **RETURN** the freshly derived state, treating the recorded error as transient or since repaired; the state file is rewritten from that derivation on the next `generate-agents` run - `inst-return-recovered-state`
   3. [ ] - `p1` - **ELSE RETURN** routing_mode = `errored`, carrying the failure reason recorded in the state file, since delivery is still not established - `inst-return-still-errored`
5. [ ] - `p1` - **IF** the persisted state is `file`, and the derived state is `hook` because a verified Studio-owned hook entry and its confirming receipt are both present - `inst-if-pending-first-run`
   1. [ ] - `p1` - **RETURN** routing_mode = `file`, matching the persisted value; this is the expected receipt-only handoff window (`cpt-studio-dod-hook-based-session-routing-payload-transport`), not a disagreement, and promotion to `hook` is deferred to the later run that persists it - `inst-return-pending-first-run-file`
6. [ ] - `p1` - **IF** the persisted state disagrees with the derived state (for example the file says `hook` but the hook entry was removed outside Studio, or it says `file` while the shared marker is gone) - `inst-if-state-disagrees`
   1. [ ] - `p1` - **RETURN** routing_mode = `unknown`, naming both the persisted and the derived value so the maintainer can see what drifted; the harness is reported, never silently omitted - `inst-return-unknown-state`
7. [ ] - `p1` - **RETURN** the agreed state for this harness - `inst-return-current-outcome`

## 4. States (CDSL)

### Per-Harness Routing State

- [ ] `p1` - **ID**: `cpt-studio-state-hook-based-session-routing-per-harness`

**States**: Off, FileFallback, HookInstalled, Errored (serialized as `off`, `file`, `hook`, `errored` per the mapping table in Section 1.1)

**Initial State**: Off for a project that has never had the routing precondition delivered — a project with no state file and no installed resources derives to Off, not to `unknown`. For a project already managed by Studio before this feature ships, the initial state is **FileFallback**, not Off — see the migration note below.

**Transitions**:
1. [ ] - `p1` - **FROM** Off **TO** FileFallback **WHEN** disablement switch is set to "routing on" and the harness's hook cannot currently be used, hook write or verify fails, or the hook's first execution has not yet been observed - `inst-transition-off-to-file`
2. [ ] - `p1` - **FROM** Off **TO** HookInstalled **WHEN** disablement switch is set to "routing on" and hook write, verify, and execution-receipt confirmation all succeed - `inst-transition-off-to-hook`
3. [ ] - `p1` - **FROM** FileFallback **TO** HookInstalled **WHEN** a later run finds the hook usable and its entry written, verified, and confirmed to have run - `inst-transition-file-to-hook`
4. [ ] - `p1` - **FROM** HookInstalled **TO** FileFallback **WHEN** a later run finds the previously-verified hook entry missing, unverifiable, or no longer carrying the intact payload - `inst-transition-hook-to-file`
5. [ ] - `p1` - **FROM** FileFallback **TO** Off **WHEN** disablement switch is set to "routing off"; the shared `AGENTS.md`/`CLAUDE.md` marker is removed by the reconciliation pass only if no dependent remains — no in-scope harness in FileFallback and no configured Windsurf — and is otherwise left in place - `inst-transition-file-to-off`
6. [ ] - `p1` - **FROM** HookInstalled **TO** Off **WHEN** disablement switch is set to "routing off"; this harness's hook entry and receipt are removed while its state file is retained and rewritten to record `off`, and the shared marker is removed by the reconciliation pass only if no dependent remains (no in-scope harness in FileFallback and no configured Windsurf) - `inst-transition-hook-to-off`
7. [ ] - `p1` - **FROM** any state **TO** Errored **WHEN** the shared-marker write or removal this harness depends on fails with a filesystem error, so neither channel is known to be delivering — or, for a harness being disabled, so the marker Studio meant to remove is still on disk, or removing this harness's own hook entry or execution receipt fails, so residual delivery state cannot be confirmed removed - `inst-transition-any-to-errored`
8. [ ] - `p1` - **FROM** Errored **TO** FileFallback, HookInstalled, or Off **WHEN** a later run succeeds in establishing the corresponding channel, or when a later inspection re-tests the recorded error and finds the installed resources now resolving cleanly - `inst-transition-errored-to-delivering`

No partial-downgrade state exists: a harness is always in exactly one of Off, FileFallback, HookInstalled, or Errored; the disablement switch (`cpt-studio-dod-hook-based-session-routing-disablement`) flips this harness's hook state and its dependence on the file marker atomically. `Errored` is distinct from `Off`: `Off` is an intentional, successful outcome, while `Errored` records that Studio tried and could not establish delivery, and is surfaced as an error-level line.

**Persistence failure is not a transition**: a failure to write the final state file for an otherwise cleanly resolved mode (`cpt-studio-algo-hook-based-session-routing-reconcile-marker` step `inst-if-persist-failed`) does **not** by itself drive a transition to Errored. The channel-establishment outcome (what state the harness is actually *in*) and the state-file persistence outcome (whether that fact got written to disk) are tracked independently; the run reports the persistence failure directly as a `level: error` `warnings` entry rather than reclassifying the harness's resolved state. The one exception is a **new** promotion into HookInstalled (step `inst-promote-persist-first`) — a harness whose target is `hook` and whose state file does not already durably record `hook`, whether it is arriving from FileFallback, from Off, from Errored, or from a state file that was absent or corrupt. Because hook emission is gated on the persisted mode the hook command reads at execution time actually saying `hook`, a failed persist at the moment of promotion means the harness never actually reached HookInstalled this run: it is correctly reported as `file` and remains a marker dependent, which is not a reclassification to Errored but simply the transition into HookInstalled (`inst-transition-file-to-hook` / `inst-transition-off-to-hook`) not yet having occurred. A harness **already** in HookInstalled with `hook` durably on disk from a prior run is not affected — its file already carries the value the hook command reads, so a failed rewrite this run cannot open a delivery gap and is reported as a bookkeeping failure only.

**Shared marker, not per-harness state**: Off means "Studio installs and maintains no routing delivery for this harness" — no hook entry, no execution receipt, and no counted dependence on the shared marker. It deliberately does **not** mean "this harness's process cannot see the routing text". Because the file marker lives in two shared, project-wide files (root `AGENTS.md`/`CLAUDE.md`) rather than one file per harness, an Off harness may coexist with a marker still on disk for another dependent's sake — another in-scope harness in FileFallback, or a configured Windsurf, whose dependence never clears — and a harness that reads those files by its own convention still reads it. That is not residual state for the Off harness; it is another harness's live state. The limitation is inherent to reusing the pre-existing shared file-injection mechanism and is an accepted constraint, not a defect (Section 1.2 and `cpt-studio-dod-hook-based-session-routing-disablement`); disabling one harness therefore does not necessarily empty the shared files, and Off **MUST NOT** be described anywhere as per-harness isolation from them.

**All four in-scope harnesses can reach HookInstalled**: per the capability survey in Section 1.4, claude, codex, cursor, and copilot each expose a session-start hook that is available by default, so every transition above applies identically to every in-scope harness — `codex` included, with no opt-in special case. Any harness whose installed client has hooks turned off or unavailable resolves to FileFallback with the corresponding fixed-enum reason, which is a configuration-dependent outcome rather than a permanent property of the harness, and moves to HookInstalled by the ordinary transitions once the hook becomes usable and its first execution is observed.

**Migration from pre-existing file injection**: every Studio-managed project created before this feature already has the routing precondition injected unconditionally into root `AGENTS.md`/`CLAUDE.md` (per `cpt-studio-feature-agent-integration`). On the first post-upgrade `cfs generate-agents` run, such a project MUST be read as starting in FileFallback for every in-scope harness — the existing marker is recognised as the file-fallback state, not ignored or re-injected — and each harness then proceeds through the normal transitions from there. Because the two shared files are one logical resource, the marker being present in **either or both** of root `AGENTS.md` and root `CLAUDE.md` is sufficient evidence of prior FileFallback for the whole in-scope harness set; a partial state left by a manual edit or an interrupted earlier run is treated as prior FileFallback and reconciled so both files match the computed target. Upgrading MUST NOT require the project to pass through Off, and MUST NOT produce a duplicate marker.

## 5. Definitions of Done

### Cross-Harness Hook Abstraction

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-hook-abstraction`

The system **MUST** implement a single cross-harness "on_session_start" abstraction, compiled per harness inside `cfs generate-agents` (`skills/studio/scripts/studio/commands/agents.py`).

The system **MUST** drive hook capability from a dedicated per-harness capability table that names, for each in-scope harness, its session-start event name and the single hook configuration path Studio writes to — the table in Section 1.4. Where a harness accepts more than one configuration location (Codex accepts `.codex/hooks.json` or a `[hooks]` table in `config.toml`), the system **MUST** write only the location named in that table and **MUST NOT** write the alternative. The abstraction **MUST** compile down to the per-harness native entry shape recorded in Section 1.4 — ownership identifier, command, and event/matcher binding — rather than a shape invented per call site. The system **MUST NOT** infer hook capability from `_TOOL_PROVIDER_SUPPORT`/`_TOOL_PROVIDER_DEFAULT`, which map tools to model providers for model/tier selection and carry no hook information; that matrix **MAY** still be used for its existing purpose of enumerating which harnesses are in scope.

When the run is scoped with `--agent <name>`, the system **MUST** compile routing for exactly that harness — matching how `--agent` already scopes every other `generate-agents` behavior — while the shared-marker reconciliation **MUST** still account for all in-scope harnesses (and for a configured Windsurf, per `cpt-studio-dod-hook-based-session-routing-fallback`), so a scoped run cannot remove a marker an unselected harness still needs.

**`--agent` scoping is not a write boundary for routing state — disclosed exception**: `--agent` scopes which harness's routing is *compiled*, but the shared marker is one project-wide resource, so a scoped run's marker outcome can change an **unselected** in-scope harness's state — most notably a failed shared-marker write, which marks every harness in the dependency set `errored`. `cpt-studio-dod-hook-based-session-routing-state-file` requires that harness's own state file to be written too. The system **MUST** therefore treat routing-state persistence as covering the run's full *affected* set (`cpt-studio-algo-hook-based-session-routing-reconcile-marker` step `inst-for-each-finalize`), not just the `--agent` selection, and this exception **MUST** be disclosed in the `generate-agents` contract in [specs/cli.md](../specs/cli.md) rather than left as a surprise. No *other* surface is affected: an unselected harness's hook entry, execution receipt, and generated files are never touched by a scoped run.

**`--dry-run` is write-free for routing too**: `cfs generate-agents --dry-run` already computes planned changes without writing files, and routing **MUST** participate in that contract with no exception of its own. Under `--dry-run` the system **MUST** compute and report the routing summary that *would* result — the same `routing` section, per-harness `routing_mode`, paths, and warnings — while writing **no** hook entry, **no** execution receipt, **no** per-harness state file (including the promotion-first persist of `inst-promote-persist-first`), and **no** change to the shared `AGENTS.md`/`CLAUDE.md` marker. Because the promotion-first persist does not happen, a harness that a real run would promote **MUST** be reported under `--dry-run` as the mode that a real run would produce, and the absence of that write **MUST NOT** be reported as a persistence failure. `--dry-run` **MUST NOT** be used as a disablement path: it changes nothing, so a harness's existing routing state on disk is left exactly as it was.

**Implements**:
- `cpt-studio-flow-hook-based-session-routing-install`
- `cpt-studio-algo-hook-based-session-routing-compile-harness`

**Touches**:
- Entities: `HarnessRoutingOutcome`

### Studio-Owned Hook Entry Identity

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-hook-ownership`

The system **MUST** stamp the hook entry it writes with a stable, Studio-owned identifier — a fixed reserved value in the harness's own naming field (the entry's `name`/`id` for configs that key entries by name, or the reserved hook filename for harnesses such as Copilot that use one file per hook), per the per-harness entry-shape table in Section 1.4. Where a harness's format has **no** per-entry naming field at all, the identifier **MUST** be the reserved Studio-owned hook-script path the entry's command invokes — a path Studio owns exclusively, matched as a whole path rather than by scanning free-form command text (Section 7, item (g)). This identifier plays the same ownership role for hook configs that `MARKER_START`/`MARKER_END` plays for the file-injection path.

The system **MUST** use that identifier as the sole means of finding, replacing, and removing its own entry, and **MUST NOT** match entries by event name, command text, or position, so a user's own session-start hook in the same config is never clobbered. Every entry Studio does not own **MUST** survive install, reinstall, and uninstall byte-for-byte.

A repeat install — `generate-agents` run again when a Studio-owned entry already exists — **MUST** replace that entry in place rather than appending a second one, and **MUST** collapse any pre-existing duplicates bearing the identifier to exactly one entry.

A hook entry that is written and then fails verification **MUST** be removed before the fallback path is taken, restoring the config to its pre-run content, so no orphaned unverified hook entry is left on disk alongside the file-fallback marker.

**Implements**:
- `cpt-studio-algo-hook-based-session-routing-compile-harness`
- `cpt-studio-algo-hook-based-session-routing-verify-hook`

### Hook Payload Transport

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-payload-transport`

The system **MUST** define, per harness, exactly one transport for getting `ROOT_AGENTS_PIPELINE_INSTRUCTION` — multi-line text containing quotes — into that harness's hook format, and **MUST** apply that harness's native escaping rather than string concatenation. Each harness's hook entry invokes a command, so the system **MUST** use a Studio-written payload file referenced by that command as the default transport, with direct embedding as an escaped string value permitted only where the harness's format accepts the full payload losslessly. The chosen transport per harness is Section 7, item (f).

The system **MUST** make the hook command, on execution, both emit the payload to the harness and stamp a per-harness execution receipt recording that this exact entry ran. That receipt is the "first observed execution" signal the fallback gate depends on.

**Delivery is unconditional**: when a harness is in `HookInstalled`, the hook **MUST** emit the payload on **every** configured session-start execution, with no per-session relevance, task-type, or "does this session need Studio?" check. This is deliberate and mirrors today's unconditional `AGENTS.md`/`CLAUDE.md` injection exactly — the same text reaches every session either way; only the channel changes.

**Receipt-only during the pending-first-run window**: between the run that writes a hook entry and the run that observes its receipt, the file fallback is still delivering (`cpt-studio-dod-hook-based-session-routing-fallback`), so an entry that also emitted the payload would deliver the routing text twice in one session. The hook command **MUST** therefore behave in two phases: while the harness's persisted mode is anything other than `hook`, the command stamps the receipt and emits **nothing**; once the receipt has been observed and the harness has been promoted to `HookInstalled`, the command both stamps the receipt and emits the payload — which is also the point at which file-fallback delivery stops. Exactly one channel therefore delivers the payload at any moment.

**What the hook command reads at execution time, and how**: the phase decision above is made per firing, from disk, and the read target is named here rather than left implicit. On every session-start firing the hook command **MUST** read exactly one file — **the harness's own per-harness routing state file**, `<harness-config-dir>/.cf-studio-routing-state.json` (`cpt-studio-dod-hook-based-session-routing-state-file`; `.claude/`, `.codex/`, `.cursor/`, `.github/` respectively) — and **MUST** take its phase from that file's `routing_mode` field alone. It **MUST NOT** re-derive the mode from installed resources, consult the shared marker, or call back into Studio: the read is a single small local file read on a latency-sensitive path, and `cpt-studio-algo-hook-based-session-routing-read-state`'s derivation-and-cross-check rules govern **CLI reporting only**, never this read. The command emits the payload **if and only if** that read yields exactly `routing_mode: hook`; every other outcome is the receipt-only phase.

**Concurrent read during a `generate-agents` rewrite**: a hook can fire at the same moment a `generate-agents` run is rewriting the same state file, so the file **MUST NOT** be observable in a partially written form. The obligation is placed on the **writer**, not the reader: every write of a state file (`cpt-studio-algo-hook-based-session-routing-reconcile-marker` steps `inst-promote-persist-attempt` and `inst-persist-state-all-modes`) **MUST** be performed as a write to a temporary file in the **same directory** followed by an atomic rename over the target path, never as an in-place truncate-and-rewrite. A concurrent reader therefore always observes either the complete previous content or the complete new content, never a partial write, and the hook command needs no locking, retry, or partial-content handling of its own. Any temporary file left behind by an interrupted write **MUST NOT** use the reserved state-file name, so it can never be mistaken for the state file.

**Unreadable or unrecognised state at execution time**: if the read yields a missing file, an unparseable file, a `schema_version` this Studio version does not recognise, or a `routing_mode` outside the four serialized values, the hook command **MUST** treat the state as **absent** — exactly the rule `cpt-studio-dod-hook-based-session-routing-state-file` already applies to inspection — and absent is **not** `hook`, so the command stamps the receipt and emits **nothing**. Failing closed this way is required rather than merely prudent: emitting without a confirmed `hook` mode is precisely the double-delivery the receipt-only window exists to prevent, and it would defeat the promotion-safety ordering in `cpt-studio-algo-hook-based-session-routing-reconcile-marker` (`inst-promote-persist-first`), which relies on "state file does not say `hook`" meaning "the hook does not emit". A read failure **MUST NOT** fail the session or block the harness's startup.

**One delivery per session-start firing, not per session — decision**: once a harness is in `HookInstalled`, the payload is emitted on **every** session-start firing the harness makes, including each `resume`, `clear`, `compact`, and (for Claude) `fork` within what a user would call one continuing session. Repeated delivery inside one continuing session is therefore **intentional and accepted**, not a defect, and the system **MUST NOT** implement session-level deduplication. The reasoning: (1) it is the direct consequence of the unconditional-delivery decision above — the hook has no relevance check, and a "has this session already been served?" check is exactly such a check, reintroduced under another name; (2) it matches the channel this feature replaces, since a harness re-reading `AGENTS.md`/`CLAUDE.md` during a long session re-encounters the same text more than once today, so hook delivery is not more repetitive than the behavior it supersedes; (3) re-delivery after a `compact` is positively useful — compaction is exactly the event most likely to have dropped the routing precondition from context, so re-asserting a small, static instruction is the correct response, not waste. The `session_id` field both Claude Code and Codex pass in the hook payload is consequently **not** used for dedup and Studio **MUST NOT** persist a last-delivered-session marker; the execution receipt remains a one-shot "this entry has run at least once" signal for the fallback gate (`cpt-studio-dod-hook-based-session-routing-fallback`) and is explicitly **not** a per-session delivery ledger. The only per-session-once guarantee this feature makes is the narrow one already stated above: the file-fallback and hook channels never both deliver at the same moment.

The system **MUST** verify payload fidelity — recovering the payload through the reverse of the transport encoding and comparing it byte-for-byte against the intended text — rather than accepting syntactic validity of the config as proof the payload survived.

**Implements**:
- `cpt-studio-algo-hook-based-session-routing-compile-harness`
- `cpt-studio-algo-hook-based-session-routing-verify-hook`

### Per-Harness Install State File

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-state-file`

The system **MUST** persist routing state in **one state file per harness** — not a single shared file keyed by harness — so each harness's write is isolated and no cross-harness merge or atomic-upsert contract is needed for partial-failure safety. Each file **MUST** live in that harness's own configuration directory under the reserved name `.cf-studio-routing-state.json`, mirroring how `cpt-studio-feature-agent-integration` names `.opencode/.cf-studio-installed` and `.codex/.cf-installed`: `.claude/.cf-studio-routing-state.json`, `.codex/.cf-studio-routing-state.json`, `.cursor/.cf-studio-routing-state.json`, and `.github/.cf-studio-routing-state.json`. These files **MUST** be covered by the managed `.gitignore` block that `generate-agents` already refreshes.

The state file **MUST** be separate from `init.py`'s `MARKER_START`/`MARKER_END` `AGENTS.md`/`CLAUDE.md` scan, since hook installs live in harness-specific config rather than in those files.

The system **MUST** write the state file for **every** resolved mode — `off`, `file`, `hook`, and `errored` alike — never only for the hook case, so inspection never has to infer a harness's mode from an absent file. `off` is explicitly included: disabling routing for a harness **MUST NOT** delete that harness's state file, it **MUST** rewrite it to record `routing_mode: off`. The state file is bookkeeping, not a delivery channel, so retaining it does not contradict the no-residual-delivery-state guarantee in `cpt-studio-dod-hook-based-session-routing-disablement`.

The system **MUST** write the final state for every harness **affected** by a run, not only the harnesses the run explicitly selected. When an `--agent`-scoped run's shared-marker outcome changes an unselected in-scope harness's state — most notably a failed shared-marker write, which marks every harness in the dependency set `errored` — that harness's own state file **MUST** be written too, so `cfs agents` reports the fresh error rather than the unselected harness's stale mode.

The state file **MUST** carry a `schema_version` field. A state file that is unparseable, or whose `schema_version` this Studio version does not recognise, **MUST** be treated exactly as an absent file: the state is re-derived from installed resources and the file is rewritten from that derivation on the next `generate-agents` run, rather than failing the run or being partially trusted. The **same** absent-treatment rule **MUST** apply to the hook command's own execution-time read of this file, where "absent" resolves to the receipt-only, emit-nothing phase (`cpt-studio-dod-hook-based-session-routing-payload-transport`); the two readers never disagree about what an unrecognised file means.

**This file has a second reader**: besides `cfs generate-agents` and `cfs agents`, the harness's own hook command reads this file on **every** session-start firing to decide whether to emit the payload or only stamp the receipt (`cpt-studio-dod-hook-based-session-routing-payload-transport`). Every write of a state file **MUST** therefore be atomic from that reader's point of view: written to a temporary file in the **same** directory and then renamed over the target path in one step, never truncated and rewritten in place. A hook firing concurrently with a `generate-agents` rewrite then always observes either the complete old content or the complete new content, and never a partial write; no locking or retry is required on the reader side. The temporary file **MUST NOT** be named `.cf-studio-routing-state.json`, so an interrupted write can never leave something that reads as a valid-looking state file.

The persisted state **MUST** be treated as a cross-check against installed resources, never as the sole source of truth; the derivation and disagreement rules are `cpt-studio-algo-hook-based-session-routing-read-state`.

**Persistence-write failure**: if the final per-harness state-file write itself fails (permission denied, read-only tree, or any other filesystem error), the system **MUST NOT** attempt to persist an `errored` state into the file that just proved unwritable — there is no on-disk state to persist that failure into. Instead the system **MUST** report the failure directly in that run's outcome record — a `level: error` entry in the `warnings` array, per `DESIGN.md`'s `HarnessRoutingOutcome` field schema — and **MUST** feed the command's existing `PARTIAL` result contract, without changing the harness's already-resolved `routing_mode`: the channel-establishment outcome and the state-file persistence outcome are reported independently, since the channel itself may have been established successfully even though bookkeeping the fact of it failed. Because `cpt-studio-algo-hook-based-session-routing-read-state` always re-derives from installed resources rather than trusting the file, an unwritten state file does not cause a wrong report on the next `cfs agents` read; it only means that read falls back to derivation for this harness until a later run's write succeeds.

**Implements**:
- `cpt-studio-algo-hook-based-session-routing-reconcile-marker`
- `cpt-studio-algo-hook-based-session-routing-read-state`

**Touches**:
- Entities: `HarnessRoutingState`

### File-Injection Fallback Retained

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-fallback`

The system **MUST** keep file injection (`_compute_managed_block`/`_inject_managed_block` and related marker-rewrite helpers in `skills/studio/scripts/studio/commands/init.py`) as the fallback for a harness, and **MUST** only stop depending on it for that harness once the harness's hook entry is verified **and** its execution receipt confirms that entry has run at least once. Syntactic validity of the hook config alone **MUST NOT** authorise dropping the fallback, because it does not prove the harness registered or will execute the entry. This mirrors the rollback-path precedent in `skills/studio/scripts/studio/commands/migrate_from_cypilot.py`.

The system **MUST** treat the injected marker as a **shared, project-wide** resource — one managed block in root `AGENTS.md` and one in root `CLAUDE.md`, written by `_inject_root_agents()`/`_inject_root_claude()` and consumed by multiple harnesses by convention — and **MUST NOT** model it as harness-owned. The two files **MUST** be treated as one logical resource, always written together and always cleared together; when they diverge, the reconciliation pass **MUST** restore both to the computed target rather than preserving the divergence.

The system **MUST** decide marker removal exactly once per run, from the complete target-mode set for all in-scope harnesses, so the result does not depend on the order harnesses were processed in. When a harness's dependency on the marker cannot be determined — it was not selected by this run and its state is missing, unparseable, or inconsistent with its installed resources — the system **MUST** fail closed and treat that harness as still depending on the marker.

**The dependency set is not limited to the four in-scope harnesses**: Windsurf is out of scope for hook install but reads the **same** two shared files and has no hook channel it could ever be promoted to, so a dependency set computed from the four in-scope harnesses alone would remove the marker as soon as all four reached `hook` or `off`, silently breaking the unchanged, unconditional file injection Section 1.4 promises Windsurf keeps. The system **MUST** therefore add Windsurf to the dependency set as a **permanent** dependent whenever Windsurf is configured for the current project, so the shared marker is **never** removed by this feature regardless of the four in-scope harnesses' states. Presence **MUST** be determined by the project's existing per-agent install detection rather than a new mechanism — `_is_agent_installed("windsurf", project_root)` (`skills/studio/scripts/studio/commands/agents.py`), which checks `_AGENT_MARKERS["windsurf"]` (`.windsurf/workflows/cf.md`, `.windsurf/workflows/studio.md`) and then the legacy `_legacy_windsurf_install_detected()` fallback. When that signal is **false**, the existing four-harness-only dependency logic applies unchanged and a fully hook-promoted or fully disabled project does remove the marker. Windsurf's participation is strictly as a marker dependent: the system **MUST NOT** create, read, or write a routing state file for Windsurf, **MUST NOT** emit a `HarnessRoutingOutcome` record for it, and **MUST NOT** bring it under the disablement switch.

**Implements**:
- `cpt-studio-algo-hook-based-session-routing-compile-harness`
- `cpt-studio-algo-hook-based-session-routing-reconcile-marker`
- `cpt-studio-algo-hook-based-session-routing-verify-hook`

### Write-Failure Error Outcome

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-write-failure`

The system **MUST** treat a failure to write the shared `AGENTS.md`/`CLAUDE.md` fallback — permission denied, read-only working tree, exhausted disk, or any other filesystem error — as an explicit `errored` outcome for every harness that depended on that write, and **MUST NOT** report such a harness as `off` or as `file`.

The same treatment **MUST** apply to the mirror-image operation: when the dependency set is empty and the shared managed block is therefore **removed**, a failure of that removal **MUST** mark every harness this run resolved to `off` as `errored` rather than finalizing it as `off`. A disablement that did not actually take effect on disk **MUST NOT** be reported as a clean success; the underlying OS error is surfaced exactly as for the write path.

**When the rollback attempt itself also fails**: both `inst-mark-remove-error` and `inst-mark-write-error` roll the shared `AGENTS.md`/`CLAUDE.md` pair back to its pre-run content "where possible" — that rollback is a best-effort write, not a guaranteed one, and it can itself fail with its own filesystem error. This is a known, accepted terminal-failure case, not a silently unhandled one: if the rollback attempt fails, the harness(es) affected are still reported `errored`, carrying the underlying error (the rollback's error if the rollback is what failed, otherwise the original write/removal error), exactly as for any other write/removal failure. The shared pair's on-disk content at that point is whatever the failed rollback left it as; no further rollback is attempted. This never changes the reported outcome — it is always `errored`, never misreported as `off` or `file` — and it self-heals on a later run's retry via the same idempotent marker-write path used elsewhere in this document.

The same `errored`-not-`off` treatment **MUST** also apply to a harness's own disablement-time removals, which are pass 1's failures to report rather than pass 2's: if removing that harness's Studio-owned hook entry (`cpt-studio-dod-hook-based-session-routing-hook-ownership`) or its execution receipt fails with a filesystem error, the system **MUST** report that harness as `errored` — not `off` — since a hook entry or receipt that could not be removed means the harness's disablement did not actually take effect on disk. These two removals (hook entry, then execution receipt) are independent, non-compensating steps: if hook-entry removal succeeds but the subsequent execution-receipt removal then fails, the harness is reported `errored` with the partial physical state left as-is — hook entry gone, receipt still present — rather than an attempt to restore the already-removed hook entry. This is always honestly reported as `errored`, never misreported as `off` or `hook`, and — like every other write/removal failure in this DoD — self-heals on the next run's idempotent retry, since a re-run's disablement branch simply finds the hook entry already gone and retries the receipt removal.

The `errored` outcome **MUST** carry the underlying OS error text, **MUST** be rendered as an error-level line in the summary, and **MUST** feed the command's existing `PARTIAL` result contract so the run is not reported as a clean success.

Hook-side failures are deliberately treated differently: an unwritable or unverifiable hook entry degrades to the fallback with a warning and is not an error, because delivery is preserved. `errored` is reserved for the case where no channel is known to be delivering.

A failure to persist an otherwise cleanly resolved mode to the harness's own state file is a **different** failure and is **not** governed by this DoD's `errored`-outcome rule: `routing_mode` is not downgraded for a persistence-only failure, since the channel itself was established. That case is a `level: error` `warnings` entry reported independently — see `cpt-studio-dod-hook-based-session-routing-state-file`.

**Implements**:
- `cpt-studio-algo-hook-based-session-routing-compile-harness`
- `cpt-studio-algo-hook-based-session-routing-reconcile-marker`
- `cpt-studio-algo-hook-based-session-routing-render-summary`

### Single Disablement Switch

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-disablement`

The system **MUST** provide exactly one disablement switch per harness with exactly two states — "routing on" (hook when usable, else file) and "routing off" (neither hook nor file for that harness) — and **MUST** flip that harness's hook install and its dependence on the shared file marker atomically, so no silent partial-downgrade state can occur.

**Scope of the guarantee**: this single-switch, no-residual-**delivery**-state guarantee covers the `AGENTS.md`/`CLAUDE.md` and hook-entry delivery paths only. The same three named exceptions stated in Section 1.2 apply, and nothing elsewhere in this document may claim otherwise:

- **Generated shim-file copies (out of scope)**: `_follow_protocol_lines()` (`skills/studio/scripts/studio/commands/agents.py`) embeds `ROOT_AGENTS_PIPELINE_INSTRUCTION` into every generated per-harness workflow/skill shim file over a second, independent channel. Those copies **MUST** be documented as persisting regardless of switch state, and the switch **MUST NOT** claim to remove them. Gating that channel belongs to a future iteration.
- **Shared marker retention**: because the file marker is project-wide rather than harness-owned (`cpt-studio-dod-hook-based-session-routing-fallback`), "routing off" for one harness **MUST NOT** remove the marker while any other dependent still needs it — another in-scope harness currently in `FileFallback` (a hook awaiting its first observed execution, a harness whose hook stopped verifying, or an installed client whose hook API is unavailable), or a configured Windsurf, whose dependency is permanent. With every in-scope harness now hook-capable by default the in-scope case narrows, but it remains reachable and is not claimed away, and the Windsurf case never clears at all.
- **The harness's own state file**: the state file **MUST** be retained on disablement and rewritten to record `routing_mode: off` (`cpt-studio-dod-hook-based-session-routing-state-file`). It carries no payload and delivers nothing; keeping it is what lets a later inspection distinguish "deliberately off" from "never touched" without guessing.

Within those exceptions, turning routing off for a harness **MUST** leave no hook entry and no execution receipt for that harness — no residual delivery state of any kind — while the harness's state file persists by design to record the `off` state.

**Exactly what "Off" guarantees — and the one thing it explicitly does not**: for a harness whose switch is "routing off", the system **MUST** guarantee (i) no Studio-owned hook entry exists for that harness, (ii) no execution receipt exists for it, so nothing of Studio's runs at its session start, and (iii) it is not counted as a dependent when the shared marker's removal is decided. The system **MUST NOT** claim, here or anywhere else in this document, that "Off" prevents that harness's **own process** from reading the shared root `AGENTS.md`/`CLAUDE.md` files. Those two files are one physical, project-wide pair read by harnesses on their own convention, so while any other dependent still needs them — another in-scope harness in `FileFallback`, or a configured Windsurf — the managed block stays on disk and an "off" harness that reads those files at session start still reads it. This is an **inherent property of reusing the pre-existing shared file-injection mechanism**, which this feature deliberately reuses rather than replacing with per-harness fallback files (Section 1.2); it is an accepted design constraint, **not** a defect and **not** an unfinished item. Per-harness isolation of the fallback channel would require replacing that mechanism project-wide and is out of scope. The guarantee "Off" makes is about what Studio installs and maintains, never about the contents of two files it shares with everyone.

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

The system **MUST** print a per-harness install-outcome summary at the end of `cfs generate-agents`, rendered through the CLI's shared result helper: a short human table by default and the same data as structured output under the global `--json` flag, per the output convention in [specs/cli.md](../specs/cli.md). The system **MUST** make the same data queryable later via `cfs agents`, derived live from installed resources rather than replayed from a cache.

The summary **MUST** be added to both commands' structured output as a new top-level `routing` key holding one record per harness, and **MUST NOT** alter or replace the fields those commands already emit (`status`, `agents`, `project_root`, `studio_root`, `results`).

**Implements**:
- `cpt-studio-flow-hook-based-session-routing-install`
- `cpt-studio-flow-hook-based-session-routing-inspect`
- `cpt-studio-algo-hook-based-session-routing-render-summary`

### Fallback Warning Visibility

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-fallback-warning`

The system **MUST** flag any harness that falls back to file injection with a warning-level, visually distinct line in the summary, reusing the CLI's existing `warnings` array shape (as already used in, e.g., `cfs info --json` output).

**Implements**:
- `cpt-studio-algo-hook-based-session-routing-reconcile-marker`
- `cpt-studio-algo-hook-based-session-routing-render-summary`

### Relative Hook-Path Disclosure

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-relative-paths`

The system **MUST** express every path it reports — the harness's hook config path, and the pair of shared file-marker paths — relative to the project root and never absolute, so `--json` output stays stable across machines and CI.

**Implements**:
- `cpt-studio-algo-hook-based-session-routing-render-summary`

### Fixed-Enum Fallback Reasons

- [ ] `p1` - **ID**: `cpt-studio-dod-hook-based-session-routing-reason-enum`

The system **MUST** attach a one-clause fallback reason to each fallback warning, drawn from a fixed, stable enum of known limitation reasons rather than free text. The enum **MUST** at minimum distinguish a hook API the installed client does not expose (an outdated client, or one whose hooks have been explicitly disabled), a hook entry that failed verification, and a hook entry awaiting its first observed execution, since these three produce the same `file` mode for very different reasons and call for different maintainer action.

**Enum values** (resolving Section 7, item (c) for the reasons that are structurally known ahead of implementation — see `DESIGN.md`'s `HarnessRoutingOutcome` field schema for the authoritative table): `hook-unavailable` (compile-harness step `inst-return-file-no-hook`), `verification-failed` (`inst-return-file-verify-failed`), `pending-first-run` (`inst-return-file-pending-receipt`). Whether `hook-unavailable` is further split into separate values for an outdated client versus explicitly-disabled hooks remains open — that split depends on Section 7 item (d)'s still-open detection decision, not on this DoD. `level: error` entries are never drawn from this enum; their `reason` is always free-text carrying the underlying OS error, since write/removal failures cannot be enumerated ahead of time.

**Implements**:
- `cpt-studio-algo-hook-based-session-routing-compile-harness`
- `cpt-studio-algo-hook-based-session-routing-render-summary`

## 6. Acceptance Criteria

- [ ] All 4 in-scope harnesses (claude, codex, cursor, copilot) go through the compile process and end in exactly one of the four states (Off, FileFallback, HookInstalled, Errored) with no partial-downgrade state observable. Windsurf is not processed by this path and keeps its existing unconditional file injection.
- [ ] Each of the 4 in-scope harnesses can reach HookInstalled: with routing on, a usable hook, and a confirming execution receipt, claude, codex, cursor, and copilot each install via their own session-start hook entry at the event and config path named in Section 1.4.
- [ ] codex takes the ordinary hook path with no opt-in handling: a default installation reaches HookInstalled without Studio reading or writing `[features].hooks` or the deprecated `codex_hooks` alias, and codex's entry is written to `.codex/hooks.json` only — `config.toml` is left untouched.
- [ ] A harness whose installed client does not expose a usable session-start hook ends in FileFallback with the hook-unavailable reason rather than as an error, and moves to HookInstalled by the ordinary transitions once the hook becomes usable and its first execution is observed.
- [ ] A harness whose hook entry is written but not yet observed to have run stays in FileFallback with the pending-first-run reason, and is promoted to HookInstalled on a later run once its execution receipt confirms the entry ran.
- [ ] During that pending-first-run window the routing text is delivered exactly once per session: the newly written hook stamps its receipt but emits nothing while the file fallback is still delivering, and only starts emitting after promotion to HookInstalled, when fallback delivery stops.
- [ ] Once a harness is in HookInstalled, its hook emits the payload on every session-start execution with no per-session relevance check, matching the unconditional delivery of today's file injection.
- [ ] Multiple session-start firings inside one continuing session — successive `compact` events, a `resume`, a `clear`, or (Claude) a `fork` — each deliver the payload, and no session-scoped deduplication suppresses any of them; no last-delivered-session-id value is written or read anywhere, and the `session_id` field the hook receives is unused. This is the documented, intended behavior, not a defect.
- [ ] Claude's Studio-owned hook entry fires for every `SessionStart` source — `startup`, `resume`, `clear`, `compact`, and `fork` — so a harness promoted to HookInstalled still receives the routing payload when its session is resumed, cleared, compacted, or forked, exactly as codex does with its unrestricted matcher.
- [ ] The hook command takes its emit-vs-stamp-only decision from `<harness-config-dir>/.cf-studio-routing-state.json`'s `routing_mode` field and nothing else: it emits only when that field reads exactly `hook`, and stamps the receipt without emitting when the file is missing, unparseable, carries an unrecognised `schema_version`, or carries an unrecognised `routing_mode` — and in none of those cases does it fail the session.
- [ ] A hook firing concurrently with a `generate-agents` rewrite of the same state file never observes partial content: the state file is written to a temporary file in the same directory and atomically renamed into place, so the concurrent read yields either the complete previous content or the complete new content.
- [ ] Hook capability is read from the dedicated capability table; changing `_TOOL_PROVIDER_SUPPORT`'s provider sets has no effect on any harness's routing_mode.
- [ ] Installing into a hook config that already contains a user-authored session-start hook leaves that user entry byte-for-byte unchanged, and running `generate-agents` repeatedly produces exactly one Studio-owned entry rather than accumulating duplicates.
- [ ] A hook entry that is written and then fails verification is removed from the config before the fallback is taken, leaving no orphaned unverified entry on disk.
- [ ] Verification rejects a hook entry whose payload did not survive transport intact (altered quoting, truncated newlines), not merely one whose config fails to parse.
- [ ] A harness with a verified, receipt-confirmed hook stops depending on the shared file marker and appears in the summary with routing_mode = hook and a project-root-relative hook path.
- [ ] Disabling routing for a harness removes that harness's hook entry and execution receipt, rewrites its state file to record `off` rather than deleting it, and removes the shared root `AGENTS.md`/`CLAUDE.md` marker **only when** no other in-scope harness still depends on it; when another in-scope harness is still in FileFallback, the shared marker is verifiably left in place and the disabled harness is still reported as `off`.
- [ ] The shared-marker outcome is identical regardless of the order harnesses are processed in: for any given set of target modes, permuting the iteration order produces the same marker state and the same per-harness outcomes.
- [ ] A `--agent <name>`-scoped run compiles routing only for the named harness, and still leaves the shared marker in place when an unselected in-scope harness depends on it.
- [ ] A `--agent <name>`-scoped run may write an unselected in-scope harness's **routing state file** when the shared-marker outcome changed that harness's state, and this exception is documented in `generate-agents`'s contract in `specs/cli.md`; no unselected harness's hook entry, execution receipt, or generated files are touched by a scoped run.
- [ ] `cfs generate-agents --dry-run` reports the same `routing` summary a real run would produce while writing nothing: no hook entry is added or removed, no execution receipt is created or deleted, no per-harness state file is written (including the promotion-first persist), and the shared `AGENTS.md`/`CLAUDE.md` marker is byte-for-byte unchanged; the skipped persist is not reported as a persistence failure.
- [ ] When an unselected harness's state cannot be determined, the run keeps the shared marker rather than removing it.
- [ ] Root `AGENTS.md` and root `CLAUDE.md` are always left in the same marker state as each other; a run that starts with the marker in only one of them ends with both matching the computed target.
- [ ] In a project where Windsurf is **not** configured, disabling routing for every in-scope harness removes the shared root `AGENTS.md`/`CLAUDE.md` marker, all Studio-owned hook entries, and all receipts, leaving no residual delivery state — while each harness's state file remains, recording `off`, and the routing text embedded in generated shim files by `_follow_protocol_lines()` is expected to remain (documented out-of-scope exceptions, not defects).
- [ ] **Windsurf present**: in a project where `_is_agent_installed("windsurf", project_root)` is true, the shared root `AGENTS.md`/`CLAUDE.md` marker is **never** removed by this feature — not when all four in-scope harnesses reach HookInstalled, not when all four are disabled to `off`, and not on any combination in between — so Windsurf's unconditional file injection keeps working unchanged; the four harnesses still report their own correct modes (`hook`/`off`), and no state file or `routing` record is created for Windsurf.
- [ ] **Windsurf absent**: in a project where that signal is false, the dependency set is exactly the four in-scope harnesses and marker removal behaves exactly as before — all four at HookInstalled, or all four `off`, removes the marker.
- [ ] "Routing off" for a harness is verifiable as (i) no Studio-owned hook entry, (ii) no execution receipt, and (iii) not counted as a marker dependent — and is **not** claimed or tested as "the harness cannot read the shared files": when another dependent (an in-scope harness in FileFallback, or a configured Windsurf) keeps the marker on disk, the off harness still reports `off` and the shared files are verifiably left intact, which is the documented, accepted shared-mechanism constraint rather than a failure.
- [ ] A failed shared-marker write reports every affected harness as `errored` with the underlying OS error, contributes to the `PARTIAL` result contract, and is never reported as `off` or `file`.
- [ ] A failed shared-marker **removal** — the empty-dependency-set path — reports every harness this run resolved to `off` as `errored` with the underlying OS error instead of finalizing it as a clean `off`.
- [ ] On an `--agent`-scoped run whose shared-marker write fails, an unselected but affected dependent gets its own state file rewritten to `errored`, so a later `cfs agents` reports the fresh error rather than that harness's stale mode.
- [ ] Every resolved mode is persisted: after a run, each affected harness has a state file recording `off`, `file`, `hook`, or `errored`, and `cfs agents` on a fresh untouched project reports `off` rather than `unknown`.
- [ ] A harness whose state file records `errored` is re-tested on the next `cfs agents` read: if its installed resources now resolve cleanly it is reported with the freshly derived `off`/`file`/`hook` mode, and if they still do not it is reported as `errored` with the reason recorded in the state file.
- [ ] If removing a harness's own Studio-owned hook entry or execution receipt fails during disablement, that harness is reported as `errored` — carrying the underlying OS error — rather than `off`, and a disablement that did not actually take effect on disk is never finalized as a clean success.
- [ ] If the final per-harness state-file write fails after a mode was otherwise cleanly resolved, the run reports that failure directly as a `level: error` `warnings` entry (contributing to `PARTIAL`) without downgrading the harness's `routing_mode`, and the next `cfs agents` read still derives the harness's state correctly from installed resources despite the unwritten file — except the FileFallback→HookInstalled promotion case below, where `routing_mode` itself is affected.
- [ ] A harness being **newly promoted** to HookInstalled this run — target `hook` while its state file does not already durably record `hook`, i.e. persisted `file`, `off`, or `errored`, or a state file that is absent, unparseable, or of unrecognised `schema_version` — has its `routing_mode: hook` persisted **before** the shared marker's dependency set is computed; if that specific persist fails, the harness is reported as `file` (not `hook`) for this run, the shared marker is retained on its behalf (it is not removed out from under it even if it was the last dependent), and the promotion is retried automatically on a later run once the write can succeed — so a persistence failure at the moment of promotion never leaves the harness with neither the file marker nor a live hook delivering. Each of the four entry paths (from `file`, from `off`, from `errored`, and from a deleted or corrupt state file) exercises this ordering identically.
- [ ] A harness **already** recording `hook` on disk from a prior run whose state-file rewrite fails this run is not affected by that ordering: it keeps `routing_mode = hook`, its state file still reads `hook`, its hook therefore still emits at the next session start, and the failure surfaces only as a `level: error` `warnings` entry feeding `PARTIAL`.
- [ ] `cfs agents` derives state from installed resources: removing a Studio-owned hook entry or the shared marker outside Studio makes the affected harness report `unknown` with both the persisted and derived values named, rather than the stale persisted value.
- [ ] A state file that is corrupt or carries an unrecognised `schema_version` is treated as absent: state is re-derived from installed resources and the file is rewritten, without failing the run.
- [ ] A project that already has the pre-existing file-injected marker in either or both root files is read as starting in FileFallback (not Off) on its first post-upgrade `cfs generate-agents` run, is not re-injected or duplicated, has both files reconciled to match, and then transitions normally to HookInstalled for each harness whose hook is usable and confirmed.
- [ ] `cfs generate-agents --json` and the default human table expose the same underlying per-harness data (routing_mode, paths, warnings), carried under a new top-level `routing` key that leaves both commands' existing output fields unchanged.
- [ ] The hook payload text is sourced from `ROOT_AGENTS_PIPELINE_INSTRUCTION` and is not duplicated elsewhere in the hook-writing code path.

## 7. Open Implementation Questions

These side-topics are deliberately left open. They **MUST** be resolved before or during implementation, not silently decided by this FEATURE document:

- [ ] **(a) Execution-receipt lifetime**: The fallback gate depends on a per-harness execution receipt proving the current hook entry has run (`cpt-studio-dod-hook-based-session-routing-payload-transport`). Its exact location, format, and staleness policy need a decision — in particular whether a receipt older than some interval should demote a harness from HookInstalled back to FileFallback, and how the receipt binds to a specific entry revision so editing the entry invalidates it.
- [ ] **(b) Disablement switch surface**: Should the disablement switch (`cpt-studio-dod-hook-based-session-routing-disablement`) be a CLI flag, a config-file setting, or both? This affects how `cfs generate-agents` and `cfs agents` read and expose the switch value.
- [x] **(c) Fallback-reason enum values**: Resolved — the fixed enum referenced by `cpt-studio-dod-hook-based-session-routing-reason-enum` is `hook-unavailable`, `verification-failed`, `pending-first-run` (see that DoD and `DESIGN.md`'s `HarnessRoutingOutcome` field schema). Partially open: whether `hook-unavailable` is further subdivided depends on item (d) below.
- [ ] **(d) Detecting a client whose hooks are unavailable**: Codex hooks are enabled by default (`[features].hooks`, default true) and Studio does not manage that flag, so the common case needs no detection. How Studio should recognise the uncommon case — an outdated client, or a project that has explicitly disabled hooks — needs a decision: whether to probe the client version, read the flag read-only for a better fallback reason, or simply let the missing execution receipt produce the fallback with a generic reason.
- [ ] **(e) ADR-0016 amendment**: ADR-0016 states Cursor has no hook support, which the 2026-09-23 capability survey supersedes. Amending that ADR is a follow-up outside this feature's diff and needs to be scheduled; no design in this document depends on the stale claim.
- [ ] **(f) Per-harness payload transport**: `cpt-studio-dod-hook-based-session-routing-payload-transport` requires one defined transport per harness and defaults to a referenced payload file. Which harnesses can instead carry the payload inline losslessly, and the exact payload-file location per harness, need a decision.
- [ ] **(g) Exact native hook-entry schema per harness**: Section 1.4 pins down, for each harness, the config location Studio writes, the event/matcher binding, the command, and where the Studio ownership identifier lives. It deliberately does **not** pin down the exact field names, nesting, and version keys of each harness's native format, because those are vendor schemas that move and must be confirmed against the shipping client at implementation time. Two parts need an explicit decision rather than an assumption: how ownership is expressed for formats with **no per-entry name field** (the Claude Code case, where the current answer is the reserved Studio-owned hook-script path the command invokes, which must be reconciled with `cpt-studio-dod-hook-based-session-routing-hook-ownership`'s "never match by command text" rule), and whether Codex's `.codex/hooks.json` accepts a per-entry identifier at all. The exact native spelling of an **unrestricted / wildcard** session-start binding is part of the same gap for both Codex and Claude — the decision that Studio registers for every `SessionStart` source is made in Section 1.4 and is not open; only whether that is expressed as an omitted matcher key or an explicit `"*"` value in each vendor's current schema is. This is a known documentation gap, not a silently missing detail.

## 8. Applicability

This feature is a CLI-command change: `cfs generate-agents` and `cfs agents` writing and reading local files in the project working tree. The following checklist domains are therefore not applicable, each for the stated reason:

- **SEC**: Not applicable because there is no authentication or authorization surface — this is a local filesystem CLI operating with the invoking user's existing permissions, and the hook payload is Studio's own static routing text, not user-supplied input.
- **COMPL**: Not applicable because no regulated data is read, stored, or transmitted.
- **UX / accessibility**: Not applicable because there is no UI — output is CLI/terminal text plus the existing global `--json` payload.
- **DATA privacy**: Not applicable because no PII is touched; the only data written is harness config entries, a marker block, and a small per-harness state file.
- **PERF**: Not applicable because there are no response-time or throughput targets — the work is bounded local file I/O over at most 4 harnesses during a one-shot command, not a running service.

## Additional Context (optional)

### Per-Harness Install / Verify / Fallback / Disablement Flow

The diagram below shows the two passes of one `cfs generate-agents` run. Pass 1 runs per harness and touches only that harness's own resources; pass 2 runs once, after every selected harness has resolved a target mode, and is the only step that touches the two shared files. Splitting them this way is what makes the run's result independent of harness iteration order.

```
PASS 1 — per harness H, harness-owned resources only
─────────────────────────────────────────────────────
              ┌──────────────────────────────┐
              │ Disablement switch for H?     │
              └──────┬───────────────┬────────┘
            routing  │               │ routing on
               off   v               v
     ┌──────────────────────┐   ┌────────────────────────────────┐
     │ Remove H's owned hook │   │ Hook usable for H?              │
     │ entry + receipt       │   │ (capability table; all four     │
     │ (state file KEPT,     │   │  harnesses hook-capable by      │
     │  rewritten to "off")  │   │  default)                       │
     │ → target: off         │   └──────┬──────────────────┬───────┘
     └──────────────────────┘      yes  │                  │ no
                                        v                  │
                          ┌───────────────────────────┐    │
                          │ Add or replace H's        │    │
                          │ Studio-owned entry by     │    │
                          │ stable id; embed payload  │    │
                          │ per transport rule        │    │
                          └───────────┬───────────────┘    │
                                      v                    │
                          ┌───────────────────────────┐    │
                          │ Verify: owned entry found,│    │
                          │ config parses, payload    │    │
                          │ round-trips intact?       │    │
                          └──────┬─────────────┬──────┘    │
                            yes  │             │ no        │
                                 v             v           │
                    ┌────────────────────┐  ┌───────────────────────┐
                    │ Receipt shows this │  │ Remove the unverified │
                    │ entry has run?     │  │ entry; → target: file │
                    └───┬───────────┬────┘  └───────────┬───────────┘
                    yes │           │ no                │
                        v           └───────────────────┴──────┐
              ┌──────────────────┐                             v
              │ → target: hook   │                   ┌──────────────────┐
              └──────────────────┘                   │ → target: file   │
                                                     └──────────────────┘

PASS 2 — once per run, shared resources
────────────────────────────────────────
   Collect target modes for all in-scope harnesses
   (untouched harnesses: last known mode, or "depends" if undeterminable)
                          │
                          v
        ┌─────────────────────────────────────────┐
        │ For each harness NEWLY promoted to hook   │
        │ (state file does not already say "hook":  │
        │  file / off / errored / absent / corrupt):│
        │ persist routing_mode=hook NOW, before     │
        │ the dependency set is built (write fails  │
        │ → revise target back to file, harness     │
        │ stays a marker dependent, retry next run) │
        └────────────────┬──────────────────────────┘
                          │
                          v
        ┌─────────────────────────────────────┐
        │ Any in-scope harness targeting file, │
        │ (using modes as revised above)       │
        │ OR is Windsurf configured for this   │
        │ project? (permanent dependent —      │
        │ no hook path, reads the same files)  │
        └────────┬──────────────────┬──────────┘
              no │                  │ yes
                 v                  v
   ┌───────────────────────────────┐  ┌────────────────────────────────┐
   │ Clear managed block from BOTH  │  │ Ensure identical managed block │
   │ AGENTS.md and CLAUDE.md        │  │ in BOTH AGENTS.md + CLAUDE.md  │
   │ (removal fails → every "off"   │  │ (write fails → errored, with   │
   │  harness errored, OS error     │  │  the OS error attached)         │
   │  attached)                     │  └────────────────────────────────┘
   └───────────────────────────────┘
                          │
                          v
        ┌────────────────────────────────────────┐
        │ Persist final state for every AFFECTED  │
        │ harness (touched + unselected ones this │
        │ run's marker outcome changed) for EVERY │
        │ mode (off/file/hook/errored), then      │
        │ render the `routing` summary            │
        │ (table + --json, same data)             │
        └────────────────────────────────────────┘
```

This flow is not applicable to harnesses outside the 4 in scope (claude, codex, cursor, copilot) — notably Windsurf, which stays on unconditional file injection (Section 1.4); adding a new harness means adding a row to the capability table and to the in-scope set, not changing this flow. Windsurf appears in pass 2 in exactly one capacity and no other: as a permanent dependent of the shared marker whenever it is configured for the project, which keeps the marker on disk for it. It has no pass-1 box, no state file, and no outcome record.

Under `cfs generate-agents --dry-run` every box above is **computed** and the resulting `routing` summary is rendered, but no box performs its write: no hook entry is added or removed, no receipt is created or deleted, no state file is persisted (including the "persist routing_mode=hook NOW" box), and neither shared file is modified.

In the diagram, every pass-2 box acts on the two shared, project-wide files as one resource: the ensure step is idempotent across harnesses and writes both files, and the clear step empties both, only when no in-scope harness still depends on the marker.

**Failure branches omitted from the boxes above, for diagram legibility**: the "Remove H's owned hook entry + receipt" box also has a failure edge — if either removal fails (filesystem error), the outcome is `target: errored` for H, not `target: off` (`cpt-studio-dod-hook-based-session-routing-write-failure`). The "Persist final state" box also has a failure edge, per harness — if that harness's state-file write itself fails, its already-resolved mode is reported unchanged plus a `level: error` `warnings` entry, rather than an attempt to write `errored` into the file that just failed to write (`cpt-studio-dod-hook-based-session-routing-state-file`). The one case where a persist failure **does** change the reported mode is the "persist routing_mode=hook NOW" box above — which covers every harness whose state file does not already say `hook`, not only `file`→`hook` promotions: a failure there revises the harness's target back to `file` rather than leaving it reported as `hook`, precisely because that specific persist is what both the dependency-set decision below it and the hook command's own execution-time read depend on (`cpt-studio-algo-hook-based-session-routing-reconcile-marker` step `inst-promote-persist-first`). All three are spelled out in full in the corresponding algorithm steps and DoDs; they are omitted (or, for the promotion box, only lightly summarized) here to keep the flow diagram at the granularity of its two passes.
