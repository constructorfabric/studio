# Feature: Generic Git Kit Installer

<!-- toc -->

- [1. Feature Context](#1-feature-context)
  - [1. Overview](#1-overview)
  - [2. Purpose](#2-purpose)
  - [3. Actors](#3-actors)
  - [4. References](#4-references)
- [2. Actor Flows (CDSL)](#2-actor-flows-cdsl)
  - [Install Generic Git Kit](#install-generic-git-kit)
  - [Update Generic Git Kit](#update-generic-git-kit)
- [3. Processes / Business Logic (CDSL)](#3-processes--business-logic-cdsl)
  - [Generic Git Source Parse](#generic-git-source-parse)
  - [Generic Git Source Policy](#generic-git-source-policy)
  - [Git Ref Resolution](#git-ref-resolution)
  - [Generic Git Fetch Cache](#generic-git-fetch-cache)
  - [Generic Git Provenance Registration](#generic-git-provenance-registration)
  - [Generic Git URL Normalization](#generic-git-url-normalization)
  - [Generic Git Auth Runtime](#generic-git-auth-runtime)
- [4. States (CDSL)](#4-states-cdsl)
  - [Generic Git Kit Source State](#generic-git-kit-source-state)
- [5. Definitions of Done](#5-definitions-of-done)
  - [Generic Git Source Grammar](#generic-git-source-grammar)
  - [Git Ref Resolution via `--version`](#git-ref-resolution-via---version)
  - [Generic Git Provenance and Schema](#generic-git-provenance-and-schema)
  - [Cache and Offline Fallback](#cache-and-offline-fallback)
  - [Auth and Redaction](#auth-and-redaction)
- [6. Implementation Modules](#6-implementation-modules)
- [7. Acceptance Criteria](#7-acceptance-criteria)

<!-- /toc -->

- [ ] `p1` - **ID**: `cpt-studio-featstatus-generic-git-kit-installer`

## 1. Feature Context

- [ ] `p1` - `cpt-studio-feature-generic-git-kit-installer`

### 1. Overview

Adds a generic Git-backed kit source mode alongside the existing GitHub shorthand and local path modes. Users can install and update kits from any Git transport accepted by `git` while Studio persists deterministic provenance, resolved commit identity, cache metadata, and redacted diagnostics.

### 2. Purpose

Studio kit installation currently supports GitHub repository shorthand and explicit local paths. This feature adds a pure Git source grammar for repositories hosted outside GitHub, self-hosted Git services, SSH-only repositories, and local `file://` repositories without merging that behavior into GitHub-specific release semantics.

### 3. Actors

| Actor | Role in Feature |
|-------|-----------------|
| `cpt-studio-actor-user` | Installs or updates a kit from a generic Git source and optionally passes `--version` as a ref selector |
| `cpt-studio-actor-studio-cli` | Parses source grammar, resolves refs, fetches Git content, validates provenance, and records kit registration metadata |

### 4. References

- **PRD**: [PRD.md](../PRD.md) - `cpt-studio-fr-core-kits`, `cpt-studio-nfr-security-integrity`, `cpt-studio-nfr-reliability-recoverability`
- **Design**: [DESIGN.md](../DESIGN.md) - `cpt-studio-fr-core-kits`, `cpt-studio-component-kit-manager`, `cpt-studio-component-config-manager`
- **Feature Dependency**: [kit-management.md](kit-management.md) - `cpt-studio-feature-blueprint-system`

## 2. Actor Flows (CDSL)

### Install Generic Git Kit

- [ ] `p1` - **ID**: `cpt-studio-flow-generic-git-kit-installer-install`

**Actor**: `cpt-studio-actor-user`

**Trigger**: User runs `cfs kit install git/<encoded-url>[//<subdir>][@<kit>] [--version <ref>] [--force] [--dry-run]`

**Success Scenarios**:
- User installs from `git/https%3A%2F%2Fgit.example.com%2Forg%2Fkit.git --version v1.2.3` and Studio records the requested tag plus the resolved commit SHA.
- User installs from an SSH repository using ambient Git authentication and Studio records no credential material.
- User installs from a repository subdirectory using `//kits/sdlc@custom-sdlc`; Studio validates only that subdirectory as the package root and registers the selected kit identity.

**Error Scenarios**:
- Source contains unencoded credentials, query, or fragment -> reject before canonicalization, hashing, fetching, or persistence.
- Source subdirectory is absolute, empty-segmented, or contains `..` -> reject before invoking Git.
- `--version` resolves to no Git object or resolves to a non-commit tree target that cannot be checked out -> fail with a structured resolver error.

**Steps**:
1. [ ] - `p1` - Parse CLI arguments and detect `git/` source grammar without routing through GitHub shorthand parsing - `inst-git-install-parse-cli`
2. [ ] - `p1` - Parse and canonicalize source grammar using `cpt-studio-algo-generic-git-kit-installer-source-parse` - `inst-git-install-parse-source`
3. [ ] - `p1` - Validate source policy and reject credential-bearing or non-persistent URL components using `cpt-studio-algo-generic-git-kit-installer-source-policy` - `inst-git-install-source-policy`
4. [ ] - `p1` - Resolve `--version` as an opaque Git ref selector; when omitted, resolve the remote default branch - `inst-git-install-resolve-ref`
5. [ ] - `p1` - Fetch or reuse cached repository content using `cpt-studio-algo-generic-git-kit-installer-fetch-cache` - `inst-git-install-fetch-cache`
6. [ ] - `p1` - Check out the resolved commit into a temporary worktree or archive extraction rooted at the selected subdirectory - `inst-git-install-checkout`
7. [ ] - `p1` - Read kit metadata from selected package root and validate that the selected kit identity matches the package when an `@<kit>` suffix is present - `inst-git-install-read-kit`
8. [ ] - `p1` - Install kit content through the existing manifest-driven or legacy kit installation path - `inst-git-install-delegate-kit-install`
9. [ ] - `p1` - Persist generic Git source provenance, content identity, freshness, and cache metadata under the kit registration - `inst-git-install-persist-provenance`
10. [ ] - `p1` - Regenerate `.gen/` aggregates unless `--dry-run` is set - `inst-git-install-regen`
11. [ ] - `p1` - **RETURN** install result with sanitized source display, requested ref, resolved commit SHA, resolution basis, and offline/cache status - `inst-git-install-return`

### Update Generic Git Kit

- [ ] `p1` - **ID**: `cpt-studio-flow-generic-git-kit-installer-update`

**Actor**: `cpt-studio-actor-user`

**Trigger**: User runs `cfs kit update <kit> [--version <ref>] [--force] [--dry-run] [--no-interactive] [-y]` for a kit registered with `source_type = "git"`

**Success Scenarios**:
- Mutable branch update resolves a new commit SHA and runs the same file-level diff and manifest validation path as initial install.
- Explicit full commit update records `pinned_commit` semantics and uses the commit SHA as immutable currentness.
- Offline update uses a cached artifact only when persisted metadata proves the same remote, ref, subdir, kit identity, and resolved commit.

**Error Scenarios**:
- Generic Git registered kit is accidentally routed through GitHub release lookup -> fail validation in tests; runtime must dispatch by `source_type`.
- Offline mode lacks a matching cached artifact for the last-known commit -> fail with a remediation hint instead of rewriting source to a local path.
- User passes a GitHub shorthand selector for a generic Git registered kit -> reject source mode conflict.

**Steps**:
1. [ ] - `p1` - Load registered kit metadata from `core.toml` and require `source_type = "git"` for this path - `inst-git-update-load-registration`
2. [ ] - `p1` - Determine requested ref from explicit `--version` or persisted `source_provenance.requested_ref` - `inst-git-update-select-ref`
3. [ ] - `p1` - Resolve the requested ref online when available; classify omitted selectors as `default_branch`, branch/tag/symbolic selectors as `mutable_ref`, and explicit full commit selectors as `pinned_commit` - `inst-git-update-resolve-ref`
4. [ ] - `p1` - **IF** online resolution fails: attempt `offline_last_known` cache resolution using persisted resolved commit metadata - `inst-git-update-offline-fallback`
5. [ ] - `p1` - Compare previous and new `resolved_commit_sha` to decide current, changed, or stale/offline status - `inst-git-update-currentness`
6. [ ] - `p1` - Build a source worktree for the selected commit and subdirectory - `inst-git-update-build-source`
7. [ ] - `p1` - Apply existing manifest-aware or legacy file-level update behavior - `inst-git-update-delegate-update`
8. [ ] - `p1` - Persist previous/new SHA, requested ref, resolution basis, freshness, and cache identity after successful update - `inst-git-update-persist`
9. [ ] - `p1` - Regenerate `.gen/` aggregates unless `--dry-run` is set - `inst-git-update-regen`
10. [ ] - `p1` - **RETURN** update result with sanitized source display and previous/new commit identity - `inst-git-update-return`

## 3. Processes / Business Logic (CDSL)

### Generic Git Source Parse

- [ ] `p1` - **ID**: `cpt-studio-algo-generic-git-kit-installer-source-parse`

**Input**: User-facing source string `git/<encoded-url>[//<subdir>][@<kit>]` or persisted source string `git:<encoded-url>[//<subdir>][@<kit>]`

**Output**: Parsed source object with canonical persisted source, decoded remote URL, selected subdirectory, optional kit identity, transport kind, and redaction-safe display

**Rules**:
1. [ ] - `p1` - CLI input uses `git/`; persisted config uses `git:`; both parse to the same structured source object - `inst-git-parse-prefix`
2. [ ] - `p1` - Decode the transport URL exactly once and reject malformed or lossy percent encodings - `inst-git-parse-decode-once`
3. [ ] - `p1` - Accept percent-encoded absolute Git URLs for HTTPS, `ssh://`, encoded scp-like `git@host:org/repo.git`, and `file://` - `inst-git-parse-transports`
4. [ ] - `p1` - Reject unencoded transport URLs that would make grammar boundaries ambiguous - `inst-git-parse-reject-lossy`
5. [ ] - `p1` - Parse optional `//<subdir>` after the encoded URL and require a clean relative path with no empty segments, absolute roots, shell expansion, or `..` traversal - `inst-git-parse-subdir`
6. [ ] - `p1` - Parse optional `@<kit>` identity and require a registry-safe slug - `inst-git-parse-kit-identity`
7. [ ] - `p1` - Persist canonical percent encoding using uppercase percent hex and minimal required grammar encoding - `inst-git-parse-canonical-source`
8. [ ] - `p1` - Build a redaction-safe display value that omits credentials, query, fragment, and raw rejected input - `inst-git-parse-safe-display`

### Generic Git Source Policy

- [ ] `p1` - **ID**: `cpt-studio-algo-generic-git-kit-installer-source-policy`

**Input**: Parsed source object

**Output**: Accepted source policy decision or stable structured error

**Steps**:
1. [ ] - `p1` - Reject userinfo in remote URLs before canonicalization, hashing, resolver setup, provenance persistence, or Git invocation - `inst-git-policy-reject-userinfo`
2. [ ] - `p1` - Reject query strings before canonicalization, hashing, resolver setup, provenance persistence, or Git invocation - `inst-git-policy-reject-query`
3. [ ] - `p1` - Reject URL fragments before canonicalization, hashing, resolver setup, provenance persistence, or Git invocation - `inst-git-policy-reject-fragment`
4. [ ] - `p1` - Return stable error code `GIT_SOURCE_CREDENTIALS_IN_URL` for userinfo-bearing sources - `inst-git-policy-error-credentials`
5. [ ] - `p1` - Return stable error code `GIT_SOURCE_QUERY_UNSUPPORTED` for query-bearing sources - `inst-git-policy-error-query`
6. [ ] - `p1` - Return stable error code `GIT_SOURCE_FRAGMENT_UNSUPPORTED` for fragment-bearing sources - `inst-git-policy-error-fragment`
7. [ ] - `p1` - Include only safe diagnostic metadata: error code, component class, transport, host hash, and sanitized URL display - `inst-git-policy-safe-diagnostics`
8. [ ] - `p1` - Show migration guidance toward Git credential helpers, `GIT_ASKPASS`, runtime `git_auth`, or SSH config without printing secret-bearing material - `inst-git-policy-migration-hint`

### Git Ref Resolution

- [ ] `p1` - **ID**: `cpt-studio-algo-generic-git-kit-installer-ref-resolution`

**Input**: Decoded remote URL, optional requested ref from `--version`, runtime-only auth configuration, optional last-known metadata

**Output**: Requested ref, resolved commit SHA, resolution basis, selector classification, freshness state, and optional offline marker

**Rules**:
1. [ ] - `p1` - Treat `--version` as an opaque Git selector that may name a tag, branch, symbolic ref, or commit SHA - `inst-git-ref-version-opaque`
2. [ ] - `p1` - When `--version` is omitted, resolve the remote default branch and record `resolution_basis = "default_branch"` - `inst-git-ref-default-branch`
3. [ ] - `p1` - Classify only explicit full commit identities as `pinned_commit` - `inst-git-ref-pinned-commit`
4. [ ] - `p1` - Classify branch, tag, symbolic, short SHA, and default-branch selectors as `mutable_ref` unless they are explicit full commits - `inst-git-ref-mutable`
5. [ ] - `p1` - Store requested selector separately from the resolved commit SHA - `inst-git-ref-store-selector-identity`
6. [ ] - `p1` - Use `resolved_commit_sha` as the currentness comparison key for install/update state - `inst-git-ref-currentness-sha`
7. [ ] - `p1` - Never rewrite a mutable selector to a pinned commit in source strings, provenance, lock files, or cache metadata - `inst-git-ref-preserve-selector`
8. [ ] - `p1` - If online resolution fails, return `offline_last_known` only when last-known metadata and cache content prove the same remote, subdir, kit identity, requested ref, and resolved SHA - `inst-git-ref-offline-last-known`

### Generic Git Fetch Cache

- [ ] `p1` - **ID**: `cpt-studio-algo-generic-git-kit-installer-fetch-cache`

**Input**: Parsed source object, requested ref, resolved commit SHA, runtime-only auth configuration, cache root

**Output**: Repository mirror and/or immutable extracted kit artifact for the requested content identity

**Steps**:
1. [ ] - `p1` - Build a versioned structured cache identity object rather than concatenating raw strings - `inst-git-cache-identity-object`
2. [ ] - `p1` - Use separate namespaces for `source_type = "git"` and `source_type = "github"` - `inst-git-cache-namespace`
3. [ ] - `p1` - Hash normalized remote identity, selected subdirectory, kit identity/default marker, requested ref, and resolved commit SHA - `inst-git-cache-hash-components`
4. [ ] - `p1` - Store optional repository mirrors under `cache/git/remotes/<remote_hash>/repo.git` - `inst-git-cache-remote-layout`
5. [ ] - `p1` - Store requested ref metadata under `refs/<requested_ref_hash>.json` - `inst-git-cache-ref-layout`
6. [ ] - `p1` - Store immutable kit artifacts under `commits/<resolved_commit_sha>/subdirs/<subdir_hash>/kits/<kit_hash>/` - `inst-git-cache-artifact-layout`
7. [ ] - `p1` - Write artifact manifests with schema version, source type, decoded remote URL hash, selected subdirectory, kit identity, requested ref, resolved commit SHA, artifact kind, creation time, validation basis, and optional redacted remote display - `inst-git-cache-manifest`
8. [ ] - `p1` - Never include decoded URLs, tokens, query strings, raw refs, usernames, passwords, or helper values in cache paths - `inst-git-cache-no-secrets-in-paths`

### Generic Git Provenance Registration

- [ ] `p1` - **ID**: `cpt-studio-algo-generic-git-kit-installer-provenance`

**Input**: Installed kit slug, parsed source object, ref resolution result, cache result, verification state

**Output**: Updated `core.toml` kit registration

**Rules**:
1. [ ] - `p1` - Set `source_type = "git"` only for persisted `git:` sources; keep `source_type = "github"` reserved for `github:` sources - `inst-git-prov-source-type`
2. [ ] - `p1` - Persist original source string, decoded remote URL, requested ref, resolved commit SHA, selected subdirectory, kit identity, `resolution_basis`, freshness, and verification state - `inst-git-prov-source-provenance`
3. [ ] - `p1` - Add optional `source_provenance` schema fields for source type, original source, canonical source, decoded remote URL, requested ref, selected subdirectory, kit identity, resolution basis, and freshness - `inst-git-prov-schema-source`
4. [ ] - `p1` - Add optional `content_identity` schema fields where `vcs = "git"` and `commit_sha` is the primary immutable identity - `inst-git-prov-schema-content`
5. [ ] - `p1` - Preserve local/path kit entries as valid without `source_provenance` or `content_identity` - `inst-git-prov-local-compatible`
6. [ ] - `p1` - Do not migrate existing `github:` entries to `git:` automatically - `inst-git-prov-no-github-migration`
7. [ ] - `p1` - Do not apply GitHub release, latest-release, API, mirror, or tarball semantics to generic `git:` sources, including GitHub-hosted Git URLs - `inst-git-prov-no-github-semantics`

### Generic Git URL Normalization

- [ ] `p1` - **ID**: `cpt-studio-algo-generic-git-kit-installer-url-normalization`

**Input**: Decoded credential-free Git URL

**Output**: Conservative normalized identity and canonical persisted source encoding

**Rules**:
1. [ ] - `p1` - Lowercase URL scheme and host when present - `inst-git-url-lower-scheme-host`
2. [ ] - `p1` - Remove default ports for recognized transports - `inst-git-url-default-ports`
3. [ ] - `p1` - Preserve path bytes and do not normalize repository path case - `inst-git-url-preserve-path`
4. [ ] - `p1` - Do not collapse HTTPS, SSH, scp-like, and `file://` transports into a shared identity - `inst-git-url-preserve-transport`
5. [ ] - `p1` - Do not collapse `repo` and `repo.git` - `inst-git-url-preserve-dot-git`
6. [ ] - `p1` - Do not apply GitHub-specific host/path equivalence to generic Git URLs - `inst-git-url-no-github-equivalence`
7. [ ] - `p1` - Reject credential-bearing, query-bearing, or fragment-bearing URLs before producing normalized identity - `inst-git-url-policy-before-hash`
8. [ ] - `p1` - Use both a pre-resolution lookup key and an immutable content key for cache and currentness operations - `inst-git-url-lookup-content-keys`

### Generic Git Auth Runtime

- [ ] `p1` - **ID**: `cpt-studio-algo-generic-git-kit-installer-auth-runtime`

**Input**: CLI/config runtime auth options and ambient environment

**Output**: Runtime-only resolver auth object for Git subprocess calls

**Rules**:
1. [ ] - `p1` - Support ambient Git authentication through SSH agent/config and Git credential helpers when `allow_ambient_git_auth = true` - `inst-git-auth-ambient`
2. [ ] - `p1` - Support non-persistent runtime values in `git_auth.env`, `git_auth.ssh_command`, `git_auth.askpass_command`, and `git_auth.credential_helper_config` - `inst-git-auth-runtime-object`
3. [ ] - `p1` - Default runtime auth object to `allow_ambient_git_auth = true`, empty env, null SSH/askpass command, empty helper config, and `persist = false` - `inst-git-auth-defaults`
4. [ ] - `p1` - Treat auth options as secret-bearing except non-secret boolean capability flags and labels - `inst-git-auth-secret-classification`
5. [ ] - `p1` - Never serialize, log, cache, persist, or include auth values in provenance, lock files, errors, or effective URL displays - `inst-git-auth-no-persist`
6. [ ] - `p1` - Allow diagnostics-only facts such as auth mode, transport, and conservative credential source kind when they contain no secret material - `inst-git-auth-safe-diagnostics`

## 4. States (CDSL)

### Generic Git Kit Source State

- [ ] `p1` - **ID**: `cpt-studio-state-generic-git-kit-installer-source`

```
[UNREGISTERED] --install-online--> [REGISTERED_VERIFIED]
[REGISTERED_VERIFIED] --mutable-ref-same-sha--> [CURRENT_VERIFIED]
[REGISTERED_VERIFIED] --mutable-ref-new-sha--> [UPDATE_AVAILABLE_VERIFIED]
[REGISTERED_VERIFIED] --offline-matching-cache--> [OFFLINE_LAST_KNOWN]
[OFFLINE_LAST_KNOWN] --online-reverify-same-sha--> [CURRENT_VERIFIED]
[OFFLINE_LAST_KNOWN] --online-reverify-new-sha--> [UPDATE_AVAILABLE_VERIFIED]
[REGISTERED_VERIFIED] --explicit-full-commit--> [PINNED_COMMIT]
[PINNED_COMMIT] --same-commit--> [CURRENT_VERIFIED]
```

**State Rules**:
1. [ ] - `p1` - `OFFLINE_LAST_KNOWN` is a freshness marker, not a selector classification - `inst-git-state-offline-marker`
2. [ ] - `p1` - `PINNED_COMMIT` requires an explicit full commit selector, not a cached resolution of a mutable ref - `inst-git-state-pinned-explicit`
3. [ ] - `p1` - `UPDATE_AVAILABLE_VERIFIED` is determined by comparing prior and newly resolved commit SHA - `inst-git-state-update-by-sha`

## 5. Definitions of Done

### Generic Git Source Grammar

- [x] `p1` - **ID**: `cpt-studio-dod-generic-git-kit-installer-source-grammar`

The system **MUST** accept `git/<encoded-url>[//<subdir>][@<kit>]` at the CLI and persist equivalent sources as `git:<encoded-url>[//<subdir>][@<kit>]`.

**Implements**:
- `cpt-studio-flow-generic-git-kit-installer-install`
- `cpt-studio-algo-generic-git-kit-installer-source-parse`
- `cpt-studio-algo-generic-git-kit-installer-url-normalization`

### Git Ref Resolution via `--version`

- [x] `p1` - **ID**: `cpt-studio-dod-generic-git-kit-installer-version-ref`

The system **MUST** resolve `--version` as a Git ref/tag/branch/commit selector for generic Git sources and persist both requested selector and resolved commit SHA.

**Implements**:
- `cpt-studio-flow-generic-git-kit-installer-install`
- `cpt-studio-flow-generic-git-kit-installer-update`
- `cpt-studio-algo-generic-git-kit-installer-ref-resolution`

### Generic Git Provenance and Schema

- [x] `p1` - **ID**: `cpt-studio-dod-generic-git-kit-installer-provenance`

The system **MUST** persist generic Git source provenance and content identity without breaking existing GitHub or local/path registrations.

**Implements**:
- `cpt-studio-algo-generic-git-kit-installer-provenance`

### Cache and Offline Fallback

- [x] `p1` - **ID**: `cpt-studio-dod-generic-git-kit-installer-cache-offline`

The system **MUST** cache generic Git content by hashed structured identity and allow offline fallback only when cached content proves the same remote, ref, subdir, kit identity, and resolved commit SHA.

**Implements**:
- `cpt-studio-flow-generic-git-kit-installer-update`
- `cpt-studio-algo-generic-git-kit-installer-fetch-cache`
- `cpt-studio-state-generic-git-kit-installer-source`

### Auth and Redaction

- [x] `p1` - **ID**: `cpt-studio-dod-generic-git-kit-installer-auth-redaction`

The system **MUST** keep Git credentials outside source grammar, cache identity, provenance, logs, errors, and lock files while still allowing runtime-only Git authentication.

**Implements**:
- `cpt-studio-algo-generic-git-kit-installer-source-policy`
- `cpt-studio-algo-generic-git-kit-installer-auth-runtime`

## 6. Implementation Modules

- `skills/studio/scripts/studio/commands/kit.py` - CLI dispatch for install/update source mode selection
- `skills/studio/scripts/studio/kit_manager.py` - install/update delegation, kit registration, and manifest-aware content application
- `skills/studio/scripts/studio/utils/git_source.py` - generic Git source parsing, normalization, ref resolution, and redaction helpers
- `skills/studio/scripts/studio/utils/kit_cache.py` - generic Git cache namespace, artifact manifest, and offline fallback helpers
- `schemas/core.schema.json` - optional kit registration schema for `source_provenance` and `content_identity`
- `tests/test_kit_generic_git_source.py` - parser, normalization, policy, dispatch, cache, offline, and auth redaction contract tests

## 7. Acceptance Criteria

- [ ] `cfs kit install git/<encoded-url> --version <ref>` installs a kit from a non-GitHub remote and records `source_type = "git"`, requested ref, and resolved commit SHA.
- [ ] `cfs kit update <kit>` for a generic Git registered kit resolves mutable refs by commit SHA and runs the existing file-level diff/update path.
- [ ] Existing `github:` registrations and GitHub shorthand installs continue to use GitHub release/tag authority and are not migrated to generic Git.
- [ ] Local/path kits remain valid without `source_provenance` or `content_identity`.
- [ ] Credentialed URLs, query strings, and fragments are rejected with stable error codes and sanitized diagnostics.
- [ ] Cache paths contain only stable hashes and never contain decoded remotes, raw refs, usernames, passwords, tokens, query strings, or fragments.
- [ ] Offline fallback never rewrites source to a local cache path and never converts mutable refs into pinned commits.
- [ ] Unit tests include fixture repositories with branch, tag, default branch, full commit, SSH/scp-like parsing, `file://`, subdirectory, and kit identity cases.
