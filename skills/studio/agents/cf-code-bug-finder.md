---
description: Invoke when running the code bug-finding methodology on code targets — loads only bug-finding.md and emits Findings for correctness, logic, reliability, security, concurrency, performance, and integration defects.
---

<!-- toc -->

- [Frozen Input Payload](#frozen-input-payload)
- [Methodology](#methodology)
- [Output Contract](#output-contract)
- [Additional Output Sections](#additional-output-sections)
  - [Hotspot Table](#hotspot-table)
  - [Residual Risk Summary](#residual-risk-summary)
- [PARTIAL_CHECKPOINT](#partialcheckpoint)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

## Dispatch Generator Contract

This file is a controller-side prompt generator source, not a runtime prompt for the dispatched sub-agent.

The controller MUST use this file to synthesize the final dispatch prompt for
the agent. The final prompt MUST include the task statement, frozen input
payload, task-relevant instruction assets resolved from `SHARED_CONTEXT_PACK`,
allowed resource metadata/path list, output contract, completion gate, and the explicit
rule that the dispatched sub-agent executes only that final prompt.

The dispatched sub-agent MUST NOT open prompt assets from disk and MUST NOT
rediscover workflows, requirements, specs, AGENTS, SKILL, or kit prompt files.
Files listed in `code_paths`, `cross_ref_paths`, or `design_artifact_path` are
reviewed resources: the controller MUST pass them only as paths plus
metadata/summaries and MUST NOT inline their file bodies into the dispatch
prompt. Instruction assets may be inlined from `SHARED_CONTEXT_PACK` only when
they are checklist, template, example, kit rules, methodology, output contract,
or required studio invariants.


## Frozen Input Payload

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

```pdsl
UNIT CodeBugFinderMethodology

PURPOSE:
  Execute ordered inspection steps over all code paths.

DO:
  - RUN Load `requirements/bug-finding.md` via the controller-supplied
     `bug_finding_methodology` asset
  - RUN Read design_artifact_path fresh via tool/disk access when provided
  - RUN 2a. Read every cross_ref_path fresh via tool/disk access when provided; extract interface contracts,
      invariants, and integration assumptions for the integration-defect sweep
  - RUN Read every code_path in full via Read tool (fresh read this turn)
     WHEN diff_scope is supplied:
       use diff_scope.review_targets and per-file status/commits metadata
       to prioritize paths
       NOTE: changed_hunks/risk_hotspots are reserved for alternate diff
             sources and may be empty
  - RUN Run: hotspot mapping, invariant extraction, failure-path exploration,
     bug-class sweep, counterexample construction, dynamic-escalation review
  - RUN Emit Findings for confirmed or high-confidence bugs only
```

## Output Contract

Emit `Validation Report — Code Bug Section` markdown followed by findings JSON:

```json
[
  { "id": "F-001", "severity": "CRITICAL|MAJOR|MINOR", "mechanical": false,
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

```pdsl
RULES:
  - ALWAYS use one of: correctness | safety | concurrency | performance | security
```

### Residual Risk Summary

After the hotspot table, emit a 1-3 sentence paragraph naming which risk classes
were NOT exhaustively covered (e.g., due to context budget) and how the caller
should reason about remaining exposure.

## PARTIAL_CHECKPOINT

```pdsl
UNIT CfCodeBugFinderPartialCheckpoint

PURPOSE:
  Emit a checkpoint when context budget is exhausted before all code_paths
  are read, rather than risk truncated output.

DO:
  - SET PARTIAL_CHECKPOINT_TARGETS = code_paths
  - SET PARTIAL_CHECKPOINT_SECTION = Partial Checkpoint — Bug Section
  - SET PARTIAL_CHECKPOINT_JSON = partial checkpoint JSON
  - SET PARTIAL_CHECKPOINT_FINDINGS = disabled
  - LOAD {cf-studio-path}/.core/skills/studio/agents/shared/context-budget-partial-checkpoint.md
  - CONTINUE SharedContextBudgetPartialCheckpoint

RULES:
  - ALWAYS the partial checkpoint JSON follow the schema below
  - ALWAYS SharedContextBudgetPartialCheckpoint remains terminal and ends with STOP_TURN
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

```pdsl
UNIT CodeBugFinderCompletionGate

PURPOSE:
  Enforce that the response reaches one of two valid terminal states.

RULES:
  - ALWAYS reach exactly one terminal state before responding
  - NEVER mix complete-run output and partial-checkpoint output in the same response
  - ALWAYS fail closed with complete-run FAIL output when authoritative evidence
    for any reviewed file was supplied inline instead of read fresh from
    `design_artifact_path` / `code_paths` / `cross_ref_paths`; categorize it as
    an orchestration contract violation
  - ALWAYS AP/self-check trailer explicitly state that all
    `design_artifact_path`, `code_paths`, and `cross_ref_paths` used as
    authoritative evidence were read fresh via tool/disk access this turn

MENU TerminalStates:
  OPTIONS:
    1 complete_run ->
      REQUIRE hotspot table is present (per Additional Output Sections)
      REQUIRE findings JSON is present
      REQUIRE residual risk summary is present
      REQUIRE AP-001..AP-008 self-check performed after all findings/table/summary
      REQUIRE {cf-studio-path}/.core/skills/studio/SKILL.md invariant satisfied
    2 partial_run ->
      REQUIRE PARTIAL_CHECKPOINT JSON is present with:
        covered_paths, pending_paths, findings_so_far,
        hotspot_table_so_far, residual_risk_so_far, resume_instructions
      NEVER PASS claim or complete-run claim for uncovered paths
```
