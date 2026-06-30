---
cf: true
type: workflow
name: cf-debug-prompts
description: "Invoke when the user or another skill or workflow needs or asks to debug prompts, skills, or workflows in session — for example to step through a skill, set a breakpoint, pause before each instruction, inspect why a workflow did something, or approve cf actions one at a time."
version: 0.1
purpose: Session-global step debugger overlay that intercepts and gates PDSL execution across all cf skills and workflows
---
```pdsl
UNIT DebugActivate
PURPOSE: Arm the debugger overlay and hand the user the debugger console.
WHEN:
  REQUIRE the user invoked cf-debug-prompts (or asked to debug skills)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-state-session.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-activate-console.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  RUN WorkflowBootstrapRouterPrelude
  RUN DebugSessionStateInit
  RUN DebugSessionConsoleOpen
RULES:
  ALWAYS keep CF_DEBUG = on until the user explicitly turns debug off
  ALWAYS remember git-commit-mode so any later commit request in this active debugger session runs GitCommitModeGate before routing, git use, or delegation
  ALWAYS treat a later skill/workflow load as a debugging target, not as a reason to drop the overlay.
```

```pdsl
UNIT DebugSessionRunModeInit
PURPOSE: Load session-state module and route to DebugSessionRunModeInitRun.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-state-session.md
  CONTINUE DebugSessionRunModeInitRun
```

```pdsl
UNIT DebugStepGate
PURPOSE: Load step-flow, step-frame, input-handoff, locators, and metrics modules and route to DebugStepGateRun.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-step-flow.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-step-frame.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-input-handoff.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-locators.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  CONTINUE DebugStepGateRun
```

```pdsl
UNIT DebugRunModeActionRecord
PURPOSE: Load step-flow, locators, and metrics modules and route to DebugRunModeActionRecordRun.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-step-flow.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-locators.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  CONTINUE DebugRunModeActionRecordRun
```

```pdsl
UNIT DebugCommandRouter
PURPOSE: Load command-router and command-menu-nav modules and route to DebugCommandRouterRun.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-command-router.md; LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-command-menu-nav.md
  CONTINUE DebugCommandRouterRun
```

```pdsl
UNIT DebugStepBack
PURPOSE: Load step-nav and metrics modules and route to DebugStepBackRun.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-step-nav.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  CONTINUE DebugStepBackRun
```

```pdsl
UNIT DebugContinue
PURPOSE: Load step-nav module and route to DebugContinueRun.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-step-nav.md
  CONTINUE DebugContinueRun
```

```pdsl
UNIT DebugBreakpoints
PURPOSE: Load breakpoint-router, breakpoint-actions, and metrics modules and route to DebugBreakpointsRun.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-breakpoint-router.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-breakpoint-actions.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  CONTINUE DebugBreakpointsRun
```

```pdsl
UNIT DebugWhere
PURPOSE: Load controls, step-frame, locators, and metrics modules and route to DebugWhereRun.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-controls.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-step-frame.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-locators.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  CONTINUE DebugWhereRun
```

```pdsl
UNIT DebugToggleGrain
PURPOSE: Load controls and metrics modules and route to DebugToggleGrainRun.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-controls.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  CONTINUE DebugToggleGrainRun
```

```pdsl
UNIT DebugStepModeEnable
PURPOSE: Load controls and metrics modules and route to DebugStepModeEnableRun.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-controls.md; LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  CONTINUE DebugStepModeEnableRun
```

```pdsl
UNIT DebugDisable
PURPOSE: Load session-controls module and route to DebugDisableRun.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-session-controls.md
  CONTINUE DebugDisableRun
```

```pdsl
UNIT DebugStop
PURPOSE: Load session-controls module and route to DebugStopRun.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-session-controls.md
  CONTINUE DebugStopRun
```

```pdsl
UNIT DebugExportTrace
PURPOSE: Load export-trace and metrics modules and route to DebugExportTraceRun.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-export-trace.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  CONTINUE DebugExportTraceRun
```

```pdsl
UNIT DebugStepFailure
PURPOSE: Load failures module and route to DebugStepFailureRun.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-failures.md
  CONTINUE DebugStepFailureRun
```

```pdsl
UNIT DebugRunFailure
PURPOSE: Load failures module and route to DebugRunFailureRun.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-failures.md
  CONTINUE DebugRunFailureRun
```
