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

```text
UNIT Phase07BrainstormInvariants

PURPOSE:
  Define the core invariants governing every brainstorm round.

INVARIANTS:
  - MUST run exactly one topic per round (multiple sub-questions per topic allowed,
    up to 3 per expert)
  - MUST dispatch all experts independently in fan-out mode: same (persona, topic, state),
    no expert sees another's output within the round
  - MUST render an expert returning relevant=false as "{persona}: skipped — {reason}"
    (skip is first-class)
  - MUST let user drive topic order from expert proposals or custom input;
    MUST NOT auto-advance topics

NOTES:
  The post-round menu has more than three entries (one per proposed next-topic plus C and W);
  "three semantic paths" refers to: advance to next topic, challenge decisions, or wrap up.
```

### Offer

```text
UNIT Phase07Offer

PURPOSE:
  Present brainstorm offer after Phase 0.5 and apply auto-skip and INLINE_FALLBACK rules.

DO:
  IF auto_skip_condition applies:
    SET brainstorm_accepted = false
    CONTINUE Phase1

  IF INLINE_FALLBACK == true:
    PREPEND to offer block:
      "⚠️ Inline mode detected — brainstorm expert independence is best-effort
       because each persona will see earlier personas' output in the orchestrator's
       context (sequential inline execution, not isolated parallel dispatches).
       Consider replying `no` to skip the panel, or restarting this flow in a host
       with native sub-agents next time."

  IF output_destination allows file writes:
    EMIT exactly:
---
Want a brainstorm panel before I collect inputs?

I'll assemble a 3-6-person expert panel relevant to `{KIND}: {name}`. Each
round we pick one topic, the panel reviews it in parallel, each expert
either contributes questions + a next-topic proposal or skips the round as
not-their-domain. You answer the questions and pick the next topic.

→ Reply `yes` (suggested when the design space is open or you want
  cross-discipline pushback), `no` (skip — go straight to inputs), or
  `save` (run the panel and persist the transcript + final design under
  `{cf-studio-path}/.cache/brainstorm/{slug}-{ISO}/`; saved sessions
  follow manual cache retention).

  Optional modifiers (append to `yes` / `save`, whitespace-separated, any
  order):
  • `:N` — custom round cap, e.g. `yes:15` (default 10,
    `BRAINSTORM_MAX_ROUNDS=10`). `save:N` is also accepted.
  • `mode=fan-out` — dispatch each expert as a separate parallel sub-agent
    (`cf-brainstorm-expert`, one per panel member). Requires a
    host with native sub-agent parallelism (otherwise degrades to
    sequential). Use this when you want strict cross-expert independence.
  • `mode=single-agent` — explicit form of the default; dispatch one
    `cf-brainstorm-panel` agent per round with all experts
    deliberating inside it (one cohesive sub-agent context, host-
    independent, INLINE_FALLBACK is a no-op).

  Examples: `yes`, `yes:15`, `yes mode=fan-out`, `save:20 mode=fan-out`.
---
  ELSE (chat-only / no-write destination):
    EMIT exactly:
---
Want a brainstorm panel before I collect inputs?

I'll assemble a 3-6-person expert panel relevant to `{KIND}: {name}`. Each
round we pick one topic, the panel reviews it in parallel, each expert
either contributes questions + a next-topic proposal or skips the round as
not-their-domain. You answer the questions and pick the next topic.

→ Reply `yes` (suggested when the design space is open or you want
  cross-discipline pushback) or `no` (skip — go straight to inputs).

  Optional modifiers (append to `yes`, whitespace-separated, any order):
  • `:N` — custom round cap, e.g. `yes:15` (default 10,
    `BRAINSTORM_MAX_ROUNDS=10`).
  • `mode=fan-out` — dispatch each expert as a separate parallel sub-agent
    (`cf-brainstorm-expert`). Requires native sub-agent
    parallelism on the host.
  • `mode=single-agent` — explicit form of the default; one
    `cf-brainstorm-panel` dispatch per round with all experts
    deliberating inside it.

  Examples: `yes`, `yes:15`, `yes mode=fan-out`, `yes:20 mode=fan-out`.
---

  WAIT user.reply
  STOP_TURN

RULES:
  - MUST auto-skip (treat as `no`) when --no-brainstorm flag is present
  - MUST auto-skip when KIND's rules.md has brainstorm = "disabled"
  - MUST NOT include `save` in the offer when output_destination is chat-only or no-write
  - MUST reject `save` reply when offer was emitted without save option
  - MUST prepend INLINE_FALLBACK warning before the offer block when INLINE_FALLBACK=true
```

### Reply parsing

```text
UNIT Phase07OfferReplyParsing

PURPOSE:
  Parse the user's brainstorm offer reply into base verb and modifiers.

DO:
  TOKENIZE user reply on whitespace
  SET base_verb = first token (yes / yes:N / save / save:N / no)
  SET modifiers = remaining tokens of form key=value

  SWITCH base_verb:
    yes ->
      SET brainstorm_mode = run
      SET save_artifacts = false
    yes:N (N positive integer) ->
      SET brainstorm_mode = run
      SET state.BRAINSTORM_MAX_ROUNDS = N
      SET save_artifacts = false
    save / save:N ->
      REQUIRE output_destination allows file writes
      SET brainstorm_mode = run
      SET save_artifacts = true
      IF N present: SET state.BRAINSTORM_MAX_ROUNDS = N
    no ->
      SET brainstorm_mode = skip
      CONTINUE Phase1

  FOR each modifier:
    mode=fan-out ->
      SET state.run_config.PANEL_MODE_TOPIC = "fan-out"
      SET state.run_config.PANEL_MODE_CHALLENGE = "fan-out"
    mode=single-agent ->
      SET state.run_config.PANEL_MODE_TOPIC = "single-agent"
      SET state.run_config.PANEL_MODE_CHALLENGE = "single-agent"
    unknown modifier ->
      EMIT one-line error naming unknown token
      EMIT offer again
      WAIT user.reply
      STOP_TURN

RULES:
  - MUST reject unknown modifiers with a one-line error naming the unknown token
  - MUST reject duplicate mode= modifiers in one reply
  - MUST NOT allow save when offer was emitted without save option
  - To set PANEL_MODE_TOPIC and PANEL_MODE_CHALLENGE to different values,
    use env-var override from phase-0-dependencies.md § Panel Mode Flags

NOTES:
  Mode precedence (highest to lowest):
  1. state.run_config.PANEL_MODE_TOPIC / PANEL_MODE_CHALLENGE (set by mode= modifier)
  2. env vars PANEL_MODE_TOPIC / PANEL_MODE_CHALLENGE
  3. workflow default "single-agent"
  Open, load, and follow `{cf-studio-path}/.core/workflows/generate/phase-0.7/round-loop.md` § Round loop for implementation.
```
