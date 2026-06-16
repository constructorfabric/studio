```pdsl
UNIT DebugWhereRun
PURPOSE: Re-print the current debugger frame and a short trace summary.
DO:
  RUN resolve SOURCE_LOC and TARGET_LOC for the current step (see DebugLocators)
  RUN re-emit the debugger frame for the current DEBUG_CURSOR with filename.md:N locators
  EMIT "TRACE: <compact list of recent DEBUG_TRACE entries; each entry suffixed with its filename.md:N locator>"
  RUN DebugCheatsheet
  WAIT user.reply
  STOP_TURN
UNIT DebugToggleGrainRun
PURPOSE: Switch between instruction-level and unit-level stepping.
DO:
  CONTINUE DebugToggleGrainToUnit WHEN DEBUG_GRAIN == instruction
  CONTINUE DebugToggleGrainToInstruction WHEN DEBUG_GRAIN != instruction
UNIT DebugToggleGrainToUnit
PURPOSE: Switch the debugger from instruction stepping to unit stepping.
DO:
  SET DEBUG_GRAIN = unit
  EMIT "Grain set to unit: the debugger now pauses before each UNIT, MENU, skill load, or workflow load, not every instruction."
  CONTINUE DebugToggleGrainPause
UNIT DebugToggleGrainToInstruction
PURPOSE: Switch the debugger from unit stepping to instruction stepping.
DO:
  SET DEBUG_GRAIN = instruction
  EMIT "Grain set to instruction: the debugger now pauses before every PDSL action."
  CONTINUE DebugToggleGrainPause
UNIT DebugToggleGrainPause
PURPOSE: Re-open the debugger prompt after a grain change.
DO:
  RUN DebugCheatsheet
  WAIT user.reply
  STOP_TURN
UNIT DebugStepModeEnableRun
PURPOSE: Return the debugger to per-action stepping without executing the pending action.
DO:
  SET DEBUG_MODE = step
  EMIT "Step mode on. The debugger now pauses before every gated action until you switch back to run mode."
  RUN DebugCheatsheet
  WAIT user.reply
  STOP_TURN
```
