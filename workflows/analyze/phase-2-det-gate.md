---
name: analyze-phase-2-det-gate
description: "Invoke when running Analyze Phase 2 to dispatch cf-deterministic-validator and gate semantic review on its result."
purpose: Analyze Phase 2 — dispatch cf-deterministic-validator sub-agent and gate semantic review on result
loaded_by: workflows/analyze.md
version: 1.0
---

```text
UNIT AnalyzePhase2DeterministicGate

PURPOSE:
  Dispatch cf-deterministic-validator and gate semantic review on its result.

WHEN:
  SEMANTIC_ONLY == false AND EXPLAIN_MODE == false

DO:
  IF SEMANTIC_ONLY == true OR EXPLAIN_MODE == true:
    CONTINUE workflows/analyze/phase-3-semantic.md
  REQUIRE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md has run
  DISPATCH cf-deterministic-validator with:
    target_paths    = diff_scope.review_targets when CHANGE_REVIEW=true, else {PATHS}
    target_kinds    = per-path map from artifacts.toml (default {TARGET_TYPE} when unmapped)
    rules_mode      = "{STRICT|RELAXED}"
    language_check_configured = true|false from .studio-workspace.toml
  Embed returned Validation Results block verbatim into Phase 4 output.
  Carry det_findings JSON forward into {cf-studio-path}/.core/workflows/analyze/phase-4-output/remediation-handoff.md when applicable.
  IF gate result == FAIL:
    CONTINUE workflows/analyze/phase-4-output/index.md
    REQUIRE {cf-studio-path}/.core/workflows/analyze/phase-4-output/remediation-handoff.md when actionable issues exist
  IF gate result == PASS OR SKIPPED (with Validator availability proof):
    CONTINUE workflows/analyze/phase-3-semantic.md

RULES:
  - MUST run {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md before any cf-* sub-agent dispatch
  - MUST skip this unit when SEMANTIC_ONLY=true OR EXPLAIN_MODE=true
  - MUST embed Validation Results block verbatim; MUST_NOT redefine the field set
  - MUST_NOT use the agent's own checklist walkthrough as a substitute for the
    dispatched validator (anti-pattern SIMULATED_VALIDATION)
  - MUST emit remediation-handoff.md when FAIL produces actionable issues

NOTES:
  Validation Results block schema is owned by:
    {cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md § Output
  Always reproduce the template from the agent file verbatim.
  Pre-dispatch fail-stop and Mode B degradation rules are in:
    {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md
  The dispatched sub-agent executes the actual resolved validator command
  from the target bootstrap (e.g. `cpt` in a Studio .bootstrap, or `cfs`
  in a Constructor Studio adapter) for validate / validate-artifact /
  validate-toc / check-language routes.
```
