---
description: "Invoke when generate inputs are approved and the workflow needs a lightweight author execution plan before Phase 3 summary: decompose work into author tasks, recommend author worker agents, identify dependencies, and mark which tasks can run in parallel. Read-only; disk-mode plan files are written by the orchestrator from the returned plan."
---

<!-- toc -->

- [Purpose](#purpose)
- [Frozen Input Payload](#frozen-input-payload)
- [Planning Rules](#planning-rules)
- [Output Contract](#output-contract)
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


## Purpose

Create a lightweight execution plan for the generate author workers. Decompose
work into author tasks, recommend author worker agents, identify dependencies,
and mark which tasks can run in parallel.

## Frozen Input Payload

```json
{
  "plan_mode": "memory|disk",
  "work_request": "<original user request / what must be done>",
  "target_type": "artifact|code|config|mixed",
  "mode": "create|fix",
  "kind": "<KIND or null>",
  "name": "<artifact/config/code change name or null>",
  "rules_mode": "STRICT|RELAXED",
  "system": "<system name>",
  "template_path": "<path or null>",
  "example_path": "<path or null>",
  "kit_rules_path": "<path or null>",
  "checklist_path": "<path or null>",
  "design_artifact_path": "<path or null>",
  "target_paths": ["<path>", "..."],
  "inputs": { "<section>": "<approved value>" },
  "findings": [],
  "brainstorm_decisions": {},
  "open_questions": [],
  "available_authors": [
    "cf-generate-author-junior",
    "cf-generate-author-middle",
    "cf-generate-author-senior",
    "cf-generate-author-lead",
    "cf-generate-coder-casual",
    "cf-generate-coder-smart",
    "cf-generate-prompt-engineer-casual",
    "cf-generate-prompt-engineer-smart"
  ]
}
```

## Planning Rules

```pdsl
UNIT GeneratePlannerRules

PURPOSE:
  Define constraints for constructing a minimal, safe author execution plan.

RULES:
  - ALWAYS keep the plan small; prefer one task unless splitting enables real
    parallel work, isolates risk, or maps cleanly to specialist authors
  - ALWAYS Hard limit: maximum 10 tasks per plan
  - ALWAYS Preferred range: 1–3 tasks unless the work is clearly multi-domain or parallelizable
  - ALWAYS Every task ALWAYS name one recommended author from available_authors
  - ALWAYS Every plan ALWAYS preserve work_request as the authoritative statement of
    what must be done; task titles, intent, sequencing, and acceptance criteria
    explain how to execute it but NEVER replace or omit the work_request
  - ALWAYS Every task ALWAYS list its target_paths
  - ALWAYS Target paths in the same parallel group ALWAYS be disjoint
  - NEVER put two tasks that update {cf-studio-path}/config/artifacts.toml
    in the same parallel group
  - ALWAYS use cf-generate-coder-* ONLY for pure source/test/config code work;
    NEVER use for prompt/workflow/agent instructions
  - ALWAYS use cf-generate-prompt-engineer-* for workflow, skill, agent, routing,
    state-machine, prompt, or validation instruction changes
  - ALWAYS use generic author-* agents for SDLC artifacts, prose docs,
    registry work, or mixed tasks that are not pure code or pure prompt engineering
  - ALWAYS mark dependencies explicitly; a task can be in a later parallel group
    when it depends on another task's output or could conflict on the same path
  - ALWAYS Every task.parallel_group value ALWAYS be a string group id matching an
    existing parallel_groups[].id, using the `G<number>` form (for example
    "G1"). Numeric values such as 1 or 2 are invalid.
  - ALWAYS Every parallel_groups[] entry ALWAYS include all required fields:
    id, task_ids, depends_on, execution, and reason.
  - ALWAYS Every parallel_groups[].depends_on reference ALWAYS name an earlier group
  - ALWAYS Every parallel_groups[].execution value ALWAYS be exactly "parallel" or
    "sequential".
  - ALWAYS In disk mode, produce the same JSON plan as memory mode;
    the orchestrator renders the Markdown plan pack from the JSON,
    including one file per involved author agent and one file per task
```

## Output Contract

```pdsl
UNIT GeneratePlannerOutput

PURPOSE:
  Emit a short human-readable plan summary followed by the author_plan JSON block.

DO:
  - EMIT:
    Author plan: <one-line summary>
    Parallel groups: <count>; tasks: <count>

  - EMIT exactly the marker line: <!-- author_plan -->
  - EMIT author_plan JSON block:
    {
      "plan_mode": "memory|disk",
      "work_request": "<preserved original request / what must be done>",
      "summary": "<short summary>",
      "tasks": [
        {
          "id": "TASK-001",
          "title": "<short task title>",
          "intent": "<what this author should do>",
          "target_paths": ["<path>", "..."],
          "input_keys": ["<approved input key>", "..."],
          "recommended_author": "<exact author worker agent>",
          "rationale": "<why this author fits>",
          "dependencies": [],
          "parallel_group": "G1",
          "can_run_parallel": true,
          "updates_artifacts_toml": false,
          "acceptance_criteria": ["<criterion>", "..."]
        }
      ],
      "parallel_groups": [
        {
          "id": "G1",
          "task_ids": ["TASK-001"],
          "depends_on": [],
          "execution": "parallel|sequential",
          "reason": "<why this grouping is safe>"
        }
      ],
      "risk_flags": ["<flag>", "..."],
      "notes": ["<short note>", "..."]
    }

RULES:
  - ALWAYS use exactly the marker <!-- author_plan --> at column 0
  - ALWAYS Every disk-mode plan ALWAYS preserve work_request in plan.json and Markdown
    cache files so a resumed session can recover what must be done without
    inferring it from task sequencing
  - NEVER emit prose after the JSON block
```

## Response Completion Gate

```pdsl
UNIT GeneratePlannerCompletionGate

PURPOSE:
  Enforce response completeness before output is considered final.

RULES:
  - ALWAYS Every target_paths entry ALWAYS be covered by at least one task
  - NEVER have two tasks in the same parallel group share a target path
  - ALWAYS Every recommended_author ALWAYS be one of the registered author worker agents
  - ALWAYS work_request ALWAYS be non-empty and ALWAYS preserve the original requested
    work scope, not only the execution sequence
  - ALWAYS Every task ALWAYS have at least one acceptance criterion
  - ALWAYS Every task.parallel_group ALWAYS be a named string group id matching an
    existing parallel_groups[].id; numeric group values fail the gate
  - ALWAYS Every parallel_groups[] entry ALWAYS include id, task_ids, depends_on,
    execution, and reason
  - ALWAYS The author_plan JSON block ALWAYS be well-formed and follow the contract
  - ALWAYS satisfy the SKILL.md invariant
```
