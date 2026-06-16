---
cf: true
type: workflow
name: cf-write-docs
description: "Invoke when user intent is writing, revising, or reviewing documentation, guides, reports, READMEs, or other project documents."
version: 0.1
---

# cf-write-docs

This skill authors and reviews project documents using the consistency-checklist and artifact-checklist semantic review methodologies. After bootstrap it optionally discovers task-relevant project context via cf-explore, applies language-complexity as bootstrap/output policy and as a deterministic gate (artifact validation, TOC, language checks), and runs a semantic review-fix loop at a selectable depth — single-pass, per-methodology, or per-layer — driven by author and reviewer sub-agents.

```pdsl
UNIT WriteDocsBootstrap
PURPOSE: Load the methodologies needed to author and review project documents.
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
  RUN WorkflowBootstrapCoreSession
  RUN WriteDocsBootstrapIntentContext
  RUN WriteDocsBootstrapReferenceLoad
  RUN WriteDocsBootstrapDimensions
  CONTINUE WriteDocsIntentCapture WHEN ORIGINAL_INTENT == unset
  CONTINUE WriteDocsIntentClassify WHEN ORIGINAL_INTENT != unset
RULES:
  ALWAYS run StudioInstructionsMemoryGate before document context discovery, authoring, validation, or review
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, authoring, git use, or delegation
  ALWAYS load context-memory before carrying resource_context or rule references into author/reviewer dispatches
  ALWAYS apply the resolved language-complexity level to every chat message and document write, rewriting breaching drafts before emitting them (source quotes verbatim/exempt)
  ALWAYS resolve and apply the audience dimension per {cf-studio-path}/.core/requirements/storytelling-dimensions.md at Bootstrap — the review flow class scopes emphasis, the authoring flow class sets the document level — never as a gate on the verdict
  ALWAYS resolve and apply the narrator dimension per {cf-studio-path}/.core/requirements/storytelling-dimensions.md at Bootstrap — map it onto the selected reviewer/author sub-agents and the document voice — never overriding the verdict
  ALWAYS resolve and apply the diagram dimension per {cf-studio-path}/.core/requirements/storytelling-dimensions.md at Bootstrap — the review flow class flags a missing or unclear diagram, the authoring flow class embeds a warranted one — never auto-generating outside the authored document
  NEVER author or review docs after a required reference load failure
```

```pdsl
UNIT WriteDocsBootstrapIntentContext
PURPOSE: Resolve the initial doc-writing intent and load context-memory for downstream document work.
DO:
  SET ORIGINAL_INTENT = the user's triggering write-docs request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  RUN WorkflowBootstrapContextOnly
```

```pdsl
UNIT WriteDocsBootstrapReferenceLoad
PURPOSE: Load and verify the shared documentation references used by cf-write-docs.
DO:
  LOAD {cf-studio-path}/.core/requirements/consistency-checklist.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/language-complexity.md
  RUN LanguageComplexityLoad
  LOAD {cf-studio-path}/.core/requirements/storytelling-dimensions.md
  LOAD {cf-studio-path}/.core/skills/studio/agents/cf-semantic-reviewer-artifact.md
  RUN verify the references loaded; EMIT "Required reference not found (consistency-checklist, language-complexity, storytelling-dimensions, or cf-semantic-reviewer-artifact under {cf-studio-path}/.core) — cannot author or review docs; reinstall or sync the studio kit, then retry." and STOP_TURN WHEN any load fails
```

```pdsl
UNIT WriteDocsBootstrapDimensions
PURPOSE: Normalize artifact context and resolve the storytelling dimensions applied to document authoring and review.
DO:
  RUN WriteDocsArtifactContextNormalize
  RUN AudienceResolution, NarratorResolution, and DiagramResolution for the cf-write-docs flow class; SET DOC_AUDIENCE_DIMENSION = resolved, SET DOC_NARRATOR_DIMENSION = resolved, and SET DOC_DIAGRAM_DIMENSION = resolved before any author or reviewer dispatch
```

