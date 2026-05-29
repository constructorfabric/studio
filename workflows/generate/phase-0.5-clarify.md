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

```text
UNIT Phase05ClarifyContext

PURPOSE:
  Clarify system context and output destination before Phase 0.7 / Phase 1.

DO:
  IF BRAINSTORM mode is selected AND brainstorm topic is missing:
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
      EMIT exactly:
---
[Phase0.5]: Brainstorm selected, but the topic is missing.

I found saved brainstorm sessions you can continue:
1. {title} — {session_id}, {status}, {rounds} rounds, updated {updated}
2. ...

Or start a new brainstorm topic:
N. A new Constructor Studio feature
N+1. A workflow or prompt redesign
N+2. A codebase architecture change
N+3. A PR/review strategy
N+4. Another specific problem or decision

Reply with a saved session number to continue it, or reply with a short new
topic. You can also reply `new: <topic>` to force a new session.
---
      WAIT user.reply
      STOP_TURN

    ELSE:
      EMIT exactly:
---
[Phase0.5]: Brainstorm selected, but the topic is missing.

No saved brainstorm sessions were found under
`{cf-studio-path}/.cache/brainstorm/`.

What should we brainstorm?

Reply with a short topic, for example:

1. A new Constructor Studio feature
2. A workflow or prompt redesign
3. A codebase architecture change
4. A PR/review strategy
5. Another specific problem or decision
---
      WAIT user.reply
      STOP_TURN

  IF system context is unclear:
    EMIT exactly:
---
Why this input is needed: system selection controls registry placement, ID prefixes, and traceability boundaries.

Which system does this artifact/code belong to?
- {list systems from artifacts.toml}
- Create new system
Suggested: the current or nearest registered system when one owns the target path; otherwise `Create new system`.
Reply with the system name or `Create new system`.
---
    WAIT user.reply
    SET selected_system = user.reply
    STOP_TURN

  IF output destination is unclear:
    EMIT exactly:
---
Why this input is needed: destination controls whether this workflow writes files, updates the registry, or returns a chat-only preview.

Where should the result go?
- File (will be written to disk and registered)
- Chat only (preview, no file created)
- MCP tool / external system (specify as `MCP: <tool>` or `External: <system>`)
Suggested: File for durable artifacts/code changes; Chat only for previews.
Reply with `File`, `Chat only`, `MCP: <tool>`, or `External: <system>`.
---
    WAIT user.reply
    SET output_destination = user.reply
    STOP_TURN

  SET selected_system (store for registry placement)
  IF file output AND using rules:
    DETERMINE path
    PLAN artifacts.toml entry
    CHECK UPDATE vs CREATE
  IF artifacts:
    IDENTIFY parent references
  IF code:
    IDENTIFY design artifacts + requirement IDs + traceability markers
  FOR new IDs:
    USE cpt-{system}-{kind}-{slug}
    VERIFY uniqueness with `{cfs_cmd} --json list-ids`

RULES:
  - MUST check for saved brainstorm sessions before asking for a new topic when
    BRAINSTORM mode is selected and topic is missing
  - MUST NOT load saved session prompt assets from disk; saved brainstorm
    sessions are resource/session state, not SHARED_CONTEXT_PACK assets
  - Continuing a saved session MUST restore state from state.json when present,
    then proceed to phase-0.7/round-loop.md or wrap-handoff.md based on status
  - If saved session has only summary.md/design.md and no state.json, offer to
    use it as context for a new brainstorm rather than claiming full resume
  - MUST clarify system context when unclear before proceeding
  - MUST clarify output destination when unclear before proceeding
  - MUST store selected system for registry placement
```
