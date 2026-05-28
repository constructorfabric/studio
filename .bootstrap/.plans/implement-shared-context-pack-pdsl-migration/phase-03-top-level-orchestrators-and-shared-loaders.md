```toml
[phase]
plan = "implement-shared-context-pack-pdsl-migration"
number = 3
total = 6
type = "implement"
title = "Top-level orchestrators and shared loaders"
depends_on = [2]
input_manifest = ""
input_signature = ""
input_files = [
  "architecture/specs/shared-context-pack.md",
  "skills/studio/SKILL.md",
  "skills/studio/protocol.md",
  "skills/studio/routing.md",
  "workflows/generate.md",
  "workflows/analyze.md",
  "workflows/plan.md",
  "workflows/pdsl.md",
  "workflows/workspace.md",
]
output_files = [
  "skills/studio/SKILL.md",
  "skills/studio/protocol.md",
  "skills/studio/routing.md",
  "workflows/generate.md",
  "workflows/analyze.md",
  "workflows/plan.md",
  "workflows/pdsl.md",
  "workflows/workspace.md",
]
outputs = [
  "out/phase-03-orchestrator-migration.md",
  "out/phase-03-pack-builder-contract.md",
]
inputs = [
  "out/phase-02-rewrite-rules.md",
  "out/phase-02-agent-context-contract.md",
  "out/phase-02-path-prefix-policy.md",
]
```

## Preamble

This is a self-contained phase file. All rules, constraints, and kit content
are included below. Project files listed in the Task section must be read
at runtime. Follow the instructions exactly, run any EXECUTE commands as
written, and report results against the acceptance criteria at the end.

## What

Migrate the top-level Constructor Studio orchestration surface to the shared-context-pack model. This phase updates only the root workflow entrypoints plus `skills/studio/SKILL.md`, `skills/studio/protocol.md`, and `skills/studio/routing.md` so prompt-asset discovery, reuse, validation, and dispatch flow through orchestrator-owned shared loaders instead of direct prompt-file reads in prompt-consuming agents. It also produces two `out/` artifacts that document the migration plan and the pack-builder contract. Do not edit leaf workflow fragments or leaf sub-agent prompt files in this phase.

## Prior Context

- Phase 2 is the immediate dependency for this phase.
- Phase 2 produced three runtime artifacts: `out/phase-02-rewrite-rules.md`, `out/phase-02-agent-context-contract.md`, and `out/phase-02-path-prefix-policy.md`.
- The updated brief explicitly reclassified those three `out/*` files as execution-time dependencies rather than compile-time blockers.
- The shared-context-pack spec makes prompt loading session-scoped, orchestrator-owned, validation-backed, and forbidden to prompt-consuming sub-agents.
- This phase prepares the top-level migration before later phases rewrite deeper prompt consumers and validators.

## User Decisions

### Already Decided (pre-resolved during planning)

- **Runtime dependency policy**: Treat `out/phase-02-rewrite-rules.md`, `out/phase-02-agent-context-contract.md`, and `out/phase-02-path-prefix-policy.md` as required runtime inputs for phase execution.
- **Write scope**: Modify only `skills/studio/SKILL.md`, `skills/studio/protocol.md`, `skills/studio/routing.md`, the five top-level workflow files, and the two `out/phase-03-*.md` artifacts.
- **Git handling**: `git_commit_mode = commit`; you may stage only files written by this phase and create one signed commit at the end.
- **Git constraints**: Do not push, reset, rebase, stash, or use `git checkout --`.

### Decisions Needed During This Phase

- None. Execute deterministically from the spec and the runtime inputs; stop only if a required runtime input or required target file is missing.

## Rules

### Scope And Phase Boundary

- MUST treat this phase as a top-level migration only.
- MUST modify only `skills/studio/SKILL.md`, `skills/studio/protocol.md`, `skills/studio/routing.md`, `workflows/generate.md`, `workflows/analyze.md`, `workflows/plan.md`, `workflows/pdsl.md`, `workflows/workspace.md`, `out/phase-03-orchestrator-migration.md`, and `out/phase-03-pack-builder-contract.md`.
- MUST NOT edit leaf workflow fragments, leaf sub-agent prompt files, or unrelated repo files in this phase.
- MUST preserve the three phase-2 `out/*` artifacts as runtime dependencies; MUST NOT delete, rename, inline, or relax them because they were absent during compilation.
- MUST NOT revert unrelated work already present in the repository.

### Shared Context Pack Law

- A chat session MUST have exactly one logical `SHARED_CONTEXT_PACK`.
- Prompt assets loaded during one workflow run MUST remain available to later workflow runs in the same session.
- The orchestrator MUST reuse the existing session pack before loading any new prompt asset.
- The orchestrator MAY extend the session pack with newly required prompt assets discovered later in the session.
- The orchestrator MUST NOT rebuild the entire pack for each workflow run by default.
- Asset freshness MUST be checked by `etag`, not by workflow-run boundaries.
- The orchestrator is the only component allowed to load prompt assets from disk for sub-agent use during a chat session.
- The orchestrator MUST resolve current task context, reuse matching assets already in the session pack, discover only missing core and kit prompt assets, load each newly required prompt asset once, extend `SHARED_CONTEXT_PACK`, and derive one `prompt_context_view` per sub-agent dispatch.
- The orchestrator MUST fail dispatch if any required prompt asset is still missing after resolution.

