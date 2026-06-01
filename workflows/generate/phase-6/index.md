---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: "Invoke when Phase 5 exits and the orchestrator must assemble the Phase 6 next-steps + handoff menus — Remediation Handoff is mandatory when remaining_findings is non-empty and locks the Post-Write Review Handoff until remediation clears."
---

# Phase 6 — Offer Next Steps (Dispatcher)

```text
UNIT Phase6EntryGate

PURPOSE:
  Decide whether Phase 6 must load after Phase 5 exit or may be skipped on the
  chat-only clean path.

WHEN:
  LOAD this phase after Phase 5 exit when at least one is true:
    - Validation Results body exists or must be surfaced
    - waiver or waiver-exception state must be evaluated or rendered
    - files were written or changed
    - remaining_findings is non-empty
    - validation state is unresolved, including any outstanding validation or
      waiver decision
  SKIP this phase only when all are true:
    - output is chat-only
    - no files changed
    - remaining_findings is empty
    - no outstanding validation or waiver decision remains

  NOTE outstanding validation or waiver decision:
    Outstanding validation includes pending reviewer validation,
    validation_result = "needs_action", any non-terminal validation status,
    queued remediation tasks, and async validation checks that have not reached
    terminal PASS, FAIL, SKIPPED_WITH_EVIDENCE, or WAIVED state.
    Outstanding waiver state includes waiver_pending,
    waiver_exception_pending, unresolved waiver determination, and any waiver
    whose applicability is required before terminal routing.
    remaining_findings non-empty always forces Phase 6. AUTHOR_PLAN_OFFER_RESOLVED
    alone does not clear outstanding validation unless validation_result is
    terminal.
    Example forcing Phase 6: chat-only output, no files changed,
    remaining_findings empty, validation_result = "needs_action".
    Example allowing skip: chat-only output, no files changed,
    remaining_findings empty, validation_result = PASS, no waiver state, and no
    queued remediation or async checks.

RULES:
  - Late-phase routing relies on controller-supplied prompt_context_view slices
  - MUST NOT reopen prompt assets from disk
  - If validation prerequisites, waiver applicability, or terminal clean/dirty
    state is unresolved, Phase 6 is required and clean skip is forbidden
```

```text
UNIT Phase6PrerequisiteGuard

PURPOSE:
  Verify Phase 5 produced required outputs before constructing terminal handoff menu.

DO:
  REQUIRE (1) complete Validation Results body from cf-deterministic-validator
    (canonical schema in validator agent file's Output section;
     assembled by phase-5.5-final.md)
  REQUIRE (2) at least one of:
    - Validation Report — <Section> block from phase-5.2-semantic.md reviewer dispatch
      (pattern: ^Validation Report — )
    - Partial Checkpoint — <Section> block with checkpoint.type = "PARTIAL_CHECKPOINT"
      from that reviewer dispatch

  NOTE: requirement (2) is waived by the first matching exception:
    Waiver 1: det_gate_final_result == "FAIL"
      (phase-5.1 skipped phase-5.2 per FAIL branch; no reviewer block exists;
       guard accepts condition 1 alone)
    Waiver 2: external entry from analyze.md with MAX_ITER=0
      (accept carried analyze-side deterministic result, semantic report blocks,
       and remaining_findings = all_findings from phase-5.3-findings.md)
    Waiver 3: PARTIAL_CHECKPOINT
      (satisfies requirement as PARTIAL only; downstream rendering uses partial schema)

  WAIVER PRIORITY (first match wins when multiple apply):
    1. det_gate_final_result == "FAIL"
    2. external entry from analyze.md with MAX_ITER=0
    3. PARTIAL_CHECKPOINT

  PARTIAL_CHECKPOINT impact:
    Phase 6 MUST keep remaining_findings non-empty
    MUST surface checkpoint/resume data through remediation handoff
    MUST NOT emit clean post-write handoff until checkpoint is resumed and completed

  IF required output is missing or contains placeholder/template content
     outside these exceptions:
    ABORT with clear prerequisite error stating which Phase 5 output is missing
    FORBID emitting handoff menus

RULES:
  - Any unresolved question about whether requirement (2) is satisfied or
    waived counts as an outstanding validation/waiver decision and forces
    Phase 6 entry; clean skip is forbidden until resolved
  - Consume Phase 5 outputs and waiver state from controller-supplied
    prompt_context_view slices; MUST NOT reopen prompt assets from disk

NOTES:
  Same exception (det-gate FAIL bypasses reviewer-block requirement) applies
  in workflows/analyze/phase-4-output/index.md when analogous prerequisite check
  is performed.
```

