---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the user picked `W3` (Plan Review Prompt) on the Post-Write Review Handoff menu and the self-contained plan-review prompt must be emitted verbatim as the FINAL section.
---

<!--
Finding I18 (plan phase 5) — KEEP SEPARATE from `prompt-template-direct-review.md`.

This template routes the next agent to `/cf-plan` (PHASED review plan) and asks for a
follow-up first-phase execution prompt. The Direct Review template routes to `/cf-analyze`
(IMMEDIATE review) instead. The two diverge across 7 load-bearing lines (heading, routing verb,
lead-in, focus, closing) — well above the 3-line collapse threshold; collapsing would require
inline conditionals that break the "self-contained final prompt usable in a fresh chat" contract.
Open, load, and follow `workflows/generate/phase-6/prompt-templates.md` for the diff summary.
-->

#### `Plan Review Prompt` template (emitted on `W3`)

```text
Plan Review Prompt (copy-paste into new chat if needed):
```

```text
Invoke skill `cf`.

I just completed `/cf-generate` and want a phased review plan for the generated changes.

Target: {TARGET_TYPE} / {KIND}
Changed files:
- `{path}` — {brief description of what was created/changed}
- `{additional path}` — {brief description}

{paste the completed Validation Results body from the canonical template above verbatim, preserving field names, order, values, and any conditional `SKIPPED`-only lines exactly as emitted}

{when remaining_findings non-empty:}
Remaining findings carried over from generation (review these explicitly):
1. **[{severity}]** {file}:{line} — {description}. Evidence: "{quote}". Root cause: {expectation}.
{... all remaining_findings}

Use `/cf-plan` to create a phased review plan for these changes.
Focus on review coverage, risk hotspots, and the minimal set of review phases needed for high confidence.
After creating the plan, give me the next execution prompt for the first review phase.

Do not regenerate the implementation. Do not ask me to restate the task unless required inputs are missing.
```
