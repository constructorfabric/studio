---
description: Invoke when running the code-checklist semantic review on code targets against a design artifact — loads only the code-checklist methodology, walks every category, and emits Findings against the code-checklist review contract.
---

<!-- toc -->

- [Frozen Input Payload](#frozen-input-payload)
- [Methodology](#methodology)
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
  "design_artifact_path": "<path or null>",
  "code_paths": ["<src or test path>", "..."],
  "diff_scope": {
    "changed_files": [],
    "changed_hunks": [],
    "review_targets": [],
    "risk_hotspots": []
  },
  "kit_rules_path": "<path or null>",
  "rules_mode": "STRICT|RELAXED",
  "traceability_mode": "FULL|DOCS-ONLY",
  "cross_ref_paths": ["<sibling artifacts>", "..."]
}
```

## Methodology

```text
UNIT ContextBudgetFailSafe

PURPOSE:
  Stop safely when context budget is exhausted; never emit PASS on partial coverage.

WHEN:
  context exhausted before every code_path is fully read

DO:
  EMIT Partial Checkpoint — Semantic Section markdown block
  EMIT checkpoint JSON block:
    {
      "type": "PARTIAL_CHECKPOINT",
      "status": "PARTIAL",
      "reviewer": "code",
      "unread_files": ["<path>", "..."],
      "uncovered_categories": ["<category>", "..."],
      "covered_files": ["<path>", "..."],
      "covered_categories": ["<category>", "..."],
      "reason": "<why the review could not complete within context>",
      "resume_inputs": {
        "design_artifact_path": "<path or null>",
        "code_paths": ["<remaining or original path>", "..."],
        "diff_scope": {"changed_files": [], "changed_hunks": [],
                       "review_targets": [], "risk_hotspots": []},
        "kit_rules_path": "<path or null>",
        "rules_mode": "STRICT|RELAXED",
        "traceability_mode": "FULL|DOCS-ONLY",
        "cross_ref_paths": ["<path>", "..."]
      }
    }
  EMIT findings: []
    (UNLESS a finding is fully supported by already-covered evidence)
  STOP_TURN

RULES:
  - MUST_NOT emit a PASS verdict on partially-read targets
  - Orchestrator MUST treat type=PARTIAL_CHECKPOINT as incomplete review coverage
  - MUST_NOT collapse PARTIAL_CHECKPOINT into a clean validation report
```

```text
UNIT CodeReviewerProcedure

PURPOSE:
  Execute the code-checklist review methodology.

DO:
  1. Load only `requirements/code-checklist.md` via the controller-supplied
     `code_review_checklist` asset as the review methodology
     Load `kit_validation_rules` only when that asset is present
     REQUIRE ContextBudgetFailSafe is active
  2. Read the design artifact when design_artifact_path is provided
  3. Estimate cumulative size of design_artifact_path + code_paths + cross_ref_paths
     Use chunked reads for files exceeding ~200 lines
     Read every code_path completely, in chunks when needed
     Use diff_scope.changed_hunks and diff_scope.risk_hotspots to prioritize,
       but verify against full files
     WHEN diff_scope is non-null AND diff_scope.review_targets is non-empty:
       Restrict file walking to that set
       Treat diff_scope.changed_files as broader changed-surface context
         when scoping cross-references
  4. Walk every applicable category with status and line-numbered evidence
  5. Emit Findings for FAIL / PARTIAL categories only
```

## Output Contract

```text
UNIT CodeReviewerOutput

PURPOSE:
  Emit exactly one of two caller-visible output shapes:
  VALIDATION_REPORT (complete) or PARTIAL_CHECKPOINT (incomplete).

MENU OutputShape:
  OPTIONS:
    VALIDATION_REPORT ->
      WHEN every required file and category was covered
      EMIT review_result JSON discriminator:
        {"type":"VALIDATION_REPORT","status":"PASS|FAIL","reviewer":"code"}
      EMIT Validation Report — Semantic Section markdown block
      EMIT findings JSON block:
        [
          {
            "id": "F-001",
            "severity": "high|medium|low",
            "mechanical": false,
            "path": "<file>",
            "line": null,
            "category": "<checklist-category>",
            "evidence_quote": "<exact text>",
            "root_cause": "<short>",
            "suggested_fix": "<one-line>",
            "mechanical_rationale": "<classification reason>"
          }
        ]
    PARTIAL_CHECKPOINT ->
      WHEN context-budget fail-safe triggers
      CONTINUE ContextBudgetFailSafe
```

## Response Completion Gate

```text
UNIT CodeReviewerCompletionGate

PURPOSE:
  Enforce response completeness before output is considered final.

RULES:
  - MUST have either:
      review_result.type = "VALIDATION_REPORT" with category evidence
        for every applicable category
      OR checkpoint.type = "PARTIAL_CHECKPOINT" with unread files /
        uncovered categories enumerated and no PASS claim for uncovered categories
  - findings JSON MUST be present in both output shapes
  - AP-001..AP-008 self-check MUST be present
  - MUST satisfy the SKILL.md invariant
```
