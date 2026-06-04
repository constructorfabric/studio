---
cf: true
type: workflow-fragment
name: pdsl-write-confirm-menu
description: Shared write-confirm menu shell for cf-pdsl write-capable modes.
version: 0.1
purpose: Reuse the common proceed or cancel confirmation menu before a cf-pdsl file-writing dispatch.
---

# PDSL Write Confirm Menu

```pdsl
MENU SharedPdslWriteConfirmMenu:
  TITLE: Confirm write to target path(s) listed above
  OPTIONS:
    1 proceed -> DISPATCH PDSL_WRITE_CONFIRM_AGENT WITH PDSL_WRITE_CONFIRM_INPUTS
                 RETURN manifest
    2 cancel  -> EMIT "Write cancelled. No files written."
                 STOP_TURN
  INVALID:
    EMIT "Reply with 1 (proceed) or 2 (cancel)."
    WAIT user.reply
    STOP_TURN
```
