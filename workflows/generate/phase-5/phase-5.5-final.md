---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the Phase 5 review loop exits and the final `Validation Results` body must be assembled for Phase 6 handoff emission.
---

### Phase 5.5: Final `Validation Results` for Phase 6

```pdsl
UNIT Phase55FinalValidationResults

PURPOSE:
  Assemble final Validation Results body from the FINAL iteration's
  cf-deterministic-validator dispatch for Phase 6 handoff.

DO:
  REPRODUCE the final-iteration cf-deterministic-validator Validation Results block
    verbatim (canonical block with all placeholders filled in)
    NOTE: block schema owned by
      {cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md § Output;
      MUST NOT redefine here; reproduce from agent's final-iteration return value

  APPEND Semantic Review summary block:
---
Semantic Review: closed {c}, accepted-as-is {a}, handed-off {h}; total iterations {N}; loop_exit={clean|user-accepted|manual-handoff|max-iter-stopped|max-iter-stopped-with-failures}.
remaining_findings = [ {id}, {id}, ... ]   # empty list when loop_exit=clean
det_gate_final_result = {PASS|FAIL|SKIPPED}
---

RULES:
  - det_gate_final_result MUST be exactly one of: "PASS", "FAIL", "SKIPPED"
  - det_gate_final_result reflects the final-iteration deterministic gate outcome
    (or "SKIPPED" with validator availability proof when gate was not run)
  - det_gate_final_result is the authoritative named field consumed by
    workflows/generate/phase-6/index.md § prerequisite guard
  - Both blocks together constitute the canonical Validation Results body that
    phase-6/index.md emits verbatim when an on-demand emission template is dispatched
  - MUST proceed to phase-6/index.md
  - phase-6/index.md MUST NOT proceed without a completed Validation Results body
    (canonical template fields filled with actual values)
  - Open, load, and follow {cf-studio-path}/.core/workflows/generate/phase-6/index.md § prerequisite guard
```
