---
cf: true
type: requirement
name: Code Quality Expert Checklist
version: 1.0
purpose: Generic (kit-agnostic) quality checklist for code changes and reviews
---

# Code Quality Expert Checklist (Generic)

<!-- toc -->

- [Procedure](#procedure)
- [Severity](#severity)
- [Review Modes](#review-modes)
- [Engineering Best Practices (ENG)](#engineering-best-practices-eng)
- [Code Quality (QUAL)](#code-quality-qual)
- [Error Handling (ERR)](#error-handling-err)
- [Security (SEC)](#security-sec)
- [Performance (PERF)](#performance-perf)
- [Observability (OBS)](#observability-obs)
- [Testing (TEST)](#testing-test)
- [Validation Summary](#validation-summary)
- [Conflict Resolution](#conflict-resolution)
- [Reporting](#reporting)
- [Reporting Commitment](#reporting-commitment)

<!-- /toc -->

**Companion methodology**: for bug hunting, logic bug review, edge-case search, regression risk analysis, or maximum-recall code review, also use `bug-finding.md` as the search procedure for hotspot mapping, invariant extraction, failure-path exploration, counterexample construction, and dynamic-escalation guidance.

## Procedure

```pdsl
UNIT CodeReviewProcedure

PURPOSE:
  Define the mandatory steps for applying this checklist to any code review.

WHEN:
  - REQUIRE a code review begins

DO:
  - SET code_domain: identify the domain of the code being reviewed
  - RUN applicability decision per checklist item
  - SET item_status: PASS, FAIL, N/A with rationale, or NOT REVIEWED when excluded by review mode

RULES:
  - NEVER skip silently; missing rationale for an inapplicable item is a violation
  - ALWAYS report issues only; each issue includes checklist ID, severity, location, evidence, why it matters, and a concrete fix
```

## Severity

- CRITICAL: unsafe/broken/security issue; blocks merge.
- HIGH: major quality issue; fix before merge.
- MEDIUM: meaningful improvement; fix when feasible.
- LOW: minor improvement; optional.

## Review Modes

```pdsl
UNIT CodeReviewModes

PURPOSE:
  Define which checklist items are required for each review mode based on code size and risk.

WHEN:
  - REQUIRE review mode is selected

DO:
  - SET review_mode: Quick when code is fewer than 50 LOC and low risk
  - SET review_mode: Standard when code is 50-200 LOC and medium risk
  - SET review_mode: Full when code is more than 200 LOC or architectural

RULES:
  - ALWAYS check SEC-CODE-001/002/003, SEC-CODE-NO-001/002, ERR-CODE-001/003, ERR-CODE-NO-001, QUAL-CODE-NO-002 in Quick mode; spot-check ENG-CODE-001 and QUAL-CODE-001; mark the rest NOT REVIEWED
  - ALWAYS check all CRITICAL and HIGH items plus all MUST NOT items in Standard mode
  - ALWAYS check all items in Full mode; triage order is SEC, ERR, QUAL/TEST, ENG/QUAL, PERF, OBS
```

# MUST HAVE
## Engineering Best Practices (ENG)
### ENG-CODE-001: Test-Driven Development (TDD) [HIGH]
- [ ] New behavior has corresponding tests.
- [ ] Tests were written before or alongside implementation.
- [ ] Tests fail if implementation is removed.
- [ ] Tests verify outcomes, not just no-crash behavior.
- [ ] Test names describe the behavior under test.
- [ ] Tests run independently.
### ENG-CODE-002: Single Responsibility Principle (SRP) [HIGH]
- [ ] Each module, class, or function has one reason to change.
- [ ] Functions do one thing well.
- [ ] Classes have a single clear purpose.
- [ ] No god objects or kitchen-sink modules exist.
- [ ] UI, business logic, and data access responsibilities are separated.
### ENG-CODE-003: Open/Closed Principle (OCP) [MEDIUM]
- [ ] Behavior is extended through composition or configuration.
- [ ] New functionality does not require unrelated working code to change.
- [ ] Extension points are clear and intentional.
- [ ] Existing working code is not modified just to add unrelated features.
### ENG-CODE-004: Liskov Substitution Principle (LSP) [HIGH]
- [ ] Implementations honor interface contracts.
- [ ] Subtypes remain substitutable for their base types.
- [ ] Polymorphic use does not cause surprising behavior.
- [ ] Subtypes do not strengthen preconditions.
- [ ] Subtypes do not weaken postconditions.
### ENG-CODE-005: Interface Segregation Principle (ISP) [MEDIUM]
- [ ] Interfaces are small and purpose-driven.
- [ ] Fat interfaces are avoided.
- [ ] Clients depend only on the methods they use.
- [ ] Role interfaces are preferred over header interfaces.
### ENG-CODE-006: Dependency Inversion Principle (DIP) [HIGH]
- [ ] High-level modules do not depend directly on low-level modules.
- [ ] Both layers depend on abstractions.
- [ ] Dependencies are injectable.
- [ ] Core logic is testable without heavy integration setup.
- [ ] External dependencies sit behind interfaces.
### ENG-CODE-007: Don't Repeat Yourself (DRY) [MEDIUM]
- [ ] Copy-paste duplication is absent.
- [ ] Shared logic is extracted with clear ownership.
- [ ] Abstraction happens only after a real repeated pattern appears.
- [ ] Constants are defined once.
- [ ] Common patterns are abstracted appropriately.
### ENG-CODE-008: Keep It Simple, Stupid (KISS) [HIGH]
- [ ] The simplest correct solution was chosen.
- [ ] Unnecessary complexity was avoided.
- [ ] Code remains readable without heavy explanation.
- [ ] Clever tricks were avoided in favor of clarity.
- [ ] Standard patterns were preferred over novelty.
### ENG-CODE-009: You Aren't Gonna Need It (YAGNI) [HIGH]
- [ ] No speculative features were added.
- [ ] No unused abstractions remain.
- [ ] No configuration exists only for hypothetical scenarios.
- [ ] No unused extension points were introduced.
- [ ] Capability was added only for current use cases.
### ENG-CODE-010: Refactoring Discipline [MEDIUM]
- [ ] Refactoring happens only after tests pass.
- [ ] Behavior stays unchanged during refactoring.
- [ ] Structure improves without introducing features.
- [ ] Refactoring occurs in small incremental steps.
- [ ] Refactoring and feature work are not mixed in one commit.
## Code Quality (QUAL)
### QUAL-CODE-001: Readability [HIGH]
- [ ] Naming is clear and descriptive.
- [ ] Naming conventions stay consistent.
- [ ] Code reads clearly.
- [ ] Complex logic is explained when needed.
- [ ] Misleading names and abbreviations are absent.
### QUAL-CODE-002: Maintainability [HIGH]
- [ ] Code is easy to modify.
- [ ] Changes stay localized.
- [ ] Dependencies are explicit and minimal.
- [ ] Hidden coupling is absent.
- [ ] Module boundaries are clear.
### QUAL-CODE-003: Testability [HIGH]
- [ ] Core logic is testable without external systems.
- [ ] Dependencies are injectable for tests.
- [ ] Side effects are isolated and mockable.
- [ ] Behavior is deterministic.
- [ ] Outcomes are observable.
### QUAL-CODE-004: Complexity Control [HIGH]
- [ ] Cyclomatic and cognitive complexity stay proportionate to the problem being solved.
- [ ] Deep nesting and long branching chains are simplified or extracted.
- [ ] Complex logic hotspots are isolated behind clear abstractions with focused tests.
- [ ] Control flow remains understandable without tracing excessive hidden state or side effects.
- [ ] Necessary complexity is justified by requirements rather than convenience or incidental design.
Optional: Quantitative guidance — advisory calibration only, not hard limits. Reviewers may use rough thresholds such as cyclomatic complexity `<= 10` for simple functions, `11–20` for moderate functions, and `> 20` as a refactor flag; max nesting depth around `3–4` levels; function length around `~200` LOC as a soft upper bound; and similar cognitive-complexity breakpoints for triage.
## Error Handling (ERR)
### ERR-CODE-001: Explicit Error Handling [CRITICAL]
- [ ] Errors fail explicitly.
- [ ] Error conditions are handled.
- [ ] Exceptions are not swallowed.
- [ ] Error messages are actionable.
- [ ] Stack traces remain available for debugging without leaking into production UI.
### ERR-CODE-002: Graceful Degradation [HIGH]
- [ ] Partial failures are handled.
- [ ] Recovery actions are defined.
- [ ] Fallback behavior is defined.
- [ ] User-facing errors stay friendly.
- [ ] System-facing errors stay detailed.
### ERR-CODE-003: Input Validation [CRITICAL]
- [ ] All external inputs are validated at system boundaries.
- [ ] Validation rules are clear and consistent.
- [ ] Invalid input is rejected early.
- [ ] Validation errors are specific.
- [ ] Internal code is not redundantly revalidated.
## Security (SEC)
### SEC-CODE-001: Injection Prevention [CRITICAL]
- [ ] Queries are parameterized.
- [ ] Command injection is blocked.
- [ ] XSS is blocked.
- [ ] Path traversal is blocked.
- [ ] User input never enters dangerous contexts unsanitized.
### SEC-CODE-002: Authentication & Authorization [CRITICAL]
- [ ] Required authentication checks exist at relevant entry points.
- [ ] Required authorization checks exist for protected operations.
- [ ] Privilege escalation is prevented.
- [ ] Session management is secure.
- [ ] Credentials are not hardcoded.
### SEC-CODE-003: Data Protection [CRITICAL]
- [ ] Sensitive data is not logged.
- [ ] PII is handled appropriately.
- [ ] Secrets stay out of code.
- [ ] Encryption is used where required.
- [ ] Sensitive data is transmitted securely.
## Performance (PERF)
### PERF-CODE-001: Efficiency [MEDIUM]
- [ ] Obvious performance anti-patterns are absent.
- [ ] N+1 query patterns are avoided.
- [ ] Unnecessary allocations are avoided.
- [ ] Resources are cleaned up properly.
- [ ] Appropriate data structures are chosen.
### PERF-CODE-002: Scalability [MEDIUM]
- [ ] Algorithmic complexity matches expected data size.
- [ ] Hot paths avoid blocking operations.
- [ ] Caching is used where beneficial.
- [ ] Batch operations are used where appropriate.
- [ ] Large datasets use pagination where appropriate.
## Observability (OBS)
### OBS-CODE-001: Logging [MEDIUM]
- [ ] Meaningful boundary events are logged.
- [ ] Log levels are used appropriately.
- [ ] Secrets are not logged.
- [ ] Correlation IDs are propagated.
- [ ] Logs include enough debugging context.
### OBS-CODE-002: Metrics & Tracing [LOW]
- [ ] Key operations expose metrics when applicable.
- [ ] Tracing is integrated where beneficial.
- [ ] Health checks exist.
- [ ] Alertable conditions are identified.
- [ ] Performance baselines are established.
- [ ] `N/A` is used only when the service has no long-running or SLO/SLA requirements.
## Testing (TEST)
### TEST-CODE-001: Test Coverage [HIGH]
- [ ] Public APIs are covered.
- [ ] Happy paths are covered.
- [ ] Error paths are covered.
- [ ] Edge cases are covered.
- [ ] Boundary conditions are covered.
### TEST-CODE-002: Test Quality [HIGH]
- [ ] Tests are fast.
- [ ] Tests are reliable.
- [ ] Tests are independent.
- [ ] Tests are readable.
- [ ] Assertions are clear.
### TEST-CODE-003: Test Completeness [MEDIUM]
- [ ] Business logic has unit tests.
- [ ] External dependencies have integration tests.
- [ ] Critical paths have E2E tests when applicable.
- [ ] Regression scenarios are covered.
- [ ] Tests document expected behavior.
# MUST NOT HAVE
### QUAL-CODE-NO-001: No Incomplete Work Markers [HIGH]
- [ ] Untracked TODO markers are absent.
- [ ] FIXME markers are absent.
- [ ] XXX markers are absent.
- [ ] HACK markers are absent.
- [ ] Temporary production fixes that became permanent are absent.
- [ ] Incomplete work is either finished or tracked in an issue.
### QUAL-CODE-NO-002: No Placeholder Implementations [CRITICAL]
- [ ] `unimplemented!()` / `todo!()` are absent from production logic.
- [ ] `NotImplementedException`-style placeholders are absent from production paths.
- [ ] Python `pass` plus TODO placeholders are absent from production paths.
- [ ] Empty catch blocks are absent.
- [ ] Stub methods that do nothing are absent.
- [ ] Placeholder implementations are either removed or completed.
### ERR-CODE-NO-001: No Silent Failures [CRITICAL]
- [ ] Empty catch blocks are absent.
- [ ] Swallowed exceptions are absent.
- [ ] Fallible return values are not ignored.
- [ ] `_ = might_fail()` patterns without handling are absent.
- [ ] `try/except: pass` patterns are absent.
- [ ] Errors are handled or propagated explicitly.
### ERR-CODE-NO-002: No Unsafe Panic Patterns [HIGH]
- [ ] Bare `unwrap()` is absent from production paths.
- [ ] Bare `panic!()` is absent from production paths.
- [ ] `expect()` calls have meaningful messages.
- [ ] Force-unwrapping without guards is absent.
- [ ] Assertions are absent from production paths.
- [ ] Proper error handling is used instead.
### TEST-CODE-NO-001: No Ignored Tests [MEDIUM]
- [ ] Ignored tests have documented reasons.
- [ ] Disabled tests have documented reasons.
- [ ] Skip markers have explanations.
- [ ] Commented-out tests are absent.
- [ ] Placeholder tests are absent.
- [ ] Ignored tests are fixed or removed.
### SEC-CODE-NO-001: No Hardcoded Secrets [CRITICAL]
- [ ] API keys are absent from code.
- [ ] Passwords are absent from code.
- [ ] Tokens are absent from code.
- [ ] Credentialed connection strings are absent from code.
- [ ] Private keys are absent from code.
- [ ] Secrets are stored in environment variables or secret management.
### SEC-CODE-NO-002: No Dangerous Patterns [CRITICAL]
- [ ] `eval()` with user input is absent.
- [ ] `exec()` with user input is absent.
- [ ] `system()` with user input is absent.
- [ ] `innerHTML` with user input is absent.
- [ ] SQL string concatenation is absent.
- [ ] Safe alternatives are used.

## Validation Summary

```pdsl
UNIT CodeReviewValidationSummary

PURPOSE:
  Verify all required checklist items and quality gates are complete before finalizing the review.

WHEN:
  - REQUIRE code review is complete

DO:
  - REQUIRE all required MUST HAVE items for the selected review mode were checked
  - REQUIRE all MUST NOT items in scope were checked
  - REQUIRE build or compilation passes; justify exceptions explicitly
  - REQUIRE unit, integration, and E2E test status is verified; justify exceptions explicitly
  - REQUIRE linting passes; justify exceptions explicitly
  - REQUIRE coverage requirements are met; justify exceptions explicitly
  - REQUIRE all violations and critical issues are documented with specific feedback
```

## Conflict Resolution

```pdsl
UNIT CodeReviewConflictResolution

PURPOSE:
  Define resolution priority when checklist principles conflict.

RULES:
  - ALWAYS apply priority order: SEC > ERR > QUAL/TEST > ENG/QUAL > PERF > OBS
  - ALWAYS prefer KISS over DRY when abstraction adds complexity without benefit
  - ALWAYS prefer YAGNI over OCP for hypothetical extension points
  - ALWAYS prefer readability before premature optimization
  - ALWAYS prefer coverage before speed on critical paths
  - ALWAYS prefer detailed logs with friendly user messages
  - ALWAYS choose the safer failure mode when uncertain: security/data loss > inconvenience > performance
  - ALWAYS document the trade-off when choosing the safer failure mode
```

## Reporting

```pdsl
UNIT CodeReviewReporting

PURPOSE:
  Define the required report format for each review mode.

WHEN:
  - REQUIRE review report is produced

RULES:
  - ALWAYS report only problems
  - ALWAYS use compact table format for Quick mode: | # | ID | Sev | Location | Issue | Fix | plus review-mode note
  - ALWAYS use compact or full format for Standard mode
  - ALWAYS include Issue, Location, Evidence, Why It Matters, and Proposal for each issue in Full mode
```

## Reporting Commitment

```pdsl
UNIT CodeReviewReportingCommitment

PURPOSE:
  Enforce completeness and honesty obligations for the final review report.

WHEN:
  - REQUIRE review report is finalized

RULES:
  - ALWAYS report every found issue
  - ALWAYS use the required report format
  - ALWAYS include evidence and impact for each issue
  - ALWAYS include a concrete fix for each issue
  - NEVER hide or omit any known problems from the report
  - ALWAYS ensure the report is ready for iteration and re-review
```
