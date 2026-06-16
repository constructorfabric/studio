# Simple Mode Gate

```pdsl
UNIT SimpleModeGate
PURPOSE: Ask once per session whether Studio should use expanded explanations and safe automatic defaults.
STATE:
  SET SIMPLE_MODE: unset | simple | normal (default unset, scope session)
WHEN:
  REQUIRE a non-exempt cf workflow is loading
DO:
  CONTINUE SimpleModeLoadRules WHEN SIMPLE_MODE == simple
  CONTINUE SimpleModeNormal WHEN SIMPLE_MODE == normal
  EMIT_MENU SimpleModeChoice WHEN SIMPLE_MODE == unset
  WAIT user.reply WHEN SIMPLE_MODE == unset
  STOP_TURN WHEN SIMPLE_MODE == unset
RULES:
  ALWAYS run before workflow-specific routing, discovery, planning, validation, authoring, review, or writes in non-exempt workflows.
  ALWAYS remember either user choice for the whole session.
  NEVER run for `cf-debug-prompts` or `cf-help`.
MENU SimpleModeChoice
TITLE: Choose workflow interaction mode for this session. Simple mode explains where we are, what each menu does, and why choices matter; normal mode keeps existing workflow behavior. Reply with a number.
OPTIONS:
  1 simple -> SET SIMPLE_MODE = simple; CONTINUE SimpleModeLoadRules
  2 normal -> SET SIMPLE_MODE = normal; CONTINUE SimpleModeNormal
  INVALID -> EMIT_MENU SimpleModeChoice
```

```pdsl
UNIT SimpleModeLoadRules
PURPOSE: Load simple-mode behavior rules only after the user has selected simple mode.
WHEN:
  REQUIRE SIMPLE_MODE == simple
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-rules.md
  RUN SimpleModeRulesActive
RULES:
  ALWAYS keep simple-mode behavior rules in `simple-mode-rules.md` so normal mode does not load them.
  NEVER load `simple-mode-rules.md` when SIMPLE_MODE == normal or SIMPLE_MODE == unset.
```

```pdsl
UNIT SimpleModeNormal
PURPOSE: Preserve existing workflow behavior after the user declines simple mode.
WHEN:
  REQUIRE SIMPLE_MODE == normal
RULES:
  ALWAYS continue with the workflow's existing menus, gates, stops, and output contracts.
  NEVER add simple-mode explanations or automatic selections while SIMPLE_MODE == normal.
```
