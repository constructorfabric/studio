# Write Skills Author Dispatch

```pdsl
UNIT WriteSkillsAuthorGitSetup
PURPOSE: Resolve git write policy before author dispatch.
DO:
  RUN GitWriteDispatchPolicyResolve
  CONTINUE WriteSkillsAuthorDispatch
```

```pdsl
UNIT WriteSkillsAuthorDispatch
PURPOSE: Run SubAgentDispatch, dispatch cf-pdsl-author, and capture the returned paths.
DO:
  RUN SubAgentDispatch for the selected cf-pdsl-author dispatch group
  DISPATCH cf-pdsl-author from {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-author.md with BRAINSTORM_DECISIONS, git_commit_mode=GIT_COMMIT_MODE, contributing_guide=CONTRIBUTING_GUIDE, git_constraint=GIT_CONSTRAINT, commit_footer_contract=COMMIT_FOOTER_CONTRACT, and any WriteSkillsExploreGate-resolved resource_context as read-only context (absolute path or reference, never inline prompt text)
  SET PATHS_WRITTEN = paths_written returned by the author dispatch WHEN the author dispatch returned one or more paths in paths_written
  CONTINUE WriteSkillsAuthorStateSetup
```

```pdsl
UNIT WriteSkillsAuthorStateSetup
PURPOSE: Normalize author-dispatch state and route to validation or a no-output stop.
DO:
  SET REVIEW_TARGET_PATHS = PATHS_WRITTEN WHEN PATHS_WRITTEN != unset
  SET REVIEW_TARGET_SLICES = full-file slices for REVIEW_TARGET_PATHS WHEN REVIEW_TARGET_PATHS != unset AND REVIEW_TARGET_SLICES == unset
  SET SKILL_FILE_WRITTEN = true WHEN PATHS_WRITTEN != unset
  CONTINUE WriteSkillsValidate WHEN SKILL_FILE_WRITTEN == true
  WHEN SKILL_FILE_WRITTEN != true:
    LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md WHEN NextActionsOffer is not yet loaded
    EMIT "The author sub-agent produced no output."
    EMIT_MENU WriteSkillsNoOutputMenu
    WAIT user.reply
    STOP_TURN
MENU WriteSkillsNoOutputMenu
TITLE: The author agent produced no output — how would you like to proceed?
OPTIONS:
  1 retry — retry with a clarified or narrowed scope -> CONTINUE WriteSkillsAuthorDispatch
  2 brainstorm — refine the task with cf-brainstorm before retrying -> RUN NextActionsOffer with cf-brainstorm marked (suggested)
  3 stop — return to free mode -> RUN NextActionsOffer
```
