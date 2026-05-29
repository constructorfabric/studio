---
description: "Invoke when the brainstorm round loop runs — manages question dispatch, user answers, state.round_count cap, and topic selection."
name: phase-0.7-round-loop
purpose: Brainstorm round loop — parallel_dispatch of experts or single-agent panel dispatch, INLINE_FALLBACK degradation, render contract, user reply parsing, and retry flow
loaded_by: workflows/generate/phase-0.7/index.md
version: 1.3
---

### Round loop

```text
UNIT Phase07RoundLoopPreconditions

PURPOSE:
  Enforce pre-loop invariants before any round-level dispatch.

RULES:
  - REQUIRE `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md` loaded before any cf-* sub-agent dispatch
  - REQUIRE INLINE_FALLBACK set before the first round (already probed by
    `{cf-studio-path}/.core/workflows/generate/phase-0-dependencies.md`)
  - IF INLINE_FALLBACK is unset at any round-level dispatch site
    (e.g. after context-loss/compaction):
    follow universal fail-stop rule in `{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md`
    § Pre-dispatch discipline; re-run shared probe before continuing
  - MUST NOT re-probe per-round when INLINE_FALLBACK is already set
```

```text
UNIT Phase07OrchestrationModes

PURPOSE:
  Define the two exclusive orchestration strategies per round.

STATE:
  panel_mode: single-agent | fan-out
    per-round, resolved from precedence chain

NOTES:
  single-agent (default): orchestrator dispatches cf-brainstorm-panel once per round.
  One expert is primary; secondary experts provide optional critique via protocol field.
  One cohesive sub-agent context; host-independent; INLINE_FALLBACK is a no-op.

  fan-out: orchestrator dispatches all relevant panel members in parallel via
  cf-brainstorm-expert. Each expert independently produces questions/contributions.
  No inter-expert live communication. Requires host with native sub-agent parallelism
  (degrades to sequential via INLINE_FALLBACK otherwise).
```

### Anti-pattern: SILENT_MODE_DOWNGRADE

```text
UNIT SilentModeDowngradeGuard

PURPOSE:
  Prevent the orchestrator from dispatching the wrong agent for the resolved panel_mode.

RULES:
  - WHEN panel_mode=="single-agent" AND len(state.panel) > 1:
    MUST NOT dispatch one cf-brainstorm-expert per panel member in parallel or sequentially
    (doing so is SILENT_MODE_DOWNGRADE failure)
  - WHEN panel_mode=="fan-out":
    MUST NOT dispatch one cf-brainstorm-panel when user requested fan-out

ON_ERROR:
  SILENT_MODE_DOWNGRADE ->
    STOP
    SET CF_PHASE_GATE = armed
    EMIT "silent mode downgrade prevented — single-agent mode requires cf-brainstorm-panel"
      (or symmetric fan-out string when direction is reversed)
    EMIT_MENU SilentModeDowngradeRecoveryMenu
    WAIT user.reply
    STOP_TURN

MENU SilentModeDowngradeRecoveryMenu:
  TITLE: A SILENT_MODE_DOWNGRADE was caught: orchestrator attempted wrong agent for resolved panel_mode.
  OPTIONS:
    1 ->
      RE-RESOLVE panel_mode from precedence chain
      DISPATCH correct agent for resolved panel_mode
      CONTINUE round normally
    2 ->
      CONTINUE wrap-handoff.md WITH reason="silent-mode-downgrade"
  INVALID:
    EMIT "Please reply with 1 or 2."
    WAIT user.reply
    STOP_TURN

NOTES:
  This recovery menu is independent of INLINE_FALLBACK and does NOT touch the
  § Agent availability check menu.
  Recovery is NOT the agent-availability menu — the agent is registered;
  orchestrator attempted the wrong agent for the resolved mode.
```

```text
UNIT Phase07RoundLoop

PURPOSE:
  Drive topic and challenge rounds, dispatch agents, validate contributions,
  render output, parse user replies, and enforce the round cap.

STATE:
  pending_round_kind: topic | challenge
    default: topic (first iteration is always a topic-round)
  INLINE_FALLBACK_THIS_ROUND: bool
    default: false
    scope: per-round

DO:
  WHILE state.topic_current is not None:

    SET INLINE_FALLBACK_THIS_ROUND = false

    # Resolve panel_mode (precedence chain):
    #   1. state.run_config.PANEL_MODE_TOPIC / PANEL_MODE_CHALLENGE (offer-reply)
    #   2. env var PANEL_MODE_TOPIC / PANEL_MODE_CHALLENGE
    #   3. workflow default "single-agent"
    IF pending_round_kind == "topic":
      SET panel_mode = state.run_config.PANEL_MODE_TOPIC
                       OR env(PANEL_MODE_TOPIC)
                       OR "single-agent"
    ELSE:
      SET panel_mode = state.run_config.PANEL_MODE_CHALLENGE
                       OR env(PANEL_MODE_CHALLENGE)
                       OR "single-agent"

    IF panel_mode == "single-agent":
      SET protocol = env(BRAINSTORM_PANEL_PROTOCOL, "independent-then-critique")
    ELSE:
      SET protocol = null

    # Pre-dispatch: run SILENT_MODE_DOWNGRADE guard and agent availability check
    CONTINUE SilentModeDowngradeGuard
    CONTINUE Phase07AgentAvailabilityCheck

    # Pre-dispatch checkpoint (MANDATORY before any dispatch):
    EMIT exactly one chat line:
      "- [BRAINSTORM-DISPATCH]: round={N} kind={topic|challenge} panel_mode={resolved}
        mode_source={offer-reply|env|default} agent={cf-brainstorm-panel|cf-brainstorm-expert}
        panel_size={len(state.panel)}"

    # Dispatch phase
    IF pending_round_kind == "topic":
      CONTINUE Phase07TopicDispatch
    ELSE:  # challenge
      CONTINUE Phase07ChallengeDispatch

    # Invariant validation
    CONTINUE Phase07InvariantValidation

    # Post-dispatch processing
    CONTINUE Phase07PostDispatch

    # Render output to user
    CONTINUE Phase07Render

    # Parse user reply
    CONTINUE Phase07ReplyParsing

    # Iteration cap check
    SET state.round_count = state.round_count + 1
    IF state.round_count >= state.BRAINSTORM_MAX_ROUNDS:
      EMIT_MENU RoundCapMenu
      WAIT user.reply
      STOP_TURN

  # After while-loop exits:
  LOAD {cf-studio-path}/.core/workflows/generate/phase-0.7/wrap-handoff.md

RULES:
  - MUST emit pre-dispatch checkpoint line after agent availability check resolves
    agent identifier AND before actual sub-agent dispatch tool call
  - MUST NOT emit checkpoint when availability check routes to its 3-option menu
  - Omitting checkpoint is MISSING_DISPATCH_CHECKPOINT failure: STOP, re-emit
    checkpoint line, then continue
  - INLINE_FALLBACK_THIS_ROUND is per-round scope; see `{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md`
    § Registered native sub-agent set & INLINE_FALLBACK_THIS_ROUND
```

```text
UNIT Phase07AgentAvailabilityCheck

PURPOSE:
  Verify resolved agent is present in host's registered native sub-agent set
  before any dispatch.

DO:
  VERIFY resolved agent identifier is in host registered native sub-agent set

  IF agent unavailable AND INLINE_FALLBACK == false:
    EMIT_MENU AgentUnavailableMenu
    WAIT user.reply
    STOP_TURN

  IF INLINE_FALLBACK == true:
    NOTE: inline-panel option is the recommended default; surface as suggested choice

MENU AgentUnavailableMenu:
  TITLE: The resolved brainstorm agent `{agent}` is not registered as a native sub-agent in this host.
  OPTIONS:
    1 ->
      SET INLINE_FALLBACK_THIS_ROUND = true
      INLINE the matching agent contract for this round only
    2 ->
      IF pending_round_kind == "topic":
        SET state.run_config.PANEL_MODE_TOPIC = other_value(current_mode)
      ELSE:
        SET state.run_config.PANEL_MODE_CHALLENGE = other_value(current_mode)
      NOTE: other_value("single-agent") = "fan-out"; other_value("fan-out") = "single-agent"
      NOTE: the OTHER mode key (not matching pending_round_kind) is left unchanged
      RE-RESOLVE panel_mode for current round
      CONTINUE Phase07AgentAvailabilityCheck (for newly resolved agent)
    3 ->
      CONTINUE wrap-handoff.md WITH reason="agent-unavailable"
  INVALID:
    EMIT "Reply with 1, 2, or 3."
    WAIT user.reply
    STOP_TURN
```

```text
UNIT Phase07TopicDispatch

PURPOSE:
  Dispatch panel for topic-round based on resolved panel_mode.

DO:
  REQUIRE pending_round_kind == "topic"

  IF panel_mode == "fan-out":
    PARALLEL_DISPATCH [cf-brainstorm-expert for each e in state.panel]
    WITH: persona=e, topic=state.topic_current, state, mode="topic"
    SET contributions = all_results

  ELSE:  # single-agent
    IF state.rounds is non-empty:
      CONTINUE Phase07MidSessionMutationGuard
      IF status != "skipped":
        DISPATCH cf-brainstorm-panel
        WITH: panel=state.panel, topic=state.topic_current, state,
              mode="topic", protocol=protocol
        SET envelope = result
        SET contributions = flatten_envelope(envelope)
    ELSE:
      DISPATCH cf-brainstorm-panel
      WITH: panel=state.panel, topic=state.topic_current, state,
            mode="topic", protocol=protocol
      SET envelope = result
      SET contributions = flatten_envelope(envelope)
```

```text
UNIT Phase07ChallengeDispatch

PURPOSE:
  Dispatch panel for challenge-round based on resolved panel_mode.
  Precondition: state.rounds non-empty and state.rounds[-1].answer_keys non-empty
  (parse-side guard in Phase07ReplyParsing refuses C when answer_keys is empty).

DO:
  REQUIRE pending_round_kind == "challenge"
  SET challenge_source_round = state.rounds[-1]
  SET challenge_keys = challenge_source_round.answer_keys
  SET challenged_decisions = { k: state.decisions[k] for k in challenge_keys }

  IF panel_mode == "fan-out":
    PARALLEL_DISPATCH [cf-brainstorm-expert for each e in state.panel]
    WITH: persona=e, topic=state.topic_current, state,
          mode="challenge", challenged_decisions=challenged_decisions
    SET contributions = all_results

  ELSE:  # single-agent
    IF state.rounds is non-empty:
      CONTINUE Phase07MidSessionMutationGuard
      IF status != "skipped":
        DISPATCH cf-brainstorm-panel
        WITH: panel=state.panel, topic=state.topic_current, state,
              mode="challenge", challenged_decisions=challenged_decisions,
              protocol=protocol
        SET contributions = flatten_envelope(result)
    # UNREACHABLE else branch: precondition guarantees state.rounds non-empty
```

```text
UNIT Phase07MidSessionMutationGuard

PURPOSE:
  Shared guard for single-agent dispatch: detect mid-session protocol or panel
  mutations and set fail-stop skip state before any dispatch attempt.
  Called by Phase07TopicDispatch and Phase07ChallengeDispatch when
  state.rounds is non-empty.

DO:
  IF state.rounds[-1].protocol AND state.rounds[-1].protocol != protocol:
    SET status = "skipped"
    SET health = { degraded: true, reason: "protocol changed mid-session" }
    SET contributions = []
    # PROTOCOL_CHANGE_DETECTED: fail-stop, skip dispatch
  ELIF state.rounds[-1].panel != state.panel:
    SET status = "skipped"
    SET health = { degraded: true, reason: "panel mutated mid-session" }
    SET contributions = []
    # PANEL_MUTATION_DETECTED: fail-stop, skip dispatch

RULES:
  - MUST be called by single-agent branches of Phase07TopicDispatch and
    Phase07ChallengeDispatch whenever state.rounds is non-empty
  - MUST NOT dispatch any agent when status is set to "skipped" by this guard
  - Callers MUST check status != "skipped" before proceeding to dispatch
```

```text
UNIT Phase07InvariantValidation

PURPOSE:
  Validate contributions structure; repair once on content violations;
  fail-stop on structural violations or second failure.

STATE:
  attempts_used: int
    default: 1
    scope: per-round

DO:
  RUN validate_contributions(contributions, kind=pending_round_kind,
                             challenged_decisions=challenged_decisions)

  # Structural invariants (short-circuit on first, do not repair):
  #  1. contributions is not a list
  #  2. a contribution has no expert_id
  #  9. a contribution has questions but no relevant field
  #  12. (single-agent only) envelope kind is invalid
  IF structural_errors:
    SET status = "skipped"
    SET health = { degraded: true,
                   reason: "Structural invariant violation {structural_errors[0]}",
                   attempts_used: 1 }
    SET contributions = []
    RETURN

  # Content invariants (accumulate all, apply repair_feedback once):
  #  3. relevant contribution has no questions array
  #  4. a question has no decision_key
  #  5. a question has empty decision_key
  #  6. duplicate decision_key within topic-round (challenge reuse allowed)
  #  7. challenge-round decision_key not in challenged_decisions
  #  8. a question has no text field
  #  10. relevant=false but no reason field
  #  11. topic-round: relevant contribution has no next_topic_proposal
  IF content_errors AND attempts_used == 1:
    SET repair_feedback = { mode, panel_mode, protocol, violations, prior_contributions }
    RE-DISPATCH with repair_feedback signal
    SET attempts_used = 2
    RE-VALIDATE
    IF content_errors remain:
      SET status = "skipped"
      SET health = { degraded: true,
                     reason: "{N} invariant violations despite retry",
                     attempts_used: 2 }
      SET contributions = []
    ELSE:
      SET status = "ok"
      SET health = { degraded: false, reason: null, attempts_used: 2 }

  IF attempts_used >= 2 AND (structural_errors OR content_errors):
    SET status = "skipped"
    SET health = { degraded: true,
                   reason: "{N} invariant violations; retry limit reached",
                   attempts_used: attempts_used }
    SET contributions = []
  ELIF NOT (structural_errors OR content_errors):
    SET status = "ok"
    SET health = { degraded: false, reason: null, attempts_used: attempts_used }
```

```text
UNIT Phase07PostDispatch

PURPOSE:
  Process contributions after dispatch and validation.

DO:
  SET participating = [c for c in contributions if c.relevant]
  SET skipped = [c for c in contributions if not c.relevant]

  IF pending_round_kind == "topic":
    SET state.next_topic_proposals = dedupe_and_merge(
        [c.next_topic_proposal for c in participating])
  # challenge-rounds reuse the most recent topic-round's proposals

RULES:
  - MUST validate every participating topic-round question has non-empty decision_key
  - MUST reject duplicate topic-round decision_key values as malformed expert output
  - MUST NOT render critique-only challenge outputs as skipped (keep in participating)
```

```text
UNIT Phase07Render

PURPOSE:
  Render round output or skipped-round menu to user.

DO:
  SET header = "Round {N} — Topic: {topic_current.text}"
               (topic-round)
               OR
               "Round {N} — Challenge: decisions from round {M} on {topic_current.text}"
               (challenge-round; M = n of challenge_source_round)

  IF status == "skipped":
    EMIT {header}
    EMIT "Round skipped: {health.reason}"
    EMIT_MENU SkippedRoundMenu
    WAIT user.reply
    STOP_TURN

  ELSE:  # status == "ok" or "degraded"
    EMIT {header}
    EMIT "Panel reacted: {len(participating)} contributing, {len(skipped)} skipped."
    IF pending_round_kind == "challenge":
      EMIT "Challenging these decisions (overwrite-on-accept):"
      FOR each key in challenged_decisions.keys():
        EMIT "  - {key}: current value = \"{state.decisions[key]}\""
    EMIT "Questions:"
    FOR each expert contribution:
      EMIT "[{expert_id}] ..." (or skipped: {reason})
    EMIT "Critique (cross-expert pushback): ..."
    EMIT "Reply per question: `{id}: accept | keep | <answer> | skip`"
    EMIT post-round menu with numbered topics + C + W options
    NOTE: Option C is hidden when state.rounds[-1].answer_keys is empty
    EMIT "then: custom: <text> — custom topic"
    EMIT "You can also type `stop` / `enough` / `done` at any point to end now."
    WAIT user.reply
    STOP_TURN

MENU SkippedRoundMenu:
  TITLE: Round skipped
  OPTIONS:
    R (with confirm) ->
      SET health.attempts_used = 1
      SET contributions = []
      SET status = null
      JUMP BACK to dispatch phase for this round
    R (without confirm or malformed) ->
      EMIT one-line clarifier
      EMIT_MENU SkippedRoundMenu
      WAIT user.reply
      STOP_TURN
    W ->
      SET state.topic_current = None
    stop_token ->
      SET state.topic_current = None
    then: custom: <text> ->
      SET pending_round_kind = "topic"
      SET state.topic_current = custom topic
      CONTINUE round loop
```

```text
UNIT Phase07ReplyParsing

PURPOSE:
  Parse user reply to record round state, update decisions, and set next topic/kind.

DO:
  APPEND to state.rounds:
    n = len(rounds)+1
    kind = pending_round_kind
    topic = state.topic_current
    panel_mode = panel_mode
    protocol = protocol (null if fan-out)
    status = status
    health = health
    contributions = contributions
    answers = parsed_answers
    challenged_decisions = challenged_decisions (null on topic-rounds)

  FOR each accepted/custom answer:
    SET key = question.decision_key
    IF challenge-round: REQUIRE key in challenged_decisions.keys()
    WRITE state.decisions[key] = value  # OVERWRITES prior value

  SET rounds[-1].answer_keys = deduped set of touched keys
    NOTE: challenge-rounds: ONLY keys overwritten by accept/<custom>;
          keep/skip answers excluded from answer_keys

  IF user replies skip to question:
    ADD question to state.open_questions
  IF expert returns relevant=false:
    MUST NOT add that expert's unposed questions to state.open_questions
  IF challenge-round keep/skip:
    leave state.decisions[key] unchanged
    MUST NOT add to open_questions

  IF reply answers questions but omits then::
    RECORD answers
    RE-RENDER only post-round menu
    ASK for then: as follow-up
    WAIT user.reply
    STOP_TURN

  # Shortcut semantics
  # "accept all" = accept every currently rendered proposed/counter value
  # "skip rest" = skip every unanswered rendered question
  # "then:" may be sent as follow-up after questions answered

RULES:
  - MUST NOT mutate state on malformed reply (multiple then: tokens, unknown
    choice letter, then: C when C is hidden)
  - MUST re-render post-round menu prefixed with one-line clarifier on malformed reply
  - MUST assert rounds[-1].answer_keys is a list before dispatching then: choice;
    if not a list, treat as malformed-state error and re-ask

  SWITCH then: choice:
    W or stop_token ->
      SET state.topic_current = None
    C ->
      IF state.rounds[-1].answer_keys is empty:
        EMIT "Nothing to challenge — the previous round produced no accepted or custom
              answers. Pick a numbered topic option, `then: custom: <text>`, or `W`
              to wrap instead."
        RE-SHOW post-round menu
        WAIT user.reply
        STOP_TURN
      ELSE:
        SET pending_round_kind = "challenge"
        NOTE: topic_current unchanged; topic_history NOT appended
    1|2|custom ->
      SET pending_round_kind = "topic"
      APPEND state.topic_current.id to state.topic_history
      SET state.topic_current = chosen-or-custom topic

NOTES:
  The C guard in this parse block is the ONLY place that decides whether a
  challenge-round may start; the loop's challenge branch trusts this guard
  and does not re-check.
```

```text
UNIT RoundCapMenu

PURPOSE:
  Present cap-reached menu when state.round_count >= state.BRAINSTORM_MAX_ROUNDS.

MENU RoundCapMenu:
  TITLE: Brainstorm round cap reached ({state.round_count}/{state.BRAINSTORM_MAX_ROUNDS}).
  OPTIONS:
    extend: M (M must be positive integer > current BRAINSTORM_MAX_ROUNDS) ->
      SET state.BRAINSTORM_MAX_ROUNDS = M
      CONTINUE round loop
    accept ->
      SET state.topic_current = None
    stop ->
      CONTINUE wrap-handoff.md WITH reason="manual-cap"
  INVALID:
    EMIT one-line rejection
    EMIT_MENU RoundCapMenu
    WAIT user.reply
    STOP_TURN
```

### Pre-dispatch checkpoint (MANDATORY)

```text
UNIT Phase07PreDispatchCheckpoint

PURPOSE:
  Enforce mandatory pre-dispatch checkpoint before every round dispatch.

RULES:
  - MUST emit exactly one checkpoint line before each round dispatch:
    "- [BRAINSTORM-DISPATCH]: round={N} kind={topic|challenge}
      panel_mode={resolved} mode_source={offer-reply|env|default}
      agent={cf-brainstorm-panel|cf-brainstorm-expert}
      panel_size={len(state.panel)}"
  - MUST emit AFTER agent availability check resolves agent identifier
  - MUST emit BEFORE actual sub-agent dispatch tool call
  - MUST NOT emit when availability check routes to its 3-option menu
  - Omitting is MISSING_DISPATCH_CHECKPOINT failure:
    STOP, re-emit checkpoint line, then continue
```

### Agent availability check (pre-dispatch)

Membership semantics and lifecycle defined in `{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md` § Registered native sub-agent set & INLINE_FALLBACK_THIS_ROUND. Handled by `Phase07AgentAvailabilityCheck` unit above.

### Envelope flattening (single-agent mode)

```text
UNIT Phase07EnvelopeFlattening

PURPOSE:
  Flatten cf-brainstorm-panel envelope into contributions[] array.

DO:
  INITIALIZE contributions = []
  FOR each block in envelope.blocks WHERE block.kind == "independent":
    FOR each row in block.rows:
      EXTRACT expert_id, questions, critique, next_topic_proposal, relevant
      APPEND contribution entry to contributions
  FOR each block in envelope.blocks WHERE block.kind == "critique":
    FOR each row in block.rows:
      EXTRACT expert_id and critique
      MERGE critique into corresponding primary contribution's critique field

  RETURN flattened contributions array

NOTES:
  Open, load, and follow {cf-studio-path}/.core/workflows/generate/phase-0.7/state-schema.md § envelope
  for the full envelope schema.
```

### Expert dispatch contracts

```text
UNIT Phase07ExpertDispatchContracts

PURPOSE:
  Define dispatch contract fields for fan-out and single-agent modes.

NOTES:
  Fan-out mode (panel_mode="fan-out"):
    Each expert dispatch follows JSON contract in
    {cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-expert.md
    Orchestrator-supplied values per expert per round:
      persona = full panel entry {id, persona, focus, rationale}
      topic = full state.topic_current object {id, text, section}
      mode = "topic" or "challenge"
      challenged_decisions = {key: value} snapshot when mode="challenge";
        MUST be omitted or null when mode="topic"
      repair_feedback = (optional) prior round violations and correction hints
      state = brainstorm state with sub-fields:
        ALWAYS: kind, rules_loaded, kit_rules_path, template_path, panel,
                decisions, topic_history
        OPTIONAL when available: example_path, rounds, open_questions,
                session_id, next_topic_proposals

  Single-agent mode (panel_mode="single-agent"):
    Dispatches cf-brainstorm-panel once per round.
    Open, load, and follow
    {cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-panel.md
    for the full contract.
    Orchestrator-supplied values:
      panel = full state.panel array
      topic = full state.topic_current object
      mode = "topic" or "challenge"
      protocol = "independent-then-critique" or "single-pass"
      challenged_decisions = (required on mode="challenge") snapshot of keys under challenge
      repair_feedback = (optional) prior round violations and correction hints
      state = same as fan-out mode
```
