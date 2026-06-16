# Coding Bootstrap Methodologies

```pdsl
UNIT CodingExecutionContextPrep
PURPOSE: Load context-memory only on review-capable or author-capable coding paths.
DO:
  RUN WorkflowBootstrapContextOnly
```

```pdsl
UNIT CodingValidationContextPrep
PURPOSE: Resolve command and context helpers only on deterministic validation paths.
DO:
  RUN WorkflowBootstrapCommandContext
```

```pdsl
UNIT CodingReviewReferenceLoad
PURPOSE: Load and verify the code review methodologies used by cf-coding before reviewer dispatch.
DO:
  LOAD {cf-studio-path}/.core/requirements/code-checklist.md
  LOAD {cf-studio-path}/.core/requirements/bug-finding.md
  LOAD {cf-studio-path}/.core/requirements/consistency-checklist.md
  RUN verify the references loaded; EMIT "Required reference not found (code-checklist, bug-finding, or consistency-checklist methodology under {cf-studio-path}/.core) — cannot author or review code; reinstall or sync the studio kit, then retry." and STOP_TURN WHEN any load fails
```
