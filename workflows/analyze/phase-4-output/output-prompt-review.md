---
name: analyze-phase-4-output-prompt-review
description: "Invoke when PROMPT_REVIEW=true to render the Phase 4 Prompt Review output schema merging prompt-engineering and optional prompt-bug-finder sub-agent reports."
purpose: Phase 4 Prompt Review output schema (PROMPT_REVIEW=true) — merges prompt-engineering and optional prompt-bug-finder sub-agent reports
loaded_by: workflows/analyze.md
version: 1.0
---

```pdsl
UNIT AnalyzePhase4PromptReview

PURPOSE:
  Render Phase 4 prompt-review output, merging prompt-engineering and
  optional prompt-bug-finder sub-agent reports.

WHEN:
  - REQUIRE PROMPT_REVIEW == true OR PROMPT_BUG_REVIEW == true

DO:
  - REQUIRE checkpoint.type == "PARTIAL_CHECKPOINT":
    Render Prompt Review Partial Checkpoint block (see below)
    Append Prompt Review Resume menu when checkpoint or findings require follow-up
    STOP (do not render the full prompt-review schema)
  - REQUIRE PROMPT_REVIEW == true:
    Render cf-semantic-reviewer-prompt report in section order:
      - Summary
      - Context Budget & Evidence
      - Compact-Prompts Findings
      - Layer Summaries
      - Issues Found
      - Recommended Fixes
      - Verification Checklist
  - REQUIRE PROMPT_BUG_REVIEW == true:
    Append cf-prompt-bug-finder report after the prompt-engineering report.
    IF PROMPT_REVIEW == false:
      Render only the prompt-bug-finder report under this schema.
      Summary ALWAYS begin with prompt-bug-finding status block:
        Review status | Deterministic gate | Scope reviewed | Review basis |
        Environment snapshot | Coverage summary
      IF deterministic gate is SKIPPED:
        State why and explicitly state "no validator-backed evidence for this review path"

RULES:
  - NEVER use the standard analysis template (output-standard.md) for prompt review
  - NEVER mark prompt-review checks N/A unless the reviewed document explicitly
    makes them inapplicable; report FAIL or PARTIAL when applicability is unresolved
  - ALWAYS render Partial Checkpoint block (not full schema) when
    checkpoint.type=PARTIAL_CHECKPOINT
  - ALWAYS append a prompt-review resume/checkpoint menu when partial checkpoint
    or findings require follow-up; NEVER offer fix/plan remediation until
    the partial review has been resumed/completed or the user explicitly
    accepts incomplete coverage

  NOTES:
  Prompt Review Partial Checkpoint block ALWAYS include:
    - checkpoint.type = "PARTIAL_CHECKPOINT"
    - reviewed target paths and covered layers
    - uncovered layers / resume anchors
    - findings backed by already-covered evidence
    - checkpoint JSON needed to resume the prompt review
  This is a valid partial output, not a clean pass.

MENU PromptReviewResumeMenu:
  TITLE: "Prompt review is partial. Resume review before remediation?"
  OPTIONS:
    1 resume -> Resume the incomplete prompt review in this chat
    2 fresh -> Emit a fresh-chat resume prompt with checkpoint JSON, evidence anchors,
               target_paths, completed/partial reviewer status, findings JSON,
               semantic report inventory, target/methodology fingerprints,
               dispatch manifest inventory, and a required rehydration-proof
               checklist before Phase 4/remediation may continue
    3 accept-partial -> SET PROMPT_REVIEW_PARTIAL_ACCEPTED = true; render prompt-review output with explicit incomplete-coverage warning; then allow remediation handoff only for findings backed by covered evidence
    4 stop -> Stop at the checkpoint
  INVALID:
    EMIT "Reply `1`, `2`, `3`, or `4`."
    WAIT user.reply
    STOP_TURN
```
