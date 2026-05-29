---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the orchestrator enters the Phase 5 review loop after Phase 4 writes files (or on external entry from analyze.md Remediation Handoff option 1).
---

# Phase 5 — Review Loop (Dispatcher)


<!-- toc -->

- [Pre-Phase-Setup (MAX_ITER resolution)](#pre-phase-setup-maxiter-resolution)
  - [Review-Loop Iteration Cap Prompt](#review-loop-iteration-cap-prompt)
- [Dispatcher](#dispatcher)

<!-- /toc -->

```text
UNIT Phase5Entry

PURPOSE:
  Enforce entry preconditions and inline-fallback probe before any Phase 5 work.

RULES:
  - REQUIRE `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md` loaded before any cf-* sub-agent
    dispatch in this phase or its sub-files
  - Pre-dispatch fail-stop and Mode B degradation rules defined in
    {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md
```

## Pre-Phase-Setup (MAX_ITER resolution)

```text
UNIT Phase5PreSetup

PURPOSE:
  Resolve MAX_ITER and set INLINE_LOOP_WARNING_THRESHOLD before review work begins.

STATE:
  MAX_ITER: integer
    default: 5
    scope: phase_run
  INLINE_LOOP_WARNING_THRESHOLD: 2
    constant

DO:
  IF entering Phase 5 from internal generate path:
    EMIT exactly:
---
How many automatic review iterations should run before I check in with you?

Each iteration: validate + review the written files → auto-fix mechanical
issues → ask you to approve any non-mechanical findings → re-validate.

Reply with a number (suggested: 5 — balances fix coverage against context cost; use 2 or less in inline mode), `enter` for 5, or `0` to skip the loop.
---
    WAIT user.reply
    STOP_TURN

  IF entering Phase 5 from external entry (analyze→generate via
     workflows/analyze/phase-4-output/remediation-handoff.md option 1):
    MUST NOT re-prompt MAX_ITER here; MAX_ITER already resolved by analyze side
    NOTE: canonical MAX_ITER prompt is owned by
          workflows/analyze/phase-4-output/remediation-handoff.md option 1
          next-turn routing step (b); it MUST wait for user reply before
          handing off here

  PARSE reply:
    bare number -> SET MAX_ITER = number
    enter -> SET MAX_ITER = 5
    0 -> SET MAX_ITER = 0 (selects zero-iteration branch)

RULES:
  - MUST NOT re-prompt MAX_ITER on analyze-side remediation handoff option 1 entry
```

### Review-Loop Iteration Cap Prompt

```text
UNIT Phase5IterationCapPrompt

PURPOSE:
  Reusable sub-block emitted by every Phase 5 iteration-end branch when N > MAX_ITER.

DO:
  EMIT exactly:
---
Iteration {N} complete; you set MAX_ITER={MAX_ITER}. Continue, accept current state, or stop?

`extend: <M>` → raise MAX_ITER to <M> and run another iteration (must be > current MAX_ITER)
`accept`     → exit the loop now; loop_exit = "max-iter-stopped"; remaining_findings = carry_forward (suggested when current findings look acceptable)
`stop`       → exit the loop now; loop_exit = "manual-handoff"; remaining_findings = carry_forward (use when you want to inspect / hand off the remaining findings before any more fixes)

Reply `extend: <M>`, `accept`, or `stop`.
---
  WAIT user.reply
  STOP_TURN

MENU IterationCapMenu:
  TITLE: Iteration cap
  OPTIONS:
    extend: M (M positive integer > current MAX_ITER) ->
      SET MAX_ITER = M
      CONTINUE iteration loop
    extend: M (invalid — M not positive integer or M <= current MAX_ITER) ->
      EMIT "extend: <M> must be a positive integer greater than current MAX_ITER
            ({current_MAX_ITER}); reply again."
      WAIT user.reply
      STOP_TURN
    accept ->
      SET loop_exit = "max-iter-stopped"
      SET remaining_findings = carry_forward
      CONTINUE workflows/generate/phase-5/phase-5.5-final.md
      NOTE: cap prompt accept exits only after post-fix deterministic gate
    stop ->
      SET loop_exit = "manual-handoff"
      SET remaining_findings = carry_forward
      CONTINUE workflows/generate/phase-6/index.md

RULES:
  - MUST use same wording at every emission site (canonical wording defined here)
  - MUST NOT change MAX_ITER until valid extend: M value is provided
  - workflows/generate/phase-5/phase-5.3-findings.md § External entry reuses
    this sub-block to resolve MAX_ITER at handoff time
```

## Dispatcher

```text
UNIT Phase5Dispatcher

PURPOSE:
  Initialize Phase 5 state and run the bounded review loop or zero-iteration paths.

STATE:
  N: integer
    default: 1 (canonical; applies both on normal path and external entry)
  carry_forward: list
    default: []
  phase5_dispatch_evidence: list
    default: []

DO:
  SET N = 1
  SET carry_forward = []
  SET phase5_dispatch_evidence = []

  IF external-entry from analyze→generate (option 1):
    REQUIRE Phase 5 state includes:
      handoff_guard.inline_fallback_reprobed = true
      handoff_guard.max_iter_resolved = true
      handoff_guard.dispatch_evidence_required = true
    IF MAX_ITER > 0:
      MUST run Phase 5.1 then Phase 5.2 before Phase 5.3 so carried findings
      are refreshed against generate-side validator/reviewer contracts before
      any author dispatch
    NOTE: When MAX_ITER > 0 AND INLINE_FALLBACK=false, phase5_dispatch_evidence
      MUST contain: validator dispatch record per iteration, semantic reviewer
      dispatch record per iteration when reaching Phase 5.2, author dispatch
      record before any file edit; each record = compact object with iteration,
      phase, agent_id, target_paths, result_marker or equivalent dispatch-return
      proof; missing evidence = protocol violation: STOP before editing files

  IF MAX_ITER == 0 AND external-entry:
    SKIP fresh Phase 5 validation/review
    CONTINUE phase-5.3-findings.md for external-entry handling
      (renders carried findings, sets remaining_findings = all_findings,
       routes to phase-6/index.md with mandatory remediation-handoff.md menu)

  IF MAX_ITER == 0 AND internal generate flow:
    RUN one deterministic validator pass through phase-5.1-det-gate.md
    IF gate PASS or validator-backed SKIPPED:
      RUN one semantic-reviewer pass through phase-5.2-semantic.md
    IF gate FAIL:
      SKIP semantic review as phase-5.1 requires
      SURFACE validator findings directly
    HAND findings to phase-5.3-findings.md WITH MAX_ITER == 0 branch
      (renders findings, routes to phase-6 without partition/auto-fix logic)

  IF MAX_ITER >= 1:
    RUN bounded review loop:
      EACH iteration:
        LOAD phase-5.1-det-gate.md
        ON det PASS or SKIPPED: LOAD phase-5.2-semantic.md
        LOAD phase-5.3-findings.md
        IF judgmental non-empty: LOAD phase-5.4-approval.md
        INCREMENT N after every author dispatch
        APPEND author-returned findings_not_fixable to carry_forward
          (open, load, and follow {cf-studio-path}/.core/workflows/generate/phase-5/phase-5.4-approval.md § Session-level carry-forward)
        IF N > MAX_ITER: EMIT_MENU IterationCapPrompt
      TERMINATE when:
        no findings remain (loop_exit = "clean"), OR
        user stops it (loop_exit = "manual-handoff"), OR
        MAX_ITER reached (loop_exit = "max-iter-stopped")
    LOAD phase-5.5-final.md

RULES:
  - Iteration cap check N > MAX_ITER fires AFTER an iteration completes
  - MAX_ITER=5 allows iterations 1..5 to run, then prompts user
  - Cap enforced uniformly via Phase5IterationCapPrompt (same wording everywhere)
  - Cap check applies when MAX_ITER >= 1; MAX_ITER=0 branches bypass cap check
  - MUST NOT substitute own checklist walkthrough for deterministic validator
    (anti-pattern: SIMULATED_VALIDATION)
  - The dispatched sub-agents execute the actual resolved validator command
    from the target bootstrap (e.g. cpt in Studio .bootstrap, cfs in
    Constructor Studio adapter)

NOTES:
  Sub-file load conditions:
    phase-5.1-det-gate.md: each iteration begins; dispatch deterministic validator
    phase-5.2-semantic.md: det gate PASS or SKIPPED; dispatch matched semantic reviewer(s)
    phase-5.3-findings.md: findings list (merged across det + semantic) must be displayed
    phase-5.4-approval.md: judgmental is non-empty; user approval required
    phase-5.5-final.md: loop exits; assemble final Validation Results body for phase-6/index.md
```
