---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the user picked `R2` (Fix Prompt) on the Remediation Handoff menu and the self-contained bounded-fix prompt must be emitted verbatim as the FINAL section.
---

```text
UNIT FixPromptEmission

PURPOSE:
  Emit self-contained Fix Prompt as the FINAL section on R2.

RULES:
  - MUST verify Validation Results body is present and complete before emitting
  - MUST begin with "Invoke skill `cf`"
  - MUST embed inline: changed file paths, what changed, kind/target,
    completed Validation Results body verbatim, full remaining_findings list
  - MUST NOT reference "previous chat" or content outside the prompt itself
  - MUST NOT ask next agent to re-discover findings
```

#### `Fix Prompt` template (emitted on `R2`)

```text
Fix Prompt (copy-paste into new chat if needed):
```

```text
Invoke skill `cf`.

I just completed Invoke skill `cf-generate` with unresolved findings.

Invoke skill `cf-generate` with mode=fix.

I need a bounded fix for these files.

Target: {TARGET_TYPE} / {KIND}
Changed files (already written):
- `{path}` — {brief description}
- `{additional path}` — {brief description}

{paste the completed Validation Results body verbatim}

Remaining findings to fix (source of truth — do not re-discover):
1. **[{severity}]** {file}:{line} — {description}. Evidence: "{quote}". Root cause: {expectation}.
{... all remaining_findings}

Fix root causes, update tests/validation where needed, and report a final change summary.
Do not ask me to restate the task unless required inputs are missing.
```
