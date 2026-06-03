---
name: analyze-overview
description: "Invoke when loading the analyze workflow overview for modes, commands, prompt-review intent matching, and actionable-issue Remediation Handoff contract."
purpose: Analyze workflow overview — modes, commands, prompt-review matching rules, change-review routing, and the mandatory Remediation Handoff contract
loaded_by: workflows/analyze.md
version: 1.0
---

<!-- toc -->
<!-- /toc -->

```pdsl
UNIT AnalyzeOverview

PURPOSE:
  Define analyze modes, commands, prompt-review matching rules, change-review
  routing, and the mandatory Remediation Handoff contract.

STATE:
  - SET CHANGE_REVIEW: false | true
    default: false
  - SET PROMPT_REVIEW: false | true
    default: false
  - SET PROMPT_BUG_REVIEW: false | true
    default: false
  - SET SEMANTIC_ONLY: false | true
    default: false

RULES:
  - NEVER run git diff scans, hotspot mapping, or changed-file triage in the
    orchestrator during change review; those belong to cf-diff-scope-resolver
  - ALWAYS consume diff_scope from cf-diff-scope-resolver for change-review routing
  - ALWAYS derive semantic methodology routing from diff_scope.changed_files typed
    sets, not from raw review_targets
  - NEVER silently enable CODE_REVIEW or CODE_BUG_REVIEW for prompt-only or
    artifact-only diffs
  - ALWAYS match prompt-review intent from phrasing, not exact strings
  - NEVER assume a dedicated prompt-specific public route unless the current host
    explicitly exposes one
  - ALWAYS end with the Remediation Handoff menu when actionable findings exist
    AND EXPLAIN_MODE=false
  - ALWAYS emit Fix Prompt and Plan Prompt only on demand (option 2 or 3 in the
    next turn); both ALWAYS be self-contained with all findings, paths, and context
    embedded inline
  - ALWAYS trigger Remediation Handoff for code-review-style requests when any
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

  Skill invocations: cf-analyze, cf-analyze semantic,
                     cf-analyze --artifact <path>,
                     cf-analyze semantic --artifact <path>

  Change-review triggers: "review commit <sha>", "review this diff",
    "review my changes", "review branch <name>", "review the <worktree> worktree",
    or any request combining a Git object/worktree with review intent.
    Set CHANGE_REVIEW=true when any change-review trigger is matched.
    Phase 0 dispatches cf-diff-scope-resolver before deterministic or semantic
    review in change-review mode; the orchestrator may resolve the named
    repository/worktree path but all git analysis belongs to the resolver.

  Prompt-review trigger matching is intent-based (not exact-string):
    "prompt engineering review", "review this prompt for bugs",
    "check prompt quality", "analyze agent instructions" and equivalents.
    Set PROMPT_BUG_REVIEW=true when defect-oriented.

  After {cf-studio-path}/.core/skills/studio/protocol.md: TARGET_TYPE, RULES,
    KIND, PATH, and resolved dependencies are available.
```
