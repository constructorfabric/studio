---
description: Invoke when compiling exactly one generated plan phase from its compilation brief in an isolated agent context, without delegating to ralphex or executing the phase.
---

<!-- toc -->

- [Frozen Input Payload](#frozen-input-payload)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

## Dispatch Generator Contract

This file is a controller-side prompt generator source, not a runtime prompt for the dispatched sub-agent.

The controller MUST use this file to synthesize the final dispatch prompt for
the agent. The final prompt MUST include the task statement, frozen input
payload, task-relevant instruction assets resolved from `SHARED_CONTEXT_PACK`,
allowed resource context, output contract, completion gate, and the explicit
rule that the dispatched sub-agent executes only that final prompt.

The dispatched sub-agent MUST NOT open prompt assets from disk and MUST NOT
rediscover workflows, requirements, specs, AGENTS, SKILL, or kit prompt files.


## Frozen Input Payload

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
