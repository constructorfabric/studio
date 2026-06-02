---
cf: true
type: requirement
name: Multi-Repo Workspace
version: 1.0
purpose: Define workspace federation for multi-repo traceability
---
# Studio Workspace Specification

<!-- toc -->

- [Overview](#overview)
- [Configuration](#configuration)
- [Source Entries](#source-entries)
- [Discovery and Path Resolution](#discovery-and-path-resolution)
- [Cross-Repo Traceability](#cross-repo-traceability)
- [Operations](#operations)
- [Compatibility and Degradation](#compatibility-and-degradation)
- [Git URL Sources](#git-url-sources)
- [Cross-Repo Editing](#cross-repo-editing)
- [Examples](#examples)

<!-- /toc -->

## Overview
Studio workspaces provide an opt-in federation layer for multi-repo projects. Each repo keeps its own adapter; the workspace maps named sources so artifacts, code, and kits can resolve across repos without merging adapters.
**Project root** = the repository root containing the adapter directory (default `.cf-studio/`; legacy / self-hosted exceptions: `.bootstrap/`, `studio/`).

```pdsl
UNIT WorkspacePrinciples

PURPOSE:
  Enforce core behavioral invariants for the Studio workspace federation layer.

RULES:
  - ALWAYS set the primary source to the repo containing the current working directory; the primary field does not exist
  - ALWAYS use a remote source's own adapter rules/templates/constraints when the remote source has one
  - ALWAYS preserve exact single-repo behavior when no workspace config exists
  - ALWAYS restrict inline workspace config to local paths only; allow local paths and Git URLs only in standalone config
  - ALWAYS warn when a source is missing
  - NEVER block available sources due to a missing source
```

## Configuration
Workspaces can be standalone or inline.
**Standalone** (`.studio-workspace.toml`):
```toml
version = "1.0"
[sources.docs-repo]
path = "../docs-repo"
adapter = ".cf-studio"
role = "artifacts"
[traceability]
cross_repo = true
resolve_remote_ids = true
```
**Inline** (`config/core.toml`):
```toml
workspace = "../.studio-workspace.toml"
[workspace.sources.docs]
path = "../docs-repo"
[workspace.sources.shared-kits]
path = "../shared-kits"
role = "kits"
```
## Source Entries
`adapter` means the source's Studio directory containing `.core/`, `.gen/`, and `config/`. If omitted, Studio auto-discovers it from the source's `AGENTS.md`.
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `path` | string | Yes unless `url` is set | — | Local path; if both exist, `path` wins over `url`. |
| `url` | string | No; standalone only | — | HTTPS/SSH Git remote; forbidden in inline config. |
| `branch` | string | No; only with `url` | remote default | Rejected on path-only sources. |
| `adapter` | string | No | auto-discover | Path to adapter directory in the source repo. |
| `role` | string | No | `full` | Contribution scope. |
Roles: `artifacts`, `codebase`, `kits`, `full`.

## Discovery and Path Resolution

```pdsl
UNIT WorkspaceDiscovery

PURPOSE:
  Locate the workspace configuration and resolve all source and artifact paths.

WHEN:
  - REQUIRE Studio initialization begins

DO:
  - LOAD workspace config by checking config/core.toml for workspace key first
  - LOAD external .studio-workspace.toml when config/core.toml workspace value is a string; resolve relative to project root
  - LOAD inline workspace definition when config/core.toml workspace value is a table; resolve source paths relative to project root
  - LOAD .studio-workspace.toml at project root when config/core.toml has no workspace key
  - SET mode: single-repo when no workspace config is found

RULES:
  - NEVER traverse parent directories implicitly to locate workspace config
  - ALWAYS resolve external workspace path in core.toml relative to project root
  - ALWAYS resolve standalone source path relative to the workspace file's parent directory
  - ALWAYS resolve inline source path relative to project root
  - ALWAYS resolve artifact/codebase/kit entries with source field relative to the named source root
  - ALWAYS resolve entries without source field locally for backward compatibility
```

`artifacts.toml` v1.2 adds optional `source` on artifacts, codebase entries, and kits. When absent, v1.0/v1.1 behavior remains unchanged.

## Cross-Repo Traceability

| Setting | Default | Effect |
|---|---|---|
| `cross_repo` | `true` | Enable workspace-aware ID collection and path resolution |
| `resolve_remote_ids` | `true` | Expand remote IDs into the validation union set |

```pdsl
UNIT WorkspaceTraceability

PURPOSE:
  Enforce cross-repo ID collection and path resolution when workspace federation is active.

WHEN:
  - REQUIRE traceability.cross_repo = true
  - AND traceability.resolve_remote_ids = true

DO:
  - RUN validate collecting IDs from all reachable sources; accept remote @cpt-* references
  - RUN where-defined, where-used, and list-ids across reachable sources
  - RETURN None for missing or unreachable source in resolve_artifact_path

RULES:
  - ALWAYS require both cross_repo = true and resolve_remote_ids = true to include remote IDs
  - ALWAYS restrict validation to the current repo when validate --local-only is used
  - ALWAYS resolve artifact paths with no source field relative to local project root
  - ALWAYS resolve artifact paths with reachable source field relative to the named source root
  - NEVER silently fall back to local when source is missing or unreachable; return None

ON_ERROR:
  scan failure -> EMIT "Warning: failed to scan IDs from <path>: <reason>" and continue
```

## Operations

| Command | Purpose |
|---|---|
| `workspace-init` | Scan nested repos and generate standalone workspace config |
| `workspace-init --inline` | Initialize inline workspace in `config/core.toml` |
| `workspace-add --name N --path P` | Add a local source; auto-detect standalone vs inline |
| `workspace-add --name N --url U` | Add a Git URL source to standalone config |
| `workspace-info` | Show config and per-source reachability/adapter status |
| `workspace-sync [--source <name>] [--dry-run] [--force]` | Fetch/update Git URL source worktrees |
| `validate --local-only` | Skip cross-repo ID resolution |
| `validate --source <name>` / `list-ids --source <name>` | Scope operations to one source |

```pdsl
UNIT WorkspaceSyncAndOperations

PURPOSE:
  Define sync behavior and operational constraints for workspace source management.

WHEN:
  - REQUIRE workspace-sync is invoked
  - OR workspace source management operations are performed

DO:
  - LOAD URL source by cloning on first access
  - CONTINUE with available sources; skip local path sources during sync

RULES:
  - ALWAYS require explicit workspace-sync for network updates to URL sources after initial clone
  - NEVER auto-fetch existing clones during ordinary resolution
  - ALWAYS treat workspace-sync --force as destructive; it may discard uncommitted changes or local commits
  - ALWAYS skip local path sources during sync
  - NEVER use workspace-remove command; edit config directly then run workspace-info to reflect changes
  - ALWAYS switch workspace mode by deleting current config, rerunning workspace-init or workspace-init --inline, then re-adding sources
```

## Compatibility and Degradation

- Existing v1.0/v1.1 registries without `source` fields remain valid.
- Workspace imports stay lazy inside functions.
- Global context may be `StudioContext` or `WorkspaceContext`; `is_workspace()` distinguishes them.

```pdsl
UNIT WorkspaceDegradation

PURPOSE:
  Define graceful degradation behavior when workspace sources are unavailable or missing.

WHEN:
  - REQUIRE a workspace source is missing or unreachable

DO:
  - EMIT warning in workspace-info output for the missing source
  - SET source reachability: reachable = false
  - CONTINUE with available sources
  - RETURN None for remote IDs and unresolved explicit-source artifacts from the missing source

RULES:
  - ALWAYS treat missing source as non-fatal; no error exit caused solely by a missing repo
  - ALWAYS preserve exact single-repo behavior when no workspace config exists
```

## Git URL Sources

Git URL sources are supported only in standalone `.studio-workspace.toml`.

```toml
version = "1.0"
[resolve]
workdir = ".workspace-sources"
[resolve.namespace]
"gitlab.com" = "{org}/{repo}"
[sources.backend]
url = "https://gitlab.com/myteam/backend.git"
branch = "main"
role = "codebase"
```

```pdsl
UNIT WorkspaceGitUrlSources

PURPOSE:
  Enforce rules for Git URL sources in standalone workspace configuration.

WHEN:
  - REQUIRE a Git URL source is configured or accessed

RULES:
  - NEVER allow Git URLs in inline workspace config
  - ALWAYS match namespace rules on exact host names; fall back to {org}/{repo} when no matching rule
  - ALWAYS use the remote default branch when branch is not specified
  - NEVER fetch existing clones during ordinary resolution; only workspace-sync may update them
  - ALWAYS resolve resolve.workdir relative to the standalone workspace file's parent
  - ALWAYS apply containment checks to resolved clone paths
  - NEVER allow traversal or symlink escape in resolved clone paths
```

## Cross-Repo Editing

```pdsl
UNIT WorkspaceCrossRepoEditing

PURPOSE:
  Define adapter selection rules for validation and generation targeting remote sources.

WHEN:
  - REQUIRE validation or generation targets a remote source

RULES:
  - ALWAYS use the remote source's adapter for validation and generation when the remote source has one
  - ALWAYS fall back to the primary repo's adapter when the remote source has no adapter
  - ALWAYS keep the primary repo's adapter active for its own files and workspace-level operations
```

## Examples

### Example: Inline docs source from code repo

```text
workspace/
├── docs-repo/      (AGENTS.md, studio/config/artifacts.toml)
├── code-repo/      (AGENTS.md, .bootstrap/config/core.toml)  ← cwd
└── shared-kits/    (kits/sdlc)
```

Running `cf validate` from `code-repo/` loads `code-repo/.bootstrap`, discovers the workspace in `config/core.toml`, loads `docs-repo` artifacts, and accepts `@cpt-*` references to IDs defined there.

### Example: Parent workspace with nested repos

```text
parent/
├── .studio-workspace.toml
├── frontend/
├── backend/
└── docs/
```

Running `cf workspace-init` from `parent/` will discover `frontend`, `backend`, and `docs` as nested sub-directories and generate the workspace config.
