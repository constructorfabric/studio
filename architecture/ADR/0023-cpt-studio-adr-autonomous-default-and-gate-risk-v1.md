---
status: accepted
date: 2026-09-04
decision-makers: project maintainer
---

# ADR-0023: Autonomous Interaction Default and Declared Gate Risk

**ID**: `cpt-studio-adr-autonomous-default-and-gate-risk`

<!-- toc -->

- [Context and Problem Statement](#context-and-problem-statement)
- [Decision Drivers](#decision-drivers)
- [Considered Options](#considered-options)
- [Decision Outcome](#decision-outcome)
  - [Interaction modes](#interaction-modes)
  - [Mode lifetime](#mode-lifetime)
  - [Declared gate risk](#declared-gate-risk)
  - [The resolution invariant](#the-resolution-invariant)
  - [Recording an autonomous resolution](#recording-an-autonomous-resolution)
  - [The risk boundary](#the-risk-boundary)
  - [The governing consequence](#the-governing-consequence)
  - [What must exist before the default moves](#what-must-exist-before-the-default-moves)
  - [What this decision does not enforce](#what-this-decision-does-not-enforce)
  - [What closes each open gap](#what-closes-each-open-gap)
  - [Relationship to ADR-0018](#relationship-to-adr-0018)
  - [Consequences](#consequences)
  - [Confirmation](#confirmation)
- [Pros and Cons of the Options](#pros-and-cons-of-the-options)
  - [Autonomous default with statically declared gate risk types (chosen)](#autonomous-default-with-statically-declared-gate-risk-types-chosen)
  - [Runtime risk derivation](#runtime-risk-derivation)
  - [No default change; reduce menus case by case](#no-default-change-reduce-menus-case-by-case)
- [Related ADRs](#related-adrs)

<!-- /toc -->

## Context and Problem Statement

Constructor Studio turns routine workflow mechanics into chat gates: mode
selection, exploration, brainstorming, planning, plan storage, and internal
dispatch. A concrete, low-risk request can pass several menus before any work
begins.

Two properties of the current runtime make that worse than it needs to be. The
session-opening mode gate stops the first turn, and the option it suggests —
`normal` — is a documented no-op: `skills/studio/modules/gates/simple-mode-normal.md:12`
reads *"NEVER add simple-mode explanations or automatic selections while
SIMPLE_MODE == normal"*. And an autonomous-by-default overlay already exists —
`workflows/brave-new-world.md` — but it is opt-in, and its eligibility module
derives risk per menu at runtime and explicitly rejects requiring a declared
marking, which is why this decision cannot simply enable it.

Nothing in ADR-0001 through ADR-0022 covers interaction modes, so both the
default and any risk model would otherwise be introduced with no recorded basis.

The requirement this decision serves is #128, which also carries the
reachability walk over the gate surface. The PDSL rule wording that prerequisites
1 and 2 below depend on is #148. This record states the decision and the
obligations it creates; it deliberately does not restate per-site counts or
measured stop counts, which go stale and are not what is being decided.

## Decision Drivers

- **Reviewability** — whether a gate may resolve autonomously must be decidable
  from a declaration in source, not from a judgement made while running.
- **Reversibility of the default** — changing the default changes behaviour for
  every existing user, so the previous behaviour must survive under a name.
- **Backward compatibility for kits** — installed kits must not change
  behaviour until their author opts in, gate by gate.
- **An unmoved risk boundary** — reducing questions must not reduce what is
  checked.
- **Verifiability** — an autonomous run must be checkable against something the
  user agreed to, or "correct" is undefined.

## Considered Options

- **Autonomous default with statically declared gate risk types (chosen)** —
  each gate declares its risk in source; the mode selects how that declared
  authority is exercised.
- **Runtime risk derivation** — keep deciding per menu while running, as the
  existing overlay does, and simply enable it by default.
- **No default change; reduce menus case by case** — leave the interaction
  model alone and remove individual gates as they are complained about.

## Decision Outcome

### Interaction modes

Four named modes. `guided` is distinct from `assistant`; without that
distinction the current `normal` behaviour would have no name and would be
silently removed.

| presented as | `SIMPLE_MODE` token | behaviour |
|---|---|---|
| autonomous | `normal` | the default; gates declared `confirmation` resolve without asking, and `decision` gates resolve from an approved, keyed source by exact match — both recorded when logging is enabled. A `blocking` gate always asks |
| guided | **`guided`** (new) | the behaviour `normal` carries today — every workflow menu, gate and stop intact, without narration. The one exception is the session-mode gate this decision removes, which no mode restores |
| assistant | `simple` | narrated; explains each step and recommends a path |
| debug | `debug` | the debugger overlay on top of `guided` gate behaviour — see the matrix below |

**Mode by declared type**, so no combination is left to interpretation. Only the
autonomous default resolves a gate from its declared type; every other mode asks,
whatever the type says. That is the governing consequence applied: a declaration
grants authority, and only one mode exercises it.

| declared type | autonomous | guided | assistant | debug |
|---|---|---|---|---|
| `confirmation` | resolves without asking; recorded | asks | asks, narrated | asks |
| `decision` | resolves from the approved keyed source, else asks; recorded | asks | asks, narrated | asks |
| `blocking` | asks | asks | asks, narrated | asks |
| undeclared | treated as `blocking` — asks | asks | asks | asks |

`debug` adds breakpoint pauses to `guided`'s behaviour rather than replacing it,
which is what "unchanged by this decision" means: its own overlay is untouched,
and it inherits the asking behaviour rather than the autonomous one. `assistant`
keeps narration and loses the auto-selection rule this decision supersedes.

`normal` **keeps its token and changes meaning**: it becomes the autonomous
contract, and the content that `gates/simple-mode-normal.md` holds today moves
to `guided`, so the previous behaviour survives by name rather than being
deleted — minus the session-opening mode gate, which this decision removes for
every mode and which `guided` therefore does not restore. Rebinding the token
rather than giving the comparisons a new meaning is deliberate — every
`SIMPLE_MODE == normal` site today guards the behaviour that becomes `guided`.
The `STATE` enum at `skills/studio/modules/gates/simple-mode.md:7` gains the
token.

Separating token from presented name is an existing pattern rather than a new
one: `skills/studio/modules/gates/simple-mode-rules.md:9` already requires the
runtime to *"present this mode to the user as `assistant` or `assistant mode`,
never as `simple mode`"* — scoped, in that rule, to copy emitted while
`SIMPLE_MODE == simple`.

The `EMIT_MENU SimpleModeChoice` / `WAIT` / `STOP_TURN` trio at
`skills/studio/modules/gates/simple-mode.md:19-21` is **removed**: the active
mode is **announced, not asked**. The runtime states the mode it selected so the
user may override it, rather than stopping the first turn to ask.

What becomes of the `MENU SimpleModeChoice` block itself is **not decided here**.
Whether the override is a menu re-emitted on request, a directly named mode, or
something else is the design of the trigger-set unit in prerequisite 1, and
belongs with its owner.

**The announcement MUST precede the first autonomous resolution in the session
transcript.** An override received afterwards applies from that point and does
not undo prior resolutions. Announcing after the first resolution, or in the same
breath as reporting it, would make the override unreachable and is **forbidden**.
That ordering rule is acceptable only because a `confirmation` gate's action is
reversible — which is why reversibility is part of the `confirmation` contract
below rather than a rationale offered for it.

`assistant` keeps its narration but **not** its auto-selection:
`skills/studio/modules/gates/simple-mode-rules.md:19` instructs the runtime to
*"choose automatically only when the option is non-destructive, reversible,
low-impact, unambiguous, and the agent has high confidence that it matches the
user's stated goal"*, which this decision supersedes — after it, autonomy comes
from a declaration rather than from that rule. The narrowness that rule relies
on today lives at `:21`, which forbids auto-selecting commits, pushes, history
rewrites and *"sub-agent dispatch approvals"* among others.

### Mode lifetime

**Mode is session state.** A cancel, an error, an off-protocol reply, or a new
task does not reset it; only an explicit request to change mode does. This is
recorded because its absence has already cost: #148 documents a field incident
in which one step off the golden path silently reset the interaction contract,
because mode persistence lived nowhere.

**Across sessions it does not persist.** There is no stored per-user mode to
inherit, so **a session cannot silently start more autonomous than the default**,
and concurrent sessions each hold their own mode independently. A persisted mode
would be precisely the *"cached resolution state that is no longer valid for the
current inputs"* that the resolution invariant below rejects.

**On the word "session".** Mode takes PDSL's existing `scope session` lifetime —
the same one the runtime already gives 48 other declared state variables across
nine modules. This record deliberately does not define that boundary: the term is
used repo-wide and undefined, and fixing it here would change the meaning of
every session-scoped variable rather than only mode. What this decision does pin
is the single property it depends on: a mode is never inherited from an earlier
session, so whatever a session turns out to be, a new one begins at the default
and announces it.

At session start the mode resolves from, in order: an explicit request in this
session; otherwise the default. A workspace or kit configuration tier **is
deliberately reserved and not implemented** — no such key exists today, and
adding one would require amending this record. `unset` is a sentinel rather than
a fifth mode: it resolves to the default and is announced as such, so **no entry
path can begin without an announced mode**.

### Declared gate risk

Every gate declares a risk type as a **static constant** of its `MENU` block,
never computed at runtime. The grammar is not invented here: the declaration is
a `TYPE:` sub-header inside the menu's declaration region — from the `MENU`
header to its first other section — whose value is one of the three literals,
written `TYPE: blocking`. That grammar **landed on `main` via #153** (merged
2026-09-08), which added it to `architecture/specs/PDSL.md` — including what
counts as a near-miss of it — and implemented the lint that validates it. This
record fixes the model; #153 fixed the syntax, so a lint and a reviewer check
the same thing.

"Gate" here means a menu: a bare `STOP_TURN`, a
`WAIT user.reply` and an approval `REQUIRE` are statements rather than menus, so
they carry no declaration and stay blocking. That is intended, and stated so it
is not mistaken for an omission.

`GitCommitModeGate` and the sub-agent dispatch gates are **not** in that
category — each resolves through a menu (`MENU GitCommitModeMenu` at
`skills/studio/modules/subagents/git-commit-mode.md:125`; `MENU
SubAgentApprovalRequest`, `SubAgentFallbackRequest` and
`SubAgentFallbackLimitRequest` at `skills/studio/modules/subagents/dispatch.md:44`,
`:53`, `:60`), so all four can carry a declaration and all four are in scope.
Being declarable does not make them autonomous: git mutation is in the blocked
set referenced below, so those gates are `blocking` unless and until an author
declares otherwise within that boundary. Nor is each of them *enforced* today,
though only one is affected: `dispatch.md:43` lets a caller pre-set the group
decision, which suppresses
`SubAgentApprovalRequest` — its `EMIT_MENU` at `:103` is guarded on that
variable being unset. That is the third of the three paths named under *What
this decision does not enforce*, and until it is bound that gate is declarable
but still bypassable. The two fallback menus are guarded on dispatch failure and
retry count rather than the group decision, and `GitCommitModeMenu` on
`GIT_COMMIT_MODE == unset` with no caller pre-set path, so neither is
suppressible this way.

| type | means | autonomous behaviour |
|---|---|---|
| `confirmation` | the answer is already derived, the action is reversible, **and the work product does not change** | resolves without asking; recorded |
| `decision` | the answer changes the work product, **even when it is reversible** | resolves from an approved, keyed source; otherwise asks |
| `blocking` | irreversible, external, or permission-expanding | never resolves autonomously |

Where two types appear to fit, the more restrictive governs, in this order:
irreversible, external or permission-expanding is `blocking` whatever else is
true; then a gate whose answer changes the work product is `decision`;
`confirmation` only where none of that holds.

**Reversibility is part of the `confirmation` contract, not a rationale for
it.** An action that is irreversible, externally visible or permission-expanding
MUST NOT be declared `confirmation` whatever the workflow has derived; it is
`blocking`. The set that may not be `confirmation` is the whole
`BraveNewWorldBlockedChoice` invariant list at
`skills/studio/modules/brave-new-world-eligibility.md:33-43` — in full, by
reference. This record does not enumerate that list, because any subset silently
narrows the boundary; the three adjectives in the table above define the type,
they do not bound the set. A lint cannot decide reversibility, so this binds the
reviewer of any change that adds or retypes a declaration.

**Splitting is constrained**, because it is the one sanctioned way around
single-gate typing: an author could otherwise split a `decision` or `blocking`
gate into a `confirmation` gate for the common path plus a narrow alternate. So:

- the selector between the two gates MUST itself be declared state — never a
  judgement made while running
- the two gates MUST be emitted from distinct, statically determinable branches;
  a single emit site whose type varies is the runtime derivation this decision
  rejects
- **the more autonomous of the two MUST NOT be reachable on the path the less
  autonomous one exists to protect**

Any change introducing a second gate that differs only in type is a review focus.
Like reversibility, no lint decides this.

An **undeclared gate is treated as `blocking`**. Failure is therefore toward
more friction, never more autonomy.

### The resolution invariant

> A `decision` gate may resolve autonomously **only** from a structured,
> explicitly keyed source using exact-match semantics. Resolution must not infer
> intent from prose, use similarity matching, normalize values at lookup time,
> or rely on cached resolution state that is no longer valid for the current
> inputs.

The source must be one the user **approved**. The invariant above constrains its
shape; approval is what makes an autonomous run checkable against something the
user agreed to, which is the Verifiability driver. A keyed source nobody approved
does not satisfy this decision.

### Recording an autonomous resolution

**When logging is enabled, every permitted autonomous resolution is recorded.**
An auditor must be able to recover **which gate** resolved, **the literal
declared type** it resolved under, **what the resolution was taken from**, and
**the core version the declaration was read at** — without those four, the event
cannot be checked back against the source that authorised it. The record's field
set is an implementation contract and may evolve without amending this ADR.

Two invariants, tested independently: **no unauthorised resolution**, and **no
unrecorded autonomous resolution**. A failure to write the record violates the
second without retroactively making the resolution illegal — it is a logging
defect, not a withdrawal of the permission. #148 carries this split as proposed
rule text.

**Choosing that direction rather than fail-closed is deliberate, and it has a
cost.** If a failed write voided the resolution, a logging outage would silently
withdraw authority the declaration had already granted, and the log would become
a dependency of every autonomous step rather than a record of it. The cost
accepted instead is that a failed write leaves an autonomous action unrecorded —
which is why *no unrecorded autonomous resolution* is stated as an invariant in
its own right rather than folded into the first as an implementation detail. A
durable outbox would remove the trade-off and is not specified here; that
belongs with the change that provides the write path.

Three limits are real rather than glossed. Logging is user-disableable
(`CFS_DECISION_LOG` off-values, or a `~/.cf-studio/decisions.off` sentinel), so
what an opted-out session may do autonomously is a question this decision does
not answer. The log rotates at a size cap, keeping a single backup, so **an
auditor's window is bounded**. And it is a CLI-side module with no path yet named
from a chat gate to `record()`.

### The risk boundary

A `blocking` gate may be passed **only** by a fresh explicit user authorisation
satisfying that gate. No plan entry, ledger entry, recorded decision, mode,
workflow recommendation, or prior authorisation resolves it. *Auto-proceed* and
*proceed after explicit approval* are distinct: `guided` permits the second, and
**no mode permits the first for a `blocking` gate**. Autonomous permits it for
`confirmation`, and for `decision` where an approved keyed source matches
exactly; never for `blocking`. That is the whole distinction being drawn.

Deterministic validators, prerequisite checks, capture policies and closing
audits run identically in every mode:

> **Autonomy changes who answers the questions, never what gets checked.**

### The governing consequence

> **Autonomous mode does not grant authority; it selects how already-declared
> authority is exercised.**

A mode never widens what Studio may do. The declared type fixes what a gate
permits; the mode determines only who exercises it.

### What must exist before the default moves

Four things, none of which exists today:

1. a **declared, closed set of mode-change triggers** and a unit that handles
   them, owned by `skills/studio/modules/gates/simple-mode.md`, which already
   owns mode selection. Today `simple-mode.md:28` promises "change mode" in a
   menu title with no unit behind it, while `workflows/brave-new-world.md:42`
   activates on open-ended *"semantically equivalent phrases"* and its `WHEN`
   carries no `SIMPLE_MODE` guard, so it fires under the autonomous default too.
   The two trigger sets MUST be disjoint, and a reply matching nothing in the
   declared set MUST NOT change mode. The set itself is not enumerated here;
   #148 carries the proposed wording, including recognising a literal phrase
   rather than semantic variants, and is where disjointness against the overlay's
   activation phrases can be checked. Naming the owner rather than specifying a
   grammar is deliberate: a trigger set invented in this record, without the unit
   that recognises it, would be one more undeclared source of runtime judgement.
   Until that unit exists the announced override is not reliably reachable, which
   is why the default must not flip before it.
2. **amendments narrowing the two runtime laws** —
   `skills/studio/modules/runtime/pdsl-execution-card.md:28-33`, which forbids
   reinterpreting a reply as broad permission, and
   `skills/studio/modules/runtime/active-workflow-state-law.md:7`, which makes
   every message workflow input rather than *"permission for generic autonomous
   behavior"*. Both are correct as written and are narrowed, not deleted; #148
   holds the proposed wording.
3. the **approved, keyed source** that `decision` gates resolve against. Its
   contract must define three things, because approval alone is not sufficient:
   **source identity** — which sources are approved, as an allowlist or an
   equivalent identity rule, so "approved" is decidable rather than asserted;
   **provenance** — how a source's approval is established and by whom; and
   **binding to the current inputs**, so a source that was approved for a
   different state cannot resolve this gate. The resolution invariant already
   forbids resolving from *"cached resolution state that is no longer valid for
   the current inputs"*, which is the freshness half of that third property; the
   other two have no home until this source exists.
4. a **write path from a chat gate to `record()`**. Recording every permitted
   autonomous resolution is mandatory above, and no such path exists, so flipping
   the default without it would produce exactly the unrecorded autonomous
   resolutions the second invariant forbids. It is a prerequisite rather than a
   consequence, and an earlier draft of this record filed it as the latter. Its
   contract must also make a failed write **detectable**: an invariant whose
   breach cannot be observed is not enforceable, and the fail-open choice above
   is only defensible if someone can tell it has happened.

The default flip is what these are prerequisites *of*, not a member of the list.
It is the first change that reads a declared type, and is called the
**default-flip change** throughout.
Accepting this record ahead of all four is deliberate: the decision has to be
reviewable before anything is built against it.

Four artifacts pin the current mode set and move with the flip rather than with
this record: `architecture/overview/agent-runtime.md`, `README.md`,
`guides/USAGE-GUIDE.md`, and `tests/test_workflow_subagents_dispatch.py`, which
asserts the mode enum and the session-opening mode gate that this decision
removes.

### What this decision does not enforce

Recording this decision does not itself alter runtime behaviour. Gate typing is
now **in progress** rather than unstarted — a growing set of menus declare a
`TYPE`, the grammar #153 made possible — but **nothing resolves a gate from its
declared type at runtime yet**. The resolution chain this decision specifies
exists as library code (`skills/studio/scripts/studio/utils/gate_chain.py`);
its safety and economy filters are landing in increments, but the chain has no
caller outside its own test suite, so every gate — typed or not — still stops
and asks exactly as before. An undeclared gate is therefore **not fail-closed
today** — three shipped paths resolve undeclared gates by runtime judgement:

- `skills/studio/modules/gates/simple-mode-rules.md:19` — assistant mode's
  auto-selection rule, with no overlay and no declaration involved
- `workflows/brave-new-world.md` — the autonomy overlay, whose eligibility
  module explicitly rejects requiring a declared marking
- `skills/studio/modules/subagents/dispatch.md:43` — a calling workflow may
  pre-set `SUB_AGENT_GROUP_DECISION = approve-once` from *"an explicit imperative
  with a named target artifact or operation … and no conditional or questioning
  language"*. The `EMIT_MENU`, `WAIT` and `STOP_TURN` at `:103-105` are each
  guarded on `SUB_AGENT_DISPATCH_MODE == unset AND SUB_AGENT_GROUP_DECISION ==
  unset`, so pre-setting the group decision alone suppresses all three

All three must be retired or bound to declared types **by the default-flip
change, as a required component of it rather than a follow-up** — a flip that
left any of them running would contradict the fail-closed default at the moment
it took effect, so the flip cannot land without all three. That change also
carries the test that an omitted type produces blocking behaviour. A lint over
source cannot bind any of them: a lint can check the syntactic half — that a
declaration present in source is a literal of the enum, in a slot that is read —
and cannot check that a running agent honours it.
Issue #128 tracks this obligation for the first two paths; the dispatch path is
not tracked anywhere yet.

The **compatibility boundary** is therefore not "no behaviour changes". A gate
that receives autonomous resolution from the overlay today becomes a mandatory
stop once undeclared means `blocking` — a behaviour change in the conservative
direction. No gate becomes more autonomous without its author declaring a type;
some become less autonomous until one does; nothing silently changes what is
checked.

### What closes each open gap

This table is the **open-gap register**: the complete list of what this decision
leaves open, and what later sections mean by "the register". It has a
stated relationship to the other two enumerations in this record: the
**prerequisite list** is the subset of these gaps that must close *before* the
default moves, and the **Confirmation table** is how acceptance of the decision
is checked, not a duplicate of this register. Every row either carries a
prerequisite number, meaning it must close first, or says that it does not block
the flip — except the first fail-closed row, which the flip itself resolves
rather than being blocked by.

Each gap is deferred to a named change rather than argued, so a reviewer can
check it off rather than re-litigate it. None of them closes by further wording
in this record.

| gap | closed by | the check that proves it |
|---|---|---|
| no declared mode-change trigger set exists | prerequisite 1 — the closed trigger set and its handling unit in `gates/simple-mode.md` | a reply matching nothing in the declared set leaves the mode unchanged, and the set is disjoint from the overlay's activation phrases |
| the two runtime laws forbid what that trigger set needs | prerequisite 2 — the amendments narrowing them | both laws admit a declared mode change while still refusing to read a reply as generic permission |
| undeclared gates are not fail-closed today | the default-flip change, once its four prerequisites are met | a `MENU` with no `TYPE` stops for fresh authorisation, in core and kit paths, with the three runtime paths retired or bound |
| no audit record is written for an autonomous resolution | the write path, prerequisite 4 | one record per permitted autonomous resolution, from which gate, literal declared type, resolution source and core version are all recoverable |
| the approved source set and its provenance are undefined | the plan-and-ledger work, prerequisite 3 | `decision` resolution tested against that store by exact match, and refused when the source carries no approval, when its provenance is not the approved one, or when it was approved against inputs other than the current ones |
| five kit `MENU` files sit outside the freeze — does not block the flip | extending the frozen roots to `.bootstrap/config/kits/sdlc/`, or a recorded exception naming the kit owner | the freeze covers all five, or the exception is recorded against an owner |
| the untyped inventory has no owner or target — does not block the flip | a planning act on the tracked inventory — not a code change | an owner and a target recorded, and the baseline reaching empty |
| the logging opt-out case is undecided — does not block the flip | the change that provides the write path, or a separate policy decision | a stated rule for what an opted-out session may resolve autonomously |
| the envelope has no core-version field — does not block the flip | the same change, extending `EVENTS` and the envelope | the core version the declaration was read at is recoverable from a record |
| no instrument measures whether autonomy changed what gets checked — does not block the flip | a per-run validator-invocation counter, compared across modes | the count is equal in every mode, compared at each release |
| no instrument measures the question count the decision exists to reduce — does not block the flip | a stop-count instrument; #128 records that counting stops from a driven transcript was tried and abandoned as non-reproducible, so hand-counted sessions are the honest measure until one exists | the count falls against a recorded baseline, compared at each release |

### Relationship to ADR-0018

ADR-0018 compiles Studio planning output into a plan an optional external runner
executes unattended. This ADR governs *interactive session* autonomy, which runs
natively. ADR-0018 is **bounded, not superseded**: its delegation remains valid
for unattended execution. Recording the boundary prevents two autonomy models
coexisting without a stated division.

### Consequences

**Positive**:

- autonomy is decided from source a reviewer can read and diff
- the previous behaviour survives under a name, minus the session-opening mode gate, so the default is reversible
- kits inherit autonomy by declaring types, at a time of their choosing

**Negative / risk**:

- every gate must eventually carry a declared type; until then legacy gates are
  conservative and therefore less autonomous than they could be. The inventory
  is tracked on #128, and #153 adds a test that freezes today's undeclared set
  and fails on a newly added one, so the surface can only shrink; completion is
  measurable as that baseline reaching empty. None of it is in CI until #153
  merges, and the freeze is that **test** — #153's lint validates a `TYPE`
  present in source and, by design, leaves an absent one valid. What is **not**
  fixed: a per-gate owner or schedule; and kit menus, five tracked files under
  `.bootstrap/config/kits/sdlc/` that carry `MENU` blocks outside the frozen
  roots and outside PDSL CI entirely, whose coverage is the kit owner's call.
- a mis-declared type is a behavioural defect no lint can catch, only a reviewer
- two decision-log obligations remain open and **neither blocks the default
  flip**, which is why they are recorded here rather than in the prerequisite
  list: the logging opt-out case — what an opted-out session may do autonomously
  — and a core-version field the current envelope has no slot for. An opted-out
  session and a missing version field both degrade the audit trail; neither
  permits a resolution the declaration did not already authorise, which is what a
  prerequisite has to prevent. The third obligation, the write path itself, does
  block the flip and is prerequisite 4. #148 carries the rule text and the
  two-invariant split, not these three.

### Confirmation

This table holds only criteria that someone can actually check, so that
"accepted" is falsifiable rather than asserted. Every row names the check, who
performs it, and when. A verifier is a **role**, not a named person: that is what
makes it statable before the work is assigned.

| criterion | checked by | verifier | when |
|---|---|---|---|
| a newly introduced untyped gate fails | the frozen-baseline test in #153 | the author of the change that breaks it | every pull request, once #153 merges |
| no `blocking` gate is passed by any path other than a fresh explicit authorisation | reviewer judgement; no lint can decide it | the reviewer of any change that adds or retypes a gate declaration | per change |
| an irreversible, externally visible or permission-expanding action is never declared `confirmation` | reviewer judgement; no lint can decide reversibility | the reviewer of any change that adds or retypes a gate declaration | per change |

**Everything else this decision would like to be true is an open gap, not a
criterion, and lives in the register above.** An earlier draft of this record
listed nine rows here. Six were not checks: four restated a gap the register
already carried, and two named a measurement whose instrument does not exist. A
table of checks containing things nobody can check is how "confirmed" stops
meaning anything, so they were moved rather than annotated. Nothing was dropped —
each is in the register with the change that closes it and the test that proves
it.

## Pros and Cons of the Options

### Autonomous default with statically declared gate risk types (chosen)

* Good, because autonomy is decided from a declaration a reviewer can read and diff.
* Good, because behaviour is reproducible: the same gate resolves the same way every run.
* Good, because undeclared gates fail safe — nothing becomes more autonomous without an author declaring it.
* Good, because the declaration is machine-readable, so the untyped surface cannot grow unnoticed inside the frozen roots.
* Bad, because it requires a migration pass across the existing gate surface.
* Bad, because a gate the overlay resolves today becomes a mandatory stop until its author types it.

### Runtime risk derivation

* Good, because it needs no migration and adapts to gates nobody anticipated.
* Bad, because the decision is invisible until after it has been made, in one session.
* Bad, because two similar gates may resolve differently, so defects are not reproducible.
* Bad, because it can only be tested through scenarios that happen to be imagined.
* Bad, because it is a classifier, which this change is explicitly not chartered to introduce.

### No default change; reduce menus case by case

* Good, because each removal is small and independently reversible.
* Bad, because the suggested mode stays a documented no-op that adds stops without adding help.
* Bad, because it offers kits no mechanism to inherit the improvement.
* Bad, because without a declared risk model each removal re-argues the same safety question.

## Related ADRs

- `cpt-studio-adr-ralphex-delegation-skill` — bounded by this ADR, not superseded
- `cpt-studio-adr-thin-skills-module-first`
- `cpt-studio-adr-ai-cli-extensibility-subagents`
