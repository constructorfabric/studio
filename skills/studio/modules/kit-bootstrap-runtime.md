# Kit Bootstrap Runtime
```pdsl
UNIT KitInitBootstrapLoadRuntime
PURPOSE: Load the kit runtime support modules before any target routing or CLI work.
DO:
  LOAD and REMEMBER rules from {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode.md
  RUN SimpleModeGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/studio-instructions-memory.md
  RUN StudioInstructionsMemoryGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/command-resolution.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/template-vars.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md
  RUN CommandResolution to resolve {cfs_cmd}
UNIT KitInitBootstrapVerifyNormalize
PURPOSE: Verify that the kit normalize command surface is available.
DO:
  RUN verify `{cfs_cmd} kit normalize --help` supports `--from`, `--output`, `--dry-run`, and `--stdout`
UNIT KitInitBootstrapNormalizeUnavailable
PURPOSE: Stop early when the required kit normalize capability is unavailable.
DO:
  EMIT "Required kit normalization command is unavailable; update Constructor Studio, then retry cf-kit."
  STOP_TURN
```
