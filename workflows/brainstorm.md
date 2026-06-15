---
cf: true
type: workflow
name: cf-brainstorm
description: "REQUIRED before any creative task. Invoke for requests to brainstorm, ideate, explore options, explore design, discover requirements, map options, or compare decision tradeoffs."
version: 0.1
purpose: Run an expert panel that explores a topic over rounds, walks questions one at a time, consolidates decisions, and routes to a next step.
---

# cf-brainstorm

This skill assembles a 3-6 expert panel relevant to the user's request and runs topic and challenge rounds. Each round reviews one topic or re-examines one round's decisions in a challenge, then the questions are walked one by one — explaining why each matters, recording the user's reaction, and only then offering next-topic / challenge / wrap choices. It consolidates decisions and open questions and routes to a context-synthesized next step (such as generate, plan, or analyze) or keeps results session-only. Inline panel execution is the default; native sub-agent dispatch remains available by explicit mode.

```pdsl
UNIT BrainstormBootstrap
PURPOSE: Load the local rules needed before any brainstorm work.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/skill-invocation-art.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/pdsl-execution-card.md
  RUN SkillInvocationArt
  LOAD and REMEMBER rules from {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/studio-instructions-memory.md
  RUN StudioInstructionsMemoryGate
  SET ORIGINAL_INTENT = the user's triggering brainstorm request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/command-resolution.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/template-vars.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  RUN CommandResolution to resolve {cfs_cmd}
  SET CURRENT_WORKFLOW = cf-brainstorm, SET COMPANION_CONTINUE = BrainstormOffer and LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md and CONTINUE CompanionSkillOffer WHEN ORIGINAL_INTENT != unset
  CONTINUE BrainstormOffer WHEN ORIGINAL_INTENT == unset
RULES:
  ALWAYS run StudioInstructionsMemoryGate before brainstorm routing, panel setup, or rounds
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, writes, or delegation
  ALWAYS load workflow-resolution before BrainstormWrap can synthesize routed next steps
  ALWAYS load template-vars before resolving brainstorm cache/checkpoint paths or unknown template variables
  ALWAYS load context-memory before storing or passing resource_context to panel/expert execution
  ALWAYS load sub-agent dispatch before BrainstormPanel or BrainstormRounds may dispatch a panel agent in `single-agent` or `fan-out` mode
  ALWAYS capture ORIGINAL_INTENT before offering the brainstorm panel, and offer companion cf-* workflows first when the request spans domains
  NEVER require cf or CFS_INIT before brainstorm; this workflow owns its prerequisite loads
```

```pdsl
UNIT BrainstormOffer
PURPOSE: Offer a brainstorm panel and parse the user's reply into a verb plus modifiers.
STATE:
  SET BRAINSTORM_MAX_ROUNDS: int (default 10, scope session)
  SET PANEL_MODE: inline | single-agent | fan-out (default inline, scope session)
DO:
  EMIT a brief offer: "Want a brainstorm panel? I'll assemble a 3-6 expert panel for cross-discipline pushback when the design space is open, run one topic per round, and walk the resulting questions one by one."
  EMIT reply grammar: `yes` (recommended when the design space is open or you want pushback), `no` (skip straight ahead), `save` (run the panel and persist transcript + design under {cf-studio-path}/.cache/brainstorm/{slug}-{ISO}/ — only when file writes are allowed)
  EMIT modifiers (append whitespace-separated): `:N` custom round cap e.g. yes:15 (default 10); `mode=inline` (default; run facilitator and panel contracts inline without sub-agents); `mode=single-agent` (one cf-brainstorm-panel native dispatch per round); `mode=fan-out` (each expert a separate parallel cf-brainstorm-expert sub-agent, needs native parallelism). Examples: yes, yes:15, yes mode=single-agent, yes mode=fan-out, save:20 mode=fan-out
  WAIT user.reply
  RUN parse: tokenize reply -> base_verb = first token, modifiers = remaining tokens
  RUN on unknown or duplicate modifier: EMIT one-line error naming the token, re-EMIT the offer, WAIT user.reply, STOP_TURN
  RUN on `no`: RETURN { "type": "BRAINSTORM_RESULT", "status": "cancelled", "decisions_count": 0, "open_questions_count": 0, "next_route": null }, STOP_TURN
  RUN on `yes` / `save`: apply `:N` -> SET BRAINSTORM_MAX_ROUNDS = N; apply `mode=inline|single-agent|fan-out` -> SET PANEL_MODE; on `save` REQUIRE writes allowed else reject; then CONTINUE BrainstormPanel
RULES:
  ALWAYS reject an unknown or duplicate modifier with a one-line error naming the token, then re-emit the offer
  ALWAYS default to `mode=inline` when the user replies `yes` or `save` without a mode modifier
  NEVER offer or accept `save` when the destination is chat-only or no-write
  ALWAYS require a writable destination before accepting `save`
```

