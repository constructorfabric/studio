---
description: "Invoke when Phase 0.7 starts and the brainstorm offer must be presented to the user (yes / no / save with optional :N cap override)."
name: phase-0.7-offer
purpose: Phase 0.7 preamble (section intro + core invariants) and the brainstorm offer block with INLINE_FALLBACK warning prepend rule
loaded_by: workflows/generate/phase-0.7/index.md
version: 1.1
---

<!-- toc -->

- [Phase 0.7: Brainstorm (optional)](#phase-07-brainstorm-optional)
  - [Offer](#offer)

<!-- /toc -->

## Phase 0.7: Brainstorm (optional)

```pdsl
UNIT Phase07BrainstormInvariants

PURPOSE:
  Define the core invariants governing every brainstorm round.

INVARIANTS:
  - ALWAYS run exactly one topic per round (multiple sub-questions per topic allowed,
    up to 3 per expert)
  - ALWAYS dispatch all experts independently in fan-out mode: same (persona, topic, state),
    no expert sees another's output within the round
  - ALWAYS render an expert returning relevant=false as "{persona}: skipped — {reason}"
    (skip is first-class)
  - ALWAYS let user drive topic order from expert proposals or custom input;
    NEVER auto-advance topics
  - ALWAYS After the user accepts brainstorm, every subsequent user-facing brainstorm
    menu ALWAYS expose `W` / `wrap` so the session can enter wrap-handoff and
    offer save/generate/analyze routing at any point

NOTES:
  The post-round menu has more than three entries (one per proposed next-topic plus C and W);
  "three semantic paths" refers to: advance to next topic, challenge decisions, or wrap up.
```

### Offer

```pdsl
UNIT Phase07Offer

PURPOSE:
  Present brainstorm offer after Phase 0.5 and apply auto-skip and INLINE_FALLBACK rules.

DO:
  - REQUIRE auto_skip_condition applies:
    - SET brainstorm_accepted = false
    - CONTINUE Phase1

  - REQUIRE INLINE_FALLBACK == true:
    PREPEND to offer block:
      "⚠️ Inline mode detected — brainstorm expert independence is best-effort
       because each persona will see earlier personas' output in the orchestrator's
       context (sequential inline execution, not isolated parallel dispatches).
       Consider replying `no` to skip the panel, or restarting this flow in a host
       with native sub-agents next time."

  - REQUIRE output_destination allows file writes:
    - EMIT exactly:
- RUN ---
- RUN Want a brainstorm panel before I collect inputs?

- RUN I'll assemble a 3-6-person expert panel relevant to `{KIND}: {name}`. Each
- RUN round we pick one topic, the panel reviews it, then I walk you through the
- RUN resulting questions one by one. For each question I explain why it matters,
- RUN offer answer options, record your reaction, and only after the full queue is
- RUN resolved do I offer next topic / challenge / wrap choices.

- RUN → Reply `yes` (suggested when the design space is open or you want
  - RUN cross-discipline pushback), `no` (skip — go straight to inputs), or
  - RUN `save` (run the panel and persist the transcript + final design under
  - RUN `{cf-studio-path}/.cache/brainstorm/{slug}-{ISO}/`; saved sessions
  - RUN follow manual cache retention).

  - RUN Optional modifiers (append to `yes` / `save`, whitespace-separated, any
  - RUN order):
  - RUN • `:N` — custom round cap, e.g. `yes:15` (default 10,
    `BRAINSTORM_MAX_ROUNDS=10`). `save:N` is also accepted.
  - RUN • `mode=fan-out` — dispatch each expert as a separate parallel sub-agent
    (`cf-brainstorm-expert`, one per panel member). Requires a
    host with native sub-agent parallelism (otherwise degrades to
    sequential). Use this when you want strict cross-expert independence.
  - RUN • `mode=single-agent` — explicit form of the default; dispatch one
    `cf-brainstorm-panel` agent per round with all experts
    deliberating inside it (one cohesive sub-agent context, host-
    independent, INLINE_FALLBACK is a no-op).

  - RUN Examples: `yes`, `yes:15`, `yes mode=fan-out`, `save:20 mode=fan-out`.
- RUN ---
  - RUN otherwise (chat-only / no-write destination):
    - EMIT exactly:
- RUN ---
- RUN Want a brainstorm panel before I collect inputs?

- RUN I'll assemble a 3-6-person expert panel relevant to `{KIND}: {name}`. Each
- RUN round we pick one topic, the panel reviews it, then I walk you through the
- RUN resulting questions one by one. For each question I explain why it matters,
- RUN offer answer options, record your reaction, and only after the full queue is
- RUN resolved do I offer next topic / challenge / wrap choices.

- RUN → Reply `yes` (suggested when the design space is open or you want
  - RUN cross-discipline pushback) or `no` (skip — go straight to inputs).

  - RUN Optional modifiers (append to `yes`, whitespace-separated, any order):
  - RUN • `:N` — custom round cap, e.g. `yes:15` (default 10,
    `BRAINSTORM_MAX_ROUNDS=10`).
  - RUN • `mode=fan-out` — dispatch each expert as a separate parallel sub-agent
    (`cf-brainstorm-expert`). Requires native sub-agent
    parallelism on the host.
  - RUN • `mode=single-agent` — explicit form of the default; one
    `cf-brainstorm-panel` dispatch per round with all experts
    deliberating inside it.

  - RUN Examples: `yes`, `yes:15`, `yes mode=fan-out`, `yes:20 mode=fan-out`.
- RUN ---

  - WAIT user.reply
  - STOP_TURN

RULES:
  - ALWAYS auto-skip (treat as `no`) when --no-brainstorm flag is present
  - ALWAYS auto-skip when KIND's rules.md has brainstorm = "disabled"
  - NEVER include `save` in the offer when output_destination is chat-only or no-write
  - ALWAYS reject `save` reply when offer was emitted without save option
  - ALWAYS prepend INLINE_FALLBACK warning before the offer block when INLINE_FALLBACK=true
```

### Reply parsing

```pdsl
UNIT Phase07OfferReplyParsing

PURPOSE:
  Parse the user's brainstorm offer reply into base verb and modifiers.

DO:
  - RUN TOKENIZE user reply on whitespace
  - SET base_verb = first token (yes / yes:N / save / save:N / no)
  - SET modifiers = remaining tokens of form key=value

  - RUN SWITCH base_verb:
    yes ->
      - SET brainstorm_mode = run
      - SET save_artifacts = false
    yes:N (N positive integer) ->
      - SET brainstorm_mode = run
      - SET state.BRAINSTORM_MAX_ROUNDS = N
      - SET save_artifacts = false
    save / save:N ->
      - REQUIRE output_destination allows file writes
      - SET brainstorm_mode = run
      - SET save_artifacts = true
      IF N present: SET state.BRAINSTORM_MAX_ROUNDS = N
    no ->
      - SET brainstorm_mode = skip
      - CONTINUE Phase1

  - RUN FOR each modifier:
    mode=fan-out ->
      - SET state.run_config.PANEL_MODE_TOPIC = "fan-out"
      - SET state.run_config.PANEL_MODE_CHALLENGE = "fan-out"
    mode=single-agent ->
      - SET state.run_config.PANEL_MODE_TOPIC = "single-agent"
      - SET state.run_config.PANEL_MODE_CHALLENGE = "single-agent"
    unknown modifier ->
      - EMIT one-line error naming unknown token
      - EMIT offer again
      - WAIT user.reply
      - STOP_TURN

RULES:
  - ALWAYS reject unknown modifiers with a one-line error naming the unknown token
  - ALWAYS reject duplicate mode= modifiers in one reply
  - NEVER allow save when offer was emitted without save option
  - ALWAYS To set PANEL_MODE_TOPIC and PANEL_MODE_CHALLENGE to different values,
    use env-var override from phase-0-dependencies.md § Panel Mode Flags

NOTES:
  Mode precedence (highest to lowest):
  1. state.run_config.PANEL_MODE_TOPIC / PANEL_MODE_CHALLENGE (set by mode= modifier)
  2. env vars PANEL_MODE_TOPIC / PANEL_MODE_CHALLENGE
  3. workflow default "single-agent"
  Open, load, and follow `{cf-studio-path}/.core/workflows/generate/phase-0.7/round-loop.md` § Round loop for implementation.
```
