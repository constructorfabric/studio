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
| `TYPE` | Declared gate risk: `confirmation`, `decision` or `blocking` |
| `OPTIONS` | Valid menu choices and their actions |
| `INVALID` | Invalid menu input handling |
| `WAIT` | Stop for user input |
| `STOP_TURN` | End assistant turn immediately |
| `CONTINUE` | Move to named unit or phase |
| `CONTINUE … after user.reply` | Deferred move, taken when the turn resumes |
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
`RULES`, or `INVARIANTS` for absolute prohibitions. Keep unit-local
execution-path prohibitions in `DO`; move remaining always-on constraints into
`RULES` or `INVARIANTS`.

Structured execution sections use list items. Each top-level item starts with
one of the section's allowed starter keywords:

- `STATE`: `SET`
- `WHEN`: `REQUIRE`, `AND`, `OR`, `NOT`
- `DO`: `SET`, `LOAD`, `RUN`, `EMIT`, `EMIT_MENU`, `WAIT`, `STOP_TURN`,
  `CONTINUE`, `DISPATCH`, `RETURN`, `REQUIRE`, `NEVER`
- `RULES` and `INVARIANTS`: `ALWAYS`, `NEVER`
- `OPTIONS`: a decimal number such as `1`, `2`, `3`

A top-level item may either lead with a dash (`- SET x = true`) or omit it
(`SET x = true`), as long as it sits at the section's top-level indent. Both
forms are validated identically — the same starter-keyword rule and the same
compactness cap apply either way. For example, these two `DO` blocks are
equivalent:

```pdsl
DO:
  - RUN check input
  - RETURN ok
```

```pdsl
DO:
  RUN check input
  RETURN ok
```

Continuation lines and nested explanatory bullets may appear under a list item,
but they do not introduce new PDSL actions or rules — regardless of dash usage,
a continuation line is any line at that item's own indent or deeper that does
not itself start with a top-level starter keyword.

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
- `LOAD and RUN <target> as controlling protocol` loads the referenced
  protocol and immediately transfers execution to it as the active
  controlling protocol.
- `RUN` executes a named local unit, probe, check, or workflow step.
- `WAIT` plus `STOP_TURN` is a hard assistant-turn boundary.
- `CONTINUE <unit-or-phase>` transfers control to that target; it is not
  optional advice.
- `CONTINUE <unit-or-phase> after user.reply` defers that transfer to the turn
  which resumes after the boundary, and **must be written before the `WAIT` it
  defers past** — a `CONTINUE` placed after `WAIT`/`STOP_TURN` is unreachable,
  because the boundary has already transferred control. Use it where a branch
  must collect a reply and then continue somewhere other than where it stopped.
  **Defined here only for a clause carrying a single boundary.** Four cases are
  deliberately left open: a block holding more than one `WAIT`, two deferred
  continuations before one boundary, control leaving the branch before the
  boundary is reached, and a boundary never reached at all. Both present uses
  carry exactly one boundary, so the corpus does not settle any of the four, and
  binding them would need an enforced check rather than a sentence.
- `DISPATCH` invokes a named sub-agent or worker contract. Concurrency,
  isolation, and join behavior belong in explicit dispatch options or
  surrounding rules, not in separate dispatch keywords.
- `RETURN` declares the terminal handoff or output shape.
- `RULES` are mandatory constraints for the owning unit.
- `INVARIANTS` stay active while the owning unit, workflow, or dispatch
  contract is active.
- `NOTES` are explanatory only; they do not create executable obligations
  unless an active rule references them.

Every workflow that contains PDSL control flow owns loading the compact runtime
card from `{cf-studio-path}/.core/skills/studio/modules/runtime/pdsl-execution-card.md`
during its bootstrap before later actions depend on PDSL runtime semantics.
Shared modules and agent prompts may rely on the workflow/controller-provided
slice instead of re-declaring the card path locally.

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

Prefer `DO` for mandatory behavior whenever the requirement can be written as
an ordered action. Use `RULES` only for constraints that cannot be represented
cleanly as `DO` steps without losing meaning or introducing fake sequencing.

Keep each `UNIT` compact. Count this limit as top-level `DO` actions only; do
not count continuation lines under the same action. If a unit needs more than
7 top-level `DO` actions, refactor it into narrower `UNIT`s, use `RUN` for
reusable helper behavior, and use `CONTINUE` for phase or ownership transfer.

Do not redundantly restate behavior between `DO` and `RULES` on the same
behavior path. Put imperative execution in `DO`, then use `RULES` only for the
non-redundant constraints that remain; factor shared constraints when
practical.

