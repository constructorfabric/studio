# Write Docs Author Dispatch

```pdsl
UNIT WriteDocsAuthorDispatch
PURPOSE: Select the document author, dispatch it, and route written content into deterministic validation.
STATE:
  SET SELECTED_DOC_AUTHOR_AGENT: cf-generate-author-junior | cf-generate-author-middle | cf-generate-author-senior | cf-generate-author-lead | unset (default unset, scope workflow_run)
  SET PATHS_WRITTEN: list | unset (default unset, scope workflow_run)
DO:
  RUN WriteDocsAuthorPrepareTarget
  CONTINUE WriteDocsAuthorTargetMissing WHEN AUTHOR_TARGET_PATHS == unset OR AUTHOR_TARGET_PATHS is empty
  RUN WriteDocsExecutionContextPrep
  RUN select SELECTED_DOC_AUTHOR_AGENT using the cf-generate-author selection rules: junior for simple one-file low-risk prose, middle for standard artifacts with moderate cross-references, senior for complex multi-file or strict-rule docs, and lead for high-risk or broad cross-system documentation
  RUN SubAgentDispatch for the SELECTED_DOC_AUTHOR_AGENT dispatch group
  DISPATCH SELECTED_DOC_AUTHOR_AGENT with mode=create, kind=ARTIFACT_REVIEW_KIND, rules_mode STRICT when ARTIFACT_CHECKLIST_CONTEXT == preset-bound else RELAXED, template_path=ARTIFACT_TEMPLATE_PATH, example_path=ARTIFACT_EXAMPLE_PATH, checklist_path=ARTIFACT_CHECKLIST_PATH, kit_rules_path=ARTIFACT_RULES_PATH, target_paths=AUTHOR_TARGET_PATHS, git_commit_mode=GIT_COMMIT_MODE, contributing_guide=CONTRIBUTING_GUIDE, git_constraint=GIT_CONSTRAINT, commit_footer_contract=COMMIT_FOOTER_CONTRACT, any WriteDocsExploreGate-resolved resource_context as read-only context, and the execution-prep-resolved audience/narrator/diagram policy data as read-only context scoped per {cf-studio-path}/.core/requirements/storytelling-dimensions.md authoring flow-class rules
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
  EMIT "I could not determine which file to write. Reply with the output path — for example: `docs/guides/my-guide.md`. Or choose a next step:"
  EMIT_MENU WriteDocsAuthorTargetMissingMenu
  WAIT user.reply
  STOP_TURN
MENU WriteDocsAuthorTargetMissingMenu
TITLE: Provide output path or choose a next step.
OPTIONS:
  1 provide path — reply with the output file path -> SET AUTHOR_TARGET_PATHS = user.reply; CONTINUE WriteDocsAuthorDispatch
  2 plan first — run cf-documenting-planning to define document scope first -> LOAD and CONTINUE cf-documenting-planning
  3 cancel -> STOP_TURN
  INVALID -> EMIT_MENU WriteDocsAuthorTargetMissingMenu
```

```pdsl
UNIT WriteDocsAuthorCaptureManifest
PURPOSE: Capture the written document paths and normalize them for review routing.
DO:
  RUN capture PATHS_WRITTEN from the returned author manifest; SET REVIEW_TARGET_PATHS = PATHS_WRITTEN and SET REVIEW_TARGET_SLICES = full-document slices for every PATHS_WRITTEN entry WHEN PATHS_WRITTEN is not empty
```
