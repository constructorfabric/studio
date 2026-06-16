# Coding Review Fix

```pdsl
UNIT CodingReviewFixGate
PURPOSE: Present review findings, gate fix approval, and route to fix dispatch or outcome.
WHEN:
  REQUIRE edits have been applied to the code OR REVIEW_LOOP_REQUESTED == true
DO:
  RUN SemanticReviewFixApprovalGate WHEN findings remain and fixes are applicable
  CONTINUE CodingReviewFixDispatch WHEN REVIEW_FIX_APPROVED == true
  CONTINUE CodingReviewFixOutcome
```

```pdsl
UNIT CodingReviewFixDispatch
PURPOSE: Select the approved-fix coder, enforce git write policy, and dispatch only the approved fixes.
STATE:
  SET SELECTED_REVIEW_FIX_AGENT: cf-codegen | cf-generate-coder-smart | cf-generate-coder-casual | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE REVIEW_FIX_APPROVED == true
DO:
  RUN GitWriteDispatchPolicyResolve
  RUN select SELECTED_REVIEW_FIX_AGENT from approved findings and target code paths using CodingAuthorDispatch priority
  RUN SubAgentDispatch for the SELECTED_REVIEW_FIX_AGENT review-fix dispatch group
  DISPATCH SELECTED_REVIEW_FIX_AGENT with mode=fix, target_paths, APPROVED_REVIEW_FINDING_IDS, REVIEW_FIX_SCOPE, git_commit_mode=GIT_COMMIT_MODE, contributing_guide=CONTRIBUTING_GUIDE, git_constraint=GIT_CONSTRAINT, commit_footer_contract=COMMIT_FOOTER_CONTRACT, and resource_context to apply only approved review fixes
  CONTINUE CodingReviewFixOutcome
RULES:
  NEVER let approvals widen silently beyond APPROVED_REVIEW_FINDING_IDS and REVIEW_FIX_SCOPE
  NEVER let resource_context gate the fix verdict
  NEVER rely on a stale or implicit coder selection for approved review fixes
```

```pdsl
UNIT CodingReviewFixOutcome
PURPOSE: Verify fix application, prevent no-spin loops, and route to validation or completion.
STATE:
  SET REVIEW_FIXES_APPLIED: true | false | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE edits have been applied to the code OR REVIEW_LOOP_REQUESTED == true
DO:
  RUN verify the returned fix manifest accounts for every APPROVED_REVIEW_FINDING_IDS entry as applied or not-fixable; SET REVIEW_FIXES_APPLIED = true WHEN one or more approved fixes changed code; SET REVIEW_FIXES_APPLIED = false WHEN no code changed
  CONTINUE CodingValidate WHEN REVIEW_FIXES_APPLIED == true
  STOP_TURN and report the remaining findings WHEN findings remain but no fixes were applied this iteration (none approved, none applicable, or the ReviewFixApprovalGate resolved to none)
  STOP_TURN and report deterministic blockers WHEN no review findings remain AND GATE_STATUS == fail
  CONTINUE CodingCompletion WHEN no review findings remain AND GATE_STATUS != fail AND (REVIEW_LOOP_REQUESTED == true OR GATE_STATUS == pass)
RULES:
  NEVER re-loop the review after an iteration with no applied fixes — STOP_TURN reporting the remaining findings so the loop cannot spin on unchanged code; only an applied fix re-runs CodingValidate and re-reviews
```
