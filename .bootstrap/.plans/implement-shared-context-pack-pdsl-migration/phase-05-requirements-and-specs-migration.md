```toml
[phase]
plan = "implement-shared-context-pack-pdsl-migration"
number = 5
total = 6
type = "implement"
title = "Requirements and specs migration"
depends_on = [4]
input_manifest = ""
input_signature = ""
input_files = [
  "requirements",
  "architecture/specs",
  "workflows/pdsl.md",
  "architecture/specs/PDSL.md",
]
output_files = [
  "requirements",
  "architecture/specs",
]
outputs = [
  "out/phase-05-pdsl-requirements-specs.md",
  "out/phase-05-path-prefix-remediation.md",
]
inputs = [
  "out/phase-01-pdsl-scope-map.md",
  "out/phase-02-rewrite-rules.md",
  "out/phase-04-agent-context-needs.md",
]
```

## Preamble

This is a self-contained phase file. All rules, constraints, and kit content
are included below. Project files listed in the Task section must be read
at runtime. Follow the instructions exactly, run any EXECUTE commands as
written, and report results against the acceptance criteria at the end.

## What

Migrate the prompt-bearing requirements and architecture specs so their
operational behavior is expressed in explicit PDSL blocks and their prompt-load
semantics align with the shared-context-pack model. This phase edits only files
under `requirements/` and `architecture/specs/`, preserves explanatory prose
when the PDSL spec allows it, and records both the migrated corpus and any
path-prefix or direct-load remediations in the required `out/` summaries.

## Prior Context

- Phase 1 produced a runtime scope map for this migration in
  `out/phase-01-pdsl-scope-map.md`.
- Phase 2 produced rewrite rules and the target migration contract in
  `out/phase-02-rewrite-rules.md`.
- Phase 4 produced agent-context requirements in
  `out/phase-04-agent-context-needs.md`.
- The shared-context-pack spec requires prompt-consuming sub-agents to consume
  prompt context via `prompt_context_view`, not by reloading prompt files.
- The PDSL spec requires explicit blocks for state, menus, actions, recovery,
  and always-on rules; rationale and narrative may remain prose.
- The `out/*` paths listed in `inputs` are execution-time dependencies for this
  phase. They were not compile-time blockers for generating this phase file.

## User Decisions

### Already Decided (pre-resolved during planning)

- **Runtime dependency handling**: treat the three `out/*` inputs as
  execution-time reads, not compile-time blockers.
- **Migration boundary**: modify only prompt-bearing files under
  `requirements/` and `architecture/specs/`.
- **Behavioral rewrite target**: move operational behavior into explicit PDSL
  blocks while preserving explanatory prose that is not executable guidance.
- **Phase outputs**: produce `out/phase-05-pdsl-requirements-specs.md` and
  `out/phase-05-path-prefix-remediation.md`.

### Decisions Needed During This Phase

- None. Use the runtime scope map, rewrite rules, and agent-context outputs from
  earlier phases as the authoritative guidance instead of reopening planning.

## Rules

### Scope And Boundary

- MUST modify only prompt-bearing files under `requirements/` and
  `architecture/specs/`.
- MUST read `workflows/pdsl.md`, `architecture/specs/PDSL.md`,
  `architecture/specs/shared-context-pack.md`, and the three runtime `out/*`
  inputs before deciding what to migrate.
- MUST read prompt-bearing files in `requirements/` and `architecture/specs/`
  at runtime and MUST ignore unrelated source code or artifact content files.
- MUST treat missing runtime `out/*` inputs during execution as dependency
  failures for this phase; MUST_NOT reconstruct them from memory.
- MUST_NOT edit `workflows/`, `skills/`, `.bootstrap/.core/`, source code,
  tests, or unrelated artifacts in this phase.
- MUST preserve semantic meaning when rewriting a file; the format may change,
  but the behavioral contract MUST remain intact.

### PDSL Migration Rules

- MUST use explicit PDSL blocks for operational behavior, especially state,
  gates, conditions, menus, user interactions, recovery paths, validation
  loops, and workflow handoffs.
