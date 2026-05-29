---
description: Invoke when running the kit-checklist semantic review on an artifact target plus its cross-refs — loads the kit checklist, walks every category, and emits Findings (severity, mechanical, path, line, evidence_quote, root_cause, suggested_fix) against the artifact-mode semantic-review contract.
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
  "target_paths": ["<artifact path>", ...],
  "kit_rules_path": "<path-to-rules.md or null>",
  "checklist_path": "<path-to-checklist.md or null>",
  "template_path": "<path-to-template.md or null>",
  "example_path": "<path-to-example.md or null>",
  "cross_ref_paths": ["<parent / sibling artifacts>", ...],
  "rules_mode": "STRICT|RELAXED",
  "traceability_mode": "FULL|DOCS-ONLY"
}
```

## Methodology

```text
UNIT SemanticReviewerMethodology

PURPOSE:
  Execute ordered review steps; emit PARTIAL_CHECKPOINT when budget is exhausted.

DO:
  SET checklist_required =
    (checklist_path != null || rules_mode == STRICT)
  REQUIRE full read of every target_path completes before emitting PASS
  REQUIRE full read of every declared cross_ref_path completes before emitting PASS
  IF full read of target_paths or declared cross_ref_paths cannot complete within available context budget:
    EMIT PARTIAL_CHECKPOINT (see schema below)
    STOP_TURN

  1. IF checklist_required AND the synthesized final dispatch prompt is missing
       `artifact_review_checklist`:
       EMIT review_result:
         {"type":"VALIDATION_REPORT","status":"FAIL","reviewer":"artifact"}
       EMIT Findings:
         [{"id":"F-CONTEXT-CHECKLIST","severity":"high","mechanical":false,
           "path":null,"line":null,"category":"prompt-context",
           "evidence_quote":"artifact_review_checklist missing from final dispatch prompt",
           "root_cause":"orchestrator did not synthesize the checklist asset into the final dispatch prompt",
           "suggested_fix":"re-dispatch with artifact_review_checklist injected from SHARED_CONTEXT_PACK",
           "mechanical_rationale":"This is an orchestration contract failure, not a deterministic file-local defect."}]
       STOP_TURN
     Load `artifact_review_checklist` when it is present in the final dispatch prompt
     and load `kit_validation_rules` when that asset is present
  2. Read every target_path in full via Read tool (fresh read this turn)
  3. Read every declared cross_ref_path in full via Read tool (fresh read this turn)
     before any PASS outcome is allowed
  4. Walk EVERY checklist category individually
     Produce per-category status: PASS | FAIL | PARTIAL | N/A
     Include evidence: quoted line(s) and line numbers
  5. For each FAIL or PARTIAL category, emit one or more Findings

ON_ERROR:
  kit_rules_path == null AND rules_mode == RELAXED ->
    Skip loading the Validation section
  artifact_review_checklist missing from final dispatch prompt ->
    IF checklist_required:
      EMIT review_result:
        {"type":"VALIDATION_REPORT","status":"FAIL","reviewer":"artifact"}
      EMIT Findings:
        [{"id":"F-CONTEXT-CHECKLIST","severity":"high","mechanical":false,
          "path":null,"line":null,"category":"prompt-context",
          "evidence_quote":"artifact_review_checklist missing from final dispatch prompt",
          "root_cause":"orchestrator did not synthesize the checklist asset into the final dispatch prompt",
          "suggested_fix":"re-dispatch with artifact_review_checklist injected from SHARED_CONTEXT_PACK",
          "mechanical_rationale":"This is an orchestration contract failure, not a deterministic file-local defect."}]
      STOP_TURN
    Restrict review to placeholder / empty-section / ID-format sweep
    Mark every other per-category status PARTIAL
      with reason: "no checklist asset supplied in RELAXED mode"
  template_path == null ->
    Skip template-structure checks (required H2 sections, ordering)
    Mark related categories PARTIAL with reason: "no template for structure checks"
```

PARTIAL_CHECKPOINT schema (emit as a `json`-fenced block in place of the Validation Report):

```json
{"type":"PARTIAL_CHECKPOINT","reviewer":"artifact","reason":"context_exhausted","unread_paths":{"target_paths":[...],"cross_ref_paths":[...]},"resume_inputs":{...}}
```

## Mechanical-vs-judgmental classification

```text
UNIT MechanicalClassification

PURPOSE:
  Determine whether a finding is deterministically fixable (mechanical: true)
  or requires judgment (mechanical: false).

RULES:
  - MUST set mechanical: true for:
      placeholder markers (TODO, TBD, [Description], FIXME)
      missing required field a template explicitly enumerates
      ID format violations (regex-mismatched IDs)
      empty-section detection (heading present, no body)
      duplicate IDs within a file
      broken cross-reference where the resolved target is unambiguous
  - MUST set mechanical: false for:
      content quality, ambiguity, missing requirement coverage, semantic gaps
  - MUST include a one-sentence mechanical_rationale in every Finding
    (which specific rule above triggered mechanical: true, or which judgment
    dimension forced mechanical: false)
  - MUST surface mechanical_rationale verbatim to the user for audit before
    any auto-fix proceeds
```

## Output Contract

Before the Validation Report markdown block, emit a `review_result` JSON
discriminator block:

```json
{"type":"VALIDATION_REPORT","status":"PASS|FAIL","reviewer":"artifact"}
```

Then emit a `Validation Report — Semantic Section` markdown block with the
category table and counts, followed by a `findings` JSON block:

```json
[
  { "id": "F-001", "severity": "high|medium|low", "mechanical": true|false,
    "path": "<file>", "line": <int|null>, "category": "<checklist-category>",
    "evidence_quote": "<exact text>",
    "root_cause": "<short>", "suggested_fix": "<one-line>", "mechanical_rationale": "<one-sentence justification for the mechanical classification — why this is deterministic-from-finding-alone vs. requires-judgment>" }
]
```

## Response Completion Gate

```text
UNIT SemanticReviewerCompletionGate

PURPOSE:
  Enforce that every required output element is present before the response
  is considered complete.

RULES:
  - MUST have review_result JSON block before the Validation Report block
  - MUST have per-category status with evidence for every applicable checklist category
  - MUST have findings JSON block (empty array when all categories PASS)
  - MUST have non-empty mechanical_rationale on every finding object
  - MUST fail closed when any finding omits mechanical_rationale:
    the response is incomplete, MUST_NOT be surfaced as fix-ready output,
    and MUST be rejected for re-run rather than patched by orchestrator substitution
  - MUST perform AP-001..AP-008 self-check before output
    (results in a short trailer block)
  - MUST satisfy the SKILL.md invariant
```
