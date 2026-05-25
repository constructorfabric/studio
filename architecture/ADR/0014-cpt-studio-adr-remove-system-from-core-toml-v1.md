---
status: accepted
date: 2026-03-10
decision-makers: project maintainer
---

# ADR-0014: Remove `[system]` Section from `core.toml` — Use `artifacts.toml` as Single Source

**ID**: `cpt-studio-adr-remove-system-from-core-toml`

<!-- toc -->

- [Context and Problem Statement](#context-and-problem-statement)
- [Decision Drivers](#decision-drivers)
- [Considered Options](#considered-options)
- [Decision Outcome](#decision-outcome)
  - [Consequences](#consequences)
  - [Confirmation](#confirmation)
- [Pros and Cons of the Options](#pros-and-cons-of-the-options)
  - [Option 1: Keep System Section in core.toml (Status Quo)](#option-1-keep-system-section-in-coretoml-status-quo)
  - [Option 2: Remove System Section from core.toml; artifacts.toml is Single Source](#option-2-remove-system-section-from-coretoml-artifactstoml-is-single-source)
  - [Option 3: Keep System Section as Derived Cache](#option-3-keep-system-section-as-derived-cache)
- [More Information](#more-information)
  - [Current Duplication](#current-duplication)
  - [Active Readers of the System Section in core.toml](#active-readers-of-the-system-section-in-coretoml)
  - [Migration Plan](#migration-plan)
  - [`core.toml` Before and After](#coretoml-before-and-after)
- [Traceability](#traceability)

<!-- /toc -->

## Context and Problem Statement

`core.toml` contains a `[system]` section with three fields — `name`, `slug`, and `kit` — that define the project's root system identity. The same data is independently maintained in `artifacts.toml` under `[[systems]]`, which is the authoritative source consumed by the entire validation, traceability, and context-loading pipeline. This creates a DRY violation: two config files claim authority over the same system identity, and edits to one have no effect on the other.

Analysis of the codebase reveals that only three code paths read `[system]` from `core.toml`: `_read_project_name_from_core()` in `kit.py` (reads `system.name`), legacy kit rename logic in `update.py` (reads/writes `system.kit`), and v2→v3 migration in `migrate.py` (reads `system.kit`). The `system.slug` field is written during `cfs init` and `cfs migrate` but never read by any code path — it is dead code. Meanwhile, `artifacts.toml` `[[systems]]` is loaded on every CLI invocation via `StudioContext.load()` and provides `name`, `slug`, `kit`, `children`, `autodetect`, `artifacts`, and `codebase` — a strict superset of what `core.toml` `[system]` offers.

## Decision Drivers

* **DRY violation** — system identity (`name`, `slug`, `kit`) is defined in both `core.toml` and `artifacts.toml`; changing one does not update the other
* **Dead code** — `system.slug` in `core.toml` is written during init/migrate but never read by any code path
* **Authoritative source already exists** — `artifacts.toml` `[[systems]]` is loaded by `StudioContext`, the validator, the traceability engine, adapter_info, and spec_coverage; it is the de facto single source of truth
* **User confusion** — editing `[system]` in `core.toml` has no effect on validation or traceability, because those systems read from `artifacts.toml`
* **Schema simplification** — removing `[system]` makes `core.toml` focused on its true responsibility: project root, kit registrations (including resource bindings for manifest-driven kits), and ignore lists

## Considered Options

1. **Keep `[system]` in `core.toml`** — status quo, accept the duplication
2. **Remove `[system]` from `core.toml`; use `artifacts.toml` `[[systems]]` as single source** — migrate three readers, stop writing `[system]` in init/migrate
3. **Keep `[system]` as derived cache** — auto-populate from `artifacts.toml` on every `cfs update`

## Decision Outcome

Chosen option: **Option 2 — Remove `[system]` from `core.toml`**, because `artifacts.toml` already serves as the authoritative source for system definitions across the entire tool, and maintaining a parallel copy in `core.toml` creates confusion without providing any benefit. The three active readers can be trivially migrated to read from `artifacts.toml` instead.

### Consequences

* Good, because the DRY violation is eliminated — system identity is defined in exactly one place (`artifacts.toml`)
* Good, because `core.toml` schema is simplified to its core responsibility: project root, kit registrations, and ignore lists
* Good, because dead code (`system.slug` reader) is removed without any behavioral change
* Good, because user confusion is eliminated — there is no longer a `[system]` section that appears editable but has no effect
* Neutral, because existing `core.toml` files with `[system]` sections are automatically cleaned up during `cfs update` — the section is removed as a migration step
* Neutral, because three code paths need migration (minimal scope: `kit.py`, `update.py`, `migrate.py`)
* Bad, because `core.toml` no longer provides a quick glance at the project's system name (mitigated: `cfs info` displays system data from `artifacts.toml`)

### Confirmation

Confirmed when:

- `_default_core_toml()` in `init.py` no longer writes `[system]` section
- `_read_project_name_from_core()` in `kit.py` is replaced with a function that reads from `artifacts.toml` `[[systems]][0].name`
- Legacy kit rename logic in `update.py` no longer reads/writes `system.kit` from `core.toml`
- v2→v3 migration in `migrate.py` no longer writes `[system]` to generated `core.toml`
- `cfs validate` passes on projects with and without `[system]` in `core.toml`
- No code path references `core_data["system"]` or `core_data.get("system")`
- `cfs update` on a project with `[system]` in `core.toml` removes the section and reports it in the update log

## Pros and Cons of the Options

### Option 1: Keep System Section in core.toml (Status Quo)

Retain the `[system]` section in `core.toml` alongside `[[systems]]` in `artifacts.toml`.

* Good, because no code changes required
* Good, because `core.toml` provides a quick human-readable system name
* Bad, because DRY violation persists — two files define the same system identity
* Bad, because `system.slug` remains dead code
* Bad, because users may edit `[system]` expecting it to affect validation/traceability (it does not)

### Option 2: Remove System Section from core.toml; artifacts.toml is Single Source

Stop writing `[system]` in init/migrate. Migrate three readers to use `artifacts.toml`.

* Good, because eliminates duplication — single source of truth for system identity
* Good, because removes dead code (`system.slug`)
* Good, because `core.toml` focuses on kit registrations only
* Good, because no user-visible behavior change (all consumers already use `artifacts.toml`)
* Bad, because three code paths need migration (low effort: ~20 lines total)

### Option 3: Keep System Section as Derived Cache

Auto-populate `[system]` from `artifacts.toml` on every `cfs update` so they stay in sync.

* Good, because `core.toml` still shows system name at a glance
* Good, because no reader migration needed
* Bad, because adds complexity — a new sync step that must run reliably
* Bad, because the section appears user-editable but would be overwritten on every update
* Bad, because still two places defining the data, even if one is auto-derived

## More Information

### Current Duplication

The same data appears in two files:

**`core.toml`**:
```toml
[system]
name = "Studio"
slug = "studio"
kit = "sdlc"
```

**`artifacts.toml`**:
```toml
[[systems]]
name = "Studio"
slug = "studio"
kit = "sdlc"
children = []
```

### Active Readers of the System Section in core.toml

| Reader | File | Field | Purpose | Migration |
|--------|------|-------|---------|-----------|
| `_read_project_name_from_core()` | `kit.py:371` | `system.name` | Project name for `.gen/` aggregation | Read `artifacts.toml` first root system name |
| Legacy kit rename | `update.py:568` | `system.kit` | Update kit slug during rename | Remove — rename already updates `artifacts.toml` |
| v2→v3 primary slug | `migrate.py:1913` | `system.kit` | Determine primary kit for JSON→TOML migration | Read from `artifacts.toml` or use default |

**Dead field**: `system.slug` — written by `init.py` and `migrate.py`, never read.

### Migration Plan

| Step | Description |
|------|-------------|
| 1 | Remove `"system"` key from `_default_core_toml()` in `init.py` |
| 2 | Replace `_read_project_name_from_core()` in `kit.py` with `_read_project_name_from_registry()` that reads `artifacts.toml` |
| 3 | Remove `system.kit` update from `_rename_legacy_kits()` in `update.py` |
| 4 | Remove `core_data["system"]` generation from `_generate_core_toml()` in `migrate.py` |
| 5 | Update `migrate.py:1913` to read primary kit from `artifacts.toml` instead of `core.toml` |
| 6 | Add migration step to `cfs update`: if `core.toml` contains `[system]`, remove the section and log the action in the update report |

### `core.toml` Before and After

**Before**:
```toml
version = "1.0"
project_root = ".."

[system]
name = "Studio"
slug = "studio"
kit = "sdlc"

[kits.sdlc]
format = "CFS"
path = "config/kits/sdlc"
version = "1.0.0"
source = "github:constructorfabric/studio-kit-sdlc"
```

**After**:
```toml
version = "1.0"
project_root = ".."

[kits.sdlc]
format = "CFS"
path = "config/kits/sdlc"
version = "1.0.0"
source = "github:constructorfabric/studio-kit-sdlc"
```

## Traceability

- **PRD**: [PRD.md](../PRD.md)
- **DESIGN**: [DESIGN.md](../DESIGN.md)

This decision directly addresses the following requirements and design elements:

* `cpt-studio-nfr-dry` — Eliminates the only known DRY violation in the config layer: system identity was defined in two places
* `cpt-studio-fr-core-config` — Simplifies `core.toml` schema to focus on kit registrations and project root
* `cpt-studio-component-config-manager` — Config Manager no longer reads/writes `[system]` section; system data comes from artifacts registry
