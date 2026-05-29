---
description: Invoke when compiling exactly one generated plan phase from its compilation brief in an isolated agent context, without delegating to ralphex or executing the phase.
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
  "brief_path": "<path to brief-XX-slug.md>",
  "output_path": "<path to phase-XX-slug.md>",
  "git_commit_mode": "commit|stage|none",
  "git_constraint": "<mode-matched constraint string>"
}
```

NOTES:
  Phase-Skip Gate is not applicable; write access is bounded by host isolation
  per SKILL.md § Sub-agent propagation. The controller supplies only the
  shared mode contract plus the authoritative phase-compilation brief contract
  in the synthesized final dispatch prompt.
  `brief_path` remains a traceability handle, not a prompt-load path.

## Response Completion Gate

```text
UNIT PhaseCompilerCompletion

RULES:
  - MUST write exactly one phase-XX-{slug}.md to output_path
  - MUST verify the written file with a separate Read tool call
  - MUST pass validation (no unresolved variables, budget compliant, kit rules covered)
  - MUST return concise summary: phase number, output filename, line count, budget status
  - IF compilation failed: MUST report exact blocker AND MUST_NOT leave partial
    output file under output_path
  - MUST honor git_commit_mode — no git invocations beyond git_constraint
```
