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

A panel-based, sub-agent-driven exploratory dialog. A facilitator agent proposes a 3-6-person expert panel; each round the orchestrator fans out in parallel to every panel member, each independently contributes 1-3 questions about the current topic + proposes a next topic, or sits the round out as irrelevant. After answering, the user picks one of three semantic paths: advance to a next topic (numbered proposal or custom), **challenge** the decisions just made (re-run the same panel in challenge mode so each persona pushes back on the accepted decisions with counter-proposals — challenge results can themselves be challenged), or wrap up. The literal post-round menu has more than three entries (one per proposed next-topic plus `C` and `W`); "three paths" refers to the semantic categories, not the option count. The session ends when the user wraps up or types a stop token.

Core invariants:

- **One topic per round.** Multiple sub-questions per topic are allowed (up to 3 per expert).
- **Experts are independent.** All expert dispatches in a round receive the same `(persona, topic, state)` and run in parallel — they do NOT see each other's output within the round. Cross-pollination happens through `state` in subsequent rounds.
- **Skip is first-class.** An expert returning `{ relevant: false }` is rendered as "`{persona}`: skipped — `{reason}`" so the user sees the full panel reaction.
- **User drives topic order.** The user always picks the next topic from expert proposals (or types a custom one); agents never auto-advance.

### Offer

After Phase 0.5 (system + output clarified), unless an auto-skip condition
(below) applies, ask the write-capable offer only when the output destination
permits file writes:

```text
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
```

When Phase 0.5 resolved a chat-only or otherwise no-write destination, the
offer MUST NOT include `save`, and choosing `save` MUST be rejected rather than
treated as consent to write cache artifacts:

```text
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
```

When `INLINE_FALLBACK=true` (set per `workflows/shared/inline-fallback-probe.md` — user replied `2` or host has no native sub-agent support), prepend this warning to the offer block above before showing it to the user:

```text
⚠️ Inline mode detected — brainstorm expert independence is best-effort because each persona will see earlier personas' output in the orchestrator's context (sequential inline execution, not isolated parallel dispatches). Consider replying `no` to skip the panel, or restarting this flow in a host with native sub-agents next time.
```

Auto-skip the offer (treat as `no`) when any of:

- the user passed `--no-brainstorm` in the invocation (`--no-brainstorm` is a recognized CLI flag for the generate workflow; the orchestrator skips the brainstorm offer entirely when this flag is present);
- the KIND's `rules.md` has `brainstorm = "disabled"` (escape hatch for kits where exploration is pointless — e.g. mechanically derived artifacts) (future kit-schema extension; not yet defined in the sdlc kit — treated as 'not present' = enabled in current kits).

### Reply parsing

Tokenize the user reply on whitespace. The first token is the **base verb** (`yes` / `yes:N` / `save` / `save:N` / `no`); zero or more subsequent tokens are **modifiers** of the form `key=value` (case-insensitive on key and value).

Base verb resolution:

- `yes` → run brainstorm, do not save artifacts.
- `yes:N` (N positive integer) → run brainstorm with `state.BRAINSTORM_MAX_ROUNDS = N`.
- `save` / `save:N` → like `yes` / `yes:N`, plus persist transcript + final design under `{cf-studio-path}/.cache/brainstorm/{slug}-{ISO}/`. Rejected when the offer was emitted without `save` (no-write destination).
- `no` → skip brainstorm.

Recognized modifiers:

- `mode=fan-out` → set `state.run_config.PANEL_MODE_TOPIC = "fan-out"` AND `state.run_config.PANEL_MODE_CHALLENGE = "fan-out"` before entering the round loop.
- `mode=single-agent` → set both to `"single-agent"` (explicit form of the default).

Unknown modifiers MUST cause rejection with a one-line error naming the unknown token and re-emitting the offer. Duplicate `mode=` modifiers in one reply MUST cause rejection. To set `PANEL_MODE_TOPIC` and `PANEL_MODE_CHALLENGE` to different values, use the env-var override mechanism (`workflows/generate/phase-0-dependencies.md` § Panel Mode Flags) instead of the offer reply.

The full precedence chain is, from highest to lowest: (1) `state.run_config.PANEL_MODE_TOPIC` / `PANEL_MODE_CHALLENGE` — set by a `mode=` modifier in the user's offer reply earlier in this session; (2) env vars `PANEL_MODE_TOPIC` / `PANEL_MODE_CHALLENGE`; (3) workflow default `"single-agent"`. When no `mode=` modifier is supplied AND no prior reply has populated `state.run_config`, the round loop falls back to tiers (2) then (3). Open, load, and follow `workflows/generate/phase-0.7/round-loop.md` § Round loop for the implementation.
