---
description: Invoke for one persona-scoped brainstorm contribution in fan-out mode. Controller uses this file to generate the final prompt for one expert in `topic` or `challenge` mode.
---

# Brainstorm Expert Dispatch Generator

This file is for the controller, not for direct sub-agent prompt loading.

## Generator Contract

The controller MUST generate a final dispatch prompt with these sections in order:
1. execution boundary
2. task statement
3. frozen input payload
4. mode rules
5. output contract
6. completion gate
7. final emit instruction

The controller MUST:
- state that the sub-agent executes only the supplied final prompt
- forbid opening AGENTS.md, SKILL.md, workflows, requirements, specs, or kit prompt files from disk
- inject only task-relevant instruction context already resolved from `SHARED_CONTEXT_PACK`
- provide the frozen input payload below as one JSON block
- restate whether `mode` is `topic` or `challenge`
- preserve output fields and mode-specific constraints verbatim or near-verbatim
- end with:
  `Return JSON only. No markdown, no preamble, no trailing commentary.`

## Frozen Input Payload

```json
{
  "persona": {
    "id": "E2",
    "persona": "Security Reviewer",
    "focus": ["auth", "data-handling"],
    "rationale": "..."
  },
  "topic": {
    "id": "T1",
    "text": "...",
    "section": "<template-section or null>"
  },
  "mode": "topic|challenge",
  "challenged_decisions": {
    "<decision-key>": "<current-value>"
  },
  "state": {
    "kind": "<KIND or null>",
    "rules_loaded": true,
    "kit_rules_path": "<path or null>",
    "template_path": "<path or null>",
    "panel": [
      {
        "id": "...",
        "persona": "...",
        "focus": ["..."],
        "rationale": "..."
      }
    ],
    "decisions": {
      "<key>": "<value>"
    },
    "topic_history": ["T0"]
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
        "persona_id": "E2",
        "needs": ["..."],
        "resource_paths": ["<path>"],
        "missing_context": ["..."]
      }
    ],
    "missing_context_questions": [
      {
        "for_persona_id": "E2",
        "question": "...",
        "why_needed": "..."
      }
    ]
  }
}
```

## Mode Rules

```text
UNIT ExpertModeRules

RULES:
  - `mode` is required
  - `challenged_decisions` MUST be non-empty when mode == "challenge"
  - `challenged_decisions` MUST be null or absent when mode == "topic"
  - WHEN mode == "challenge":
      treat challenged_decisions as authoritative for this dispatch
      MUST_NOT reread later values from state.decisions for those keys

TOPIC MODE:
  - IF persona is not relevant and another persona clearly owns the topic:
      return { "relevant": false, "reason": "<one sentence>" }
  - ELSE return 1-3 questions
  - Each question MUST include:
      id
      decision_key
      text
      proposed_default
      rationale
  - decision_key pattern:
      IF topic.section != null:
        <topic.section>:<persona.id>:<question-slug>
      ELSE:
        <topic.id>:<persona.id>:<question-slug>
  - decision_key MUST_NOT be empty
  - MUST_NOT use bare `topic.section` as the whole key
  - MAY include short critique
  - MUST include next_topic_proposal

CHALLENGE MODE:
  - IF persona is not relevant and no cross-cutting concern applies:
      return { "relevant": false, "reason": "<one sentence>" }
  - ELSE critique MUST be non-empty
  - questions length MAY be 0..3
  - Each question MUST include:
      id
      decision_key
      text
      proposed_default
      rationale
  - Every decision_key MUST already exist in challenged_decisions
  - At most one question per challenged decision key
  - next_topic_proposal MUST be null
  - If a challenged decision is already optimal from this persona's POV:
      MUST_NOT invent a counter

KIT/TEMPLATE RULES:
  - REQUIRE kit_rules_path is non-null before applying kit rules from it
  - REQUIRE template_path is non-null before applying template constraints from it
  - WHEN state.rules_loaded == true:
      MUST_NOT propose defaults that violate kit or template constraints
  - WHEN mode == "challenge" AND a current decision violates kit rules:
      SHOULD name it in critique as a high-priority target

RESOURCE CONTEXT RULES:
  - Use resource_context.summary, resources, and persona_needs when producing
    project-specific architecture/code/artifact questions
  - MAY rely on resource excerpts and summaries already present in
    resource_context
  - MUST_NOT invent project facts that are absent from resource_context
  - MUST_NOT open prompt assets from disk
  - MAY inspect only non-prompt resource paths explicitly listed in
    resource_context.resources when the final dispatch prompt grants resource
    reads
  - IF resource_context.exploration_status == "insufficient" OR this persona's
    persona_needs[].missing_context is non-empty:
      ask a concrete context-gathering question instead of a substantive
      proposal
      set proposed_default to a specific request beginning with
      "Please provide: "
      explain in rationale why that missing context is necessary
```

## Output Contract

Either:

```json
{
  "relevant": false,
  "reason": "<one-sentence>"
}
```

or:

```json
{
  "relevant": true,
  "questions": [
    {
      "id": "<persona.id>Q1",
      "decision_key": "<decision-key>",
      "text": "...",
      "proposed_default": "...",
      "rationale": "..."
    }
  ],
  "critique": "<one-paragraph or empty>",
  "next_topic_proposal": {
    "text": "...",
    "why": "..."
  }
}
```

## Completion Gate

```text
UNIT ExpertCompletionGate

RULES:
  - MUST emit exactly one of the two JSON shapes above and nothing else
  - Every question id MUST be non-empty
  - `questions[].id` values MUST be unique within the response
  - Every decision_key MUST be non-empty
  - challenge `questions[].decision_key` values MUST be unique within this response
  - WHEN relevant == true AND mode == "topic":
      questions length MUST be 1..3
  - WHEN relevant == true AND mode == "challenge":
      questions length MUST be 0..3
      critique MUST be non-empty
      critique-only challenge is valid only when no concrete counter-proposal
      should overwrite any challenged decision
      critique-only challenge MUST return relevant: true, empty questions,
      non-empty critique, and next_topic_proposal = null
      next_topic_proposal MUST be null
      each `decision_key` MUST name a key present in `challenged_decisions`
      every decision_key MUST be present in challenged_decisions
      decision_key values MUST be unique within the response
  - WHEN state.rules_loaded == true:
      proposed_default values MUST respect active kit/template constraints
  - WHEN only one of kit_rules_path/template_path is available:
      proceed with available context
  - WHEN resource_context is insufficient for a project-specific proposal:
      proposed_default MUST be a concrete "Please provide: ..." request for
      the missing context
  - MUST satisfy the SKILL.md invariant
```
