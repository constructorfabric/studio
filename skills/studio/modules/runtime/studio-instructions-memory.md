# Studio Instructions Memory

```pdsl
UNIT StudioInstructionsMemoryGate
PURPOSE: Load and remember generated and project-specific Studio instruction files before workflow-specific work begins.
STATE:
  SET STUDIO_INSTRUCTIONS_MEMORY: unloaded | loaded (default unloaded, scope session)
WHEN:
  REQUIRE a workflow that includes this gate is starting
DO:
  RUN reuse remembered generated Studio instruction rules, project Studio navigation rules, and project Studio skill rules, then return control to the calling workflow WHEN STUDIO_INSTRUCTIONS_MEMORY == loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md WHEN ContextCategories is not loaded
  LOAD {cf-studio-path}/.gen/AGENTS.md as generated Studio instruction rules
  LOAD {cf-studio-path}/config/AGENTS.md as project Studio navigation rules
  LOAD {cf-studio-path}/config/SKILL.md as project Studio skill rules
  RUN verify all three Studio instruction files loaded; EMIT "Required Studio instruction files not found under {cf-studio-path}/.gen or {cf-studio-path}/config - sync or initialize Constructor Studio, then retry." and STOP_TURN WHEN any load fails
  RUN ContextCategories to classify generated Studio instruction rules, project Studio navigation rules, and project Studio skill rules as `rules`
  RUN RulesMemory to remember generated Studio instruction rules, project Studio navigation rules, and project Studio skill rules for the session
  SET STUDIO_INSTRUCTIONS_MEMORY = loaded
RULES:
  ALWAYS run this gate before workflow-specific routing, planning, validation, discovery, authoring, review, or write-capable work in workflows that include it
  ALWAYS treat `{cf-studio-path}/.gen/AGENTS.md`, `{cf-studio-path}/config/AGENTS.md`, and `{cf-studio-path}/config/SKILL.md` as `rules`, not task content
  ALWAYS load and remember these instruction files at most once per session through RulesMemory
  NEVER continue workflow-specific work when any required Studio instruction file cannot be loaded
```
