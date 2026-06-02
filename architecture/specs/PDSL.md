---
studio: true
type: spec
name: PDSL Specification
version: 0.1
purpose: Define a compact instruction language for human-readable and LLM-readable workflow, skill, and requirement files
---

# PDSL Specification

PDSL is a compact notation for writing agent instructions in
`skills/`, `workflows/`, and `requirements/`.

The goal is not to create a programming language. The goal is to make
mandatory behavior clear, reviewable, and hard to misread.

Use PDSL for:

- workflow phases
- state gates
- approval menus
- UX prompts
- error handling
- required and forbidden actions
- handoff rules

Keep prose for context and rationale. Use PDSL for behavior.

---

## Design Goals

PDSL is:

- compact enough to replace repetitive prose
- readable by humans without a parser
- explicit about state, branches, and stop points
- easy for an LLM to follow as an execution contract
- stable under copy, review, and partial editing

PDSL does not depend on hidden semantics. If a state change,
menu choice, or stop condition matters, write it explicitly.

---

## Core Shape

Use uppercase block headers. Each block describes one concern.

```pdsl
UNIT <name>

PURPOSE:
  <one sentence>

STATE:
  - SET <name>: <allowed values>

WHEN:
  - REQUIRE <condition>

DO:
  - RUN <ordered actions>

MENU <name>:
  TITLE: <menu title>
  OPTIONS:
    1 <choice> -> <actions>
  INVALID:
    EMIT <retry instruction>
    WAIT user.reply
    STOP_TURN

RULES:
  - ALWAYS <rule>
  - NEVER <rule>

ON_ERROR:
  <error> -> <actions>
```

Blocks can be omitted when not relevant. `PURPOSE`, `WHEN`, and `DO` are the
default minimum for executable behavior.

Markdown code fences that contain PDSL instruction blocks use the `pdsl`
language tag. Use ```` ```pdsl ```` for `UNIT`, `PATTERNS`, `WHEN`, `DO`,
`MENU`, `RULES`, `ON_ERROR`, `INVARIANTS`, `NOTES`, and other PDSL-shaped
blocks. Do not use ```` ```text ```` for PDSL instruction blocks.

---

## Keywords

Use this small keyword set before inventing new words.

| Keyword | Meaning |
| --- | --- |
| `UNIT` | Named instruction unit, phase, gate, or reusable rule |
| `PURPOSE` | Why this unit exists |
| `INPUT` | Required inputs or context |
| `OUTPUT` | Expected result or handoff |
| `STATE` | State variables and allowed values |
| `WHEN` | Entry condition |
| `DO` | Ordered required actions |
| `SET` | Assign state |
| `LOAD` | Load or reuse a referenced prompt asset or context slice |
| `RUN` | Execute a named local unit, probe, check, or workflow step |
| `EMIT` | Show user-facing text |
| `EMIT_MENU` | Show a named `MENU` block |
| `MENU` | User choice surface |
| `TITLE` | User-facing menu title |
| `OPTIONS` | Valid menu choices and their actions |
| `INVALID` | Invalid menu input handling |
| `WAIT` | Stop for user input |
| `STOP_TURN` | End assistant turn immediately |
| `CONTINUE` | Move to named unit or phase |
| `DISPATCH` | Invoke a named sub-agent or worker contract |
| `RETURN` | Return a manifest, report, checkpoint, or handoff |
| `REQUIRE` | Required precondition |
| `RULES` | Mandatory constraints |
| `ON_ERROR` | Error recovery |
| `INVARIANTS` | Conditions that must always hold |
| `ALWAYS` | Absolute positive rule inside `RULES` or `INVARIANTS` |
| `NEVER` | Absolute prohibition inside `DO`, `RULES`, or `INVARIANTS` |
| `NOTES` | Non-executable explanation |

Use `ALWAYS` inside `RULES` and `INVARIANTS`. Use `NEVER` inside `DO`,
`RULES`, or `INVARIANTS` for absolute prohibitions.

Structured execution sections use list items. Each top-level item starts with
one of the section's allowed starter keywords:

- `STATE`: `SET`
- `WHEN`: `REQUIRE`, `AND`, `OR`, `NOT`
- `DO`: `SET`, `LOAD`, `RUN`, `EMIT`, `EMIT_MENU`, `WAIT`, `STOP_TURN`,
  `CONTINUE`, `DISPATCH`, `RETURN`, `REQUIRE`, `NEVER`
