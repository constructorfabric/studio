---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when each Phase 5 iteration begins and the deterministic validator must run before any semantic reviewer dispatch.
---

### Phase 5.1: Deterministic Gate

<!-- The `Validation Results` block schema is owned by the deterministic-validator agent file (`{cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md` § Output). Workflows reference it by name only; do NOT redefine the field set here — always reproduce the template from the agent file verbatim. -->

Requires: `workflows/shared/inline-fallback-probe.md` before any `cf-*` sub-agent dispatch.

Dispatch sub-agent `cf-deterministic-validator` with the JSON contract documented in `{cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md`. Inputs: see "Inputs (dispatched-prompt contract)" in that agent file (mandatory vs optional listed there). Orchestrator-supplied values for this dispatch:

- `target_paths` = the Phase 5 `target_paths` state on external analyze→generate entry; otherwise `manifest.paths_written` from `workflows/generate/phase-4-write.md` (or the last accepted manifest from a prior iteration)
- `target_kinds` = `{ "<path>": "{TARGET_TYPE}" }` per path
- `rules_mode` = `{STRICT|RELAXED}`
- `language_check_configured` = `true|false` from `.studio-workspace.toml`

Capture the returned `Validation Results` block and the `det_findings` JSON array.
Append a `phase5_dispatch_evidence` record for this validator dispatch with
`phase = "5.1"`, `agent_id = "cf-deterministic-validator"`,
`target_paths`, and the returned `Validation Results` marker.

- If the overall gate is `PASS` (or `SKIPPED` with `Validator availability proof`), proceed to `workflows/generate/phase-5/phase-5.2-semantic.md`.
- If the gate is `FAIL`, set `all_findings = det_findings`; skip `workflows/generate/phase-5/phase-5.2-semantic.md`; proceed to `workflows/generate/phase-5/phase-5.3-findings.md`.

In STRICT mode the gate result is authoritative; in RELAXED mode the loop may exit via an explicitly unvalidated `Deterministic gate: SKIPPED` or `Deterministic gate: FAIL` path on the `workflows/generate/phase-5/phase-5.4-approval.md` § option `4` manual-handoff branch.