```pdsl
UNIT WriteDocsArtifactContextNormalize
PURPOSE: Normalize preset-bound artifact references into the payload field names required by author and artifact-reviewer contracts.
DO:
  RUN WriteDocsNormalizeArtifactKind
  RUN WriteDocsNormalizeArtifactTemplateAndRules
  RUN WriteDocsNormalizeArtifactChecklist
  RUN WriteDocsNormalizeArtifactExample
RULES:
  ALWAYS keep preset-bound artifact references as read-only payload fields
  NEVER invent artifact template, rules, checklist, or example paths when no preset supplied them
```

```pdsl
UNIT WriteDocsNormalizeArtifactKind
PURPOSE: Normalize the artifact kind into the review payload field.
DO:
  SET ARTIFACT_REVIEW_KIND = ARTIFACT_KIND WHEN ARTIFACT_KIND is set
  SET ARTIFACT_REVIEW_KIND = null WHEN ARTIFACT_REVIEW_KIND == unset
```

```pdsl
UNIT WriteDocsNormalizeArtifactTemplateAndRules
PURPOSE: Normalize preset-bound template and rules references.
DO:
  SET ARTIFACT_TEMPLATE_PATH = artifact_template WHEN artifact_template is set
  SET ARTIFACT_TEMPLATE_PATH = null WHEN ARTIFACT_TEMPLATE_PATH == unset
  SET ARTIFACT_RULES_PATH = artifact_rules WHEN artifact_rules is set
  SET ARTIFACT_RULES_PATH = null WHEN ARTIFACT_RULES_PATH == unset
```

```pdsl
UNIT WriteDocsNormalizeArtifactChecklist
PURPOSE: Normalize checklist references and whether checklist context is available.
DO:
  SET ARTIFACT_CHECKLIST_PATH = artifact_checklist WHEN artifact_checklist is set
  SET ARTIFACT_CHECKLIST_PATH = checklist_path WHEN ARTIFACT_CHECKLIST_PATH == unset AND checklist_path is set
  SET ARTIFACT_CHECKLIST_PATH = null WHEN ARTIFACT_CHECKLIST_PATH == unset
  SET ARTIFACT_CHECKLIST_CONTEXT = preset-bound WHEN ARTIFACT_CHECKLIST_PATH != null
  SET ARTIFACT_CHECKLIST_CONTEXT = unavailable WHEN ARTIFACT_CHECKLIST_PATH == null
```

```pdsl
UNIT WriteDocsNormalizeArtifactExample
PURPOSE: Normalize the preset-bound example reference.
DO:
  SET ARTIFACT_EXAMPLE_PATH = artifact_example WHEN artifact_example is set
  SET ARTIFACT_EXAMPLE_PATH = null WHEN ARTIFACT_EXAMPLE_PATH == unset
```

```pdsl
UNIT WriteDocsIntentCapture
PURPOSE: Capture the documentation target before any context discovery or framing gate runs.
DO:
  EMIT "Describe the documentation work you want done: the document, audience, goal, and any source material you already know. I need that target before cf-explore or brainstorm can search usefully."
  RUN register WriteDocsIntentResume as the resume continuation for the next user.reply
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER offer cf-explore, cf-brainstorm, or dispatch author/reviewer agents while ORIGINAL_INTENT == unset
```

```pdsl
UNIT WriteDocsIntentResume
PURPOSE: Resume the workflow after the user provides the documentation target.
WHEN:
  REQUIRE user.reply exists
DO:
  SET ORIGINAL_INTENT = user.reply
  CONTINUE WriteDocsIntentClassify
```

