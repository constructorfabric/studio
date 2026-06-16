# Debug Prompts Breakpoint Match
```pdsl
UNIT DebugBreakpointMatch
PURPOSE: Decide whether the pending action hits an enabled breakpoint.
DO:
  SET BP_HIT = the first enabled breakpoint in DEBUG_BREAKPOINTS that matches the pending action; else none
  RUN skip disabled breakpoints during matching
  RUN pause via DebugStepGate with the breakpoint id in the BREAKPT frame line WHEN BP_HIT != none AND DEBUG_MODE == run
  RETURN BP_HIT
RULES:
  ALWAYS evaluate only enabled breakpoints for hits.
  ALWAYS route run-mode breakpoint hits through DebugStepGate.
  ALWAYS remove a oneshot breakpoint from DEBUG_BREAKPOINTS immediately after it fires once.
  NEVER let breakpoint matching execute, skip, or mutate the pending action; it only decides whether to pause.
NOTES:
  Match semantics by type: line -> SOURCE_LOC equals filename.md:N or falls inside N-M; unit -> the pending action enters a UNIT or MENU whose name equals spec; kind -> the pending action's kind is write | edit | exec | dispatch | menu | load; cond -> the named state variable satisfies spec: VAR == value, VAR != value, or VAR matches pattern.
```
