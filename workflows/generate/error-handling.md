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

```pdsl
UNIT GenerateErrorHandling

PURPOSE:
  Handle tool failure, user abandonment, and validation-failure loops
  during any generate phase.

ON_ERROR:
  tool_failure ->
    EMIT "⚠️ Tool error: {error message}
→ Check Python environment and dependencies
→ Verify Constructor Studio is correctly configured
→ Run `{cfs_cmd} update` to refresh the adapter if the local installation is stale"
    STOP_TURN

  user_abandonment ->
    NEVER auto-proceed with assumptions
    NOTE: state is resumed by re-running the workflow command
    NOTE: target artifact/code files are untouched before Phase 4
    IF AUTHOR_PLAN_CACHE_DIR exists OR partial cache write was reported:
      EMIT partial cache state (do not claim no pre-Phase-4 files exist)
    RULES:
      - NEVER claim no pre-Phase-4 files exist when AUTHOR_PLAN_CACHE_DIR exists
      - ALWAYS disclose partial cache writes
      - NEVER auto-cleanup

  - ALWAYS validation_failure_loop (3+ iterations) ->
    EMIT_MENU ValidationFailureMenu
    WAIT user.reply
    STOP_TURN

MENU ValidationFailureMenu:
  TITLE: Deterministic validation still failing after repeated fixes. Options:
  OPTIONS:
    1 ->
      NOTE: Review checklist requirements manually and fix the reported validator errors.
            Suggested default — continue trying to reach validator PASS.
      CONTINUE CurrentValidationPath
    2 ->
      NOTE: Simplify artifact scope or revert the last change set, then re-run validation.
            Use when current scope is too broad or last changes were incorrect.
      CONTINUE CurrentValidationPath
    3 ->
      REQUIRE rules_mode == RELAXED
      SET loop_exit = "explicit-unvalidated"
      EMIT "Deterministic gate: FAIL"
      NEVER presenting result as PASS
      IF manifest.paths_written non-empty:
        EMIT Post-Write Review Handoff menu
        IF remaining_findings non-empty:
          EMIT Remediation Handoff menu
  INVALID:
    EMIT "Reply with 1, 2, or 3."
    WAIT user.reply
    STOP_TURN

RULES:
  - NEVER continue with incomplete state on tool failure
  - NEVER auto-proceed on user abandonment
  - ALWAYS surface AUTHOR_PLAN_CACHE_DIR state on resume or abandonment
    when AUTHOR_PLAN_CACHE_DIR exists or a partial cache write was reported
  - ALWAYS Option 3 is RELAXED-mode only; result is marked Deterministic gate: FAIL
    and NEVER be presented as PASS
  - ALWAYS emit Post-Write Review Handoff menu (and Remediation Handoff when
    remaining_findings non-empty) even on option 3 exit when files were written

NOTES:
  A legitimate RELAXED Deterministic gate: SKIPPED exit (separate from this loop)
  is valid only when Validator availability proof shows no canonical validator
  route is target-applicable for the current written output. Record explicit
  Validator availability proof, Skip reason, Validator-backed evidence note, and
  mandatory Post-Write Review Handoff menu (plus Remediation Handoff when
  applicable) without inventing a validation-failure narrative.
```
