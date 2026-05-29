---
cf: true
type: workflow
name: cf-help
description: "Thin help router for Constructor Studio. Use for cf help, /cf help, cf-studio help, /cf-studio help, or cfs help; it presets the normal cf-explain storytelling help session and delegates to analyze.md."
version: 1.0
purpose: Standalone help command; presets cf help storytelling and passes through to analyze.md
---

```text
UNIT HelpProxy

PURPOSE:
  Pass through to analyze.md with the cf help preset active.

DO:
  SET CF_HELP_PRESET = true
  SET EXPLAIN_MODE = true
  SET EXPLAIN_TARGET = "{cf-studio-path}"
  SET STORYTELLING_MODE = "presentation"
  SET STORYTELLING_ARTIFACT_DISPOSITION = "chat-only"
  SET STORYTELLING_AUDIENCE = "Constructor Studio newcomers"
  SET STORYTELLING_CONTEXT_PACK_STRATEGY = "hybrid"
  SET STORYTELLING_PLAN_APPROVED = true
  SET STORYTELLING_DIAGRAM_FORMAT = "ascii"
  SET STORYTELLING_DIAGRAM_FORMAT_PRESET = true
  SET STORYTELLING_HELP_GOAL = "Run a normal cf-explain storytelling session about Constructor Studio itself: target {cf-studio-path}, presentation mode, chat-only, newcomers audience, source-grounded portions, normal navigation."
  LOAD skill `cf` IN ANALYZE + EXPLAIN mode, CF_HELP_PRESET=true

RULES:
  - MUST_NOT render custom one-shot help here
  - MUST_NOT ask the diagram-format lazy prompt in help mode
  - MUST render help-mode diagrams as ASCII inline in chat unless the user overrides mid-session
  - MUST preserve the preset variables for analyze.md preamble

ON_ERROR:
  load_failed -> EMIT "Cannot load target workflow — check that {cf-studio-path} is correctly set." STOP_TURN
```
