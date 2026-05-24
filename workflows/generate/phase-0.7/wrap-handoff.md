---
description: "Invoke when the brainstorm session ends (user wrap-up, stop-token, or BRAINSTORM_MAX_ROUNDS cap) and the wrap-up summary + handoff to Phase 1 must run."
name: phase-0.7-wrap-handoff
purpose: Brainstorm loop exit — consolidated design block, approve/iterate/discard branches, stop-token semantics, Phase 1 hand-off
loaded_by: workflows/generate/phase-0.7/index.md
version: 1.1
---

<!-- toc -->

- [Consolidated design block (loop exit)](#consolidated-design-block-loop-exit)
- [Contributions shape and orchestration modes](#contributions-shape-and-orchestration-modes)
- [Hand-off to `workflows/generate/phase-1-collect.md`](#hand-off-to-workflowsgeneratephase-1-collectmd)

<!-- /toc -->

### Consolidated design block (loop exit)

When `state.topic_current` becomes `None`, emit (when `rules_mode == RELAXED`, prefix the block with `⚠ Brainstorm without kit rules (reduced quality assurance)` per the contract declared in `workflows/generate/phase-0.7/save-and-rules.md` § Rules respect):

```text
Brainstorm complete after {N} rounds.
Panel: {personas}
Topics covered: {topic_history}

Decisions:
- {section_or_key}: {value}

Open questions (carry into inputs):
- {open_question}

Reply `approve` (suggested) to hand decisions to input collection,
`iterate` to reopen a specific topic for another round, or `discard handoff`
to ignore brainstorm decisions and proceed from scratch. In `save` mode, the
saved brainstorm cache remains on disk and follows manual retention.
```

- `approve` → set `PRE_RESOLVED_INPUTS = state.decisions`, `CARRYOVER_QUESTIONS = state.open_questions`; proceed to `workflows/generate/phase-1-collect.md`.
- `iterate` → ask the user which gap to reopen; append as a forced topic; set `pending_round_kind = "topic"` before resuming the round loop (the resumed loop's first iteration is always a topic-round on the forced topic, never a challenge-round, regardless of the kind of the last in-loop round before wrap).
- `discard` or `discard handoff` → set `PRE_RESOLVED_INPUTS = {}`, `CARRYOVER_QUESTIONS = []`; proceed to `workflows/generate/phase-1-collect.md`. If the session used `save`, do not delete cache artifacts; the saved brainstorm cache remains on disk until manual cache retention removes it.

Stop tokens (`stop` / `enough` / `done`) at any prompt end the session immediately; unanswered questions become `open_questions`; current `decisions` carry forward.

### Contributions shape and orchestration modes

**Audit note**: The wrap-up logic operates on aggregated `state.decisions` post-flatten, which is protocol-agnostic. The `contributions[]` array in `state.rounds[]` may originate from either:

- **Fan-out mode** (`rounds[].panel_mode == "fan-out"`): All relevant experts dispatched in parallel. Each expert independently produces questions and critique. The orchestrator collects and flattens contributions before persisting.
- **Single-agent panel** (`rounds[].panel_mode == "single-agent"`): One expert runs full round logic. Other panelists read the primary output and (optionally) provide structured critique per `protocol`. The panel renderer emits the envelope; the orchestrator flattens before persisting.

**Semantic equivalence post-flatten**: Both modes produce an identical `state.rounds[].contributions[]` shape. Each entry has `expert_id`, `relevant`, `questions[]`, `critique`, and `next_topic_proposal`. Dissent computations (rate of counter-proposals, cross-referenced challenges) remain valid because the **stance enum + delta + cross-reference invariant** (see state-schema.md § Round Field Reference) carries the dissent signal regardless of dispatch shape.

**Single-pass protocol behavior**: When `rounds[].protocol == "single-pass"` (only valid under single-agent mode), the `critique` field in non-primary panelists is absent or empty. Orthogonal self-audit is permitted but silent (the primary expert's internal review does not surface as a critique block). This is a valid optimization for low-latency or bandwidth-constrained scenarios; dissent computations remain sound.

**Wrap-up evaluation**: The wrap-up menu and decision summary **surface `rounds[].panel_mode` and `rounds[].status`** implicitly: high `status == "degraded"` rate may warrant user review before approve. When evaluating carryover decisions, note that:

- `status == "ok"`: All experts completed normally.
- `status == "degraded"`: One or more experts exceeded SLA (timeout, retry exhausted) but round completed.
- `rounds[].panel_mode` presence enables auditing which rounds used single-agent pooling vs. fan-out parallelism.

### Hand-off to `workflows/generate/phase-1-collect.md`

`workflows/generate/phase-1-collect.md` dispatches `cf-constructor-generate-collector` with `pre_resolved_inputs = PRE_RESOLVED_INPUTS` and `open_questions = CARRYOVER_QUESTIONS`. The collector marks pre-filled sections `[from brainstorm]` and surfaces a `Carryover Questions` mini-section. Open, load, and follow `workflows/generate/phase-1-collect.md`.
