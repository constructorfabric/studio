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

```text
UNIT Phase6EmissionTargets

PURPOSE:
  Define emission rules for self-contained prompt templates emitted on R2/R3/W2/W3.

RULES:
  - MUST NOT emit these templates unconditionally
  - MUST emit ONLY when user picks R2/R3 (Remediation Handoff) or W2/W3
    (Post-Write Review Handoff) in their next turn
  - Each emitted template MUST be a self-contained final prompt usable in a
    fresh chat without any prior context:
    MUST explicitly begin with the phrase "Invoke skill cf"
    MUST embed inline: changed file paths, what was changed per file (brief summary),
      kind/target, and completed Validation Results body with actual values;
      for R2/R3 also embed full remaining_findings list
    MUST verify before emitting that Validation Results body is present and complete;
      if not: STOP with Phase 6 prerequisite error instead of generating partial prompt
    MUST NOT reference "previous chat", "findings above", or any content outside
      the prompt itself
    MUST NOT ask next agent to regenerate or re-implement changes (W*)
    MUST NOT ask next agent to re-discover findings (R*)

MENU EmissionTargetRouting:
  TITLE: Emission target routing (machine reference)
  OPTIONS:
    W3 (Plan Review Prompt) ->
      LOAD prompt-template-plan-review.md
    W2 (Direct Review Prompt) ->
      LOAD prompt-template-direct-review.md
    R2 (Fix Prompt) ->
      LOAD prompt-template-fix.md
    R3 (Plan Prompt) ->
      LOAD prompt-template-plan.md
```

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
any prior context" rule above. Keep separate; do NOT collapse. Open, load, and follow `{cf-studio-path}/.core/workflows/generate/phase-6/prompt-template-plan-review.md`
and `{cf-studio-path}/.core/workflows/generate/phase-6/prompt-template-direct-review.md` headers for the same rationale.
-->

Finding I18 (DRY: Plan-Review vs Direct-Review templates) — re-evaluated in plan phase 5: **KEEP SEPARATE**. See the comment block above for the diff summary and rationale. Both `{cf-studio-path}/.core/workflows/generate/phase-6/prompt-template-plan-review.md` and `{cf-studio-path}/.core/workflows/generate/phase-6/prompt-template-direct-review.md` carry header comments restating the same decision so future readers do not re-open the question.
