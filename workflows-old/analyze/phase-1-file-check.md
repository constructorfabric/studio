---
name: analyze-phase-1-file-check
description: "Invoke when running Analyze Phase 1 to verify every path in {PATHS} exists, is readable, and non-empty."
purpose: Analyze Phase 1 — verify every path in {PATHS} exists, is readable, and non-empty
loaded_by: workflows/analyze.md
version: 1.0
---

```pdsl
UNIT AnalyzePhase1FileCheck

PURPOSE:
  Verify every path in {PATHS} exists, is readable, and non-empty before
  any analysis proceeds.

INPUT:
  {PATHS}: list of paths to check
    default: [{PATH}]
    expanded by: workflows/analyze/phase-0.5-scope.md § Consistency-path capture
                 when consistency review is in scope

DO:
  - RUN FOR EACH path in {PATHS}:
    Check path exists AND is readable AND is not empty.
    IF any check fails:
      - EMIT "✗ Target not found: {failing path}"
      - EMIT "→ Invoke skill `cf-generate` to create it (resolve the failing path's kind via {cf-studio-path}/config/artifacts.toml when multiple paths are in scope)"
      STOP analysis

RULES:
  - ALWAYS check every path in {PATHS}, not just the first
  - ALWAYS STOP analysis on any failing path check
  - NEVER proceed to Phase 2 if any path fails
```