- MUST use the canonical PDSL keyword set: `UNIT`, `PURPOSE`, `INPUT`,
  `OUTPUT`, `STATE`, `WHEN`, `DO`, `SET`, `EMIT`, `EMIT_MENU`, `WAIT`,
  `STOP_TURN`, `CONTINUE`, `DISPATCH`, `RETURN`, `FORBID`, `REQUIRE`,
  `RULES`, `ON_ERROR`, `INVARIANTS`, and `NOTES`.
- MUST declare state defaults explicitly whenever missing state changes
  behavior.
- MUST declare reset behavior explicitly whenever state is scoped to a turn,
  workflow, or session.
- MUST define invalid-menu handling whenever a `MENU` block is present.
- MUST make user-visible interaction boundaries explicit with `EMIT`,
  `EMIT_MENU`, `WAIT`, and `STOP_TURN`.
- MUST move required and forbidden behavior into `RULES` or `INVARIANTS`
  instead of leaving it only in prose.
- MUST keep rationale, explanation, examples, and reference prose outside the
  executable PDSL blocks unless they create behavior.
- MUST_NOT invent hidden semantics, implied state transitions, or implied
  recovery paths.
- MUST_NOT rewrite stable narrative sections solely to make them look
  algorithmic.

### Shared Context Pack Rules

- MUST preserve the separation between prompt assets and non-prompt task
  resources.
- MUST keep prompt/instruction assets as shared-context-pack content and keep
  source code, target artifacts, and domain documents as ordinary task
  resources.
- MUST state that prompt-consuming sub-agents consume prompt and instruction
  context via `prompt_context_view`.
- MUST state that prompt-consuming sub-agents declare semantic
  `prompt_context_requirements` when they require prompt assets.
- MUST keep orchestrator-owned prompt loading responsibilities with the
  orchestrator, shared-context-pack builder, or another explicitly designated
  top-level controller.
- MUST treat missing required prompt context as an orchestration error.
- MUST_NOT allow silent degradation from missing prompt context to direct
  prompt-file reads.
- MUST_NOT instruct prompt-consuming sub-agents to open `SKILL.md`,
  `workflows/*.md`, `requirements/*.md`, `AGENTS.md`, `sysprompts`, or kit
  prompt assets directly from disk.

### Path And Direct-Load Remediation

- MUST remediate direct prompt-loading patterns in migrated prompt-consuming
  documents so they align with shared-context-pack semantics.
- MUST preserve direct prompt-file loading only where the shared-context-pack
  spec explicitly allows it, such as orchestrators or dedicated prompt-pack
  builders.
- MUST normalize any remaining path references that are still valid after the
  migration and record those changes in
  `out/phase-05-path-prefix-remediation.md`.
- MUST record each migrated file, the main transformation applied, and any
  intentionally deferred follow-up in `out/phase-05-pdsl-requirements-specs.md`.

### Completion Rules

- MUST self-verify against every acceptance criterion before reporting
  completion.
- MUST report failures deterministically and identify the blocking file or rule
  when the phase cannot complete.

## Input

### PDSL Rewrite Contract

- Use PDSL for behavior and prose for explanation.
- Convert every meaningful branch, precondition, state change, menu, stop
  condition, and recovery path into explicit PDSL structure.
- Prefer compact, reviewable units over long prose paragraphs that hide control
  flow.
- High-value conversions include phase gates, approval prompts, recovery menus,
  validation loops, state-reset logic, and workflow handoffs.

### Shared Context Pack Contract

- Prompt assets are session-scoped shared context; task resources are not.
- The orchestrator loads prompt assets once, reuses them across the session,
  and derives the smallest `prompt_context_view` that satisfies each agent's
  declared needs.
- Prompt-consuming sub-agents treat `prompt_context_view` as their sole prompt
  and instruction source.
- Missing prompt context blocks dispatch; it does not justify direct prompt-file
  reloads.

### Migration Focus

- Migrate only prompt-bearing requirement and spec files whose primary purpose
  is to instruct agent behavior, routing, validation, prompting, or workflow
  control.
