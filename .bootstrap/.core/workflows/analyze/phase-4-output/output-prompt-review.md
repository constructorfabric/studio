---
name: analyze-phase-4-output-prompt-review
description: "Invoke when PROMPT_REVIEW=true to render the Phase 4 Prompt Review output schema merging prompt-engineering and optional prompt-bug-finder sub-agent reports."
purpose: Phase 4 Prompt Review output schema (PROMPT_REVIEW=true) — merges prompt-engineering and optional prompt-bug-finder sub-agent reports
loaded_by: workflows/analyze.md
version: 1.0
---

### Prompt Review Output (PROMPT_REVIEW / PROMPT_BUG_REVIEW)
`PROMPT_REVIEW=true` or `PROMPT_BUG_REVIEW=true` does **not** use the standard analysis template defined in `workflows/analyze/phase-4-output/output-standard.md`. When `PROMPT_REVIEW=true`, render the `cf-semantic-reviewer-prompt` report in the prompt-engineering section order:

1. `Summary`
2. `Context Budget & Evidence`
3. `Compact-Prompts Findings`
4. `Layer Summaries`
5. `Issues Found`
6. `Recommended Fixes`
7. `Verification Checklist`

When `PROMPT_BUG_REVIEW=true`, append the separate `cf-prompt-bug-finder` report after the prompt-engineering report. If `PROMPT_REVIEW=false`, render only the prompt-bug-finder report under this schema. Its `Summary` MUST begin with the prompt-bug-finding status block: `Review status`, `Deterministic gate`, `Scope reviewed`, `Review basis`, `Environment snapshot`, and `Coverage summary`. If the deterministic gate is `SKIPPED`, state why and explicitly state `no validator-backed evidence for this review path`.

Do **not** mark prompt-review checks `N/A` unless the reviewed document explicitly makes them inapplicable. If applicability or hotspot-relevant normative effect remains unresolved, report `FAIL` or `PARTIAL` as required by the active prompt sub-agent methodology.

### Prompt Review Partial Checkpoint

When the prompt reviewer returns `checkpoint.type = "PARTIAL_CHECKPOINT"`,
Phase 4 renders a `Prompt Review Partial Checkpoint` block instead of requiring
the full 10-layer prompt-engineering report. The block MUST include:

- `checkpoint.type = "PARTIAL_CHECKPOINT"`
- reviewed target paths and covered layers
- uncovered layers / resume anchors
- findings backed by already-covered evidence
- the checkpoint JSON needed to resume the prompt review

This is a valid partial output, not a clean pass. Append the Remediation Handoff
menu when the checkpoint or findings require follow-up work.
