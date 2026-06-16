# Write Docs Completion
```pdsl
UNIT WriteDocsCompletion
PURPOSE: Emit a concise completion report, then offer context-grounded next actions after document authoring/review completes cleanly.
WHEN:
  REQUIRE no review findings remain
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT a concise completion report covering work done, deterministic gate outcome (including "not run" when GATE_STATUS == not-run), and semantic review outcome with no remaining findings
  RUN NextActionsOffer
RULES:
  ALWAYS use this unit only after document validation/review is complete and control is about to return to the user
  NEVER bypass NextActionsOffer on a clean terminal path that returns control to the user
```
