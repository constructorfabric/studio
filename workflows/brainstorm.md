---
cf: true
type: workflow
name: cf-brainstorm
description: "REQUIRED before any creative task. Invoke for requests to brainstorm, ideate, explore options, explore design, discover requirements, map options, or compare decision tradeoffs."
version: 0.1
purpose: Run a sub-agent expert panel that explores a topic over rounds, walks questions one at a time, consolidates decisions, and routes to a next step.
---

# cf-brainstorm

This skill assembles a 3-6 expert panel relevant to the user's request and runs topic and challenge rounds. Each round one topic is reviewed, then the questions are walked one by one — explaining why each matters, recording the user's reaction, and only then offering next-topic / challenge / wrap choices. It consolidates decisions and open questions and routes to a next step (generate, analyze, save, or session-only) — all via sub-agents.

```pdsl
UNIT BrainstormBootstrap
PURPOSE: Ensure the cf skill is loaded before any brainstorm work.
STATE:
  SET CFS_INIT: true | false (default false, scope session)
DO:
  EMIT_MENU LoadCfSkillConfirm WHEN CFS_INIT != true
RULES:
  ALWAYS verify the cf skill is loaded, CFS_INIT == true, before any brainstorm work
MENU LoadCfSkillConfirm
TITLE: The cf skill is not loaded. It is the Constructor Studio core that loads the shared rules and routes to cf-* skills, so brainstorm cannot run without it. Load it now to continue?
OPTIONS:
  1 load -> INVOKE skill `cf` and CONTINUE BrainstormBootstrap
  2 stop -> RETURN BRAINSTORM_RESULT with status="cancelled", next_route=null; STOP_TURN
  INVALID -> EMIT_MENU LoadCfSkillConfirm
```

```pdsl
UNIT BrainstormOffer
PURPOSE: Offer a brainstorm panel and parse the user's reply into a verb plus modifiers.
STATE:
  SET BRAINSTORM_MAX_ROUNDS: int (default 10, scope session)
  SET PANEL_MODE: single-agent | fan-out (default single-agent, scope session)
DO:
  EMIT a brief offer: "Want a brainstorm panel? I'll assemble a 3-6 expert panel for cross-discipline pushback when the design space is open, run one topic per round, and walk the resulting questions one by one."
  EMIT reply grammar: `yes` (recommended when the design space is open or you want pushback), `no` (skip straight ahead), `save` (run the panel and persist transcript + design under {cf-studio-path}/.cache/brainstorm/{slug}-{ISO}/ — only when file writes are allowed)
  EMIT modifiers (append whitespace-separated): `:N` custom round cap e.g. yes:15 (default 10); `mode=fan-out` (each expert a separate parallel cf-brainstorm-expert sub-agent, needs native parallelism); `mode=single-agent` (default; one cf-brainstorm-panel dispatch per round). Examples: yes, yes:15, yes mode=fan-out, save:20 mode=fan-out
  WAIT user.reply
  RUN parse: tokenize reply -> base_verb = first token, modifiers = remaining tokens
  RUN on unknown or duplicate modifier: EMIT one-line error naming the token, re-EMIT the offer, WAIT user.reply, STOP_TURN
  RUN on `no`: RETURN { "type": "BRAINSTORM_RESULT", "status": "cancelled", "decisions_count": 0, "open_questions_count": 0, "next_route": null }, STOP_TURN
  RUN on `yes` / `save`: apply `:N` -> SET BRAINSTORM_MAX_ROUNDS = N; apply `mode=fan-out|single-agent` -> SET PANEL_MODE; on `save` REQUIRE writes allowed else reject; then CONTINUE BrainstormPanel
RULES:
  ALWAYS reject an unknown or duplicate modifier with a one-line error naming the token, then re-emit the offer
  NEVER offer or accept `save` when the destination is chat-only or no-write
  ALWAYS require a writable destination before accepting `save`
```

```pdsl
UNIT BrainstormPanel
PURPOSE: Propose, edit, and confirm the expert panel, then gather resource context before rounds.
DO:
  DISPATCH cf-brainstorm-facilitator to propose a 3-6 persona panel plus a seed topic for round 1
  RUN RECEIVE the proposed panel and seed topic
  EMIT the rendered panel (E1..E6: persona, focus, why) and the seed topic
  EMIT_MENU PanelEditMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS refuse a compound reply with a one-line clarifier asking for a single edit form
  ALWAYS re-render the panel and seed topic after each edit until the user replies start
  ALWAYS keep min 3 and max 6 personas
  ALWAYS pass resource_context to every later panel/expert dispatch
MENU PanelEditMenu
TITLE: Panel setup — reply start to begin, or edit one thing.
OPTIONS:
  1 start -> INVOKE skill `cf-explore` with intent=brainstorm and return_context=true (it returns resource_context and skips its save offer and the global next-actions offer), SET resource_context, then CONTINUE BrainstormRounds
  2 seed:<topic> -> set the seed topic, re-render the panel, and EMIT_MENU PanelEditMenu
  3 drop E{N} -> REQUIRE min 3 remain, re-render the panel, and EMIT_MENU PanelEditMenu
  4 swap E{N}:<persona>(<focus>) -> replace the persona, re-render the panel, and EMIT_MENU PanelEditMenu
  5 add:<persona>(<focus>) -> REQUIRE panel size < 6, re-render the panel, and EMIT_MENU PanelEditMenu
  6 W | wrap -> CONTINUE BrainstormWrap
  INVALID -> EMIT one-line clarifier and EMIT_MENU PanelEditMenu
```

