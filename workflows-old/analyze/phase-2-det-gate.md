---
name: analyze-phase-2-det-gate
description: "Invoke when running Analyze Phase 2 to dispatch cf-deterministic-validator and gate semantic review on its result."
purpose: Analyze Phase 2 — dispatch cf-deterministic-validator sub-agent and gate semantic review on result
loaded_by: workflows/analyze.md
version: 1.0
---

# Analyze Phase 2 — Deterministic Gate

```pdsl
UNIT AnalyzePhase2DeterministicGate

PURPOSE:
  Dispatch cf-deterministic-validator and gate semantic review on its result.

WHEN:
  - REQUIRE SEMANTIC_ONLY == false AND EXPLAIN_MODE == false

DO:
  - REQUIRE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md has run
  - LOAD {cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md
    as the validator source contract
  - RUN SYNTHESIZE final dispatch prompt from the loaded validator source contract
    plus SHARED_CONTEXT_PACK and the payload below
  - REQUIRE source contract is not loaded, unreadable, ambiguous, or not reflected in
     the final dispatch prompt:
    FAIL per sub-agent-dispatch.md § SubAgentContractReadGate
    - NEVER dispatch
  - DISPATCH cf-deterministic-validator with synthesized final prompt including:
    target_paths    = diff_scope.review_targets when CHANGE_REVIEW=true, else {PATHS}
    target_kinds    = per-path map derived from Phase 0 typed sets
                      (prompt_targets -> prompt, code_targets -> code,
                       artifact_targets -> artifact), falling back to artifacts.toml
                      and then {TARGET_TYPE} only for paths not present in a typed set
    rules_mode      = "{STRICT|RELAXED}"
    language_check_configured = true|false from .studio-workspace.toml
  - RUN Embed returned Validation Results block verbatim into Phase 4 output.
  - RUN Carry det_findings JSON forward into {cf-studio-path}/.core/workflows/analyze/phase-4-output/remediation-handoff.md when applicable.
  - REQUIRE gate result == FAIL:
    - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-4-output/index.md
    - REQUIRE {cf-studio-path}/.core/workflows/analyze/phase-4-output/remediation-handoff.md when actionable issues exist
  - REQUIRE gate result == PASS OR SKIPPED (with Validator availability proof):
    - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-2.5-reviewer-plan.md

RULES:
  - ALWAYS run {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md before any cf-* sub-agent dispatch
  - ALWAYS apply sub-agent-dispatch.md § SubAgentContractReadGate before
    dispatching cf-deterministic-validator
  - ALWAYS skip this unit when SEMANTIC_ONLY=true OR EXPLAIN_MODE=true
  - ALWAYS embed Validation Results block verbatim; NEVER redefine the field set
  - NEVER use the agent's own checklist walkthrough as a substitute for the
    dispatched validator (anti-pattern SIMULATED_VALIDATION)
  - ALWAYS emit remediation-handoff.md when FAIL produces actionable issues
  - ALWAYS route PASS/SKIPPED through Phase 2.5 before Phase 3 whenever semantic
    methodology may run; Phase 3 owns no implicit planner auto-skip

NOTES:
  Validator availability proof: exit-0 result from cfs validate --version or
    equivalent availability check run before the dispatch.
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
