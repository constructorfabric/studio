---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when each Phase 5 iteration begins and the deterministic validator must run before any semantic reviewer dispatch.
---

# Generate Phase 5.1: Deterministic Gate

```pdsl
UNIT Phase51DeterministicGate

PURPOSE:
  Dispatch cf-deterministic-validator and route based on gate result.

DO:
  - REQUIRE `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md` loaded before dispatch
  - LOAD {cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md
    as the validator source contract
  - RUN SYNTHESIZE final dispatch prompt from the loaded validator contract plus
    SHARED_CONTEXT_PACK and the payload below
  - REQUIRE validator source contract is not loaded, unreadable, ambiguous, or not
     reflected in the final dispatch prompt:
    FAIL per sub-agent-dispatch.md § SubAgentContractReadGate
    - NEVER dispatch
  - DISPATCH cf-deterministic-validator with the synthesized final prompt and
    orchestrator-supplied payload:
    target_paths = Phase 5 target_paths state on external analyze→generate entry;
                   otherwise manifest.paths_written from phase-4-write.md
                   (or last accepted manifest from prior iteration)
    target_kinds = { "<path>": "{TARGET_TYPE}" } per path
    rules_mode = {STRICT|RELAXED}
    language_check_configured = true|false from .studio-workspace.toml
  - RUN CAPTURE returned Validation Results block and det_findings JSON array
  - RUN APPEND phase5_dispatch_evidence record:
    phase = "5.1"
    agent_id = "cf-deterministic-validator"
    target_paths = target_paths
    result_marker = returned Validation Results marker

MENU Det51Routing:
  TITLE: Deterministic gate routing (machine reference)
  OPTIONS:
    1 PASS or SKIPPED (with Validator availability proof) ->
      SET det_gate_result = returned deterministic gate result
      SET det_gate_evidence = returned validator availability proof when SKIPPED,
        otherwise returned Validation Results marker
      SET all_findings = []
      CONTINUE workflows/generate/phase-5/phase-5.2-semantic.md
    2 FAIL ->
      SET all_findings = det_findings
      SKIP workflows/generate/phase-5/phase-5.2-semantic.md
      CONTINUE workflows/generate/phase-5/phase-5.3-findings.md

RULES:
  - ALWAYS STRICT mode: gate result is authoritative
  - ALWAYS PASS and SKIPPED outcomes ALWAYS preserve det_gate_result and
    det_gate_evidence for Phase 5.3 / Phase 5.5; clearing all_findings ALWAYS
    NOT erase validator proof
  - ALWAYS apply sub-agent-dispatch.md § SubAgentContractReadGate before
    dispatching cf-deterministic-validator
  - ALWAYS RELAXED mode: loop may exit via explicitly unvalidated Deterministic gate: SKIPPED
    or Deterministic gate: FAIL path on phase-5.4-approval.md § option 4
    manual-handoff branch

NOTES:
  Validator availability proof: an exit-0 result from running the bootstrap
  validator command (e.g. `cfs validate --version` or `cpt validate --version`)
  confirming no canonical validator route is target-applicable for the current
  written output. Must be recorded explicitly alongside Skip reason and
  Validator-backed evidence note before SKIPPED is accepted as a gate result.
  Consistent with how analyze/phase-2-det-gate.md and
  workflows/generate/error-handling.md handle the SKIPPED path.
```
