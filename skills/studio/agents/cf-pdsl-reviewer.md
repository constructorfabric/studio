---
description: Invoke when cf-pdsl runs in review mode to inspect prompt/workflow/skill files for PDSL correctness, compactness, and behavioral safety.
---

# PDSL Reviewer

## Dispatch Generator Contract

This file is a controller-side prompt generator source, not a runtime prompt for the dispatched sub-agent.

The controller uses this file to synthesize the final dispatch prompt for
the agent. The final prompt includes the task statement, frozen input
payload, task-relevant instruction assets resolved from `SHARED_CONTEXT_PACK`,
allowed resource context, output contract, completion gate, and the explicit
rule that the dispatched sub-agent executes only that final prompt.
The final prompt also requires the reviewer to flag PDSL instruction blocks
fenced as `text`; they are fenced as `pdsl`.
The final prompt also requires the reviewer to validate PDSL structure:
`STATE`, `WHEN`, `DO`, `RULES`, and `INVARIANTS` are list blocks, and each
top-level list item starts with the starter keywords allowed by
`architecture/specs/PDSL.md`:

- `STATE`: `SET`
- `WHEN`: `REQUIRE`, `AND`, `OR`, `NOT`
- `DO`: `SET`, `LOAD`, `RUN`, `EMIT`, `EMIT_MENU`, `WAIT`, `STOP_TURN`,
  `CONTINUE`, `DISPATCH`, `RETURN`, `REQUIRE`, `NEVER`
- `RULES` and `INVARIANTS`: `ALWAYS`, `NEVER`
- `OPTIONS`: a decimal number such as `1`, `2`, `3`

The dispatched sub-agent does not open prompt assets from disk and does not
rediscover workflows, requirements, specs, AGENTS, SKILL, or kit prompt files.


## Output

Emit `Validation Report - PDSL` with sections in this order:

1. Summary
2. Files Reviewed
3. Findings
4. Compactness Opportunities
5. Residual Risks
6. Recommended Fixes

Then emit:

```json
{
  "type": "VALIDATION_REPORT",
  "status": "PASS|FAIL|PARTIAL",
  "reviewer": "pdsl",
  "findings": [
    {
      "id": "pcd-001",
      "path": "<path>",
      "line": 1,
      "severity": "critical|high|medium|low",
      "category": "state|menu|stop-turn|hidden-rule|error-handling|authority|compactness|handoff|keyword-registry",
      "evidence": "<quote or summary>",
      "impact": "<why it matters>",
      "suggested_fix": "<specific fix>"
    }
  ],
  "unread_paths": [],
  "residual_risk": "<1-3 sentences>"
}
```

## Response Completion Gate

```pdsl
UNIT PdslReviewerCompletion

RULES:
  - ALWAYS account for every target path
  - ALWAYS include the six report sections
  - ALWAYS include findings JSON
  - ALWAYS flag unknown PDSL line/action keywords and classify each as
    spec-extension candidate, normalization candidate, or scanner noise
  - ALWAYS flag structured section items that are not list items or do not start
    with the section's allowed starter keyword
  - ALWAYS flag menu options whose top-level choice does not start with a
    decimal number
  - NEVER claim PASS for unread files
```
