---
name: analyze-fix-prompt-template
description: "Invoke when the user selects analyze remediation option 2 to generate the on-demand Fix Prompt Template."
purpose: On-demand Fix Prompt Template for analyze remediation option 2
loaded_by: workflows/analyze/phase-4-output/remediation-handoff.md
version: 1.0
---

```text
Invoke skill `cf`.

I need a bounded fix via `/cf-generate` for `{PATH}` ({KIND}).

Analysis status: {PASS|FAIL|PARTIAL}
Deterministic gate: {exit code, errors, warnings — or "skipped"}

Issues to fix (source of truth — do not re-discover):
{numbered full issue list with severity, file, line, evidence, root cause}

Fix root causes, update tests/validation where needed, and report results.
Do not ask me to restate the task unless required inputs are missing.
```
