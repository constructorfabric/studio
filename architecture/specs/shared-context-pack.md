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
- [Operational Contract](#operational-contract)
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
- [Controller Responsibilities](#controller-responsibilities)
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
stores them as structured JSON, and lets a dispatching controller provide each
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
- Make the dispatching controller responsible for prompt asset selection and
  slicing
- Preserve task-specific resource loading for non-prompt files
- Make prompt-context validation deterministic and auditable

## Operational Contract

```text
UNIT SharedContextPackControllerLifecycle

PURPOSE:
  Make controller-owned pack reuse, refresh, and dispatch preparation explicit.

STATE:
  SHARED_CONTEXT_PACK_STATUS: absent | current | stale
    default: absent

DO:
  IF session pack does not exist:
    SET SHARED_CONTEXT_PACK_STATUS = absent
  ELSE IF any reused asset fails `etag` revalidation:
    SET SHARED_CONTEXT_PACK_STATUS = stale
  ELSE:
    SET SHARED_CONTEXT_PACK_STATUS = current

  IF SHARED_CONTEXT_PACK_STATUS == absent:
    REQUIRE controller loads the required prompt assets from disk exactly once
    SET SHARED_CONTEXT_PACK_STATUS = current
  ELSE IF SHARED_CONTEXT_PACK_STATUS == stale:
    REQUIRE controller refreshes or replaces stale assets before dispatch
    SET SHARED_CONTEXT_PACK_STATUS = current

RULES:
  - MUST keep prompt-asset loading controller-owned
  - MUST reuse current session-pack assets before loading new ones
  - MUST_NOT rebuild the entire pack for every workflow run by default
```

```text
UNIT PromptContextViewContract

PURPOSE:
  Define what every dispatch-ready prompt context view must contain.

DO:
  REQUIRE controller reads the agent's `prompt_context_requirements`
  REQUIRE controller selects the smallest prompt-asset subset that satisfies
    those requirements
  REQUIRE controller passes executable prompt text and provenance metadata in
    `prompt_context_view`

RULES:
  - MUST include all required assets
  - MUST include only assets needed for the current dispatch
  - MUST treat `asset_refs` as audit metadata, not as a substitute for prompt
    text
```

```text
UNIT SharedContextPackValidation

PURPOSE:
  Define the fail-closed validation boundary before dispatch.

DO:
  REQUIRE every dispatched agent declares `prompt_context_requirements`
  REQUIRE every reused asset for the dispatch has passed `etag` revalidation
  REQUIRE every selected asset is of an allowed type and origin
  REQUIRE no non-prompt resource has entered the shared context pack

ON_ERROR:
  missing_required_prompt_context ->
    EMIT "Missing required prompt context for dispatch"
    RETURN blocker

  stale_asset_not_refreshed ->
    EMIT "Stale prompt asset was not refreshed before dispatch"
    RETURN blocker
```

```text
UNIT PromptConsumerRules

PURPOSE:
  Express the non-negotiable rules for prompt-consuming sub-agents.

RULES:
  - MUST consume prompt and instruction context exclusively via
    `prompt_context_view`
  - MUST treat missing required prompt context as an orchestration error
  - MUST_NOT reload prompt assets from disk
  - MUST_NOT silently degrade from missing prompt context to direct prompt-file
    reads
```

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

If a file mixes prompt content and non-prompt content, the dispatching
controller MUST
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
- The dispatching controller MUST reuse the existing session pack before
  loading any new prompt asset
- Before reusing an existing asset, the dispatching controller MUST revalidate
  the recorded `etag` against the current on-disk prompt asset state
- If revalidation shows an asset is stale, the dispatching controller MUST
  refresh or replace that asset in the session pack before deriving any
  `prompt_context_view` that depends on it
- The dispatching controller MAY extend the session pack with newly required
  prompt assets discovered later in the session
- The dispatching controller MUST NOT rebuild the entire pack for each
  workflow run by default
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
- Reuse of a stored asset MUST be preceded by `etag` revalidation against the
  current source state before that asset may contribute to
  `prompt_context_view`
- `scope` MUST describe where the asset is valid or intended to apply
- `session_id` MUST be stable for the current chat session
- `workflow_ids_seen` SHOULD accumulate workflow names or identifiers that have
  already reused or extended the pack during the session
- The session pack MUST NOT store singular per-dispatch fields such as
  `task_kind`, `rules_mode`, or other one-dispatch-only controller state.
  Those inputs belong to dispatch-time selection and validation, not the
  session registry itself.

The pack MAY contain full asset bodies plus extracted sections. The dispatching
controller chooses whether an agent receives whole assets or named sections via
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

Before dispatch, the dispatching controller MUST derive an agent-specific
`prompt_context_view` from the shared context pack.

```json
{
  "prompt_context_view": {
    "agent_id": "<string>",
    "assets": [
      {
        "asset_id": "<stable asset id>",
        "asset_type": "<workflow|skill|requirement|checklist|rule|system|instruction>",
        "origin": "<core|kit|project>",
        "kit_id": "<string|null>",
        "path": "<source path recorded for provenance>",
        "etag": "<deterministic freshness token>",
        "tags": ["<tag>", "..."],
        "body": "<full prompt text used when whole-asset delivery is selected>",
        "sections": [
          {
            "section_id": "layers-1-10",
            "title": "Layers 1-10",
            "tags": ["<tag>", "..."],
            "body": "<section text supplied to the agent>"
          }
        ]
      }
    ],
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
- Each delivered asset MUST preserve provenance metadata from the session pack,
  including `asset_id`, `origin`, `kit_id`, `path`, `etag`, and applicable
  asset/section tags
- It MUST include executable prompt text, either as whole-asset `body` content
  or as populated `sections[].body` slices; references alone are not enough
- The dispatching controller MAY pass full assets or section-restricted slices
- The agent MUST treat `prompt_context_view` as its sole prompt/instruction
  source
- `asset_refs` remain an audit/provenance index and do not replace the
  executable prompt text carried in `assets`

---

## Controller Responsibilities

### Loading Rule

A dispatching controller is the primary component allowed to load prompt assets
from disk for sub-agent use during a chat session. A dedicated
shared-context-pack builder or another explicitly designated top-level runtime
controller may also load prompt assets, but only to populate or extend the same
session pack for controller-managed dispatches.

The dispatching controller MUST:

1. resolve current task context
2. check whether a session-scoped shared context pack already exists
3. revalidate the `etag` of matching assets already present in that pack
4. reuse only assets whose revalidated `etag` still matches current source state
5. refresh or replace stale assets in the pack before any downstream selection
6. discover only the missing core prompt assets
7. discover only the missing kit prompt assets
8. load each newly required prompt asset once
9. extend `SHARED_CONTEXT_PACK`
10. derive one `prompt_context_view` per sub-agent dispatch

### Selection Algorithm

For each sub-agent dispatch, the dispatching controller MUST:

1. read the agent's `prompt_context_requirements`
2. gather all matching assets already present in the session shared context pack
3. revalidate the gathered assets by recomputing or otherwise checking their
   current `etag` against the source of record
4. refresh or replace any gathered asset whose `etag` no longer matches before
   it is eligible for selection
5. gather matching core, kit, and project assets from the session pack after
   freshness revalidation
6. filter by:
   - workflow/task kind
   - methodology
   - target type
   - rules mode
   - active kit set
   - explicit `required_when` conditions
7. build the smallest prompt context view that satisfies the declared
   requirements
8. if a required prompt asset is absent from the session pack, load and append
   it before dispatch
9. fail dispatch if any required prompt asset is still missing after resolution

### Kit Asset Resolution

Kits may contribute their own prompt assets. These assets MUST be treated as
first-class prompt assets, not as ad hoc disk reads inside sub-agents.

When kits contribute prompt assets relevant to the current task, the
dispatching controller MUST:

- load those assets once into the session `SHARED_CONTEXT_PACK`
- mark them with `origin = "kit"`
- set `kit_id` to the active kit identifier
- include them in `prompt_context_view` only when the agent declaration and
  task context require them

The dispatching controller MUST NOT pass unrelated kit prompt assets to an
agent.

### Project Prompt Surface Resolution

Project-local prompt surfaces such as `.github/prompts/**`,
`.claude/agents/**`, `.claude/skills/**`, `.cursor/agents/**`,
`.cursor/commands/**`, and `.codex/agents/**` are valid prompt-asset families
when they instruct agent behavior. This classification is content-based rather
than extension-based; instruction-bearing Codex agent surfaces remain project
prompt assets regardless of whether they are `.md`, `.toml`, or another
project-local authoring format.

Generated plan-phase outputs such as `.bootstrap/.plans/**/out/*.md` are also
classified by content and usage, not by path alone. When a generated out-phase
document is later followed as an executable instruction contract, rewrite
policy, validation rule set, or prompt surface, it is a prompt asset. When it
is only a deliverable, planning note, analysis target, or other task content,
it remains a runtime task resource.

When those surfaces are used as instructions, a dispatching controller,
dedicated shared-context-pack builder, or top-level runtime controller MAY load
them from disk to populate the session pack. Prompt-consuming sub-agents MUST
receive the needed instruction text only through `prompt_context_view` and MUST
NOT reopen those files directly.

---

## Sub-Agent Contract Rules

All Studio sub-agents that consume prompt context MUST follow these rules:

- MUST consume prompt and instruction context exclusively via
  `prompt_context_view`
- MUST NOT load prompt assets from filesystem directly
- MUST NOT instruct themselves to open `SKILL.md`, `workflows/*.md`,
  `requirements/*.md`, `AGENTS.md`, `.github/prompts/**/*.md`,
  `.claude/agents/**/*.md`, `.claude/skills/**/SKILL.md`,
  `.cursor/agents/**/*.md`, `.cursor/commands/**/*.md`,
  `.codex/agents/**`, generated out-phase prompt contracts under
  `.bootstrap/.plans/**/out/*.md`, or kit prompt files directly when those
  files are being used as instructions
- MUST treat missing required prompt context as an orchestration error
- MAY still read non-prompt resource inputs such as target files, code, or
  artifact documents according to their task contract

This creates a hard separation:

- prompt assets -> shared context pack
- task resources -> ordinary agent inputs

---

## Validation

### Pre-Dispatch Validation

Before dispatching a sub-agent, the dispatching controller MUST validate:

- the agent declares `prompt_context_requirements`
- the shared context pack exists
- all required prompt assets have been resolved
- every reused asset required for this dispatch has passed `etag` revalidation
- any asset found stale during revalidation has been refreshed or replaced in
  the session pack before selection
- every resolved asset is of allowed type and allowed origin
- no required asset is missing
- no non-prompt resource has been inserted into the shared context pack

If any pre-dispatch validation fails, the dispatching controller MUST stop before
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

These patterns are allowed only for a dispatching controller, a dedicated
shared-context-pack builder, or another explicitly designated top-level runtime
controller.

### Runtime Validation

At runtime, the dispatching controller SHOULD log:

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
- `Open and follow .github/prompts/...`
- `Open and follow .claude/agents/...`
- `Open and follow .claude/skills/.../SKILL.md`
- `Open and follow .cursor/agents/...`
- `Open and follow .cursor/commands/...`
- `Open and follow .codex/agents/...`
- `Open and follow .bootstrap/.plans/.../out/...` when that out-phase file is a
  later-phase instruction contract or rewrite rule
- `Open and follow {KITS_PATH}/...` for prompt assets
- any equivalent imperative telling the agent to load prompt instructions from
  disk

Allowed exception:

- the dispatching controller
- a dedicated shared-context-pack builder
- another explicitly designated top-level runtime controller whose role is
  prompt asset discovery and pack construction

Reading non-prompt task resources remains allowed and is outside this forbidden
set.

---

## Failure Handling

If the shared context pack cannot satisfy an agent's required prompt assets, the
dispatching controller MUST NOT silently degrade to direct prompt file reads.

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
    "assets": [
      {
        "asset_id": "prompt-engineering",
        "asset_type": "requirement",
        "origin": "core",
        "kit_id": null,
        "path": "/repo/requirements/prompt-engineering.md",
        "etag": "sha256:aaa",
        "tags": ["prompt-review", "methodology"],
        "body": "",
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
        "asset_id": "agent-compliance",
        "asset_type": "requirement",
        "origin": "core",
        "kit_id": null,
        "path": "/repo/requirements/agent-compliance.md",
        "etag": "sha256:ccc",
        "tags": ["agent-compliance"],
        "body": "",
        "sections": [
          {
            "section_id": "ap-001-008",
            "title": "Critical failures",
            "tags": ["critical-failures"],
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
        "tags": ["kit-rules", "validation"],
        "body": "<full text>",
        "sections": []
      }
    ],
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
2. introduce a shared-context-pack builder in dispatching-controller workflows
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
- only a dispatching controller, a dedicated shared-context-pack builder, or
  another explicitly designated top-level runtime controller may load prompt
  assets from disk
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
