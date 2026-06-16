# Debug Prompts Breakpoint Router
```pdsl
UNIT DebugBreakpointsRun
PURPOSE: Set, clear, list, enable, disable, and run-to breakpoints via short commands or plain language.
STATE:
  SET DEBUG_BREAKPOINT_ACTION: set | clear | list | enable | disable | run-to | invalid (default invalid, scope workflow_run)
DO:
  RUN DebugBreakpointActionParse
  CONTINUE DebugBreakpointActionDispatch
RULES:
  ALWAYS accept both short commands and plain-language equivalents for every action.
  ALWAYS assign a stable short id (b1, b2, ...) and reuse it for later enable/disable/clear.
  ALWAYS echo each breakpoint change with the affected breakpoint id and locator context.
  NEVER drop or renumber existing breakpoints during add or toggle operations.
NOTES:
  Short commands (also expressible in plain language): `b <spec>` set, `bc <ref>` clear, `bl` list, `be <id>` enable, `bd <id>` disable, `run to <loc>` run until filename.md:N then auto-remove.
UNIT DebugBreakpointActionDispatch
PURPOSE: Route the parsed breakpoint action to the matching breakpoint handler.
DO:
  CONTINUE DebugBreakpointActionDispatchPrimary WHEN DEBUG_BREAKPOINT_ACTION == set OR DEBUG_BREAKPOINT_ACTION == clear OR DEBUG_BREAKPOINT_ACTION == list
  CONTINUE DebugBreakpointActionDispatchSecondary WHEN DEBUG_BREAKPOINT_ACTION == enable OR DEBUG_BREAKPOINT_ACTION == disable OR DEBUG_BREAKPOINT_ACTION == run-to
  RUN DebugCheatsheet
  WAIT user.reply
  STOP_TURN
UNIT DebugBreakpointActionDispatchPrimary
PURPOSE: Route breakpoint creation, removal, and listing commands.
DO:
  CONTINUE DebugBreakpointSet WHEN DEBUG_BREAKPOINT_ACTION == set
  CONTINUE DebugBreakpointClear WHEN DEBUG_BREAKPOINT_ACTION == clear
  CONTINUE DebugBreakpointList WHEN DEBUG_BREAKPOINT_ACTION == list
UNIT DebugBreakpointActionDispatchSecondary
PURPOSE: Route breakpoint enable, disable, and run-to commands.
DO:
  CONTINUE DebugBreakpointEnable WHEN DEBUG_BREAKPOINT_ACTION == enable
  CONTINUE DebugBreakpointDisable WHEN DEBUG_BREAKPOINT_ACTION == disable
  CONTINUE DebugBreakpointRunTo WHEN DEBUG_BREAKPOINT_ACTION == run-to
UNIT DebugBreakpointActionParse
PURPOSE: Parse the user's breakpoint command into one canonical breakpoint action.
DO:
  RUN parse the user's request into one action: set | clear | list | enable | disable | run-to
```
