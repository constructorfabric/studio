---
name: analyze-state-summary
description: "Invoke when loading the Analyze State Summary table showing the target-type x template / checklist / design usage matrix."
purpose: Analyze State Summary table — target-type × template / checklist / design usage matrix
loaded_by: workflows/analyze.md
version: 1.0
---

<!-- toc -->

- [State Summary](#state-summary)

<!-- /toc -->

## State Summary

| State | TARGET_TYPE | Uses Template | Uses Checklist | Uses Design |
|-------|-------------|---------------|----------------|-------------|
| Analysing artifact | artifact | ✓ | ✓ | parent only |
| Analysing code | code | ✗ | ✓ | ✓ |
| Explaining (EXPLAIN_MODE) | artifact or code | ✗ (uses storytelling protocol) | ✗ (replaced by storytelling protocol) | parent + linked-via-registry |
| CHANGE_REVIEW | code-or-prompt diff | ✗ | ✓ (per matched methodology) | parent only |
| CONSISTENCY_REVIEW | multi-path artifact | ✗ | ✓ | ≥ 2 cross-refs |
| PROMPT_REVIEW | prompt | ✗ | ✓ (prompt-engineering.md) | N/A |
| CODE_BUG_REVIEW | code | ✗ | ✓ (bug-finding.md) | parent only |
