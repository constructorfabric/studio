# Debug Prompts Input Handoff
```pdsl
UNIT DebugTargetInputHandoff
PURPOSE: Hand target WAIT/menu input to the target workflow while staying in run mode.
DO:
  CONTINUE DebugStepGatePrepare
  SET DEBUG_TARGET_INPUT_HANDOFF = awaiting-user
  SET DEBUG_TARGET_INPUT_LOC = SOURCE_LOC
  EMIT "Run-mode pause at <SOURCE_LOC>: the target workflow needs input. Executing its prompt/menu now; your next reply goes to the target workflow and will be traced."
  RUN execute the pending target WAIT/menu now, mark its DEBUG_TRACE entry executed, and surface the target prompt/menu exactly as authored
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS bypass the debugger console for this handoff while DEBUG_MODE == run
  ALWAYS preserve the current cursor and breakpoints across the handoff
  NEVER treat the next reply as a debugger command while DEBUG_TARGET_INPUT_HANDOFF == awaiting-user
```
