---
status: accepted
date: 2026-09-16
decision-makers: project maintainer
---

# ADR-0024: Validation Severity as Declared, Reviewable Policy

**ID**: `cpt-studio-adr-validation-severity-policy`

<!-- toc -->

- [Context and Problem Statement](#context-and-problem-statement)
- [Decision Drivers](#decision-drivers)
- [Considered Options](#considered-options)
- [Decision Outcome](#decision-outcome)
  - [The severity vocabulary](#the-severity-vocabulary)
  - [Where policy is declared](#where-policy-is-declared)
  - [Resolution: two layers, not six](#resolution-two-layers-not-six)
  - [The raise/lower rule, and what it does to No-Weakening](#the-raiselower-rule-and-what-it-does-to-no-weakening)
  - [An unrecognised value fails the load](#an-unrecognised-value-fails-the-load)
  - [Where policy is applied](#where-policy-is-applied)
  - [The fail-fast heading gate counts errors, not findings](#the-fail-fast-heading-gate-counts-errors-not-findings)
  - [What a run reports](#what-a-run-reports)
  - [Ordering is deterministic](#ordering-is-deterministic)
  - [Consequences](#consequences)
  - [Confirmation](#confirmation)
- [Pros and Cons of the Options](#pros-and-cons-of-the-options)
  - [Declared policy in kit and project configuration (chosen)](#declared-policy-in-kit-and-project-configuration-chosen)
  - [CLI flags per rule](#cli-flags-per-rule)
  - [Keep deletion as the only relaxation](#keep-deletion-as-the-only-relaxation)
- [More Information](#more-information)

<!-- /toc -->

## Context and Problem Statement

`cfs validate` has one severity. Every finding it produces fails the run, and
the only way to stop a rule from failing a run is to delete the rule —
`required = false` in the kit's `constraints.toml`, which does not make the rule
advisory but removes it. A team that wants a rule visible and non-blocking has
no way to say so, and a team that deletes the rule has no record that it ever
existed.

That is the adoption blocker. Teams whose documents do not match the shipped
SDLC kit's expectations cannot turn `cfs validate` on at all, because turning it
on means failing their build on rules they have not agreed to yet.

The first half of the model already landed: every finding now carries a
`severity` field stamped from a declared, exhaustive table
(`utils/severity.py`). What remains is that nothing can change that value. A kit
cannot ship a posture, a project cannot relax a rule that does not fit its
documents, and no one can see which severity is actually in force.

Relaxing a quality gate is the kind of change that goes wrong quietly, and
`cpt-studio-constraint-no-weakening` already says validation rules cannot be
weakened. This record has to reconcile a configurable severity with that
constraint, or one of the two is dishonest.

Three report inconsistencies sit alongside the same work and are settled here
because they are the same question — what does a run tell you about what it did:
`validate` withholds the `warnings` list entirely on a passing non-verbose run
(`issues/ole-31`), `validate-kits` has no top-level `warning_count`, and each of
the three validate commands assembles its own summary and exit decision.

## Decision Drivers

- A rule must be able to be visible without being blocking, per artifact kind.
- Relaxing a rule must leave a trace that a reviewer sees without asking for it.
- `cpt-studio-constraint-no-weakening` must remain true, not be quietly dropped.
- With no configuration present, output and exit codes must not move — the
  change has to be adoptable by projects that want none of it.
- A kit must retain authority over rules it considers non-negotiable.
- An unparseable setting must not resolve to "no opinion".
- `status: PASS` / `FAIL` is load-bearing: the in-process kit gate
  (`commands/validate.py`) and every prompt that reads a Studio report key off it.

## Considered Options

- **Declared policy in kit and project configuration, with a raise/lower rule**
  (chosen).
- **CLI flags per rule** — `--warn-on toc-missing`, `--ignore heading-missing`.
- **Keep deletion as the only relaxation** — document `required = false` as the
  supported answer and close the requests.

## Decision Outcome

Chosen: **declared policy in kit and project configuration**, with lowering
permitted only where the kit has not locked the rule, and every lowering named
in every report.

### The severity vocabulary

`error`, `warning`, `off`. These are the three states a rule can be in:
enforced, reported, or not applicable. `off` is a third state rather than a
deletion because a rule that is off is still a rule — it has a name, a default,
and a record that someone turned it off.

### Where policy is declared

A kit declares posture in `constraints.toml`:

```toml
[validation.severity]                      # per rule code, whole kit
"toc-missing" = "warning"

[artifacts.PRD.validation.severity]        # per rule code, one artifact kind
"heading-number-not-consecutive" = "off"

[[artifacts.PRD.headings]]
id = "prd-metrics"
severity = "warning"                       # advisory: reported, never gates
locked = true                              # a project may not lower this entry
```

A project declares its own in `config/core.toml`:

```toml
[validation]
fail_on_warnings = false

[validation.severity]
"toc-missing" = "warning"

[validation.severity.FEATURE]
"heading-missing" = "error"
```

The top-level `[validation]` table is lifted out of the constraints file
*before* the `artifacts` unwrap. In the legacy unwrapped layout the artifact
kinds sit at the top level, so a `[validation]` table left in place would be
read as an artifact kind named `VALIDATION` and fail the entire file to load.

### Resolution: two layers, not six

Resolution reads as six layers of specificity — entry, project-kind,
project-code, kit-kind, kit-code, built-in default — but applying it that way is
wrong, and the wrongness is instructive. The constraint entry is the most
specific declaration of all, so under plain specificity a project could never
override an entry, and `locked` would have nothing left to mean.

So there are two layers:

1. **The kit's own opinion** settles first, by specificity: the constraint
   entry, then the kit's per-kind table, then its whole-kit table, then the
   built-in default from `DEFAULT_SEVERITY`.
2. **The project layer** is then admitted against it, under the raise/lower
   rule below.

Every resolved severity carries the layer that decided it, and that layer name
is reported by `--explain-severity`.

When several kits are bound into one project, merging their tables asks a
different question from resolution, and it is worth separating the two.
*Within* one kit, specificity decides: its own per-kind table overrides its own
whole-kit table, exactly as the resolution order above says. *Between* kits,
strictness decides, including across the whole-kit/per-kind boundary — one
kit's whole-kit `error` is not relaxed by another kit's PRD-scoped `off`,
because neither has agreed to be overruled by the other. Each kit contributes
its effective value for a kind, and the strictest of those wins. Applying
strictest-wins uniformly would defeat a kit's own per-kind override, which is
the one thing a per-kind table exists to do.

### The raise/lower rule, and what it does to No-Weakening

- A project may **raise** any rule, always. Holding yourself to more than the
  kit asks needs no permission.
- A project may **lower** any rule the kit has not marked `locked`. The
  lowering is listed under `severity_overrides` in every report.
- A project may not lower a `locked` entry. The attempt is refused, the kit's
  value stands, and the refusal is reported.
- **No CLI flag may lower anything.** `--fail-on-warnings` raises. There is no
  flag that relaxes, because a flag is typed once and leaves no artifact a
  reviewer can read.

`cpt-studio-constraint-no-weakening` is therefore narrowed, not dropped: **no
silent or runtime weakening.** Policy is declared in configuration that is
diffed and reviewed like any other file, and it is visible in the output of
every run that it affects. The constraint was always about preventing an agent
from quietly downgrading a finding mid-run; it was never about forbidding a
team from deciding, in writing, which rules apply to them.

### An unrecognised value fails the load

A severity that does not parse fails the run. This is the opposite of the
posture taken in the cf-ux evaluation work, where an unfamiliar result shape
deliberately does not manufacture a failure — and the distinction is the point:

> **Fail closed where the unknown disables a check. Do not manufacture failures
> where the unknown merely describes an outcome.**

There, an unrecognised value described a result that had already happened.
Here, an unrecognised value would *disable checking*: a typo in a severity
would switch a rule off and the run would still report success. That is the
exact failure this whole model exists to make impossible.

An unrecognised **key** — or a `severity` entry naming a rule code this engine
does not have — is different again, and the two configuration surfaces are
deliberately **not** treated alike:

- **In a kit's `constraints.toml`**: reported by `validate-kits` as a
  `constraints-unknown-key` warning, and the rest of the file still loads. A
  kit is authored elsewhere and pinned at a version, so it must stay
  installable on an engine older than the one it was written for. That is the
  same forward-compatibility bargain the manifest already makes for unknown
  kit keys.
- **In the project's own `core.toml`**: a hard error that refuses the run.
  There is no forward-compatibility case here — the file is authored by the
  person running the command, against the engine they are running it on — so
  the failure mode to protect against is not "a newer schema" but "a typo the
  author believes is in force". Failing loudly is the better service.

Neither is ever silent. The engine's rule-code registry is closed and guarded
at import, so a misspelled code is knowable at parse time on both surfaces.

A misspelled *artifact kind* under `[validation.severity.<KIND>]` is the third
case, and the one most worth catching: it is not a rule code, so it resolves
to nothing and appears in no override report, and the common direction is a
**raise** — leaving the author believing a rule now blocks when it does not.
A kit's own file warns, as above; `core.toml` refuses the run.

Both checks need the whole composition, and that is what decides where they
live. The known-kind set is the union of every loaded kit's declared kinds and
every kind the artifact registry registers, because either source alone would
raise false alarms: a kit may constrain a kind no system registers, and a
system may register a kind constrained by a kit that is not loaded.

That union is also why a kit's kinds are *not* judged while its
`constraints.toml` is parsed. A kit file is read alone, and in a multi-kit
project one kit may legitimately scope a severity to a kind a companion kit
declares — a setting the composition resolves correctly and a per-file check
would strip and misreport as a typo. So the kit-side check runs from
`validate-kits`, and only on the view that holds every kit: an unfiltered
registered-mode run. Validating one kit by path, or through `--kit`, the
siblings a kind may come from are out of view, so the check stands down rather
than calling a composable kit's setting a mistake.

### Where policy is applied

Policy is applied to a file's findings at the end of `validate_artifact_file`,
which is the only place the artifact kind is known. That pass also records
`artifact_kind` on every finding from the file — previously only heading
findings carried it, which would have left per-kind policy unable to reach a
TOC, CDSL or identifier finding.

A second pass at the command level settles everything the per-artifact pass did
not see: cross-artifact findings, code traceability, reference coverage, context
errors. Each finding resolves against its own recorded kind, or unscoped if it
has none. Re-applying the policy to an already-settled finding changes nothing —
resolution is a function of the finding's own code, kind and entry, and a
suppressed finding is removed rather than marked, so nothing can be counted
twice.

Order within a pass is: drop `off`, count it, restamp, repartition into errors
and warnings, then enrich.

### The fail-fast heading gate counts errors, not findings

`validate_artifact_file` skips the TOC and identifier phases when the heading
phase produced errors. That gate now counts *error-severity* heading findings.
Without this, a rule lowered to `warning` would still hide two entire validation
phases behind it, and the reader would see one advisory note with no sign that
anything had been skipped — which is the failure mode this ADR is meant to
close, reappearing one level down.

### What a run reports

- `severity` on every finding (shipped previously).
- `suppressed_count` — findings an `off` rule removed. A suppressed rule is
  never simply invisible.
- `severity_overrides` — every project setting that lowers a rule, plus any
  refusals actually encountered. Emitted whenever non-empty, not on request:
  `--explain-severity` answers a question, and the reader who most needs to
  know a rule was switched off is the one who does not know to ask. The
  lowerings are derived from the configuration rather than from what happened
  to be emitted, because a rule lowered to `off` produces no finding at all and
  that is precisely the case most in need of naming.
- `failed_on: "warnings"` when warnings alone decided the outcome.
- Human output names the suppressed count and lists the lowered rules.

`status` stays `PASS` / `FAIL` for `validate` and `validate-kits`. A `WARN`
status would break the in-process kit gate and every consumer keyed on `PASS`,
and `warning_count` already carries the information. `validate-toc` keeps its
`WARN`: it is the one command whose third status nothing keys off.

One shared helper (`run_verdict`) produces status and exit code for all three
commands, so the invariant *without `fail_on_warnings`, the exit code is a
function of the error count and nothing else* is stated once rather than
reimplemented three times.

### Ordering is deterministic

Findings sort by `(path, line, code)`; `--explain-severity` sorts by
`(kind, code)`; `severity_overrides` sorts by `(kind, code, entry)`. Both
outputs are read by humans and diffed in CI, and a golden comparison hides an
ordering bug behind whatever insertion order a dict happened to have.

### Consequences

- Teams can adopt `cfs validate` incrementally: turn rules to `warning`, fix
  over time, raise back to `error`. That is the adoption path this ADR exists
  to open.
- A reviewer reading a project's `core.toml` diff sees every relaxation, and a
  reader of any affected run sees it again in the report.
- Kit authors gain a real obligation: `locked` is the only protection against a
  project relaxing a rule, so a kit that locks nothing has consented to
  everything. The shipped SDLC kit must deliberately leave `toc-*` unlocked for
  the `validate-toc` relaxation case to be satisfiable at all.
- `validate` now emits `warnings` on a passing non-verbose run, where it
  previously withheld them. This is a deliberate output change and the only one:
  the non-verbose golden moves by design, and the verbose golden does not move.
- Two report keys are added to the `validate` contract (`suppressed_count`,
  `severity_overrides`) and one to `validate-kits` (`warning_count`). All are
  additive; a consumer reading only `errors` sees no change.
- The severity model is now a public contract. `DEFAULT_SEVERITY` values, the
  source names, and the precedence rule are all things a project's
  configuration depends on, and changing one is a breaking change.

### Confirmation

- The whole `DEFAULT_SEVERITY` table is pinned by value in `tests/test_severity.py`
  — by value and not by presence, because a rule shipped as `warning` when it
  should be `error` keeps every "fails on bad input" test green, given that
  those tests assert exit codes and message text rather than the label itself.
- The precedence table, the raise/lower rule and the locked refusal are each
  pinned by unit test.
- `validate --json --verbose` on this repository is compared against a baseline
  captured before the change: identical apart from additive keys, confirming
  that with no configuration nothing moves.
- `make validate` stays at 0 errors and the same 271 warnings.
- The invariant "without `fail_on_warnings` the exit code is a function of the
  error count alone" is asserted directly rather than inferred from examples.

## Pros and Cons of the Options

### Declared policy in kit and project configuration (chosen)

- Good, because relaxation lands in a file that is reviewed and diffed like any
  other change, rather than in a command line nobody reads twice.
- Good, because the kit keeps authority over what it considers non-negotiable,
  through `locked`.
- Good, because per-kind scoping matches how the problem actually presents: a
  team's PRDs diverge from the kit while their FEATURE docs do not.
- Good, because the reports make the policy visible without being asked, so the
  passive reader is served and not just the curious one.
- Bad, because the precedence rule is genuinely intricate, and the two-layer
  reading has to be explained or it will be misapplied as plain specificity.
- Bad, because it adds two configuration surfaces, both of which must be
  schema-described and documented or they become folklore.

### CLI flags per rule

- Good, because it is trivial to implement and needs no schema work.
- Good, because it suits one-off local exploration well.
- Bad, decisively, because it leaves no artifact. A relaxation typed into a CI
  script is invisible in review, and `cpt-studio-constraint-no-weakening` could
  not be honestly narrowed to cover it — this is runtime weakening exactly.
- Bad, because per-kind scoping would need an unreadable flag grammar.
- Bad, because a kit could not protect anything.

### Keep deletion as the only relaxation

- Good, because it changes nothing and cannot regress.
- Good, because `required = false` is already understood.
- Bad, because it does not address the adoption blocker at all — it is the
  status quo that produced the requests.
- Bad, because deletion destroys the record: a rule removed from a kit's
  constraints leaves nothing saying it was ever considered, so the team never
  revisits it.
- Bad, because it pushes teams to fork the kit, which is the failure this
  epic's other half exists to prevent.

## More Information

The severity vocabulary and the exhaustive `DEFAULT_SEVERITY` table were
introduced separately and are described by
`cpt-studio-algo-traceability-validation-severity-policy` in
`architecture/features/traceability-validation.md`. Configuration reference:
`guides/CONFIGURATION.md` and `architecture/specs/kit/constraints.md`.
