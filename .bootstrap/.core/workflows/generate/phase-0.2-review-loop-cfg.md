---
name: generate-phase-0.2-review-loop-cfg
description: "Invoke when the generate workflow reaches Phase 0.2 to configure COLLECTOR_MAX_ITER before Phase 1 input collection begins."
purpose: Generate Phase 0.2 — configure COLLECTOR_MAX_ITER (Phase 1 collector ↔ user edit cap); MAX_ITER prompt moved to workflows/generate/phase-5/index.md § Pre-Phase-Setup per finding I10.
loaded_by: workflows/generate.md
version: 1.0
---

## Phase 1 Collector Iteration Cap

Phase 1 (input collection) uses iteration cap `COLLECTOR_MAX_ITER` (default `5`) for collector ↔ user edit rounds. Resolve it before Phase 1.

If the user supplied `collector=<m>` in the invocation, use that value. Otherwise default to `5`; ask only when the user explicitly wants collector-loop control. `COLLECTOR_MAX_ITER=0` disables iteration — the collector returns once and on any edit reply the orchestrator stops with `BLOCKED`.

Phase 5 `MAX_ITER` prompts do not change `COLLECTOR_MAX_ITER`; by then Phase 1 is complete.
