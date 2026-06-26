# Brainstorm Offer

```pdsl
UNIT BrainstormTopicCapture
PURPOSE: Capture the topic to brainstorm before offering a panel when activation started without an explicit topic.
DO:
  EMIT "What topic should we brainstorm? Reply with the topic, or `cancel` to stop."
  WAIT user.reply
  RUN parse the reply into topic_status = accepted | cancelled | invalid and topic_text = the user's reply trimmed
  CONTINUE BrainstormTopicCaptureInvalid WHEN topic_status == invalid
  CONTINUE BrainstormTopicCaptureCancelled WHEN topic_status == cancelled
  SET ORIGINAL_INTENT = topic_text
  CONTINUE BrainstormOffer
RULES:
  ALWAYS capture a concrete topic before offering a brainstorm panel when the workflow was activated without explicit topic text
  ALWAYS reject empty topic replies with a one-line clarifier and re-prompt
```

```pdsl
UNIT BrainstormTopicCaptureInvalid
PURPOSE: Reject an empty brainstorm topic and re-prompt.
DO:
  EMIT "Reply with the topic to brainstorm, or `cancel` to stop."
  CONTINUE BrainstormTopicCapture
```

```pdsl
UNIT BrainstormTopicCaptureCancelled
PURPOSE: Return a cancelled brainstorm result when the user declines to provide a topic.
DO:
  EMIT "Brainstorm cancelled before panel setup."
  RETURN { "type": "BRAINSTORM_RESULT", "status": "cancelled", "decisions_count": 0, "open_questions_count": 0, "next_route": null }
  STOP_TURN
```

```pdsl
UNIT BrainstormOffer
PURPOSE: Offer a brainstorm panel and parse the user's reply into a verb plus modifiers.
STATE:
  SET BRAINSTORM_MAX_ROUNDS: int (default 10, scope session)
  SET PANEL_MODE: inline | single-agent | fan-out (default inline, scope session)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/brainstorm-offer-outcomes.md
  EMIT BrainstormOfferText
  WAIT user.reply
  RUN parse the reply into base_verb = first token, modifiers = remaining tokens, and reply_status = invalid | cancelled | save_rejected | accepted
  CONTINUE BrainstormOfferInvalid WHEN reply_status == invalid
  CONTINUE BrainstormOfferCancelled WHEN reply_status == cancelled
  CONTINUE BrainstormOfferSaveRejected WHEN reply_status == save_rejected
  CONTINUE BrainstormOfferAccepted WHEN reply_status == accepted
RULES:
  ALWAYS reject an unknown or duplicate modifier with a one-line error naming the token, then re-emit the offer
  ALWAYS default to `mode=inline` when the user replies `yes` or `save` without a mode modifier
  NEVER offer or accept `save` when the destination is chat-only or no-write
  ALWAYS require a writable destination before accepting `save`
NOTES:
  BrainstormOfferText: "Want a brainstorm panel? I'll assemble a 3-6 expert panel for cross-discipline pushback when the design space is open, run one topic per round, and walk the resulting questions one by one. Reply `yes` (recommended when the design space is open or you want pushback), `no` (skip straight ahead), or `save` (run the panel and persist transcript + design under {cf-studio-path}/.cache/brainstorm/{slug}-{ISO}/ — only when file writes are allowed). Optional modifiers: `:N` custom round cap e.g. yes:15 (default 10); `mode=inline` (default; run facilitator and panel contracts inline without sub-agents); `mode=single-agent` (one cf-brainstorm-panel native dispatch per round); `mode=fan-out` (each expert a separate parallel cf-brainstorm-expert sub-agent, needs native parallelism). Examples: yes, yes:15, yes mode=single-agent, yes mode=fan-out, save:20 mode=fan-out"
```
