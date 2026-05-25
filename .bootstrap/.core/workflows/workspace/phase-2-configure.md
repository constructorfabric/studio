---
cf: true
type: workflow
parent: workflows/workspace.md
description: "Invoke when the workspace workflow enters Phase 2 to confirm selected source settings and workspace location before writing config."
---

<!-- toc -->

- [Phase 2: Configure](#phase-2-configure)

<!-- /toc -->

## Phase 2: Configure

**Goal**: confirm workspace structure.

For each selected source, confirm `name`, relative `path` or `url`, `role`,
and `adapter` (auto-discovered or explicit). Also confirm:

- `cross_repo` (default yes)
- `resolve_remote_ids` (default yes; both settings must be true to include
  remote IDs)
- workspace location: standalone `.studio-workspace.toml` or inline
  `[workspace]` in `config/core.toml`

Primary source is always determined by the current working directory; no
`primary` field exists.

Track confirmation per source. Do not enter Phase 3 until **every** selected
source is confirmed and the workspace location choice is final. Set
`WORKSPACE_ALL_SOURCES_CONFIRMED=true` only after that gate passes.

Use one batched confirmation prompt per source:

```text
Why this input is needed: confirm the exact source settings before writing workspace configuration.
Reply with `approve` to accept the proposed source settings, or list only the fields to change.
Suggested defaults: keep the detected `adapter`, keep `cross_repo = yes`, and keep `resolve_remote_ids = yes` unless the user wants stricter local-only behavior.
- `approve` → keep the proposed source settings and continue.
- field edits → update only the named fields, then re-show the proposal.
```

(per `workflows/shared/stop-token-policy.md`)

If the reply edits workspace location (`standalone` vs `inline`), update the
global location choice before re-showing the current source proposal. If any
source uses a URL, reject `inline` and ask for a standalone location instead.

After each source approval, continue to the next unconfirmed source. Only after
all selected sources are confirmed and the workspace location is still valid
for the whole set may the workflow continue to
`workflows/workspace/phase-3-generate.md`.
