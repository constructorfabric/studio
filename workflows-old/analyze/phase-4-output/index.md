---
name: analyze-phase-4-output-index
description: "Invoke when entering Analyze Phase 4 to select the output schema sub-file matching the active mode and route the remediation handoff."
purpose: Phase 4 output dispatcher — selects the schema sub-file matching the active mode and routes the remediation handoff
loaded_by: workflows/analyze.md
version: 1.0
---

```pdsl
UNIT AnalyzePhase4OutputDispatcher

PURPOSE:
  Select the output schema sub-file matching the active mode and route the
  remediation handoff when applicable.

RULES:
  - ALWAYS print to chat only; NEVER create files
  - ALWAYS load exactly one output sub-file
  - ALWAYS treat this phase as terminal when it emits either:
      a PARTIAL checkpoint/resume block
      a remediation handoff menu
  - ALWAYS append remediation-handoff.md after the selected schema when actionable
    findings exist AND EXPLAIN_MODE=false
  - NEVER emit Fix Prompt or Plan Prompt from this unit (those are emitted by
    remediation-handoff.md on demand)
  - ALWAYS render Prompt Review Partial Checkpoint block (not full schema) when
    PROMPT_REVIEW=true AND checkpoint.type=PARTIAL_CHECKPOINT
  - ALWAYS STOP_TURN after a prompt-review PARTIAL checkpoint block
  - ALWAYS STOP_TURN after remediation-handoff.md emits its menu
  - ALWAYS return to router for Phase 5 only when PARTIAL=false, no remediation
    handoff was emitted, and the selected schema completed a non-EXPLAIN PASS turn

DO:
  - REQUIRE EXPLAIN_MODE == true:
    - LOAD {cf-studio-path}/.core/workflows/analyze/phase-4-output/output-storytelling.md
  - RUN otherwise IF PROMPT_REVIEW == true OR PROMPT_BUG_REVIEW == true:
    - LOAD {cf-studio-path}/.core/workflows/analyze/phase-4-output/output-prompt-review.md
  - RUN otherwise
    - LOAD {cf-studio-path}/.core/workflows/analyze/phase-4-output/output-standard.md
  - REQUIRE (PROMPT_REVIEW == true OR PROMPT_BUG_REVIEW == true) AND checkpoint.type == "PARTIAL_CHECKPOINT":
    - STOP_TURN
  - REQUIRE actionable findings exist AND EXPLAIN_MODE == false:
    - LOAD {cf-studio-path}/.core/workflows/analyze/phase-4-output/remediation-handoff.md
    - STOP_TURN

NOTES:
  Output sub-file selection:
  - `PROMPT_REVIEW=true` or `PROMPT_BUG_REVIEW=true` → output-prompt-review.md
  - `PROMPT_REVIEW=false`, `PROMPT_BUG_REVIEW=false` and EXPLAIN_MODE=false → output-standard.md
  - EXPLAIN_MODE=true → output-storytelling.md

  prompt-review partial checkpoints satisfy Phase 4 terminal requirements;
  no remediation handoff is appended after a PARTIAL_CHECKPOINT stop.

  enforceRemediationPrompts policy and the EXPLAIN_MODE override live in the
  standard output sub-file and the remediation-handoff sub-file; load both
  together when the active mode requires the handoff menu.
```
