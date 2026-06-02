---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the orchestrator enters the Phase 5 review loop after Phase 4 writes complete (or on external entry from analyze.md Remediation Handoff option 1 after the analyze-side adapter finishes its accepted payload and branch mapping work).
---

# Phase 5 — Review Loop (Dispatcher)

<!-- toc -->

- [Pre-Phase-Setup (MAX_ITER resolution)](#pre-phase-setup-maxiter-resolution)
  - [Review-Loop Iteration Cap Prompt](#review-loop-iteration-cap-prompt)
- [Dispatcher](#dispatcher)

<!-- /toc -->

```pdsl
UNIT Phase5Entry

PURPOSE:
  Enforce entry preconditions and inline-fallback probe before any lazy
  Phase 5 branch work begins.

DO:
  - REQUIRE one of:
    - internal generate path with Phase 4 writes/updates complete
    - external entry from analyze→generate remediation handoff option 1 with
      analyze-side accepted payload predicates, payload shaping, and branch
      mapping already resolved
  - REQUIRE internal generate path:
    - NEVER loading any Phase 5 branch file before Phase 4 write completion
  - REQUIRE external-entry from analyze→generate (option 1):
    TREAT analyze-side remediation adapter checks as eager/nondeferrable
    - REQUIRE accepted external-entry payload already mapped onto the Phase 5
      contract before this file proceeds
    - NEVER re-run adapter acceptance checks or branch mapping inside the
      Phase 5 lazy loop body
    CANONICAL external-entry definitions:
      - "analyze-side accepted payload predicates" are the nondeferrable
        adapter checks that prove the payload has source analyze run id,
        target_paths, all_findings, deterministic validation result or skip
        evidence, semantic report blocks when available, MAX_ITER, files_changed
        state, and explicit remediation handoff option 1 selection.
      - "payload shaping" transforms the analyze output into
        Phase5ExternalEntryPayload:
          {source_workflow:"analyze", source_run_id, target_paths,
           all_findings, remaining_findings, files_changed,
           validation_result, validator_evidence, semantic_reports,
           max_iter, entry_branch}.
        remaining_findings ALWAYS equal all_findings on MAX_ITER=0 entry unless
        the analyze adapter supplies a validated narrower remediation set.
      - "branch mapping" sets entry_branch by deterministic algorithm:
        MAX_ITER == 0 -> phase-5.3-findings;
        validation_result == "FAIL" -> phase-5.1-deterministic;
        otherwise -> phase-5.2-semantic.
      - Adapter acceptance checks that are nondeferrable: schema validation,
        target path normalization, finding id stability, validation_result
        terminal-or-explicitly-skipped status, MAX_ITER resolution, and branch
        mapping. Phase 5 consumes only the validated, shaped, mapped payload.

RULES:
  - ALWAYS REQUIRE `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md` loaded before any cf-* sub-agent
    dispatch in this phase or its sub-files
  - ALWAYS Pre-dispatch fail-stop and Mode B degradation rules defined in
    {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md
  - ALWAYS Late-phase instructions in this phase and its sub-files come from
    controller-supplied prompt_context_view slices; NEVER reopen prompt
    assets from disk
  - ALWAYS After entry, the Phase 5 loop body stays lazy: phase-5.* branch files load
    only when the dispatcher branch below requires them
```

## Pre-Phase-Setup (MAX_ITER resolution)

```pdsl
UNIT Phase5PreSetup

PURPOSE:
  Resolve MAX_ITER and set INLINE_LOOP_WARNING_THRESHOLD before review work begins.

STATE:
  - SET MAX_ITER: integer
    default: 5
    scope: phase_run
  - SET INLINE_LOOP_WARNING_THRESHOLD: 2
    constant

DO:
  - REQUIRE entering Phase 5 from internal generate path:
    - EMIT "Each review iteration validates and reviews written files, auto-fixes mechanical issues, asks you to approve non-mechanical findings, then re-validates."
    - EMIT_MENU MaxIterMenu
    - WAIT user.reply
    - STOP_TURN
    PARSE reply:
      bare positive integer -> SET MAX_ITER = number
      enter -> SET MAX_ITER = 5
      0 -> SET MAX_ITER = 0 (selects zero-iteration branch)
      otherwise ->
        - EMIT_MENU MaxIterMenu
        - WAIT user.reply
        - STOP_TURN

  - REQUIRE entering Phase 5 from external entry (analyze→generate via
     workflows/analyze/phase-4-output/remediation-handoff.md option 1):
    USE MAX_ITER value set by analyze-side handoff; treat as resolved
    SKIP PARSE
    NOTE: re-prompting MAX_ITER here is forbidden; canonical prompt is owned by
          workflows/analyze/phase-4-output/remediation-handoff.md option 1
          next-turn routing step (b); it ALWAYS wait for user reply before
          handing off here

RULES:
  - NEVER re-prompt MAX_ITER on analyze-side remediation handoff option 1 entry;
    on external-entry, MAX_ITER is already set by the analyze-side handoff and
    the PARSE block ALWAYS be skipped entirely
  - ALWAYS MAX_ITER ALWAYS be an integer >= 0; negative values, decimals, ranges, and
    non-numeric text are invalid and ALWAYS re-prompt without selecting a default

MENU MaxIterMenu:
  TITLE: Automatic review iterations
  OPTIONS:
    1 default 5 -> SET MAX_ITER = 5
    2 custom N -> SET MAX_ITER = N when N is a non-negative integer
    3 skip loop -> SET MAX_ITER = 0
  INVALID:
    EMIT "Reply with 1 for default 5, 2: <non-negative integer>, or 3 to skip."
    WAIT user.reply
    STOP_TURN
```

### Review-Loop Iteration Cap Prompt

```pdsl
UNIT Phase5IterationCapPrompt

PURPOSE:
  Reusable sub-block emitted by every Phase 5 iteration-end branch when N > MAX_ITER.

DO:
  - EMIT "Iteration {N} complete; MAX_ITER={MAX_ITER}. Choose whether to extend the loop, accept the current state, or stop for handoff."
  - EMIT_MENU IterationCapMenu
  - WAIT user.reply
  - STOP_TURN

MENU IterationCapMenu:
  TITLE: Iteration cap
  OPTIONS:
    1 extend: M (run more iterations; M must be > current MAX_ITER) ->
      SET MAX_ITER = M
      CONTINUE iteration loop
    2 accept current state ->
      SET loop_exit = "max-iter-stopped"
      SET remaining_findings = carry_forward
      CONTINUE {cf-studio-path}/.core/workflows/generate/phase-5/phase-5.5-final.md
    3 stop for handoff ->
      SET loop_exit = "manual-handoff"
      SET remaining_findings = carry_forward
      CONTINUE {cf-studio-path}/.core/workflows/generate/phase-6/index.md
  INVALID:
    EMIT "Reply with 1: <M> where M is greater than current MAX_ITER, 2 to accept, or 3 to stop."
    WAIT user.reply
    STOP_TURN

RULES:
  - ALWAYS use same wording at every emission site (canonical wording defined here)
  - NEVER change MAX_ITER until valid extend: M value is provided
  - ALWAYS workflows/generate/phase-5/phase-5.3-findings.md § External entry reuses
    this sub-block to resolve MAX_ITER at handoff time
```

## Dispatcher

```pdsl
UNIT Phase5Dispatcher

PURPOSE:
  Initialize Phase 5 state and run the bounded review loop or zero-iteration paths.

STATE:
  - SET N: integer
    default: 1 (canonical; applies both on normal path and external entry)
  - SET carry_forward: list
    default: []
  - SET phase5_dispatch_evidence: list
    default: []

DO:
  - SET N = 1
  - SET carry_forward = []
  - SET phase5_dispatch_evidence = []

  - REQUIRE external-entry from analyze→generate (option 1):
    - REQUIRE Phase 5 state includes:
      handoff_guard.inline_fallback_reprobed = true
      handoff_guard.max_iter_resolved = true
      handoff_guard.dispatch_evidence_required = true
    IF MAX_ITER > 0:
      ALWAYS enter Phase 5.3 first with carried analyze findings; those findings
      were already produced by analyze-side deterministic and semantic review.
      - NEVER run Phase 5.1 or Phase 5.2 before the first author dispatch on
      external entry merely to refresh already-reviewed findings.
    NOTE: When MAX_ITER > 0 AND INLINE_FALLBACK=false, phase5_dispatch_evidence
      ALWAYS contain: author dispatch record before the first file edit; validator
      dispatch record per post-author iteration; semantic reviewer dispatch
      record per post-author iteration when reaching Phase 5.2. Each record =
      compact object with iteration, phase, agent_id, target_paths,
      result_marker or equivalent dispatch-return proof; missing required
      evidence = protocol violation: STOP before editing files
    NOTE: When MAX_ITER == 0 AND external-entry, phase-5.3-findings.md sets
      remaining_findings = all_findings and routes to phase-6/index.md with
      the mandatory remediation-handoff.md menu; no validator or reviewer
      dispatch evidence is required.

  - REQUIRE MAX_ITER == 0 AND internal generate flow:
    - RUN one deterministic validator pass through phase-5.1-det-gate.md
    IF gate PASS or validator-backed SKIPPED:
      - RUN one semantic-reviewer pass through phase-5.2-semantic.md
    IF gate FAIL:
      SKIP semantic review as phase-5.1 requires
      SURFACE validator findings directly
    HAND findings to phase-5.3-findings.md WITH MAX_ITER == 0 branch
      (renders findings, routes to phase-6 without partition/auto-fix logic)

  - REQUIRE MAX_ITER >= 1:
    - RUN bounded review loop:
      FIRST external-entry iteration from analyze→generate:
        - LOAD phase-5.3-findings.md directly with carried analyze findings
        - LOAD phase-5.4-approval.md when judgmental is non-empty
        EXECUTE author dispatch when approved or all-mechanical fast-path applies
        INCREMENT N after author dispatch
      EACH post-author iteration:
        - LOAD phase-5.1-det-gate.md
        ON det PASS or SKIPPED: LOAD phase-5.2-semantic.md
        - LOAD phase-5.3-findings.md
        IF judgmental non-empty: LOAD phase-5.4-approval.md
        INCREMENT N after every author dispatch
        APPEND author-returned findings_not_fixable to carry_forward
          (open, load, and follow {cf-studio-path}/.core/workflows/generate/phase-5/phase-5.4-approval.md § Session-level carry-forward)
        IF N > MAX_ITER: EMIT_MENU IterationCapPrompt
      TERMINATE when:
        no findings remain (loop_exit = "clean"), OR
        user stops it (loop_exit = "manual-handoff"), OR
        MAX_ITER reached (loop_exit = "max-iter-stopped")
    - LOAD phase-5.5-final.md

RULES:
  - ALWAYS Iteration cap check N > MAX_ITER fires AFTER an iteration completes
  - ALWAYS MAX_ITER=5 allows iterations 1..5 to run, then prompts user
  - ALWAYS Cap enforced uniformly via Phase5IterationCapPrompt (same wording everywhere)
  - ALWAYS Cap check applies when MAX_ITER >= 1; MAX_ITER=0 branches bypass cap check
  - NEVER substitute own checklist walkthrough for deterministic validator
    (anti-pattern: SIMULATED_VALIDATION)
  - ALWAYS The dispatched sub-agents execute the actual resolved validator command
    from the target bootstrap (e.g. cpt in Studio .bootstrap, cfs in
    Constructor Studio adapter)

NOTES:
  Sub-file load conditions (lazy; load only by matched branch):
    phase-5.1-det-gate.md: post-author iterations begin; dispatch deterministic validator
    phase-5.2-semantic.md: det gate PASS or SKIPPED; dispatch matched semantic reviewer(s)
    phase-5.3-findings.md: external entry displays carried analyze findings first;
      post-author iterations display findings merged across det + semantic
    phase-5.4-approval.md: judgmental is non-empty; user approval required
    phase-5.5-final.md: loop exits; assemble final Validation Results body for phase-6/index.md
```
