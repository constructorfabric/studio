# Brave New World Session

```pdsl
UNIT BraveNewWorldSessionInit
PURPOSE: Initialize Brave New World session state without taking a terminal turn.
DO:
  - SET BRAVE_NEW_WORLD_ENABLED = true
  - SET BRAVE_NEW_WORLD_SCOPE = non-destructive-allow-by-default
  - RUN initialize BRAVE_NEW_WORLD_DECISION_LOG as empty when it is unset
  - SET BRAVE_NEW_WORLD_LAST_STATUS = enabled
```

```pdsl
UNIT BraveNewWorldSessionEnable
PURPOSE: Initialize Brave New World session state and announce the overlay.
DO:
  - RUN BraveNewWorldSessionInit
  - EMIT "Brave New World enabled. I will choose automatically for any non-destructive option (file edits, safe defaults, tool selections). I will always stop and ask for: destructive git operations, external service calls, data deletion, and irreversible changes. Autonomous choices will be noted inline. Say 'turn off Brave New World' to disable and review what was decided. What would you like to work on? (I'll handle non-destructive choices automatically as we go.)"
  - STOP_TURN
```
