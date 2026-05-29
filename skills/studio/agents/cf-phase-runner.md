---
description: Invoke when executing the next or a specific phase from a generated Constructor Studio plan inside a dedicated agent context, without delegating to ralphex.
---

<!-- toc -->

- [Inputs (dispatched-prompt contract)](#inputs-dispatched-prompt-contract)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

## Dispatch Guidance

This file is orchestration-time guidance for the controller, not a runtime
self-bootstrap contract for the dispatched sub-agent.

The controller MUST load this file, resolve the task-relevant instruction
assets from `SHARED_CONTEXT_PACK`, and synthesize a fully materialized final
dispatch prompt for this agent. The dispatched sub-agent MUST execute only that
final prompt and MUST NOT open prompt assets from disk directly.


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
  cfs_mode remains off — the controller supplies only the shared mode contract
  plus the authoritative phase-execution contract in the synthesized final
  dispatch prompt, while `plan.toml` remains a runtime resource. The orchestrator owns the Session Sub-Agent Approval Gate,
  INLINE_FALLBACK probe, and CF_PHASE_GATE release-reset window before
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
