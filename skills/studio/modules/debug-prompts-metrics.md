# Debug Prompts Metrics
```pdsl
UNIT DebugMetrics
PURPOSE: Count loaded LoC and characters per action and keep an approximate token estimate.
DO:
  CONTINUE DebugMetricsMeasureAction
  CONTINUE DebugMetricsAccumulateTotals
  CONTINUE DebugMetricsPrepareDisplay
RULES:
  ALWAYS count real lines/characters from the content the action actually loads; these are exact.
  ALWAYS label token displays as measured or estimated.
  ALWAYS prefer measured token and usage figures over estimated displays.
  NEVER present an estimated token display as exact or authoritative.
NOTES:
  lines/chars cover content loaded into context (file reads, LOADs, dispatched context). The token figure is approximate (~chars/4) unless a real usage number is available from the host.
UNIT DebugMetricsMeasureAction
PURPOSE: Measure the pending action's loaded context and store per-action counts.
DO:
  SET this_lines = the number of lines the pending action loads into context (0 when it loads no file/content)
  SET this_chars = the number of characters the pending action loads into context (0 when none)
  SET this_tok_est = round(this_chars / 4)
  RUN store {lines: this_lines, chars: this_chars, tok_est: this_tok_est} on the action's DEBUG_TRACE entry
UNIT DebugMetricsAccumulateTotals
PURPOSE: Roll the current action's counts into the debugger session totals.
DO:
  SET DEBUG_LOC_TOTAL = DEBUG_LOC_TOTAL + this_lines; SET DEBUG_CHARS_TOTAL = DEBUG_CHARS_TOTAL + this_chars; SET DEBUG_TOKENS_EST = DEBUG_TOKENS_EST + this_tok_est
UNIT DebugMetricsPrepareDisplay
PURPOSE: Prepare measured or estimated token-display strings for the frame.
DO:
  SET this_token_display = "~<this_tok_est> tok est"; SET total_token_display = "~<DEBUG_TOKENS_EST> tok est"
  SET this_token_display and total_token_display from the host-exposed real token or usage figure, marked as measured, WHEN the host exposes a real token or usage figure
UNIT DebugCheatsheet
PURPOSE: Show a compact command hint at every debugger pause instead of the full menu.
DO:
  EMIT "dbg> step over back cont · step mode · dump · off stop"
  EMIT "    bp: b <spec> · bc <ref> · bl · be/bd <id> · run to <loc> · grain"
  EMIT "    dbg=full menu"
RULES:
  ALWAYS keep the cheatsheet to at most three lines.
  ALWAYS interpret the next reply via DebugCommandRouter; on unrecognized input re-emit this cheatsheet.
  NEVER emit the full DebuggerMenu at a normal pause; it opens only on the `dbg` command.
```
