---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when each Phase 5 iteration begins and the deterministic validator must run before any semantic reviewer dispatch.
---

### Phase 5.1: Deterministic Gate

<!-- The `Validation Results` block schema is owned by the deterministic-validator agent file (`{cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md` § Output). Workflows reference it by name only; do NOT redefine the field set here — always reproduce the template from the agent file verbatim. -->

```text
UNIT Phase51DeterministicGate

PURPOSE:
  Dispatch cf-deterministic-validator and route based on gate result.

DO:
  REQUIRE `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md` loaded before dispatch
  DISPATCH cf-deterministic-validator with JSON contract from
    {cf-studio-path}/.core/skills/studio/agents/cf-deterministic-validator.md
  WITH orchestrator-supplied values:
    target_paths = Phase 5 target_paths state on external analyze→generate entry;
                   otherwise manifest.paths_written from phase-4-write.md
                   (or last accepted manifest from prior iteration)
    target_kinds = { "<path>": "{TARGET_TYPE}" } per path
    rules_mode = {STRICT|RELAXED}
    language_check_configured = true|false from .studio-workspace.toml

  CAPTURE returned Validation Results block and det_findings JSON array

  APPEND phase5_dispatch_evidence record:
    phase = "5.1"
    agent_id = "cf-deterministic-validator"
    target_paths = target_paths
    result_marker = returned Validation Results marker

MENU Det51Routing:
  TITLE: Deterministic gate routing (machine reference)
  OPTIONS:
    PASS or SKIPPED (with Validator availability proof) ->
      CONTINUE workflows/generate/phase-5/phase-5.2-semantic.md
    FAIL ->
      SET all_findings = det_findings
      SKIP workflows/generate/phase-5/phase-5.2-semantic.md
      CONTINUE workflows/generate/phase-5/phase-5.3-findings.md

RULES:
  - STRICT mode: gate result is authoritative
  - RELAXED mode: loop may exit via explicitly unvalidated Deterministic gate: SKIPPED
    or Deterministic gate: FAIL path on phase-5.4-approval.md § option 4
    manual-handoff branch
```
