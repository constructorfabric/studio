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

```text
UNIT TransformPromptMode

PURPOSE:
  Convert one or more existing prose prompt files into PDSL.

STATE:
  PDSL_MODE: new | transform | review
    scope: inherited_from_parent

WHEN:
  PDSL_MODE == transform

REQUIRE:
  target_paths is non-empty

DO:
  EMIT write_summary(target_paths, source_paths)
  EMIT_MENU WriteConfirmMenu
  WAIT user.reply
  STOP_TURN

MENU WriteConfirmMenu:
  TITLE: Confirm write to target path(s) listed above
  OPTIONS:
    1 proceed -> DISPATCH cf-pdsl-transformer WITH TransformPromptInputs
                 RETURN manifest
    2 cancel  -> EMIT "Write cancelled. No files written."
                 STOP_TURN
  INVALID:
    EMIT "Reply with 1 (proceed) or 2 (cancel)."
    WAIT user.reply
    STOP_TURN

ON_ERROR:
  missing_target_paths ->
    EMIT "Provide one or more prompt/workflow/skill files to transform."
    WAIT user.reply
    CONTINUE TransformPromptMode

  dispatch_failed ->
    SET CF_PHASE_GATE = armed
    EMIT failure_summary
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

Transform mode MUST preserve behavior before compacting wording. If a prompt
contains ambiguous behavior that cannot be preserved safely, the transformer
MUST either keep the original prose in `NOTES` with an `OPEN_QUESTIONS` block
or return `TRANSFORM_BLOCKED` with the unresolved questions.

Completion: return the `cf-pdsl-transformer` manifest or a
`TRANSFORM_BLOCKED` payload.
