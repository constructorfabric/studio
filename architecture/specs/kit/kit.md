---
studio: true
type: spec
name: Kit Specification
version: 1.0
purpose: Define kit structure, installation, update model, directory layout, generated output overview, taxonomy, and extension protocol
drivers:
  - cpt-studio-fr-core-kits
  - cpt-studio-fr-sdlc-plugin
---

# Kit Specification


<!-- toc -->

- [Kit Overview](#kit-overview)
- [Kit Directory Structure](#kit-directory-structure)
- [Kit File Reference](#kit-file-reference)
- [Project-Level Outputs](#project-level-outputs)
  - [taxonomy.md](#taxonomymd)
- [Kit Extension Protocol (p2)](#kit-extension-protocol-p2)
- [Related Specifications](#related-specifications)

<!-- /toc -->

---
---

## Kit Overview

A **Kit** is a file package that provides domain-specific artifact and codebase definitions for Studio. Each kit contains ready-to-use files — rules, templates, checklists, examples, constraints, workflows, and skill extensions — maintained directly by kit authors.

**What a kit provides** (installed into `{cf-studio-path}/config/kits/<slug>/` or
registered in place via manifest-driven install modes):
- Per-artifact files: `artifacts/<KIND>/` containing `template.md`, `rules.md`, `checklist.md`, `examples/example.md`
- Codebase files: `codebase/` containing `rules.md`, `checklist.md`
- Kit-wide: `constraints.toml` (structural validation rules), `conf.toml` (version metadata)
- Workflow files: `workflows/{name}.md`
- SKILL.md — kit skill extensions for AI agent discoverability
- Scripts: `scripts/` — kit-specific scripts and prompts
- Optional canonical `.cf-studio-kit.toml` — declarative installation manifest
- Optional legacy `manifest.toml` — compatibility input normalized into the
  canonical manifest model

**Key properties**:
- Kit registration (slug, version, config path, resolved resource bindings) is stored in `{cf-studio-path}/config/core.toml`; persisted resource binding paths are always project-relative (never absolute), and register-mode kits re-derive effective resource locations from the manifest at runtime instead of relying on persisted path anchors
- Tracked kit files are user-editable after installation
- Ignored kit files remain overwriteable generated surfaces
- User modifications to tracked kit files are preserved across kit updates via
  file-level diff with interactive prompts
- Kit version is stored in `{cf-studio-path}/config/kits/<slug>/conf.toml`

> **Plugin system** (CLI subcommands, validation hooks, generation hooks) is planned for p2 and not covered in this specification.
>
> **Legacy**: The previous blueprint-based kit model (where kit files were generated from `@cpt:` marker files) has been removed per `cpt-studio-adr-remove-blueprint-system`. See [blueprint.md](blueprint.md) for legacy reference only.

---

## Kit Directory Structure

When a kit is installed, all files are copied to `{cf-studio-path}/config/kits/{slug}/` where users can edit them:

```
{cf-studio-path}/config/kits/<slug>/
├── .cf-studio-kit.toml            # (optional) Canonical declarative installation manifest
├── manifest.toml                  # (optional) Legacy compatibility manifest
├── conf.toml                      # Kit version metadata (slug, version, name)
├── SKILL.md                       # Per-kit skill instructions (user-editable)
├── constraints.toml               # Kit-wide structural constraints (user-editable)
├── artifacts/                     # Per-artifact files
│   ├── PRD/
│   │   ├── template.md            # Heading structure for artifact creation
│   │   ├── rules.md               # Agent rules for generate/analyze workflows
│   │   ├── checklist.md           # Quality checklist
│   │   └── examples/example.md    # Concrete example artifact
│   ├── DESIGN/
│   │   └── ...
│   └── .../
├── codebase/                      # Codebase review files
│   ├── rules.md                   # Codebase agent rules
│   └── checklist.md               # Codebase quality checklist
├── scripts/                       # Kit-specific scripts and prompts
│   └── ...
└── workflows/                     # Workflow definitions
    ├── pr-review.md
    ├── pr-status.md
    └── ...
```

Top-level `.gen/` retains only aggregate files: `AGENTS.md`, `SKILL.md`, `README.md`.

**Flow**:
1. `cfs init` / `cfs kit install` installs kit files from source:
   - **If canonical `.cf-studio-kit.toml` or legacy `manifest.toml` is present**: normalize to the manifest model, validate resources, prompt for `user_modifiable` destinations when required, copy or register each resource at its effective path, preserve `{identifier}` template variables in installed files, and record effective install state in `core.toml` (`[kits.{slug}.resources]` only for non-register installs)
   - **If no `manifest.toml`**: copy all kit files from source to `{cf-studio-path}/config/kits/{slug}/` (legacy behavior)
   - Register kit in `core.toml`
2. Regenerate `.gen/AGENTS.md` to include public kit rules; generate skill/workflow entrypoints through agent integration files
3. Users may freely edit any kit file at any time
4. On kit update, the system compares new files against user's installed copies via file-level diff (using registered resource paths for manifest-driven kits), then regenerates `.gen/` aggregate files. New resources in the updated manifest trigger a path prompt; removed resources produce a warning

**Update modes**:

| Mode | Command | Behavior |
|------|---------|----------|
| **Force** | `cfs kit update --force` | Overwrites all kit files in `{cf-studio-path}/config/kits/{slug}/`. User edits are discarded. |
| **Interactive** (default) | `cfs kit update` | File-level diff: for each file, compare new version against user's installed copy. **IF** identical → no action. **IF** different → present unified diff with `[a]ccept / [d]ecline / [A]ccept all / [D]ecline all / [m]odify` prompts. Files accepted by the user are counted as fully updated; declined files keep the kit in a partial-update outcome instead of being counted as fully updated. |

**Interactive partial outcome semantics**:
- When a user accepts some changes and declines others, the command reports a partial outcome rather than inflating `kits_updated`.
- Machine-readable output distinguishes full and partial success via separate counters such as `kits_updated` and `kits_partially_updated`.
- Interactive partial updates are user-confirmed outcomes, not write failures; the command surfaces the partial status explicitly so callers can distinguish it from a clean full update.

**Canonical public-component semantics**:

- Canonical manifests may declare `public = true` resources.
- Public resources may declare `generated_targets = [...]` to constrain which
  agent hosts receive generated outputs.
- Public agent resources may declare nested `subagents`.
- `generate-agents` consumes these public resources to produce shared
  `.agents/skills/*`, host-native proxies, and supported subagent outputs.
- Unsupported host capabilities are surfaced as partial/skip metadata rather
  than silently dropped.

**Check-updates semantics**:
- `cfs kit check-updates` succeeds only when every inspected kit source check succeeds.
- If at least one kit cannot be checked because its source is invalid, unreachable, or otherwise errors, the command returns a failing result and non-zero exit even if other kits were checked successfully.

---

## Kit File Reference

Each kit file is authored directly by kit authors and user-editable after installation.

| File | Location | Purpose | Spec |
|------|----------|---------|------|
| `rules.md` | `artifacts/<KIND>/` | Agent rules for generate/analyze workflows | [rules.md](rules.md) |
| `checklist.md` | `artifacts/<KIND>/` | Quality checklist for validation | [checklist.md](checklist.md) |
| `template.md` | `artifacts/<KIND>/` | Heading structure for artifact creation | [template.md](template.md) |
| `example.md` | `artifacts/<KIND>/examples/` | Concrete example artifact | [example.md](example.md) |
| `constraints.toml` | kit root | Kit-wide structural validation rules | [constraints.md](constraints.md) |
| codebase `rules.md` | `codebase/` | Codebase agent rules | [rules.md](rules.md) |
| codebase `checklist.md` | `codebase/` | Codebase quality checklist | [checklist.md](checklist.md) |
| `workflows/{name}.md` | `workflows/` | Workflow definitions | — |
| `SKILL.md` | kit root | Kit skill extensions | — |
| `conf.toml` | kit root | Kit version metadata | — |
| `.cf-studio-kit.toml` | kit root (optional) | Canonical declarative installation manifest: resource identifiers, install paths, types, public generation settings, and user-modifiability flags | [kit.md](#kit-overview) |
| `manifest.toml` | kit root (optional) | Legacy compatibility manifest normalized into the canonical model | [kit.md](#kit-overview) |

---

## Project-Level Outputs

### taxonomy.md

`taxonomy.md` is an optional kit-level document that aggregates information about the kit's artifact kinds into a single human-readable reference.

**Location**: `{cf-studio-path}/config/kits/{slug}/taxonomy.md`

This file is authored directly by kit authors as part of the kit file package.

---

## Kit Extension Protocol (p2)

> **p2**: The plugin system (CLI subcommands, validation hooks) is planned for a future phase. The following documents the target design for reference.

Kit authors extend Studio by adding files to the standard kit directories:
- New artifact kinds: add a new `artifacts/<KIND>/` directory with `rules.md`, `template.md`, `checklist.md`, `examples/example.md`
- New workflows: add `.md` files to `workflows/`
- New scripts: add files to `scripts/`
- SKILL extensions: edit `SKILL.md` to add kit-specific commands and workflows
- Constraint rules: edit `constraints.toml` to define structural validation rules

---

## Related Specifications

| Spec | Description |
|------|-------------|
| [blueprint.md](blueprint.md) | **DEPRECATED** — Legacy blueprint format reference |
| [rules.md](rules.md) | `rules.md` format, structure, loading, and usage |
| [checklist.md](checklist.md) | `checklist.md` format, domain organization, check items |
| [template.md](template.md) | `template.md` format, heading structure, placeholders |
| [constraints.md](constraints.md) | `constraints.toml` format, validation semantics, cross-artifact rules |
| [example.md](example.md) | `example.md` format, derivation from examples |
