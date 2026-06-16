---
cf: true
type: workflow
name: cf-write-docs
description: "Invoke when user intent is writing, revising, or reviewing documentation, guides, reports, READMEs, or other project documents."
version: 0.1
---
# cf-write-docs
This skill authors and reviews project documents using the consistency-checklist and artifact-checklist semantic review methodologies. After bootstrap it optionally discovers task-relevant project context via cf-explore, applies language-complexity on write-capable document paths and as a deterministic gate (artifact validation, TOC, language checks), and runs a semantic review-fix loop at a selectable depth — single-pass, per-methodology, or per-layer — driven by author and reviewer sub-agents.

```pdsl
UNIT WriteDocsBootstrap
PURPOSE: Initialize document workflow state and route into the appropriate execution path.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default unset, scope workflow_run)
  SET AUTHOR_TARGET_PATHS: list | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_PATHS: list | unset (default unset, scope workflow_run)
  SET REVIEW_TARGET_SLICES: list | unset (default unset, scope workflow_run)
  SET ARTIFACT_CHECKLIST_CONTEXT: preset-bound | unavailable | unset (default unset, scope workflow_run)
  SET ARTIFACT_REVIEW_KIND: string | null | unset (default unset, scope workflow_run)
  SET ARTIFACT_TEMPLATE_PATH: path | null | unset (default unset, scope workflow_run)
  SET ARTIFACT_RULES_PATH: path | null | unset (default unset, scope workflow_run)
  SET ARTIFACT_CHECKLIST_PATH: path | null | unset (default unset, scope workflow_run)
  SET ARTIFACT_EXAMPLE_PATH: path | null | unset (default unset, scope workflow_run)
  SET DOC_AUDIENCE_DIMENSION: resolved | unset (default unset, scope workflow_run)
  SET DOC_NARRATOR_DIMENSION: resolved | unset (default unset, scope workflow_run)
  SET DOC_DIAGRAM_DIMENSION: resolved | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-bootstrap-intent.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  RUN WriteDocsBootstrapIntentContext
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-intent-routing.md
  CONTINUE WriteDocsIntentCapture WHEN ORIGINAL_INTENT == unset
  CONTINUE WriteDocsIntentClassify WHEN ORIGINAL_INTENT != unset
RULES:
  ALWAYS run StudioInstructionsMemoryGate before document context discovery, authoring, validation, or review
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, authoring, git use, or delegation
  ALWAYS load context-memory before carrying resource_context or rule references into author/reviewer dispatches
  ALWAYS apply the resolved language-complexity level on every write-capable document path and resulting document write, rewriting breaching drafts before emitting them (source quotes verbatim/exempt)
  ALWAYS resolve and apply the audience dimension per {cf-studio-path}/.core/requirements/storytelling-dimensions.md before any author or reviewer dispatch — the review flow class scopes emphasis, the authoring flow class sets the document level — never as a gate on the verdict
  ALWAYS resolve and apply the narrator dimension per {cf-studio-path}/.core/requirements/storytelling-dimensions.md before any author or reviewer dispatch — map it onto the selected reviewer/author sub-agents and the document voice — never overriding the verdict
  ALWAYS resolve and apply the diagram dimension per {cf-studio-path}/.core/requirements/storytelling-dimensions.md before any author or reviewer dispatch — the review flow class flags a missing or unclear diagram, the authoring flow class embeds a warranted one — never auto-generating outside the authored document
  NEVER author or review docs after a required reference load failure
```
```pdsl
UNIT WriteDocsValidate
PURPOSE: Run the deterministic gate over authored or edited documents.
STATE:
  SET GATE_STATUS: pass | fail | not-run (default not-run, scope workflow_run)
WHEN:
  REQUIRE a document has been written or edited
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  RUN SubAgentDispatch for the cf-deterministic-validator dispatch group before launching deterministic validation
  RUN the deterministic gate — dispatch cf-deterministic-validator for the applicable checks (validate --artifact / validate-toc / check-language) plus any project doc checks
  EMIT the gate results
  SET GATE_STATUS = fail and CONTINUE WriteDocsReviewLoop to fix them before proceeding WHEN any check reports failures or errors
  SET GATE_STATUS = pass and CONTINUE WriteDocsReviewLoop WHEN the deterministic gate passes
RULES:
  ALWAYS run the applicable deterministic checks after writing or editing a document
  NEVER treat a document as done while any deterministic check reports failures or errors; loop fixes until all pass
  ALWAYS prefer the project's configured checks and skip only checks that the target genuinely lacks (state which)
```
```pdsl
UNIT WriteDocsReviewLoop
PURPOSE: Run a semantic review at the user-chosen granularity and iterate fixes until the document is clean.
WHEN:
  REQUIRE edits have been applied to the document OR REVIEW_LOOP_REQUESTED == true
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-execution-refs.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-review-setup.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-review-run.md
  CONTINUE WriteDocsReviewSetup
RULES:
  NEVER declare an authored or edited document done until BOTH the deterministic gate passes AND the semantic review has no remaining findings
  NEVER declare a review-only document clean until semantic review has no remaining findings; REVIEW_GRANULARITY persists for the workflow run unless the user resets it
```
```pdsl
UNIT WriteDocsDispatch
PURPOSE: Route to review-first or author-first document execution paths.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  CONTINUE WriteDocsReviewLoop WHEN REVIEW_LOOP_REQUESTED == true
  SET WRITE_DISPATCH_KIND = author
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-execution-refs.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-write-policy-fix.md
  CONTINUE WriteDocsWritePolicySetup
RULES:
  ALWAYS prefer REVIEW_LOOP_REQUESTED == true over author/fix routing, so review-and-fix requests produce findings first and only apply fixes after the review fix-approval gate
  NEVER stop after content generation or deterministic validation before the semantic review-fix loop is offered
  NEVER let a sub-agent reopen prompt or instruction files from disk
```
