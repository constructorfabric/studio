---
description: "Invoke when the brainstorm state object must be initialized, inspected, or persisted — defines the canonical JSON schema including BRAINSTORM_MAX_ROUNDS."
name: phase-0.7-state-schema
purpose: Brainstorm state object schema (held by orchestrator, persisted between rounds) and default-location rule
loaded_by: workflows/generate/phase-0.7/index.md
version: 1.1
---

<!-- toc -->

- [State (held by orchestrator, persisted between rounds)](#state-held-by-orchestrator-persisted-between-rounds)
- [Round Field Reference](#round-field-reference)
  - [panel_mode (orchestration strategy)](#panel_mode-orchestration-strategy)
  - [protocol (single-agent interaction pattern)](#protocol-single-agent-interaction-pattern)
  - [status (round outcome)](#status-round-outcome)
  - [health (round resilience tracking)](#health-round-resilience-tracking)
  - [envelope (wire-level blocks, orchestrator-internal)](#envelope-wire-level-blocks-orchestrator-internal)
- [Loader Lazy-Normalization Rule](#loader-lazy-normalization-rule)
- [Run Config Sibling Pattern](#run-config-sibling-pattern)
- [Default Location](#default-location)

<!-- /toc -->

### State (held by orchestrator, persisted between rounds)

```json
{
  "session_id": "{slug}-{ISO}",
  "kind": "{KIND}",
  "rules_loaded": false,
  "kit_rules_path": null,
  "template_path": "{path or null}",
  "example_path": "{path or null}",
  "context_requirements": [
    {
      "persona_id": "E1",
      "needs": ["architecture decisions", "current module boundaries"],
      "why_needed": "..."
    }
  ],
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
  "panel": [
    { "id": "E1", "persona": "...", "focus": ["..."], "rationale": "..." }
  ],
  "rounds": [
    {
      "n": 1,
      "kind": "topic",
      "panel_mode": "single-agent",
      "protocol": "independent-then-critique",
      "status": "ok",
      "health": {
        "degraded": false,
        "reason": null,
        "attempts_used": 1
      },
      "topic": { "id": "T1", "text": "...", "section": "<template-section or null>" },
      "contributions": [
        { "expert_id": "E1", "relevant": true,
          "questions": [{ "id": "E1Q1", "text": "...",
                          "decision_key": "<section-or-topic>:<expert-id>:<question-key>",
                          "proposed_default": "...", "rationale": "..." }],
          "critique": "...",
          "next_topic_proposal": { "text": "...", "why": "..." } },
        { "expert_id": "E2", "relevant": false, "reason": "..." }
      ],
      "question_queue": [
        {
          "queue_index": 1,
          "expert_id": "E1",
          "question_id": "E1Q1",
          "decision_key": "<section-or-topic>:<expert-id>:<question-key>",
          "text": "...",
          "proposed_default": "...",
          "rationale": "...",
          "status": "pending|answered|accepted_default|kept_prior|open_unanswered"
        }
      ],
      "current_question_index": 1,
      "answers": [{ "question_id": "E1Q1",
                    "decision_key": "<section-or-topic>:<expert-id>:<question-key>",
                    "value": "..." }],
      "answer_keys": ["<section-or-topic>:<expert-id>:<question-key>"],
      "next_topic_chosen": "T2"
    },
    {
      "n": 2,
      "kind": "challenge",
      "panel_mode": "single-agent",
      "protocol": "independent-then-critique",
      "status": "degraded",
      "health": {
        "degraded": true,
        "reason": "One expert agent timeout; critique completed within limits",
        "attempts_used": 2
      },
      "topic": { "id": "T1", "text": "...", "section": "<template-section or null>" },
      "challenged_decisions": { "<key>": "<prior-value-at-challenge-start>" },
      "contributions": [
        { "expert_id": "E1", "relevant": true,
          "questions": [{ "id": "E1Q1", "text": "<counter-question>",
                          "decision_key": "<key>",
                          "proposed_default": "<counter-proposal>", "rationale": "..." }],
          "critique": "...",
          "next_topic_proposal": null }
      ],
      "answers": [{ "question_id": "E1Q1", "decision_key": "<key>",
                    "value": "<accept|keep-prior|custom>" }],
      "answer_keys": ["<template-section-or-key-touched>"],
      "next_topic_chosen": null
    }
  ],
  "topic_history": ["T1", "T2"],
  "topic_current": { "id": "T2", "text": "...", "section": "<template-section or null>" },
  "next_topic_proposals": [
    { "text": "...", "proposed_by": ["E1"] }
  ],
  "decisions": { "<template-section-or-key>": "<resolved-value>" },
  "open_questions": [
    {
      "question_id": "E1Q1",
      "decision_key": "<section-or-topic>:<expert-id>:<question-key>",
      "text": "...",
      "reason": "user_skipped|missing_context|deferred_decision",
      "source": "brainstorm"
    }
  ],
  "round_count": 0,
  "BRAINSTORM_MAX_ROUNDS": 10
}
```

```pdsl
UNIT BrainstormStateRules

PURPOSE:
  Define canonical rules for state field semantics and update behavior.

RULES:
  - ALWAYS round_count:
    - ALWAYS be incremented by orchestrator after every completed round
      (both kind="topic" and kind="challenge")
  - ALWAYS BRAINSTORM_MAX_ROUNDS:
    - ALWAYS default: 10
    - ALWAYS configurable: SET to N when user replies yes:N to offer
  - ALWAYS rules_loaded:
    - ALWAYS be set true ONLY when kit_rules_path was resolved and loaded
    - ALWAYS be false for RELAXED/no-kit sessions or chat-only exploratory runs
    - ALWAYS include kit_rules_path alongside rules_loaded in every brainstorm
      facilitator or expert dispatch
  - ALWAYS context_requirements:
    - ALWAYS set after the panel is confirmed and before the first round dispatch
    - ALWAYS captures what each persona needs to know to contribute high-quality
      questions/proposals
  - ALWAYS resource_context:
    - ALWAYS set by cf-explorer after panel confirmation
    - ALWAYS stores non-prompt project resources only; NEVER be copied into
      SHARED_CONTEXT_PACK
    - ALWAYS be included in every cf-brainstorm-panel and cf-brainstorm-expert
      dispatch
  - ALWAYS topic_current:
    - ALWAYS store full topic object {id, text, section}; NEVER store only id
    - ALWAYS topic_history stores id-only history
    - ALWAYS null before first topic is chosen
  - ALWAYS rounds[].kind:
    - ALWAYS "topic": normal exploratory; appends to topic_history;
      refreshes next_topic_proposals
    - ALWAYS "challenge": re-opens preceding round's decisions; reuses same topic;
      does NOT append to topic_history; does NOT refresh next_topic_proposals
  - ALWAYS rounds[].answer_keys:
    - ALWAYS topic-rounds: lists decisions keys written (skip answers excluded)
    - ALWAYS challenge-rounds: lists ONLY keys overwritten by accept/<custom>;
      keep/skip excluded; empty list when user skipped/kept every question
      (suppresses option C on next post-round menu)
  - ALWAYS rounds[].question_queue:
    - ALWAYS flattened queue of rendered questions for the round
    - ALWAYS orchestrator asks exactly one pending question per user turn
    - ALWAYS queue order follows panel order, then question order inside each
      contribution
    - ALWAYS post-round topic/challenge/wrap menu is emitted only after every queue
      item is answered, accepted, kept, or marked open_unanswered
  - ALWAYS open_questions:
    - ALWAYS stores intentionally unanswered brainstorm questions
    - ALWAYS these are valid downstream inputs for PRD, DESIGN, ADR, and FEATURE docs
    - ALWAYS preserve question text and decision_key so generated artifacts can
      carry them as open questions instead of inventing answers
  - ALWAYS rounds[].challenged_decisions:
    - ALWAYS set ONLY on kind="challenge" rounds
    - ALWAYS snapshot of {key: value} at challenge start, scoped to
      state.rounds[-1].answer_keys (the preceding answer-writing round)
    - ALWAYS later overwrites do NOT retro-edit it
  - ALWAYS next_topic_proposals:
    - ALWAYS deduped/merged list from most recent kind="topic" round
    - ALWAYS survives subsequent kind="challenge" rounds
  - ALWAYS decisions overwrite semantics:
    - ALWAYS challenge-round accept/custom OVERWRITES state.decisions[key] in place
    - ALWAYS prior values not versioned at decisions level
    - ALWAYS rounds[] array preserves audit trail
```

---

### Round Field Reference

#### panel_mode (orchestration strategy)

```pdsl
UNIT BrainstormPanelModeField

PURPOSE:
  Define rounds[].panel_mode field semantics.

STATE:
  - SET rounds[].panel_mode: fan-out | single-agent
    default: single-agent

RULES:
  - ALWAYS single-agent:
    - ALWAYS dispatch cf-brainstorm-panel once per round (not per expert)
    - ALWAYS One expert is primary; secondary experts deliberate inside same agent
    - ALWAYS One cohesive sub-agent context per round; host-independent; INLINE_FALLBACK is a no-op
    - ALWAYS protocol field ALWAYS be non-null
  - ALWAYS fan-out:
    - ALWAYS dispatch all relevant panel members in parallel via cf-brainstorm-expert
    - ALWAYS No inter-expert live communication
    - ALWAYS Requires host with native sub-agent parallelism
    - ALWAYS protocol field ALWAYS be null
  INVARIANTS:
    - NEVER mix strategies within a single round
```

#### protocol (single-agent interaction pattern)

```pdsl
UNIT BrainstormProtocolField

PURPOSE:
  Define rounds[].protocol field semantics.

STATE:
  - SET rounds[].protocol: independent-then-critique | single-pass | null

RULES:
  - ALWAYS Non-null ONLY when panel_mode == "single-agent"
  - ALWAYS null ONLY when panel_mode == "fan-out"
  - ALWAYS independent-then-critique:
    - ALWAYS Primary expert produces questions independently
    - ALWAYS Secondary members review primary output and provide structured critique
  - ALWAYS single-pass:
    - ALWAYS Primary expert produces full round output
    - ALWAYS Secondary members have read-only visibility; do not produce critique
    - ALWAYS Minimal latency; suitable for time-sensitive scenarios
```

#### status (round outcome)

```pdsl
UNIT BrainstormStatusField

PURPOSE:
  Define rounds[].status field semantics.

STATE:
  - SET rounds[].status: ok | degraded | skipped

NOTES:
  ok: all experts completed within SLA; no fallback needed
  degraded: one or more experts exceeded SLA; round completed with partial output;
    review health.reason before accepting decisions
  skipped: round not executed; contributions array is empty or omitted
```

#### health (round resilience tracking)

```pdsl
UNIT BrainstormHealthField

PURPOSE:
  Define rounds[].health field semantics for troubleshooting and retry logic.

STATE:
  - SET rounds[].health:
    degraded: bool
    reason: string or null
    attempts_used: positive integer
    default: { degraded: false, reason: null, attempts_used: 1 }

NOTES:
  degraded: true if one or more agents failed within SLA
  reason: human-readable explanation; null when degraded=false
  attempts_used: count of execution attempts for this round; resets per round
```

#### envelope (wire-level blocks, orchestrator-internal)

```pdsl
UNIT BrainstormEnvelopeField

PURPOSE:
  Define the transient envelope wire structure used during agent dispatch.

RULES:
  - NEVER persist envelope in rounds[] — transient wire-level only
  - ALWAYS Orchestrator canonicalizes block order before flattening

NOTES:
  Envelope schema:
    { "kind": "independent", "rows": [{ "expert_id": "E1", "block": "...", "metadata": {...} }] }
    OR
    { "kind": "critique", "rows": [{ "expert_id": "E2", "block": "...", "metadata": {...} }] }
  kind "independent": primary contributions
  kind "critique": secondary reviews
  rows: flattened into contributions[] after canonicalization
```

---

### Loader Lazy-Normalization Rule

```pdsl
UNIT BrainstormLoaderNormalization

PURPOSE:
  Normalize missing fields in loaded state.json on next save (backward compatibility).

DO:
  - REQUIRE rounds[].panel_mode is missing (pre-1.1 state files):
    - SET rounds[].panel_mode = "fan-out"
    - SET rounds[].protocol = null

  - REQUIRE rounds[].health is missing:
    - SET rounds[].health = { degraded: false, reason: null, attempts_used: 1 }

  - REQUIRE rounds[].status is missing:
    IF round_count > n: SET status = "ok"
    ELIF round_count == n AND contributions.length > 0: SET status = "ok"
    ELIF contributions.length == 0: SET status = "skipped"

RULES:
  - ALWAYS apply normalization before state is operational
  - NEVER load state with missing required fields without normalizing first
```

---

### Run Config Sibling Pattern

```pdsl
UNIT BrainstormRunConfigPattern

PURPOSE:
  Define the run_config.json sibling file structure and panel mode fields.

NOTES:
  File layout:
    {cf-studio-path}/.cache/brainstorm/{session_id}/
    ├── state.json        # Persisted round-by-round state (this schema)
    └── run_config.json   # Environment + execution config (separate schema)

  Contents of run_config.json:
    {
      "environment": {
        "cpt_path": "/path/to/.cf",
        "python_version": "3.11",
        "agent_timeout_seconds": 120,
        "model": "claude-opus-4.1",
        "temperature": 0.7
      },
      "session_metadata": {
        "created_at": "2025-05-23T14:30:00Z",
        "user_email": "user@example.com"
      },
      "PANEL_MODE_TOPIC": "single-agent",
      "PANEL_MODE_CHALLENGE": "single-agent"
    }

  PANEL_MODE_TOPIC / PANEL_MODE_CHALLENGE:
    enum {"single-agent", "fan-out"} or null
    Set from offer reply; parsing contract owned by offer.md § Reply parsing.
    null (or absent) means "no offer-time override"; round loop falls back to env
    var then to workflow default "single-agent".
    mode= modifier always sets both fields to same value;
    use env vars to set independently.

  Config drift detection:
    Compare current runtime env against saved run_config.json.
    DEFAULT: current environment wins; log drift for user inspection.
    WITH --reconfigure flag: reload and use saved config.
```

---

### Default Location

```pdsl
UNIT BrainstormStateLocation

PURPOSE:
  Define where brainstorm state is kept and when it is persisted.

RULES:
  - ALWAYS keep state in-memory by orchestrator across rounds
  - ALWAYS persist to {cf-studio-path}/.cache/brainstorm/{session_id}/state.json
    ONLY when user picked explicit save mode AND current output destination
    allows file writes
  - NEVER write cache artifacts for chat-only/no-write sessions
  - ALWAYS use in-chat checkpoint for compaction recovery in chat-only mode
```
