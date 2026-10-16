---
cf: true
type: requirement
name: Review Anti-Patterns
version: 1.0
purpose: Authoritative definitions of anti-patterns AP-001..AP-008 and the self-check trailer that review and bug-finding agents emit
---

# Review Anti-Patterns

<!-- toc -->

- [Anti-Pattern Catalog](#anti-pattern-catalog)
- [Self-Check Trailer](#self-check-trailer)

<!-- /toc -->

This file is the single source of truth for the numbered anti-patterns `AP-001`..`AP-008`.
Agents that require an "AP-001..AP-008 self-check" receive this file from the controller
as the `review_anti_patterns` asset of `SHARED_CONTEXT_PACK`; they do not open it from disk.

"Reviewed paths" means every path the agent's frozen input payload declares as review
evidence: `target_paths`, `cross_ref_paths`, `code_paths`, `design_artifact_path`, or the
equivalent fields of that agent.

## Anti-Pattern Catalog

| ID | Name | Description | Detection signal |
|---|---|---|---|
| AP-001 | SKIP_SEMANTIC | A deterministic check passed, so the semantic review was skipped | The output has no per-category or per-path semantic results |
| AP-002 | MEMORY_VALIDATION | Evidence comes from context, a summary, or an inline payload, not from a fresh read | A reviewed path has no fresh tool/disk read in this turn |
| AP-003 | ASSUMED_NA | A checklist category is marked `N/A` without a statement in the reviewed file | An `N/A` row has no quote of an explicit "not applicable" statement |
| AP-004 | BULK_PASS | "All checks pass" is claimed without per-item verification | A PASS covers several categories or paths with one piece of evidence |
| AP-005 | SELF_TEST_LIE | The self-check is answered before the work is done, or claims what the output does not show | A self-check line contradicts the findings, table, or read log |
| AP-006 | SHORTCUT_OUTPUT | A result is reported without the sections the agent's output contract requires | A required output section is absent |
| AP-007 | TEDIUM_AVOIDANCE | Categories, paths, or checklist items are left out because the review is long | An in-scope category or path appears nowhere in the output |
| AP-008 | CONTEXT_ASSUMPTION | File content is assumed from earlier turns, or from content that was truncated or summarized | A claim cites content that was not read in full in this turn |

```pdsl
UNIT ReviewAntiPatterns

PURPOSE:
  Define AP-001..AP-008 and make any detected anti-pattern invalidate the run.

RULES:
  - ALWAYS treat the catalog above as the complete and only definition of AP-001..AP-008
  - ALWAYS check every anti-pattern against the finished output, not against the plan
  - ALWAYS treat a run with any VIOLATION as not complete: NEVER claim PASS or a
    complete-run status for it, and report the violation in the trailer
  - NEVER invent anti-pattern IDs or meanings beyond this catalog
```

## Self-Check Trailer

The trailer is the last block of the agent's output, after findings, tables, and summaries.

```text
AP self-check:
- AP-001 SKIP_SEMANTIC: PASS | VIOLATION | N/A — <evidence or reason>
- AP-002 MEMORY_VALIDATION: PASS | VIOLATION | N/A — <evidence or reason>
- AP-003 ASSUMED_NA: PASS | VIOLATION | N/A — <evidence or reason>
- AP-004 BULK_PASS: PASS | VIOLATION | N/A — <evidence or reason>
- AP-005 SELF_TEST_LIE: PASS | VIOLATION | N/A — <evidence or reason>
- AP-006 SHORTCUT_OUTPUT: PASS | VIOLATION | N/A — <evidence or reason>
- AP-007 TEDIUM_AVOIDANCE: PASS | VIOLATION | N/A — <evidence or reason>
- AP-008 CONTEXT_ASSUMPTION: PASS | VIOLATION | N/A — <evidence or reason>
- Fresh reads: all reviewed paths were read fresh via tool/disk access this turn | NOT ALL — <unread paths>
```

```pdsl
UNIT SelfCheckTrailer

PURPOSE:
  Make the self-check observable and verifiable.

RULES:
  - ALWAYS emit one line for each of AP-001..AP-008, in order, and the Fresh reads line
  - ALWAYS write the self-check after all other output is complete
  - ALWAYS give concrete evidence for PASS (read counts, row counts, section names)
  - ALWAYS use N/A only when the anti-pattern has no subject in this agent's contract,
    and state that reason (for example: no checklist, so AP-003 has nothing to check)
  - NEVER write a bare PASS without evidence
```
