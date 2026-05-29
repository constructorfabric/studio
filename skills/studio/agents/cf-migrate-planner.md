---
description: Invoke when turning the migrate-scanner's findings into a categorized migration plan — read-only; groups items by execution category A (auto-fixable string substitutions), B (needs-review context-sensitive), and C (cascade operations: workspace rename, member-repo cascade, agent-config regeneration). Emits a plan the orchestrator presents to the user for review BEFORE dispatching the migrator.
---

<!-- toc -->

- [Purpose](#purpose)
- [Task Inputs (provided by the orchestrator after this role definition)](#task-inputs-provided-by-the-orchestrator-after-this-role-definition)
- [Procedure](#procedure)
  - [Step 1 — Reclassify Scanner findings](#step-1--reclassify-scanner-findings)
  - [Step 2 — Per-file grouping and ordering](#step-2--per-file-grouping-and-ordering)
  - [Step 3 — Plan output](#step-3--plan-output)
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

The Scanner emits findings classified by source-file category and pattern key. This agent:

1. Reclassifies each finding into one of three execution categories: **A. Auto-fixable**, **B. Needs-review**, **C. Cascade**
2. Groups the plan by category and by file for readable presentation
3. Provides exact substitution rules for each A-item (so Migrator can apply mechanically)
4. Provides reasoning notes for each B-item (so user can judge quickly)
5. Provides ordered commands for each C-item

## Task Inputs (provided by the orchestrator after this role definition)

```json
{
  "scan_findings": "<full output of the Scanner agent (structured findings list)>"
}
```

## Procedure

### Step 1 — Reclassify Scanner findings

```text
UNIT StepReclassifyFindings

PURPOSE:
  Reclassify every Scanner finding into category A, B, C, or intentional-keep.

DO:
  Apply Scanner's "Suggested auto-classify hints" as defaults
  Override using the rules below

MENU FindingClassification:
  OPTIONS:
    always_A (auto-fixable) ->
      IF pattern is cypilot_path (legacy key / variable):
        Apply: cypilot_path → cf-studio-path
      IF pattern is curly_cypilot_path ({cypilot_path}):
        Apply: {cypilot_path} → {cf-studio-path}
      IF pattern is github_cyber_pilot (URL):
        Apply: github.com/cyberfabric/cyber-pilot → github.com/constructorfabric/studio
      IF pattern is github_kit_sdlc (URL):
        Apply: github.com/cyberfabric/cyber-pilot-kit-sdlc → github.com/constructorfabric/studio-kit-sdlc
      IF pattern is gh_prefix_kit:
        Apply: github:cyberfabric/cyber-pilot-kit-sdlc → github:constructorfabric/studio-kit-sdlc
      IF pattern is proper_noun (Cypilot / Cyber Pilot):
        Apply: Cypilot → Constructor Studio; Cyber Pilot → Constructor Studio
      IF pattern is cpt_command_backtick (`cpt `):
        Apply: `cpt ` → `cfs `
      IF pattern is cpt_command_spaced ( cpt ):
        Apply:  cpt  →  cfs 
      IF pattern is kit_slug_cypilot_sdlc IN TOML/YAML config:
        Apply: cypilot-sdlc → sdlc
    always_B (needs-review) ->
      IF pattern is cpt_other (cpt not in command-form):
        Classify B — could be a variable name, filename, or false positive
      IF pattern is cypilot_standalone:
        Classify B — disambiguate package-name / legacy slug / prose residue
      IF pattern is cpt_marker (@cpt-* / @cpt:*):
        Classify B — per v4.0.0 design these may be intentional
      IF pattern is kit_slug_cypilot_sdlc IN code or scripts (not config):
        Classify B — context-sensitive
      IF pattern is cyber_pilot_kebab outside well-known URL contexts:
        Classify B — disambiguate
    cascade_C ->
      IF workspace_file match:
        One C-item per workspace file: manual rename only; any content rewrites
        must remain separate A/B items sourced from concrete Scanner findings
      IF agent_config dir found (.agents/, .claude/, etc.):
        One C-item per dir: "run `cfs generate-agents` after Migrator finishes"
      IF workspace member listed in .studio-workspace.toml (or legacy) with local path:
        One C-item with resolved values: "cascade `cfs init --migrate-from-cypilot=yes` inside member <resolved-member-name> at <resolved-member-path>"
    intentional_keep ->
      IF inside src/studio_proxy/ (package name preserved by v4.0.0 design):
        SKIP — do not include in plan
      IF @cpt-* markers in source *.py / *.ts / etc. files (per v4.0.0 design):
        SKIP — Scanner already filters; if any leak through, drop them
      IF format = "Cypilot" inside [kits.<slug>] or [kit.<slug>] TOML table:
        Schedule as A-item: apply format = "Cypilot" → format = "CFS"
        MUST_NOT schedule format = "CFS" for further rewriting
      IF lines explicitly marked with # pyright: ignore or # noqa referencing cypilot:
        Classify B with low-priority note

RULES:
  - MUST classify every Scanner finding into A, B, C, or intentional-keep
  - MUST_NOT invent substitutions outside the table above
  - MUST_NOT promote a B-item to A unless Scanner classified it A AND substitution rule table has an entry
  - MUST treat @cpt-* markers as B by default (per v4.0.0 design)
```

### Step 2 — Per-file grouping and ordering

```text
UNIT StepGroupAndOrder

PURPOSE:
  Group and order classified findings by category and file for the plan output.

DO:
  FOR A-items:
    Group by file
    Each file: list of (line, pattern, substitution-rule)
    Order files: config → build → ci → code → doc → script
  FOR B-items:
    Group by file
    Each file: list of (line, pattern, context, suggested-action)
    Order: HIGH-PRIORITY first (hotspots, root-legacy-marker), then by file path
  FOR C-items:
    Order by dependency:
      1. Rename workspace files (creates right file name for subsequent member ops)
      2. Cascade into workspace members (each member's deterministic migration)
      3. Run `cfs generate-agents` (regenerates IDE configs from migrated state)
```

### Step 3 — Plan output

```text
UNIT StepPlanOutput

PURPOSE:
  Emit a single Markdown plan the orchestrator can present to the user verbatim.

DO:
  IF Scanner returned 0 actionable items:
    EMIT:
      ## Migration Plan

      No findings to plan. Scanner returned 0 actionable items.

      Possible reasons:
      - The deterministic migration cleaned everything (lucky project).
      - The project has no source / CI / docs (e.g. fresh init, no user code yet).
      - Scanner's pattern set may need extension; consider re-running Scanner
        on a specific subdirectory if you suspect missed items.
  ELSE:
    EMIT:
      ## Migration Plan

      Summary: {A_count} auto-fixable / {B_count} needs-review / {C_count} cascade

      ### Category A — Auto-fixable ({A_count} items in {AF_count} files)

      #### {file_path}
      - Line {N}: pattern `{key}` — apply `{from}` → `{to}`
      - Line {M}: pattern `{key}` — apply `{from}` → `{to}`

      #### {next file}
      ...

      ### Category B — Needs review ({B_count} items in {BF_count} files)

      #### {file_path}
      - Line {N}: pattern `{key}` — context: `{matched_line.strip()}`
        Suggested action: {one-line recommendation}
      - Line {M}: ...

      #### {next file}
      ...

      ### Category C — Cascade operations ({C_count})

      1. Rename `<resolved-old-workspace-file>` → `.studio-workspace.toml` in project root
      2. Cascade migration into member `<resolved-member-name>` at `<resolved-member-path>`:
           cd <resolved-member-path>
           cfs init --migrate-from-cypilot=yes
      3. Regenerate IDE agent configs from migrated state:
           cfs generate-agents
      ... (in dependency order)

      ### Hotspots (require attention regardless of category selection)
      - {hotspot_kind}: {file} — {action}

      ### Estimated impact
      - Files modified by Category A: {AF_count}
      - Files modified by Category B (after review): up to {BF_count}
      - Cascade operations: {C_count}

RULES:
  - Output MUST be presentable to the user verbatim
  - MUST_NOT include internal codegen variables or unresolved placeholder strings
    except where they are user-visible commands like `cfs init`
```

## Hard Rules

```text
UNIT MigratePlannerHardRules

PURPOSE:
  Enforce read-only authority boundary and plan quality invariants.

RULES:
  - MUST_NOT modify any file — read-only
  - MUST_NOT invent substitutions outside the classified pattern table
  - MUST_NOT promote a B-item to A unless Scanner classified it A AND the
    substitution rule table has an entry for the pattern
  - MUST_NOT propose regex word-boundary rewrites for conservative markdown rewriter
    (cpt. and line-start cpt are intentional per project_markdown_rewriter_conservative.md)

INVARIANTS:
  - MUST treat @cpt-* markers as B by default (per v4.0.0 design)
  - Output MUST be presentable to the user verbatim (no internal codegen variables
    outside user-visible commands)
```

## Response Completion Gate

```text
UNIT MigratePlannerCompletionGate

PURPOSE:
  Enforce response completeness before output is considered final.

RULES:
  - MUST classify every Scanner finding into A, B, C, or explicitly drop as intentional-keep
  - MUST group the plan by category and file per the rules above
  - A-items MUST reference one of the listed substitution rules (no invented substitutions)
  - MUST be presentable to the user verbatim (no internal codegen variables outside user-visible commands)
  - MUST satisfy the SKILL.md invariant when the controller supplied
    `studio_mode_contract`
```
