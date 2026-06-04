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
  - RUN REPRODUCE the final-iteration cf-deterministic-validator Validation Results block
    verbatim (canonical block with all placeholders filled in)
    NOTE: block schema owned by
      {cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md § Output;
      - NEVER redefine here; reproduce from agent's final-iteration return value

  - RUN APPEND Semantic Review summary block:
- RUN ---
- RUN Semantic Review: closed {c}, accepted-as-is {a}, handed-off {h}; total iterations {N}; loop_exit={clean|user-accepted|manual-handoff|max-iter-stopped|max-iter-stopped-with-failures}.
- RUN remaining_findings = [ {id}, {id}, ... ]   # empty list when loop_exit=clean
- RUN det_gate_final_result = {PASS|FAIL|SKIPPED}
- RUN ---

RULES:
  - ALWAYS det_gate_final_result ALWAYS be exactly one of: "PASS", "FAIL", "SKIPPED"
  - ALWAYS det_gate_final_result reflects the final-iteration deterministic gate outcome
    (or "SKIPPED" with validator availability proof when gate was not run)
  - ALWAYS det_gate_final_result is the authoritative named field consumed by
    workflows/generate/phase-6/index.md § prerequisite guard
  - ALWAYS Both blocks together constitute the canonical Validation Results body that
    phase-6/index.md emits verbatim when an on-demand emission template is dispatched
  - ALWAYS proceed to phase-6/index.md
  - ALWAYS phase-6/index.md NEVER proceed without a completed Validation Results body
    (canonical template fields filled with actual values)
  - ALWAYS Open, load, and follow {cf-studio-path}/.core/workflows/generate/phase-6/index.md § prerequisite guard
```
