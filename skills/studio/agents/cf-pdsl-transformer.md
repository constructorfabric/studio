---
description: Invoke when cf-pdsl runs in transform mode to convert one or more prose prompt/workflow/skill files into PDSL.
---

# PDSL Transformer

## Dispatch Generator Contract

This file is a controller-side prompt generator source, not a runtime prompt for the dispatched sub-agent.

The controller uses this file to synthesize the final dispatch prompt for
the agent. The final prompt includes the task statement, frozen input
payload, task-relevant instruction assets resolved from `SHARED_CONTEXT_PACK`,
allowed resource context, output contract, completion gate, and the explicit
rule that the dispatched sub-agent executes only that final prompt.
The final prompt also requires every transformed PDSL instruction block to
use a `pdsl` Markdown fence, not `text`.
The final prompt also requires transformed `STATE`, `WHEN`, `DO`, `RULES`,
and `INVARIANTS` sections to be list blocks whose top-level items start with
the starter keywords allowed by `architecture/specs/PDSL.md`:

- `STATE`: `SET`
- `WHEN`: `REQUIRE`, `AND`, `OR`, `NOT`
- `DO`: `SET`, `LOAD`, `RUN`, `EMIT`, `EMIT_MENU`, `WAIT`, `STOP_TURN`,
  `CONTINUE`, `DISPATCH`, `RETURN`, `REQUIRE`, `NEVER`
- `RULES` and `INVARIANTS`: `ALWAYS`, `NEVER`
- `OPTIONS`: a decimal number such as `1`, `2`, `3`

The dispatched sub-agent does not open prompt assets from disk and does not
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

```pdsl
UNIT PdslTransformerCompletion

RULES:
  - ALWAYS return either `TransformManifest` or `TransformBlocked`
  - ALWAYS account for every input target path in `paths_written` or `paths_blocked`
  - ALWAYS normalize ad-hoc uppercase action verbs to registered PDSL keywords
    when the meaning is equivalent
  - ALWAYS normalize structured execution sections to list blocks with valid
    section starter keywords
  - ALWAYS normalize menu options so every top-level option starts with a
    decimal number
  - NEVER introduce unregistered PDSL keywords unless `TransformBlocked` or
    `TransformManifest.open_questions` identifies them as proposed spec
    extensions
```
