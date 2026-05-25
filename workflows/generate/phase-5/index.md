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

Requires: `workflows/shared/inline-fallback-probe.md` before any `cf-*` sub-agent dispatch in this phase or its sub-files. Pre-dispatch fail-stop and Mode B degradation rules are defined in `{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md`.

## Pre-Phase-Setup (MAX_ITER resolution)

**Constants**:
- `INLINE_LOOP_WARNING_THRESHOLD = 2` — iteration count above which inline sequential review may exhaust context; used to gate long-loop context-exhaustion warnings in phase-5.2-semantic.

Emit the MAX_ITER prompt ONLY when entering Phase 5 from an internal generate path. On external entry (analyze→generate via `workflows/analyze/phase-4-output/remediation-handoff.md` option 1), `MAX_ITER` is ALREADY resolved by the analyze side: `workflows/analyze/phase-4-output/remediation-handoff.md` option 1 next-turn routing step (b) owns the canonical MAX_ITER prompt and MUST wait for the user reply before handing off to this phase. MUST NOT re-prompt MAX_ITER here on analyze-side remediation handoff option 1 entry.

Before any heavy review work, resolve the review-loop iteration cap. Ask the user how many automatic review iterations to run after `workflows/generate/phase-4-write.md` writes files:

```text
How many automatic review iterations should run before I check in with you?

Each iteration: validate + review the written files → auto-fix mechanical
issues → ask you to approve any non-mechanical findings → re-validate.

Reply with a number (suggested: 5 — balances fix coverage against context cost; use 2 or less in inline mode), `enter` for 5, or `0` to skip the loop.
```

Parser: a bare number sets `MAX_ITER`. Default `5` on `enter`. `MAX_ITER=0`
selects the zero-iteration branch; external analyze→generate entry and internal
generate entry have separate semantics in the Dispatcher below.

### Review-Loop Iteration Cap Prompt

Reusable sub-block emitted by every Phase 5 iteration-end branch (`workflows/generate/phase-5/phase-5.3-findings.md` fast-path return, `workflows/generate/phase-5/phase-5.4-approval.md` options `1` / `2` / `2:`) when `N > MAX_ITER`:

```text
Iteration {N} complete; you set MAX_ITER={MAX_ITER}. Continue, accept current state, or stop?

`extend: <M>` → raise MAX_ITER to <M> and run another iteration (must be > current MAX_ITER)
`accept`     → exit the loop now; loop_exit = "max-iter-stopped"; remaining_findings = carry_forward (suggested when current findings look acceptable)
`stop`       → exit the loop now; loop_exit = "manual-handoff"; remaining_findings = carry_forward (use when you want to inspect / hand off the remaining findings before any more fixes)

Reply `extend: <M>`, `accept`, or `stop`.
```

Parser: a bare `extend: <M>` sets `MAX_ITER = M` when `M` is a positive integer greater than the current `MAX_ITER`. Invalid `extend: <M>` (M not a positive integer, or M ≤ current MAX_ITER) → re-emit the cap prompt with the clarifier `extend: <M> must be a positive integer greater than current MAX_ITER ({current_MAX_ITER}); reply again.` and do not change `MAX_ITER` until a valid value is provided.

Same wording at every emission site so users see one canonical extension dialog regardless of which branch hit the cap. `workflows/generate/phase-5/phase-5.3-findings.md` § External entry reuses this sub-block to resolve `MAX_ITER` at handoff time.

## Dispatcher

State initialization (canonical values applied on entry to this phase, both from the normal `workflows/generate/phase-4-write.md` → Phase 5 path and from the `workflows/generate/phase-5/phase-5.3-findings.md` § External entry block): `N = 1`, `carry_forward = []`. The `workflows/generate/phase-5/phase-5.3-findings.md` External entry block re-states the same values for clarity at the handoff site; both readings agree. The loop body increments `N` after every author dispatch and appends each author-returned `findings_not_fixable` to `carry_forward`; open, load, and follow `workflows/generate/phase-5/phase-5.4-approval.md` § Session-level carry-forward for the union-on-exit rule.

