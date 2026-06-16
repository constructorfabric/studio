```pdsl
UNIT DebugStepGateRun
PURPOSE: The breakpoint. Stop before a pending action, explain it, and wait for the user.
WHEN:
  REQUIRE CF_DEBUG == on
  AND a prospective gated action is pending
  AND DEBUG_MODE == step AND DEBUG_GRAIN == instruction
    OR DEBUG_MODE == step AND DEBUG_GRAIN == unit AND the pending action enters a UNIT, MENU, skill load, or workflow load
    OR the pending action is a WAIT/menu or an error handler
    OR DebugBreakpointMatch returns a hit for the pending action
DO:
  CONTINUE DebugTargetInputHandoff WHEN DEBUG_MODE == run AND the pending action is a target WAIT/menu
  CONTINUE DebugStepGatePrepare
  CONTINUE DebugStepGateRenderFrame
  RUN DebugCheatsheet
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS show all eight frame lines (WHERE, TARGET, NOW, WHY, NEXT, BREAKPT, METRICS, STATE) on every pause, followed by the cheatsheet.
  ALWAYS use the token display values prepared by DebugMetrics and attach filename.md:N locators per DebugLocators.
  ALWAYS quote the pending action faithfully; never summarize it into something vaguer.
  NEVER run the pending action inside this gate; running it is the explicit job of the `step` choice.
UNIT DebugStepGatePrepare
PURPOSE: Record the pending target action and resolve the frame context before a pause is shown.
DO:
  SET DEBUG_CURSOR = DEBUG_CURSOR + 1
  RUN append the pending action to DEBUG_TRACE with actor = controller, status = pending, only when the action belongs to the target skill/workflow (never for cf-debug-prompts's own actions)
  RUN resolve SOURCE_LOC and TARGET_LOC for the pending action (see DebugLocators)
  RUN DebugMetrics to record this action's loaded lines/chars and update totals
UNIT DebugRunModeActionRecordRun
PURPOSE: Log a target action immediately before it runs without pausing while DEBUG_MODE == run.
WHEN:
  REQUIRE CF_DEBUG == on
  REQUIRE DEBUG_MODE == run
DO:
  SET DEBUG_CURSOR = DEBUG_CURSOR + 1
  RUN append the pending target action to DEBUG_TRACE with actor = controller and status = pending
  RUN resolve SOURCE_LOC and TARGET_LOC for the pending action (see DebugLocators)
  RUN DebugMetrics to record this action's loaded lines/chars and update totals
RULES:
  ALWAYS use this unit only for non-debug target actions that are about to execute without a DebugStepGate pause
  ALWAYS mark the recorded trace entry executed after the action succeeds
  ALWAYS leave the recorded trace entry available to DebugRunFailure when the action fails
  NEVER record cf-debug-prompts's own debugger-console actions
```
