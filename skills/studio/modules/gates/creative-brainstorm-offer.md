# Creative Brainstorm Offer

```pdsl
UNIT CreativeIntentBrainstormOffer
PURPOSE: Always offer cf-brainstorm before any creative task, and respect the user's decline.
WHEN:
  REQUIRE the prompt contains a creative intent (brainstorm, ideate, explore options, explore or shape a design, discover requirements, map options, compare decision tradeoffs, or design a new artifact or feature)
DO:
  EMIT_MENU CreativeBrainstormOffer
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer to Invoke cf-brainstorm before starting any creative task
  ALWAYS let the user decline the cf-brainstorm offer
  ALWAYS evaluate this offer after IntentRouting has routed, and before PlanFirstGate when a single request is both creative and substantive
  NEVER load or invoke cf-brainstorm when the user declines; continue with the requested task instead
MENU CreativeBrainstormOffer
TITLE: This looks like a creative task — run a cf-brainstorm panel first? (recommended)
OPTIONS:
  1 brainstorm -> INVOKE skill `cf-brainstorm`
  2 skip -> NEVER load cf-brainstorm; CONTINUE the requested task without it
  INVALID -> EMIT_MENU CreativeBrainstormOffer
```