```pdsl
UNIT WriteDocsIntentClassify
PURPOSE: Classify ORIGINAL_INTENT to set review-first routing, then hand off to companion routing.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  RUN classify ORIGINAL_INTENT by requested operation plus whether it evaluates an existing document, guide, report, README, or documentation artifact; SET REVIEW_LOOP_REQUESTED = true WHEN ORIGINAL_INTENT asks to review, audit, critique, inspect, check, validate, verify, analyze, compare behavior, or find issues/findings, bugs, risks, failures, regressions, bypasses, defects, root causes, routing problems, or behavioral-analysis concerns in an existing target, including review-and-fix wording
  RUN default REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset AND ORIGINAL_INTENT primarily evaluates an existing document, guide, report, README, or documentation artifact rather than creating one
  RUN classify ORIGINAL_INTENT; SET REVIEW_LOOP_REQUESTED = false WHEN REVIEW_LOOP_REQUESTED == unset
  CONTINUE WriteDocsCompanionRouting
RULES:
  ALWAYS route review/audit/critique/inspect/check/validate/verify/analyze/behavior-comparison/find-issues/bug-risk-failure-regression-bypass-defect-root-cause-routing-analysis intents through WriteDocsReviewLoop first; any fixes must be gated by ReviewFindingsReportBrowser and ReviewFixApprovalGate, not by direct author dispatch
  NEVER run when ORIGINAL_INTENT == unset
```

```pdsl
UNIT WriteDocsCompanionRouting
PURPOSE: Centralize companion-skill and plan-first routing after intent classification.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  SET PLAN_FIRST_CONTINUE = WriteDocsDispatch
  SET CURRENT_WORKFLOW = cf-write-docs
  SET COMPANION_CONTINUE = WriteDocsExploreGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md
  CONTINUE CompanionSkillOffer
```

```pdsl
UNIT WriteDocsExploreGate
PURPOSE: Offer task-relevant context discovery before any document is authored or reviewed, after Bootstrap and before the first edit.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  SET WORKFLOW_PREP_EXPLORE_MENU = WriteDocsExploreMenu
  SET WORKFLOW_PREP_BRAINSTORM_GATE = WriteDocsBrainstormGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/workflow-prep.md
  CONTINUE WorkflowPrepExploreGate
RULES:
  ALWAYS use WorkflowPrepExploreGate for the shared explore prompt mechanics
MENU WriteDocsExploreMenu
TITLE: Before writing or reviewing docs, discover task-relevant project context (existing docs, related guides, source material, conventions) with cf-explore — or skip? Skip is the default when the target and its context are already clear; explore for unfamiliar or cross-cutting documentation. Reply with a number.
OPTIONS:
  1 explore -> INVOKE skill `cf-explore` with intent=workflow-prep, task=ORIGINAL_INTENT, return_context=true; require it to return resource_context only and not perform review/authoring, SET RESOURCE_CONTEXT = provided, then CONTINUE WriteDocsBrainstormGate
  2 skip -> CONTINUE WriteDocsBrainstormGate
  INVALID -> EMIT_MENU WriteDocsExploreMenu
```

```pdsl
UNIT WriteDocsBrainstormGate
PURPOSE: Offer decision/design exploration via cf-brainstorm as the next step after the explore gate, before any document is authored or reviewed.
DO:
  SET WORKFLOW_PREP_BRAINSTORM_MENU = WriteDocsBrainstormMenu
  SET WORKFLOW_PREP_DISPATCH_UNIT = PlanFirstGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/workflow-prep.md
  CONTINUE WorkflowPrepBrainstormGate
RULES:
  ALWAYS use WorkflowPrepBrainstormGate for the shared brainstorm prompt mechanics
MENU WriteDocsBrainstormMenu
TITLE: Before writing or reviewing docs, brainstorm ambiguous decisions or framing options with cf-brainstorm — or skip? Skip is the default when the approach is already clear; brainstorm for ambiguous requirements or open framing questions. Reply with a number.
OPTIONS:
  1 brainstorm -> INVOKE skill `cf-brainstorm`; require it to return brainstorm_decisions, SET BRAINSTORM_DECISIONS = provided, then SET PLAN_FIRST_CONTINUE = WriteDocsDispatch, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE PlanFirstGate
  2 skip -> SET PLAN_FIRST_CONTINUE = WriteDocsDispatch, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE PlanFirstGate
  INVALID -> EMIT_MENU WriteDocsBrainstormMenu
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
UNIT WriteDocsReviewSetup
PURPOSE: Load review modules and anti-spin rules before reviewer dispatch.
WHEN:
  REQUIRE edits have been applied to the document OR REVIEW_LOOP_REQUESTED == true
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/finding-contract.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/semantic-loop-skeleton.md
  RUN SemanticReviewNoSpinRules
  CONTINUE WriteDocsReviewTargetResolution
```

