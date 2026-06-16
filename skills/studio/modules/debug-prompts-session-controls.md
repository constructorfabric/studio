# Debug Prompts Session Controls

```pdsl
UNIT DebugDisableRun
PURPOSE: Turn the debugger off and hand control back to normal cf execution.
DO:
  SET CF_DEBUG = off; SET DEBUG_MODE = step; SET DEBUG_TARGET_INPUT_HANDOFF = off; SET DEBUG_TARGET_INPUT_LOC = unset
  EMIT "Debugger off. Skills and workflows now run normally with no per-step breakpoints. Re-invoke cf-debug-prompts to arm it again."
  RUN resume the target workflow normally, or end the turn if there is no active target
RULES:
  ALWAYS leave DEBUG_TRACE intact after disabling so the session history stays inspectable.
  NEVER keep gating actions once CF_DEBUG == off.
UNIT DebugStopRun
PURPOSE: Halt immediately, staying paused at the current breakpoint.
DO:
  EMIT "Halted at the current breakpoint. Debug stays on. Send any message to reopen the debugger console."
  STOP_TURN
RULES:
  ALWAYS keep CF_DEBUG = on and the cursor where it is so the session can resume from the same breakpoint.
```