### Prompt Context Contract

- Every prompt-consuming Studio sub-agent MUST declare `prompt_context_requirements`.
- `requires_shared_context_pack` MUST be `true` for any sub-agent that uses prompt assets.
- `required_assets` MUST list every prompt asset class necessary to execute the contract safely.
- Agents MUST declare prompt needs semantically, not as imperative file-open instructions.
- `prompt_context_view` MUST contain all required assets declared by the agent.
- `prompt_context_view` MUST contain only the prompt assets needed by that agent for the current task.
- Prompt-consuming sub-agents MUST treat `prompt_context_view` as their sole prompt and instruction source.
- Prompt-consuming sub-agents MUST treat missing required prompt context as an orchestration error.

### Forbidden Direct Prompt Loads

- Prompt-consuming sub-agents MUST NOT load prompt assets from the filesystem directly.
- Prompt-consuming sub-agents MUST NOT instruct themselves to open `SKILL.md`, `workflows/*.md`, `requirements/*.md`, `AGENTS.md`, or kit prompt files directly.
- Top-level workflows and `skills/studio` loader files MUST route prompt-asset discovery through orchestrator-owned shared loaders only.
- Any direct prompt-asset load that remains in the touched top-level files MUST be limited to orchestrator-owned or dedicated shared-context-pack builder responsibilities.

### Validation And Router Discipline

- Before dispatching a sub-agent, the orchestrator MUST validate that the sub-agent declares `prompt_context_requirements`, the shared context pack exists, all required prompt assets are resolved, every resolved asset is of allowed type and origin, no required asset is missing, and no non-prompt resource has been inserted into the shared context pack.
- If pre-dispatch validation fails, the orchestrator MUST stop before dispatch and surface a deterministic error.
- Touched top-level workflow files MUST use `.bootstrap`-prefixed canonical paths when referencing core prompt assets.
- Routers MUST stay compact and MUST NOT inline full phase bodies or sibling branches that are not active.
- Any new runtime-loadable instruction unit introduced by this phase MUST be `<= 200` lines unless it is a compact router or reference exemption under the prompt-engineering methodology.
- The phase MUST keep deterministic inspection and rewrite steps ahead of narrative synthesis; use `out/` artifacts to record migration results and contract decisions instead of rediscovering scope later.

### Git And Delivery

- MUST stage only files written by this phase.
- MUST create at most one signed commit at the end of the phase because `git_commit_mode` is `commit`.
- The commit subject SHOULD use the `chore(bootstrap):` prefix because this phase writes a bootstrap plan artifact and bootstrap-facing prompt files.
- MUST NOT push, reset, rebase, stash, or use `git checkout --`.

## Input

### Runtime Source Files

- `architecture/specs/shared-context-pack.md`
  Scope to enforce: session lifetime, prompt-context requirements, prompt-context view, orchestrator responsibilities, validation, forbidden patterns, and failure handling.
- `skills/studio/SKILL.md`
  Scope to enforce: phase-gate behavior, bootstrap loading order, dispatch ownership, and git/contributing payload propagation.
- `skills/studio/protocol.md`
  Scope to enforce: protocol guard, CLI resolution, write confirmation, and context block semantics.
- `skills/studio/routing.md`
  Scope to enforce: top-level routing precedence and the `compile phase` / `execute phase` entrypoints.
- `workflows/generate.md`, `workflows/analyze.md`, `workflows/plan.md`, `workflows/pdsl.md`, `workflows/workspace.md`
  Scope to enforce: top-level bootstrap/load rules, orchestrator-owned prompt loading, router compactness, and `.bootstrap` path-prefix normalization.

### Runtime Phase-2 Inputs

- `out/phase-02-rewrite-rules.md`
- `out/phase-02-agent-context-contract.md`
- `out/phase-02-path-prefix-policy.md`

These three `out/*` files are required at execution time. They are not compile-time blockers for this phase file, but the executing agent must read them before editing prompt-loading behavior so the phase-2 rewrite policy, agent contract rules, and path-prefix policy are preserved.

### Required Deliverables

- `out/phase-03-orchestrator-migration.md`
  Must inventory the top-level migration surface, current direct-load hotspots, target ownership boundaries, and affected files.
- `out/phase-03-pack-builder-contract.md`
  Must define the shared-context-pack builder and loader contract the touched top-level files will implement.

## Task

