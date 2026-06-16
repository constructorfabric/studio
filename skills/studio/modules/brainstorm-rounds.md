# Brainstorm Rounds

```pdsl
UNIT BrainstormRounds
PURPOSE: Drive rounds — one topic or one challenge per round — executing the panel, then walking the question queue one at a time.
STATE:
  SET round_count: int (default 0, scope session)
  SET round_kind: topic | challenge (default topic, scope session)
  SET round_dispatched: true | false (default false, scope session)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/brainstorm-wrap.md
  RUN when round_dispatched == false: execute the cf-brainstorm-panel contract inline WHEN PANEL_MODE == inline, RUN SubAgentDispatch for the cf-brainstorm-panel dispatch group before DISPATCH cf-brainstorm-panel WHEN PANEL_MODE == single-agent, or RUN SubAgentDispatch for the cf-brainstorm-expert fan-out dispatch group before DISPATCH one cf-brainstorm-expert per persona in parallel WHEN PANEL_MODE == fan-out, passing the current topic, round_kind, this round's recorded decisions WHEN round_kind == challenge, and resource_context; collect the question_queue (challenge questions that re-examine this round's decisions WHEN round_kind == challenge); collect the panel's proposed next topics; SET round_dispatched = true; SET round_count = round_count + 1
  RUN when the question_queue has an unanswered question: EMIT the next question (text, why it matters, proposed default, decision key); EMIT_MENU QuestionMenu; WAIT user.reply; STOP_TURN
  RUN when the question_queue is fully resolved AND round_count reaches BRAINSTORM_MAX_ROUNDS: CONTINUE BrainstormWrap
  RUN otherwise (question_queue fully resolved and rounds remain): EMIT_MENU PostRoundMenu; WAIT user.reply; STOP_TURN
RULES:
  ALWAYS increment round_count when a round is executed, and check it against BRAINSTORM_MAX_ROUNDS only after that round's questions are fully resolved, so the final round's questions are never skipped
  ALWAYS run exactly one topic or one challenge per round and NEVER auto-advance topics — the user drives topic order
  ALWAYS execute the panel for a challenge round using the same PANEL_MODE as a topic round, collect a challenge question_queue from this round's decisions, and walk it one question at a time via QuestionMenu
  ALWAYS set round_dispatched = false on every path that starts a new round (next:<topic>, challenge, reopen), so the panel is executed exactly once per round, and NEVER re-execute the panel while round_dispatched == true
  ALWAYS render a relevant=false expert as "{persona}: skipped — {reason}"
  ALWAYS expose W / wrap on every menu
  NEVER let skip update decisions; ALWAYS preserve the skipped question as an open question
MENU QuestionMenu
TITLE: Reply with a number, or write a custom answer.
OPTIONS:
  1 accept-default -> record the default as the decision and CONTINUE BrainstormRounds to the next question
  2 custom -> record the user's free text as the decision and CONTINUE BrainstormRounds to the next question
  3 skip -> keep the question open/unanswered and CONTINUE BrainstormRounds to the next question
  4 keep-current -> leave the decision unchanged (challenge-rounds only) and CONTINUE BrainstormRounds to the next question
  5 W | wrap -> CONTINUE BrainstormWrap
  INVALID -> treat non-empty free text as option 2 custom; else EMIT clarifier and EMIT_MENU QuestionMenu
RULES:
  ALWAYS hide option 4 keep-current in topic-rounds and show it only in challenge-rounds; a reply of 4 in a topic-round re-renders QuestionMenu
MENU PostRoundMenu
TITLE: Round complete — advance, challenge, or wrap.
OPTIONS:
  1 next:<topic> -> pick one of the panel's proposed next topics, set it as the current topic, SET round_kind = topic, SET round_dispatched = false, and CONTINUE BrainstormRounds to start the next round
  2 C | challenge -> SET round_kind = challenge, SET round_dispatched = false, and CONTINUE BrainstormRounds to execute the panel on this round's decisions and walk the challenge questions one by one
  3 W | wrap -> CONTINUE BrainstormWrap
  INVALID -> EMIT clarifier and EMIT_MENU PostRoundMenu
```