- Preserve reference-only or explanatory sections unless they contain
  executable behavior that the PDSL spec says should be explicit.
- Use the earlier runtime outputs to decide which files are in scope, which
  patterns to transform, and which direct-load or path-prefix issues still need
  remediation in this phase.

## Task

1. Read these runtime inputs before editing:
   `workflows/pdsl.md`, `architecture/specs/PDSL.md`,
   `architecture/specs/shared-context-pack.md`,
   `out/phase-01-pdsl-scope-map.md`,
   `out/phase-02-rewrite-rules.md`, and
   `out/phase-04-agent-context-needs.md`.
2. Read the prompt-bearing files under `requirements/` and
   `architecture/specs/`, then build a phase-local target list of files that
   still contain executable prompt behavior in prose, direct prompt-loading
   instructions, or stale path-prefix assumptions.
3. Update the targeted files under `requirements/` so operational behavior is
   represented in explicit PDSL blocks where required, while keeping narrative
   explanation in prose where the PDSL spec allows it.
4. Update the targeted files under `architecture/specs/` so operational
   behavior is represented in explicit PDSL blocks where required and the
   shared-context-pack semantics remain accurate for prompt-loading,
   prompt-context requirements, and prompt-context views.
5. Remediate direct prompt-loading and path-prefix issues in every migrated
   prompt-consuming file, preserving direct file-loading only for orchestrators
   or designated prompt-pack builders allowed by the shared-context-pack spec.
6. Write `out/phase-05-pdsl-requirements-specs.md` with the migrated file
   inventory, a short description of each transformation, and any intentionally
   deferred follow-up.
7. Write `out/phase-05-path-prefix-remediation.md` with every path-prefix or
   direct-load remediation made in this phase, including any remaining
   exceptions that are still valid by spec.
8. Self-verify all modified files and outputs against the acceptance criteria,
   then report results in the required output format.

## Acceptance Criteria

- Only prompt-bearing files under `requirements/` and `architecture/specs/`
  were modified for this phase.
- Every migrated file that contains operational behavior now expresses that
  behavior in explicit PDSL blocks where state, branching, interaction,
  validation, recovery, or handoff behavior matters.
- No migrated prompt-consuming document instructs direct prompt-file reads from
  `SKILL.md`, `workflows/*.md`, `requirements/*.md`, `AGENTS.md`,
  `sysprompts`, or kit prompt assets unless the file is explicitly describing
  an allowed orchestrator or prompt-pack-builder responsibility.
- Shared-context-pack semantics remain intact in migrated docs: prompt assets
  stay separate from task resources, prompt-consuming agents rely on
  `prompt_context_view`, and missing prompt context is treated as an
  orchestration error rather than a direct-read fallback.
- `out/phase-05-pdsl-requirements-specs.md` and
  `out/phase-05-path-prefix-remediation.md` both exist and accurately summarize
  the phase outputs.
- This phase file contains no unresolved variables outside code fences and is
  no more than 600 lines long.

## Output Format

When complete, report results in this exact format:
```text
PHASE 5/6 COMPLETE
Status: PASS | FAIL
Files created: {list}
Files modified: {list}
Acceptance criteria:
  [x] Criterion 1 — PASS
  [ ] Criterion 2 — FAIL: {reason}
  ...
Line count: {actual}/600
Notes: {any issues or decisions made}
```

Then generate a copy-pasteable prompt for the next phase inside a single code
fence:

```text
Next phase prompt (copy-paste into new chat if needed):
```

```text
I have a Studio execution plan at:
  .bootstrap/.plans/implement-shared-context-pack-pdsl-migration/plan.toml

Phase 5 is complete ({status}).
Please read the plan manifest, then execute Phase 6: "Validation and gap closure".
The phase file is: .bootstrap/.plans/implement-shared-context-pack-pdsl-migration/phase-06-validation-and-gap-closure.md
It is self-contained — follow its instructions exactly.
After completion, report results and generate the prompt for the next phase.
```
