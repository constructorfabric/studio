# Debug Prompts Command Router
```pdsl
UNIT DebugCommandRouterRun
PURPOSE: Map a typed debugger command (from the cheatsheet) to its handler at any pause.
DO:
  CONTINUE DebugTargetInputResume WHEN DEBUG_TARGET_INPUT_HANDOFF == awaiting-user
  CONTINUE DebugCommandRouteExecution WHEN user.reply == step OR user.reply == s OR user.reply == over OR user.reply == o
  CONTINUE DebugCommandRouteNavigation WHEN user.reply == back OR user.reply == cont OR user.reply == c OR user.reply == continue OR user.reply == where OR user.reply == w OR user.reply == grain OR user.reply == g OR user.reply == step mode
  CONTINUE DebugCommandRouteSession WHEN user.reply == off OR user.reply == stop OR user.reply == dump
  CONTINUE DebugBreakpoints WHEN user.reply starts with b OR user.reply starts with bc OR user.reply == bl OR user.reply starts with be OR user.reply starts with bd OR user.reply starts with run to
  CONTINUE DebugCommandOpenMenu WHEN user.reply == dbg OR user.reply == menu OR user.reply == ?
  CONTINUE DebugCommandRouterFallback
RULES:
  ALWAYS accept the numeric choices from DebuggerMenu as equivalents (1 step ... 11 step mode).
  ALWAYS treat unrecognized input as a no-op that just re-shows the cheatsheet.
UNIT DebugTargetInputResume
PURPOSE: Route a run-mode handoff reply into the paused target workflow instead of the debugger console.
DO:
  RUN append the user's reply to DEBUG_TRACE with actor = user, loc = DEBUG_TARGET_INPUT_LOC, where = "reply to <DEBUG_TARGET_INPUT_LOC>", action = user.reply, why = the paused target workflow requested input, status = consumed
  SET DEBUG_TARGET_INPUT_HANDOFF = off
  SET DEBUG_TARGET_INPUT_LOC = unset
  RUN resume the paused target workflow from its WAIT/menu using user.reply under DebugOverlayInvariants
RULES:
  ALWAYS record the handoff reply before the target workflow consumes it
  ALWAYS bypass normal debugger command parsing for this reply
ON_ERROR:
  run_failed -> CONTINUE DebugRunFailure
UNIT DebugCommandRouteExecution
PURPOSE: Route debugger execution commands for the current pending action.
DO:
  CONTINUE DebugCommandStep WHEN user.reply == step OR user.reply == s
  CONTINUE DebugCommandOver WHEN user.reply == over OR user.reply == o
UNIT DebugCommandStep
PURPOSE: Execute the pending action from the debugger console.
DO:
  RUN execute the pending action now, mark its DEBUG_TRACE entry executed, then RUN DebugStepGate on the next action
UNIT DebugCommandOver
PURPOSE: Skip the pending action from the debugger console.
DO:
  RUN skip the pending action without executing it, mark its DEBUG_TRACE entry skipped, then RUN DebugStepGate on the next action
```
