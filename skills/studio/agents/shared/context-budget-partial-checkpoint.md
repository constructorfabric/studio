---
description: Shared partial-checkpoint guard for agent prompts that must stop before context exhaustion causes truncated output.
name: context-budget-partial-checkpoint
version: 0.1
purpose: Reuse the common budget-exhaustion checkpoint flow while keeping caller-specific payload schemas local.
---

# Context Budget Partial Checkpoint

```pdsl
UNIT SharedContextBudgetPartialCheckpoint

PURPOSE:
  Emit a checkpoint when context budget is exhausted before all target inputs
  are read, rather than risk truncated output.

WHEN:
  - REQUIRE fewer than 20% of estimated remaining context budget remains
  - AND NOT all PARTIAL_CHECKPOINT_TARGETS have been fully read

DO:
  - EMIT PARTIAL_CHECKPOINT_SECTION markdown block
  - EMIT PARTIAL_CHECKPOINT_JSON payload
  - EMIT PARTIAL_CHECKPOINT_FINDINGS payload when the caller requires it
  - NEVER emitting a complete validation report
  - STOP_TURN

RULES:
  - ALWAYS the caller owns target-field naming, checkpoint schema shape, and
    resume instructions
```