```pdsl
UNIT BrainstormRounds
PURPOSE: Drive rounds — one topic each — dispatching the panel, then walking the question queue one at a time.
STATE:
  SET round_count: int (default 0, scope session)
DO:
  RUN when the current topic has no dispatched round yet: DISPATCH cf-brainstorm-panel WHEN PANEL_MODE == single-agent, or one cf-brainstorm-expert per persona in parallel WHEN PANEL_MODE == fan-out, with the current topic and resource_context; collect the question_queue; SET round_count = round_count + 1
  RUN when round_count reaches BRAINSTORM_MAX_ROUNDS: EMIT_MENU WrapMenu; WAIT user.reply; STOP_TURN
  RUN when the question_queue has an unanswered question: EMIT the next question (text, why it matters, proposed default, decision key); EMIT_MENU QuestionMenu; WAIT user.reply; STOP_TURN
  RUN otherwise (queue fully resolved): EMIT_MENU PostRoundMenu; WAIT user.reply; STOP_TURN
RULES:
  ALWAYS increment round_count after a round's questions are collected and check it against BRAINSTORM_MAX_ROUNDS
  ALWAYS run exactly one topic per round and NEVER auto-advance topics — the user drives topic order
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
  1 next:<topic> -> pick one of the panel's proposed next topics, set it as the current topic, and CONTINUE BrainstormRounds to start the next round
  2 C | challenge -> re-examine this round's decisions in a challenge-round and CONTINUE BrainstormRounds
  3 W | wrap -> CONTINUE BrainstormWrap
  INVALID -> EMIT clarifier and EMIT_MENU PostRoundMenu
```

```pdsl
UNIT BrainstormWrap
PURPOSE: Consolidate the design, route to the next step, and always return the completion envelope.
DO:
  EMIT a consolidated design block: rounds count, panel personas, topics covered, Decisions list, Open questions list
  EMIT_MENU WrapMenu
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER auto-route into generate or analyze without the wrap menu
  NEVER treat a stop-token as implicit approval
  ALWAYS preserve decisions and open questions when routing
  ALWAYS RETURN the BRAINSTORM_RESULT envelope on every terminal wrap option; human-facing wrap text is not a substitute for it
NOTES:
  Envelope shape: { "type": "BRAINSTORM_RESULT", "status": "wrapped|handoff|checkpointed|cancelled", "decisions_count": <int>, "open_questions_count": <int>, "next_route": "<generate|plan|analyze|null>" }
MENU WrapMenu
TITLE: Brainstorm complete — choose next step.
OPTIONS:
  1 session -> preserve results in session only, write no files, RETURN envelope with status="wrapped", next_route=null, STOP_TURN
  2 disk -> REQUIRE writes allowed, WRITE design + state under {cf-studio-path}/.cache/brainstorm/{session_id}/, RETURN envelope with status="checkpointed", next_route=null, STOP_TURN
  3 generate -> CONTINUE generate input collection with decisions + open questions pre-filled, RETURN envelope with status="handoff", next_route="generate"
  4 analyze -> CONTINUE review/analyze with the brainstorm results, RETURN envelope with status="handoff", next_route="analyze"
  5 reopen -> reopen a topic for another round and CONTINUE BrainstormRounds
  INVALID -> EMIT clarifier and EMIT_MENU WrapMenu
```

```pdsl
UNIT BrainstormDispatch
PURPOSE: Name the sub-agents and the cf-explore skill, and when each is used.
RULES:
  ALWAYS dispatch cf-brainstorm-facilitator from {cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-facilitator.md to propose the panel + seed topic
  ALWAYS gather resource_context after panel confirmation by INVOKE skill `cf-explore` with intent=brainstorm and return_context=true (cf-explore returns resource_context and control returns here), NEVER by dispatching the cf-explorer sub-agent directly
  ALWAYS dispatch cf-brainstorm-panel from {cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-panel.md once per round in single-agent mode
  ALWAYS dispatch cf-brainstorm-expert from {cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-expert.md once per persona in fan-out mode
  ALWAYS pass resource_context to every panel/expert dispatch
  NEVER let a sub-agent reopen prompt/instruction files from disk
```
