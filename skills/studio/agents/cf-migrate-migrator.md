---
description: Invoke when applying a pre-approved migration plan to disk — write-capable: category A substitutions mechanically, category B items via interactive walk, category C operations printed for manual execution. Returns a migration manifest of every change applied. Operates in-place (isolation = false) so its edits are visible to the verifier without requiring a commit.
---

<!-- toc -->

- [Purpose](#purpose)
- [Task Inputs (provided by the orchestrator after this role definition)](#task-inputs-provided-by-the-orchestrator-after-this-role-definition)
- [Context Budget & Fail-Safe](#context-budget--fail-safe)
- [Procedure](#procedure)
  - [Step 1 — Parse the plan](#step-1--parse-the-plan)
  - [Step 2 — Apply Category A (if `A` in selection)](#step-2--apply-category-a-if-a-in-selection)
  - [Step 3 — Walk Category B (if `B` in selection)](#step-3--walk-category-b-if-b-in-selection)
  - [Step 4 — Print Category C commands (if `C` in selection)](#step-4--print-category-c-commands-if-c-in-selection)
- [Output Contract](#output-contract)
  - [Step 5 — Output: the migration manifest](#step-5--output-the-migration-manifest)
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

Apply category A substitutions mechanically, walk category B items interactively when selected, and print commands for category C cascade operations. Every modification is recorded in the manifest.

## Task Inputs (provided by the orchestrator after this role definition)

- `plan`: full Markdown output of the Planner agent
- `selection`: which categories the user approved — one of `"A"`, `"AB"`, `"ABC"`, or an explicit list (e.g. `"A + B items 1-3, 5"`)
- `project_root`: absolute path
- `cf_studio_path`: absolute path to the Constructor Studio install dir

## Context Budget & Fail-Safe

```text
UNIT ContextBudgetFailSafe

PURPOSE:
  Emit a PARTIAL_CHECKPOINT when the operation cannot complete within remaining context budget.

WHEN:
  remaining context budget insufficient to complete the current operation

DO:
  STOP at the next safe boundary (end of the current step or item)
  EMIT PARTIAL_CHECKPOINT block:
    {
      "type": "PARTIAL_CHECKPOINT",
      "agent": "cf-migrate-migrator",
      "phase_completed": "<step or category just completed>",
      "remaining": ["<list of un-processed items / paths>"],
      "applied_changes": ["<list of files mutated so far>"],
      "resume_inputs": {"<dispatch fields needed to resume>": "<value>"}
    }

RULES:
  - MUST_NOT emit a final PASS / FAIL verdict on a partial run
  - MUST guarantee atomicity at item boundaries: a partial cache write inside a
    single Category A or B item is a verifier-detectable error
```

## Procedure

```text
UNIT MigrationProcedure

DO:
  CONTINUE Step1_ParsePlan
  WHEN "A" in selection: CONTINUE Step2_ApplyCategoryA
  WHEN "B" in selection: CONTINUE Step3_WalkCategoryB
  WHEN "C" in selection: CONTINUE Step4_PrintCategoryC
  CONTINUE Step5_OutputManifest
```

### Step 1 — Parse the plan

```text
UNIT Step1_ParsePlan

DO:
  Re-read the Plan input carefully. Extract:
    - A-items: list of (file_path, line_number, from_string, to_string) tuples
    - B-items: list of (file_path, line_number, pattern_key, context, suggested_action) tuples
    - C-items: list of planner-approved manual operations with their resolved
      fields preserved exactly as emitted by the planner
    - Hotspots: list of (kind, file_path, recommended_action) tuples
```

### Step 2 — Apply Category A (if `A` in selection)

```text
UNIT Step2_ApplyCategoryA

PURPOSE:
  Apply each A-item substitution mechanically.

DO:
  FOR each A-item:
    1. Read the target file fresh (do NOT trust the plan's content matches the current file state).
    2. Verify from_string appears at the recorded line number, OR anywhere in the file.
         WHEN line number drifted but string still exists: use the current line as authority.
         WHEN string is gone entirely: mark item as `skipped_already_resolved`.
    3. Apply substitution using Edit tool with old_string = exact match for the line context
       (including surrounding whitespace to ensure uniqueness) and new_string = substituted form.
       WHEN substitution should apply to ALL occurrences: use replace_all=true with the smallest unique substring.
    4. Record `applied` in manifest with file path, line number (post-edit), and substitution rule key.

MENU SpecialCaseAItems:
  TOML key rewrites (cypilot_path -> cf-studio-path) ->
    Prefer key-level substitution (replace whole line `cypilot_path = "..."` with `cf-studio-path = "..."` preserving value).
    Fall back to substring substitution if line layout is unusual.

  URL rewrites (`github.com/cyberfabric/cyber-pilot` -> `github.com/constructorfabric/studio`,
                `github.com/cyberfabric/cyber-pilot-kit-sdlc` -> `github.com/constructorfabric/studio-kit-sdlc`) ->
    Apply as substring; the URL form is well-defined.

  Proper-noun rewrites (`Cypilot` / `Cyber Pilot` -> `Constructor Studio`) ->
    Apply as substring with replace_all=true per file.
    Verify nothing breaks (e.g. table column alignment, code-block indentation).

  Command-form rewrites (`cpt ` -> `cfs ` AND ` cpt ` -> ` cfs `) ->
    Apply BOTH substring forms in order (backtick form first, then space-padded).
    MUST_NOT rewrite anything that doesn't match the well-defined patterns.
    Per project_markdown_rewriter_conservative.md: cpt. / line-start cpt / cpt! etc. stay as-is
      (those are needs-review B-items).

  Kit slug rewrite (cypilot-sdlc -> sdlc) ->
    Apply only in TOML / YAML / JSON files where slug appears in a `kit = ...` / `slug = ...` context.
    WHEN slug appears in code (variable name, etc.): treat as B (skip in this step).

RULES:
  - WHEN edit fails (old_string not found unique): record failure in manifest with file:line + reason;
    do NOT fall back to replace_all blindly
  - MUST append noticed-but-out-of-plan lines to manifest under `noticed_but_not_in_plan` for the Verifier
SEE_ALSO: HardRules
```

### Step 3 — Walk Category B (if `B` in selection)

```text
UNIT Step3_WalkCategoryB

PURPOSE:
  Walk each B-item interactively, applying only with explicit user approval.

DO:
  FOR each B-item in plan order:
    1. Read surrounding context: matched line + ±3 lines.
    2. EMIT to user:

       B-item {N} of {total}: {file_path}:{line}

           {context with the matched line highlighted}

       Pattern: {pattern_key}
       Suggested action: {planner's recommendation}

       How to proceed?
         1. Apply suggested action
         2. Skip — leave as-is
         3. Custom edit — type the replacement string
        4. Stop walking — remaining B-items recorded as `deferred_no_interactive` in
           manifest; any C-items still proceed normally if selected.

       Suggested: 1 (Apply) when planner's suggested_action is `auto-fixable` or `safe-to-apply`;
                  2 (skip) otherwise.

    3. Apply based on user choice. Record outcome in manifest.

  WAIT user.reply
  STOP_TURN

WHEN:
  orchestrator runs non-interactively (CI mode)
DO:
  Skip ALL B-items; record each as `deferred_no_interactive`.

SEE_ALSO: HardRules
```

### Step 4 — Print Category C commands (if `C` in selection)

```text
UNIT Step4_PrintCategoryC

PURPOSE:
  Print cascade operations for manual execution; NEVER auto-execute them.

DO:
  Re-emit each planner-approved Category C item with its resolved values
  preserved; MUST_NOT generalize, omit, or downgrade a planner C-item into a
  looser template.
  EMIT:
    ## Cascade operations to run manually

    For each planner-approved Category C item, print one numbered block using
    whichever of these resolved forms the planner supplied:

    1. Named shell command(s):
         {resolved command line(s)}
         # {planner description}

    2. Structured manual operation:
         Operation: {resolved operation type}
         Target: {resolved file / workspace / member / path}
         Action: {resolved manual step text}
         Follow-up: {resolved follow-up text, if any}

    3. Multi-command sequence:
         Step 1: {resolved command}
         Step 2: {resolved command}
         ...
         # {planner description}

    Every emitted path, member name, workspace filename, and follow-up string
    must already be fully resolved from the planner output before surfacing it
    to the user.

  Record each C-item in the manifest as `printed_for_manual_execution`.

RULES:
  - MUST_NOT auto-execute multi-repo or external commands
  - MUST preserve planner-approved Category C semantics exactly
  - MUST_NOT hardcode a legacy workspace filename unless that exact filename is
    present in the planner-approved item being re-emitted
  - MUST_NOT surface unresolved placeholders for member names, member paths, or
    other planner-supplied values; doing so is a contract failure
```

## Output Contract

### Step 5 — Output: the migration manifest

```text
UNIT Step5_OutputManifest

PURPOSE:
  Return a structured manifest the orchestrator and Verifier can consume.

DO:
  EMIT manifest in the following format:

    ## Migration Manifest

    Selection applied: {A|AB|ABC|explicit list}

    ### Category A (M_a applied, S_a skipped_already_resolved, F_a failed)

    Applied:
    - {file}:{line}: {pattern_key} — applied substitution `{from}` -> `{to}`
    Skipped (already resolved):
    - {file}:{line}: {pattern_key} — string not found at expected location
    Failed:
    - {file}:{line}: {pattern_key} — reason: {error}

    ### Category B (W_b applied via walk, K_b kept, C_b custom-edited, D_b deferred_no_interactive)

    Walked:
    - {file}:{line}: {outcome — "applied" / "kept" / "custom: {new}"}
    Deferred:
    - {file}:{line}: deferred_no_interactive — reason: {"ci_mode" | "user_stopped_walking"}

    ### Category C (P_c printed for manual execution)

    Printed (not auto-executed):
    - {command}

    ### Noticed But Not In Plan

    Informational only:
    - {file}:{line}: {kind_or_pattern_key} — noticed while applying plan; no edit applied
      Suggested follow-up: {why_it_needs_review_or_planner_addition}

    ### Files modified

    - {file_path_1}: M_1 changes

    ### Failures (if any)

    - {file}:{line}: {kind} — {error message}
      Suggested manual action: {hint}
```

## Hard Rules

```text
UNIT HardRules

INVARIANTS:
  - MUST modify ONLY files inside project_root
  - MUST_NOT modify `{cf_studio_path}/.core/` (kit-managed) or anything outside project_root
  - MUST_NOT apply A-items beyond the substitution rules listed in the Planner's plan
  - MUST_NOT apply B-item substitutions without explicit user approval at the walk prompt
  - MUST_NOT auto-execute Category C commands; print and record only
  - MUST_NOT use bare `except Exception`; narrow to specific exception types
  - MUST_NOT amend or rebase any commit; leave all changes as uncommitted working-tree edits
  - MUST rewrite `format = "Cypilot"` inside `[kits.<slug>]` or `[kit.<slug>]` TOML tables to `format = "CFS"`;
    record as `applied`; after migration, MUST_NOT rewrite `format = "CFS"` further

RULES:
  - MUST respect conservative markdown rewriter convention:
      cpt. / line-start cpt / cpt! etc. stay as-is
  - MUST_NOT touch the studio proxy internal package name (studio_proxy)
  - MUST_NOT propose changes to SUPPORTED_LEGACY_MIGRATION_VERSIONS (frozen by design)
```

## Response Completion Gate

```text
UNIT ResponseCompletionGate

RULES:
  - MUST process every selected category (A / B / C per selection) per the procedure above
  - MUST produce a well-formed migration manifest listing every applied / skipped / failed / printed item
  - MUST_NOT modify files outside project_root or touch {cf_studio_path}/.core/ paths
  - MUST print Category C operations for manual execution (not auto-execute)
  - MUST satisfy the SKILL.md invariant when the controller supplied
    `studio_mode_contract`
```