```pdsl
UNIT WriteDocsReviewTargetResolution
PURPOSE: Resolve review target paths and reviewed slices before reviewer or approved-fix dispatch.
WHEN:
  REQUIRE edits have been applied to the document OR REVIEW_LOOP_REQUESTED == true
DO:
  RUN resolve REVIEW_TARGET_PATHS to the declared read-only document path or paths under review, and REVIEW_TARGET_SLICES to the declared reviewed content slices for those targets, before reviewer dispatch or approved review-fix dispatch
  EMIT "Review target resolution is required before document review can continue. Provide the reviewed document path(s) and declared content slice(s) for the target under review." and STOP_TURN WHEN REVIEW_TARGET_PATHS == unset OR REVIEW_TARGET_SLICES == unset
  CONTINUE WriteDocsReviewRun
RULES:
  NEVER dispatch reviewers or approved review-fix writers while REVIEW_TARGET_PATHS == unset OR REVIEW_TARGET_SLICES == unset
```

```pdsl
UNIT WriteDocsReviewerDispatchPolicy
PURPOSE: Prepare scoped reviewer payloads for the selected documentation review granularity.
STATE:
  SET REVIEW_GRANULARITY: single-pass | per-methodology | per-layer (default unset, scope workflow_run)
  SET SELECTED_REVIEWER_DISPATCH_GROUP: dispatch-group | unset (default unset, scope workflow_run)
  SET REVIEWER_SCOPE_MANIFEST: manifest | unset (default unset, scope workflow_run)
DO:
  SET REVIEW_GRANULARITY_SCOPE = "Docs review scope: single-pass covers consistency-checklist and artifact-checklist together; per-methodology dispatches cf-semantic-reviewer-consistency and cf-semantic-reviewer-artifact separately, plus cf-semantic-reviewer-freeform only for a custom review prompt; per-layer dispatches one reviewer per current category."
  RUN SemanticReviewGranularityGate WHEN REVIEW_GRANULARITY == unset
  RUN read the current consistency-checklist category map and the preset-bound ARTIFACT_CHECKLIST_PATH category map WHEN ARTIFACT_CHECKLIST_CONTEXT == preset-bound before a per-layer or per-methodology dispatch, so added categories/sections are covered automatically and never a fixed count
  RUN mark cf-semantic-reviewer-artifact scope as RELAXED/PARTIAL for generic documentation targets WHEN ARTIFACT_CHECKLIST_CONTEXT == unavailable
  SET REVIEWER_SCOPE_MANIFEST = each reviewer instance with only its assigned methodology/category slice plus REVIEW_TARGET_PATHS, REVIEW_TARGET_SLICES, kind=ARTIFACT_REVIEW_KIND, template_path=ARTIFACT_TEMPLATE_PATH, checklist_path=ARTIFACT_CHECKLIST_PATH, example_path=ARTIFACT_EXAMPLE_PATH, kit_rules_path=ARTIFACT_RULES_PATH, rules_mode STRICT when ARTIFACT_CHECKLIST_CONTEXT == preset-bound else RELAXED, any WriteDocsExploreGate-resolved resource_context as read-only context (an absolute path or reference, never inline prompt text), and the Bootstrap-resolved audience/narrator/diagram policy data scoped per {cf-studio-path}/.core/requirements/storytelling-dimensions.md review flow-class rules; reviewers flag a warranted-but-missing or unclear diagram as a finding
  SET SELECTED_REVIEWER_DISPATCH_GROUP for REVIEW_GRANULARITY: single-pass = cf-semantic-reviewer-consistency and cf-semantic-reviewer-artifact in one combined dispatch group, plus cf-semantic-reviewer-freeform only when the user supplied a custom review prompt; per-methodology = cf-semantic-reviewer-consistency and cf-semantic-reviewer-artifact in parallel, plus cf-semantic-reviewer-freeform only when the user supplied a custom review prompt; per-layer = one reviewer per current category for each applicable methodology
RULES:
  ALWAYS preserve the selected REVIEW_GRANULARITY for the remainder of the workflow run unless the user explicitly resets it
  ALWAYS keep workflow-specific reviewer dispatches in this workflow
  NEVER let resource_context or storytelling dimensions gate a reviewer verdict
```

