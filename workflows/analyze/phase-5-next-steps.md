---
name: analyze-phase-5-next-steps
description: "Invoke when running Analyze Phase 5 to offer next steps (skipped when EXPLAIN_MODE=true; FAIL defers to Phase 4 Remediation Handoff menu)."
purpose: Analyze Phase 5 — offer next steps from rules.md (EXPLAIN_MODE skips this phase; FAIL defers to Phase 4 Remediation Handoff menu)
loaded_by: workflows/analyze.md
version: 1.0
---

```pdsl
UNIT AnalyzePhase5NextSteps

PURPOSE:
  Offer applicable next steps from rules.md after a PASS result.

WHEN:
  - REQUIRE overall result is PASS AND EXPLAIN_MODE == false

DO:
  - REQUIRE EXPLAIN_MODE == true:
    STOP (skip this phase entirely)
  - REQUIRE actionable findings exist:
    STOP (Remediation Handoff menu in Phase 4 is the next-step selector)
  - RUN Read "## Next Steps" from rules.md.
  - EMIT_MENU NextStepsMenu
  - WAIT user.reply
  - STOP_TURN

MENU NextStepsMenu:
  TITLE: "What would you like to do next?"
  OPTIONS:
    1 deeper ->
        Run a related deeper analysis on the same or adjacent targets.
    2 generate ->
        Handoff to Invoke skill `cf-generate` for improvements or follow-up changes.
    3 plan ->
        Handoff to Invoke skill `cf-plan` to decompose broader follow-up work.
    4 done ->
        End the analyze session with no further workflow handoff.
    5 other ->
        Say what you want to change or do next.
  INVALID:
    EMIT "Reply 1, 2, 3, 4, 5, or describe what you want to do next."
    WAIT user.reply
    STOP_TURN

RULES:
  - ALWAYS skip this phase entirely when EXPLAIN_MODE=true
    (Storytelling Output already emits Suggested Next Steps)
  - NEVER emit a separate menu when actionable findings exist (FAIL path);
    Phase 4 Remediation Handoff IS the next-step selector for failure cases
  - NEVER duplicate or paraphrase the Remediation Handoff menu here
  - NEVER ask whether the handoff menu should be generated
  - NEVER defer the handoff menu to a later user turn

NOTES:
  EXPLAIN_MODE was set in preamble.md; no re-load of phase-0-dependencies.md needed.
  For the EXPLAIN_MODE skip-list see:
    {cf-studio-path}/.core/requirements/storytelling.md § Agent Instructions
```
