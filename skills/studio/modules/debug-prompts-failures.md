# Debug Prompts Failures
```pdsl
UNIT DebugStepFailureRun
PURPOSE: Recover when the action currently being stepped fails to execute.
ON_ERROR:
  step_failed -> EMIT "The stepped action failed to execute. Reporting the error verbatim and staying paused at this breakpoint."; EMIT "ERROR: <the raw error from the failed action>"; EMIT_MENU DebugStepFailureMenu; WAIT user.reply; STOP_TURN
MENU DebugStepFailureMenu:
  TITLE: "Stepped action failed."
  OPTIONS:
    1 retry -> RUN re-attempt the failed action, mark its DEBUG_TRACE entry replayed, then RUN DebugStepGate on the next action
    2 over -> RUN skip the failed action, mark its DEBUG_TRACE entry skipped, then RUN DebugStepGate on the next action
    3 off -> CONTINUE DebugDisable
    4 stop -> CONTINUE DebugStop
  INVALID:
    EMIT "Reply `1`, `2`, `3`, or `4`."
    WAIT user.reply
    STOP_TURN
UNIT DebugRunFailureRun
PURPOSE: Recover when a target action fails while run mode is executing without per-action pauses.
ON_ERROR:
  run_failed -> EMIT "A run-mode target action failed. Reporting the error verbatim and staying paused at the failed action with cursor and trace preserved."; EMIT "ERROR: <the raw error from the failed action>"; EMIT_MENU DebugRunFailureMenu; WAIT user.reply; STOP_TURN
MENU DebugRunFailureMenu:
  TITLE: "Run-mode action failed."
  OPTIONS:
    1 retry -> LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-step-nav.md; RUN re-attempt the failed action, mark its DEBUG_TRACE entry replayed, then RUN DebugRunModeResume
    2 over -> LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-step-nav.md; RUN skip the failed action, mark its DEBUG_TRACE entry skipped, then RUN DebugRunModeResume
    3 off -> CONTINUE DebugDisable
    4 stop -> CONTINUE DebugStop
  INVALID:
    EMIT "Reply `1`, `2`, `3`, or `4`."
    WAIT user.reply
    STOP_TURN
```
