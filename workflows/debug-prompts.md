---
cf: true
type: workflow
name: cf-debug-prompts
description: "Invoke when user intent is debugging prompts / skills / workflows in session — e.g. step through a skill, set a breakpoint, pause before each instruction, inspect why a workflow did something, or approve cf actions one at a time. Loads a step-through debugger overlay that pauses before each subsequent skill/workflow instruction, explains what it will do and why, and gates every action on your approval until you turn debug off."
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
UNIT DebugSessionRunModeInit
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-state-session.md
  CONTINUE DebugSessionRunModeInitRun
UNIT DebugStepGate
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-step-flow.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-step-frame.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-input-handoff.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-locators.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  CONTINUE DebugStepGateRun
UNIT DebugRunModeActionRecord
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-step-flow.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-locators.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  CONTINUE DebugRunModeActionRecordRun
UNIT DebugCommandRouter
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-command-router.md; LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-command-menu-nav.md
  CONTINUE DebugCommandRouterRun
UNIT DebugStepBack
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-step-nav.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  CONTINUE DebugStepBackRun
UNIT DebugContinue
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-step-nav.md
  CONTINUE DebugContinueRun
UNIT DebugBreakpoints
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-breakpoint-router.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-breakpoint-actions.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  CONTINUE DebugBreakpointsRun
UNIT DebugWhere
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-controls.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-step-frame.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-locators.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  CONTINUE DebugWhereRun
UNIT DebugToggleGrain
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-controls.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  CONTINUE DebugToggleGrainRun
UNIT DebugStepModeEnable
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-controls.md; LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  CONTINUE DebugStepModeEnableRun
UNIT DebugDisable
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-session-controls.md
  CONTINUE DebugDisableRun
UNIT DebugStop
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-session-controls.md
  CONTINUE DebugStopRun
UNIT DebugExportTrace
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-export-trace.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-metrics.md
  CONTINUE DebugExportTraceRun
UNIT DebugStepFailure
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-failures.md
  CONTINUE DebugStepFailureRun
UNIT DebugRunFailure
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/debug-prompts-failures.md
  CONTINUE DebugRunFailureRun
```
