---
description: "Brainstorm round loop — dispatch, INLINE_FALLBACK degradation, question queue, reply parsing, round cap."
name: phase-0.7-round-loop
purpose: Drive topic/challenge rounds, dispatch agents, validate contributions, walk questions, parse post-round choice, enforce round cap.
loaded_by: workflows/generate/phase-0.7/index.md
version: 1.4
---

# Generate Phase 0.7: Round Loop

```text
UNIT Phase07RoundLoopPreconditions
PURPOSE: Enforce pre-loop invariants before any round-level dispatch.
RULES:
  - REQUIRE `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md` loaded before any cf-* sub-agent dispatch
  - REQUIRE INLINE_FALLBACK set before first round (probed by phase-0-dependencies.md)
  - IF INLINE_FALLBACK unset at any round-level dispatch site (e.g. after context-loss):
      follow universal fail-stop in `{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md` § Pre-dispatch discipline
      re-run shared probe before continuing
  - MUST_NOT re-probe per-round when INLINE_FALLBACK is already set
```

```text
UNIT Phase07OrchestrationModes
PURPOSE: Define the two exclusive orchestration strategies per round.
STATE:
  panel_mode: single-agent | fan-out   default: single-agent   scope: per-round
NOTES:
  single-agent: dispatch cf-brainstorm-panel once; one primary expert + optional critique via protocol field; host-independent; INLINE_FALLBACK is no-op.
  fan-out: dispatch all panel members in parallel via cf-brainstorm-expert; no inter-expert live communication; requires native parallelism or degrades via INLINE_FALLBACK.
```

```text
UNIT SilentModeDowngradeGuard
PURPOSE: Prevent dispatch of wrong agent for resolved panel_mode.
RULES:
  - WHEN panel_mode=="single-agent" AND len(state.panel)>1:
      MUST_NOT dispatch one cf-brainstorm-expert per panel member (SILENT_MODE_DOWNGRADE)
  - WHEN panel_mode=="fan-out":
      MUST_NOT dispatch cf-brainstorm-panel
ON_ERROR:
  SILENT_MODE_DOWNGRADE ->
    STOP
    SET CF_PHASE_GATE = armed
    EMIT "silent mode downgrade prevented — wrong agent for resolved panel_mode"
    EMIT_MENU SilentModeDowngradeRecoveryMenu
    WAIT user.reply
    STOP_TURN

MENU SilentModeDowngradeRecoveryMenu:
  TITLE: SILENT_MODE_DOWNGRADE caught: orchestrator attempted wrong agent for resolved panel_mode.
  OPTIONS:
    1 ->
      RE-RESOLVE panel_mode from precedence chain
      DISPATCH correct agent for resolved panel_mode
      CONTINUE round normally
    2 ->
      CONTINUE wrap-handoff.md WITH reason="silent-mode-downgrade"
    W | wrap ->
      CONTINUE wrap-handoff.md WITH reason="silent-mode-downgrade-wrap"
  INVALID:
    EMIT "Please reply with 1, 2, or W."
    WAIT user.reply
    STOP_TURN
NOTES:
  Recovery is NOT the agent-availability menu. The agent is registered; orchestrator used the wrong one for the resolved mode.
```

```text
UNIT Phase07RoundLoop
PURPOSE: Drive topic/challenge rounds: resolve mode, dispatch, validate, ask questions, parse choice, enforce cap.
STATE:
  pending_round_kind: topic | challenge   default: topic
  INLINE_FALLBACK_THIS_ROUND: bool        default: false   scope: per-round

DO:
  WHILE state.topic_current is not None:

    SET contributions = []
    SET status = null
    SET health = { degraded: false, reason: null, attempts_used: 0 }
    SET INLINE_FALLBACK_THIS_ROUND = false

    # Resolve panel_mode precedence: offer-reply config > env var > "single-agent"
    IF pending_round_kind == "topic":
      SET panel_mode = state.run_config.PANEL_MODE_TOPIC OR env(PANEL_MODE_TOPIC) OR "single-agent"
    ELSE:
      SET panel_mode = state.run_config.PANEL_MODE_CHALLENGE OR env(PANEL_MODE_CHALLENGE) OR "single-agent"

    IF panel_mode == "single-agent":
      SET protocol = env(BRAINSTORM_PANEL_PROTOCOL, "independent-then-critique")
    ELSE:
      SET protocol = null

    CONTINUE SilentModeDowngradeGuard
    CONTINUE Phase07AgentAvailabilityCheck

    # Pre-dispatch checkpoint (MANDATORY — emit after availability resolves agent, before dispatch call)
    EMIT "- [BRAINSTORM-DISPATCH]: round={N} kind={topic|challenge} panel_mode={resolved} mode_source={offer-reply|env|default} agent={cf-brainstorm-panel|cf-brainstorm-expert} panel_size={len(state.panel)}"

    IF pending_round_kind == "topic":
      CONTINUE Phase07TopicDispatch
    ELSE:
      CONTINUE Phase07ChallengeDispatch

    CONTINUE Phase07InvariantValidation
    CONTINUE Phase07PostDispatch
    CONTINUE Phase07QuestionQueue
    CONTINUE Phase07PostRoundChoiceParsing

    # Bug fix: increment BEFORE STOP_TURN so cap check executes each iteration
    SET state.round_count = state.round_count + 1
    IF state.round_count >= state.BRAINSTORM_MAX_ROUNDS:
      EMIT_MENU RoundCapMenu
      WAIT user.reply
      STOP_TURN

  LOAD {cf-studio-path}/.core/workflows/generate/phase-0.7/wrap-handoff.md

RULES:
  - MUST emit pre-dispatch checkpoint after availability check resolves agent AND before dispatch tool call
  - MUST_NOT emit checkpoint when availability check routes to its 3-option menu
  - Omitting checkpoint is MISSING_DISPATCH_CHECKPOINT failure: STOP, re-emit checkpoint, then continue
  - INLINE_FALLBACK_THIS_ROUND is per-round scope; see sub-agent-dispatch.md § Registered native sub-agent set & INLINE_FALLBACK_THIS_ROUND
```

```text
UNIT Phase07AgentAvailabilityCheck
PURPOSE: Verify resolved agent is in host's registered native sub-agent set before dispatch.
DO:
  VERIFY resolved agent is in host registered native sub-agent set

  IF agent unavailable AND INLINE_FALLBACK == false:
    EMIT_MENU AgentUnavailableMenu
    WAIT user.reply
    STOP_TURN

  IF INLINE_FALLBACK == true:
    NOTE: inline-panel option is recommended default; surface as suggested choice

MENU AgentUnavailableMenu:
  TITLE: Resolved brainstorm agent `{agent}` is not registered as a native sub-agent in this host.
  OPTIONS:
    1 ->
      SET INLINE_FALLBACK_THIS_ROUND = true
      INLINE matching agent contract for this round only
    2 ->
      IF pending_round_kind == "topic":
        SET state.run_config.PANEL_MODE_TOPIC = other_value(current_mode)
      ELSE:
        SET state.run_config.PANEL_MODE_CHALLENGE = other_value(current_mode)
      # other_value("single-agent")="fan-out"; other_value("fan-out")="single-agent"; other mode key unchanged
      RE-RESOLVE panel_mode for current round
      CONTINUE Phase07AgentAvailabilityCheck
    3 ->
      CONTINUE wrap-handoff.md WITH reason="agent-unavailable"
    W | wrap ->
      CONTINUE wrap-handoff.md WITH reason="agent-unavailable-wrap"
  INVALID:
    EMIT "Reply with 1, 2, 3, or W."
    WAIT user.reply
    STOP_TURN
```

```text
UNIT Phase07TopicDispatch
PURPOSE: Dispatch panel for topic-round based on resolved panel_mode.
DO:
  REQUIRE pending_round_kind == "topic"

  IF panel_mode == "fan-out":
    PARALLEL_DISPATCH [cf-brainstorm-expert for each e in state.panel]
      WITH: persona=e, topic=state.topic_current, state,
            resource_context=state.resource_context, mode="topic"
    SET contributions = all_results

  ELSE:  # single-agent
    IF state.rounds is non-empty:
      CONTINUE Phase07MidSessionMutationGuard
    IF status != "skipped":
      DISPATCH cf-brainstorm-panel
        WITH: panel=state.panel, topic=state.topic_current, state,
              resource_context=state.resource_context, mode="topic", protocol=protocol
      SET contributions = flatten_envelope(result)
```

```text
UNIT Phase07ChallengeDispatch
PURPOSE: Dispatch panel for challenge-round based on resolved panel_mode.
NOTES: Precondition state.rounds non-empty and rounds[-1].answer_keys non-empty is enforced by Phase07PostRoundChoiceParsing C-guard.
DO:
  REQUIRE pending_round_kind == "challenge"
  SET challenge_source_round = state.rounds[-1]
  SET challenge_keys = challenge_source_round.answer_keys
  SET challenged_decisions = { k: state.decisions[k] for k in challenge_keys }

  IF panel_mode == "fan-out":
    PARALLEL_DISPATCH [cf-brainstorm-expert for each e in state.panel]
      WITH: persona=e, topic=state.topic_current, state,
            resource_context=state.resource_context,
            mode="challenge", challenged_decisions=challenged_decisions
    SET contributions = all_results

  ELSE:  # single-agent; state.rounds guaranteed non-empty by precondition
    CONTINUE Phase07MidSessionMutationGuard
    IF status != "skipped":
      DISPATCH cf-brainstorm-panel
        WITH: panel=state.panel, topic=state.topic_current, state,
              resource_context=state.resource_context,
              mode="challenge", challenged_decisions=challenged_decisions, protocol=protocol
      SET contributions = flatten_envelope(result)
```

```text
UNIT Phase07MidSessionMutationGuard
PURPOSE: Detect mid-session protocol or panel mutations; set fail-stop skip before dispatch.
DO:
  IF state.rounds[-1].protocol AND state.rounds[-1].protocol != protocol:
    SET status = "skipped"
    SET health = { degraded: true, reason: "protocol changed mid-session" }
    SET contributions = []
  ELIF state.rounds[-1].panel != state.panel:
    SET status = "skipped"
    SET health = { degraded: true, reason: "panel mutated mid-session" }
    SET contributions = []

RULES:
  - MUST be called by single-agent branches of Phase07TopicDispatch and Phase07ChallengeDispatch when state.rounds is non-empty
  - MUST_NOT dispatch any agent when status == "skipped"
  - Callers MUST check status != "skipped" before proceeding to dispatch
```

```text
UNIT Phase07InvariantValidation
PURPOSE: Validate contributions structure; repair once on content violations; fail-stop on structural violations or second failure.
STATE:
  attempts_used: int   default: 1   scope: per-round

DO:
  RUN validate_contributions(contributions, kind=pending_round_kind,
                             challenged_decisions=challenged_decisions)

  # Structural invariants (short-circuit; no repair):
  #  1. contributions not a list  2. contribution has no expert_id
  #  9. contribution has questions but no relevant field  12. (single-agent) invalid envelope kind
  IF structural_errors:
    SET status = "skipped"
    SET health = { degraded: true, reason: "Structural invariant violation {structural_errors[0]}", attempts_used: 1 }
    SET contributions = []
    RETURN

  # Content invariants (accumulate all; repair once):
  #  3. relevant contribution has no questions array  4. question has no decision_key
  #  5. empty decision_key  6. duplicate decision_key (topic-round)
  #  7. challenge decision_key not in challenged_decisions  8. question has no text
  #  10. relevant=false but no reason  11. topic-round relevant contribution has no next_topic_proposal
  IF content_errors AND attempts_used == 1:
    SET repair_feedback = { mode, panel_mode, protocol, violations, prior_contributions }
    RE-DISPATCH with repair_feedback signal
    SET attempts_used = 2
    RE-VALIDATE
    IF content_errors remain:
      SET status = "skipped"
      SET health = { degraded: true, reason: "{N} invariant violations despite retry", attempts_used: 2 }
      SET contributions = []
    ELSE:
      SET status = "ok"
      SET health = { degraded: false, reason: null, attempts_used: 2 }

  IF attempts_used >= 2 AND (structural_errors OR content_errors):
    SET status = "skipped"
    SET health = { degraded: true, reason: "{N} invariant violations; retry limit reached", attempts_used: attempts_used }
    SET contributions = []
  ELIF NOT (structural_errors OR content_errors):
    SET status = "ok"
    SET health = { degraded: false, reason: null, attempts_used: attempts_used }
```

```text
UNIT Phase07PostDispatch
PURPOSE: Process contributions after validation; build one-question-at-a-time intake queue.
DO:
  SET participating = [c for c in contributions if c.relevant]
  SET skipped_experts = [c for c in contributions if not c.relevant]

  IF pending_round_kind == "topic":
    SET state.next_topic_proposals = dedupe_and_merge([c.next_topic_proposal for c in participating])
  # challenge-rounds reuse the most recent topic-round's proposals

  SET question_queue = flatten questions from participating contributions
    ordered by state.panel order then each contribution.questions order
  SET current_question_index = 1

RULES:
  - MUST validate every participating topic-round question has non-empty decision_key
  - MUST reject duplicate topic-round decision_key values as malformed expert output
  - parse-side guard: challenge choices are valid only when rounds[-1].answer_keys is non-empty
  - MUST_NOT render critique-only challenge outputs as skipped (keep in participating)
  - MUST NOT render critique-only challenge outputs as skipped
  - MUST_NOT ask the user to answer the whole question_queue in one reply
```

```text
UNIT Phase07QuestionQueue
PURPOSE: Render one brainstorm question per user turn; collect reaction; show post-round menu only after queue is complete.
DO:
  SET header = "Round {N} — Topic: {topic_current.text}"                          # topic-round
            OR "Round {N} — Challenge: decisions from round {M} on {topic_current.text}"  # challenge-round; M = n of challenge_source_round

  IF status == "skipped":
    EMIT {header}
    EMIT "Round skipped: {health.reason}"
    EMIT_MENU SkippedRoundMenu
    WAIT user.reply
    STOP_TURN

  ELSE:
    APPEND to state.rounds:
      n=len(rounds)+1, kind=pending_round_kind, topic=state.topic_current,
      panel_mode=panel_mode, protocol=protocol, status=status, health=health,
      contributions=contributions, question_queue=question_queue,
      current_question_index=1, answers=[], answer_keys=[],
      challenged_decisions=challenged_decisions, next_topic_chosen=null

    EMIT {header}
    EMIT "Panel reacted: {len(participating)} contributing, {len(skipped_experts)} skipped."
    IF skipped_experts non-empty:
      EMIT "Skipped personas: {persona}: {reason}" for each
    IF pending_round_kind == "challenge":
      EMIT "Challenging these decisions (overwrite-on-accept):"
      FOR each key in challenged_decisions.keys():
        EMIT "  - {key}: current value = \"{state.decisions[key]}\""

    IF question_queue is empty:
      EMIT "No actionable questions were produced. Critique summary: {critique}"
      CONTINUE Phase07PostRoundMenu

    CONTINUE Phase07AskCurrentQuestion

RULES:
  - MUST show exactly one pending question per turn
  - MUST_NOT dump full question_queue to user
  - MUST NOT dump the full question_queue to the user
  - MUST include concise context per question: expert/persona, why it matters, proposed default, relevant critique
  - MUST offer numbered answer options for each question
```

```text
UNIT Phase07AskCurrentQuestion
PURPOSE: Ask exactly one pending brainstorm question with answer options.
DO:
  SET q = first state.rounds[-1].question_queue item with status == "pending"

  IF no pending q:
    CONTINUE Phase07PostRoundMenu

  EMIT:
    "Question {q.queue_index}/{len(question_queue)} — {expert_id}"
    "{q.text}"
    "Why it matters: {q.rationale}"
    "Proposed default: {q.proposed_default}"
    "Possible answer directions:"
    "- Accept the proposed default as-is."
    "- Adjust the default with your constraints or preference."
    "- Skip to keep it open/unanswered for later PRD/DESIGN/ADR handling."
    "Decision key: {q.decision_key}"
    IF challenge-round: "Current value: {state.decisions[q.decision_key]}"

  EMIT_MENU QuestionReactionMenu
  WAIT user.reply
  STOP_TURN

MENU QuestionReactionMenu:
  TITLE: Reply with a number, or write a custom answer.
  OPTIONS:
    1 accept-default ->
      record q.proposed_default as answer
      APPEND {decision_key: q.decision_key, answer: q.proposed_default,
              source: "accepted_default"} to state.rounds[-1].answers
      APPEND q.decision_key to state.rounds[-1].answer_keys
      mark q.status = "accepted_default"
      SET state.decisions[q.decision_key] = q.proposed_default
      update state.decisions[q.decision_key]
      CONTINUE Phase07AskCurrentQuestion
    2 custom-answer ->
      IF reply has no custom text: ask for custom answer, WAIT user.reply, STOP_TURN
      record user text as answer
      APPEND {decision_key: q.decision_key, answer: user_text,
              source: "custom_answer"} to state.rounds[-1].answers
      APPEND q.decision_key to state.rounds[-1].answer_keys
      mark q.status = "answered"
      SET state.decisions[q.decision_key] = user_text
      CONTINUE Phase07AskCurrentQuestion
    3 skip ->
      APPEND to state.open_questions: { question_id=q.question_id, decision_key=q.decision_key, text=q.text, reason="user_skipped", source="brainstorm" }
      SET reason = "user_skipped"
      mark q.status = "open_unanswered"
      CONTINUE Phase07AskCurrentQuestion
    4 keep-current ->
      REQUIRE challenge-round; IF topic-round re-render menu
      leave state.decisions[q.decision_key] unchanged
      mark q.status = "kept_prior"
      CONTINUE Phase07AskCurrentQuestion
    5 wrap-save ->
      SET state.topic_current = None
      CONTINUE wrap-handoff.md WITH reason="question-wrap"
  INVALID:
    IF reply is non-empty free text: treat as option 2 custom-answer
    ELSE:
      IF challenge-round:
        EMIT "Reply with 1 accept default, 2 custom answer, 3 skip, 4 keep current, 5 wrap, or a custom answer."
      ELSE:
        EMIT "Reply with 1 accept default, 2 custom answer, 3 skip, 5 wrap, or a custom answer."
      WAIT user.reply
      STOP_TURN

RULES:
  - option 4 MUST be hidden in topic-rounds; reply 4 in topic-round re-renders menu
  - "accept"/"yes"/"default" -> option 1; "skip" -> option 3; "keep" -> option 4 (challenge only); "W"/"wrap"/"save"/"stop"/"enough"/"done" -> option 5
  - After each recorded reaction update rounds[-1].answers and rounds[-1].answer_keys immediately
  - answer_keys includes only accepted-default/custom topic answers and accepted-default/custom challenge overwrites; skip/keep excluded
  - skip MUST_NOT update state.decisions
  - skip MUST NOT update state.decisions
  - skip MUST preserve question as open_unanswered for downstream PRD/DESIGN/ADR/FEATURE
  - MUST always show wrap/save as user-facing option

MENU SkippedRoundMenu:
  TITLE: Round skipped.
  OPTIONS:
    R (with confirm) ->
      SET health = { degraded: false, reason: null, attempts_used: 0 }
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
      CONTINUE wrap-handoff.md WITH reason="skipped-round-wrap"
    stop_token ->
      SET state.topic_current = None
      CONTINUE wrap-handoff.md WITH reason="skipped-round-wrap"
    custom: <text> ->
      SET pending_round_kind = "topic"
      SET state.topic_current = custom topic
      CONTINUE round loop
```

```text
UNIT Phase07PostRoundMenu
PURPOSE: After all questions resolved, offer next topic, challenge, or wrap.
DO:
  EMIT "Round {N} question queue complete."
  EMIT "Recorded decisions this round: {rounds[-1].answer_keys or 'none'}"
  EMIT "Critique summary: {critique summary from participating contributions}"
  EMIT post-round menu: numbered topics + C (hidden when rounds[-1].answer_keys is empty) + W options
  EMIT "custom: <text> — custom next topic"
  EMIT "W / wrap — open the wrap/save menu now."
  WAIT user.reply
  STOP_TURN

RULES:
  - MUST_NOT show before every pending question is resolved
  - MUST NOT show this menu before every pending question is resolved
  - MUST always show W / wrap as user-facing option
```

```text
UNIT Phase07PostRoundChoiceParsing
PURPOSE: Parse post-round next-action reply after all question reactions are recorded.
DO:
  REQUIRE every state.rounds[-1].question_queue item status != "pending"

RULES:
  - MUST_NOT mutate state on malformed reply (multiple tokens, unknown letter, C when hidden)
  - MUST re-render post-round menu prefixed with one-line clarifier on malformed reply
  - MUST assert rounds[-1].answer_keys is a list; if not, treat as malformed-state error and re-ask

  SWITCH user choice:
    W | stop_token ->
      SET state.topic_current = None
      CONTINUE wrap-handoff.md WITH reason="post-round-wrap"
    C ->
      IF rounds[-1].answer_keys is empty:
        EMIT "Nothing to challenge — no accepted or custom answers. Pick a numbered topic, `custom: <text>`, or `W`."
        RE-SHOW post-round menu
        WAIT user.reply
        STOP_TURN
      ELSE:
        SET pending_round_kind = "challenge"
        # topic_current unchanged; topic_history NOT appended
    1 | 2 | custom ->
      IF numeric reply:
        REQUIRE chosen topic number is in the rendered topic option range 1..N
        IF out of range: RE-SHOW post-round menu with one-line clarifier; WAIT user.reply; STOP_TURN
      SET pending_round_kind = "topic"
      APPEND state.topic_current.id to state.topic_history
      SET state.topic_current = chosen-or-custom topic

NOTES:
  The C guard here is the ONLY place that authorises a challenge-round; the loop's challenge branch trusts this guard.
```

```text
UNIT RoundCapMenu
PURPOSE: Present cap-reached menu when state.round_count >= state.BRAINSTORM_MAX_ROUNDS.
MENU RoundCapMenu:
  TITLE: Brainstorm round cap reached ({state.round_count}/{state.BRAINSTORM_MAX_ROUNDS}).
  OPTIONS:
    extend: M (M positive integer > current BRAINSTORM_MAX_ROUNDS) ->
      SET state.BRAINSTORM_MAX_ROUNDS = M
      CONTINUE round loop
    W | wrap | accept ->
      SET state.topic_current = None
      CONTINUE wrap-handoff.md WITH reason="manual-cap"
    stop ->
      CONTINUE wrap-handoff.md WITH reason="manual-cap"
  INVALID:
    EMIT one-line rejection
    EMIT_MENU RoundCapMenu
    WAIT user.reply
    STOP_TURN
```

```text
UNIT Phase07WrapOptionInvariant
PURPOSE: Ensure user can exit to wrap/save at every brainstorm interaction point.
RULES:
  - Every user-facing brainstorm menu after brainstorm acceptance MUST expose a W or wrap option
  - Wrap MUST route to {cf-studio-path}/.core/workflows/generate/phase-0.7/wrap-handoff.md
  - Wrap MUST_NOT imply discard; wrap-handoff owns save/generate/analyze/continue routing
```

```text
UNIT Phase07EnvelopeFlattening
PURPOSE: Flatten cf-brainstorm-panel envelope into contributions[] array.
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
  RETURN contributions

NOTES:
  Full envelope schema: {cf-studio-path}/.core/workflows/generate/phase-0.7/state-schema.md § envelope
```

```text
UNIT Phase07ExpertDispatchContracts
PURPOSE: Define dispatch contract fields for fan-out and single-agent modes.
RULES:
  Fan-out (panel_mode="fan-out"):
    - MUST open, load, and follow {cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-expert.md per expert dispatch
    - Final prompt MUST preserve canonical input payload, output contract, parse-time invariants, completion gate, final emit instruction
    - Fail-closed per sub-agent-dispatch.md § SubAgentContractReadGate if contract missing/unreadable/ambiguous
    - Per-expert per-round fields: persona, topic, mode, challenged_decisions (required when mode="challenge"; omit/null when mode="topic"), repair_feedback (optional)
    - state sub-fields ALWAYS: kind, rules_loaded, kit_rules_path, template_path, panel, decisions, topic_history, resource_context
    - state sub-fields OPTIONAL when available: example_path, rounds, open_questions, session_id, next_topic_proposals

  Single-agent (panel_mode="single-agent"):
    - MUST open, load, and follow {cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-panel.md
    - Final prompt MUST preserve canonical contract sections for input, envelope shape, parse-time invariants, completion gate
    - MUST_NOT replace canonical schema with a short bullet summary when it can be carried forward directly
    - Fields: panel, topic, resource_context, mode, protocol, challenged_decisions (required on mode="challenge"), repair_feedback (optional), state (same as fan-out)
```
