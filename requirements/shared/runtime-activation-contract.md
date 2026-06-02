---
cf: true
type: requirement
name: Runtime Activation Contract
version: 0.1
purpose: Reuse the common controller-owned methodology activation contract for requirement routers.
---

# Runtime Activation Contract

```pdsl
UNIT SharedRuntimeActivationContract

PURPOSE:
  Route methodology activation through explicit controller-owned prompt loading.

WHEN:
  - REQUIRE ACTIVATION_INTENT is detected

DO:
  - REQUIRE this methodology is active
  - REQUIRE controller has loaded ACTIVATION_REQUIRED_PROMPT_ASSETS
  - SET ACTIVATION_MODE_FLAG = true

RULES:
  - ALWAYS treat upstream methodologies as controller-owned prompt assets
  - NEVER let prompt-consuming sub-agents reopen those prompt files from disk
  - ALWAYS provide any dispatched subset through prompt_context_view
```
