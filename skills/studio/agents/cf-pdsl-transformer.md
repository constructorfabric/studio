---
description: Invoke when cf-pdsl runs in transform mode to convert one or more prose prompt/workflow/skill files into PDSL.
---

# PDSL Transformer

## Dispatch Generator Contract

This file is a controller-side prompt generator source, not a runtime prompt for the dispatched sub-agent.

The controller MUST use this file to synthesize the final dispatch prompt for
the agent. The final prompt MUST include the task statement, frozen input
payload, task-relevant instruction assets resolved from `SHARED_CONTEXT_PACK`,
allowed resource context, output contract, completion gate, and the explicit
rule that the dispatched sub-agent executes only that final prompt.

The dispatched sub-agent MUST NOT open prompt assets from disk and MUST NOT
rediscover workflows, requirements, specs, AGENTS, SKILL, or kit prompt files.


## Output

```json
{
  "TransformManifest": {
    "type": "MANIFEST",
    "mode": "transform",
    "paths_written": ["<path>", "..."],
    "paths_blocked": [],
    "source_paths_read": ["<path>", "..."],
    "pdsl_spec_path": "{cf-studio-path}/.core/architecture/specs/PDSL.md",
    "summary": "<1-3 sentences>",
    "open_questions": []
  },
  "TransformBlocked": {
    "type": "TRANSFORM_BLOCKED",
    "paths_written": ["<successfully transformed path>", "..."],
    "paths_blocked": ["<blocked path>", "..."],
    "reason": "<why>",
    "open_questions": ["<question>", "..."]
  }
}
```

## Response Completion Gate

```text
UNIT PdslTransformerCompletion

RULES:
  - MUST return either `TransformManifest` or `TransformBlocked`
  - MUST account for every input target path in `paths_written` or `paths_blocked`
```
