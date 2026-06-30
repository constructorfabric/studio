# Review Fix Approval Gate

```pdsl
UNIT ReviewFindingsReportBrowser
PURPOSE: Present review findings as an interactive report before any fixes are approved.
STATE:
  SET REVIEW_REPORT_VIEW: detail | table (default detail, scope workflow_run)
  SET CURRENT_FINDING_INDEX: integer (default 1, scope workflow_run)
  SET REVIEW_FINDINGS_BROWSER_ENTRY: first | rerender | unset (default unset, scope workflow_run)
  SET SELECTED_FINDING_IDS: list | empty (default empty, scope workflow_run)
  SET REVIEW_FIX_SCOPE: critical-major | all | partial | none | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_APPROVED: true | false | unset (default unset, scope workflow_run)
  SET APPROVED_REVIEW_FINDING_IDS: list | all-critical-major | all | empty (default empty, scope workflow_run)
  SET REVIEW_FIX_MENU_TOKEN: ready | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_MENU_REPORT: current | unset (default unset, scope workflow_run)
  SET REVIEW_FINDINGS_BROWSER_CONFIRMED: true | false | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE ReviewFindingsReport exists and contains one or more findings
DO:
  RUN ReviewFindingsBrowserReset
  RUN ReviewFindingsBrowserRender
  SET REVIEW_FINDINGS_BROWSER_CONFIRMED = true
  EMIT_MENU ReviewFindingsNavigation
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS show findings one by one by default, preserving every ReviewFindingContract field in detail view
  ALWAYS allow next and previous navigation without changing fix approval state
  ALWAYS allow marking and unmarking the current finding for partial fixes before ReviewFixApprovalGate resolves REVIEW_FIX_SCOPE
  ALWAYS when marking a non-final finding, advance to the next finding in detail view after recording the selection
  ALWAYS when marking the final finding, keep the browser active, preserve the current final-finding position, and rerender so the user may still review, unmark, switch views, or choose `fix-menu`
  ALWAYS allow switching to a full table view and back to detailed finding view
  ALWAYS treat REVIEW_FINDINGS_BROWSER_ENTRY == first as the first browser entry for the current ReviewFindingsReport, clear any carried marked selection, reset CURRENT_FINDING_INDEX to 1, and reset REVIEW_REPORT_VIEW to detail before rendering
  ALWAYS treat REVIEW_FINDINGS_BROWSER_ENTRY == rerender as navigation or rerender within the same browser session and preserve SELECTED_FINDING_IDS, CURRENT_FINDING_INDEX, and REVIEW_REPORT_VIEW except when menu options explicitly change them
  ALWAYS preserve SELECTED_FINDING_IDS for the calling review loop when REVIEW_FIX_SCOPE == partial
  NEVER apply fixes from this report browser; only ReviewFixApprovalGate can approve a fix scope
  NEVER present ReviewFixScope before ReviewFindingsReportBrowser has rendered the current report and set REVIEW_FINDINGS_BROWSER_CONFIRMED = true
MENU ReviewFindingsNavigation
TITLE: Review findings — inspect them, mark specific items for fix, switch views, or continue to fix choices.
OPTIONS:
  1 next -> increment CURRENT_FINDING_INDEX up to the final finding, SET REVIEW_REPORT_VIEW = detail, and rerender ReviewFindingsReportBrowser
  2 prev -> decrement CURRENT_FINDING_INDEX down to 1, SET REVIEW_REPORT_VIEW = detail, and rerender ReviewFindingsReportBrowser
  3 mark -> add the current finding id to SELECTED_FINDING_IDS, SET REVIEW_REPORT_VIEW = detail, increment CURRENT_FINDING_INDEX and rerender ReviewFindingsReportBrowser WHEN the current finding is not the final finding; otherwise SET REVIEW_REPORT_VIEW = detail and rerender ReviewFindingsReportBrowser
  4 unmark -> remove the current finding id from SELECTED_FINDING_IDS, SET REVIEW_REPORT_VIEW = detail, and rerender ReviewFindingsReportBrowser
  5 table -> SET REVIEW_REPORT_VIEW = table and rerender ReviewFindingsReportBrowser
  6 detail -> SET REVIEW_REPORT_VIEW = detail and rerender ReviewFindingsReportBrowser
  7 fix-menu -> SET REVIEW_FINDINGS_BROWSER_ENTRY = unset; SET REVIEW_FIX_MENU_TOKEN = ready; SET REVIEW_FIX_MENU_REPORT = current; CONTINUE ReviewFixApprovalGate
  8 exit (skip all fixes) — leave findings open, return without fixing -> SET REVIEW_FINDINGS_BROWSER_ENTRY = unset; SET REVIEW_FIX_SCOPE = none; SET REVIEW_FIX_APPROVED = false; SET APPROVED_REVIEW_FINDING_IDS = empty; RETURN to the calling review loop without applying fixes
  INVALID -> EMIT_MENU ReviewFindingsNavigation
```

