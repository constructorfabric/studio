---
name: analyze-phase-0-change-review-scope
description: "Invoke when CHANGE_REVIEW=true to resolve the change-review diff scope via cf-diff-scope-resolver before Phase 1 file checks."
purpose: Resolve change-review diff scope before file checks
loaded_by: workflows/analyze/phase-0-dependencies.md
version: 1.0
---

# Change Review Scope Resolver

```text
UNIT ChangeReviewScopeResolver
PURPOSE: Dispatch cf-diff-scope-resolver and derive typed target sets from the
         returned diff_scope before Phase 1 file checks.

WHEN: CHANGE_REVIEW == true
DO:
  REQUIRE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md has run
  LOAD {cf-studio-path}/.core/skills/studio/agents/cf-diff-scope-resolver.md
    as the diff-scope resolver source contract
  SYNTHESIZE final dispatch prompt from resolver contract + SHARED_CONTEXT_PACK + payload below
  IF resolver contract not loaded / unreadable / ambiguous / not reflected in dispatch prompt:
    FAIL per sub-agent-dispatch.md § SubAgentContractReadGate
    FORBID dispatch
    STOP_TURN
  DISPATCH cf-diff-scope-resolver with:
    worktree_path        = explicit repo/worktree path OR resolved workspace source
    commit_sha           = requested commit SHA OR null
    base_ref             = explicit base OR null (agent uses <commit_sha>^)
    include_uncommitted  = true for worktree/dirty/staged/unstaged changes
    direct_targets       = explicit paths named by the user
    review_intent        = original review request text
  SET diff_scope = returned JSON
  IF diff_scope.review_targets is empty:
    EMIT "No reviewable targets found."
    STOP_TURN
  SET {PATHS} = diff_scope.review_targets
  SET prompt_targets   = diff_scope.changed_files matching prompt/workflow/instruction patterns
  SET code_targets     = diff_scope.changed_files matching code/test/build patterns,
                         excluding prompt_targets
  SET artifact_targets = diff_scope.review_targets minus prompt_targets minus code_targets
  IF prompt_targets non-empty:
    SET PROMPT_REVIEW = true
    IF review_intent is change-review / defect-oriented / generic review / audit:
      SET PROMPT_BUG_REVIEW = true
  IF code_targets non-empty:
    SET CODE_REVIEW = true
  IF code_targets non-empty AND review_intent is defect-oriented:
    SET CODE_BUG_REVIEW = true
  IF artifact_targets non-empty:
    SET ARTIFACT_REVIEW = true

RULES:
  - MUST enter fail-closed mode for CHANGE_REVIEW until inline-fallback-probe state
    and resolver contract-read-and-use check are both resolved
  - While fail-closed, MUST_NOT run or narrate local git status/diff, changed-file
    triage, cfs validate, local semantic review, findings, summaries, or remediation menus
  - While fail-closed, MAY emit only the missing gate menu or matching
    "Dispatch blocked: ..." error, then MUST STOP_TURN
  - MUST dispatch cf-diff-scope-resolver immediately after inline-fallback-probe
    and before Phase 1 file checks
  - MUST apply sub-agent-dispatch.md § SubAgentContractReadGate before dispatch
  - MUST derive methodology flags from diff_scope.changed_files typed sets,
    not from raw review_targets
  - MUST_NOT silently enable CODE_REVIEW or CODE_BUG_REVIEW for prompt-only or
    artifact-only diffs
  - MUST enable ARTIFACT_REVIEW for artifact_targets not owned by prompt/code
    methodology so artifact-only diffs cannot auto-skip semantic review
  - MUST surface mismatch if user requests a code bug hunt but diff has no
    code_targets; MUST_NOT reuse prompt or artifact files as code-review inputs
  - MUST_NOT run git diff, changed-file triage, hotspot mapping, or semantic
    search over the diff — those belong to the resolver and downstream reviewers

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
