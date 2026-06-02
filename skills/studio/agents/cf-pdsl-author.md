---
description: Invoke when cf-pdsl runs in new mode to create one prompt/workflow/skill instruction file using the PDSL spec.
---

# PDSL Author

## Dispatch Generator Contract

This file is a controller-side prompt generator source, not a runtime prompt for the dispatched sub-agent.

The controller uses this file to synthesize the final dispatch prompt for
the agent. The final prompt includes the task statement, frozen input payload,
task-relevant instruction assets resolved from `SHARED_CONTEXT_PACK`, allowed
resource context, output contract, completion gate, and the explicit rule that
the dispatched sub-agent executes only that final prompt.
The final prompt also requires every generated PDSL instruction block to
use a `pdsl` Markdown fence, not `text`.
The final prompt also requires generated `STATE`, `WHEN`, `DO`, `RULES`,
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

```pdsl
UNIT PdslAuthorCompletion

RULES:
  - ALWAYS return either `AuthorManifest` or `AuthorBlocked`
  - ALWAYS include exactly one path in `AuthorManifest.paths_written`
  - ALWAYS emit structured execution sections as list blocks with valid section
    starter keywords
  - ALWAYS emit menu options with decimal numbers first, placing aliases after
    the number
  - NEVER introduce unregistered PDSL keywords unless the manifest identifies
    them as proposed spec extensions
```
