# Explain Bootstrap Refs

```pdsl
UNIT ExplainExecutionContextPrep
PURPOSE: Load dispatch and context helpers only when explain is about to launch storytelling agents.
DO:
  RUN WorkflowBootstrapDispatchContext
```

```pdsl
UNIT ExplainStorytellingReferenceLoad
PURPOSE: Load storytelling requirements only after a concrete explanation target exists.
DO:
  LOAD {cf-studio-path}/.core/requirements/storytelling.md (its router loads storytelling-shared, storytelling-phases, storytelling-modes, and storytelling-preferences)
  LOAD {cf-studio-path}/.core/requirements/storytelling-export.md WHEN EXPLAIN_EXPORT == true
```

```pdsl
UNIT ExplainExportContextPrep
PURPOSE: Load template helpers only when explain export is about to resolve package paths.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/template-vars.md
```
