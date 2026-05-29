---
name: analyze-phase-0-dependencies
description: "Invoke when running Analyze Phase 0 / 0.5 for mode detection, dependency setup, and scope capture."
purpose: Analyze Phase 0 / 0.5 dispatcher — mode detection, dependency setup, scope capture
loaded_by: workflows/analyze.md
version: 1.0
---

<!-- toc -->
<!-- /toc -->

```text
UNIT AnalyzePhase0Dependencies

PURPOSE:
  Detect analyze mode flags, resolve dependencies, run the inline-fallback
  probe, and hand off to the plan-escalation gate.

STATE:
  SEMANTIC_ONLY: false | true
    default: false
  PROMPT_REVIEW: false | true
    default: false
  PROMPT_BUG_REVIEW: false | true
    default: false
  EXPLAIN_MODE: false | true
    default: false
  CHANGE_REVIEW: false | true
    default: false
  ARTIFACT_REVIEW: false | true
    default: false
  CODE_REVIEW: false | true
    default: false
  CODE_BUG_REVIEW: false | true
    default: false
  CONSISTENCY_REVIEW: false | true
    default: false
    scope: workflow_run

DO:
  Match conditions and set flags (do NOT re-initialize flags to false here):
    IF semantic command:            SET SEMANTIC_ONLY = true
    IF prompt/instruction review:   SET PROMPT_REVIEW = true
    IF defect-oriented prompt/instruction review: SET PROMPT_BUG_REVIEW = true
    IF explain/storytelling:        SET EXPLAIN_MODE = true
    IF commit/branch/patch/diff/worktree review: SET CHANGE_REVIEW = true
    IF resolved target is artifact AND no prompt/code methodology owns it:
                                    SET ARTIFACT_REVIEW = true
    IF resolved target is code AND NOT CHANGE_REVIEW:
                                    SET CODE_REVIEW = true
    IF CODE_REVIEW AND request contains bug/defect/regression/root cause/crash/broken/hunt:
                                    SET CODE_BUG_REVIEW = true
  FORBID opening code methodology files in the orchestrator
  FORBID opening prompt methodology files in the orchestrator
  LOAD {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md
  IF CHANGE_REVIEW == true:
    LOAD {cf-studio-path}/.core/workflows/analyze/phase-0-change-review-scope.md
  LOAD {cf-studio-path}/.core/requirements/raw-input-overflow.md
  IF ARTIFACT_REVIEW == true AND rules.md is loaded:
    dependencies are resolved
    IF artifact review dependencies are missing:
      ask for missing checklist/template/example only when ARTIFACT_REVIEW == true
  REQUIRE all dependencies available before proceeding to Phase 1
  LOAD {cf-studio-path}/.core/workflows/analyze/phase-0.1-plan-escalation-gate.md
  IF (target_paths has more than one entry AND no explicit scope named)
     OR (CONSISTENCY_REVIEW == true AND fewer than two paths captured)
     OR (ARTIFACT_REVIEW == true AND artifact not in artifacts.toml):
    LOAD {cf-studio-path}/.core/workflows/analyze/phase-0.5-scope.md
  CONTINUE workflows/analyze/phase-1-file-check.md

RULES:
  - MUST_NOT pre-enable CODE_REVIEW or CODE_BUG_REVIEW for a diff-scoped run
    before code_targets is derived from diff_scope.changed_files
  - MUST_NOT proceed to Phase 1 until all dependencies are available
  - MUST_NOT open code or prompt methodology files in the orchestrator

NOTES:
  Variable checkpoint: {cfs_cmd}, {cf-studio-path}, and {project_root}
  come from `{cf-studio-path}/.core/skills/studio/protocol.md`; re-run info after context loss.
  Per-run analyze flags are initialized in preamble.md; this file only
  matches conditions to set flags to true. ARTIFACT_REVIEW=false is the
  default before artifact target detection.
  Code and prompt methodologies do not require artifact checklist/template/
  example to proceed; they use their own reviewer methodology files in Phase 3.
```
