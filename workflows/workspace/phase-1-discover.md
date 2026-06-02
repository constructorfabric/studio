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

```pdsl
UNIT WorkspaceDiscover

PURPOSE:
  Find candidate repos and collect repo selection and storage mode from the user.

DO:
  - RUN Run `{cfs_cmd} --json info` to identify root
  - RUN Run `{cfs_cmd} --json workspace-init --dry-run` to scan nested repos
  - RUN Present results: repo name/path, adapter found or not, and inferred role
  - REQUIRE results == zero:
    - CONTINUE WorkspaceDiscoverZeroResults
  - RUN otherwise
    - CONTINUE WorkspaceDiscoverDecisionPoint
```

### Zero Results

```pdsl
UNIT WorkspaceDiscoverZeroResults

PURPOSE:
  Handle the case where no candidate repos were found; do not proceed to configuration.

DO:
  - EMIT exactly:
    No workspace sources were discovered under {root}.

    Reply with one of:
    - Provide a parent directory to scan.
    - Add a source manually with name + path or URL. (URL sources force `standalone`; inline config does not support Git URL sources.)
    - Stop workspace setup.
  - WAIT user.reply
  - STOP_TURN

MENU ZeroResultsMenu:
  TITLE: No workspace sources discovered (reply 1, 2, or 3)
  OPTIONS:
    1 -> Receive new scan root from user
         Re-run scan under new root
         IF results == zero:
           CONTINUE WorkspaceDiscoverZeroResults
         ELSE:
           CONTINUE WorkspaceDiscoverDecisionPoint
    2 -> Receive manual source (name + path or URL) from user
         Add to candidate list
         CONTINUE WorkspaceDiscoverDecisionPoint
    3 -> STOP_TURN
  STOP_TOKEN:
    treat as option 3; preserve scan results in state; no files written; end cleanly
  INVALID:
    EMIT "Reply with 1, 2, or 3."
    WAIT user.reply
    STOP_TURN

RULES:
  - NEVER proceed to Phase 2 or write any config when results are zero
  - NEVER infer sources from unrelated directories
  - ALWAYS repeat this branch if re-scan also returns zero results
```

### Decision Point

```pdsl
UNIT WorkspaceDiscoverDecisionPoint

PURPOSE:
  Collect repo selection (Prompt 1) and storage mode (Prompt 2) as two sequential hard interaction boundaries.

DO:
  - EMIT Prompt 1 (repo selection)
  - WAIT user.reply
  - STOP_TURN

MENU RepoSelectionPrompt:
  TITLE: |
    Why this input is needed: select which discovered repositories become workspace sources before deciding where to store the config.

    Which repositories should be included as workspace sources?

    {numbered list of discovered repos with name, path, adapter found/missing, and inferred role}

    Suggested default: include all repos that have the expected adapter.

    Reply with comma- or space-separated numbers, names, or the word `all`.
  OPTIONS:
    1 <selection> ->
      Parse selection into included repos list
      CONTINUE WorkspaceDiscoverStorageModePrompt
  STOP_TOKEN:
    cancel workspace setup immediately; do not carry partial or provisional source selection into Phase 2
  INVALID:
    EMIT "Reply with comma- or space-separated numbers, names, or the word `all`."
    WAIT user.reply
    STOP_TURN

RULES:
  - NEVER proceed to storage mode prompt until user has replied to repo selection
  - NEVER carry partial or provisional selection into Phase 2 on stop token
```

```pdsl
UNIT WorkspaceDiscoverStorageModePrompt

PURPOSE:
  Collect storage mode (standalone vs inline) as a hard interaction boundary after repo selection.

DO:
  - EMIT Prompt 2 (storage mode)
  - WAIT user.reply
  - STOP_TURN

MENU StorageModePrompt:
  TITLE: |
    Why this input is needed: the storage mode determines where the workspace config lives and whether it can track Git URL sources.

    Use a standalone workspace file or an inline workspace config?

    - `standalone` → write `.studio-workspace.toml` and keep workspace config separate from `config/core.toml`.
    - `inline` → write `[workspace]` inside `config/core.toml`. Not available when any selected source is a Git URL.

    Suggested: `standalone` unless you specifically want workspace config inside `config/core.toml`.

    Reply `standalone` or `inline`.
  OPTIONS:
    1 standalone -> CONTINUE workflows/workspace/phase-2-configure.md
    2 inline ->
      IF any selected repo is a Git URL:
        EMIT "inline config does not support Git URL sources — reply standalone."
        WAIT user.reply
        STOP_TURN
      ELSE:
        CONTINUE workflows/workspace/phase-2-configure.md
  STOP_TOKEN:
    cancel workspace setup; no files written
  INVALID:
    EMIT "Reply `standalone` or `inline`."
    WAIT user.reply
    STOP_TURN

NOTES:
  See workflows/shared/stop-token-policy.md for stop-token routing.
  Both prompts are hard interaction boundaries; the workflow NEVER proceed until each reply is received.
  Git URL sources always force standalone mode.
```
