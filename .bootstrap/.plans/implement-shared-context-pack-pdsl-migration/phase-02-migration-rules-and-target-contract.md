```toml
[phase]
plan = "implement-shared-context-pack-pdsl-migration"
number = 2
total = 6
type = "implement"
title = "Migration rules and target contract"
depends_on = [1]
input_manifest = ""
input_signature = ""
input_files = [
  "architecture/specs/shared-context-pack.md",
  "architecture/specs/PDSL.md",
  "workflows/pdsl.md",
  "skills/studio/agents.toml",
]
output_files = ["architecture/specs/shared-context-pack.md"]
outputs = [
  "out/phase-02-rewrite-rules.md",
  "out/phase-02-agent-context-contract.md",
  "out/phase-02-path-prefix-policy.md",
]
inputs = [
  "out/phase-01-prompt-inventory.md",
  "out/phase-01-load-path-findings.md",
  "out/phase-01-pdsl-scope-map.md",
]
```

## Preamble

This is a self-contained phase file. All rules, constraints, and kit content
are included below. Project files listed in the Task section must be read
at runtime. Follow the instructions exactly, run any EXECUTE commands as
written, and report results against the acceptance criteria at the end.

## What

Define the migration contract that moves Constructor Studio prompt assets from
direct per-agent disk loads into a session-scoped shared context pack plus
agent-specific `prompt_context_view` handoff. In this phase, write the three
phase outputs that codify rewrite rules, agent-context requirements, and path
prefix policy, then update `architecture/specs/shared-context-pack.md` so the
target contract is explicit and aligned with current PDSL migration machinery.
Do not migrate prompt files in place yet; this phase establishes the rules that
later phases must follow.

## Prior Context

Phase 1 classified prompt assets, direct-load patterns, and PDSL scope, but
its `out/*` artifacts are execution-time dependencies rather than compile-time
preconditions.
The authoritative target spec is `architecture/specs/shared-context-pack.md`.
The current PDSL workflow and `cf-pdsl-*` agents still include direct prompt
file loads that later phases must replace or route through orchestrators.
This phase depends on Phase 1 but MUST continue even when the Phase 1 `out/*`
artifacts are absent at execution start.

## User Decisions

### Already Decided (pre-resolved during planning)

- **Runtime dependency rule**: Missing `out/phase-01-*.md` files MUST NOT
  block execution of this phase.
- **Write scope**: This phase may modify only
  `architecture/specs/shared-context-pack.md` and create only the three listed
  `out/phase-02-*.md` files.
- **Migration scope**: This phase defines rewrite rules and target contracts;
  it does not perform the later prompt-file rewrites.

### Decisions Needed During This Phase

No additional review gates, confirmation points, or user-input requests are
authorized in this phase. Execute deterministically.

## Rules

### Scope And Authority

- MUST execute only this phase's scope.
- MUST read the runtime files listed in the Task section before making
  cross-file claims.
- MUST treat `out/phase-01-prompt-inventory.md`,
  `out/phase-01-load-path-findings.md`, and
  `out/phase-01-pdsl-scope-map.md` as execution-time dependencies.
- MUST continue when one or more Phase 1 `out/*` inputs are missing and record
  them as pending runtime dependencies instead of failing.
- MUST write only `architecture/specs/shared-context-pack.md`,
  `out/phase-02-rewrite-rules.md`,
  `out/phase-02-agent-context-contract.md`, and
  `out/phase-02-path-prefix-policy.md`.
- MUST NOT modify `workflows/pdsl.md`, `workflows/pdsl/*.md`,
  `skills/studio/agents.toml`, or any `skills/studio/agents/cf-pdsl-*.md`
  file in this phase.
- MUST NOT broaden scope into later migration execution work.

### Shared Context Pack Contract

- MUST keep the shared context pack limited to prompt and instruction assets.
- MUST keep non-prompt task resources outside the shared context pack.
- MUST preserve session scope for `SHARED_CONTEXT_PACK`.
- MUST preserve incremental reuse and enrichment across workflow runs in the
  same chat session.
- MUST preserve `etag`-based freshness semantics rather than workflow-run
  resets.
- MUST preserve asset-origin semantics for `core`, `kit`, and `project`.
- MUST preserve `prompt_context_requirements` as a semantic declaration rather
  than imperative file-open instructions.
- MUST preserve `prompt_context_view` as the sole prompt/instruction source for
  prompt-consuming sub-agents.
- MUST keep the orchestrator as the only component allowed to load prompt
  assets from disk for sub-agent use during a chat session.
- MUST keep kit prompt assets as first-class shared-context-pack assets rather
  than ad hoc reads inside sub-agents.
- MUST preserve failure semantics that stop dispatch when required prompt
  context is missing.
- MUST NOT allow silent fallback from missing prompt context to direct prompt
  file reads.

### Forbidden Direct-Load Patterns

- MUST define direct prompt-file loading by prompt-consuming sub-agents as a
  migration defect.
- MUST keep `SKILL.md`, `workflows/*.md`, `requirements/*.md`, `AGENTS.md`,
  sysprompt files, and kit prompt files in the forbidden direct-load set for
  prompt-consuming sub-agents.
