# Feature: Core Infrastructure

<!-- toc -->

- [1. Feature Context](#1-feature-context)
  - [1. Overview](#1-overview)
  - [2. Purpose](#2-purpose)
  - [3. Actors](#3-actors)
  - [4. References](#4-references)
- [2. Actor Flows (CDSL)](#2-actor-flows-cdsl)
  - [Global CLI Invocation](#global-cli-invocation)
  - [Project Initialization](#project-initialization)
  - [Cypilot Migration](#cypilot-migration)
- [3. Processes / Business Logic (CDSL)](#3-processes--business-logic-cdsl)
  - [Resolve Skill Target](#resolve-skill-target)
  - [Route Command](#route-command)
  - [Define Root System](#define-root-system)
  - [Create Config Directory](#create-config-directory)
  - [Inject Root AGENTS.md](#inject-root-agentsmd)
  - [Cache Skill from GitHub](#cache-skill-from-github)
  - [Create Config AGENTS.md](#create-config-agentsmd)
  - [Display Project Info](#display-project-info)
  - [Project Root Detection](#project-root-detection)
  - [Config Management](#config-management)
  - [TOML Utilities](#toml-utilities)
  - [Registry Parsing](#registry-parsing)
  - [Context Loading](#context-loading)
  - [Mirror Override](#mirror-override)
- [4. States (CDSL)](#4-states-cdsl)
  - [Project Installation State](#project-installation-state)
- [5. Definitions of Done](#5-definitions-of-done)
  - [CLI Proxy Routes Commands](#cli-proxy-routes-commands)
  - [Global CLI Package](#global-cli-package)
  - [Skill Cache Downloads from GitHub](#skill-cache-downloads-from-github)
  - [Init Creates Full Config](#init-creates-full-config)
  - [Root AGENTS.md Integrity](#root-agentsmd-integrity)
  - [Usage Telemetry](#usage-telemetry)
  - [5.x Mirror Override](#5x-mirror-override)
- [6. Implementation Modules](#6-implementation-modules)
- [7. Acceptance Criteria](#7-acceptance-criteria)

<!-- /toc -->

- [ ] `p1` - **ID**: `cpt-studio-featstatus-core-infra`

## 1. Feature Context

- [ ] `p1` - `cpt-studio-feature-core-infra`

### 1. Overview

Foundation layer providing the global CLI proxy, skill engine command dispatch, config directory management, and project initialization. This feature is the base upon which all other Studio features are built — no other feature can function without it.

### 2. Purpose

Enables users to install Studio globally, initialize it in any project with sensible defaults, and execute deterministic commands with consistent JSON output. Addresses PRD requirements for a ≤5-minute install-to-init experience (`cpt-studio-fr-core-installer`, `cpt-studio-fr-core-init`) and a structured config directory (`cpt-studio-fr-core-config`).

### 3. Actors

| Actor | Role in Feature |
|-------|-----------------|
| `cpt-studio-actor-user` | Runs `cfs init`, `cfs info`, `cfs update` |
| `cpt-studio-actor-studio-cli` | Global proxy that resolves skill target and forwards commands |

### 4. References

- **PRD**: [PRD.md](../PRD.md)
- **Design**: [DESIGN.md](../DESIGN.md)
- **CLI Spec**: [cli.md](../specs/cli.md)
- **Dependencies**: None (foundation feature)

## 2. Actor Flows (CDSL)

### Global CLI Invocation

- [x] `p1` - **ID**: `cpt-studio-flow-core-infra-cli-invocation`

**Actors**:

- `cpt-studio-actor-user`
- `cpt-studio-actor-studio-cli`

**Success Scenarios**:
- User runs any `cfs` command from inside a project → routed to project-installed skill
- User runs `cfs` command outside a project → routed to cached skill
- First run after `pipx install` with empty cache → skill bundle downloaded from GitHub automatically

**Error Scenarios**:
- GitHub download fails (network, rate limit) → error with retry instructions
- Python version < 3.11 → error with version requirement

**Steps**:
1. [x] - `p1` - User invokes `cfs <command> [args]` from terminal - `inst-user-invokes`
2. [x] - `p1` - Fire non-blocking telemetry for the invocation (daemon thread: git identity + remote URL, local log, optional OTLP HTTP) - `inst-telemetry`
3. [x] - `p1` - CLI proxy checks for project-installed skill at `{cf-studio-path}/` in current or parent directories - `inst-check-project-skill`
4. [x] - `p1` - **IF** project skill found - `inst-if-project-skill`
   1. [x] - `p1` - Forward command and args to project skill engine - `inst-forward-project`
5. [x] - `p1` - **ELSE** - `inst-else-no-project`
   1. [x] - `p1` - Check cached skill at `~/.cf-studio/cache/` - `inst-check-cache`
   2. [x] - `p1` - **IF** cached skill exists - `inst-if-cache`
      1. [x] - `p1` - Forward command and args to cached skill engine - `inst-forward-cache`
   3. [x] - `p1` - **ELSE** no cached skill — first run after install - `inst-else-no-cache`
      1. [x] - `p1` - Algorithm: download and cache skill using `cpt-studio-algo-core-infra-cache-skill` - `inst-auto-download`
      2. [x] - `p1` - **IF** download failed - `inst-if-download-failed`
         1. [x] - `p1` - **RETURN** error: "Failed to download Studio skill. Check network and retry." (exit 1) - `inst-return-download-error`
      3. [x] - `p1` - Forward command and args to freshly cached skill engine - `inst-forward-fresh-cache`
6. [x] - `p1` - Skill engine executes command, produces JSON to stdout - `inst-engine-execute`
7. [x] - `p1` - CLI proxy performs non-blocking background version check - `inst-bg-version-check`
8. [x] - `p1` - **IF** cached version newer than project version - `inst-if-version-mismatch`
   1. [x] - `p1` - Display update notice to stderr - `inst-show-update-notice`
9. [x] - `p1` - **IF** first arg is `update` - `inst-if-update-cache`
   1. [x] - `p1` - Algorithm: download and cache skill using `cpt-studio-algo-core-infra-cache-skill` with optional version/branch/SHA argument - `inst-explicit-cache-update`
   2. [x] - `p1` - **RETURN** JSON: `{status, message, version}` (exit 0 on success, 1 on failure) - `inst-return-cache-update`
10. [x] - `p1` - **RETURN** exit code from skill engine (0=PASS, 1=error, 2=FAIL) - `inst-return-exit`

**Supporting**:
- [x] - `p1` - Imports, param extraction helpers (`_extract_version_param`, `_extract_named_param`), version display, init cache logic, forward-to-skill subprocess wrapper, background version check function - `inst-cli-proxy-helpers`

### Project Initialization

- [x] `p1` - **ID**: `cpt-studio-flow-core-infra-project-init`

**Actors**:

- `cpt-studio-actor-user`
- `cpt-studio-actor-studio-cli`

**Success Scenarios**:
- User initializes a fresh project → full config created, root system defined, AGENTS.md injected
- User initializes with custom directory and agent selection → respects choices

**Error Scenarios**:
- Studio already initialized → abort with suggestion to use `cfs update`
- No cached skill bundle → error with install instructions

**Steps**:
1. [x] - `p1` - User invokes `cfs init [--project-root ROOT] [--install-dir DIR]` - `inst-user-init`
2. [x] - `p1` - Check if `{cf-studio-path}/` (or specified dir) already exists - `inst-check-existing`
3. [x] - `p1` - **IF** already initialized - `inst-if-exists`
   1. [x] - `p1` - **RETURN** error: "Studio already initialized. Use 'cfs update' to upgrade." (exit 2) - `inst-return-exists`
4. [x] - `p1` - **IF** interactive terminal AND no --dir flag - `inst-if-interactive`
   1. [x] - `p1` - Prompt user for installation directory (default: `studio`) - `inst-prompt-dir`
   2. [x] - `p2` - Prompt user for agent selection (default: all) - `inst-prompt-agents`
5. [x] - `p2` - Copy skill bundle from `~/.cf-studio/cache/` into install directory - `inst-copy-skill`
6. [x] - `p1` - Algorithm: define root system using `cpt-studio-algo-core-infra-define-root-system` - `inst-define-root`
7. [x] - `p1` - Algorithm: create config directory using `cpt-studio-algo-core-infra-create-config` - `inst-create-config`
8. [x] - `p2` - Delegate agent entry point generation to Agent Generator (Feature 5 boundary) - `inst-delegate-agents`
9. [x] - `p1` - Prompt user: `Install SDLC kit? [a]ccept [d]ecline` - `inst-prompt-kit`
10. [x] - `p1` - **IF** user accepts: delegate kit installation from GitHub to Kit Manager (Feature 2 boundary) - `inst-install-kit-accepted`
11. [x] - `p1` - **ELSE**: skip kit installation, display install command for later use - `inst-skip-kit-declined`
11. [x] - `p1` - Algorithm: inject root AGENTS.md using `cpt-studio-algo-core-infra-inject-root-agents` - `inst-inject-agents`
12. [x] - `p1` - Algorithm: create config/AGENTS.md using `cpt-studio-algo-core-infra-create-config-agents` - `inst-create-config-agents`
13. [x] - `p1` - **RETURN** JSON: `{status, install_dir, kits_installed, agents_configured, systems}` (exit 0) - `inst-return-init-ok`
14. [x] - `p1` - Helper functions: copy from cache, generate READMEs for .core/.gen/config dirs, default core.toml, path prompting, slug-to-PascalCase - `inst-init-helpers`
15. [x] - `p1` - Detect existing Studio installation by reading AGENTS.md TOML block with `cf-studio-path` variable - `inst-init-detect-existing`
16. [x] - `p1` - Inject/update CLAUDE.md managed block for Claude agent integration - `inst-init-inject-claude`
17. [x] - `p1` - Human-friendly formatters for init success and error output - `inst-init-format-output`

### Cypilot Migration

- [x] `p1` - **ID**: `cpt-studio-flow-core-infra-migrate-from-cypilot`

**Actors**:

- `cpt-studio-actor-user`
- `cpt-studio-actor-studio-cli`

**Success Scenarios**:
- User runs `cfs init` in a project with a legacy Studio install and approves migration → legacy config is copied or reused as Constructor Studio config, root managed blocks are rewritten, and follow-up update refreshes the installation
- User runs with `--dry-run` → planned copy, rewrite, and update actions are reported without mutating files
- User declines migration during implicit init/update flow → Constructor Studio either initializes side-by-side or aborts with a clear result, depending on the command path

**Error Scenarios**:
- Legacy install is missing, outside project root, or not directly migratable → command returns structured error and avoids partial writes
- Target Constructor Studio directory exists without `--force` → command returns structured error and preserves both directories
- Root managed block rewrite fails after backups → command restores root files from backups and reports the failed step
- Host-integration cleanup MUST NOT touch `.github/workflows/` or any path outside the host-integration directories (`.claude/`, `.windsurf/`, `.cursor/`, `.github/copilot-instructions.md`, `.codex/`) — these paths are user-owned and preserved unconditionally

**Steps**:
1. [x] - `p1` - Define migration constants and imports used by implicit init/update migration flows - `inst-migration-module`
2. [x] - `p1` - Resolve legacy source and Constructor Studio target as child directories of the project root - `inst-resolve-dirs`
3. [x] - `p1` - Reject missing legacy installs and unsafe absolute or parent-directory paths - `inst-validate-dirs`
4. [x] - `p1` - **IF** target exists without force, return error without copying or deleting files - `inst-target-exists`
5. [x] - `p1` - **IF** replacing target, create a backup, replace from legacy source, and restore backup on replace failure - `inst-replace-target`
6. [x] - `p1` - **ELSE** create target from legacy source and clean up partial target on copy failure - `inst-create-target`
7. [x] - `p1` - Reuse the legacy directory in-place when source and target are the same directory - `inst-reuse-target`
8. [x] - `p1` - **IF** not dry-run, run post-copy rewrites for core TOML, artifacts TOML, config markdown, AGENTS.md, and CLAUDE.md - `inst-post-copy-rewrites`
9. [x] - `p1` - **ELSE** report dry-run rewrite actions without writing files - `inst-dry-run-actions`
10. [x] - `p1` - Run follow-up update unless skipped or dry-run, preserving warning status when update fails - `inst-followup-update`
11. [x] - `p1` - Return a structured migration result with actions, backups, warnings, and update details - `inst-return-result`
12. [x] - `p1` - Detect a legacy install from root AGENTS.md or known legacy directories - `inst-detect-legacy`
13. [x] - `p1` - Resolve ask/yes/no migration prompts for interactive and non-interactive callers - `inst-should-migrate`
14. [x] - `p1` - Return an explicit declined result when user rejects migration - `inst-declined-result`
15. [x] - `p1` - Read legacy version and accept only supported migration baseline versions - `inst-check-legacy-version`
16. [x] - `p1` - For dry-run unsupported legacy installs, report the planned baseline update without running it - `inst-preflight-dry-run`
17. [x] - `p1` - Prompt for unsupported legacy update and abort when user declines - `inst-prompt-legacy-update`
18. [x] - `p1` - Run legacy `cfs update --version` with bridge bypass environment and report subprocess result - `inst-run-legacy-update`
19. [x] - `p1` - Re-read legacy version after update and reject version mismatch - `inst-check-updated-version`
20. [x] - `p1` - Merge legacy preflight metadata into the final migration result without overwriting migration actions - `inst-merge-preflight`
21. [x] - `p1` - Read legacy version from known legacy skill package locations - `inst-read-version`
22. [x] - `p1` - Normalize optional legacy version strings before comparison - `inst-normalize-version`
23. [x] - `p1` - Prompt interactively for baseline update when needed - `inst-prompt-update-ui`
24. [x] - `p1` - Prompt interactively for migration approval with project and legacy directory context - `inst-prompt-migration-ui`
25. [x] - `p1` - Run follow-up Constructor update and capture JSON output when JSON mode is active - `inst-run-followup-update`
26. [x] - `p1` - Restore target directory backup after failed replacement - `inst-restore-target`
27. [x] - `p1` - Create root file backups before managed block rewrites - `inst-backup-root-files`
28. [x] - `p1` - Refuse root rewrites when AGENTS.md or CLAUDE.md are dirty unless force-overwrite is set - `inst-probe-root-dirty`
29. [x] - `p1` - Execute post-copy rewrite steps in deterministic order and restore root files on rewrite failure - `inst-run-rewrite-steps`
30. [x] - `p1` - Resolve project root from explicit argument, root markers, or git root fallback - `inst-resolve-project-root`
31. [x] - `p1` - Enforce child-directory constraints for source and target options - `inst-child-dir-guard`
32. [x] - `p1` - Read legacy install directory from root AGENTS.md TOML or known legacy directories - `inst-read-legacy-install`
33. [x] - `p1` - Probe dirty root files through git status without failing when git is unavailable - `inst-probe-git-dirty`
34. [x] - `p1` - Replace root managed blocks and warn when malformed legacy blocks must be preserved - `inst-replace-root-blocks`
35. [x] - `p1` - Remove well-formed legacy managed blocks while preserving malformed content for manual cleanup - `inst-remove-legacy-block`
36. [x] - `p1` - Migrate core TOML kit keys, kit paths, kit sources, and obsolete system section - `inst-migrate-core-toml`
37. [x] - `p1` - Migrate artifacts TOML systems from legacy kit slug to canonical SDLC kit slug - `inst-migrate-artifacts-toml`
38. [x] - `p1` - Recursively walk `config/**/*.md` (via `rglob("*.md")`) and apply four conservative substitutions: `{cypilot_path}` → `{cf-studio-path}`, backtick-`cpt` → backtick-`cfs`, space-surrounded `cpt` → `cfs`, `Cypilot` → `Constructor Studio`; returns changed paths as POSIX strings relative to the config dir - `inst-migrate-config-markdown`
39. [x] - `p1` - Rewrite the `{cypilot_path}` template placeholder to `{cf-studio-path}` across config TOML files (e.g. `pr-review.toml`) under the migrated config dir - `inst-migrate-config-toml-template-vars`
40. [x] - `p1` - Run `cfs kit update` after migration so renamed kit sources pull their latest release from the canonical `constructorfabric/studio-kit-sdlc` (or the user's mirror); honor `--dry-run` by recording the planned action only; **in JSON mode** suppress `cfs kit update` sub-command stdout via `contextlib.redirect_stdout` so the outer migration JSON remains the sole document on the wire - `inst-followup-kit-update`
41. [x] - `p1` - Render human migration summary with actions and warnings - `inst-human-output`
42. [x] - `p1` - Defer-import cleanup helpers from `agents.py` (one source of truth for legacy-artifact recognition) and short-circuit with a warning if the import fails - `inst-cleanup-legacy-host-import`
43. [x] - `p1` - Sweep each supported host (`claude`, `windsurf`, `cursor`, `copilot`, `openai`) and remove pre-rebrand `cypilot-*` / `cf-constructor-*` agent files, skill directories, install markers, and per-tool single-file legacy skill paths whose body is a pure generator stub; preserve user-edited files; collect `{agent: [relpath, ...]}` of removals - `inst-cleanup-legacy-host-sweep`
44. [x] - `p1` - For every host with at least one removed artifact, regenerate fresh `cf-*` integration inline via `_process_single_agent`; surface per-host regeneration failure as a non-fatal warning; return `{"removed": {agent: [relpath, ...]}, "regenerated": [agent, ...]}` - `inst-cleanup-legacy-host-regen`

## 3. Processes / Business Logic (CDSL)

### Resolve Skill Target

- [x] `p1` - **ID**: `cpt-studio-algo-core-infra-resolve-skill`

**Input**: Current working directory, command arguments

**Output**: Path to skill engine entry point, or error

**Steps**:
1. [x] - `p1` - Walk from current directory upward looking for `AGENTS.md` with `<!-- @cf:root-agents -->` marker, read `cf-studio-path` variable to get install dir - `inst-walk-parents`
2. [x] - `p1` - **IF** install dir found and skill entry point exists at `{cf-studio-path}/.core/skills/studio/scripts/studio.py` - `inst-if-marker`
   1. [x] - `p1` - **RETURN** path to project skill engine - `inst-return-project-path`
3. [x] - `p1` - **ELSE** check `~/.cf-studio/cache/` for cached skill bundle - `inst-check-global-cache`
4. [x] - `p1` - **IF** cache exists - `inst-if-cache-exists`
   1. [x] - `p1` - **RETURN** path to cached skill engine - `inst-return-cache-path`
5. [x] - `p1` - **ELSE** **RETURN** error: no skill found - `inst-return-not-found`

**Supporting**:
- [x] - `p1` - Imports, constants (marker, regex patterns), project root finder, TOML markdown parser, studio path reader, install dir finder, cache dir/version file getters, cached/project version readers - `inst-resolve-helpers`

### Route Command

- [x] `p1` - **ID**: `cpt-studio-algo-core-infra-route-command`

**Input**: Command name, arguments, resolved skill path

**Output**: JSON to stdout, exit code

**Steps**:
1. [x] - `p1` - Parse command name from first positional argument - `inst-parse-command`
2. [x] - `p1` - Look up command handler in registry - `inst-lookup-handler`
3. [x] - `p1` - **IF** handler not found - `inst-if-no-handler`
   1. [x] - `p1` - **RETURN** error JSON: `{error: "Unknown command"}` (exit 1) - `inst-return-unknown`
4. [x] - `p1` - Parse remaining arguments per handler's argument spec - `inst-parse-args`
5. [x] - `p1` - Verify root AGENTS.md integrity (re-inject if missing/stale) - `inst-verify-agents`
6. [x] - `p1` - Execute handler with parsed arguments - `inst-execute-handler`
7. [x] - `p1` - Serialize handler result to JSON on stdout - `inst-serialize-json`
8. [x] - `p1` - **RETURN** exit code from handler (0=PASS, 1=error, 2=FAIL) - `inst-return-code`

**Supporting**:
- [x] - `p1` - Imports, command wrapper functions, context loading, help text, command descriptions, section layout, `__main__` block - `inst-route-helpers`

### Define Root System

- [x] `p1` - **ID**: `cpt-studio-algo-core-infra-define-root-system`

**Input**: Project directory path

**Output**: System definition `{name, slug}`

**Steps**:
1. [x] - `p1` - Extract directory basename from project path (e.g., `/path/to/my-app` → `my-app`) - `inst-extract-basename`
2. [x] - `p1` - Derive slug: lowercase, replace spaces/underscores with hyphens, strip non-alphanumeric - `inst-derive-slug`
3. [x] - `p1` - Derive name: convert slug to PascalCase (e.g., `my-app` → `MyApp`) - `inst-derive-name`
4. [x] - `p1` - **RETURN** `{name, slug}` - `inst-return-system-def`

### Create Config Directory

- [x] `p1` - **ID**: `cpt-studio-algo-core-infra-create-config`

**Input**: Studio directory path, root system definition

**Output**: Created `core.toml` and `artifacts.toml` in studio directory

**Steps**:
1. [x] - `p1` - Create studio directory if absent - `inst-mkdir-config`
2. [x] - `p1` - Create `{cf-studio-path}/kits/` directory - `inst-mkdir-kits`
3. [x] - `p1` - Write `core.toml` with: kits registration (including per-kit config output paths), project root (system identity is written to `artifacts.toml` per `cpt-studio-adr-remove-system-from-core-toml`) - `inst-write-core-toml`
4. [x] - `p1` - Write `artifacts.toml` with default registry (systems, autodetect rules, codebase, ignore patterns) - `inst-write-artifacts-toml`
5. [x] - `p2` - Validate files against schemas before final write - `inst-validate-schemas`
6. [x] - `p1` - **RETURN** paths to created files - `inst-return-config-paths`

### Inject Root AGENTS.md

- [x] `p1` - **ID**: `cpt-studio-algo-core-infra-inject-root-agents`

**Input**: Project root path, install directory path

**Output**: Updated or created `{project_root}/AGENTS.md`

**Steps**:
1. [x] - `p1` - Validate target file path is within project root; raise error if it would escape - `inst-validate-path`
2. [x] - `p1` - Compute managed block content: TOML fenced block with `cf-studio-path = "{install_dir}"`, navigation rule `ALWAYS open and follow {cf-studio-path}/config/AGENTS.md FIRST` - `inst-compute-block`
3. [x] - `p1` - **IF** `{project_root}/AGENTS.md` does not exist - `inst-if-no-agents`
   1. [x] - `p1` - Create file with managed block wrapped in `<!-- @cf:root-agents -->` markers - `inst-create-agents-file`
3. [x] - `p1` - **ELSE** read existing file content - `inst-read-existing`
   1. [x] - `p1` - **IF** managed block markers found - `inst-if-markers-exist`
      1. [x] - `p1` - Replace content between markers with computed block - `inst-replace-block`
   2. [x] - `p1` - **ELSE** insert managed block at beginning of file - `inst-insert-block`
4. [x] - `p1` - Write file - `inst-write-agents`
5. [x] - `p1` - **RETURN** path to AGENTS.md - `inst-return-agents-path`

### Cache Skill from GitHub

- [x] `p1` - **ID**: `cpt-studio-algo-core-infra-cache-skill`

**Input**: Target ref (optional, defaults to "latest") — accepts version tag (v3.0.0), branch name (main), or commit SHA

**Output**: Path to cached skill bundle at `~/.cf-studio/cache/`, or error

**Steps**:
1. [x] - `p1` - Create `~/.cf-studio/cache/` directory if absent - `inst-mkdir-cache`
2. [x] - `p1` - Resolve target version: if "latest", query GitHub API for latest release tag - `inst-resolve-version`
3. [x] - `p1` - **IF** cached version matches target version - `inst-if-cache-fresh`
   1. [x] - `p1` - **RETURN** existing cache path (no download needed) - `inst-return-cache-hit`
4. [x] - `p1` - Download skill bundle archive from GitHub release asset - `inst-download-archive`
5. [x] - `p1` - **IF** download fails (network error, 404, rate limit) - `inst-if-download-error`
   1. [x] - `p1` - **RETURN** error with HTTP status and retry suggestion - `inst-return-download-fail`
6. [x] - `p1` - Extract archive into `~/.cf-studio/cache/` (overwrite previous) - `inst-extract-archive`
7. [x] - `p1` - Write version marker file `~/.cf-studio/cache/.version` with downloaded version - `inst-write-version`
8. [x] - `p1` - **RETURN** path to cached skill bundle - `inst-return-cache-path-new`

**Supporting**:
- [x] - `p1` - Imports, constants (GitHub owner/repo, API base, user agent), API URL resolver, latest version resolver, local copy function, archive extraction helpers (tar prefix, tar extract, zip prefix, zip extract) - `inst-cache-helpers`

### Create Config AGENTS.md

- [x] `p1` - **ID**: `cpt-studio-algo-core-infra-create-config-agents`

**Input**: Studio directory path, installed kits list

**Output**: Created `{cf-studio-path}/config/AGENTS.md`

**Steps**:
1. [x] - `p1` - Generate default WHEN rules for artifacts.toml, schemas, requirements - `inst-gen-when-rules`
2. [x] - `p1` - Write `{cf-studio-path}/config/AGENTS.md` with navigation header and WHEN rules - `inst-write-config-agents`
3. [x] - `p1` - **RETURN** path to created file - `inst-return-config-agents-path`

### Display Project Info

- [ ] `p1` - **ID**: `cpt-studio-algo-core-infra-display-info`

**Input**: Start path (default: current directory), optional studio-root override

**Output**: JSON with project root, studio directory, config, and registry details

**Steps**:
1. [x] - `p1` - Parse arguments: `--root`, `--studio-root` - `inst-info-parse-args`
2. [x] - `p1` - Find project root from start path - `inst-info-find-root`
3. [x] - `p1` - **IF** project root not found - `inst-info-if-no-root`
   1. [x] - `p1` - **RETURN** JSON: `{status: NOT_FOUND, hint}` (exit 1) - `inst-info-return-no-root`
4. [x] - `p1` - Find studio directory - `inst-info-find-studio`
5. [x] - `p1` - **IF** studio directory not found - `inst-info-if-no-studio`
   1. [x] - `p1` - **RETURN** JSON: `{status: NOT_FOUND, hint}` (exit 1) - `inst-info-return-no-studio`
6. [x] - `p1` - Load studio config from directory - `inst-info-load-config`
7. [x] - `p1` - Locate artifacts registry (config/artifacts.toml, fallback to legacy paths) - `inst-info-locate-registry`
8. [x] - `p1` - **IF** registry found — load and expand with autodetect data - `inst-info-expand-registry`
9. [x] - `p1` - **ELSE** — set registry to null with error code - `inst-info-registry-missing`
10. [x] - `p1` - Compute relative path and config presence - `inst-info-compute-metadata`
11. [ ] - `p1` - **FOR EACH** installed kit with resource bindings: collect resolved resource variables from `core.toml` `[kits.{slug}.resources]` - `inst-info-collect-resources`
12. [x] - `p1` - Detect and display workspace config status in info output - `inst-info-workspace-section`
13. [x] - `p1` - **RETURN** JSON: `{status: FOUND, project_root, config, registry, workspace}` (exit 0) - `inst-info-return-ok`

**Supporting**:
- [x] - `p1` - Human-friendly output formatter for info command (callback passed to ui.result) - `inst-info-human-fmt`
- [x] - `p1` - JSON mode flag: `_json_mode` global, `set_json_mode`, `is_json_mode` - `inst-ui-json-mode-flag`
- [x] - `p1` - ANSI escape code constants and color availability/application helpers - `inst-ui-ansi-helpers`
- [x] - `p1` - `header`: print bold section header to stderr (suppressed in JSON mode) - `inst-ui-progress-header`
- [x] - `p1` - `step` / `substep`: progress step indicators printed to stderr - `inst-ui-progress-step`
- [x] - `p1` - `success` / `error` / `warn` / `info`: status message printers to stderr - `inst-ui-status-messages`
- [x] - `p1` - `detail` / `hint` / `blank` / `divider`: supplementary output helpers to stderr - `inst-ui-detail-hint`
- [x] - `p1` - `table`: aligned column table renderer to stderr - `inst-ui-table`
- [x] - `p1` - `file_action`: file-change icon printer (created/updated/unchanged/etc.) to stderr - `inst-ui-file-action`
- [x] - `p1` - `result` JSON branch: serialize result dict as JSON to stdout in `--json` mode - `inst-ui-result-json`
- [x] - `p1` - `result` human branch: invoke `human_fn` or generic status/message fallback to stderr - `inst-ui-result-human`
- [x] - `p1` - `relpath`: convert absolute path to cwd-relative path with fallback - `inst-ui-relpath`
- [x] - `p1` - `_UI` singleton class exposing all helpers as static methods via `ui` module attribute - `inst-ui-singleton`

### Project Root Detection

- [x] `p1` - **ID**: `cpt-studio-algo-core-infra-project-root-detection`

**Input**: Start path (directory to begin searching from)

1. [x] - `p1` - Resolve start path to absolute - `inst-root-resolve-start`
2. [x] - `p1` - Walk up directory hierarchy (max 25 levels) looking for AGENTS.md with `@cf:root-agents` marker or `.git` directory - `inst-root-walk-up`
3. [x] - `p1` - **IF** found AGENTS.md with marker **RETURN** that directory as project root - `inst-root-found-agents`
4. [x] - `p1` - **IF** found `.git` **RETURN** that directory as project root - `inst-root-found-git`
5. [x] - `p1` - **ELSE RETURN** None - `inst-root-not-found`

**Supporting**:
- [x] - `p1` - Imports, constants, and path helper functions (core_subpath, config_subpath, cfg_get_str) - `inst-root-datamodel`

### Config Management

- [ ] `p1` - **ID**: `cpt-studio-algo-core-infra-config-management`

**Input**: Adapter directory path, project root

1. [x] - `p1` - Read `cf-studio-path` variable from root AGENTS.md TOML block - `inst-cfg-read-var`
2. [x] - `p1` - Load project config from `config/core.toml` (with fallback to flat layout) - `inst-cfg-load-core`
3. [x] - `p1` - Find studio directory: priority 1 = TOML variable, priority 2 = recursive search - `inst-cfg-find-dir`
4. [x] - `p1` - Load studio config from AGENTS.md and rules directory - `inst-cfg-load-config`
5. [x] - `p1` - Load artifacts registry from `artifacts.toml` (with fallback chain) - `inst-cfg-load-registry`
6. [ ] - `p1` - Read/write resource bindings: manage `[kits.{slug}.resources]` section in `core.toml` for manifest-driven kits. Provide lookup API so other components can resolve `{identifier}` template variables to filesystem paths - `inst-cfg-resource-bindings`

**Supporting**:
- [x] - `p1` - Helper functions: studio root detection from config, registry entry iteration, directory type detection, text file loader - `inst-cfg-helpers`

### TOML Utilities

- [x] `p1` - **ID**: `cpt-studio-algo-core-infra-toml-utils`

**Input**: TOML text or file path, or markdown text with embedded TOML blocks

1. [x] - `p1` - Parse TOML string or file using stdlib `tomllib` - `inst-toml-parse`
2. [x] - `p1` - Extract and merge TOML fenced code blocks from markdown text - `inst-toml-from-markdown`
3. [x] - `p1` - Serialize nested dict to TOML format (tables, arrays of tables, scalars) - `inst-toml-serialize`

**Supporting**:
- [x] - `p1` - Imports, type alias, regex constants, and deep merge helper - `inst-toml-datamodel`

### Registry Parsing

- [x] `p1` - **ID**: `cpt-studio-algo-core-infra-registry-parsing`

**Input**: Path to adapter directory containing artifacts.toml and core.toml

1. [x] - `p1` - Locate artifacts registry file (config/artifacts.toml, fallback to legacy paths) - `inst-reg-locate`
2. [x] - `p1` - Parse registry data and merge fields from core.toml (version, project_root, kits) - `inst-reg-parse-merge`
3. [x] - `p1` - Build ArtifactsMeta from parsed dict: parse kits, systems hierarchy, ignore rules - `inst-reg-build-meta`
4. [x] - `p1` - Expand autodetect rules into concrete artifact/codebase entries via glob matching - `inst-reg-expand-autodetect`
5. [x] - `p1` - **RETURN** ArtifactsMeta with indexed artifacts and system tree - `inst-reg-return`
6. [x] - `p1` - Define registry data model: Kit, Artifact, CodebaseEntry, IgnoreBlock, AutodetectRule, SystemNode dataclasses with from_dict parsing and slug validation - `inst-reg-dataclasses`
7. [x] - `p1` - Query and iteration methods: get artifact by path, iterate all artifacts/codebase/systems, collect system prefixes, validate slugs - `inst-reg-query-methods`
8. [x] - `p1` - Utility functions: create backup, extract system slug from cfs ID, generate slug from name, generate default registry for new projects - `inst-reg-utilities`

### Context Loading

- [x] `p1` - **ID**: `cpt-studio-algo-core-infra-context-loading`

**Input**: Optional start path

1. [x] - `p1` - Find studio directory and load artifacts registry - `inst-ctx-find-and-load`
2. [x] - `p1` - **FOR EACH** registered kit, load constraints and templates - `inst-ctx-load-kits`
3. [x] - `p1` - **FOR EACH** manifest-driven kit, load resource bindings from `core.toml` and resolve resource paths (constraints, templates, examples may be at non-default locations) - `inst-ctx-load-resource-bindings`
   - [x] - `p1` - If `constraints` binding exists and file is present, use binding path for `load_constraints_toml` instead of default kit root - `inst-constraints-from-binding`
4. [x] - `p1` - Expand autodetect rules into concrete artifact/codebase entries - `inst-ctx-expand-autodetect`
5. [x] - `p1` - Collect registered system prefixes - `inst-ctx-collect-systems`
6. [x] - `p1` - Build StudioContext with all loaded metadata - `inst-ctx-build-primary`
7. [x] - `p1` - Attempt workspace upgrade: call `WorkspaceContext.load(primary_ctx)` to discover workspace config via core.toml `workspace` key (string path or inline dict), falling back to standalone `.studio-workspace.toml` at project root - `inst-ctx-workspace-upgrade`
8. [x] - `p1` - **IF** workspace found — load source contexts, resolve reachability, **RETURN** WorkspaceContext - `inst-ctx-return-workspace`
9. [x] - `p1` - **ELSE RETURN** StudioContext (single-repo mode) - `inst-ctx-return`

**Supporting**:
- [x] - `p1` - Define context data model: LoadedKit, StudioContext dataclasses, imports - `inst-ctx-datamodel`
- [x] - `p1` - Global context management: get/set/ensure context singleton, get_known_id_kinds query - `inst-ctx-globals`

### Mirror Override

- [ ] `p1` - **ID**: `cpt-studio-algo-core-infra-mirror-override`

**Input**: URL to redirect (any default GitHub URL produced by Constructor Studio)

**Output**: Rewritten URL after applying matching override, or the original URL when no override applies

**Steps**:
1. [ ] - `p1` - Load merged override entries from XDG (`${XDG_CONFIG_HOME:-~/.config}/constructor-studio/mirrors.toml`) and brand-home (`~/.constructor-studio/mirrors.toml`); brand-home wins on duplicate `from` key - `inst-load-overrides`
2. [ ] - `p1` - Canonicalize the input URL: strip `https://` / `http://` / `ssh://` / `git@` prefix, trailing `.git`, trailing `/` - `inst-canonicalize-url`
3. [ ] - `p1` - Apply longest-prefix match across the merged override `from` keys - `inst-longest-prefix-match`
4. [ ] - `p1` - **IF** a match is found - `inst-if-match`
   1. [ ] - `p1` - **RETURN** the rewritten URL with the matched `from` replaced by its `to` - `inst-return-rewritten`
5. [ ] - `p1` - **ELSE** **RETURN** the original (un-rewritten) URL - `inst-return-original`

**Supporting**:
- [ ] - `p1` - TOML readers for both config locations, write-target resolution (existing brand-home wins, else existing XDG, else create XDG), `set_override` / `remove_override` / `list_overrides` helpers, URL canonicalizer - `inst-mirror-helpers`
- [x] - `p1` - XDG and brand-home config path resolvers for `mirrors.toml` locations - `inst-mirror-config-paths`
- [x] - `p1` - `_load_file`: parse a single `mirrors.toml` file into `(from, to)` tuple list - `inst-mirror-load-file`
- [x] - `p1` - `_load_overrides`: merge XDG and brand-home entries; brand-home wins on duplicate `from` - `inst-mirror-merge-overrides`
- [x] - `p1` - `apply_override`: apply all registered overrides as substring replacements to a URL - `inst-mirror-apply-override`

## 4. States (CDSL)

### Project Installation State

- [x] `p1` - **ID**: `cpt-studio-state-core-infra-project-install`

**States**: UNINITIALIZED, INITIALIZED, STALE

**Initial State**: UNINITIALIZED

**Transitions**:
1. [x] - `p1` - **FROM** UNINITIALIZED **TO** INITIALIZED **WHEN** `cfs init` completes successfully - `inst-init-complete`
2. [x] - `p1` - **FROM** INITIALIZED **TO** STALE **WHEN** cached skill version is newer than project skill version - `inst-version-mismatch`
3. [x] - `p1` - **FROM** STALE **TO** INITIALIZED **WHEN** `cfs update` completes successfully - `inst-update-complete`

## 5. Definitions of Done

### CLI Proxy Routes Commands

- [x] `p1` - **ID**: `cpt-studio-dod-core-infra-cli-routes`

The system **MUST** provide a global `studio` (and `cpt` alias) CLI entry point that resolves the skill target (project-installed or cached) and forwards all commands with their arguments, returning JSON output and appropriate exit codes.

**Implements**:
- `cpt-studio-flow-core-infra-cli-invocation`
- `cpt-studio-algo-core-infra-resolve-skill`
- `cpt-studio-algo-core-infra-route-command`

**Covers (PRD)**:
- `cpt-studio-fr-core-installer`
- `cpt-studio-fr-core-skill-engine`
- `cpt-studio-nfr-adoption-usability`

**Covers (DESIGN)**:
- `cpt-studio-principle-determinism-first`
- `cpt-studio-principle-zero-harm`
- `cpt-studio-constraint-python-stdlib`
- `cpt-studio-constraint-cross-platform`
- `cpt-studio-component-cli-proxy`
- `cpt-studio-component-skill-engine`

### Global CLI Package

- [x] `p1` - **ID**: `cpt-studio-dod-core-infra-global-package`

The project **MUST** provide a Python package `studio` that acts as the global CLI proxy. The package **MUST** be installable via `pipx install git+https://github.com/{org}/studio.git` (or from PyPI when published). The package **MUST** contain only the thin proxy logic — skill resolution, cache management, command forwarding — with zero third-party dependencies (Python stdlib only). The package **MUST** register `studio` and `cpt` as console entry points. The package **MUST** work natively on Linux, Windows, and macOS.

**Implements**:
- `cpt-studio-flow-core-infra-cli-invocation`
- `cpt-studio-algo-core-infra-resolve-skill`

**Covers (PRD)**:
- `cpt-studio-fr-core-installer`
- `cpt-studio-nfr-adoption-usability`

**Covers (DESIGN)**:
- `cpt-studio-constraint-python-stdlib`
- `cpt-studio-constraint-cross-platform`
- `cpt-studio-component-cli-proxy`

### Skill Cache Downloads from GitHub

- [x] `p1` - **ID**: `cpt-studio-dod-core-infra-skill-cache`

The system **MUST** provide a cache mechanism in the CLI proxy that downloads the skill bundle from a GitHub release into `~/.cf-studio/cache/` on first invocation (or when cache is empty/stale). The download **MUST** be automatic and transparent — no separate manual step beyond `pipx install studio`. The proxy **MUST** report actionable errors on download failure.

**Implements**:
- `cpt-studio-algo-core-infra-cache-skill`

**Covers (PRD)**:
- `cpt-studio-fr-core-installer`
- `cpt-studio-nfr-adoption-usability`

**Covers (DESIGN)**:
- `cpt-studio-component-cli-proxy`

### Init Creates Full Config

- [x] `p1` - **ID**: `cpt-studio-dod-core-infra-init-config`

The system **MUST** provide a `cfs init` command that copies skill bundle from cache, defines the root system from the project directory name, creates `{cf-studio-path}/kits/` directory, creates `{cf-studio-path}/config/core.toml` with kit registrations and project root, creates `{cf-studio-path}/config/artifacts.toml` with root system definition and default autodetect rules, injects the root `AGENTS.md` managed block, creates `{cf-studio-path}/config/AGENTS.md` with default WHEN rules, and prompts the user to install the SDLC kit with `[a]ccept / [d]ecline`. If accepted, the kit is downloaded from GitHub and installed inline.

**Implements**:
- `cpt-studio-flow-core-infra-project-init`
- `cpt-studio-algo-core-infra-define-root-system`
- `cpt-studio-algo-core-infra-create-config`
- `cpt-studio-algo-core-infra-inject-root-agents`
- `cpt-studio-algo-core-infra-create-config-agents`

**Covers (PRD)**:
- `cpt-studio-fr-core-init`
- `cpt-studio-fr-core-config`
- `cpt-studio-nfr-adoption-usability`

**Covers (DESIGN)**:
- `cpt-studio-principle-tool-managed-config`
- `cpt-studio-principle-occams-razor`
- `cpt-studio-constraint-git-project-heuristics`
- `cpt-studio-component-config-manager`
- `cpt-studio-seq-init`

### Root AGENTS.md Integrity

- [x] `p1` - **ID**: `cpt-studio-dod-core-infra-agents-integrity`

The system **MUST** verify the root `AGENTS.md` managed block on every CLI invocation (not just init). If the `<!-- @cf:root-agents -->` block is missing, stale, or the file does not exist, the system silently re-injects it with the correct block pointing to the `{cf-studio-path}/` directory.

**Implements**:
- `cpt-studio-algo-core-infra-inject-root-agents`

**Covers (PRD)**:
- `cpt-studio-fr-core-init`

**Covers (DESIGN)**:
- `cpt-studio-principle-zero-harm`
- `cpt-studio-component-skill-engine`

### Usage Telemetry

- [x] `p1` - **ID**: `cpt-studio-dod-core-infra-telemetry`

The system **MUST** provide non-blocking usage telemetry in the CLI proxy that records every invocation. The telemetry module **MUST**: collect git user identity (`user.name`, `user.email`) and remote URL via a single `git config --get-regexp` subprocess call; append JSONL records to `~/.cf-studio/logs/YYYY-MM-DD.log`; optionally POST OTLP Logs JSON to `CFS_TELEMETRY_URL`; rotate old log files when a new day's file is created; log HTTP errors to the local log file (never to stderr); be fully disableable via `CFS_TELEMETRY=0`; use only Python stdlib.

**Implements**:
- `cpt-studio-flow-core-infra-cli-invocation`

**Covers (PRD)**:
- `cpt-studio-fr-core-telemetry`

**Covers (DESIGN)**:
- `cpt-studio-component-cli-proxy`
- `cpt-studio-constraint-python-stdlib`

### 5.x Mirror Override

- [x] `p1` - **ID**: `cpt-studio-dod-core-infra-mirror-override`

The system **MUST** provide a global mirror-override capability (`cfs mirror`) that intercepts and rewrites any default download or API URL before network operations are performed. This enables users who mirror GitHub repositories (e.g., on air-gapped networks, corporate proxies, or private GitHub Enterprise instances) to redirect Constructor Studio's default URLs without modifying source code or config files.

#### Design

- **Module**: `src/studio_proxy/mirrors.py` exports `load_overrides()`, `apply_override(url) -> url`, `set_override(old, new)`, `remove_override(old)`, `list_overrides()`.
- **Dual-location config**: overrides are stored in TOML files at two locations, read in merge order: (1) `${XDG_CONFIG_HOME:-~/.config}/constructor-studio/mirrors.toml` and (2) `~/.constructor-studio/mirrors.toml`. On duplicate `from` key the second location wins (brand-home overrides XDG).
- **Write-target resolution**: new override writes go to `~/.constructor-studio/mirrors.toml` if it already exists; else to the XDG path if it exists; else create the XDG path (preferred for new installs).
- **TOML format**:
  ```toml
  [[mirror]]
  from = "github.com/constructorfabric/studio"
  to   = "github.com/myorg/studio"
  ```
- **URL canonicalization**: strip scheme (`https://`, `http://`), strip trailing `.git`, strip trailing `/` before matching and storing.
- **Match semantics**: longest-prefix match on the canonicalized URL. Applied before any GitHub API call, git clone, or asset download.
- **Integration points**: `cache.py` `_resolve_api_base` and `download_and_cache`; `init`/`update` URL forwarding; kit `source = "github:..."` autodetect resolution.

#### CLI Verbs

```
cfs mirror override <old-url> <new-url>   # register or update an override
cfs mirror list                           # print effective merged set with source path
cfs mirror remove <old-url>              # delete an override
cfs mirror clear                          # delete all overrides
```

#### Reference

See ADR-0020 (`architecture/ADR/0020-cpt-studio-adr-rebrand-and-mirror-override-v1.md`) for the full decision record including rationale, write-target resolution algorithm, and backwards-compatibility notes.

**Covers (PRD)**:
- `cpt-studio-fr-core-mirror-override`

---

## 6. Implementation Modules

| Module | Path | Responsibility |
|--------|------|----------------|
| CLI Proxy | `src/studio_proxy/cli.py` | Global CLI entry point, command routing, version check |
| Skill Resolver | `src/studio_proxy/resolve.py` | Project root detection, skill target resolution |
| Cache Manager | `src/studio_proxy/cache.py` | GitHub download, local copy, archive extraction |
| Telemetry | `src/studio_proxy/telemetry.py` | Non-blocking usage telemetry: local JSONL logs, OTLP HTTP, log rotation |
| Skill Engine CLI | `skills/.../cli.py` | Skill engine command dispatch |
| Init Command | `skills/.../commands/init.py` | Project initialization, directory creation |
| Adapter Info | `skills/.../commands/adapter_info.py` | `info` command — display project config |
| File Utilities | `skills/.../utils/files.py` | Project root discovery, config loading, path resolution |
| Context | `skills/.../utils/context.py` | Global context management, registry loading |
| Constants | `skills/.../constants.py` | Regex patterns, config filenames |
| TOML Utilities | `skills/.../utils/toml_utils.py` | TOML reading/writing, markdown TOML extraction |
| Artifacts Meta | `skills/.../utils/artifacts_meta.py` | Artifacts registry parsing, autodetect expansion |
| Mirror Override | `src/studio_proxy/mirrors.py` | URL override load/apply/set/remove/list; dual-location config; canonicalization |

## 7. Acceptance Criteria

- [x] `cfs init` creates `{cf-studio-path}/config/core.toml` (kit registrations) and `{cf-studio-path}/config/artifacts.toml` with correct root system definition
- [x] `cfs init` in an already-initialized project returns exit code 2 with helpful message
- [x] `cfs <command>` from inside a project routes to project skill; from outside routes to cache
- [x] First `studio` invocation after `pipx install` with empty cache automatically downloads skill from GitHub
- [x] `cfs update [VERSION|BRANCH]` downloads specified version/branch/SHA into cache
- [x] Download failure produces actionable error message with HTTP status
- [x] All commands output JSON to stdout and use exit codes 0/1/2
- [x] Root `AGENTS.md` managed block is verified and re-injected on every CLI invocation
- [x] Background version check does not block command execution
- [x] `{cf-studio-path}/config/AGENTS.md` is created with default WHEN rules for artifacts registry
