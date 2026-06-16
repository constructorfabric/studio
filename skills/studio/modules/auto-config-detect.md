# Auto-Config Detect

```pdsl
UNIT AutoConfigDetect
PURPOSE: Detect systems and semantic topics, then confirm the system map and topic split before generating.
WHEN:
  REQUIRE the documentation map is confirmed
DO:
  RUN detect systems (Monolith | Monorepo | Microservices | Library) and semantic topics (conventions, architecture, patterns, testing, api-contracts, infrastructure, security, anti-patterns)
  EMIT the System Map and Topic/Rule-file map checkpoints
  LOAD {cf-studio-path}/.core/skills/studio/modules/auto-config-generate.md
  EMIT_MENU DetectConfirmMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS propose only topics with at least 3 project-specific rules, merge topics with fewer, and split any topic over 120 lines
  ALWAYS confirm the system map and topic split before generating
  ALWAYS use activity-based WHEN conditions, never location-based
MENU DetectConfirmMenu
TITLE: System and topic map — proceed to rule generation?
OPTIONS:
  1 proceed -> CONTINUE AutoConfigGenerate
  2 adjust -> revise systems/topics per user feedback and EMIT_MENU DetectConfirmMenu
  3 cancel -> RETURN a blocked AUTO_CONFIG_RESULT with reason="auto-config cancelled at the system/topic map checkpoint" and next_action="re-run auto-config to continue" and STOP_TURN
  INVALID -> EMIT_MENU DetectConfirmMenu
```
