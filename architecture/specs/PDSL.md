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

PDSL MUST be:

- compact enough to replace repetitive prose
- readable by humans without a parser
- explicit about state, branches, and stop points
- easy for an LLM to follow as an execution contract
- stable under copy, review, and partial editing

PDSL MUST NOT depend on hidden semantics. If a state change,
menu choice, or stop condition matters, write it explicitly.

---

## Core Shape

Use uppercase block headers. Each block describes one concern.

```text
UNIT <name>

PURPOSE:
  <one sentence>

STATE:
  <name>: <allowed values>

WHEN:
  <condition>

DO:
  <ordered actions>

MENU <name>:
  <choice> -> <actions>

RULES:
  - MUST <rule>
  - MUST_NOT <rule>

ON_ERROR:
  <error> -> <actions>
```

Blocks MAY be omitted when not relevant. `PURPOSE`, `WHEN`, and `DO` are the
default minimum for executable behavior.

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
| `EMIT` | Show user-facing text |
| `EMIT_MENU` | Show a named `MENU` block |
| `MENU` | User choice surface |
| `WAIT` | Stop for user input |
| `STOP_TURN` | End assistant turn immediately |
| `CONTINUE` | Move to named unit or phase |
| `DISPATCH` | Invoke a named sub-agent or worker contract |
| `RETURN` | Return a manifest, report, checkpoint, or handoff |
| `FORBID` | Disallowed action |
| `REQUIRE` | Required precondition |
| `RULES` | Mandatory constraints |
| `ON_ERROR` | Error recovery |
| `INVARIANTS` | Conditions that must always hold |
| `NOTES` | Non-executable explanation |

Prefer `MUST` and `MUST_NOT` inside `RULES` and `INVARIANTS`.

---

## Conditions

Conditions use plain expressions, not code syntax.

```text
WHEN:
  SUB_AGENT_SESSION_APPROVED == unset
  AND host.supports_native_subagents == true
```

Allowed operators:

- `==`, `!=`
- `AND`, `OR`, `NOT`
- `exists(<name>)`
- `contains(<value>, <token>)`
- `matches(<value>, <pattern-name>)`

Pattern names MUST be defined nearby or in a referenced requirement.

File-scoped patterns MAY be declared in a local `PATTERNS:` block at the top
of the PDSL file. Patterns intended for reuse across files MUST be registered
in `requirements/pdsl-patterns.md`.

---

## PATTERNS Block

A `PATTERNS:` block declares named patterns for use in `matches()` conditions.

```text
PATTERNS:
  slug-format: /^[a-z][a-z0-9-]{0,62}$/
    description: Lowercase kebab-case identifier, 1-63 chars
  semver-tag: /^\d+\.\d+\.\d+$/
    description: Strict three-part semantic version tag
```

Rules:

- A `PATTERNS:` block is file-scoped. It MUST appear before the first `UNIT`
  that references it.
- Pattern names MUST be unique within a file.
- Patterns shared across multiple files MUST be registered in the canonical
  patterns registry at `requirements/pdsl-patterns.md`.
- A `matches()` call MUST reference a name defined in the local `PATTERNS:`
  block or in the canonical registry. Undefined names are a PDSL authoring
  error.

---

## Actions

Actions are imperative and one per line.

```text
DO:
  REQUIRE workflow_target is known
  SET INLINE_FALLBACK = true
  EMIT_MENU ApprovalMenu
  WAIT user.reply
  STOP_TURN
```

Use `SET` only for state changes. Use `EMIT` or `EMIT_MENU` only for visible
UX output. Use `STOP_TURN` whenever the next step must wait for the user.

---

## Menus

Menus are first-class behavior, not prose.

```text
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

- Every option MUST have an action.
- Invalid input MUST be specified.
- If the menu is a hard interaction boundary, it MUST end with `STOP_TURN`.
- Suggested options belong in `TITLE` or `NOTES`, not hidden in prose.

---

## State

State declarations list allowed values and default behavior.

```text
STATE:
  CF_PHASE_GATE: armed | released_for_dispatch | released_for_inline_write
    default: armed
    reset: start_of_assistant_turn

  INLINE_FALLBACK: unset | true | false
    default: unset
```

State rules:

- Every referenced state variable SHOULD be declared in the nearest relevant
  `STATE` block.
- Defaults MUST be explicit when missing state changes behavior.
- Reset rules MUST be explicit when state is scoped to a turn, workflow, or
  session.

---

## Invariants And Forbids

Use `INVARIANTS` for always-on rules.

```text
INVARIANTS:
  - MUST keep CF_PHASE_GATE = armed outside released write windows
  - MUST reset CF_PHASE_GATE to armed after dispatch returns
  - MUST_NOT write files while CF_PHASE_GATE == armed
```

Use `FORBID` inside `DO` when a prohibition is local to that unit.

```text
DO:
  FORBID apply_patch while CF_PHASE_GATE == armed
```

---

## Error Handling

Error handling must be part of the same unit when failure changes control flow.

```text
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

```text
NOTES:
  Native sub-agents preserve context isolation and parallelism. Inline fallback
  is slower and weaker, but allows the workflow to continue without host
  support.
```

LLMs MUST NOT infer extra rules from `NOTES` unless another executable block
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

```text
UNIT SubAgentApprovalGate

PURPOSE:
  Resolve whether this workflow may use native sub-agents.

STATE:
  SUB_AGENT_SESSION_APPROVED: unset | true
    default: unset
    scope: session

  INLINE_FALLBACK: unset | true | false
    default: unset
    scope: workflow_run

WHEN:
  SUB_AGENT_SESSION_APPROVED == unset

DO:
  EMIT_MENU SubAgentApprovalMenu
  WAIT user.reply
  STOP_TURN

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
  - MUST_NOT set INLINE_FALLBACK = true from missing approval
  - MUST_NOT set INLINE_FALLBACK = false unless SUB_AGENT_SESSION_APPROVED == true
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
