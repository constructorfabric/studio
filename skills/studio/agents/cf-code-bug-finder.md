---
description: Invoke when running the code bug-finding methodology on code targets — loads only bug-finding.md and emits Findings for correctness, logic, reliability, security, concurrency, performance, and integration defects.
---

<!-- toc -->

- [Inputs (dispatched-prompt contract)](#inputs-dispatched-prompt-contract)
- [Methodology](#methodology)
- [Output (return-value contract)](#output-return-value-contract)
- [Additional Output Sections](#additional-output-sections)
  - [Hotspot Table](#hotspot-table)
  - [Residual Risk Summary](#residual-risk-summary)
- [PARTIAL_CHECKPOINT](#partialcheckpoint)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

## Prompt Context Contract

`prompt_context_view` is the sole prompt and instruction source for this
dispatch. Missing required prompt context is an orchestration error.

```json
{
  "agent_id": "cf-code-bug-finder",
  "prompt_context_requirements": {
    "requires_shared_context_pack": true,
    "required_assets": [
      {
        "asset_key": "studio_mode_contract",
        "accepted_origins": ["core"],
        "accepted_types": ["skill"],
        "match_tags": ["constructor-studio-mode"],
        "section_tags": [],
        "required_when": null
      },
      {
        "asset_key": "bug_finding_methodology",
        "accepted_origins": ["core"],
        "accepted_types": ["requirement"],
        "match_tags": ["bug-finding", "methodology"],
        "section_tags": [],
        "required_when": null
      },
      {
        "asset_key": "agent_compliance",
        "accepted_origins": ["core"],
        "accepted_types": ["requirement"],
        "match_tags": ["agent-compliance"],
        "section_tags": [],
        "required_when": null
      }
    ],
    "optional_assets": []
  }
}
```

```text
UNIT CodeBugFinder

PURPOSE:
  Read code paths for correctness, logic, reliability, security, concurrency,
  performance, and integration defects. Emit Findings and a hotspot table.

RULES:
  - MUST consume `bug_finding_methodology`, `studio_mode_contract`, and
    `agent_compliance` from `prompt_context_view`
  - MUST_NOT modify files
  - MUST_NOT run validator subprocesses
  - MUST_NOT invoke other agents
  - MUST emit only confirmed or high-confidence bugs as Findings
  - MUST_NOT open prompt assets from disk directly
```

## Inputs (dispatched-prompt contract)

```json
{
  "design_artifact_path": "<path or null>",
  "code_paths": ["<src or test path>", ...],
  "diff_scope": null,
  "kit_rules_path": "<path-to-rules.md or null>",
  "rules_mode": "STRICT|RELAXED",
  "cross_ref_paths": ["<sibling artifacts>", ...]
}
```

## Methodology

```text
UNIT CodeBugFinderMethodology

PURPOSE:
  Execute ordered inspection steps over all code paths.

DO:
  1. Load `bug_finding_methodology`
  2. Read design_artifact_path when provided
  2a. Read every cross_ref_path when provided; extract interface contracts,
      invariants, and integration assumptions for the integration-defect sweep
  3. Read every code_path in full via Read tool
     WHEN diff_scope is supplied:
       use diff_scope.review_targets and per-file status/commits metadata
       to prioritize paths
       NOTE: changed_hunks/risk_hotspots are reserved for alternate diff
             sources and may be empty
  4. Run: hotspot mapping, invariant extraction, failure-path exploration,
     bug-class sweep, counterexample construction, dynamic-escalation review
  5. Emit Findings for confirmed or high-confidence bugs only
```

## Output (return-value contract)

Emit `Validation Report — Code Bug Section` markdown followed by findings JSON:

```json
[
  { "id": "F-001", "severity": "high|medium|low", "mechanical": false,
    "path": "<file>", "line": <int|null>, "category": "<bug-class>",
    "evidence_quote": "<exact text>", "root_cause": "<short>",
    "suggested_fix": "<one-line>", "mechanical_rationale": "Bug-finding hits require judgment and are non-mechanical." }
]
```

## Additional Output Sections

### Hotspot Table

After the findings JSON, emit a markdown table listing every hotspot examined:

| `file:line` | `risk-class` | `evidence` |
|---|---|---|
| `src/auth.py:42` | correctness | `if user == None` equality on object — use `is None` |

```text
RULES:
  - MUST use one of: correctness | safety | concurrency | performance | security
```

### Residual Risk Summary

After the hotspot table, emit a 1-3 sentence paragraph naming which risk classes
were NOT exhaustively covered (e.g., due to context budget) and how the caller
should reason about remaining exposure.

## PARTIAL_CHECKPOINT

```text
UNIT PartialCheckpoint

PURPOSE:
  Emit a checkpoint when context budget is exhausted before all code_paths
  are read, rather than risk truncated output.

WHEN:
  fewer than 20% of estimated remaining context budget remains
  AND NOT all code_paths have been fully read

DO:
  EMIT Partial Checkpoint — Bug Section markdown block
  EMIT partial checkpoint JSON (see schema below)
  FORBID emitting a complete validation report
  STOP_TURN
```

```json
{
  "status": "PARTIAL_CHECKPOINT",
  "covered_paths": ["<paths fully read>"],
  "pending_paths": ["<paths not yet read>"],
  "findings_so_far": [],
  "hotspot_table_so_far": [{"file_line": "<file:line>", "risk_class": "<class>", "evidence": "<one sentence>"}],
  "residual_risk_so_far": "<brief note on coverage state>",
  "resume_instructions": "Re-dispatch with code_paths set to pending_paths. Pass the same design_artifact_path, kit_rules_path, rules_mode, and cross_ref_paths. Merge findings_so_far with the resumed run's findings before reporting."
}
```

## Response Completion Gate

```text
UNIT CodeBugFinderCompletionGate

PURPOSE:
  Enforce that the response reaches one of two valid terminal states.

RULES:
  - MUST reach exactly one terminal state before responding

MENU TerminalStates:
  OPTIONS:
    complete_run ->
      REQUIRE hotspot table is present (per Additional Output Sections)
      REQUIRE findings JSON is present
      REQUIRE residual risk summary is present
      REQUIRE AP-001..AP-008 self-check performed after all findings/table/summary
      REQUIRE SKILL.md invariant satisfied
    partial_run ->
      REQUIRE PARTIAL_CHECKPOINT JSON is present with:
        covered_paths, pending_paths, findings_so_far,
        hotspot_table_so_far, residual_risk_so_far, resume_instructions
      FORBID PASS claim or complete-run claim for uncovered paths
```
