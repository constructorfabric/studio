---
cf: true
type: workflow
name: cf-studio
description: "Thin alias for the cf skill. /cf-studio behaves identically to /cf — same skill, same routing, same gates (per routing.md CliAliasAndInvocation)."
version: 1.0
purpose: Standalone cf-studio command; pass-through alias to the cf skill
---

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

```pdsl
UNIT CfStudioAlias

PURPOSE:
  Pass-through alias to the cf skill. /cf-studio behaves identically to /cf
  per routing.md's CliAliasAndInvocation rule.

DO:
  - RUN ALWAYS open and follow {cf-studio-path}/.core/skills/studio/SKILL.md

ON_ERROR:
  load_failed -> EMIT "Cannot load cf skill — check that {cf-studio-path} is correctly set." STOP_TURN
```
