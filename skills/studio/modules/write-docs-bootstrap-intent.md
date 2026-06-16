# Write Docs Bootstrap Intent

```pdsl
UNIT WriteDocsBootstrapIntentContext
PURPOSE: Resolve the initial doc-writing intent and load context-memory for downstream document work.
DO:
  SET ORIGINAL_INTENT = the user's triggering write-docs request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  RUN WorkflowBootstrapContextOnly
```

```pdsl
UNIT WriteDocsBootstrapReferenceLoad
PURPOSE: Load and verify the shared documentation references used by cf-write-docs.
DO:
  LOAD {cf-studio-path}/.core/requirements/consistency-checklist.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/language-complexity.md
  RUN LanguageComplexityLoad
  LOAD {cf-studio-path}/.core/requirements/storytelling-dimensions.md
  LOAD {cf-studio-path}/.core/skills/studio/agents/cf-semantic-reviewer-artifact.md
  RUN verify the references loaded; EMIT "Required reference not found (consistency-checklist, language-complexity, storytelling-dimensions, or cf-semantic-reviewer-artifact under {cf-studio-path}/.core) — cannot author or review docs; reinstall or sync the studio kit, then retry." and STOP_TURN WHEN any load fails
```

```pdsl
UNIT WriteDocsBootstrapDimensions
PURPOSE: Normalize artifact context and resolve the storytelling dimensions applied to document authoring and review.
DO:
  RUN WriteDocsArtifactContextNormalize
  RUN AudienceResolution, NarratorResolution, and DiagramResolution for the cf-write-docs flow class; SET DOC_AUDIENCE_DIMENSION = resolved, SET DOC_NARRATOR_DIMENSION = resolved, and SET DOC_DIAGRAM_DIMENSION = resolved before any author or reviewer dispatch
```
