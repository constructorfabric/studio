---
name: analyze-phase-5-next-steps
description: "Invoke when running Analyze Phase 5 to offer next steps (skipped when EXPLAIN_MODE=true; FAIL defers to Phase 4 Remediation Handoff menu)."
purpose: Analyze Phase 5 — offer next steps from rules.md (EXPLAIN_MODE skips this phase; FAIL defers to Phase 4 Remediation Handoff menu)
loaded_by: workflows/analyze.md
version: 1.0
---

```text
UNIT AnalyzePhase5NextSteps

PURPOSE:
  Offer applicable next steps from rules.md after a PASS result.

WHEN:
  overall result is PASS AND EXPLAIN_MODE == false

DO:
  IF EXPLAIN_MODE == true:
    STOP (skip this phase entirely)
  IF actionable findings exist:
    STOP (Remediation Handoff menu in Phase 4 is the next-step selector)
  Read "## Next Steps" from rules.md.
  EMIT_MENU NextStepsMenu
  WAIT user.reply
  STOP_TURN

MENU NextStepsMenu:
  TITLE: "What would you like to do next?"
  OPTIONS:
    1 {option from rules Next Steps for success} ->
        State why and what happens next (suggested when clearest continuation)
    2 {option from rules Next Steps} ->
        State what this does next
    3 Other -> Say what you want to change or do next
  INVALID:
    EMIT "Reply 1, 2, or 3, or describe what you want to do next."
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST skip this phase entirely when EXPLAIN_MODE=true
    (Storytelling Output already emits Suggested Next Steps)
  - MUST_NOT emit a separate menu when actionable findings exist (FAIL path);
    Phase 4 Remediation Handoff IS the next-step selector for failure cases
  - MUST_NOT duplicate or paraphrase the Remediation Handoff menu here
  - MUST_NOT ask whether the handoff menu should be generated
  - MUST_NOT defer the handoff menu to a later user turn

NOTES:
  EXPLAIN_MODE was set in preamble.md; no re-load of phase-0-dependencies.md needed.
  For the EXPLAIN_MODE skip-list see:
    {cf-studio-path}/.core/requirements/storytelling.md § Agent Instructions
```

## Phase 5: Offer Next Steps

When `EXPLAIN_MODE=true`, **skip this phase entirely** — the Storytelling Output schema (`{cf-studio-path}/.core/workflows/analyze/phase-4-output/output-storytelling.md`) already emits a contextual `Suggested Next Steps` section, so running this sub-file would produce a redundant menu. (EXPLAIN_MODE was set in `{cf-studio-path}/.core/workflows/analyze/preamble.md`; no re-load of `{cf-studio-path}/.core/workflows/analyze/phase-0-dependencies.md` needed. Open, load, and follow `{cf-studio-path}/.core/requirements/storytelling.md` § Agent Instructions for the full skip-list.)

Read `## Next Steps` from `{cf-studio-path}/.core/workflows/analyze/rules.md` and present applicable options.

PASS:
```
What would you like to do next?
1. {option from rules Next Steps for success} — Suggested when it is the clearest continuation from the current result; state why and what happens next.
2. {option from rules Next Steps} — State what this does next.
3. Other — Say what you want to change or do next.
Reply with the option number or a short custom instruction.
```
FAIL:

When actionable findings exist, this sub-file does NOT emit a separate menu. The `workflows/analyze/phase-4-output/remediation-handoff.md` menu IS the next-step selector for failure cases. Do not duplicate or paraphrase it here. MUST NOT ask whether the handoff menu should be generated and MUST NOT defer it to a later user turn — the menu is emitted as the final section of the current response per `workflows/analyze/phase-4-output/remediation-handoff.md` § `enforceRemediationPrompts`.
