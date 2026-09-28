# `KEY:` Declared Gate Key — Implementation Design Note (2026-09)

<!-- toc -->

- [Purpose of this document](#purpose-of-this-document)
- [Why this is being proposed](#why-this-is-being-proposed)
- [Spec change](#spec-change)
- [Implementation touch-points (not yet coded)](#implementation-touch-points-not-yet-coded)
  - [`skills/studio/scripts/studio/utils/pdsl.py`](#skillsstudioscriptsstudioutilspdslpy)
  - [Cross-file uniqueness — the one piece with no `TYPE`/`SHAPE` precedent](#cross-file-uniqueness--the-one-piece-with-no-typeshape-precedent)
  - [Tests](#tests)
- [Open questions for review](#open-questions-for-review)

<!-- /toc -->

## Purpose of this document

This note accompanies the `KEY:` sub-header proposal added to
`architecture/specs/PDSL.md` ("Declared gate key"). It records where in the
existing validator that declaration would need to be wired once the spec
wording is settled, so the PR captures the full picture — wording and
implementation shape — in one place, per HYP-2984 (a subtask of 2871). No
code in this PR implements any of it; this is a map for whoever picks up the
follow-on ticket.

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
own "PROPOSED namespace scope" line for the reasoning.

### Tests

Mirror the existing `TYPE`/`SHAPE` cases in `tests/test_pdsl_keywords.py`
(region membership, indentation/continuation, near-miss aliases,
duplicate-per-menu), plus two cases only `KEY` needs: malformed-syntax
rejection, and cross-file duplicate detection (likely in a new test module
alongside wherever the cross-file index lands, given today's `pdsl.py` tests
are all single-source).

## Open questions for review

1. **Key syntax** — is `^[a-z][a-z0-9_]*$` right, or should hyphens be
   allowed (PDSL identifiers elsewhere, e.g. `UNIT`/`MENU` names, allow
   `[A-Za-z][A-Za-z0-9_-]*`)?
2. **Namespace scope** — repo-wide (proposed), or should a kit boundary
   matter? `GateRuling` itself carries no file/kit qualifier today, which is
   the argument for repo-wide, but that's worth a second look given kits are
   meant to be independently distributable.
3. **Three-way declaration order** — confirmed order-independent in the spec
   text above by direct extension of `TYPE`/`SHAPE`'s existing guarantee; flag
   if that extension itself needs a test asserting it explicitly rather than
   assuming it transfers.
