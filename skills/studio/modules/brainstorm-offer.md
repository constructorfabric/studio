# Brainstorm Offer

```pdsl
UNIT BrainstormOffer
PURPOSE: Offer a brainstorm panel and parse the user's reply into a verb plus modifiers.
STATE:
  SET BRAINSTORM_MAX_ROUNDS: int (default 10, scope session)
  SET PANEL_MODE: inline | single-agent | fan-out (default inline, scope session)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/brainstorm-offer-outcomes.md
  EMIT the brainstorm offer, reply grammar, and modifier examples: "Want a brainstorm panel? I'll assemble a 3-6 expert panel for cross-discipline pushback when the design space is open, run one topic per round, and walk the resulting questions one by one. Reply `yes` (recommended when the design space is open or you want pushback), `no` (skip straight ahead), or `save` (run the panel and persist transcript + design under {cf-studio-path}/.cache/brainstorm/{slug}-{ISO}/ — only when file writes are allowed). Optional modifiers: `:N` custom round cap e.g. yes:15 (default 10); `mode=inline` (default; run facilitator and panel contracts inline without sub-agents); `mode=single-agent` (one cf-brainstorm-panel native dispatch per round); `mode=fan-out` (each expert a separate parallel cf-brainstorm-expert sub-agent, needs native parallelism). Examples: yes, yes:15, yes mode=single-agent, yes mode=fan-out, save:20 mode=fan-out"
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
```
