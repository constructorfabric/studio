---
cf: true
type: workflow
name: cf-studio
version: 0.1
description: "Invoke when the user or another skill or workflow needs or asks for /cf-studio, cf-studio help, or cfs studio."
purpose: Pass-through alias that delegates to the cf skill entrypoint.
---

# cf-studio

This is a thin alias: `cf-studio` behaves identically to `cf` — same skill, same routing, same gates. It performs no work of its own; it simply delegates to the `cf` skill, which initializes the session, loads the core rules, and routes to the matching cf-* skill.

```pdsl
UNIT StudioAlias
PURPOSE: Delegate cf-studio to the cf skill — they are the same skill.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/skill-invocation-art.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/pdsl-execution-card.md
  RUN SkillInvocationArt
  INVOKE skill `cf` to initialize the session and route the request, then STOP_TURN
RULES:
  ALWAYS treat cf-studio as an exact alias of cf — same skill, same routing, same gates
  ALWAYS keep SimpleModeGate owned by the resolved non-exempt workflow, never by this alias
  NEVER perform any work, render any output, or apply any gate here beyond the SkillInvocationArt entry banner and delegating to the cf skill
```
