# Debug Prompts Locators

```pdsl
UNIT DebugLocators
PURPOSE: Attach a filename.md:N locator to every action, menu, unit, and instruction the debugger names.
STATE:
  SET SOURCE_LOC: locator | unset (default unset, scope workflow_run)
  SET TARGET_LOC: locator | "(no file touched)" | unset (default unset, scope workflow_run)
DO:
  SET LOCATOR(x) = "<filename>.md:<N>" where <filename>.md is the file that defines x and <N> is its real 1-based line number (the start line; use "<N>-<M>" for an explicit span)
  SET SOURCE_LOC = LOCATOR(the PDSL instruction currently at the breakpoint)
  SET TARGET_LOC = LOCATOR(the file and line the pending action reads, writes, edits, or runs against) WHEN the action touches a concrete path; otherwise SET TARGET_LOC = "(no file touched)"
  RUN append filename.md:N for each emitted MENU and each option's target unit/menu
  RUN prepend a relative path to basename locators WHEN two referenced files share a basename
  RUN set TARGET_LOC to the precise affected line for file read, write, edit, and shell command targets
  RUN use the matched pre-change line and note it is about to change WHEN an edit's post-change line is not yet known
RULES:
  ALWAYS suffix every emitted action, menu reference, unit reference, and instruction reference with its locator in the form filename.md:N.
  ALWAYS include locators for every emitted MENU and each option's target unit/menu.
  ALWAYS resolve real 1-based line numbers from the live file before emitting; NEVER guess or invent a line number — use the '(line unknown)' fallback only when real resolution fails.
  ALWAYS emit a fallback locator of '(line unknown)' with a warning when real line resolution fails, and surface that warning to the user in the step frame.
  ALWAYS use the basename filename.md:N as the default locator form.
  ALWAYS point TARGET_LOC at the most precise known affected line.
  ALWAYS identify pending edit locators from stable pre-change evidence.
  NEVER omit the locator on any action, menu, unit, or instruction the debugger names.
```
