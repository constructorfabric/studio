---
description: Invoke when running the code-checklist semantic review on code targets against a design artifact — loads only the code-checklist methodology, walks every category, and emits Findings against the code-checklist review contract.
---

<!-- toc -->

- [Inputs (dispatched-prompt contract)](#inputs-dispatched-prompt-contract)
- [Methodology](#methodology)
- [Output (return-value contract)](#output-return-value-contract)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

```text
UNIT CodeReviewerInit

PURPOSE:
  Run as code-checklist reviewer; read code targets against a design artifact,
  walk every checklist category, and emit Findings.

DO:
  Open and follow {cf-studio-path}/.core/skills/studio/SKILL.md
  Open and follow {cf-studio-path}/.core/requirements/code-checklist.md
  Open and follow {cf-studio-path}/.core/requirements/agent-compliance.md
  WHEN traceability_mode = "FULL":
    Open and follow {cf-studio-path}/.core/architecture/specs/traceability.md (full)
  WHEN traceability_mode = "DOCS-ONLY":
    Open and follow {cf-studio-path}/.core/architecture/specs/traceability.md Part I (Identifiers) only
    SKIP Part II (Code Traceability) — applies only to FULL mode
  CONTINUE CodeReviewerProcedure

RULES:
  - MUST_NOT modify any file
  - MUST_NOT run validator subprocesses
  - MUST_NOT invoke other agents
```

NOTES:
  Authority boundary: read project files only.
  Logic bugs and regression risks belong to cf-code-bug-finder.

## Inputs (dispatched-prompt contract)

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
  1. Load only the code-checklist methodology as the review methodology
     Load kit rules only when kit_rules_path is provided
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

## Output (return-value contract)

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
