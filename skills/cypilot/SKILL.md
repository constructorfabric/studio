---
name: cf-constructor
description: "Invoke when user asks to do something with Cyber Constructor, or wants to analyze/validate artifacts, or create/generate/implement anything using Cyber Constructor workflows, or plan phased execution. Core capabilities: workflow routing (plan/analyze/generate/auto-config); deterministic validation (structure, cross-refs, traceability, TOC); code↔artifact traceability with @cpt-* markers; spec coverage measurement; ID search/navigation; init/bootstrap; adapter + registry discovery; auto-configuration of brownfield projects (scan conventions, generate rules); kit management (install/update with file-level diff); TOC generation; agent integrations (Windsurf, Cursor, Claude, Copilot, OpenAI)."
---

# Cyber Constructor Unified Tool


<!-- toc -->

- [Cyber Constructor Unified Tool](#cyber-constructor-unified-tool)
  - [Goal](#goal)
  - [Preconditions](#preconditions)
  - [⚠️ MUST Instruction Semantics ⚠️](#️-must-instruction-semantics-️)
  - [Agent Acknowledgment](#agent-acknowledgment)
  - [Execution Logging](#execution-logging)
  - [Variables](#variables)
    - [Template Variable Resolution](#template-variable-resolution)
  - [CLI Resolution](#cli-resolution)
  - [Protocol Guard](#protocol-guard)
  - [Cyber Constructor Mode](#cyber-constructor-mode)
  - [Agent-Safe Invocation](#agent-safe-invocation)
  - [Quick Commands](#quick-commands)
    - [Direct CLI Commands (No Workflow Routing)](#direct-cli-commands-no-workflow-routing)
    - [Workflow Shortcuts](#workflow-shortcuts)
  - [Workflow Routing](#workflow-routing)
  - [Command Reference](#command-reference)
  - [Auto-Configuration](#auto-configuration)
  - [Project Configuration](#project-configuration)

<!-- /toc -->

## Goal

Cyber Constructor provides artifact validation, cross-reference validation, code traceability, spec coverage measurement, ID search/navigation, kit management, TOC generation/validation, multi-agent integration, and design-to-code implementation with `@cpt-*` markers.

## Preconditions

- `cfc` available (preferred) or `python3` as fallback
- Target paths exist and are readable

---

## ⚠️ MUST Instruction Semantics ⚠️

**MUST** and **ALWAYS** are mandatory. Skipping any MUST instruction invalidates execution, the output must be discarded, and the workflow fails.

## Agent Acknowledgment

- [ ] MUST/ALWAYS are mandatory; skipping any MUST invalidates execution.
- [ ] I will read all required files before proceeding.
- [ ] I will follow workflows step-by-step without shortcuts.
- [ ] I will not create or modify files, or execute any other write-capable Cyber Constructor command, without explicit user confirmation, and I will not add auto-approval flags unless the user explicitly asks for them.
- [ ] I will list Cyber Constructor files read, why, and the triggering instruction before any approval prompt.

By proceeding with Cyber Constructor work, I acknowledge and accept these requirements.

ALWAYS SET {cfc_mode} = `on` FIRST when loading this skill

## Execution Logging

ALWAYS provide execution visibility:
- Notify the user when entering any H2 section of a Cyber Constructor prompt.
- Notify the user when completing any `- [ ]` checklist task.
- Use `- [CONTEXT]: MESSAGE`; set context to the file/section and message to the action + why.
- Logging must help the user understand loaded prompts, routing decisions, debugging state, and workflow progress.

Example:
```text
- [execution-protocol]: Entering "Load Rules" — target is CODE, loading codebase/rules.md
- [DESIGN rules]: Completing "Validate structure" — all required sections present
- [workflows/generate.md]: Entering "Determine Target" — user requested code implementation
```

## Variables

| Variable | Value | Use |
|---|---|---|
| `{cf-constructor-path}` | Directory path resolved from root `AGENTS.md` | Base path for all Cyber Constructor-relative references |
| `{cfc_mode}` | `on` or `off` | Current Cyber Constructor mode state |
| `{cfc_cmd}` | `cfc` or `python3 {cf-constructor-path}/.core/skills/cypilot/scripts/cypilot.py` | Resolved CLI entrypoint |
| `{cfc_installed}` | `true` or `false` | Whether the `cfc` CLI is available |

Setting `{cfc_mode}`: explicit `cf-constructor on/off` or a prompt that activates/deactivates Cyber Constructor workflows.

### Template Variable Resolution

- Resolve variables from `{cfc_cmd} --json info` first; parse the returned `variables` dict.
- Use `{cfc_cmd} --json resolve-vars` only when a fresh or filtered map is needed.
- Variable sources: system (`cf-constructor-path`, `project_root`) + installed kit resources.
- ALWAYS resolve `{variable}` references to absolute paths before using kit markdown files.

## CLI Resolution

Run before Protocol Guard when `{cfc_mode}` is `on`:
1. `command -v cfc` → `{cfc_cmd} = cfc`, `{cfc_installed} = true`
2. Otherwise `{cfc_cmd} = python3 {cf-constructor-path}/.core/skills/cypilot/scripts/cypilot.py`, `{cfc_installed} = false`
3. If `{cfc_installed}` is `false` and the marker file `~/.cf-constructor/cache/cfc-prompt-dismissed` does not exist, display this prompt verbatim and wait for input:
   `Install cfc to enable the short 'cfc' command? Reply 'yes' or 'no' [y/N]:`
   - `y` or `yes` (case-insensitive) → run `pipx install git+https://github.com/cyberfabric/cyber-constructor.git`; on success set `{cfc_cmd} = cfc` and `{cfc_installed} = true`
   - `n` or `no` (case-insensitive) → decline; keep `{cfc_cmd} = python3 {cf-constructor-path}/.core/skills/cypilot/scripts/cypilot.py` and create the marker file `~/.cf-constructor/cache/cfc-prompt-dismissed` so the prompt is not shown again
   - Pressing Enter with no input → use the default `no` (the capital `N` in `[y/N]` indicates the default); treat as decline and create the marker file
   - `Ctrl+C` / interrupt → treat as decline/abort: do not install, create the marker file, and continue with the long-path invocation
4. Re-offer installation (re-display the prompt above and, on dismissal, refresh the marker file) only when the user later asks about the long invocation path `python3 {cf-constructor-path}/.core/skills/cypilot/scripts/cypilot.py`; otherwise the marker file suppresses re-prompting

ALWAYS use `{cfc_cmd}` for all later CLI invocations.

## Protocol Guard

- ALWAYS FIRST open and remember `{cf-constructor-path}/.gen/AGENTS.md`
- ALWAYS open and follow `{cf-constructor-path}/config/AGENTS.md` when it exists
- ALWAYS open and follow `{cf-constructor-path}/.gen/SKILL.md` when it exists
- ALWAYS open and follow `{cf-constructor-path}/config/SKILL.md` when it exists
- ALWAYS FIRST run `{cfc_cmd} --json info` before any Cyber Constructor workflow action
- ALWAYS store the `variables` dict from `info` output and use it to resolve `{variable}` references in AGENTS/SKILL/rules/workflows
- ALWAYS follow this load order: `info` → registry/intent/target/rules resolution from `execution-protocol.md` → matched WHEN-clause specs
- ALWAYS load matched WHEN-clause specs only after registry understanding, target determination, and `rules.md` resolution provide enough context to match safely
- ALWAYS FIRST parse and load all matched WHEN-clause specs before proceeding
- MUST NOT preload every AGENTS/SKILL/spec file up front; load only the smallest set needed for the current request
- Before opening a large AGENTS/SKILL/spec file, estimate size and prefer chunked reads of matched sections over full-file reads
- If safe WHEN-clause matching is not yet possible, stop after registry/target/rules resolution and continue only when enough context exists to load specs boundedly
- If required Protocol Guard context would exceed the current turn budget, checkpoint or escalate instead of proceeding with partial or unbounded spec loading
- ALWAYS include this block when editing code:
```text
Cyber Constructor Context:
- Cyber Constructor: {path}
- Target: {artifact|codebase}
- Specs loaded: {list paths or "none required"}
```
- ALWAYS stop and re-run Protocol Guard when required specs should have been loaded but were not
- ALWAYS open and follow `{cf-constructor-path}/.core/requirements/language-complexity.md` for the global UX rule on output language complexity. Resolved level (`low` / `middle` / `high`, default `middle`) applies to ALL Cyber Constructor user-facing output across every workflow / methodology / skill — chat messages AND user-facing artifact / documentation bodies. Source quotes from input artifacts and spec/normative files (workflows, requirements, kits, agent definitions) are exempt. Resolution: mid-session override `change language complexity to {X}` → `[language] complexity` in `{cf-constructor-path}/config/core.toml` → default `middle`. Override `remember new language complexity` persists to `core.toml`.

## Cyber Constructor Mode

- ALWAYS set `{cfc_mode} = on` first when user invokes `cf-constructor {prompt}`
- ALWAYS run `info` when enabling Cyber Constructor mode
- ALWAYS show:
```text
Cyber Constructor Mode Enabled
Cyber Constructor: {FOUND at path | NOT_FOUND}
```

## Agent-Safe Invocation

- ALWAYS use `{cfc_cmd} --json <subcommand> [options]` for agent-driven CLI calls unless a command-specific exception below says otherwise
- ALWAYS pass `--json` immediately after `{cfc_cmd}` and before the subcommand when using machine-output mode
- EXCEPTION: NEVER run `{cfc_cmd} init` with `--json`; always invoke `{cfc_cmd} init ...` without `--json`
- EXCEPTION: NEVER run `{cfc_cmd} delegate` with `--json`; always invoke `{cfc_cmd} delegate <plan_dir> ...` without `--json`
- EXCEPTION: NEVER run `{cfc_cmd} update` with `--json`; always invoke `{cfc_cmd} update ...` without `--json`
- ALWAYS use `=` form for pattern args starting with `-` (example: `--pattern=-req-`)
- MUST obtain explicit user confirmation before executing any write-capable command, including direct CLI commands that do not route through a workflow
- MUST NOT add auto-approval flags such as `--yes`, `-y`, or `--force` to write-capable commands unless the user explicitly requested that non-interactive behavior

## Quick Commands

### Direct CLI Commands (No Workflow Routing)

No workflow routing skips workflow selection only. It does not waive confirmation: obtain explicit user confirmation before executing any write-capable direct CLI command below. When asking for that confirmation, explain why the command is needed now, tell the user exactly how to approve or decline, state what approval will do next, and mark the suggested path when one option is clearly safer or more relevant.

| User invocation | Direct action |
|---|---|
| `cf-constructor init` | After explicit user confirmation, run `{cfc_cmd} init` without `--json` |
| `cf-constructor update` | After explicit user confirmation, run `{cfc_cmd} update` without `--json` |
| `cf-constructor agents <name>` | Run `{cfc_cmd} --json agents --agent <name>` |
| `cf-constructor generate-agents <name>` | After explicit user confirmation, run `{cfc_cmd} --json generate-agents --agent <name>` |
| `cf-constructor workspace init` | After explicit user confirmation, run `{cfc_cmd} --json workspace-init [--root <dir>] [--output <path>] [--inline] [--force] [--max-depth <N>] [--dry-run]` |
| `cf-constructor workspace add` | After explicit user confirmation, run `{cfc_cmd} --json workspace-add --name <name> (--path <path> \| --url <url>) [--branch <branch>] [--role <role>] [--adapter <path>] [--inline] [--force]` |
| `cf-constructor workspace info` | Run `{cfc_cmd} --json workspace-info` |
| `cf-constructor workspace sync` | After explicit user confirmation, run `{cfc_cmd} --json workspace-sync [--source <name>] [--dry-run] [--force]`; `--force` is destructive |

### Workflow Shortcuts

| User invocation | Action |
|---|---|
| `cf-constructor auto-config` / `cf-constructor configure` | Open and follow `{cf-constructor-path}/.core/workflows/generate.md` |

## Workflow Routing

Cyber Constructor has exactly three core workflows plus specialized sub-workflows and dedicated capability agents. Routing priority is `delegate` > `compile-phase` > `execute-phase` > `plan` > `generate`/`analyze`. Delegation intent MUST route to the `cf-constructor-ralphex` capability agent rather than falling through to generic planning or generation. Generated-plan phase compilation intent MUST route to the dedicated `cf-constructor-phase-compiler` capability agent, and generated-plan phase execution intent MUST route to the dedicated `cf-constructor-phase-runner` capability agent rather than back into generic planning.

Oversized-input invariant: if the raw task input exceeds `500` total lines across the direct prompt text, attached or provided files, or one large file, Cyber Constructor MUST explicitly offer `/cf-constructor-plan` before any direct `/cf-constructor-generate` or `/cf-constructor-analyze` execution continues. Line count = sum( lines in direct prompt text if present + lines in each attached or provided file ); when stdin is used the direct prompt text is included in this sum as `input/direct-prompt.md`; intermediate/generated chunk files are excluded from this count (only raw user inputs are counted). If the user chooses the plan path, the planner MUST first compute the input signature using the read-only `{cfc_cmd} --json chunk-input ... --dry-run` mode (which writes no files) to check for existing package reuse, and MUST obtain explicit user approval before materializing that input under `{cf-constructor-path}/.plans/{task-slug}/input/` using the write-capable `{cfc_cmd} --json chunk-input ... --max-lines 300 --threshold-lines 500` command (without `--dry-run`). The planner MUST pass `--include-stdin` when direct prompt text must be packaged together with provided files; when stdin is used, it MUST also preserve that raw prompt as `input/direct-prompt.md`. The emitted chunk files become mandatory plan inputs for the relevant phases. If the user declines plan escalation, Cyber Constructor MAY continue in the direct workflow only after an explicit warning that reduced guarantees apply.

Completion invariants for workflow outputs:
- A `/cf-constructor-plan` run is not complete until it reaches one of three valid stopping points defined by `workflows/plan.md`: `(a)` the raw-input approval checkpoint, where the planner has identified oversized input and presented the `Proceed with raw-input materialization? [y/n]` prompt — the user may approve (`y`) to continue on the plan path or reject (`n`) to decline raw-input materialization with no filesystem mutations; `(b)` the brief checkpoint where `plan.toml` and every required `brief-*` file exist on disk and the response presents the explicit next-step choice set; or `(c)` the fully compiled plan state where every corresponding `phase-*` file also exists on disk after the user chose inline generation or `cf-constructor-phase-compiler` execution.
- A `/cf-constructor-generate` run that wrote or updated any files is not complete until the final response includes both `Plan Review Prompt` and `Direct Review Prompt` blocks. This applies on both the validated success path and the RELAXED explicitly unvalidated recovery path.
- A `/cf-constructor-analyze` run with any actionable issue is not complete until the final response includes both `Fix Prompt` and `Plan Prompt` blocks.
- A `/cf-constructor delegate` run is not complete until the final response includes delegation status, handoff result or error details, and next-step options.
- A native plan-phase compilation run is not complete until the final response includes compiled phase identity, output file path, and compile-time validation outcome.
- A native plan-phase execution run is not complete until the final response includes executed phase status, manifest update outcome, and the next-phase handoff or recovery action.
- MUST NOT end a workflow response immediately after the summary, analysis report, or next-step options when one of the required prompt pairs is still missing.

| Intent | Match | Action |
|---|---|---|
| Delegate | `delegate`, `delegate to ralphex`, `ralphex execute`, `ralphex review`, `hand off to ralphex`, `run with ralphex`, `ralphex delegation` | Open and follow `{cf-constructor-path}/.core/skills/cypilot/agents/cf-constructor-ralphex.md` |
| Compile phase | `compile phase`, `compile next phase`, `compile plan phase`, `generate phase file`, `compile from brief`, `build phase from brief` | Open and follow `{cf-constructor-path}/.core/skills/cypilot/agents/cf-constructor-phase-compiler.md` |
| Execute phase | `execute phase`, `run next phase`, `continue plan`, `resume plan`, `execute plan phase`, `run plan phase`, `execute the next phase` | Open and follow `{cf-constructor-path}/.core/skills/cypilot/agents/cf-constructor-phase-runner.md` |
| Plan | `plan`, `create a plan`, `execution plan`, `break down`, `decompose`, or `plan to ...` | Open and follow `{cf-constructor-path}/.core/workflows/plan.md` first |
| Generate | `create`, `edit`, `fix`, `update`, `implement`, `refactor`, `delete`, `add`, `setup`, `configure`, `build`, `code` and user did not say `plan` | Open and follow `{cf-constructor-path}/.core/workflows/generate.md` |
| Analyze | `analyze`, `validate`, `review`, `check`, `inspect`, `audit`, `compare`, `list`, `show`, `find`, `explain`, `tell me about`, `walk me through`, `teach me`, `present`, `introduce`, `let's understand`, `make sense of` (or equivalents in any user language; intent matching is language-agnostic) and user did not say `plan` | Open and follow `{cf-constructor-path}/.core/workflows/analyze.md` (storytelling intent activates `EXPLAIN_MODE=true` via the WHEN-rule for `requirements/storytelling.md`) |
 | Workspace | `workspace`, `multi-repo`, `add source`, `add repo`, `cross-reference`, `cross-repo` | Open and follow `{cf-constructor-path}/.core/workflows/workspace.md` |
 | Unclear | `help`, `look at`, `work with`, `handle` | Ask `Why this input is needed: I need the Cyber Constructor mode to route your request correctly. Reply with plan / generate / analyze. plan = phased execution for large or multi-step work; generate = create or modify files; analyze = read-only inspection or review. Suggested: generate for requested changes; analyze for inspection-only requests.` and stop if the user cancels |
 
 `configure` and `auto-config` are workflow shortcuts, not direct no-protocol commands; both route through `generate.md`, which may auto-trigger `requirements/auto-config.md` for brownfield projects with no project-specific rules.
 
 ## Command Reference

Entrypoint: `{cfc_cmd} <command> [options]`
Machine output: add `--json` immediately after `{cfc_cmd}` and before the subcommand, except for `init`, `delegate`, and `update`, which MUST run without `--json`. Exit codes: `0 = PASS`, `1 = filesystem/config error`, `2 = FAIL`.
Legacy aliases: `validate-code` = `validate`; `validate-rules` = `validate-kits`.

| Category | Commands |
|---|---|
| Validation | `validate`, `validate-kits`, `validate-toc`, `self-check`, `spec-coverage` |
| Search | `list-ids`, `list-id-kinds`, `get-content`, `where-defined`, `where-used` |
| Kit management | `kit install`, `kit update` |
| Delegation | `delegate <plan_dir>` |
| Utilities | `toc`, `chunk-input`, `info`, `resolve-vars`, `init`, `update`, `agents`, `generate-agents` |
| Workspace | `workspace-init`, `workspace-add`, `workspace-info`, `workspace-sync` |

Use `validate` for artifact or code validation, `toc` for Markdown TOC generation, `chunk-input` for oversized workflow inputs, `info` and `resolve-vars` for discovery/path resolution, and `generate-agents` for integration generation. Use `kit update` for file-level kit refresh, `delegate` for ralphex handoff, and workspace commands for multi-repo setup.

See `{cf-constructor-path}/.core/skills/cypilot/cypilot.clispec` for full syntax, arguments, options, exit semantics, and examples.

 ---

 ## Auto-Configuration

Use auto-config after `cf-constructor init` on a brownfield project, when project conventions are unknown, or after major structural changes. It scans structure/conventions, generates `{cf-constructor-path}/config/rules/{slug}.md`, adds WHEN rules to `{cf-constructor-path}/config/AGENTS.md`, and registers systems in `{cf-constructor-path}/config/artifacts.toml`. Invoke via `cf-constructor auto-config`, `cf-constructor configure`, or the automatic offer inside `generate.md`.

## Project Configuration

Project configuration lives in `{cf-constructor-path}/config/core.toml` (systems, kits, ignore lists). Artifact registry lives in `{cf-constructor-path}/config/artifacts.toml` (artifact paths, kinds, system mappings, codebase paths, autodetect rules). All commands output JSON when invoked with `--json`. Exit codes: 0=PASS, 1=filesystem error, 2=FAIL.
