# Debug Prompts Step Nav

```pdsl
UNIT DebugStepBackRun
PURPOSE: Move the cursor to a previous step and re-inspect it.
DO:
  CONTINUE DebugStepBackReinspect WHEN DEBUG_CURSOR > 1
  CONTINUE DebugStepBackAtStart WHEN DEBUG_CURSOR <= 1
RULES:
  ALWAYS warn that step back only repositions the cursor for inspection and re-narration.
  NEVER claim that already-applied side effects (file writes, shell exec, sub-agent dispatch) were undone.
  ALWAYS require an explicit fresh `step` confirmation before re-executing an action reached by stepping back.
UNIT DebugStepBackReinspect
PURPOSE: Move the cursor back one step and re-show that earlier frame.
DO:
  SET DEBUG_CURSOR = DEBUG_CURSOR - 1
  EMIT "Stepped back. Re-showing the previous frame for inspection."
  RUN re-emit the debugger frame for the DEBUG_TRACE entry at DEBUG_CURSOR
  RUN DebugCheatsheet
  WAIT user.reply
  STOP_TURN
UNIT DebugStepBackAtStart
PURPOSE: Report that the debugger cannot step back before the first recorded action.
DO:
  EMIT "Already at the first step; cannot step back further."
  RUN DebugCheatsheet
  WAIT user.reply
  STOP_TURN
UNIT DebugContinueRun
PURPOSE: Run without pausing at every action until the next breakpoint or natural stop.
DO:
  SET DEBUG_MODE = run
  EMIT "Continuing. The debugger runs subsequent actions without pausing until the next breakpoint hit, target input handoff (WAIT/menu), or failure."
  RUN DebugRunModeResume
RULES:
  ALWAYS keep CF_DEBUG = on while in run mode; continue does not disarm the debugger.
  ALWAYS honor user requests to return to step mode.
UNIT DebugRunModeResume
PURPOSE: Resume target execution under run mode until the next breakpoint, target-input handoff, or failure.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-breakpoint-match.md
  RUN before each action in run mode: RUN DebugBreakpointMatch and pause via DebugStepGate on a hit
  RUN resume executing the target workflow under DebugOverlayInvariants in run mode
RULES:
  ALWAYS evaluate breakpoints before run-mode actions
  ALWAYS route target WAIT/menu pauses through DebugTargetInputHandoff
  ALWAYS route run-mode target-action failures through DebugRunFailureRun
  ALWAYS preserve cursor and trace state across breakpoint, handoff, and failure pauses
ON_ERROR:
  run_failed -> CONTINUE DebugRunFailureRun
```
