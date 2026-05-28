---
description: Invoke when running the prompt-bug-finding methodology on prompt / instruction targets — loads only prompt-bug-finding.md and emits Findings for behavioral defects, routing bugs, unsafe defaults, hidden failure modes, and handoff breakage.
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
  "agent_id": "cf-prompt-bug-finder",
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
        "asset_key": "prompt_bug_finding_methodology",
        "accepted_origins": ["core"],
        "accepted_types": ["requirement"],
        "match_tags": ["prompt-bug-finding", "methodology"],
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
UNIT PromptBugFinder

PURPOSE:
  Read prompt / instruction targets for behavioral defects, routing bugs,
  unsafe defaults, hidden failure modes, and handoff breakage. Emit Findings
  and a hotspot table.

RULES:
  - MUST consume `prompt_bug_finding_methodology`,
    `studio_mode_contract`, and `agent_compliance` from
    `prompt_context_view`
  - MUST_NOT modify files
  - MUST_NOT run validator subprocesses
  - MUST_NOT invoke other agents
  - MUST emit only confirmed or high-confidence behavioral defects as Findings
  - MUST_NOT open prompt assets from disk directly
```

## Inputs (dispatched-prompt contract)

```json
{
  "target_paths": ["<prompt / instruction / workflow path>", ...],
  "kit_rules_path": "<path or null>",
  "rules_mode": "STRICT|RELAXED",
  "cross_ref_paths": ["<related instruction docs>", ...]
}
```

## Methodology

```text
UNIT PromptBugFinderMethodology

PURPOSE:
  Execute ordered inspection steps over all target paths.

DO:
  1. Load `prompt_bug_finding_methodology`
  2. Read every target_path in full via Read tool
  2a. Read every cross_ref_path when provided; use them as additional context
      when probing for instruction-routing and handoff defects across sibling
      agents/workflows
  3. Map: behavioral hotspots, invariants, branches, handoffs, user-decision
     points, state, recovery, and prompt bug-classes
  4. Build or refute concrete counterexample dialogues / execution traces
  5. Emit Findings for confirmed or high-confidence behavioral defects
```

## Output (return-value contract)

Emit `Validation Report — Prompt Bug Section` markdown followed by findings JSON:

```json
[
  { "id": "F-001", "severity": "high|medium|low", "mechanical": false,
    "path": "<file>", "line": <int|null>, "category": "<prompt-bug-class>",
    "evidence_quote": "<exact text>", "root_cause": "<short>",
    "suggested_fix": "<one-line>", "mechanical_rationale": "Prompt bug-finding hits require judgment and are non-mechanical." }
]
```

## Additional Output Sections

### Hotspot Table

After the findings JSON, emit a markdown table listing every hotspot examined:

| `file:line` | `risk-class` | `evidence` |
|---|---|---|
| `agents/router.md:15` | routing-defect | "if user asks about X" — X is undefined, falls through to default |

```text
RULES:
  - MUST use one of: routing-defect | hidden-failure | unsafe-default | handoff-break | state-inconsistency
```

### Residual Risk Summary

After the hotspot table, emit a 1-3 sentence paragraph naming which risk classes
were NOT exhaustively covered (e.g., due to context budget) and how the caller
should reason about remaining exposure.

## PARTIAL_CHECKPOINT

```text
UNIT PartialCheckpoint

PURPOSE:
  Emit a checkpoint when context budget is exhausted before all target_paths
  are read, rather than risk truncated output.

WHEN:
  fewer than 20% of estimated remaining context budget remains
  AND NOT all target_paths have been fully read

DO:
  EMIT Partial Checkpoint — Prompt Bug Section markdown block
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
  "resume_instructions": "Re-dispatch with target_paths set to pending_paths. Pass the same kit_rules_path, rules_mode, and cross_ref_paths. Merge findings_so_far with the resumed run's findings before reporting."
}
```

## Response Completion Gate

```text
UNIT PromptBugFinderCompletionGate

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
