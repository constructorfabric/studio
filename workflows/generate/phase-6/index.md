---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: "Invoke when Phase 5 exits and the orchestrator must assemble the Phase 6 next-steps + handoff menus — Remediation Handoff is mandatory when remaining_findings is non-empty and locks the Post-Write Review Handoff until remediation clears."
---

# Phase 6 — Offer Next Steps (Dispatcher)

Prerequisite guard: before constructing the terminal handoff menu
(`workflows/generate/phase-6/remediation-handoff.md` when
`remaining_findings` is non-empty, otherwise
`workflows/generate/phase-6/post-write-handoff.md` when files were written),
verify that `workflows/generate/phase-5/index.md` produced (1) the complete
`Validation Results` body from `cf-deterministic-validator`
(canonical schema lives in the validator agent file's Output section;
assembled by `workflows/generate/phase-5/phase-5.5-final.md`) AND (2) at
least one `Validation Report — <Section>` block from a
`workflows/generate/phase-5/phase-5.2-semantic.md` reviewer dispatch
(pattern: `^Validation Report — `) OR a `Partial Checkpoint — <Section>` block
with `checkpoint.type = "PARTIAL_CHECKPOINT"` from that reviewer dispatch. A
partial checkpoint satisfies the semantic-output presence requirement only as
`PARTIAL`; Phase 6 MUST keep `remaining_findings` non-empty, surface the
checkpoint/resume data through the remediation handoff, and MUST NOT emit a
clean post-write handoff until the checkpoint is resumed and completed. The
semantic-output requirement is otherwise waived only when `det_gate_final_result == "FAIL"` (the named field set by `workflows/generate/phase-5/phase-5.5-final.md`; `workflows/generate/phase-5/phase-5.1-det-gate.md` skips `workflows/generate/phase-5/phase-5.2-semantic.md` in that case per the
FAIL branch, so no reviewer block exists and the guard accepts the Validation Results body requirement (condition 1) alone with
the FAIL state as the explanation). External entry from `analyze.md` with `MAX_ITER=0` is a second explicit exception: accept the carried analyze-side
deterministic result, semantic report blocks, and `remaining_findings =
all_findings` produced by `workflows/generate/phase-5/phase-5.3-findings.md`,
then emit the mandatory remediation handoff without requiring a fresh Phase 5 validator or reviewer dispatch.

**Waiver priority (first match wins):** When multiple waiver conditions apply simultaneously, apply them in this order:
1. `det_gate_final_result == "FAIL"` — bypasses the semantic-output requirement entirely; routes to Remediation Handoff with det-gate evidence.
2. External entry from `analyze.md` with `MAX_ITER=0` — accepts carried analyze-side outputs in lieu of an internal reviewer block.
3. `PARTIAL_CHECKPOINT` — satisfies the requirement as `PARTIAL` only; downstream rendering uses the partial schema.

If a required output is missing or still
contains placeholder/template content outside these exceptions, abort this
sub-file with a clear prerequisite error stating which Phase 5 output is
missing; do not emit the handoff menus. The same exception (det-gate FAIL
bypasses the reviewer-block requirement) applies in
`workflows/analyze/phase-4-output/index.md` when an analogous prerequisite
check is performed.

Read `## Next Steps` from `rules.md` and present:

```text
What would you like to do next?
1. {option from rules Next Steps} — Mark as `Suggested` when it is the clearest continuation from the current result; state why and what happens next.
2. {option from rules Next Steps} — State what this does next.
3. Other — Say what you want to change or do next.
Reply with the option number or a short custom instruction.
```

WHEN `rules.md` is unavailable or has no `## Next Steps` section, present this default menu instead:

```text
What would you like to do next?
1. Run /cf-analyze on the written files — Suggested when files were created; validates the output and surfaces any remaining issues.
2. Other — Describe next action.
Reply with the option number or a short custom instruction.
```

If `workflows/generate/phase-4-write.md` wrote or updated any files, the
next-step menu above is informational only. When `remaining_findings` from
`workflows/generate/phase-5/index.md` is empty, the terminal section of the
response is the `workflows/generate/phase-6/post-write-handoff.md` menu. When
`remaining_findings` is non-empty, the terminal reply contract is
remediation-only: emit `workflows/generate/phase-6/remediation-handoff.md` as
the final actionable menu and do not ask for W replies in this response.
Post-write review choices are deferred until remediation is processed. MUST
NOT ask whether the handoff menus should be generated and MUST NOT defer the
required remediation handoff to a later user turn.

This applies to any file-writing generate flow, including validated outputs, RELAXED explicitly unvalidated outputs, artifacts, code, workflow/instruction updates, and multi-file edits.

If output was chat-only, no files changed, and `remaining_findings` is empty,
skip both handoff menus. chat-only output with non-empty `remaining_findings` still emits the `workflows/generate/phase-6/remediation-handoff.md` menu as the terminal actionable menu; the no-files condition does not suppress remediation.

If files were written and `remaining_findings` is empty, omitting the
`Post-Write Review Handoff` menu makes the generate output incomplete. If
files were written and `remaining_findings` is non-empty, omitting the
`Remediation Handoff` menu or also asking for actionable W replies makes the
generate output incomplete.

A summary alone is not completion. The `Validation Results` body alone is not
completion. The next-step menu alone is not completion. For any file-writing
generate flow with no remaining findings, the response is invalid unless it
ends with `Post-Write Review Handoff`. For any file-writing generate flow with
remaining findings, the response is invalid unless it ends with
`Remediation Handoff` as the only actionable reply menu.

Before ending a file-writing response, perform this final self-check: were
files written; if yes and `remaining_findings` is empty, was the
`Post-Write Review Handoff` menu emitted; if `remaining_findings` is
non-empty, was the `Remediation Handoff` menu emitted as the final actionable
section and were W replies withheld; only then may the response end.

| Sub-file | Load WHEN |
|---|---|
| `remediation-handoff.md` | `remaining_findings` from `workflows/generate/phase-5/index.md` is non-empty (manual-handoff, user-accepted with remaining, MAX_ITER=0 surfacing all findings, or RELAXED `Deterministic gate: FAIL`) |
| `post-write-handoff.md` | Files were written by `workflows/generate/phase-4-write.md` (or any later iteration) AND `remaining_findings` is empty; otherwise deferred/locked until remediation is processed |
| `prompt-templates.md` | User picked `R2`/`R3`, or picked `W2`/`W3` after post-write review was unlocked, and the corresponding emission template must be rendered as the FINAL section |

After the terminal handoff sub-file (remediation-handoff, post-write-handoff, or prompt-templates) emits its final section, the generate workflow is complete. No further phase loads.
