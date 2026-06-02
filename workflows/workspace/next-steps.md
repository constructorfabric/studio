---
cf: true
type: workflow
parent: workflows/workspace.md
description: "Invoke when the workspace workflow completes Phase 4 validation and is ready to present post-setup next steps."
---

<!-- toc -->

- [Phase 5: Next Steps](#phase-5-next-steps)

<!-- /toc -->

## Phase 5: Next Steps

```pdsl
UNIT WorkspaceNextSteps

PURPOSE:
  Present post-setup next steps after successful workspace setup.

DO:
  - EMIT_MENU NextStepsMenu
  - WAIT user.reply
  - STOP_TURN

MENU NextStepsMenu:
  TITLE: What would you like to do next? Reply with the option number or a short custom instruction.
  OPTIONS:
    1 -> Run `validate` from each participating repo — Suggested default; verifies cross-repo ID resolution end to end.
    2 -> Run `list-ids` to confirm artifacts from all sources are visible.
    3 -> Review or edit workspace/source fields before using the workspace further.
    4 -> Other — describe the next workspace action you want (e.g., a `cfs` command to run, a config field to change, or a workspace-related question).
  STOP_TOKEN:
    EMIT "Workspace setup complete. No further workspace action selected."
    STOP_TURN
  INVALID:
    EMIT "Reply with 1, 2, 3, or 4, or describe a custom next step."
    WAIT user.reply
    STOP_TURN

NOTES:
  Stop tokens (stop/enough/done) at this menu emit a one-line completion acknowledgement and no further menus.
  See workflows/shared/stop-token-policy.md.
  Suggested post-setup actions include: running validate from each repo, using list-ids to confirm
  artifact visibility, adding source fields to artifacts.toml for remote repos, and adding workspace
  setup to project onboarding documentation.
```
