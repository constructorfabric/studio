---
description: Invoke when reviewing a GitHub pull request with structured checklist-based analysis in a separate context — keeps detailed review output isolated from the main conversation.
---

<!-- toc -->

- [Inputs (dispatched-prompt contract)](#inputs-dispatched-prompt-contract)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

## Dispatch Guidance

This file is orchestration-time guidance for the controller, not a runtime
self-bootstrap contract for the dispatched sub-agent.

The controller MUST load this file, resolve the task-relevant instruction
assets from `SHARED_CONTEXT_PACK`, and synthesize a fully materialized final
dispatch prompt for this agent. The dispatched sub-agent MUST execute only that
final prompt and MUST NOT open prompt assets from disk directly.


## Inputs (dispatched-prompt contract)

```json
{
  "target_paths": ["<changed file path>", "..."],
  "rules_mode": "STRICT|RELAXED",
  "pr_ref": "<owner/repo#NN or URL>",
  "review_intent": "<one-line: defect-oriented / checklist / scope-only>"
}
```

NOTES:
  Authority boundary: reads PR diffs, artifact files, and checklists only.
  Nested dispatch is limited to analyze-scoped reviewer and validator agents;
  only the summary and handoff menu return to the main conversation.

## Response Completion Gate

```text
UNIT PrReviewCompletion

RULES:
  - MUST run analyze workflow through Phase 4 for the PR diff/changes
  - MUST return structured review report to main conversation
  - MUST end with Remediation Handoff menu when actionable issues exist
  - MUST satisfy the `studio_mode_contract` invariant
  - VALID stopping state: INLINE_FALLBACK was unset at a nested dispatch site and
    `inline_fallback_probe_contract` was followed as a hard interaction
    boundary pending user 1/2 reply
```
