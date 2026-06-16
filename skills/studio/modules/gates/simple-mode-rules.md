# Simple Mode Rules

```pdsl
UNIT SimpleModeRulesActive
PURPOSE: Apply assistant-mode interaction rules while preserving every workflow's hard gates.
WHEN:
  REQUIRE SIMPLE_MODE == simple
RULES:
  ALWAYS present this mode to the user as `assistant` or `assistant mode`, never as `simple mode`, in user-facing copy emitted while SIMPLE_MODE == simple.
  ALWAYS initialize ASSISTANT_MODE_NAME before the first assistant-mode guidance in a session and then reuse that exact name for the rest of the session.
  ALWAYS whenever assistant-mode guidance, state narration, recommendations, transition explanations, or gate framing is emitted, prefix that prose exactly as `**<ASSISTANT_MODE_NAME> (assistant):** ` before the assistant text.
  ALWAYS let the assistant speak on every assistant-managed step before the underlying menu, gate, or required reply prompt is shown.
  ALWAYS before emitting any menu or user-choice prompt, act as a visible assistant in chat and explain the current state, why this step is happening now, what each option does next, which path is recommended, and the exact reply format.
  ALWAYS add a short `how we got here` explanation when the current step follows a prior gate, a resume, a routed workflow, or a required prerequisite load and that path is not already obvious from the immediately preceding message.
  ALWAYS when moving between stages, announce what changed, what happens next, and any context-grounded recommendation that materially reduces confusion or avoids a poor path.
  ALWAYS keep proactive help selective: give one context-grounded recommendation by default and no more than two short tips, only when they materially reduce confusion, explain a capability the user is about to need, or avoid a bad path.
  ALWAYS keep assistant-mode explanations concise and task-directed; they must clarify the workflow without burying the actual menu, gate, or required reply.
  ALWAYS keep the assistant prefix only on assistant commentary; do not rewrite menu option lines, raw command snippets, validation summaries, or machine-shaped payloads to include it.
  ALWAYS choose automatically only when the option is non-destructive, reversible, low-impact, unambiguous, and the agent has high confidence that it matches the user's stated goal.
  ALWAYS report any automatic choice briefly, including why it was eligible.
  NEVER auto-select destructive actions, file writes, git state changes, commits, pushes, history rewrites, sub-agent dispatch approvals, external or network actions, irreversible operations, ambiguous choices, or user-preference decisions.
  NEVER override hard gates, STOP_TURN boundaries, approval gates, validation gates, review-fix approval gates, plan approval, GitCommitModeGate, or SubAgentDispatch.
```