```text
UNIT Phase6NextStepMenu

PURPOSE:
  Present informational next-step menu from rules.md.

DO:
  READ ## Next Steps from rules.md

  IF rules.md available AND has ## Next Steps:
    EMIT exactly:
---
What would you like to do next?
1. {option from rules Next Steps} — Mark as `Suggested` when it is the clearest continuation from the current result; state why and what happens next.
2. {option from rules Next Steps} — State what this does next.
3. Other — Say what you want to change or do next.
Reply with the option number or a short custom instruction.
---

  ELSE (rules.md unavailable or no ## Next Steps):
    EMIT exactly:
---
What would you like to do next?
1. Run /cf-analyze on the written files — Suggested when files were created; validates the output and surfaces any remaining issues.
2. Other — Describe next action.
Reply with the option number or a short custom instruction.
---

RULES:
  - Next-step menu is informational only when phase-4-write.md wrote or updated files
  - MUST emit next-step menu before the terminal handoff section
```

```text
UNIT Phase6TerminalHandoffRouting

PURPOSE:
  Route to the correct terminal handoff sub-file based on remaining_findings
  and file-write state.

DO:
  IF remaining_findings is non-empty:
    LOAD remediation-handoff.md as terminal actionable menu
    FORBID emitting W replies in this response
    FORBID emitting post-write-handoff.md while remediation pending
    NOTE: Post-write review choices deferred until remediation is processed

  IF remaining_findings is empty AND files were written:
    LOAD post-write-handoff.md as terminal section

  IF output was chat-only AND no files changed AND remaining_findings is empty
     AND no outstanding validation or waiver decision remains:
    SKIP both handoff menus

  IF chat-only output with non-empty remaining_findings:
    EMIT remediation-handoff.md as terminal actionable menu
    NOTE: no-files condition does NOT suppress remediation

  AFTER terminal handoff sub-file emits its final section:
    Generate workflow is COMPLETE — no further phase loads

RULES:
  - MUST NOT ask whether handoff menus should be generated
  - MUST NOT defer required remediation handoff to a later user turn
  - MUST emit remediation handoff when remaining_findings is non-empty
    (for any file-writing generate flow: validated, RELAXED unvalidated,
     artifacts, code, workflow/instruction updates, multi-file edits)
  - Phase 6 skip is allowed only on the chat-only clean path with no files
    changed, no findings, and no outstanding validation/waiver decision
  - If files were written and remaining_findings is empty:
    MUST emit Post-Write Review Handoff menu as FINAL section;
    omitting it makes generate output incomplete
  - If files were written and remaining_findings is non-empty:
    MUST emit Remediation Handoff menu as terminal section;
    asking for actionable W replies makes generate output incomplete
  - A summary alone is not completion
  - Validation Results body alone is not completion
  - Next-step menu alone is not completion

INVARIANTS:
  - Fix Prompt / Plan Prompt / Direct Review Prompt / Plan Review Prompt
    MUST be emitted ONLY on the NEXT turn after user picks matching handoff option;
    MUST NOT emit in same turn as handoff menu

NOTES:
  Sub-file routing:
    remediation-handoff.md: remaining_findings non-empty
    post-write-handoff.md: files written AND remaining_findings empty
    prompt-templates.md: user picked R2/R3 or W2/W3 after post-write unlocked

  Final self-check before ending file-writing response:
    VERIFY files were written
    IF yes AND remaining_findings empty: VERIFY Post-Write Review Handoff emitted
    IF remaining_findings non-empty: VERIFY Remediation Handoff emitted as only
      actionable reply menu; VERIFY W replies withheld
```
