---
description: Invoke when cross-checking terminology, references, normative claims, and scope across ≥ 2 target documents — loads consistency-checklist and emits Findings against the consistency contract.
---

<!-- toc -->

- [Frozen Input Payload](#frozen-input-payload)
- [Methodology](#methodology)
- [Mechanical-vs-judgmental classification](#mechanical-vs-judgmental-classification)
- [Output Contract](#output-contract)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

## Dispatch Generator Contract

This file is a controller-side prompt generator source, not a runtime prompt for the dispatched sub-agent.

The controller MUST use this file to synthesize the final dispatch prompt for
the agent. The final prompt MUST include the task statement, frozen input
payload, task-relevant instruction assets resolved from `SHARED_CONTEXT_PACK`,
allowed resource context, output contract, completion gate, and the explicit
rule that the dispatched sub-agent executes only that final prompt.

The dispatched sub-agent MUST NOT open prompt assets from disk and MUST NOT
rediscover workflows, requirements, specs, AGENTS, SKILL, or kit prompt files.


## Frozen Input Payload

```json
{
  "target_paths": ["<doc 1>", "<doc 2>"],
  "baseline_path": "<canonical doc to defer to on conflict, or null>",
  "kit_rules_path": "<path or null>",
  "rules_mode": "STRICT|RELAXED",
  "namespace_prefix": "<string or null>"
}
```

```text
UNIT SingleTargetPreconditionGate

PURPOSE:
  Refuse dispatch when the precondition len(target_paths) >= 2 is unmet.

WHEN:
  len(target_paths) < 2

DO:
  EMIT {"type":"VALIDATION_REPORT","status":"SKIPPED","reviewer":"consistency",
        "reason":"single target — consistency review requires >= 2 paths"}
  EMIT Validation Report — Semantic Section block:
    Mark every consistency category as N/A
    Evidence: "single-target dispatch — precondition len(target_paths) >= 2 unmet; refusing to proceed"
  EMIT findings: []
  STOP_TURN

RULES:
  - MUST_NOT attempt cross-document checks on a single document
```

## Methodology

```text
UNIT ContextBudgetFailSafe

PURPOSE:
  Stop safely when context budget is exhausted before all targets are read;
  never emit a PASS verdict on partial coverage.

WHEN:
  full read of every target_path cannot complete within available context budget

DO:
  EMIT {"type":"PARTIAL_CHECKPOINT","reviewer":"consistency",
        "reason":"context_exhausted",
        "unread_paths":[...],
        "resume_inputs":{...}}
  STOP_TURN

RULES:
  - MUST_NOT emit a PASS verdict on partial run
```

```text
UNIT ConsistencyReviewerProcedure

PURPOSE:
  Execute the consistency review methodology.

DO:
  1. Load `consistency_checklist` and `kit_validation_rules`
     when that asset is present
  2. Read every target_path in full via Read tool (fresh read this turn)
     WHEN baseline_path is non-null:
       Treat it as canonical; flag non-baseline document as deviator in any direct conflict
     WHEN baseline_path is null AND target documents make conflicting claims of equal authority:
       Use majority-usage consensus across target_paths
       WHEN evenly-split conflict:
         Flag every involved document
         SET mechanical = false for that finding
  3. Walk EVERY consistency-checklist category individually:
       terminology, cross-reference integrity, contradictory normative claims,
       scope-overlap, and any others the checklist defines
     Produce per-category status (PASS / FAIL / PARTIAL / N/A) with evidence
       (quoted line(s) and line numbers from every involved document)
  4. FOR each FAIL / PARTIAL category:
       Emit one or more Findings citing every conflicting location

RULES:
  - WHEN namespace_prefix is provided:
      Prefix every emitted finding id with {namespace_prefix}-
      (e.g., Rcons-001)
  - WHEN namespace_prefix is not provided:
      Use per-run default (e.g., F-001)
```

## Mechanical-vs-judgmental classification

```text
UNIT MechanicalClassification

PURPOSE:
  Classify each finding as mechanical (deterministic fix) or judgmental.

MENU FindingClassificationRules:
  OPTIONS:
    mechanical_true ->
      IF terminology mismatch with unambiguous canonical form
        (provided by baseline_path or overwhelming majority usage across target_paths)
      OR IF broken cross-reference where resolved target is unambiguous
        (typo, renamed section, removed anchor)
      OR IF duplicate definition of the same identifier across documents
        where one definition is clearly authoritative:
        SET mechanical = true
    mechanical_false ->
      IF contradictory normative claims
      OR IF scope-overlap decisions
      OR IF two documents make competing well-formed claims:
        SET mechanical = false — ALWAYS

RULES:
  - Every Finding MUST include a one-sentence mechanical_rationale:
      Which specific rule above triggered mechanical=true,
      OR which judgment dimension forced mechanical=false
  - The orchestrator surfaces mechanical_rationale verbatim to the user
    for auditing classification before any auto-fix proceeds
```

## Output Contract

```text
UNIT ConsistencyReviewerOutput

PURPOSE:
  Emit the review_result discriminator, then the Validation Report, then findings.

DO:
  EMIT review_result JSON discriminator block before the Validation Report:
    {"type":"VALIDATION_REPORT","status":"PASS|FAIL","reviewer":"consistency"}
  EMIT Validation Report — Semantic Section markdown block:
    Include category table and counts
  EMIT findings JSON block:
    [
      {
        "id": "F-001",
        "severity": "high|medium|low",
        "mechanical": true|false,
        "path": "<file>",
        "line": <int|null>,
        "category": "<consistency-category>",
        "evidence_quote": "<exact text>",
        "root_cause": "<short>",
        "suggested_fix": "<one-line>",
        "mechanical_rationale": "<one-sentence justification>"
      }
    ]

RULES:
  - For multi-document findings:
      List the primary deviator in path/line
      Quote other locations inside evidence_quote with <file>:<line> prefixes
  - Emit findings: [] when all categories PASS
```

## Response Completion Gate

```text
UNIT ConsistencyReviewerCompletionGate

PURPOSE:
  Enforce response completeness before output is considered final.

RULES:
  - MUST have a review_result JSON block
    {"type":"VALIDATION_REPORT","status":"PASS|FAIL","reviewer":"consistency"}
    present before the Validation Report block
  - MUST have per-category status with evidence for every applicable
    consistency-checklist category
  - Every Finding MUST cite every involved document location
  - Every finding object SHOULD have a non-empty mechanical_rationale string
    (advisory — when missing, the orchestrator substitutes
    "<no rationale provided by {agent_name}>" and continues; fallback behavior
    defined in {cf-studio-path}/.core/workflows/generate/phase-5/phase-5.3-findings.md)
  - MUST perform AP-001..AP-008 self-check before output;
    state results in a short trailer block
  - MUST satisfy the SKILL.md invariant
SEE_ALSO: ConsistencyReviewerOutput
```
