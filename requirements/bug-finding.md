---
cf: true
type: requirement
name: Bug-Finding Methodology
version: 1.0
purpose: Compact language-agnostic methodology for high-recall bug discovery in source code
---

# Bug-Finding Methodology

**Scope**: Source-code analysis for correctness, logic, reliability, security, concurrency, performance, and integration defects across programming languages.

**Non-goal**: guarantee `100%` bug detection. That is not achievable in the general case because programs depend on incomplete specifications, runtime environment, dynamic inputs, external systems, and nondeterministic behavior. The practical target is **maximum recall with explicit uncertainty, evidence, and escalation paths**.

## Core Principles

```pdsl
UNIT BugFindingPrinciples

PURPOSE:
  Establish the behavioral principles governing all bug-finding review work.

RULES:
  - ALWAYS combine complementary signals: pattern rules, semantic reasoning, data-flow review, dynamic checks, and historical evidence
  - ALWAYS optimize for recall first, then calibrate precision with evidence
  - ALWAYS keep the smallest slice that covers the full invariant or boundary under test; expand when a plausible bug depends on unseen callers, callees, shared state, config, or cross-language contracts
  - ALWAYS work from invariants and failure modes, not language syntax alone
  - NEVER claim all bugs found; report confidence and residual uncertainty explicitly
  - ALWAYS load only the code needed for the current reasoning slice; expand only when call graph, state flow, or boundary contracts require it
  - NEVER rely on a single LLM pass; require a layered review stack for CodeRabbit-like quality
```

## Context Budget & Expansion Control

```pdsl
UNIT BugFindingContextBudget

PURPOSE:
  Define the canonical hotspot budget and escalation rules for every bug-finding review pass.

STATE:
  - SET working_set_files: integer
    default: 5
  - SET working_set_lines: integer
    default: 800

RULES:
  - ALWAYS start each hotspot with a working set of <= 5 files and <= 800 active code lines
  - ALWAYS summarize and drop already-processed context before expanding
  - ALWAYS expand only when the current slice cannot confirm or refute a plausible bug in the active invariant, state transition, or boundary contract
  - ALWAYS load the smallest decisive slice first for companion requirements or checklists: TOC, then review-mode or reporting slices, then only the specific item sections required by the chosen review mode or the active hotspot, then one contiguous line range if needed
  - ALWAYS keep companion coverage bounded to <= 2 dependency files and <= 240 raw dependency lines in active context for one review pass; summarize and drop raw dependency text before loading the next slice
  - ALWAYS treat a companion as proved non-material only when the inspected slice is sufficient to show the remaining unseen text cannot change hotspot-relevant obligations
  - ALWAYS emit a checkpoint with the unresolved boundary and mark review PARTIAL when a hotspot still needs more than 1500 active code lines, more than 2 expansion rounds, or companion coverage beyond the dependency budget
  - NEVER broaden beyond budget; recommend a focused follow-up pass or dynamic validation instead
```

## Layer Map

| Layer | Question |
|---|---|
| L1 | Where are the real risk hotspots? |
| L2 | What contracts and invariants must always hold? |
| L3 | Which paths, states, and interleavings can violate them? |
| L4 | Which universal bug classes apply here? |
| L5 | Can a concrete counterexample be constructed? |
| L6 | What dynamic check would confirm or refute the finding? |
| L7 | What is the overall review status, confidence, impact, and next action? |

## L1: Risk Hotspot Mapping

Focus first on code that is most likely to contain high-impact defects.

```pdsl
UNIT BugFindingL1

PURPOSE:
  Identify and prioritize the highest-risk code hotspots before deeper analysis.

DO:
  - SET hotspot_list: changed code, entry points, trust boundaries, persistence boundaries, async boundaries, and externally visible behavior
  - RUN prioritization: authentication, authorization, money movement, state transitions, retries, parsing, serialization, migrations, caching, and cleanup logic first
  - LOAD callers, callees, shared utilities, and configuration only when they influence the active path
  - LOAD repository signals when available: churn, incident history, bug-fix patterns, flaky tests, complex functions, and modules with many dependencies
```

## L2: Contract & Invariant Extraction

Extract what must be true before, during, and after execution.

```pdsl
UNIT BugFindingL2

PURPOSE:
  Extract explicit and inferred contracts and invariants for the code under review.

DO:
  - SET preconditions: input shape, nullability, permissions, ordering, initialization, feature flags, units, and schema assumptions
  - SET postconditions: returned value, persisted state, emitted events, side effects, idempotency, and cleanup guarantees
  - SET cross_step_invariants: uniqueness, monotonicity, ownership, transactional boundaries, retry safety, and consistency between cache, database, and outbound messages
  - SET contract_source: infer from tests, names, types, assertions, error messages, docs, and call sites when contract is not explicit

RULES:
  - ALWAYS mark inferred contracts as inferred rather than proven
```

