# Debug Prompts State Session
```pdsl
UNIT DebugState
PURPOSE: Define the session-scoped state the debugger tracks.
STATE:
  SET CF_DEBUG: on | off (default off, scope session)
  SET DEBUG_MODE: step | run (default step, scope session)
  SET DEBUG_GRAIN: instruction | unit (default instruction, scope session)
  SET DEBUG_CURSOR: integer pointer into DEBUG_TRACE (default 0, scope session)
  SET DEBUG_TRACE: ordered list of {seq, actor, loc, where, action, why, status, lines, chars, tok_est} (default empty, scope session)
  SET DEBUG_LOC_TOTAL: cumulative lines of target content loaded so far (default 0, scope session)
  SET DEBUG_CHARS_TOTAL: cumulative characters of target content loaded so far (default 0, scope session)
  SET DEBUG_TOKENS_EST: cumulative APPROXIMATE token/context-usage estimate (default 0, scope session)
  SET DEBUG_BREAKPOINTS: list of {id, type, spec, enabled, oneshot} (default empty, scope session)
  SET DEBUG_SLUG: slug of the skill/workflow under debug (default session, scope session)
  SET DEBUG_TARGET_INPUT_HANDOFF: off | awaiting-user (default off, scope session)
  SET DEBUG_TARGET_INPUT_LOC: string | unset (default unset, scope session)
NOTES:
  step mode pauses before every gated action; run mode pauses only at a breakpoint, a WAIT/menu, or an error. instruction grain gates each PDSL action; unit grain gates each UNIT, MENU, skill load, or workflow load. Each breakpoint has a stable short id (b1, b2, ...) and one of four types: line -> filename.md:N or filename.md:N-M, unit -> a UNIT or MENU name, kind -> one of write | edit | exec | dispatch | menu | load, cond -> VAR ==|!=|matches value.
UNIT DebugSessionStateInit
PURPOSE: Initialize debugger session state before opening the debugger console.
DO:
  SET CF_DEBUG = on
  SET DEBUG_MODE = step
  SET DEBUG_GRAIN = instruction
  SET DEBUG_CURSOR = 0
UNIT DebugSessionRunModeInitRun
PURPOSE: Arm or reuse the debugger overlay in run mode without opening the standalone debugger console.
DO:
  CONTINUE DebugSessionRunModeArm WHEN CF_DEBUG != on
  CONTINUE DebugSessionRunModeReuse WHEN CF_DEBUG == on
RULES:
  ALWAYS keep the existing debug trace and breakpoints when reusing an active debugger session
  NEVER stop the turn or open the standalone debugger console from this init path
UNIT DebugSessionRunModeArm
PURPOSE: Initialize a fresh debugger session in run mode for simple-mode debug.
DO:
  SET CF_DEBUG = on; SET DEBUG_MODE = run; SET DEBUG_GRAIN = instruction; SET DEBUG_CURSOR = 0
  EMIT "Debugger armed in run mode. Tracing, logs, and breakpoints stay active; pauses happen on breakpoints, WAIT/menu, or errors. Use `step mode` later to return to per-action stepping."
UNIT DebugSessionRunModeReuse
PURPOSE: Reuse the active debugger session without resetting its current trace or breakpoint state.
DO:
  REQUIRE CF_DEBUG == on
  SET DEBUG_MODE = run
RULES:
  ALWAYS preserve the existing trace, cursor, grain, and breakpoints while converging reuse to run mode
```
