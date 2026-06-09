# Change Impact Report: cpt-studio-featstatus-kit-management

## Summary

- **Mode**: cascade-tracking
- **Upstream artifact**: FEATURE `architecture/features/kit-management.md`
- **Upstream ID**: `cpt-studio-featstatus-kit-management`
- **Baseline ref**: `origin/main` (`50559f60b1fe78f46d9017ea44e3b841c5b1343d`)
- **Current ref**: `HEAD` plus working tree changes
- **Diff size**: `247` insertions, `44` deletions in `architecture/features/kit-management.md`
- **Configured thresholds**: `stale_flag_threshold = 30` days; `marker_coverage_threshold = 80`; FEATURE cascade depth limit `2`

The change expands kit management from legacy manifest/layout behavior toward a canonical `.cf-studio-kit.toml` and shared `KitModel` service boundary. It adds or rewrites requirements for local copy/register install mode, public skill/subagent generation, manifest normalization, drift/prune handling, tool-risk fingerprints, variable resolution, and `cfs info` kit model output.

High-impact cascade findings:

- New or substantially changed feature IDs are mostly self-contained in `architecture/features/kit-management.md`.
- Downstream artifact references outside the changed feature are limited and do not show stale timestamps beyond the configured 30-day threshold.
- No `@cpt-*` code markers were found for the changed ID set in `src` or `skills/studio/scripts/studio`.
- The affected implementation surface has coverage gaps: `skills/studio/scripts/studio/commands/kit.py` is below the configured 80% file threshold, and two newly declared implementation modules do not exist.

## Cascade tree

```text
cpt-studio-featstatus-kit-management
└── architecture/features/kit-management.md (FEATURE, changed upstream artifact)
    ├── New / changed algorithm and state IDs
    │   ├── cpt-studio-algo-kit-model-normalize
    │   ├── cpt-studio-algo-kit-canonical-manifest
    │   ├── cpt-studio-algo-kit-local-path-install-mode
    │   ├── cpt-studio-algo-kit-info-model-output
    │   ├── cpt-studio-algo-kit-public-component-generation
    │   ├── cpt-studio-algo-kit-variable-resolution
    │   ├── cpt-studio-algo-kit-update-drift-prune
    │   ├── cpt-studio-algo-kit-tool-permission-risk
    │   ├── cpt-studio-algo-kit-manifest-normalize
    │   ├── cpt-studio-state-kit-manifest
    │   └── cpt-studio-state-kit-install-mode
    ├── Existing IDs with changed semantics/status
    │   ├── cpt-studio-flow-kit-install-cli
    │   ├── cpt-studio-flow-kit-update-cli
    │   ├── cpt-studio-algo-kit-install
    │   ├── cpt-studio-algo-kit-update
    │   ├── cpt-studio-algo-kit-manifest-install
    │   ├── cpt-studio-algo-kit-manifest-legacy-migration
    │   ├── cpt-studio-algo-kit-manifest-resolve
    │   └── cpt-studio-algo-kit-manifest-source-mapping
    ├── Downstream artifact references outside kit-management.md
    │   ├── architecture/DESIGN.md:298 references cpt-studio-adr-unified-manifest-hierarchy
    │   ├── architecture/features/project-extensibility.md:120 references cpt-studio-adr-unified-manifest-hierarchy
    │   ├── architecture/features/version-config.md:87 references cpt-studio-algo-kit-manifest-legacy-migration
    │   ├── architecture/DECOMPOSITION.md:119 references cpt-studio-adr-remove-blueprint-system
    │   ├── architecture/DESIGN.md:195 references cpt-studio-adr-remove-blueprint-system
    │   ├── architecture/DESIGN.md:280 references cpt-studio-adr-remove-blueprint-system
    │   ├── architecture/DESIGN.md:474 references cpt-studio-adr-remove-blueprint-system
    │   └── architecture/DESIGN.md:1437 references cpt-studio-adr-remove-blueprint-system
    └── Declared implementation modules
        ├── skills/studio/scripts/studio/commands/kit.py (exists; 73% file coverage)
        ├── skills/studio/scripts/studio/utils/kit_model.py (missing)
        ├── skills/studio/scripts/studio/utils/manifest.py (exists; 97% file coverage)
        ├── skills/studio/scripts/studio/commands/info.py (missing)
        └── skills/studio/scripts/studio/commands/agents.py (exists; 98% file coverage)
```

## Coverage gaps

