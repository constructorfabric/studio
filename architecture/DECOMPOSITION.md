# Decomposition: Studio



<!-- toc -->

- [1. Overview](#1-overview)
- [2. Entries](#2-entries)
  - [2.1 Core Infrastructure ⏳ HIGH](#21-core-infrastructure--high)
  - [2.2 Kit Management ⏳ HIGH](#22-kit-management--high)
  - [2.3 Traceability & Validation ⏳ HIGH](#23-traceability--validation--high)
  - [2.4 SDLC Kit & Artifact Pipeline (EXTRACTED) ⏳ HIGH](#24-sdlc-kit--artifact-pipeline-extracted--high)
  - [2.5 Agent Integration & Workflows ✅ DONE](#25-agent-integration--workflows--done)
  - [2.6 PR Workflows (EXTRACTED) ⏳ MEDIUM](#26-pr-workflows-extracted--medium)
  - [2.7 Version & Config Management ⏳ MEDIUM](#27-version--config-management--medium)
  - [2.8 Developer Experience ⏳ LOW](#28-developer-experience--low)
  - [2.9 Advanced SDLC Workflows (EXTRACTED) ⏳ LOW](#29-advanced-sdlc-workflows-extracted--low)
  - [2.10 Spec Coverage ⏳ HIGH](#210-spec-coverage--high)
  - [2.11 Execution Plans 🔶 HIGH](#211-execution-plans--high)
  - [2.12 Multi-Repo Workspace Federation ✅ DONE](#212-multi-repo-workspace-federation--done)
  - [2.13 Subagent Registration ⏳ HIGH](#213-subagent-registration--high)
  - [2.14 ralphex Delegation ⏳ HIGH](#214-ralphex-delegation--high)
  - [2.15 Project-Level Extensibility ⏳ HIGH](#215-project-level-extensibility--high)
  - [2.16 Dependency Mapping 🔶 HIGH](#216-dependency-mapping--high)
- [3. Feature Dependencies](#3-feature-dependencies)

<!-- /toc -->

## 1. Overview

Studio DESIGN is decomposed into features organized around architectural layers and functional cohesion. The decomposition follows a dependency order where core infrastructure enables the kit system and validation, which in turn enable agent integration and advanced workflows.

**Decomposition Strategy**:
- Features grouped by architectural layer and functional cohesion (related components together)
- Dependencies minimize coupling between features — each feature is independently implementable given its dependencies
- SDLC-specific features (F4, F6, F9) have been **extracted** to the SDLC kit repository (`constructorfabric/studio-kit-sdlc`) per `cpt-studio-adr-extract-sdlc-kit`
- Core features (F1–F3, F5, F7–F8, F10–F15) cover all core functional requirements


## 2. Entries

**Overall implementation status:**

- [ ] `p1` - **ID**: `cpt-studio-status-overall`

### 2.1 [Core Infrastructure](features/core-infra.md) ⏳ HIGH

- [ ] `p1` - **ID**: `cpt-studio-feature-core-infra`

- **Purpose**: Provide the foundation layer — global CLI proxy, skill engine command dispatch, config directory management, and project initialization — upon which all other features are built.

- **Depends On**: None

- **Scope**:
  - Global CLI proxy with local cache (`~/.cf-studio/cache/`), automatic skill bundle download from GitHub on first run, command routing, background version checks
  - Skill engine: command dispatch, JSON output serialization, exit code conventions (0/1/2)
  - Config manager: `{cf-studio-path}/config/core.toml` CRUD (including resource bindings for manifest-driven kits), schema validation, deterministic TOML serialization, resource path lookup API for other components
  - Project initialization: interactive bootstrapper, root system definition (name/slug from directory) written to `artifacts.toml` `[[systems]]`, per-kit config output directory selection, `{cf-studio-path}/config/core.toml` creation (with kit config paths), `{cf-studio-path}/config/artifacts.toml` with default autodetect rules, `{cf-studio-path}/kits/` directory creation, root `AGENTS.md` injection, `{cf-studio-path}/config/AGENTS.md` with default WHEN rules

- **Out of scope**:
  - Kit installation logic (Feature 2)
  - Validation logic (Feature 3)
  - Agent entry point generation (Feature 5)
  - CLI config subcommands beyond init (Feature 7)

- **Requirements Covered**:

  - `p1` - `cpt-studio-fr-core-installer`
  - `p1` - `cpt-studio-fr-core-init`
  - `p1` - `cpt-studio-fr-core-config`
  - `p1` - `cpt-studio-fr-core-skill-engine`
  - `p1` - `cpt-studio-fr-core-mirror-override`
  - `p1` - `cpt-studio-fr-core-telemetry`
  - `p1` - `cpt-studio-fr-core-toc`
  - `p1` - `cpt-studio-nfr-adoption-usability`
  - `p1` - `cpt-studio-nfr-reliability-recoverability`

- **Design Principles Covered**:

  - `p1` - `cpt-studio-principle-determinism-first`
  - `p1` - `cpt-studio-principle-occams-razor`
  - `p2` - `cpt-studio-principle-tool-managed-config`
  - `p1` - `cpt-studio-principle-zero-harm`

- **Design Constraints Covered**:

  - `p1` - `cpt-studio-constraint-python-stdlib`
  - `p1` - `cpt-studio-constraint-cross-platform`
  - `p2` - `cpt-studio-constraint-git-project-heuristics`

- **Domain Model Entities**:
  - System
  - Config
  - Kit (registration only)

- **Design Components**:

  - `p1` - `cpt-studio-component-cli-proxy`
  - `p1` - `cpt-studio-component-skill-engine`
  - `p1` - `cpt-studio-component-config-manager`

- **API**:
  - `cfs init [--dir DIR] [--agents AGENTS]`
  - `cfs config show`

- **Sequences**:
  - `cpt-studio-seq-init`

- **Data**:
  - `{cf-studio-path}/config/core.toml` — kit registrations (including resource bindings for manifest-driven kits), project root, ignore lists (system identity defined in `artifacts.toml` per `cpt-studio-adr-remove-system-from-core-toml`)
  - `{cf-studio-path}/config/artifacts.toml` — artifact registry with autodetect rules


### 2.2 [Kit Management](features/kit-management.md) ⏳ HIGH

- [ ] `p1` - **ID**: `cpt-studio-feature-blueprint-system`

- **Purpose**: Manage kit lifecycle — installation, file-level diff updates, interactive conflict resolution, SKILL/AGENTS composition, and kit structural validation. Kits are direct file packages (per `cpt-studio-adr-remove-blueprint-system`).

- **Depends On**: `cpt-studio-feature-core-infra`

- **Scope**:
  - Kit Manager: install kits (copy files from source into `{cf-studio-path}/config/kits/{slug}/`), register in `core.toml`
  - Manifest-driven installation: if kit contains `manifest.toml`, validate against `kit-manifest.schema.json`, read declared resources, prompt user for `user_modifiable` resource paths (offering defaults), copy resources to resolved paths, resolve `{identifier}` template variables in kit files, register all resource bindings in `core.toml` under `[kits.{slug}.resources]`. Kit root directory itself is relocatable when manifest permits. Falls back to legacy copy behavior when no manifest present
  - Legacy install migration: when updating a kit that was installed without a manifest and the new version introduces one, auto-populate all resource bindings from existing kit root + manifest `default_path` values without requiring re-installation
  - Update model: force mode (full overwrite) and interactive mode (file-level diff — compare each file in new version against user's installed copy, present unified diffs with accept/decline/accept-all/decline-all/modify prompts). For manifest-driven kits, updates use registered resource paths, detect new resources (prompt for path), warn about removed resources
  - Resource Diff Engine: interactive conflict resolution for kit file updates (`accept-file`, `reject-file`, `accept-all`, `reject-all`, `modify` with git-style conflict markers)
  - Kit config relocation: `cfs kit move-config <slug>` moves kit config directory, updates `core.toml` (including all resource paths relative to kit root)
  - SKILL composition: collect kit `SKILL.md` files and write to `{cf-studio-path}/config/SKILL.md`
  - System prompt composition: collect kit AGENTS.md content and append to `{cf-studio-path}/config/AGENTS.md`
  - Kit structural validation: verify required files (`conf.toml`, `constraints.toml`, `artifacts/` directory); for manifest-driven kits, verify all registered resource paths exist on disk

- **Out of scope**:
  - Custom plugin hooks and CLI subcommands (planned p2 plugin system)
  - Validation of kit file content (Feature 3)

- **Requirements Covered**:

  - `p1` - `cpt-studio-fr-core-kits`
  - `p1` - `cpt-studio-fr-core-kit-manifest`
  - `p1` - `cpt-studio-fr-core-resource-diff`

- **Design Principles Covered**:

  - `p1` - `cpt-studio-principle-kit-centric`
  - `p1` - `cpt-studio-principle-plugin-extensibility`
  - `p1` - `cpt-studio-principle-dry`
  - `p2` - `cpt-studio-principle-no-manual-maintenance`

- **Design Constraints Covered**:

  - `p1` - `cpt-studio-constraint-markdown-contract`

- **Domain Model Entities**:
  - Kit
  - Manifest
  - ResourceBinding
  - Constraint
  - Workflow

- **Design Components**:

  - `p1` - `cpt-studio-component-kit-manager`

- **API**:
  - `cfs kit install <path>`
  - `cfs kit update [--force]`
  - `cfs kit move-config <slug>`

- **Sequences**:

  None (kit file operations are invoked internally by kit install/update)

- **Data**:
  - `{cf-studio-path}/config/kits/{slug}/conf.toml` — kit version metadata
  - `{cf-studio-path}/config/kits/{slug}/manifest.toml` — (optional) declarative installation manifest
  - `{cf-studio-path}/config/kits/{slug}/SKILL.md` — per-kit skill (user-editable)
  - `{cf-studio-path}/config/kits/{slug}/constraints.toml` — kit-wide structural constraints (user-editable)
  - `{cf-studio-path}/config/kits/{slug}/artifacts/{KIND}/` — per-artifact files (user-editable)
  - `{cf-studio-path}/config/kits/{slug}/codebase/` — codebase rules and checklist (user-editable)
  - `{cf-studio-path}/config/kits/{slug}/workflows/` — generated workflow files (user-editable)
  - `{cf-studio-path}/config/kits/{slug}/scripts/` — kit scripts and prompts (user-editable)
  - `{cf-studio-path}/config/core.toml` → `[kits.{slug}.resources]` — resolved resource identifier → path bindings (for manifest-driven kits)


### 2.3 [Traceability & Validation](features/traceability-validation.md) ⏳ HIGH

- [ ] `p1` - **ID**: `cpt-studio-feature-traceability-validation`

- **Purpose**: Provide the deterministic quality gate — ID scanning, cross-reference resolution, structural validation, and constraint enforcement — that catches issues without relying on LLMs.

- **Depends On**: `cpt-studio-feature-core-infra`

- **Scope**:
  - Traceability Engine: scan artifacts for ID definitions and references, scan code for `@cpt-*` tags, resolve cross-references, query commands (list-ids, list-id-kinds, where-defined, where-used, get-content), ID versioning (`-vN`)
  - Validator: template structure compliance, ID format validation, priority markers, placeholder detection, cross-reference validation (covered_by, checked consistency), constraint enforcement from `constraints.toml`. For manifest-driven kits, resolves paths to constraints, templates, and examples from resource bindings in `core.toml` instead of assuming default kit directory structure
  - Cross-artifact validation: load all registered artifacts, compare definitions vs references per constraints rules
  - CDSL: parse instruction markers for implementation tracking
  - Single-pass scanning for ≤3s performance

- **Out of scope**:
  - Semantic validation (checklist review done by AI agents)
  - Modifying artifacts (read-only analysis)
  - Kit-specific validation hooks (planned p2)

- **Requirements Covered**:

  - `p1` - `cpt-studio-fr-core-traceability`
  - `p1` - `cpt-studio-fr-core-cdsl`
  - `p1` - `cpt-studio-nfr-validation-performance`
  - `p1` - `cpt-studio-nfr-security-integrity`

- **Design Principles Covered**:

  - `p1` - `cpt-studio-principle-determinism-first`
  - `p1` - `cpt-studio-principle-traceability-by-design`
  - `p1` - `cpt-studio-principle-ci-automation-first`
  - `p2` - `cpt-studio-principle-machine-readable`

- **Design Constraints Covered**:

  - `p1` - `cpt-studio-constraint-no-weakening`

- **Domain Model Entities**:
  - Identifier
  - Artifact
  - Constraint

- **Design Components**:

  - `p1` - `cpt-studio-component-validator`
  - `p1` - `cpt-studio-component-traceability-engine`

- **API**:
  - `cfs validate --artifact <path>`
  - `cfs validate`
  - `cfs list-ids [--kind K] [--pattern P]`
  - `cfs where-defined --id <id>`
  - `cfs where-used --id <id>`
  - `cfs get-content --id <id>`

- **Sequences**:
  - `cpt-studio-seq-validate`
  - `cpt-studio-seq-traceability-query`

- **Data**:
  - In-memory ID index (definitions + references, built from filesystem scan)


### 2.4 SDLC Kit & Artifact Pipeline (EXTRACTED) ⏳ HIGH

> **EXTRACTED per `cpt-studio-adr-extract-sdlc-kit`**: This feature has been moved to the SDLC kit repository (`constructorfabric/studio-kit-sdlc`). All SDLC-specific scope, requirements, components, and data are now owned by the kit's own repository.


### 2.5 [Agent Integration & Workflows](features/agent-integration.md) ✅ DONE

- [x] `p1` - **ID**: `cpt-studio-feature-agent-integration`

- **Purpose**: Bridge Studio's unified skill system to diverse AI coding assistants by generating agent-native entry points and providing generic generate/analyze workflows.

- **Depends On**: `cpt-studio-feature-core-infra`

- **Scope**:
  - Agent Generator: produce entry points in each agent's native format
  - Supported agents: Windsurf, Cursor, Claude, Copilot, OpenAI
  - SKILL.md composition: collect `@cpt:skill` sections and assemble into main SKILL.md
  - Full overwrite on each invocation; `--agent` flag for single-agent regeneration
  - Generic workflows: `{cf-studio-path}/.core/workflows/generate.md` and `{cf-studio-path}/.core/workflows/analyze.md` with common execution protocol

- **Out of scope**:
  - Agent-specific state persistence
  - Kit-specific workflow content (provided by Feature 4)

- **Requirements Covered**:

  - `p1` - `cpt-studio-fr-core-agents`
  - `p1` - `cpt-studio-fr-core-workflows`

- **Design Principles Covered**:

  - `p2` - `cpt-studio-principle-skill-documented`
  - `p2` - `cpt-studio-principle-no-manual-maintenance`

- **Design Constraints Covered**:

  None

- **Domain Model Entities**:
  - AgentEntryPoint
  - Workflow

- **Design Components**:

  - `p1` - `cpt-studio-component-agent-generator`

- **API**:
  - `cfs agents [--agent A]` — read-only listing of generated agent integration files
  - `cfs generate-agents [--agent A] [--dry-run]` — generate or update agent integration files (full overwrite on each invocation)

- **Sequences**:
  - `cpt-studio-seq-generate-workflow`

- **Data**:
  - Workflow entry points: `.windsurf/workflows/`, `.cursor/commands/`, `.claude/commands/`, `.github/prompts/`
  - Shared skill stubs (non-Claude): `.agents/skills/`
  - Agent-specific subagents: `.cursor/agents/`, `.claude/agents/`, `.github/agents/`, `.codex/agents/`


### 2.6 PR Workflows (EXTRACTED) ⏳ MEDIUM

> **EXTRACTED per `cpt-studio-adr-extract-sdlc-kit`**: This feature has been moved to the SDLC kit repository (`constructorfabric/studio-kit-sdlc`). PR review and status workflows are now provided by the SDLC kit as kit workflows.


### 2.7 [Version & Config Management](features/version-config.md) ⏳ MEDIUM

- [ ] `p2` - **ID**: `cpt-studio-feature-version-config`

- **Purpose**: Enable project skill updates with config migration, and provide CLI commands for managing ignore lists and kit registrations.

- **Depends On**: `cpt-studio-feature-core-infra`

- **Scope**:
  - Update command: copy cached skill to project, detect and auto-restructure old directory layout, migrate `{cf-studio-path}/config/core.toml`, migrate bundled kit references to GitHub sources (versions < 3.0.8), regenerate agent entry points
  - Layout restructuring: automatically detect old directory layout during `cfs update` and restructure (move generated outputs from `.gen/kits/` to `config/kits/`, remove old reference copies)
  - Config migration: backup before applying, preserve all user settings across versions
  - CLI config interface: `config system add/remove`, dry-run mode
  - Schema validation before all config writes
  - Version information: `--version` flag

- **Out of scope**:
  - Kit-specific CLI subcommands (planned p2 plugin)
  - Initial project setup (Feature 1)

- **Requirements Covered**:

  - `p2` - `cpt-studio-fr-core-version`
  - `p1` - `cpt-studio-fr-core-layout-migration`
  - `p2` - `cpt-studio-fr-core-cli-config`
  - `p1` - `cpt-studio-nfr-reliability-recoverability`

- **Design Principles Covered**:

  - `p2` - `cpt-studio-principle-tool-managed-config`
  - `p2` - `cpt-studio-principle-no-manual-maintenance`

- **Design Constraints Covered**:

  None

- **Domain Model Entities**:
  - Config

- **Design Components**:

  Components reused from Feature 1 (`config-manager`, `skill-engine`) and Feature 2 (`kit-manager`)

- **API**:
  - `cfs update [--check]`
  - `cfs migrate-config`
  - `cfs config system add <name> [--kit K]`
  - `cfs config system remove <name>`
  - `cfs --version`

- **Sequences**:
  - `cpt-studio-seq-update`

- **Data**:
  - `{cf-studio-path}/config/core.toml` — migrated config with version field


### 2.8 [Developer Experience](features/developer-experience.md) ⏳ LOW

- [ ] `p2` - **ID**: `cpt-studio-feature-developer-experience`

- **Purpose**: Enhance developer productivity with IDE integration, environment health checks, and utility commands for daily use.

- **Depends On**: `cpt-studio-feature-traceability-validation`

- **Scope**:
  - VS Code extension: ID syntax highlighting, go-to-definition, real-time validation, autocompletion, hover info, CodeLens, traceability tree view, quick fixes — all delegated to `cfs validate`
  - `cfs doctor`: check Python version, git, gh CLI, agents, config integrity
  - `cfs self-check`: validate examples against templates
  - `cfs resolve-vars`: resolve template variables (`{adr_template}`, `{scripts}`, etc.) to absolute paths from core.toml resource bindings
  - `cfs hook install/uninstall`: git pre-commit hooks for validation
  - `cfs completions install`: shell completion scripts for bash/zsh/fish

- **Out of scope**:
  - VS Code extension publishing (separate repo/process)
  - IDE-specific validation logic (delegated to skill)

- **Requirements Covered**:

  - `p2` - `cpt-studio-fr-core-vscode-plugin`
  - `p2` - `cpt-studio-fr-core-template-qa`
  - `p2` - `cpt-studio-fr-core-doctor`
  - `p3` - `cpt-studio-fr-core-hooks`
  - `p3` - `cpt-studio-fr-core-completions`

- **Design Principles Covered**:

  - `p2` - `cpt-studio-principle-machine-readable`
  - `p1` - `cpt-studio-principle-zero-harm`

- **Design Constraints Covered**:

  None

- **Domain Model Entities**:
  - Identifier (for IDE features)

- **Design Components**:

  Components reused from Feature 3 (`validator`, `traceability-engine`)

- **API**:
  - `cfs doctor`
  - `cfs self-check`
  - `cfs resolve-vars`
  - `cfs hook install`
  - `cfs hook uninstall`
  - `cfs completions install`

- **Sequences**:

  None

- **Data**:

  None


### 2.9 Advanced SDLC Workflows (EXTRACTED) ⏳ LOW

> **EXTRACTED per `cpt-studio-adr-extract-sdlc-kit`**: This feature has been moved to the SDLC kit repository (`constructorfabric/studio-kit-sdlc`). Code generation, brownfield support, feature lifecycle, PR config, and quickstart guides are now provided by the SDLC kit.


### 2.10 [Spec Coverage](features/spec-coverage.md) ⏳ HIGH

- [x] `p1` - **ID**: `cpt-studio-feature-spec-coverage`

- **Purpose**: Measure how much of a project's codebase is covered by CDSL specification markers, report coverage percentage and instruction granularity quality, and support reverse-engineering of feature specs from existing code.

- **Depends On**: `cpt-studio-feature-traceability-validation`

- **Scope**:
  - Coverage percentage: ratio of spec-covered lines to total effective lines
  - Granularity score: instruction density (~1 instruction per 10 lines of code)
  - JSON report matching `coverage.py` structure (summary + per-file)
  - Threshold enforcement via `--min-coverage` and `--min-granularity` flags
  - Reverse-engineering workflow: identify uncovered code, place markers, generate specs (p2)

- **Out of scope**:
  - Modifying validation logic (Feature 3)
  - Generating PRD or DESIGN from code (manual process)

- **Requirements Covered**:

  - `p1` - `cpt-studio-fr-core-traceability`
  - `p1` - `cpt-studio-fr-core-cdsl`

- **Design Principles Covered**:

  - `p1` - `cpt-studio-principle-traceability-by-design`
  - `p1` - `cpt-studio-principle-determinism-first`

- **Design Constraints Covered**:

  - `p1` - `cpt-studio-constraint-no-weakening`

- **Domain Model Entities**:
  - CodeFile
  - CoverageRecord
  - CoverageReport

- **Design Components**:

  - `p1` - `cpt-studio-component-traceability-engine`
  - `p1` - `cpt-studio-component-validator`

- **API**:
  - `cfs spec-coverage [--min-coverage N] [--min-granularity N] [--verbose]`

- **Sequences**:

  None (single-command flow)

- **Data**:
  - Registered codebase entries from `{cf-studio-path}/config/artifacts.toml`


### 2.11 [Execution Plans](features/execution-plans.md) 🔶 HIGH

- [ ] `p1` - **ID**: `cpt-studio-feature-execution-plans`

- **Purpose**: Decompose large agent tasks into self-contained phase files that fit within a single LLM context window, eliminating context overflow and non-deterministic results from attention drift.

- **Depends On**: `cpt-studio-feature-agent-integration`

- **Scope**:
  - Plan workflow (`workflows/plan.md`): instructions for AI agents to decompose tasks into phases and generate self-contained phase files
  - Phase file template (`requirements/plan-template.md`): strict structure for generated phase files — TOML frontmatter, inlined rules, pre-resolved paths, binary acceptance criteria
  - Decomposition strategies (`requirements/plan-decomposition.md`): how to split tasks by type — generate (template sections), analyze (checklist categories), implement (CDSL blocks)
  - Budget enforcement: ≤500 lines target, ≤1000 lines max per phase file
  - Plan storage: `{cf-studio-path}/.plans/{task-slug}/` directory (git-ignored) with `plan.toml` manifest and phase files
  - Phase execution: agent reads self-contained phase file, follows instructions, reports against acceptance criteria
  - Status tracking: `plan.toml` tracks phase lifecycle (pending → in_progress → done/failed)

- **Out of scope**:
  - CLI commands for plan management (pure prompt-level feature)
  - Modifications to existing generate.md or analyze.md workflows
  - Deterministic validation of phase files (phase files are ephemeral execution artifacts)

- **Requirements Covered**:

  - `p1` - `cpt-studio-fr-core-execution-plans`
  - `p1` - `cpt-studio-fr-core-workflows`

- **Design Principles Covered**:

  - `p1` - `cpt-studio-principle-determinism-first`
  - `p1` - `cpt-studio-principle-occams-razor`

- **Design Constraints Covered**:

  - `p1` - `cpt-studio-constraint-markdown-contract`

- **Domain Model Entities**:
  - ExecutionPlan
  - Phase
  - PhaseFile

- **Design Components**:

  Components reused from Feature 5 (`workflow-engine` via generate/analyze patterns)

- **API**:
  None (prompt-level feature — no CLI commands)

- **Sequences**:

  None (agent-driven workflow)

- **Data**:
  - `{cf-studio-path}/.plans/{task-slug}/plan.toml` — plan manifest with phase metadata and status
  - `{cf-studio-path}/.plans/{task-slug}/phase-{NN}-{slug}.md` — self-contained phase files


### 2.12 [Multi-Repo Workspace Federation](features/workspace.md) ✅ DONE

- [x] `p1` - **ID**: `cpt-studio-feature-workspace`

- **Purpose**: Enable multi-repo workspace federation — discover repos in nested sub-directories, configure sources, generate workspace config, and provide cross-repo artifact traceability without merging adapters.

- **Depends On**: `cpt-studio-feature-core-infra`, `cpt-studio-feature-traceability-validation`

- **Scope**:
  - Workspace configuration: standalone `.studio-workspace.toml` or inline `[workspace]` section in `config/core.toml`
  - Source discovery: scan nested sub-directories for repos with `.git` or `AGENTS.md` marker, infer roles (artifacts/codebase/kits/full)
  - Workspace config discovery: check the `core.toml` `workspace` key first (string path or inline dict), then fall back to `.studio-workspace.toml` at the project root
  - Context upgrade: `StudioContext` → `WorkspaceContext` with `SourceContext` per source
  - Cross-repo artifact path resolution: `resolve_artifact_path` returns `Optional[Path]`, `None` when source is explicitly set but unreachable
  - Traceability settings: `cross_repo` + `resolve_remote_ids` flags controlling remote ID expansion
  - CLI commands: `workspace-init`, `workspace-add` (with `--inline` flag for inline mode), `workspace-info`, `workspace-sync`
  - `--local-only` flag for validate to skip cross-repo resolution
  - `--source` filter for `list-ids`
  - Graceful degradation: unreachable sources emit warnings, operations continue with available sources
  - Scan warning logging: stderr warnings for individual artifact scan failures
  - Git URL sources in standalone workspace config: remote Git repository URLs with working directory configuration, namespace resolution rules (e.g., `gitlab.com/org/repo.git` → `org/repo`), and per-source branch/ref pinning (`cpt-studio-fr-core-workspace-git-sources`)
  - Cross-repo editing with remote adapter context: when editing files in a remote source, apply that source's own adapter rules/templates/constraints instead of the primary repo's adapter (`cpt-studio-fr-core-workspace-cross-repo-editing`)

- **Requirements Covered**:

  - [x] `p1` - `cpt-studio-fr-core-workspace`
  - [x] `p1` - `cpt-studio-fr-core-traceability`
  - [x] `p1` - `cpt-studio-fr-core-workspace-git-sources`
  - [x] `p1` - `cpt-studio-fr-core-workspace-cross-repo-editing`

- **Design Principles Covered**:

  - [x] `p1` - `cpt-studio-principle-traceability-by-design`
  - [x] `p1` - `cpt-studio-principle-determinism-first`
  - [x] `p1` - `cpt-studio-principle-zero-harm`

- **Design Constraints Covered**:

  - [x] `p1` - `cpt-studio-constraint-python-stdlib`

- **Domain Model Entities**:
  - WorkspaceConfig
  - SourceEntry
  - TraceabilityConfig
  - ResolveConfig
  - NamespaceRule
  - SourceContext
  - WorkspaceContext

- **Design Components**:

  - [x] `p1` - `cpt-studio-component-config-manager`
  - [x] `p1` - `cpt-studio-component-traceability-engine`

- **API**:
  - `cfs workspace-init [--root DIR] [--output PATH] [--inline] [--force] [--dry-run]`
  - `cfs workspace-add --name N (--path P | --url U) [--branch B] [--role R] [--adapter A] [--inline]`
  - `cfs workspace-info`
  - `cfs workspace-sync [--source NAME] [--dry-run]`
  - `cfs validate --local-only`
  - `cfs validate --source <name>`
  - `cfs list-ids --source <name>`

- **Sequences**:

  None (workspace setup is a configuration flow)

- **Out of scope**:
  - Cross-repo merge conflict resolution
  - Automatic workspace discovery across machines or CI environments
  - Authentication and credential management for Git URL sources

- **Data**:
  - `.studio-workspace.toml` — standalone workspace configuration
  - `config/core.toml` `[workspace]` section — inline workspace configuration
  - `config/artifacts.toml` `source` fields — per-artifact source references


### 2.13 [Subagent Registration](features/subagent-registration.md) ⏳ HIGH

- [x] `p1` - **ID**: `cpt-studio-feature-subagent-registration`

- **Purpose**: Allow Studio to register and generate subagent definitions that delegate specialized tasks to lightweight, tool-scoped agents.

- **Scope**:
  - Subagent definition format and registration
  - Subagent generation per agent tool
  - Model and tool scoping for subagents

- **Out of scope**:
  - Project-level subagent overrides (handled by Project-Level Extensibility)

- **Domain Model Entities**:
  - SubagentDefinition
  - SubagentConfig

- **API**:
  - `cfs generate-agents --agent <tool>`


### 2.14 [ralphex Delegation](features/ralphex-delegation.md) ⏳ HIGH

- [ ] `p1` - **ID**: `cpt-studio-feature-ralphex-delegation`

- **Purpose**: Provide a dedicated delegation skill that integrates Studio with ralphex for autonomous plan execution, while preserving Studio as the source of truth for SDLC guidance, decomposition, and validation contracts.

- **Depends On**: `cpt-studio-feature-execution-plans`, `cpt-studio-feature-version-config`

- **Scope**:
  - ralphex executable discovery on PATH and reuse of persisted absolute path
  - Diagnostics and availability validation before delegation
  - Optional project-local `.ralphex/` bootstrap via `ralphex --init`
  - Bounded plan export from canonical Studio plan outputs into `docs/plans/` in ralphex Markdown grammar
  - Optional derived `.ralphex/` overrides (prompts, agents) generated from Studio sources
  - Delegation modes: execute exported plan, review-only, worktree isolation, dashboard serving
  - Post-run handoff: status, output refs, validation continuity via Studio-supplied deterministic commands

- **Out of scope**:
  - Vendoring ralphex into the Studio Python package
  - Copying SDLC kit into `.ralphex/` as source of truth
  - Replacing generate/analyze/plan workflows
  - Replacing host-tool-native subagents

- **Requirements Covered**:

  - `p1` - `cpt-studio-fr-core-workflows`
  - `p1` - `cpt-studio-fr-core-execution-plans`
  - `p1` - `cpt-studio-fr-core-agents`

- **Design Principles Covered**:

  - `p1` - `cpt-studio-principle-determinism-first`
  - `p1` - `cpt-studio-principle-skill-documented`
  - `p1` - `cpt-studio-principle-occams-razor`

- **Design Constraints Covered**:

  - `p1` - `cpt-studio-constraint-markdown-contract`

- **Domain Model Entities**:
  - DelegationPlan
  - DelegationState

- **Design Components**:

  - `p1` - `cpt-studio-component-skill-engine` (delegation command routing)
  - `p1` - `cpt-studio-component-config-manager` (ralphex path persistence)

- **API**:
  `cfs delegate` — CLI command that routes delegation requests to the `cf-ralphex` skill handler for discovery, export, and execution

- **Sequences**:
  - `cpt-studio-seq-ralphex-delegation`

- **Data**:
  - `{plans_dir}/{task-slug}.md` — exported ralphex-compatible plans (path resolved from ralphex config, default `docs/plans/`)
  - `{plans_dir}/completed/` — completed plan lifecycle artifacts (managed by ralphex)
  - `.ralphex/` — optional derived overrides (prompts, agents, config)
  - `core.toml` `[integrations.ralphex]` — persisted executable path


### 2.15 [Project-Level Extensibility](features/project-extensibility.md) ⏳ HIGH

- [ ] `p1` - **ID**: `cpt-studio-feature-project-extensibility`

- **Purpose**: Extend `cfs generate-agents` with a four-layer manifest hierarchy (Core → Kit → Master Repo → Repo), enabling projects and orchestrator repos to declare skills, agents, workflows, and rules via `manifest.toml`. Adds `includes` directive for subdirectory manifests, `[[skills]]` generation, extended agent schema (tools, color, memory_dir, model passthrough), section appending for template composition, provenance traceability, and fully deterministic assembly pipeline.

- **Depends On**: `cpt-studio-feature-agent-integration`, `cpt-studio-feature-blueprint-system`, `cpt-studio-feature-subagent-registration`

- **Scope**:
  - Manifest v2.0 schema: `[[agents]]`, `[[skills]]`, `[[workflows]]`, `[[rules]]` component sections (`[[hooks]]` and `[[permissions]]` are reserved in the schema but deferred to a follow-up feature and are not in scope here)
  - `includes` directive for subdirectory manifests (same-layer, max depth 3, circular detection)
  - Four-layer walk-up discovery: Core → Kit → Master Repo → Repo (Organization and Project layers deferred)
  - Inner-scope-wins merge semantics across all layers
  - Extended agent schema: `tools`, `disallowed_tools`, `color`, `memory_dir`, model passthrough
  - Cross-agent translation including OpenAI Codex (`sandbox_mode`, `developer_instructions`)
  - `[[skills]]` generation code path (coexists with kit-composed skills)
  - Section appending for template composition (full block-based composition deferred)
  - Layer variable resolution: `{base_dir}`, `{master_repo}`, `{repo}`
  - Provenance traceability: `--show-layers` flag showing per-component winning layer and overridden layers
  - Deterministic pipeline: zero LLM calls, byte-identical output for same inputs
  - Component auto-discovery: `--discover` flag scans conventional directories
  - Backward compatibility: v1 manifests and `agents.toml` fallback

- **Out of scope**:
  - Master repo bootstrapping and structure conventions (orchestrator-specific)
  - Kit-specific component definitions (owned by individual kits)

- **Requirements Covered**:

  - `p1` - `cpt-studio-fr-core-agents`
  - `p1` - `cpt-studio-fr-core-kits`
  - `p1` - `cpt-studio-fr-core-kit-manifest`

- **Design Principles Covered**:

  - `p1` - `cpt-studio-principle-plugin-extensibility`
  - `p1` - `cpt-studio-principle-kit-centric`
  - `p1` - `cpt-studio-principle-dry`
  - `p1` - `cpt-studio-principle-determinism-first`

- **Design Constraints Covered**:

  - `p1` - `cpt-studio-constraint-python-stdlib`
  - `p1` - `cpt-studio-constraint-cross-platform`

- **Domain Model Entities**:
  - Manifest
  - ManifestLayer
  - MergedComponents
  - ProvenanceReport

- **Design Components**:

  - `p1` - `cpt-studio-component-agent-generator`
  - `p1` - `cpt-studio-component-kit-manager`

- **API**:
  - `cfs generate-agents --agent <agent> [--discover] [--show-layers]`

- **Sequences**:

  None (extends existing `cpt-studio-seq-generate-workflow`)

- **Data**:
  - `manifest.toml` at each layer (kit, master repo, org, project, repo)
  - Layer path variables in resolved variable dict


### 2.16 [Dependency Mapping](features/dependency-mapping.md) 🔶 HIGH

- [x] `p1` - **ID**: `cpt-studio-feature-dependency-mapping`

- **Purpose**: Visualize the full project architecture graph — markdown specs, source files, cfs traceability edges, and markdown hyperlinks — as an interactive HTML viewer or canonical JSON, enabling reverse-engineering workflows and phantom-ID detection.

- **Depends On**: `cpt-studio-feature-traceability-validation`, `cpt-studio-feature-workspace`

- **Scope**:
  - Markdown and source file scanning with cpt-ID extraction
  - `cpt-impl` edge construction (source marker → markdown definition)
  - `cpt-doc` edge construction (markdown reference → markdown definition)
  - `file-link` edge construction (markdown hyperlink → markdown)
  - Phantom cpt-ID detection: IDs used but never defined become `phantom-cpt` nodes
  - Three-step category resolution: override (`md-map.toml`) → artifacts.toml registry prefix → parent directory
  - Per-edge content enrichment via `get_content_scoped` for tooltip display
  - Rectpack-based category layout (16:9 target aspect, affinity-ordered placement)
  - JSON canonical output (nodes, edges, dangling_cpt_uses, categories, layout)
  - Self-contained HTML viewer with vis-network, viewer JS/CSS, inline or sidecar data
  - Workspace federation support (multi-source scanning)

- **Out of scope**:
  - Artifact structural validation (Feature 3)
  - Modifying source files or artifacts (read-only)
  - Persistent storage of map data

- **Requirements Covered**:

  - [x] `p1` - `cpt-studio-fr-core-dependency-mapping`
  - [x] `p1` - `cpt-studio-fr-core-traceability`

- **Design Principles Covered**:

  - [x] `p1` - `cpt-studio-principle-determinism-first`
  - [x] `p1` - `cpt-studio-principle-traceability-by-design`
  - [x] `p1` - `cpt-studio-principle-zero-harm`

- **Design Constraints Covered**:

  - [x] `p1` - `cpt-studio-constraint-python-stdlib`

- **Domain Model Entities**:
  - Node (markdown, source, phantom-cpt)
  - Edge (cpt-impl, cpt-doc, file-link)
  - Ref
  - CptUse
  - ScanOptions
  - CategorizeOptions
  - OverrideConfig
  - RenderJsonInput
  - RenderHtmlInput

- **Design Components**:

  - [x] `p1` - `cpt-studio-component-map-renderer`
  - [x] `p1` - `cpt-studio-component-traceability-engine`

- **API**:
  - `cfs map [--out PATH] [--format html|json] [--config FILE] [--no-source] [--local-only] [--inline-data] [--verbose]`

- **Sequences**:

  None (single-command flow)

- **Data**:
  - `md-map.html` (default output) — self-contained HTML viewer
  - `md-map.html.js` (optional sidecar) — JSON data payload
  - `md-map.toml` (optional override config) — category path overrides and styles
  - `artifacts.toml` — read-only: codebase entries and artifact paths for registry categorization


---

## 3. Feature Dependencies

```text
cpt-studio-feature-core-infra
    ↓
    ├─→ cpt-studio-feature-blueprint-system (Kit Management)
    │
    ├─→ cpt-studio-feature-agent-integration ─┬─→ cpt-studio-feature-execution-plans
    │                                          │    ↓
    │                                          │    └─→ cpt-studio-feature-ralphex-delegation ←── cpt-studio-feature-version-config
    │                                          │
    │                                          ├─→ cpt-studio-feature-subagent-registration
    │                                          │
    │                                          ↓
    │   cpt-studio-feature-project-extensibility ←── cpt-studio-feature-blueprint-system
    │
    ├─→ cpt-studio-feature-version-config
    │
    ├─→ cpt-studio-feature-traceability-validation
    │    ↓
    │    ├─→ cpt-studio-feature-developer-experience
    │    │
    │    └─→ cpt-studio-feature-spec-coverage
    │
    ├─→ cpt-studio-feature-workspace ←── cpt-studio-feature-traceability-validation
    │
    └─→ cpt-studio-feature-dependency-mapping ←── cpt-studio-feature-traceability-validation
                                                ←── cpt-studio-feature-workspace

    (EXTRACTED to constructorfabric/studio-kit-sdlc:)
    cpt-studio-feature-sdlc-kit
    cpt-studio-feature-pr-workflows
    cpt-studio-feature-advanced-sdlc
```

**Dependency Rationale**:

- `cpt-studio-feature-traceability-validation` requires `cpt-studio-feature-core-infra`: validator needs config manager for system/artifact resolution
- `cpt-studio-feature-agent-integration` requires `cpt-studio-feature-core-infra`: agent generator consumes kit SKILL.md and workflow files
- `cpt-studio-feature-execution-plans` requires `cpt-studio-feature-agent-integration`: plan workflow builds on existing generate/analyze workflows and agent entry points
- `cpt-studio-feature-version-config` requires `cpt-studio-feature-core-infra`: update command needs config migration
- `cpt-studio-feature-developer-experience` requires `cpt-studio-feature-traceability-validation`: VS Code plugin and doctor delegate to validator and traceability engine
- `cpt-studio-feature-workspace` requires `cpt-studio-feature-core-infra` and `cpt-studio-feature-traceability-validation`: workspace federation builds on core context loading and extends cross-repo ID resolution in the traceability engine
- `cpt-studio-feature-ralphex-delegation` requires `cpt-studio-feature-execution-plans` and `cpt-studio-feature-version-config`: delegation compiles exported plans from Studio's authoritative decomposition model and persists ralphex integration settings via the config manager
- SDLC-specific features (F4, F6, F9) have been extracted to `constructorfabric/studio-kit-sdlc` per `cpt-studio-adr-extract-sdlc-kit`
