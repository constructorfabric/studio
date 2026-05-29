---
description: Invoke when cf-pdsl runs in new mode to create one prompt/workflow/skill instruction file using the PDSL spec.
---

# PDSL Author

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
