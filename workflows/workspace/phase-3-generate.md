---
cf: true
type: workflow
parent: workflows/workspace.md
description: "Invoke when the workspace workflow enters Phase 3 to write standalone or inline workspace configuration via CLI."
---

<!-- toc -->

- [Phase 3: Generate](#phase-3-generate)

<!-- /toc -->

## Phase 3: Generate

**Goal**: write the workspace config.

Prerequisite: `WORKSPACE_ALL_SOURCES_CONFIRMED=true`. If the flag is unset,
fail-stop and route back to `workflows/workspace/phase-2-configure.md`; Phase 3
MUST NOT infer confirmation from partially edited source proposals.

Also require a valid final workspace location for the selected sources before
invoking the CLI:

- standalone mode → `{project_root}/.studio-workspace.toml` must be the
  final confirmed destination
- inline mode → `{project_root}/config/core.toml` must be the final confirmed
  destination and no selected source may use a Git URL

If the final location is unresolved or invalid for the selected source set,
fail-stop and route back to `workflows/workspace/phase-2-configure.md`. Do NOT
attempt Phase 3 with `--inline` against a Git URL source set.

Set CF_PHASE_GATE=released_for_orchestrator_write with scope =
`{workspace_config_path}` before invoking the workspace CLI.

`workspace_config_path` is always a file path or path-prefix accepted by the
gate:

- standalone mode → `{project_root}/.studio-workspace.toml`
- inline mode → `{project_root}/config/core.toml`

The logical `[workspace]` TOML section is part of the inline write target, but
it is **not** itself a valid gate scope.

| Action | Command |
|---|---|
| Initialize workspace | `{cfs_cmd} --json workspace-init [--root <super-root>] [--output <path>] [--inline] [--force] [--dry-run]` |
| Add one source | `{cfs_cmd} --json workspace-add --name <name> (--path <path> \| --url <url>) [--branch <branch>] [--role <role>] [--adapter <path>] [--inline]` |

`workspace-init` writes standalone config by default; `--inline` writes
`[workspace]` into `config/core.toml`. `workspace-add` auto-detects workspace
type unless `--inline` forces inline mode. Git URL sources are not supported
inline.

Reset CF_PHASE_GATE=armed immediately after the CLI returns — success or
failure.

**On CLI failure**: Report the CLI exit code and error message to the user. Do NOT continue to `workflows/workspace/phase-4-validate.md`. Offer the user a structured choice:

| Option | Action |
|---|---|
| 1 | Retry the workspace generate CLI command (suggested for transient failures) |
| 2 | Reconfigure — return to Phase 2 to adjust the workspace config |
| 3 | Stop workspace setup |

Suggested: 1 if the error message mentions a path collision or locked file (transient); Suggested: 2 if the error references invalid config values or missing required fields.

Reply `1`, `2`, or `3` (per `workflows/shared/stop-token-policy.md`). No
manual partial-write rollback is needed — the CLI is responsible for atomicity.
