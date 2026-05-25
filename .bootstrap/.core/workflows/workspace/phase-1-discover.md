---
cf: true
type: workflow
parent: workflows/workspace.md
description: "Invoke when the workspace workflow enters Phase 1 to discover candidate repositories and handle zero-result scans."
---

<!-- toc -->

- [Phase 1: Discover](#phase-1-discover)
  - [Zero Results](#zero-results)
  - [Decision Point](#decision-point)

<!-- /toc -->

## Phase 1: Discover

**Goal**: find candidate repos.

| Step | Action |
|---|---|
| Identify root | `{cfs_cmd} --json info` |
| Scan nested repos | `{cfs_cmd} --json workspace-init --dry-run` |
| Present results | show repo name/path, adapter found or not, and inferred role |

### Zero Results

If discovery returns zero candidate repos, do not proceed to configuration or
write an empty workspace config. Emit:

```text
No workspace sources were discovered under {root}.

Reply with one of:
1. Provide a parent directory to scan.
2. Add a source manually with name + path or URL. (URL sources force `standalone`; inline config does not support Git URL sources.)
3. Stop workspace setup.
```

(per `workflows/shared/stop-token-policy.md`)

Only continue after the user supplies a new scan root or at least one manual
source. If the new scan also returns zero results, repeat the same branch; do
not infer sources from unrelated directories.

### Decision Point

After presenting discovered repos, ask two explicit sequential prompts — one per decision. Do not combine them.

**Prompt 1 — Repo Selection** (hard interaction boundary — MUST NOT proceed until the user replies):

```text
Why this input is needed: select which discovered repositories become workspace sources before deciding where to store the config.

Which repositories should be included as workspace sources?

{numbered list of discovered repos with name, path, adapter found/missing, and inferred role}

Suggested default: include all repos that have the expected adapter.

Reply with comma- or space-separated numbers, names, or the word `all`.
```

A stop token at this prompt cancels workspace setup immediately; do not carry a
partial or provisional source selection into Phase 2.

After the user replies, parse the selection into a list of included repos. Then
ask Prompt 2.

**Prompt 2 — Storage Mode** (hard interaction boundary — MUST NOT proceed until the user replies):

```text
Why this input is needed: the storage mode determines where the workspace config lives and whether it can track Git URL sources.

Use a standalone workspace file or an inline workspace config?

- `standalone` → write `.studio-workspace.toml` and keep workspace config separate from `config/core.toml`.
- `inline` → write `[workspace]` inside `config/core.toml`. Not available when any selected source is a Git URL.

Suggested: `standalone` unless you specifically want workspace config inside `config/core.toml`.

Reply `standalone` or `inline`.
```

If any selected repo is specified by Git URL, reject `inline` with: `inline config does not support Git URL sources — reply standalone.` and ask again.

(per `workflows/shared/stop-token-policy.md`)
