---
cf: true
type: workflow-fragment
parent: workflows/pdsl.md
description: Invoke when cf-pdsl intent is reviewing PDSL prompt files.
version: 0.1
---

# PDSL Review Mode

Open, load, and follow this file only when `PDSL_MODE == review` or
the user intent clearly asks to check PDSL quality, safety, or
compactness.

```text
UNIT ReviewPromptMode

PURPOSE:
  Review prompt files for PDSL quality and behavioral safety.

STATE:
  PDSL_MODE: new | transform | review
    scope: inherited_from_parent

WHEN:
  PDSL_MODE == review

REQUIRE:
  target_paths is non-empty
  SUB_AGENT_SESSION_APPROVED == true OR INLINE_FALLBACK == true

DO:
  IF SUB_AGENT_SESSION_APPROVED == unset AND INLINE_FALLBACK == unset:
    CONTINUE PdslDispatchGate
  DISPATCH cf-pdsl-reviewer WITH ReviewPromptInputs
  RETURN validation_report

ON_ERROR:
  missing_target_paths ->
    EMIT "Provide one or more prompt/workflow/skill files to review."
    WAIT user.reply
    CONTINUE ReviewPromptMode

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
  "pdsl_spec_path": "{cf-studio-path}/.core/architecture/specs/PDSL.md",
  "rules_mode": "STRICT|RELAXED"
}
```

Review mode is read-only. It MUST NOT write files.

Completion: return the `cf-pdsl-reviewer` validation report. If the
reviewer cannot read every requested file, return a partial checkpoint and do
not claim PASS for unread paths.
