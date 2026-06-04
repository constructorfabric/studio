---
name: generate-phase-0.5-clarify
description: "Invoke when the generate workflow reaches Phase 0.5 to clarify output destination and system context before input collection."
purpose: Generate Phase 0.5 — clarify output destination and system context
loaded_by: workflows/generate.md
version: 1.0
---

<!-- toc -->

- [Phase 0.5: Clarify Output & Context](#phase-05-clarify-output--context)

<!-- /toc -->




## Phase 0.5: Clarify Output & Context

```pdsl
UNIT Phase05ClarifyContext

PURPOSE:
  Clarify system context and output destination before Phase 0.7 / Phase 1.

DO:
  - REQUIRE BRAINSTORM mode is selected AND brainstorm topic is missing:
    DISCOVER saved brainstorm sessions:
      LOOK under {cf-studio-path}/.cache/brainstorm/
      FIND directories containing state.json OR summary.md OR design.md
      SORT by newest modified time first
      TAKE up to 5 sessions
      EXTRACT for each:
        session_id = directory name
        title = first heading from summary.md/design.md OR state.topic_current.text OR session_id
        updated = newest mtime among state.json, summary.md, design.md
        status = in_progress when state.topic_current is non-null, otherwise wrapped/saved
        rounds = len(state.rounds) when state.json exists

    IF saved sessions found:
      - EMIT "Brainstorm selected, but the topic is missing. I found saved brainstorm sessions you can continue: {title} — {session_id}, {status}, {rounds} rounds, updated {updated}; ... Reply with a saved session number to continue it, or choose a new topic from the menu."
      - EMIT_MENU BrainstormTopicMenu
      - WAIT user.reply
      - STOP_TURN

    ELSE:
      - EMIT "Brainstorm selected, but the topic is missing. No saved brainstorm sessions were found under `{cf-studio-path}/.cache/brainstorm/`."
      - EMIT_MENU BrainstormTopicMenu
      - WAIT user.reply
      - STOP_TURN

  - REQUIRE system context is unclear:
    - EMIT "Why this input is needed: system selection controls registry placement, ID prefixes, and traceability boundaries. Suggested: the current or nearest registered system when one owns the target path; otherwise create a new system."
    - EMIT_MENU SystemSelectionMenu
    - WAIT user.reply
    - SET selected_system = user.reply
    - STOP_TURN

  - REQUIRE output destination is unclear:
    - EMIT "Why this input is needed: destination controls whether this workflow writes files, updates the registry, or returns a chat-only preview. Suggested: File for durable artifacts/code changes; Chat only for previews. Reply with `File`, `Chat only`, `MCP: <tool>`, or `External: <system>` via the numbered menu."
    - EMIT_MENU OutputDestinationMenu
    - WAIT user.reply
    - SET output_destination = user.reply
    - STOP_TURN

  - SET selected_system (store for registry placement)
  - REQUIRE file output AND using rules:
    DETERMINE path
    PLAN artifacts.toml entry
    CHECK UPDATE vs CREATE
  - REQUIRE artifacts:
    IDENTIFY parent references
  - REQUIRE code:
    IDENTIFY design artifacts + requirement IDs + traceability markers
  - RUN FOR new IDs:
    USE cpt-{system}-{kind}-{slug}
    VERIFY uniqueness with `{cfs_cmd} --json list-ids`

MENU BrainstormTopicMenu:
  TITLE: Choose brainstorm topic source
  OPTIONS:
    1 saved session N -> Continue saved brainstorm session N
    2 new feature -> SET brainstorm_topic = "A new Constructor Studio feature"
    3 workflow or prompt redesign -> SET brainstorm_topic = "A workflow or prompt redesign"
    4 codebase architecture change -> SET brainstorm_topic = "A codebase architecture change"
    5 PR/review strategy -> SET brainstorm_topic = "A PR/review strategy"
    6 custom topic -> SET brainstorm_topic = user supplied topic
  INVALID:
    EMIT "Reply with 1: <session number>, 2, 3, 4, 5, or 6: <custom topic>."
    WAIT user.reply
    STOP_TURN

MENU SystemSelectionMenu:
  TITLE: Choose system context
  OPTIONS:
    1 existing system -> SET selected_system = user supplied existing system name from artifacts.toml
    2 create new system -> SET selected_system = "Create new system"
  INVALID:
    EMIT "Reply with 1: <existing system name> or 2 to create a new system."
    WAIT user.reply
    STOP_TURN

MENU OutputDestinationMenu:
  TITLE: Choose output destination
  OPTIONS:
    1 file -> SET output_destination = File
    2 chat only -> SET output_destination = Chat only
    3 MCP tool -> SET output_destination = MCP tool named by user
    4 external system -> SET output_destination = External system named by user
  INVALID:
    EMIT "Reply with 1 for File, 2 for Chat only, 3: <MCP tool>, or 4: <external system>."
    WAIT user.reply
    STOP_TURN

RULES:
  - ALWAYS check for saved brainstorm sessions before asking for a new topic when
    BRAINSTORM mode is selected and topic is missing
  - NEVER load saved session prompt assets from disk; saved brainstorm
    sessions are resource/session state, not SHARED_CONTEXT_PACK assets
  - ALWAYS Continuing a saved session ALWAYS restore state from state.json when present,
    then proceed to phase-0.7/round-loop.md or wrap-handoff.md based on status
  - ALWAYS If saved session has only summary.md/design.md and no state.json, offer to
    use it as context for a new brainstorm rather than claiming full resume
  - ALWAYS clarify system context when unclear before proceeding
  - ALWAYS clarify output destination when unclear before proceeding
  - ALWAYS store selected system for registry placement
```
