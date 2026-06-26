# Findings Aggregate

```pdsl
UNIT FindingsAggregateContract
PURPOSE: Aggregate multiple reviewer or analyzer finding sets into one canonical ordered report.
STATE:
  SET REVIEWER_FINDING_SETS: list | unset (default unset, scope unit_run)
  SET AGGREGATED_FINDINGS: list | unset (default unset, scope unit_run)
WHEN:
  REQUIRE REVIEWER_FINDING_SETS is provided
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/finding-contract.md WHEN ReviewFindingContract is not yet loaded
  RUN verify ReviewFindingContract loaded; EMIT "Required finding-contract.md not found — cannot aggregate findings" and STOP_TURN WHEN load fails
  RUN ReviewFindingContract
  RUN FindingsAggregateNormalizationContract
  RUN FindingsAggregateDedupContract
  RUN FindingsAggregateOrderingContract
  RUN FindingsAggregateIdContract
RULES:
  ALWAYS use this module to merge multi-reviewer findings before browser, fix-approval, or result rendering work begins
  ALWAYS preserve every surviving finding's ReviewFindingContract fields after aggregation
  NEVER let reviewer arrival order change the canonical aggregate result
```

```pdsl
UNIT FindingsAggregateNormalizationContract
PURPOSE: Normalize each reviewer-emitted finding to the canonical review finding shape before merge.
DO:
  RUN collect every finding from REVIEWER_FINDING_SETS into one working list
  RUN normalize location, severity, evidence, root_cause, impact, suggested_fix, verification, confidence, and any mechanical classification fields to ReviewFindingContract names
RULES:
  ALWAYS keep reviewer-specific extension fields only when they do not conflict with ReviewFindingContract
  NEVER preserve reviewer-local IDs as the final aggregate IDs
```

```pdsl
UNIT FindingsAggregateDedupContract
PURPOSE: Remove materially identical findings across reviewers.
DO:
  RUN deduplicate normalized findings by path, normalized location, root_cause, evidence, severity, and category when category is present
  SET AGGREGATED_FINDINGS = the surviving deduplicated findings
RULES:
  ALWAYS merge reviewer provenance into the surviving finding when duplicate findings came from more than one reviewer
  ALWAYS keep the strongest supported confidence when duplicate findings differ only by reviewer wording
  NEVER keep two findings that differ only by reviewer-local ID or equivalent prose paraphrase
```

```pdsl
UNIT FindingsAggregateOrderingContract
PURPOSE: Keep aggregate findings in stable deterministic order.
RULES:
  ALWAYS order AGGREGATED_FINDINGS by severity descending as CRITICAL, MAJOR, MINOR; then by path; then by line or line_range start; then by root_cause
  ALWAYS place findings without a concrete location after same-path findings with concrete locations
  NEVER sort by reviewer name, arrival timing, or freeform explanation text before stronger structural keys
```

```pdsl
UNIT FindingsAggregateIdContract
PURPOSE: Assign stable canonical IDs after deduplication and ordering.
DO:
  RUN assign AGGREGATED_FINDINGS IDs in deterministic sorted order using ReviewFindingContract ID rules and a stable aggregate namespace
RULES:
  ALWAYS emit unique IDs across the final aggregate report
  NEVER reuse reviewer-local IDs as aggregate IDs once deduplication changed ordering or cardinality
```