```pdsl
UNIT ReviewFindingsBrowserReset
PURPOSE: Normalize the first-entry state for the active review findings browser session.
DO:
  SET REVIEW_FINDINGS_BROWSER_ENTRY = first WHEN REVIEW_FINDINGS_BROWSER_ENTRY == unset
  SET SELECTED_FINDING_IDS = empty WHEN REVIEW_FINDINGS_BROWSER_ENTRY == first
  SET CURRENT_FINDING_INDEX = 1 WHEN REVIEW_FINDINGS_BROWSER_ENTRY == first
  SET REVIEW_REPORT_VIEW = detail WHEN REVIEW_FINDINGS_BROWSER_ENTRY == first
  SET REVIEW_FINDINGS_BROWSER_CONFIRMED = false WHEN REVIEW_FINDINGS_BROWSER_ENTRY == first
  SET REVIEW_FINDINGS_BROWSER_ENTRY = rerender WHEN REVIEW_FINDINGS_BROWSER_ENTRY == first
```

```pdsl
UNIT ReviewFindingsBrowserRender
PURPOSE: Emit the current browser view for the active review findings report.
DO:
  EMIT the current finding in detail view WHEN REVIEW_REPORT_VIEW == detail: finding id, position N of total, SEVERITY, LOCATION, EVIDENCE, ROOT_CAUSE, IMPACT, SUGGESTED_FIX, VERIFICATION, and CONFIDENCE
  EMIT the full findings table WHEN REVIEW_REPORT_VIEW == table: id, severity, location, one-line impact, selected-for-fix marker
```

```pdsl
UNIT ReviewFixApprovalGate
PURPOSE: Gate every review-fix loop on explicit user approval and let the user choose the fix scope.
STATE:
  SET SELECTED_FINDING_IDS: list | empty (default empty, scope workflow_run)
  SET REVIEW_FIX_SCOPE: critical-major | all | partial | none | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_APPROVED: true | false | unset (default unset, scope workflow_run)
  SET APPROVED_REVIEW_FINDING_IDS: list | all-critical-major | all | empty (default empty, scope workflow_run)
  SET REVIEW_FIX_MENU_TOKEN: ready | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_MENU_REPORT: current | unset (default unset, scope workflow_run)
  SET REVIEW_FINDINGS_BROWSER_CONFIRMED: true | false | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE a review-fix loop has produced findings and is about to apply fixes
  REQUIRE REVIEW_FIX_MENU_TOKEN == ready
  REQUIRE REVIEW_FIX_MENU_REPORT == current
DO:
  CONTINUE ReviewFindingsReportBrowser WHEN REVIEW_FINDINGS_BROWSER_CONFIRMED != true
  EMIT_MENU ReviewFixScope
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS request user confirmation before applying any fixes in a review-fix loop
  ALWAYS run only when continued from the browser-owned `fix-menu` in ReviewFindingsReportBrowser for the current review iteration
  ALWAYS treat REVIEW_FIX_MENU_TOKEN plus REVIEW_FIX_MENU_REPORT == current as a one-use continuation guard from the active ReviewFindingsReport
  ALWAYS return to ReviewFindingsReportBrowser instead of emitting ReviewFixScope when the current report has not been rendered by the browser in this workflow run
  ALWAYS offer the fix-scope options: only CRITICAL and MAJOR findings, all findings, or a user-selected partial subset
  ALWAYS include a browser option in ReviewFixScope so the user can return from fix approval to the findings browser without applying fixes
  ALWAYS set REVIEW_FIX_SCOPE and REVIEW_FIX_APPROVED from the resolved menu option before returning control to the calling review loop
  ALWAYS clear REVIEW_FIX_MENU_TOKEN and REVIEW_FIX_MENU_REPORT after ReviewFixApprovalGate resolves
  ALWAYS treat REVIEW_FIX_SCOPE == none and REVIEW_FIX_APPROVED == false as "no fixes approved" and let the calling review loop report the remaining findings
  NEVER present ReviewFixScope as a short findings table plus fix choices; the findings table belongs only to ReviewFindingsReportBrowser table view
  NEVER apply review fixes without explicit user approval of the chosen scope
MENU ReviewFixScope
TITLE: Review found issues — what should I fix? Inject live counts before emitting: "N CRITICAL/MAJOR and M MINOR findings — nothing is changed until you choose."
OPTIONS:
  1 critical + major only — fix the N highest-severity findings, then re-review (suggested when CRITICAL or MAJOR findings exist) -> CONTINUE ReviewFixScopeApproveCriticalMajor
  2 all findings — fix all N+M findings including MINOR -> CONTINUE ReviewFixScopeApproveAll
  3 select specific — choose individual findings by ID or browser selection -> SET REVIEW_FIX_SCOPE = partial; SET REVIEW_FIX_APPROVED = true; CONTINUE ReviewFixPartialScopeResolve
  4 back to browser — review findings again before deciding -> SET REVIEW_FIX_MENU_TOKEN = unset; SET REVIEW_FIX_MENU_REPORT = unset; CONTINUE ReviewFindingsReportBrowser
  5 skip fixes — close without applying any fixes -> CONTINUE ReviewFixScopeApproveNone
  INVALID -> EMIT_MENU ReviewFixScope
```

