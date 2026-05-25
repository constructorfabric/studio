---
name: analyze-phase-0-dependencies
description: "Invoke when running Analyze Phase 0 / 0.5 for mode detection, dependency setup, and scope capture."
purpose: Analyze Phase 0 / 0.5 dispatcher — mode detection, dependency setup, scope capture
loaded_by: workflows/analyze.md
version: 1.0
---

<!-- toc -->

- [Mode Detection](#mode-detection)
  - [Post-Probe Resume Checkpoint](#post-probe-resume-checkpoint)

<!-- /toc -->



## Mode Detection

<!-- Per-run analyze flags are initialized in `preamble.md`; this file only matches conditions to set flags to true. `ARTIFACT_REVIEW=false` is the default before artifact target detection. -->

- Semantic command → `SEMANTIC_ONLY=true`; skip Phase 2 and go to Phase 3.
- Prompt/instruction review context → `PROMPT_REVIEW=true`; defect-oriented
  prompt/instruction review also sets `PROMPT_BUG_REVIEW=true`.
- Prompt-bug-only requests MAY set `PROMPT_BUG_REVIEW=true` without
  `PROMPT_REVIEW=true`.
- Explain/storytelling context → `EXPLAIN_MODE=true`; storytelling handoff and
  routing invariants are owned by `workflows/analyze/preamble.md` and
  `{cf-studio-path}/.core/requirements/storytelling.md`.
- Review of a commit, branch, patch, diff, or worktree → `CHANGE_REVIEW=true`.
- Artifact target review -> `ARTIFACT_REVIEW=true` when the resolved target is
  an artifact and no prompt/code-specific methodology has taken ownership.

Do NOT open code methodology files in the orchestrator. Do NOT open prompt methodology files in the orchestrator. Phase 3 dispatches one sub-agent per selected methodology.

Variable checkpoint: `{cfs_cmd}`, `{cf-studio-path}`, and `{project_root}`
come from `skills/studio/protocol.md`; re-run info after context loss.

Requires: `workflows/shared/inline-fallback-probe.md` before any
`cf-*` sub-agent dispatch.

Open, load, and follow `workflows/shared/inline-fallback-probe.md` now.

### Post-Probe Resume Checkpoint

If the probe emitted the session-approval menu and ended the turn, on the next
turn the orchestrator MUST re-enter Phase 0 at the post-probe continuation point
(the plan-escalation gate load below), NOT from the top of
`phase-0-dependencies.md`. The probe's reply (`1` or `2`) sets
`SUB_AGENT_SESSION_APPROVED` and `INLINE_FALLBACK` for the rest of the workflow
run.

Open, load, and follow `workflows/analyze/phase-0-change-review-scope.md` WHEN
`CHANGE_REVIEW=true`; this dispatches `cf-diff-scope-resolver`.
The orchestrator MUST NOT run `git diff`.

Open, load, and follow `{cf-studio-path}/.core/requirements/raw-input-overflow.md`.

Artifact review dependencies: if `ARTIFACT_REVIEW=true` and `rules.md` is
loaded, dependencies are resolved. If artifact review dependencies are missing,
ask for the missing checklist/template/example only when `ARTIFACT_REVIEW=true`.
Code and prompt methodologies do not require artifact checklist/template/example
to proceed; they use their own reviewer methodology files in Phase 3.
Outside change review, code mode sets `CODE_REVIEW=true` when the resolved
target is code. Outside change review, additionally set `CODE_BUG_REVIEW=true`
when the user request contains any of the words: `bug`, `defect`,
`regression`, `root cause`, `crash`, `broken`, `hunt`.

When `CHANGE_REVIEW=true`, Phase 0 change-review scope owns typed target-set
derivation from `diff_scope.changed_files`. Do NOT pre-enable `CODE_REVIEW` or
`CODE_BUG_REVIEW` for a diff-scoped run before `code_targets` is derived.

MUST NOT proceed to Phase 1 until all dependencies are available.

Open, load, and follow `workflows/analyze/phase-0.1-plan-escalation-gate.md` NEXT
(MUST — gate is mandatory; the `> 2000` line threshold offer is required before
any further Phase-0 / Phase-1 work).

After the plan-escalation gate resolves, open, load, and follow
`workflows/analyze/phase-0.5-scope.md` WHEN target_paths contains more than one entry AND no explicit scope was named in the user request, OR when CONSISTENCY_REVIEW=true and fewer than two paths are captured, OR when ARTIFACT_REVIEW=true and the artifact is not registered in artifacts.toml.

After scope resolves (or scope-load is skipped), proceed to Phase 1: open, load, and follow `workflows/analyze/phase-1-file-check.md`.
