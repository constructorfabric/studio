# Debug Prompts Export Trace

```pdsl
UNIT DebugExportTraceRun
PURPOSE: Write the current debug trace to a timestamped Markdown file.
DO:
  CONTINUE DebugExportTracePrepare
  CONTINUE DebugExportTraceWrite
  CONTINUE DebugExportTraceAnnounce
  RUN DebugCheatsheet
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS load template-vars before resolving the debug trace dump path or unknown template variables.
  ALWAYS resolve <YYYY-MM-DD> and <HHMMSS> from the current local date and time at dump time.
  ALWAYS slugify DEBUG_SLUG to lowercase kebab-case before building the filename.
  ALWAYS write a fresh file per dump; NEVER overwrite an earlier dump.
  NEVER disarm the debugger or clear DEBUG_TRACE on dump; exporting is read-only over the session state.
ON_ERROR:
  write_failed -> EMIT "Could not write the trace dump to <DUMP_PATH>. Check that {cf-studio-path} is writable."; RUN DebugCheatsheet; WAIT user.reply; STOP_TURN
```

```pdsl
UNIT DebugExportTracePrepare
PURPOSE: Resolve the output path for the current debug trace export.
STATE:
  SET DUMP_PATH: path | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/template-vars.md
  RUN TemplateVarResolution before resolving DUMP_PATH; this resolver is the mechanism that substitutes <YYYY-MM-DD> and <HHMMSS> from the current local timestamp and slugifies DEBUG_SLUG to lowercase kebab-case
  SET DUMP_PATH = "{cf-studio-path}/.debug-skill/<DEBUG_SLUG>-<YYYY-MM-DD>-<HHMMSS>.md"
```

```pdsl
UNIT DebugExportTraceWrite
PURPOSE: Materialize the trace export file on disk.
DO:
  RUN ensure the directory {cf-studio-path}/.debug-skill/ exists, creating it if missing
  RUN render the trace report (see DebugTraceReport) into DUMP_PATH
```

```pdsl
UNIT DebugExportTraceAnnounce
PURPOSE: Announce the completed trace export and surface the written file reference.
DO:
  EMIT "Trace written to <DUMP_PATH> (<count> steps)."
  EMIT the written file as a clickable reference: <ref_file file="<absolute DUMP_PATH>" />
```

```pdsl
UNIT DebugTraceReport
PURPOSE: Define the Markdown shape of an exported debug trace.
NOTES:
  The report contains, in order: 1. title `# Debug trace — <DEBUG_SLUG>`; 2. metadata block with dumped-at timestamp, DEBUG_SLUG, CF_DEBUG, DEBUG_MODE, DEBUG_GRAIN, DEBUG_CURSOR, and enabled-breakpoint count; 3. totals block with DEBUG_LOC_TOTAL, DEBUG_CHARS_TOTAL, and DEBUG_TOKENS_EST clearly marked as an estimate; 4. breakpoints section with DEBUG_BREAKPOINTS; 5. trace section with DEBUG_TRACE rows; 6. a trailing note that loc/where values are filename.md:N locators and tok_est figures are approximate.
RULES:
  ALWAYS keep every loc and where value in filename.md:N form so the report is navigable.
  ALWAYS quote each action faithfully, matching what the breakpoint frame showed.
  ALWAYS render empty breakpoints sections as "(no breakpoints)" and empty trace sections as "(empty trace)".
```
