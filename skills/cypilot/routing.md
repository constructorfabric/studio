---
description: "Invoke when routing a Cyber Constructor command or user request to the matching workflow or agent."
---

# Cyber Constructor Routing

Direct CLI commands still require write confirmation when write-capable.
Use `{cfc_cmd} --json agents --agent <name>` for agent lookup. Run `init`,
`delegate`, and `update` without `--json`.

Workflow routing priority:
1. `delegate` -> open and follow `{cf-constructor-path}/.core/skills/cypilot/agents/cf-constructor-ralphex.md`.
2. `compile phase` -> open and follow `{cf-constructor-path}/.core/skills/cypilot/agents/cf-constructor-phase-compiler.md`.
3. `execute phase` -> open and follow `{cf-constructor-path}/.core/skills/cypilot/agents/cf-constructor-phase-runner.md`.
4. `plan` / decompose / break down -> open and follow `workflows/plan.md`.
5. create / edit / fix / update / implement / refactor / setup / build ->
   open and follow `workflows/generate.md`.
6. analyze / validate / review / check / inspect / audit / compare /
   explain / walk through / teach / onboard / bug hunt / find bugs / prompt bugs ->
   open and follow `workflows/analyze.md`.
7. workspace / multi-repo / add source / cross-reference ->
   open and follow `workflows/workspace.md`.
8. map / dependency map / cfc map / visualize dependencies / render graph ->
   open and follow `workflows/cf-constructor-map.md`.
9. migrate from cypilot -> open and follow `migrate-from-cypilot.md`.

Compound find+fix intent: when a request matches keywords from BOTH entry 5 (`fix`/`update`/`refactor`) and entry 6 (`find bugs`/`bug hunt`/`audit`/`review`), prefer entry 6 (`analyze`) — the analyze run produces findings, then offers a Remediation Handoff that routes into `generate` if the user accepts. Routing both to `generate` skips the find phase entirely.

If routing is unclear, ask why the input is needed and request exactly one of
`plan`, `generate`, `analyze`, `workspace`, or `migrate`.

Oversized raw inputs over `500` lines (line count of the user's pasted text or directly provided files) must surface the raw-input-overflow rule (`{cf-constructor-path}/.core/requirements/raw-input-overflow.md`) which offers `/cf-constructor-plan` before direct generate/analyze continues. This raw-input threshold is distinct from the workflow-level estimated-context gates (`analyze`: > 2000 lines, `generate`: > 2500 lines); do not collapse the three thresholds.
