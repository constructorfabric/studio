---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the Phase 5 review loop exits and the final `Validation Results` body must be assembled for Phase 6 handoff emission.
---

### Phase 5.5: Final `Validation Results` for Phase 6

The Validation Results body emitted in `workflows/generate/phase-6/index.md` (used by both handoff menus and the on-demand emission templates) is the result of the FINAL iteration's `cf-deterministic-validator` dispatch — its canonical block with all placeholders filled in. The block schema is owned by the validator agent file (`{cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md` § Output) and is NOT redefined here; reproduce it verbatim from the agent's final-iteration return value.

After the validator block, append a short Semantic Review summary block listing counts:

```text
Semantic Review: closed {c}, accepted-as-is {a}, handed-off {h}; total iterations {N}; loop_exit={clean|user-accepted|manual-handoff|max-iter-stopped|max-iter-stopped-with-failures}.
remaining_findings = [ {id}, {id}, ... ]   # empty list when loop_exit=clean
det_gate_final_result = {PASS|FAIL|SKIPPED}
```

`det_gate_final_result` MUST be one of the string literals `"PASS"`, `"FAIL"`, or `"SKIPPED"` and reflects the final-iteration deterministic gate outcome (or `"SKIPPED"` with validator availability proof when the gate was not run). This named field is the authoritative source consumed by `workflows/generate/phase-6/index.md` § prerequisite guard.

Both blocks together constitute the canonical `Validation Results` body that `workflows/generate/phase-6/index.md` emits verbatim when an on-demand emission template is dispatched.

Gate: `workflows/generate/phase-6/index.md` MUST NOT proceed without a completed `Validation Results` body (canonical template fields filled with actual values). Open, load, and follow `workflows/generate/phase-6/index.md` § prerequisite guard.
