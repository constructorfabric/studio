---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the user picked `R3` (Plan Prompt) on the Remediation Handoff menu and the self-contained phased-remediation prompt must be emitted verbatim as the FINAL section.
---

#### `Plan Prompt` template (emitted on `R3`)

```text
Plan Prompt (copy-paste into new chat if needed):
```

```text
Invoke skill `cf`.

I just completed `/cf-generate` with unresolved findings. I need a phased remediation plan via `/cf-plan` for these files.

Target: {TARGET_TYPE} / {KIND}
Changed files (already written):
- `{path}` — {brief description}
- `{additional path}` — {brief description}

{paste the completed Validation Results body verbatim}

Remaining findings to remediate (source of truth — do not re-discover):
1. **[{severity}]** {file}:{line} — {description}. Evidence: "{quote}". Root cause: {expectation}.
{... all remaining_findings}

Create a phased plan to fix root causes, update tests/validation, and verify each phase.
Do not ask me to restate the task unless required inputs are missing.
```
