---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the user picked `W2` (Direct Review Prompt) on the Post-Write Review Handoff menu and the self-contained direct-review prompt must be emitted verbatim as the FINAL section.
---

<!--
Finding I18 (plan phase 5) — KEEP SEPARATE from `prompt-template-plan-review.md`.

This template routes the next agent to `/cf-analyze` (IMMEDIATE review) and asks for
findings with severity, evidence, risks, regressions, and recommended fixes. The Plan-Review
template routes to `/cf-plan` (PHASED review plan) instead. The two diverge across
7 load-bearing lines (heading, routing verb, lead-in, focus, closing) — well above the 3-line
collapse threshold; collapsing would require inline conditionals that break the "self-contained
final prompt usable in a fresh chat" contract. Open, load, and follow `workflows/generate/phase-6/prompt-templates.md`
for the diff summary.
-->

#### `Direct Review Prompt` template (emitted on `W2`)

```text
Direct Review Prompt (copy-paste into new chat if needed):
```

```text
Invoke skill `cf`.

I just completed `/cf-generate` and want an immediate review of the generated changes.

Target: {TARGET_TYPE} / {KIND}
Changed files:
- `{path}` — {brief description of what was created/changed}
- `{additional path}` — {brief description}

{paste the completed Validation Results body from the canonical template above verbatim, preserving field names, order, values, and any conditional `SKIPPED`-only lines exactly as emitted}

{when remaining_findings non-empty:}
Remaining findings carried over from generation (review these explicitly):
1. **[{severity}]** {file}:{line} — {description}. Evidence: "{quote}". Root cause: {expectation}.
{... all remaining_findings}

Use `/cf-analyze` to review these changes now.
Report findings with severity, evidence, risks, regressions, and recommended fixes.

Do not regenerate the implementation. Do not ask me to restate the task unless required inputs are missing.
```
