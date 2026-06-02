---
cf: true
type: workflow
name: cf-help
description: "Thin help router for Constructor Studio. Use for cf help, /cf help, cf-studio help, /cf-studio help, or cfs help; it presets the normal cf-explain storytelling help session and delegates to analyze.md."
version: 1.0
purpose: Standalone help command; presets cf help storytelling and passes through to analyze.md
---

```pdsl
UNIT RootSkillEntrypointBootstrap
PURPOSE: Prevent direct workflow entry from bypassing the root cf skill.
DO:
  - REQUIRE {cf-studio-path}/.core/skills/studio/SKILL.md is loaded completely
     and followed FIRST.
  - REQUIRE CfSkillInit, Bootstrap, HardRules, and
     WorkflowProtocolNonSubstitution from SKILL.md have completed.
  - CONTINUE this workflow only after the root cf skill routing/entrypoint
     selects it.
RULES:
  - ALWAYS execute before any workflow-specific unit in this file.
  - NEVER treat protocol.md, routing.md, or a thin proxy skill as a
    substitute for loading and following SKILL.md.
  - ALWAYS If this workflow file is opened directly, STOP workflow phases until
    SKILL.md has been loaded completely and followed.
  - ALWAYS This gate applies to the top-level controller only; dispatched sub-agents
    consume the synthesized final prompt and supplied context slices.
```

```pdsl
UNIT HelpProxy

PURPOSE:
  Pass through to analyze.md with the cf help preset active.

DO:
  - SET CF_HELP_PRESET = true
  - SET EXPLAIN_MODE = true
  - SET EXPLAIN_TARGET = "{cf-studio-path}"
  - SET STORYTELLING_MODE = "presentation"
  - SET STORYTELLING_ARTIFACT_DISPOSITION = "chat-only"
  - SET STORYTELLING_AUDIENCE = "Constructor Studio newcomers"
  - SET STORYTELLING_CONTEXT_PACK_STRATEGY = "hybrid"
  - SET STORYTELLING_PLAN_APPROVED = true
  - SET STORYTELLING_DIAGRAM_FORMAT = "ascii"
  - SET STORYTELLING_DIAGRAM_FORMAT_PRESET = true
  - SET STORYTELLING_HELP_GOAL = "Run a normal cf-explain storytelling session about Constructor Studio itself: target {cf-studio-path}, presentation mode, chat-only, newcomers audience, source-grounded portions, normal navigation."
  - LOAD skill `cf` IN ANALYZE + EXPLAIN mode, CF_HELP_PRESET=true

RULES:
  - NEVER render custom one-shot help here
  - NEVER ask the diagram-format lazy prompt in help mode
  - ALWAYS render help-mode diagrams as ASCII inline in chat unless the user overrides mid-session
  - ALWAYS preserve the preset variables for analyze.md preamble

ON_ERROR:
  load_failed -> EMIT "Cannot load target workflow — check that {cf-studio-path} is correctly set." STOP_TURN
```