## L3: Path, State, and Interleaving Exploration

Trace how bugs emerge when the happy path breaks.

```pdsl
UNIT BugFindingL3

PURPOSE:
  Explore paths, state transitions, and concurrent interleavings that can violate contracts.

DO:
  - RUN main path, unhappy path, edge values, repeated invocation, partial failure, timeout, retry, stale state, invalid config, startup, shutdown, and rollback paths
  - RUN stateful logic trace: creation, mutation, persistence, invalidation, and cleanup
  - RUN async/concurrent logic: races, double delivery, out-of-order completion, missing awaits, lock ordering, cancellation, and duplicate side effects
  - RUN distributed flow checks: retries, deduplication, eventual consistency gaps, and split-brain assumptions between services
```

## L4: Universal Bug-Class Sweep

Apply the same defect lenses regardless of language.

| Class | Typical failures |
|---|---|
| Correctness & logic | Wrong branch, inverted condition, off-by-one, missing case, unreachable branch, bad default |
| Input & boundary | Missing validation, parse mismatch, encoding mismatch, unit mismatch, schema drift |
| Error handling & resilience | Swallowed error, wrong fallback, retry storm, partial commit, misleading success |
| State & lifecycle | Wrong initialization order, stale cache, missing cleanup, duplicate apply, broken rollback |
| Security & trust boundary | Authz gap, injection path, traversal, unsafe deserialization, secret or PII leak |
| Concurrency & async | Race, deadlock, lost update, double execution, missing await, cancellation bug |
| Performance & resources | N+1, unbounded loop, leak, blocking hot path, missing backpressure |
| Integration & config | Version drift, env mismatch, clock/timezone bug, feature-flag inversion, protocol mismatch |
| Testing gaps | Missing regression coverage for critical or failure paths |

## L5: Counterexample Construction

A suspected bug becomes stronger when you can describe exactly how it fails.

```pdsl
UNIT BugFindingL5

PURPOSE:
  Build or refute concrete counterexamples for suspected bugs.

DO:
  - SET trigger: the smallest input, prior state, ordering, timing, or configuration needed to break the invariant
  - SET failure_expression: condition -> execution path -> bad outcome
  - RUN search for contradictory code, assertions, tests, or guards that disprove the hypothesis

RULES:
  - ALWAYS lower confidence or discard the finding when no plausible trigger can be constructed
```

## L6: Dynamic Escalation Strategy

When static reasoning is insufficient, specify the cheapest next proof.

```pdsl
UNIT BugFindingL6

PURPOSE:
  Select the cheapest confirming dynamic check for each unresolved bug hypothesis.

DO:
  - RUN targeted unit tests for local logic and boundary conditions
  - RUN integration tests for persistence, network, serialization, configuration, and cross-service behavior
  - RUN property-based tests or fuzzing for parsers, protocol handlers, validators, and state machines
  - RUN semantic static analysis or data-flow engines for taint, authorization, and multi-hop flow issues
  - RUN runtime traces, logs, metrics, and production incidents for nondeterministic or environment-sensitive failures

NOTES:
  Practical layered stack:
  1. Hotspot triage plus invariant and failure-path review on bounded local slices
  2. Universal bug-class sweep plus counterexample construction on the highest-risk paths
  3. Cheapest confirming proof next: targeted tests, semantic/static analyzers, runtime evidence, then feedback from escaped defects or incidents
```

## L7: Reporting, Review Status, and Residual Risk

