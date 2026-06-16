---
cf: true
type: workflow
name: cf-debug-prompts
description: "Invoke when user intent is debugging prompts / skills / workflows in session — e.g. step through a skill, set a breakpoint, pause before each instruction, inspect why a workflow did something, or approve cf actions one at a time. Loads a step-through debugger overlay that pauses before each subsequent skill/workflow instruction, explains what it will do and why, and gates every action on your approval until you turn debug off."
version: 0.1
purpose: Session-global step debugger overlay that intercepts and gates PDSL execution across all cf skills and workflows
---

# Debug Skill Workflow

This workflow installs a **session-global debugger overlay**. Once loaded it
behaves like a classic step debugger: before any subsequent skill or workflow
instruction runs, execution pauses at a breakpoint, the debugger explains
*where you are*, *what it is about to do*, *why*, and *what comes next*, then
waits for your approval. The overlay stays active across every later skill and
workflow load until you turn debug off.

The LLM controller is the interpreter, so this file is the contract that tells
the controller to stop at each step instead of running straight through.

This skill is self-contained for bootstrap, protocol, and routing: invoking it
goes straight to DebugActivate. It may load small runtime/UI modules needed for
the debugger console and export helpers.

```pdsl
UNIT DebugState
PURPOSE: Define the session-scoped state the debugger tracks.
STATE:
  - SET CF_DEBUG: on | off
    default: off
    scope: session
  - SET DEBUG_MODE: step | run
    default: step
    scope: session
  - SET DEBUG_GRAIN: instruction | unit
    default: instruction
    scope: session
  - SET DEBUG_CURSOR: integer pointer into DEBUG_TRACE
    default: 0
    scope: session
  - SET DEBUG_TRACE: ordered list of {seq, actor, loc, where, action, why, status, lines, chars, tok_est}
    default: empty
    scope: session
    NOTE: the trace holds only NON-debug (target) activity. actor is "controller"
          for gated target PDSL actions and "user" for the user's replies that the
          target skill/workflow consumes. cf-debug-skill's own actions are never traced.
          lines/chars are the LoC and character count this action loaded (0 if it loads nothing);
          tok_est is an APPROXIMATE token estimate for this action (see DebugMetrics).
  - SET DEBUG_LOC_TOTAL: cumulative lines of target content loaded so far
    default: 0
    scope: session
  - SET DEBUG_CHARS_TOTAL: cumulative characters of target content loaded so far
    default: 0
    scope: session
  - SET DEBUG_TOKENS_EST: cumulative APPROXIMATE token/context-usage estimate
    default: 0
    scope: session
  - SET DEBUG_BREAKPOINTS: list of {id, type, spec, enabled, oneshot}
    default: empty
    scope: session
  - SET DEBUG_SLUG: slug of the skill/workflow under debug (basename without extension), or "session"
    default: session
    scope: session
NOTES:
  step mode pauses before every gated action. run mode pauses only at a
  breakpoint, a WAIT/menu, an error, or an explicit user interrupt.
  instruction grain gates each PDSL action; unit grain gates each UNIT, MENU, skill load, or workflow load.
  Each breakpoint has a stable short id (b1, b2, ...) and one of four types:
    line  -> a filename.md:N (or filename.md:N-M span)
    unit  -> a UNIT or MENU name
    kind  -> one of write | edit | exec | dispatch | menu | load
    cond  -> a watch expression: VAR ==|!=|matches value
```

```pdsl
UNIT DebugActivate
PURPOSE: Arm the debugger overlay and hand the user the debugger console.
WHEN:
  - REQUIRE the user invoked cf-debug-skill (or asked to debug skills)
DO:
  - LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  - RUN WorkflowBootstrapRouterPrelude
  - RUN DebugSessionStateInit
  - RUN DebugSessionConsoleOpen
RULES:
  - ALWAYS keep CF_DEBUG = on until the user explicitly turns debug off.
  - ALWAYS remember git-commit-mode so any later commit request in this active debugger session runs GitCommitModeGate before routing, git use, or delegation.
  - ALWAYS treat a later skill/workflow load as a debugging target, not as a reason to drop the overlay.
```

```pdsl
UNIT DebugSessionStateInit
PURPOSE: Initialize debugger session state before opening the debugger console.
DO:
  - SET CF_DEBUG = on
  - SET DEBUG_MODE = step
  - SET DEBUG_GRAIN = instruction
  - SET DEBUG_CURSOR = 0
```

