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
  - [Constructor Studio Framework](#cypilot-framework)
  - [Kit](#kit)
  - [Adapter](#adapter)
  - [Artifact](#artifact)
  - [Constructor Studio ID](#cypilot-id)
  - [Constructor Studio Marker](#cypilot-marker)
  - [Traceability Levels](#traceability-levels)
- [System Hierarchy](#system-hierarchy)
- [Key Data Structures](#key-data-structures)
  - [ArtifactsMeta](#artifactsmeta)
  - [Constructor StudioContext](#cypilotcontext)
  - [Template](#template)
  - [CodeFile](#codefile)
- [Workflows](#workflows)
  - [generate.md](#generatemd)
  - [analyze.md](#analyzemd)
- [CLI Commands](#cli-commands)

<!-- /toc -->

## Core Concepts

### Constructor Studio Framework
Constructor Studio is a workflow-centered methodology framework for AI-assisted software development with design-to-code traceability.

### Kit
A **kit** is a direct file package containing templates, rules, checklists, examples, and workflows for artifact validation. Installed to `config/kits/{kit-id}/`.

```
config/kits/sdlc/
├── conf.toml             # Kit version metadata
├── constraints.toml      # Validation constraints
├── SKILL.md              # Kit skill entry point
├── AGENTS.md             # Kit navigation rules
├── artifacts/
│   ├── PRD/              # Product Requirements Document
│   ├── DESIGN/           # Technical Design
│   ├── DECOMPOSITION/    # Decomposition Manifest
│   ├── FEATURE/          # Feature Design
│   └── ADR/              # Architecture Decision Record
├── codebase/
│   ├── rules.md
│   └── checklist.md
├── workflows/            # Kit-specific workflows
└── scripts/              # Kit scripts
```

### Adapter
A **project-specific configuration** in `cypilot/config/` that configures Constructor Studio for a project:
- `AGENTS.md` - Custom navigation rules (WHEN clauses)
- `artifacts.toml` - Registry of systems, artifacts, codebase
- `rules/*.md` - Project-specific rules (per-topic)
- `core.toml` - Project settings (system name, kit references)

### Artifact
A **design document** tracked by Constructor Studio (PRD, DESIGN, DECOMPOSITION, FEATURE, ADR). Each artifact:
- Has a `kind` matching a kit template
- Has a `path` in the project
- Has `traceability` level (FULL or DOCS-ONLY)

### Constructor Studio ID
A **unique identifier** in format `cpt-{hierarchy-prefix}-{kind}-{slug}`:
- `cpt-cypilot-fr-must-authenticate` - Functional requirement
- `cpt-cypilot-core-comp-api-gateway` - Component definition
- `cpt-cypilot-core-auth-flow-login` - Flow definition

### Constructor Studio Marker
**Code traceability markers** linking code to design:
- `@cpt-{kind}:{cpt-id}:p{N}` - Scope marker
- `@cpt-begin:{cpt-id}:p{N}:inst-{local}` / `@cpt-end:{cpt-id}:p{N}:inst-{local}` - Block markers

### Traceability Levels
- **FULL** - Code markers are allowed and validated
- **DOCS-ONLY** - Documentation traceability only, no code markers

## System Hierarchy

```
artifacts.toml
└── systems[]
    ├── name: "Constructor Studio"
    ├── kit: "sdlc"
    ├── artifacts[]
    │   └── {path, kind, traceability}
    ├── codebase[]
    │   └── {path, extensions, comments}
    └── children[]  (nested subsystems)
```

## Key Data Structures

### ArtifactsMeta
Parses `artifacts.toml` and provides lookups:
- `get_kit(id)` → Kit
- `get_artifact_by_path(path)` → (Artifact, SystemNode)
- `iter_all_artifacts()` → Iterator
- `iter_all_codebase()` → Iterator

### Constructor StudioContext
Global context loaded at CLI startup:
- `adapter_dir` - Path to adapter
- `project_root` - Path to project root
- `meta` - ArtifactsMeta instance
- `kits` - Dict of LoadedKit (templates loaded)
- `registered_systems` - Set of system names

### Template
Parsed template from `template.md`:
- `kind` - Artifact kind (PRD, DESIGN, etc.)
- `version` - Template version (major.minor)
- `blocks` - List of TemplateBlock markers

### CodeFile
Parsed source file with Constructor Studio markers:
- `path` - File path
- `references` - List of CodeReference
- `scope_markers` - List of ScopeMarker

## Workflows

### generate.md
Creates/updates artifacts following template rules.

### analyze.md
Validates artifacts against templates and traceability rules.

## CLI Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize Constructor Studio config and adapter |
| `info` | Show adapter discovery information |
| `validate` | Validate artifacts and code (structure, cross-refs, traceability) |
| `validate-kits` | Validate kit templates and blueprint integrity |
| `validate-toc` | Validate Table of Contents in Markdown files |
| `self-check` | Validate kit examples against their templates |
| `spec-coverage` | Measure CDSL marker coverage in codebase |
| `list-ids` | Scan and list all Constructor Studio IDs |
| `list-id-kinds` | List ID kinds with counts and template mappings |
| `get-content` | Retrieve content block for a specific Constructor Studio ID |
| `where-defined` | Find where an ID is defined |
| `where-used` | Find all references to an ID |
| `toc` | Generate/update Table of Contents in Markdown files |
| `kit install` | Install a kit from source directory |
| `kit update` | Update kit files with file-level diff |
| `agents` | Generate agent-specific workflow proxies (windsurf, cursor, claude, copilot, openai) |
| `update` | Update `.core/` from cache, update kits, regenerate `.gen/` |
| `migrate` | Migrate Constructor Studio v2 project to v3 layout |
| `migrate-config` | Convert legacy JSON config to TOML |
