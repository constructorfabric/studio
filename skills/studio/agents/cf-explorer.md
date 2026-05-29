---
description: Invoke when a controller needs read-only discovery of task-relevant project resources before dispatching brainstorm, generate, analyze, or planning agents.
---

# Explorer Dispatch Generator

This file is for the controller, not for direct sub-agent prompt loading.

## Generator Contract

The controller MUST generate a final dispatch prompt with these sections in order:
1. execution boundary
2. task statement
3. frozen input payload
4. discovery rules
5. output contract
6. completion gate
7. final emit instruction

The controller MUST:
- state that the sub-agent executes only the supplied final prompt
- forbid opening AGENTS.md, SKILL.md, workflows, requirements, specs, or kit prompt files from disk
- allow read-only inspection of non-prompt project resources inside `search_roots`
- keep discovered source/docs/artifacts out of `SHARED_CONTEXT_PACK`
- end with:
  `Return JSON only. No markdown, no preamble, no trailing commentary.`

## Frozen Input Payload

```json
{
  "task": "<user or parent-workflow task>",
  "intent": "standalone|brainstorm|generate|analyze|plan",
  "panel": [
    {
      "id": "E1",
      "persona": "...",
      "focus": ["..."],
      "rationale": "..."
    }
  ],
  "known_paths": ["<path>"],
  "search_roots": ["<project root or subdir>"],
  "constraints": {
    "kind": "<KIND or null>",
    "system": "<system or null>",
    "max_files": 20,
    "max_excerpt_lines_per_file": 40
  }
}
```

## Discovery Rules

```text
UNIT ExplorerDiscoveryRules

PURPOSE:
  Find resource context that a downstream agent needs to reason about the task.

DO:
  Identify information needs from:
    task
    panel personas and focus areas when panel != null
    known_paths
    constraints.kind
    constraints.system

  Search only non-prompt project resources:
    source code
    architecture docs
    architecture specs when they are the subject/resource of the task
    PRD/DESIGN/ADR/DECOMPOSITION/FEATURE artifacts
    README/docs
    tests
    config files that describe project behavior

  MUST NOT read prompt assets as resources:
    AGENTS.md
    SKILL.md
    workflows/**
    requirements/**
    skills/studio/**
    kit prompt/rules/checklist files

  For each relevant resource, return:
    path
    resource_type
    why_relevant
    suggested_slices
    summary
    confidence

  For each panel persona, return its context needs and matching resources.

RULES:
  - Prefer precise, few, high-signal resources over broad file lists
  - Include direct excerpts only when they are short and necessary
  - If no sufficient resource is found, record the missing knowledge explicitly
  - Do not invent architecture facts not supported by inspected resources
```

## Output Contract

```json
{
  "exploration_status": "sufficient|partial|insufficient",
  "task_summary": "...",
  "resource_context": {
    "summary": "...",
    "resources": [
      {
        "path": "<path>",
        "resource_type": "architecture|artifact|code|test|docs|config|other",
        "why_relevant": "...",
        "suggested_slices": [
          {
            "label": "...",
            "line_range": { "start": 1, "end": 40 },
            "summary": "...",
            "excerpt": "<short excerpt or null>"
          }
        ],
        "confidence": "high|medium|low"
      }
    ],
    "persona_needs": [
      {
        "persona_id": "E1",
        "needs": ["..."],
        "resource_paths": ["<path>"],
        "missing_context": ["..."]
      }
    ],
    "missing_context_questions": [
      {
        "for_persona_id": "E1",
        "question": "...",
        "why_needed": "..."
      }
    ]
  }
}
```

## Completion Gate

```text
UNIT ExplorerCompletionGate

RULES:
  - MUST emit exactly the output JSON object above and nothing else
  - exploration_status MUST be one of sufficient, partial, insufficient
  - resource_context.summary MUST be present
  - resources MUST contain only non-prompt project resources
  - persona_needs MUST be present when panel is non-null
  - missing_context_questions MUST be present, empty if none
  - MUST NOT claim sufficiency when persona_needs contains unresolved missing_context
```
