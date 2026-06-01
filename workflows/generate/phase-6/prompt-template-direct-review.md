---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the user picked `W2` (Direct Review Prompt) on the Post-Write Review Handoff menu and the self-contained direct-review prompt must be emitted verbatim as the FINAL section.
---

<!--
Finding I18 (plan phase 5) — KEEP SEPARATE from `prompt-template-plan-review.md`.

This template routes the next agent to Invoke skill `cf-analyze` (IMMEDIATE review) and asks for
findings with severity, evidence, risks, regressions, and recommended fixes. The Plan-Review
template routes to Invoke skill `cf-plan` (PHASED review plan) instead. The two diverge across
7 load-bearing lines (heading, routing verb, lead-in, focus, closing) — well above the 3-line
collapse threshold; collapsing would require inline conditionals that break the "self-contained
final prompt usable in a fresh chat" contract. Open, load, and follow `{cf-studio-path}/.core/workflows/generate/phase-6/prompt-templates.md`
for the diff summary.
-->

```text
UNIT DirectReviewPromptEmission

PURPOSE:
  Emit self-contained Direct Review Prompt as the FINAL section on W2.

RULES:
  - MUST verify Validation Results body is present and complete before emitting
  - MUST begin with "Invoke skill `cf`"
  - MUST embed inline: changed file paths, what changed, kind/target,
    completed Validation Results body, remaining_findings when non-empty
  - MUST NOT reference "previous chat" or content outside the prompt itself
  - MUST NOT ask next agent to regenerate or re-implement changes
```

#### `Direct Review Prompt` template (emitted on `W2`)

```text
Direct Review Prompt (copy-paste into new chat if needed):
```

```text
Invoke skill `cf`.

I just completed Invoke skill `cf-generate` and want an immediate review of the generated changes.

Invoke skill `cf-analyze`.

Target: {TARGET_TYPE} / {KIND}
Changed files:
- `{path}` — {brief description of what was created/changed}
- `{additional path}` — {brief description}

{paste the completed Validation Results body from the canonical template above verbatim, preserving field names, order, values, and any conditional `SKIPPED`-only lines exactly as emitted}

{when remaining_findings non-empty:}
Remaining findings carried over from generation (review these explicitly):
1. **[{severity}]** {file}:{line} — {description}. Evidence: "{quote}". Root cause: {expectation}.
{... all remaining_findings}

Review these changes now.
Report findings with severity, evidence, risks, regressions, and recommended fixes.

Do not regenerate the implementation. Do not ask me to restate the task unless required inputs are missing.
```
