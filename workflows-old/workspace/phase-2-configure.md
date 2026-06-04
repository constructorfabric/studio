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

```pdsl
UNIT WorkspaceConfigure

PURPOSE:
  Confirm all selected source settings and workspace location before allowing Phase 3 to proceed.

STATE:
  - SET WORKSPACE_ALL_SOURCES_CONFIRMED: unset | true
    default: unset
    scope: workflow_run
    reset: any source edit re-requires re-confirmation of that source

RULES:
  - ALWAYS cross_repo defaults to yes
  - ALWAYS resolve_remote_ids defaults to yes
  - ALWAYS have both cross_repo == yes AND resolve_remote_ids == yes to include remote IDs

DO:
  - RUN FOR each selected source (sequentially):
    - EMIT batched confirmation prompt for source
    - WAIT user.reply
    - STOP_TURN

MENU SourceConfirmationPrompt:
  TITLE: |
    Why this input is needed: confirm the exact source settings before writing workspace configuration.
    Reply with `approve` to accept the proposed source settings, or list only the fields to change.
    Suggested defaults: keep the detected `adapter`, keep `cross_repo = yes`, and keep `resolve_remote_ids = yes` unless the user wants stricter local-only behavior.
    - `approve` → keep the proposed source settings and continue.
    - field edits → update only the named fields, then re-show the proposal.
  OPTIONS:
    1 approve ->
      Mark source as confirmed
      IF more unconfirmed sources remain:
        CONTINUE WorkspaceConfigure (next source)
      ELSE:
        CONTINUE WorkspaceConfigureCompletionGate
    field edits ->
      Apply edits to named fields
      IF edit targets workspace location:
        CONTINUE WorkspaceConfigureLocationUpdate
      ELSE:
        Re-show updated source proposal
        WAIT user.reply
        STOP_TURN
  STOP_TOKEN:
    cancel before writing workspace config; no files written
  INVALID:
    EMIT "Reply `approve` or list fields to change."
    WAIT user.reply
    STOP_TURN

RULES:
  - ALWAYS confirm: name, relative path or url, role, adapter, cross_repo, resolve_remote_ids, workspace location
  - ALWAYS track confirmation per source individually
  - NEVER enter Phase 3 until every selected source is confirmed and workspace location is final
  - ALWAYS Primary source is always determined by the current working directory; no `primary` field exists
```

```pdsl
UNIT WorkspaceConfigureLocationUpdate

PURPOSE:
  Handle workspace location edits and URL constraints when user changes standalone vs inline.

DO:
  - REQUIRE reply changes location to inline AND any source uses a URL:
    - EMIT "inline config does not support Git URL sources — a standalone location is required."
    Reset location to standalone
    Re-show current source proposal
    - WAIT user.reply
    - STOP_TURN
  - RUN otherwise
    Update global location choice
    Re-show current source proposal
    - WAIT user.reply
    - STOP_TURN
```

```pdsl
UNIT WorkspaceConfigureCompletionGate

PURPOSE:
  Gate entry to Phase 3 — only pass when all sources confirmed and location valid.

DO:
  - RUN Verify all selected sources are confirmed
  - RUN Verify final workspace location is valid for the whole source set
  - REQUIRE valid:
    - SET WORKSPACE_ALL_SOURCES_CONFIRMED = true
    - CONTINUE {cf-studio-path}/.core/workflows/workspace/phase-3-generate.md
  - RUN otherwise
    - EMIT summary of remaining unconfirmed sources or location conflict
    - CONTINUE WorkspaceConfigure (resume at first unconfirmed source)

NOTES:
  See workflows/shared/stop-token-policy.md for stop-token routing.
  Workspace location choices: standalone (.studio-workspace.toml) or inline ([workspace] in config/core.toml).
  Git URL sources are incompatible with inline mode; reject inline and require standalone in that case.
```
