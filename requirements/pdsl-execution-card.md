---
cf: true
type: requirement
name: PDSL Execution Card
version: 0.1
purpose: Compact runtime semantics for LLMs executing or reviewing PDSL instruction blocks
---

# PDSL Execution Card

Use this card as the minimal runtime semantics slice when a prompt-consuming
agent must execute, author, transform, or review PDSL instruction blocks.

```pdsl
UNIT PdslExecutionSemantics

PURPOSE:
  Define compact execution semantics for PDSL blocks in LLM context.

RULES:
  - MUST treat PDSL blocks as executable instruction contracts.
  - MUST treat `WHEN` as an activation predicate; once true, the owning
    `DO`, `RULES`, `INVARIANTS`, and matching `ON_ERROR` obligations are active.
  - MUST execute `DO` actions in written order unless a `CONTINUE`, `RETURN`,
    `WAIT`, or `STOP_TURN` transfers control earlier.
  - MUST treat `REQUIRE` as a precondition. If unmet, enter matching `ON_ERROR`
    when present; otherwise stop and report the missing precondition.
  - MUST treat `FORBID` as an immediate prohibition in the current scope.
  - MUST treat `WAIT` plus `STOP_TURN` as a hard assistant-turn boundary.
  - MUST treat `CONTINUE <unit-or-phase>` as transfer of control to that target,
    not optional advice.
  - MUST treat `RETURN` as the declared terminal handoff or output shape.
  - MUST treat `RULES` as mandatory constraints for the owning unit.
  - MUST treat `INVARIANTS` as always active while the owning unit, workflow,
    or dispatch contract is active.
  - MUST treat `MENU` options and `INVALID` branches as the only valid menu
    transitions unless another active rule explicitly extends them.
  - MUST treat `ON_ERROR` as the named recovery path for matching failures.
  - MUST treat `NOTES` as explanatory only; NOTES do not create executable
    obligations unless an active rule references them.
  - MUST_NOT weaken `MUST`, `MUST_NOT`, `ALWAYS`, `NEVER`, `REQUIRE`, `FORBID`,
    `WAIT`, `STOP_TURN`, or `INVARIANTS` because nearby prose sounds softer.
  - MUST_NOT infer hidden behavior from prose outside PDSL blocks.
  - MUST_NOT use text-labeled fences for PDSL instruction blocks; use
    pdsl-labeled fences.
```
