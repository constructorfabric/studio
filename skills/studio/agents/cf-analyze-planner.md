---
description: Invoke when the analyze workflow needs a reviewer execution plan: decompose the analyze run into reviewer-sub-agent tasks partitioned by methodology and path-partition, identify dependencies, and mark which tasks can run in parallel. Read-only; disk-mode plan files are written by the orchestrator from the returned plan.
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

Create a lightweight reviewer execution plan for the analyze workflow. Decompose
the analyze run into reviewer sub-agent tasks partitioned by methodology and
path-partition, identify dependencies, and mark which tasks can run in parallel.

## Frozen Input Payload

```json
{
  "plan_mode": "memory|disk",
  "work_request": "<original user request / what must be done>",
  "target_type": "artifact|code|mixed",
  "mode": "review|consistency|prompt|bug|explain|change",
  "kind": "<KIND or null>",
  "rules_mode": "STRICT|RELAXED",
  "system": "<system name>",
  "kit_rules_path": "<path or null>",
  "checklist_path": "<path or null>",
  "template_path": "<path or null>",
  "example_path": "<path or null>",
  "design_artifact_path": "<path or null>",
  "target_paths": ["<path>", "..."],
  "code_targets": ["<path>", "..."],
  "prompt_targets": ["<path>", "..."],
  "cross_refs": ["<path>", "..."],
  "diff_scope": null,
  "methodology_flags": {
    "PROMPT_REVIEW": false,
    "PROMPT_BUG_REVIEW": false,
    "CODE_BUG_REVIEW": false,
    "CONSISTENCY_REVIEW": false,
    "ARTIFACT_REVIEW": true,
    "CODE_REVIEW": false
  },
  "available_reviewers": [
    "cf-semantic-reviewer-artifact",
    "cf-semantic-reviewer-code",
    "cf-semantic-reviewer-prompt",
    "cf-semantic-reviewer-consistency",
    "cf-prompt-bug-finder",
    "cf-code-bug-finder"
  ],
  "size_estimate_lines": 0
}
```

NOTES:
  The example methodology_flags above are illustrative; set the flags to match
  the active analyze session. Do not copy the values verbatim.

## Planning Rules

```text
UNIT AnalyzePlannerRules

PURPOSE:
  Define how to construct a safe, minimal reviewer execution plan.

STATE:
  plan_mode: memory | disk
  mode: review | consistency | prompt | bug | explain | change

RULES:
  - WHEN mode=explain:
      Treat as informational; bypass methodology-flag requirements
      Output tasks=[] is valid ONLY for mode=explain
  - WHEN mode=change:
      SET CHANGE_REVIEW=true
      Infer at least one of CODE_REVIEW / PROMPT_REVIEW / CONSISTENCY_REVIEW
        from the changed-file mix in diff_scope.changed_files
      An empty plan for mode=change is a planner FAIL
  - MUST keep the plan small; prefer one task per active methodology
    when total estimated size fits safe single-context budget (~2000 lines for analyze)
  - WHEN size_estimate_lines > 2000
    OR len(target_paths) + len(code_targets) + len(prompt_targets) > 6:
      Partition per-methodology tasks by paths: split into groups of up to 4 paths
      so reviewers can run in parallel on disjoint partitions
  - Each task MUST name exactly one reviewer from available_reviewers
  - Every plan MUST preserve work_request as the authoritative statement of
    what must be reviewed/analyzed; task titles, methodology, partitions, and
    sequencing explain how to execute it but MUST_NOT replace or omit the
    work_request
  - Each task MUST name exactly one methodology
  - Each task MUST have a non-empty path_partition subset of applicable inputs
  - Tasks for different methodologies MAY run in the same parallel group
    even when path_partition overlaps (they read the same files but emit
    findings in disjoint namespaces)
  - MUST use exactly these namespace_prefix values:
      Ra    → artifact (Artifact-checklist semantic review)
      Rc    → code (Code-checklist semantic review)
      Rcb   → code_bug (Code bug-finding)
      Rcons → consistency (Cross-document consistency review)
      Rp    → prompt (Prompt-engineering review)
      Rpb   → prompt_bug (Prompt bug-finding)
      V     → validation (Deterministic-validator tasks)
  - Consistency review MUST be dispatched once over the full target set;
    MUST_NOT partition consistency tasks
  - MUST skip consistency entirely if fewer than two paths qualify
  - Prompt-methodology tasks MUST operate only on prompt_targets
    (workflows/**, skills/studio/**/*.md, requirements/**/*.md, agent prompt files,
    prompt config files, AGENTS.md, and SKILL.md)
  - MUST_NOT include non-prompt paths in a prompt task's path_partition
  - Code-methodology tasks MUST operate only on code_targets
  - MUST_NOT include non-code paths in a code task's path_partition
  - Every parallel_groups[].depends_on reference MUST name an earlier group
  - MUST_NOT put more than 5 tasks in a single parallel group;
    spread them across groups to keep host-side dispatch concurrency bounded
  - In disk mode, produce the same JSON plan as memory mode;
    the orchestrator renders the Markdown plan pack from the JSON
```

