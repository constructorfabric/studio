---
description: "Invoke when the user accepted the brainstorm offer and the expert panel must be selected / edited before the round loop begins."
name: phase-0.7-panel-selection
purpose: Brainstorm session setup — facilitator dispatch, proposed-panel rendering, panel-edit forms, seed-topic confirmation
loaded_by: workflows/generate/phase-0.7/index.md
version: 1.0
---

<!-- toc -->

- [Session setup (panel selection)](#session-setup-panel-selection)

<!-- /toc -->

### Session setup (panel selection)

Requires: `workflows/shared/inline-fallback-probe.md` before any `cf-*` sub-agent dispatch.

Dispatch sub-agent `cf-brainstorm-facilitator` with the JSON contract documented in `{cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-facilitator.md`. Orchestrator-supplied values for this dispatch:

- `initial_topic` = a one-paragraph summary of the user's original request (the trigger prompt for this `/cf-generate` run)
- `kind` = `{KIND}`; `rules_loaded` = `true` only when kit rules were actually loaded for this brainstorm session, else `false`
- `kit_rules_path`, `template_path`, `example_path` = resolved from `rules.md` when available (each `null` when unavailable; pass the key with `null` rather than omitting). A non-null `kit_rules_path` by itself does not make `rules_loaded=true`; the orchestrator must have opened and applied the rules.
- `project_ctx` = a 2-3-sentence summary covering: the selected `system` (from Phase 0.5), the `KIND` and its kit (when STRICT + kit-mapped), and the most-relevant existing artifact paths identified during Phase 0.5 parent/sibling discovery

The agent returns `{ proposed_panel: [...3..6 entries], seed_topic: {...} }`. Show to the user:

```text
Proposed panel for `{KIND}: {name}`:

E1. Domain Architect      — focus: domain model, actor boundaries
                            why: <rationale>
E2. Security Reviewer     — focus: auth, data-handling
                            why: <rationale>
...

Reply `accept` (suggested when the proposed panel matches your needs), list
IDs to drop (`drop E2,E4`), `swap E2: <new persona> (<focus>)`, or
`add: <persona> (<focus>)`. Min 3, max 6 participants. One reply form per
turn — compound replies (e.g. `drop E2; add: X (focus)`) are refused with
a one-line clarifier asking for a single edit form; re-issue panel edits
across multiple turns. After every edit the orchestrator re-renders the
proposed panel until the user replies `accept`.

Seed topic: `{seed_topic.text}`
Reply `start` after confirming the panel, or `seed: <topic>` to override.
```

After user confirmation, set `state.panel = confirmed_list` and `state.topic_current = confirmed_seed_topic`.
