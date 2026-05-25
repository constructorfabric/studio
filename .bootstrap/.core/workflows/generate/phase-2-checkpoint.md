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

Skip this phase; see Phase 4 for content production.

Content production is delegated through Phase 4. If Phase 1.5 produced an
`AUTHOR_EXECUTION_PLAN`, Phase 4 executes the planned task groups; otherwise
the read-only `cf-generate-author` selector chooses the cheapest
capable write-capable author for the whole payload. The orchestrator collects
inputs in Phase 1, resolves the author-plan offer in Phase 1.5, and confirms
the final summary in Phase 3; there is no separate "generation pass" in the
orchestrator. The selected author loads template + example + (checklist when
STRICT requires pre-write) + design (code mode) inside its isolated context.

Open, load, and follow `{cf-studio-path}/.core/skills/studio/agents/cf-generate-author-worker.md` "Content Production Rules" for placeholder / ID format / CDSL / traceability / markdown-quality requirements; they are enforced by the selected author sub-agent per its Response Completion Gate.

## Phase 2.5: Checkpoint (for long artifacts)

Checkpoint when artifacts have `>10` sections or generation spans multiple turns.

```markdown
### Generation Checkpoint
**Workflow**: /cf-generate {KIND}
**Phase**: 2 complete, ready for Phase 3
**Inputs collected**: {section summaries}
**Author plan**: {AUTHOR_PLAN_OFFER_RESOLVED}; {task/group summary or "single author flow"}
**Content generated**: {line count} lines
**Pending**: Summary → Confirmation → Write → Analyze
Resume: Re-read this checkpoint, verify no file changes, continue to Phase 3.
```

Checkpoint policy: default is chat only; write a checkpoint file only if the user explicitly requests/approves it. On resume after compaction: re-read the target file if it exists, re-load rules dependencies, then continue from the saved phase.