- **Gap: no code marker evidence for changed IDs**
  - Evidence: `rg` for the changed ID set under `src` and `skills/studio/scripts/studio` returned no `@cpt-*` matches.
  - Impact: the new and changed FEATURE requirements currently have no direct code traceability marker evidence.

- **Gap: affected file below configured marker coverage threshold**
  - Evidence: `cfs spec-coverage --system studio --min-coverage 80 --verbose`
  - Result: overall system coverage passed at `91.1%`, but `skills/studio/scripts/studio/commands/kit.py` is `73%`, below the configured `80%` marker coverage threshold.

- **Gap: declared implementation modules missing**
  - `skills/studio/scripts/studio/utils/kit_model.py` is declared for `cpt-studio-algo-kit-model-normalize`, `cpt-studio-algo-kit-canonical-manifest`, `cpt-studio-algo-kit-public-component-generation`, `cpt-studio-algo-kit-tool-permission-risk`, and `cpt-studio-algo-kit-manifest-normalize`, but the file does not exist.
  - `skills/studio/scripts/studio/commands/info.py` is declared for `cpt-studio-algo-kit-info-model-output`, but the file does not exist.

## Stale flags

No stale flags exceeded the configured `30` day threshold.

Downstream last-update evidence:

- `architecture/ADR/0012-cpt-studio-adr-git-style-conflict-markers-v1.md`: last commit `2026-05-25`
- `architecture/ADR/0013-cpt-studio-adr-extract-sdlc-kit-to-github-v1.md`: last commit `2026-05-25`
- `architecture/ADR/0020-cpt-studio-adr-rebrand-and-mirror-override-v1.md`: last commit `2026-05-26`
- `architecture/DECOMPOSITION.md`: last commit `2026-06-08`
- `architecture/DESIGN.md`: last commit `2026-06-07`
- `architecture/features/project-extensibility.md`: last commit `2026-05-25`
- `architecture/features/version-config.md`: last commit `2026-06-01`

As of `2026-06-09`, all listed downstream artifacts are within 30 days of last modification.

## Traceability evidence

Commands run:

```text
cfs where-defined --id cpt-studio-featstatus-kit-management
cfs list-ids --kind feature
git diff --stat origin/main -- architecture/features/kit-management.md
git diff --unified=0 origin/main -- architecture/features/kit-management.md
cfs where-used --id <changed-id>
rg -n '@cpt-(changed-id-set)' src skills/studio/scripts/studio
cfs spec-coverage --system studio --min-coverage 80 --verbose
git log -1 --format='%cs %h %s' -- <downstream-file>
```

Key direct evidence:

- `architecture/features/kit-management.md:62`: defines `cpt-studio-featstatus-kit-management`
- `architecture/features/kit-management.md:523`: defines `cpt-studio-algo-kit-model-normalize`
- `architecture/features/kit-management.md:542`: defines `cpt-studio-algo-kit-canonical-manifest`
- `architecture/features/kit-management.md:561`: defines `cpt-studio-algo-kit-local-path-install-mode`
- `architecture/features/kit-management.md:579`: defines `cpt-studio-algo-kit-info-model-output`
- `architecture/features/kit-management.md:594`: defines `cpt-studio-algo-kit-public-component-generation`
- `architecture/features/kit-management.md:609`: defines `cpt-studio-algo-kit-variable-resolution`
- `architecture/features/kit-management.md:623`: defines `cpt-studio-algo-kit-update-drift-prune`
- `architecture/features/kit-management.md:639`: defines `cpt-studio-algo-kit-tool-permission-risk`
- `architecture/features/kit-management.md:653`: defines `cpt-studio-algo-kit-manifest-normalize`
- `architecture/features/kit-management.md:779`: defines `cpt-studio-state-kit-manifest`
- `architecture/features/kit-management.md:791`: defines `cpt-studio-state-kit-install-mode`
- `architecture/features/kit-management.md:848`: maps changed flow/algo IDs to `skills/studio/scripts/studio/commands/kit.py`
- `architecture/features/kit-management.md:849`: maps new `KitModel` and public-generation IDs to missing `skills/studio/scripts/studio/utils/kit_model.py`
- `architecture/features/kit-management.md:850`: maps manifest and variable-resolution IDs to `skills/studio/scripts/studio/utils/manifest.py`
- `architecture/features/kit-management.md:853`: maps `cpt-studio-algo-kit-info-model-output` to missing `skills/studio/scripts/studio/commands/info.py`
- `architecture/features/kit-management.md:854`: maps `cpt-studio-algo-kit-public-component-generation` to `skills/studio/scripts/studio/commands/agents.py`
