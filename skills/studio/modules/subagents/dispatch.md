# Sub-Agent Dispatch

```pdsl
UNIT SubAgentSelectionRegistry
PURPOSE: Give every cf-* workflow a shared, cost-aware view of available cf-* sub-agents.
WHEN:
  REQUIRE a workflow must choose a cf-* sub-agent for planning, exploration, authoring, coding, validation, review, migration, phase execution, or storytelling
DO:
  LOAD the available sub-agent registry from {cf-studio-path}/.core/skills/studio/agents.toml
  RUN build a selection table with id, description, mode, isolation, role, target, model tier, reasoning_effort, context_window, and prompt_file when present
  RUN filter candidate agents by role, target, mode, workflow-specific required methodology, reasoning_effort, and context_window
  RUN choose the cheapest capable candidate first, preferring low reasoning_effort for resolved plans/contracts and escalating reasoning_effort or context_window only for task risk, ambiguity, scope, prompt semantics, security/concurrency/data concerns, strict methodology coverage, or context-window need
RULES:
  ALWAYS treat agents.toml as the canonical registry of available cf-* sub-agents
  ALWAYS prefer native sub-agent dispatch for coding, authoring, scanning, validation, review, planning, exploration, phase work, and migration unless the user explicitly requests inline/no sub-agents or selects inline fallback
  ALWAYS use workflow-specific required agents when correctness depends on a named methodology or contract
  ALWAYS expose the selected sub-agent or dispatch group to SubAgentDispatch before launch
  NEVER invent sub-agent names outside the loaded registry
```

```pdsl
UNIT SubAgentDispatch
PURPOSE: Synthesize and dispatch cf-* sub-agents from `rules` plus a contract while gating every dispatch group on approval and providing inline fallback.
STATE:
  SET SUB_AGENT_DISPATCH_MODE: unset | approve-session | inline-session (default unset, scope session)
  SET SUB_AGENT_GROUP_DECISION: unset | approve-once | inline-once | stop (default unset, scope dispatch_group)
  SET SUB_AGENT_RETRY_COUNT: integer 0..2 (default 0, scope dispatch_group)
WHEN:
  REQUIRE one or more cf-* sub-agents must be launched as an immediate dispatch group
DO:
  RUN SubAgentSelectionRegistry WHEN the workflow has not already selected a dispatch group
  LOAD each sub-agent contract from the selected registry entry's prompt_file when present, else from {cf-studio-path}/.core/skills/studio/agents/{sub-agent-name}.md
  EMIT_MENU SubAgentApprovalRequest WHEN SUB_AGENT_DISPATCH_MODE == unset AND SUB_AGENT_GROUP_DECISION == unset
  WAIT user.reply WHEN SUB_AGENT_DISPATCH_MODE == unset AND SUB_AGENT_GROUP_DECISION == unset
  STOP_TURN WHEN SUB_AGENT_DISPATCH_MODE == unset AND SUB_AGENT_GROUP_DECISION == unset
  REQUIRE SUB_AGENT_GROUP_DECISION != stop
  RUN synthesis of each initial prompt from the controller-selected `rules` plus that sub-agent contract
  DISPATCH the dispatch group natively WHEN SUB_AGENT_DISPATCH_MODE == approve-session OR SUB_AGENT_GROUP_DECISION == approve-once
  RUN each contract inline WHEN SUB_AGENT_DISPATCH_MODE == inline-session OR SUB_AGENT_GROUP_DECISION == inline-once
RULES:
  ALWAYS synthesize the initial prompt from `rules` plus the sub-agent contract, with the controller deciding which `rules` the sub-agent needs and which it does not
  ALWAYS pass any needed `content` to the sub-agent as an absolute path or web reference/link, never inline
  ALWAYS allow the sub-agent to load any `content` it needs
  ALWAYS ask before every dispatch group unless SUB_AGENT_DISPATCH_MODE is already approve-session or inline-session
  ALWAYS let the user choose native once, native for session, inline once, inline for session, or stop
  ALWAYS treat explicit user language such as "no sub-agents", "without subagents", or "без саб агентов" as inline-once unless the user asks to save it for the session
  ALWAYS reset SUB_AGENT_DISPATCH_MODE to unset when the user asks to revoke or change the saved dispatch preference
  ALWAYS prefer native dispatch over inline fallback when the user has not explicitly requested inline/no sub-agents
  NEVER allow the sub-agent to load any instructions (`rules`)
  NEVER dispatch a sub-agent silently; launching native work without this gate resolving to approve-once or approve-session is a protocol violation
ON_ERROR:
  EMIT_MENU SubAgentApprovalRequest WHEN SUB_AGENT_DISPATCH_MODE == unset AND SUB_AGENT_GROUP_DECISION == unset
  EMIT_MENU SubAgentFallbackRequest WHEN native dispatch fails AND SUB_AGENT_RETRY_COUNT < 2
  EMIT_MENU SubAgentFallbackLimitRequest WHEN native dispatch fails AND SUB_AGENT_RETRY_COUNT >= 2
MENU SubAgentApprovalRequest
TITLE: Approve this cf-* sub-agent dispatch group? Native sub-agents are preferred for this work; inline keeps execution in this chat. You can save either choice for the session.
OPTIONS:
  1 approve-once -> SET SUB_AGENT_GROUP_DECISION = approve-once; CONTINUE dispatch
  2 approve-session -> SET SUB_AGENT_DISPATCH_MODE = approve-session; CONTINUE dispatch
  3 inline-once -> SET SUB_AGENT_GROUP_DECISION = inline-once; RUN each contract inline for this dispatch group
  4 inline-session -> SET SUB_AGENT_DISPATCH_MODE = inline-session; RUN each contract inline for this and later dispatch groups
  5 stop -> SET SUB_AGENT_GROUP_DECISION = stop; STOP_TURN
  INVALID -> EMIT_MENU SubAgentApprovalRequest
MENU SubAgentFallbackRequest
TITLE: The sub-agent could not run natively — how should I proceed? (inline is suggested)
OPTIONS:
  1 inline -> SET SUB_AGENT_GROUP_DECISION = inline-once; RUN each contract inline for this dispatch group
  2 retry -> SET SUB_AGENT_RETRY_COUNT = SUB_AGENT_RETRY_COUNT + 1; DISPATCH the sub-agent natively
  3 stop -> STOP_TURN
  INVALID -> EMIT_MENU SubAgentFallbackRequest
MENU SubAgentFallbackLimitRequest
TITLE: The sub-agent still could not run natively after 2 retries — how should I proceed? (inline is suggested)
OPTIONS:
  1 inline -> SET SUB_AGENT_GROUP_DECISION = inline-once; RUN each contract inline for this dispatch group
  2 stop -> STOP_TURN
  INVALID -> EMIT_MENU SubAgentFallbackLimitRequest
```
