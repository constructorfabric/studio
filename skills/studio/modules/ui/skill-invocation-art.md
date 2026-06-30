---
cf: true
type: module
name: skill-invocation-art
purpose: Defines SkillInvocationArt — the ASCII-art entry picture rendered at cf/cf-* workflow bootstrap.
---

# Skill Invocation Art

```pdsl
UNIT SkillInvocationArt
PURPOSE: Prefix each cf, cf-studio, or cf-* skill entry with one small ASCII-art picture relevant to the skill name, with a plain-text label below, without changing the workflow's control flow.
WHEN:
  REQUIRE a cf, cf-studio, or cf-* skill or workflow entry is beginning execution
  SKIP silently (no picture, no output) WHEN this unit is loaded in a context that does not satisfy the above REQUIRE
DO:
  RUN SkillInvocationArtGuard
  RUN SkillInvocationArtGenerate WHEN SkillInvocationArtGuard passes
RULES:
  ALWAYS run this unit once at the start of every cf, cf-studio, or cf-* workflow bootstrap or alias entry, before the workflow's first normal EMIT, EMIT_MENU, WAIT, CONTINUE, INVOKE, DISPATCH, RETURN, or STOP_TURN
  NEVER alter, delay, or suppress any existing output directive; the picture precedes but does not replace or reorder normal output
  NEVER replace, delay, reorder, suppress, or alter any load report
  NEVER emit more than one picture for the same skill or workflow entry
NOTES:
  APPROVED_VISUAL_CATEGORIES: animal, monster, object, graffiti tag, creature, tool, scene
```

```pdsl
UNIT SkillInvocationArtGuard
PURPOSE: Gate the picture emission — determine whether conditions allow a picture to be drawn and emitted.
WHEN:
  REQUIRE SkillInvocationArt is running
DO:
  SKIP the picture and continue the workflow immediately WHEN the entering skill name is unavailable or blank, or WHEN no subject from the approved visual categories (see SkillInvocationArt NOTES) can be associated with the skill name in a single selection
  PASS (allow picture emission) WHEN a concrete visual subject can be selected from the approved visual categories (see SkillInvocationArt NOTES)
RULES:
  ALWAYS skip the picture and continue immediately when a picture subject cannot be derived
  EMIT the picture only when a selected workflow begins execution — specifically, at the moment the selected skill or workflow's own bootstrap begins — not when presenting a companion suggestion, matched-route option, next-action option, or generated launch list
  NEVER block, fail, retry, or ask the user over picture derivation failure
  NEVER emit a picture for menus that merely list skills without entering them
```

```pdsl
UNIT SkillInvocationArtGenerate
PURPOSE: Draw the ASCII-art picture and emit it with a label line.
WHEN:
  REQUIRE SkillInvocationArtGuard passes
DO:
  RUN derive a picture subject from the entering skill or workflow name and purpose — pick a concrete visual subject from the approved visual categories (see SkillInvocationArt NOTES) whose role or action type is recognizably associated with the skill's primary function (see subject mapping in NOTES)
  CHECK before emitting: verify the picture satisfies all RULES constraints below; revise once if any constraint fails, then skip silently if still unmet
  EMIT exactly one ASCII-art picture followed by the label line, before the entry's normal output
RULES:
  ALWAYS draw the picture as a small ASCII illustration of the chosen subject using printable-ASCII characters, NOT as large-letter text rendered in ASCII font
  ALWAYS keep the picture at most 12 lines tall and 60 columns wide, using printable-ASCII only
  ALWAYS place a short plain-text label on the line immediately after the picture; format: `<skill-name> | <subject-noun>`, plain lowercase, max one line, max 60 characters (e.g., `cf-brainstorm | the owl`)
  ALWAYS prefer drawing a recognizable pictorial shape over abstract line patterns
  ALWAYS treat the picture as entry presentation only; it is not a prerequisite gate, not a routing decision, not a consent prompt, and not a source of workflow state
  ALWAYS prefer immediate workflow progress over waiting on picture derivation
  ALWAYS permit alias-delegation INVOKE to the resolved target skill immediately after the picture when this unit runs from a cf-studio alias entry; the delegated target MUST NOT emit a second picture
NOTES:
  Subject mapping guidance (examples, not normative): planners get architectural subjects; reviewers get inspectors or detectives; generators get craftspeople or machines; explorers get scouts or animals; debuggers get creatures that hunt or dissect; brainstorm gets a creative animal or inventor.

  Minimal correct example — cf-brainstorm with an owl:

      (o,o)
      (   )
     --"-"--
    cf-brainstorm | the owl

  Incorrect example (VIOLATION — large-letter ASCII-font text, not a pictorial illustration):

       ____  _____
      | __ )/ ____|
      |  _ \\___ \
      | |_) |___) |
      |____/|____/
      cf-brainstorm | letters
```
