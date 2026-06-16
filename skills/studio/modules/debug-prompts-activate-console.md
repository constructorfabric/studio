# Debug Prompts Activate Console
```pdsl
UNIT DebugSessionConsoleOpen
PURPOSE: Announce the debugger console after the debugger session state is initialized.
DO:
  EMIT "Debugger armed. From now on every cf skill/workflow instruction stops at a breakpoint before it runs. Load the skill you want to debug, then drive it from this console."
  EMIT "Commands: step=run the pending action · over=skip it · back=re-inspect the previous step · cont=run to the next breakpoint · step mode=return to per-action pauses · dump=export trace · off=disable · stop=halt · dbg=full menu. Breakpoints: b <spec>=set · bc <ref>=clear · bl=list · be/bd <id>=enable/disable · run to <loc>."
  RUN DebugCheatsheet
  WAIT user.reply
  STOP_TURN
UNIT DebugOverlayInvariants
PURPOSE: Make the breakpoint gate mandatory and global while debug is on.
WHEN:
  REQUIRE CF_DEBUG == on
INVARIANTS:
  ALWAYS run DebugStepGate before performing any prospective target action (LOAD, RUN, CONTINUE, DISPATCH, SET, EMIT_MENU, file write, shell exec, or sub-agent dispatch) in a non-debug cf skill or workflow when step mode, breakpoint, WAIT/menu, or error conditions require a pause.
  ALWAYS apply the gate across target skill and workflow boundaries.
  ALWAYS record every gated target action in DEBUG_TRACE with its resolved status (executed | skipped | replayed).
  ALWAYS record every run-mode target action through DebugRunModeActionRecord before execution when DebugStepGate does not pause.
  NEVER perform a target action while CF_DEBUG == on without either passing DebugStepGate or recording it through DebugRunModeActionRecord.
  NEVER silently disarm the overlay because a target workflow defines its own menus or gates; those gates are themselves stepped through.
  ALWAYS fail closed by treating unclear gate status as gated and pausing.
  ALWAYS attach a filename.md:N locator (per DebugLocators) to every action, menu, unit, and instruction the debugger names while CF_DEBUG == on.
  ALWAYS keep DEBUG_SLUG = the basename without extension of the skill/workflow file currently being stepped.
  ALWAYS append an actor=user entry to DEBUG_TRACE only for user replies the target skill/workflow consumes, recording the verbatim reply as action and the target prompt's filename.md:N as loc.
  ALWAYS route a run-mode target WAIT/menu pause through DebugTargetInputHandoff.
  ALWAYS route run-mode target-action failures through DebugRunFailure while preserving cursor and trace state.
  NEVER record cf-debug-prompts's own activity in DEBUG_TRACE.
  ALWAYS keep DEBUG_TRACE limited to non-debug target activity only.
  NEVER gate cf-debug-prompts's own debugger-console actions through DebugStepGate.
```
