# Author Plan: cf-explore result persistence offer

Work request: Update cf-explore so it offers to save exploration results after emitting the resource map, defaults to {cf-studio-path}/.cache/explore/{slug}-{ISO}/, allows a user-provided folder, and saves JSON + Markdown + summary files after explicit confirmation.

Summary: Add a post-explore save offer in the workflow, document the behavior in the agent-integration spec, and extend dispatch tests for the persistence flow and boundary rules.

Risk flags:
- Workflow text changes may need exact string matching in tests.
- Persistence must remain orchestrator-owned to avoid violating the resource_context boundary.
- Default path formatting must stay consistent with existing cache conventions.

Parallel groups:

| Group | Execution | Tasks | Reason |
| --- | --- | --- | --- |
| G1 | sequential | TASK-001 | A single prompt/spec/test task keeps the scope narrow and avoids split ownership across tightly coupled workflow behavior. |

Tasks:

| Task | Title | Author | Targets |
| --- | --- | --- | --- |
| TASK-001 | Add cf-explore save offer and test coverage | cf-generate-prompt-engineer-smart | architecture/features/agent-integration.md, workflows/explore.md, tests/test_workflow_subagents_dispatch.py |

Notes:
- Keep the change narrow and spec-first.
- Do not move exploration output into prompt context.
