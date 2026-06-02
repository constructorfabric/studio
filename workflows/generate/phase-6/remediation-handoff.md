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
  - EMIT verbatim (filled with actual counts) as terminal actionable reply menu:
- RUN ---
- RUN Remaining findings: High {h} / Medium {m} / Low {l}. How do you want to address them?

- RUN R1. Continue here in fix mode — Invoke skill `cf-generate` with mode=fix in this session on the remaining findings
- RUN R2. Generate a Fix Prompt — emit a self-contained prompt for direct fix via Invoke skill `cf-generate` in a new chat
- RUN R3. Generate a Plan Prompt — emit a self-contained prompt for phased remediation via Invoke skill `cf-plan` in a new chat

- RUN Suggested: {R1|R2|R3} because {scope/risk reason}.

- RUN Reply with exactly one remediation choice: `R1`, `R2`, or `R3`.
- RUN Do not combine remediation and review choices. The `W*` review menu unlocks only after remediation clears.
- RUN ---
  - WAIT user.reply (next turn)

MENU RemediationHandoffMenu:
  TITLE: Remediation choice (next-turn reply)
  OPTIONS:
    1 R1 ->
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
    R2 ->
      EMIT Fix Prompt template from prompt-template-fix.md
        as FINAL section, filled with analyzed paths, kind, validation results,
        and full inline list of remaining_findings
    R3 ->
      EMIT Plan Prompt template from prompt-template-plan.md
        as FINAL section, filled the same way

  4 combined R+W reply (any form: R1+W2, R2,W3, W2 R1, etc.) ->
    EMIT exactly:
---
Combined R+W replies are not supported (since each `R*` may change `remaining_findings` and `Validation Results` that the `W*` template would embed). Reply with just one of `R1`, `R2`, `R3` now; the Post-Write Review Handoff menu will be emitted after remediation clears so you can pick `W1` / `W2` / `W3` then.
---
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

RULES:
  - NEVER emit post-write-handoff.md while remediation is pending
  - ALWAYS refuse combined R+W replies with the verbatim one-line clarifier
  - ALWAYS W-only replies are refused while remediation is pending
  - ALWAYS refuse W-only replies while remediation pending
  - ALWAYS refuse multiple-choice replies within one menu with one-line clarifier
```
