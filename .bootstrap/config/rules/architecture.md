---
cf: true
type: project-rule
topic: architecture
generated-by: auto-config
version: 1.0
---

# Architecture


<!-- toc -->

- [Source Layout](#source-layout)
- [Two-Package Design](#two-package-design)
- [Runtime Context](#runtime-context)
- [Path Resolution](#path-resolution)
- [Registry and Config Authority](#registry-and-config-authority)
- [Architecture Patterns](#architecture-patterns)
  - [Command Router + Thin Proxy](#command-router--thin-proxy)
  - [Workflow-Driven AI Layer](#workflow-driven-ai-layer)
  - [Kit Package Model](#kit-package-model)
- [Critical Files](#critical-files)

<!-- /toc -->

System design, module boundaries, and key abstractions of the self-hosted Constructor Studio project.

## Source Layout

```
src/studio_proxy/                  # Global proxy package
  cli.py                            # Console entry: resolve skill, forward command
  resolve.py                        # Project-vs-cache skill resolution
  cache.py                          # Cache download/copy logic

skills/studio/scripts/studio/      # Studio engine package
  cli.py                            # Main command router
  commands/                         # Command modules
  utils/                            # Shared utility modules

.bootstrap/                        # Self-hosted adapter directory
  .core/                            # Read-only mirror of canonical sources
  .gen/                             # Generated aggregates
  config/                           # User-editable config + auto-config outputs

tests/                              # 44 pytest modules + shared conftest/bootstrap
```

## Two-Package Design

The installed `cfs` / `constructor-studio` entry points load the proxy in `src/studio_proxy/`. The proxy discovers the active Studio engine (project-local or cached) and forwards the command through `subprocess.run`. All deterministic validation, registry loading, kit management, and workflow support live in `skills/studio/scripts/studio/`.

The repository is also self-hosted: `.bootstrap/` is a live adapter/config tree for this same project, while the canonical editable sources remain under the repo root.

## Runtime Context

`StudioContext.load()` runs at CLI startup in the Studio engine, reads `artifacts.toml`, resolves kits and constraints, and stores the loaded context for command handlers. Workspace upgrades are deferred until first access, so lightweight commands do not pay unnecessary startup cost.

## Path Resolution

Two cooperating path-resolution layers exist:

- **Proxy layer**: `src/studio_proxy/resolve.py` walks upward for root `AGENTS.md`, reads the managed TOML block, and resolves `cf-studio-path`
- **Studio layer**: `skills/studio/scripts/studio/utils/files.py` resolves project root, adapter root, and `.core` / `.gen` subpaths inside the active adapter

This separation keeps the globally installed proxy small while letting the skill engine own project-layout semantics.

## Registry and Config Authority

`core.toml` stores adapter-level project settings and installed kit registrations. `artifacts.toml` is the authoritative registry for systems, autodetect rules, artifacts, and codebase roots. For this self-hosted repo, `.bootstrap/config/` is the live user-editable config surface; `.bootstrap/.core/` and `.bootstrap/.gen/` are derived outputs.

## Architecture Patterns

### Command Router + Thin Proxy
The proxy performs cache/project resolution only. The skill engine CLI uses lazy imports so each command loads only the handler modules it needs.

### Workflow-Driven AI Layer
AI-facing behavior is defined in Markdown skills, workflows, and requirements. Python provides deterministic primitives; workflows orchestrate how agents read and apply them.

### Kit Package Model
Kits provide templates, rules, checklists, workflows, scripts, and constraints as ready files. Installed kit content lives under `config/kits/{slug}/`, while the registry and resolved variables expose those resources to workflows and commands.

## Critical Files

| File | Why it matters |
|------|---------------|
| `skills/studio/scripts/studio/cli.py` | Command dispatch hub — touch when adding or renaming commands |
| `skills/studio/scripts/studio/utils/context.py` | Loads runtime context used by nearly every command |
| `skills/studio/scripts/studio/utils/files.py` | Resolves project root, adapter root, and layout helpers |
| `skills/studio/scripts/studio/utils/artifacts_meta.py` | Parses and normalizes the artifacts registry |
| `skills/studio/scripts/studio/commands/init.py` | Initializes or force-reinitializes adapter/config state |
| `skills/studio/scripts/studio/commands/update.py` | Refreshes `.core`, `.gen`, and installed kit outputs |
| `src/studio_proxy/resolve.py` | Determines whether commands use project or cached skill |
| `src/studio_proxy/cache.py` | Owns GitHub/local cache population semantics |
| `.bootstrap/config/artifacts.toml` | Source of truth for systems, artifacts, codebases |
| `tests/conftest.py` | sys.path setup — must include all source roots |
