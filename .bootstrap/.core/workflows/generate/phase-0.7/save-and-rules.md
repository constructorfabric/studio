---
description: "Invoke when the user replied 'save' (or 'save:N') to the brainstorm offer and the rules-file save flow must run before normal Phase 0.7 continues."
name: phase-0.7-save-and-rules
purpose: Brainstorm `save` mode persistence, rules-respect matrix (STRICT/RELAXED/non-kit), and standalone invocation entry
loaded_by: workflows/generate/phase-0.7/index.md
version: 1.0
---

<!-- toc -->

- [`save` mode](#save-mode)
- [Rules respect](#rules-respect)
- [Standalone use](#standalone-use)
- [Cache retention (TTL)](#cache-retention-ttl)

<!-- /toc -->

### `save` mode

`save` mode exists only when Phase 0.5 resolved an output destination that
allows file writes and the offer included the explicit `save` option. When the
user picked `save` in that write-allowed offer, the orchestrator writes
`state.json` to
`{cf-studio-path}/.cache/brainstorm/{session_id}/state.json` after every
round (durable across compaction) and, on loop exit, also emits `design.md`
(human-readable consolidated decisions + open questions + panel transcript)
in the same directory. Skipped/declined brainstorm leaves no artifacts.

Chat-only/no-write destinations cannot enter persisted `save` mode. If the
user replies `save` to a chat-only offer or free-form message, reject it with a
one-line explanation and ask for `yes` or `no`; do not create
`state.json`, `design.md`, or any brainstorm cache directory. If compaction
recovery is needed in chat-only mode, emit an in-chat checkpoint instead.

### Rules respect

- STRICT + KIND mapped to a kit → facilitator and every expert open, load, and follow `rules.md` and the template; all proposed defaults must satisfy template constraints and Content Rules; non-compliant alternatives are not offered; the facilitator's panel selection favors personas whose `focus` covers the template's high-leverage sections.
- RELAXED with `kit_rules_path` present → agents load the provided rules as
  guidance but may ask clarifying questions when the request intentionally
  departs from kit form.
- RELAXED with `kit_rules_path = null` → agents run with whatever context the
  user supplied; the consolidated design block is prefixed with `⚠ Brainstorm
  without kit rules (reduced quality assurance)`.
- Non-kit ad-hoc target → agents run free-form, `rules_loaded=false`, no rules
  loaded; the facilitator picks personas purely from the user's request
  semantics.

### Standalone use

The brainstorm session is invokable outside the `generate` flow via the
`cf` skill router (no separate workflow file). Standalone mode
runs the same facilitator → round-loop sequence, first asks for chat-only vs
`save`, and writes the final design to the brainstorm cache directory only
when the user explicitly selects `save`.

### Cache retention (TTL)

Saved brainstorm caches under `{cf-studio-path}/.cache/brainstorm/{session_id}/` MUST be retained only when (newer than 30 days) OR (one of the last 10 sessions).

Retention is currently advisory; cleanup is manual (delete entries older than the retention window).
