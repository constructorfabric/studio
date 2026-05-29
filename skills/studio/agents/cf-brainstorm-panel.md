---
description: Invoke in single-agent panel mode. Controller uses this file to generate one final prompt that renders the full brainstorm round envelope for the whole panel.
---

# Brainstorm Panel Dispatch Generator

This file is for the controller, not for direct sub-agent prompt loading.

## Generator Contract

The controller MUST generate a final dispatch prompt with these sections in order:
1. execution boundary
2. task statement
3. frozen input payload
4. protocol and render rules
5. output contract
6. invariants
7. completion gate
8. final emit instruction

The controller MUST:
- state that the sub-agent executes only the supplied final prompt
- forbid opening AGENTS.md, SKILL.md, workflows, requirements, specs, or kit prompt files from disk
- inject only task-relevant instruction context already resolved from `SHARED_CONTEXT_PACK`
- provide the frozen input payload below as one JSON block
- restate `mode`, `round_number`, `panel_mode=true`, and `protocol`
- preserve the output contract, row shapes, invariants, and completion gate verbatim or near-verbatim
- end with:
  `Return JSON only. No markdown, no preamble, no trailing commentary.`

The controller MUST NOT:
- translate the envelope schema into a loose bullet summary when the canonical schema can be carried forward directly
- add output fields, block kinds, counters, wrappers, or enums absent from this file
- remove or rename required fields from this file

## Frozen Input Payload

```json
{
  "panel": [
    {
      "id": "E1",
      "persona": "...",
      "focus": ["...", "..."],
      "rationale": "..."
    }
  ],
  "topic": {
    "id": "T1",
    "text": "...",
    "section": "<section name or null>"
  },
  "state": {
    "kind": "<KIND or null>",
    "rules_loaded": true,
    "kit_rules_path": "<path or null>",
    "template_path": "<path or null>",
    "panel": ["..."],
    "decisions": {
      "<key>": "<value>"
    },
    "topic_history": ["T0"],
    "rounds": [
      {
        "n": 1,
        "kind": "topic",
        "topic": {}
      }
    ],
    "open_questions": ["..."],
    "BRAINSTORM_MAX_ROUNDS": "<integer>",
    "round_count": "<integer>"
  },
  "resource_context": {
    "exploration_status": "sufficient|partial|insufficient",
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
  },
  "round_contributions": [
    {
      "persona_id": "E1",
      "relevant": true,
      "reason": "<when relevant=false>",
      "questions": [
        {
          "id": "<E1Q1>",
          "decision_key": "<key>",
          "text": "...",
          "proposed_default": "...",
          "rationale": "..."
        }
      ],
      "critique": "<paragraph or empty>",
      "next_topic_proposal": {
        "text": "...",
        "why": "..."
      }
    }
  ],
  "mode": "topic|challenge",
  "round_number": "<integer>",
  "protocol": "independent-then-critique|single-pass",
  "challenged_decisions": {
    "<key>": "<value>"
  },
  "repair_feedback": {
    "mode": "topic|challenge",
    "panel_mode": "fan-out|single-agent",
    "protocol": "independent-then-critique|single-pass|null",
    "violations": [
      {
        "invariant_id": "I3..I12 or G1..G5",
        "error_code": "E_*",
        "detail": "..."
      }
    ],
    "prior_contributions": [
      {
        "persona_id": "E1",
        "relevant": true,
        "reason": "<when relevant=false>",
        "questions": [
          {
            "id": "...",
            "decision_key": "...",
            "text": "...",
            "proposed_default": "...",
            "rationale": "..."
          }
        ],
        "critique": "<paragraph or empty>",
        "next_topic_proposal": {
          "text": "...",
          "why": "..."
        }
      }
    ]
  }
}
```

## Protocol And Render Rules

```text
UNIT PanelRenderRules

RULES:
  - panel order is frozen; MUST follow input order exactly
  - `protocol` is frozen for the session
  - `repair_feedback`, when present, MUST be applied; violating rows from prior_contributions MUST_NOT be re-emitted unchanged
  - The panel agent emits only an envelope; it MUST_NOT mutate orchestrator state
  - Use resource_context for project-specific architecture/code/artifact claims
  - MUST_NOT invent project facts absent from resource_context
  - MAY inspect only non-prompt resource paths explicitly listed in
    resource_context.resources when the final dispatch prompt grants resource
    reads
  - IF resource_context.exploration_status == "insufficient" OR a persona has
    unresolved missing_context:
      that persona's independent row MUST ask for the missing information
      instead of proposing a substantive architecture decision
      proposed_default MUST start with "Please provide: "
      rationale MUST explain why the missing context is required

INDEPENDENT-THEN-CRITIQUE:
  - blocks length MUST be exactly 2
  - block[0].kind = "independent"
  - block[1].kind = "critique"
  - independent block contains one row per emitted question in panel order
  - critique block contains one row per persona in panel order

SINGLE-PASS:
  - blocks length MUST be exactly 1
  - block[0].kind = "independent"
  - only primary persona emits rows

ROW SHAPES:
  - topic independent row:
      persona_id
      question_id
      decision_key
      text
      proposed_default
      rationale
      stance = "none"
  - challenge independent row:
      persona_id
      question_id
      decision_key
      text
      proposed_default
      rationale
      stance = "agree|partial|reject"
      delta required only when stance == "partial"
  - critique row:
      persona_id
      critique
```

## Output Contract

Success envelope:

```json
{
  "attempt": 1,
  "block_count": 2,
  "blocks": [
    {
      "kind": "independent",
      "row_count": 0,
      "rows": []
    },
    {
      "kind": "critique",
      "row_count": 0,
      "rows": []
    }
  ],
  "challenged_decisions": null,
  "envelope_version": "1",
  "panel_mode": true,
  "protocol": "independent-then-critique",
  "round_index": 1
}
```

Error envelope:

```json
{
  "error": "<ERROR_CODE>",
  "reason": "<one-sentence explanation>",
  "guard": "<G3-G5 or none>",
  "invariant": "<I1-I13 or none>",
  "attempt": 1,
  "round_index": 1
}
```

## Invariants

```text
UNIT PanelInvariants

I1  envelope_version MUST be string "1"
I2  protocol MUST be "independent-then-critique" or "single-pass"
I3  round_index MUST be integer >= 0
I4  attempt MUST be integer >= 1
I5  panel_mode MUST be boolean true
I6  blocks MUST be:
      exactly 2 for independent-then-critique
      exactly 1 for single-pass
I7  each block.row_count MUST equal len(block.rows)
    each block.kind MUST be "independent" or "critique"
I8  topic-mode independent rows MUST have stance "none" or omit stance
I9  challenge-mode independent rows MUST use stance in {agree, partial, reject}
    delta MUST be present and non-empty only when stance == "partial"
I10 topic-mode independent decision_key values MUST be unique across the independent block
I11 challenge-mode independent decision_key values MUST be keys from challenged_decisions
I12 every persona_id referenced in the envelope MUST exist in panel
I13 when context is insufficient for a persona, its proposed_default MUST be a
    concrete "Please provide: ..." request for missing context, not an invented
    project-specific decision
```

## Completion Gate

```text
UNIT PanelCompletionGate

RULES:
  - MUST satisfy the protocol/render rules above
  - MUST satisfy invariants I1-I13 above
  - MUST render deterministic JSON only
  - MUST use sorted keys and LF line endings
  - MUST emit no markdown, no prose, no commentary outside the JSON object
  - MUST satisfy the SKILL.md invariant
```
