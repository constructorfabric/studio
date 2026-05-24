---
description: "Invoke when the brainstorm round loop runs — manages question dispatch, user answers, state.round_count cap, and topic selection."
name: phase-0.7-round-loop
purpose: Brainstorm round loop — parallel_dispatch of experts or single-agent panel dispatch, INLINE_FALLBACK degradation, render contract, user reply parsing, and retry flow
loaded_by: workflows/generate/phase-0.7/index.md
version: 1.1
---

### Round loop

Requires: `workflows/shared/inline-fallback-probe.md` before any `cf-constructor-*` sub-agent dispatch.

Precondition: INLINE_FALLBACK must be set before the first round (already probed by `workflows/generate/phase-0-dependencies.md` at workflow start). If `INLINE_FALLBACK` is unset at any round-level dispatch site (e.g., after a context-loss / compaction event), follow the universal fail-stop rule in `skills/cypilot/sub-agent-dispatch.md` § Pre-dispatch discipline and re-run the shared probe before continuing. Do NOT re-probe per-round when `INLINE_FALLBACK` is already set.

**Orchestration modes:** This loop supports two exclusive orchestration strategies per round, controlled by environment variables:
- **Fan-out (default):** `PANEL_MODE_TOPIC` and `PANEL_MODE_CHALLENGE` both default to `"fan-out"`. When set to `"fan-out"`, the orchestrator dispatches all relevant panel members in parallel using the legacy `cf-constructor-brainstorm-expert` contract. Each expert independently produces questions/contributions; the orchestrator collects all responses before aggregation.
- **Single-agent:** When `PANEL_MODE_TOPIC` or `PANEL_MODE_CHALLENGE` is set to `"single-agent"`, the orchestrator dispatches the new `cf-constructor-brainstorm-panel` agent instead. That agent runs the full round logic with one expert as primary; subsequent experts provide optional critique via the `protocol` field. Single-agent is opt-in per round kind; fan-out is the legacy default and remains unchanged in that branch.

**Inline-fallback note:** When `INLINE_FALLBACK=true`, parallel_dispatch degrades to sequential; experts-are-independent guarantee is best-effort in that mode (per `skills/cypilot/sub-agent-dispatch.md` Mode B). In single-agent mode, INLINE_FALLBACK is a no-op: single-agent orchestration is inherently sequential.

The loop drives two kinds of rounds, chosen by the user after every round finishes:

- **topic-round** (`kind="topic"`) — explore `state.topic_current`; panel contributes 1-3 questions each with proposed defaults + a `next_topic_proposal`.
- **challenge-round** (`kind="challenge"`) — re-open decisions from the most recent completed round; panel critiques those decisions from each persona's POV and offers counter-proposals. Challenge results can themselves be challenged when the user accepted or wrote counter-values. Topic does not advance; `next_topic_proposal` is ignored (kept from the most recent topic-round).

