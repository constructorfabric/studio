---
name: analyze-phase-0.5-scope
description: "Invoke when clarifying direct analysis scope and resolving multi-path inputs before Phase 1."
purpose: Clarify direct analysis scope and multi-path inputs
loaded_by: workflows/analyze/phase-0-dependencies.md
version: 1.0
---

If scope is unclear, ask:

```text
Why this input is needed: analysis rigor depends on whether I should validate
the whole target, a bounded slice, or skip deterministic checks.

1. Full analysis — check the entire artifact/codebase target.
2. Partial analysis — check specific sections/IDs; semantic review still runs.
3. Semantic-only review — skip deterministic gate; semantic review still runs.

Suggested: 1 for ordinary review requests; 3 only when the target is
unregistered or deterministic validation is not applicable.

Reply `1`, `2: <sections-or-IDs>`, or `3`.
```

Traceability mode: read artifacts.toml. `FULL` checks code markers and
codebase cross-refs; `DOCS-ONLY` skips codebase traceability checks.

Registry consistency: verify target path exists in artifacts.toml, kind
matches, and system assignment is correct. If not registered, warn and require
semantic-only mode unless the user registers it first.

Cross-reference scope: identify parent artifacts, child artifacts, and code
directories when relevant.

Consistency-path capture: for explicit consistency reviews, collect at least
two paths into `{PATHS}`. If fewer than two paths are supplied, log
`consistency-skipped: single-target` and continue other selected reviewers.
