---
cf: true
type: workflow-fragment
name: shared-context-pack-ownership
description: Shared controller-owned prompt-asset loading contract for workflow and protocol surfaces.
version: 0.1
purpose: Reuse the common shared-context-pack ownership rules without inlining controller prompt-loading policy.
---

# Shared Context Pack Ownership

```pdsl
UNIT SharedContextPackOwnership

PURPOSE:
  Keep prompt-asset loading controller-owned and shared-context-pack aware.

RULES:
  - ALWAYS the designated prompt-asset family is controller-owned and loaded by
    the top-level controller only
  - ALWAYS before any prompt-consuming dispatch, the controller reuses or
    refreshes SHARED_CONTEXT_PACK, loads the agent prompt source, and
    synthesizes the final dispatch prompt with only the task-relevant
    instruction context
  - ALWAYS prompt-consuming sub-agents ALWAYS receive needed instruction text
    through the controller-synthesized final dispatch prompt or
    prompt_context_view
  - ALWAYS prompt-consuming sub-agents NEVER reopen prompt assets directly from
    disk
  - ALWAYS workflow-specific or protocol-specific asset lists, origin logging,
    and scope addenda remain local to the caller
```
