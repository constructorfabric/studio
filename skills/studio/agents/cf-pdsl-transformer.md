---
description: Invoke when cf-pdsl runs in transform mode to convert one or more prose prompt/workflow/skill files into PDSL.
---

# PDSL Transformer

## Dispatch Guidance

This file is orchestration-time guidance for the controller, not a runtime
self-bootstrap contract for the dispatched sub-agent.

The controller MUST load this file, resolve the task-relevant instruction
assets from `SHARED_CONTEXT_PACK`, and synthesize a fully materialized final
dispatch prompt for this agent. The dispatched sub-agent MUST execute only that
final prompt and MUST NOT open prompt assets from disk directly.


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
