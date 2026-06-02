---
cf: true
type: workflow-fragment
parent: workflows/pdsl.md
description: Invoke when cf-pdsl intent is transforming existing prompt files into PDSL.
version: 0.1
---

# PDSL Transform Mode

Open, load, and follow this file only when `PDSL_MODE == transform`
or the user intent clearly asks to convert, rewrite, or migrate existing prompt
files into PDSL.

```pdsl
UNIT TransformPromptMode

PURPOSE:
  Convert one or more existing prose prompt files into PDSL.

STATE:
  - SET PDSL_MODE: new | transform | review
    scope: inherited_from_parent

WHEN:
  - REQUIRE PDSL_MODE == transform

DO:
  - REQUIRE target_paths is non-empty
  - SET PDSL_WRITE_CONFIRM_MODE = transform
  - SET PDSL_WRITE_CONFIRM_PRECONDITIONS = satisfied
  - SET PDSL_WRITE_CONFIRM_AGENT = cf-pdsl-transformer
  - SET PDSL_WRITE_CONFIRM_INPUTS = TransformPromptInputs
  - LOAD {cf-studio-path}/.core/workflows/shared/pdsl-write-confirm-menu.md
  - LOAD {cf-studio-path}/.core/workflows/shared/pdsl-write-confirm-gate.md
  - CONTINUE SharedPdslWriteConfirmGate

ON_ERROR:
  missing_target_paths ->
    EMIT_MENU TransformMissingTargetsMenu
    WAIT user.reply
    CONTINUE TransformPromptMode

  dispatch_failed ->
    SET CF_PHASE_GATE = armed
    EMIT failure_summary
    STOP_TURN

MENU TransformMissingTargetsMenu:
  TITLE: PDSL transform targets
  OPTIONS:
    1 provide target paths -> SET target_paths = user supplied prompt/workflow/skill paths
    2 stop -> STOP_TURN
  INVALID:
    EMIT "Reply with 1: <paths> or 2 to stop."
    WAIT user.reply
    STOP_TURN
```

Dispatch payload:

```json
{
  "target_paths": ["<prompt/workflow/skill path>", "..."],
  "source_paths": ["<optional cross-reference paths>"],
  "transform_policy": "in_place",
  "pdsl_spec_path": "{cf-studio-path}/.core/architecture/specs/PDSL.md",
  "rules_mode": "STRICT|RELAXED"
}
```

```pdsl
UNIT TransformPromptCompletion

PURPOSE:
  Define the semantic preservation contract and terminal return for transform mode.

RULES:
  - ALWAYS preserve behavioral semantics before compacting wording
  - ALWAYS keep the original prose in NOTES with an OPEN_QUESTIONS block when ambiguous behavior cannot be safely preserved
  - ALWAYS return TRANSFORM_BLOCKED with unresolved questions when ambiguous behavior cannot be safely preserved
  - ALWAYS return the cf-pdsl-transformer manifest on successful dispatch
```
