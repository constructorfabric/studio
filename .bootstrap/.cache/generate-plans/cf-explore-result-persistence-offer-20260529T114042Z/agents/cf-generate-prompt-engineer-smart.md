# Author: cf-generate-prompt-engineer-smart

Work request: Update cf-explore so it offers to save exploration results after emitting the resource map, defaults to {cf-studio-path}/.cache/explore/{slug}-{ISO}/, allows a user-provided folder, and saves JSON + Markdown + summary files after explicit confirmation.

## G1

### TASK-001: Add cf-explore save offer and test coverage

Intent: Update the exploration workflow and supporting spec so that after resource map emission the top-level controller offers a save step with the default {cf-studio-path}/.cache/explore/{slug}-{ISO}/ path, accepts an alternate user-provided folder, and persists JSON, Markdown, and summary files only after explicit confirmation. Keep the explorer sub-agent read-only and preserve resource_context as non-prompt output.

Targets:
- architecture/features/agent-integration.md
- workflows/explore.md
- tests/test_workflow_subagents_dispatch.py

Acceptance criteria:
- The workflow offers a save step after emitting the exploration resource map/context summary.
- The default save location is {cf-studio-path}/.cache/explore/{slug}-{ISO}/, and the user can choose a different folder.
- The saved bundle includes JSON, Markdown, and summary files.
- Saving only happens after explicit user selection/confirmation, with no silent write.
- The explorer sub-agent remains read-only and its output stays in resource_context rather than SHARED_CONTEXT_PACK.
- Tests cover the default cache path, alternate folder selection, file bundle naming, no-silent-write behavior, and the existing clarify gate.