- MUST preserve the allowed exception set: orchestrator, dedicated
  shared-context-pack builder, or another explicitly designated top-level
  controller responsible for prompt asset discovery.
- MUST distinguish forbidden prompt-asset reads from allowed runtime reads of
  non-prompt task resources.

### PDSL Normalization Contract

- MUST preserve behavior before compacting wording.
- MUST express executable behavior in PDSL blocks rather than hiding it in
  prose.
- MUST keep rationale and background in `NOTES`.
- MUST capture state explicitly when behavior depends on state.
- MUST encode user-visible interaction surfaces with `MENU`, `EMIT`, `WAIT`,
  and `STOP_TURN` when applicable.
- MUST encode required actions in ordered `DO` steps.
- MUST encode hard rules with `RULES`, `INVARIANTS`, `REQUIRE`, or `FORBID`.
- MUST encode failure-path control flow with `ON_ERROR` when recovery behavior
  matters.
- MUST preserve approval gates, write-authority boundaries, stop points,
  invalid-input handling, and state-reset behavior.
- MUST NOT drop `MUST`, `ALWAYS`, `NEVER`, `FORBID`, `REQUIRE`, approval, or
  `STOP_TURN` semantics during normalization.
- MUST use the current PDSL workflow and `cf-pdsl-*` agents as migration
  tooling requirements and explicitly record any self-migration gaps they still
  contain.

### Phase Outputs

- MUST write `out/phase-02-rewrite-rules.md` as the canonical rewrite policy
  for migrating prompt-loading instructions and PDSL-normalization behavior.
- MUST write `out/phase-02-agent-context-contract.md` as the target contract
  for orchestrators and prompt-consuming sub-agents.
- MUST write `out/phase-02-path-prefix-policy.md` as the canonical mapping of
  prompt-asset path families, orchestrator-only loaders, and allowed runtime
  resource reads.
- MUST update `architecture/specs/shared-context-pack.md` so it references or
  incorporates the migration rules, target contract, and path-prefix policy.
- MUST keep the updated shared-context-pack spec aligned with session scope,
  compaction safety, kit asset handling, and forbidden prompt reload rules.

### Validation And Reporting

- MUST verify that every file listed in `input_files` has a matching runtime
  read in the Task section.
- MUST verify that every file listed in `inputs` is either read or explicitly
  recorded as missing-but-required-at-runtime.
- MUST verify that the completion report accounts for all four written files.
- MUST verify that no unresolved brace-delimited placeholder variables remain
  outside code fences.
- MUST verify that this phase file remains at or below 600 lines.

## Input

### Inlined PDSL Normalization Obligations

Use PDSL to make mandatory behavior explicit and reviewable.

- Core executable blocks: `UNIT`, `PURPOSE`, `INPUT`, `STATE`, `WHEN`, `DO`,
  `MENU`, `RULES`, `INVARIANTS`, `ON_ERROR`, `NOTES`.
- `PATTERNS:` declarations are file-scoped and MUST appear before the first
  `UNIT` that references them.
- `DO` actions are imperative and one per line.
- Use `SET` only for state changes.
- Use `EMIT` or `EMIT_MENU` only for visible UX output.
- Use `WAIT` and `STOP_TURN` whenever behavior must pause for the user.
- Every menu option MUST have an action, and invalid input handling MUST be
  explicit.
- State defaults and reset or scope rules MUST be explicit when state changes
  behavior.
- `NOTES` is explanatory only; executable requirements MUST stay in PDSL
  blocks.
- When converting prose to PDSL: identify state first, convert conditional
  behavior to `WHEN` or `ON_ERROR`, convert visible interaction to menu and
  turn-boundary constructs, convert hard rules to `RULES` or `INVARIANTS`, and
  split overly complex behavior into multiple `UNIT` blocks connected with
  `CONTINUE`.

### Runtime Files To Ground This Phase

Read these project files at execution time before writing outputs:

- `architecture/specs/shared-context-pack.md`
- `architecture/specs/PDSL.md`
- `workflows/pdsl.md`
- `workflows/pdsl/new.md`
- `workflows/pdsl/transform.md`
- `workflows/pdsl/review.md`
- `skills/studio/agents/cf-pdsl-author.md`
- `skills/studio/agents/cf-pdsl-transformer.md`
- `skills/studio/agents/cf-pdsl-reviewer.md`
- `skills/studio/agents.toml`

Treat these Phase 1 artifacts as runtime dependencies:

- `out/phase-01-prompt-inventory.md`
- `out/phase-01-load-path-findings.md`
- `out/phase-01-pdsl-scope-map.md`

If one of those Phase 1 artifacts is absent, record the absence in the phase
outputs and continue without failing.

## Task

1. Read `architecture/specs/shared-context-pack.md` and extract the current
   authoritative contract for scope boundary, session lifetime, asset origins,
   `prompt_context_requirements`, `prompt_context_view`, orchestrator
   responsibilities, validation, forbidden patterns, failure handling, and
   migration guidance.
