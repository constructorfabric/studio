
<!-- toc -->

- [Phase 4: Validate](#phase-4-validate)

<!-- /toc -->

---
cf: true
type: workflow
parent: workflows/workspace.md
description: "Invoke when the workspace workflow enters Phase 4 to validate workspace reachability, adapters, and cross-repo behavior."
---

## Phase 4: Validate

**Goal**: verify reachability, adapters, and cross-repo behavior.

| Check | Command / Expectation |
|---|---|
| Workspace status | `{cfs_cmd} --json workspace-info` |
| Source health | path exists; adapter found if expected; `artifacts.toml` valid when adapter exists; at least one system if adapter exists |
| Cross-repo IDs | `{cfs_cmd} --json list-ids` |
| Cross-repo validation | `{cfs_cmd} --json validate` |

Report total sources, reachable sources, sources with adapters, and available
cross-repo IDs.

**Graceful degradation**:

- missing repos emit warnings, not errors
- available sources continue working
- remote IDs from missing sources are unavailable
- explicit `source` entries targeting missing repos resolve to `None`
- scan failures warn on stderr without blocking the operation

If validation reveals critical failures (sources with expected adapters not found, cross-repo validation FAIL), present this menu:

| Option | Action |
|---|---|
| 1 | Diagnose and fix source paths, then re-run validation. |
| 2 | Continue to next-steps despite failures (workspace may behave unexpectedly). |
| 3 | Stop and preserve the current workspace state. |

Suggested: 1 because validation failures usually indicate misconfigured source paths or missing adapters that are quickly fixable.
Reply with 1, 2, or 3.

After validation, continue to `workflows/workspace/next-steps.md`.
