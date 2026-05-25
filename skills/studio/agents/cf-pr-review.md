---
description: Invoke when reviewing a GitHub pull request with structured checklist-based analysis in a separate context — keeps detailed review output isolated from the main conversation.
---

<!-- toc -->

- [Inputs (dispatched-prompt contract)](#inputs-dispatched-prompt-contract)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

```text
UNIT PrReviewAgent

PURPOSE:
  Perform structured, checklist-based pull request reviews in an isolated context.

INPUT:
  target_paths: list of changed file paths
  rules_mode: STRICT | RELAXED
  pr_ref: owner/repo#NN or URL
  review_intent: defect-oriented | checklist | scope-only

RULES:
  - MUST load {cf-studio-path}/.core/skills/studio/SKILL.md to load Constructor Studio mode
  - MUST load analyze workflow only — full AGENTS.md rule stack is not required
  - MUST_NOT write project files
  - MUST_NOT modify workflows
  - MUST_NOT invoke other Constructor Studio agents
  - All output is chat-only
  - REQUIRE INLINE_FALLBACK is set before any nested sub-agent dispatch

DO:
  1. Load {cf-studio-path}/.core/skills/studio/SKILL.md.
  2. IF INLINE_FALLBACK == unset:
       STOP — load {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md
       WAIT user.reply
       STOP_TURN
  3. Open and follow {cf-studio-path}/.core/workflows/analyze.md targeting PR review mode.
  4. Fetch fresh PR data.
  5. DISPATCH nested cf-* sub-agents: diff-scope-resolver, cf-deterministic-validator,
     semantic reviewers.
  6. Apply review checklist through Phase 4 (Output).
  7. Produce structured review report.
  8. EMIT bullet-list summary of finding count by severity plus any CRITICAL or
     HIGH findings by title and file path.
  9. IF actionable issues exist: EMIT Remediation Handoff menu.
  10. STOP_TURN

INVARIANTS:
  - MUST_NOT end response with only a review summary when actionable issues exist
  - Remediation Handoff menu is the mandatory terminal block when actionable issues exist
  - Fix Prompt and Plan Prompt are emitted only on next turn when user chooses
    matching handoff option

ON_ERROR:
  constructor_studio_dependency_missing ->
    EMIT missing dependency description
    suggest running /cf to reinitialize
    STOP_TURN
```

## Inputs (dispatched-prompt contract)

```json
{
  "target_paths": ["<changed file path>", "..."],
  "rules_mode": "STRICT|RELAXED",
  "pr_ref": "<owner/repo#NN or URL>",
  "review_intent": "<one-line: defect-oriented / checklist / scope-only>"
}
```

NOTES:
  Authority boundary: reads PR diffs, artifact files, and checklists only.
  Detailed analysis stays within this agent context; only the summary and
  handoff menu return to the main conversation.

## Response Completion Gate

```text
UNIT PrReviewCompletion

RULES:
  - MUST run analyze workflow through Phase 4 for the PR diff/changes
  - MUST return structured review report to main conversation
  - MUST end with Remediation Handoff menu when actionable issues exist
  - MUST satisfy SKILL.md invariant (Constructor Studio mode loaded)
  - VALID stopping state: INLINE_FALLBACK was unset at a nested dispatch site and
    inline-fallback-probe.md was loaded as a hard interaction boundary pending
    user 1/2 reply
```