2. Read `architecture/specs/PDSL.md`, `workflows/pdsl.md`,
   `workflows/pdsl/new.md`, `workflows/pdsl/transform.md`,
   `workflows/pdsl/review.md`, `skills/studio/agents/cf-pdsl-author.md`,
   `skills/studio/agents/cf-pdsl-transformer.md`,
   `skills/studio/agents/cf-pdsl-reviewer.md`, and
   `skills/studio/agents.toml` to inventory the current PDSL normalization
   rules, write-approval gates, review-only guarantees, and remaining
   direct-load instructions that later phases must migrate.
3. Read `out/phase-01-prompt-inventory.md`,
   `out/phase-01-load-path-findings.md`, and
   `out/phase-01-pdsl-scope-map.md` if they exist. If any are missing, record
   each missing file as a pending runtime dependency and continue.
4. Write `out/phase-02-rewrite-rules.md` with deterministic migration rules
   that separate prompt assets from task resources, define the forbidden
   direct-load patterns, preserve allowed orchestrator exceptions, and specify
   how workflows, skills, requirements, specs, and agent prompts must be
   normalized into PDSL-compatible shared-context-pack consumers.
5. Write `out/phase-02-agent-context-contract.md` with the target contract for
   top-level orchestrators, shared-context-pack builders, and prompt-consuming
   sub-agents. Include required `prompt_context_requirements` fields, required
   `prompt_context_view` behavior, allowed prompt-asset loader roles, and
   deterministic failure semantics when required prompt context is missing.
6. Write `out/phase-02-path-prefix-policy.md` with the canonical path-prefix
   policy that classifies orchestrator-only prompt-asset reads, forbidden
   sub-agent prompt reloads, and allowed runtime resource reads.
7. Update `architecture/specs/shared-context-pack.md` so the migration guidance
   and target contract explicitly reference the rewrite rules, agent-context
   contract, and path-prefix policy produced in this phase, while preserving
   the existing session-scoped shared-context-pack model.
8. Self-verify the four written files against the acceptance criteria,
   including the missing-`out/*` runtime-dependency rule, then prepare the
   completion report exactly in the required output format.

## Acceptance Criteria

- [ ] `out/phase-02-rewrite-rules.md` exists and defines rewrite rules for
  prompt assets versus task resources, forbidden direct-load patterns, allowed
  orchestrator exceptions, and PDSL normalization obligations for workflows,
  skills, requirements, specs, and agent prompts.
- [ ] `out/phase-02-agent-context-contract.md` exists and defines the target
  responsibilities and failure semantics for orchestrators, shared-context-pack
  builders, and prompt-consuming sub-agents.
- [ ] `out/phase-02-path-prefix-policy.md` exists and classifies prompt-asset
  path prefixes versus allowed runtime resource reads.
- [ ] `architecture/specs/shared-context-pack.md` is updated and still states
  that the shared context pack is session-scoped, limited to prompt assets,
  orchestrator-loaded, kit-aware, and incompatible with direct prompt reloads
  by prompt-consuming sub-agents.
- [ ] Missing `out/phase-01-*.md` files did not block completion and are
  explicitly reported as missing runtime dependencies when absent.
- [ ] None of the four written files instruct prompt-consuming sub-agents to
  directly open `SKILL.md`, workflow files, requirement files, `AGENTS.md`,
  sysprompt files, or kit prompt files except when naming those patterns as
  forbidden examples or orchestrator-only exceptions.
- [ ] The completion report accounts for all files created or modified and
  includes a line count for each written file.
- [ ] No unresolved brace-delimited placeholder variables remain outside code
  fences in this phase file, and this phase file is at or below 600 lines.

## Output Format

When complete, report results in this exact format:
```text
PHASE 2/6 COMPLETE
Status: PASS | FAIL
Files created: out/phase-02-rewrite-rules.md, out/phase-02-agent-context-contract.md, out/phase-02-path-prefix-policy.md
Files modified: architecture/specs/shared-context-pack.md
Acceptance criteria:
  [x] Criterion 1 — PASS
  [ ] Criterion 2 — FAIL: {reason}
  ...
Line count:
  out/phase-02-rewrite-rules.md: {actual}
  out/phase-02-agent-context-contract.md: {actual}
  out/phase-02-path-prefix-policy.md: {actual}
  architecture/specs/shared-context-pack.md: {actual}
Notes: {any issues or decisions made}
```

Then generate a copy-pasteable prompt for the next phase inside a single code
fence:

```text
Next phase prompt (copy-paste into new chat if needed):

I have a Studio execution plan at:
  .bootstrap/.plans/implement-shared-context-pack-pdsl-migration/plan.toml

Phase 2 is complete ({status}).
Please read the plan manifest, then execute Phase 3: "Top-level orchestrators and shared loaders".
The phase file is: .bootstrap/.plans/implement-shared-context-pack-pdsl-migration/phase-03-top-level-orchestrators-and-shared-loaders.md
It is self-contained - follow its instructions exactly.
After completion, report results and generate the prompt for the next phase.
```