```pdsl
UNIT DebugSessionConsoleOpen
PURPOSE: Announce the debugger console after the debugger session state is initialized.
DO:
  - EMIT "Debugger armed. From now on every cf skill/workflow instruction stops at a breakpoint before it runs. Load the skill you want to debug, then drive it from this console."
  - EMIT "Commands: step=run the pending action · over=skip it · back=re-inspect the previous step · cont=run to the next breakpoint · dump=export trace · off=disable · stop=halt · dbg=full menu. Breakpoints: b <spec>=set · bc <ref>=clear · bl=list · be/bd <id>=enable/disable · run to <loc>."
  - RUN DebugCheatsheet
  - WAIT user.reply
  - STOP_TURN
```

```pdsl
UNIT DebugOverlayInvariants
PURPOSE: Make the breakpoint gate mandatory and global while debug is on.
WHEN:
  - REQUIRE CF_DEBUG == on
INVARIANTS:
  - ALWAYS run DebugStepGate before performing ANY prospective target action (LOAD, RUN, CONTINUE, DISPATCH, SET, EMIT_MENU, file write, shell exec, or sub-agent dispatch) in a non-debug cf skill or workflow.
  - ALWAYS apply the gate across target skill and workflow boundaries.
  - ALWAYS record every gated target action in DEBUG_TRACE with its resolved status (executed | skipped | replayed).
  - NEVER perform a gated target action while CF_DEBUG == on without first passing DebugStepGate and receiving user approval.
  - NEVER silently disarm the overlay because a target workflow defines its own menus or gates;
    those gates are themselves stepped through.
  - ALWAYS fail closed by treating unclear gate status as gated and pausing.
  - ALWAYS attach a filename.md:N locator (per DebugLocators) to every action, menu, unit, and
    instruction the debugger names, in any unit's output, while CF_DEBUG == on.
  - ALWAYS keep DEBUG_SLUG = the basename without extension of the skill/workflow file currently being stepped.
  - ALWAYS append an actor=user entry to DEBUG_TRACE only for user replies the TARGET skill/workflow
    consumes (answers to the target's own prompts or menus), recording the verbatim reply as action
    and the target prompt's filename.md:N as loc.
  - NEVER record cf-debug-skill's own activity in DEBUG_TRACE: its instructions, units, menus, frames,
    breakpoint commands, or the user's debugger-console choices (step/over/back/continue/where/grain/off/stop/bp/dump).
  - ALWAYS keep DEBUG_TRACE limited to non-debug (target) activity only.
  - NEVER gate cf-debug-skill's own debugger-console actions through DebugStepGate.
```

```pdsl
UNIT DebugStepGate
PURPOSE: The breakpoint. Stop before a pending action, explain it, and wait for the user.
WHEN:
  - REQUIRE CF_DEBUG == on
  - AND a prospective gated action is pending
  - AND DEBUG_MODE == step AND DEBUG_GRAIN == instruction
    OR DEBUG_MODE == step AND DEBUG_GRAIN == unit AND the pending action enters a UNIT, MENU, skill load, or workflow load
    OR the pending action is a WAIT/menu or an error handler
    OR DebugBreakpointMatch returns a hit for the pending action
DO:
  - CONTINUE DebugStepGatePrepare
  - CONTINUE DebugStepGateRenderFrame
  - RUN DebugCheatsheet
  - WAIT user.reply
  - STOP_TURN
RULES:
  - ALWAYS show all eight frame lines (WHERE, TARGET, NOW, WHY, NEXT, BREAKPT, METRICS, STATE) on every pause, followed by the cheatsheet.
  - ALWAYS use the token display values prepared by DebugMetrics.
  - ALWAYS attach a filename.md:N locator to every action, menu, unit, and instruction the frame names, per DebugLocators.
  - ALWAYS quote the pending action faithfully; never summarize it into something vaguer.
  - NEVER run the pending action inside this gate; running it is the explicit job of the `step` choice.
```

```pdsl
UNIT DebugStepGatePrepare
PURPOSE: Record the pending target action and resolve the frame context before a pause is shown.
DO:
  - SET DEBUG_CURSOR = DEBUG_CURSOR + 1
  - RUN append the pending action to DEBUG_TRACE with actor = controller, status = pending,
    only when the action belongs to the target skill/workflow (never for cf-debug-skill's own actions)
  - RUN resolve SOURCE_LOC and TARGET_LOC for the pending action (see DebugLocators)
  - RUN DebugMetrics to record this action's loaded lines/chars and update totals
```