```pdsl
UNIT ReviewFixScopeApproveCriticalMajor
PURPOSE: Approve only CRITICAL and MAJOR findings for the current review-fix iteration.
DO:
  SET REVIEW_FIX_SCOPE = critical-major
  SET REVIEW_FIX_APPROVED = true
  SET APPROVED_REVIEW_FINDING_IDS = all-critical-major
  SET REVIEW_FIX_MENU_TOKEN = unset
  SET REVIEW_FIX_MENU_REPORT = unset
  RETURN to the calling review loop to fix only CRITICAL and MAJOR findings, then re-review
```

```pdsl
UNIT ReviewFixScopeApproveAll
PURPOSE: Approve every finding from the current review report for the next fix iteration.
DO:
  SET REVIEW_FIX_SCOPE = all
  SET REVIEW_FIX_APPROVED = true
  SET APPROVED_REVIEW_FINDING_IDS = all
  SET REVIEW_FIX_MENU_TOKEN = unset
  SET REVIEW_FIX_MENU_REPORT = unset
  RETURN to the calling review loop to fix all findings, then re-review
```

```pdsl
UNIT ReviewFixScopeApproveNone
PURPOSE: Return to the calling review loop with no fixes approved for the current report.
DO:
  SET REVIEW_FIX_SCOPE = none
  SET REVIEW_FIX_APPROVED = false
  SET APPROVED_REVIEW_FINDING_IDS = empty
  SET REVIEW_FIX_MENU_TOKEN = unset
  SET REVIEW_FIX_MENU_REPORT = unset
  RETURN to the calling review loop without applying fixes
```

```pdsl
UNIT ReviewFixPartialScopeResolve
PURPOSE: Resolve a partial review-fix approval from marked findings or explicit ID capture.
STATE:
  SET SELECTED_FINDING_IDS: list | empty (default empty, scope workflow_run)
  SET REVIEW_FIX_SCOPE: critical-major | all | partial | none | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_APPROVED: true | false | unset (default unset, scope workflow_run)
  SET PARTIAL_IDS_CAPTURE_STATE: prompt | validate | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_MENU_TOKEN: ready | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_MENU_REPORT: current | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE REVIEW_FIX_SCOPE == partial
  REQUIRE REVIEW_FIX_APPROVED == true
  REQUIRE REVIEW_FIX_MENU_TOKEN == ready
  REQUIRE REVIEW_FIX_MENU_REPORT == current
DO:
  SET SELECTED_FINDING_IDS = the finding IDs in SELECTED_FINDING_IDS that match findings in the active ReviewFindingsReport WHEN SELECTED_FINDING_IDS != empty
  SET PARTIAL_IDS_CAPTURE_STATE = prompt WHEN SELECTED_FINDING_IDS == empty
  CONTINUE ReviewFixPartialMarkedSelectionReturn WHEN SELECTED_FINDING_IDS != empty
  CONTINUE ReviewFixPartialIdsCapture WHEN SELECTED_FINDING_IDS == empty
RULES:
  ALWAYS filter SELECTED_FINDING_IDS against the active ReviewFindingsReport before partial-scope branching
  ALWAYS preserve the active ReviewFindingsReport guard until the partial path resolves to marked findings or explicit captured IDs
```

