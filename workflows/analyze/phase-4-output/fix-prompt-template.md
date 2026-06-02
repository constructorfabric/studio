---
name: analyze-fix-prompt-template
description: "Invoke when the user selects analyze remediation option 2 to generate the on-demand Fix Prompt Template."
purpose: On-demand Fix Prompt Template for analyze remediation option 2
loaded_by: workflows/analyze/phase-4-output/remediation-handoff.md
version: 1.0
---

```pdsl
UNIT AnalyzeFixPromptTemplate

PURPOSE:
  Emit the self-contained Fix Prompt when the user selects remediation option 2.

RULES:
  - MUST emit as the FINAL section of the response
  - MUST start with "Invoke skill `cf`"
  - MUST be self-contained: include PATH, KIND, status, and full numbered issue list
  - MUST embed all findings with severity, file, line, evidence, root cause
  - MUST_NOT omit any actionable finding
```

```text
Invoke skill `cf`.

Invoke skill `cf-generate`.

I need a bounded fix for `{PATH}` ({KIND}).

Analysis status: {PASS|FAIL|PARTIAL}
Deterministic gate: {exit code, errors, warnings — or "skipped"}

Issues to fix (source of truth — do not re-discover):
{numbered full issue list with severity, file, line, evidence, root cause}

Fix root causes, update tests/validation where needed, and report results.
Do not ask me to restate the task unless required inputs are missing.
```
