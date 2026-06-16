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
PURPOSE: Run SubAgentDispatch, dispatch cf-pdsl-author, and mark the file as written.
DO:
  RUN SubAgentDispatch for the selected cf-pdsl-author dispatch group
  DISPATCH cf-pdsl-author from {cf-studio-path}/.core/skills/studio/agents/cf-pdsl-author.md with BRAINSTORM_DECISIONS, git_commit_mode=GIT_COMMIT_MODE, contributing_guide=CONTRIBUTING_GUIDE, git_constraint=GIT_CONSTRAINT, commit_footer_contract=COMMIT_FOOTER_CONTRACT, and any WriteSkillsExploreGate-resolved resource_context as read-only context (absolute path or reference, never inline prompt text)
  SET PATHS_WRITTEN = paths_written returned by the author dispatch WHEN the author dispatch returned one or more paths in paths_written
  SET REVIEW_TARGET_PATHS = PATHS_WRITTEN WHEN PATHS_WRITTEN != unset
  SET REVIEW_TARGET_SLICES = full-file slices for REVIEW_TARGET_PATHS WHEN REVIEW_TARGET_PATHS != unset AND REVIEW_TARGET_SLICES == unset
  SET SKILL_FILE_WRITTEN = true WHEN the author dispatch returned one or more paths in paths_written
  CONTINUE WriteSkillsValidate WHEN SKILL_FILE_WRITTEN == true
  STOP_TURN and report that the author sub-agent produced no output — request clarification or retry WHEN SKILL_FILE_WRITTEN == false
```
