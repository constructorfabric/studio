---
description: "Invoke when the user accepted the brainstorm offer and the expert panel must be selected / edited before the round loop begins."
name: phase-0.7-panel-selection
purpose: Brainstorm session setup — facilitator dispatch, proposed-panel rendering, panel-edit forms, seed-topic confirmation
loaded_by: workflows/generate/phase-0.7/index.md
version: 1.0
---

<!-- toc -->

- [Session setup (panel selection)](#session-setup-panel-selection)

<!-- /toc -->

### Session setup (panel selection)

```text
UNIT Phase07PanelSelection

PURPOSE:
  Dispatch facilitator, render proposed panel, manage panel edits, confirm seed topic.

DO:
  REQUIRE `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md` loaded before any cf-* sub-agent dispatch
  DISPATCH cf-brainstorm-facilitator with JSON contract from
    {cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-facilitator.md
  WITH orchestrator-supplied values:
    initial_topic = one-paragraph summary of user's original request
    kind = {KIND}
    rules_loaded = true ONLY when kit rules actually loaded for this brainstorm session,
                   else false
    kit_rules_path = resolved from rules.md or null
    template_path = resolved from rules.md or null
    example_path = resolved from rules.md or null
    NOTE: non-null kit_rules_path alone does NOT make rules_loaded=true;
          orchestrator must have opened and applied the rules
    project_ctx = 2-3-sentence summary covering: selected system (Phase 0.5),
                  KIND and its kit (STRICT + kit-mapped), most-relevant existing
                  artifact paths from Phase 0.5 parent/sibling discovery

  RECEIVE { proposed_panel: [...3..6 entries], seed_topic: {...} }

  EMIT exactly:
---
Proposed panel for `{KIND}: {name}`:

E1. Domain Architect      — focus: domain model, actor boundaries
                            why: <rationale>
E2. Security Reviewer     — focus: auth, data-handling
                            why: <rationale>
...

Reply `accept` (suggested when the proposed panel matches your needs), list
IDs to drop (`drop E2,E4`), `swap E2: <new persona> (<focus>)`, or
`add: <persona> (<focus>)`. Min 3, max 6 participants. One reply form per
turn — compound replies (e.g. `drop E2; add: X (focus)`) are refused with
a one-line clarifier asking for a single edit form; re-issue panel edits
across multiple turns. After every edit the orchestrator re-renders the
proposed panel until the user replies `accept`.

Seed topic: `{seed_topic.text}`
Reply `start` after confirming the panel, or `seed: <topic>` to override.
---
  WAIT user.reply

MENU PanelEditLoop:
  TITLE: Panel edit loop (repeat until user replies accept)
  OPTIONS:
    accept ->
      SET state.panel = confirmed_list
      SET state.topic_current = confirmed_seed_topic
      CONTINUE phase-0.7/round-loop.md
    drop E{N},E{M} ->
      REMOVE listed experts from proposed panel
      REQUIRE min 3 remain
      EMIT re-rendered panel
      WAIT user.reply
    swap E{N}: <new persona> (<focus>) ->
      REPLACE E{N} with new persona
      EMIT re-rendered panel
      WAIT user.reply
    add: <persona> (<focus>) ->
      REQUIRE panel size < 6
      ADD new persona to panel
      EMIT re-rendered panel
      WAIT user.reply
    start ->
      SET state.panel = confirmed_list
      SET state.topic_current = confirmed_seed_topic
      CONTINUE phase-0.7/round-loop.md
    seed: <topic> ->
      SET confirmed_seed_topic = <topic>
      EMIT re-rendered panel with updated seed topic
      WAIT user.reply
  INVALID (compound reply):
    EMIT one-line clarifier asking for single edit form
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST refuse compound replies with a one-line clarifier
  - MUST require min 3 panel members; MUST NOT allow more than 6
  - MUST re-render proposed panel after every edit until user replies accept
  - MUST set state.panel = confirmed_list and state.topic_current before
    entering round loop
```
