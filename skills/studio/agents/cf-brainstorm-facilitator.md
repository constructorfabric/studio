---
description: Invoke when opening a brainstorm session. Controller uses this file to generate one facilitator dispatch prompt that proposes a 3-6 persona panel plus a seed topic for round 1.
---

# Brainstorm Facilitator Dispatch Generator

This file is for the controller, not for direct sub-agent prompt loading.

## Generator Contract

The controller MUST generate a final dispatch prompt with these sections in order:
1. execution boundary
2. task statement
3. frozen input payload
4. methodology
5. output contract
6. completion gate
7. final emit instruction

The controller MUST:
- state that the sub-agent executes only the supplied final prompt
- forbid opening AGENTS.md, SKILL.md, workflows, requirements, specs, or kit prompt files from disk
- inject only task-relevant instruction context already resolved from `SHARED_CONTEXT_PACK`
- carry the frozen input payload, output contract, and completion gate verbatim or near-verbatim
- end with:
  `Return JSON only. No markdown, no preamble, no trailing commentary.`

## Frozen Input Payload

```json
{
  "initial_topic": "<user request summary>",
  "kind": "<KIND or null>",
  "rules_loaded": true,
  "kit_rules_path": "<path or null>",
  "template_path": "<path or null>",
  "example_path": "<path or null>",
  "project_ctx": "<short summary of relevant existing artifacts>"
}
```

## Methodology

```text
UNIT FacilitatorMethod

DO:
  WHEN rules_loaded == true AND kit_rules_path != null:
    Read kit_rules_path
  WHEN rules_loaded == true AND template_path != null:
    Read template_path
    Use its high-leverage sections to shape persona selection
  WHEN example_path != null:
    Read example_path
    Use its structure/tone/domain emphasis to refine panel and seed topic
    MUST_NOT copy example content unless already inside the user's topic

  Build proposed_panel with 3-6 personas:
    id        = unique E1..En
    persona   = short role name
    focus     = 2-3 topic-specific areas
    rationale = one sentence explaining why this persona is needed here

  Build seed_topic:
    id        = "T1"
    text      = single most load-bearing round-1 question
    section   = most relevant template section or null
    why_first = one sentence explaining why this should be first

RULES:
  - MUST_NOT create two personas with overlapping focus lists
  - SHOULD prefer template high-leverage sections when rules are loaded
  - MUST keep panel diverse rather than redundant
```

## Output Contract

```json
{
  "proposed_panel": [
    {
      "id": "E1",
      "persona": "...",
      "focus": ["...", "..."],
      "rationale": "..."
    }
  ],
  "seed_topic": {
    "id": "T1",
    "text": "...",
    "section": "<template-section or null>",
    "why_first": "..."
  }
}
```

## Completion Gate

```text
UNIT FacilitatorCompletionGate

RULES:
  - MUST emit exactly the output JSON object above and nothing else
  - proposed_panel length MUST be 3..6
  - proposed_panel[*].id values MUST be unique
  - proposed_panel[*].focus lists MUST NOT overlap materially
  - MUST have non-empty id in seed_topic
  - MUST have non-empty text in seed_topic
  - MUST have section key in seed_topic (string or null)
  - MUST have non-empty why_first in seed_topic
  - MUST satisfy the SKILL.md invariant
```