```text
pending_round_kind = "topic"        # first iteration is always a topic-round
while state.topic_current is not None:
  # Read orchestration mode flags independently for each round kind
  panel_mode_topic = env("PANEL_MODE_TOPIC", "fan-out")
  panel_mode_challenge = env("PANEL_MODE_CHALLENGE", "fan-out")
  
  if pending_round_kind == "topic":
    panel_mode = panel_mode_topic
  else:  # pending_round_kind == "challenge"
    panel_mode = panel_mode_challenge
  
  # Select protocol (used only when panel_mode="single-agent")
  protocol = env("BRAINSTORM_PANEL_PROTOCOL", "independent-then-critique")
  
  # Dispatch phase — conditional on panel_mode
  challenged_decisions = None
  if pending_round_kind == "topic":
    if panel_mode == "fan-out":
      # Legacy parallel dispatch: all experts independently
      contributions = parallel_dispatch([
        cf-constructor-brainstorm-expert(
            persona = e, topic = state.topic_current, state,
            mode = "topic")
        for e in state.panel
      ])
    else:  # panel_mode == "single-agent"
      # Pre-dispatch G1/G2 guards (only when prior rounds exist)
      if state.rounds:
        if state.rounds[-1].protocol and state.rounds[-1].protocol != protocol:
          status = "skipped"
          health = { degraded: true, reason: "protocol changed mid-session" }
          contributions = []
          # PROTOCOL_CHANGE_DETECTED: fail-stop, skip dispatch
        elif state.rounds[-1].panel != state.panel:
          status = "skipped"
          health = { degraded: true, reason: "panel mutated mid-session" }
          contributions = []
          # PANEL_MUTATION_DETECTED: fail-stop, skip dispatch
        else:
          # New single-agent panel dispatch
          envelope = cf-constructor-brainstorm-panel(
              panel = state.panel, topic = state.topic_current, state,
              mode = "topic", protocol = protocol)
          # Flatten envelope into contributions[] (see state-schema.md § envelope)
          contributions = flatten_envelope(envelope)
      else:
        # New single-agent panel dispatch
        envelope = cf-constructor-brainstorm-panel(
            panel = state.panel, topic = state.topic_current, state,
            mode = "topic", protocol = protocol)
        # Flatten envelope into contributions[] (see state-schema.md § envelope)
        contributions = flatten_envelope(envelope)
      
  else:  # pending_round_kind == "challenge"
    # The parse-side guard (see Parse block) refuses `C` when
    # `state.rounds[-1].answer_keys` is empty BEFORE this branch is entered,
    # so by precondition `state.rounds` is non-empty and `answer_keys` is
    # non-empty here. The orchestrator MUST NOT enter this branch otherwise.
    challenge_source_round = state.rounds[-1]
    challenge_keys = challenge_source_round.answer_keys
    challenged_decisions = { k: state.decisions[k] for k in challenge_keys }
    
    if panel_mode == "fan-out":
      # Legacy parallel dispatch: all experts independently
      contributions = parallel_dispatch([
        cf-constructor-brainstorm-expert(
            persona = e, topic = state.topic_current, state,
            mode = "challenge",
            challenged_decisions = challenged_decisions)
        for e in state.panel
      ])
    else:  # panel_mode == "single-agent"
      # Pre-dispatch G1/G2 guards (only when prior rounds exist)
      if state.rounds:
        if state.rounds[-1].protocol and state.rounds[-1].protocol != protocol:
          status = "skipped"
          health = { degraded: true, reason: "protocol changed mid-session" }
          contributions = []
          # PROTOCOL_CHANGE_DETECTED: fail-stop, skip dispatch
        elif state.rounds[-1].panel != state.panel:
          status = "skipped"
          health = { degraded: true, reason: "panel mutated mid-session" }
          contributions = []
          # PANEL_MUTATION_DETECTED: fail-stop, skip dispatch
        else:
          # New single-agent panel dispatch
          envelope = cf-constructor-brainstorm-panel(
              panel = state.panel, topic = state.topic_current, state,
              mode = "challenge", challenged_decisions = challenged_decisions,
              protocol = protocol)
          # Flatten envelope into contributions[]
          contributions = flatten_envelope(envelope)
      else:
        # New single-agent panel dispatch
        envelope = cf-constructor-brainstorm-panel(
            panel = state.panel, topic = state.topic_current, state,
            mode = "challenge", challenged_decisions = challenged_decisions,
            protocol = protocol)
        # Flatten envelope into contributions[]
        contributions = flatten_envelope(envelope)
  
  # ---- Invariant validation (applies to both orchestration modes) ----
  # Validate contributions structure and detect invariant violations.
  # If violations are detected and attempts_used < 2, construct repair_feedback
  # and dispatch once more before persisting. On second failure or at
  # attempts_used == 2, mark status="skipped" and set health.degraded=true.
  #
  # 12 Invariant violations grouped by category:
  #   Structural (short-circuit on first, do not continue):
  #     1. contributions is not a list
  #     2. a contribution has no expert_id
  #     9. a contribution has questions but no relevant field
  #     12. (in single-agent mode only) envelope kind is invalid
  #
  #   Content (accumulate all violations found, apply repair_feedback once):
  #     3. a relevant contribution has no questions array
  #     4. a question has no decision_key
  #     5. a question has an empty decision_key
  #     6. duplicate decision_key within topic-round (challenge-round reuse is allowed)
  #     7. decision_key in challenge-round not in challenged_decisions
  #     8. a question has no text field
  #     10. relevant=false but no reason field
  #     11. topic-round: a relevant contribution has no next_topic_proposal
  #
  # Upon first structural violation: set status="skipped", health.degraded=true,
  # health.reason="Structural invariant violation {N}", contributions=[],
  # do NOT dispatch repair. End round.
  #
  # Upon content violations (accumulated across all contributions):
  # If attempts_used == 1:
  #   - Construct repair_feedback object with violation details and re-dispatch once.
  #   - If re-dispatch succeeds with no new violations: continue normally with
  #     status="ok" (or "degraded" if SLA was exceeded), health.attempts_used=2.
  #   - If re-dispatch fails with violations: set status="skipped",
  #     health.degraded=true, health.reason="{N} invariant violations despite retry",
  #     contributions=[], answer_keys=[], do NOT render.
  # If attempts_used >= 2:
  #   - Skip the current round, set status="skipped", health.degraded=true,
  #     health.reason="{N} invariant violations; retry limit reached",
  #     contributions=[], answer_keys=[].
  
  # Placeholder: run validation
  validation_result = validate_contributions(contributions, kind=pending_round_kind, 
                                             challenged_decisions=challenged_decisions)
  structural_errors = validation_result.structural_errors
  content_errors = validation_result.content_errors
  attempts_used = 1  # Track retry attempts per round
  
  while True:  # Retry loop (max 2 iterations per round)
    if structural_errors and attempts_used == 1:
      # Structural violation: short-circuit, do not repair
      status = "skipped"
      health = { degraded: true, reason: f"Structural invariant violation {structural_errors[0]}", 
                 attempts_used: 1 }
      contributions = []
      break  # Exit retry loop
    elif content_errors and attempts_used == 1:
      # Content violations: attempt repair with repair_feedback
      repair_feedback = {
        mode: pending_round_kind,
        panel_mode: panel_mode,
        protocol: protocol,
        violations: content_errors,
        prior_contributions: contributions
      }
      
      # Re-dispatch with repair_feedback signal
      if pending_round_kind == "topic":
        if panel_mode == "fan-out":
          contributions = parallel_dispatch([
            cf-constructor-brainstorm-expert(
                persona = e, topic = state.topic_current, state,
                mode = "topic", repair_feedback = repair_feedback)
            for e in state.panel
          ])
        else:  # single-agent
          envelope = cf-constructor-brainstorm-panel(
              panel = state.panel, topic = state.topic_current, state,
              mode = "topic", protocol = protocol, 
              repair_feedback = repair_feedback)
          contributions = flatten_envelope(envelope)
      else:  # challenge
        if panel_mode == "fan-out":
          contributions = parallel_dispatch([
            cf-constructor-brainstorm-expert(
                persona = e, topic = state.topic_current, state,
                mode = "challenge",
                challenged_decisions = challenged_decisions,
                repair_feedback = repair_feedback)
            for e in state.panel
          ])
        else:  # single-agent
          envelope = cf-constructor-brainstorm-panel(
              panel = state.panel, topic = state.topic_current, state,
              mode = "challenge", challenged_decisions = challenged_decisions,
              protocol = protocol, repair_feedback = repair_feedback)
          contributions = flatten_envelope(envelope)
      
      attempts_used = 2
      validation_result = validate_contributions(contributions, kind=pending_round_kind,
                                                 challenged_decisions=challenged_decisions)
      structural_errors = validation_result.structural_errors
      content_errors = validation_result.content_errors
      
      if content_errors:
        # Second failure: mark as skipped
        status = "skipped"
        health = { degraded: true, 
                   reason: f"{len(content_errors)} invariant violations despite retry",
                   attempts_used: 2 }
        contributions = []
        break  # Exit retry loop
      else:
        # Repair successful
        status = "ok"
        health = { degraded: false, reason: null, attempts_used: 2 }
        break  # Exit retry loop normally
    else:
      # No errors or attempts_used >= 2
      if structural_errors or content_errors:
        status = "skipped"
        health = { degraded: true,
                   reason: f"{len(structural_errors or content_errors)} invariant violations; retry limit reached",
                   attempts_used: attempts_used }
        contributions = []
      else:
        status = "ok"
        health = { degraded: false, reason: null, attempts_used: attempts_used }
      break  # Exit retry loop
  
  # Post-dispatch processing
  participating = [c for c in contributions if c.relevant]
  skipped       = [c for c in contributions if not c.relevant]
  # Only topic-rounds refresh the next-topic proposal cache; challenge-rounds
  # reuse the most recent topic-round's proposals so the post-round menu can
  # keep offering them.
  if pending_round_kind == "topic":
    state.next_topic_proposals = dedupe_and_merge(
      [c.next_topic_proposal for c in participating])
  # In challenge mode, critique-only challenge outputs stay in `participating`;
  # do not render critique-only challenge outputs as skipped merely because
  # they have no questions.
  # Topic-round decision keys are write targets, not display labels. Before
  # rendering a topic-round, validate that every participating question has a
  # non-empty `decision_key` and that all topic-round `decision_key` values are
  # unique across the rendered questions. MUST reject duplicate topic-round `decision_key` values as malformed expert output instead of allowing
  # last-write-wins overwrites. Challenge-round questions intentionally reuse
  # existing keys from `challenged_decisions`.
  # ---- Render ----
  header  = "Round {N} — Topic: {topic_current.text}"   (topic-round)
            or
            "Round {N} — Challenge: decisions from round {M} on {topic_current.text}"
            (challenge-round; M = n of challenge_source_round)
  
  # If status="skipped", skip rendering and go directly to post-round menu
  # with retry option.
  if status == "skipped":
    present to user:
      {header}
      Round skipped: {health.reason}
      | Option | Action |
      |---|---|
      | R      | Retry this round (confirm-gated) |
      | W      | Wrap up brainstorm (no more topics) |
      | then: custom: <text> | Skip to a custom topic (topic-rounds only) |
      
      Parse retry confirmation:
        - `R` with confirm: reset health.attempts_used=1, contributions=[],
          status=null; jump back to dispatch phase for this round.
        - `R` without confirm or malformed: re-show the skipped menu with
          one-line clarifier.
        - `W` or stop-token: state.topic_current = None; break (end brainstorm).
        - `then: custom: <text>`: set pending_round_kind="topic",
          state.topic_current = custom topic, continue the loop.
  else:
    # Normal render (status="ok" or "degraded")
    present to user:
      {header}
      Panel reacted: {len(participating)} contributing, {len(skipped)} skipped.
      [challenge-round only]
      Challenging these decisions (overwrite-on-accept):
        - {key1}: current value = "{state.decisions[key1]}"
        - {key2}: current value = "{state.decisions[key2]}"
      Questions:
        [E1 Domain Architect]
          E1Q1. {text}
                Target: {decision_key}
                Proposed: {proposed_default}    # in challenge-mode this is the
                                                # counter-proposal that overwrites
                                                # the current value on accept
                Why: {rationale}
        [E2 Security Reviewer] — skipped: {reason}
      Critique (cross-expert pushback):
        [E1] {critique}
      Reply per question: `E1Q1: accept | keep | <answer> | skip`
        accept = take the proposed/counter value
        keep   = (challenge-round only) keep the current decision unchanged
        skip   = leave unanswered (moves to state.open_questions on topic-rounds;
                 on challenge-rounds keep = skip semantically, but `keep` is
                 preferred for clarity)
        Note: on challenge-rounds, `keep` and `skip` produce the same effect
        (no overwrite); prefer `keep`.
      After answers, what next?
        1. {next_topic_proposals[0].text}  — proposed by {experts}
        2. {next_topic_proposals[1].text}  — proposed by {experts}
        C. Challenge the decisions just made (same topic, panel pushes back)
        W. Wrap up brainstorm (no more topics)
      then: custom: <text> — custom topic
      Reply with `<answers> + then: <1|2|C|W>` or `then: custom: <text>`.
      Shortcuts: `accept all; then: <1|2|C|W>`, `skip rest`, and `then:` may be sent as a follow-up when the user answered only the questions first.
      You can also type `stop` / `enough` / `done` at any point to end now.
      Option `C` is hidden when there are no decisions to challenge (e.g. the user skipped every question, or the last round itself was a challenge where nothing was overwritten).
  
  # ---- Parse ----
  parse user reply:
    - append a new entry to state.rounds with n = len(rounds)+1,
      kind = pending_round_kind, topic = state.topic_current,
      panel_mode = panel_mode, protocol = protocol (null if fan-out),
      status = status, health = health,
      contributions = contributions, answers = parsed_answers,
      challenged_decisions = challenged_decisions   # null on topic-rounds
    - decision key derivation: for each accepted/custom answer,
      `key = question.decision_key`; in challenge-rounds this MUST be one
      of `challenged_decisions.keys()`
    - for each accepted/custom answer, write state.decisions[key] = value
      (OVERWRITES any prior value — challenge-rounds intentionally clobber
      the topic-round value when the user accepted a counter-proposal)
    - record the set of touched keys as rounds[-1].answer_keys (deduped).
      On challenge-rounds, `answer_keys` lists ONLY keys whose value was
      actually overwritten by an `accept` / `<custom>` answer; `keep` /
      `skip` answers are excluded from `answer_keys` (the value was
      re-affirmed, not rewritten).
    - When the user replies `skip` to a question, add that question to `state.open_questions`.
    - When an expert returns `relevant: false`, do NOT add that expert's unposed questions to `state.open_questions` — they were never surfaced.
    - on challenge-rounds `keep`/`skip` leaves state.decisions[key] unchanged
      and does NOT add to open_questions (it was an explicit re-affirmation)
    - if a reply answers questions but omits `then:`, record the answers,
      re-render only the post-round menu, and ask for `then:` as a follow-up
    - `accept all` accepts every currently rendered proposed/counter value;
      `skip rest` applies `skip` to every unanswered rendered question
    - malformed reply (e.g. multiple `then:` tokens, unknown choice letter,
      `then: C` when option C is hidden): do NOT mutate state; re-render
      the post-round menu prefixed with a one-line clarifier and re-ask
    - self-check before dispatching the `then:` choice: assert that
      `state.rounds[-1].answer_keys` is a list (possibly empty); if it is
      not a list, treat as a malformed-state error and re-ask
    # ---- Iteration cap check (runs after every completed round) ----
    state.round_count = state.round_count + 1
    if state.round_count >= state.BRAINSTORM_MAX_ROUNDS:
      emit:
        Brainstorm round cap reached ({state.round_count}/{state.BRAINSTORM_MAX_ROUNDS}).
        | Option | Action |
        |---|---|
        | extend: M | Raise cap to M (must be > current BRAINSTORM_MAX_ROUNDS) and continue |
        | accept     | Wrap up brainstorm now with decisions collected so far |
        | stop       | Manual handoff — route to wrap-handoff.md (reason: manual-cap) |
        Reply `extend: <M>`, `accept`, or `stop`.
      parse cap reply:
        - `extend: M` (M must be a positive integer greater than state.BRAINSTORM_MAX_ROUNDS):
              state.BRAINSTORM_MAX_ROUNDS = M; continue the loop
        - `accept`:
              state.topic_current = None; break  # wrap up normally
        - `stop`:
              route to wrap-handoff.md with reason="manual-cap"; break
        - anything else: re-emit the cap prompt with one-line rejection
    then dispatch on the user's `then:` choice:
    - `W` or stop-token: state.topic_current = None; break
    - `C`: REFUSE if `state.rounds[-1].answer_keys` is empty — render the
           one-line clarifier "Nothing to challenge — the previous round
           produced no accepted or custom answers. Pick a numbered topic
           option, `then: custom: <text>`, or `W` to wrap instead." and
           re-show the post-round menu without entering a new round. Otherwise
           set `pending_round_kind = "challenge"` (topic_current unchanged;
           topic_history NOT appended) and continue the loop.
           Authoritative guard: this is the ONLY place that decides whether
           a challenge-round may start; the loop's challenge branch trusts
           this guard and does not re-check.
    - `1|2|custom`: pending_round_kind = "topic"
           state.topic_history.append(state.topic_current.id)
           state.topic_current = chosen-or-custom topic
```

