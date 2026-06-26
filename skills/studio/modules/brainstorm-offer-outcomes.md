# Brainstorm Offer Outcomes

```pdsl
UNIT BrainstormOfferInvalid
PURPOSE: Reject an invalid brainstorm-offer reply and re-show the offer.
DO:
  EMIT one-line error naming the unknown or duplicate modifier token
  CONTINUE BrainstormOffer
```

```pdsl
UNIT BrainstormOfferCancelled
PURPOSE: Return a cancelled brainstorm result when the user declines the panel.
DO:
  EMIT "Brainstorm panel declined. No panel was started."
  RETURN { "type": "BRAINSTORM_RESULT", "status": "cancelled", "decisions_count": 0, "open_questions_count": 0, "next_route": null }
  STOP_TURN
```

```pdsl
UNIT BrainstormOfferSaveRejected
PURPOSE: Reject `save` when no writable destination is available, then re-show the offer.
DO:
  EMIT "The `save` option needs a writable destination; reply `yes` to continue without saving, or retry in a writable context."
  CONTINUE BrainstormOffer
```

```pdsl
UNIT BrainstormOfferAccepted
PURPOSE: Apply accepted brainstorm modifiers, then continue to panel setup.
DO:
  RUN parse :N modifier and mode= modifier from the accepted reply modifiers
  SET BRAINSTORM_MAX_ROUNDS = N WHEN :N modifier is present in accepted reply
  SET PANEL_MODE = mode WHEN mode= modifier is present in accepted reply
  LOAD {cf-studio-path}/.core/skills/studio/modules/brainstorm-panel.md
  RUN BrainstormExecutionContextPrep
  CONTINUE BrainstormPanel
```
