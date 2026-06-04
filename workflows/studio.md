---
cf: true
type: workflow
name: cf-studio
version: 0.1
description: "Thin alias for the cf skill — /cf-studio, cf-studio help, and cfs studio behave identically to /cf (same skill, same routing, same gates)."
purpose: Pass-through alias that delegates to the cf skill
---

# cf-studio

This is a thin alias: `cf-studio` behaves identically to `cf` — same skill, same routing, same gates. It performs no work of its own; it simply delegates to the `cf` skill, which initializes the session, loads the core rules, and routes to the matching cf-* skill.

```pdsl
UNIT StudioAlias
PURPOSE: Delegate cf-studio to the cf skill — they are the same skill.
DO:
  INVOKE skill `cf` to initialize the session and route the request, then STOP_TURN
RULES:
  ALWAYS treat cf-studio as an exact alias of cf — same skill, same routing, same gates
  NEVER perform any work, render any output, or apply any gate here beyond delegating to the cf skill
```