```pdsl
UNIT DebugStepGateRenderFrame
PURPOSE: Emit the full debugger frame for the current pending action.
DO:
  - CONTINUE DebugStepGateRenderFrameContext
  - CONTINUE DebugStepGateRenderFrameSession
```

```pdsl
UNIT DebugStepGateRenderFrameContext
PURPOSE: Emit the debugger frame lines that describe the current action and its immediate context.
DO:
  - EMIT the debugger frame:
    - "WHERE  : <SOURCE_LOC> > <UNIT> > step <DEBUG_CURSOR>"
    - "TARGET : <TARGET_LOC, or `(no file touched)` when the action reads/writes no file>"
    - "NOW    : <the pending action, verbatim> (<SOURCE_LOC>)"
    - "WHY    : <one-line rationale: the owning PURPOSE or rule this action serves; condense a multi-sentence PURPOSE to its core reason in one line>"
```

```pdsl
UNIT DebugStepGateRenderFrameSession
PURPOSE: Emit the debugger frame lines that describe the next control point and session status.
DO:
  - EMIT the debugger frame:
    - "NEXT   : <the immediate next action(s) if this one runs; for a branch, the first action of each branch; cap the list at 3 and append `(+N more)` when longer, each suffixed with its filename.md:N>"
    - "BREAKPT: <id+type+spec of the breakpoint that fired, or `(stepping)` when paused by step mode>"
    - "METRICS: this +<this_lines> LoC +<this_chars> chars <this_token_display> | total <DEBUG_LOC_TOTAL> LoC <DEBUG_CHARS_TOTAL> chars <total_token_display>"
    - "STATE  : debug=on mode=<DEBUG_MODE> grain=<DEBUG_GRAIN> cursor=<DEBUG_CURSOR> bps=<count of enabled breakpoints>"
```

```pdsl
UNIT DebugLocators
PURPOSE: Attach a filename.md:N locator to every action, menu, unit, and instruction the debugger names.
DO:
  - SET LOCATOR(x) = "<filename>.md:<N>" where <filename>.md is the file that defines x
    and <N> is its real 1-based line number (the start line; use "<N>-<M>" for an explicit span)
  - SET SOURCE_LOC = LOCATOR(the PDSL instruction currently at the breakpoint)
  - SET TARGET_LOC = LOCATOR(the file and line the pending action reads, writes, edits, or runs against)
    WHEN the action touches a concrete path; otherwise SET TARGET_LOC = "(no file touched)"
  - RUN append filename.md:N for each emitted MENU and each option's target unit/menu
  - RUN prepend a relative path to basename locators WHEN two referenced files share a basename
  - RUN set TARGET_LOC to the precise affected line for file read, write, edit, and shell command targets
  - RUN use the matched pre-change line and note it is about to change WHEN an edit's post-change line is not yet known
RULES:
  - ALWAYS suffix every emitted action, menu reference, unit reference, and instruction
    reference with its locator in the form filename.md:N.
  - ALWAYS include locators for every emitted MENU and each option's target unit/menu.
  - ALWAYS resolve real 1-based line numbers from the live file before emitting; NEVER guess or use a placeholder line.
  - ALWAYS use the basename filename.md:N as the default locator form.
  - ALWAYS point TARGET_LOC at the most precise known affected line.
  - ALWAYS identify pending edit locators from stable pre-change evidence.
  - NEVER omit the locator on any action, menu, unit, or instruction the debugger names.
```

```pdsl
UNIT DebugMetrics
PURPOSE: Count loaded LoC and characters per action and keep an approximate token estimate.
DO:
  - CONTINUE DebugMetricsMeasureAction
  - CONTINUE DebugMetricsAccumulateTotals
  - CONTINUE DebugMetricsPrepareDisplay
RULES:
  - ALWAYS count real lines/characters from the content the action actually loads; these are exact.
  - ALWAYS label token displays as measured or estimated.
  - ALWAYS prefer measured token and usage figures over estimated displays.
  - NEVER present an estimated token display as exact or authoritative.
NOTES:
  lines/chars cover content loaded into context (file reads, LOADs, dispatched
  context). The token figure is approximate (~chars/4) unless a real usage
  number is available from the host.
```

```pdsl
UNIT DebugMetricsMeasureAction
PURPOSE: Measure the pending action's loaded context and store per-action counts.
DO:
  - SET this_lines = the number of lines the pending action loads into context (0 when it loads no file/content)
  - SET this_chars = the number of characters the pending action loads into context (0 when none)
  - SET this_tok_est = round(this_chars / 4)  // coarse heuristic, English/code
  - RUN store {lines: this_lines, chars: this_chars, tok_est: this_tok_est} on the action's DEBUG_TRACE entry
```

