---
description: "Invoke when the brainstorm session ends (user wrap-up, stop-token, or BRAINSTORM_MAX_ROUNDS cap) and the wrap-up summary + next-step routing menu must run."
name: phase-0.7-wrap-handoff
purpose: Brainstorm loop exit — consolidated design block, save/generate/analyze/iterate routing, stop-token semantics, Phase 1 or review hand-off
loaded_by: workflows/generate/phase-0.7/index.md
version: 1.1
---

<!-- toc -->

- [Consolidated design block (loop exit)](#consolidated-design-block-loop-exit)
- [Contributions shape and orchestration modes](#contributions-shape-and-orchestration-modes)
- [Hand-off routing](#hand-off-routing)

<!-- /toc -->

### Consolidated design block (loop exit)

```pdsl
UNIT BrainstormWrapHandoff

PURPOSE:
  Emit consolidated design block on loop exit; route based on explicit user choice.

DO:
  - RUN WHEN state.topic_current becomes None:
    IF rules_mode == RELAXED:
      PREPEND "⚠ Brainstorm without kit rules (reduced quality assurance)"
    - EMIT exactly:
- RUN ---
- RUN Brainstorm complete after {N} rounds.
- RUN Panel: {personas}
- RUN Topics covered: {topic_history}

- RUN Decisions:
- RUN {section_or_key}: {value}

- RUN Open questions (carry into inputs):
- RUN {open_question}

- RUN Next-step menu follows immediately:
- RUN Save brainstorm results only (in session)
- RUN Save brainstorm results only (to disk)
- RUN Send results to generate input collection
- RUN Send results to review/analyze
- RUN Reopen a topic for another brainstorm round
- RUN In `save` mode, the saved brainstorm cache remains on disk and follows manual retention.
- RUN The discard handoff path ALWAYS state whether saved cache artifacts remain.
- RUN ---
    - EMIT_MENU WrapHandoffMenu
    - WAIT user.reply
    - STOP_TURN

MENU WrapHandoffMenu:
  TITLE: Brainstorm complete — choose next step (reply 1, 2, 3, 4, or 5)
  OPTIONS:
    1 ->
      NOTE: preserve brainstorm outputs only in current chat/session state
      NOTE: do not write cache files
      NOTE: do not enter generate or analyze
      EMIT "Brainstorm results saved in session only. No workflow handoff started."
      STOP_TURN
    2 ->
      REQUIRE output_destination allows file writes
      WRITE state.json to {cf-studio-path}/.cache/brainstorm/{session_id}/state.json
      WRITE design.md to {cf-studio-path}/.cache/brainstorm/{session_id}/design.md
      EMIT "Brainstorm results saved to disk under {cf-studio-path}/.cache/brainstorm/{session_id}/. No workflow handoff started."
      STOP_TURN
    3 ->
      SET PRE_RESOLVED_INPUTS = state.decisions
      SET CARRYOVER_QUESTIONS = state.open_questions
      CONTINUE workflows/generate/phase-1-collect.md
    4 ->
      SET REVIEW_BRAINSTORM_RESULTS = {
        decisions: state.decisions,
        open_questions: state.open_questions,
        topic_history: state.topic_history,
        rounds: state.rounds
      }
      CONTINUE workflows/analyze.md
      WITH:
        brainstorm_review = true
        brainstorm_results = REVIEW_BRAINSTORM_RESULTS
    5 ->
      EMIT "Which topic gap should be reopened?"
      WAIT user.reply
      STOP_TURN
      APPEND as forced topic
      SET pending_round_kind = "topic"
      RESUME round loop (first iteration of resumed loop is always topic-round)
  6 stop_token (stop / enough / done) ->
    EMIT_MENU WrapHandoffMenu
    WAIT user.reply
    STOP_TURN
  INVALID:
    EMIT "Reply with 1, 2, 3, 4, or 5."
    WAIT user.reply
    STOP_TURN

RULES:
  - ALWAYS prepend RELAXED brainstorm warning when rules_mode == RELAXED
    per the contract declared in save-and-rules.md § Rules respect
  - NEVER auto-route directly into generate without the wrap-handoff menu
  - NEVER interpret stop-token as implicit approval for generate
  - ALWAYS preserve brainstorm decisions/open questions when routing to generate
    or analyze
  - ALWAYS Open questions from skipped brainstorm questions ALWAYS remain unresolved;
    generate/analyze handoff NEVER convert them into implicit decisions
  - ALWAYS keep saved cache artifacts on disk when session used save
  - ALWAYS Option 1 ALWAYS be session-only and NEVER write files
  - ALWAYS Option 2 ALWAYS be hidden or rejected with a one-line explanation when
    output_destination is chat-only or no-write
```

### Contributions shape and orchestration modes

```pdsl
UNIT BrainstormWrapContributionsShape

PURPOSE:
  Clarify that wrap-up logic is protocol-agnostic; both modes produce
  identical contributions[] shape.

NOTES:
  Fan-out mode (rounds[].panel_mode == "fan-out"):
    All relevant experts dispatched in parallel; each independently produces
    questions and critique; orchestrator collects and flattens before persisting.

  Single-agent panel (rounds[].panel_mode == "single-agent"):
    One expert runs full round logic; other panelists provide structured critique
    per protocol; panel renderer emits envelope; orchestrator flattens before persisting.

  Semantic equivalence post-flatten:
    Both modes produce identical state.rounds[].contributions[] shape.
    Each entry has expert_id, relevant, questions[], critique, next_topic_proposal.
    Dissent computations remain valid regardless of dispatch shape.

  Single-pass protocol behavior:
    When rounds[].protocol == "single-pass" (only valid under single-agent mode),
    critique field in non-primary panelists is absent or empty.
    Dissent computations remain sound.

  Wrap-up evaluation notes:
    High status="degraded" rate may warrant user review before approve.
    rounds[].panel_mode presence enables auditing which rounds used single-agent
    pooling vs. fan-out parallelism.
```

### Hand-off routing

```pdsl
UNIT BrainstormNextStepRouting

PURPOSE:
  Define the explicit next-step routes after brainstorm wrap-up.

DO:
  - RUN WHEN user chose 2:
    - REQUIRE output_destination allows file writes
    WRITE state.json to {cf-studio-path}/.cache/brainstorm/{session_id}/state.json
    WRITE design.md to {cf-studio-path}/.cache/brainstorm/{session_id}/design.md
    - EMIT "Brainstorm results saved to disk under {cf-studio-path}/.cache/brainstorm/{session_id}/. No workflow handoff started."
    - STOP_TURN

  - RUN WHEN user chose 3:
    - CONTINUE workflows/generate/phase-1-collect.md
    WITH:
      pre_resolved_inputs = PRE_RESOLVED_INPUTS
      open_questions = CARRYOVER_QUESTIONS

  - RUN WHEN user chose 4:
    - CONTINUE workflows/analyze.md
    WITH:
      brainstorm_review = true
      brainstorm_results = REVIEW_BRAINSTORM_RESULTS

NOTES:
  Generate route:
    The collector marks pre-filled sections [from brainstorm] and surfaces
    a Carryover Questions mini-section.
    Skipped brainstorm questions appear there as unresolved inputs for PRD,
    DESIGN, ADR, FEATURE, or implementation planning.
    Open, load, and follow {cf-studio-path}/.core/workflows/generate/phase-1-collect.md.

  Analyze route:
    The review/analyze path treats brainstorm outputs as the review subject for
    the next workflow. Carry decisions, open questions, topic history, and
    rounds forward as controller-owned context for that review handoff.
```
