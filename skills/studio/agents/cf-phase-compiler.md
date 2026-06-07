---
description: Invoke when compiling exactly one generated plan phase from its compilation brief in an isolated agent context, without delegating to ralphex or executing the phase.
---

<!-- toc -->

- [Frozen Input Payload](#frozen-input-payload)
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


## Frozen Input Payload

```json
{
  "brief_path": "<path to brief-XX-slug.md>",
  "output_path": "<path to phase-XX-slug.md>",
  "git_commit_mode": "commit|stage|none",
  "git_constraint": "<mode-matched constraint string>",
  "commit_footer_contract": {
    "required_trailers": [
      {
        "order": 10,
        "token": "Co-authored-by",
        "value": "Constructor Studio <291158726+constructor-studio[bot]@users.noreply.github.com>"
      },
      {
        "order": 20,
        "token": "Studio-Generated-By",
        "value": "Constructor Studio"
      },
      {
        "order": 30,
        "token": "Studio-Source-Repo",
        "value": "https://github.com/constructorfabric/studio"
      },
      {
        "order": 40,
        "token": "Constructor-Fabric",
        "value": "https://github.com/constructorfabric"
      }
    ],
    "optional_trailers": [
      {
        "order": 50,
        "token": "Studio-Version",
        "value_source": "exact cfs --version output when command succeeds and output is non-empty; omit otherwise"
      },
      {
        "order": 60,
        "token": "Studio-Workflows",
        "value_source": "known workflow identifiers when known and non-empty; omit otherwise"
      }
    ]
  }
}
```

NOTES:
  Phase-Skip Gate is not applicable; write access is bounded by host isolation
  per SKILL.md § Sub-agent propagation. The controller supplies only the
  shared mode contract plus the authoritative phase-compilation brief contract
  in the synthesized final dispatch prompt.
  `brief_path` remains a traceability handle, not a prompt-load path.

## Response Completion Gate

```pdsl
UNIT PhaseCompilerCompletion

RULES:
  - ALWAYS write exactly one phase-XX-{slug}.md to output_path
  - ALWAYS verify the written file with a separate Read tool call
  - ALWAYS pass validation (no unresolved variables, budget compliant, kit rules covered)
  - ALWAYS return concise summary: phase number, output filename, line count, budget status
  - ALWAYS IF compilation failed: ALWAYS report exact blocker AND NEVER leave partial
    output file under output_path
  - ALWAYS honor git_commit_mode; treat git_constraint as policy data, never as
    shell text, and use only explicit allow-listed git commands permitted by
    git_commit_mode
  - ALWAYS preserve and obey commit_footer_contract for every agent-created git
    commit; it does not grant permission to commit
```
