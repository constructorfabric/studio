
<!-- toc -->

- [Phase 5: Next Steps](#phase-5-next-steps)

<!-- /toc -->

---
cf: true
type: workflow
parent: workflows/workspace.md
description: "Invoke when the workspace workflow completes Phase 4 validation and is ready to present post-setup next steps."
---

## Phase 5: Next Steps

**After successful workspace setup**:

- Run `validate` from each participating repo to verify cross-repo ID
  resolution works
- Use `list-ids` to confirm artifacts from all sources are visible
- Add `source` fields to `artifacts.toml` entries that reference remote repos
- Consider adding workspace setup to project onboarding documentation

When presenting next steps to the user, include a suggested default and an
explicit reply contract:

```text
What would you like to do next?
Reply with the option number or a short custom instruction.
1. Run `validate` from each participating repo — Suggested default; verifies cross-repo ID resolution end to end.
2. Run `list-ids` to confirm artifacts from all sources are visible.
3. Review or edit workspace/source fields before using the workspace further.
4. Other — describe the next workspace action you want (e.g., a `cfs` command to run, a config field to change, or a workspace-related question).
```

(per `workflows/shared/stop-token-policy.md`)
