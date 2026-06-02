---
name: analyze-context-budget
description: "Invoke when loading analyze workflow context-budget rules for sizing, chunked loading, fail-safe behavior, and the Phase 0.1 plan-escalation pointer."
purpose: Analyze workflow context-budget rules — sizing, chunked loading, fail-safe, and Phase 0.1 plan-escalation pointer
loaded_by: workflows/analyze.md
version: 1.0
---

# Analyze — Context Budget

```pdsl
UNIT AnalyzeContextBudget

PURPOSE:
  Enforce context-budget sizing, chunked loading, fail-safe output, and
  plan-escalation pointer before loading large documents.

WHEN:
  - REQUIRE AnalyzePhase0 has completed dependency resolution
  - AND Phase 0.1 or later analysis is about to load large documents
  - OR estimated total context would exceed 1200 retained instruction/input lines

DO:
  - RUN Estimate size before loading large docs (e.g. with `wc -l`); state both
  - RUN estimated retained lines and percent of original context window for this turn.
  - RUN Load only what is used: prefer rules.md Validation and needed checklist categories only.
  - RUN Use read_file ranges; summarize each chunk; keep only extracted criteria.
  - REQUIRE checks cannot be completed within context:
    - EMIT partial output with PARTIAL status as a terminal checkpoint block
    - EMIT checkpoint + resume menu with in-chat retry/resume, fresh-chat resume,
      or stop choices
    - REQUIRE the checkpoint to be durable enough for cross-turn resume
    - NEVER claiming overall PASS
  - CONTINUE phase-0.1-plan-escalation-gate.md

RULES:
  - ALWAYS estimate context size before loading large documents
  - ALWAYS "1200 lines" means retained lines after slice extraction, not raw file
    lines that will be summarized and dropped
  - ALWAYS use chunked reads and summarize-and-drop
  - NEVER claim overall PASS when context budget is exhausted
  - ALWAYS output PARTIAL with checkpoint when checks cannot complete
  - ALWAYS make the PARTIAL checkpoint the terminal shape for that turn when
    further analysis cannot complete safely in-context
  - ALWAYS include explicit resume guidance and a user-visible checkpoint/resume menu
  - NEVER rely on memory-only continuation when budget exhaustion or
    resumability requirements make a durable checkpoint mandatory

NOTES:
  Plan escalation: Phase 0.1 is mandatory after dependencies load; this file
  ALWAYS be entered only after AnalyzePhase0 completes dependency resolution.
  When SUB_AGENT_SESSION_APPROVED=true AND INLINE_FALLBACK=false, the gate
  logs the estimate and proceeds without proposing Invoke skill `cf-plan`; decomposition is
  handled in-workflow by Phase 2.5 (reviewer plan). Otherwise the fallback
  menu routes to Invoke skill `cf-plan` or stop; local single-context continuation is not
  allowed by default.
```
