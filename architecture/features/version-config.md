# Feature: Version & Config Management


<!-- toc -->

- [1. Feature Context](#1-feature-context)
  - [1. Overview](#1-overview)
  - [2. Purpose](#2-purpose)
  - [3. Actors](#3-actors)
  - [4. References](#4-references)
- [2. Actor Flows (CDSL)](#2-actor-flows-cdsl)
  - [Update Project Installation](#update-project-installation)
  - [Manage Config via CLI](#manage-config-via-cli)
- [3. Processes / Business Logic (CDSL)](#3-processes--business-logic-cdsl)
  - [Update Pipeline](#update-pipeline)
  - [Resolve GitHub Version Authority](#resolve-github-version-authority)
  - [Layout Restructuring](#layout-restructuring)
  - [Compare Blueprint Versions (LEGACY)](#compare-blueprint-versions-legacy)
  - [Migrate Config](#migrate-config)
- [4. States (CDSL)](#4-states-cdsl)
  - [Installation Version State](#installation-version-state)
- [5. Definitions of Done](#5-definitions-of-done)
  - [Update Command](#update-command)
  - [GitHub Version Authority](#github-version-authority)
  - [Version CLI Output](#version-cli-output)
  - [Config CLI Commands](#config-cli-commands)
  - [Config Migration](#config-migration)
  - [ralphex Integration Settings](#ralphex-integration-settings)
- [6. Implementation Modules](#6-implementation-modules)
- [7. Acceptance Criteria](#7-acceptance-criteria)

<!-- /toc -->

- [ ] `p2` - **ID**: `cpt-studio-featstatus-version-config`

## 1. Feature Context

- [ ] `p2` - `cpt-studio-feature-version-config`

### 1. Overview

Enables project skill updates with config migration, and provides CLI commands for managing ignore lists and kit registrations. System definitions are managed in `artifacts.toml` (per `cpt-studio-adr-remove-system-from-core-toml`). The update command refreshes `.core/` from the GitHub-backed proxy cache, whose version authority is the resolved GitHub Release/tag provenance captured at cache/update time. Local version files inside copied skill content are diagnostic only and MUST NOT be treated as authoritative. Project installs persist structured install provenance and freshness state in the project install metadata file. Kit file updates remain a separate operation via `cfs kit update`.

### 2. Purpose

Ensures teams can upgrade Studio without losing configuration or customizations while keeping GitHub-backed version state auditable and drift-free. Config CLI commands eliminate manual TOML editing and enforce schema validation. Addresses PRD requirements for version management (`cpt-studio-fr-core-version`) and CLI configuration (`cpt-studio-fr-core-cli-config`).

### 3. Actors

| Actor | Role in Feature |
|-------|-----------------|
| `cpt-studio-actor-user` | Runs `cfs update`, `cfs config`, `cfs migrate-config` |
| `cpt-studio-actor-studio-cli` | Executes update pipeline, config mutations, migration |

### 4. References

- **PRD**: [PRD.md](../PRD.md) — `cpt-studio-fr-core-version`, `cpt-studio-fr-core-layout-migration`, `cpt-studio-fr-core-cli-config`
- **Design**: [DESIGN.md](../DESIGN.md) — `cpt-studio-component-config-manager`, `cpt-studio-seq-update`
- **Dependencies**: `cpt-studio-feature-core-infra`, `cpt-studio-feature-blueprint-system`

## 2. Actor Flows (CDSL)

### Update Project Installation

- [ ] `p1` - **ID**: `cpt-studio-flow-version-config-update`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User runs `cfs update` → `.core/` refreshed from cache, old layout auto-restructured if detected, bundled kit refs migrated to GitHub sources, config scaffold ensured
- User runs `cfs update` → report shows the resolved GitHub Release/tag, commit/content identity, whether project install metadata was updated, and that local copied version files were ignored as authority
- Bundled kit (no `source` field) → auto-migrated to GitHub source
- Offline update/status lookup → uses last-known installed state, marks freshness/verification as offline, last-known, stale, unverified, or unknown according to the reporting surface, and prints the remediation command to re-verify online

**Error Scenarios**:
- Studio not initialized → error with hint to run `cfs init`
- Cache not available → error with hint to check network

**Steps**:
1. [x] - `p1` - User invokes `cfs update [--project-root P] [--dry-run]` - `inst-user-update`
2. [x] - `p1` - Resolve project root and studio directory - `inst-resolve-project`
3. [x] - `p1` - Replace `.core/` from cache (always force-overwrite) - `inst-replace-core`
4. [x] - `p1` - Detect directory layout; if old layout detected, trigger automatic restructuring using `cpt-studio-algo-version-config-layout-restructure` - `inst-detect-layout`
5. [x] - `p1` - Migrate `{cf-studio-path}/config/core.toml` preserving all user settings - `inst-migrate-config`
6. [ ] - `p1` - **IF** `core.toml` contains `[system]` section, remove it (system identity is defined in `artifacts.toml` per `cpt-studio-adr-remove-system-from-core-toml`); log removal in update report - `inst-remove-system-section`
7. [x] - `p1` - Migrate bundled kit references to GitHub sources (add `source` field for kits without one) - `inst-migrate-kit-sources`
7. [ ] - `p1` - **FOR EACH** registered kit: **IF** kit source contains `manifest.toml` and `core.toml` has no `[kits.{slug}.resources]` section, trigger legacy manifest migration via `cpt-studio-algo-kit-manifest-legacy-migration` (Feature 2 boundary) - `inst-manifest-legacy-migration`
8. [x] - `p1` - Ensure config scaffold files exist (create only if missing) - `inst-ensure-scaffold`
9. [x] - `p1` - Regenerate agent entry points - `inst-regenerate-agents`
9. [x] - `p1` - Run self-check to verify kit integrity (`run_self_check_from_meta`); include result in report, WARN if failed - `inst-self-check`
10. [x] - `p1` - **RETURN** update report with actions taken and self-check result - `inst-return-report`
11. [x] - `p1` - Imports, constants, and module setup for update command - `inst-update-imports`
12. [x] - `p1` - Display core whatsnew entries (cache vs installed) before applying update only when cache provenance is Git/GitHub-authoritative; local/path cache sources skip root `whatsnew.toml` display and install-root metadata refresh - `inst-whatsnew`
13. [x] - `p1` - Helper functions: ensure file creation, config README, auto-regenerate agents, read/show whatsnew - `inst-update-helpers`
14. [x] - `p1` - Human-friendly formatter for update report output - `inst-update-format-output`
15. [ ] - `p1` - Resolve authoritative cache provenance from GitHub Release/tag metadata; record resolved ref, release/tag name, commit/content identity, source URL, and verification timestamp - `inst-resolve-github-provenance`
16. [ ] - `p1` - Ignore local copied skill version files for version authority; use them only as legacy/display diagnostics when provenance is absent - `inst-ignore-local-version-authority`
17. [ ] - `p1` - Persist project install metadata with structured provenance and freshness state after `.core/` refresh succeeds - `inst-write-install-metadata`
18. [ ] - `p1` - Include resolved release/tag, commit/content identity, metadata update status, and local-files-ignored note in the update report - `inst-report-provenance`

### Manage Config via CLI

- [ ] `p2` - **ID**: `cpt-studio-flow-version-config-manage`

**Actor**: `cpt-studio-actor-user`

**Success Scenarios**:
- User runs `cfs config show` → displays current core.toml contents
- User runs `cfs config system add` → adds system definition to `artifacts.toml` with schema validation

**Steps**:
1. [ ] - `p2` - User invokes `cfs config <subcommand> [args]` - `inst-user-config`
2. [ ] - `p2` - Validate change against config schema - `inst-validate-schema`
3. [ ] - `p2` - Apply change to config file - `inst-apply-change`
4. [ ] - `p2` - **RETURN** summary of what was modified - `inst-return-config-summary`

## 3. Processes / Business Logic (CDSL)

### Update Pipeline

- [x] `p1` - **ID**: `cpt-studio-algo-version-config-update-pipeline`

1. [x] - `p1` - Replace `.core/` from cache - `inst-replace-core-algo`
2. [x] - `p1` - Detect and auto-restructure old directory layout - `inst-detect-layout-algo`
3. [x] - `p1` - Migrate `{cf-studio-path}/config/core.toml` - `inst-migrate-config-algo`
4. [x] - `p1` - Remove `[system]` section from `core.toml` if present (per `cpt-studio-adr-remove-system-from-core-toml`) - `inst-remove-system-section-algo`
5. [x] - `p1` - Migrate bundled kit references to GitHub sources (add `source` field) - `inst-migrate-kit-sources-algo`
6. [x] - `p1` - Trigger legacy manifest migration for kits updated to manifest-driven versions without existing resource bindings - `inst-manifest-legacy-migration-algo`
7. [x] - `p1` - Helper: check manifest presence and resource binding state before triggering migration - `inst-manifest-legacy-migration-helper`
8. [x] - `p1` - (Removed — no separate regen step; kit files are updated directly) - `inst-regen-algo`
9. [x] - `p1` - Ensure config scaffold - `inst-scaffold-algo`

### Resolve GitHub Version Authority

- [ ] `p1` - **ID**: `cpt-studio-algo-version-config-github-authority`

**Authority Rule**: For GitHub-backed proxy package builds, proxy cache, and project install state, release tags are the source of version truth. The Python package version is derived dynamically from SCM tag metadata at build/install time, while installed cache/project state uses resolved GitHub Release/tag provenance captured during cache resolution or update. Local/path cache sources are not version-authoritative: `cfs init` and `cfs update` must not create, replace, or delete install-root `version.toml` or `whatsnew.toml` from such cache content. Local version files copied into `.core/` or cache content are not authoritative.

1. [ ] - `p1` - Resolve explicit version, `latest`, or default target to a GitHub Release/tag/ref - `inst-authority-resolve-ref`
2. [ ] - `p1` - Capture source repository, resolved release/tag, resolved commit/content identity, asset/source URL, and retrieval timestamp - `inst-authority-capture-provenance`
3. [ ] - `p1` - Write cache/project provenance only after downloaded content is successfully extracted and installed - `inst-authority-commit-state`
4. [ ] - `p1` - Mark freshness as `verified` when GitHub resolution succeeds online; mark as `unknown`/`unverified` when only last-known local state is available - `inst-authority-freshness`
5. [ ] - `p1` - Never overwrite authoritative provenance from local copied `__version__`, `.version`, or equivalent legacy files - `inst-authority-ignore-local-files`
6. [ ] - `p1` - Configure proxy package metadata so `pyproject.toml` declares dynamic versioning from SCM tags instead of a checked-in literal package version - `inst-proxy-dynamic-version`

### Layout Restructuring

- [x] `p1` - **ID**: `cpt-studio-algo-version-config-layout-restructure`

**Input**: Studio directory path

**Output**: Restructured directory layout or no-op if already new layout

**Detection**: Old layout is detected when `{cf-studio-path}/.gen/kits/{slug}/` exists.

**Steps**:
1. [x] - `p1` - Backup affected directories - `inst-layout-backup`
2. [x] - `p1` - Move generated outputs: `.gen/kits/{slug}/` → `config/kits/{slug}/` - `inst-layout-move-gen`
3. [x] - `p1` - Remove old `kits/{slug}/` reference copies if present - `inst-layout-remove-refs`
4. [x] - `p1` - Remove `.gen/kits/` directory (preserve `.gen/AGENTS.md`, `.gen/SKILL.md`, `.gen/README.md`) - `inst-layout-clean-gen`
5. [x] - `p1` - Update `core.toml` kit registrations with new paths (`config/kits/{slug}`) - `inst-layout-update-core`
6. [x] - `p1` - **IF** any step fails, restore from backup and report error - `inst-layout-rollback`

**Supporting**:
- [x] - `p1` - Migrate single entry from old `kits/{slug}/` directory to new layout - `inst-migrate-kits-entry`
- [x] - `p1` - Migrate single entry from old `.gen/kits/{slug}/` directory to config - `inst-migrate-gen-entry`
- [x] - `p1` - Update kit path registrations in `core.toml` after layout migration - `inst-update-core-paths`

### Compare Blueprint Versions (LEGACY)

- [x] `p1` - **ID**: `cpt-studio-algo-version-config-compare-versions`

> **LEGACY**: Blueprint version comparison is preserved for backward compatibility with v2/early-v3 installations. New kit updates use file-level diff.

1. - `p1` - Read `@cpt:blueprint` TOML block from each blueprint to extract version - `inst-read-versions`
2. - `p1` - Compare cache version vs user version per blueprint - `inst-compare-per-bp`
3. - `p1` - **RETURN** `current` (same), `migration_needed` (higher), or `missing` - `inst-return-comparison`

### Migrate Config

- [ ] `p2` - **ID**: `cpt-studio-algo-version-config-migrate`

1. - `p2` - Create backup of current config - `inst-backup`
2. - `p2` - Apply migration rules preserving user settings - `inst-apply-migration`
3. - `p2` - Report any settings that could not be migrated - `inst-report-unmigrated`

## 4. States (CDSL)

### Installation Version State

- [x] `p1` - **ID**: `cpt-studio-state-version-config-installation`

```
[UNINSTALLED] --init/update-online--> [INSTALLED_VERIFIED]
[INSTALLED_VERIFIED] --new-release/tag-available--> [OUTDATED_VERIFIED]
[OUTDATED_VERIFIED] --update-online--> [INSTALLED_VERIFIED]
[INSTALLED_VERIFIED] --offline-lookup--> [INSTALLED_UNVERIFIED]
[INSTALLED_UNVERIFIED] --online-reverify--> [INSTALLED_VERIFIED]
[OUTDATED_VERIFIED] --update-with-migration--> [MIGRATION_NEEDED] --manual-resolve--> [INSTALLED_VERIFIED]
```

Installed state is derived from project install metadata. Freshness describes whether the last-known provenance was verified against GitHub during the current operation. Offline lookup MUST NOT claim freshness; it reports the last-known release/tag and remediation command.

## 5. Definitions of Done

### Update Command

- [x] `p1` - **ID**: `cpt-studio-dod-version-config-update`

- [x] - `p1` - `cfs update` replaces `.core/` from cache
- [x] - `p1` - `cfs update` detects old directory layout and auto-restructures (move generated outputs from `.gen/kits/` to `config/kits/`, remove old reference copies)
- [x] - `p1` - `cfs update` migrates bundled kit references to GitHub sources (versions < 3.0.8)
- [x] - `p1` - User config files in `config/` are NEVER overwritten
- [x] - `p1` - [LEGACY] Blueprint version comparison detects same, migration needed, and missing states
- [x] - `p1` - `cfs update` renders `whatsnew` ANSI styling only when stderr is a TTY; redirected or piped stderr stays plain text
- [x] - `p1` - `cfs init` and `cfs update` skip install-root `version.toml` and `whatsnew.toml` when cache provenance is local/path rather than Git/GitHub
- [x] - `p1` - `cfs update` removes leftover `config/kits/*/blueprints/` directories from pre-ADR-0001 installs
- [x] - `p1` - `cfs update` removes legacy `[system]` section from `config/core.toml` (system identity now lives in `artifacts.toml`)
- [x] - `p1` - `cfs update` auto-migrates legacy kits to manifest-driven resource bindings when source contains `manifest.toml` and core.toml lacks `[kits.{slug}.resources]`
- [ ] - `p1` - `cfs update` updates project install metadata after successful `.core/` refresh
- [ ] - `p1` - `cfs update` reports authoritative GitHub provenance instead of local copied version-file values

### GitHub Version Authority

- [ ] `p1` - **ID**: `cpt-studio-dod-version-config-github-authority`

- [ ] - `p1` - GitHub-backed cache/project state uses resolved GitHub Release/tag provenance as version authority
- [ ] - `p1` - Local copied version files are ignored for authority and treated only as legacy/display diagnostics
- [ ] - `p1` - Project install metadata stores structured provenance: source repo, resolved release/tag/ref, commit/content identity, retrieval timestamp, and freshness state
- [ ] - `p1` - Offline lookup reports last-known state with freshness `unknown`/`unverified` and a remediation command
- [ ] - `p1` - `cfs update` report includes resolved release/tag, commit/content identity, metadata update status, and local-files-ignored status

### Version CLI Output

- [ ] `p1` - **ID**: `cpt-studio-dod-version-config-cli-version`

- [ ] - `p1` - `cfs --version` separates package metadata from installed engine state
- [ ] - `p1` - Proxy/package version is reported from installed package metadata derived from the Git release tag
- [ ] - `p1` - Cached/project engine state is reported from structured install/cache provenance when available
- [ ] - `p1` - Offline or stale provenance is clearly labeled as last-known and freshness `unknown`/`unverified`

### Config CLI Commands

- [ ] `p2` - **ID**: `cpt-studio-dod-version-config-cli`

- [ ] - `p2` - `cfs config show` displays current configuration
- [ ] - `p2` - `cfs config system add/remove` manages system definitions in `artifacts.toml`
- [ ] - `p2` - Schema validation rejects invalid changes before writing

### Config Migration

- [ ] `p2` - **ID**: `cpt-studio-dod-version-config-migration`

- [ ] - `p2` - `cfs migrate-config` migrates legacy JSON configs to TOML
- [ ] - `p2` - Backup created before any migration
- [ ] - `p2` - User settings preserved across version upgrades

### ralphex Integration Settings

- [ ] `p1` - **ID**: `cpt-studio-dod-version-config-ralphex-settings`

The Config Manager MUST persist resolved `ralphex` executable path and related integration settings in `core.toml` so that future delegation does not require re-discovery. Settings are stored under a dedicated `[integrations.ralphex]` section in `core.toml`.

**Persisted settings**:
- `executable_path` — resolved absolute path to the `ralphex` binary

Note: `plans_dir` and other execution-time settings are owned by ralphex's own config precedence chain (CLI flags > local `.ralphex/` > global `~/.config/ralphex/` > embedded defaults). Studio does not duplicate or override ralphex's `plans_dir` resolution — it queries ralphex at export time to determine the active plans directory.

**Implements**:
- `cpt-studio-component-config-manager` (see `cpt-studio-adr-ralphex-delegation-skill`)

## 6. Implementation Modules

| Module | Path | Responsibility |
|--------|------|----------------|
| Update Command | `skills/.../commands/update.py` | Update pipeline, layout restructuring, file-level kit diff |
| Proxy Cache Provenance | `src/studio_proxy/cache.py` / `src/studio_proxy/resolve.py` | Resolve GitHub Release/tag authority, persist cache provenance, expose last-known freshness |
| Version CLI | `src/studio_proxy/cli.py` | Print package metadata separately from cached/project installed engine state |
| Project Install Metadata | `skills/.../commands/update.py` | Persist project install provenance and freshness after successful update |

## 7. Acceptance Criteria

- [x] `cfs update` refreshes `.core/` without touching user config
- [x] `cfs update` detects and auto-restructures old directory layout with backup and rollback
- [x] `cfs update` migrates bundled kit references to GitHub sources (versions < 3.0.8)
- [x] [LEGACY] Blueprint version comparison correctly identifies same, migration needed, and missing states
- [ ] `cfs config show` displays readable config summary
- [ ] Config migration preserves all user settings with backup
- [ ] `core.toml` `[integrations.ralphex]` section persists resolved executable path
- [x] `cfs update` automatically runs self-check after update and reports WARN if integrity check fails
- [ ] GitHub Release/tag provenance is the authority for GitHub-backed cache and project install state
- [ ] Local copied version files do not determine installed version authority
- [ ] Project install metadata records structured provenance and freshness state
- [ ] `cfs --version` separates proxy package version from cached/project engine install state
- [ ] `cfs update` reports resolved release/tag, commit/content identity, metadata updated, and local files ignored
- [ ] Offline lookup reports last-known state, freshness unknown/unverified, and remediation command
- [ ] Tests cover cross-source version authority matrix: GitHub release asset, GitHub tag/ref tarball, local source, existing legacy `.version`/`__version__`, and offline last-known lookup
- [ ] Tests cover legacy idempotency: repeated update of pre-provenance installs does not churn metadata or regress legacy migrations
