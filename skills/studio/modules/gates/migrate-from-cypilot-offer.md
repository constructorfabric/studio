# Migrate From Cypilot Offer

```pdsl
UNIT MigrateFromCypilotOffer
PURPOSE: Offer the migrate-from-cypilot orchestrator when the prompt intent is a cypilot migration, and respect the user's decline.
WHEN:
  REQUIRE the prompt intent is migrating from cypilot (migrate from cypilot, migrate-from-cypilot, or cleaning up residual cypilot/cpt/Cypilot/Cyber Pilot references after the deterministic migration)
DO:
  EMIT_MENU MigrateFromCypilotConfirm
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer the migrate-from-cypilot orchestrator when the prompt intent is a cypilot migration
  ALWAYS let the user decline the offer
  NEVER open or run the migrate-from-cypilot orchestrator when the user declines; continue with the requested task instead
MENU MigrateFromCypilotConfirm
TITLE: This looks like a cypilot to Constructor Studio migration — run the migrate-from-cypilot cleanup orchestrator? It checks the deterministic-migration preconditions first and gates every sub-agent step.
OPTIONS:
  1 migrate -> open and follow {cf-studio-path}/.core/skills/studio/migrate-from-cypilot.md
  2 skip -> NEVER open the orchestrator; CONTINUE the requested task without it
  INVALID -> EMIT_MENU MigrateFromCypilotConfirm
```
