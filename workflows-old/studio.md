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
  - LOAD {cf-studio-path}/.core/skills/studio/SKILL.md
  - CONTINUE CfSkillInit from {cf-studio-path}/.core/skills/studio/SKILL.md
```