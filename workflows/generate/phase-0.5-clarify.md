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
      - EMIT exactly:
- RUN ---
- RUN [Phase0.5]: Brainstorm selected, but the topic is missing.

- RUN I found saved brainstorm sessions you can continue:
- RUN {title} — {session_id}, {status}, {rounds} rounds, updated {updated}
- RUN ...

- RUN Or start a new brainstorm topic:
- RUN N. A new Constructor Studio feature
- RUN N+1. A workflow or prompt redesign
- RUN N+2. A codebase architecture change
- RUN N+3. A PR/review strategy
- RUN N+4. Another specific problem or decision

- RUN Reply with a saved session number to continue it, or reply with a short new
- RUN topic. You can also reply `new: <topic>` to force a new session.
- RUN ---
      - WAIT user.reply
      - STOP_TURN

    ELSE:
      - EMIT exactly:
- RUN ---
- RUN [Phase0.5]: Brainstorm selected, but the topic is missing.

- RUN No saved brainstorm sessions were found under
- RUN `{cf-studio-path}/.cache/brainstorm/`.

- RUN What should we brainstorm?

- RUN Reply with a short topic, for example:

- RUN A new Constructor Studio feature
- RUN A workflow or prompt redesign
- RUN A codebase architecture change
- RUN A PR/review strategy
- RUN Another specific problem or decision
- RUN ---
      - WAIT user.reply
      - STOP_TURN

  - REQUIRE system context is unclear:
    - EMIT exactly:
- RUN ---
- RUN Why this input is needed: system selection controls registry placement, ID prefixes, and traceability boundaries.

- RUN Which system does this artifact/code belong to?
- RUN {list systems from artifacts.toml}
- RUN Create new system
- RUN Suggested: the current or nearest registered system when one owns the target path; otherwise `Create new system`.
- RUN Reply with the system name or `Create new system`.
- RUN ---
    - WAIT user.reply
    - SET selected_system = user.reply
    - STOP_TURN

  - REQUIRE output destination is unclear:
    - EMIT exactly:
- RUN ---
- RUN Why this input is needed: destination controls whether this workflow writes files, updates the registry, or returns a chat-only preview.

- RUN Where should the result go?
- RUN File (will be written to disk and registered)
- RUN Chat only (preview, no file created)
- RUN MCP tool / external system (specify as `MCP: <tool>` or `External: <system>`)
- RUN Suggested: File for durable artifacts/code changes; Chat only for previews.
- RUN Reply with `File`, `Chat only`, `MCP: <tool>`, or `External: <system>`.
- RUN ---
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
