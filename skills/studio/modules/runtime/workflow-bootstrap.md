# Workflow Bootstrap Helpers

```pdsl
UNIT WorkflowBootstrapRouterPrelude
PURPOSE: Load the shared invocation art and git-session memory used by router-style and overlay entrypoints.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/skill-invocation-art.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/pdsl-execution-card.md
  RUN SkillInvocationArt
  LOAD and REMEMBER rules from {cf-studio-path}/.core/skills/studio/modules/runtime/active-workflow-state-law.md
  LOAD and REMEMBER rules from {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
RULES:
  ALWAYS remember active-workflow-state-law before a later user follow-up may resume, interrupt, reroute, or exit an active workflow
  ALWAYS remember git-commit-mode before a later commit request may be routed, delegated, or executed
```

```pdsl
UNIT WorkflowBootstrapCoreSession
PURPOSE: Extend the shared router prelude with remembered Studio instruction files for full workflows.
DO:
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapStudioInstructionsMemory
RULES:
  ALWAYS run StudioInstructionsMemoryGate before workflow-specific routing, discovery, planning, validation, authoring, review, or writes
```

```pdsl
UNIT WorkflowBootstrapSimpleModeGate
PURPOSE: Load and run the once-per-session simple-mode choice for non-exempt workflows.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode.md
  RUN SimpleModeGate
RULES:
  ALWAYS run after WorkflowBootstrapRouterPrelude and before workflow-specific routing, discovery, planning, validation, authoring, review, or writes in non-exempt workflows
  NEVER run for `cf-debug-prompts` or `cf-help`
```

```pdsl
UNIT WorkflowBootstrapStudioInstructionsMemory
PURPOSE: Load and run remembered Studio instruction files after workflow entry gates resolve.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/studio-instructions-memory.md
  RUN StudioInstructionsMemoryGate
RULES:
  ALWAYS run StudioInstructionsMemoryGate before workflow-specific routing, discovery, planning, validation, authoring, review, or writes
```

```pdsl
UNIT WorkflowBootstrapCommandResolution
PURPOSE: Resolve the shared `{cfs_cmd}` handle before any workflow CLI use.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/command-resolution.md
  RUN CommandResolution to resolve {cfs_cmd}
RULES:
  ALWAYS load command-resolution before invoking `{cfs_cmd}` or passing remembered CLI capabilities downstream
```

```pdsl
UNIT WorkflowBootstrapCommandWorkflowResolution
PURPOSE: Resolve `{cfs_cmd}` plus the available workflow registry for router-style workflows.
DO:
  RUN WorkflowBootstrapCommandResolution
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md
RULES:
  ALWAYS load workflow-resolution after command-resolution so downstream routing can resolve cf-* skills deterministically
```

```pdsl
UNIT WorkflowBootstrapCommandContext
PURPOSE: Resolve `{cfs_cmd}` and load context-memory for workflows that carry read-only resource context.
DO:
  RUN WorkflowBootstrapCommandResolution
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md
RULES:
  ALWAYS load context-memory before storing or forwarding workflow resource_context
```

```pdsl
UNIT WorkflowBootstrapContextOnly
PURPOSE: Load context-memory for workflows that do not need `{cfs_cmd}` during bootstrap.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md
RULES:
  ALWAYS load context-memory before storing or forwarding workflow resource_context
```

```pdsl
UNIT WorkflowBootstrapCommandTemplateContext
PURPOSE: Resolve `{cfs_cmd}` and load template/context helpers for path-aware workflows.
DO:
  RUN WorkflowBootstrapCommandResolution
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/template-vars.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md
RULES:
  ALWAYS load template-vars before resolving workflow paths or unknown template variables
  ALWAYS load context-memory before storing or forwarding workflow resource_context
```

```pdsl
UNIT WorkflowBootstrapDispatchTemplateContext
PURPOSE: Load sub-agent dispatch plus template/context helpers for non-CLI workflows.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/template-vars.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md
RULES:
  ALWAYS load sub-agent dispatch before a workflow may launch native or inline sub-agents
  ALWAYS load template-vars before resolving workflow paths or unknown template variables
  ALWAYS load context-memory before storing or forwarding workflow resource_context
```

```pdsl
UNIT WorkflowBootstrapDispatchContext
PURPOSE: Load sub-agent dispatch plus context-memory for non-CLI workflows that do not always need template helpers.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md
RULES:
  ALWAYS load sub-agent dispatch before a workflow may launch native or inline sub-agents
  ALWAYS load context-memory before storing or forwarding workflow resource_context
```

```pdsl
UNIT WorkflowBootstrapCommandDispatchContext
PURPOSE: Resolve `{cfs_cmd}` and load dispatch/context helpers for authoring workflows.
DO:
  RUN WorkflowBootstrapCommandResolution
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md
RULES:
  ALWAYS load sub-agent dispatch before a workflow may launch native or inline sub-agents
  ALWAYS load context-memory before storing or forwarding workflow resource_context
```

```pdsl
UNIT WorkflowBootstrapCommandDispatchTemplateContext
PURPOSE: Resolve `{cfs_cmd}` and load dispatch, template, and context helpers for path-aware workflows that may dispatch sub-agents.
DO:
  RUN WorkflowBootstrapCommandResolution
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/template-vars.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md
RULES:
  ALWAYS load sub-agent dispatch before a workflow may launch native or inline sub-agents
  ALWAYS load template-vars before resolving workflow paths or unknown template variables
  ALWAYS load context-memory before storing or forwarding workflow resource_context
```
