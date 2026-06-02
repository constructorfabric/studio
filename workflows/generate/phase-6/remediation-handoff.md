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

```pdsl
UNIT RemediationHandoff

PURPOSE:
  Emit terminal Remediation Handoff menu when remaining_findings is non-empty.

WHEN:
  - REQUIRE remaining_findings is non-empty
  - REQUIRE (manual-handoff | user-accepted with remaining | MAX_ITER=0 surfacing all findings |
   RELAXED Deterministic gate: FAIL)

DO:
  - EMIT "Remaining findings: High {h} / Medium {m} / Low {l}. Suggested: {R1|R2|R3} because {scope/risk reason}. Do not combine remediation and review choices; the W* review menu unlocks only after remediation clears."
  - EMIT_MENU RemediationHandoffMenu
  - WAIT user.reply (next turn)

MENU RemediationHandoffMenu:
  TITLE: Remediation choice (next-turn reply)
  OPTIONS:
    1 R1 continue here in fix mode ->
      ENTER phase-5/index.md § Dispatcher in fix mode
        (iteration 1 begins at phase-5.1-det-gate.md)
      ALWAYS: (a) emit canonical MAX_ITER resolution prompt from
        phase-5/index.md § Pre-Phase-Setup and wait for reply;
        (b) initialize Phase 5 state:
          all_findings = remaining_findings
          manifest.paths_written = unchanged from written/analyzed paths
          target_paths = manifest.paths_written
            (prefer external_target_paths when manifest.paths_written is empty)
          carry_forward = [];
        (c) execute full Phase 5 review-fix loop — each iteration ALWAYS dispatch
          cf-deterministic-validator (Phase 5.1) and matched semantic reviewer
          set (Phase 5.2) on target_paths BEFORE author dispatch
          (subject to INLINE_FALLBACK per inline-fallback-probe.md)
      NEVER shortcut loop with inline review, inline fix, or single-pass summary
      Loop iterates until clean or MAX_ITER hit
      NOTE: no prompt block emitted
    2 R2 generate fix prompt ->
      EMIT Fix Prompt template from prompt-template-fix.md
        as FINAL section, filled with analyzed paths, kind, validation results,
        and full inline list of remaining_findings
    3 R3 generate plan prompt ->
      EMIT Plan Prompt template from prompt-template-plan.md
        as FINAL section, filled the same way

  4 combined R+W reply (any form: R1+W2, R2,W3, W2 R1, etc.) ->
    EMIT "Combined R+W replies are not supported because each R* may change remaining_findings and Validation Results. Reply with 1 for R1, 2 for R2, or 3 for R3; the W* review menu appears after remediation clears."
    WAIT user.reply
    STOP_TURN

  5 multiple R choices (R1,R2 or R2,R3) ->
    EMIT one-line clarifier shape asking for single choice from that menu
    WAIT user.reply
    STOP_TURN

  6 multiple W choices while remediation pending ->
    EMIT one-line clarifier shape asking for single choice from that menu
    WAIT user.reply
    STOP_TURN

  7 W-only reply while remediation pending ->
    REFUSE with clarifying prompt
    WAIT user.reply
    STOP_TURN
  INVALID:
    EMIT "Reply with 1 for R1, 2 for R2, or 3 for R3."
    WAIT user.reply
    STOP_TURN

RULES:
  - NEVER emit post-write-handoff.md while remediation is pending
  - ALWAYS refuse combined R+W replies with the verbatim one-line clarifier
  - ALWAYS W-only replies are refused while remediation is pending
  - ALWAYS refuse W-only replies while remediation pending
  - ALWAYS refuse multiple-choice replies within one menu with one-line clarifier
```
