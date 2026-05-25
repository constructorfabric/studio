---
status: accepted
date: 2026-03-07
decision-makers: project maintainer
---

# ADR-0013: Extract SDLC Kit to Separate GitHub Repository

**ID**: `cpt-studio-adr-extract-sdlc-kit`

<!-- toc -->

- [Context and Problem Statement](#context-and-problem-statement)
- [Decision Drivers](#decision-drivers)
- [Considered Options](#considered-options)
- [Decision Outcome](#decision-outcome)
  - [Consequences](#consequences)
  - [Confirmation](#confirmation)
- [Pros and Cons of the Options](#pros-and-cons-of-the-options)
  - [Option 1: Keep SDLC Kit Bundled](#option-1-keep-sdlc-kit-bundled)
  - [Option 2: Extract Kit to GitHub Repo with GitHub Releases Versioning](#option-2-extract-kit-to-github-repo-with-github-releases-versioning)
  - [Option 3: Extract Kit to Separate Package Registry](#option-3-extract-kit-to-separate-package-registry)
- [More Information](#more-information)
  - [Changes to Studio Core](#changes-to-studio-core)
  - [Migration Plan (versions < 3.0.8 → GitHub v1.0.0)](#migration-plan-versions--308--github-v100)
  - [`core.toml` Kit Section (new format)](#coretoml-kit-section-new-format)
  - [`cfs init` Kit Prompt](#cfs-init-kit-prompt)
- [Traceability](#traceability)

<!-- /toc -->

## Context and Problem Statement

The SDLC kit (`kits/sdlc/`) is currently bundled inside the Studio tool repository (`constructorfabric/studio`). This creates tight coupling between the tool and its primary content package: every kit content change (template update, checklist refinement, new artifact kind) requires a Studio release, the `cfs update` command must handle both tool updates and kit updates in the same pipeline, and users cannot install or update the kit independently of the tool.

The SDLC kit is a domain-specific content package — Markdown templates, checklists, rules, examples, TOML constraints, and workflow files. It has no code dependency on the Studio core; it is purely a file package consumed by the core's generic kit infrastructure. The current architecture already treats kits as pluggable file packages (per `cpt-studio-adr-remove-blueprint-system`), but the bundling contradicts this design by shipping the only kit inside the tool itself.

The question is: should the SDLC kit live in a separate repository with its own versioning, or remain bundled with the tool?

## Decision Drivers

* **Independent versioning** — kit content (templates, checklists, rules) evolves at a different cadence than the tool (CLI, validator, traceability engine); bundling forces synchronized releases for unrelated changes
* **Clean separation of concerns** — Studio core is a Python CLI tool; the SDLC kit is a content package of Markdown and TOML files; mixing them in one repository conflates tool development with content authoring
* **GitHub-native distribution** — GitHub releases provide versioning (tags), changelogs, and download URLs without requiring custom infrastructure or package registries
* **Reduced tool complexity** — `cfs update` currently handles both tool skill updates and kit file-level diff updates in a single pipeline; extracting the kit removes kit update logic from the core update command
* **Ecosystem enablement** — when the primary bundled kit uses the same installation mechanism as third-party kits, the ecosystem model is proven by the first kit itself
* **No bundled kits** — the tool should be a generic engine with zero domain-specific content; all domain value comes from independently installable kits

## Considered Options

1. **Keep SDLC Kit Bundled** — retain the kit inside the Studio repository, ship kit files as part of the tool
2. **Extract Kit to GitHub Repo with GitHub Releases Versioning** — move the kit to `constructorfabric/studio-kit-sdlc`, install via `cfs kit install`, version via GitHub tags/releases, store source and version in `core.toml`
3. **Extract Kit to Separate Package Registry (PyPI/npm)** — publish the kit as a package on a package registry

## Decision Outcome

Chosen option: **Option 2 — Extract Kit to GitHub Repo with GitHub Releases Versioning**, because the kit is a file package (not executable code) and GitHub releases provide natural versioning, changelogs, and download infrastructure without additional dependencies. This aligns with the existing architecture where kits are file packages and the tool is a generic engine.

### Consequences

* Good, because the tool becomes a pure generic engine with zero domain-specific content — all domain value is delivered by independently installable kits
* Good, because kit content can be versioned, released, and changelog'd independently of the tool
* Good, because `cfs update` simplifies to tool-only updates — no kit file-level diff logic in the update pipeline
* Good, because the SDLC kit proves the third-party kit installation model — if the primary kit installs from GitHub, any kit can
* Good, because `core.toml` kit section gains `source` and `version` fields, providing a clear audit trail of where each kit came from
* Neutral, because `cfs init` prompts the user to install the SDLC kit inline (`[a]ccept / [d]ecline`) — no separate command needed unless the user declines
* Bad, because kit installation now requires network access to GitHub (mitigated by supporting `--source <local-path>` for offline installation)
* Neutral, because the migration from bundled versions (< 3.0.8) to GitHub version v1.0.0 is a one-time operation handled automatically during `cfs update`

### Confirmation

Confirmed when:

- `kits/sdlc/` directory is removed from the Studio repository
- `constructorfabric/studio-kit-sdlc` repository contains the full SDLC kit with GitHub release v1.0.0
- `cfs kit install --github constructorfabric/studio-kit-sdlc` installs the kit from GitHub
- `core.toml` kit section stores `source = "github:constructorfabric/studio-kit-sdlc"` and `version = "v1.0.0"`
- `cfs update` no longer touches kit files — only updates the tool skill
- `cfs init` prompts to install the SDLC kit inline (`[a]ccept / [d]ecline`); if accepted, downloads and installs immediately
- Migration from versions < 3.0.8 automatically converts the bundled kit to GitHub source v1.0.0
- All SDLC-specific requirements, components, and features are removed from Studio's PRD, DESIGN, and DECOMPOSITION
- All architecture documents (PRD, DESIGN, DECOMPOSITION, feature specs) are updated to reflect the new model

## Pros and Cons of the Options

### Option 1: Keep SDLC Kit Bundled

Retain the kit inside the Studio repository. Kit files ship as part of the tool and are updated via `cfs update`.

* Good, because zero additional setup — kit is immediately available after `cfs init`
* Good, because no network dependency for kit installation
* Bad, because every kit content change requires a Studio release
* Bad, because `cfs update` must handle both tool and kit updates in a single pipeline
* Bad, because the bundling model contradicts the extensible kit architecture — the primary kit is privileged over third-party kits
* Bad, because Studio's PRD, DESIGN, and DECOMPOSITION must document SDLC-specific requirements alongside core requirements

> Note: Option 2 achieves the same zero-setup experience by prompting during `cfs init` with `[a]ccept / [d]ecline`, so the convenience advantage of Option 1 is negligible.

### Option 2: Extract Kit to GitHub Repo with GitHub Releases Versioning

Move the kit to `constructorfabric/studio-kit-sdlc`. Install via `cfs kit install`. Version via GitHub tags.

* Good, because maximum separation — tool repo contains zero domain-specific content
* Good, because GitHub releases provide versioning, changelogs, and download URLs natively
* Good, because `cfs update` simplifies to tool-only scope
* Good, because the ecosystem model is proven by the first kit
* Good, because `cfs init` prompts to install the kit inline — no extra step
* Bad, because requires network access to GitHub for kit installation

### Option 3: Extract Kit to Separate Package Registry

Publish the kit as a package on PyPI or npm.

* Good, because leverages established package infrastructure
* Good, because supports dependency resolution and version pinning
* Bad, because the kit is a file package, not executable code — package registries add unnecessary complexity
* Bad, because introduces a dependency on a third-party registry
* Bad, because kit installation would require pip/npm in addition to the Studio CLI

## More Information

### Changes to Studio Core

| Area | Before | After |
|------|--------|-------|
| `kits/sdlc/` | Bundled in repo | Removed — lives in `constructorfabric/studio-kit-sdlc` |
| `core.toml` kit section | `format`, `path`, `version` | Adds `source` field (e.g., `"github:constructorfabric/studio-kit-sdlc"`) |
| `cfs update` | Updates tool + kits | Updates tool only; recommends kit updates if available |
| `cfs init` | Installs bundled kits | Prompts `Install SDLC kit? [a]ccept [d]ecline`; downloads from GitHub if accepted |
| `cfs kit install` | From local/cache source only | Supports `--github <owner/repo>` for GitHub sources |
| PRD Section 5.2 | SDLC Kit requirements | Removed — SDLC requirements live in kit repo |
| DESIGN SDLC component | SDLC plugin component | Removed from component model |
| DECOMPOSITION Features 4, 6, 9 | SDLC-specific features | Removed or reduced to core-only scope |

### Migration Plan (versions < 3.0.8 → GitHub v1.0.0)

| Step | Description |
|------|-------------|
| 1 | During `cfs update`, detect bundled kit (no `source` field in `core.toml`) |
| 2 | Add `source = "github:constructorfabric/studio-kit-sdlc"` to kit section |
| 3 | Set `version = "v1.0.0"` (current kit content matches this version) |
| 4 | Kit files in `config/kits/sdlc/` remain unchanged — no file operations needed |
| 5 | Display message: "SDLC kit migrated to GitHub source. Future updates: `cfs kit update sdlc`" |

### `core.toml` Kit Section (new format)

```toml
[kits.sdlc]
source = "github:constructorfabric/studio-kit-sdlc"
path = "config/kits/sdlc"
version = "v1.0.0"
```

### `cfs init` Kit Prompt

During `cfs init`, after creating core configs, the tool prompts:

```
Install recommended SDLC kit (constructorfabric/studio-kit-sdlc)? [a]ccept [d]ecline: 
```

- **`[a]ccept`**: downloads the kit from GitHub, installs it into `config/kits/sdlc/`, registers in `core.toml`
- **`[d]ecline`**: skips kit installation; user can install later via `cfs kit install --github constructorfabric/studio-kit-sdlc`
- **Non-interactive mode** (`--no-prompt`): skips the prompt (no kit installed)

## Traceability

- **PRD**: [PRD.md](../PRD.md)
- **DESIGN**: [DESIGN.md](../DESIGN.md)

This decision directly addresses the following requirements and design elements:

* `cpt-studio-fr-core-kits` — Kit installation now supports GitHub as a source; kits are no longer bundled with the tool
* `cpt-studio-fr-core-version` — `update` command scope reduced to tool-only; kit updates are a separate operation
* `cpt-studio-fr-core-init` — Project initialization prompts to install the SDLC kit inline with `[a]ccept / [d]ecline`
* `cpt-studio-component-kit-manager` — Updated to support GitHub-based kit sources with `source` and `version` tracking in `core.toml`
* SDLC plugin component — Removed from Studio component model; SDLC kit is an external package
* `cpt-studio-principle-kit-centric` — Reinforced: even the primary kit is an external package, proving the extensible kit model