- `RULES` and `INVARIANTS`: `ALWAYS`, `NEVER`
- `OPTIONS`: a decimal number such as `1`, `2`, `3`

Continuation lines and nested explanatory bullets may appear under a list item,
but they do not introduce new PDSL actions or rules.

---

## Execution Semantics

PDSL blocks are executable instruction contracts for humans and LLMs. A
controller or sub-agent interpreting PDSL applies these rules:

- `WHEN` is an activation predicate; once true, the owning `DO`, `RULES`,
  `INVARIANTS`, and matching `ON_ERROR` obligations are active.
- `DO` actions run in written order unless `CONTINUE`, `RETURN`, `WAIT`, or
  `STOP_TURN` transfers control earlier.
- `REQUIRE` is a precondition; if unmet, enter matching `ON_ERROR` when
  present, otherwise stop and report the missing precondition.
- `NEVER` is an absolute prohibition in the current scope.
- `LOAD` makes a referenced prompt asset or context slice available before
  later actions depend on it.
- `RUN` executes a named local unit, probe, check, or workflow step.
- `WAIT` plus `STOP_TURN` is a hard assistant-turn boundary.
- `CONTINUE <unit-or-phase>` transfers control to that target; it is not
  optional advice.
- `DISPATCH` invokes a named sub-agent or worker contract. Concurrency,
  isolation, and join behavior belong in explicit dispatch options or
  surrounding rules, not in separate dispatch keywords.
- `RETURN` declares the terminal handoff or output shape.
- `RULES` are mandatory constraints for the owning unit.
- `INVARIANTS` stay active while the owning unit, workflow, or dispatch
  contract is active.
- `NOTES` are explanatory only; they do not create executable obligations
  unless an active rule references them.

The root `skills/studio/SKILL.md` owns loading the compact runtime card at
`requirements/pdsl-execution-card.md` once into the shared context pack.
Workflow and agent prompts should rely on that root-skill slice instead of
re-declaring the card path locally.

---

## Conditions

Conditions use plain expressions, not code syntax.

```pdsl
WHEN:
  - REQUIRE SUB_AGENT_SESSION_APPROVED == unset
  - AND host.supports_native_subagents == true
```

Allowed operators:

- `==`, `!=`
- `AND`, `OR`, `NOT`
- `exists(<name>)`
- `contains(<value>, <token>)`
- `matches(<value>, <pattern-name>)`

Pattern names are defined nearby or in a referenced requirement.

File-scoped patterns can be declared in a local `PATTERNS:` block at the top
of the PDSL file. Patterns intended for reuse across files are registered
in `requirements/pdsl-patterns.md`.

---

## PATTERNS Block

A `PATTERNS:` block declares named patterns for use in `matches()` conditions.

```pdsl
PATTERNS:
  slug-format: /^[a-z][a-z0-9-]{0,62}$/
    description: Lowercase kebab-case identifier, 1-63 chars
  semver-tag: /^\d+\.\d+\.\d+$/
    description: Strict three-part semantic version tag
```

Rules:

- A `PATTERNS:` block is file-scoped. It appears before the first `UNIT`
  that references it.
- Pattern names are unique within a file.
- Patterns shared across multiple files are registered in the canonical
  patterns registry at `requirements/pdsl-patterns.md`.
- A `matches()` call references a name defined in the local `PATTERNS:`
  block or in the canonical registry. Undefined names are a PDSL authoring
  error.

---

## Actions

Actions are imperative and one per line.

```pdsl
DO:
  - REQUIRE workflow_target is known
  - SET INLINE_FALLBACK = true
  - EMIT_MENU ApprovalMenu
  - WAIT user.reply
  - STOP_TURN
```

Use `SET` only for state changes. Use `EMIT` or `EMIT_MENU` only for visible
UX output. Use `STOP_TURN` whenever the next step must wait for the user.

---

## Menus

Menus are first-class behavior, not prose.

```pdsl
MENU ApprovalMenu:
  TITLE: Approve sub-agent use for this session
  OPTIONS:
    1 -> SET SUB_AGENT_SESSION_APPROVED = true
         SET INLINE_FALLBACK = false
         CONTINUE CurrentWorkflow
    2 -> SET INLINE_FALLBACK = true
         CONTINUE CurrentWorkflow
  INVALID:
    EMIT "Reply with 1 or 2."
    WAIT user.reply
    STOP_TURN
```

Menu rules:

- Every option has an action.
- Every option starts with a decimal number. Put aliases after the number, for
  example `1 | save | save default -> ...`.
