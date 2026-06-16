---
cf: true
type: workflow
name: cf-coding
description: "Invoke when user intent is writing, implementing, refactoring, fixing, or reviewing source code."
version: 0.1
---

# cf-coding

This skill authors and reviews source code using the code-checklist, bug-finding, and consistency-checklist methodologies. After bootstrap it optionally discovers task-relevant project context via cf-explore, loads code review methodologies only on review-capable paths, runs a deterministic gate (tests, lint, typecheck, build), and runs a semantic review-fix loop at a selectable depth — single-pass, per-methodology, or per-layer — driven by coding and reviewer sub-agents.

```pdsl
UNIT CodingBootstrap
PURPOSE: Load the methodologies needed to author and review source code.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  SET ORIGINAL_INTENT = the user's triggering coding request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-intent-companion.md
  CONTINUE CodingIntentCapture WHEN ORIGINAL_INTENT == unset
  CONTINUE CodingIntentClassify WHEN ORIGINAL_INTENT != unset
RULES:
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, authoring, git use, or delegation
  NEVER author or review code after a required reference load failure
```

```pdsl
UNIT CodingValidate
PURPOSE: Run the project's deterministic gate over authored or edited code.
STATE:
  SET GATE_STATUS: pass | fail (default unset, scope workflow_run)
WHEN:
  REQUIRE code has been written or edited
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-bootstrap-methodologies.md
  RUN CodingValidationContextPrep
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  RUN SubAgentDispatch for the cf-deterministic-validator dispatch group before launching studio-applicable deterministic validation
  RUN the project's deterministic gate — resolve the test, lint, typecheck, and build commands from the project's config (package.json / Makefile / pyproject.toml / build files) or the remembered {cfs_cmd}/project commands, run them in order, and dispatch cf-deterministic-validator for studio-applicable checks (validate / validate-toc / check-language)
  EMIT the gate results
  SET GATE_STATUS = fail and CONTINUE CodingReviewLoop to fix them before proceeding WHEN any gate reports failures or errors
  SET GATE_STATUS = pass and CONTINUE CodingReviewLoop WHEN the deterministic gate passes
RULES:
  NEVER treat code as done while any deterministic gate (tests/lint/typecheck/build) reports failures or errors; loop fixes until all pass
  ALWAYS prefer the project's configured commands and skip only gates that the project genuinely lacks (state which)
```

```pdsl
UNIT CodingReviewLoop
PURPOSE: Run a semantic review at the user-chosen granularity and iterate fixes until the code is clean.
WHEN:
  REQUIRE edits have been applied to the code OR REVIEW_LOOP_REQUESTED == true
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-bootstrap-methodologies.md
  RUN CodingExecutionContextPrep
  RUN CodingReviewReferenceLoad
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-review-setup-run.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-review-fix.md
  CONTINUE CodingReviewSetup
RULES:
  NEVER declare authored or edited code done until BOTH the deterministic gate (tests/lint/typecheck/build) passes AND the semantic review has no remaining findings
```

```pdsl
UNIT CodingCompletion
PURPOSE: Emit a concise completion report, then offer context-grounded next actions after code authoring/review completes cleanly.
WHEN:
  REQUIRE no review findings remain
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT a concise completion report covering work done, deterministic gate outcome (or "not run" when GATE_STATUS is unset), and semantic review outcome
  RUN NextActionsOffer
RULES:
  ALWAYS use this unit only after code validation/review is complete
  NEVER bypass NextActionsOffer on a clean terminal path
```

```pdsl
UNIT CodingDispatch
PURPOSE: Route to review-first or author-first code execution paths.
DO:
  CONTINUE CodingReviewLoop WHEN REVIEW_LOOP_REQUESTED == true
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-bootstrap-methodologies.md
  RUN CodingExecutionContextPrep
  LOAD {cf-studio-path}/.core/skills/studio/modules/coding-author-dispatch.md
  CONTINUE CodingAuthorGitSetup
RULES:
  ALWAYS prefer REVIEW_LOOP_REQUESTED == true over coder routing, so review-and-fix requests produce findings first and only apply fixes after the review fix-approval gate
  NEVER stop after code generation or deterministic validation before the semantic review-fix loop is offered
  NEVER let a sub-agent reopen prompt or instruction files from disk
```
