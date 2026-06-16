# Explore Bootstrap Refs

```pdsl
UNIT ExploreExecutionContextPrep
PURPOSE: Load dispatch and context helpers only when explore is about to run explorer agents.
DO:
  RUN WorkflowBootstrapDispatchContext
```

```pdsl
UNIT ExploreSaveContextPrep
PURPOSE: Load template helpers only when explore is about to resolve a save path.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/template-vars.md
```
