# Simple Mode Rules

```pdsl
UNIT SimpleModeRulesActive
PURPOSE: Apply simple-mode interaction rules while preserving every workflow's hard gates.
WHEN:
  REQUIRE SIMPLE_MODE == simple
RULES:
  ALWAYS before emitting any menu or user-choice prompt, explain the current workflow/unit/menu, what is happening, why the input is needed, what each option does next, and which option is suggested when the current context clearly favors one.
  ALWAYS choose automatically only when the option is non-destructive, reversible, low-impact, unambiguous, and the agent has high confidence that it matches the user's stated goal.
  ALWAYS report any automatic choice briefly, including why it was eligible.
  NEVER auto-select destructive actions, file writes, git state changes, commits, pushes, history rewrites, sub-agent dispatch approvals, external or network actions, irreversible operations, ambiguous choices, or user-preference decisions.
  NEVER override hard gates, STOP_TURN boundaries, approval gates, validation gates, review-fix approval gates, plan approval, GitCommitModeGate, or SubAgentDispatch.
```
