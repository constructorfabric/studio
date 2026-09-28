# `KEY:` Declared Gate Key — Implementation Design Note (2026-09)

<!-- toc -->

- [Purpose of this document](#purpose-of-this-document)
- [Why this is being proposed](#why-this-is-being-proposed)
- [Spec change](#spec-change)
- [Implementation touch-points (not yet coded)](#implementation-touch-points-not-yet-coded)
  - [`skills/studio/scripts/studio/utils/pdsl.py`](#skillsstudioscriptsstudioutilspdslpy)
  - [`requirements/plan-template.md`](#requirementsplan-templatemd)
  - [Cross-file uniqueness — the one piece with no `TYPE`/`SHAPE` precedent](#cross-file-uniqueness--the-one-piece-with-no-typeshape-precedent)
  - [Tests](#tests)
- [Resolved in review (PR #327, Sanjeev Solanki, 2026-09-28)](#resolved-in-review-pr-327-sanjeev-solanki-2026-09-28)

<!-- /toc -->

## Purpose of this document

This note accompanies the `KEY:` sub-header proposal added to
`architecture/specs/PDSL.md` ("Declared gate key"). It records where in the
existing validator that declaration would need to be wired, so the PR
captures the full picture — wording and implementation shape — in one place,
per HYP-2984 (a subtask of 2871). No code in this PR implements any of it;
Sanjeev Solanki has taken the follow-on implementation (PR #327 review,
2026-09-28) — this is the map he'll work from.

## Why this is being proposed

`skills/studio/scripts/studio/utils/gate_chain.py` (landed in #272, "the
autonomy filter chain skeleton, wired to nothing") already assumes a gate's
decision key exists as a fact a plan can answer — its own module docstring
states it as given: *"a plan can answer a decision key"*. `GateRuling`
(`skills/studio/scripts/studio/utils/decision_log.py:988`) already carries a
`decision_key: str` field, the first name in what its docstring calls "the
frozen resolution contract" (`decision_key → value → provenance → status`,
`architecture/features/core-infra.md`, `inst-log-gate-ruling`). The "later
increments" #272 names explicitly — "already-answered, plan-and-ledger" — are
the economy filters that would read a gate's key and check it against the
plan/ledger.

None of that machinery has anything to read from PDSL source today: nothing
lets a `MENU` declare the key a plan is expected to answer. `KEY:` is that
declaration — the same shape `TYPE:` gave gate risk in #162 and `SHAPE:` gave
reply arity in #186, this time for the decision-key half of the resolution
contract.

## Spec change

See `architecture/specs/PDSL.md`, new "### Declared gate key" subsection
under "## Menus", plus two small edits to the existing `TYPE`/`SHAPE` region
text so their own definitions stay accurate once a third declaration shares
the region.

## Implementation touch-points (not yet coded)

### `skills/studio/scripts/studio/utils/pdsl.py`

All of the following mirror the existing `TYPE`/`SHAPE` pattern directly:

| Location | Change |
|---|---|
| `pdsl.py:140-198` | Add `GATE_KEY_HEADER = "KEY"`, a `GATE_KEY_HEADER_ALIASES` frozenset, `GATE_KEY_HEADER_TYPO_DISTANCE = 1`, and — since `KEY` isn't a closed table — a `GATE_KEY_SYNTAX_RE` in place of a `_TYPES` tuple |
| `pdsl.py:157` (`DECLARED_HEADER_NON_TERMINATORS`) | Add `GATE_KEY_HEADER` |
| `pdsl.py:202-219` (`SECTION_HEADERS`) | Add `"KEY"` |
| `pdsl.py:114-126` (`_BlockValidationState`) | Add `menu_key_line: int = 0` **and** `menu_key_value: Optional[str] = None` — note the *value* has to be latched here, not just the line: `TYPE`/`SHAPE` never need their value outside the block, `KEY` does, for the cross-file uniqueness pass below |
| `pdsl.py:675-736` (`_handle_declared_menu_header`) | Its `valid_tokens: Tuple[str, ...]` + `if value not in valid_tokens` (line 729) is enum-shaped and won't fit `KEY` unmodified — needs a validator-callable parameter, or a parallel `_handle_declared_menu_key_header` that reuses the region/duplicate logic but swaps the value check for the syntax regex |
| new `_handle_gate_key_header` | Mirrors `_handle_gate_type_header` (`pdsl.py:738`), wired into `_handle_section_header_line`'s dispatch (`pdsl.py:644`) next to `TYPE`/`SHAPE` |
| Error codes | Following the existing 700/710 allocation: **PDSL720** (malformed value) / **PDSL721** (duplicate-per-menu) / **PDSL722** (outside declaration region) / **PDSL723** (near-miss) |

### `requirements/plan-template.md`

Flagged in review: the engine already reads `[[gate_decisions]]`
(`plan_decisions.py`, exact match against `decision_key`), and
`execution-plans.md` documents it, but the author-facing plan template still
only has a prose "User Decisions" section — not the array. Without this, a
declared `KEY` resolves against nothing an author actually wrote in a real
plan. The template needs to expose `[[gate_decisions]]` directly as part of
this same follow-on, not as a separate, easy-to-drop task.

### Cross-file uniqueness — the one piece with no `TYPE`/`SHAPE` precedent

`TYPE`/`SHAPE`'s "duplicate" check is per-menu, done entirely with in-block
state (`_BlockValidationState`) — it never leaves `_validate_block`, and
`cfs pdsl validate` validates each source file independently
(`skills/studio/scripts/studio/commands/pdsl.py:76`). Repo-wide `KEY`
uniqueness needs a corpus-level pass that doesn't exist in `pdsl.py` today.

The one existing precedent for this shape of check is
`_validate_duplicate_definitions` (`skills/studio/scripts/studio/utils/
constraints.py:2440`), which does the same thing today for `@cpt-`
traceability IDs via a `defs_by_id` index built by
`_scan_cross_artifact_rows`. Concretely this needs either:

- a new `declared_keys_by_name` index built the same way, fed from each
  file's `state.menu_key_value`, checked once at the end of a corpus run; or
- `KEY` declarations registering into the *existing* `@cpt-` id index instead
  of a new one — a bigger call, since that treats a decision key as a
  citizen of the traceability-ID system rather than a PDSL-local concept.

This note assumes the first (a separate, PDSL-local index) — see the spec's
own "namespace scope" rule for the reasoning, including the confirmed
kit-over-core follow-up below.

### Tests

Mirror the existing `TYPE`/`SHAPE` cases in `tests/test_pdsl_keywords.py`
(region membership, indentation/continuation, near-miss aliases,
duplicate-per-menu), plus cases only `KEY` needs:

- malformed-syntax rejection;
- cross-file duplicate detection (likely in a new test module alongside
  wherever the cross-file index lands, given today's `pdsl.py` tests are all
  single-source);
- **three-way declaration-order independence, asserted explicitly** — flagged
  in review as not safe to leave implicit. Three declarations sharing one
  region has no `TYPE`/`SHAPE` precedent (that pair only ever had two to
  order), so cover all six orderings of `TITLE`/`TYPE`/`SHAPE`/`KEY`, plus one
  case confirming a fourth recognized section (e.g. `NOTES:`) still ends the
  region regardless of which of the three preceded it.

## Resolved in review (PR #327, Sanjeev Solanki, 2026-09-28)

1. **Key syntax** — `^[a-z][a-z0-9_]*$` confirmed, no hyphens. `KEY` is a data
   identifier (a `[[gate_decisions]]` table key, exact-match resolved), so it
   stays snake_case to keep it visually distinct from `UNIT`/`MENU`'s
   PascalCase and `@cpt-`'s kebab-case. Grouping is a prefix convention
   (`plan_produce_approach`), not a hierarchy separator — a dot was
   considered and dropped: it clashes with TOML's own dotted-key syntax.
2. **Namespace scope** — repo-wide confirmed for the core corpus. One gap
   named, tracked as a non-blocking follow-up: a kit's keys can't be
   lint-checked against core's at authoring time, so a kit-over-core key
   collision is invisible to this lint even though both can resolve against
   the same active plan at runtime. Follow-up: a prefix convention (core
   unprefixed, each kit required to prefix its own), the same shape as the
   existing rule that a kit inherits behaviour only by declaring its own.
3. **Three-way declaration order** — must be asserted by an explicit test,
   not left to ride on "transfers from TYPE/SHAPE". See the Tests section
   above.
