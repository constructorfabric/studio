---
description: Invoke when opening a brainstorm session — one-shot per session. Given the initial topic plus rules.md / template / example / project context, proposes a 3-6-person expert panel (persona, focus, rationale) and a seed topic for round 1. Pure function: orchestrator collects user edits before the round loop starts.
---

<!-- toc -->

- [Inputs (dispatched-prompt contract)](#inputs-dispatched-prompt-contract)
- [Methodology](#methodology)
- [Output (return-value contract)](#output-return-value-contract)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

## Dispatch Guidance

This file is orchestration-time guidance for the controller, not a runtime
self-bootstrap contract for the dispatched sub-agent.

The controller MUST load this file, resolve the task-relevant instruction
assets from `SHARED_CONTEXT_PACK`, and synthesize a fully materialized final
dispatch prompt for this agent. The dispatched sub-agent MUST execute only that
final prompt and MUST NOT open prompt assets from disk directly.


## Inputs (dispatched-prompt contract)

```json
{
  "initial_topic": "<user request summary>",
  "kind": "<KIND or null>",
  "rules_loaded": true|false,
  "kit_rules_path": "<path or null>",
  "template_path": "<path or null>",
  "example_path": "<path or null>",
  "project_ctx": "<short summary of relevant existing artifacts>"
}
```

## Methodology

```text
UNIT BrainstormFacilitatorMethodology

PURPOSE:
  Load context files and construct the panel + seed topic.

DO:
  WHEN rules_loaded == true AND kit_rules_path != null:
    Read kit_rules_path
  WHEN rules_loaded == true AND template_path != null:
    Read template_path
    Use template's high-leverage sections (most-constrained,
    most-cross-referenced, most-likely-to-break) to inform persona selection
  WHEN example_path != null:
    Read example_path
    Use its concrete structure, tone, and domain emphasis to refine
    persona selection and the seed topic
    FORBID copying example content into output unless it is already
    part of the user's requested topic

  Build panel of 3-6 personas; for each fill:
    id:        unique expert ID (E1, E2, ...) — MUST be unique across panel
    persona:   short role name
    focus:     2-3 focus areas specific to this topic, not generic
    rationale: 1 sentence explaining why this persona is needed for
               this particular topic / kind / project

  INVARIANTS:
    - MUST_NOT have two personas with overlapping focus lists
    - Prefer personas whose focus covers the template's high-leverage sections
      when rules are loaded

  Build seed topic for round 1:
    Pick the single most-load-bearing question that, once answered, unblocks
    the largest fraction of remaining design decisions
    Set section to the most relevant template section when one is known;
    otherwise null
    Provide a 1-sentence why_first
```

NOTES:
  Persona role examples: "Domain Architect", "Security Reviewer",
  "API Designer", "Reliability Engineer", "Operator / SRE", "End User
  Advocate", "Compliance Reviewer", "Cost / Budget Owner".
  Diversity over coverage: avoid two personas with overlapping focus.

## Output (return-value contract)

```text
RULES:
  - MUST emit exactly the JSON block below as the entire response
  - MUST_NOT emit preamble or trailing commentary
```

```json
{
  "proposed_panel": [
    { "id": "E1", "persona": "...", "focus": ["...", "..."],
      "rationale": "..." }
  ],
  "seed_topic": { "id": "T1", "text": "...", "section": "<template-section or null>", "why_first": "..." }
}
```

## Response Completion Gate

```text
UNIT BrainstormFacilitatorCompletionGate

PURPOSE:
  Enforce all required output properties before the response is complete.

RULES:
  - MUST have 3-6 personas in the panel
  - MUST have unique id values for all proposed_panel[] entries
  - MUST_NOT have two personas with overlapping focus lists
  - MUST have non-empty id in seed_topic
  - MUST have non-empty text in seed_topic
  - MUST have section key in seed_topic (non-empty template section name or null)
  - MUST have non-empty why_first in seed_topic
  - MUST satisfy the SKILL.md invariant
```
