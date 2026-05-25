---
name: analyze-phase-5-next-steps
description: "Invoke when running Analyze Phase 5 to offer next steps (skipped when EXPLAIN_MODE=true; FAIL defers to Phase 4 Remediation Handoff menu)."
purpose: Analyze Phase 5 — offer next steps from rules.md (EXPLAIN_MODE skips this phase; FAIL defers to Phase 4 Remediation Handoff menu)
loaded_by: workflows/analyze.md
version: 1.0
---

## Phase 5: Offer Next Steps

When `EXPLAIN_MODE=true`, **skip this phase entirely** — the Storytelling Output schema (`workflows/analyze/phase-4-output/output-storytelling.md`) already emits a contextual `Suggested Next Steps` section, so running this sub-file would produce a redundant menu. (EXPLAIN_MODE was set in `preamble.md`; no re-load of `phase-0-dependencies.md` needed. Open, load, and follow `{cf-studio-path}/.core/requirements/storytelling.md` § Agent Instructions for the full skip-list.)

Read `## Next Steps` from `rules.md` and present applicable options.

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