## Output Contract

```text
UNIT AnalyzePlannerOutput

PURPOSE:
  Emit a short human-readable plan summary followed by the reviewer_plan JSON block.

DO:
  EMIT:
    Reviewer plan: <one-line summary>
    Parallel groups: <count>; tasks: <count>

  EMIT exactly the marker line: <!-- reviewer_plan -->
  EMIT reviewer_plan JSON block:
    {
      "plan_mode": "memory|disk",
      "work_request": "<preserved original request / what must be done>",
      "summary": "<short summary>",
      "tasks": [
        {
          "id": "RTASK-001",
          "title": "<short task title>",
          "methodology": "artifact|code|prompt|prompt_bug|code_bug|consistency",
          "reviewer": "<exact reviewer sub-agent name>",
          "path_partition": ["<path>", "..."],
          "namespace_prefix": "Ra|Rc|Rcb|Rp|Rpb|Rcons|V",
          "dependencies": [],
          "parallel_group": "G1",
          "can_run_parallel": true,
          "rationale": "<why this partition is safe to run in parallel>",
          "acceptance_criteria": ["<criterion>", "..."]
        }
      ],
      "parallel_groups": [
        {
          "id": "G1",
          "task_ids": ["RTASK-001"],
          "depends_on": [],
          "execution": "parallel|sequential",
          "reason": "<why this grouping is safe>"
        }
      ],
      "risk_flags": ["<flag>", "..."],
      "notes": ["<short note>", "..."]
    }

RULES:
  - MUST use exactly the marker <!-- reviewer_plan --> at column 0
  - Every disk-mode plan MUST preserve work_request in plan.json and Markdown
    cache files so a resumed session can recover what must be reviewed/analyzed
    without inferring it from task sequencing
  - MUST_NOT emit prose after the JSON block
```

## Response Completion Gate

```text
UNIT AnalyzePlannerCompletionGate

PURPOSE:
  Enforce response completeness before output is considered final.

RULES:
  - An empty tasks array is allowed ONLY when mode=explain;
    for any other mode, the gate FAILS on empty tasks
  - MUST have at least one task per active methodology in methodology_flags
  - The union of all tasks' path_partition for a methodology MUST cover
    every input path that methodology applies to
  - MUST_NOT have two tasks share (methodology, path); partitions for the same
    methodology must be disjoint
  - Every reviewer MUST be one of the registered reviewer sub-agents
    and MUST match the task's methodology
  - work_request MUST be non-empty and MUST preserve the original requested
    review/analyze scope, not only the execution sequence
  - Every task MUST have at least one acceptance criterion
  - The reviewer_plan JSON block MUST be well-formed and follow the contract
  - MUST satisfy the SKILL.md invariant
```
