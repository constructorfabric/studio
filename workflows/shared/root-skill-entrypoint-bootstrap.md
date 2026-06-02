---
cf: true
type: workflow-fragment
name: root-skill-entrypoint-bootstrap
description: Shared root cf skill entrypoint bootstrap gate for workflow prompt files.
version: 0.1
purpose: Prevent direct workflow entry from bypassing the root cf skill.
---

# Root Skill Entrypoint Bootstrap

```pdsl
UNIT RootSkillEntrypointBootstrap
PURPOSE: Prevent direct workflow entry from bypassing the root cf skill.
DO:
  - REQUIRE {cf-studio-path}/.core/skills/studio/SKILL.md is loaded and followed FIRST.
  - REQUIRE {cf-studio-path}/.core/skills/studio/protocol.md is loaded.
  - REQUIRE CfSkillInit from {cf-studio-path}/.core/skills/studio/SKILL.md has completed.
  - REQUIRE Bootstrap, HardRules, and WorkflowProtocolNonSubstitution from
     {cf-studio-path}/.core/skills/studio/protocol.md have completed.
  - CONTINUE this workflow only after the root cf skill routing/entrypoint
     selects it.
RULES:
  - ALWAYS execute before any workflow-specific unit in this file.
  - NEVER treat {cf-studio-path}/.core/skills/studio/routing.md or a workflow
    file as a substitute for loading and following
    {cf-studio-path}/.core/skills/studio/SKILL.md plus
    {cf-studio-path}/.core/skills/studio/protocol.md.
  - ALWAYS if this workflow file is opened directly, STOP workflow phases until
    {cf-studio-path}/.core/skills/studio/SKILL.md and
    {cf-studio-path}/.core/skills/studio/protocol.md have been loaded and followed.
  - ALWAYS This gate applies to the top-level controller only; dispatched sub-agents
    consume the synthesized final prompt and supplied context slices.
```
