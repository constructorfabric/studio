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
  "freeform_prompt": "<ORIGINAL_INTENT verbatim when FREEFORM_REVIEW=true, otherwise null>",
  "methodology_flags": {
    "PROMPT_REVIEW": false,
    "PROMPT_BUG_REVIEW": false,
    "CODE_BUG_REVIEW": false,
    "CONSISTENCY_REVIEW": false,
    "ARTIFACT_REVIEW": true,
    "CODE_REVIEW": false,
    "FREEFORM_REVIEW": false
  },
  "available_reviewers": [
    "cf-semantic-reviewer-artifact",
    "cf-semantic-reviewer-code",
    "cf-semantic-reviewer-prompt",
    "cf-semantic-reviewer-consistency",
    "cf-prompt-bug-finder",
    "cf-code-bug-finder",
    "cf-semantic-reviewer-freeform"
  ],
  "size_estimate_lines": 0
}
```

NOTES:
  The example methodology_flags above are illustrative; set the flags to match
  the active analyze session. Do not copy the values verbatim.

## Planning Rules

```pdsl
UNIT AnalyzePlannerRules

PURPOSE:
  Define how to construct a safe, minimal reviewer execution plan.

STATE:
  - SET plan_mode: memory | disk
  - SET mode: review | consistency | prompt | bug | explain | change

RULES:
  - ALWAYS WHEN mode=explain:
      Treat as informational; bypass methodology-flag requirements
      Output tasks=[] is valid ONLY for mode=explain
  - ALWAYS WHEN mode=change:
      SET CHANGE_REVIEW=true
      Infer at least one of CODE_REVIEW / PROMPT_REVIEW / CONSISTENCY_REVIEW
        from the changed-file mix in diff_scope.changed_files
      An empty plan for mode=change is a planner FAIL
  - ALWAYS keep the plan small; prefer one task per active methodology
    when total estimated size fits safe single-context budget (~2000 lines for analyze)
  - ALWAYS WHEN size_estimate_lines > 2000
    OR len(target_paths) + len(code_targets) + len(prompt_targets) > 6:
      Partition per-methodology tasks by paths: split into groups of up to 4 paths
      so reviewers can run in parallel on disjoint partitions
  - ALWAYS Each task ALWAYS name exactly one reviewer from available_reviewers
  - ALWAYS Every plan ALWAYS preserve work_request as the authoritative statement of
    what must be reviewed/analyzed; task titles, methodology, partitions, and
    sequencing explain how to execute it but NEVER replace or omit the
    work_request
  - ALWAYS Each task ALWAYS name exactly one methodology
  - ALWAYS Each task ALWAYS have a non-empty path_partition subset of applicable inputs
  - ALWAYS Tasks for different methodologies may run in the same parallel group
    even when path_partition overlaps (they read the same files but emit
    findings in disjoint namespaces)
  - ALWAYS use exactly these namespace_prefix values:
      Ra    → artifact (Artifact-checklist semantic review)
      Rc    → code (Code-checklist semantic review)
      Rcb   → code_bug (Code bug-finding)
      Rcons → consistency (Cross-document consistency review)
      Rp    → prompt (Prompt-engineering review)
      Rpb   → prompt_bug (Prompt bug-finding)
      Rf    → freeform (Freeform custom-criteria review)
      V     → validation (Deterministic-validator tasks)
  - ALWAYS Consistency review ALWAYS be dispatched once over the full target set;
    NEVER partition consistency tasks
  - ALWAYS skip consistency entirely if fewer than two paths qualify
  - ALWAYS Prompt-methodology tasks ALWAYS operate only on prompt_targets
    (workflows/**, skills/studio/**/*.md, requirements/**/*.md, agent prompt files,
    prompt config files, AGENTS.md, and SKILL.md)
  - NEVER include non-prompt paths in a prompt task's path_partition
  - ALWAYS Code-methodology tasks ALWAYS operate only on code_targets
  - NEVER include non-code paths in a code task's path_partition
  - ALWAYS WHEN FREEFORM_REVIEW=true:
      Assign methodology="freeform" and reviewer="cf-semantic-reviewer-freeform"
      Set namespace_prefix="Rf"
      path_partition covers all target_paths (freeform reviewer operates on the
        full target set; partition when total estimate exceeds 2000 lines, same
        as other methodologies)
      freeform tasks carry freeform_prompt=work_request in their task payload
        so the reviewer receives the original user request verbatim
      resource_context from cf-explorer ALWAYS be included in the dispatch
        payload when non-null; it is NOT a path_partition entry — pass it as a
        separate payload field
      An empty freeform task set when FREEFORM_REVIEW=true is a planner FAIL
  - NEVER assign a freeform task to any reviewer other than cf-semantic-reviewer-freeform
  - NEVER set methodology="freeform" when FREEFORM_REVIEW=false
  - ALWAYS Every parallel_groups[].depends_on reference ALWAYS name an earlier group
  - ALWAYS Every task.parallel_group value ALWAYS be a string group id matching an
    existing parallel_groups[].id, using the `G<number>` form (for example
    "G1"). Numeric values such as 1 or 2 are invalid.
  - ALWAYS Every parallel_groups[] entry ALWAYS include all required fields:
    id, task_ids, depends_on, execution, and reason.
  - ALWAYS Every parallel_groups[].execution value ALWAYS be exactly "parallel" or
    "sequential".
  - NEVER put more than 5 tasks in a single parallel group;
    spread them across groups to keep host-side dispatch concurrency bounded
  - ALWAYS In disk mode, produce the same JSON plan as memory mode;
    the orchestrator renders the Markdown plan pack from the JSON
