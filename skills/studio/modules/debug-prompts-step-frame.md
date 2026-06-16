# Debug Prompts Step Frame
```pdsl
UNIT DebugStepGateRenderFrame
PURPOSE: Emit the full debugger frame for the current pending action.
DO:
  CONTINUE DebugStepGateRenderFrameContext
  CONTINUE DebugStepGateRenderFrameSession
UNIT DebugStepGateRenderFrameContext
PURPOSE: Emit the debugger frame lines that describe the current action and its immediate context.
DO:
  EMIT the debugger frame:
    - "WHERE  : <SOURCE_LOC> > <UNIT> > step <DEBUG_CURSOR>"
    - "TARGET : <TARGET_LOC, or `(no file touched)` when the action reads/writes no file>"
    - "NOW    : <the pending action, verbatim> (<SOURCE_LOC>)"
    - "WHY    : <one-line rationale: the owning PURPOSE or rule this action serves; condense a multi-sentence PURPOSE to its core reason in one line>"
UNIT DebugStepGateRenderFrameSession
PURPOSE: Emit the debugger frame lines that describe the next control point and session status.
DO:
  EMIT the debugger frame:
    - "NEXT   : <the immediate next action(s) if this one runs; for a branch, the first action of each branch; cap the list at 3 and append `(+N more)` when longer, each suffixed with its filename.md:N>"
    - "BREAKPT: <id+type+spec of the breakpoint that fired, or `(stepping)` when paused by step mode>"
    - "METRICS: this +<this_lines> LoC +<this_chars> chars <this_token_display> | total <DEBUG_LOC_TOTAL> LoC <DEBUG_CHARS_TOTAL> chars <total_token_display>"
    - "STATE  : debug=on mode=<DEBUG_MODE> grain=<DEBUG_GRAIN> cursor=<DEBUG_CURSOR> bps=<count of enabled breakpoints>"
```
