---
cf: true
type: workflow
name: cf-brave-new-world
description: Invoke when the user or another skill or workflow needs or wants Brave New World mode, autonomous-by-default behavior, fewer confirmation questions, or a reversible safe path chosen automatically.
version: 0.1
purpose: Reduce nuisance questions by choosing any path that does not risk project damage, data loss, irreversible side effects, dangerous git operations, or external commitments.
---

# Brave New World

This workflow is a self-contained session overlay. It keeps normal Constructor
Studio control flow intact while answering only eligible non-destructive choices
autonomously.

```pdsl
UNIT BraveNewWorldActivate
PURPOSE: Enable the autonomous-default overlay for the current session without starting task work.
STATE:
  SET BRAVE_NEW_WORLD_ENABLED: true | false (default false, scope session)
  SET BRAVE_NEW_WORLD_SCOPE: non-destructive-allow-by-default (default non-destructive-allow-by-default, scope session)
  SET BRAVE_NEW_WORLD_DECISION_LOG: list (default empty, scope session)
  SET BRAVE_NEW_WORLD_LAST_STATUS: enabled | disabled | autonomous-choice | fallback (default disabled, scope session)
WHEN:
  REQUIRE user explicitly requests one of: cf-brave-new-world, brave-new-world, Brave New World, autonomous-default mode
  NOT user requests disable, off, stop, turn off, or disable autonomous defaults
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/brave-new-world-session.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/brave-new-world-choice.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/brave-new-world-choice-follow-up.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/brave-new-world-eligibility.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/brave-new-world-fallback-verification.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN BraveNewWorldSessionEnable
RULES:
  ALWAYS treat this workflow as an overlay on later workflow execution, not as a replacement workflow
  ALWAYS remember git-commit-mode so any later commit request in this active overlay session runs GitCommitModeGate before routing, git use, or delegation
  ALWAYS keep all current and future underlying rules, prerequisites, menus, waits, hard stops, validation gates, and terminal shapes active, while allowing this overlay to answer eligible menus and questions by selecting one valid original option
  ALWAYS keep BRAVE_NEW_WORLD_DECISION_LOG append-only for the session across disable and re-enable cycles
  ALWAYS resolve semantically equivalent phrases such as 'stop asking me', 'auto mode', 'autonomous', 'fewer questions', 'less interruptions' as BNW activation when context is unambiguous
  NEVER start substantive task work merely because this overlay was enabled
  NEVER require `cf` or `CFS_INIT == true` merely to enable or disable this overlay
```

```pdsl
UNIT BraveNewWorldDisable
PURPOSE: Turn off the autonomous-default overlay without shutting down Constructor Studio.
WHEN:
  REQUIRE user requests disable, off, stop, turn off, stop autonomous-default mode, turn off autonomous defaults, or disable autonomous defaults for Brave New World
DO:
  RUN resolve disable intent before activation intent WHEN a request contains both
  SET BRAVE_NEW_WORLD_ENABLED = false
  SET BRAVE_NEW_WORLD_LAST_STATUS = disabled
  EMIT "Brave New World disabled: original menus and questions will be shown normally."
  EMIT a summary when BRAVE_NEW_WORLD_DECISION_LOG is non-empty: "During this BNW session, N autonomous choices were made. Reply 'show BNW log' to see the full list." WHEN BRAVE_NEW_WORLD_DECISION_LOG != empty
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  RUN NextActionsOffer
RULES:
  ALWAYS give disable intent precedence over activation intent
  ALWAYS disable only this overlay and leave Constructor Studio rules, loaded context, and session state intact
  NEVER treat disabling this overlay as a Studio shutdown or session unload
```
