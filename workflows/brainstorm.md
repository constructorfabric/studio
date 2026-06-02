---
cf: true
type: workflow
name: cf-brainstorm
description: "REQUIRED before any creative task. Invoke for requests to brainstorm, ideate, explore options, explore design, discover requirements, map options, or compare decision tradeoffs."
version: 1.0
purpose: Standalone brainstorm command; pass-through to generate.md with BRAINSTORM mode
---

```pdsl
UNIT BrainstormRootSkillEntrypointBootstrap
PURPOSE: Load the shared root cf skill entrypoint bootstrap.
DO:
  - LOAD {cf-studio-path}/.core/workflows/shared/root-skill-entrypoint-bootstrap.md
  - CONTINUE RootSkillEntrypointBootstrap
```

```pdsl
UNIT BrainstormProxy

PURPOSE:
  Pass through to generate.md with BRAINSTORM mode active.

DO:
  - LOAD skill `cf` IN GENERATE + BRAINSTORM mode
  - RUN The target generate Phase 0.7 workflow ALWAYS run cf-explore after panel
  - RUN selection and pass RESOURCE_CONTEXT into brainstorm agents.
  - RUN Completion signal from the target generate flow ALWAYS include:
    { "type": "BRAINSTORM_RESULT", "status": "wrapped|handoff|checkpointed|cancelled", "decisions_count": <int>, "open_questions_count": <int>, "next_route": "<generate|plan|analyze|null>" }
  - RUN Every clean, cancelled, checkpointed, or handoff terminal exit ALWAYS emit this
  - RUN BRAINSTORM_RESULT envelope; human-facing wrap text is not a substitute for
  - RUN the machine-readable completion signal.

ON_ERROR:
  load_failed ->
    EMIT "Cannot load target workflow — check that {cf-studio-path} is correctly set."
    EMIT_MENU BrainstormLoadFailureMenu
    WAIT user.reply
    STOP_TURN

MENU BrainstormLoadFailureMenu:
  TITLE: "Brainstorm target workflow failed to load."
  OPTIONS:
    1 retry -> Retry loading the target generate workflow
    2 route -> Return to routing and choose another workflow
    3 stop -> Stop without starting brainstorm
  INVALID:
    EMIT "Reply `1`, `2`, or `3`."
    WAIT user.reply
    STOP_TURN
```
