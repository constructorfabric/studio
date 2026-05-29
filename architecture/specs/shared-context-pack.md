---
studio: true
type: spec
name: Shared Context Pack Specification
version: 2.0
purpose: Define session-scoped prompt-asset reuse and orchestration-time final prompt synthesis for Studio sub-agents
drivers:
  - cpt-studio-fr-core-workflows
  - cpt-studio-fr-core-config
---

# Shared Context Pack Specification

## Overview

Constructor Studio loads a large amount of prompt-bearing material:
workflows, skills, requirements, checklists, system prompts, kit instructions,
and project-level instruction surfaces such as configured sysprompts.

This specification defines a session-scoped `SHARED_CONTEXT_PACK` that stores
those prompt assets exactly once per chat session. The pack is owned by the
top-level controller. Sub-agents never load prompt assets directly.

Agent prompt files remain important, but their role changes:

- `skills/studio/agents/*.md` are orchestration-time prompt sources
- they are read by the controller, not by the leaf agent
- the controller uses them as guidance/templates for synthesizing the final
  task-specific dispatch prompt
- the dispatched sub-agent receives only that fully materialized final prompt

The pack is strictly limited to prompt and instruction assets. Non-prompt task
resources remain outside the pack.

## Goals

- load prompt and instruction assets once per chat session
- make prompt loading controller-owned
- keep sub-agents from reopening prompt assets from disk
- preserve agent prompt files as orchestration-time guidance
- let the controller synthesize a minimal final prompt per dispatch
- support core, kit, and project prompt assets
- survive compaction by persisting pack state outside volatile model context

## Non-Goals

- storing source code, target artifacts, or documentation-under-review inside
  the pack
- forcing a deterministic slot-filling compiler for final prompt assembly
- making leaf agents discover prompt dependencies on their own
- replacing normal resource-input handling for non-prompt files

## Core Terms

**Prompt asset**: any file or section whose primary purpose is to instruct an
agent how to behave.

**Shared context pack**: the persisted session-scoped JSON store for prompt
assets already loaded by the controller.

**Agent prompt source**: a canonical agent markdown file under
`skills/studio/agents/*.md` used by the controller as orchestration-time
guidance for generating a final dispatch prompt.

**Final dispatch prompt**: the task-specific prompt synthesized by the
controller from the agent prompt source, the current task state, and the
relevant subset of `SHARED_CONTEXT_PACK`.

**Resource input**: any non-prompt task data such as code, docs, artifacts,
diffs, manifests, or target files.

## Scope Boundary

### Included In Shared Context Pack

The pack MAY include only prompt and instruction assets such as:

- workflow prompts
- skill prompts
- system prompts
- methodology docs
- checklists used as agent instructions
- rules used as agent instructions
- `AGENTS.md`-like instruction docs
- kit-provided guidance, validation rules, and checklists
- project sysprompts and other project-level instruction surfaces

### Excluded From Shared Context Pack

The pack MUST NOT contain:

- source code
- target files
- PRDs, ADRs, DESIGN docs, or markdown artifacts when they are the subject of
  work rather than instructions to the agent
- diffs, manifests, runtime reports, or dependency inventories
- examples used as domain content rather than instructions
- any other non-prompt task resource

If a file mixes prompt and non-prompt content, the controller MUST extract only
the instruction-bearing sections into the pack.

## Asset Origins

Each prompt asset MUST declare an `origin`:

- `core` for Constructor Studio core prompt assets
- `kit` for task-relevant kit prompt assets
- `project` for project-level prompt assets such as configured sysprompts

## Lifetime And Compaction Safety

`SHARED_CONTEXT_PACK` is scoped to the entire chat session, not to one
workflow run.

Rules:

- the controller MUST reuse the existing session pack before loading any new
  prompt asset
- the controller MAY append missing prompt assets as new tasks appear in the
  same session
- reused assets MUST be revalidated by `etag` before reuse
- the pack MUST be persisted outside volatile model context
- compaction MUST NOT make the pack unrecoverable
- after compaction, the controller MUST restore pack state from persisted
  storage before later dispatch

