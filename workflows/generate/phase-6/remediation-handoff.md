---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when `remaining_findings` from Phase 5 is non-empty and the conditional Remediation Handoff menu must be emitted as the terminal actionable menu.
---

<!-- toc -->

- [Remediation Handoff (conditional — only when `remaining_findings` non-empty)](#remediation-handoff-conditional--only-when-remainingfindings-non-empty)

<!-- /toc -->

### Remediation Handoff (conditional — only when `remaining_findings` non-empty)

```text
UNIT RemediationHandoff

PURPOSE:
  Emit terminal Remediation Handoff menu when remaining_findings is non-empty.

WHEN:
  remaining_findings is non-empty
  (manual-handoff | user-accepted with remaining | MAX_ITER=0 surfacing all findings |
   RELAXED Deterministic gate: FAIL)

DO:
  EMIT verbatim (filled with actual counts) as terminal actionable reply menu:
---
Remaining findings: High {h} / Medium {m} / Low {l}. How do you want to address them?

R1. Continue here in fix mode — invoke `/cf-generate(mode=fix)` in this session on the remaining findings
R2. Generate a Fix Prompt — emit a self-contained prompt for direct fix via `/cf-generate` in a new chat
R3. Generate a Plan Prompt — emit a self-contained prompt for phased remediation via `/cf-plan` in a new chat

Suggested: {R1|R2|R3} because {scope/risk reason}.

Reply with exactly one remediation choice: `R1`, `R2`, or `R3`.
Do not combine remediation and review choices. The `W*` review menu unlocks only after remediation clears.
---
  WAIT user.reply (next turn)

MENU RemediationHandoffMenu:
  TITLE: Remediation choice (next-turn reply)
  OPTIONS:
    R1 ->
      ENTER phase-5/index.md § Dispatcher in fix mode
        (iteration 1 begins at phase-5.1-det-gate.md)
      MUST: (a) emit canonical MAX_ITER resolution prompt from
        phase-5/index.md § Pre-Phase-Setup and wait for reply;
        (b) initialize Phase 5 state:
          all_findings = remaining_findings
          manifest.paths_written = unchanged from written/analyzed paths
          target_paths = manifest.paths_written
            (prefer external_target_paths when manifest.paths_written is empty)
          carry_forward = [];
        (c) execute full Phase 5 review-fix loop — each iteration MUST dispatch
          cf-deterministic-validator (Phase 5.1) and matched semantic reviewer
          set (Phase 5.2) on target_paths BEFORE author dispatch
          (subject to INLINE_FALLBACK per inline-fallback-probe.md)
      MUST NOT shortcut loop with inline review, inline fix, or single-pass summary
      Loop iterates until clean or MAX_ITER hit
      NOTE: no prompt block emitted
    R2 ->
      EMIT Fix Prompt template from prompt-template-fix.md
        as FINAL section, filled with analyzed paths, kind, validation results,
        and full inline list of remaining_findings
    R3 ->
      EMIT Plan Prompt template from prompt-template-plan.md
        as FINAL section, filled the same way

  combined R+W reply (any form: R1+W2, R2,W3, W2 R1, etc.) ->
    EMIT exactly:
---
Combined R+W replies are not supported (since each `R*` may change `remaining_findings` and `Validation Results` that the `W*` template would embed). Reply with just one of `R1`, `R2`, `R3` now; the Post-Write Review Handoff menu will be emitted after remediation clears so you can pick `W1` / `W2` / `W3` then.
---
    WAIT user.reply
    STOP_TURN

  multiple R choices (R1,R2 or R2,R3) ->
    EMIT one-line clarifier shape asking for single choice from that menu
    WAIT user.reply
    STOP_TURN

  multiple W choices while remediation pending ->
    EMIT one-line clarifier shape asking for single choice from that menu
    WAIT user.reply
    STOP_TURN

  W-only reply while remediation pending ->
    REFUSE with clarifying prompt
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST NOT emit post-write-handoff.md while remediation is pending
  - MUST refuse combined R+W replies with the verbatim one-line clarifier
  - MUST refuse W-only replies while remediation pending
  - MUST refuse multiple-choice replies within one menu with one-line clarifier
```
