# Write Docs Bootstrap Intent

```pdsl
UNIT WriteDocsBootstrapIntentContext
PURPOSE: Resolve the initial doc-writing intent before workflow-specific routing decides whether execution prep is needed.
DO:
  SET ORIGINAL_INTENT = the user's triggering write-docs request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
```

```pdsl
UNIT WriteDocsExecutionContextPrep
PURPOSE: Load shared execution-time context and resolve document policy dimensions before any author or reviewer dispatch.
DO:
  RUN WorkflowBootstrapContextOnly
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-artifact-normalize.md
  LOAD {cf-studio-path}/.core/requirements/storytelling-dimensions.md
  RUN verify the references loaded; EMIT "Required reference not found (write-docs-artifact-normalize or storytelling-dimensions under {cf-studio-path}/.core) — cannot author or review docs; reinstall or sync the studio kit, then retry." and STOP_TURN WHEN any load fails
  RUN WriteDocsArtifactContextNormalize
  RUN AudienceResolution for the cf-write-docs flow class; SET DOC_AUDIENCE_DIMENSION = resolved before any author or reviewer dispatch
  RUN NarratorResolution for the cf-write-docs flow class; SET DOC_NARRATOR_DIMENSION = resolved before any author or reviewer dispatch
  RUN DiagramResolution for the cf-write-docs flow class; SET DOC_DIAGRAM_DIMENSION = resolved before any author or reviewer dispatch
```

```pdsl
UNIT WriteDocsReviewReferenceLoad
PURPOSE: Load and verify the read-only review references used by the docs review loop.
DO:
  LOAD {cf-studio-path}/.core/requirements/consistency-checklist.md
  LOAD {cf-studio-path}/.core/skills/studio/agents/cf-semantic-reviewer-artifact.md
  RUN verify the references loaded; EMIT "Required review reference not found (consistency-checklist or cf-semantic-reviewer-artifact under {cf-studio-path}/.core) — cannot review docs; reinstall or sync the studio kit, then retry." and STOP_TURN WHEN any load fails
```

```pdsl
UNIT WriteDocsWriteReferenceLoad
PURPOSE: Load and verify the write-capable document policy references used by document author and review-fix dispatches.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/language-complexity.md
  RUN LanguageComplexityLoad
  RUN verify the references loaded; EMIT "Required write reference not found (language-complexity under {cf-studio-path}/.core) — cannot write docs; reinstall or sync the studio kit, then retry." and STOP_TURN WHEN any load fails
```