```pdsl
UNIT DebugMetricsAccumulateTotals
PURPOSE: Roll the current action's counts into the debugger session totals.
DO:
  - SET DEBUG_LOC_TOTAL = DEBUG_LOC_TOTAL + this_lines
  - SET DEBUG_CHARS_TOTAL = DEBUG_CHARS_TOTAL + this_chars
  - SET DEBUG_TOKENS_EST = DEBUG_TOKENS_EST + this_tok_est
```

```pdsl
UNIT DebugMetricsPrepareDisplay
PURPOSE: Prepare measured or estimated token-display strings for the frame.
DO:
  - SET this_token_display = "~<this_tok_est> tok est"
  - SET total_token_display = "~<DEBUG_TOKENS_EST> tok est"
  - SET this_token_display and total_token_display from the host-exposed real token or usage figure, marked as measured, WHEN the host exposes a real token or usage figure
```

```pdsl
UNIT DebugCheatsheet
PURPOSE: Show a compact command hint at every debugger pause instead of the full menu.
DO:
  - EMIT "dbg> step over back cont · dump · off stop · dbg=full menu"
  - EMIT "    bp: b <spec> · bc <ref> · bl · be/bd <id> · run to <loc> · grain"
RULES:
  - ALWAYS keep the cheatsheet to at most three lines.
  - ALWAYS interpret the next reply via DebugCommandRouter; on unrecognized input re-emit this cheatsheet.
  - NEVER emit the full DebuggerMenu at a normal pause; it opens only on the `dbg` command.
```

```pdsl
UNIT DebugCommandRouter
PURPOSE: Map a typed debugger command (from the cheatsheet) to its handler at any pause.
DO:
  - CONTINUE DebugCommandStep WHEN user.reply == step OR user.reply == s
  - CONTINUE DebugCommandOver WHEN user.reply == over OR user.reply == o
  - CONTINUE DebugCommandRouteNavigation WHEN user.reply == back OR user.reply == cont OR user.reply == c OR user.reply == continue OR user.reply == where OR user.reply == w OR user.reply == grain OR user.reply == g
  - CONTINUE DebugCommandRouteSession WHEN user.reply == off OR user.reply == stop OR user.reply == dump
  - CONTINUE DebugBreakpoints WHEN user.reply starts with b OR user.reply starts with bc OR user.reply == bl OR user.reply starts with be OR user.reply starts with bd OR user.reply starts with run to
  - CONTINUE DebugCommandOpenMenu WHEN user.reply == dbg OR user.reply == menu OR user.reply == ?
  - CONTINUE DebugCommandRouterFallback
RULES:
  - ALWAYS accept the numeric choices from DebuggerMenu as equivalents (1 step ... 10 dump).
  - ALWAYS treat unrecognized input as a no-op that just re-shows the cheatsheet.
```

```pdsl
UNIT DebugCommandStep
PURPOSE: Execute the pending action from the debugger console.
DO:
  - RUN execute the pending action now, mark its DEBUG_TRACE entry executed, then RUN DebugStepGate on the next action
```

```pdsl
UNIT DebugCommandOver
PURPOSE: Skip the pending action from the debugger console.
DO:
  - RUN skip the pending action without executing it, mark its DEBUG_TRACE entry skipped, then RUN DebugStepGate on the next action
```

```pdsl
UNIT DebugCommandRouteNavigation
PURPOSE: Route debugger navigation commands that stay within the active session.
DO:
  - CONTINUE DebugStepBack WHEN user.reply == back
  - CONTINUE DebugContinue WHEN user.reply == cont OR user.reply == c OR user.reply == continue
  - CONTINUE DebugWhere WHEN user.reply == where OR user.reply == w
  - CONTINUE DebugToggleGrain WHEN user.reply == grain OR user.reply == g
```

```pdsl
UNIT DebugCommandRouteSession
PURPOSE: Route debugger commands that change or export the current session.
DO:
  - CONTINUE DebugDisable WHEN user.reply == off
  - CONTINUE DebugStop WHEN user.reply == stop
  - CONTINUE DebugExportTrace WHEN user.reply == dump
```

```pdsl
UNIT DebugCommandRouterFallback
PURPOSE: Re-show the cheatsheet when the debugger command is not recognized.
DO:
  - RUN DebugCheatsheet
  - WAIT user.reply
  - STOP_TURN
```

