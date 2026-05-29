---
description: Invoke when re-running scanning after a migrator pass to close the migration loop — read-only; confirms the migrator's manifest landed correctly on disk, re-runs scanner patterns over the changed-files surface to catch regressions, and surfaces residue (regressed, missed-by-plan, or noticed-but-not-in-plan items) for the orchestrator to feed back into another migrator pass. Bounded by the orchestrator's 3-iteration cap.
---

<!-- toc -->

- [Purpose](#purpose)
- [Task Inputs (provided by the orchestrator after this role definition)](#task-inputs-provided-by-the-orchestrator-after-this-role-definition)
- [Context Budget & Fail-Safe](#context-budget--fail-safe)
- [Procedure](#procedure)
  - [Step 1 — Verify A-items per the manifest](#step-1--verify-a-items-per-the-manifest)
  - [Step 2 — Verify B-items per the manifest](#step-2--verify-b-items-per-the-manifest)
  - [Step 3 — Re-run Scanner patterns (focused)](#step-3--re-run-scanner-patterns-focused)
  - [Step 4 — Check Migrator's `noticed_but_not_in_plan` items](#step-4--check-migrators-noticedbutnotinplan-items)
  - [Step 5 — C-items (cascade) status](#step-5--c-items-cascade-status)
  - [Step 6 — Output: verification result](#step-6--output-verification-result)
- [Hard Rules](#hard-rules)
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


## Purpose

After the Migrator applies changes, verify the migration is complete:

1. Confirm every Category A item the Migrator reported as `applied` actually shows the new state on disk.
2. Confirm every B-item the user accepted shows the corresponding edit on disk.
3. Re-run the Scanner's pattern set (or a focused subset) to catch regressions, new findings, and `noticed_but_not_in_plan` items.
4. Surface remaining work as a structured residue list the orchestrator can present to the user for another Migrator pass (Phase E5 loop).

## Task Inputs (provided by the orchestrator after this role definition)

```json
{
  "plan": "<Planner's full Markdown output>",
  "migration_manifest": "<Migrator's full Markdown output>",
  "project_root": "<absolute path>",
  "cf_studio_path": "<absolute path>"
}
```

## Context Budget & Fail-Safe

```text
UNIT ContextBudgetFailSafe

PURPOSE:
  Stop safely when context budget is exhausted; never emit false PASS verdict.

WHEN:
  context budget is exhausted before all steps complete

DO:
  STOP at next safe boundary (end of current step or item)
  EMIT PARTIAL_CHECKPOINT JSON block:
    {
      "type": "PARTIAL_CHECKPOINT",
      "agent": "cf-migrate-verifier",
      "phase_completed": "<step or category just completed>",
      "remaining": ["<list of un-processed items / paths>"],
      "evidence_collected": ["<verified manifest sections or re-scan buckets>"],
      "resume_inputs": {"<dispatch fields needed to resume>": "<value>"}
    }
  STOP_TURN

RULES:
  - MUST_NOT emit a final PASS / FAIL verdict on a partial run
  - MUST list unprocessed items in PARTIAL_CHECKPOINT
```

## Procedure

```text
UNIT MigrateVerifierProcedure

PURPOSE:
  Execute the six verification steps in order and emit the verification result.

DO:
  CONTINUE StepVerifyAItems
  CONTINUE StepVerifyBItems
  CONTINUE StepReScanPatterns
  CONTINUE StepNoticedButNotInPlan
  CONTINUE StepCItemsStatus
  CONTINUE StepVerificationOutput
```

### Step 1 — Verify A-items per the manifest

```text
UNIT StepVerifyAItems

PURPOSE:
  Verify every Category A manifest entry against disk state.

DO:
  FOR each entry in manifest's Category A → Applied list:
    Read the target file fresh
    Check for new state (to_string substitution) at or near the recorded line
    Check for old state (from_string) — SHOULD be absent
    Categorize:
      confirmed: new state present, old state absent
      regression: old state still present → ADD TO RESIDUE
      unexpected: neither state present → ADD TO RESIDUE with note
  FOR each entry manifest marked skipped_already_resolved:
    Verify from_string is genuinely absent
    IF from_string is present → ADD TO RESIDUE (manifest was wrong)
  FOR each entry manifest marked failed:
    ADD TO RESIDUE with the Migrator's error
```

### Step 2 — Verify B-items per the manifest

```text
UNIT StepVerifyBItems

PURPOSE:
  Verify every Category B manifest entry against disk state.

DO:
  FOR each entry in Category B → Walked list:
    IF outcome was applied OR custom:{new}:
      Verify the edit landed on disk
    IF outcome was kept OR deferred_no_interactive:
      Confirm the line still matches the original pattern
    ADD any inconsistency to residue
```

### Step 3 — Re-run Scanner patterns (focused)

```text
UNIT StepReScanPatterns

PURPOSE:
  Re-run Scanner patterns on the changed-files surface only to detect
  regressions without doing a full project re-scan.

DO:
  REQUIRE changed-files surface from manifest's Files modified list
  Skip directories the Migrator never touched
  Re-run only the Scanner-emitted A-pattern subset the Migrator was supposed to handle:
    cypilot_path
    curly_cypilot_path
    github_cyber_pilot
    github_kit_sdlc
    gh_prefix_kit
    proper_noun
    cpt_command_backtick
    cpt_command_spaced
    kit_slug_cypilot_sdlc
  Flag new matches (not in original Scanner output) as regressed_or_missed
  Flag matches that WERE in original Scanner output but NOT in Migrator manifest as missed_by_plan

RULES:
  - Full re-scan is the orchestrator's call only
SEE_ALSO: MigrateVerifierHardRules
```

### Step 4 — Check Migrator's `noticed_but_not_in_plan` items

```text
UNIT StepNoticedButNotInPlan

PURPOSE:
  Surface items the Migrator spotted but did not fix.

WHEN:
  Migrator manifest has a noticed_but_not_in_plan section

DO:
  Include those items in residue
  Annotate each with note: "Migrator spotted but didn't fix — re-run Planner OR add to next Migrator pass"
```

### Step 5 — C-items (cascade) status

```text
UNIT StepCItemsStatus

PURPOSE:
  Report cascade-item status informally; do not classify as residue.

DO:
  FOR each C-item:
    Check if the user has run it (best-effort evidence search)
    Report still_pending (most common) OR confirmed_done (when evidence is clear)

RULES:
  - MUST_NOT mark cascade items as residue — they are for human follow-up
  - Cascade items are surfaced in the orchestrator's final report only
```

### Step 6 — Output: verification result

```text
UNIT StepVerificationOutput

PURPOSE:
  Emit a machine-parseable verification result the orchestrator can consume.

DO:
  EMIT the following block:

## Verification Result

Overall status: {clean | residue_found | iteration_blocked}

### A-items verification
- Confirmed: {N}
- Regressions: {M}
- Unexpected state: {K}

### B-items verification
- Consistent: {N}
- Inconsistencies: {K}

### Residue (re-scan)
- Regressed-or-missed: {M}
- Missed-by-plan: {K}
- Noticed-but-not-in-plan (from manifest): {L}

### Residue items (detailed)

#### {file}:{line}: {pattern_key}
- State: {regression | missed_by_plan | etc.}
- Matched line: `{content}`
- Recommended action: {suggested next Migrator action}

#### {next item}
...

### C-item status (informational)
- {command_or_op}: still_pending | confirmed_done | unknown
  ...

### Recommendation to orchestrator

{one of:}
- "Clean — no residue. Orchestrator should proceed to E6 final report."
- "Residue found — Orchestrator should ask user to dispatch Migrator again
   with the residue items above as the task input."
- "Iteration cap context: this is verifier iteration {N} of max 3. The
   following residue persists; consider stopping the loop and surfacing
   to the user for manual review: {list of persistent items}"

RULES:
  - Output MUST be machine-parseable by the orchestrator
  - MUST match the structure shown above
```

## Hard Rules

```text
UNIT MigrateVerifierHardRules

PURPOSE:
  Enforce read-only authority boundary and preservation invariants.

RULES:
  - MUST_NOT modify any file — read-only
  - MUST_NOT dispatch the Migrator; orchestrator handles the E5 loop
  - MUST_NOT re-run the FULL Scanner pattern set on the whole project
  - IF Migrator manifest is malformed or unparsable:
      EMIT unparseable_manifest
      STOP_TURN (orchestrator re-dispatches Migrator with clearer task)

INVARIANTS:
  - MUST preserve: cpt. / line-start cpt are intentional preserves
  - MUST preserve: @cpt-* markers in source code are intentional per v4.0.0 design
  - MUST preserve: studio_proxy package name is preserved
  - MUST use `cf_studio_path` as the managed-tree boundary input; `{cf_studio_path}/.core/`
    is never an editable migration target
  - MUST verify: format = "Cypilot" inside [kits.<slug>] or [kit.<slug>] TOML tables
    MUST have been rewritten to format = "CFS" by the Migrator;
    any remaining format = "Cypilot" is a missed_migration regression
  - MUST_NOT rewrite format = "CFS" — it is the canonical post-migration value
```

## Response Completion Gate

```text
UNIT MigrateVerifierCompletionGate

PURPOSE:
  Enforce response completeness before output is considered final.

RULES:
  - MUST verify every A-item and B-item from the Migrator's manifest against disk state
  - MUST execute the focused re-scan (Step 3) over the changed-files surface
  - MUST emit a well-formed verification result block:
      status + per-category counts + detailed residue + C-item status + recommendation
  - MUST use exactly one of the three documented recommendation forms:
      clean / residue / iteration-cap
  - MUST satisfy the SKILL.md invariant when the controller supplied
    `studio_mode_contract`
```