```pdsl
UNIT WriteDocsReviewRun
PURPOSE: Dispatch reviewer sub-agents and aggregate their findings into one report.
WHEN:
  REQUIRE REVIEW_TARGET_PATHS != unset
  REQUIRE REVIEW_TARGET_SLICES != unset
DO:
  RUN WriteDocsReviewerDispatchPolicy
  RUN SubAgentDispatch for SELECTED_REVIEWER_DISPATCH_GROUP before launching reviewer instances
  RUN SELECTED_REVIEWER_DISPATCH_GROUP with REVIEWER_SCOPE_MANIFEST
  RUN aggregation of every reviewer's findings into one deduplicated ReviewFindingsReport with stable finding IDs and every ReviewFindingContract field
  CONTINUE WriteDocsReviewFixGate
RULES:
  ALWAYS scope each reviewer to only its assigned slice and run independent reviewers in parallel
```

```pdsl
UNIT WriteDocsReviewFixGate
PURPOSE: Present review findings, gate fix approval, and route to fix dispatch or outcome.
WHEN:
  REQUIRE REVIEW_TARGET_PATHS != unset
  REQUIRE REVIEW_TARGET_SLICES != unset
DO:
  RUN SemanticReviewFixApprovalGate WHEN findings remain and fixes are applicable
  CONTINUE WriteDocsReviewFixDispatch WHEN REVIEW_FIX_APPROVED == true
  CONTINUE WriteDocsReviewFixOutcome
```

```pdsl
UNIT WriteDocsReviewFixDispatch
PURPOSE: Resolve shared write policy before dispatching approved document review fixes.
WHEN:
  REQUIRE REVIEW_FIX_APPROVED == true
DO:
  SET WRITE_DISPATCH_KIND = review-fix
  CONTINUE WriteDocsWritePolicySetup
```

```pdsl
UNIT WriteDocsReviewFixDispatchRun
PURPOSE: Select the approved-fix document author and dispatch only approved review fixes.
STATE:
  SET SELECTED_REVIEW_FIX_AGENT: cf-generate-author-junior | cf-generate-author-middle | cf-generate-author-senior | cf-generate-author-lead | unset (default unset, scope workflow_run)
DO:
  RUN select SELECTED_REVIEW_FIX_AGENT from the approved findings and REVIEW_TARGET_PATHS using the cf-generate-author selection rules; choose only a concrete write-capable cf-generate-author-* worker tier
  RUN SubAgentDispatch for the SELECTED_REVIEW_FIX_AGENT review-fix dispatch group
  DISPATCH SELECTED_REVIEW_FIX_AGENT with mode=fix, kind=ARTIFACT_REVIEW_KIND, rules_mode STRICT when ARTIFACT_CHECKLIST_CONTEXT == preset-bound else RELAXED, template_path=ARTIFACT_TEMPLATE_PATH, example_path=ARTIFACT_EXAMPLE_PATH, checklist_path=ARTIFACT_CHECKLIST_PATH, kit_rules_path=ARTIFACT_RULES_PATH, target_paths=REVIEW_TARGET_PATHS, REVIEW_TARGET_SLICES, APPROVED_REVIEW_FINDING_IDS, REVIEW_FIX_SCOPE, git_commit_mode=GIT_COMMIT_MODE, contributing_guide=CONTRIBUTING_GUIDE, git_constraint=GIT_CONSTRAINT, commit_footer_contract=COMMIT_FOOTER_CONTRACT, any WriteDocsExploreGate-resolved resource_context as read-only context, and the resolved audience/narrator/diagram policy data as read-only context to apply only approved review fixes
  CONTINUE WriteDocsReviewFixOutcome
RULES:
  NEVER dispatch the read-only cf-generate-author selector itself to write or fix documents
  NEVER let approvals widen silently beyond APPROVED_REVIEW_FINDING_IDS and REVIEW_FIX_SCOPE
  NEVER let resource_context or storytelling dimensions gate the fix verdict
```

