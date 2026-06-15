# Skill Invocation Art

```pdsl
UNIT SkillInvocationArt
PURPOSE: Prefix each cf/cf-* skill entry with one small skill-themed ASCII-art banner without changing the workflow's control flow.
WHEN:
  REQUIRE a cf, cf-studio, or cf-* skill/workflow entry is beginning execution
DO:
  RUN derive a small printable-ASCII theme from the entering skill or workflow name plus its purpose or description
  SKIP the banner and continue the workflow immediately WHEN the theme cannot be derived immediately
  EMIT exactly one small ASCII-art banner for this entry before the entry's normal output
RULES:
  ALWAYS run this unit at the start of every cf/cf-* workflow bootstrap or alias entry, immediately after this module is loaded and before the workflow's first normal EMIT, EMIT_MENU, WAIT, CONTINUE, INVOKE, DISPATCH, RETURN, or STOP_TURN
  ALWAYS treat the banner as entry presentation only; it is not a prerequisite gate, not a routing decision, not a consent prompt, and not a source of workflow state
  ALWAYS keep the banner at most 12 lines tall and 60 columns wide, using printable ASCII only
  ALWAYS make the banner specific to the entering skill/workflow name and available purpose details
  ALWAYS prefer immediate workflow progress over waiting on banner theme derivation
  NEVER emit more than one banner for the same skill/workflow entry
  NEVER emit a banner for menus that merely list skills without entering them
  NEVER emit a banner for a companion suggestion, matched-route option, next-action option, or generated launch list; emit only after the selected workflow begins execution
  NEVER replace, delay, reorder, suppress, or alter any load report, gate, menu, WAIT, STOP_TURN, validation result, or terminal shape; the banner only precedes the entry's normal output
  NEVER block, fail, retry, or ask the user over banner derivation failure
```
