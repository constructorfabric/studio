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

When `workflows/generate/phase-5/index.md` exits with non-empty `remaining_findings` (manual-handoff, user-accepted with remaining, MAX_ITER=0 surfacing all findings, or RELAXED `Deterministic gate: FAIL`), emit this menu verbatim (filled with actual counts) as the terminal actionable reply menu. Do not emit the `workflows/generate/phase-6/post-write-handoff.md` menu while remediation is pending.

```text
Remaining findings: High {h} / Medium {m} / Low {l}. How do you want to address them?

R1. Continue here in fix mode — invoke `/cf-generate(mode=fix)` in this session on the remaining findings
R2. Generate a Fix Prompt — emit a self-contained prompt for direct fix via `/cf-generate` in a new chat
R3. Generate a Plan Prompt — emit a self-contained prompt for phased remediation via `/cf-plan` in a new chat

Suggested: {R1|R2|R3} because {scope/risk reason}.

Reply `R1`, `R2`, or `R3`. The Post-Write Review Handoff menu unlocks only after remediation clears; do NOT combine remediation and review replies (e.g. `R1, W2`) — combined replies are refused with a clarifying prompt. W-only replies are refused while remediation is pending; process an `R*` choice first.
```

On the user's next-turn reply:

- `R1` → enter `workflows/generate/phase-5/index.md` § Dispatcher in fix mode (iteration 1 begins at `workflows/generate/phase-5/phase-5.1-det-gate.md`). The orchestrator MUST: (a) emit the canonical `MAX_ITER` resolution prompt from `workflows/generate/phase-5/index.md` § Pre-Phase-Setup and wait for the reply; (b) initialize Phase 5 state with `all_findings = remaining_findings`, `manifest.paths_written` unchanged from the written/analyzed paths, `target_paths = manifest.paths_written`, but prefer `external_target_paths` when `manifest.paths_written` is empty, `carry_forward = []`; (c) execute the full Phase 5 review-fix loop — each iteration MUST dispatch `cf-deterministic-validator` (Phase 5.1) and the matched semantic reviewer sub-agent set (Phase 5.2) on `target_paths` BEFORE the author dispatch (subject to `INLINE_FALLBACK` per `workflows/shared/inline-fallback-probe.md`). MUST NOT shortcut the loop with an inline review, inline fix, or single-pass summary. Loop iterates until clean or `MAX_ITER` is hit. No prompt block is emitted by this step.
- `R2` → emit the `Fix Prompt` template (defined in `workflows/generate/phase-6/prompt-template-fix.md`) as a final section, filled with the analyzed paths, kind, validation results, and the full inline list of `remaining_findings`.
- `R3` → emit the `Plan Prompt` template (defined in `workflows/generate/phase-6/prompt-template-plan.md`) as a final section, filled the same way.

Combine semantics: Remediation (`R*`) and Post-Write Review (`W*`) choices MUST be processed on separate user turns. If the user replies with both on the same turn (e.g. `R1, W2`, `R2 + W3`, `W2, R1`) — including any whitespace, comma, or `+` separator variant — the orchestrator MUST refuse the combined reply with this one-line clarifier and wait for a fresh single-choice reply:

```text
Combined R+W replies are not supported (since each `R*` may change `remaining_findings` and `Validation Results` that the `W*` template would embed). Reply with just one of `R1`, `R2`, `R3` now; the Post-Write Review Handoff menu will be emitted after remediation clears so you can pick `W1` / `W2` / `W3` then.
```

Multiple-choice replies within one menu (`R1, R2` or `W1, W2`) are also refused with the same one-line clarifier shape, asking for a single choice from that menu.
