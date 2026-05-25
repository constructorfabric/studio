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

```text
UNIT NewPromptMode

PURPOSE:
  Create one new prompt/workflow/skill instruction file in PDSL.

STATE:
  PDSL_MODE: new | transform | review
    scope: inherited_from_parent

WHEN:
  PDSL_MODE == new

REQUIRE:
  target_paths contains exactly one output path
  user intent or source context is available

DO:
  EMIT write_summary(target_paths, source_paths)
  EMIT_MENU WriteConfirmMenu
  WAIT user.reply
  STOP_TURN

MENU WriteConfirmMenu:
  TITLE: Confirm write to target path(s) listed above
  OPTIONS:
    1 proceed -> DISPATCH cf-pdsl-author WITH NewPromptInputs
                 RETURN manifest
    2 cancel  -> EMIT "Write cancelled. No files written."
                 STOP_TURN
  INVALID:
    EMIT "Reply with 1 (proceed) or 2 (cancel)."
    WAIT user.reply
    STOP_TURN

ON_ERROR:
  missing_output_path ->
    EMIT "Provide one output path for the new prompt file."
    WAIT user.reply
    CONTINUE NewPromptMode

  missing_intent ->
    EMIT "Describe the prompt's purpose, expected inputs, outputs, and UX decisions."
    WAIT user.reply
    CONTINUE NewPromptMode

  dispatch_failed ->
    SET CF_PHASE_GATE = armed
    EMIT failure_summary
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
