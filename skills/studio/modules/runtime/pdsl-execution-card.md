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
  ALWAYS treat every `EMIT_MENU` in this corpus as a blocking gate paired with
    `WAIT`/`STOP_TURN` in the same `DO` block; the native-dialog routing below
    applies to that pairing, not to text output that merely lists choices
    without waiting on a reply.
  ALWAYS, when executing `EMIT_MENU`, first check the menu is native-dialog
    shape-compatible: at most 4 top-level `OPTIONS` entries, and no entry
    documented as accepting free-text/arbitrary input (a path, a name, "or
    describe your own", etc.) rather than choosing among the listed entries.
  ALWAYS treat an `ask_tool_name` context that was never established (no
    generated shim or dispatch prompt set it at all) identically to `unset`;
    the distinction between "explicitly no binding" and "never bound" carries
    no different behavior.
  ALWAYS, for a shape-compatible `EMIT_MENU` where the active `ask_tool_name`
    context is a real tool name (not `unset` or never established), invoke
    that tool instead of rendering the menu as prose, mapped onto that tool's
    own question/options schema: `TITLE` fills its single question/header
    field (there is one `EMIT_MENU` per invocation, never a multi-question
    batch), and each numbered `OPTIONS` entry becomes one selectable option —
    label from the entry's short form, description from its action clause —
    with the entry's number/alias retained as that option's canonical,
    non-displayed identity so the returned selection resumes the exact
    numbered branch regardless of how the harness renders or truncates the
    displayed label; that invocation is itself the turn's `WAIT`/`STOP_TURN`
    boundary — NEVER additionally re-render the menu as text or execute a
    redundant `STOP_TURN` after it.
  ALWAYS treat a native-tool result that selects none of the numbered
    `OPTIONS` — an out-of-band/free-text answer, a cancellation, a dismissal,
    or a tool error — as unmatched input for the menu's own `INVALID` handler;
    NEVER treat any such outcome as silently choosing a default option or
    advancing past the gate.
  ALWAYS, for a shape-compatible `EMIT_MENU` where `ask_tool_name` is `unset`
    or never established, still surface the menu so a harness exposing an
    equivalent affordance it recognizes by `ask_tool_description` can match
    it: state the question, list the numbered options, and mark it explicitly
    as a blocking question the assistant is waiting on — placed as the last
    content in the turn.
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
