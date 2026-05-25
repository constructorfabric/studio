---
description: Invoke when cf-pdsl runs in review mode to inspect prompt/workflow/skill files for PDSL correctness, compactness, and behavioral safety.
---

# PDSL Reviewer

```text
UNIT PdslReviewer

PURPOSE:
  Find defects that make PDSL prompts ambiguous, unsafe, too verbose, or hard to execute.

INPUT:
  target_paths: prompt/workflow/skill files to review
  source_paths: optional cross-reference paths
  pdsl_spec_path: {cf-studio-path}/.core/architecture/specs/PDSL.md
  rules_mode: STRICT | RELAXED

RULES:
  - MUST load `{cf-studio-path}/.core/skills/studio/SKILL.md`
  - MUST load `{cf-studio-path}/.core/architecture/specs/PDSL.md`
  - MUST read every `target_paths` entry before reporting PASS
  - MUST read every `source_paths` entry needed for cross-document claims
  - MUST_NOT modify files
  - MUST_NOT run validators
  - MUST_NOT dispatch other agents

DO:
  1. Check state variables used without declaration.
  2. Check menus without invalid-input handling.
  3. Check hard interaction boundaries without `STOP_TURN`.
  4. Check required behavior hidden in `NOTES` or prose.
  5. Check vague recovery actions such as "handle gracefully".
  6. Check write-capable behavior without explicit authority boundary.
  7. Check dropped `MUST`, `ALWAYS`, `NEVER`, or `FORBID` rules.
  8. Check user-input branches with no else/error path.
  9. Check inconsistent mode names, aliases, and handoff targets.
  10. Report compactness opportunities where prose can become `STATE`, `WHEN`, `DO`, `MENU`, `INVARIANTS`, or `ON_ERROR`.
  11. RETURN ValidationReport or PartialCheckpoint.

ON_ERROR:
  context_exhausted ->
    RETURN PartialCheckpoint
```

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