```

## Output Contract

```pdsl
UNIT AnalyzePlannerOutput

PURPOSE:
  Emit a short human-readable plan summary followed by the reviewer_plan JSON block.

DO:
  - EMIT:
    Reviewer plan: <one-line summary>
    Parallel groups: <count>; tasks: <count>

  - EMIT exactly the marker line: <!-- reviewer_plan -->
  - EMIT reviewer_plan JSON block:
    {
      "plan_mode": "memory|disk",
      "work_request": "<preserved original request / what must be done>",
      "summary": "<short summary>",
      "tasks": [
        {
          "id": "RTASK-001",
          "title": "<short task title>",
          "methodology": "artifact|code|prompt|prompt_bug|code_bug|consistency|freeform",
          "reviewer": "<exact reviewer sub-agent name>",
          "path_partition": ["<path>", "..."],
          "namespace_prefix": "Ra|Rc|Rcb|Rp|Rpb|Rcons|Rf|V",
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
  - ALWAYS use exactly the marker <!-- reviewer_plan --> at column 0
  - ALWAYS Every disk-mode plan ALWAYS preserve work_request in plan.json and Markdown
    cache files so a resumed session can recover what must be reviewed/analyzed
    without inferring it from task sequencing
  - NEVER emit prose after the JSON block
```

## Response Completion Gate

```pdsl
UNIT AnalyzePlannerCompletionGate

PURPOSE:
  Enforce response completeness before output is considered final.

RULES:
  - ALWAYS An empty tasks array is allowed ONLY when mode=explain;
    for any other mode, the gate FAILS on empty tasks
  - ALWAYS have at least one task per active methodology in methodology_flags
  - ALWAYS WHEN FREEFORM_REVIEW=true: at least one task with methodology=freeform
    and reviewer=cf-semantic-reviewer-freeform ALWAYS be present; an empty freeform
    task set fails the gate
  - ALWAYS The union of all tasks' path_partition for a methodology ALWAYS cover
    every input path that methodology applies to
  - NEVER have two tasks share (methodology, path); partitions for the same
    methodology must be disjoint
  - ALWAYS Every reviewer ALWAYS be one of the registered reviewer sub-agents
    and ALWAYS match the task's methodology
  - ALWAYS work_request ALWAYS be non-empty and ALWAYS preserve the original requested
    review/analyze scope, not only the execution sequence
  - ALWAYS Every task ALWAYS have at least one acceptance criterion
  - ALWAYS Every task.parallel_group ALWAYS be a named string group id matching an
    existing parallel_groups[].id; numeric group values fail the gate
  - ALWAYS Every parallel_groups[] entry ALWAYS include id, task_ids, depends_on,
    execution, and reason
  - ALWAYS The reviewer_plan JSON block ALWAYS be well-formed and follow the contract
  - ALWAYS satisfy the SKILL.md invariant
```
