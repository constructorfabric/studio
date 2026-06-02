---
cf: true
type: workflow
name: cf-studio
description: "Thin alias for the cf skill. /cf-studio behaves identically to /cf — same skill, same routing, same gates (per routing.md CliAliasAndInvocation)."
version: 1.0
purpose: Standalone cf-studio command; pass-through alias to the cf skill
---

```pdsl
UNIT StudioRootSkillEntrypointBootstrap
PURPOSE: Load the shared root cf skill entrypoint bootstrap.
DO:
  - LOAD {cf-studio-path}/.core/workflows/shared/root-skill-entrypoint-bootstrap.md
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