```pdsl
UNIT DebugCommandOpenMenu
PURPOSE: Open the full debugger menu on demand from the compact console.
DO:
  - EMIT_MENU DebuggerMenu
  - WAIT user.reply
  - STOP_TURN
```

```pdsl
MENU DebuggerMenu:
  TITLE: "Debugger — full menu (open with `dbg`)"
  OPTIONS:
    1 step -> RUN execute the pending action now, mark its DEBUG_TRACE entry executed, then RUN DebugStepGate on the next action
    2 over -> RUN skip the pending action without executing it, mark its DEBUG_TRACE entry skipped, then RUN DebugStepGate on the next action
    3 back -> CONTINUE DebugStepBack
    4 continue -> CONTINUE DebugContinue
    5 where -> CONTINUE DebugWhere
    6 grain -> CONTINUE DebugToggleGrain
    7 off -> CONTINUE DebugDisable
    8 stop -> CONTINUE DebugStop
    9 bp -> CONTINUE DebugBreakpoints
    10 dump -> CONTINUE DebugExportTrace
  INVALID:
    EMIT "Reply with 1 (step), 2 (over), 3 (back), 4 (continue), 5 (where), 6 (grain), 7 (off), 8 (stop), 9 (bp), or 10 (dump). Breakpoint commands also work directly: b <spec>, bc <ref>, bl, be <id>, bd <id>, run to <loc>."
    WAIT user.reply
    STOP_TURN
```

```pdsl
UNIT DebugStepBack
PURPOSE: Move the cursor to a previous step and re-inspect it.
DO:
  - CONTINUE DebugStepBackReinspect WHEN DEBUG_CURSOR > 1
  - CONTINUE DebugStepBackAtStart WHEN DEBUG_CURSOR <= 1
RULES:
  - ALWAYS warn that step back only repositions the cursor for inspection and re-narration.
  - NEVER claim that already-applied side effects (file writes, shell exec, sub-agent dispatch) were undone.
  - ALWAYS require an explicit fresh `step` confirmation before re-executing an action reached by stepping back.
```

```pdsl
UNIT DebugStepBackReinspect
PURPOSE: Move the cursor back one step and re-show that earlier frame.
DO:
  - SET DEBUG_CURSOR = DEBUG_CURSOR - 1
  - EMIT "Stepped back. Re-showing the previous frame for inspection."
  - RUN re-emit the debugger frame for the DEBUG_TRACE entry at DEBUG_CURSOR
  - RUN DebugCheatsheet
  - WAIT user.reply
  - STOP_TURN
```

```pdsl
UNIT DebugStepBackAtStart
PURPOSE: Report that the debugger cannot step back before the first recorded action.
DO:
  - EMIT "Already at the first step; cannot step back further."
  - RUN DebugCheatsheet
  - WAIT user.reply
  - STOP_TURN
```

```pdsl
UNIT DebugContinue
PURPOSE: Run without pausing at every action until the next breakpoint or natural stop.
DO:
  - SET DEBUG_MODE = run
  - EMIT "Continuing. The debugger runs subsequent actions without pausing until the next breakpoint hit, a WAIT/menu, an error, or you interrupt."
  - RUN before each action in run mode: RUN DebugBreakpointMatch and pause via DebugStepGate on a hit
  - RUN resume executing the target workflow under DebugOverlayInvariants in run mode
  - RUN pause via DebugStepGate WHEN reaching a WAIT/menu or an error
RULES:
  - ALWAYS keep CF_DEBUG = on while in run mode; continue does not disarm the debugger.
  - ALWAYS evaluate breakpoints before run-mode actions.
  - ALWAYS route WAIT/menu/error pauses through DebugStepGate.
  - ALWAYS honor user requests to return to step mode.
```

```pdsl
UNIT DebugBreakpointMatch
PURPOSE: Decide whether the pending action hits an enabled breakpoint.
DO:
  - SET BP_HIT = the first enabled breakpoint in DEBUG_BREAKPOINTS that matches the pending action; else none
  - RUN skip disabled breakpoints during matching
  - RUN pause via DebugStepGate with the breakpoint id in the BREAKPT frame line WHEN BP_HIT != none AND DEBUG_MODE == run
  - RETURN BP_HIT
RULES:
  - ALWAYS evaluate only enabled breakpoints for hits.
  - ALWAYS route run-mode breakpoint hits through DebugStepGate.
  - ALWAYS remove a oneshot breakpoint from DEBUG_BREAKPOINTS immediately after it fires once.
  - NEVER let breakpoint matching execute, skip, or mutate the pending action; it only decides whether to pause.
NOTES:
  Match semantics by type:
    line -> the pending instruction's SOURCE_LOC equals filename.md:N, or N falls inside the breakpoint's N-M span (same file basename).
    unit -> the pending action enters a UNIT or MENU whose name equals spec.
    kind -> the pending action's kind is the spec, where kind in {write, edit, exec, dispatch, menu, load}.
    cond -> the named state variable satisfies spec: VAR == value, VAR != value, or VAR matches pattern.
```