```pdsl
UNIT BugFindingL7

PURPOSE:
  Produce the mandatory review status, findings, and residual risk report.

RULES:
  - ALWAYS assign review status PASS when: stated scope completed, every hotspot checked enough to resolve active bug hypotheses, every required companion slice covered within budget, no confirmed or high-confidence material defect remains open, and residual risk is explicitly bounded
  - ALWAYS assign review status PARTIAL when: coverage is incomplete, a hotspot or companion dependency was checkpointed, a material hypothesis still needs more bounded context, or dynamic validation is still required
  - ALWAYS assign review status FAIL when: methodology requirements were not followed well enough for a valid review, or at least one confirmed or high-confidence material defect remains open
  - ALWAYS use PARTIAL when the canonical hotspot budget forced a stop, any required companion slice remains unresolved, or follow-up validation is still required for a material hotspot
  - ALWAYS use FAIL when methodology requirements were not followed or an open material defect still stands at report time
  - NEVER use PASS when unresolved hotspots, unresolved companion effects, or required follow-up validation remain
  - ALWAYS count a companion as checked only after its inspected slice resolved the hotspot-relevant normative effect or proved the dependency non-material; otherwise it stays unresolved and forces PARTIAL

DO:
  - EMIT finding report per finding: bug class, severity (CRITICAL/MAJOR/MINOR only), confidence (CONFIRMED/HIGH/MEDIUM/LOW), location, violated invariant or contract, minimal trigger or counterexample, impact, evidence, proposed fix, best validation step
  - EMIT residual uncertainty: unproven high-risk areas, required dynamic checks not yet run, bug classes checked vs. only partially checked, reason for PARTIAL or FAIL status

RULES:
  - ALWAYS reject any finding severity value outside CRITICAL, MAJOR, or MINOR
  - NEVER collapse uncertainty into a blanket PASS
  - ALWAYS produce final review output
  - ALWAYS use standalone four-section order or map into host workflow wrapper; never introduce competing top-level headings

NOTES:
  Standalone report section order (authoritative even when companion checklists are loaded):
  1. Review Summary: review status, target scope, hotspots reviewed, files inspected, local/expanded review, companion slices loaded
  2. Findings: severity-sorted findings; if none, state "No confirmed findings"
  3. Coverage & Residual Risk: bug classes checked/partially checked, unchecked hotspots, dynamic checks not run, checklist ledger (ID | Status | Rationale) with PASS/FAIL/N/A/NOT REVIEWED
  4. Next Actions: cheapest confirming validations, required context expansions, or explicit statement that no further action is justified

  Checklist ledger: compact rows allowed only when every ID in that row shares the same status and rationale using exact ID lists or contiguous ranges. Record excluded items as NOT REVIEWED with rationale "excluded by review mode".

  cf-analyze integration: keep the six-section Validation Report wrapper; place Review Summary, Coverage & Residual Risk, and Next Actions inside "### 3. Semantic Review (MANDATORY)"; surface Findings defects in "### 6. Issues (if any)".
```

## Integration with Studio

```pdsl
UNIT BugFindingIntegration

PURPOSE:
  Define when and how to integrate this methodology with other Studio components.

WHEN:
  - REQUIRE user asks to find bugs, logic errors, edge cases, regressions, hidden failure modes, or "all problems" in code

DO:
  - RUN this methodology as the search procedure for code paths and failure modes
  - LOAD reverse-engineering.md when bug review needs structure beyond the local hotspot (entry points, module boundaries, dependency direction, state lifecycle, integration boundaries); start with TOC/section/range read, summarize and drop before loading next slice; skip for bounded local reviews
  - LOAD code-checklist.md before final output as mandatory acceptance and reporting checklist; start with only reporting, procedure, review-mode, conflict-resolution, and specific checklist-item slices required by chosen review mode or implicated by hotspot; do not load unrelated sections by default

RULES:
  - ALWAYS bound companion dependency loading by Context Budget & Expansion Control
  - ALWAYS checkpoint unresolved dependency, set final review status to PARTIAL, and recommend focused follow-up when required coverage cannot be completed safely within budget
```

## Execution Protocol

Use this sequence for each hotspot:

```pdsl
UNIT BugFindingExecution

PURPOSE:
  Execute the seven-step review sequence for each code hotspot.

DO:
  - RUN Step 1: map the boundary and impacted path
  - RUN Step 2: extract explicit and inferred invariants
  - RUN Step 3: walk the happy path and the most dangerous unhappy paths
  - RUN Step 4: sweep all universal bug classes
  - RUN Step 5: build or refute a concrete counterexample
  - RUN Step 6: propose the cheapest confirming dynamic check
  - RUN Step 7: report confidence and residual risk

RULES:
  - ALWAYS apply Context Budget & Expansion Control as the single canonical hotspot budget and escalation rule
  - ALWAYS keep only the active path, invariant, and evidence in working context; summarize and drop processed code before expanding
  - ALWAYS expand to adjacent files or companion requirements only when a plausible bug depends on that boundary and the current slice cannot resolve it
  - ALWAYS emit a checkpoint and set status per L7 when the canonical budget forces a stop; never broaden implicitly
```

## Validation

Review is complete when:

- [ ] Risk hotspots were identified and prioritized
- [ ] Explicit and inferred invariants were extracted
- [ ] Happy path and failure paths were both examined
- [ ] All universal bug classes were swept for the target scope
- [ ] Each reported issue includes a plausible trigger or counterexample
- [ ] Missing proof was converted into a concrete dynamic follow-up
- [ ] Review status, bounded companion coverage, and residual uncertainty were reported explicitly
- [ ] Any unresolved companion dependency or required follow-up validation forced `PARTIAL` instead of `PASS`
- [ ] Final output either used the standalone four-section order or mapped it into the host workflow's mandatory wrapper without competing top-level headings
- [ ] No claim of `100%` detection or blanket coverage was made