External-fix handoff guard: on analyze→generate option `1` entry, Phase 5
state MUST include `handoff_guard.inline_fallback_reprobed = true`,
`handoff_guard.max_iter_resolved = true`, and
`handoff_guard.dispatch_evidence_required = true` before any review or fix
work begins. For analyze-originated external entry, if `MAX_ITER > 0`, the
orchestrator MUST run Phase 5.1 and Phase 5.2 before Phase 5.3 so carried
findings are refreshed against the generate-side validator/reviewer contracts
before any author dispatch. Initialize `phase5_dispatch_evidence = []` on entry. When
`MAX_ITER > 0` and `INLINE_FALLBACK=false`, `phase5_dispatch_evidence` MUST
contain a validator dispatch record for every executed iteration, a semantic reviewer dispatch record for every executed iteration when that iteration
reaches Phase 5.2, and an author dispatch record before any file edit. The
evidence record is a
compact object with `iteration`, `phase`, `agent_id`, `target_paths`, and
`result_marker` or equivalent dispatch-return proof. For native sub-agent mode,
missing dispatch evidence is a protocol violation: stop before editing files
or before claiming the fix loop ran. Inline fallback mode may record
`inline_fallback=true` evidence instead. `MAX_ITER=0` records the zero-iteration
branch and does not require validator/reviewer/author dispatch evidence.

Iteration cap: the check `N > MAX_ITER` fires AFTER an iteration completes, so `MAX_ITER=5` allows iterations `1..5` to run and then prompts the user. The cap is enforced uniformly via the `Review-Loop Iteration Cap Prompt` defined above; same wording used by every iteration-end branch including the `workflows/generate/phase-5/phase-5.3-findings.md` fast-path and every `workflows/generate/phase-5/phase-5.4-approval.md` option. (The cap check applies when `MAX_ITER ≥ 1`; the `MAX_ITER=0` branches above bypass the cap check and route directly to Phase 5.3.)

After `workflows/generate/phase-4-write.md` writes files, run a bounded review loop. Each iteration dispatches `cf-deterministic-validator` then (on det PASS) the matched semantic reviewer(s); the orchestrator auto-fixes mechanical findings through `workflows/generate/phase-4-write.md` § Author Selection and Dispatch with a `mode=fix` payload, and asks the user to approve any non-mechanical findings before fixing them. The loop terminates when no findings remain, the user stops it, or `MAX_ITER` (set above in Pre-Phase-Setup) is reached.

If `MAX_ITER=0` AND this is an **external-entry** dispatch (analyze→generate via `workflows/analyze/phase-4-output/remediation-handoff.md` option 1), skip fresh Phase 5 validation/review and proceed directly through the external-entry handling in `workflows/generate/phase-5/phase-5.3-findings.md`; that path renders the carried findings, sets `remaining_findings = all_findings`, and routes to `workflows/generate/phase-6/index.md` with the mandatory `workflows/generate/phase-6/remediation-handoff.md` menu.

If `MAX_ITER=0` on an **internal** generate flow, run exactly one deterministic
validator pass through `workflows/generate/phase-5/phase-5.1-det-gate.md`. When
that gate allows semantic review (`PASS` or validator-backed `SKIPPED`), run one
semantic-reviewer pass through `workflows/generate/phase-5/phase-5.2-semantic.md`.
When that gate fails, skip semantic review exactly as Phase 5.1 requires and
surface the validator findings directly. Then hand the resulting findings to
`workflows/generate/phase-5/phase-5.3-findings.md` with the `MAX_ITER == 0`
branch (which renders findings and routes to phase-6 without entering the
partition/auto-fix logic).

> **⛔ CRITICAL**: The agent's own checklist walkthrough is **NOT** a substitute for the deterministic validator. See anti-pattern `SIMULATED_VALIDATION`. The dispatched sub-agents execute the actual resolved validator command from the target bootstrap (for example `cpt` in a Studio `.bootstrap`, or `cfs` in a Constructor Studio adapter) and the methodology checklists.

| Sub-file | Load WHEN |
|---|---|
| `phase-5.1-det-gate.md` | Each iteration begins; dispatch the deterministic validator |
| `phase-5.2-semantic.md` | Det gate PASS or SKIPPED; dispatch matched semantic reviewer(s) |
| `phase-5.3-findings.md` | Findings list (merged across det + semantic) must be displayed; partition + mechanical fast-path |
| `phase-5.4-approval.md` | `judgmental` is non-empty (mixed or judgmental-only iteration); user approval required |
| `phase-5.5-final.md` | Loop exits; assemble final `Validation Results` body for `workflows/generate/phase-6/index.md` |
