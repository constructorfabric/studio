---
name: cf
aliases: [cf-studio]
description: "Invoke when running Constructor Studio planning, generation, analysis, validation, traceability, kit, workspace, and agent-integration workflows."
---

<!-- toc -->

  - [Context Budget & Fail-Safe](#context-budget--fail-safe)
  - [Phase-Skip Gate (loaded with the skill)](#phase-skip-gate-loaded-with-the-skill)
  - [Session GIT_COMMIT_MODE Gate](#session-gitcommitmode-gate)
  - [Session Sub-Agent Approval Gate](#session-sub-agent-approval-gate)
- [Completion Invariants](#completion-invariants)

<!-- /toc -->

# Constructor Studio Unified Tool

ALWAYS SET {cfs_mode} = `on` FIRST. MUST/ALWAYS are mandatory.

### Context Budget & Fail-Safe

Before opening the mandatory protocol, dispatch, and routing files, estimate the line count of each target file when tooling permits. Only minimal metadata and sizing reads are allowed before this gate; full content loads are not. Load only those files and the directly selected workflow sections for the current request. If the required files cannot fit in context, stop with a checkpoint that lists loaded files, deferred files, and the next exact file to open. If tooling does not permit a size estimate, treat each file as ~200 lines (the practical loadable-resource cap) and load files one at a time, checkpointing if the cumulative load approaches the conservative budget.

Open, load, and follow `protocol.md` for logging, CLI, Protocol Guard, invocation, language, write-confirmation rules.
Open, load, and follow `sub-agent-dispatch.md` before any `cf-*` sub-agent dispatch.
Open, load, and follow `routing.md` for commands and workflows.

### Phase-Skip Gate (loaded with the skill)

On skill load, MUST set `CF_PHASE_GATE=armed`. The gate has these states:

- `armed` (default) — all `Edit` / `Write` / `MultiEdit` / `NotebookEdit` calls are FORBIDDEN, regardless of path, size, or intent.
- `released_for_dispatch` — set by a workflow write-phase immediately before dispatching a write-capable sub-agent (`cf-generate-*-author-*`, `cf-generate-coder-*`, `cf-generate-prompt-engineer-*`, `cf-migrate-migrator`, `cf-phase-compiler`). Reset to `armed` immediately after the dispatch returns — whether with a manifest, an `AUTHOR_ESCALATION_REQUIRED` payload, an error, or no response at all. On any error path the reset is mandatory; the gate MUST NOT remain in this state across turns.
- `released_for_orchestrator_write` — set by a workflow phase that legitimately writes from the orchestrator (plan cache files under `.cache/generate-plans/` and `.cache/analyze-plans/`, `plan.toml`, brief files under `.plans/`, `phase-*.md` files under `.plans/`, workspace config files written by `workspace-init` / `workspace-add` CLI). The phase MUST name the path or path-prefix being released; writes outside that scope still fail PHASE_SKIP. Reset to `armed` immediately after the named writes complete or fail.
- `released_for_inline_write` — `released_for_inline_write` is reachable ONLY after the Session Sub-Agent Approval Gate has resolved `INLINE_FALLBACK` to a concrete `true`/`false`. Attempting to set this state while `INLINE_FALLBACK` is unset is itself a `PHASE_SKIP` failure; the orchestrator MUST run `workflows/shared/inline-fallback-probe.md` first. Set when `INLINE_FALLBACK=true` AND the orchestrator is executing an inlined author/coder/migrator contract inside a workflow write-phase, in lieu of dispatching a sub-agent. Reset to `armed` immediately after the inline write block completes or fails.
- `user_bypass` — set when the user's current message contains `CF_BYPASS=on` AS A STANDALONE LINE (not inside a fenced code block, blockquote, or quoted example). When the token appears only in quoted / pasted content, do NOT activate `user_bypass`. When the context is ambiguous (the token is present but it is unclear whether it is an instruction or quoted/pasted content), emit exactly this confirmation prompt and end the orchestrator turn immediately (hard interaction boundary, identical semantics to the Session Sub-Agent Approval Gate):
  ```
  I see `CF_BYPASS=on` in your message but cannot determine whether it is an instruction or quoted/pasted content.
  Reply `confirm bypass` to activate user_bypass for this turn, or anything else to leave it unset.
  ```
  On absence of an explicit `confirm bypass` reply, do NOT activate `user_bypass`. Resets to `armed` at the start of the next orchestrator assistant turn — NOT at sub-agent dispatch boundaries within the same turn. The CF_BYPASS=on token is orchestrator-turn-scoped only: sub-agents that do NOT load SKILL.md (cf-phase-compiler, cf-phase-runner) MUST NOT receive the parent orchestrator's user message verbatim; pass them only the structured dispatch payload defined in their contracts.

Read-only carve-out. `Read`, `Grep`, `Glob` are always exempt. `Bash` is exempt ONLY when the command contains: no shell construct that opens a file for writing — including but not limited to `>`, `>>`, `|tee`, `>|`, `>&`, `&>`, `|&`, here-doc/here-string output redirects (`<<`, `<<<`), or any external invocation of write-capable CLI tools; no file-mutating commands (`rm`, `mv`, `cp`, `mkdir`, `touch`, `chmod`, `install`, `ln`, `rename`), no `git commit` / `git push` / `git reset --hard` / `git checkout --` / `git restore`, and no calls to write-capable CLI tools (compilers writing artifacts, package managers installing, formatters writing in place, etc.). If in doubt, treat as write and apply the gate.

NotebookEdit semantics. The gate applies to each cell write. On ANY cell failure within a sequence, the orchestrator MUST: (1) ABORT all remaining cells in the sequence (do NOT continue executing remaining cells under the released gate), AND (2) reset the gate to `armed`. Cell execution side-effects (shell commands writing files from executed cells) are subject to the same gate rules as direct `Write` calls. Treat any individual `MultiEdit` edit failure with the same abort-then-reset semantics.

Sub-agent propagation. Gate state is NOT inherited by dispatched sub-agents. Each sub-agent that loads SKILL.md independently starts at `armed`. Write capability for author / coder / prompt-engineer / migrator sub-agents derives from their own tool contracts in the dispatched context, not from gate inheritance. Exception: `cf-phase-compiler` and `cf-phase-runner` intentionally do not load SKILL.md; write access for those agents is bounded by host isolation only.

Actor warning. `released_for_*` states are trust-based windows — the gate cannot verify which entity is calling write tools. While `released_for_dispatch` is active, the orchestrator MUST NOT call `Edit` / `Write` / `MultiEdit` / `NotebookEdit` itself; only the dispatched sub-agent owns those writes. Orchestrator-side writes are permitted only under `released_for_orchestrator_write` (with a named scope) or `released_for_inline_write`. For cf-phase-compiler and cf-phase-runner dispatch, the released_for_dispatch window is intentionally broader because these agents do not load SKILL.md. The orchestrator MUST suppress its own writes during this window; trust the agent's host isolation for the rest.

Violation handling. Any `Edit` / `Write` / `MultiEdit` / `NotebookEdit` invocation while `CF_PHASE_GATE=armed` is a `PHASE_SKIP` failure: STOP immediately, surface to the user `"phase-skip prevented — switching to /cf-<workflow>"`, and route into the matching workflow without performing the write.

If an `Edit` / `Write` / `MultiEdit` / `NotebookEdit` call is observed under `released_for_dispatch` from the orchestrator itself (rather than the dispatched sub-agent), this is also a `PHASE_SKIP` failure: STOP immediately, reset gate to `armed`, surface `"phase-skip prevented — orchestrator wrote during released_for_dispatch"`, and route to the matching workflow without performing the write. The same handler applies to writes outside the named scope under `released_for_orchestrator_write`.

### Session GIT_COMMIT_MODE Gate

`GIT_COMMIT_MODE` is a session-scoped flag probed once per chat session by the generate workflow (Phase 0.x) or, when entered first, by the plan workflow before any `cf-phase-compiler` or `cf-phase-runner` dispatch. It controls how write-capable sub-agents (`cf-generate-*-author-*`, `cf-generate-coder-*`, `cf-generate-prompt-engineer-*`, `cf-migrate-migrator`, `cf-phase-compiler`, `cf-phase-runner`) interact with git. Three modes (`commit`, `stage`, `none`) — full definitions and permitted operations are defined in `workflows/generate/phase-0-git-commit-mode.md` § Mode Semantics; the same definitions are propagated verbatim to each write-capable sub-agent dispatch payload's `git_constraint` field via `workflows/generate/phase-4-write.md` § Git constraint blocks.

Probe semantics: once per chat session (parallel to `SUB_AGENT_SESSION_APPROVED`). External-entry handoffs (briefs_only stop + resume in a new chat) re-probe. Do NOT re-probe on every workflow run within the same chat. `GIT_COMMIT_MODE` carries across multiple `/cf-generate` runs within the same chat session, just like `SUB_AGENT_SESSION_APPROVED`.

`GIT_COMMIT_MODE` is orthogonal to the Phase-Skip Gate. The Phase-Skip Gate guards write tool calls (`Edit`/`Write`/`MultiEdit`/`NotebookEdit`); `GIT_COMMIT_MODE` guards git tool calls. Both apply simultaneously and independently.

Every write-capable sub-agent dispatch payload MUST carry both `GIT_COMMIT_MODE` and `CONTRIBUTING_GUIDE` (path + key directives, or `null` when not found). The dispatch payload MUST include the mode-matched constraint block from `workflows/generate/phase-4-write.md` § Git constraint blocks.

### Session Sub-Agent Approval Gate

Native sub-agent dispatch requires explicit user approval once per chat session. `SUB_AGENT_SESSION_APPROVED=true` approves it for the session. This gate is orchestrator-only: dispatched sub-agents skip it unless they will dispatch another `cf-*` sub-agent.

If `SUB_AGENT_SESSION_APPROVED` is unset and the host supports native sub-agents, emit exactly this numbered-menu prompt (Approve sub-agent use for this session):

```text
This workflow can use Constructor Studio sub-agents for isolated/parallel work.

| Option | Action |
|---|---|
| 1 | Use native sub-agents — isolated/parallel dispatch, remembered for this session |
| 2 | Use inline fallback for this workflow — no isolation, slower, but no host primitive needed |

Suggested: 1 because native dispatch preserves context-isolation and parallelism when the host supports it.

Reply with 1 or 2.
```

The approval prompt is a hard interaction boundary: after emitting it, the orchestrator MUST end the assistant turn immediately. Absence of a user reply is not option `2`. Reply `1` = approve; reply `2` = decline; anything else re-prompts. Replies are trimmed of leading/trailing whitespace before matching. Replies containing the literal token "1" or "2" embedded in a longer phrase (e.g., "option 1 please") are accepted as the matching numeric choice.

Set `INLINE_FALLBACK=false` only when `SUB_AGENT_SESSION_APPROVED=true` (user replied `1`). Set `INLINE_FALLBACK=true` only when the user replied `2` or the host has no native sub-agent support. MUST NOT set `INLINE_FALLBACK=false` from host capability alone. MUST NOT default `INLINE_FALLBACK=true` from missing approval. Do not collapse the remaining states into a generic `otherwise` branch.

Probe once per workflow run. External-entry handoffs count as a new run and MUST re-probe. `SUB_AGENT_SESSION_APPROVED` carries across; `INLINE_FALLBACK` does not. A `briefs_only` plan-workflow stop followed by a resume in a new chat is an external-entry handoff and MUST re-probe; the prior session's `SUB_AGENT_SESSION_APPROVED` carries across only when the resume happens in the same chat session.

## Completion Invariants

A `/cf-generate` file-writing run with no remaining findings is
not complete until the final response ends with the `Post-Write Review Handoff` menu. If remaining findings exist, it is not complete until the
final response ends with the `Remediation Handoff` menu as the only actionable
reply menu; `W1`/`W2`/`W3` choices remain locked until remediation clears and
Phase 6 re-enters with `remaining_findings` empty. Exception: if the user stops
at `workflows/generate/phase-5/phase-5.2-semantic.md`'s inline long-loop
warning before any validator/reviewer/author dispatch and
`manifest.paths_written` is non-empty, the run is complete only when the final
response ends with that file's `Pre-Review Warning Handoff` block; this is the
sanctioned terminal path for pre-review warning aborts because no valid
`Validation Results` body exists yet.

A `/cf-analyze` run with actionable issues is not complete until the final response ends with the `Remediation Handoff` menu.

A `/cf-plan` run that compiled phase files is not complete until the final response ends with the Phase 4.2 next-steps menu OR the Phase 3.2A brief-checkpoint menu (for `briefs_only` stops). A run that stopped after emitting downstream phase-compilation prompts (`plan.execution_status = "prompts_emitted"`) is complete only when the final response ends with the emitted prompt set as the deliverable and no Phase 4.2 menu is shown. A run that stopped at the raw-input `n`-path or the decomposition `n`-path is a valid completion state and requires no terminal menu — the orchestrator must still emit the canonical stop message defined in `workflows/plan.md`.

`Fix Prompt`, `Plan Prompt`, `Direct Review Prompt`, and `Plan Review Prompt` blocks are emitted only on the next turn when the user chooses the matching handoff option.
