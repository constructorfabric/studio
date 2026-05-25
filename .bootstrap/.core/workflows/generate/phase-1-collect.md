---
name: generate-phase-1-collect
description: "Invoke when the generate workflow enters Phase 1 to dispatch the collector sub-agent, manage the edit-iteration loop, and await final input approval."
purpose: Generate Phase 1 — collector dispatch contract, edit-iteration loop, COLLECTOR_MAX_ITER handling
loaded_by: workflows/generate.md
version: 1.0
---

<!-- toc -->

- [Phase 1: Collect Information](#phase-1-collect-information)

<!-- /toc -->

## Phase 1: Collect Information

Requires: `workflows/shared/inline-fallback-probe.md` before any `cf-*` sub-agent dispatch.

Dispatch sub-agent `cf-generate-collector` with the JSON contract documented in `{cf-studio-path}/.core/skills/studio/agents/cf-generate-collector.md`. Inputs: see "Inputs (dispatched-prompt contract)" in that agent file (mandatory vs optional listed there). Orchestrator-supplied values for this dispatch:

- `kind` = `{KIND}`; `name` = `{name}`; `rules_mode` = `{STRICT|RELAXED}`; `system` from Phase 0.5
- `template_path`, `example_path`, `kit_rules_path` resolved from `rules.md`
- `pre_resolved_inputs` = `state.decisions` from Phase 0.7 (or `{}` when brainstorm was skipped)
- `open_questions` = `state.open_questions` from Phase 0.7 (or `[]` when skipped)

The agent returns a single Inputs markdown block (shown to the user verbatim)
followed by a `proposed_inputs` JSON block (consumed by the orchestrator).
Show the markdown; persist the returned JSON as
`stored_proposed_inputs`. This stored value is the only authoritative Phase 1
state for Phase 4. Await `approve all` or per-item edits.

On edits, merge the user's modifications into `stored_proposed_inputs`, then
re-dispatch the collector with the **same full Inputs field set** as the
initial dispatch above (`kind`, `name`, `rules_mode`, `system`,
`template_path`, `example_path`, `kit_rules_path`, `open_questions` all
carried over unchanged), with **only `pre_resolved_inputs` updated** to that
merged `stored_proposed_inputs` map. When the collector returns a refreshed
Inputs block, replace `stored_proposed_inputs` with the refreshed
`proposed_inputs` JSON before showing the next edit/approval prompt. Every
collector return supersedes the prior stored state; Phase 4 MUST use the final
approved `stored_proposed_inputs`, not an earlier display copy. Iterate until
`approve all` or `COLLECTOR_MAX_ITER` is reached. `COLLECTOR_MAX_ITER`
defaults to `5` (mirrors Phase 5's `MAX_ITER` default). On exhaustion the
orchestrator MUST STOP and surface a `BLOCKED` status with the partial Inputs
block — identically to other Constructor Studio iteration loops — rather than
auto-proceeding to Phase 3.

After approval:

```text
Inputs confirmed. Proceeding to author planning...
```

Then proceed to `workflows/generate/phase-1.5-author-plan.md`. Phase 3 MUST
NOT run until `AUTHOR_PLAN_OFFER_RESOLVED` is set by Phase 1.5.

Input collection rules: the collector MUST propose specific answers, use project context, allow modifications, and the orchestrator MUST require final confirmation. MUST NOT skip questions, assume answers, or proceed without explicit `approve all`.