### Envelope flattening (single-agent mode)

When `cf-constructor-brainstorm-panel` returns an `envelope` object (in single-agent mode), the orchestrator flattens it into a `contributions[]` array before persisting. The envelope has two kinds of blocks:

- **`kind="independent"`**: Primary expert output (questions, initial answers, next_topic_proposal).
- **`kind="critique"`**: Secondary experts' reviews of the primary's output.

**Flattening algorithm:**
1. Initialize `contributions = []`.
2. For each block in `envelope.blocks` where `block.kind=="independent"`, iterate `block.rows`:
   - Extract expert_id, questions, critique, next_topic_proposal, relevant.
   - Create a contribution entry and append to `contributions`.
3. For each block in `envelope.blocks` where `block.kind=="critique"`, iterate `block.rows`:
   - Extract expert_id and critique.
   - Merge the critique into the corresponding primary contribution's `critique` field (append to existing critique or create it).
4. Return flattened `contributions` array.

Open, load, and follow `workflows/generate/phase-0.7/state-schema.md` § envelope for the full envelope schema.

### Expert dispatch contracts

**Fan-out mode (panel_mode="fan-out"):**
Each expert dispatch follows the JSON contract in `{cf-constructor-path}/.core/skills/cypilot/agents/cf-constructor-brainstorm-expert.md`. The facilitator is dispatched once per session; experts are re-dispatched fresh each round (parallel fan-out). Orchestrator-supplied values for every expert dispatch (same shape per expert in a given round):

