---
cf: true
type: requirement
name: Workspace Setup Reference
version: 1.0
purpose: Reference detail for the cf-workspace skill — command surface, config sections, edit routing, sync preference rules, validation checks, and terminal-record shapes
---

# Workspace Setup Reference

Reference data loaded by the `cf-workspace` skill. This document is the
workspace knowledge base: it enumerates the supported CLI commands, the config
surface that must be edited directly, sync-targeting rules, and the minimum
validation expected after writes.

## Decision Framing (why each prompt is asked)

- **Repo selection** — choose which discovered repositories become workspace sources
  before deciding where the config lives. Reply with comma- or space-separated numbers,
  names, or the word `all`. Suggested default: include all repos that have the expected adapter.
- **Storage mode** — determines where the workspace config lives and whether it can track
  Git URL sources. Suggested: `standalone` unless the config must live inside `config/core.toml`.
- **Source confirmation** — confirm the exact source settings before writing config.
  Suggested defaults: keep the detected `adapter`, keep `cross_repo = yes`, keep
  `resolve_remote_ids = yes` unless stricter local-only behavior is wanted.
- **Minimal-gate routing** — when the user already supplied a safe, specific request
  such as "show workspace status", "sync source docs", or "set cross_repo = false",
  prefer direct execution over a menu or wizard.

## Source Fields (confirmed per source)

`name`, relative `path` or `url`, `role`, `adapter`, optional `branch`, workspace
`location`, and the workspace-level sections `[traceability]`, `[resolve]`, `[validation]`.

- `cross_repo` defaults to `yes`; `resolve_remote_ids` defaults to `yes`.
- Both must be `yes` to include remote IDs.
- The primary source is always the current working directory; there is no `primary` field.
- Confirmation is tracked per source individually; any source edit re-requires re-confirmation of that source.

## Workspace Config Surface

- Source entry fields:
  `path`, `url`, `branch`, `role`, `adapter`
- Workspace sections:
  `[traceability]` with `cross_repo`, `resolve_remote_ids`
- `[resolve]` with `workdir`, `namespace.<host> = "{org}/{repo}"`-style mappings
- `[validation]` with `allowed_content_languages`, `ignore_paths`

## Operation Routing

- Prefer CLI writes when a matching command exists:
  `workspace-init`, `workspace-add`, `workspace-sync`
- Prefer direct config edits when the CLI has no dedicated mutation:
  remove source, rename source, rewrite source fields, change storage mode,
  update `[traceability]`, update `[resolve]`, update `[validation]`
- Prefer read-only CLI for diagnostics and discovery:
  `workspace-info`, `list-ids`, `where-defined`, `where-used`, `validate`, `map`
- When a source path, repo name, URL, branch, or ID implies one workspace source,
  route to that source instead of broad workspace-wide commands when possible.

## Storage Modes

- `standalone` → write `{project_root}/.cf-workspace.toml`, separate from `config/core.toml`.
- `inline` → write `[workspace]` inside `{project_root}/config/core.toml`.
- **Inline is NOT available when any selected source is a Git URL.** On an inline+URL conflict, emit
  exactly: `Inline storage is not supported for Git URL sources; please choose standalone storage or change the selected repos.` then reset to standalone.

## CLI Commands

- Initialize: `{cfs_cmd} --json workspace-init [--root <super-root>] [--output <path>] [--inline] [--force] [--dry-run]`
- Add source: `{cfs_cmd} --json workspace-add --name <name> (--path <path> | --url <url>) [--branch <branch>] [--role <role>] [--adapter <path>] [--inline]`
- Status: `{cfs_cmd} --json workspace-info`
- Sync Git URL sources: `{cfs_cmd} --json workspace-sync [--source <name>] [--dry-run] [--force]`
- `workspace-init` writes standalone by default; `--inline` writes `[workspace]` into `config/core.toml`. Git URL sources are not supported inline. The CLI is responsible for write atomicity.

## Workspace-Aware Read-Only Commands

- Visible IDs: `{cfs_cmd} --json list-ids [--source <name>]`
- Definition lookup: `{cfs_cmd} --json where-defined --id <id>`
- Usage lookup: `{cfs_cmd} --json where-used --id <id>`
- Validation: `{cfs_cmd} --json validate [--source <name> | --local-only]`
- Dependency and traceability map: `{cfs_cmd} --json map [--local-only]`

## Sync Preference

- Prefer `workspace-sync --source <name>` whenever the user names a source or a
  single relevant source can be inferred from the request.
- Use full `workspace-sync` only when the user explicitly requests all Git URL
  sources or the target source cannot be narrowed safely.
- Use `--dry-run` when the user asks for a preview.
- Treat `--force` as destructive because it may discard local changes in the
  synced worktree; require a dedicated confirmation only for that case.

## Phase 4 Validation Checks

1. `{cfs_cmd} --json workspace-info` — workspace status.
2. Per-source health — path exists; adapter found if expected; `artifacts.toml` valid when an adapter exists; at least one system if an adapter exists.
3. `{cfs_cmd} --json list-ids` — cross-repo IDs.
4. `{cfs_cmd} --json validate` — cross-repo validation.

Recommended targeted follow-ups:

5. `{cfs_cmd} --json list-ids --source <name>` when a write affected one source.
6. `{cfs_cmd} --json where-defined --id <id>` when a traceability or source-routing edit must be verified against a specific ID.
7. `{cfs_cmd} --json map [--local-only]` when debugging federation reachability or cross-repo dependency visibility.

Report total sources, reachable sources, sources with adapters, and available cross-repo IDs.

- **Critical failures** = sources with expected adapters not found, OR cross-repo validation FAIL.
- **Graceful degradation** = missing repos emit warnings (not errors); available sources keep working;
  remote IDs from missing sources are unavailable; explicit `source` entries to missing repos resolve to None.

## Write Discipline

- `CF_PHASE_GATE` is an external session-scoped protocol variable (defined in the studio protocol), not workflow STATE.
  Set it to `released_for_orchestrator_write` (scoped to the config path) before the write CLI and back to `armed` immediately after the CLI returns.
- Never write workspace config until the final location is valid and the target section or source entry is unambiguous.
- Preserve unrelated workspace sections and sources during manual config edits.
- Keep menus and confirmations to the minimum required for safety:
  read-only operations do not need gates; non-destructive explicit edits do not need confirmation; only force/overwrite/migration paths need a gate.

## Terminal Records

Every phase emits exactly one of these before its STOP_TURN or continuation:

```text
{ "type": "WORKSPACE_STATUS", "phase": "<id>", "status": "pending|complete|invalid|failed", "next_route": "<WS_*|null>" }
{ "type": "WORKSPACE_VALIDATION", "status": "PASS|FAIL|WARN", "checked_sources": [], "issues": [] }
{ "type": "WORKSPACE_FAILURE", "phase": "<id>", "reason": "<one-line>", "recovery": "<next action>" }
```
