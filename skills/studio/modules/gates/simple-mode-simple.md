# Simple Mode Branch

```pdsl
UNIT SimpleModeSimpleEntry
PURPOSE: Load assistant-mode behavior rules, then hand off to the Brave New World opt-in gate.
WHEN:
  - REQUIRE SIMPLE_MODE == simple
DO:
  - LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-rules.md
  - CONTINUE SimpleModeAssistantNameInit WHEN ASSISTANT_MODE_NAME == unset
  - RUN SimpleModeRulesActive
  - CONTINUE SimpleModeBraveNewWorldGate
RULES:
  - ALWAYS keep assistant-mode behavior rules in `simple-mode-rules.md` so normal mode does not load them
  - NEVER load `simple-mode-rules.md` for normal mode or unset mode
```

```pdsl
UNIT SimpleModeAssistantNameInit
PURPOSE: Initialize a stable assistant display name once per session before assistant-mode guidance is emitted.
WHEN:
  - REQUIRE SIMPLE_MODE == simple
  - REQUIRE ASSISTANT_MODE_NAME == unset
DO:
  - SET ASSISTANT_MODE_NAME = derive one short human first name from a stable curated assistant-name pool
  - RUN SimpleModeRulesActive
  - CONTINUE SimpleModeBraveNewWorldGate
RULES:
  - ALWAYS keep ASSISTANT_MODE_NAME stable for the whole session once it is set
  - ALWAYS choose a short plain given name suitable for the prefix `**<name> (assistant):**`
  - NEVER choose a username, a title, a role label, a multi-word name, or a joke name
```

```pdsl
UNIT SimpleModeBraveNewWorldGate
PURPOSE: Offer a once-per-session opt-in to enable Brave New World after assistant-mode rules are active.
WHEN:
  - REQUIRE SIMPLE_MODE == simple
DO:
  - EMIT_MENU SimpleModeBraveNewWorldChoice WHEN SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION == unset
  - WAIT user.reply WHEN SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION == unset
  - STOP_TURN WHEN SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION == unset
RULES:
  - ALWAYS offer Brave New World only after assistant-mode rules load
  - ALWAYS keep Brave New World opt-in explicit; assistant mode alone must not enable it
  - NEVER bypass the menu until a saved Brave New World decision exists
MENU SimpleModeBraveNewWorldChoice
TITLE: Assistant mode is active. Also enable Brave New World for this session? Brave New World automatically chooses non-destructive, reversible workflow options when the current rules make that safe, or you can skip it and keep assistant mode only. Reply with a number.
OPTIONS:
  1 enable Brave New World -> SET SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION = enable; CONTINUE SimpleModeBraveNewWorldEnable
  2 skip -> SET SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION = skip; CONTINUE SimpleModeBraveNewWorldSkip
  INVALID -> EMIT_MENU SimpleModeBraveNewWorldChoice
```

```pdsl
UNIT SimpleModeBraveNewWorldEnable
PURPOSE: Reuse the canonical Brave New World session initialization path after explicit opt-in from assistant mode.
WHEN:
  - REQUIRE SIMPLE_MODE == simple
  - REQUIRE SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION == enable
DO:
  - LOAD {cf-studio-path}/.core/workflows/brave-new-world.md
  - RUN BraveNewWorldSessionInit
RULES:
  - ALWAYS reuse the canonical `cf-brave-new-world` workflow initialization unit instead of duplicating overlay state rules here
  - NEVER auto-enable Brave New World without the explicit menu choice
```

```pdsl
UNIT SimpleModeBraveNewWorldSkip
PURPOSE: Continue with assistant mode only after the user declines Brave New World.
WHEN:
  - REQUIRE SIMPLE_MODE == simple
  - REQUIRE SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION == skip
DO:
  - REQUIRE SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION == skip
RULES:
  - ALWAYS preserve assistant-mode behavior after Brave New World is skipped
```
