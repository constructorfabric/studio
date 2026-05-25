---
name: analyze-plan-prompt-template
description: "Invoke when the user selects analyze remediation option 3 to generate the on-demand Plan Prompt Template."
purpose: On-demand Plan Prompt Template for analyze remediation option 3
loaded_by: workflows/analyze/phase-4-output/remediation-handoff.md
version: 1.0
---

```text
Invoke skill `cf`.

I need a phased remediation plan via `/cf-plan` for `{PATH}` ({KIND}).

Analysis status: {PASS|FAIL|PARTIAL}
Deterministic gate: {exit code, errors, warnings — or "skipped"}

Issues to remediate (source of truth — do not re-discover):
{numbered full issue list with severity, file, line, evidence, root cause}

Create a phased plan to fix root causes, update tests/validation, and verify each phase.
Do not ask me to restate the task unless required inputs are missing.
```
