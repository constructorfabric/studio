# Write Docs Write Policy
```pdsl
UNIT WriteDocsWritePolicySetup
PURPOSE: Resolve the shared git write policy before any write-capable document author or approved review-fix dispatch.
STATE:
  SET WRITE_DISPATCH_KIND: author | review-fix | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE WRITE_DISPATCH_KIND != unset
DO:
  RUN GitWriteDispatchPolicyResolve
  RUN WriteDocsWriteReferenceLoad
  CONTINUE WriteDocsReviewFixDispatchRun WHEN WRITE_DISPATCH_KIND == review-fix
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-author-dispatch.md WHEN WRITE_DISPATCH_KIND == author
  CONTINUE WriteDocsAuthorDispatch WHEN WRITE_DISPATCH_KIND == author
RULES:
  ALWAYS attach commit_footer_contract as read-only policy data to every write-capable dispatch payload
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
  LOAD {cf-studio-path}/.core/skills/studio/modules/write-docs-completion.md WHEN no review findings remain AND (GATE_STATUS == pass OR (REVIEW_LOOP_REQUESTED == true AND GATE_STATUS == not-run))
  CONTINUE WriteDocsCompletion WHEN no review findings remain AND GATE_STATUS == pass
  CONTINUE WriteDocsCompletion WHEN no review findings remain AND REVIEW_LOOP_REQUESTED == true AND GATE_STATUS == not-run
RULES:
  NEVER re-loop the review after an iteration with no applied fixes — STOP_TURN reporting the remaining findings so the loop cannot spin on unchanged content; only an applied fix re-runs WriteDocsValidate and re-reviews
```
