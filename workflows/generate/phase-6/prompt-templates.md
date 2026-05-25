---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the user picked `R2`/`R3`/`W2`/`W3` and the corresponding emission template (Fix / Plan / Direct Review / Plan Review Prompt) must be rendered as the FINAL section.
---

<!-- toc -->

- [Emission targets (templates — emitted on demand only)](#emission-targets-templates--emitted-on-demand-only)

<!-- /toc -->

### Emission targets (templates — emitted on demand only)

These templates are NOT emitted unconditionally. They are emitted only when the user picks `R2`/`R3` (Remediation Handoff) or `W2`/`W3` (Post-Write Review Handoff) in their next turn. Each, when emitted, MUST be a **self-contained final prompt** usable in a fresh chat without any prior context:

- explicitly begin with the phrase `Invoke skill cf`
- embed inline: changed file paths, what was changed per file (brief summary), kind/target, and the completed `Validation Results` body with actual values; for `R2`/`R3` also embed the full `remaining_findings` list
- verify before emitting that the `Validation Results` body is present and complete; if not, stop with the Phase 6 prerequisite error instead of generating a partial prompt
- do NOT reference "previous chat", "findings above", or any content outside the prompt itself
- MUST NOT ask the next agent to regenerate or re-implement the changes (W*) or re-discover the findings (R*)

| User pick | Template sub-file |
|---|---|
| `W3` (Plan Review Prompt) | `prompt-template-plan-review.md` |
| `W2` (Direct Review Prompt) | `prompt-template-direct-review.md` |
| `R2` (Fix Prompt) | `prompt-template-fix.md` |
| `R3` (Plan Prompt) | `prompt-template-plan.md` |

<!--
I18 re-evaluation outcome (plan phase 5): KEEP SEPARATE.

Diff `prompt-template-plan-review.md` vs `prompt-template-direct-review.md` shows 7 line-level
differences (frontmatter description; section heading; opening prompt heading; lead-in sentence;
routing instruction; report-focus / focus-and-output instruction; closing instruction) — well above
the 3-line collapse threshold. The differences are load-bearing:

  * `W3` template routes the next agent to `/cf-plan` (PHASED review plan) and asks for
    review coverage + risk hotspots + a follow-up first-phase execution prompt.
  * `W2` template routes the next agent to `/cf-analyze` (IMMEDIATE review) and asks
    for findings with severity, evidence, risks, regressions, and recommended fixes.

Collapsing the two into a single template guarded by a `routing_kind` switch would require five
inline conditionals, defeating the "self-contained final prompt — usable in a fresh chat without
any prior context" rule above. Keep separate; do NOT collapse. Open, load, and follow `prompt-template-plan-review.md`
and `prompt-template-direct-review.md` headers for the same rationale.
-->

Finding I18 (DRY: Plan-Review vs Direct-Review templates) — re-evaluated in plan phase 5: **KEEP SEPARATE**. See the comment block above for the diff summary and rationale. Both `prompt-template-plan-review.md` and `prompt-template-direct-review.md` carry header comments restating the same decision so future readers do not re-open the question.
