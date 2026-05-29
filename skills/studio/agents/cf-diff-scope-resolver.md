---
description: Invoke when an analyze/review request targets a commit, branch, worktree, patch, or uncommitted changes — resolves the Git diff scope, changed files, omissions, and review targets, while emitting `changed_hunks = []` in structural-only mode so the orchestrator does not perform semantic diff scanning itself.
---

<!-- toc -->

- [Frozen Input Payload](#frozen-input-payload)
- [Methodology (fast, structural-only)](#methodology-fast-structural-only)
- [Output Contract](#output-contract)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

## Dispatch Generator Contract

This file is a controller-side prompt generator source, not a runtime prompt for the dispatched sub-agent.

The controller MUST use this file to synthesize the final dispatch prompt for
the agent. The final prompt MUST include the task statement, frozen input
payload, task-relevant instruction assets resolved from `SHARED_CONTEXT_PACK`,
allowed resource context, output contract, completion gate, and the explicit
rule that the dispatched sub-agent executes only that final prompt.

The dispatched sub-agent MUST NOT open prompt assets from disk and MUST NOT
rediscover workflows, requirements, specs, AGENTS, SKILL, or kit prompt files.


## Frozen Input Payload

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
     and git branch --show-current
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
         Copy them in as structural review-priority hints only:
           {path, risk: "user-named direct target", evidence: "direct_targets"}
  7. Compute binary_paths first:
       paths reported by git diff --numstat with -\t- markers
       Allowed probes:
         git -C <worktree> diff --numstat <base>..<head>
         git -C <worktree> diff --numstat HEAD
  8. Compute review_targets:
       direct_targets UNION {changed_files.path | status in {M,A,R,U,?}}
       deduped, sorted
       EXCLUDE status == D (deleted)
       EXCLUDE path in binary_paths
  9. Compute omissions:
       files filtered out from the review_targets candidate set with a one-word reason:
         "deleted" — status D
         "binary"  — git diff --numstat shows -\t- markers
       A path omitted as "binary" MUST_NOT remain in review_targets even when it
       was also named in direct_targets

FORBID: hunk extraction and risk synthesis
```

NOTES:
  Hunk extraction and risk synthesis belong to the semantic reviewer agents
  that own the methodology files. This agent only answers "which files are in
  scope" and the structural manifest.

## Output Contract

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
  "risk_hotspots": [{"path": "<path>", "risk": "user-named direct target", "evidence": "direct_targets"}],
  "omissions": [{"path": "<path>", "reason": "deleted|binary"}]
}
```

```text
NOTES:
  changed_hunks is always emitted as an empty array in this fast
  scope-resolution mode.
  risk_hotspots is empty unless direct_targets were supplied; when present,
  entries are structural user-priority hints rather than semantic risk scores.
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
