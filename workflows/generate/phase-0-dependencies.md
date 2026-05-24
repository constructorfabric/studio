---
name: generate-phase-0-dependencies
description: "Invoke when the generate workflow enters dependency resolution after protocol.md — ensures kit deps, capability probe, CONTRIBUTING discovery, and raw-input overflow rule."
purpose: Generate Phase 0 — ensure dependencies, capability probe, CONTRIBUTING discovery, raw-input overflow rule
loaded_by: workflows/generate.md
version: 1.0
---

<!-- toc -->

- [Phase 0: Ensure Dependencies](#phase-0-ensure-dependencies)

<!-- /toc -->

## Phase 0: Ensure Dependencies

After `skills/cypilot/protocol.md`, you have `KITS_PATH`, the phase-appropriate dependency set, and `REQUIREMENTS`.

Variable checkpoint: `{cfc_cmd}`, `{cf-constructor-path}`, and `{project_root}` are resolved by `skills/cypilot/protocol.md`. On context loss or new-chat resume, re-run `{cfc_cmd} --json info` to restore these values before any path-dependent step.

Sub-agent approval/probe: load and apply `workflows/shared/inline-fallback-probe.md` now. This evaluates SKILL.md § Session Sub-Agent Approval Gate and assigns `INLINE_FALLBACK`; it MUST complete before Phase 1 and before any later sub-agent dispatch (Phase 0.7 brainstorm, Phase 1 collector, Phase 1.5 author planner, Phase 4 author, Phase 5 validator/reviewers/author). (External-entry re-probe is documented in `workflows/shared/inline-fallback-probe.md` and `workflows/generate/phase-5/phase-5.3-findings.md` § External entry; this file is only reached on fresh-generate runs.)

| Condition | Action |
|-----------|--------|
| `rules.md` loaded | Phase-appropriate dependencies were already resolved from rules Dependencies; proceed silently. |
| `rules.md` not loaded | Ask the user to provide/specify the generation-phase dependencies that are actually needed now; request `checklist` only when the current phase or rules explicitly require it. |
| Code mode additional | Ask the user to specify the design artifact if missing; open, load, and follow `{cf-constructor-path}/.core/requirements/code-checklist.md` up front only when the current rules explicitly require implementation-time checklist guidance, otherwise defer it to Phase 5 review. |

**MUST NOT proceed** to Phase 1 until all generation-phase dependencies required for the current target are available.

### CONTRIBUTING Guide Discovery (runs unconditionally — every generate run)

Search for a CONTRIBUTING guide in this order. Stop at the first match and store the result as `CONTRIBUTING_GUIDE`:

1. `{project_root}/CONTRIBUTING.md` or `{project_root}/CONTRIBUTING`
2. `{project_root}/.github/CONTRIBUTING.md`
3. `{project_root}/docs/CONTRIBUTING.md`
4. `{project_root}/CONTRIBUTING.rst` or `{project_root}/CONTRIBUTING.txt`

When a file is found:
- Store `CONTRIBUTING_GUIDE = { "path": "<absolute path>", "directives": "<key directives summary>" }`.
- Load the file subject to the ~200-line practical cap. If longer, read the first 200 lines, summarize commit-message format, branch-naming conventions, and PR-template requirements into `directives`, then drop the full body from context.
- When no file is found, set `CONTRIBUTING_GUIDE = null`.

Discovery runs unconditionally — independent of `GIT_COMMIT_MODE`. The guide informs non-commit concerns (style, branch naming, PR templates) as well as commit constraints when `GIT_COMMIT_MODE=commit`.

Raw-input overflow rule: open, load, and follow `{cf-constructor-path}/.core/requirements/raw-input-overflow.md`. If the direct user prompt plus all provided files exceeds `500` total lines, the agent MUST stop direct generation long enough to offer `/cf-constructor-plan` versus continuing here with reduced guarantees, exactly as specified in that file.

### Panel Mode Flags (session-scoped, defaults single-agent)

Two independent session-scoped flags control brainstorm orchestration strategy:

- **PANEL_MODE_TOPIC**: orchestration mode for exploratory rounds (`topic` kind). Defaults to `'single-agent'` — one `cf-constructor-brainstorm-panel` dispatch per round, with all panel experts deliberating inside that single agent. Switch to `'fan-out'` to use parallel per-expert dispatch via `cf-constructor-brainstorm-expert` (one sub-agent per panel member, runs in parallel on hosts with native fan-out). Single-agent mode is inherently sequential; INLINE_FALLBACK degradation becomes a no-op for it.
- **PANEL_MODE_CHALLENGE**: orchestration mode for challenge rounds (`challenge` kind). Defaults to `'single-agent'`; independently switchable to `'fan-out'` with same semantics.

To override defaults for a single run: `{cfc_cmd} --reconfigure generate` accepts an interactive environment-state override menu where you may set `state.run_config.PANEL_MODE_TOPIC` and `state.run_config.PANEL_MODE_CHALLENGE` before Phase 0.7 brainstorm begins. Flags persist for the lifetime of the session.
