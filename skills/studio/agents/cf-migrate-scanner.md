---
description: Invoke when scanning a project for residual cypilot/cpt/Cypilot/Cyber Pilot references that the mechanical `cfs init --migrate-from-cypilot=yes` did not touch (source code, CI, docs, agent configs, workspaces, build files) — read-only post-deterministic cleanup; emits a structured findings list for the planner to categorize. Dispatched by the `migrate from cypilot` orchestrator after user approval.
---

<!-- toc -->

- [Purpose](#purpose)
- [Task Inputs (provided by the orchestrator after this role definition)](#task-inputs-provided-by-the-orchestrator-after-this-role-definition)
- [Context Budget & Fail-Safe](#context-budget--fail-safe)
- [Procedure](#procedure)
  - [Step 1 — Project-wide grep](#step-1--project-wide-grep)
  - [Step 2 — Targeted hotspot scan](#step-2--targeted-hotspot-scan)
  - [Step 3 — Filter intentional-keep cases](#step-3--filter-intentional-keep-cases)
  - [Step 4 — Output](#step-4--output)
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

The deterministic migration (`cfs init --migrate-from-cypilot=yes`) handles install-dir copy, root `AGENTS.md`/`CLAUDE.md` managed-block swap, TOML rewrites in `{cf-studio-path}/config/`, and Markdown rewrites for the fixed list (`AGENTS.md`/`SKILL.md`/`README.md`). Everything else is your scan surface.

## Task Inputs (provided by the orchestrator after this role definition)

- `project_root`: absolute path to the project root
- `cf_studio_path`: absolute path to the Constructor Studio install dir (default `.cf-studio`)
- `exclude_dirs`: list of paths to skip (typically `.git`, `{cf-studio-path}`, build caches like `__pycache__`, `node_modules`, `.venv`, `dist`, `build`)

`cf_studio_path` is the canonical managed-tree input name for this migration
chain. The Scanner, Migrator, and Verifier all use that exact field name.

## Context Budget & Fail-Safe

```text
UNIT ContextBudgetFailSafe

PURPOSE:
  Stop safely when remaining context budget is insufficient to complete the scan.

WHEN:
  remaining context budget cannot cover the next step or item

DO:
  EMIT PARTIAL_CHECKPOINT JSON block using schema:
    {
      "type": "PARTIAL_CHECKPOINT",
      "agent": "cf-migrate-scanner",
      "phase_completed": "<step or category just completed>",
      "remaining": ["<list of un-processed items / paths>"],
      "evidence_collected": ["<completed scan buckets or hotspot checks>", "..."],
      "resume_inputs": {"<dispatch fields needed to resume>": "<value>"}
    }
  STOP_TURN

RULES:
  - MUST_NOT emit a final PASS / FAIL verdict on a partial run
  - MUST emit only what has been scanned so far and what remains
```

## Procedure

### Step 1 — Project-wide grep

Run grep / rg across the project root with the following file globs and patterns. Record every match with `{file_path_relative_to_project_root}:{line_number}:{matched_line}`.

**File globs to include** (use `rg`'s file-type filters if available, else `grep --include=`):
- Source code: `*.py`, `*.ts`, `*.tsx`, `*.js`, `*.jsx`, `*.go`, `*.rs`, `*.java`, `*.kt`, `*.rb`, `*.php`
- Config: `*.toml`, `*.cfg`, `*.ini`, `*.json` (BUT skip everything under `{cf_studio_path}` — the deterministic migration owns it)
- Docs: `*.md`, `*.mdx`, `*.rst`
- CI: `*.yml`, `*.yaml` (in `.github/`, `.gitlab/`, `.circleci/`, root)
- Shell: `*.sh`, `*.bash`, `*.zsh`, `*.fish`, `Makefile`, `Dockerfile`, `*.envrc`

**Exclude directories** (in addition to `exclude_dirs` input):
- `.git`
- `{cf_studio_path}` (e.g. `.cf-studio` — exclude the whole tree)
- `node_modules`, `__pycache__`, `.venv`, `venv`, `dist`, `build`, `.next`, `.nuxt`, `target`
- `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `.cache`

**Search patterns** (record which pattern hit each line):

| Pattern key | Regex | Notes |
|---|---|---|
| `cypilot_path` | `\bcypilot_path\b` | Legacy template variable / TOML key |
| `curly_cypilot_path` | `\{cypilot_path\}` | Legacy template variable literal |
| `github_cyber_pilot` | `github\.com/cyberfabric/cyber-pilot(?!-kit)` | GitHub URL (legacy cypilot main repo) |
| `github_kit_sdlc` | `github\.com/cyberfabric/cyber-pilot-kit-sdlc` | GitHub URL (legacy cypilot SDLC kit) |
| `gh_prefix_kit` | `github:cyberfabric/cyber-pilot-kit-sdlc` | Legacy kit source string |
| `proper_noun` | `(?:\bCypilot\b|\bCyber Pilot\b)` | Legacy proper noun in prose |
| `cpt_command_backtick` | `` `cpt ` `` | Well-formed legacy command ref (backtick + space) |
| `cpt_command_spaced` | ` cpt ` (space-padded) | Well-formed legacy command ref (space-padded) |
| `cpt_other` | `\bcpt\b` minus the above | Any other `cpt` — needs review |
| `cypilot_standalone` | `\bcypilot\b` minus `cypilot_path` matches | Standalone `cypilot` — could be package name, kit slug, etc. |
| `cpt_marker` | `@cpt[-:]` | Marker syntax — per v4.0.0 design these can be intentional |
| `kit_slug_cypilot_sdlc` | `\bcypilot-sdlc\b` | Legacy kit slug |
| `cyber_pilot_kebab` | `\bcyber-pilot\b` (not part of URL) | Kebab form (e.g. in slugs) |
| `workspace_file` | `(?:\.cypilot-workspace\.toml|\.bootstrap-workspace\.toml)` | Legacy workspace file name |

For each match, also classify into a SOURCE-FILE category:
- `code` — source-code file (auto-fixable depends on pattern)
- `ci` — CI configuration
- `build` — build/packaging config (`pyproject.toml`, `package.json`, `Makefile`, `Dockerfile`)
- `doc` — documentation (`*.md`, `*.rst`)
- `script` — shell script
- `agent_config` — under `.agents/`, `.claude/`, `.cursor/`, `.codex/`, `.windsurf/`
- `workspace` — workspace file or member-related
- `other`

### Step 2 — Targeted hotspot scan

In addition to the project-wide pass, look specifically at these locations:

1. **`{cf_studio_path}/config/`** — the deterministic migration should have rewritten all TOML keys and the fixed-list Markdown. Re-scan for any leftover `cypilot-sdlc` / `cypilot_path` / `Cypilot` / `Cyber Pilot` references. Flag as `hotspot_config_residue` if found (HIGH PRIORITY).

2. **Agent integration dirs** — list presence of `.agents/`, `.claude/`, `.cursor/`, `.codex/`, `.windsurf/`, `.copilot/`, `.openai/` under project root. For each present, count files. Do NOT modify. Mark Phase-C: _"run `cfs generate-agents` after Migrator finishes"_.

3. **Root system prompts** — read `{project_root}/AGENTS.md` and `{project_root}/CLAUDE.md`. If either still contains `<!-- @cpt:root-agents -->` markers (legacy), flag as `hotspot_root_legacy_marker` (CRITICAL — deterministic migration failed silently OR didn't run).

4. **Workspace files**:
   - `.cypilot-workspace.toml` or `.bootstrap-workspace.toml` (legacy names) → recommend manual rename as Category C; any in-file rewrite work must come from the recorded line findings and hotspot scan, not from an implied extra rewrite step
   - `.studio-workspace.toml` (current name) → re-scan inside it for any `cypilot` / `cyber-pilot` references in source / branch URLs

5. **Workspace member repos** (if workspace file is present): parse the workspace file's `sources` table. For each source's `path` (when it's a local path under the user's workspace root), record the member's resolved name and absolute path. Do NOT recurse into the member's filesystem (that's the member's own migration job). Mark as Phase-C: _"cascade `cfs init --migrate-from-cypilot=yes` into member repo `<resolved-member-name>` at `<resolved-member-path>`"_.

### Step 3 — Filter intentional-keep cases

```text
UNIT IntentionalKeepFilter

PURPOSE:
  Suppress known-intentional matches before emitting findings.

RULES:
  - MUST skip matches inside `src/studio_proxy/` for all patterns
    (this is the Constructor Studio package name, intentionally new-brand)
  - MUST skip `cpt_marker` pattern matches when source-file category is `code`
    (per v4.0.0 design all @cpt-* markers in source files are intentionally preserved)
  - MUST include `cpt_marker` matches when source-file category is `doc`
    (markers in user-facing docs may genuinely be residue)
  - MUST_NOT flag `format = "CFS"` inside a `[kits.<slug>]` or `[kit.<slug>]` TOML table
    (`format = "Cypilot"` in those same tables is pre-migration state — record as expected)
  - MUST classify `cypilot` in a `# noqa:` comment or near a deprecation notice
    as `intentional_likely` (low priority) — let the user decide
  - MUST_NOT speculate about user intent beyond these rules
```

### Step 4 — Output

Return a structured findings list. Format:

```text
## Scanner Findings

Total findings: {N}

### Hotspots (HIGH PRIORITY)
- {hotspot_kind}: {file_path} — {description}
  ...

### Findings by category

#### code (M)
- {file}:{line}: pattern={pattern_key} — {matched_line}
  ...

#### ci (M)
...

#### build (M)
...

#### doc (M)
...

#### script (M)
...

#### agent_config (M)
... (counts only — no per-file findings; the per-file action is "regenerate via cfs generate-agents")

#### workspace (M)
- {workspace_file_path}: manual rename to .studio-workspace.toml recommended
- workspace member `<resolved-member-name>` at `<resolved-member-path>`: cascade migration recommended
- ... (any in-file matches scanned as `doc` / `code` etc.)

### Suggested auto-classify hints (per pattern)

- pattern `cypilot_path` / `curly_cypilot_path` → auto-fixable (A)
- pattern `github_cyber_pilot` / `github_kit_sdlc` / `gh_prefix_kit` → auto-fixable (A)
- pattern `proper_noun` → auto-fixable (A)
- pattern `cpt_command_backtick` / `cpt_command_spaced` → auto-fixable (A)
- pattern `cpt_other` → needs review (B)
- pattern `cypilot_standalone` → needs review (B)
- pattern `cpt_marker` → needs review (B) — even if in a doc; user judges
- pattern `kit_slug_cypilot_sdlc` → auto-fixable (A) in TOML; needs review (B) in code/scripts
- pattern `cyber_pilot_kebab` → needs review (B) — may be deliberate in URLs or filename
- pattern `workspace_file` (the file name itself) → cascade (C)
```

## Hard Rules

```text
UNIT ScannerHardRules

RULES:
  - MUST_NOT modify any file
  - MUST_NOT recurse into excluded directories
  - MUST_NOT speculate about user intent; classify by the rules above only
  - MUST produce output machine-parseable by the Planner matching the structure in Step 4
  - WHEN grep / rg are unavailable:
      fall back to a Python-script scan using the Read tool to enumerate files
      report the fallback method in the output
```

## Response Completion Gate

```text
UNIT ScannerCompletionGate

RULES:
  - MUST have run all configured search patterns
  - MUST emit findings list in the documented output structure
  - MUST include hotspot scan section
  - MUST have applied intentional-keep filtering
    (project memory: `_migrate_config_markdown` deliberately preserves `cpt.` and line-start `cpt`)
  - MUST satisfy the SKILL.md invariant
```
