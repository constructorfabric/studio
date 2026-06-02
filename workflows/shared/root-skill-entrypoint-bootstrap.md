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
  - REQUIRE {cf-studio-path}/.core/skills/studio/SKILL.md is loaded completely
     and followed FIRST.
  - REQUIRE CfSkillInit, Bootstrap, HardRules, and
     WorkflowProtocolNonSubstitution from SKILL.md have completed.
  - CONTINUE this workflow only after the root cf skill routing/entrypoint
     selects it.
RULES:
  - ALWAYS execute before any workflow-specific unit in this file.
  - NEVER treat protocol.md, routing.md, or a thin proxy skill as a
    substitute for loading and following SKILL.md.
  - ALWAYS If this workflow file is opened directly, STOP workflow phases until
    SKILL.md has been loaded completely and followed.
  - ALWAYS This gate applies to the top-level controller only; dispatched sub-agents
    consume the synthesized final prompt and supplied context slices.
```
