---
description: Invoke when cf-pdsl runs in review mode to inspect prompt/workflow/skill files for PDSL correctness, compactness, and behavioral safety.
---

# PDSL Reviewer

## Dispatch Generator Contract

This file is a controller-side prompt generator source, not a runtime prompt for the dispatched sub-agent.

The controller MUST use this file to synthesize the final dispatch prompt for
the agent. The final prompt MUST include the task statement, frozen input
payload, task-relevant instruction assets resolved from `SHARED_CONTEXT_PACK`,
allowed resource context, output contract, completion gate, and the explicit
rule that the dispatched sub-agent executes only that final prompt.

The dispatched sub-agent MUST NOT open prompt assets from disk and MUST NOT
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
      "category": "state|menu|stop-turn|hidden-rule|error-handling|authority|compactness|handoff",
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

```text
UNIT PdslReviewerCompletion

RULES:
  - MUST account for every target path
  - MUST include the six report sections
  - MUST include findings JSON
  - MUST_NOT claim PASS for unread files
```