- Invalid input is specified.
- If the menu is a hard interaction boundary, it ends with `STOP_TURN`.
- Suggested options belong in `TITLE` or `NOTES`, not hidden in prose.

---

## State

State declarations list allowed values and default behavior.

```pdsl
STATE:
  - SET CF_PHASE_GATE: armed | released_for_dispatch | released_for_inline_write
    default: armed
    reset: start_of_assistant_turn

  - SET INLINE_FALLBACK: unset | true | false
    default: unset
```

State rules:

- Every referenced state variable is declared in the nearest relevant
  `STATE` block.
- Defaults are explicit when missing state changes behavior.
- Reset rules are explicit when state is scoped to a turn, workflow, or
  session.

---

## Invariants And Prohibitions

Use `INVARIANTS` for always-on rules.

```pdsl
INVARIANTS:
  - ALWAYS keep CF_PHASE_GATE = armed outside released write windows
  - ALWAYS reset CF_PHASE_GATE to armed after dispatch returns
  - NEVER write files while CF_PHASE_GATE == armed
```

Use `NEVER` in `DO` or `RULES` when a prohibition is local to one unit.

---

## Error Handling

Error handling must be part of the same unit when failure changes control flow.

```pdsl
ON_ERROR:
  invalid_menu_reply ->
    EMIT "Reply with 1 or 2."
    WAIT user.reply
    STOP_TURN

  dispatch_failed ->
    SET CF_PHASE_GATE = armed
    EMIT failure_summary
    CONTINUE RecoveryMenu
```

Avoid vague recovery text such as "handle gracefully". Name the next action.

---

## Prose Boundary

PDSL is executable guidance. Prose is explanatory.

Use `NOTES` for explanation that does not create behavior.

```pdsl
NOTES:
  Native sub-agents preserve context isolation and parallelism. Inline fallback
  is slower and weaker, but allows the workflow to continue without host
  support.
```

LLMs do not infer extra rules from `NOTES` unless another executable block
references them.

---

## Example

Prose instruction:

```text
If sub-agent use has not been approved, ask the user whether to use native
sub-agents or inline fallback. If they choose native sub-agents, remember that
for this session. If they choose inline fallback, continue without native
dispatch. Do not assume inline fallback just because the user did not answer.
```

PDSL:

```pdsl
UNIT ExampleSubAgentApprovalGate

PURPOSE:
  Resolve whether this workflow may use native sub-agents.

STATE:
  - SET SUB_AGENT_SESSION_APPROVED: unset | true
    default: unset
    scope: session

  - SET INLINE_FALLBACK: unset | true | false
    default: unset
    scope: workflow_run

WHEN:
  - REQUIRE SUB_AGENT_SESSION_APPROVED == unset

DO:
  - EMIT_MENU SubAgentApprovalMenu
  - WAIT user.reply
  - STOP_TURN

MENU SubAgentApprovalMenu:
  OPTIONS:
    1 -> SET SUB_AGENT_SESSION_APPROVED = true
         SET INLINE_FALLBACK = false
         CONTINUE CurrentWorkflow
    2 -> SET INLINE_FALLBACK = true
         CONTINUE CurrentWorkflow
  INVALID:
    EMIT "Reply with 1 or 2."
    WAIT user.reply
    STOP_TURN

INVARIANTS:
  - NEVER set INLINE_FALLBACK = true from missing approval
  - NEVER set INLINE_FALLBACK = false unless SUB_AGENT_SESSION_APPROVED == true
```

---

## Authoring Rules

When converting prose instructions to PDSL:

1. Identify state first.
2. Convert every "when/if/unless" sentence into `WHEN` or `ON_ERROR`.
3. Convert every visible user interaction into `MENU`, `EMIT`, `WAIT`, and
   `STOP_TURN`.
4. Convert every "must/never/always" sentence into `RULES` or `INVARIANTS`.
5. Keep rationale in `NOTES`.
6. Do not hide required behavior in paragraphs after the DSL block.

If behavior is too complex for one unit, split it into multiple `UNIT` blocks
and connect them with `CONTINUE <unit-name>`.

---

## Adoption Guidance

Use PDSL first in files with high control-flow risk:

- phase gates
- approval prompts
- recovery menus
- state reset rules
- validation and review loops
- workflow handoffs

Do not rewrite stable narrative sections just to make them look algorithmic.
The value comes from reducing ambiguity in behavior, not from removing all
natural language.
