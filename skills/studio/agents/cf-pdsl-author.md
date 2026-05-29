---
description: Invoke when cf-pdsl runs in new mode to create one prompt/workflow/skill instruction file using the PDSL spec.
---

# PDSL Author

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
  "AuthorManifest": {
    "type": "MANIFEST",
    "mode": "new",
    "paths_written": ["<target_path>"],
    "source_paths_read": ["<path>", "..."],
    "pdsl_spec_path": "{cf-studio-path}/.core/architecture/specs/PDSL.md",
    "summary": "<1-3 sentences>",
    "open_questions": []
  },
  "AuthorBlocked": {
    "type": "AUTHOR_BLOCKED",
    "reason": "<why>",
    "required_inputs": ["<input>", "..."],
    "open_questions": ["<question>", "..."]
  }
}
```

## Response Completion Gate

```text
UNIT PdslAuthorCompletion

RULES:
  - MUST return either `AuthorManifest` or `AuthorBlocked`
  - MUST include exactly one path in `AuthorManifest.paths_written`
```
