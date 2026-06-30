# Brainstorm Panel

```pdsl
UNIT BrainstormPanel
PURPOSE: Propose, edit, and confirm the expert panel, then gather resource context before rounds.
DO:
  RUN ResourceContextMemory
  LOAD {cf-studio-path}/.core/skills/studio/modules/brainstorm-panel-render.md
  CONTINUE BrainstormPanelInlineProposal WHEN PANEL_MODE == inline
  CONTINUE BrainstormPanelDispatchProposal WHEN PANEL_MODE != inline
RULES:
  ALWAYS refuse a compound reply with a one-line clarifier asking for a single edit form
  ALWAYS re-render the panel and seed topic after each edit until the user replies start
  ALWAYS keep min 3 and max 6 personas
  ALWAYS pass resource_context to every later panel/expert execution, whether inline or native
  ALWAYS SET PENDING_CLARIFICATION = unset and SET clarify_count = 0 before transitioning to BrainstormRounds, to prevent stale clarify-state from a prior round contaminating the new one
```

```pdsl
UNIT BrainstormPanelInlineProposal
PURPOSE: Build the panel proposal inline, then render it.
DO:
  RUN the cf-brainstorm-facilitator contract inline to propose a 3-6 persona panel plus a seed topic for round 1
  CONTINUE BrainstormPanelRender
```

```pdsl
UNIT BrainstormPanelDispatchProposal
PURPOSE: Dispatch the facilitator natively, receive the proposal, then render it.
DO:
  RUN SubAgentDispatch for the cf-brainstorm-facilitator dispatch group
  DISPATCH cf-brainstorm-facilitator to propose a 3-6 persona panel plus a seed topic for round 1
  RUN RECEIVE the proposed panel and seed topic
  CONTINUE BrainstormPanelRender
```
