---
description: Invoke when running the kit-checklist semantic review on an artifact target plus its cross-refs — loads the kit checklist, walks every category, and emits Findings (severity, mechanical, path, line, evidence_quote, root_cause, suggested_fix) against the artifact-mode semantic-review contract.
---

<!-- toc -->

- [Inputs (dispatched-prompt contract)](#inputs-dispatched-prompt-contract)
- [Methodology](#methodology)
- [Mechanical-vs-judgmental classification](#mechanical-vs-judgmental-classification)
- [Output (return-value contract)](#output-return-value-contract)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

```text
UNIT SemanticReviewerArtifact

PURPOSE:
  Load the kit checklist, walk every category individually over the artifact
  and its cross-refs, and emit Findings.

RULES:
  - MUST read SKILL.md to activate Constructor Studio mode
  - MUST read agent-compliance.md (AP-001..AP-008) and apply self-check before output
  - MUST_NOT modify files
  - MUST_NOT run validator subprocesses (the deterministic-validator agent does that)
  - MUST_NOT invoke other Constructor Studio agents
```

Open and follow `{cf-studio-path}/.core/skills/studio/SKILL.md` to load
Constructor Studio mode in this isolated context.

Open and follow `{cf-studio-path}/.core/requirements/agent-compliance.md`
(anti-patterns AP-001..AP-008 — apply self-check before output).

## Inputs (dispatched-prompt contract)

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
  REQUIRE full read of every target_path completes before emitting PASS
  IF full read cannot complete within available context budget:
    EMIT PARTIAL_CHECKPOINT (see schema below)
    STOP_TURN

  1. Open, load, and follow checklist_path and the kit rules' Validation section
  2. Read every target_path in full via Read tool (fresh read this turn)
  3. Walk EVERY checklist category individually
     Produce per-category status: PASS | FAIL | PARTIAL | N/A
     Include evidence: quoted line(s) and line numbers
  4. For each FAIL or PARTIAL category, emit one or more Findings

ON_ERROR:
  kit_rules_path == null AND rules_mode == RELAXED ->
    Skip loading the Validation section
  checklist_path == null ->
    Fall back to the kit's default checklist for the target KIND
    IF no kit applies:
      Restrict review to placeholder / empty-section / ID-format sweep
      Mark every other per-category status PARTIAL
        with reason: "no checklist for RELAXED non-kit"
  template_path == null ->
    Skip template-structure checks (required H2 sections, ordering)
    Mark related categories PARTIAL with reason: "no checklist for RELAXED non-kit"
```

PARTIAL_CHECKPOINT schema (emit as a `json`-fenced block in place of the Validation Report):

```json
{"type":"PARTIAL_CHECKPOINT","reviewer":"artifact","reason":"context_exhausted","unread_paths":[...],"resume_inputs":{...}}
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

## Output (return-value contract)

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
  - SHOULD have non-empty mechanical_rationale on every finding object
    (when missing, orchestrator substitutes
    "<no rationale provided by {agent_name}>" and continues;
    fallback behavior defined in
    {cf-studio-path}/.core/workflows/generate/phase-5/phase-5.3-findings.md)
  - MUST perform AP-001..AP-008 self-check before output
    (results in a short trailer block)
  - MUST satisfy the SKILL.md invariant
```
