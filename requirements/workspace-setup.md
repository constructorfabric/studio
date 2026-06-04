---
cf: true
type: requirement
name: Workspace Setup Reference
version: 1.0
purpose: Reference detail for the cf-workspace skill — decision framing, source fields, storage modes, validation checks, and terminal-record shapes
---

# Workspace Setup Reference

Reference data loaded by the `cf-workspace` skill. The skill's menus stay compact and
the controller renders the full "why this input is needed" framing, field lists, and
suggested defaults from this document at each decision point.

## Decision Framing (why each prompt is asked)

- **Repo selection** — choose which discovered repositories become workspace sources
  before deciding where the config lives. Reply with comma- or space-separated numbers,
  names, or the word `all`. Suggested default: include all repos that have the expected adapter.
- **Storage mode** — determines where the workspace config lives and whether it can track
  Git URL sources. Suggested: `standalone` unless the config must live inside `config/core.toml`.
- **Source confirmation** — confirm the exact source settings before writing config.
  Suggested defaults: keep the detected `adapter`, keep `cross_repo = yes`, keep
  `resolve_remote_ids = yes` unless stricter local-only behavior is wanted.

## Source Fields (confirmed per source)

`name`, relative `path` or `url`, `role`, `adapter`, `cross_repo`, `resolve_remote_ids`, workspace `location`.

- `cross_repo` defaults to `yes`; `resolve_remote_ids` defaults to `yes`.
- Both must be `yes` to include remote IDs.
- The primary source is always the current working directory; there is no `primary` field.
- Confirmation is tracked per source individually; any source edit re-requires re-confirmation of that source.

## Storage Modes

- `standalone` → write `{project_root}/.studio-workspace.toml`, separate from `config/core.toml`.
- `inline` → write `[workspace]` inside `{project_root}/config/core.toml`.
- **Inline is NOT available when any selected source is a Git URL.** On an inline+URL conflict, emit
  exactly: `Inline storage is not supported for Git URL sources; please choose standalone storage or change the selected repos.` then reset to standalone.

## CLI Commands

- Initialize: `{cfs_cmd} --json workspace-init [--root <super-root>] [--output <path>] [--inline] [--force] [--dry-run]`
- Add source: `{cfs_cmd} --json workspace-add --name <name> (--path <path> | --url <url>) [--branch <branch>] [--role <role>] [--adapter <path>] [--inline]`
- Status: `{cfs_cmd} --json workspace-info`
- Sync Git URL sources: `{cfs_cmd} --json workspace-sync`
- `workspace-init` writes standalone by default; `--inline` writes `[workspace]` into `config/core.toml`. Git URL sources are not supported inline. The CLI is responsible for write atomicity.

## Phase 4 Validation Checks

1. `{cfs_cmd} --json workspace-info` — workspace status.
2. Per-source health — path exists; adapter found if expected; `artifacts.toml` valid when an adapter exists; at least one system if an adapter exists.
3. `{cfs_cmd} --json list-ids` — cross-repo IDs.
4. `{cfs_cmd} --json validate` — cross-repo validation.

Report total sources, reachable sources, sources with adapters, and available cross-repo IDs.

- **Critical failures** = sources with expected adapters not found, OR cross-repo validation FAIL.
- **Graceful degradation** = missing repos emit warnings (not errors); available sources keep working;
  remote IDs from missing sources are unavailable; explicit `source` entries to missing repos resolve to None.

## Write Discipline

- `CF_PHASE_GATE` is an external session-scoped protocol variable (defined in the studio protocol), not workflow STATE.
  Set it to `released_for_orchestrator_write` (scoped to the config path) before the write CLI and back to `armed` immediately after the CLI returns.
- Never write workspace config until every selected source is confirmed and the final location is valid.

## Terminal Records

Every phase emits exactly one of these before its STOP_TURN or continuation:

```text
{ "type": "WORKSPACE_STATUS", "phase": "<id>", "status": "pending|complete|invalid|failed", "next_route": "<WS_*|null>" }
{ "type": "WORKSPACE_VALIDATION", "status": "PASS|FAIL|WARN", "checked_sources": [], "issues": [] }
{ "type": "WORKSPACE_FAILURE", "phase": "<id>", "reason": "<one-line>", "recovery": "<next action>" }
```
