# PDSL Execution Card

Use this module as the minimal runtime semantics slice when a prompt-consuming
agent must execute, author, transform, or review PDSL instruction blocks.

```pdsl
UNIT PdslExecutionSemantics

PURPOSE:
  Define compact execution semantics for PDSL blocks in LLM context.

RULES:
  ALWAYS treat PDSL blocks as executable instruction contracts.
  ALWAYS treat `WHEN` as an activation predicate; once true, the owning
    `DO`, `RULES`, `INVARIANTS`, and matching `ON_ERROR` obligations are active.
  ALWAYS execute `DO` actions in written order unless a `CONTINUE`, `RETURN`,
    `WAIT`, or `STOP_TURN` transfers control earlier.
  ALWAYS treat `REQUIRE` as a precondition. If unmet, enter matching `ON_ERROR`
    when present; otherwise stop and report the missing precondition.
  ALWAYS treat `NEVER` as an absolute prohibition in the current scope.
  ALWAYS treat `LOAD` as loading or reusing a referenced prompt asset or
    context slice before later actions depend on it.
  ALWAYS treat `RUN` as executing a named local unit, probe, check, or
    workflow step.
  ALWAYS treat `WAIT` plus `STOP_TURN` as a hard assistant-turn boundary.
  ALWAYS treat `CONTINUE <unit-or-phase>` as transfer of control to that target,
    not optional advice.
  ALWAYS after any `WAIT`/`STOP_TURN` resume at the exact active PDSL
    continuation target; REQUIRED: do not reinterpret the user's reply as
    broad permission for generic autonomous execution.
  ALWAYS while a workflow, gate, or menu remains active, treat each new user
    message as input to that active continuation, not as permission for
    unrelated execution.
  ALWAYS treat `RETURN` as the declared terminal handoff or output shape.
  ALWAYS treat `RULES` as mandatory constraints for the owning unit.
  ALWAYS treat `INVARIANTS` as always active while the owning unit, workflow,
    or dispatch contract is active.
  ALWAYS treat `TITLE`, `OPTIONS`, and `INVALID` as executable menu structure:
    `TITLE` names the surface, `OPTIONS` declares valid choices, and `INVALID`
    handles all unmatched input.
  ALWAYS require every top-level `OPTIONS` entry to start with a decimal
    number; aliases or patterns follow the number, not replace it.
  ALWAYS, when executing `EMIT_MENU`, first check the menu is native-dialog
    shape-compatible: at most 4 top-level `OPTIONS` entries, and no entry
    documented as accepting free-text/arbitrary input (a path, a name, "or
    describe your own", etc.) rather than choosing among the listed entries.
  ALWAYS, for a shape-compatible `EMIT_MENU` where the active `ask_tool_name`
    context is a real tool name (not `unset`), invoke that tool instead of
    rendering the menu as prose: pass `TITLE` as the question/header text and
    each numbered `OPTIONS` entry as one selectable option (its short label as
    the option label, its action clause as the option description).
  ALWAYS, for a shape-compatible `EMIT_MENU` where `ask_tool_name` is `unset`,
    still surface the menu so a harness exposing an equivalent affordance it
    recognizes by `ask_tool_description` can match it: state the question,
    list the numbered options, and mark it explicitly as a blocking question
    the assistant is waiting on — placed as the last content in the turn.
  ALWAYS, for a shape-incompatible `EMIT_MENU` (more than 4 options, or any
    free-text-accepting entry), render as today's text menu regardless of
    `ask_tool_name` — a native dialog's fixed-choice shape cannot represent it
    faithfully — but still place it last in the turn and mark it blocking.
  NEVER treat a harness with no matching native affordance as an error;
    fall back to the same explicitly-marked, end-of-turn text rendering used
    for shape-incompatible menus.
  ALWAYS treat `ON_ERROR` as the named recovery path for matching failures.
  ALWAYS treat `NOTES` as explanatory only; NOTES do not create executable
    obligations unless an active rule references them.
  NEVER weaken `ALWAYS`, `NEVER`, `REQUIRE`, `WAIT`, `STOP_TURN`, or
    `INVARIANTS` because nearby prose sounds softer.
```
