# Review Finding Contract

```pdsl
UNIT ReviewFindingContract
PURPOSE: Define the fields every review finding must report, for all review operations.
RULES:
  ALWAYS report each finding of any review operation with ID, SEVERITY, LOCATION (path plus line or range), EVIDENCE, ROOT_CAUSE, IMPACT, SUGGESTED_FIX, VERIFICATION (how to confirm the fix resolves it), and CONFIDENCE
  ALWAYS set ID to a stable unique finding identifier within the current ReviewFindingsReport so browser marking, partial fix approval, and approved-fix dispatch can reference the same finding deterministically
  ALWAYS set SEVERITY to exactly one of: CRITICAL, MAJOR, MINOR
  ALWAYS apply this finding contract to every review operation, regardless of which skill or workflow runs it
  NEVER emit a review finding that is missing any of the required fields
  NEVER emit duplicate IDs within the same ReviewFindingsReport
  NEVER emit any SEVERITY value other than CRITICAL, MAJOR, or MINOR; reserve deterministic validator severities such as error for validator diagnostics outside ReviewFindingContract
```