---

## Rules

`RULES` declare mandatory constraints that stay active for the owning unit.

```pdsl
RULES:
  - ALWAYS load required references before review
  - NEVER dispatch authoring work after a required bootstrap failure
```

Major authoring rules:

- Define `RULES` only when the behavior cannot be represented cleanly as `DO`
  actions.
- Keep `RULES` compact. A `RULES` block may contain at most 5 rules; if more
  are needed, refactor into narrower units with the correct rule scope, or
  elevate truly cross-cutting constraints to `INVARIANTS`.
- Do not redundantly restate the same behavior on the same behavior path
  across `RULES` blocks; factor shared constraints when practical.
- Do not restate a `DO` action as a `RULES` item unless the rule adds a
  distinct always-on constraint that the action alone cannot express.

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

### Declared gate risk

A menu may declare how much authority it carries, so the decision is read from
source rather than re-derived while running.

```pdsl
MENU PlanApprovalGate:
  TITLE: Approve this plan?
  TYPE: blocking
  OPTIONS:
    1 approve -> CONTINUE CurrentWorkflow
    2 revise -> CONTINUE PlanRevision
  INVALID:
    EMIT "Reply with 1 or 2."
    WAIT user.reply
    STOP_TURN
```

| `TYPE` | meaning |
|---|---|
| `confirmation` | the workflow has already derived the answer, **and the action it takes is reversible** |
| `decision` | the answer changes the work product |
| `blocking` | irreversible, external, or permission-expanding |

Rules:

- `TYPE` is a **static constant**: one bare lowercase token from the table
  above, never interpolated, never a variable, never carrying a `WHEN` clause.
  Where risk genuinely differs by entry mode, emit two differently-typed menus —
  subject to the constraints on splitting recorded in
  `cpt-studio-adr-autonomous-default-and-gate-risk`, which a lint cannot check.
- At most one `TYPE` per menu.
- **`TYPE` may be omitted.** An undeclared menu is valid, and a *newly added*
  menu must declare one, so menus migrate one at a time and the undeclared set
  can only shrink.
- **What an omitted `TYPE` means at runtime is not implemented here, and this
  spec does not claim otherwise.** Nothing reads a declaration today, in any
  mode: the rules above are lint only. The intended contract is that an
  undeclared menu is treated as `blocking` — the conservative direction, in
  which a gate asks rather than proceeds.
- **Nothing resolves a gate from a declared type today**, so this lint changes
  no runtime behaviour. Three shipped paths *do* auto-resolve gates, and none of
  them reads a declaration: assistant mode's own auto-selection rule
  (`skills/studio/modules/gates/simple-mode-rules.md:19`), the autonomy overlay
  (`workflows/brave-new-world.md`), and sub-agent dispatch's pre-set rule
  (`skills/studio/modules/subagents/dispatch.md:43`), all of which decide by
  runtime judgement. So an undeclared menu is **not** fail-closed today — it is
  subject to those three paths exactly as it was before this change.
- **Enforcing the default here would not make it true.** A lint cannot bind
  either path; both must be retired or bound to declared types by the change
  that introduces declaration-driven resolution, which is where the obligation
  and a test asserting that an omitted `TYPE` produces blocking behaviour
  belong. Until then, omission is *unvalidated*, and the safety of the
  grandfathered set rests on those three paths being narrow and reviewed — not on
  a default that has been demonstrated.
- **`TYPE` is read only in the menu's declaration region:** from the menu
  header up to the first section that is not `TITLE` or `TYPE`. A declaration
  outside a menu, nested in its body, or trailing it is inert, and is reported
  rather than ignored.
- **A line indented deeper than the menu's other sub-headers is continuation
  text of the header above it**, not a header of its own — so a title running
  onto a second line is read as title text. A `TYPE:` written there is not read
  as the declaration, and a near-miss written there is not reported. The level
  is taken from the menu's first sub-header, whichever that is, and measured per
  menu rather than per block — **that first sub-header's own indentation sets the
  level even where it is itself over-indented**, and the exemption below changes
  whether a header is a section, never whether it sets the level. **`TITLE:`, `OPTIONS:` and `INVALID:` are exempt
  from this rule** and keep their section status at any indentation, so an
  over-indented `OPTIONS:` still ends the region and a `TYPE:` after it is
  inert — reported as a declaration nothing reads. Every other recognized
  header is subject to it: an over-indented `NOTES:` is continuation text, so the
  region has *not* ended — and a `TYPE:` after it is read **only if that `TYPE:`
  itself sits at the level**, since a `TYPE:` indented deeper is continuation
  text by this same rule. Resolve the two rules in that order — the exemption
  first, then the region-ending rule below.
