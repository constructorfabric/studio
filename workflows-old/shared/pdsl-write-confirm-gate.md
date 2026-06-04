---
cf: true
type: workflow-fragment
name: pdsl-write-confirm-gate
description: Shared write-confirm gate shell for cf-pdsl write-capable modes.
version: 0.1
purpose: Pause a write-capable cf-pdsl mode at an explicit confirmation boundary before dispatch.
---

# PDSL Write Confirm Gate

```pdsl
UNIT SharedPdslWriteConfirmGate

PURPOSE:
  Pause a write-capable cf-pdsl mode at an explicit confirmation boundary
  before dispatch.

STATE:
  - SET PDSL_MODE: new | transform | review
    scope: inherited_from_parent

WHEN:
  - REQUIRE PDSL_MODE == PDSL_WRITE_CONFIRM_MODE

DO:
  - REQUIRE PDSL_WRITE_CONFIRM_PRECONDITIONS are satisfied
  - EMIT write_summary(target_paths, source_paths)
  - EMIT_MENU SharedPdslWriteConfirmMenu
  - WAIT user.reply
  - STOP_TURN

RULES:
  - ALWAYS keep mode-specific missing-input recovery local to the caller
  - ALWAYS keep the dispatched input contract binding local to the caller
```
