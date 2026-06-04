---
name: analyze-phase-0-dependencies
description: "Invoke when running Analyze Phase 0 / 0.5 for mode detection, dependency setup, and scope capture."
purpose: Analyze Phase 0 / 0.5 dispatcher — mode detection, dependency setup, scope capture
loaded_by: workflows/analyze.md
version: 1.0
---

<!-- toc -->
<!-- /toc -->

```pdsl
UNIT AnalyzePhase0Dependencies

PURPOSE:
  Detect analyze mode flags, resolve dependencies, run the inline-fallback
  probe, and hand off to the plan-escalation gate.

STATE:
  - SET SEMANTIC_ONLY: false | true
    default: false
  - SET PROMPT_REVIEW: false | true
    default: false
  - SET PROMPT_BUG_REVIEW: false | true
    default: false
  - SET EXPLAIN_MODE: false | true
    default: false
  - SET CHANGE_REVIEW: false | true
    default: false
  - SET ARTIFACT_REVIEW: false | true
    default: false
  - SET CODE_REVIEW: false | true
    default: false
  - SET CODE_BUG_REVIEW: false | true
    default: false
  - SET CONSISTENCY_REVIEW: false | true
    default: false
  - SET FREEFORM_REVIEW: false | true
    default: false
    scope: workflow_run

DO:
  - RUN Match conditions and set flags (do NOT re-initialize flags to false here):
    IF semantic command:            SET SEMANTIC_ONLY = true
    IF prompt/instruction review:   SET PROMPT_REVIEW = true
    IF defect-oriented prompt/instruction review: SET PROMPT_BUG_REVIEW = true
    IF explain/storytelling:        SET EXPLAIN_MODE = true
    IF commit/branch/patch/diff/worktree review: SET CHANGE_REVIEW = true
    IF resolved target is artifact AND no prompt/code methodology owns it:
                                    - SET ARTIFACT_REVIEW = true
    IF resolved target is code AND NOT CHANGE_REVIEW:
                                    - SET CODE_REVIEW = true
    IF CODE_REVIEW AND request contains bug/defect/regression/root cause/crash/broken/hunt:
                                    - SET CODE_BUG_REVIEW = true
    IF FREEFORM_REVIEW is not yet true AND all standard methodology flags are still
       false (CODE_REVIEW=false, CODE_BUG_REVIEW=false, CONSISTENCY_REVIEW=false,
       PROMPT_REVIEW=false, PROMPT_BUG_REVIEW=false, CHANGE_REVIEW=false,
       ARTIFACT_REVIEW=false) AND EXPLAIN_MODE=false AND ORIGINAL_INTENT has
       meaningful task content:
                                    - SET FREEFORM_REVIEW = true
  - NEVER opening code methodology files in the orchestrator
  - NEVER opening prompt methodology files in the orchestrator
  - LOAD {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md
  - REQUIRE CHANGE_REVIEW == true:
    - LOAD {cf-studio-path}/.core/workflows/analyze/phase-0-change-review-scope.md
  - LOAD {cf-studio-path}/.core/requirements/raw-input-overflow.md
  - REQUIRE ARTIFACT_REVIEW == true AND rules.md is loaded:
    dependencies are resolved
    IF artifact review dependencies are missing:
      ask for missing checklist/template/example only when ARTIFACT_REVIEW == true
  - REQUIRE all dependencies available before proceeding to Phase 1
  - LOAD {cf-studio-path}/.core/workflows/analyze/phase-0.1-plan-escalation-gate.md
  - REQUIRE (target_paths has more than one entry AND no explicit scope named)
     OR (CONSISTENCY_REVIEW == true AND fewer than two paths captured)
     OR (ARTIFACT_REVIEW == true AND artifact not in artifacts.toml):
    - LOAD {cf-studio-path}/.core/workflows/analyze/phase-0.5-scope.md
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-1-file-check.md

RULES:
  - NEVER pre-enable CODE_REVIEW or CODE_BUG_REVIEW for a diff-scoped run
    before code_targets is derived from diff_scope.changed_files
  - NEVER proceed to Phase 1 until all dependencies are available
  - NEVER open code or prompt methodology files in the orchestrator

NOTES:
  Variable checkpoint: {cfs_cmd}, {cf-studio-path}, and {project_root}
  come from `{cf-studio-path}/.core/skills/studio/protocol.md`; re-run info after context loss.
  Per-run analyze flags are initialized in preamble.md; this file only
  matches conditions to set flags to true. ARTIFACT_REVIEW=false is the
  default before artifact target detection.
  Code and prompt methodologies do not require artifact checklist/template/
  example to proceed; they use their own reviewer methodology files in Phase 3.
```
