# Review Fix Approval Gate

```pdsl
UNIT ReviewFindingsReportBrowser
PURPOSE: Present review findings as an interactive report before any fixes are approved.
STATE:
  SET REVIEW_REPORT_VIEW: detail | table (default detail, scope workflow_run)
  SET CURRENT_FINDING_INDEX: integer (default 1, scope workflow_run)
  SET SELECTED_FINDING_IDS: list | empty (default empty, scope workflow_run)
  SET REVIEW_FIX_APPROVED: true | false | unset (default unset, scope workflow_run)
  SET APPROVED_REVIEW_FINDING_IDS: list | all-critical-major | all | empty (default empty, scope workflow_run)
WHEN:
  REQUIRE ReviewFindingsReport exists and contains one or more findings
DO:
  EMIT the current finding in detail view WHEN REVIEW_REPORT_VIEW == detail: finding id, position N of total, SEVERITY, LOCATION, EVIDENCE, ROOT_CAUSE, IMPACT, SUGGESTED_FIX, VERIFICATION, and CONFIDENCE
  EMIT the full findings table WHEN REVIEW_REPORT_VIEW == table: id, severity, location, one-line impact, selected-for-fix marker
  EMIT_MENU ReviewFindingsNavigation
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS show findings one by one by default, preserving every ReviewFindingContract field in detail view
  ALWAYS allow next and previous navigation without changing fix approval state
  ALWAYS allow marking and unmarking the current finding for partial fixes before ReviewFixApprovalGate resolves REVIEW_FIX_SCOPE
  ALWAYS allow switching to a full table view and back to detailed finding view
  ALWAYS preserve SELECTED_FINDING_IDS for the calling review loop when REVIEW_FIX_SCOPE == partial
  NEVER apply fixes from this report browser; only ReviewFixApprovalGate can approve a fix scope
MENU ReviewFindingsNavigation
TITLE: Review findings — inspect them, mark specific items for fix, switch views, or continue to fix choices.
OPTIONS:
  1 next -> increment CURRENT_FINDING_INDEX up to the final finding, SET REVIEW_REPORT_VIEW = detail, and rerender ReviewFindingsReportBrowser
  2 prev -> decrement CURRENT_FINDING_INDEX down to 1, SET REVIEW_REPORT_VIEW = detail, and rerender ReviewFindingsReportBrowser
  3 mark -> add the current finding id to SELECTED_FINDING_IDS, SET REVIEW_REPORT_VIEW = detail, and rerender ReviewFindingsReportBrowser
  4 unmark -> remove the current finding id from SELECTED_FINDING_IDS, SET REVIEW_REPORT_VIEW = detail, and rerender ReviewFindingsReportBrowser
  5 table -> SET REVIEW_REPORT_VIEW = table and rerender ReviewFindingsReportBrowser
  6 detail -> SET REVIEW_REPORT_VIEW = detail and rerender ReviewFindingsReportBrowser
  7 fix-menu -> CONTINUE ReviewFixApprovalGate
  8 none -> SET REVIEW_FIX_SCOPE = none; SET REVIEW_FIX_APPROVED = false; SET APPROVED_REVIEW_FINDING_IDS = empty; return to the calling review loop without applying fixes
  INVALID -> EMIT_MENU ReviewFindingsNavigation
```

```pdsl
UNIT ReviewFixApprovalGate
PURPOSE: Gate every review-fix loop on explicit user approval and let the user choose the fix scope.
STATE:
  SET REVIEW_FIX_SCOPE: critical-major | all | partial | none | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_APPROVED: true | false | unset (default unset, scope workflow_run)
  SET APPROVED_REVIEW_FINDING_IDS: list | all-critical-major | all | empty (default empty, scope workflow_run)
WHEN:
  REQUIRE a review-fix loop has produced findings and is about to apply fixes
DO:
  EMIT_MENU ReviewFixScope
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS request user confirmation before applying any fixes in a review-fix loop
  ALWAYS run after ReviewFindingsReportBrowser has shown the findings report for the current review iteration
  ALWAYS offer the fix-scope options: only CRITICAL and MAJOR findings, all findings, or a user-selected partial subset
  ALWAYS when REVIEW_FIX_SCOPE == partial, use SELECTED_FINDING_IDS from ReviewFindingsReportBrowser or ask for specific finding IDs before returning to the caller
  ALWAYS set REVIEW_FIX_SCOPE and REVIEW_FIX_APPROVED from the resolved menu option before returning control to the calling review loop
  ALWAYS set APPROVED_REVIEW_FINDING_IDS to all-critical-major, all, or the selected specific finding IDs before returning with REVIEW_FIX_APPROVED == true
  ALWAYS treat REVIEW_FIX_SCOPE == none and REVIEW_FIX_APPROVED == false as "no fixes approved" and let the calling review loop report the remaining findings
  NEVER apply review fixes without explicit user approval of the chosen scope
MENU ReviewFixScope
TITLE: Review found issues — what should I fix? (nothing is changed until you choose)
OPTIONS:
  1 crit-major -> SET REVIEW_FIX_SCOPE = critical-major; SET REVIEW_FIX_APPROVED = true; SET APPROVED_REVIEW_FINDING_IDS = all-critical-major; return to the calling review loop to fix only CRITICAL and MAJOR findings, then re-review (suggested)
  2 all -> SET REVIEW_FIX_SCOPE = all; SET REVIEW_FIX_APPROVED = true; SET APPROVED_REVIEW_FINDING_IDS = all; return to the calling review loop to fix all findings, then re-review
  3 partial -> SET REVIEW_FIX_SCOPE = partial; SET REVIEW_FIX_APPROVED = true; SET APPROVED_REVIEW_FINDING_IDS = SELECTED_FINDING_IDS when non-empty, otherwise ask which specific finding IDs to fix; return to the calling review loop to fix only those, then re-review
  4 none -> SET REVIEW_FIX_SCOPE = none; SET REVIEW_FIX_APPROVED = false; SET APPROVED_REVIEW_FINDING_IDS = empty; return to the calling review loop without applying fixes
  INVALID -> EMIT_MENU ReviewFixScope
```
