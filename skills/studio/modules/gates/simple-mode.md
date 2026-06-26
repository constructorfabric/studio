# Simple Mode Gate

```pdsl
UNIT SimpleModeGate
PURPOSE: Ask once per session which workflow interaction mode Studio should use, then apply any mode-specific session setup.
STATE:
  - SET SIMPLE_MODE: unset | simple | normal | debug (default unset, scope session)
  - SET SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION: unset | enable | skip (default unset, scope session)
  - SET ASSISTANT_MODE_NAME: string | unset (default unset, scope session)
WHEN:
  - REQUIRE a non-exempt cf workflow is loading
DO:
  - LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-simple.md WHEN SIMPLE_MODE == simple
  - CONTINUE SimpleModeSimpleEntry WHEN SIMPLE_MODE == simple
  - LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-debug.md WHEN SIMPLE_MODE == debug
  - CONTINUE SimpleModeDebug WHEN SIMPLE_MODE == debug
  - LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-normal.md WHEN SIMPLE_MODE == normal
  - CONTINUE SimpleModeNormal WHEN SIMPLE_MODE == normal
  - EMIT_MENU SimpleModeChoice WHEN SIMPLE_MODE == unset
  - WAIT user.reply WHEN SIMPLE_MODE == unset
  - STOP_TURN WHEN SIMPLE_MODE == unset
RULES:
  - ALWAYS run before workflow-specific routing, discovery, planning, validation, authoring, review, or writes in non-exempt workflows
  - ALWAYS remember the selected interaction mode for the whole session
  - ALWAYS remember the Brave New World opt-in or skip decision for the whole session after the user answers it
  - NEVER run for `cf-debug-prompts` or `cf-help`
MENU SimpleModeChoice
TITLE: Choose interaction mode for this session — reply with a number. You can change mode any time by saying "change mode".
OPTIONS:
  1 assistant — explains each step, why it is happening, and which path is recommended -> SET SIMPLE_MODE = simple; LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-simple.md; CONTINUE SimpleModeSimpleEntry
  2 normal — standard workflow behavior, no extra narration (suggested) -> SET SIMPLE_MODE = normal; LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-normal.md; CONTINUE SimpleModeNormal
  3 debug — debugger overlay in run mode, for workflow development only -> SET SIMPLE_MODE = debug; LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-debug.md; CONTINUE SimpleModeDebug
  INVALID -> EMIT_MENU SimpleModeChoice
```