```pdsl
UNIT ReviewFixPartialMarkedSelectionReturn
PURPOSE: Return approved partial selections that were already marked in the review browser.
STATE:
  SET SELECTED_FINDING_IDS: list | empty (default empty, scope workflow_run)
  SET REVIEW_FIX_SCOPE: critical-major | all | partial | none | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_APPROVED: true | false | unset (default unset, scope workflow_run)
  SET APPROVED_REVIEW_FINDING_IDS: list | all-critical-major | all | empty (default empty, scope workflow_run)
  SET REVIEW_FIX_MENU_TOKEN: ready | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_MENU_REPORT: current | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE REVIEW_FIX_SCOPE == partial
  REQUIRE REVIEW_FIX_APPROVED == true
  REQUIRE SELECTED_FINDING_IDS != empty
  REQUIRE REVIEW_FIX_MENU_TOKEN == ready
  REQUIRE REVIEW_FIX_MENU_REPORT == current
DO:
  SET APPROVED_REVIEW_FINDING_IDS = SELECTED_FINDING_IDS
  SET REVIEW_FIX_MENU_TOKEN = unset
  SET REVIEW_FIX_MENU_REPORT = unset
  RETURN to the calling review loop to fix only those, then re-review
RULES:
  ALWAYS set APPROVED_REVIEW_FINDING_IDS before clearing REVIEW_FIX_MENU_TOKEN and REVIEW_FIX_MENU_REPORT
```

```pdsl
UNIT ReviewFixPartialIdsCapture
PURPOSE: Route explicit partial-ID capture between the first-entry prompt and resumed validation.
STATE:
  SET PARTIAL_IDS_CAPTURE_STATE: prompt | validate | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE REVIEW_FIX_SCOPE == partial
  REQUIRE REVIEW_FIX_APPROVED == true
  REQUIRE SELECTED_FINDING_IDS == empty
  REQUIRE REVIEW_FIX_MENU_TOKEN == ready
  REQUIRE REVIEW_FIX_MENU_REPORT == current
DO:
  CONTINUE ReviewFixPartialIdsPrompt WHEN PARTIAL_IDS_CAPTURE_STATE == prompt
  CONTINUE ReviewFixPartialIdsValidate WHEN PARTIAL_IDS_CAPTURE_STATE == validate
RULES:
  ALWAYS route first-entry partial-ID capture through the prompt unit before any explicit-ID validation runs
```

```pdsl
UNIT ReviewFixPartialIdsPrompt
PURPOSE: Capture explicit finding IDs for a partial review-fix request when the report browser has no marked selection.
STATE:
  SET SELECTED_FINDING_IDS: list | empty (default empty, scope workflow_run)
  SET REVIEW_FIX_SCOPE: critical-major | all | partial | none | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_APPROVED: true | false | unset (default unset, scope workflow_run)
  SET PARTIAL_IDS_CAPTURE_STATE: prompt | validate | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_MENU_TOKEN: ready | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_MENU_REPORT: current | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE REVIEW_FIX_SCOPE == partial
  REQUIRE REVIEW_FIX_APPROVED == true
  REQUIRE SELECTED_FINDING_IDS == empty
  REQUIRE PARTIAL_IDS_CAPTURE_STATE == prompt
  REQUIRE REVIEW_FIX_MENU_TOKEN == ready
  REQUIRE REVIEW_FIX_MENU_REPORT == current
DO:
  EMIT the following prompt, replacing bracketed values with live data from the active ReviewFindingsReport: "Select findings to fix by ID. Available: [list all IDs with severity, e.g. F-001 CRITICAL, F-002 MAJOR, F-003 MINOR]. Reply with one or more IDs separated by spaces or commas (e.g. F-001 F-003), or reply `back` to return to the findings browser."
  SET PARTIAL_IDS_CAPTURE_STATE = validate
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS emit the available finding IDs with their severities before waiting for input
  ALWAYS emit the expected format example (e.g. F-001 F-003) in the prompt
  ALWAYS advance PARTIAL_IDS_CAPTURE_STATE to validate before stopping so the resumed turn cannot treat the scope-menu reply as finding-ID input
```

