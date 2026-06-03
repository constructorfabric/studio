---
cf: true
type: project-rule
topic: domain-model
generated-by: auto-config
version: 1.0
---

# Domain Model


<!-- toc -->

- [Core Concepts](#core-concepts)
  - [Constructor Studio Framework](#constructor-studio-framework)
  - [Kit](#kit)
  - [Adapter](#adapter)
  - [Artifact](#artifact)
  - [Constructor Studio ID](#constructor-studio-id)
  - [Constructor Studio Marker](#constructor-studio-marker)
  - [Traceability Levels](#traceability-levels)
- [System Hierarchy](#system-hierarchy)
- [Key Data Structures](#key-data-structures)
- [CLI Commands](#cli-commands)

<!-- /toc -->

## Core Concepts

### Constructor Studio Framework
Constructor Studio is a workflow-centered methodology framework for AI-assisted software development with design-to-code traceability.

### Kit
A **kit** is a direct file package with templates, rules, checklists, examples, and workflows. Installed to `config/kits/{kit-id}/`.

### Adapter
A **project-specific configuration** in `{cf-studio-path}/config/`: `AGENTS.md`, `artifacts.toml`, `rules/*.md`, `core.toml`.

### Artifact
A **design document** (PRD, DESIGN, DECOMPOSITION, FEATURE, ADR) with a `kind`, `path`, and `traceability` level (`FULL` or `DOCS-ONLY`).

### Constructor Studio ID
Format: `cpt-{hierarchy-prefix}-{kind}-{slug}`, e.g. `cpt-studio-fr-must-authenticate`.

### Constructor Studio Marker
- Scope: `@cpt-{kind}:{cpt-id}:p{N}`
- Block: `@cpt-begin:{cpt-id}:p{N}:inst-{local}` / `@cpt-end:{cpt-id}:p{N}:inst-{local}`

### Traceability Levels
- **FULL** — code markers allowed and validated
- **DOCS-ONLY** — documentation traceability only, no code markers

## System Hierarchy

```
artifacts.toml
└── systems[]
    ├── name / slug / kit
    ├── artifacts[]  — {path, kind, traceability}
    ├── codebase[]   — {path, extensions, comments}
    └── children[]   (nested subsystems)
```

## Key Data Structures

| Type | Purpose |
|------|---------|
| `ArtifactsMeta` | Parses `artifacts.toml`; exposes `get_kit()`, `iter_all_artifacts()`, `iter_all_codebase()` |
| `StudioContext` | Global CLI context: `adapter_dir`, `project_root`, `meta`, `kits`, `registered_systems` |
| `Template` | Parsed artifact template: `kind`, `version`, `blocks` |
| `CodeFile` | Parsed source file with cpt markers: `path`, `references`, `scope_markers` |

## CLI Commands

| Group | Commands |
|-------|----------|
| Setup | `init`, `update`, `info`, `resolve-vars`, `agents`, `generate-agents` |
| Validation | `validate`, `validate-kits`, `validate-toc`, `spec-coverage`, `check-language` |
| Search | `list-ids`, `list-id-kinds`, `get-content`, `where-defined`, `where-used` |
| Kit | `kit install`, `kit update` |
| Utility | `toc`, `chunk-input`, `pdsl` |
| Workspace | `workspace-init`, `workspace-add`, `workspace-info`, `workspace-sync` |
| Delegation | `delegate` |
| Diagnostics | `doctor` |
| Visualization | `map` |
