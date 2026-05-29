---
description: Invoke when reviewing a GitHub pull request with structured checklist-based analysis in a separate context — keeps detailed review output isolated from the main conversation.
---

<!-- toc -->

- [Frozen Input Payload](#frozen-input-payload)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

## Dispatch Generator Contract

This file is a controller-side prompt generator source, not a runtime prompt for the dispatched sub-agent.

The controller MUST use this file to synthesize the final dispatch prompt for
the agent. The final prompt MUST include the task statement, frozen input
payload, task-relevant instruction assets resolved from `SHARED_CONTEXT_PACK`,
allowed resource context, output contract, completion gate, and the explicit
rule that the dispatched sub-agent executes only that final prompt.

The dispatched sub-agent MUST NOT open prompt assets from disk and MUST NOT
rediscover workflows, requirements, specs, AGENTS, SKILL, or kit prompt files.


## Frozen Input Payload

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
  - Remediation prompt blocks are emitted only on next turn after the user
    selects the handoff prompt option
  - MUST satisfy the `studio_mode_contract` invariant
  - VALID stopping state: INLINE_FALLBACK was unset at a nested dispatch site and
    `inline_fallback_probe_contract` was followed as a hard interaction
    boundary pending user 1/2 reply
```
