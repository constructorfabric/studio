# Review Fix Approval Gate

```pdsl
UNIT ReviewFixApprovalGate
PURPOSE: Gate every review-fix loop on explicit user approval and let the user choose the fix scope.
WHEN:
  REQUIRE a review-fix loop has produced findings and is about to apply fixes
DO:
  EMIT_MENU ReviewFixScope
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS request user confirmation before applying any fixes in a review-fix loop
  ALWAYS offer the fix-scope options: only CRITICAL and MAJOR findings, all findings, or a user-selected partial subset
  NEVER apply review fixes without explicit user approval of the chosen scope
MENU ReviewFixScope
TITLE: Review found issues — what should I fix? (nothing is changed until you choose)
OPTIONS:
  1 crit-major -> fix only CRITICAL and MAJOR findings, then re-review (suggested)
  2 all -> fix all findings, then re-review
  3 partial -> ask which specific findings to fix, fix only those, then re-review
  4 none -> STOP_TURN
  INVALID -> EMIT_MENU ReviewFixScope
```
