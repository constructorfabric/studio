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
  - ALWAYS treat PDSL blocks as executable instruction contracts.
  - ALWAYS treat `WHEN` as an activation predicate; once true, the owning
    `DO`, `RULES`, `INVARIANTS`, and matching `ON_ERROR` obligations are active.
  - ALWAYS execute `DO` actions in written order unless a `CONTINUE`, `RETURN`,
    `WAIT`, or `STOP_TURN` transfers control earlier.
  - ALWAYS read `STATE`, `WHEN`, `DO`, `RULES`, and `INVARIANTS` as list blocks;
    every top-level item starts with that section's allowed starter keyword.
  - ALWAYS treat `REQUIRE` as a precondition. If unmet, enter matching `ON_ERROR`
    when present; otherwise stop and report the missing precondition.
  - ALWAYS treat `NEVER` as an absolute prohibition in the current scope.
  - ALWAYS treat `LOAD` as loading or reusing a referenced prompt asset or
    context slice before later actions depend on it.
  - ALWAYS treat `RUN` as executing a named local unit, probe, check, or
    workflow step.
  - ALWAYS treat `WAIT` plus `STOP_TURN` as a hard assistant-turn boundary.
  - ALWAYS treat `CONTINUE <unit-or-phase>` as transfer of control to that target,
    not optional advice.
  - ALWAYS treat `DISPATCH` as invoking a named sub-agent or worker contract;
    concurrency, isolation, and join behavior come from explicit dispatch
    options or surrounding rules, not separate dispatch keywords.
  - ALWAYS treat `RETURN` as the declared terminal handoff or output shape.
  - ALWAYS treat `RULES` as mandatory constraints for the owning unit.
  - ALWAYS treat `INVARIANTS` as always active while the owning unit, workflow,
    or dispatch contract is active.
  - ALWAYS treat `TITLE`, `OPTIONS`, and `INVALID` as executable menu structure:
    `TITLE` names the surface, `OPTIONS` declares valid choices, and `INVALID`
    handles all unmatched input.
  - ALWAYS require every top-level `OPTIONS` entry to start with a decimal
    number; aliases or patterns follow the number, not replace it.
  - ALWAYS treat `ON_ERROR` as the named recovery path for matching failures.
  - ALWAYS treat `NOTES` as explanatory only; NOTES do not create executable
    obligations unless an active rule references them.
  - NEVER weaken `ALWAYS`, `NEVER`, `REQUIRE`, `WAIT`, `STOP_TURN`, or
    `INVARIANTS` because nearby prose sounds softer.
  - NEVER infer hidden behavior from prose outside PDSL blocks.
  - NEVER use text-labeled fences for PDSL instruction blocks; use
    pdsl-labeled fences.
```
