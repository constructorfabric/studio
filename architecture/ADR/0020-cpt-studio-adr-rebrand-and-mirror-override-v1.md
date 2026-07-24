---
status: accepted
date: 2026-05-25
decision-makers: project maintainer
---

# ADR-0020: Constructor Studio Rebrand and Global Mirror-Override Capability

**ID**: `cpt-studio-adr-rebrand-and-mirror-override`

<!-- toc -->

- [Context and Problem Statement](#context-and-problem-statement)
- [Decision Drivers](#decision-drivers)
- [Considered Options](#considered-options)
- [Decision Outcome](#decision-outcome)
  - [Rename Decisions](#rename-decisions)
  - [Mirror-Override Decisions](#mirror-override-decisions)
  - [Consequences](#consequences)
  - [Confirmation](#confirmation)
- [Pros and Cons of the Options](#pros-and-cons-of-the-options)
  - [Constructor Studio with mirror-override (chosen)](#constructor-studio-with-mirror-override-chosen)
  - [Two-hop rename without mirror-override](#two-hop-rename-without-mirror-override)
  - [Constructor Studio rename only, no mirror-override](#constructor-studio-rename-only-no-mirror-override)
- [Mirror-Override Semantics](#mirror-override-semantics)
  - [Dual Config File Locations](#dual-config-file-locations)
  - [Read-Merge Order](#read-merge-order)
  - [Write-Target Resolution](#write-target-resolution)
  - [URL Canonicalization](#url-canonicalization)
  - [Match Semantics](#match-semantics)
  - [Lookup Integration Points](#lookup-integration-points)
- [Related ADRs](#related-adrs)

<!-- /toc -->

## Context and Problem Statement

This project has undergone two brand transitions:

1. **Cypilot → Cyber Constructor** — an intermediate rename that aligned the project name with the `cyberfabric` GitHub organization and introduced the `cfc` CLI binary and the `cf-constructor` skill name.
2. **Cyber Constructor → Constructor Studio** — the v1.0.0 rename documented in this ADR, collapsing the intermediate name and establishing `constructor-studio` as the permanent identity.

The v1.0.0 release collapses both hops: a cypilot install migrates **directly** to Constructor Studio, skipping the intermediate Cyber Constructor form. The frozen `SUPPORTED_LEGACY_MIGRATION_VERSIONS = {"3.9.0", "3.10.0"}` constant stays (per the existing lifecycle rule), but every target identifier produced by the migration uses Constructor Studio forms.

**CPT identifier system**: `CPT = Canonical Provenance Trace` — the identifier scheme `cpt-{system}-{kind}-{slug}-v{N}` remains intact. Only the `{system}` token changes from `cypilot` (and the intermediate `cyber-constructor`) to `studio`. No CPT machinery is removed or restructured.

**CDSL**: `CDSL = Constructor DSL` is the now-canonical expansion, replacing the former "Cypilot DSL" name. The language and its syntax are unchanged.

**Mirror override**: users operating behind corporate proxies, on air-gapped networks, or with GitHub Enterprise mirrors need a way to redirect Constructor Studio's default download and API URLs to alternative hosts. There was no mechanism for this in prior releases. v1.0.0 introduces a global mirror-override capability exposed via `cfs mirror` CLI verbs with dual-location TOML config.

## Decision Drivers

* **Brand clarity** — "Constructor Studio" is the marketing name from v1.0.0; all prior names are legacy aliases
* **CLI simplicity** — `cfs` is shorter than `cfc` and aligns with "Constructor Fabric Studio"
* **Skill namespace simplification** — the `cf` skill name (alias `cf-studio`) is cleaner than `cf-constructor`
* **Zero-hop migration** — cypilot users migrate directly to Constructor Studio without a Cyber Constructor intermediate step
* **Network flexibility** — enterprise users need mirror support without modifying source code or build scripts
* **XDG compliance** — new installs default to XDG config dir; existing brand-home installs are preserved

## Considered Options

* **Constructor Studio with mirror-override (chosen)** — single-hop rename from cypilot directly to Constructor Studio combined with a global URL-redirect mechanism exposed via `cfs mirror`.
* **Two-hop rename (Cypilot → Cyber Constructor → Constructor Studio) without mirror-override** — keep the intermediate Cyber Constructor name as a real migration target and defer mirror support to a later release.
* **Constructor Studio rename only, no mirror-override** — apply the v1.0.0 rename but leave enterprise URL redirection to source patches or environment-variable hacks.

## Decision Outcome

### Rename Decisions

The following renames are applied across all architecture docs, source code, and agent skill files:

| Domain | Old | New |
|--------|-----|-----|
| Marketing name | Cyber Constructor / Cyber Pilot | Constructor Studio |
| Project (pyproject.toml) | `cyber-constructor` | `constructor-studio` |
| Python proxy package | `cypilot_proxy` | `studio_proxy` |
| Console script (primary) | `cfc` | `cfs` |
| Console script (long form) | `cf-constructor` | `constructor-studio` |
| User-agent header | `cyber-constructor/4.0` | `constructor-studio/1.0` |
| Asset name pattern | `cf-constructor-skill-*` | `studio-skill-*` |
| Cache directory | `~/.cf-constructor/cache/` | `~/.cf-studio/cache/` |
| Default GitHub repo | `cyberfabric/cyber-constructor` | `constructorfabric/studio` |
| Default kit-sdlc repo | `cyberfabric/cyber-pilot-kit-sdlc` / `cyberfabric/cyber-constructor-kit-sdlc` | `constructorfabric/studio-kit-sdlc` |
| Workspace marker file | `.cypilot-workspace.toml` | `.cf-workspace.toml` (canonical; `.studio-workspace.toml` is legacy fallback) |
| VS Code workspace file | `Cypilot.code-workspace` | `Studio.code-workspace` |
| Skill name (canonical) | `cf-constructor` | `cf` (alias `cf-studio`) |
| Skill directory | `skills/cypilot/` | `skills/studio/` |
| Agent file prefix | `cf-constructor-*.md` | `cf-*.md` |
| CPT system token in IDs | `cpt-cypilot-*` / `cpt-cyber-constructor-*` | `cpt-studio-*` |
| Version | `4.1.0` | `1.0.0` |
| Template variable | `{cf-constructor-path}` | `{cf-studio-path}` |
| Template variable | `{cfc_cmd}` | `{cfs_cmd}` |
| Template variable | `{cfc_mode}` | `{cfs_mode}` |

**Universal rename rule** (applied with case preservation):
- lowercase `cypilot` → `studio`
- PascalCase `Cypilot` → `Studio`
- UPPERCASE `CYPILOT` → `STUDIO`

**Not renamed**: `.bootstrap/` — the bootstrap config tree is intentionally frozen at HEAD. It will be regenerated by a downstream `cfs update` cycle from the new layout after v1.0.0 ships. No bucket in this rebrand touches `.bootstrap/`.

### Mirror-Override Decisions

A new `cfs mirror` command group provides global URL redirect management:

```
cfs mirror override <old-url> <new-url>   # register or update
cfs mirror list                           # print effective set with source path
cfs mirror remove <old-url>              # delete one entry
cfs mirror clear                          # delete all entries
```

Implementation lives in `src/studio_proxy/mirrors.py` exporting `load_overrides()`, `apply_override(url) -> url`, `set_override(old, new)`, `remove_override(old)`, `list_overrides()`.

### Consequences

**Positive**:
- Single canonical name: Constructor Studio / `cfs` / `studio_proxy` going forward
- Migration path from cypilot collapses to one hop (direct to Constructor Studio)
- Enterprise users can redirect all GitHub URLs without patching source code
- XDG compliance for new installs; existing `~/.constructor-studio/` setups preserved

**Neutral**:
- Cached skill layouts under `studio/` (formerly `cypilot/`) are still recognized for one release
- Legacy `cf-constructor-skill-*` asset names are still resolved by `cache.py` during the migration window
- The `SUPPORTED_LEGACY_MIGRATION_VERSIONS = {"3.9.0", "3.10.0"}` gate is frozen and unchanged

**Negative / risk**:
- Users who have scripted `cfc` as the CLI binary must update their scripts (one-time migration)
- Agent config files referencing `cf-constructor` skill name must be regenerated via `cfs generate-agents`

### Confirmation

Confirmed when:
- `cfs --version` returns `1.0.0`
- `cfs init` creates the project install directory and uses `~/.cf-studio/cache/` for cached skill bundles
- `cfs generate-agents` produces host integration files under agent-specific locations such as `.agents/skills/cf/` and `.claude/skills/cf/`; canonical source files remain under `skills/studio/`
- `cfs mirror override github.com/constructorfabric/studio github.com/myorg/studio` writes to XDG path on fresh install
- `cfs mirror list` shows merged set with correct source path for each entry
- Migrating a cypilot 3.9.0 project writes canonical `.cf-workspace.toml` directly (no intermediate Cyber Constructor form); `.studio-workspace.toml` remains a legacy discovery fallback
- All `cpt-cypilot-*` ID references in migrated projects are rewritten to `cpt-studio-*`

## Pros and Cons of the Options

### Constructor Studio with mirror-override (chosen)

A single canonical name (`constructor-studio` / `cfs`) combined with a global URL-redirect layer (`cfs mirror`) backed by dual XDG/brand-home TOML configs.

* Good, because cypilot users migrate in one hop with no intermediate Cyber Constructor artifacts
* Good, because enterprise users can redirect every GitHub URL (API, kit, asset, init/update) without patching source
* Good, because XDG-preferred write target satisfies platform conventions while preserving existing brand-home installs
* Neutral, because legacy `cf-constructor-*` and `cypilot/` asset names remain resolvable for one migration window
* Bad, because users who scripted the `cfc` CLI binary must update their scripts (one-time migration cost)

### Two-hop rename without mirror-override

Keep Cyber Constructor as a real intermediate state and ship mirror support later.

* Good, because each rename hop is smaller and individually reversible
* Bad, because cypilot users would be forced through two migrations within a short release window
* Bad, because enterprise users behind mirrors remain blocked until a follow-up release
* Bad, because the codebase carries two transitional brand names simultaneously, doubling rename surface area

### Constructor Studio rename only, no mirror-override

Apply the v1.0.0 rename but leave URL redirection to ad-hoc means.

* Good, because the v1.0.0 change set is smaller and ships sooner
* Bad, because enterprise / air-gapped users have no first-class redirection mechanism and must patch source or set per-call env vars
* Bad, because deferring mirror support introduces a second config schema later, breaking the principle of a single canonical config layout from v1.0.0

---

## Mirror-Override Semantics

### Dual Config File Locations

Two config files participate in mirror override management:

1. **XDG primary**: `${XDG_CONFIG_HOME:-~/.config}/constructor-studio/mirrors.toml`
2. **Brand-home fallback**: `~/.constructor-studio/mirrors.toml`

Both files use the same TOML schema:

```toml
[[mirror]]
from = "github.com/constructorfabric/studio"
to   = "github.com/myorg/studio"

[[mirror]]
from = "github.com/constructorfabric/studio-kit-sdlc"
to   = "github.com/myorg/studio-kit-sdlc"
```

### Read-Merge Order

On every `cfs mirror list` or `apply_override()` call, both files are read and merged:

1. Read XDG path entries first (lower precedence).
2. Read brand-home path entries second (higher precedence).
3. On duplicate `from` key: the brand-home entry wins.

`cfs mirror list` MUST print the effective merged set with the source path of each entry so users can diagnose which file contributes which override.

### Write-Target Resolution

When writing (via `override`, `remove`, or `clear`):

1. If `~/.constructor-studio/mirrors.toml` already exists → write there (preserve the user's explicit choice).
2. Else if `${XDG_CONFIG_HOME:-~/.config}/constructor-studio/mirrors.toml` already exists → write there.
3. Else → create `${XDG_CONFIG_HOME:-~/.config}/constructor-studio/mirrors.toml` (XDG-preferred default for new installs).

This policy ensures that users who have an existing brand-home file (upgraded from a prior release) are not silently switched to XDG, and that new installs default to XDG.

### URL Canonicalization

Before storing or matching, all URLs are canonicalized by:

1. Stripping the URL scheme (`https://`, `http://`, `ssh://`, `git@` prefix).
2. Stripping a trailing `.git` suffix.
3. Stripping a trailing `/`.

Example: `https://github.com/constructorfabric/studio.git` → `github.com/constructorfabric/studio`.

### Match Semantics

Apply the longest-prefix match on the canonicalized URL. If multiple override entries match, the one with the longest `from` prefix wins.

### Lookup Integration Points

`apply_override(url)` MUST be called at every point that constructs a URL for external access:

- `cache.py` `_resolve_api_base` — GitHub API base URL construction
- `cache.py` `download_and_cache` — asset download URL (zip/tarball)
- `init` command URL forwarding when cloning skill source
- `update` command URL forwarding when downloading new skill version
- Kit `source = "github:..."` resolution in `autodetect` logic

---

## Related ADRs

- **ADR-0007** (`cpt-studio-adr-proxy-cli-pattern`) — establishes the global CLI proxy architecture; this ADR adds mirror-override to the proxy layer
- **ADR-0013** (`cpt-studio-adr-extract-sdlc-kit`) — established the GitHub-based kit distribution model that mirror-override now extends
- **ADR-0003** (`cpt-studio-adr-pipx-distribution`) — establishes `pipx install` as the distribution mechanism; this ADR renames the package from `cyber-constructor` to `constructor-studio`
- **ADR-0019** (`cpt-studio-adr-unified-manifest-hierarchy`) — unified manifest hierarchy for multi-layer component registration; kit `source` field resolution is an integration point for mirror overrides