```pdsl
UNIT DebugBreakpoints
PURPOSE: Set, clear, list, enable, disable, and run-to breakpoints via short commands or plain language.
STATE:
  - SET DEBUG_BREAKPOINT_ACTION: set | clear | list | enable | disable | run-to | invalid
    default: invalid
    scope: workflow_run
DO:
  - RUN DebugBreakpointActionParse
  - CONTINUE DebugBreakpointActionDispatch
RULES:
  - ALWAYS accept both short commands and plain-language equivalents for every action.
  - ALWAYS assign a stable short id (b1, b2, ...) and reuse it for later enable/disable/clear.
  - ALWAYS echo each breakpoint change with the affected breakpoint id and locator context.
  - NEVER drop or renumber existing breakpoints during add or toggle operations.
NOTES:
  Short commands (also expressible in plain language):
    b <spec>      set     (line: b debug-skill.md:108 | unit: b DebuggerMenu | kind: b kind:write | cond: b cond:DEBUG_GRAIN==unit)
    bc <ref>      clear   (by id `bc b2`, by locator, or `bc all`)
    bl            list
    be <id>       enable
    bd <id>       disable
    run to <loc>  run until filename.md:N, then auto-remove (one-shot)
```

```pdsl
UNIT DebugBreakpointActionDispatch
PURPOSE: Route the parsed breakpoint action to the matching breakpoint handler.
DO:
  - CONTINUE DebugBreakpointActionDispatchPrimary WHEN DEBUG_BREAKPOINT_ACTION == set OR DEBUG_BREAKPOINT_ACTION == clear OR DEBUG_BREAKPOINT_ACTION == list
  - CONTINUE DebugBreakpointActionDispatchSecondary WHEN DEBUG_BREAKPOINT_ACTION == enable OR DEBUG_BREAKPOINT_ACTION == disable OR DEBUG_BREAKPOINT_ACTION == run-to
  - RUN DebugCheatsheet
  - WAIT user.reply
  - STOP_TURN
```

```pdsl
UNIT DebugBreakpointActionDispatchPrimary
PURPOSE: Route breakpoint creation, removal, and listing commands.
DO:
  - CONTINUE DebugBreakpointSet WHEN DEBUG_BREAKPOINT_ACTION == set
  - CONTINUE DebugBreakpointClear WHEN DEBUG_BREAKPOINT_ACTION == clear
  - CONTINUE DebugBreakpointList WHEN DEBUG_BREAKPOINT_ACTION == list
```

```pdsl
UNIT DebugBreakpointActionDispatchSecondary
PURPOSE: Route breakpoint enable, disable, and run-to commands.
DO:
  - CONTINUE DebugBreakpointEnable WHEN DEBUG_BREAKPOINT_ACTION == enable
  - CONTINUE DebugBreakpointDisable WHEN DEBUG_BREAKPOINT_ACTION == disable
  - CONTINUE DebugBreakpointRunTo WHEN DEBUG_BREAKPOINT_ACTION == run-to
```

```pdsl
UNIT DebugBreakpointActionParse
PURPOSE: Parse the user's breakpoint command into one canonical breakpoint action.
DO:
  - RUN parse the user's request into one action: set | clear | list | enable | disable | run-to
```

```pdsl
UNIT DebugBreakpointSet
PURPOSE: Append a normal breakpoint from a locator, unit, kind, or condition specification.
DO:
  - RUN derive type+spec from the input (line: filename.md:N | unit: a UNIT/MENU name | kind: write|edit|exec|dispatch|menu|load | cond: VAR ==|!=|matches value)
  - RUN append {id: next b<n>, type, spec, enabled: true, oneshot: false} to DEBUG_BREAKPOINTS
  - EMIT "set <id> <type> <spec>" with its filename.md:N when the type is line or unit
  - RUN DebugCheatsheet
  - WAIT user.reply
  - STOP_TURN
```

```pdsl
UNIT DebugBreakpointClear
PURPOSE: Remove one breakpoint by id/locator or clear them all.
DO:
  - RUN remove the breakpoint matching the given id or locator; remove all WHEN spec == all
  - EMIT "cleared <id-or-spec>"
  - RUN DebugCheatsheet
  - WAIT user.reply
  - STOP_TURN
```

