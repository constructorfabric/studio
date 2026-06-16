```pdsl
UNIT DebugBreakpointSet
PURPOSE: Append a normal breakpoint from a locator, unit, kind, or condition specification.
DO:
  RUN derive type+spec from the input (line: filename.md:N | unit: a UNIT/MENU name | kind: write|edit|exec|dispatch|menu|load | cond: VAR ==|!=|matches value)
  RUN append {id: next b<n>, type, spec, enabled: true, oneshot: false} to DEBUG_BREAKPOINTS
  EMIT "set <id> <type> <spec>" with its filename.md:N when the type is line or unit
  RUN DebugCheatsheet
  WAIT user.reply
  STOP_TURN
UNIT DebugBreakpointClear
PURPOSE: Remove one breakpoint by id/locator or clear them all.
DO:
  RUN remove the breakpoint matching the given id or locator; remove all WHEN spec == all
  EMIT "cleared <id-or-spec>"
  RUN DebugCheatsheet
  WAIT user.reply
  STOP_TURN
UNIT DebugBreakpointList
PURPOSE: Render the current breakpoint table.
DO:
  EMIT each breakpoint as "<id> <type> <spec> <enabled|disabled>" with its filename.md:N where applicable, or "(no breakpoints)"
  RUN DebugCheatsheet
  WAIT user.reply
  STOP_TURN
UNIT DebugBreakpointEnable
PURPOSE: Re-enable a disabled breakpoint.
DO:
  RUN set enabled = true on the breakpoint by id
  EMIT "enabled <id>"
  RUN DebugCheatsheet
  WAIT user.reply
  STOP_TURN
UNIT DebugBreakpointDisable
PURPOSE: Disable an existing breakpoint without removing it.
DO:
  RUN set enabled = false on the breakpoint by id
  EMIT "disabled <id>"
  RUN DebugCheatsheet
  WAIT user.reply
  STOP_TURN
UNIT DebugBreakpointRunTo
PURPOSE: Add a one-shot line breakpoint and resume execution until it fires.
DO:
  RUN append {id: next b<n>, type: line, spec: <filename.md:N>, enabled: true, oneshot: true} to DEBUG_BREAKPOINTS
  SET DEBUG_MODE = run
  EMIT "running to <filename.md:N> (one-shot)"
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-step-nav.md
  RUN DebugRunModeResume
```