```pdsl
UNIT WriteDocsReviewFixOutcome
PURPOSE: Verify fix application, prevent no-spin loops, and route to validation or completion.
STATE:
  SET REVIEW_FIXES_APPLIED: true | false | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE REVIEW_TARGET_PATHS != unset
  REQUIRE REVIEW_TARGET_SLICES != unset
DO:
  RUN verify the returned fix manifest accounts for every APPROVED_REVIEW_FINDING_IDS entry as applied or not-fixable; SET REVIEW_FIXES_APPLIED = true WHEN one or more approved fixes changed content; SET REVIEW_FIXES_APPLIED = false WHEN no content changed
  CONTINUE WriteDocsValidate WHEN REVIEW_FIXES_APPLIED == true
  STOP_TURN and report the remaining findings WHEN findings remain but no fixes were applied this iteration (none approved, none applicable, or the ReviewFixApprovalGate resolved to none) — re-reviewing unchanged content cannot change the result
  STOP_TURN and report that deterministic blockers remain WHEN no review findings remain AND GATE_STATUS == fail
  CONTINUE WriteDocsCompletion WHEN no review findings remain AND GATE_STATUS == pass
  CONTINUE WriteDocsCompletion WHEN no review findings remain AND REVIEW_LOOP_REQUESTED == true AND GATE_STATUS == not-run
RULES:
  NEVER re-loop the review after an iteration with no applied fixes — STOP_TURN reporting the remaining findings so the loop cannot spin on unchanged content; only an applied fix re-runs WriteDocsValidate and re-reviews
```

```pdsl
UNIT WriteDocsReviewLoop
PURPOSE: Run a semantic review at the user-chosen granularity and iterate fixes until the document is clean.
WHEN:
  REQUIRE edits have been applied to the document OR REVIEW_LOOP_REQUESTED == true
DO:
  CONTINUE WriteDocsReviewSetup
RULES:
  NEVER declare an authored or edited document done until BOTH the deterministic gate passes AND the semantic review has no remaining findings
  NEVER declare a review-only document clean until semantic review has no remaining findings; REVIEW_GRANULARITY persists for the workflow run unless the user resets it
```

```pdsl
UNIT WriteDocsCompletion
PURPOSE: Emit a concise completion report, then offer context-grounded next actions after document authoring/review completes cleanly.
WHEN:
  REQUIRE no review findings remain
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT a concise completion report covering work done, deterministic gate outcome (including "not run" when GATE_STATUS == not-run), and semantic review outcome with no remaining findings
  RUN NextActionsOffer
RULES:
  ALWAYS use this unit only after document validation/review is complete and control is about to return to the user
  NEVER bypass NextActionsOffer on a clean terminal path that returns control to the user
```

```pdsl
UNIT WriteDocsDispatch
PURPOSE: Route to review-first or author-first document execution paths.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  CONTINUE WriteDocsReviewLoop WHEN REVIEW_LOOP_REQUESTED == true
  SET WRITE_DISPATCH_KIND = author
  CONTINUE WriteDocsWritePolicySetup
RULES:
  ALWAYS prefer REVIEW_LOOP_REQUESTED == true over author/fix routing, so review-and-fix requests produce findings first and only apply fixes after the review fix-approval gate
  NEVER stop after content generation or deterministic validation before the semantic review-fix loop is offered
  NEVER let a sub-agent reopen prompt or instruction files from disk
```

