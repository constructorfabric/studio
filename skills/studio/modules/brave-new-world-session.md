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
  - EMIT "Brave New World enabled: I will autonomously choose any non-destructive, reversible path. Say \"turn off Brave New World\" to disable it."
  - STOP_TURN
```