## Operational Model

```text
UNIT SharedContextPackLifecycle

PURPOSE:
  Define controller-owned load, reuse, refresh, and recovery behavior.

STATE:
  SHARED_CONTEXT_PACK_STATUS: absent | current | stale
    default: absent

DO:
  IF persisted session pack is missing:
    SET SHARED_CONTEXT_PACK_STATUS = absent
  ELSE IF any reused asset fails `etag` validation:
    SET SHARED_CONTEXT_PACK_STATUS = stale
  ELSE:
    SET SHARED_CONTEXT_PACK_STATUS = current

  IF SHARED_CONTEXT_PACK_STATUS == absent:
    REQUIRE controller loads required prompt assets from disk
    REQUIRE controller persists the resulting pack
    SET SHARED_CONTEXT_PACK_STATUS = current

  IF SHARED_CONTEXT_PACK_STATUS == stale:
    REQUIRE controller refreshes only stale or missing assets
    REQUIRE controller persists the refreshed pack
    SET SHARED_CONTEXT_PACK_STATUS = current

RULES:
  - MUST keep prompt-asset loading controller-owned
  - MUST reuse current session-pack assets before loading new ones
  - MUST_NOT rebuild the entire pack for every workflow run by default
  - MUST_NOT allow sub-agents to repair missing prompt assets themselves
```

```text
UNIT FinalPromptSynthesis

PURPOSE:
  Define how a controller prepares a sub-agent dispatch.

DO:
  1. Load the agent prompt source file
  2. Interpret it as orchestration-time guidance/template
  3. Select only the prompt assets relevant to the current task from SHARED_CONTEXT_PACK
  4. Combine:
       - agent prompt source
       - selected prompt assets
       - task state
       - resource handles
       - output expectations
  5. Use the controller model to synthesize a final dispatch prompt
  6. Dispatch only that final prompt to the sub-agent

RULES:
  - MUST respect the agent prompt source as guidance for prompt synthesis
  - MUST inject all required instruction context before dispatch
  - MUST keep non-prompt resource inputs outside SHARED_CONTEXT_PACK
  - MUST_NOT treat the leaf agent as responsible for prompt discovery
  - MUST_NOT require deterministic slot-filling semantics
```

```text
UNIT LeafAgentExecutionBoundary

PURPOSE:
  Define the boundary between controller and dispatched sub-agent.

RULES:
  - A dispatched sub-agent MUST receive a fully materialized final prompt
  - A dispatched sub-agent MUST_NOT load workflow, skill, requirement, spec,
    or AGENTS prompt files from disk
  - A dispatched sub-agent MUST_NOT discover prompt dependencies at runtime
  - Missing instruction context is an orchestration failure, not a leaf-agent
    recovery path
```

## Shared Context Pack Schema

```json
{
  "shared_context_pack": {
    "version": "2.0",
    "session_id": "<string>",
    "workflow_ids_seen": ["<workflow-id>", "..."],
    "persisted_store": {
      "kind": "json",
      "path": "<absolute path or logical store handle>"
    },
    "prompt_assets": [
      {
        "asset_id": "<stable id>",
        "origin": "core|kit|project",
        "asset_type": "workflow|skill|requirement|spec|system|instruction|checklist|agents_doc",
        "path": "<absolute path>",
        "etag": "<sha256(path:size:mtime-or-content)>",
        "title": "<short title>",
        "tags": ["<tag>", "..."],
        "body": "<prompt text>",
        "sections": [
          {
            "section_id": "<stable section id>",
            "title": "<section title>",
            "tags": ["<tag>", "..."],
            "body": "<section text>"
          }
        ]
      }
    ]
  }
}
```

Rules:

- `body` MAY contain the whole prompt asset
- `sections` MAY provide smaller reusable slices for controller selection
- resource inputs MUST NOT be stored here

## Controller Responsibilities

The top-level controller is responsible for:

