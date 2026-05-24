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
  "panel": [
    { "id": "E1", "persona": "...", "focus": ["..."], "rationale": "..." }
  ],
  "rounds": [
    {
      "n": 1,
      "kind": "topic",
      "panel_mode": "fan-out",
      "protocol": null,
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
  "open_questions": [ "<unanswered or skipped>" ],
  "round_count": 0,
  "BRAINSTORM_MAX_ROUNDS": 10
}
```

`round_count` is incremented by the orchestrator after every completed round
(both `kind="topic"` and `kind="challenge"`). `BRAINSTORM_MAX_ROUNDS` defaults
to `10`. It is configurable: when the user replies `yes:N` to the offer (e.g.
`yes:15`), the orchestrator sets `BRAINSTORM_MAX_ROUNDS = N` before entering
the round loop. The cap-check and cap-prompt behavior live in
`workflows/generate/phase-0.7/round-loop.md` § Round loop.

`rules_loaded` is a boolean, not an implied constant. Set it to `true` only
when `kit_rules_path` was resolved and loaded for this brainstorm session; set
it to `false` for RELAXED/no-kit sessions or any chat-only exploratory run
without kit rules. When dispatching brainstorm facilitator or expert agents,
include `kit_rules_path` alongside `rules_loaded` so the receiver can
distinguish "rules intentionally absent" from "rules required but missing".

`topic_current` is the full topic object used by the round-loop dispatch
contract, or `null` before the first topic is chosen. Do not store only the
topic id string; `topic_history` is the id-only history.

`rounds[].kind` is `"topic"` (default) for normal exploratory rounds.
`kind="challenge"` rounds re-open the immediately-preceding answer-writing round's
decisions for cross-expert pushback. Challenge rounds may challenge the
accepted/custom answers from a prior challenge round. Only `kind="topic"`
rounds append to `topic_history` and refresh `next_topic_proposals`;
`kind="challenge"` rounds reuse the same `topic` as the round they are
challenging and leave `topic_history` untouched.

`rounds[].answer_keys` lists the `decisions` keys whose value was actually
written by that round (used by the next iteration to compute the challenge
scope without re-walking the answers list). On `kind="challenge"` rounds,
`answer_keys` lists ONLY keys overwritten by an `accept` / `<custom>` answer;
`keep` / `skip` answers are excluded (the value was re-affirmed, not
rewritten). On `kind="topic"` rounds, `skip` answers are excluded for the
same reason (no write happened). The field is the empty list when the user
skipped/kept every question, which suppresses option `C` on the next
post-round menu.

`rounds[].challenged_decisions` is set only on `kind="challenge"` rounds: a
snapshot of `{ key: value }` pairs from `state.decisions` *at the moment the
challenge round started*, scoped to the keys written by the immediately-preceding
answer-writing round (i.e. `state.rounds[-1].answer_keys` when the user chose
`C`). The snapshot is what the panel saw; later overwrites do not retro-edit it.

`next_topic_proposals` is the deduped/merged list emitted by the most recent
`kind="topic"` round. It survives subsequent `kind="challenge"` rounds so the
post-round menu can keep offering the same next-topic options without
re-dispatching the panel just to refresh proposals.

Decision overwrite semantics: when a challenge-round's answer accepts a
counter-proposal (or the user supplies a custom value), `state.decisions[key]`
is **overwritten** in place — prior values are not versioned at the
`decisions` level. The `rounds[]` array preserves the audit trail
(every value the panel produced and the user accepted lives in
`rounds[*].answers`).

---

### Round Field Reference

#### panel_mode (orchestration strategy)

**Field:** `rounds[].panel_mode` (required, non-null)  
**Type:** enum `{fan-out, single-agent}`  
**Default:** `"fan-out"`

Controls how the orchestrator coordinates expert agents during a round:

- **`fan-out`** (default): Dispatch all relevant panel members in parallel. Each expert independently produces questions/contributions; the orchestrator collects all responses before aggregation. No inter-expert live communication during this mode.
- **`single-agent`**: Designate one expert as primary for this round. That expert runs the full round logic; subsequent experts see the primary's output and (optionally) provide critique via the `protocol` field. Smaller panel, lower latency, expert specialization.

The **single field** constraint means each round has exactly one orchestration strategy; mixed strategies within a single round are not supported. When `panel_mode` is `"fan-out"`, the `protocol` field must be `null`. When `panel_mode` is `"single-agent"`, the `protocol` field must be non-null (see § protocol below).

#### protocol (single-agent interaction pattern)

**Field:** `rounds[].protocol` (conditional, nullable)  
**Type:** enum `{independent-then-critique, single-pass}` or `null`  
**Constraint:** Non-null only when `panel_mode == "single-agent"`

Specifies the interaction pattern when using single-agent orchestration:

- **`independent-then-critique`**: Primary expert produces questions and initial answers independently. Secondary panel members then review the primary's output and provide structured critique without modifying answers. Supports asynchronous, high-latency expert cycles.
- **`single-pass`**: Primary expert produces full round output; secondary members have read-only visibility but do not produce critique. Minimal latency, suitable for time-sensitive or bandwidth-constrained scenarios.
- **`null`**: Only valid when `panel_mode == "fan-out"`. Indicates no single-agent protocol is in effect.

The orchestrator pre-canonicalizes block order before flattening multi-expert outputs (see § envelope below).

#### status (round outcome)

**Field:** `rounds[].status` (required, non-null)  
**Type:** enum `{ok, degraded, skipped}`

Indicates the outcome and health of the completed round:

- **`ok`**: All experts completed their tasks within SLA (no timeouts, no errors). Primary output is canonical; no fallback or advisory needed.
- **`degraded`**: One or more experts exceeded SLA (timeout, retry exhausted) but the round completed with partial or fallback output. Check the `health.reason` field for details. Round contributions may be incomplete; decisions should be reviewed before accepting.
- **`skipped`**: Round was not executed (user skipped, max rounds reached before dispatch, or configuration prevented dispatch). No expert output; `contributions` array is empty or omitted.

#### health (round resilience tracking)

**Field:** `rounds[].health` (object with three sub-fields)  
**Type:** `{ degraded: bool, reason: str|null, attempts_used: int }`  
**Default:** `{ degraded: false, reason: null, attempts_used: 1 }`

Tracks round-level resilience metrics for troubleshooting and retry logic:

- **`degraded`** (boolean): `true` if one or more agents failed to complete within SLA; `false` if all completed normally. Mirrors the `status` field intent but provides structured access for automated decision-making.
- **`reason`** (string or null): Human-readable explanation of degradation. Examples: `"Expert E2 timeout after 120s; used cached prior response"`, `"Token limit exceeded; critique phase skipped"`, `null` if `degraded == false`.
- **`attempts_used`** (positive integer, default 1): Count of execution attempts for this round (1 = first try, 2 = one retry, etc.). Used by retry-budget logic to prevent infinite loops. Resets per round; does not accumulate across rounds.

**Usage in retry/fallback:** The orchestrator may inspect `health.attempts_used` and `health.degraded` to decide whether to re-run the round (up to a configurable budget) or proceed with partial output. The `reason` field provides audit trail context for manual review.

#### envelope (wire-level blocks, orchestrator-internal)

**Field:** NOT persisted in `rounds[]` — transient wire-level structure only  
**Type:** Object with `kind` and `rows` fields  
**Scope:** Orchestrator-to-agent RPC envelope, not stored in state.json

The `envelope` is a transient wire-level data structure used during agent dispatch and response aggregation. It is **not persisted** in the `rounds[]` array. The orchestrator canonicalizes block order pre-flatten:

```json
{
  "kind": "independent",
  "rows": [
    { "expert_id": "E1", "block": "...", "metadata": {...} }
  ]
}
```

or

```json
{
  "kind": "critique",
  "rows": [
    { "expert_id": "E2", "block": "...", "metadata": {...} }
  ]
}
```

- **`kind`** (`"independent"` | `"critique"`): Categorizes the block's role. `independent` blocks are primary contributions; `critique` blocks are secondary reviews.
- **`rows`** (array): List of expert contributions with metadata (expert ID, timestamps, token usage, etc.). Each row is flattened into the `contributions[]` array after canonicalization.

The envelope structure enables the orchestrator to manage block order, de-duplication, and fallback selection before persisting to `rounds[]`. It is **not** part of the saved state schema and should not be loaded from state.json.

---

### Loader Lazy-Normalization Rule

When loading `state.json` (or a state checkpoint), the loader applies the following normalization logic **on next save**:

**If `rounds[].panel_mode` is missing (backward compatibility with pre-1.1 state files):**
1. Set `rounds[].panel_mode = "fan-out"` (the default orchestration strategy).
2. Set `rounds[].protocol = null` (matches fan-out mode).
3. Leave all other fields unchanged.

**If `rounds[].health` is missing:**
1. Initialize `rounds[].health = { degraded: false, reason: null, attempts_used: 1 }`.

**If `rounds[].status` is missing:**
1. Infer `status` from context:
   - If `round_count > n`: set `status = "ok"` (round completed).
   - If `round_count == n and contributions.length > 0`: set `status = "ok"`.
   - If `contributions.length == 0`: set `status = "skipped"`.

This lazy approach ensures that old state files automatically upgrade on the next save, without requiring an explicit migration step. The orchestrator never loads a state with missing required fields; normalization always occurs before the state is operational.

---

### Run Config Sibling Pattern

The orchestrator run configuration is split into a **sibling** `run_config.json` file, separate from the persisted `state.json`:

**File layout:**
```
{cf-constructor-path}/.cache/brainstorm/{session_id}/
├── state.json           # Persisted round-by-round state (this schema)
└── run_config.json      # Environment + execution config (separate schema)
```

**Contents of `run_config.json`:**
```json
{
  "environment": {
    "cpt_path": "/path/to/.cf-constructor",
    "python_version": "3.11",
    "agent_timeout_seconds": 120,
    "model": "claude-opus-4.1",
    "temperature": 0.7
  },
  "session_metadata": {
    "created_at": "2025-05-23T14:30:00Z",
    "user_email": "user@example.com"
  }
}
```

**Config drift detection:**

The orchestrator compares the current runtime environment against the saved `run_config.json`:

1. If environment variables or config values differ from the saved state, emit a `config_drift` event (logged to the session transcript).
2. **By default:** Continue with current environment (current environment wins). Log the drift for user inspection.
3. **With `--reconfigure` flag:** Reload and use the saved config from `run_config.json` instead of the current environment. Useful for resuming a brainstorm session with the exact same model, timeout, and environment settings.

**Example drift scenario:**  
User pauses brainstorm at round 5, then resumes later. Environment now has `agent_timeout_seconds=60` (different from the original `120`). The orchestrator:
- Detects drift (timeout changed).
- Emits `config_drift: {field: "agent_timeout_seconds", saved: 120, current: 60}`.
- Uses current environment (`60`) unless user invokes `--reconfigure`.

This pattern enables resumable, auditable brainstorm sessions with reproducible environment constraints.

---

### Default Location

Kept in-memory by the orchestrator across rounds. Persist to
`{cf-constructor-path}/.cache/brainstorm/{session_id}/state.json` only when
the user picked explicit `save` mode and the current output destination allows
file writes. Chat-only/no-write sessions must use an in-chat checkpoint for
compaction recovery and must not write cache artifacts.