```pdsl
UNIT ReviewFixPartialIdsValidate
PURPOSE: Validate resumed explicit finding-ID input for a partial review-fix request.
STATE:
  SET SELECTED_FINDING_IDS: list | empty (default empty, scope workflow_run)
  SET REVIEW_FIX_SCOPE: critical-major | all | partial | none | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_APPROVED: true | false | unset (default unset, scope workflow_run)
  SET APPROVED_REVIEW_FINDING_IDS: list | all-critical-major | all | empty (default empty, scope workflow_run)
  SET PARTIAL_IDS_CAPTURE_STATE: prompt | validate | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_MENU_TOKEN: ready | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_MENU_REPORT: current | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE REVIEW_FIX_SCOPE == partial
  REQUIRE REVIEW_FIX_APPROVED == true
  REQUIRE SELECTED_FINDING_IDS == empty
  REQUIRE PARTIAL_IDS_CAPTURE_STATE == validate
  REQUIRE REVIEW_FIX_MENU_TOKEN == ready
  REQUIRE REVIEW_FIX_MENU_REPORT == current
DO:
  SET PARTIAL_IDS_CAPTURE_STATE = unset WHEN user.reply == "back"
  CONTINUE ReviewFindingsReportBrowser WHEN user.reply == "back"
  CONTINUE ReviewFixPartialIdsRetry WHEN user.reply is empty OR user.reply names no finding IDs from the active ReviewFindingsReport
  CONTINUE ReviewFixPartialIdsReturn WHEN user.reply names one or more finding IDs from the active ReviewFindingsReport
RULES:
  ALWAYS keep the active ReviewFindingsReport guard in place while waiting for explicit partial finding IDs
  ALWAYS retry partial ID capture when user.reply is missing, empty, or names no finding IDs from the active ReviewFindingsReport
  ALWAYS return from partial ID capture only after parsing at least one valid finding ID from the active ReviewFindingsReport
```

```pdsl
UNIT ReviewFixPartialIdsRetry
PURPOSE: Re-prompt for explicit finding IDs when the resumed reply does not name any valid current findings.
DO:
  EMIT_MENU ReviewFixPartialIdsRetryMenu
  WAIT user.reply
  STOP_TURN
MENU ReviewFixPartialIdsRetryMenu
TITLE: No valid finding IDs were recognised — how do you want to proceed?
OPTIONS:
  1 retry — enter IDs again (format: F-001 F-003, separated by spaces or commas) -> CONTINUE ReviewFixPartialIdsValidate
  2 browser — return to the findings browser to check IDs -> SET REVIEW_FIX_MENU_TOKEN = unset; SET REVIEW_FIX_MENU_REPORT = unset; CONTINUE ReviewFindingsReportBrowser
  3 back — return to the fix-scope menu -> SET REVIEW_FIX_SCOPE = unset; SET REVIEW_FIX_APPROVED = unset; CONTINUE ReviewFixApprovalGate
  INVALID -> EMIT_MENU ReviewFixPartialIdsRetryMenu
```

```pdsl
UNIT ReviewFixPartialIdsReturn
PURPOSE: Return the explicit partial finding-ID selection to the calling review loop.
STATE:
  SET APPROVED_REVIEW_FINDING_IDS: list | all-critical-major | all | empty (default empty, scope workflow_run)
  SET PARTIAL_IDS_CAPTURE_STATE: prompt | validate | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_MENU_TOKEN: ready | unset (default unset, scope workflow_run)
  SET REVIEW_FIX_MENU_REPORT: current | unset (default unset, scope workflow_run)
DO:
  SET APPROVED_REVIEW_FINDING_IDS = the specific finding IDs named in user.reply that match findings in the active ReviewFindingsReport
  SET PARTIAL_IDS_CAPTURE_STATE = unset
  SET REVIEW_FIX_MENU_TOKEN = unset
  SET REVIEW_FIX_MENU_REPORT = unset
  RETURN to the calling review loop to fix only those, then re-review
```
