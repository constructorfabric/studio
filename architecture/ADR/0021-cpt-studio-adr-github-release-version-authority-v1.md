---
status: accepted
date: 2026-06-01
decision-makers: project maintainer
---

# ADR-0021: GitHub Release Provenance as Version Authority

**ID**: `cpt-studio-adr-github-release-version-authority`

<!-- toc -->

- [Context and Problem Statement](#context-and-problem-statement)
- [Decision Drivers](#decision-drivers)
- [Considered Options](#considered-options)
- [Decision Outcome](#decision-outcome)
  - [Authority Rules](#authority-rules)
  - [Structured Provenance](#structured-provenance)
  - [Source Modes](#source-modes)
  - [User Reporting](#user-reporting)
  - [Consequences](#consequences)
  - [Confirmation](#confirmation)
- [Pros and Cons of the Options](#pros-and-cons-of-the-options)
  - [GitHub Release/tag provenance authority (chosen)](#github-releasetag-provenance-authority-chosen)
  - [Local package files as authority](#local-package-files-as-authority)
  - [Git tag-only authority](#git-tag-only-authority)
- [Related ADRs](#related-adrs)

<!-- /toc -->

## Context and Problem Statement

Constructor Studio has two GitHub-backed version surfaces:

1. The global proxy cache for the Studio skill engine bundle.
2. Installed kits, including the default SDLC kit.

Before this decision, version reporting could drift because local files such as a static `pyproject.toml` version, kit `conf.toml`, `.version`, or Python `__version__` could be read after content was copied from GitHub. That makes release correctness depend on maintainers remembering to update several local version declarations in addition to creating a GitHub release/tag.

The desired release workflow is simpler: the maintainer creates a GitHub Release/tag and does not perform any extra local version bump for release recognition. The proxy package derives build metadata from the Git tag, and the tool resolves, stores, reports, and compares installed content versions from GitHub provenance for GitHub-backed content.

## Decision Drivers

* **Single release action** — creating a GitHub Release/tag must be enough for version recognition.
* **No local drift** — copied local metadata files must not override GitHub-backed release state.
* **Auditable installs** — installed state must preserve source, resolved ref, content identity, and verification freshness.
* **Mirror compatibility** — mirror/fork overrides must be reflected by separating requested source from effective source.
* **Offline honesty** — offline mode may report last-known state but must not invent freshness from local files.
* **Compatibility** — repositories without published GitHub Releases may still work through an explicit semver tag/ref fallback.
* **Local workflows** — local/path installs remain useful but are explicitly outside GitHub authority.

## Considered Options

* **GitHub Release/tag provenance authority (chosen)** — resolve GitHub-backed proxy and kit versions from published releases/tags/refs, then persist structured provenance and content identity.
* **Local package files as authority** — continue reading version from copied files such as `conf.toml`, `pyproject.toml`, `.version`, or `__version__`.
* **Git tag-only authority** — use Git tags as the only source of version truth and ignore GitHub Releases.

## Decision Outcome

### Authority Rules

For GitHub-backed sources, version authority is resolved in this order:

1. An explicit selector from the user, such as `--version`, `owner/repo@tag`, branch, or SHA.
2. The effective GitHub source's latest published Release.
3. A semver tag compatibility fallback when the repository has no Release.
4. Existing structured metadata for offline display only.

Local copied version files are never authoritative for GitHub-backed proxy cache or kit currentness. They may be shown as legacy or diagnostic metadata only.

GitHub Release version and content identity are separate. The release/tag/ref is the display/backcompat version, while commit SHA, resolved ref, asset digest, source archive digest, or equivalent tree identity describes the installed content.

### Structured Provenance

GitHub-backed proxy cache state, project-installed core state, and kit registrations persist structured provenance with at least:

| Field | Meaning |
|-------|---------|
| `installed_version` | Display/backcompat version derived from GitHub release/tag/ref |
| `requested_ref` | User selector or implicit selector such as `latest` |
| `resolved_ref` | GitHub release tag, tag name, branch ref, or SHA actually used |
| `commit_sha` | Immutable commit/content identity when available |
| `resolver_mode` | `explicit`, `explicit_release`, `latest_release`, `semver_tag_fallback`, `github_ref`, `default_branch`, `offline_last_known`, or `local_path` |
| `resolution_basis` | What GitHub object or persisted state produced the result |
| `canonical_source` | Canonical repository/source before overrides |
| `effective_source` | Repository/source after mirror or fork override |
| `resolved_at` | Timestamp of the verified online resolution |
| `verified` / `freshness` | Whether the state was verified online, stale/offline, unverified, or unknown |

Release assets are optional. When no suitable asset is present, downloading the source tarball for the resolved release/tag/ref is first-class behavior, not a degraded local-version path.

### Source Modes

GitHub-backed modes and local/path modes are distinct:

* GitHub-backed proxy and kit installs use the GitHub authority rules above.
* Local/path installs are outside GitHub authority and record local provenance.
* `--version` selectors and `owner/repo@ref` syntax conflict with local/path mode.
* `core.toml [kits.<slug>].version` remains a display/backcompat field. For GitHub-backed kits it is GitHub-derived; for local/path kits it is local metadata.

Mirror and fork overrides are applied before authority lookup. Reporting always shows both requested and effective source when they differ.

### User Reporting

Version and update output must distinguish:

* proxy/package metadata;
* cached skill bundle state;
* project-installed core state;
* installed kit state.

For each item, output should show source, effective source, resolved release/tag/ref, content identity when known, verification/freshness status, and remediation when freshness is unknown or stale. Offline lookup reports last-known state and an online reverify/update command; it does not infer authority from local files.

### Consequences

**Positive**:
- Maintainers can publish a GitHub Release/tag as the single release action for version recognition.
- The proxy package can be built with dynamic package metadata from the Git tag instead of a checked-in static version.
- Users receive auditable installed-state reports that explain where version information came from.
- Enterprise mirror/fork behavior is diagnosable through requested/effective source provenance.
- Offline reporting becomes explicit instead of silently trusting stale local files.

**Neutral**:
- Existing `version` fields in `core.toml`, `conf.toml`, `.version`, and `__version__` may remain for compatibility and diagnostics.
- Python package metadata still contains a version after build/install; it is derived from SCM tags rather than manually written in source.
- Repositories without Releases still work through semver tag/ref fallback, but the fallback is labeled.

**Negative / risk**:
- Existing code paths that compare local `conf.toml` or copied skill versions must be migrated carefully.
- Metadata schema changes require backward-compatible loading for pre-provenance installs.
- Tests must cover release, tag-only, explicit ref, branch, SHA, local/path, mirror, and offline cases.

### Confirmation

Confirmed when:

- Creating a GitHub Release/tag is sufficient for proxy cache and kit version recognition.
- `cfs update` reports GitHub-derived provenance and ignores copied local version files for authority.
- `cfs --version` separates package metadata from cached and project-installed core state; kit state is reported through kit update/report paths.
- GitHub-backed `cfs kit install` and `cfs kit update` store `requested_ref`, `resolved_ref`, `commit_sha` or content identity, `canonical_source`, `effective_source`, `resolver_mode`, and freshness.
- Local/path kit operations reject GitHub selector/ref options and report local provenance.
- Offline status uses last-known structured metadata and marks freshness/verification as `offline`, `last_known`, `stale`, `unverified`, or `unknown` according to the surface reporting it.
- Tests cover the cross-source matrix and legacy pre-provenance idempotency.

## Pros and Cons of the Options

### GitHub Release/tag provenance authority (chosen)

GitHub Releases are the stable user-facing release object; tags/refs provide explicit and compatibility resolution. Structured provenance stores the result.

* Good, because maintainers do not need to update local metadata files for release recognition.
* Good, because the resolver can explain exactly which release/tag/ref and content identity were installed.
* Good, because mirrors and forks remain auditable through requested/effective source fields.
* Good, because local/path development remains supported as an explicit non-GitHub mode.
* Bad, because more metadata must be persisted and migrated than a single string version.

### Local package files as authority

Read version values from copied files inside the cached skill bundle or installed kit.

* Good, because existing code already has several local version readers.
* Bad, because release correctness depends on manual version bumps in multiple files.
* Bad, because copied local metadata cannot distinguish requested source, effective source, release tag, and content identity.
* Bad, because offline mode can appear fresh even when it only has stale local files.

### Git tag-only authority

Use Git tags as the only source of truth for GitHub-backed sources.

* Good, because tags are simple and map directly to source archives.
* Bad, because GitHub Releases are the published release object users and maintainers expect.
* Bad, because release assets and release notes become second-class.
* Neutral, because semver tags remain useful as an explicit compatibility fallback.

## Related ADRs

- `cpt-studio-adr-proxy-cli-pattern` — global proxy/cache pattern.
- `cpt-studio-adr-pipx-distribution` — global CLI distribution.
- `cpt-studio-adr-extract-sdlc-kit` — external GitHub kit package model.
- `cpt-studio-adr-rebrand-and-mirror-override` — Constructor Studio identity and requested/effective source override semantics.
