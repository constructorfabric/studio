# Brainstorm Offer

```pdsl
UNIT BrainstormTopicCapture
PURPOSE: Emit the topic prompt and stop the turn; routing on resume is handled by BrainstormTopicCaptureResume.
STATE:
  SET BRAINSTORM_TOPIC_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
DO:
  SET BRAINSTORM_TOPIC_CAPTURE_STATE = resume WHEN BRAINSTORM_TOPIC_CAPTURE_STATE == unset
  EMIT "What should we brainstorm? Describe the topic, decision, or design question — e.g. 'auth strategy for the mobile app' or 'whether to use event sourcing'. A phrase or sentence is enough. Reply with your topic, or `cancel` to stop."
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS capture a concrete topic before offering a brainstorm panel when the workflow was activated without explicit topic text
  ALWAYS stop the turn after emitting the prompt; routing on the reply happens in BrainstormTopicCaptureResume

```

```pdsl
UNIT BrainstormTopicCaptureResume
PURPOSE: Route the resumed topic reply from BrainstormTopicCapture.
STATE:
  SET BRAINSTORM_TOPIC_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE BRAINSTORM_TOPIC_CAPTURE_STATE == resume
DO:
  RUN parse the reply into topic_status = accepted | cancelled | invalid and topic_text = the user's reply trimmed
  SET BRAINSTORM_TOPIC_CAPTURE_STATE = unset
  CONTINUE BrainstormTopicCaptureInvalid WHEN topic_status == invalid
  CONTINUE BrainstormTopicCaptureCancelled WHEN topic_status == cancelled
  SET ORIGINAL_INTENT = topic_text
  CONTINUE BrainstormOffer
```

```pdsl
UNIT BrainstormTopicCaptureInvalid
PURPOSE: Reject an empty brainstorm topic and re-prompt.
DO:
  EMIT "What should we brainstorm? Describe the topic, decision, or design question — e.g. 'auth strategy for the mobile app' or 'whether to use event sourcing'. A phrase or sentence is enough. Reply with your topic, or `cancel` to stop."
  CONTINUE BrainstormTopicCapture
```

```pdsl
UNIT BrainstormTopicCaptureCancelled
PURPOSE: Return a cancelled brainstorm result when the user declines to provide a topic.
DO:
  EMIT "Brainstorm cancelled before panel setup."
  RETURN { "type": "BRAINSTORM_RESULT", "status": "cancelled", "decisions_count": 0, "open_questions_count": 0, "next_route": null }
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
  ALWAYS present only yes / no / save in the primary offer; present round-cap and mode modifiers only in a follow-up turn after the user chooses yes or save
  NEVER surface the save option when writes are not allowed in the current context; pre-check write availability before rendering the offer
NOTES:
  BrainstormOfferText: "Want a brainstorm panel? I'll assemble a 3-6 expert panel for cross-discipline pushback when the design space is open, run one topic per round, and walk the resulting questions one by one. Reply `yes` (recommended when the design space is open or you want pushback), `no` (skip straight ahead), or `save` (run the panel and persist transcript + design under {cf-studio-path}/.cache/brainstorm/{slug}-{ISO}/ — only when file writes are allowed). Optional modifiers: `:N` custom round cap e.g. yes:15 (default 10); `mode=inline` (default; run facilitator and panel contracts inline without sub-agents); `mode=single-agent` (one cf-brainstorm-panel native dispatch per round); `mode=fan-out` (each expert a separate parallel cf-brainstorm-expert sub-agent). Examples: yes, yes:15, yes mode=single-agent, yes mode=fan-out, save:20 mode=fan-out"
```
