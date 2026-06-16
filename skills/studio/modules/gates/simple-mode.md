# Simple Mode Gate

```pdsl
UNIT SimpleModeGate
PURPOSE: Ask once per session which workflow interaction mode Studio should use, then apply any mode-specific session setup.
STATE:
  - SET SIMPLE_MODE: unset | simple | normal | debug (default unset, scope session)
  - SET SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION: unset | enable | skip (default unset, scope session)
WHEN:
  - REQUIRE a non-exempt cf workflow is loading
DO:
  - CONTINUE SimpleModeLoadRules WHEN SIMPLE_MODE == simple
  - CONTINUE SimpleModeDebug WHEN SIMPLE_MODE == debug
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
TITLE: Choose workflow interaction mode for this session. Simple mode explains where we are, what each menu does, and why choices matter; normal mode keeps existing workflow behavior; debug loads the existing debugger overlay in run mode so traces/logs stay active and it pauses only on breakpoints, WAIT/menu, or error until you turn step mode back on. Reply with a number.
OPTIONS:
  1 simple -> SET SIMPLE_MODE = simple; CONTINUE SimpleModeLoadRules
  2 normal -> SET SIMPLE_MODE = normal; CONTINUE SimpleModeNormal
  3 debug -> SET SIMPLE_MODE = debug; CONTINUE SimpleModeDebug
  INVALID -> EMIT_MENU SimpleModeChoice
```

```pdsl
UNIT SimpleModeLoadRules
PURPOSE: Load simple-mode behavior rules only after the user has selected simple mode.
WHEN:
  - REQUIRE SIMPLE_MODE == simple
DO:
  - LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-rules.md
  - RUN SimpleModeRulesActive
  - CONTINUE SimpleModeBraveNewWorldGate
RULES:
  - ALWAYS keep simple-mode behavior rules in `simple-mode-rules.md` so normal mode does not load them
  - NEVER load `simple-mode-rules.md` for normal mode or unset mode
```

```pdsl
UNIT SimpleModeBraveNewWorldGate
PURPOSE: Offer a once-per-session opt-in to enable Brave New World after simple-mode rules are active.
WHEN:
  - REQUIRE SIMPLE_MODE == simple
DO:
  - EMIT_MENU SimpleModeBraveNewWorldChoice WHEN SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION == unset
  - WAIT user.reply WHEN SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION == unset
  - STOP_TURN WHEN SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION == unset
RULES:
  - ALWAYS offer Brave New World only after simple-mode rules load
  - ALWAYS keep Brave New World opt-in explicit; simple mode alone must not enable it
  - NEVER bypass the menu until a saved Brave New World decision exists
MENU SimpleModeBraveNewWorldChoice
TITLE: Simple mode is active. Also enable Brave New World for this session? Brave New World automatically chooses non-destructive, reversible workflow options when the current rules make that safe, or you can skip it and keep simple mode only. Reply with a number.
OPTIONS:
  1 enable Brave New World -> SET SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION = enable; CONTINUE SimpleModeBraveNewWorldEnable
  2 skip -> SET SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION = skip; CONTINUE SimpleModeBraveNewWorldSkip
  INVALID -> EMIT_MENU SimpleModeBraveNewWorldChoice
```

```pdsl
UNIT SimpleModeBraveNewWorldEnable
PURPOSE: Reuse the canonical Brave New World session initialization path after explicit opt-in from simple mode.
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
PURPOSE: Continue with simple mode only after the user declines Brave New World.
WHEN:
  - REQUIRE SIMPLE_MODE == simple
  - REQUIRE SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION == skip
DO:
  - REQUIRE SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION == skip
RULES:
  - ALWAYS preserve simple-mode behavior after Brave New World is skipped
```

```pdsl
UNIT SimpleModeNormal
PURPOSE: Preserve existing workflow behavior after the user declines simple mode.
WHEN:
  - REQUIRE SIMPLE_MODE == normal
DO:
  - REQUIRE SIMPLE_MODE == normal
RULES:
  - ALWAYS continue with the workflow's existing menus, gates, stops, and output contracts
  - NEVER add simple-mode explanations or automatic selections while SIMPLE_MODE == normal
```

```pdsl
UNIT SimpleModeDebug
PURPOSE: Reuse the canonical debugger overlay in run mode without opening the standalone debugger console.
WHEN:
  - REQUIRE SIMPLE_MODE == debug
DO:
  - LOAD {cf-studio-path}/.core/workflows/debug-prompts.md
  - RUN DebugSessionRunModeInit
RULES:
  - ALWAYS reuse the canonical `cf-debug-prompts` workflow instead of duplicating debugger state here
  - ALWAYS arm the debugger in run mode on first activation so traces, logs, and breakpoints stay active without per-action stepping
  - NEVER open the standalone debugger console from the simple-mode gate
  - NEVER clear an active debugger session during reuse for later workflow entries
```
