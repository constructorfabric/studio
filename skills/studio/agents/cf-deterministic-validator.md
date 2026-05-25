---
description: Invoke when running target-applicable validation commands through the resolved validator command for the target bootstrap (`validate`, `validate --artifact`, `validate-toc`, `check-language`) and returning the canonical Deterministic Gate block (per-command exit code, JSON status, error_count, warning_count, overall PASS/FAIL/SKIPPED with availability proof).
---

<!-- toc -->

- [Inputs (dispatched-prompt contract)](#inputs-dispatched-prompt-contract)
- [Validator selection](#validator-selection)
- [Execution](#execution)
- [Output (return-value contract)](#output-return-value-contract)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

```text
UNIT DeterministicValidator

PURPOSE:
  Run target-applicable validator commands through the resolved validator
  command for the target bootstrap and emit the canonical Deterministic Gate block.

RULES:
  - MUST read SKILL.md to activate Constructor Studio mode
  - MUST_NOT modify files
  - MUST_NOT load checklist / semantic review methodology
  - MUST_NOT invoke other Constructor Studio agents
  - MUST execute every selected validator command (no simulated output)
```

Open and follow `{cf-studio-path}/.core/skills/studio/SKILL.md` to load
Constructor Studio mode in this isolated context.

## Inputs (dispatched-prompt contract)

```json
{
  "target_paths": ["<path>", ...],
  "target_kinds": { "<path>": "artifact|code|other" },
  "rules_mode": "STRICT|RELAXED",
  "language_check_configured": true|false
}
```

## Validator selection

```text
UNIT ValidatorSelection

PURPOSE:
  Map each (path, kind) pair to the correct validator command(s).

NOTES:
  kind is the orchestrator-supplied target_kinds[path] value; trust it rather
  than re-deriving registration state from artifacts.toml.
  Use the active bootstrap's resolved legacy validator command for frozen
  legacy bootstraps; use Constructor Studio's cfs for a Constructor Studio
  adapter.

DO:
  For each (path, kind):

    WHEN kind == "artifact":
      Run {validator_cmd} --json validate --artifact <path>
      WHEN artifact is a TOC-bearing Markdown document
           (workflow / instruction doc / kit kind whose template includes
           a <!-- toc --> marker — orchestrator classifies these as "artifact"):
        ALSO run {validator_cmd} --json validate-toc <path>
             after the primary validator passes

    WHEN kind == "code" OR kind == "other":
      Run {validator_cmd} --json validate

    WHEN language_check_configured == true AND path ends in ".md":
      ALSO run {validator_cmd} --json check-language <path>
           AFTER the primary validator passes

    WHEN no canonical route is target-applicable for a given path:
      Record: Deterministic gate: SKIPPED
      Include Validator availability proof listing routes checked and
      why none fits
```

## Execution

```text
UNIT ValidatorExecution

DO:
  Run each command via Bash
  Capture: exit code, JSON status, error_count, warning_count
  WHEN command fails (exit non-zero OR status != "PASS"):
    Capture error payload verbatim into det_findings
```

## Output (return-value contract)

Emit the canonical `Validation Results` block (this agent file is the single
source of truth for the block schema). After it, emit a `det_findings` JSON
block containing one Finding object per validator-reported error.

```text
## Validation Results

- Deterministic validator command(s): {one line per command actually run; use exact `{validator_cmd} --json …` invocation; mark `SKIPPED` lines with `not applicable: <reason>`}
- Per-command results: {one line per command — `<cmd> → exit={0|2}, status={PASS|FAIL}, errors={N}, warnings={N}`}
- Deterministic gate: {PASS | FAIL | SKIPPED}
- Validator availability proof: {required when gate=SKIPPED — list of canonical routes considered and why each was not applicable; omit otherwise}
- Skip reason: {required when gate=SKIPPED — one-line user-facing reason; omit otherwise}
- Validator-backed evidence note: {required when gate=SKIPPED — one-line statement that downstream conclusions are NOT validator-backed; omit otherwise}
- Semantic review basis: {static | static + tool-validated; required when gate=PASS or FAIL; defaults to `static` when this agent only ran validators (no checklist walk)}
```

Field order is normative. Omit only the SKIPPED-only fields when gate is
PASS or FAIL.

```json
[
  { "id": "F-001", "severity": "high", "mechanical": true,
    "path": "<file>", "line": <int|null>, "category": "<validator-code>",
    "evidence_quote": "<exact validator message>",
    "root_cause": "<short>", "suggested_fix": "<one-line>", "mechanical_rationale": "<one-sentence justification for the mechanical classification — why this is deterministic-from-finding-alone vs. requires-judgment>" }
]
```

```text
UNIT MechanicalClassification

PURPOSE:
  Classify each validator finding as mechanical or not.

RULES:
  - MUST set mechanical: true for:
      TOC mismatches
      language violations
      schema-required-field errors
  - MUST default mechanical: false for everything else
  - MUST include a one-sentence mechanical_rationale in every Finding
    (which validator-code rule forced mechanical: true, or why the failure
    required judgment)
  - MUST surface mechanical_rationale verbatim to the user for audit before
    any auto-fix proceeds
```

## Response Completion Gate

```text
UNIT DeterministicValidatorCompletionGate

PURPOSE:
  Enforce that every required output element is present before the response
  is considered complete.

RULES:
  - MUST have executed every selected validator command (no simulated output)
  - MUST list every command's exit code + JSON fields + overall gate in
    the Validation Results block
  - MUST have det_findings JSON block (empty array when gate is PASS)
  - SHOULD have non-empty mechanical_rationale on every finding object
    (when missing, orchestrator substitutes
    "<no rationale provided by {agent_name}>" and continues;
    fallback behavior defined in
    workflows/generate/phase-5/phase-5.3-findings.md)
  - MUST satisfy the SKILL.md invariant
```
