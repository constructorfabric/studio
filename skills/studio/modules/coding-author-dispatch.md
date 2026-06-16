# Coding Author Dispatch

```pdsl
UNIT CodingAuthorGitSetup
PURPOSE: Resolve git write policy before author dispatch.
DO:
  RUN GitWriteDispatchPolicyResolve
  CONTINUE CodingAuthorDispatch
```

```pdsl
UNIT CodingAuthorDispatch
PURPOSE: Select the coding author, dispatch it, and route written code into validation.
STATE:
  SET SELECTED_CODING_AGENT: cf-codegen | cf-generate-coder-smart | cf-generate-coder-casual | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  SET SELECTED_CODING_AGENT by this priority order (first match wins): (1) cf-codegen for fully specified tasks implementable in an isolated context with no clarification; else (2) cf-generate-coder-smart for changes involving behavior, tests, refactors, API boundaries, or any security/concurrency/data-model implication; else (3) cf-generate-coder-casual for small code-only tasks touching at most two source/test files with no security/concurrency/data-model risk; else cf-generate-coder-smart as the default
  RUN SubAgentDispatch for SELECTED_CODING_AGENT dispatch group
  DISPATCH SELECTED_CODING_AGENT with git_commit_mode=GIT_COMMIT_MODE, contributing_guide=CONTRIBUTING_GUIDE, git_constraint=GIT_CONSTRAINT, commit_footer_contract=COMMIT_FOOTER_CONTRACT, and any CodingExploreGate-resolved resource_context as read-only context (absolute path or reference, never inline prompt text)
  CONTINUE CodingValidate WHEN code has been written or edited
RULES:
  NEVER let resource_context gate a coder verdict
```