```pdsl
UNIT BrainstormPanel
PURPOSE: Propose, edit, and confirm the expert panel, then gather resource context before rounds.
DO:
  RUN ResourceContextMemory
  RUN the cf-brainstorm-facilitator contract inline to propose a 3-6 persona panel plus a seed topic for round 1 WHEN PANEL_MODE == inline
  RUN SubAgentDispatch for the cf-brainstorm-facilitator dispatch group WHEN PANEL_MODE != inline
  DISPATCH cf-brainstorm-facilitator to propose a 3-6 persona panel plus a seed topic for round 1 WHEN PANEL_MODE != inline
  RUN RECEIVE the proposed panel and seed topic
  EMIT the rendered panel (E1..E6: persona, focus, why) and the seed topic
  EMIT_MENU PanelEditMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS refuse a compound reply with a one-line clarifier asking for a single edit form
  ALWAYS re-render the panel and seed topic after each edit until the user replies start
  ALWAYS keep min 3 and max 6 personas
  ALWAYS pass resource_context to every later panel/expert execution, whether inline or native
MENU PanelEditMenu
TITLE: Panel setup — reply start to begin, or edit one thing.
OPTIONS:
  1 start -> INVOKE skill `cf-explore` with intent=brainstorm and return_context=true (it returns resource_context and skips its save offer and NextActionsOffer handoff), SET resource_context, then CONTINUE BrainstormRounds
  2 seed:<topic> -> set the seed topic, re-render the panel, and EMIT_MENU PanelEditMenu
  3 drop E{N} -> REQUIRE min 3 remain, re-render the panel, and EMIT_MENU PanelEditMenu
  4 swap E{N}:<persona>(<focus>) -> replace the persona, re-render the panel, and EMIT_MENU PanelEditMenu
  5 add:<persona>(<focus>) -> REQUIRE panel size < 6, re-render the panel, and EMIT_MENU PanelEditMenu
  6 W | wrap -> CONTINUE BrainstormWrap
  INVALID -> EMIT one-line clarifier and EMIT_MENU PanelEditMenu
```

```pdsl
UNIT BrainstormRounds
PURPOSE: Drive rounds — one topic or one challenge per round — executing the panel, then walking the question queue one at a time.
STATE:
  SET round_count: int (default 0, scope session)
  SET round_kind: topic | challenge (default topic, scope session)
  SET round_dispatched: true | false (default false, scope session)
DO:
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

```pdsl
UNIT BrainstormWrap
PURPOSE: Consolidate the design, route to the next step, and always return the completion envelope.
DO:
  EMIT a consolidated design block: rounds count, panel personas, topics covered, Decisions list, Open questions list
  RUN WorkflowResolution to resolve the available cf-* skills
  RUN TemplateVarResolution before any disk checkpoint path is resolved
  RUN synthesis of 3 to 5 routed next steps from the current context (decisions, open questions) and the available cf-* skills, marking exactly one (suggested) and giving each a one-line why
  EMIT_MENU WrapMenu
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER auto-route into a next step without the wrap menu
  NEVER treat a stop-token as implicit approval
  ALWAYS preserve decisions and open questions when routing
  ALWAYS synthesize the routed next steps from the current context and the available cf-* skills, never a fixed or guessed list, and mark exactly one (suggested)
  ALWAYS synthesize each routed next step by matching the current decisions, open questions, and unresolved topics to a cf-* skill's purpose, include only skills that fit the context, mark the best-fitting one (suggested), and NEVER offer a generic skill that does not align with the current context
  ALWAYS set status="handoff" and next_route to the chosen route's cf-* skill (for example generate, plan, or analyze) when a routed next step is chosen
  ALWAYS RETURN the BRAINSTORM_RESULT envelope on every terminal wrap option; human-facing wrap text is not a substitute for it
NOTES:
  Envelope shape: { "type": "BRAINSTORM_RESULT", "status": "wrapped|handoff|checkpointed|cancelled", "decisions_count": <int>, "open_questions_count": <int>, "next_route": "<cf-* skill name (e.g. generate, plan, analyze)>|null" }
MENU WrapMenu
TITLE: Brainstorm complete — keep the results or pick a context-grounded next step (one is suggested).
OPTIONS:
  1 session -> preserve results in session only, write no files, RETURN envelope with status="wrapped", decisions_count=<count>, open_questions_count=<count>, next_route=null, STOP_TURN
  2 disk -> REQUIRE writes allowed, WRITE design + state under {cf-studio-path}/.cache/brainstorm/{session_id}/, RETURN envelope with status="checkpointed", decisions_count=<count>, open_questions_count=<count>, next_route=null, STOP_TURN
  3 reopen -> reopen a topic for another round, SET round_kind = topic, SET round_dispatched = false, and CONTINUE BrainstormRounds
  4 route -> INVOKE the chosen synthesized cf-* skill with decisions + open questions pre-filled, RETURN envelope with status="handoff", decisions_count=<count>, open_questions_count=<count>, next_route="<chosen cf-* skill>"
  INVALID -> EMIT clarifier and EMIT_MENU WrapMenu
NOTES:
  The rendered menu lists session, disk, and reopen, then enumerates every synthesized routed next step (3 to 5) on its own line as `N <route> — <why>`, and tags exactly one (suggested); option `4 route` above is the representative template for those numbered routes.
```

```pdsl
UNIT BrainstormDispatch
PURPOSE: Name the sub-agents and the cf-explore skill, and when each is used.
RULES:
  ALWAYS run cf-brainstorm-facilitator from {cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-facilitator.md inline when PANEL_MODE == inline, else dispatch it natively to propose the panel + seed topic
  ALWAYS gather resource_context after panel confirmation by INVOKE skill `cf-explore` with intent=brainstorm and return_context=true (cf-explore returns resource_context and control returns here), NEVER by dispatching the cf-explorer sub-agent directly
  ALWAYS run cf-brainstorm-panel from {cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-panel.md inline once per round when PANEL_MODE == inline
  ALWAYS dispatch cf-brainstorm-panel from {cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-panel.md once per round when PANEL_MODE == single-agent
  ALWAYS dispatch cf-brainstorm-expert from {cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-expert.md once per persona when PANEL_MODE == fan-out
  ALWAYS pass resource_context to every panel/expert execution, whether inline or native
  ALWAYS run SubAgentDispatch before every native brainstorm facilitator, panel, or expert dispatch group; inline panel mode never launches sub-agents
  ALWAYS synthesize inline execution from the same controller-side contract files used for native dispatch; inline execution does not launch sub-agents
  NEVER let a sub-agent or inline panel run reopen prompt/instruction files from disk
```
