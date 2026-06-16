# Brainstorm Bootstrap Refs

```pdsl
UNIT BrainstormExecutionContextPrep
PURPOSE: Load dispatch and context helpers only when brainstorm is about to run panel execution.
DO:
  RUN WorkflowBootstrapDispatchContext
```

```pdsl
UNIT BrainstormWrapPathPrep
PURPOSE: Load template helpers only when brainstorm wrap is about to resolve a checkpoint path.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/template-vars.md
```
