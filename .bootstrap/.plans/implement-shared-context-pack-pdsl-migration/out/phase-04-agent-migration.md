# Phase 04 Agent Migration Report

Disposition legend:
- `migrated`: Phase 4 rewrote the prompt contract and aligned the registry entry.
- `deferred`: Explicit controller/runtime exception left for later phases.
- `out_of_scope`: Registry entry had no Phase 4 leaf prompt-loader migration requirement.

| Agent | Disposition | Files changed | PDSL-normalized | Follow-up / reason |
| --- | --- | --- | --- | --- |
| `cf-codegen` | deferred | none | n/a | Explicit phase exception: controller/runtime contract. |
| `cf-pr-review` | deferred | none | n/a | Explicit phase exception: top-level review controller. |
| `cf-ralphex` | deferred | none | n/a | Explicit phase exception: autonomous orchestration surface. |
| `cf-phase-runner` | deferred | none | n/a | Explicit phase exception: plan execution controller. |
| `cf-phase-compiler` | deferred | none | n/a | Explicit phase exception: plan compilation controller. |
| `cf-migrate-scanner` | migrated | `cf-migrate-scanner.md`, `agents.toml` | yes | Loader path replaced with `prompt_context_view` contract. |
| `cf-migrate-planner` | migrated | `cf-migrate-planner.md`, `agents.toml` | yes | Loader path replaced with `prompt_context_view` contract. |
| `cf-migrate-migrator` | migrated | `cf-migrate-migrator.md`, `agents.toml` | yes | Loader path replaced with `prompt_context_view` contract. |
| `cf-migrate-verifier` | migrated | `cf-migrate-verifier.md`, `agents.toml` | yes | Loader path replaced with `prompt_context_view` contract. |
| `cf-diff-scope-resolver` | migrated | `cf-diff-scope-resolver.md`, `agents.toml` | yes | Structural git contract preserved; prompt self-load removed. |
| `cf-deterministic-validator` | migrated | `cf-deterministic-validator.md`, `agents.toml` | yes | Prompt self-load removed; validator execution unchanged. |
| `cf-semantic-reviewer-artifact` | migrated | `cf-semantic-reviewer-artifact.md`, `agents.toml` | yes | Checklist/compliance assets now semantic. |
| `cf-semantic-reviewer-code` | migrated | `cf-semantic-reviewer-code.md`, `agents.toml` | yes | Checklist/traceability/compliance assets now semantic. |
| `cf-code-bug-finder` | migrated | `cf-code-bug-finder.md`, `agents.toml` | yes | Bug methodology/compliance assets now semantic. |
| `cf-semantic-reviewer-prompt` | migrated | `cf-semantic-reviewer-prompt.md`, `agents.toml` | yes | Prompt-review methodology/compliance assets now semantic. |
| `cf-prompt-bug-finder` | migrated | `cf-prompt-bug-finder.md`, `agents.toml` | yes | Prompt-bug methodology/compliance assets now semantic. |
| `cf-pdsl-author` | migrated | `cf-pdsl-author.md`, `agents.toml` | yes | PDSL spec moved behind semantic asset contract. |
| `cf-pdsl-transformer` | migrated | `cf-pdsl-transformer.md`, `agents.toml` | yes | PDSL spec moved behind semantic asset contract. |
| `cf-pdsl-reviewer` | migrated | `cf-pdsl-reviewer.md`, `agents.toml` | yes | PDSL spec moved behind semantic asset contract. |
| `cf-semantic-reviewer-consistency` | migrated | `cf-semantic-reviewer-consistency.md`, `agents.toml` | yes | Consistency checklist/compliance assets now semantic. |
| `cf-brainstorm-facilitator` | migrated | `cf-brainstorm-facilitator.md`, `agents.toml` | yes | Mode bootstrap moved to `prompt_context_view`. |
| `cf-brainstorm-expert` | migrated | `cf-brainstorm-expert.md`, `agents.toml` | yes | Mode bootstrap moved to `prompt_context_view`. |
| `cf-brainstorm-panel` | out_of_scope | none | n/a | No direct prompt-asset self-load found; already compact leaf contract. |
| `cf-generate-collector` | migrated | `cf-generate-collector.md`, `agents.toml` | yes | Mode bootstrap moved to `prompt_context_view`. |
| `cf-analyze-planner` | migrated | `cf-analyze-planner.md`, `agents.toml` | yes | Mode bootstrap moved to `prompt_context_view`. |
| `cf-generate-planner` | migrated | `cf-generate-planner.md`, `agents.toml` | yes | Mode bootstrap moved to `prompt_context_view`. |
| `cf-generate-author` | out_of_scope | none | n/a | Selector does not self-load prompt assets; no leaf migration needed. |
| `cf-generate-author-junior` | migrated | `cf-generate-author-junior.md`, `agents.toml` | no | Wrapper now requests shared worker contract semantically. |
| `cf-generate-author-middle` | migrated | `cf-generate-author-middle.md`, `agents.toml` | no | Wrapper now requests shared worker contract semantically. |
| `cf-generate-author-senior` | migrated | `cf-generate-author-senior.md`, `agents.toml` | no | Wrapper now requests shared worker contract semantically. |
| `cf-generate-author-lead` | migrated | `cf-generate-author-lead.md`, `agents.toml` | no | Wrapper now requests shared worker contract semantically. |
| `cf-generate-coder-casual` | migrated | `cf-generate-coder-casual.md`, `agents.toml` | no | Wrapper now requests shared worker contract semantically. |
| `cf-generate-coder-smart` | migrated | `cf-generate-coder-smart.md`, `agents.toml` | no | Wrapper now requests shared worker contract semantically. |
| `cf-generate-prompt-engineer-casual` | migrated | `cf-generate-prompt-engineer-casual.md`, `agents.toml` | no | Wrapper now requests shared worker contract semantically. |
| `cf-generate-prompt-engineer-smart` | migrated | `cf-generate-prompt-engineer-smart.md`, `agents.toml` | no | Wrapper now requests shared worker contract semantically. |
| `storytelling-preflight` | out_of_scope | none | n/a | Task-resource/access-tier contract; no direct prompt-asset self-load found. |
| `storytelling-gate` | out_of_scope | none | n/a | Gate/controller-like surface excluded from leaf migration. |
| `storytelling-context-pack` | out_of_scope | none | n/a | Content-pack builder reads task resources, not prompt assets. |
| `storytelling-wrap` | out_of_scope | none | n/a | Wrap synthesizer has no direct prompt-asset self-load surface. |
| `storytelling-export` | out_of_scope | none | n/a | Export writer has no direct prompt-asset self-load surface. |