```pdsl
UNIT DebugBreakpointList
PURPOSE: Render the current breakpoint table.
DO:
  - EMIT each breakpoint as "<id> <type> <spec> <enabled|disabled>" with its filename.md:N where applicable, or "(no breakpoints)"
  - RUN DebugCheatsheet
  - WAIT user.reply
  - STOP_TURN
```

```pdsl
UNIT DebugBreakpointEnable
PURPOSE: Re-enable a disabled breakpoint.
DO:
  - RUN set enabled = true on the breakpoint by id
  - EMIT "enabled <id>"
  - RUN DebugCheatsheet
  - WAIT user.reply
  - STOP_TURN
```

```pdsl
UNIT DebugBreakpointDisable
PURPOSE: Disable an existing breakpoint without removing it.
DO:
  - RUN set enabled = false on the breakpoint by id
  - EMIT "disabled <id>"
  - RUN DebugCheatsheet
  - WAIT user.reply
  - STOP_TURN
```

```pdsl
UNIT DebugBreakpointRunTo
PURPOSE: Add a one-shot line breakpoint and resume execution until it fires.
DO:
  - RUN append {id: next b<n>, type: line, spec: <filename.md:N>, enabled: true, oneshot: true} to DEBUG_BREAKPOINTS
  - SET DEBUG_MODE = run
  - EMIT "running to <filename.md:N> (one-shot)"
  - RUN resume executing the target workflow under DebugOverlayInvariants in run mode
  - RUN DebugCheatsheet
  - WAIT user.reply
  - STOP_TURN
```

```pdsl
UNIT DebugWhere
PURPOSE: Re-print the current debugger frame and a short trace summary.
DO:
  - RUN resolve SOURCE_LOC and TARGET_LOC for the current step (see DebugLocators)
  - RUN re-emit the debugger frame for the current DEBUG_CURSOR with filename.md:N locators
  - EMIT "TRACE: <compact list of recent DEBUG_TRACE entries; each entry suffixed with its filename.md:N locator>"
  - RUN DebugCheatsheet
  - WAIT user.reply
  - STOP_TURN
```

```pdsl
UNIT DebugToggleGrain
PURPOSE: Switch between instruction-level and unit-level stepping.
DO:
  - CONTINUE DebugToggleGrainToUnit WHEN DEBUG_GRAIN == instruction
  - CONTINUE DebugToggleGrainToInstruction WHEN DEBUG_GRAIN != instruction
```

```pdsl
UNIT DebugToggleGrainToUnit
PURPOSE: Switch the debugger from instruction stepping to unit stepping.
DO:
  - SET DEBUG_GRAIN = unit
  - EMIT "Grain set to unit: the debugger now pauses before each UNIT, MENU, skill load, or workflow load, not every instruction."
  - CONTINUE DebugToggleGrainPause
```

```pdsl
UNIT DebugToggleGrainToInstruction
PURPOSE: Switch the debugger from unit stepping to instruction stepping.
DO:
  - SET DEBUG_GRAIN = instruction
  - EMIT "Grain set to instruction: the debugger now pauses before every PDSL action."
  - CONTINUE DebugToggleGrainPause
```

```pdsl
UNIT DebugToggleGrainPause
PURPOSE: Re-open the debugger prompt after a grain change.
DO:
  - RUN DebugCheatsheet
  - WAIT user.reply
  - STOP_TURN
```

```pdsl
UNIT DebugDisable
PURPOSE: Turn the debugger off and hand control back to normal cf execution.
DO:
  - SET CF_DEBUG = off
  - SET DEBUG_MODE = step
  - EMIT "Debugger off. Skills and workflows now run normally with no per-step breakpoints. Re-invoke cf-debug-skill to arm it again."
  - RUN resume the target workflow normally, or end the turn if there is no active target
RULES:
  - ALWAYS leave DEBUG_TRACE intact after disabling so the session history stays inspectable.
  - NEVER keep gating actions once CF_DEBUG == off.
```

```pdsl
UNIT DebugStop
PURPOSE: Halt immediately, staying paused at the current breakpoint.
DO:
  - EMIT "Halted at the current breakpoint. Debug stays on. Send any message to reopen the debugger console."
  - STOP_TURN
RULES:
  - ALWAYS keep CF_DEBUG = on and the cursor where it is so the session can resume from the same breakpoint.
```

