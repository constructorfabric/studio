# Feature: Workflow Eval-Harness

<!-- toc -->

- [1. Feature Context](#1-feature-context)
  - [1. Overview](#1-overview)
  - [2. Purpose](#2-purpose)
  - [3. Actors](#3-actors)
  - [4. References](#4-references)
- [2. Actor Flows (CDSL)](#2-actor-flows-cdsl)
  - [Run Eval Harness](#run-eval-harness)
- [3. Processes / Business Logic (CDSL)](#3-processes--business-logic-cdsl)
  - [Run Eval Suite](#run-eval-suite)
  - [Score Structural Compliance](#score-structural-compliance)
  - [Score Rule Compliance (Advisory Judge)](#score-rule-compliance-advisory-judge)
  - [Assess Semantic Coverage](#assess-semantic-coverage)
- [4. States (CDSL)](#4-states-cdsl)
  - [Eval Report Lifecycle](#eval-report-lifecycle)
- [5. Definitions of Done](#5-definitions-of-done)
  - [Compliance Report](#compliance-report)
  - [Conditional JSON report fields](#conditional-json-report-fields)
- [6. Implementation Modules](#6-implementation-modules)
- [7. Acceptance Criteria](#7-acceptance-criteria)

<!-- /toc -->

- [x] `p1` - **ID**: `cpt-studio-featstatus-eval-harness`

## 1. Feature Context

- [x] `p1` - `cpt-studio-feature-eval-harness`

### 1. Overview

Scores completed workflow runs for how faithfully they followed their own plan. The
harness is a scaffold: it discovers **scenarios** (a completed run plus metadata), feeds
each run to a set of pluggable **scorers**, and aggregates the results into a JSON report
with a compliance verdict per scenario. Two scorer families plug into the same seam — a
deterministic structural scorer (which may affect the exit code) and an advisory
LLM-judge (which may never). This feature provides the scaffold and a placeholder
reference scorer; the real scorers are separate work.

### 2. Purpose

Studio's structural gates check that code is traceable, but nothing measures whether a
workflow *run* obeyed its recipe — step numbering, declared phase outputs, dependency
order. Without a harness the reasoning layer is a black box. The harness makes runs
scoreable and regression-checkable, while keeping the honest-signal discipline of the rest
of the tool: a run that cannot be scored reports `UNKNOWN`, never a silent zero, and an
advisory verdict can never gate a build.

### 3. Actors

| Actor | Role in Feature |
|-------|-----------------|
| `cpt-studio-actor-user` | Invokes `cfs eval` to score a suite of workflow-run scenarios |
| `cpt-studio-actor-ci-pipeline` | Runs `cfs eval` as a regression check against a baseline report |

### 4. References

- **PRD**: [PRD.md](../PRD.md) — `cpt-studio-fr-core-traceability`
- **Design**: [DESIGN.md](../DESIGN.md) — `cpt-studio-component-validator`
- **Dependencies**: `cpt-studio-feature-traceability-validation`

## 2. Actor Flows (CDSL)

### Run Eval Harness

- [x] `p1` - **ID**: `cpt-studio-flow-eval-harness-run`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User runs `cfs eval` → every scenario under `<project>/eval` is scored, JSON report emitted, exit 0 (gating is off by default — eval reports, it does not fail the build)
- User runs `cfs eval --scenarios-dir DIR` → scenarios discovered under `DIR`
- User runs `cfs eval --baseline report.json` → same, plus a per-scenario regression diff; the exit code is unchanged unless `--check` is also given
- User runs `cfs eval --check [--min N]` → exit 2 when structural compliance is below `--min`, **or** when `--baseline` shows a per-scenario compliance regression
- User runs `cfs eval --calibrate` → the report gains a `judge_calibration` object (reference-stub accuracy/consistency over gold-backed scenarios); advisory only, the exit code is unchanged
- User runs `cfs eval --save FILE` → the run's report JSON is written to `FILE` to serve as a later `--baseline`; the payload gains `saved` (the path, or `null` on failure) and, only on failure, `save_error`
- The JSON report always carries a `gate` field (`pass`/`fail`) matching the exit code, so a CI step can cross-check from `--json` alone

**Error Scenarios**:
- Constructor Studio not initialized, or the scenarios directory does not exist → ERROR, exit 1
- With `--check`: structural compliance below `--min`, or a baseline regression (a compliance drop, or a scenario that broke while still in the suite) → exit 2. A scenario removed from the suite entirely (`no_longer_scoreable`), or a `--baseline` that cannot be loaded (surfaced via the regression `error` field), is reported but does not by itself gate.

**Steps**:
1. [x] - `p1` - User invokes `cfs eval [--scenarios-dir DIR] [--check] [--min N] [--baseline FILE] [--save FILE] [--calibrate]` - `inst-user-eval`
2. [x] - `p1` - Load project context; if absent, emit ERROR and exit 1 - `inst-load-context`
3. [x] - `p1` - Resolve the scenarios directory, run the suite through the deterministic structural scorer, attach an optional regression diff, emit the JSON report, and return the harness exit code - `inst-run-and-report`

**Supporting**:
- [x] - `p1` - Imports and module setup for the eval command - `inst-eval-imports`
- [x] - `p1` - Build the CLI parser for the scenarios directory, gating, baseline, and save flags - `inst-build-parser`
- [x] - `p1` - Load an optional baseline report JSON, degrading to no-diff on error - `inst-load-baseline`
- [x] - `p1` - Save this run's report JSON to serve as a later baseline - `inst-save-report`
- [x] - `p1` - Render a short human-readable summary when not in JSON mode - `inst-human-report`
- [x] - `p1` - In the human summary, explain advisory-only UNKNOWNs (unwired judge, never gates) - `inst-human-advisory`
- [x] - `p1` - In the human summary, print the calibration metrics and note under `--calibrate`, tolerating a malformed payload - `inst-human-calibration`
- [x] - `p1` - In the human summary, render a `--baseline` regression (regressed scenarios, no-longer-scoreable count) and any save failure - `inst-human-regression`
- [x] - `p1` - Under `--calibrate`, measure the reference judge over the gold-backed scenarios - `inst-judge-calibration`

## 3. Processes / Business Logic (CDSL)

### Run Eval Suite

- [x] `p1` - **ID**: `cpt-studio-algo-eval-harness-run`

Loads scenarios and completed-run artifacts, applies scorers, and aggregates the results
under the gate contract (only deterministic verdicts affect the exit code).

**Steps**:
1. [x] - `p1` - Discover scenarios by globbing `*/scenario.toml` under the root, skipping malformed, escaping, or duplicate-id descriptors (ids stay unique so calibration identities are unambiguous) - `inst-load-scenarios`
2. [x] - `p1` - Load a completed run's `plan.toml` and phase files, returning `None` (UNKNOWN) instead of raising on a missing or malformed plan - `inst-load-run`
3. [x] - `p1` - Load one scenario's run and apply every scorer to it, isolating a raising scorer as UNKNOWN - `inst-run-scenario`
4. [x] - `p1` - Run every scenario under the root through the scorers and aggregate into a report - `inst-run-suite`
5. [x] - `p1` - Compute structural compliance (deterministic pass ratio) per scenario and in aggregate, `None` when nothing was scored - `inst-compliance`
6. [x] - `p1` - Derive the exit code: gate only under `--check` when compliance is below the floor; advisory verdicts never gate - `inst-gate`
7. [x] - `p1` - Serialise the report: per-scenario compliance, a failing-check histogram, and an UNKNOWN-aware coverage-stating summary - `inst-report-json`
8. [x] - `p1` - Bucket per-scenario compliance changes against a baseline (regressed / improved / newly- and no-longer-scoreable) - `inst-diff-reports`

**Supporting**:
- [x] - `p1` - Imports and module setup for the harness - `inst-harness-imports`
- [x] - `p1` - Load every `(scenario, run)` once so the report and calibration share one disk snapshot - `inst-load-cases`
- [x] - `p1` - Scorer kinds, verdicts, the scorer protocol, and the result/scenario/report data model - `inst-eval-datamodel`
- [x] - `p1` - A placeholder deterministic reference scorer that checks run presence, used to exercise the seam - `inst-reference-scorer`

### Score Structural Compliance

- [x] `p1` - **ID**: `cpt-studio-algo-eval-structural`

The real deterministic scorer plugged into the `Scorer` seam. It reads a completed run's
`plan.toml` manifest plus each phase file's `[phase]` frontmatter and runs a registry of
independent structural checks (numbering, manifest agreement, dependency order, declared
outputs, required sections). Verdict is `PASS` when every active check passes, `FAIL` when
any fails, and `UNKNOWN` when the run cannot be loaded or no phase carries parseable
frontmatter — "unscoreable is not zero". The scorer is pure over the in-memory run
artifacts: it touches no filesystem.

**Steps**:
1. [x] - `p1` - Parse each phase file's `[phase]` frontmatter into a number-keyed table, recording files that re-declare a number as duplicates - `inst-structural-parse`
2. [x] - `p1` - Run the phase-file validity and numbering-uniqueness checks over the parsed phases - `inst-structural-checks`
3. [x] - `p1` - Run the manifest-agreement and numbering checks over the parsed phases - `inst-structural-checks-manifest`
4. [x] - `p1` - Aggregate into a `ScorerResult`: compliance %, per-check findings, and the UNKNOWN discipline when nothing is scoreable - `inst-structural-scorer`

**Supporting**:
- [x] - `p1` - Module imports and the logger - `inst-structural-imports`
- [x] - `p1` - The frontmatter pattern and the per-workflow required-sections configuration - `inst-structural-config`
- [x] - `p1` - The `StructuralInput` data model the checks read from - `inst-structural-datamodel`
- [x] - `p1` - Shared reducers over the manifest and phases (declared numbers, totals, capped detail formatting) that the checks build on - `inst-structural-check-helpers`
- [x] - `p1` - Dependency-graph helpers: resolve/forward problems and misspelled-key detection - `inst-structural-deps`
- [x] - `p1` - The per-phase checks — total consistency, dependency order, declared outputs - `inst-structural-checks-phase`
- [x] - `p1` - Reduce a phase body to real Markdown prose (frontmatter and fenced code blocks removed) before heading detection - `inst-structural-prose`
- [x] - `p1` - The required-body-sections check over that prose - `inst-structural-checks-sections`
- [x] - `p1` - The check dataclass and the registry list binding each check name and tags to its predicate - `inst-structural-registry`

### Score Rule Compliance (Advisory Judge)

- [x] `p1` - **ID**: `cpt-studio-algo-eval-judge`

The advisory LLM-judge plugged into the `Scorer` seam. It opines on whether a completed run
followed its workflow's `RULES:`, the layer the deterministic scorer cannot measure. Its
kind is `ADVISORY` — the runner forbids it from touching the exit code — and it is built as
a *seam, not a transport*: the harness owns the deterministic prompt and reply parsing, while
the model call is supplied by the host/agent through a pluggable `judge_fn` (Studio stays
stdlib-only, and with no `judge_fn` the judge is `UNKNOWN`). Trustworthiness is measured, not
asserted: calibration reports accuracy against a human gold set and run-to-run consistency, and
judge coverage is derived from which scenarios carry a gold set.

**Authoring a gold-backed scenario** — what `--calibrate` measures against. A scenario opts in by
pointing at a gold file that carries the human verdict:

```toml
# <scenario-dir>/scenario.toml
[scenario]
id = "coding-happy-path"
workflow = "coding"
run_dir = "run"
expect = "compliant"

[scenario.gold]
path = "gold.toml"
```

```toml
# <scenario-dir>/gold.toml — the human label the judge is scored against
[gold]
verdict = "compliant"          # accepted values: compliant | non_compliant
rationale = "every declared rule was followed"
rules_assessed = [1, 3]        # optional, reserved: rule numbers this verdict applies to
                               # (list of ints; schema not yet stable — future per-rule scoring)
```

A scenario with no gold file is still scored, but reported as *unvalidated advisory*; a malformed
or unreadable gold file is *excluded* from calibration rather than counted as a judge mismatch.

**Steps**:
1. [x] - `p1` - Extract the `## Rules` declarations from each phase body, tracking fenced-code state so a rule heading inside an example is not mistaken for a real section - `inst-judge-prompt`
2. [x] - `p1` - Assemble the deterministic judge request (rules + evidence + prompt) and map replies to verdicts, with no model call - `inst-judge-request`
3. [x] - `p1` - Score rule-compliance via the injected judge, returning an advisory result that can never gate - `inst-judge-scorer`
4. [x] - `p1` - Calibrate the judge over gold-backed scenarios: accuracy vs the human label and run-to-run consistency - `inst-judge-calibrate-run`

**Supporting**:
- [x] - `p1` - Imports, the rules-section pattern, and the gold-label-to-verdict mapping - `inst-judge-imports`
- [x] - `p1` - Recognise a Markdown fenced-code delimiter (backtick or tilde, by character and length) so a `## Rules` inside a fenced example is not read as a heading - `inst-judge-fence`
- [x] - `p1` - Order phase texts by the run manifest so rules, evidence, and the run summary present the same sequence - `inst-judge-order`
- [x] - `p1` - The judge data model: gold label, judge request/reply, and the `JudgeFn` seam - `inst-judge-datamodel`
- [x] - `p1` - Detect when the harness cannot present real evidence (empty, or whole phases omitted) so the run is UNKNOWN and excluded from calibration - `inst-judge-gap`
- [x] - `p1` - Assemble the bounded run evidence (total-capped share per phase, omitted phases flagged) and the run summary - `inst-judge-evidence`
- [x] - `p1` - Load a scenario's `gold.toml` human label, degrading to unvalidated on absence - `inst-judge-gold`
- [x] - `p1` - A deterministic reference-stub `JudgeFn` for tests and calibration wiring (not a model) - `inst-judge-stub`
- [x] - `p1` - The `Calibration` result model (accuracy, consistency, coverage) - `inst-judge-calibrate`

### Assess Semantic Coverage

- [x] `p1` - **ID**: `cpt-studio-algo-eval-semantic`

The semantic-coverage engine: it asks whether a marked block *implements the requirement it
cites*, which marker density cannot. A deterministic stdlib token-overlap pre-filter scores
every block against its requirement text and surfaces the weak links; only those go to a
pluggable `SemanticJudgeFn` (the model call lives out-of-tree). It is advisory throughout —
no verdict here touches an exit code — and honest: a block with no retrievable requirement, or
too little text to compare, is reported `unjudgeable`, never a silent "covered". Files a human
declared `excluded` in the coverage report are skipped; files flagged `whole_file_claims` are
prioritised. Every model verdict carries an evidence check: a quote absent from the code is not
trusted.

**Steps**:
1. [x] - `p1` - Tokenise code and requirement (camelCase + Unicode word-boundary split, stopwords dropped) and score their overlap against the requirement set, or `None` below the token floor - `inst-semantic-tokenize`
2. [x] - `p1` - Rank every pairing weakest-first, marking below-threshold blocks as weak links and below-floor blocks as unjudgeable, and marking every block in a whole-file-claim file a weak link regardless of overlap (always judged) - `inst-semantic-prefilter`
3. [x] - `p1` - Judge only the weak links through the injected `SemanticJudgeFn`, degrading a raising or malformed reply to unjudgeable and evidence-checking every quote - `inst-semantic-finding`
4. [x] - `p1` - Assess pairings end-to-end — scope, rank, judge weak links, and report unjudgeable coverage gaps — advisory throughout - `inst-semantic-report`

**Supporting**:
- [x] - `p1` - Module imports, verdict constants, and the provisional calibration constants + stopword set - `inst-semantic-imports`
- [x] - `p1` - The pairing, ranked (with a whole-file-claim `forced` flag), request, reply data model and the `SemanticJudgeFn` seam — the seam is called synchronously and unbounded, so a judge that can hang must enforce its own timeout - `inst-semantic-datamodel`
- [x] - `p1` - Blank character spans in place (spaces, newlines preserved) so a verbatim quote of the untouched text still matches - `inst-semantic-blank`
- [x] - `p1` - Derive two code views in one grammar-aware `tokenize` pass — an overlap view (comments and all strings blanked, so prose cannot inflate the score) and an evidence view (comments and docstrings blanked, inline strings kept) — falling back to a plain comment strip for a non-tokenisable fragment - `inst-semantic-strip`
- [x] - `p1` - Read the frozen coverage-report contract (`excluded[]` / `whole_file_claims[]`, path-separator normalised, `excluded` taking precedence), degrading to an empty scope - `inst-semantic-scope`
- [x] - `p1` - Build the deterministic judge prompt (bounded fields) and parse a reply to a verdict - `inst-semantic-prompt`
- [x] - `p1` - The evidence-present hallucination guard: a quote must occur in the evidence view (comments/docstrings stripped), so a quote matching only a comment is not evidence - `inst-semantic-evidence`
- [x] - `p1` - The `SemanticGap` coverage-gap record (block_id, path, start_line, reason), located like a finding so a report consumer can point at every gap - `inst-semantic-gap`
- [x] - `p1` - The reference stub judge (deterministic overlap buckets) and its best-evidence-line quote - `inst-semantic-stub`
- [x] - `p1` - The requirement resolver adapter over `get_content_scoped` - `inst-semantic-resolve`
- [x] - `p1` - Read a `[gold]` verdict label for calibration, or `None` when absent/malformed - `inst-semantic-gold`
- [x] - `p1` - Calibrate the judge over gold-backed pairings: report accuracy, consistency, and effective sample size per case, excluding unscoreable / crashed / strict-tie cases — accuracy over cases with a majority, consistency over cases with ≥2 surviving runs — `None` when nothing is measurable - `inst-semantic-calibrate`

## 4. States (CDSL)

### Eval Report Lifecycle

Each scenario result carries one verdict. `NOT_SCORED` is the initial state before scoring.
A run transitions to `SCORED` when a scorer returns `PASS` or `FAIL`, or to `UNKNOWN` when
its artifacts cannot be loaded. The harness never transitions a run out of `UNKNOWN` into a
numeric score — "unscoreable" is terminal for that run, not a zero.

## 5. Definitions of Done

### Compliance Report

- [x] `p1` - **ID**: `cpt-studio-dod-eval-harness-report`

The scaffold is done when `cfs eval` emits a JSON report scoring every discovered scenario;
only deterministic scorer verdicts affect the exit code; a run whose artifacts cannot be
loaded reports `UNKNOWN` with a `null` score and is counted separately; and `--baseline`
yields a per-scenario regression diff without changing the exit code.

**Implements**:
- `cpt-studio-flow-eval-harness-run`
- `cpt-studio-algo-eval-harness-run`

### Conditional JSON report fields

Beyond the always-present `schema_version`, `summary`, `failing_checks`, `per_scenario`, and
`gate`, three top-level keys appear only under specific flags — a consumer must presence-check
them (subscripting when the flag is absent raises `KeyError`):

| Key | Present when | Shape |
|-----|--------------|-------|
| `regression` | `--baseline` given | object: `has_regression` (bool), `regressed[] {scenario, from, to}`, `improved[]`, `newly_scoreable[]`, `no_longer_scoreable[]`, `aggregate_before`, `aggregate_after`; or `{error}` when the baseline is unusable |
| `judge_calibration` | `--calibrate` given | object: `judge`, `gold_backed[]`, `excluded_unscoreable[]`, `broken_gold[]`, `accuracy` (float\|null), `consistency` (float\|null), `runs_per_scenario`, `note` |
| `saved` / `save_error` | `--save FILE` given | `saved`: the path, or `null` on failure. `save_error`: present **only** on failure, a message with the destination and reason |

## 6. Implementation Modules

| Module | Path | Responsibility |
|--------|------|----------------|
| Eval Command | `skills/studio/scripts/studio/commands/eval.py` | CLI entry point, arg parsing, context, exit code |
| Eval Harness | `skills/studio/scripts/studio/utils/eval_harness.py` | Scenario/run loading, scorer seam, runner, report, regression diff |
| Structural Scorer | `skills/studio/scripts/studio/utils/eval_structural.py` | Deterministic structural checks over a run's manifest + phase frontmatter |
| Advisory Judge | `skills/studio/scripts/studio/utils/eval_judge.py` | Advisory rule-compliance judge (pluggable model seam) + gold-set calibration |
| Semantic Coverage | `skills/studio/scripts/studio/utils/eval_semantic.py` | Token-overlap pre-filter + advisory judge seam over marked-block vs requirement, with honesty + evidence guards |

## 7. Acceptance Criteria

- [x] `p1` - `cfs eval` scores every scenario under the resolved directory and emits a JSON report with a `gate` field consistent with the exit code
- [x] `p1` - Only deterministic scorer verdicts affect the exit code; an advisory FAIL never does
- [x] `p1` - A run that cannot be loaded, or whose phases declare no checkable file, scores `UNKNOWN` with a `null` score, never `0`, and is counted separately in the summary
- [x] `p1` - `--baseline` alone (without `--check`) produces a per-scenario regression diff without changing the exit code; a removed/unavailable scenario is surfaced but does not gate
- [x] `p1` - When `--baseline` is given, the `regression` key is always present (a diff object, or an `error` object when the baseline is unusable)
- [x] `p1` - `cfs eval` scores structural compliance via a registry of deterministic checks over each run's manifest and phase frontmatter; any failing check makes the scenario verdict `FAIL` while the per-scenario `score_pct` still reports the fraction of checks passed
- [x] `p1` - A run whose phase files carry no parseable `[phase]` frontmatter scores `UNKNOWN`, never 0; the scorer touches no filesystem and is a pure function of the in-memory run artifacts
- [x] `p1` - The advisory rule-judge is `ADVISORY` and never affects the exit code; with no injected `judge_fn` it scores `UNKNOWN`, so `cfs eval` runs and gates deterministically without a model
- [x] `p1` - Judge calibration reports accuracy against a human gold set and run-to-run consistency, kept separate from structural compliance; judge coverage is derived from which scenarios carry a gold set
- [x] `p1` - The run evidence is hard-capped: the total (headers, truncation markers, separators and the omission line included) never exceeds the evidence budget. A trimmed phase is still judged; when whole phases are omitted to fit, the request is marked incomplete and the judge returns `UNKNOWN` without a model call — a verdict is never certified from evidence with entire phases unseen
- [x] `p1` - In default (non-JSON) mode the human summary prints the scorer coverage line, explains that advisory-only UNKNOWNs come from an unwired judge (never counted against the gate), and prints the calibration metrics under `--calibrate`; the JSON payload is unchanged
- [x] `p1` - Semantic coverage ranks marked blocks by deterministic token-overlap against their requirement and judges only the surfaced weak links — a strong-overlap block triggers no model call, except a block in a `whole_file_claims` file, which is always judged regardless of overlap (its structural coverage rests on a whole-file scope marker, so a high lexical score there must not buy a free pass)
- [x] `p1` - A block with no retrievable requirement, or with too little text to compare, is reported `unjudgeable`, never a silent `covered`; with no `SemanticJudgeFn` wired every weak link is `unjudgeable` and nothing gates
- [x] `p1` - A model `evidence_quote` absent from the cited code sets `evidence_ok=false`; a raising or malformed judge reply degrades that one finding to `unjudgeable` without sinking the assessment
- [x] `p1` - Files a human declared in the coverage report's `excluded[]` are skipped; a report lacking the `excluded[]` / `whole_file_claims[]` fields yields an empty scope (skip nothing, prioritise nothing), never an error
