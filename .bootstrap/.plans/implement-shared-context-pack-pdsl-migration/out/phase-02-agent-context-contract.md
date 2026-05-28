# Phase 02 Agent Context Contract

## Purpose

This document defines the target contract for shared-context-pack-aware
controllers and prompt-consuming sub-agents.

## Roles

| Role | May load prompt assets from disk | Required behavior |
| --- | --- | --- |
| Top-level orchestrator | Yes | Resolve task context, reuse or extend the session pack, derive one `prompt_context_view` per dispatch, and block dispatch on missing required prompt context. |
| Dedicated shared-context-pack builder | Yes | Load only the prompt assets delegated by a controller, classify them, compute `etag`, and return them for insertion into the session pack. |
| Prompt-consuming sub-agent | No | Consume prompt instructions only from `prompt_context_view`, read task resources only when its task contract names them, and fail closed when required prompt context is absent. |

No other role is allowed to discover or reload prompt assets from disk.

## Required Agent Declaration

Every prompt-consuming sub-agent must declare
`prompt_context_requirements` semantically rather than as file-open steps.

Minimum contract:

```json
{
  "prompt_context_requirements": {
    "requires_shared_context_pack": true,
    "required_assets": [
      {
        "asset_key": "<semantic name>",
        "accepted_origins": ["core", "kit", "project"],
        "accepted_types": ["workflow", "skill", "requirement", "checklist", "rule", "system", "instruction"],
        "match_tags": ["<tag>", "..."],
        "section_tags": ["<tag>", "..."],
        "required_when": "<condition or null>"
      }
    ],
    "optional_assets": []
  }
}
```

Required rules:

- `requires_shared_context_pack` must be `true` for any prompt-consuming
  sub-agent.
- `required_assets` must cover every prompt asset class needed to execute the
  contract safely.
- `optional_assets` may be used for kit-provided or mode-specific prompt
  additions, but they do not weaken required assets.
- Declarations must describe prompt needs semantically; they must not say
  "open file X before acting."

## Required Prompt Context View Behavior

Before dispatch, the controller must provide:

```json
{
  "prompt_context_view": {
    "agent_id": "<string>",
    "asset_refs": [
      {
        "asset_id": "<stable asset id>",
        "section_ids": ["<section id>", "..."]
      }
    ]
  }
}
```

Rules:

- The view must satisfy every required asset declaration before dispatch.
- The view must contain only the prompt assets needed for that sub-agent and
  task.
- The sub-agent must treat `prompt_context_view` as its sole prompt and
  instruction source.
- The sub-agent may still read non-prompt task resources explicitly named by
  its task contract.
- A controller may pass whole assets or section-scoped references, but the
  selection must be deterministic and auditable.

## Controller Responsibilities

Controllers that dispatch prompt-consuming sub-agents must:

1. Determine the task kind, methodology, target type, rules mode, and active
   kit context.
2. Reuse the existing session `SHARED_CONTEXT_PACK` before discovering new
   prompt assets.
3. Load only the missing prompt assets required to satisfy declared semantic
   needs.
4. Preserve `origin`, `kit_id`, `asset_type`, tags, and `etag` metadata.
5. Build the smallest valid `prompt_context_view` for each dispatch.
6. Stop dispatch if any required prompt asset remains unresolved.

## Deterministic Failure Semantics

Missing prompt context must fail closed.

Required failure behavior:

- Do not dispatch the sub-agent when a required prompt asset is missing.
- Do not silently degrade to direct prompt-file reads.
- Report the missing semantic asset key or missing resolved asset id.
- Report which controller role attempted the dispatch.
- Preserve checkpoint or partial-return semantics when the surrounding
  workflow/agent contract already uses them.

Accepted failure forms:

- pre-dispatch validation failure returned to the controller
- partial/checkpoint return with unresolved prompt-context details
- orchestrator-owned repair prompt or recovery branch

Forbidden failure form:

- letting the sub-agent open `SKILL.md`, workflow files, requirement files,
  specs, `AGENTS.md`, sysprompts, or kit prompt files on its own

## Migration Notes For Later Phases

- `agents.toml` should become the durable home for prompt-context declarations
  or references to them.
- Agents that currently forbid `SKILL.md` reads but still read controller
  references, such as plan-specialized contracts, need explicit controller or
  minimal-context decisions in their migration phase.
- Review-only agents and write-capable agents follow the same prompt-context
  loading rule; write authority does not imply prompt-loader authority.