```pdsl
UNIT DebugExportTrace
PURPOSE: Write the current debug trace to a timestamped Markdown file.
DO:
  - CONTINUE DebugExportTracePrepare
  - CONTINUE DebugExportTraceWrite
  - CONTINUE DebugExportTraceAnnounce
  - RUN DebugCheatsheet
  - WAIT user.reply
  - STOP_TURN
RULES:
  - ALWAYS load template-vars before resolving the debug trace dump path or unknown template variables.
  - ALWAYS resolve <YYYY-MM-DD> and <HHMMSS> from the current local date and time at dump time.
  - ALWAYS slugify DEBUG_SLUG to lowercase kebab-case before building the filename.
  - ALWAYS write a fresh file per dump; NEVER overwrite an earlier dump (the timestamp keeps each unique).
  - NEVER disarm the debugger or clear DEBUG_TRACE on dump; exporting is read-only over the session state.
ON_ERROR:
  write_failed ->
    EMIT "Could not write the trace dump to <DUMP_PATH>. Check that {cf-studio-path} is writable."
    RUN DebugCheatsheet
    WAIT user.reply
    STOP_TURN
```

```pdsl
UNIT DebugExportTracePrepare
PURPOSE: Resolve the output path for the current debug trace export.
DO:
  - LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/template-vars.md
  - RUN TemplateVarResolution before resolving DUMP_PATH
  - SET DUMP_PATH = "{cf-studio-path}/.debug-skill/<DEBUG_SLUG>-<YYYY-MM-DD>-<HHMMSS>.md"
```

```pdsl
UNIT DebugExportTraceWrite
PURPOSE: Materialize the trace export file on disk.
DO:
  - RUN ensure the directory {cf-studio-path}/.debug-skill/ exists, creating it if missing
  - RUN render the trace report (see DebugTraceReport) into DUMP_PATH
```

```pdsl
UNIT DebugExportTraceAnnounce
PURPOSE: Announce the completed trace export and surface the written file reference.
DO:
  - EMIT "Trace written to <DUMP_PATH> (<count> steps)."
  - EMIT the written file as a clickable reference: <ref_file file="<absolute DUMP_PATH>" />
```

```pdsl
UNIT DebugTraceReport
PURPOSE: Define the Markdown shape of an exported debug trace.
NOTES:
  The report contains, in order:
    1. Title: "# Debug trace — <DEBUG_SLUG>"
    2. Metadata block: dumped-at timestamp, DEBUG_SLUG, CF_DEBUG, DEBUG_MODE, DEBUG_GRAIN, DEBUG_CURSOR, enabled-breakpoint count
    3. Totals block: DEBUG_LOC_TOTAL, DEBUG_CHARS_TOTAL, and DEBUG_TOKENS_EST (clearly marked as an estimate)
    4. Breakpoints section: a table of DEBUG_BREAKPOINTS (id, type, spec, enabled, oneshot)
    5. Trace section: a table of DEBUG_TRACE rows (seq, actor, loc, where, action, why, status, lines, chars, tok_est),
       with actor as controller|user and loc/where as filename.md:N; user replies appear inline in sequence
    6. A trailing note that loc/where values are filename.md:N locators and that tok_est/DEBUG_TOKENS_EST are approximate
RULES:
  - ALWAYS keep every loc and where value in filename.md:N form so the report is navigable.
  - ALWAYS quote each action faithfully, matching what the breakpoint frame showed.
  - ALWAYS render empty breakpoints sections as "(no breakpoints)" and empty trace sections as "(empty trace)".
```

```pdsl
UNIT DebugStepFailure
PURPOSE: Recover when the action currently being stepped fails to execute.
ON_ERROR:
  step_failed ->
    EMIT "The stepped action failed to execute. Reporting the error verbatim and staying paused at this breakpoint."
    EMIT "ERROR: <the raw error from the failed action>"
    EMIT_MENU DebugStepFailureMenu
    WAIT user.reply
    STOP_TURN

MENU DebugStepFailureMenu:
  TITLE: "Stepped action failed."
  OPTIONS:
    1 retry -> RUN re-attempt the failed action, mark its DEBUG_TRACE entry replayed, then RUN DebugStepGate on the next action
    2 over -> RUN skip the failed action, mark its DEBUG_TRACE entry skipped, then RUN DebugStepGate on the next action
    3 off -> CONTINUE DebugDisable
    4 stop -> CONTINUE DebugStop
  INVALID:
    EMIT "Reply `1`, `2`, `3`, or `4`."
    WAIT user.reply
    STOP_TURN
```
