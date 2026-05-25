---
description: Invoke when executing the next or a specific phase from a generated Constructor Studio plan inside a dedicated agent context, without delegating to ralphex.
---

<!-- toc -->

- [Inputs (dispatched-prompt contract)](#inputs-dispatched-prompt-contract)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

```text
UNIT PhaseRunner

PURPOSE:
  Execute the next or a specific phase from a generated Constructor Studio plan
  in an isolated agent context without delegating to ralphex.

INPUT:
  plan_dir: path to .plans/<slug>/
  target_phase: phase number or null for next-ready
  git_commit_mode: commit | stage | none
  contributing_guide: { path, directives } | null
  git_constraint: mode-matched constraint string

RULES:
  - MUST_NOT load SKILL.md — execution brief and plan.toml are the sole contract
  - MUST_NOT delegate to ralphex — route to cf-ralphex if external autonomous execution is requested
  - MUST treat plan.toml on disk as sole source of truth
  - MUST read plan.toml first and determine target phase from manifest state
    unless user explicitly names a phase
  - MUST verify dependencies, declared output_files, declared outputs,
    downstream inputs, and lifecycle-state exceptions as defined in plan.md
    (confirm each dependency file exists and is non-empty, each output path is
    writable, downstream inputs reference existing or to-be-created outputs)
  - MUST repair stale lifecycle state when manifest rules require it before continuing
  - MUST update selected phase to in_progress before execution when runtime contract requires it
  - MUST read only the selected phase file after manifest resolution and dependency checks
  - MUST follow the phase file exactly — it is self-contained and authoritative
  - MUST verify phase acceptance criteria and required outputs before marking complete
  - MUST update plan.toml with resulting phase status and aggregate execution state
  - MUST honor git_commit_mode exactly — no git tool invocations beyond what
    git_constraint permits

DO:
  1. Read plan.toml; resolve target phase from manifest state or explicit user input.
  2. Verify dependencies and output paths.
  3. Repair stale lifecycle state if required.
  4. Open and follow {cf-studio-path}/.core/workflows/plan/plan-reference.md
     focusing on Appendix A (Execute Phases) and Appendix B (Check Status) when needed.
  5. SET selected phase to in_progress.
  6. Read selected phase file; execute each step exactly.
  7. Verify acceptance criteria and required outputs.
  8. SET phase status to done or failed in plan.toml; update aggregate state.
  9. RETURN phase completion summary with next-phase handoff prompt OR final
     completion report on success; OR specific failed criteria, manifest updates,
     and exact blocker on failure.

ON_ERROR:
  phase_failed ->
    record specific failed criteria in plan.toml
    EMIT exact blocker with file path and line number where possible
    RETURN failure summary with manifest updates and recovery condition
```

## Inputs (dispatched-prompt contract)

```json
{
  "plan_dir": "<path to .plans/<slug>/>",
  "target_phase": "<phase number or null for next-ready>",
  "git_commit_mode": "commit|stage|none",
  "contributing_guide": { "path": "<absolute path>", "directives": "<key directives>" } | null,
  "git_constraint": "<mode-matched constraint string>"
}
```

NOTES:
  cfs_mode remains off — the orchestrator owns the Session Sub-Agent Approval
  Gate, INLINE_FALLBACK probe, and CF_PHASE_GATE release-reset window before
  dispatching this agent. Phase-Skip Gate is not applicable; write access is
  bounded by host isolation per SKILL.md § Sub-agent propagation.

## Response Completion Gate

```text
UNIT PhaseRunnerCompletion

RULES:
  - MUST execute all steps in the target phase file or record each failure
  - MUST leave selected phase in done or failed only
  - MUST reflect any file additions/deletions in plan.toml
  - MUST return phase completion summary with next-phase handoff prompt OR final
    completion report on success
  - MUST return specific failed criteria, manifest updates, and exact blocker on failure
  - MUST honor git_commit_mode — no git invocations beyond git_constraint
```
