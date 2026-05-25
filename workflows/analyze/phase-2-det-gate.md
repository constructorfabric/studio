---
name: analyze-phase-2-det-gate
description: "Invoke when running Analyze Phase 2 to dispatch cf-deterministic-validator and gate semantic review on its result."
purpose: Analyze Phase 2 — dispatch cf-deterministic-validator sub-agent and gate semantic review on result
loaded_by: workflows/analyze.md
version: 1.0
---

## Phase 2: Deterministic Gate

<!-- The `Validation Results` block schema is owned by the deterministic-validator agent file (`{cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md` § Output). Workflows reference it by name only; do NOT redefine the field set here — always reproduce the template from the agent file verbatim. -->

If `SEMANTIC_ONLY=true` OR `EXPLAIN_MODE=true`, skip this sub-file and go to `workflows/analyze/phase-3-semantic.md`.

Requires: `workflows/shared/inline-fallback-probe.md` before any `cf-*` sub-agent dispatch. Pre-dispatch fail-stop and Mode B degradation rules are defined in `{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md`.

Dispatch sub-agent `cf-deterministic-validator` with the JSON contract documented in `{cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md`. Inputs: see "Inputs (dispatched-prompt contract)" in that agent file (mandatory vs optional listed there). Orchestrator-supplied values for this dispatch:

- `target_paths` = `diff_scope.review_targets when CHANGE_REVIEW=true, otherwise {PATHS}`
- `target_kinds` = per-path map keyed by each entry in `target_paths`, value from `artifacts.toml` (default `{TARGET_TYPE}` when unmapped)
- `rules_mode` = `"{STRICT|RELAXED}"`
- `language_check_configured` = `true|false` from `.studio-workspace.toml` (`[validation] allowed_content_languages`)

The agent returns the canonical `Validation Results` block plus a `det_findings` JSON array. Embed the block verbatim into `workflows/analyze/phase-4-output/index.md` output; carry `det_findings` forward into the `workflows/analyze/phase-4-output/remediation-handoff.md` menu when applicable.

Gate behavior:
- If the overall deterministic gate is `FAIL`, skip `workflows/analyze/phase-3-semantic.md` and jump to `workflows/analyze/phase-4-output/index.md` to report blocking issues; the `workflows/analyze/phase-4-output/remediation-handoff.md` menu is mandatory when actionable issues exist.
- If `PASS` or `SKIPPED` (with `Validator availability proof`), continue to `workflows/analyze/phase-3-semantic.md`.

> **⛔ CRITICAL**: The agent's own checklist walkthrough is **NOT** a substitute for the deterministic validator. See anti-pattern `SIMULATED_VALIDATION`. The dispatched sub-agent executes the actual resolved validator command from the target bootstrap (for example `cpt` in a Studio `.bootstrap`, or `cfs` in a Constructor Studio adapter) for validate / validate-artifact / validate-toc / check-language routes.