- `persona` = the full panel entry for expert `e` from `state.panel` (`{id, persona, focus, rationale}` — pass the entire object, not just the id)
- `topic` = the full `state.topic_current` object (`{id, text, section}` — `section` is the template H2 section name when the topic maps to one, else `null`)
- `mode` = `"topic"` for an exploratory round or `"challenge"` for a challenge round; required field
- `challenged_decisions` = `{ "<key>": "<current value>", ... }` snapshot of `state.decisions` for the keys under challenge; required when `mode="challenge"`, MUST be omitted (or `null`) when `mode="topic"`
- `repair_feedback` = (optional) object containing prior round violations and suggestions for correction; omit if no repair is needed
- `state` = the orchestrator's brainstorm state with these sub-fields always present: `kind`, `rules_loaded`, `kit_rules_path`, `template_path`, `panel`, `decisions`, `topic_history`. Sub-fields not in this list (`example_path`, `rounds`, `open_questions`, `session_id`, `next_topic_proposals`) are optional — pass them when available, omit otherwise.

**Single-agent mode (panel_mode="single-agent"):**
The orchestrator dispatches `cf-constructor-brainstorm-panel` once per round (not per expert). Open, load, and follow `workflows/generate/phase-0.7/cf-constructor-brainstorm-panel.md` for the full contract.

- `panel` = the full `state.panel` array (all experts, to allow the agent to designate a primary)
- `topic` = the full `state.topic_current` object
- `mode` = `"topic"` or `"challenge"`
- `protocol` = orchestration protocol for multi-expert interaction (`"independent-then-critique"` or `"single-pass"`)
- `challenged_decisions` = (required on `mode="challenge"`) snapshot of keys under challenge
- `repair_feedback` = (optional) prior round violations and correction hints
- `state` = same as fan-out mode

After the while-loop exits (any of: `W` stop, stop-token, `accept` cap reply, `stop` cap reply), load and follow `workflows/generate/phase-0.7/wrap-handoff.md` to consolidate the design and hand off to Phase 1.
