# Debug Prompts Command Menu Nav

```pdsl
UNIT DebugCommandRouteNavigation
PURPOSE: Route debugger navigation commands that stay within the active session.
DO:
  CONTINUE DebugStepBackRun WHEN user.reply == back
  CONTINUE DebugContinueRun WHEN user.reply == cont OR user.reply == c OR user.reply == continue
  CONTINUE DebugWhereRun WHEN user.reply == where OR user.reply == w
  CONTINUE DebugToggleGrainRun WHEN user.reply == grain OR user.reply == g
  CONTINUE DebugStepModeEnableRun WHEN user.reply == step mode
UNIT DebugCommandRouteSession
PURPOSE: Route debugger commands that change or export the current session.
DO:
  CONTINUE DebugDisableRun WHEN user.reply == off
  CONTINUE DebugStopRun WHEN user.reply == stop
  CONTINUE DebugExportTraceRun WHEN user.reply == dump
UNIT DebugCommandRouterFallback
PURPOSE: Re-show the cheatsheet when the debugger command is not recognized.
DO:
  RUN DebugCheatsheet
  WAIT user.reply
  STOP_TURN
UNIT DebugCommandOpenMenu
PURPOSE: Open the full debugger menu on demand from the compact console.
DO:
  EMIT_MENU DebuggerMenu
  WAIT user.reply
  STOP_TURN
MENU DebuggerMenu:
  TITLE: "Debugger — full menu (open with `dbg`)"
  OPTIONS:
    1 step -> RUN execute the pending action now, mark its DEBUG_TRACE entry executed, then RUN DebugStepGate on the next action
    2 over -> RUN skip the pending action without executing it, mark its DEBUG_TRACE entry skipped, then RUN DebugStepGate on the next action
    3 back -> CONTINUE DebugStepBackRun
    4 continue -> CONTINUE DebugContinueRun
    5 where -> CONTINUE DebugWhereRun
    6 grain -> CONTINUE DebugToggleGrainRun
    7 off -> CONTINUE DebugDisableRun
    8 stop -> CONTINUE DebugStopRun
    9 bp -> CONTINUE DebugBreakpoints
    10 dump -> CONTINUE DebugExportTraceRun
    11 step mode -> CONTINUE DebugStepModeEnableRun
  INVALID:
    EMIT "Reply with 1 (step), 2 (over), 3 (back), 4 (continue), 5 (where), 6 (grain), 7 (off), 8 (stop), 9 (bp), 10 (dump), or 11 (step mode). Breakpoint commands also work directly: b <spec>, bc <ref>, bl, be <id>, bd <id>, run to <loc>."
    WAIT user.reply
    STOP_TURN
```