1. loading prompt assets once per session
2. persisting the pack
3. reusing or refreshing assets by `etag`
4. loading the agent prompt source for each dispatch
5. selecting only the task-relevant prompt assets
6. synthesizing the final dispatch prompt
7. dispatching the leaf agent with only the final prompt plus runtime resource
   inputs/handles as needed

### Selection Rules

When selecting prompt assets for one dispatch, the controller MUST:

- start from the active task and active workflow state
- include relevant core prompt assets
- include relevant kit prompt assets when the task requires them
- include relevant project prompt assets when configured
- avoid including unrelated prompt assets
- prefer smaller relevant sections when a full asset is unnecessary

### Kit Asset Resolution

Kit-borne instructions are prompt assets and MUST be handled the same way as
core prompt assets:

- load once into `SHARED_CONTEXT_PACK`
- mark `origin = "kit"`
- reuse them across the session
- inject only the task-relevant kit instruction subset into the final prompt

## Agent Prompt Source Rules

Agent markdown files under `skills/studio/agents/*.md` are orchestration-time
prompt sources.

Rules:

- they MUST be readable by the controller
- they MUST NOT be treated as self-bootstrap contracts for the leaf agent
- they MAY describe methodology, boundaries, output shapes, escalation rules,
  and prompt-composition hints in freeform prompt language
- they SHOULD avoid telling the leaf agent to load prompt assets itself
- they MAY still mention required instruction surfaces as orchestration hints,
  but not as a runtime self-load protocol

## Registration Model

`skills/studio/agents.toml` is host-registration metadata only.

It MAY define:

- description
- mode
- isolation
- model/provider hints
- role/target hints
- reasoning/context-window hints

It MUST NOT be the source of truth for prompt contracts.

Generated host descriptions SHOULD instruct the host/controller to:

1. load the agent prompt source file
2. use it as orchestration-time guidance/template
3. synthesize the final dispatch prompt with shared-context assets
4. dispatch only the synthesized prompt

## Validation

### Pre-Dispatch Validation

Before dispatch, the controller MUST verify:

- the session pack exists or has been built
- all selected assets passed `etag` validation or were refreshed
- no non-prompt resource was inserted into the pack
- the agent prompt source file exists
- the synthesized final prompt includes the necessary instruction context for
  the task

### Leaf-Agent Validation

Any leaf-agent prompt or generated host shim is invalid if it instructs the
leaf agent to:

- open `SKILL.md`
- open workflow prompt files
- open requirement/spec prompt files
- open `AGENTS.md`-like prompt assets
- resolve prompt dependencies from disk on its own

### Runtime Validation

When a dispatch fails because required instruction context is missing:

- the failure MUST be attributed to the controller
- the controller MUST repair the final prompt synthesis path
- the system MUST NOT fall back to leaf-agent prompt-file loading

## Forbidden Patterns

The following patterns are forbidden for dispatched leaf agents:

- `Open and follow .../SKILL.md`
- `Open and follow .../workflows/...`
- `Open and follow .../requirements/...`
- `Open and follow .../architecture/specs/...`
- any instruction that tells the sub-agent to resolve prompt dependencies from
  disk directly

These patterns remain valid only for the top-level controller or another
explicitly designated controller-owned prompt-loading layer.

## Failure Handling

If the controller cannot produce a valid final prompt:

- it MUST fail closed before dispatch
- it MUST report which prompt asset or synthesis step is missing
- it MUST NOT silently degrade to direct prompt-file loading by the leaf agent

## Migration Guidance

To migrate existing Studio prompts to this model:

1. keep `skills/studio/agents/*.md` as orchestration-time prompt sources
2. remove embedded prompt-context contract blocks from agent prompt files
3. remove prompt-contract fields such as `requires_shared_context_pack` from
   `agents.toml`
4. move host-generated descriptions to the new “load prompt source and
   synthesize final prompt” wording
5. update workflow/skill docs so they describe controller-owned synthesis
   rather than leaf-agent prompt-context contracts

## References

- `{cf-studio-path}/.core/skills/studio/SKILL.md`
- `{cf-studio-path}/.core/skills/studio/protocol.md`
- `{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md`
