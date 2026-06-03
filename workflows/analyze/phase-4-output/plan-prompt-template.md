---
name: analyze-plan-prompt-template
description: "Invoke when the user selects analyze remediation option 3 to generate the on-demand Plan Prompt Template."
purpose: On-demand Plan Prompt Template for analyze remediation option 3
loaded_by: workflows/analyze/phase-4-output/remediation-handoff.md
version: 1.0
---

```pdsl
UNIT AnalyzePlanPromptTemplate

PURPOSE:
  Emit the self-contained Plan Prompt when the user selects remediation option 3.

DO:
  - EMIT plan prompt:
      Invoke skill `cf`.

      Invoke skill `cf-plan`.

      I need a phased remediation plan for `{PATH}` ({KIND}).

      Analysis status: {PASS|FAIL|PARTIAL}
      Deterministic gate: {exit code, errors, warnings — or "skipped"}

      Issues to remediate (source of truth — do not re-discover):
      {numbered full issue list with severity, file, line, evidence, root cause}

      Create a phased plan to fix root causes, update tests/validation, and verify each phase.
      Do not ask me to restate the task unless required inputs are missing.

RULES:
  - ALWAYS emit as the FINAL section of the response
  - ALWAYS start with "Invoke skill `cf`"
  - ALWAYS be self-contained: include PATH, KIND, status, and full numbered issue list
  - ALWAYS embed all findings with severity, file, line, evidence, root cause
  - NEVER omit any actionable finding
```
