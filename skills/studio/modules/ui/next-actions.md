# Next Actions Offer

```pdsl
UNIT NextActionsOffer
PURPOSE: After completing a task or operation, always offer next actions synthesized from the current context and the available cf-* skills.
WHEN:
  REQUIRE a task or operation has just completed and control is about to return to the user
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md WHEN WorkflowResolution is not yet loaded
  RUN WorkflowResolution to resolve the available cf-* skills
  RUN synthesis of 3 to 5 next actions from the current context and the available cf-* skills
  EMIT_MENU NextActionsMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer next actions when a task or operation completes and control returns to the user
  ALWAYS load workflow-resolution before resolving available cf-* skills
  ALWAYS synthesize 3 to 5 next actions from the current context and the available cf-* skills, never a fixed or guessed list
  ALWAYS include `cf-explain` as a candidate next action when the current context contains produced artifacts, decisions, findings, plans, or completed changes that the user may reasonably want explained
  ALWAYS prefer `cf-explain` as the suggested final-step handoff when the most useful next action is to explain what was done, what changed, or how to read the produced result
  ALWAYS explain why each offered action is relevant to the current context and mark exactly one as suggested
  ALWAYS include an explicit `back` option in the menu
  ALWAYS let the user pick an offered action or decline
  NEVER offer `cf-explain` as a next action when the active workflow is already `cf-explain`
  NEVER offer next actions when the operation returns control to a calling skill or workflow rather than the user (for example a skill invoked in return-context mode)
MENU NextActionsMenu
TITLE: Next actions for this context — pick a number or reply done. (one action is marked suggested)
OPTIONS:
  1 action -> run the chosen synthesized next action; the menu lists each of the 3 to 5 synthesized actions as its own number with its why, and exactly one is tagged (suggested)
  2 back -> STOP_TURN and return to the nearest previous workflow-owned decision point when one exists, otherwise STOP_TURN as a safe terminal return
  3 done -> STOP_TURN
  INVALID -> EMIT_MENU NextActionsMenu
NOTES:
  The rendered menu enumerates every synthesized action (3 to 5) on its own line as `N <action> — <why>`, tags exactly one `(suggested)`, and appends `back` plus a final `done` option; when `cf-explain` is included, its why should mention explaining what was done, what changed, or how to read the resulting artifacts. Option `1 action` above is the representative template for those numbered actions.
```
