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

```pdsl
UNIT ExpertModeRules

RULES:
  - ALWAYS `mode` is required
  - ALWAYS `challenged_decisions` ALWAYS be non-empty when mode == "challenge"
  - ALWAYS `challenged_decisions` ALWAYS be null or absent when mode == "topic"
  - ALWAYS WHEN mode == "challenge":
      treat challenged_decisions as authoritative for this dispatch
      NEVER reread later values from state.decisions for those keys

- ALWAYS TOPIC MODE:
  - ALWAYS IF persona is not relevant and another persona clearly owns the topic:
      return { "relevant": false, "reason": "<one sentence>" }
  - ALWAYS ELSE return 1-3 questions
  - ALWAYS Each question ALWAYS include:
      id
      decision_key
      text
      proposed_default
      rationale
  - ALWAYS decision_key pattern:
      IF topic.section != null:
        <topic.section>:<persona.id>:<question-slug>
      ELSE:
        <topic.id>:<persona.id>:<question-slug>
  - ALWAYS decision_key NEVER be empty
  - NEVER use bare `topic.section` as the whole key
  - ALWAYS may include short critique
  - ALWAYS include next_topic_proposal

- ALWAYS CHALLENGE MODE:
  - ALWAYS IF persona is not relevant and no cross-cutting concern applies:
      return { "relevant": false, "reason": "<one sentence>" }
  - ALWAYS ELSE critique ALWAYS be non-empty
  - ALWAYS questions length may be 0..3
  - ALWAYS Each question ALWAYS include:
      id
      decision_key
      text
      proposed_default
      rationale
  - ALWAYS Every decision_key ALWAYS already exist in challenged_decisions
  - ALWAYS At most one question per challenged decision key
  - ALWAYS next_topic_proposal ALWAYS be null
  - ALWAYS If a challenged decision is already optimal from this persona's POV:
      NEVER invent a counter

- ALWAYS KIT/TEMPLATE RULES:
  - ALWAYS REQUIRE kit_rules_path is non-null before applying kit rules from it
  - ALWAYS REQUIRE template_path is non-null before applying template constraints from it
  - ALWAYS WHEN state.rules_loaded == true:
      NEVER propose defaults that violate kit or template constraints
  - ALWAYS WHEN mode == "challenge" AND a current decision violates kit rules:
      ALWAYS name it in critique as a high-priority target

- ALWAYS RESOURCE CONTEXT RULES:
  - ALWAYS Use resource_context.summary, resources, and persona_needs when producing
    project-specific architecture/code/artifact questions
  - ALWAYS may rely on resource excerpts and summaries already present in
    resource_context
  - NEVER invent project facts that are absent from resource_context
  - NEVER open prompt assets from disk
  - ALWAYS may inspect only non-prompt resource paths explicitly listed in
    resource_context.resources when the final dispatch prompt grants resource
    reads
  - ALWAYS IF resource_context.exploration_status == "insufficient" OR this persona's
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

```pdsl
UNIT ExpertCompletionGate

RULES:
  - ALWAYS emit exactly one of the two JSON shapes above and nothing else
  - ALWAYS Every question id ALWAYS be non-empty
  - ALWAYS `questions[].id` values ALWAYS be unique within the response
  - ALWAYS Every decision_key ALWAYS be non-empty
  - ALWAYS challenge `questions[].decision_key` values ALWAYS be unique within this response
  - ALWAYS WHEN relevant == true AND mode == "topic":
      questions length ALWAYS be 1..3
  - ALWAYS WHEN relevant == true AND mode == "challenge":
      questions length ALWAYS be 0..3
      critique ALWAYS be non-empty
      critique-only challenge is valid only when no concrete counter-proposal
      should overwrite any challenged decision
      critique-only challenge ALWAYS return relevant: true, empty questions,
      non-empty critique, and next_topic_proposal = null
      next_topic_proposal ALWAYS be null
      each `decision_key` ALWAYS name a key present in `challenged_decisions`
      every decision_key ALWAYS be present in challenged_decisions
      decision_key values ALWAYS be unique within the response
  - ALWAYS WHEN state.rules_loaded == true:
      proposed_default values ALWAYS respect active kit/template constraints
  - ALWAYS WHEN only one of kit_rules_path/template_path is available:
      proceed with available context
  - ALWAYS WHEN resource_context is insufficient for a project-specific proposal:
      proposed_default ALWAYS be a concrete "Please provide: ..." request for
      the missing context
  - ALWAYS satisfy the SKILL.md invariant
```