1. Read `architecture/specs/shared-context-pack.md`, `skills/studio/SKILL.md`, `skills/studio/protocol.md`, `skills/studio/routing.md`, `workflows/generate.md`, `workflows/analyze.md`, `workflows/plan.md`, `workflows/pdsl.md`, and `workflows/workspace.md`. Record every top-level place where prompt assets are loaded directly, routing still assumes direct file opens, `.bootstrap` path prefixes are missing, or session-pack reuse is absent.
2. Read `out/phase-02-rewrite-rules.md`, `out/phase-02-agent-context-contract.md`, and `out/phase-02-path-prefix-policy.md`. Extract the rewrite rules, prompt-context contract constraints, and path-prefix policy that must remain true after this migration.
3. Write `out/phase-03-orchestrator-migration.md` with a deterministic migration inventory: touched files, current behavior, target behavior, shared-loader ownership, direct-load removals, session-reuse points, and any remaining downstream dependencies that later phases must address.
4. Write `out/phase-03-pack-builder-contract.md` defining the top-level shared-context-pack builder contract: session scope, `etag` freshness, pack extension rules, `prompt_context_requirements` resolution, `prompt_context_view` derivation, pre-dispatch validation, failure handling, runtime logging expectations, and compaction-safe/session-reuse behavior.
5. Update `skills/studio/SKILL.md`, `skills/studio/protocol.md`, and `skills/studio/routing.md` so the top-level Studio bootstrap and routing rules make orchestrator-owned shared-context-pack loading the only legal prompt-asset loading path for prompt-consuming agents, preserve dispatch ownership boundaries, and keep compile/execute phase routing aligned with the pack-builder contract.
6. Update `workflows/generate.md`, `workflows/analyze.md`, `workflows/plan.md`, `workflows/pdsl.md`, and `workflows/workspace.md` so their bootstrap and router text uses `.bootstrap`-prefixed canonical paths, removes or rewrites direct prompt-loading instructions that should now be satisfied by the shared context pack, and keeps each router compact instead of inlining downstream prompt bodies.
7. Run deterministic verification on the touched top-level files and the two new `out/` artifacts. Confirm that forbidden direct prompt-loading patterns are gone from prompt-consuming agent paths, `.bootstrap` path-prefix normalization is present where required, the phase-2 runtime inputs are still referenced as dependencies, and only the files listed in this phase changed.
8. Self-verify every acceptance criterion. If all criteria pass, stage only the files written by this phase and create one signed commit that follows the contributing guide and the `git_commit_mode = commit` constraint.

## Acceptance Criteria

- `out/phase-03-orchestrator-migration.md` exists and identifies every touched top-level file plus the current-versus-target prompt-loading responsibility for each.
- `out/phase-03-pack-builder-contract.md` exists and defines session-scoped pack reuse, `etag` freshness, `prompt_context_requirements`, `prompt_context_view`, pre-dispatch validation, failure handling, and runtime logging expectations.
- `skills/studio/SKILL.md`, `skills/studio/protocol.md`, `skills/studio/routing.md`, `workflows/generate.md`, `workflows/analyze.md`, `workflows/plan.md`, `workflows/pdsl.md`, and `workflows/workspace.md` no longer tell prompt-consuming sub-agents to load prompt assets directly from disk; any remaining direct prompt loads in those files are limited to orchestrator-owned or dedicated shared-loader responsibilities.
- All touched top-level prompt-asset references use `.bootstrap`-prefixed canonical paths where core assets are referenced, and the three phase-2 `out/*` inputs remain explicit execution-time dependencies.
- No file outside `skills/studio/SKILL.md`, `skills/studio/protocol.md`, `skills/studio/routing.md`, `workflows/generate.md`, `workflows/analyze.md`, `workflows/plan.md`, `workflows/pdsl.md`, `workflows/workspace.md`, `out/phase-03-orchestrator-migration.md`, and `out/phase-03-pack-builder-contract.md` is created or modified.
- Every new runtime-loadable instruction unit introduced by this phase is `<= 200` lines or is explicitly structured as a compact router/reference exemption, and verification includes a search showing zero forbidden direct prompt-load patterns in the touched prompt-consuming paths.
- The execution report contains no unresolved template variables outside fenced code blocks and records whether the single signed commit was created.

## Output Format

When complete, report results in this exact format:
```text
PHASE 3/6 COMPLETE
Status: PASS | FAIL
Files created: {list}
Files modified: {list}
Acceptance criteria:
  [x] Criterion 1 — PASS
  [ ] Criterion 2 — FAIL: {reason}
  ...
Line count: {actual}/{budget}
Notes: {any issues or decisions made}
```

Then generate a copy-pasteable prompt for the next phase inside a single code fence:

```text
Next phase prompt (copy-paste into new chat if needed):

I have a Studio execution plan at:
  .bootstrap/.plans/implement-shared-context-pack-pdsl-migration/plan.toml

Phase 3 is complete ({status}).
Please read the plan manifest, then execute Phase 4 using the Phase 4 file listed in plan.toml.
It is self-contained — follow its instructions exactly.
After completion, report results and generate the prompt for the next phase.
```
