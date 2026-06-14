# Studio Shutdown

```pdsl
UNIT StudioShutdown
PURPOSE: Turn the studio off only after explicit user confirmation, then forget all loaded `content` and `rules` for the session.
WHEN:
  REQUIRE the user intent can be interpreted as a request to turn off, disable, or shut down the studio
DO:
  EMIT_MENU StudioShutdownConfirm
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS require explicit user confirmation via the menu before turning the studio off
  ALWAYS give StudioShutdown precedence only when shutdown is the unambiguous intent; otherwise resolve the task intent first and confirm the shutdown separately
  ALWAYS set CFS_INIT = false and forget all `content` and all `rules` on confirmation
  ALWAYS make the user aware that confirming forgets all loaded `content` and `rules`
  NEVER turn the studio off or forget `content`/`rules` without confirmation
MENU StudioShutdownConfirm
TITLE: Confirm: turning the studio off will FORGET all loaded `content` and `rules` for this session.
OPTIONS:
  1 confirm -> SET CFS_INIT = false; forget/unload all `content` and all `rules` from the session
  2 cancel -> STOP_TURN
  INVALID -> EMIT_MENU StudioShutdownConfirm
```
