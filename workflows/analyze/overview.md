---
name: analyze-overview
description: "Invoke when loading the analyze workflow overview for modes, commands, prompt-review intent matching, and actionable-issue Remediation Handoff contract."
purpose: Analyze workflow overview — modes, commands, prompt-review intent matching, actionable-issue Remediation Handoff contract
loaded_by: workflows/analyze.md
version: 1.0
---

<!-- toc -->

- [Overview](#overview)

<!-- /toc -->

```text
UNIT AnalyzeOverview

PURPOSE:
  Define analyze modes, commands, prompt-review matching rules, change-review
  routing, and the mandatory Remediation Handoff contract.

STATE:
  CHANGE_REVIEW: false | true
    default: false
  PROMPT_REVIEW: false | true
    default: false
  PROMPT_BUG_REVIEW: false | true
    default: false
  SEMANTIC_ONLY: false | true
    default: false

RULES:
  - MUST_NOT run git diff scans, hotspot mapping, or changed-file triage in the
    orchestrator during change review; those belong to cf-diff-scope-resolver
  - MUST consume diff_scope from cf-diff-scope-resolver for change-review routing
  - MUST derive semantic methodology routing from diff_scope.changed_files typed
    sets, not from raw review_targets
  - MUST_NOT silently enable CODE_REVIEW or CODE_BUG_REVIEW for prompt-only or
    artifact-only diffs
  - MUST match prompt-review intent from phrasing, not exact strings
  - MUST end with the Remediation Handoff menu when actionable findings exist
    AND EXPLAIN_MODE=false
  - MUST emit Fix Prompt and Plan Prompt only on demand (option 2 or 3 in the
    next turn); both MUST be self-contained with all findings, paths, and context
    embedded inline
  - MUST trigger Remediation Handoff for code-review-style requests when any
    reported defect, regression risk, or fix recommendation requires changes

NOTES:
  Modes:
    Full (default) = deterministic gate -> semantic review
    Semantic-only  = skip deterministic gate
    Artifact       = template + checklist
    Code           = dispatch code-checklist reviewer and, when defect/change-oriented,
                     a separate code bug-finder against design requirements
    Prompt review  = dispatch prompt-engineering reviewer and, when defect-oriented,
                     a separate prompt-bug-finder for instruction documents

  Commands: /cf-analyze, /cf-analyze semantic,
            /cf-analyze --artifact <path>,
            /cf-analyze semantic --artifact <path>

  Change-review triggers: "review commit <sha>", "review this diff",
    "review my changes", "review branch <name>", "review the <worktree> worktree",
    or any request combining a Git object/worktree with review intent.

  Prompt-review trigger matching is intent-based (not exact-string):
    "prompt engineering review", "review this prompt for bugs",
    "check prompt quality", "analyze agent instructions" and equivalents.
    Set PROMPT_BUG_REVIEW=true when defect-oriented.
```

## Overview
Modes: Full (default) = deterministic gate -> semantic review; Semantic-only = skip deterministic gate; Artifact = template + checklist; Code = dispatch code-checklist reviewer and, when defect/change-oriented, a separate code bug-finder against design requirements; Prompt review = dispatch prompt-engineering reviewer and, when defect-oriented, a separate prompt-bug-finder for instruction documents.
Commands: `/cf-analyze`, `/cf-analyze semantic`, `/cf-analyze --artifact <path>`, `/cf-analyze semantic --artifact <path>`.
Change review mode: requests like `review commit <sha>`, `review this diff`, `review my changes`, `review branch <name>`, `review the <worktree> worktree`, or any request combining a Git object/worktree with review intent set `CHANGE_REVIEW=true`. In change review mode, Phase 0 dispatches `cf-diff-scope-resolver` before deterministic or semantic review. The orchestrator may resolve the named repository/worktree path, but MUST NOT run semantic `git diff` scans, hotspot mapping, or changed-file triage itself; it consumes the resolver's `diff_scope` package. Semantic methodology routing in change review is typed from `diff_scope.changed_files`: prompt/workflow-only diffs enable prompt reviewers only, code reviewers receive only typed `code_targets`, and prompt-only diffs MUST NOT silently enable code review or code bug-finding.
Prompt review trigger matching is intent-based, not exact-string based. Match intent (for example `prompt engineering review`, `review this prompt for bugs`, `check prompt quality`, or `analyze agent instructions`), and treat equivalent phrasing as setting `PROMPT_REVIEW=true`; additionally set `PROMPT_BUG_REVIEW=true` when defect-oriented review is requested. Select prompt review from the request intent and target context; do **not** assume a dedicated prompt-specific public route unless the current host explicitly exposes one. After `{cf-studio-path}/.core/skills/studio/protocol.md`, you have `TARGET_TYPE`, `RULES`, `KIND`, `PATH`, and resolved dependencies.
If analysis finds actionable issues, the workflow MUST end with the `Remediation Handoff` menu offering three paths: (1) continue in this session with `/cf-generate` in fix mode (suggested when scope is bounded), (2) generate a self-contained `Fix Prompt` for a fresh chat via `/cf-generate`, (3) generate a self-contained `Plan Prompt` for a fresh chat via `/cf-plan`. The two prompt blocks (Fix / Plan) are emitted on demand only when the user picks option 2 or 3 in the next turn; both, when emitted, MUST be self-contained — all findings, paths, and context embedded inline.
For code-review-style requests such as `review my changes`, `review this diff`, `inspect this patch`, or similar review/audit requests, every reported defect, regression risk, or fix recommendation that requires artifact, code, or workflow/instruction changes counts as an actionable issue and therefore MUST trigger the `Remediation Handoff` menu in the same response. `Fix Prompt` and `Plan Prompt` blocks remain on-demand emissions for the next turn when the user chooses option 2 or 3.
