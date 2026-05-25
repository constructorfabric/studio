---
name: analyze-phase-0-change-review-scope
description: "Invoke when CHANGE_REVIEW=true to resolve the change-review diff scope via cf-diff-scope-resolver before Phase 1 file checks."
purpose: Resolve change-review diff scope before file checks
loaded_by: workflows/analyze/phase-0-dependencies.md
version: 1.0
---

When `CHANGE_REVIEW=true`, dispatch sub-agent
`cf-diff-scope-resolver` immediately after the inline-fallback-probe
(`workflows/shared/inline-fallback-probe.md`) and before Phase 1 file checks.

Supply:
- `worktree_path` = explicit repo/worktree path, or resolved workspace source
- `commit_sha` = requested commit SHA, or `null`
- `base_ref` = explicit base, or `null` (agent uses `<commit_sha>^`)
- `include_uncommitted` = `true` for worktree/dirty/staged/unstaged changes
- `direct_targets` = explicit paths named by the user
- `review_intent` = original review request text

Store returned JSON as `diff_scope`. `diff_scope` schema (fields consumed
downstream): `review_targets: string[]`, `base_ref: string|null`,
`head_ref: string|null`, `commits: object[]`, `changed_files: object[]`.
Downstream consumers may use `diff_scope.review_targets` for the full diff
surface, but semantic methodology routing MUST derive typed target sets from
`diff_scope.changed_files`, not from raw `review_targets`.

Set `{PATHS} = diff_scope.review_targets` for downstream file checks and
change-review bookkeeping. If empty, stop and report no reviewable targets.

After `diff_scope` is stored, from `diff_scope.changed_files`, derive prompt_targets, code_targets, and artifact_targets based on each file's classification (described below):

- `prompt_targets` from `diff_scope.changed_files[].path` matching
  `workflows/**`, `skills/studio/**/*.md`, `requirements/**/*.md`,
  `skills/**/SKILL.md`, `skills/**/agents/*.md`, `AGENTS.md`, `SKILL.md`,
  `.github/prompts/**`, `.cursor/agents/**`, `.codex/agents/**`, or prompt
  config files.
- `code_targets` from `diff_scope.changed_files[].path` matching code/test/build
  surfaces owned by the code reviewer methodology (`*.py`, `*.ts`, `*.tsx`,
  `*.js`, `*.jsx`, `*.go`, `*.rs`, `*.java`, `*.kt`, `*.rb`, `*.php`,
  `*.sh`, `Dockerfile`, `Makefile`, `pyproject.toml`, `package.json`,
  `Cargo.toml`, `go.mod`, `go.sum`, and equivalent source-local build files),
  excluding any path already classified into prompt_targets.
- `artifact_targets` = `diff_scope.review_targets` minus `prompt_targets` minus
  `code_targets`.

Methodology flags for change review are then derived from those typed sets:

- if `prompt_targets` is non-empty, set `PROMPT_REVIEW=true`
- if `prompt_targets` is non-empty and `review_intent` is change-review,
  defect-oriented, or generic review/audit wording, set
  `PROMPT_BUG_REVIEW=true`
- set `CODE_REVIEW=true` only when `code_targets` is non-empty
- set `CODE_BUG_REVIEW=true` only when `code_targets` is non-empty and
  `review_intent` is defect-oriented (`bug`, `defect`, `regression`,
  `root cause`, `crash`, `broken`, `hunt`)

Prompt-only or artifact-only diffs MUST NOT silently enable `CODE_REVIEW` or
`CODE_BUG_REVIEW`. If the user explicitly asks for a code bug hunt but the diff
contains no `code_targets`, surface that mismatch during scope clarification;
do not reuse prompt or artifact files as code-review inputs.

The orchestrator MUST NOT run `git diff`, changed-file triage, hotspot mapping,
or semantic search over the diff itself; those operations belong to the
resolver and downstream semantic reviewer agents.
