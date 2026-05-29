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

```text
UNIT BrainstormSaveMode

PURPOSE:
  Persist brainstorm state and design artifacts when user picked save
  and output destination allows file writes.

DO:
  REQUIRE output_destination allows file writes
  REQUIRE offer included the save option
  AFTER every round:
    WRITE state.json to {cf-studio-path}/.cache/brainstorm/{session_id}/state.json
      (durable across compaction)
  ON loop exit:
    WRITE design.md to {cf-studio-path}/.cache/brainstorm/{session_id}/design.md
      (human-readable: consolidated decisions + open questions + panel transcript)

RULES:
  - MUST NOT enter persisted save mode for chat-only or no-write destinations
  - MUST NOT create state.json, design.md, or any brainstorm cache directory
    if user replies save to a chat-only offer or free-form message
  - MUST reject save reply with a one-line explanation and ask for yes or no
    when destination is chat-only
  - IF compaction recovery needed in chat-only mode:
    EMIT in-chat checkpoint instead of writing cache files
  - Skipped/declined brainstorm leaves no artifacts
```

### Rules respect

```text
UNIT BrainstormRulesRespect

PURPOSE:
  Define how agents respect kit rules during brainstorm based on mode and kit availability.

MENU RulesRespectMatrix:
  TITLE: Rules-respect routing (machine reference)
  OPTIONS:
    STRICT AND KIND mapped to kit ->
      REQUIRE facilitator and every expert open, load, and follow the resolved kit `rules.md` and template inputs
      REQUIRE all proposed defaults satisfy template constraints and Content Rules
      FORBID offering non-compliant alternatives
      SELECT personas whose focus covers template's high-leverage sections
    RELAXED WITH kit_rules_path present ->
      LOAD provided rules as guidance
      ALLOW clarifying questions when request intentionally departs from kit form
    RELAXED WITH kit_rules_path null ->
      RUN agents with user-supplied context
      EMIT "⚠ Brainstorm without kit rules (reduced quality assurance)"
        as prefix to consolidated design block
    non-kit ad-hoc target ->
      RUN agents free-form
      SET rules_loaded = false
      LOAD no rules
      SELECT personas from user's request semantics
```

### Standalone use

```text
UNIT BrainstormStandaloneUse

PURPOSE:
  Define invocation path when brainstorm is used outside the generate flow.

DO:
  WHEN invoked standalone via cf skill router:
    ASK for chat-only vs save
    RUN same facilitator -> round-loop sequence
    WRITE final design to {cf-studio-path}/.cache/brainstorm/{session_id}/
      only when user explicitly selects save
```

### Cache retention (TTL)

```text
UNIT BrainstormCacheRetention

PURPOSE:
  Define retention policy for saved brainstorm caches.

RULES:
  - MUST retain saved brainstorm caches when:
    (newer than 30 days) OR (one of the last 10 sessions)
  - Retention is advisory; cleanup is manual

NOTES:
  Delete entries older than the retention window manually.
```
