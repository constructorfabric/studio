# Write Skills Bootstrap Refs

```pdsl
UNIT WriteSkillsExecutionContextPrep
PURPOSE: Load command, dispatch, and context helpers only on authoring/review-capable paths.
DO:
  RUN WorkflowBootstrapCommandDispatchContext
```

```pdsl
UNIT WriteSkillsExecutionReferenceLoad
PURPOSE: Load and verify the PDSL authoring references used by cf-write-skills before author or reviewer dispatch.
DO:
  LOAD {cf-studio-path}/.core/architecture/specs/PDSL.md
  LOAD {cf-studio-path}/.core/requirements/prompt-engineering.md
  RUN verify both references loaded; EMIT "Required reference not found (PDSL spec or prompt-engineering methodology under {cf-studio-path}/.core) — cannot author or review; reinstall or sync the studio kit, then retry." and STOP_TURN WHEN either load fails
```