```pdsl
UNIT WriteDocsWritePolicySetup
PURPOSE: Resolve the shared git write policy before any write-capable document author or approved review-fix dispatch.
STATE:
  SET WRITE_DISPATCH_KIND: author | review-fix | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE WRITE_DISPATCH_KIND != unset
DO:
  RUN GitWriteDispatchPolicyResolve
  CONTINUE WriteDocsReviewFixDispatchRun WHEN WRITE_DISPATCH_KIND == review-fix
  CONTINUE WriteDocsAuthorDispatch WHEN WRITE_DISPATCH_KIND == author
RULES:
  ALWAYS attach commit_footer_contract as read-only policy data to every write-capable dispatch payload
```

```pdsl
UNIT WriteDocsAuthorDispatch
PURPOSE: Select the document author, dispatch it, and route written content into deterministic validation.
STATE:
  SET SELECTED_DOC_AUTHOR_AGENT: cf-generate-author-junior | cf-generate-author-middle | cf-generate-author-senior | cf-generate-author-lead | unset (default unset, scope workflow_run)
  SET PATHS_WRITTEN: list | unset (default unset, scope workflow_run)
DO:
  RUN WriteDocsAuthorPrepareTarget
  CONTINUE WriteDocsAuthorTargetMissing WHEN AUTHOR_TARGET_PATHS == unset OR AUTHOR_TARGET_PATHS is empty
  RUN select SELECTED_DOC_AUTHOR_AGENT using the cf-generate-author selection rules: junior for simple one-file low-risk prose, middle for standard artifacts with moderate cross-references, senior for complex multi-file or strict-rule docs, and lead for high-risk or broad cross-system documentation
  RUN SubAgentDispatch for the SELECTED_DOC_AUTHOR_AGENT dispatch group
  DISPATCH SELECTED_DOC_AUTHOR_AGENT with mode=create, kind=ARTIFACT_REVIEW_KIND, rules_mode STRICT when ARTIFACT_CHECKLIST_CONTEXT == preset-bound else RELAXED, template_path=ARTIFACT_TEMPLATE_PATH, example_path=ARTIFACT_EXAMPLE_PATH, checklist_path=ARTIFACT_CHECKLIST_PATH, kit_rules_path=ARTIFACT_RULES_PATH, target_paths=AUTHOR_TARGET_PATHS, git_commit_mode=GIT_COMMIT_MODE, contributing_guide=CONTRIBUTING_GUIDE, git_constraint=GIT_CONSTRAINT, commit_footer_contract=COMMIT_FOOTER_CONTRACT, any WriteDocsExploreGate-resolved resource_context as read-only context, and the Bootstrap-resolved audience/narrator/diagram policy data as read-only context scoped per {cf-studio-path}/.core/requirements/storytelling-dimensions.md authoring flow-class rules
  RUN WriteDocsAuthorCaptureManifest
  CONTINUE WriteDocsValidate WHEN a document has been written or edited
RULES:
  NEVER dispatch cf-generate-author itself because it is a read-only selector, not a write-capable worker
  NEVER let resource_context or storytelling dimensions gate an author verdict
```

```pdsl
UNIT WriteDocsAuthorPrepareTarget
PURPOSE: Load dispatch support and resolve the create-mode author target paths.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  RUN resolve AUTHOR_TARGET_PATHS from explicit output path(s), preset artifact path, or requested document path in ORIGINAL_INTENT before create-mode author dispatch
```

```pdsl
UNIT WriteDocsAuthorTargetMissing
PURPOSE: Stop when create-mode author target paths are still missing.
DO:
  EMIT "Author target resolution is required before document creation can continue. Provide the output document path(s) to write."
  STOP_TURN
```

```pdsl
UNIT WriteDocsAuthorCaptureManifest
PURPOSE: Capture the written document paths and normalize them for review routing.
DO:
  RUN capture PATHS_WRITTEN from the returned author manifest; SET REVIEW_TARGET_PATHS = PATHS_WRITTEN and SET REVIEW_TARGET_SLICES = full-document slices for every PATHS_WRITTEN entry WHEN PATHS_WRITTEN is not empty
```
