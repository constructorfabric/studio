# Brainstorm Wrap

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
