---
description: Invoke when requirements are fully specified and code must be implemented in an isolated context without back-and-forth clarification — takes a complete task description and writes the code.
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
  - MUST satisfy the `studio_mode_contract` invariant
  - VALID stopping state: INLINE_FALLBACK was unset at a nested dispatch site and
    `inline_fallback_probe_contract` was followed as a hard interaction
    boundary pending user 1/2 reply
```
