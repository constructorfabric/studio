---
studio: true
type: spec
name: Shared Context Pack Specification
version: 1.0
purpose: Define how Constructor Studio loads prompt and instruction assets once per chat session, composes a shared context pack, and supplies agent-specific prompt context views to sub-agents without allowing direct prompt reloads
drivers:
  - cpt-studio-fr-core-workflows
  - cpt-studio-fr-core-config
---

# Shared Context Pack Specification

<!-- toc -->

- [Overview](#overview)
- [Goals](#goals)
- [Non-Goals](#non-goals)
- [Core Terms](#core-terms)
- [Scope Boundary](#scope-boundary)
  - [Included in Shared Context Pack](#included-in-shared-context-pack)
  - [Excluded from Shared Context Pack](#excluded-from-shared-context-pack)
- [Asset Origins](#asset-origins)
- [Lifetime and Scope](#lifetime-and-scope)
- [Shared Context Pack Schema](#shared-context-pack-schema)
- [Prompt Context Requirements](#prompt-context-requirements)
- [Prompt Context View](#prompt-context-view)
- [Orchestrator Responsibilities](#orchestrator-responsibilities)
  - [Loading Rule](#loading-rule)
  - [Selection Algorithm](#selection-algorithm)
  - [Kit Asset Resolution](#kit-asset-resolution)
- [Sub-Agent Contract Rules](#sub-agent-contract-rules)
- [Validation](#validation)
  - [Pre-Dispatch Validation](#pre-dispatch-validation)
  - [Agent Contract Validation](#agent-contract-validation)
  - [Runtime Validation](#runtime-validation)
- [Forbidden Patterns](#forbidden-patterns)
- [Failure Handling](#failure-handling)
- [Examples](#examples)
  - [Shared Context Pack Example](#shared-context-pack-example)
  - [Agent Declaration Example](#agent-declaration-example)
  - [Prompt Context View Example](#prompt-context-view-example)
- [Migration Guidance](#migration-guidance)
- [References](#references)

<!-- /toc -->

---

## Overview

Constructor Studio workflows load a large amount of agent-facing prompt
material: workflow instructions, skill contracts, requirements, checklists,
system prompts, and kit-provided prompt assets. Historically, this material has
been reloaded by multiple sub-agents in the same workflow run, causing context
duplication, unpredictable drift between agents, and unnecessary token cost.

This specification defines a `SHARED_CONTEXT_PACK` model that loads all
task-relevant prompt and instruction assets exactly once per chat session,
stores them as structured JSON, and lets the orchestrator provide each
sub-agent with a minimal `prompt_context_view` derived from that pack.

The pack is strictly limited to **agent operating context**. It does not
contain the user artifact, source code, documentation being analyzed, or other
non-prompt resources.

---

## Goals

- Load prompt and instruction assets once per chat session
- Prevent sub-agents from reloading prompt assets from disk
- Support both core Studio prompt assets and kit-provided prompt assets
- Let each Studio agent declare what prompt context it requires
- Make the orchestrator responsible for prompt asset selection and slicing
- Preserve task-specific resource loading for non-prompt files
- Make prompt-context validation deterministic and auditable

---

## Non-Goals

- This spec does not define how source code, artifacts, or documentation are
  analyzed as task resources
- This spec does not replace resource-specific chunking or partial-checkpoint
  logic for non-prompt files
- This spec does not require all assets to be inlined into every agent; agents
  receive only the prompt context they need
- This spec does not define business logic for kit semantics beyond prompt asset
  selection and transport

---

## Core Terms

**Prompt asset**: any file or section whose primary purpose is to instruct an
agent how to behave.

**Shared context pack**: the JSON object holding all prompt assets loaded once
for the current chat session.

**Prompt context requirements**: an agent-declared contract describing which
prompt assets or prompt-asset classes the agent requires.

**Prompt context view**: the agent-specific subset of the shared context pack
supplied to one sub-agent dispatch.

**Resource input**: non-prompt task data such as code files, artifact files,
design docs, or cross-reference documents. Resource inputs are not stored in
the shared context pack.

**Core asset**: a prompt asset originating from Constructor Studio core files.

**Kit asset**: a prompt asset contributed by the active kit and relevant to the
current task.

---

## Scope Boundary

### Included in Shared Context Pack

The shared context pack MAY include only prompt and instruction assets such as:

- workflow prompts
- skill prompts
- system prompts
- methodology documents
- checklists used as agent instructions
- rules used as agent instructions
- `AGENTS.md` or equivalent instruction documents
- kit-specific rules, checklists, guidance, and validation instructions
- any other file whose purpose is to instruct agent behavior

### Excluded from Shared Context Pack

The shared context pack MUST NOT contain non-prompt task resources such as:

- source code
- target artifact files
- PRDs, ADRs, DESIGN docs, or markdown artifacts when they are the subject of
  work rather than agent instructions
- examples used as content references rather than prompt instructions
- project documentation
- PR diffs
- user-provided input artifacts
- any resource whose primary purpose is domain/task content rather than agent
  instruction

If a file mixes prompt content and non-prompt content, the orchestrator MUST
extract only the prompt-bearing sections into the shared context pack and keep
the original file in resource-input handling.

---

## Asset Origins

Every prompt asset in the shared context pack MUST declare an `origin`:

- `core` -> Constructor Studio core prompt assets
- `kit` -> task-relevant prompt assets contributed by an active kit
- `project` -> project-level prompt assets such as configured sysprompts

This specification requires support for `core` and `kit`. `project` is allowed
for future-proofing and local extension compatibility.

---

## Lifetime and Scope

The shared context pack is **session-scoped**, not workflow-run-scoped.

Rules:

- A chat session has exactly one logical `SHARED_CONTEXT_PACK`
- Prompt assets loaded during one workflow run in the session MUST remain
  available to later workflow runs in the same session
- The orchestrator MUST reuse the existing session pack before loading any new
  prompt asset
- The orchestrator MAY extend the session pack with newly required prompt
  assets discovered later in the session
- The orchestrator MUST NOT rebuild the entire pack for each workflow run by
  default
- Asset freshness MUST be checked by `etag`, not by workflow-run boundaries

This means the pack behaves as a session-wide prompt context registry with
incremental enrichment, rather than as a per-run temporary bundle.

---

## Shared Context Pack Schema

The canonical transport shape is JSON.

```json
{
  "shared_context_pack": {
    "version": "1.0",
    "session_id": "<string>",
    "workflow_ids_seen": ["<string>", "..."],
    "task_kind": "<generate|analyze|plan|brainstorm|explain|workspace|other>",
    "rules_mode": "<STRICT|RELAXED>",
    "assets": [
      {
        "asset_id": "<stable asset id>",
        "asset_type": "<workflow|skill|requirement|checklist|rule|system|instruction>",
        "origin": "<core|kit|project>",
        "kit_id": "<string|null>",
        "path": "<absolute path>",
        "etag": "<sha256(path:byte_size:line_count)>",
        "title": "<short title>",
        "tags": ["<tag>", "..."],
        "scope": ["<generate>", "<analyze>", "<prompt-review>", "..."],
        "body": "<full prompt text>",
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

Schema rules:

- `body` MUST contain only prompt/instruction content
- `sections[]` MAY be omitted when section-level slicing is not available
- `kit_id` MUST be non-null only when `origin == "kit"`
- `etag` MUST be deterministic for a given file state
- `scope` MUST describe where the asset is valid or intended to apply
- `session_id` MUST be stable for the current chat session
- `workflow_ids_seen` SHOULD accumulate workflow names or identifiers that have
  already reused or extended the pack during the session

The pack MAY contain full asset bodies plus extracted sections. The orchestrator
chooses whether an agent receives whole assets or named sections via
`prompt_context_view`.

---

## Prompt Context Requirements

Every Studio sub-agent that consumes prompt or instruction assets MUST declare a
`prompt_context_requirements` contract.

```json
{
  "agent_id": "<string>",
  "prompt_context_requirements": {
    "requires_shared_context_pack": true,
    "required_assets": [
      {
        "asset_key": "<semantic name>",
        "accepted_origins": ["core", "kit", "project"],
        "accepted_types": ["requirement", "checklist", "workflow"],
        "match_tags": ["<tag>", "..."],
        "section_tags": ["<tag>", "..."],
        "required_when": "<condition or null>"
      }
    ],
    "optional_assets": [
      {
        "asset_key": "<semantic name>",
        "accepted_origins": ["kit"],
        "accepted_types": ["rule", "checklist"],
        "match_tags": ["kit-rules", "validation"],
        "section_tags": [],
        "required_when": null
      }
    ]
  }
}
```

Rules:

- `requires_shared_context_pack` MUST be `true` for any sub-agent that uses
  prompt assets
- `required_assets` MUST list every prompt asset class necessary to execute the
  contract safely
- `optional_assets` MAY be used for kit augmentations or task-specific add-ons
- `required_when` MAY gate an asset on task mode or methodology
- Agents MUST declare prompt needs semantically, not as imperative file-open
  instructions

Example semantic keys:

- `agent_compliance`
- `prompt_engineering_methodology`
- `consistency_checklist`
- `code_checklist`
- `kit_validation_rules`
- `language_complexity_rules`

---

## Prompt Context View

Before dispatch, the orchestrator MUST derive an agent-specific
`prompt_context_view` from the shared context pack.

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

- `prompt_context_view` MUST contain all required assets declared by the agent
- It MUST contain only the prompt assets needed by that agent for the current
  task
- The orchestrator MAY pass full assets or section-restricted references
- The agent MUST treat `prompt_context_view` as its sole prompt/instruction
  source

---

## Orchestrator Responsibilities

### Loading Rule

The orchestrator is the only component allowed to load prompt assets from disk
for sub-agent use during a chat session.

The orchestrator MUST:

1. resolve current task context
2. check whether a session-scoped shared context pack already exists
3. reuse matching assets already present in that pack
4. discover only the missing core prompt assets
5. discover only the missing kit prompt assets
6. load each newly required prompt asset once
7. extend `SHARED_CONTEXT_PACK`
8. derive one `prompt_context_view` per sub-agent dispatch

### Selection Algorithm

For each sub-agent dispatch, the orchestrator MUST:

1. read the agent's `prompt_context_requirements`
2. gather all matching core assets from the session shared context pack
3. gather all matching kit assets from the session shared context pack when applicable
4. filter by:
   - workflow/task kind
   - methodology
   - target type
   - rules mode
   - active kit set
   - explicit `required_when` conditions
5. build the smallest prompt context view that satisfies the declared
   requirements
6. if a required prompt asset is absent from the session pack, load and append
   it before dispatch
7. fail dispatch if any required prompt asset is still missing after resolution

### Kit Asset Resolution

Kits may contribute their own prompt assets. These assets MUST be treated as
first-class prompt assets, not as ad hoc disk reads inside sub-agents.

When kits contribute prompt assets relevant to the current task, the
orchestrator MUST:

- load those assets once into the session `SHARED_CONTEXT_PACK`
- mark them with `origin = "kit"`
- set `kit_id` to the active kit identifier
- include them in `prompt_context_view` only when the agent declaration and
  task context require them

The orchestrator MUST NOT pass unrelated kit prompt assets to an agent.

---

## Sub-Agent Contract Rules

All Studio sub-agents that consume prompt context MUST follow these rules:

- MUST consume prompt and instruction context exclusively via
  `prompt_context_view`
- MUST NOT load prompt assets from filesystem directly
- MUST NOT instruct themselves to open `SKILL.md`, `workflows/*.md`,
  `requirements/*.md`, `AGENTS.md`, or kit prompt files directly
- MUST treat missing required prompt context as an orchestration error
- MAY still read non-prompt resource inputs such as target files, code, or
  artifact documents according to their task contract

This creates a hard separation:

- prompt assets -> shared context pack
- task resources -> ordinary agent inputs

---

## Validation

### Pre-Dispatch Validation

Before dispatching a sub-agent, the orchestrator MUST validate:

- the agent declares `prompt_context_requirements`
- the shared context pack exists
- all required prompt assets have been resolved
- every resolved asset is of allowed type and allowed origin
- no required asset is missing
- no non-prompt resource has been inserted into the shared context pack

If any pre-dispatch validation fails, the orchestrator MUST stop before
dispatch and surface a deterministic error.

### Agent Contract Validation

Studio agent prompt files MUST be validated for compatibility with this spec.

An agent contract is invalid if it contains direct prompt-loading instructions
for assets that should come from `prompt_context_view`.

Validator checks MUST detect:

- direct `Open and follow ...SKILL.md`
- direct `Open and follow ...workflows/...`
- direct `Open and follow ...requirements/...`
- direct `Open and follow ...AGENTS.md`
- imperative self-bootstrap for prompt assets

These patterns are allowed only for the orchestrator or another explicitly
designated prompt-pack builder.

### Runtime Validation

At runtime, the orchestrator SHOULD log:

- which prompt assets entered the session shared context pack
- which prompt assets were selected for each agent
- which kit assets were included and why
- whether any required asset resolution failed

Runtime logging MUST make it possible to audit:

- prompt assets loaded once per session
- prompt assets passed to each agent
- absence of direct prompt-file reloads in sub-agents

---

## Forbidden Patterns

The following patterns are forbidden in prompt-consuming sub-agents:

- `Open and follow {cf-studio-path}/.core/skills/studio/SKILL.md`
- `Open and follow {cf-studio-path}/.core/workflows/...`
- `Open and follow {cf-studio-path}/.core/requirements/...`
- `Open and follow {cf-studio-path}/config/AGENTS.md`
- `Open and follow {cf-studio-path}/config/sysprompts/...`
- `Open and follow {KITS_PATH}/...` for prompt assets
- any equivalent imperative telling the agent to load prompt instructions from
  disk

Allowed exception:

- the workflow orchestrator
- a dedicated shared-context-pack builder
- another explicitly designated top-level controller whose role is prompt asset
  discovery and pack construction

Reading non-prompt task resources remains allowed and is outside this forbidden
set.

---

## Failure Handling

If the shared context pack cannot satisfy an agent's required prompt assets, the
orchestrator MUST NOT silently degrade to direct prompt file reads.

Valid failure paths:

- stop and request missing orchestration context repair
- dispatch a composite agent only if that composite agent can still be supplied
  entirely via `prompt_context_view`
- return a partial/checkpoint state describing missing prompt context

Invalid failure path:

- "agent can just load the missing prompt file itself"

---

## Examples

### Shared Context Pack Example

```json
{
  "shared_context_pack": {
    "version": "1.0",
    "session_id": "chat-2026-05-28T12-00-00Z",
    "workflow_ids_seen": ["analyze"],
    "task_kind": "analyze",
    "rules_mode": "STRICT",
    "assets": [
      {
        "asset_id": "prompt-engineering",
        "asset_type": "requirement",
        "origin": "core",
        "kit_id": null,
        "path": "/repo/requirements/prompt-engineering.md",
        "etag": "sha256:aaa",
        "title": "Prompt Engineering Methodology",
        "tags": ["prompt-review", "methodology"],
        "scope": ["analyze", "prompt-review"],
        "body": "<full text>",
        "sections": [
          {
            "section_id": "layers-1-10",
            "title": "Layers 1-10",
            "tags": ["layers"],
            "body": "<section text>"
          }
        ]
      },
      {
        "asset_id": "sdlc-validation-rules",
        "asset_type": "rule",
        "origin": "kit",
        "kit_id": "sdlc",
        "path": "/repo/kits/sdlc/rules.md",
        "etag": "sha256:bbb",
        "title": "SDLC Validation Rules",
        "tags": ["kit-rules", "validation"],
        "scope": ["analyze", "generate"],
        "body": "<full text>",
        "sections": []
      }
    ]
  }
}
```

### Agent Declaration Example

```json
{
  "agent_id": "cf-semantic-reviewer-prompt",
  "prompt_context_requirements": {
    "requires_shared_context_pack": true,
    "required_assets": [
      {
        "asset_key": "prompt_engineering_methodology",
        "accepted_origins": ["core"],
        "accepted_types": ["requirement"],
        "match_tags": ["prompt-review", "methodology"],
        "section_tags": ["layers"],
        "required_when": null
      },
      {
        "asset_key": "agent_compliance",
        "accepted_origins": ["core"],
        "accepted_types": ["requirement"],
        "match_tags": ["agent-compliance"],
        "section_tags": [],
        "required_when": null
      }
    ],
    "optional_assets": [
      {
        "asset_key": "kit_validation_rules",
        "accepted_origins": ["kit"],
        "accepted_types": ["rule", "checklist"],
        "match_tags": ["kit-rules", "validation"],
        "section_tags": [],
        "required_when": "rules_mode == STRICT"
      }
    ]
  }
}
```

### Prompt Context View Example

```json
{
  "prompt_context_view": {
    "agent_id": "cf-semantic-reviewer-prompt",
    "asset_refs": [
      {
        "asset_id": "prompt-engineering",
        "section_ids": ["layers-1-10"]
      },
      {
        "asset_id": "agent-compliance",
        "section_ids": ["ap-001-008"]
      },
      {
        "asset_id": "sdlc-validation-rules",
        "section_ids": []
      }
    ]
  }
}
```

---

## Migration Guidance

Adopting this spec requires two complementary changes:

1. agent contracts must stop instructing direct prompt-file loading
2. orchestrators must build, retain for the chat session, and supply
   `prompt_context_view`

Recommended migration order:

1. add `prompt_context_requirements` to Studio agents
2. introduce a shared-context-pack builder in orchestrator workflows
3. update reviewer/planner/gate agents to consume `prompt_context_view`
4. add validator rules for forbidden direct prompt-loading patterns
5. remove legacy direct prompt-load instructions from sub-agent contracts

High-value early targets include prompt reviewers, bug finders, consistency
reviewers, code reviewers, and planners.

Phase 2 of the shared-context-pack migration establishes three companion
contracts that later phases must follow:

- rewrite policy:
  `.bootstrap/.plans/implement-shared-context-pack-pdsl-migration/out/phase-02-rewrite-rules.md`
- agent-context contract:
  `.bootstrap/.plans/implement-shared-context-pack-pdsl-migration/out/phase-02-agent-context-contract.md`
- path-prefix policy:
  `.bootstrap/.plans/implement-shared-context-pack-pdsl-migration/out/phase-02-path-prefix-policy.md`

Those companion contracts refine this specification with the following
requirements:

- prompt-consuming sub-agents must declare semantic
  `prompt_context_requirements` and must treat `prompt_context_view` as their
  sole prompt/instruction source
- only top-level orchestrators, dedicated shared-context-pack builders, or
  another explicitly designated top-level controller may load prompt assets
  from disk
- controller-owned imperative prompt loads must use runtime
  `{cf-studio-path}`-prefixed references when a runtime mirror exists
- requirements and specs may stay prose-first when they are reference
  material, but any executable gating behavior, state, menus, approval
  boundaries, or failure handling consumed as instructions must be made
  explicit in PDSL during migration
- missing required prompt context must stop dispatch rather than silently
  degrade into direct prompt-file reads by the target sub-agent

---

## References

- [Project Extension Specification](sysprompts.md)
- [PDSL Specification](PDSL.md)
- [Identifiers & Traceability Specification](traceability.md)
- [Phase 02 Rewrite Rules](../../.bootstrap/.plans/implement-shared-context-pack-pdsl-migration/out/phase-02-rewrite-rules.md)
- [Phase 02 Agent Context Contract](../../.bootstrap/.plans/implement-shared-context-pack-pdsl-migration/out/phase-02-agent-context-contract.md)
- [Phase 02 Path Prefix Policy](../../.bootstrap/.plans/implement-shared-context-pack-pdsl-migration/out/phase-02-path-prefix-policy.md)