- **Any recognized section other than `TITLE` or `TYPE` ends the region** — `OPTIONS:`,
  `INVALID:`, and also `NOTES:`, `RULES:`, `ON_ERROR:`, `PURPOSE:` and the
  rest. Unrecognized prose headers such as `NOTE:` and `ELSE:` do not. So put
  `TYPE` before `NOTES:`, not after it.
- A sub-header **in that region** that is a near-miss of `TYPE` is an error, so
  a typo cannot silently leave a gate undeclared. Reported: a misspelling
  (`TYP:`, `TPYE:`), a miscasing (`Type:`) when its value is a gate type,
  decoration around the name (`- TYPE:`, `` `TYPE:` ``, `[TYPE]:`,
  `**TYPE:**`), a separator other than `:` (`TYPE = blocking`,
  `TYPE -> blocking`) or none at all (`TYPE blocking`), an invisible or
  confusable character in the name, and a rejected alternative (`RISK:`,
  `GATE_TYPE:`).
- Detection is by edit distance 1 from `TYPE`, counting a transposition as one,
  after folding case and trimming `_`/`-` from the ends, plus that alias list.
  The trimming means many decorated spellings reduce to `TYPE` and are caught,
  so the radius is wide; what matters to an author is which *words* fall in it.
  The ordinary English words are `HYPE`, `TAPE`, `TYKE`, `TYPED`, `TYPES`,
  `TYPO` and `TYRE`; `RISK` is flagged deliberately. `GATE:` is **not**
  flagged: in a codebase about gates it is a plausible sub-header.
- **The boundary, stated rather than implied.** Decoration is discarded, not
  listed, so the set of decorated forms is open-ended. What is *not* detected
  is a declaration with another token embedded in it — `1. TYPE:`,
  `- [x] TYPE:`, `<b>TYPE</b>:`, `TYPE(gate):` — a near-miss **outside** the
  region, which is read as prose, a declaration or near-miss written as
  **continuation text**, indented past the menu's other sub-headers, and a name
  spelled in lookalikes this map does not carry at **two or more** positions
  (`ᴛʏPE:`, `ᴛʏᴘᴇ:`), which sit outside the distance-1 radius — one such letter
  is still caught by distance, and any number of *mapped* ones fold to `TYPE`
  and are caught too. That last limit is deliberate rather than pending: PDSL
  is authored in ASCII, so widening the rule would trade a spelling nobody
  writes for false positives on prose in another script. In every such case the
  gate is left undeclared, and therefore `blocking` **under the model this spec
  records** — the failure direction is more friction, never more autonomy. That
  is the contract rather than current behaviour: as stated above, an undeclared
  menu is not fail-closed today, because three shipped paths still resolve one
  by runtime judgement.
- Everything else is prose, in the region or out of it: `NOTE:`, `NOTES:` and
  `ELSE:`, any lower- or mixed-case line whose value is **some other token**
  (`type: skill`, `**Type**: CLI`), and any line with neither a separator nor a
  gate type as its value (`Tape recorder notes`).
- An **empty** value is not prose. `type:` and `Type:` are reported as near-misses
  and `TYPE:` as a non-literal, because a header written with its separator and
  nothing after it is an abandoned declaration rather than front matter — the one
  case where a lower-case candidate is reported despite its value not being a gate
  type.

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
4. Convert imperative required behavior into `DO` first; define `RULES` only
   when the constraint cannot be represented cleanly as `DO` actions.
5. Convert remaining always-on "must/always" constraints into `RULES` or
   `INVARIANTS`; keep unit-local `NEVER` constraints in `DO` when they apply
   only to a specific execution path.
6. Keep each `UNIT` compact: maximum 7 top-level `DO` actions. Continuation
   lines under one action do not increase the count. If more are needed,
   refactor into narrower `UNIT`s.
7. Keep each `RULES` block compact: maximum 5 rules. If more are needed,
   refactor into narrower units with the correct rule scope, or elevate truly
   cross-cutting constraints to `INVARIANTS`.
8. Do not redundantly restate behavior on the same behavior path between
   `RULES` blocks or between `RULES` and `DO`; factor shared constraints when
   practical.
9. Keep rationale in `NOTES`.
10. Do not hide required behavior in paragraphs after the DSL block.

If behavior is too complex for one unit, split it into multiple `UNIT` blocks.
Use `RUN <unit-name>` for reusable helper behavior and `CONTINUE <unit-name>`
for phase or ownership transfer.

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
