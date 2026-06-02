---
name: generate-phase-0.2-review-loop-cfg
description: "Invoke when the generate workflow reaches Phase 0.2 to configure COLLECTOR_MAX_ITER before Phase 1 input collection begins."
purpose: Generate Phase 0.2 — configure COLLECTOR_MAX_ITER (Phase 1 collector ↔ user edit cap); MAX_ITER prompt moved to workflows/generate/phase-5/index.md § Pre-Phase-Setup per finding I10.
loaded_by: workflows/generate.md
version: 1.0
---

## Phase 1 Collector Iteration Cap

```pdsl
UNIT Phase02ReviewLoopCfg

PURPOSE:
  Resolve COLLECTOR_MAX_ITER before Phase 1 input collection begins.

STATE:
  COLLECTOR_MAX_ITER: integer
    default: 5
    scope: workflow_run

DO:
  IF user supplied collector=<m> in invocation:
    SET COLLECTOR_MAX_ITER = m
  ELSE:
    SET COLLECTOR_MAX_ITER = 5
    ASK only when user explicitly wants collector-loop control

RULES:
  - MUST resolve COLLECTOR_MAX_ITER before Phase 1
  - COLLECTOR_MAX_ITER=0 disables iteration: collector returns once;
    on any edit reply the orchestrator MUST stop with BLOCKED
  - Phase 5 MAX_ITER prompts MUST NOT change COLLECTOR_MAX_ITER;
    by then Phase 1 is complete
```
