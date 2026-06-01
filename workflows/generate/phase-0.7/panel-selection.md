---
description: "Invoke when the user accepted the brainstorm offer and the expert panel must be selected / edited before the round loop begins."
name: phase-0.7-panel-selection
purpose: Brainstorm session setup — facilitator dispatch, proposed-panel rendering, panel-edit forms, seed-topic confirmation
loaded_by: workflows/generate/phase-0.7/index.md
version: 1.0
---

# Phase 0.7: Panel Selection

```text
UNIT Phase07PanelSelection

PURPOSE:
  Dispatch facilitator, render proposed panel, manage panel edits, confirm seed topic.

DO:
  REQUIRE `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md` loaded before any cf-* sub-agent dispatch
  LOAD {cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-facilitator.md
    as the facilitator source contract
  SYNTHESIZE final dispatch prompt from the loaded facilitator contract plus
    SHARED_CONTEXT_PACK and the payload below
  IF facilitator source contract is not loaded, unreadable, ambiguous, or not
     reflected in the final dispatch prompt:
    FAIL per sub-agent-dispatch.md § SubAgentContractReadGate
    FORBID dispatch
  DISPATCH cf-brainstorm-facilitator with the synthesized final prompt including:
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
  SET confirmed_list = proposed_panel
  SET confirmed_seed_topic = seed_topic

  EMIT proposed panel display containing:
    - header: "Proposed panel for {KIND}: {name}:"
    - E1..E6 entries: persona name, focus, why rationale
    - "Seed topic for round 1:" + seed_topic.text
    - numbered action menu: 1=start, 2=seed:<topic>, 3=drop E{N},
      4=swap E{N}:<persona>(<focus>), 5=add:<persona>(<focus>), W=wrap
    - one-liner: "One reply form per turn. Compound replies refused."
  WAIT user.reply

MENU PanelEditLoop:
  TITLE: Panel setup loop (reply start to begin, or edit one thing)
  OPTIONS:
    start ->
      SET state.panel = confirmed_list
      SET state.topic_current = confirmed_seed_topic
      CONTINUE Phase07ExplorePanelContext
    accept ->
      SET state.panel = confirmed_list
      SET state.topic_current = confirmed_seed_topic
      CONTINUE Phase07ExplorePanelContext
    drop E{N},E{M} ->
      REMOVE listed experts from proposed panel
      SET confirmed_list = proposed panel
      REQUIRE min 3 remain
      EMIT re-rendered panel
      WAIT user.reply
    swap E{N}: <new persona> (<focus>) ->
      REPLACE E{N} with new persona
      SET confirmed_list = proposed panel
      EMIT re-rendered panel
      WAIT user.reply
    add: <persona> (<focus>) ->
      REQUIRE panel size < 6
      ADD new persona to panel
      SET confirmed_list = proposed panel
      EMIT re-rendered panel
      WAIT user.reply
    seed: <topic> ->
      SET confirmed_seed_topic = <topic>
      EMIT re-rendered panel and seed topic with the same action menu
      WAIT user.reply
    W | wrap | stop | done ->
      SET state.panel = confirmed_list
      SET state.topic_current = None
      CONTINUE wrap-handoff.md WITH reason="panel-setup-wrap"
  INVALID (compound reply):
    EMIT one-line clarifier asking for single edit form
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST refuse compound replies with a one-line clarifier
  - MUST require min 3 panel members; MUST NOT allow more than 6
  - MUST re-render proposed panel and seed topic after every edit until user
    replies start
  - MUST treat accept as backwards-compatible alias for start; MUST NOT show
    accept in the primary user-facing action list
  - MUST always show wrap as a user-facing option in the panel setup menu
  - MUST set state.panel = confirmed_list and state.topic_current before
    entering round loop

NOTES:
  accept alias exists for backwards compatibility with earlier prompt versions.
```

```text
UNIT Phase07ExplorePanelContext

PURPOSE:
  After the panel is confirmed, determine what project/resource knowledge the
  experts need and materialize it before the first round dispatch.

DO:
  BUILD context_requirements from:
    state.topic_current
    confirmed_list personas, focus, rationale
    KIND, name, system, rules_mode
    known artifact paths from Phase 0.5 parent/sibling discovery

  LOAD {cf-studio-path}/.core/skills/studio/agents/cf-explorer.md
    as the explorer source contract
  SYNTHESIZE final dispatch prompt from the loaded explorer contract plus
    SHARED_CONTEXT_PACK and the payload below
  IF explorer source contract is not loaded, unreadable, ambiguous, or not
     reflected in the final dispatch prompt:
    FAIL per sub-agent-dispatch.md § SubAgentContractReadGate
    FORBID dispatch
  DISPATCH cf-explorer with the synthesized final prompt including:
    task = state.topic_current.text
    intent = "brainstorm"
    panel = state.panel
    known_paths = artifact paths from Phase 0.5 parent/sibling discovery
    search_roots = resolved project/workspace roots in scope
    constraints.kind = {KIND}
    constraints.system = {system or null}

  RECEIVE explorer resource_context
  SET state.context_requirements = derived context_requirements
  SET state.resource_context = explorer.resource_context
  SET state.resource_context.exploration_status = explorer.exploration_status
  CONTINUE phase-0.7/round-loop.md

RULES:
  - MUST run before the first brainstorm round after panel confirmation
  - MUST NOT put docs/code/artifacts into SHARED_CONTEXT_PACK
  - MUST pass resource_context to every brainstorm panel/expert dispatch
  - MUST apply sub-agent-dispatch.md § SubAgentContractReadGate before
    facilitator and explorer dispatch
  - IF cf-explorer returns exploration_status == "insufficient":
      still enter the round loop, but downstream panel/expert agents MUST ask
      for missing context instead of inventing project-specific proposals
```
