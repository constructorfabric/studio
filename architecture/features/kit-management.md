# Feature: Kit Management

<!-- toc -->

- [1. Feature Context](#1-feature-context)
  - [1. Overview](#1-overview)
  - [2. Purpose](#2-purpose)
  - [3. Actors](#3-actors)
  - [4. References](#4-references)
- [2. Actor Flows (CDSL)](#2-actor-flows-cdsl)
  - [Kit Install CLI](#kit-install-cli)
  - [Kit Update CLI](#kit-update-cli)
  - [Kit Validate CLI](#kit-validate-cli)
  - [Kit Normalize CLI](#kit-normalize-cli)
  - [Kit CLI Dispatcher](#kit-cli-dispatcher)
- [3. Processes / Business Logic (CDSL)](#3-processes--business-logic-cdsl)
  - [GitHub Helpers](#github-helpers)
  - [GitHub Kit Version Authority](#github-kit-version-authority)
  - [Kit Content Management](#kit-content-management)
  - [Gen Aggregation](#gen-aggregation)
  - [Kit Installation](#kit-installation)
  - [Kit Update](#kit-update)
  - [File-Level Kit Update](#file-level-kit-update)
  - [Kit File Enumeration](#kit-file-enumeration)
  - [Kit File Classification](#kit-file-classification)
  - [Kit Interactive Review](#kit-interactive-review)
  - [Kit Diff Display](#kit-diff-display)
  - [Kit Conflict Merge](#kit-conflict-merge)
  - [Kit TOC Handling](#kit-toc-handling)
  - [Kit Whatsnew Display](#kit-whatsnew-display)
  - [Kit Snapshot](#kit-snapshot)
  - [Kit Validation Engine](#kit-validation-engine)
  - [Kit Validate by Path](#kit-validate-by-path)
  - [Kit Config Helpers](#kit-config-helpers)
  - [Kit Source Mode Validation](#kit-source-mode-validation)
  - [Universal Kit Model Normalization](#universal-kit-model-normalization)
  - [Canonical `.cf-studio-kit.toml`](#canonical-cf-studio-kittoml)
  - [Local Path Install Mode](#local-path-install-mode)
  - [Kit Info Model Output](#kit-info-model-output)
  - [Public Component Generation](#public-component-generation)
  - [Kit Variable Resolution](#kit-variable-resolution)
  - [Kit Update, Drift, and Prune](#kit-update-drift-and-prune)
  - [Tool Permission Risk](#tool-permission-risk)
  - [Kit Manifest Normalization and Migration](#kit-manifest-normalization-and-migration)
  - [Manifest-Driven Installation](#manifest-driven-installation)
  - [Manifest Legacy Migration](#manifest-legacy-migration)
  - [Manifest Resource Resolution](#manifest-resource-resolution)
  - [Manifest Source Path Mapping](#manifest-source-path-mapping)
- [4. States (CDSL)](#4-states-cdsl)
  - [Kit Authority State](#kit-authority-state)
  - [Kit Installation State](#kit-installation-state)
  - [Kit Manifest State](#kit-manifest-state)
  - [Kit Install Mode State](#kit-install-mode-state)
- [5. Definitions of Done](#5-definitions-of-done)
  - [Kit Install Copies Files](#kit-install-copies-files)
  - [Kit Update Shows Diffs](#kit-update-shows-diffs)
  - [Kit Validate Checks Integrity](#kit-validate-checks-integrity)
- [6. Implementation Modules](#6-implementation-modules)
- [7. Acceptance Criteria](#7-acceptance-criteria)

<!-- /toc -->

- [ ] `p1` - **ID**: `cpt-studio-featstatus-kit-management`

## 1. Feature Context

- [ ] `p1` - `cpt-studio-featstatus-kit-management`

### 1. Overview

Manage kit lifecycle — installation, file-level diff updates, interactive conflict resolution, SKILL/AGENTS composition, generated agent entry points, and kit structural validation. Kits are direct file packages (per `cpt-studio-adr-remove-blueprint-system`). New kits use a canonical `.cf-studio-kit.toml` package manifest as their entry point; one manifest may declare either one kit or multiple selectable kits. Legacy `manifest.toml` v1/v2, ADR-0019 component manifests, layout scanning, and `conf.toml` are compatibility inputs normalized into the same internal `KitModel`. For GitHub-backed kits, version authority comes from resolved GitHub Release/tag/ref provenance and content identity, not from kit-local metadata.

### 2. Purpose

Enables users to install, update, and validate kit packages with interactive file-level diffs, automatic `.gen/` aggregation, and structural validation. A kit may be installed from GitHub, generic Git, or any local directory supported by the `KitModel` source precedence: canonical `.cf-studio-kit.toml`, legacy `manifest.toml` v1/v2, `conf.toml + layout`, or installed `core.toml` resource bindings. Local/path installation always asks whether to copy resources into Studio-managed storage or register eligible in-project resources in place. The manifest enumerates resources, public skills, subagents, rules, supporting files, user-modifiable installation paths, and tool-risk configuration for one or more kits in one file. `core.toml` stores installed-state bindings only; it is not source truth. Local/path kit operations are explicitly outside GitHub authority and record local provenance only.

### 3. Actors

| Actor | Role in Feature |
|-------|-----------------|
| `cpt-studio-actor-user` | Runs `cfs kit install`, `cfs kit update`, `cfs validate-kits` |
| `cpt-studio-actor-studio-cli` | Dispatches kit subcommands to skill engine |

### 4. References

- **PRD**: `cpt-studio-fr-core-kits`, `cpt-studio-fr-core-kit-manifest`, `cpt-studio-fr-core-resource-diff`
- **Design**: `cpt-studio-component-kit-manager`, `cpt-studio-component-config-manager`, `cpt-studio-component-validator`
- **ADR**: `cpt-studio-adr-remove-blueprint-system`, `cpt-studio-adr-unified-manifest-hierarchy`

---

## 2. Actor Flows (CDSL)

### Kit Install CLI

- [x] `p1` - **ID**: `cpt-studio-flow-kit-install-cli`

**Actor**: `cpt-studio-actor-user`

**Trigger**: User runs `cfs kit install <owner/repo[@version]> [--kit <slug>|--kit all] [--force] [--dry-run]` or `cfs kit install --path <dir> [--kit <slug>|--kit all] [--force] [--dry-run] [--install-mode copy|register]`

**Steps**:
1. [x] - `p1` - Parse CLI arguments (path, --force, --dry-run) - `inst-parse-args`
2. [x] - `p1` - Validate kit source directory exists - `inst-validate-source`
3. [x] - `p1` - Read kit slug from `.cf-studio-kit.toml` when present; otherwise use legacy metadata (`manifest.toml`, `conf.toml`, or layout adapter) and read `conf.toml version` only as optional local metadata, never as GitHub release authority - `inst-read-slug-version`
4. [x] - `p1` - **IF** `.cf-studio-kit.toml` declares multiple kits: select kits from `--kit <slug>` / repeated `--kit` / `--kit all`; in interactive mode prompt for number, slug, comma-separated list, or `all`; in non-interactive mode fail with available slugs when omitted - `inst-install-select-kit`
5. [x] - `p1` - **IF** installing from GitHub: resolve requested GitHub ref to authoritative GitHub metadata via `cpt-studio-algo-kit-github-version-authority`; set `core.toml [kits.<slug>].version` from GitHub release/ref metadata, not from `conf.toml` - `inst-resolve-github-authority`
6. [x] - `p1` - **IF** installing from `--path`: mark resolver mode as local/path, do not apply GitHub authority, and reject GitHub selector flags or `owner/repo[@ref]` selectors mixed with local/path mode - `inst-validate-source-mode`
7. [x] - `p1` - Resolve project root and studio directory via `_resolve_studio_dir` - `inst-resolve-project`
8. [x] - `p1` - Check if kit already installed; fail if exists without --force - `inst-check-existing`
9. [x] - `p1` - **IF** --dry-run: return preview and STOP - `inst-dry-run`
10. [x] - `p1` - Load the source through `cpt-studio-algo-kit-model-normalize`, with precedence `.cf-studio-kit.toml` > legacy `manifest.toml` v2/v1 > `conf.toml + layout` > `core.toml` resources-only - `inst-load-kit-model`
11. [x] - `p1` - **IF** installing from `--path`: resolve install mode through `cpt-studio-algo-kit-local-path-install-mode`; interactive mode must ask copy vs register, non-interactive mode requires `--install-mode` - `inst-resolve-local-install-mode`
12. [x] - `p1` - **IF** canonical or legacy manifest input is present: delegate to manifest-driven installation via `cpt-studio-algo-kit-manifest-install` using the normalized `KitModel` - `inst-manifest-install`
13. [x] - `p1` - **ELSE**: delegate to `install_kit()` for legacy installation - `inst-delegate-install`
14. [x] - `p1` - Regenerate `.gen/` aggregates via `regenerate_gen_aggregates` - `inst-regen-gen`
15. [x] - `p1` - Format and output result JSON - `inst-output-result`

**Supporting**:
- [x] - `p1` - Resolve GitHub source: parse owner/repo and requested ref, resolve canonical/effective source, requested_ref, resolved_ref, commit_sha/content identity, version display value, verified/freshness state, then download tarball and extract to temp dir - `inst-resolve-github-source`
- [x] - `p1` - Cleanup temporary download directory in finally block - `inst-cleanup-tmp`
- [x] - `p1` - Human-friendly output formatter for install results - `inst-human-output`

### Kit Update CLI

- [x] `p1` - **ID**: `cpt-studio-flow-kit-update-cli`

**Actor**: `cpt-studio-actor-user`

**Trigger**: User runs `cfs kit update <path> [--force] [--dry-run] [--no-interactive] [-y]`

**Steps**:
1. [x] - `p1` - Parse CLI arguments (path, --force, --dry-run, --no-interactive, -y) - `inst-parse-args`
2. [x] - `p1` - Validate kit source directory exists - `inst-validate-source`
2a. [x] - `p1` - Validate source mode: registered GitHub-backed updates use GitHub authority; local `--path` updates are outside GitHub authority and conflict with GitHub selector flags - `inst-validate-source-mode`
3. [x] - `p1` - Read slug from canonical `.cf-studio-kit.toml` when present; otherwise use legacy source metadata - `inst-read-slug`
4. [x] - `p1` - Resolve project root and studio directory - `inst-resolve-project`
5. [x] - `p1` - **IF** kit source contains `whatsnew.toml`: display whatsnew entries via `cpt-studio-algo-kit-whatsnew-display`; in interactive mode prompt to continue or abort - `inst-show-whatsnew`
6. [x] - `p1` - **IF** kit source contains canonical `.cf-studio-kit.toml` or legacy `manifest.toml` and existing install has no resource bindings: trigger legacy install migration via `cpt-studio-algo-kit-manifest-legacy-migration` - `inst-legacy-migration`
7. [x] - `p1` - Delegate to `update_kit()` with interactive/auto_approve/force flags - `inst-delegate-update`
8. [x] - `p1` - Regenerate `.gen/` aggregates (unless dry-run) - `inst-regen-gen`
9. [x] - `p1` - Format version status, accepted/declined files, and output result - `inst-format-output`


**Supporting**:
- [x] - `p1` - Resolve GitHub update targets from registered kit metadata; online resolution refreshes requested_ref, resolved_ref, commit_sha/content identity, canonical/effective source, verified/freshness state, and display version; offline fallback uses the last-known persisted state only and MUST NOT infer authority from local kit files - `inst-resolve-github-targets`
- [x] - `p1` - Build normalized update result dict from kit update output - `inst-build-update-result`
- [x] - `p1` - Human-friendly output formatter for update results - `inst-human-output`

### Kit Validate CLI

- [x] `p1` - **ID**: `cpt-studio-flow-kit-validate-cli`

**Actor**: `cpt-studio-actor-user`

**Trigger**: User runs `cfs validate-kits [path] [--kit ID] [--verbose]`

**Steps**:
1. [x] - `p1` - Parse CLI arguments (optional path, --kit, --verbose) - `inst-parse-args`
2. [x] - `p1` - **IF** path provided: validate standalone kit via `_validate_kit_by_path` - `inst-path-mode`
3. [x] - `p1` - **ELSE**: get context and run `run_validate_kits` for registered kits - `inst-registered-mode`
4. [x] - `p1` - Output result JSON with human formatter - `inst-output-result`

**Supporting**:
- [x] - `p1` - Imports and module setup for validate-kits command - `inst-validate-kits-imports`
- [x] - `p1` - Human-friendly formatter and error display helpers for validate-kits output - `inst-validate-kits-format`

### Kit Normalize CLI

- [x] `p1` - **ID**: `cpt-studio-flow-kit-normalize-cli`

**Actor**: `cpt-studio-actor-user`

**Trigger**: User runs `cfs kit normalize <path> [--from manifest|layout|core] [--output <path>] [--dry-run]`

**Steps**:
1. [x] - `p1` - Parse CLI arguments (path, --from, --output, --dry-run) - `inst-normalize-parse-args`
2. [x] - `p1` - Validate source directory or installed resource binding source exists - `inst-normalize-validate-source`
3. [x] - `p1` - Load source through `cpt-studio-algo-kit-manifest-normalize`, using the shared `KitModel` normalization pipeline - `inst-normalize-load-source`
4. [x] - `p1` - **IF** --dry-run: output migration report and proposed `.cf-studio-kit.toml` without writing - `inst-normalize-dry-run`
5. [x] - `p1` - **ELSE**: write canonical `.cf-studio-kit.toml` to the selected output path and output migration report - `inst-normalize-write-output`

### Kit CLI Dispatcher

- [x] `p1` - **ID**: `cpt-studio-flow-kit-dispatch`

**Actor**: `cpt-studio-actor-studio-cli`

**Trigger**: User runs `cfs kit <subcommand>`

**Steps**:
1. [x] - `p1` - Parse subcommand (install | update | validate | normalize | migrate) - `inst-parse-subcmd`
2. [x] - `p1` - Route to appropriate handler; error on unknown subcommand - `inst-route`

**Supporting**:
- [x] - `p1` - Deprecated `migrate` subcommand handler with deprecation notice - `inst-migrate-deprecated`

---

## 3. Processes / Business Logic (CDSL)

### GitHub Helpers

- [x] `p1` - **ID**: `cpt-studio-algo-kit-github-helpers`

**Input**: GitHub source string (`owner/repo[@ref]`), optional `GITHUB_TOKEN`, optional last-known persisted source state

**Output**: Downloaded kit directory path plus structured GitHub authority metadata

**Steps**:
1. [x] - `p1` - Build HTTP headers for GitHub API (Accept, User-Agent, optional Bearer token) - `inst-github-headers`
2. [x] - `p1` - Parse GitHub source string into owner, repo, and requested_ref; empty requested_ref means resolver chooses latest release/default branch - `inst-parse-source`
3. [x] - `p1` - Resolve GitHub authority: determine resolver_mode, resolution_basis, requested_ref, resolved_ref, commit_sha/content identity, canonical_source, effective_source, version display value, verified state, and freshness state - `inst-resolve-release`
4. [x] - `p1` - Download tarball using the resolved effective ref, extract to temp directory, and return extracted path plus authority metadata - `inst-download`
5. [x] - `p1` - **IF** GitHub cannot be reached and last-known metadata exists: mark freshness as stale/offline and use last-known requested_ref/resolved_ref/commit_sha/version for reporting; do not guess from local files or `conf.toml` - `inst-offline-last-known`

**Supporting**:
- [x] - `p1` - Module imports and dependencies for kit management commands - `inst-kit-imports`

### GitHub Kit Version Authority

- [x] `p1` - **ID**: `cpt-studio-algo-kit-github-version-authority`

**Input**: GitHub owner/repo, requested_ref, resolver mode, optional last-known metadata

**Output**: Structured authority metadata for `core.toml [kits.<slug>]`

**Rules**:
1. [x] - `p1` - For GitHub-backed kits, `core.toml [kits.<slug>].version` is the display/backcompat release version resolved from GitHub; it MUST NOT be read from kit `conf.toml` - `inst-core-version-github-authority`
2. [x] - `p1` - Persist `resolver_mode`, `resolution_basis`, `requested_ref`, `resolved_ref`, `commit_sha` or equivalent content identity, `canonical_source`, `effective_source`, `verified`, and `freshness` in structured metadata under the kit registration - `inst-persist-authority-metadata`
3. [x] - `p1` - `conf.toml version` is optional local/package metadata only; it MAY be reported as migrated/local metadata but MUST NOT drive GitHub update currentness checks - `inst-conf-version-local-only`
4. [x] - `p1` - For latest-release resolution, store the requested selector separately from the resolved release tag and commit identity so future updates can refresh the selector without losing the previous content identity - `inst-store-selector-and-identity`
5. [x] - `p1` - For branch or SHA resolution, store both the requested ref and immutable resolved content identity; currentness checks compare content identity where available - `inst-store-ref-identity`
6. [x] - `p1` - Offline fallback uses the last-known persisted GitHub state and marks freshness stale/offline; it MUST NOT inspect installed files or local `conf.toml` to invent a GitHub version - `inst-offline-authority`

### Kit Content Management

- [x] `p1` - **ID**: `cpt-studio-algo-kit-content-mgmt`

**Input**: Kit source directory, target config directory

**Output**: Copied kit files, seeded config files, collected metadata

**Steps**:
1. [x] - `p1` - Seed config files: copy `.toml` files from kit scripts/ to config/ (only if missing) - `inst-seed-configs`
2. [x] - `p1` - Copy kit content: iterate `_KIT_CONTENT_DIRS` and `_KIT_CONTENT_FILES`, copy from source to config/kits/{slug}/ - `inst-copy-content`
3. [x] - `p1` - Collect kit metadata: read SKILL.md for navigation line, AGENTS.md for content aggregation - `inst-collect-metadata`

**Supporting**:
- [x] - `p1` - Wrapper function for metadata collection from installed kit directory - `inst-collect-metadata-fn`
- [x] - `p1` - Kit content directory/file constants and config extension definitions - `inst-content-constants`

### Gen Aggregation

- [x] `p1` - **ID**: `cpt-studio-algo-kit-regen-gen`

**Input**: Studio adapter directory

**Output**: Updated `.gen/AGENTS.md`, `.gen/SKILL.md`, `.gen/README.md`

**Steps**:
1. [x] - `p1` - Read installed kit registrations from `config/core.toml`; unregistered `config/kits/*` directories never contribute generated aggregate output - `inst-scan-kits`
2. [x] - `p1` - Collect metadata (skill_nav, agents_content) from each registered kit - `inst-collect-all-metadata`
3. [x] - `p1` - Read project name from `config/artifacts.toml [[systems]][0].name` (per `cpt-studio-adr-remove-system-from-core-toml`) - `inst-read-project-name`
4. [x] - `p1` - Compose and write `.gen/AGENTS.md` with navigation rules and kit agent content - `inst-write-gen-agents`
5. [x] - `p1` - Compose and write `.gen/SKILL.md` with per-kit skill navigation pointers - `inst-write-gen-skill`
6. [x] - `p1` - Write `.gen/README.md` using `_gen_readme()` - `inst-write-gen-readme`

**Supporting**:
- [x] - `p1` - Top-level `regenerate_gen_aggregates` function orchestrating all gen steps - `inst-regen-fn`
- [x] - `p1` - Helper to read project name from `config/artifacts.toml` registry - `inst-read-project-name-fn`

### Kit Installation

- [x] `p1` - **ID**: `cpt-studio-algo-kit-install`

**Input**: Kit source path, studio dir, slug, authority metadata or local metadata

**Output**: Result dict with status, files_copied, actions, metadata

**Steps**:
1. [x] - `p1` - Validate kit source directory exists - `inst-validate-source`
2. [x] - `p1` - **IF** normalized kit model is manifest-backed: delegate to `install_kit_with_manifest` and **RETURN** its result - `inst-manifest-install`
3. [x] - `p1` - Copy kit content to `config/kits/{slug}/` via `_copy_kit_content` (legacy path) - `inst-copy-content`
4. [x] - `p1` - **IF** GitHub authority metadata is absent: read version from source `conf.toml` only as optional local/path metadata; **ELSE** ignore `conf.toml version` for authoritative registration - `inst-read-version`
5. [x] - `p1` - Seed config files from kit's scripts/ directory - `inst-seed-configs`
6. [x] - `p1` - Register kit in `core.toml` with path, source mode, display/backcompat version, and structured authority metadata when GitHub-backed - `inst-register-core`
7. [x] - `p1` - Collect metadata for `.gen/` aggregation - `inst-collect-meta`
8. [x] - `p1` - **RETURN** result with status, files_copied, actions, skill_nav, agents_content - `inst-return-result`

### Kit Update

- [x] `p1` - **ID**: `cpt-studio-algo-kit-update`

**Input**: Kit slug, source dir, studio dir, flags (dry_run, interactive, auto_approve, force)

**Output**: Result dict with kit, version status, gen actions, accepted/declined files

**Steps**:
1. [x] - `p1` - Resolve config dir paths (config_dir, config_kits_dir, config_kit_dir) - `inst-resolve-config`
2. [x] - `p1` - **IF** dry_run: return early with dry_run status - `inst-dry-run-check`
3. [x] - `p1` - Resolve source version/currentness input from GitHub authority metadata for GitHub-backed kits; read `conf.toml version` only for local/path metadata - `inst-read-source-version`
4. [x] - `p1` - **IF** not force and authoritative content identity or resolved display version matches installed GitHub metadata: return "current" status with source/freshness metadata - `inst-version-check`
5. [x] - `p1` - **IF** source has canonical or legacy manifest and kit has no `resources` in core.toml: trigger `migrate_legacy_kit_to_manifest` - `inst-legacy-manifest-migration`
6. [x] - `p1` - **IF** source has canonical or legacy manifest: build source-path-to-resource-id mapping from normalized manifest resources, resolve resource bindings from `core.toml` via `cpt-studio-algo-kit-manifest-resolve` - `inst-resolve-resource-bindings`
7. [x] - `p1` - **IF** the authoritative installed root from `config/core.toml` `kits.{slug}.path` does not exist (defaulting to `config/kits/{slug}` when missing): first-install via `_copy_kit_content`, seed configs, register in core.toml - `inst-first-install`
8. [x] - `p1` - **ELSE**: existing kit — delegate to `file_level_kit_update` for interactive diff, passing `resource_bindings`, `source_to_resource_id`, and `resource_info` for manifest-driven kits - `inst-file-level-diff`
9. [x] - `p1` - Update `core.toml` version and structured authority metadata from GitHub resolution for GitHub-backed kits; for local/path mode, update only local metadata derived from the provided path - `inst-update-core-toml`
10. [x] - `p1` - Collect metadata for `.gen/` aggregation - `inst-collect-metadata`
11. [x] - `p1` - **RETURN** result with kit, version, gen, accepted/declined files - `inst-return-result`

**Supporting**:
- [x] - `p1` - First-install helper: copy content, seed configs, register in core.toml when config dir does not exist - `inst-perform-first-install`
- [x] - `p1` - Sync manifest resource bindings: merge new manifest resources into existing core.toml bindings - `inst-sync-manifest-bindings`

### File-Level Kit Update

- [x] `p1` - **ID**: `cpt-studio-algo-kit-file-update`

**Input**: Source dir, user dir, flags (interactive, auto_approve, force, dry_run, content_dirs, content_files), optional resource_bindings (Dict[str, Path]), optional source_to_resource_id (Dict[str, str]), optional resource_info (Dict[str, {"type": str, "source_base": str}])

**Output**: Dict with status, added/removed/modified/unchanged, accepted/declined paths

**Steps**:
1. [x] - `p1` - Enumerate source and user kit files via `_enumerate_kit_files` - `inst-enumerate-files`
2. [x] - `p1` - **IF** `resource_bindings` provided: build target path mapping for each source file using `source_to_resource_id` lookup. For file resources, target is `resource_bindings[resource_id]`. For directory resources, target is `resource_bindings[resource_id] / relative_path_within_directory`. For files without binding, target is `user_dir / rel_path` (default behavior) - `inst-build-target-mapping`
3. [x] - `p1` - **IF** `resource_bindings` provided: enumerate user files from all bound target paths (files directly, directories recursively) to correctly detect modifications - `inst-enumerate-bound-user-files`
4. [x] - `p1` - Strip TOC from both sides for cleaner diff comparison, record `toc_formats` per file - `inst-strip-toc`
5. [x] - `p1` - Classify changes between source and user via `_classify_kit_files` - `inst-classify-changes`
6. [x] - `p1` - **IF** no changes: return "current" status early - `inst-check-no-changes`
7. [x] - `p1` - Show update summary with colored counts (added/removed/modified/unchanged); for redirected files, show both source path and target path - `inst-show-summary`
8. [x] - `p1` - **FOR EACH** changed file: display context (new file, deleted, or unified diff) - `inst-show-change-context`
9. [x] - `p1` - **FOR EACH** changed file: get user decision via `_prompt_kit_file` or auto-accept/decline per flags - `inst-prompt-decision`
10. [x] - `p1` - **IF** decision is "modify": open editor for manual merge via `_open_editor_for_file` - `inst-editor-merge`
11. [x] - `p1` - Apply accepted changes: write new/modified files to target paths (using target mapping for bound resources), delete removed files from their target paths - `inst-apply-changes`
12. [x] - `p1` - **IF** file had TOC and was written: prompt/auto-regenerate TOC, handle errors with rollback - `inst-toc-regen`
13. [x] - `p1` - **RETURN** result with all entries, accepted/declined paths - `inst-build-result`

**Supporting**:
- [x] - `p1` - Result list initialization and changed file aggregation helpers - `inst-update-datamodel`

### Kit File Enumeration

- [x] `p1` - **ID**: `cpt-studio-algo-kit-file-enumerate`

**Input**: Directory path, include/exclude filters

**Output**: Dict of `{relative_posix_path: content_bytes}`

**Steps**:
1. [x] - `p1` - Walk directory recursively, collecting files matching include filters or excluding by exclude filters - `inst-walk-dir`
2. [x] - `p1` - **IF** `content_dirs`/`content_files` provided: include-only mode (top-level dir in content_dirs or root file in content_files) - `inst-include-filter`
3. [x] - `p1` - **ELSE**: exclude mode (skip files in `_KIT_EXCLUDE_FILES`, dirs in `_KIT_EXCLUDE_DIRS`) - `inst-exclude-filter`
4. [x] - `p1` - Read file bytes and store in result dict - `inst-read-bytes`

**Supporting**:
- [x] - `p1` - Kit exclude/include constants and default content filters - `inst-enum-datamodel`

### Kit File Classification

- [x] `p1` - **ID**: `cpt-studio-algo-kit-file-classify`

**Input**: Source files dict, user files dict

**Output**: DiffReport with added/removed/modified/unchanged

**Steps**:
1. [x] - `p1` - Union all paths from source and user, classify each as added/removed/modified/unchanged by content comparison - `inst-classify`

### Kit Interactive Review

- [x] `p1` - **ID**: `cpt-studio-algo-kit-interactive-review`

**Input**: Relative path, review state dict

**Output**: User decision: accept/decline/modify

**Steps**:
1. [x] - `p1` - **IF** `accept_all` or `decline_all` set in state: return immediately - `inst-check-bulk`
2. [x] - `p1` - Prompt user with `[a]ccept [d]ecline [A]ccept-all [D]ecline-all [m]odify`, parse response, update state flags for bulk decisions, return choice - `inst-prompt`

### Kit Diff Display

- [x] `p1` - **ID**: `cpt-studio-algo-kit-diff-display`

**Input**: DiffReport or file content pair

**Output**: Colored text to stderr

**Steps**:
1. [x] - `p1` - Show summary: colored counts of added (green +), removed (red -), modified (yellow ~) files - `inst-show-summary`
2. [x] - `p1` - Show per-file unified diff: decode bytes, compute `difflib.unified_diff`, color-code output lines - `inst-show-file-diff`

**Supporting**:
- [x] - `p1` - Imports, DiffReport dataclass, and editor/conflict marker constants - `inst-diff-datamodel`

### Kit Conflict Merge

- [x] `p1` - **ID**: `cpt-studio-algo-kit-conflict-merge`

**Input**: Old content bytes, new content bytes, relative path

**Output**: Resolved content bytes or None (decline)

**Steps**:
1. [x] - `p1` - Detect conflict markers: scan lines for `<<<<<<<`, `=======`, `>>>>>>>` - `inst-detect-markers`
2. [x] - `p1` - Build conflict content: use `SequenceMatcher` to produce git-style `<<<<<<<`/`=======`/`>>>>>>>` regions for each differing hunk - `inst-build-conflicts`
3. [x] - `p1` - Open editor: write conflict content to temp file, invoke `$VISUAL`/`$EDITOR`/`vi`, read result; if empty return None - `inst-open-editor`
4. [x] - `p1` - **IF** conflict markers remain: prompt retry/accept-upstream/decline - `inst-prompt-unresolved`
5. [x] - `p1` - Loop: retry reopens editor, accept returns upstream, decline returns None - `inst-resolve-loop`

**Supporting**:
- [x] - `p1` - Editor detection helper function - `inst-merge-datamodel`

### Kit TOC Handling

- [x] `p1` - **ID**: `cpt-studio-algo-kit-toc-handling`

**Input**: File content bytes

**Output**: TOC-stripped content for diff, regenerated content post-write

**Steps**:
1. [x] - `p1` - Strip marker-based TOC (`<!-- toc -->` / `<!-- /toc -->`) or heading-based TOC (`## Table of Contents`) from content - `inst-strip-toc`
2. [x] - `p1` - Prompt user about TOC regeneration (or auto-regen if auto_approve) - `inst-prompt-regen`
3. [x] - `p1` - Regenerate TOC using `insert_toc_markers` or `insert_toc_heading` based on detected format - `inst-regenerate`
4. [x] - `p1` - **IF** regeneration fails: restore previous content, prompt continue/stop - `inst-handle-error`

**Supporting**:
- [x] - `p1` - TOC marker constants and heading regex patterns - `inst-toc-datamodel`

### Kit Whatsnew Display

- [x] `p1` - **ID**: `cpt-studio-algo-kit-whatsnew-display`

**Input**: Kit source directory (containing `whatsnew.toml`), installed kit version from `core.toml`, interactive flag

**Output**: Displayed whatsnew entries, user acknowledgment (bool)

**Steps**:
1. [x] - `p1` - Read `whatsnew.toml` from kit source directory; **IF** not present, return True (no-op) - `inst-read-whatsnew`
2. [x] - `p1` - Read installed kit version from `core.toml` (`kits.{slug}.version`); **IF** not installed, treat as version "0.0.0" - `inst-read-installed-version`
3. [x] - `p1` - Filter entries: keep all versions greater than installed version - `inst-filter-versions`
4. [x] - `p1` - **IF** no new entries: return True (no-op) - `inst-check-no-new`
5. [x] - `p1` - Sort filtered entries by version (ascending, using semantic version comparison) - `inst-sort-versions`
6. [x] - `p1` - Display entries to stderr with ANSI formatting (when stderr is TTY); show version, summary, and details for each entry - `inst-display-entries`
7. [x] - `p1` - **IF** interactive mode: prompt user "Press Enter to continue with update (or 'q' to abort)"; **IF** user aborts, return False - `inst-prompt-continue`
8. [x] - `p1` - **RETURN** True (acknowledged) - `inst-return-ack`

**Supporting**:
- [x] - `p1` - Semantic version comparison helper (parse `X.Y.Z` and compare) - `inst-whatsnew-version-cmp`
- [x] - `p1` - ANSI formatting helper for summary and details text (bold version, cyan code spans) - `inst-whatsnew-format`
- [x] - `p1` - Module-level imports and type aliases for whatsnew utilities - `inst-whatsnew-imports`
- [x] - `p1` - ANSI color availability check (stderr TTY detection) - `inst-whatsnew-ansi-check`
- [x] - `p1` - `format_whatsnew_text`: apply ANSI bold/cyan formatting to version headers and inline code spans - `inst-whatsnew-format-text`
- [x] - `p1` - `read_whatsnew`: load and normalize entries from `whatsnew.toml` (handles `whatsnew.X.Y.Z` key prefix) - `inst-whatsnew-read-toml`
- [x] - `p1` - `show_whatsnew`: orchestrate filter, sort, display, and acknowledgment prompt - `inst-whatsnew-show-core`

### Kit Snapshot

- [x] `p1` - **ID**: `cpt-studio-algo-kit-snapshot`

**Input**: Directory path, file extensions filter

**Output**: Snapshot dict `{rel_path: bytes}`, DiffReport

**Steps**:
1. [x] - `p1` - Recursively read all files matching extensions into `{relative_path: bytes}` dict - `inst-read-files`

### Kit Validation Engine

- [x] `p1` - **ID**: `cpt-studio-algo-kit-validate`

**Input**: Project root, adapter dir, optional kit filter, verbose flag

**Output**: (return_code, report_dict) — rc=0 PASS, rc=2 FAIL

**Steps**:
1. [x] - `p1` - Get context and initialize validation state - `inst-init-context`
2. [x] - `p1` - **Phase 1 — Structural**: for each registered Studio-format kit, load and validate all `kind = "constraints"` resources in manifest order, falling back to legacy `constraints.toml` only for legacy kits without constraints resources - `inst-structural-check`
3. [x] - `p1` - **Phase 1b — Resource paths**: for manifest-driven kits, resolve paths to constraints resources, templates, and examples from resource bindings in `core.toml` via `cpt-studio-algo-kit-manifest-resolve` instead of assuming default kit directory structure - `inst-resolve-resource-paths`
4. [x] - `p1` - **Phase 2 — Templates**: load `artifacts_meta`, run `self_check` for template/example consistency - `inst-template-check`
5. [x] - `p1` - Build result: aggregate errors, set overall PASS/FAIL status - `inst-build-result`

### Kit Validate by Path

- [x] `p1` - **ID**: `cpt-studio-algo-kit-validate-by-path`

**Input**: Kit directory path, verbose flag

**Output**: (return_code, report_dict)

**Steps**:
1. [x] - `p1` - Resolve kit directory, verify exists - `inst-resolve-dir`
2. [x] - `p1` - **Phase 1 — Structural**: load and validate all `kind = "constraints"` resources in manifest order, falling back to legacy `constraints.toml` only for legacy path validation - `inst-structural-check`
3. [x] - `p1` - **Phase 1b — Manifest resources**: **IF** manifest-driven kit, verify all registered resource paths exist on disk - `inst-verify-resource-paths`
4. [x] - `p1` - Build synthetic `ArtifactsMeta` from kit's artifacts/ directory - `inst-build-artifacts-meta`
5. [x] - `p1` - **Phase 2 — Templates**: run `self_check` for template/example validation - `inst-template-check`
6. [x] - `p1` - Build result: aggregate errors, set PASS/FAIL - `inst-build-result`

### Kit Config Helpers

- [x] `p1` - **ID**: `cpt-studio-algo-kit-config-helpers`

**Input**: Various conf.toml / core.toml paths

**Output**: Parsed config values

**Steps**:
1. [x] - `p1` - Read top-level `version` from conf.toml as integer - `inst-read-conf-version`
2. [x] - `p1` - Read kit `slug` from source conf.toml - `inst-read-slug`
3. [x] - `p1` - Read installed kit display/backcompat version from `core.toml [kits.{slug}].version`; for GitHub-backed kits this value is GitHub-derived - `inst-read-version-from-core`
4. [x] - `p1` - Read kit version string from `conf.toml` as optional local metadata only - `inst-read-kit-version`
5. [x] - `p1` - Register or update kit entry in `core.toml` with format, path, source, display/backcompat version, and structured authority metadata without overwriting existing last-known GitHub state unless a new verified resolution exists - `inst-register-core`

**Supporting**:
- [x] - `p1` - Resolve project root and studio directory from CWD - `inst-resolve-studio-dir`
- [x] - `p1` - Read all registered kit entries from `core.toml [kits]` section - `inst-read-kits-core`
- [x] - `p1` - Wrapper function for reading kit slug from conf.toml - `inst-read-slug-fn`
- [x] - `p1` - Wrapper function for reading kit version from core.toml - `inst-read-version-core-fn`
- [x] - `p1` - Wrapper function for reading kit version from conf.toml path - `inst-read-kit-version-fn`
- [x] - `p1` - Wrapper function for registering/updating kit in core.toml - `inst-register-core-fn`

### Kit Source Mode Validation

- [x] `p1` - **ID**: `cpt-studio-algo-kit-source-mode-validation`

**Input**: CLI arguments, registered kit entry, optional source path

**Output**: Source mode decision or validation error

**Steps**:
1. [x] - `p1` - Classify mode as `github` when using `owner/repo[@ref]` or registered `github:` source; classify as `local_path` when using `--path` - `inst-classify-source-mode`
2. [x] - `p1` - Reject invocations that combine local/path mode with GitHub selector flags or GitHub ref syntax - `inst-reject-mode-conflicts`
3. [x] - `p1` - For local/path mode, skip GitHub authority resolution and treat `conf.toml version` as optional local metadata only - `inst-local-path-outside-authority`
4. [x] - `p1` - For GitHub mode, require persisted source metadata to be refreshed from GitHub when online or reused as last-known state when offline - `inst-github-mode-authority`

### Universal Kit Model Normalization

- [x] `p1` - **ID**: `cpt-studio-algo-kit-model-normalize`

**Input**: Kit source root, optional existing `core.toml` registration, install/update context

**Output**: `KitModel` with canonical metadata, normalized resources, public components, generated names, install mode, provenance, warnings, and legacy compatibility metadata

**Rules**:
1. [x] - `p1` - Treat `.cf-studio-kit.toml` as the canonical source of truth when present; do not require `conf.toml` and do not read `conf.toml` for fields already declared in the canonical manifest - `inst-kitmodel-canonical-manifest`
2. [x] - `p1` - Apply source precedence: `.cf-studio-kit.toml` > legacy `manifest.toml` v2/v1 > `conf.toml + layout` > installed `core.toml` resources-only reconstruction - `inst-kitmodel-precedence`
3. [x] - `p1` - Normalize legacy `[[workflows]]` entries into public `skill` resources with `origin = "legacy-workflow"`; new author-facing manifests MUST NOT require a `workflow` resource kind - `inst-kitmodel-workflow-to-skill`
4. [x] - `p1` - Normalize all public skills and subagents to generated names `cf-{kit-slug}-{name}`; if the name already has that exact prefix, preserve it without double-prefixing - `inst-kitmodel-prefix-public-names`
5. [x] - `p1` - Preserve short manifest resource IDs for bindings and variables while exposing generated public names separately for agent-entry-point output - `inst-kitmodel-resource-id-vs-generated-name`
6. [x] - `p1` - Compute `manifest_semantic_hash`, `manifest_bytes_hash`, per-file resource hashes as `sha256(bytes)`, directory resource hashes, and separate tool-risk fingerprint - `inst-kitmodel-hashes`
7. [x] - `p1` - Compute directory resource hashes from sorted relative paths plus per-file hashes, excluding VCS directories, cache directories, and configured ignore globs - `inst-kitmodel-directory-hash`
8. [x] - `p1` - Return structured warnings for legacy input, workflow normalization, unknown optional fields, unqualified variable conflicts, and risk-confirmation requirements - `inst-kitmodel-warnings`
9. [x] - `p1` - Expose a single `KitModel` service boundary used by install, update, info, resolve-vars, validate, and generate-agents; no command may independently scan kit directories except through this service or its legacy adapters - `inst-kitmodel-single-boundary`

### Canonical `.cf-studio-kit.toml`

- [x] `p1` - **ID**: `cpt-studio-algo-kit-canonical-manifest`

**Input**: `.cf-studio-kit.toml`

**Output**: Validated canonical manifest model

**Rules**:
1. [x] - `p1` - The file is valid at any kit root and may describe any directory structure exclusively by enumerating resources; fixed folders such as `artifacts/`, `workflows/`, or `scripts/` are conventions only, not requirements - `inst-canonical-any-layout`
2. [x] - `p1` - The file MUST declare top-level `manifest_version = "1.0"`; missing or unsupported manifest versions are blocking errors that instruct the user to update Constructor Studio with `pipx upgrade constructor-studio` before retrying - `inst-canonical-version-gate`
3. [x] - `p1` - Manifest metadata declares at least slug/name/version-compatible display metadata and may declare description, source, targets, defaults, and compatibility fields - `inst-canonical-metadata`
4. [x] - `p1` - A canonical file always uses `[[kits]]` entries with nested `[[kits.resources]]`; the file may contain one kit or multiple selectable kits, and kit slugs must be unique - `inst-canonical-multi-kit`
5. [x] - `p1` - `[[kits.resources]]` entries require `id`, `kind`, and `source`; optional fields include `install_path`, `type`, `public`, `description`, `user_modifiable`, `aliases`, `generated_targets`, and nested configuration tables - `inst-canonical-resource-shape`
6. [x] - `p1` - Public resource kinds are `skill`, `agent`, and `rule`; supporting kinds include `template`, `checklist`, `constraints`, `script`, `directory`, and `other`; `workflow` is accepted only as a legacy alias normalized to `skill` - `inst-canonical-resource-kinds`
7. [x] - `p1` - Small agent configuration may be inline on the resource; larger configuration may use `[kits.resources.agent]`, `[kits.resources.targets.<target>]`, and `[kits.resources.permissions]` under the selected `[[kits.resources]]` entry - `inst-canonical-agent-config`
8. [x] - `p1` - Agent configuration supports `mode`, `isolation`, `model`, `tools`, `disallowed_tools`, `skills`, `color`, `memory_dir`, `role`, `target`, `provider`, `reasoning_effort`, `context_window`, and nested `subagents` - `inst-canonical-agent-fields`
9. [x] - `p1` - Nested `subagents` may declare the same target-specific agent schema as top-level agent resources, including tool permissions, generated targets, prompt/source resources, and model/provider fields - `inst-canonical-subagent-config`
10. [x] - `p1` - Public resources and nested subagents generate agent-facing names as `cf-{kit-slug}-{resource-id}` by default; `prefix_generated_name = false` disables that prefix for a resource or subagent and uses its `id` as-is - `inst-canonical-public-name-prefix`
11. [x] - `p1` - `generated_targets` defaults to `installed`, accepts an explicit target list or `all`, and controls which agent tools receive public component output - `inst-canonical-generated-targets`
12. [x] - `p1` - The manifest MUST NOT expose author-facing `binding_path`; effective paths are installation state recorded in `core.toml` - `inst-canonical-no-binding-path`

### Local Path Install Mode

- [x] `p1` - **ID**: `cpt-studio-algo-kit-local-path-install-mode`

**Input**: `cfs kit install --path <dir>`, project root, manifest root, normalized resources, optional `--install-mode`

**Output**: Install mode decision (`copy` or `register`) plus resolved resource bindings

**Steps**:
1. [x] - `p1` - In interactive mode, always ask whether to copy resources into Studio-managed storage or register resources in place; default suggestion is `register` only when containment validation passes - `inst-local-mode-always-ask`
2. [x] - `p1` - In non-interactive mode, require `--install-mode copy|register`; fail with remediation when omitted - `inst-local-mode-noninteractive-required`
3. [x] - `p1` - Allow `register` only for local `--path` installs where manifest path, manifest root, and every resource source resolves inside the current project root after symlink resolution - `inst-local-register-containment`
4. [x] - `p1` - Reject absolute resource source paths and symlink escapes before writing any `core.toml` bindings - `inst-local-register-reject-escape`
5. [x] - `p1` - For `register`, leave source files in place and write effective resource bindings, hashes, install mode, and provenance to `core.toml` - `inst-local-register-core-only`
6. [x] - `p1` - For `copy`, copy resources to Studio/project-approved destinations, preserving user-selected `install_path` overrides and `user_modifiable` prompts - `inst-local-copy-resources`
7. [x] - `p1` - Never silently overwrite `user_modifiable` resources during copy install or copy update; require interactive acceptance or explicit non-interactive approval for each changed effective path - `inst-local-copy-no-silent-overwrite`
8. [x] - `p1` - Never use `register` for GitHub or generic Git installs; remote sources use copied/managed artifacts - `inst-local-register-local-only`

### Kit Info Model Output

- [x] `p1` - **ID**: `cpt-studio-algo-kit-info-model-output`

**Input**: Installed kit registrations, normalized `KitModel` objects, drift state

**Output**: `cfs info` JSON with canonical `kit_models` plus temporary compatibility fields

**Rules**:
1. [x] - `p1` - Build `cfs info` from normalized `KitModel` data for kits registered in `core.toml`, not from independent ad hoc directory scans; unregistered `config/kits/*` directories never contribute kit output - `inst-info-kitmodel-source`
2. [x] - `p1` - Add top-level `kit_models[slug]` objects containing metadata, manifest source, install mode, drift, resource counts, resources, public components, generated names, active targets, risk, provenance, content identity, legacy compatibility, and warnings - `inst-info-kitmodels-shape`
3. [x] - `p1` - Preserve legacy `kit_details` for one minor compatibility cycle, derived from `kit_models` rather than populated separately - `inst-info-kitdetails-derived`
4. [x] - `p1` - Expose legacy `kit_details.workflows` only as derived skills where `origin = "legacy-workflow"` and mark the field deprecated - `inst-info-workflows-deprecated`
5. [x] - `p1` - Report copy/register mode, containment status, semantic hash drift, byte hash drift, resource hash drift, stale/missing resources, and disabled public components - `inst-info-drift`

### Public Component Generation

- [x] `p1` - **ID**: `cpt-studio-algo-kit-public-component-generation`

**Input**: `KitModel.public_components`, target agent tool, installed resource bindings

**Output**: Generated skills, subagents, and rules for the requested target

**Rules**:
1. [x] - `p1` - `generate-agents` consumes `KitModel.public_components` where kind is `skill`, `agent`, or `rule` and the component is enabled for the target - `inst-public-generate-from-kitmodel`
2. [x] - `p1` - For manifest-backed kits, do not scan workflow directories to infer public commands; generated output is manifest-driven - `inst-public-no-workflow-scan`
3. [x] - `p1` - Project-level `.cf-studio-kit.toml` files contribute public components only after explicit install/register; the system must not recursively scan arbitrary manifests, legacy `manifest.toml` files, or unregistered `config/kits/*/workflows` directories - `inst-public-explicit-install`
4. [x] - `p1` - Generated public skill and subagent names use `cf-{kit-slug}-{name}` with no double prefixing - `inst-public-prefix`
5. [x] - `p1` - A legacy workflow source renders as a skill entry point and may retain a compatibility alias only when the target supports it - `inst-public-legacy-workflow-alias`

### Kit Variable Resolution

- [x] `p1` - **ID**: `cpt-studio-algo-kit-variable-resolution`

**Input**: Installed kit resource bindings and aliases

**Output**: Deterministic variable map for `cfs resolve-vars`, templates, and generated prompts

**Rules**:
1. [x] - `p1` - Do not expose `{kit_slug.resource_id}` variables in the flat map; keep kit slug separation only in structured `kits[slug]` output - `inst-vars-no-kit-qualified`
2. [x] - `p1` - Expose unqualified `{resource_id}` variables only when unique across all installed kits; omit conflicts and report warnings - `inst-vars-unqualified-unique`
3. [x] - `p1` - Apply explicit aliases using the same uniqueness and warning rules as resource IDs - `inst-vars-aliases`
4. [x] - `p1` - Resolve variable values from `core.toml` effective bindings, not from manifest source paths - `inst-vars-effective-bindings`

### Kit Update, Drift, and Prune

- [x] `p1` - **ID**: `cpt-studio-algo-kit-update-drift-prune`

**Input**: Existing registration, old and new `KitModel`, install mode, resource hashes

**Output**: Update plan, applied changes, drift report, optional prune plan

**Rules**:
1. [x] - `p1` - Normal update never deletes files solely because a resource disappeared from the new manifest; unregister or mark stale instead - `inst-update-no-auto-delete`
2. [x] - `p1` - Missing public resources cannot remain active; mark their generated components disabled until the resource is restored or removed - `inst-update-disable-missing-public`
3. [x] - `p1` - Deletion requires an explicit prune mode and a prune fingerprint; never delete register-in-place source files - `inst-update-explicit-prune`
4. [x] - `p1` - Prompt per path before deleting `user_modifiable` resources or anything outside the copied kit root - `inst-update-prune-path-prompts`
5. [x] - `p1` - For register-in-place updates, re-read the manifest in place, revalidate containment, recompute hashes/risk, and update `core.toml` after showing drift - `inst-update-register-reread`
6. [x] - `p1` - For copy updates, use the existing file-level diff path at effective resource destinations and preserve user-chosen install paths - `inst-update-copy-diff`

### Tool Permission Risk

- [x] `p1` - **ID**: `cpt-studio-algo-kit-tool-permission-risk`

**Input**: Resource agent/tool configuration from `KitModel`

**Output**: Risk summary, fingerprint, and install/update approval requirement

**Rules**:
1. [x] - `p1` - Accept unknown tools with warnings so new host-tool capabilities do not block kit installation by default - `inst-risk-unknown-tools-warn`
2. [x] - `p1` - Tag dangerous capabilities in a stable risk summary used for user confirmation and non-interactive fingerprints - `inst-risk-dangerous-summary`
3. [x] - `p1` - Interactive install/update asks for confirmation when the dangerous tool summary changes - `inst-risk-interactive-confirm`
4. [x] - `p1` - Non-interactive install/update requires `--approve-tool-risk <fingerprint>` when dangerous capability risk is present or changed - `inst-risk-noninteractive-fingerprint`

### Kit Manifest Normalization and Migration

- [x] `p1` - **ID**: `cpt-studio-algo-kit-manifest-normalize`

**Input**: Source kit root, optional `--from manifest|layout|core`, optional output path

**Output**: Generated `.cf-studio-kit.toml` plus migration report

**Steps**:
1. [x] - `p1` - `cfs kit normalize <path>` loads the source through the same `KitModel` normalization pipeline used by install/update - `inst-normalize-load-kitmodel`
2. [x] - `p1` - Convert legacy `manifest.toml` v1/v2 or `conf.toml + layout` inputs into canonical `.cf-studio-kit.toml` without changing source files - `inst-normalize-convert`
3. [x] - `p1` - Convert installed `core.toml` resource bindings into canonical `.cf-studio-kit.toml` without changing installed resources - `inst-normalize-core-bindings`
4. [x] - `p1` - Emit public legacy workflows as `kind = "skill"` resources with `origin = "legacy-workflow"` metadata and generated-name preview - `inst-normalize-workflows-to-skills`
5. [x] - `p1` - Preserve resource IDs, user-modifiable path defaults, aliases, generated targets, agent configuration, and source provenance wherever they can be inferred deterministically - `inst-normalize-preserve-fields`
6. [x] - `p1` - Report fields that require user choice rather than guessing, including ambiguous resource kinds, conflicting aliases, missing source files, or unsafe paths - `inst-normalize-report-ambiguity`
7. [x] - `p1` - Refuse to write a canonical manifest that would reference sources outside the selected kit root unless the user explicitly chooses a safe local registration root and containment passes - `inst-normalize-containment`

**Rollout Phases**:
1. [x] - `p1` - Add parser/model/converter tests with no install behavior change - `inst-rollout-kitmodel-tests`
2. [x] - `p1` - Make `cfs info` read through `KitModel` while preserving legacy fields for compatibility - `inst-rollout-info`
3. [x] - `p1` - Make `cfs kit install --path` support copy/register using compact `core.toml` bindings - `inst-rollout-path-install`
4. [x] - `p1` - Make `generate-agents` consume `KitModel.public_components` and emit skills-only public workflow replacements - `inst-rollout-generate-agents`
5. [x] - `p1` - Add update, prune, drift, hash, and risk-fingerprint behavior - `inst-rollout-update-drift`
6. [x] - `p1` - Add docs, warnings, and deprecation messaging for legacy `manifest.toml`, legacy workflow resources, and layout-only kits - `inst-rollout-docs-deprecation`

### Manifest-Driven Installation

- [x] `p1` - **ID**: `cpt-studio-algo-kit-manifest-install`

**Input**: Kit source directory, normalized `KitModel`, studio dir, slug, provenance, install mode

**Output**: Result dict with status, resolved resource paths, files_copied

**Steps**:
1. [x] - `p1` - Read and validate canonical `.cf-studio-kit.toml` or normalize a legacy manifest/layout into `KitModel` - `inst-manifest-read`
2. [x] - `p1` - Resolve effective install mode (`copy` or `register`) and effective resource destinations - `inst-manifest-resolve-install-mode`
3. [x] - `p1` - Resolve the effective installed kit root from an explicit registered path or manifest root template - `inst-manifest-root-prompt`
4. [x] - `p1` - **FOR EACH** resource declared in `KitModel.resources` - `inst-manifest-foreach-resource`
   1. [x] - `p1` - **IF** `install_path` is user-modifiable in copy mode: prompt user for destination path (offering the manifest default) - `inst-manifest-prompt-path`
   2. [x] - `p1` - Resolve each resource target from its effective default or user-selected path - `inst-manifest-default-path`
5. [x] - `p1` - Before writing files or registering resources, reject installation when any public component or nested subagent `generated_name` conflicts with another public component in the installing kit or with an already registered kit - `inst-public-name-conflict`
6. [x] - `p1` - Manifest preview and kit-init approval reports show final generated names for public skills, agents, rules, and nested subagents, including whether each name is default-prefixed or `prefix_generated_name = false` as-is - `inst-public-name-preview`
   3. [x] - `p1` - **IF** copy mode: copy resource from source to resolved path, preserving directory structure within directory resources - `inst-manifest-copy-resource`
   4. [x] - `p1` - **IF** register mode: leave files in place and bind the resource to its source path after containment validation - `inst-manifest-register-resource-in-place`
5. [x] - `p1` - Preserve `{identifier}` template variables in copied kit source files; expose effective bindings for read-time resolution by consumers - `inst-manifest-resolve-vars`
6. [x] - `p1` - Register effective resource paths, install mode, hashes, generated names, provenance, and warnings in `core.toml`; prefer paths relative to `{cf-studio-path}` or project root when deterministic - `inst-manifest-register-bindings`
7. [x] - `p1` - Collect public component metadata for `.gen/` aggregation and target-specific agent generation from `KitModel.public_components` - `inst-manifest-collect-meta`
8. [x] - `p1` - **RETURN** result with status, install_mode, resource_bindings, files_copied, files_registered, generated_names, warnings, and risk fingerprint - `inst-manifest-return`

**Supporting**:
- [x] - `p1` - Manifest/KitModel dataclass definitions (`KitModel`, `KitResource`, public component view, provenance, drift, risk) and imports - `inst-manifest-datamodel`
- [x] - `p1` - Validate parsed manifest against kit source (unique IDs, source paths exist, type matches, path containment for register mode) - `inst-manifest-validate`
- [x] - `p1` - Copy a single manifest resource (file or directory) from source to target path - `inst-copy-manifest-resource`
- [x] - `p1` - Preserve `{identifier}` template variables in copied kit files; resolve variables only through registered bindings at read time - `inst-resolve-template-vars`

### Manifest Legacy Migration

- [x] `p1` - **ID**: `cpt-studio-algo-kit-manifest-legacy-migration`

**Input**: Kit source directory containing canonical `.cf-studio-kit.toml` or legacy `manifest.toml`, studio dir, slug, existing kit root from `core.toml`

**Output**: Populated resource bindings in `core.toml`

**Steps**:
1. [x] - `p1` - Read canonical manifest or normalize legacy manifest/layout from kit source - `inst-legacy-read-manifest`
2. [x] - `p1` - Read existing kit root path from `core.toml` - `inst-legacy-read-root`
3. [x] - `p1` - **FOR EACH** resource declared in manifest - `inst-legacy-foreach-resource`
   1. [x] - `p1` - Compute expected path from existing kit root plus normalized manifest default `install_path`/legacy `default_path` - `inst-legacy-compute-path`
   2. [x] - `p1` - **IF** file/directory exists at computed path: register silently in `core.toml` - `inst-legacy-register-existing`
   3. [x] - `p1` - **ELSE** (truly new resource not on disk): prompt user for destination path, copy from source, register - `inst-legacy-prompt-new`
4. [x] - `p1` - Write all resource bindings to `core.toml` under `[kits.{slug}.resources]` - `inst-legacy-write-bindings`
5. [x] - `p1` - **RETURN** migration result with registered paths count - `inst-legacy-return`

### Manifest Resource Resolution

- [x] `p1` - **ID**: `cpt-studio-algo-kit-manifest-resolve`

**Input**: Kit slug, `core.toml` resource bindings, studio dir (adapter directory)

**Output**: Dict of `{identifier: resolved_absolute_path}`

**Steps**:
1. [x] - `p1` - Read `[kits.{slug}.resources]` section from `core.toml` - `inst-resolve-read-bindings`
2. [x] - `p1` - **FOR EACH** binding: resolve relative path against `{cf-studio-path}` (adapter directory) to absolute path; paths may contain `..` for resources outside the adapter tree - `inst-resolve-to-absolute`
3. [x] - `p1` - **RETURN** identifier → absolute path dict - `inst-resolve-return`

### Manifest Source Path Mapping

- [x] `p1` - **ID**: `cpt-studio-algo-kit-manifest-source-mapping`

**Input**: Kit source directory plus normalized `KitModel`

**Output**: Tuple of:
- `source_to_resource_id`: Dict of `{source_rel_path: resource_id}` for all files (including files inside directory resources)
- `resource_info`: Dict of `{resource_id: {"type": "file"|"directory", "source_base": str}}` — for directory resources, `source_base` is the directory path in source kit (e.g., `"artifacts/ADR"`)

**Steps**:
1. [x] - `p1` - Load `KitModel` from canonical manifest, legacy manifest, or layout adapter - `inst-load-manifest`
2. [x] - `p1` - **FOR EACH** resource in manifest: record resource info (type, source_base) - `inst-record-resource-info`
3. [x] - `p1` - **FOR EACH** file resource: map `resource.source` → `resource.id` directly - `inst-map-file-resources`
4. [x] - `p1` - **FOR EACH** directory resource: recursively enumerate all files under `source` path, map each file's full relative path (e.g., `artifacts/ADR/template.md`) to the resource id - `inst-expand-directories`
5. [x] - `p1` - **RETURN** (source_to_resource_id, resource_info) - `inst-return-mapping`

**Note**: When resolving target path for a file inside a directory resource, compute `relative_path_within_directory = source_rel_path.removeprefix(resource_info[resource_id]["source_base"] + "/")`, then target is `resource_bindings[resource_id] / relative_path_within_directory`.

---

## 4. States (CDSL)

### Kit Authority State

- [ ] `p1` - **ID**: `cpt-studio-state-kit-authority`

| State | Condition | Transitions |
|-------|-----------|-------------|
| `verified_fresh` | GitHub metadata was resolved online for the effective source/ref and content identity | -> `verified_stale` when offline age/freshness policy expires, -> `changed` when new content identity resolves |
| `verified_stale` | Last-known GitHub metadata exists but could not be refreshed online | -> `verified_fresh` after successful refresh |
| `local_only` | Kit was installed or updated from local/path mode | -> `verified_fresh` only after explicit GitHub source registration/resolution |
| `unknown` | No persisted authority metadata exists | -> `verified_fresh` after GitHub resolution, -> `local_only` for path mode |

### Kit Installation State

- [x] `p1` - **ID**: `cpt-studio-state-kit-installation`

| State | Condition | Transitions |
|-------|-----------|-------------|
| `not_installed` | The authoritative installed root from `config/core.toml` `kits.{slug}.path` does not exist (or defaults to missing `config/kits/{slug}`) | → `installed` via `install_kit` |
| `installed` | Kit files present at the authoritative installed root from `kits.{slug}.path` | → `updated` via `update_kit`, → `current` if version matches |
| `current` | Installed version matches source version | → `updated` via force update |
| `updated` | Files changed via file-level diff | → `current` on next check |

### Kit Manifest State

- [ ] `p1` - **ID**: `cpt-studio-state-kit-manifest`

| State | Condition | Transitions |
|-------|-----------|-------------|
| `canonical` | Source root contains `.cf-studio-kit.toml`; no `conf.toml` is required | -> `drifted` when semantic or resource hashes differ from registered state |
| `legacy_manifest` | Source root has `manifest.toml` v1/v2 and no canonical manifest | -> `canonical` via `cfs kit normalize` |
| `legacy_layout` | Source has `conf.toml` and recognized kit directories but no manifest | -> `canonical` via `cfs kit normalize` |
| `registered_only` | Installed state can be reconstructed from `core.toml` bindings only | -> `canonical` when a manifest is added |
| `drifted` | Manifest/resource/risk hashes differ from registered state | -> `canonical` after accepted update/registration refresh |

### Kit Install Mode State

- [ ] `p1` - **ID**: `cpt-studio-state-kit-install-mode`

| State | Condition | Transitions |
|-------|-----------|-------------|
| `copy` | Resources are copied into Studio/project-approved effective destinations | -> `copy` on update via file-level diff |
| `register` | Local in-project resources are left in place and only bindings are recorded | -> `register` on update after containment revalidation |
| `mode_required` | Non-interactive local path install omitted `--install-mode` | -> `copy` or `register` when explicit mode is supplied |

---

## 5. Definitions of Done

### Kit Install Copies Files

- [x] `p1` - **ID**: `cpt-studio-dod-kit-install`

1. [x] - `p1` - `install_kit` copies all `_KIT_CONTENT_DIRS` and `_KIT_CONTENT_FILES` from source to `config/kits/{slug}/`
2. [x] - `p1` - Kit is registered in `core.toml` with correct path and version
3. [x] - `p1` - `.gen/` aggregates are updated after install
4. [x] - `p1` - **IF** kit contains `.cf-studio-kit.toml` or a legacy manifest: all declared resources are copied or registered at effective paths, template variables are preserved in source files, and resource bindings are registered in `core.toml` for read-time resolution
5. [x] - `p1` - **IF** local `--path` install: user is asked copy vs register in interactive mode, or `--install-mode` is required in non-interactive mode
6. [x] - `p1` - GitHub-backed installs persist GitHub-derived version authority and structured source/content metadata; `conf.toml version` is not authoritative
7. [x] - `p1` - Local/path installs are recorded as outside GitHub authority and reject conflicting GitHub selector options
8. [x] - `p1` - Public skills and subagents are generated with `cf-{kit-slug}-{name}` names and no double-prefixing

### Kit Update Shows Diffs

- [x] `p1` - **ID**: `cpt-studio-dod-kit-update`

1. [x] - `p1` - `file_level_kit_update` enumerates and classifies files correctly
2. [x] - `p1` - Interactive mode shows colored unified diffs per changed file
3. [x] - `p1` - User can accept/decline/modify per file, or bulk accept/decline all
4. [x] - `p1` - TOC sections are stripped for diff comparison and regenerated post-write
5. [x] - `p1` - Editor merge uses git-style conflict markers
6. [x] - `p1` - **IF** manifest-driven kit with resource bindings: files are updated at their registered paths, not default `config/kits/{slug}/` paths
7. [x] - `p1` - **IF** manifest-driven kit: new resources (in manifest but not in `core.toml` bindings) trigger path prompt and are registered
8. [x] - `p1` - **IF** kit source contains `whatsnew.toml`: display new version entries before file-level diff; user can abort update after reviewing
9. [x] - `p1` - GitHub-backed updates determine currentness from persisted/refreshed GitHub authority metadata, not `conf.toml`
10. [x] - `p1` - Offline GitHub update fallback reports and uses last-known source state only; it does not guess versions from local files
11. [x] - `p1` - Register-in-place updates re-read source files in place, revalidate containment, recompute hashes/risk, and update only bindings/state unless the user explicitly chooses copy or prune
12. [x] - `p1` - Removed resources are not deleted by normal update; prune requires explicit confirmation/fingerprint and never deletes registered source files

### Kit Validate Checks Integrity

- [x] `p1` - **ID**: `cpt-studio-dod-kit-validate`

1. [x] - `p1` - Canonical `kind = "constraints"` resources are parsed and validated per kit, with multiple files applied together; legacy `constraints.toml` remains supported for legacy kits
2. [x] - `p1` - Templates and examples are checked against constraints via `self_check`
3. [x] - `p1` - Both registered and standalone (by-path) kits can be validated
4. [x] - `p1` - For manifest-driven kits, all registered resource paths verified to exist on disk

---

## 6. Implementation Modules

| Module | Algorithms Implemented |
|--------|----------------------|
| `skills/studio/scripts/studio/commands/kit.py` | `cpt-studio-algo-kit-github-helpers`, `cpt-studio-algo-kit-content-mgmt`, `cpt-studio-algo-kit-regen-gen`, `cpt-studio-algo-kit-install`, `cpt-studio-algo-kit-update`, `cpt-studio-algo-kit-config-helpers`, `cpt-studio-algo-kit-manifest-install`, `cpt-studio-algo-kit-manifest-legacy-migration`, `cpt-studio-algo-kit-local-path-install-mode`, `cpt-studio-flow-kit-install-cli`, `cpt-studio-flow-kit-update-cli`, `cpt-studio-flow-kit-dispatch` |
| `skills/studio/scripts/studio/utils/kit_model.py` | `cpt-studio-algo-kit-model-normalize`, `cpt-studio-algo-kit-canonical-manifest`, `cpt-studio-algo-kit-public-component-generation`, `cpt-studio-algo-kit-tool-permission-risk`, `cpt-studio-algo-kit-manifest-normalize` |
| `skills/studio/scripts/studio/utils/manifest.py` | legacy manifest adapter, `cpt-studio-algo-kit-manifest-resolve`, `cpt-studio-algo-kit-manifest-source-mapping`, `cpt-studio-algo-kit-variable-resolution` |
| `skills/studio/scripts/studio/utils/diff_engine.py` | `cpt-studio-algo-kit-file-update`, `cpt-studio-algo-kit-file-enumerate`, `cpt-studio-algo-kit-file-classify`, `cpt-studio-algo-kit-interactive-review`, `cpt-studio-algo-kit-diff-display`, `cpt-studio-algo-kit-conflict-merge`, `cpt-studio-algo-kit-toc-handling`, `cpt-studio-algo-kit-snapshot` |
| `skills/studio/scripts/studio/commands/validate_kits.py` | `cpt-studio-algo-kit-validate`, `cpt-studio-algo-kit-validate-by-path`, `cpt-studio-flow-kit-validate-cli` |
| `skills/studio/scripts/studio/commands/adapter_info.py` | `cpt-studio-algo-kit-info-model-output` |
| `skills/studio/scripts/studio/commands/agents.py` | `cpt-studio-algo-kit-public-component-generation` |
| `skills/studio/scripts/studio/utils/whatsnew.py` | `cpt-studio-algo-kit-whatsnew-display` |

---

## 7. Acceptance Criteria

- [x] `p1` - `cfs kit install <owner/repo[@version]>` or `cfs kit install --path <dir>` installs a kit and returns JSON with status, files_copied
- [x] `p1` - `cfs kit install` with `.cf-studio-kit.toml`: validates canonical manifest, prompts for `user_modifiable` paths and local copy/register mode, copies or registers resources at effective paths, and records bindings in `core.toml`
- [x] `p1` - `cfs kit install --kit <slug>` selects one kit from a multi-kit `.cf-studio-kit.toml`; repeated `--kit`, comma-separated values, `--kit all`, and interactive selection install multiple selected kits with aggregate output
- [x] `p1` - `.cf-studio-kit.toml` is sufficient by itself; `conf.toml` is not required and is ignored for canonical fields when the canonical manifest is present
- [x] `p1` - `cfs kit normalize <path>` can generate a canonical `.cf-studio-kit.toml` from legacy `manifest.toml`, `conf.toml + layout`, or installed resource bindings without mutating resources
- [x] `p1` - A local path kit whose manifest and resources are inside the current project root can be explicitly registered in place without copying files
- [x] `p1` - `cfs kit update <path>` shows interactive diff and applies accepted changes
- [x] `p1` - `cfs kit update` with canonical or legacy manifest on legacy install: auto-populates resource bindings from existing kit root + manifest defaults
- [x] `p1` - `cfs kit update` with resource bindings: updates files at their registered paths (not default `config/kits/{slug}/` paths); new resources without bindings go to default paths
- [x] `p1` - `cfs validate-kits` validates all registered kits (constraints + templates); for manifest kits, verifies registered resource paths exist
- [x] `p1` - `.gen/AGENTS.md` and `.gen/SKILL.md` are regenerated after install/update
- [x] `p1` - `cfs generate-agents` consumes `KitModel.public_components` and emits skills/subagents/rules, not workflow directory scans, for manifest-backed kits
- [x] `p1` - Public skills and subagents generated from kits are named `cf-{kit-slug}-{name}` and already-prefixed names are not double-prefixed
- [x] `p1` - Legacy `workflow` entries are surfaced as skills with `origin = "legacy-workflow"` and deprecated workflow output is derived from those skills only for compatibility
- [x] `p1` - File-level diff correctly handles TOC stripping, conflict merging, and editor integration
- [x] `p1` - `cfs info` outputs canonical `kit_models` with resource bindings, generated names, install mode, drift, risk, provenance, and legacy `kit_details` derived from the same model
- [x] `p1` - `cfs resolve-vars` omits `{kit_slug.resource_id}` variables from the flat map, exposes unqualified variables only when unique, and warns on conflicts
- [x] `p1` - Install, update, info, resolve-vars, validate, and generate-agents all use the shared `KitModel` service; command-specific ad hoc kit scanning is limited to declared legacy adapters
- [x] `p1` - `cfs kit update` displays whatsnew entries from kit's `whatsnew.toml` before file-level diff (versions > installed version)
- [x] `p1` - All CDSL instructions have corresponding `@cpt-begin`/`@cpt-end` markers in code
- [x] `p1` - GitHub-backed kit registrations store `version` as GitHub-derived display/backcompat release/ref version plus structured authority metadata: resolver_mode, resolution_basis, requested_ref, resolved_ref, commit_sha/content identity, canonical_source, effective_source, verified, and freshness
- [x] `p1` - `conf.toml version` is optional local metadata only and never determines GitHub-backed install/update authority
- [x] `p1` - Local/path kit operations are outside GitHub authority and reject GitHub selector/ref flags
- [x] `p1` - Kit install/update/report output shows source, effective source, content identity, authority freshness, and any migration from legacy `conf.toml` metadata
- [x] `p1` - Offline GitHub fallback uses last-known persisted state and never guesses from installed files or local `conf.toml`
