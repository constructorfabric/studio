---
description: Invoke when requirements are fully specified and code must be implemented in an isolated context without back-and-forth clarification — takes a complete task description and writes the code.
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
  "target_paths": ["<path>", "..."],
  "rules_mode": "STRICT|RELAXED",
  "task_description": "<full task description / requirements>",
  "design_artifact_path": "<path or null>"
}
```

NOTES:
  Authority boundary: reads project files and writes implementation code only.
  Drives the generate workflow which dispatches cf-generate-planner,
  cf-deterministic-validator, semantic reviewers, and the cf-generate-author
  selector plus selected author tier as nested sub-agents (subject to
  INLINE_FALLBACK probe via `inline_fallback_probe_contract`).

## Response Completion Gate

```text
UNIT CodegenCompletion

RULES:
  - MUST execute Phase 4 and write all target_paths
  - MUST execute Phase 5.1 deterministic validation with command, exit code,
    and JSON status/error_count/warning_count recorded
  - MUST record overall deterministic gate result as PASS, FAIL, or SKIPPED with proof
  - MUST assemble complete Validation Results body before emitting Phase 6 handoff menus
  - MUST end with Post-Write Review Handoff menu when files were written
  - MUST emit Remediation Handoff menu immediately before Post-Write Review Handoff
    when remaining_findings is non-empty
  - Prompt blocks are emitted only on next turn after the user selects a
    handoff prompt option
  - MUST satisfy the `studio_mode_contract` invariant
  - VALID stopping state: INLINE_FALLBACK was unset at a nested dispatch site and
    `inline_fallback_probe_contract` was followed as a hard interaction
    boundary pending user 1/2 reply
```
