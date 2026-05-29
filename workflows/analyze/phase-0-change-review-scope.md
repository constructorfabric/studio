---
name: analyze-phase-0-change-review-scope
description: "Invoke when CHANGE_REVIEW=true to resolve the change-review diff scope via cf-diff-scope-resolver before Phase 1 file checks."
purpose: Resolve change-review diff scope before file checks
loaded_by: workflows/analyze/phase-0-dependencies.md
version: 1.0
---

```text
UNIT ChangeReviewScopeResolver

PURPOSE:
  Dispatch cf-diff-scope-resolver and derive typed target sets from the
  returned diff_scope before Phase 1 file checks.

WHEN:
  CHANGE_REVIEW == true

DO:
  REQUIRE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md has run
  DISPATCH cf-diff-scope-resolver with:
    worktree_path   = explicit repo/worktree path OR resolved workspace source
    commit_sha      = requested commit SHA OR null
    base_ref        = explicit base OR null (agent uses <commit_sha>^)
    include_uncommitted = true for worktree/dirty/staged/unstaged changes
    direct_targets  = explicit paths named by the user
    review_intent   = original review request text
  SET diff_scope = returned JSON
  IF diff_scope.review_targets is empty:
    EMIT "No reviewable targets found."
    STOP_TURN
  SET {PATHS} = diff_scope.review_targets
  Derive typed target sets from diff_scope.changed_files:
    SET prompt_targets  = paths matching prompt/workflow/instruction patterns
    SET code_targets    = paths matching code/test/build patterns, excluding prompt_targets
    SET artifact_targets = diff_scope.review_targets minus prompt_targets minus code_targets
  IF prompt_targets is non-empty:
    SET PROMPT_REVIEW = true
    IF review_intent is change-review, defect-oriented, or generic review/audit:
      SET PROMPT_BUG_REVIEW = true
  IF code_targets is non-empty:
    SET CODE_REVIEW = true
  IF code_targets is non-empty AND review_intent is defect-oriented:
    SET CODE_BUG_REVIEW = true

RULES:
  - MUST dispatch cf-diff-scope-resolver immediately after inline-fallback-probe
    and before Phase 1 file checks
  - MUST derive methodology flags from diff_scope.changed_files typed sets, not
    from raw review_targets
  - MUST_NOT silently enable CODE_REVIEW or CODE_BUG_REVIEW for prompt-only or
    artifact-only diffs
  - MUST surface mismatch if user requests a code bug hunt but diff contains no
    code_targets; do not reuse prompt or artifact files as code-review inputs
  - MUST_NOT run git diff, changed-file triage, hotspot mapping, or semantic
    search over the diff; those belong to the resolver and downstream reviewers

NOTES:
  prompt_targets match: workflows/**, skills/studio/**/*.md,
    requirements/**/*.md, skills/**/SKILL.md, skills/**/agents/*.md,
    AGENTS.md, SKILL.md, .github/prompts/**, .cursor/agents/**,
    .codex/agents/**, and prompt config files.
  code_targets match: *.py, *.ts, *.tsx, *.js, *.jsx, *.go, *.rs, *.java,
    *.kt, *.rb, *.php, *.sh, Dockerfile, Makefile, pyproject.toml,
    package.json, Cargo.toml, go.mod, go.sum, and equivalent source-local
    build files — excluding any path already in prompt_targets.
  diff_scope schema fields consumed downstream: review_targets, base_ref,
    head_ref, commits, changed_files.
```
