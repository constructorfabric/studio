# Next Actions Offer

```pdsl
UNIT NextActionsOffer
PURPOSE: After completing a task or operation, always offer next actions synthesized from the current context and the available cf-* skills.
STATE:
  SET NEXT_ACTION_PINNED_SKILL: cf-skill-name | unset (default unset, scope workflow_run)
  SET NEXT_ACTION_PAYLOAD: object | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE a task or operation has just completed and control is about to return to the user
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md WHEN WorkflowResolution is not yet loaded
  RUN WorkflowResolution to resolve the available cf-* skills
  RUN synthesis of 3 to 5 next actions from the current context and the available cf-* skills
  RUN include NEXT_ACTION_PINNED_SKILL as the exactly-one suggested action and attach NEXT_ACTION_PAYLOAD to that menu choice WHEN NEXT_ACTION_PINNED_SKILL != unset
  EMIT_MENU NextActionsMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer next actions when a task or operation completes and control returns to the user
  ALWAYS load workflow-resolution before resolving available cf-* skills
  ALWAYS synthesize 3 to 5 next actions from the current context and the available cf-* skills, never a fixed or guessed list
  ALWAYS include `cf-explain` as a candidate next action when the current context contains produced artifacts, decisions, findings, plans, or completed changes that the user may reasonably want explained
  ALWAYS prefer `cf-explain` as the suggested final-step handoff when the most useful next action is to explain what was done, what changed, or how to read the produced result
  NEVER include `cf-explain` as a candidate next action when produced_artifacts are of type phase-plan, phase-dod, or other internal planning artifacts; in those cases always surface the first executable skill from the phase sequence as the suggested action instead
  ALWAYS explain why each offered action is relevant to the current context and mark exactly one as suggested
  ALWAYS when NEXT_ACTION_PINNED_SKILL is set, include that skill as an offered action, mark it as the exactly-one suggested action, and preserve NEXT_ACTION_PAYLOAD as read-only handoff context for the selected workflow
  ALWAYS include an explicit `back` option in the menu when a concrete previous workflow-owned decision point can be resolved; omit `back` and use `done` as the sole exit when no such point exists
  ALWAYS let the user pick an offered action or decline
  NEVER offer `cf-explain` as a next action when the active workflow is already `cf-explain`
  NEVER offer next actions when the operation returns control to a calling skill or workflow rather than the user (for example a skill invoked in return-context mode)

When `back` is included, it occupies position N+1 and `done` occupies N+2. When `back` is omitted (no concrete prior decision point), `done` is the only exit and occupies position N+1. When cf-explain is included, its why should mention explaining what was done, what changed, or how to read the resulting artifacts.

MENU NextActionsMenu
TITLE: Next actions for this context — pick a number or reply done. (one action is marked suggested)
OPTIONS:
  1..N actions -> the menu enumerates 3 to 5 synthesized next actions, each on its own line as `N <action> — <why>`, with exactly one tagged (suggested); the agent synthesizes these from current context and available cf-* skills
  N+1 back -> CONTINUE [resolved-destination-unit] WHEN a concrete previous workflow-owned decision point can be resolved; ALWAYS resolve and name the destination before emitting this option (e.g. "back — returns to [unit name or step description]"); STOP_TURN WHEN no concrete previous decision point can be resolved
  N+2 done -> STOP_TURN
  INVALID -> EMIT_MENU NextActionsMenu
```
