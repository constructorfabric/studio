---
name: analyze-phase-1-file-check
description: "Invoke when running Analyze Phase 1 to verify every path in {PATHS} exists, is readable, and non-empty."
purpose: Analyze Phase 1 — verify every path in {PATHS} exists, is readable, and non-empty
loaded_by: workflows/analyze.md
version: 1.0
---

## Phase 1: File Existence Check

Check every path in `{PATHS}` (defaults to `[{PATH}]`; expanded by `workflows/analyze/phase-0.5-scope.md` § Consistency-path capture when consistency review is in scope) exists, is readable, and is not empty.

If any check fails for any path in `{PATHS}`:
```
✗ Target not found: {failing path}
→ Run /cf-generate to create it (resolve the failing path's kind via {cf-studio-path}/config/artifacts.toml when multiple paths are in scope)
```
STOP analysis.
