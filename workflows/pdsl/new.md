---
cf: true
type: workflow-fragment
parent: workflows/pdsl.md
description: Invoke when cf-pdsl intent is new prompt/workflow/skill instruction creation.
version: 0.1
---

# PDSL New Mode

Open, load, and follow this file only when `PDSL_MODE == new` or the
user intent clearly asks to create a new prompt/workflow/skill instruction file.

```pdsl
UNIT NewPromptMode

PURPOSE:
  Create one new prompt/workflow/skill instruction file in PDSL.

STATE:
  - SET PDSL_MODE: new | transform | review
    scope: inherited_from_parent

WHEN:
  - REQUIRE PDSL_MODE == new

DO:
  - REQUIRE target_paths contains exactly one output path
  - REQUIRE user intent or source context is available
  - SET PDSL_WRITE_CONFIRM_MODE = new
  - SET PDSL_WRITE_CONFIRM_PRECONDITIONS = satisfied
  - SET PDSL_WRITE_CONFIRM_AGENT = cf-pdsl-author
  - SET NewPromptInputs = target_paths, source_paths, user intent, source context,
    constraints, pdsl_spec_path, rules_mode
  - SET PDSL_WRITE_CONFIRM_INPUTS = NewPromptInputs
  - LOAD {cf-studio-path}/.core/workflows/shared/pdsl-write-confirm-menu.md
  - LOAD {cf-studio-path}/.core/workflows/shared/pdsl-write-confirm-gate.md
  - CONTINUE SharedPdslWriteConfirmGate

ON_ERROR:
  missing_output_path ->
    EMIT_MENU NewPromptMissingOutputMenu
    WAIT user.reply
    CONTINUE NewPromptMode

  missing_intent ->
    EMIT_MENU NewPromptMissingIntentMenu
    WAIT user.reply
    CONTINUE NewPromptMode

  dispatch_failed ->
    SET CF_PHASE_GATE = armed
    EMIT failure_summary
    STOP_TURN

MENU NewPromptMissingOutputMenu:
  TITLE: New PDSL prompt output path
  OPTIONS:
    1 provide output path -> SET target_paths = user supplied single output path
    2 stop -> STOP_TURN
  INVALID:
    EMIT "Reply with 1: <output path> or 2 to stop."
    WAIT user.reply
    STOP_TURN

MENU NewPromptMissingIntentMenu:
  TITLE: New PDSL prompt intent
  OPTIONS:
    1 describe intent -> SET source context = user supplied purpose, inputs, outputs, and UX decisions
    2 stop -> STOP_TURN
  INVALID:
    EMIT "Reply with 1: <purpose/inputs/outputs/UX> or 2 to stop."
    WAIT user.reply
    STOP_TURN
```

Dispatch payload:

```json
{
  "target_path": "<new file path>",
  "prompt_purpose": "<what the prompt/workflow/skill should do>",
  "source_paths": ["<optional context paths>"],
  "constraints": ["<must-have behavior, state, UX, routing, or safety rules>"],
  "pdsl_spec_path": "{cf-studio-path}/.core/architecture/specs/PDSL.md",
  "rules_mode": "STRICT|RELAXED"
}
```

Completion: return the `cf-pdsl-author` manifest or an
`AUTHOR_BLOCKED` payload.
