---
name: analyze-phase-0.5-scope
description: "Invoke when clarifying direct analysis scope and resolving multi-path inputs before Phase 1."
purpose: Clarify direct analysis scope and multi-path inputs
loaded_by: workflows/analyze/phase-0-dependencies.md
version: 1.0
---

```pdsl
UNIT AnalyzeScope

PURPOSE:
  Clarify analysis scope for multi-path, consistency, or unregistered artifact
  targets before Phase 1 file checks.

WHEN:
  - REQUIRE scope is unclear

DO:
  - EMIT_MENU ScopeMenu
  - WAIT user.reply
  - STOP_TURN

MENU ScopeMenu:
  TITLE: |
    Why this input is needed: analysis rigor depends on whether I should validate
    the whole target, a bounded slice, or skip deterministic validation only.
  OPTIONS:
    1 full    -> proceed with full analysis — check the entire artifact/codebase target
    2 partial -> SET ANALYZE_SCOPE = partial; SET ANALYZE_SCOPE_SELECTORS = user supplied sections/IDs; semantic review still runs
    3 semantic-only -> SET SEMANTIC_ONLY = true; skip deterministic validation only; semantic review still runs
  INVALID:
    EMIT "Reply `1`, `2: <sections-or-IDs>`, or `3`."
    WAIT user.reply
    STOP_TURN

DO (traceability mode):
  Read artifacts.toml.
  IF FULL traceability: check code markers and codebase cross-refs.
  IF DOCS-ONLY traceability: skip codebase traceability checks.

DO (registry consistency):
  Verify target path exists in artifacts.toml, kind matches, system assignment correct.
  IF not registered:
    EMIT warning
    REQUIRE semantic-only mode unless user registers target first

DO (cross-reference scope):
  Identify parent artifacts, child artifacts, and code directories when relevant.

DO (consistency-path capture):
  IF consistency review: collect at least two paths into {PATHS}.
  IF fewer than two paths supplied:
    SET consistency-skipped = "single-target"
    CONTINUE other selected reviewers

RULES:
  - ALWAYS check artifacts.toml for registry consistency when ARTIFACT_REVIEW=true
  - ALWAYS warn and require semantic-only mode when target is not registered,
    unless user registers it first
  - NEVER proceed with consistency review when fewer than two paths are available

NOTES:
  Suggested modes: 1 for ordinary review requests; 3 only when the target is
  unregistered or deterministic validation is not applicable. "semantic-only"
  skips the deterministic gate only; all applicable semantic review still runs.
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
