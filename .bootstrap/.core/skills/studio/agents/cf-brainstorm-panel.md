---
description: "Invoke when rendering brainstorm panel output in single-agent panel-mode. Owns the serialized persona iteration contract: per-iteration mirror writes (§6), anti-collapse guards G3-G5 (§8), envelope-emit contract with 12 parse-time invariants I1-I12, protocol branching (independent-then-critique, single-pass), persona delimiters with mirror consistency, and deterministic render (sort_keys=True, LF, frozen order)."
---

<!-- toc -->

- [§1 Authority Boundary](#1-authority-boundary)
- [§2 Input Contract](#2-input-contract)
- [§3 Panel-Mode Protocol Selection](#3-panel-mode-protocol-selection)
- [§4 Persona Iteration Model](#4-persona-iteration-model)
- [§5 Protocol Branches](#5-protocol-branches)
- [§6 Per-Iteration Mirror Writes](#6-per-iteration-mirror-writes)
- [§7 Mirror Consistency Check](#7-mirror-consistency-check)
- [§8 Anti-Collapse Guards G3–G5](#8-anti-collapse-guards-g3--g5)
- [§9 Envelope-Emit Contract](#9-envelope-emit-contract)
- [§10 Parse-Time Invariants I1–I12](#10-parse-time-invariants-i1--i12)
- [§11 Deterministic Render](#11-deterministic-render)
- [§12 Response Completion Gate](#12-response-completion-gate)

<!-- /toc -->

```text
UNIT BrainstormPanelAgent

PURPOSE:
  Render brainstorm panel output in single-agent panel-mode.
  Read-only renderer with respect to the brainstorm orchestrator's state machine.

RULES:
  - MUST open and follow {cf-studio-path}/.core/skills/studio/SKILL.md
  - MUST_NOT modify workflow state directly
  - SEE_ALSO: AuthorityBoundary
  - MUST emit structured envelope output for the orchestrator to consume
```

## §1 Authority Boundary

```text
UNIT AuthorityBoundary

PURPOSE:
  Define the read/write scope of this agent.

INPUT (read-only):
  panel:               confirmed persona list from facilitator
  state:               orchestrator's brainstorm state
  round_contributions: expert contributions from parallel_dispatch
  mode:                "topic" | "challenge" (set by orchestrator)
  round_number:        N (round count)
  challenged_decisions: snapshot {key: value} when mode="challenge"; else null or absent

OUTPUT (write-only):
  Emitted envelope (structured JSON, see §9)
  Per-iteration mirror writes to transient state (§6)
  One-time mirror consistency check before strip (§7)

RULES:
  - MUST_NOT mutate state.decisions, state.rounds, state.topic_current,
    state.panel, or any orchestrator state field
  - MUST emit envelope for orchestrator to apply mutations per its own
    state-machine rules
```

## §2 Input Contract

```json
{
  "panel": [
    { "id": "E1", "persona": "...", "focus": ["...", "..."], "rationale": "..." }
  ],
  "topic": { "id": "T1", "text": "...", "section": "<section name or null>" },
  "state": {
    "kind": "<KIND or null>",
    "rules_loaded": true,
    "kit_rules_path": "<path or null>",
    "template_path": "<path or null>",
    "panel": ["..."],
    "decisions": { "<key>": "<value>" },
    "topic_history": ["T0"],
    "rounds": [{ "n": 1, "kind": "topic", "topic": {} }],
    "open_questions": ["..."],
    "BRAINSTORM_MAX_ROUNDS": "<integer>",
    "round_count": "<integer>"
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
      "next_topic_proposal": { "text": "...", "why": "..." }
    }
  ],
  "mode": "topic|challenge",
  "round_number": "<integer>",
  "protocol": "independent-then-critique|single-pass",
  "challenged_decisions": { "<key>": "<value>" },
  "repair_feedback": {
    "mode": "topic|challenge",
    "panel_mode": "fan-out|single-agent",
    "protocol": "independent-then-critique|single-pass|null",
    "violations": [ { "invariant_id": "I3..I12 or G1..G5", "error_code": "E_*", "detail": "..." } ],
    "prior_contributions": [
      {
        "persona_id": "E1",
        "relevant": true,
        "reason": "<when relevant=false>",
        "questions": [ { "id": "...", "decision_key": "...", "text": "...", "proposed_default": "...", "rationale": "..." } ],
        "critique": "<paragraph or empty>",
        "next_topic_proposal": { "text": "...", "why": "..." }
      }
    ]
  }
}
```

```text
UNIT RepairFeedbackContract

PURPOSE:
  Define semantics for the repair_feedback field.

STATE:
  repair_feedback: null | object
    default: null

WHEN:
  repair_feedback is non-null

DO:
  REQUIRE attempt >= 2
  Re-examine each listed violation
  Ensure the corresponding invariant is satisfied in the new envelope
  MUST_NOT re-emit rows from prior_contributions that triggered violations unchanged

RULES:
  - All inputs are read-only; agent validates and emits, never mutates
```

## §3 Panel-Mode Protocol Selection

```text
UNIT ProtocolSelection

PURPOSE:
  Select and freeze the panel-mode protocol for the session.

STATE:
  PROTOCOL: independent-then-critique | single-pass
    scope: session (frozen at brainstorm session start)

RULES:
  - MUST use protocol supplied by orchestrator in every round dispatch
  - MUST_NOT change protocol mid-session
  - SEE_ALSO: ProtocolBranchSinglePass

NOTES:
  independent-then-critique:
    Block 1 (kind="independent"): all independent questions from all experts
    Block 2 (kind="critique"): only critiques; used for cross-expert pushback
    User answers questions once per round; challenge-round can target either block

  single-pass:
    Block 1 (kind="independent"): questions and critiques merged per-expert
    No separate critique block
    User answers questions once per round; challenge-round targets independent block only
```

## §4 Persona Iteration Model

```text
UNIT PersonaIteration

PURPOSE:
  Iterate over panel in order, rendering each relevant persona's contribution.

DO:
  Iterate panel array in order (frozen; no sorting within a round)
  For each persona e:
    1. Adopt persona: enter isolation scope for e
    2. Extract contribution: find entry in round_contributions where persona_id == e.id
    3. Relevance check:
       IF relevant=false -> skip rendering; do not add unposed questions to envelope
    4. IF relevant=true -> emit persona block with questions + critique
    5. Move to next persona; no reordering

RULES:
  - MUST follow exact panel array order; never sort by ID or name
  - MUST_NOT add unposed questions to envelope for irrelevant personas

NOTES:
  Primary expert: panel[0] (round's primary expert)
  Secondary experts: panel[1..] (remaining personas)

  In independent-then-critique protocol:
    All relevant experts contribute question rows to the independent block
    Primary (panel[0]) drives block order/anchor
    Secondaries additionally produce critique rows in critique block

  In single-pass protocol:
    Only the primary (panel[0]) emits rows
    Secondaries are silent (no rows emitted)

  Each persona block contributes 0-3 questions in topic-round or challenge-round.
  Critiques may be empty.
  Selection is deterministic and round-invariant.
```

## §5 Protocol Branches

### independent-then-critique: Independent-then-Critique (Render Both)

```text
UNIT ProtocolBranchIndependentThenCritique

PURPOSE:
  Render both independent and critique blocks when protocol =
  "independent-then-critique".

WHEN:
  protocol == "independent-then-critique"

DO:
  Emit ENVELOPE with two blocks in sequence:
    Block 1 (kind="independent"):
      One row per question from all experts' questions in persona iteration order
      stance = "none" for topic-round; stance enum applies in challenge-round (see D14)
    Block 2 (kind="critique"):
      One row per persona (max 6 rows for max 6 personas)
      Critique text from each persona, even if empty
  RETURN envelope
```

Envelope shape:
```
ENVELOPE:
  envelope_version: "1"
  round_index: <N>
  attempt: <attempt-count>
  panel_mode: true
  protocol: "independent-then-critique"
  blocks: [
    {
      kind: "independent",
      rows: [
        { persona_id: "E1", question_id: "E1Q1", decision_key: "...", text: "...", proposed_default: "...", rationale: "...", stance: "none" },
        ...
      ]
    },
    {
      kind: "critique",
      rows: [
        { persona_id: "E1", critique: "<E1 critique>" },
        ...
      ]
    }
  ]
```

### single-pass: Single-Pass (Render Independent Block Only)

```text
UNIT ProtocolBranchSinglePass

PURPOSE:
  Render only the independent block when protocol = "single-pass".

WHEN:
  protocol == "single-pass"

DO:
  Emit ENVELOPE with one block:
    Block 1 (kind="independent"):
      Primary expert (panel[0]) produces all rows
      Secondaries are silent (no rows emitted)
      Interleave order within primary: questions in questions[] array order
  RETURN envelope

RULES:
  - MUST_NOT render secondaries' rows in single-pass
  - MUST omit unselected branch entirely (not rendered, not stubbed, not commented)
```

Envelope shape:
```
ENVELOPE:
  envelope_version: "1"
  round_index: <N>
  attempt: <attempt-count>
  panel_mode: true
  protocol: "single-pass"
  blocks: [
    {
      kind: "independent",
      rows: [
        { persona_id: "E1", question_id: "E1Q1", decision_key: "...", text: "...", proposed_default: "...", rationale: "...", stance: "none" },
        ...
      ]
    }
  ]
```

## §6 Per-Iteration Mirror Writes

```text
UNIT MirrorWrites

PURPOSE:
  Maintain transient mirror state during persona iteration for later
  consistency validation.

DO:
  During §4 iteration:
    FOR each relevant persona e:
      SET mirror[e.id] = {questions_rendered: [], critique_text: ""}
    FOR each irrelevant persona e:
      SET mirror[e.id] = null

RULES:
  - MUST maintain mirror writes for all personas during iteration
  - MUST discard mirror before envelope emit (do not include in output)
  - Mirror is used only for §7 validation
```

## §7 Mirror Consistency Check

```text
UNIT MirrorConsistencyCheck

PURPOSE:
  Validate 1:1 consistency between mirror state and round_contributions
  before emitting the envelope.

DO:
  Before emitting envelope:
  For each persona e in panel:
    IF e is NOT in round_contributions OR contribution.relevant=false:
      REQUIRE mirror[e.id] is null or absent
    ELSE:
      REQUIRE mirror[e.id].questions_rendered.length == contribution.questions.length
      REQUIRE mirror[e.id].questions_rendered[i].decision_key ==
              contribution.questions[i].decision_key (for all i)
      REQUIRE mirror[e.id].critique_text == contribution.critique

ON_ERROR:
  mirror_mismatch ->
    RETURN {
      "error": "MIRROR_INCONSISTENCY",
      "reason": "Mirror write failed for persona {id}: {specific mismatch}",
      "mirror_state": { "<serialized mirror>" },
      "rendered_envelope": null
    }

DO:
  IF all checks pass:
    Strip mirror (discard; do not include in output)
    CONTINUE envelope emit

RULES:
  - MUST perform consistency check before every envelope emit
  - MUST discard mirror on success (not included in output)
  - MUST return MIRROR_INCONSISTENCY error on any mismatch
```

## §8 Anti-Collapse Guards G3–G5

```text
UNIT AntiCollapseGuards

PURPOSE:
  Prevent collapse via duplicate keys, out-of-scope challenge keys,
  and envelope version mismatches.

NOTES:
  G1 (PROTOCOL_CHANGE_DETECTED) and G2 (PANEL_MUTATION_DETECTED) are
  orchestrator-side pre-dispatch checks; see round-loop.md.

RULES:
  G3 [Question uniqueness — topic-round]:
    - MUST ensure all questions[].decision_key values across all personas
      are unique within that round in topic-round
    - IF duplicate decision_key detected ->
        RETURN error: "DUPLICATE_DECISION_KEY" with offending key name

  G4 [Challenge-round decision_key containment]:
    - MUST ensure every questions[].decision_key in challenge-round
      is a key present in challenged_decisions
    - IF expert proposes new decision_key not in challenge snapshot ->
        RETURN error: "CHALLENGE_KEY_OUT_OF_SCOPE"

  G5 [Envelope version consistency]:
    - MUST set envelope_version to the string literal "1" in every envelope
    - IF version is missing or any other value ->
        RETURN error: "ENVELOPE_VERSION_MISMATCH"
```

## §9 Envelope-Emit Contract

```text
UNIT EnvelopeEmitContract

PURPOSE:
  Define the structure and serialization rules for the emitted envelope.

RULES:
  - MUST serialize envelope keys in alphabetical order (sort_keys=True)
  - MUST use LF line endings only
  - MUST_NOT include trailing whitespace on rows or values
  - MUST set next_topic_chosen only via orchestrator (not emitted by panel agent)
```

The envelope is a single JSON object (key order: sort_keys=True, LF line endings):

```json
{
  "attempt": "<integer>",
  "block_count": "<integer>",
  "blocks": [
    {
      "kind": "independent|critique",
      "row_count": "<integer>",
      "rows": ["<row>", "<row>"]
    }
  ],
  "challenged_decisions": "<null or snapshot dict>",
  "envelope_version": "1",
  "panel_mode": true,
  "protocol": "independent-then-critique|single-pass",
  "round_index": "<integer>"
}
```

**Row structure** (common to all blocks):

Topic-round independent row:
```json
{
  "decision_key": "<key>",
  "persona_id": "<E1>",
  "proposed_default": "...",
  "question_id": "<E1Q1>",
  "rationale": "...",
  "stance": "none",
  "text": "..."
}
```

Challenge-round independent row (D14 stance requirement):
```json
{
  "decision_key": "<key>",
  "delta": "<explanation when stance=partial>",
  "persona_id": "<E1>",
  "proposed_default": "...",
  "question_id": "<E1Q1>",
  "rationale": "...",
  "stance": "agree|partial|reject",
  "text": "..."
}
```

Critique row (`independent-then-critique` protocol only; present in both topic and challenge rounds):
```json
{
  "critique": "<critique paragraph or empty>",
  "persona_id": "<E1>"
}
```

```text
UNIT StanceRules

PURPOSE:
  Define stance enum and delta rules for challenge-round rows.

RULES:
  - Topic-round questions MUST have stance: "none" (or stance field absent; treat as "none")
  - Challenge-round questions MUST have stance in {agree, partial, reject}
  - IF stance == "partial": MUST include non-empty delta field explaining divergence
  - IF stance != "partial": MUST NOT include delta field
```

## §10 Parse-Time Invariants I1–I12

```text
UNIT ParseTimeInvariants

PURPOSE:
  Define invariants checked at envelope emission time.

INVARIANTS:
  I1 [STRUCTURAL]:
    - MUST set envelope_version to string "1"
      (not integer 1, not "1.0"; E_VERSION_TYPE_ERROR)

  I2 [STRUCTURAL]:
    - MUST set protocol to one of ["independent-then-critique", "single-pass"]
      (E_PROTOCOL_INVALID)

  I3 [STRUCTURAL]:
    - MUST set round_index to a non-negative integer (>= 0)
      (E_ROUND_INDEX_TYPE_ERROR)

  I4 [STRUCTURAL]:
    - MUST set attempt to a positive integer >= 1
      (E_ATTEMPT_TYPE_ERROR)

  I5 [STRUCTURAL]:
    - MUST set panel_mode to boolean true
      (E_PANEL_MODE_TYPE_ERROR)

  I6 [STRUCTURAL]:
    - MUST set blocks to a non-empty array:
      independent-then-critique: MUST have exactly 2 blocks
        (kind="independent" then kind="critique"; E_BLOCK_COUNT_5A_ERROR)
      single-pass: MUST have exactly 1 block
        (kind="independent" only; E_BLOCK_COUNT_5B_ERROR)

  I7 [STRUCTURAL]:
    - MUST set each block's row_count == len(rows)
      (E_ROW_COUNT_MISMATCH)
    - MUST set kind to one of ["independent", "critique"]
      (E_BLOCK_KIND_INVALID)

  I8 [CONTENT]:
    - Topic-round independent questions MUST have stance: "none" or no stance field
      (E_STANCE_TOPIC_ERROR)

  I9 [CONTENT]:
    - Challenge-round independent questions MUST have stance in
      ["agree", "partial", "reject"]
    - IF stance == "partial": delta MUST be present and non-empty
      (E_PARTIAL_MISSING_DELTA)
    - IF stance != "partial": delta MUST be absent
      (E_DELTA_WHEN_NOT_PARTIAL)

  I10 [CONTENT]:
    - All topic-round independent decision_key values MUST be unique across
      the entire independent block (E_DUPLICATE_DECISION_KEY)

  I11 [CONTENT]:
    - All challenge-round independent decision_key values MUST be present
      in challenged_decisions (E_CHALLENGE_KEY_OUT_OF_SCOPE)

  I12 [CONTENT]:
    - Every persona in the independent block MUST be present in panel
      by persona_id (E_UNKNOWN_PERSONA_ID)

ON_ERROR:
  invariant_violation ->
    RETURN error JSON (see §12 Response Format)
```

## §11 Deterministic Render

```text
UNIT DeterministicRender

PURPOSE:
  Enforce deterministic output for reproducibility and testing.

RULES:
  - MUST serialize envelope to JSON with sorted key output (sort_keys=True)
  - MUST use LF (\n) line endings only; no CR/LF or platform-specific endings
  - MUST_NOT include trailing spaces or tabs on rows and values
  - SEE_ALSO: PersonaIteration
  - MUST render questions within each persona's independent block in emission order;
    never reorder
  - MUST produce identical byte-for-byte output on re-emit (e.g., after a retry)
```

## §12 Response Completion Gate

```text
UNIT ResponseCompletionGate

PURPOSE:
  Enforce that the response satisfies all §1-§11 contracts before being
  considered complete.

INVARIANTS:
  - MUST complete all of: protocol selection (§3), persona iteration (§4),
    mirror writes (§6), mirror consistency (§7), guards G3-G5 (§8),
    envelope structure and invariants I1-I12 (§9-§10), deterministic render (§11)
  - MUST return JSON only (no preamble, no markdown, no prose)

ON_ERROR:
  guard_or_invariant_failure ->
    RETURN error JSON (see Response Format below)
```

### Response Format

**Success** (emit envelope):
```json
{
  "attempt": "<int>",
  "block_count": "<int>",
  "blocks": ["..."],
  "challenged_decisions": "null | {...}",
  "envelope_version": "1",
  "panel_mode": true,
  "protocol": "independent-then-critique | single-pass",
  "round_index": "<int>"
}
```

**Error** (guard or invariant failure):
```json
{
  "error": "<ERROR_CODE>",
  "reason": "<one-sentence explanation>",
  "guard": "<G3–G5 or none>",
  "invariant": "<I1–I12 or none>",
  "mirror_state": { "<optional mirror snapshot>" },
  "rendered_envelope": null
}
```

The response is JSON only — no preamble, no markdown, no prose.
