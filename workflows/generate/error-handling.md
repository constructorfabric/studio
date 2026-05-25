---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when a tool/dispatch failure, user abandonment, or validation-failure loop (3+) occurs during any generate phase and the canonical error-handling guidance must be applied.
---

<!-- toc -->

- [Error Handling](#error-handling)

<!-- /toc -->



## Error Handling

Tool failure:

```text
⚠️ Tool error: {error message}
→ Check Python environment and dependencies
→ Verify Constructor Studio is correctly configured
→ Run `{cfs_cmd} update` to refresh the adapter if the local installation is stale
```

STOP — do not continue with incomplete state.

User abandonment: do not auto-proceed with assumptions; state is resumed by
re-running the workflow command. Target artifact/code files are still untouched
before Phase 4, but Generate Phase 1.5 disk mode may already have written
author-plan cache files under `{cf-studio-path}/.cache/generate-plans/`.
If `AUTHOR_PLAN_CACHE_DIR` exists or a partial cache write was reported, surface
that cache state on resume or abandonment handling instead of claiming that no
pre-Phase-4 files exist. No automatic cleanup is required, but partial cache
writes must be disclosed and either resumed from or removed explicitly.

Validation failure loop (3+ times):

```text
⚠️ Deterministic validation is still failing after repeated fixes. Options:
1. Review checklist requirements manually and fix the reported validator errors
2. Simplify artifact scope or revert the last change set, then re-run validation
3. RELAXED mode only: stop the validated success path and return the result as explicitly unvalidated with `Deterministic gate: FAIL`; do not present it as PASS, and if files were written still emit the Post-Write Review Handoff menu (and Remediation Handoff menu when remaining_findings non-empty) before ending the response
Reply with `1`, `2`, or `3`.
1. Review checklist requirements manually and fix the reported validator errors — Suggested default path; continue trying to reach validator `PASS`.
2. Simplify artifact scope or revert the last change set, then re-run validation — Use this when the current scope is too broad or the last changes were incorrect.
3. RELAXED mode only: stop the validated success path and exit as explicitly unvalidated — Use this only in RELAXED mode when fixes are not feasible; the result is marked `Deterministic gate: FAIL` and is NOT presented as PASS, and if files were written still emit the Post-Write Review Handoff menu (and Remediation Handoff menu when remaining_findings non-empty) before ending the response.
```

Option 3 distinct from option 1 in being RELAXED-mode only and exiting as explicitly unvalidated.

A legitimate RELAXED `Deterministic gate: SKIPPED` exit for file-writing output is separate from this failure loop: use it only when `Validator availability proof` shows that no canonical validator route is target-applicable for the current written output, and record the explicit `Validator availability proof`, `Skip reason`, `Validator-backed evidence note`, and mandatory Post-Write Review Handoff menu (plus the Remediation Handoff menu when applicable) without inventing a validation-failure narrative.
