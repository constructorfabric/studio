---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when Phase 2 (no-op) and Phase 2.5 checkpoint guidance must be applied between Phase 1 and Phase 3 — particularly for long artifacts spanning multiple turns.
---

<!-- toc -->

- [Phase 2: Generate (no-op — content production happens in Phase 4)](#phase-2-generate-no-op--content-production-happens-in-phase-4)
- [Phase 2.5: Checkpoint (for long artifacts)](#phase-25-checkpoint-for-long-artifacts)

<!-- /toc -->

## Phase 2: Generate (no-op — content production happens in Phase 4)

```pdsl
UNIT Phase2NoOp

PURPOSE:
  Skip Phase 2; content production is delegated through Phase 4.

DO:
  SKIP this phase
  CONTINUE Phase 4 for content production

NOTES:
  If Phase 1.5 produced an AUTHOR_EXECUTION_PLAN, Phase 4 executes planned
  task groups; otherwise the read-only cf-generate-author selector chooses
  the cheapest capable write-capable author for the whole payload.
  The orchestrator collects inputs in Phase 1, resolves the author-plan offer
  in Phase 1.5, and confirms the final summary in Phase 3; there is no separate
  "generation pass" in the orchestrator.
  The selected author loads template + example + (checklist when STRICT requires
  pre-write) + design (code mode) inside its isolated context.
  Open, load, and follow
  {cf-studio-path}/.core/skills/studio/agents/cf-generate-author-worker.md
  "Content Production Rules" for placeholder / ID format / CDSL / traceability /
  markdown-quality requirements.
```

## Phase 2.5: Checkpoint (for long artifacts)

```pdsl
UNIT Phase25Checkpoint

PURPOSE:
  Emit a checkpoint when artifacts have >10 sections, generation spans
  multiple turns, or resumable section/state bookkeeping must be preserved.

WHEN:
  artifact has > 10 sections OR generation spans multiple turns OR resumable
  section/state bookkeeping exists or must be emitted for resume safety

DO:
  IF artifact has > 10 sections OR generation spans multiple turns OR
     resumable section/state bookkeeping exists or must be emitted:
    EMIT exactly:
---
### Generation Checkpoint
**Workflow**: Invoke skill `cf-generate` {KIND}
**Phase**: 2 complete, ready for Phase 3
**Inputs collected**: {section summaries}
**Author plan**: {AUTHOR_PLAN_OFFER_RESOLVED}; {task/group summary or "single author flow"}
**Content generated**: {line count} lines
**Pending**: Summary → Confirmation → Write → Analyze
Resume: Re-read this checkpoint, verify no file changes, continue to Phase 3.
---

RULES:
  - Default: checkpoint is chat-only
  - MUST write a checkpoint file ONLY when user explicitly requests/approves it
  - This fragment is lazy-loaded only when the WHEN predicate is true
  - On resume after compaction:
    RE-READ target file if it exists
    RE-LOAD only the controller-supplied prompt_context_view slices required
      for the saved phase and checkpoint bookkeeping
    MUST NOT reopen prompt assets from disk
    CONTINUE from saved phase
```
