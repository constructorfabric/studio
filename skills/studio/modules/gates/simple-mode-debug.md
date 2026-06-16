# Debug Mode Branch

```pdsl
UNIT SimpleModeDebug
PURPOSE: Reuse the canonical debugger overlay in run mode without opening the standalone debugger console.
WHEN:
  - REQUIRE SIMPLE_MODE == debug
DO:
  - LOAD {cf-studio-path}/.core/workflows/debug-prompts.md
  - RUN DebugSessionRunModeInit
RULES:
  - ALWAYS reuse the canonical `cf-debug-prompts` workflow instead of duplicating debugger state here
  - ALWAYS arm the debugger in run mode on first activation so traces, logs, and breakpoints stay active without per-action stepping
  - NEVER open the standalone debugger console from the simple-mode gate
  - NEVER clear an active debugger session during reuse for later workflow entries
```
