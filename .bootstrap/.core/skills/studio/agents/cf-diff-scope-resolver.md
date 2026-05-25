---
description: Invoke when an analyze/review request targets a commit, branch, worktree, patch, or uncommitted changes — resolves the Git diff scope, changed files, hunks, and review targets so the orchestrator does not perform semantic diff scanning itself.
---

<!-- toc -->

- [Inputs (dispatched-prompt contract)](#inputs-dispatched-prompt-contract)
- [Methodology (fast, structural-only)](#methodology-fast-structural-only)
- [Output (return-value contract)](#output-return-value-contract)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

```text
UNIT DiffScopeResolver

PURPOSE:
  Resolve commit, branch, worktree, patch, and dirty-change scope into a
  bounded review package for downstream validator and semantic-review agents.

STATE:
  PERFORMANCE_CONTRACT: structural-only
    scope: this_agent_run
    target: ≤ 30 seconds wall-clock

RULES:
  - MUST read SKILL.md to activate Constructor Studio mode
  - MUST_NOT read full file contents
  - MUST_NOT perform semantic analysis or score risk by inspecting code
  - MUST_NOT run git show or full git diff without --name-status/--stat
  - MUST_NOT modify files or run validators

INVARIANTS:
  - MUST stay structural throughout; semantic work belongs to downstream agents
```

Open and follow `{cf-studio-path}/.core/skills/studio/SKILL.md` to load
Constructor Studio mode in this isolated context.

```text
UNIT AllowedGitCommands

PURPOSE:
  Enumerate the bounded set of git commands this agent may run.

RULES:
  - MUST use only:
      git -C <worktree> status --short
      git -C <worktree> diff --name-status <base>..<head>        (committed)
      git -C <worktree> diff --name-status HEAD                  (uncommitted)
      git -C <worktree> rev-parse HEAD
      git -C <worktree> rev-parse <ref>^
      git -C <worktree> diff --stat <base>..<head>               (size summary)
      git -C <worktree> diff --numstat <base>..<head>            (binary omission check)
      git -C <worktree> diff --numstat HEAD                      (uncommitted binary omission check)
```

## Inputs (dispatched-prompt contract)

```json
{
  "worktree_path":       "<absolute path to the worktree root>",
  "commit_sha":          "<starting commit SHA (inclusive) or null>",
  "base_ref":            "<base ref like HEAD~1, branch name, or null>",
  "include_uncommitted": "<bool: include staged+unstaged>",
  "direct_targets":      ["<file path>", "..."],
  "review_intent":       "<short string explaining the review goal>"
}
```

## Methodology (fast, structural-only)

```text
UNIT DiffScopeResolverMethodology

PURPOSE:
  Execute structural-only scope resolution steps.

DO:
  1. Resolve worktree_path: record HEAD, branch, dirty count from
     git status --short (line count, no per-file inspection)
  2. WHEN commit_sha is present:
       Compute base = base_ref OR <commit_sha>^
       List committed changes via git diff --name-status <base>..<commit_sha>
  3. WHEN include_uncommitted == true:
       List working-tree changes via git diff --name-status HEAD
       Append untracked from git status --short ?? lines
  4. Merge into changed_files:
       {path, old_path (renames only), status, source}
  5. Hunks: FORBID extraction
       SET changed_hunks = []
       NOTES: Downstream reviewers read full files themselves
  6. Risk hotspots: FORBID semantic risk analysis
       SET risk_hotspots = []
       EXCEPTION: WHEN direct_targets are named:
         Copy them in as:
           {path, risk: "user-named direct target", evidence: "direct_targets"}
  7. Compute review_targets:
       direct_targets UNION {changed_files.path | status in {M,A,R,U,?}}
       deduped, sorted
       EXCLUDE status == D (deleted)
  8. Compute omissions:
       files filtered out from review_targets with a one-word reason:
         "deleted" — status D
         "binary"  — git diff --numstat shows -\t- markers

FORBID: hunk extraction and risk synthesis
```

NOTES:
  Hunk extraction and risk synthesis belong to the semantic reviewer agents
  that own the methodology files. This agent only answers "which files are in
  scope" and the structural manifest.

## Output (return-value contract)

Emit a compact `Diff Scope Package` summary (10 lines or fewer: HEAD, branch,
base, counts) followed by the `diff_scope` JSON:

```json
{
  "worktree_path": "<resolved path>", "head": "<sha>",
  "branch": "<branch or detached>", "base_ref": "<resolved base>",
  "commit_sha": "<sha or null>", "include_uncommitted": true,
  "changed_files": [{"path": "<path>", "old_path": null, "status": "M|A|D|R|U|?", "source": "committed|staged|unstaged|untracked"}],
  "changed_hunks": [],
  "review_targets": ["<path>", "..."],
  "risk_hotspots": [],
  "omissions": [{"path": "<path>", "reason": "deleted|binary"}]
}
```

```text
NOTES:
  changed_hunks and risk_hotspots are always emitted as empty arrays in
  this fast scope-resolution mode; downstream agents derive their own.
```

## Response Completion Gate

```text
UNIT DiffScopeResolverCompletionGate

PURPOSE:
  Enforce that every required output element is present before the response
  is complete.

RULES:
  - MUST have compact Diff Scope Package summary
  - MUST have diff_scope JSON
  - MUST classify every changed file into changed_files + review_targets
    or omissions
  - MUST_NOT have read any changed-file or user-artifact contents or
    performed risk scoring
    (SKILL.md / protocol.md / Protocol Guard loads are exempt)
  - MUST satisfy the SKILL.md invariant
```
