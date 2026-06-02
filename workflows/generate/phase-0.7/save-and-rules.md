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

```pdsl
UNIT BrainstormSaveMode

PURPOSE:
  Persist brainstorm state and design artifacts when user picked save at the
  initial offer or chose wrap option 2 (save to disk), and output destination
  allows file writes.

DO:
  - REQUIRE output_destination allows file writes
  - REQUIRE offer included the save option OR wrap-handoff option 2 was selected
  - RUN AFTER every round:
    WRITE state.json to {cf-studio-path}/.cache/brainstorm/{session_id}/state.json
      (durable across compaction)
  - RUN ON loop exit:
    WRITE design.md to {cf-studio-path}/.cache/brainstorm/{session_id}/design.md
      (human-readable: consolidated decisions + open questions + panel transcript)

RULES:
  - NEVER enter persisted save mode for chat-only or no-write destinations
  - NEVER create state.json, design.md, or any brainstorm cache directory
    if user replies save to a chat-only offer or free-form message
  - ALWAYS reject save reply with a one-line explanation and ask for yes or no
    when destination is chat-only
  - ALWAYS IF compaction recovery needed in chat-only mode:
    EMIT in-chat checkpoint instead of writing cache files
  - ALWAYS Skipped/declined brainstorm leaves no artifacts
```

### Rules respect

```pdsl
UNIT BrainstormRulesRespect

PURPOSE:
  Define how agents respect kit rules during brainstorm based on mode and kit availability.

MENU RulesRespectMatrix:
  TITLE: Rules-respect routing (machine reference)
  OPTIONS:
    1 STRICT AND KIND mapped to kit ->
      REQUIRE facilitator and every expert open, load, and follow the resolved kit `rules.md` and template inputs
      REQUIRE all proposed defaults satisfy template constraints and Content Rules
      NEVER offering non-compliant alternatives
      SELECT personas whose focus covers template's high-leverage sections
    2 RELAXED WITH kit_rules_path present ->
      LOAD provided rules as guidance
      ALLOW clarifying questions when request intentionally departs from kit form
    3 RELAXED WITH kit_rules_path null ->
      RUN agents with user-supplied context
      EMIT "⚠ Brainstorm without kit rules (reduced quality assurance)"
        as prefix to consolidated design block
    4 non-kit ad-hoc target ->
      RUN agents free-form
      SET rules_loaded = false
      LOAD no rules
      SELECT personas from user's request semantics
```

### Standalone use

```pdsl
UNIT BrainstormStandaloneUse

PURPOSE:
  Define invocation path when brainstorm is used outside the generate flow.

DO:
  - RUN WHEN invoked standalone via cf skill router:
    ASK for chat-only vs save
    - RUN same facilitator -> round-loop sequence
    WRITE final design to {cf-studio-path}/.cache/brainstorm/{session_id}/
      only when user explicitly selects save
```

### Cache retention (TTL)

```pdsl
UNIT BrainstormCacheRetention

PURPOSE:
  Define retention policy for saved brainstorm caches.

RULES:
  - ALWAYS retain saved brainstorm caches when:
    (newer than 30 days) OR (one of the last 10 sessions)
  - ALWAYS Retention is advisory; cleanup is manual

NOTES:
  Delete entries older than the retention window manually.
```
