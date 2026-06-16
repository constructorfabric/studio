# Write Docs Bootstrap Intent

```pdsl
UNIT WriteDocsBootstrapIntentContext
PURPOSE: Resolve the initial doc-writing intent before workflow-specific routing decides whether execution prep is needed.
DO:
  SET ORIGINAL_INTENT = the user's triggering write-docs request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
```
