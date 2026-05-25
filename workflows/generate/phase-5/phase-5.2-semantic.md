---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the deterministic gate is PASS (or SKIPPED with proof) and the matched semantic reviewer(s) must be dispatched for the current iteration.
---

<!-- toc -->

- [Phase 5.2: Semantic Reviewers](#phase-52-semantic-reviewers)

<!-- /toc -->

### Phase 5.2: Semantic Reviewers

Requires: `workflows/shared/inline-fallback-probe.md` before any `cf-*` sub-agent dispatch.

Select reviewer sub-agent(s) by KIND and the current rules' preferences. This generate-side matrix covers the same review axes as `workflows/analyze/phase-3-semantic.md` (artifact / code / consistency / bug-finding). When both `PROMPT_REVIEW=true` and `PROMPT_BUG_REVIEW=true`, both `cf-semantic-reviewer-prompt` and `cf-prompt-bug-finder` are dispatched in parallel. Dispatch in parallel.

When `INLINE_FALLBACK=true` (set per `workflows/shared/inline-fallback-probe.md` — user replied `2` or host has no native sub-agent support) AND `MAX_ITER > INLINE_LOOP_WARNING_THRESHOLD` (where `INLINE_LOOP_WARNING_THRESHOLD = 2` per `workflows/generate/phase-5/index.md` § Pre-Phase-Setup), emit the long-loop context-exhaustion warning below before the first iteration of this phase runs (this file is the canonical source of the warning text):

```text
⚠️ Inline mode detected with MAX_ITER={MAX_ITER}. Sequential inline review may exhaust context (each iteration loads the full reviewer prompt set + per-target reads in this orchestrator's context window). Recommend reducing MAX_ITER to 2 or splitting the run. Reply `reduce: N` (1 ≤ N ≤ current MAX_ITER) to lower MAX_ITER, or `continue` to proceed at risk.
```

On `reduce: N` validate `1 ≤ N ≤ current MAX_ITER`; on out-of-range reply re-prompt with `reduce: N must satisfy 1 ≤ N ≤ {current MAX_ITER}; reply again or `continue`.` and do not change `MAX_ITER` until a valid value is provided. On valid `reduce: N` set `MAX_ITER = N` and continue; on `continue` proceed with the original `MAX_ITER`. (Bound parallels `workflows/generate/phase-5/phase-5.4-approval.md` § `extend: <M>` which requires `M > current MAX_ITER`.)

A stop token at this warning prompt is handled by
`workflows/shared/stop-token-policy.md`. It always cancels the current Phase 5
entry before any validator/reviewer/author dispatch for this review-loop run.
When `manifest.paths_written` is non-empty (a file-writing generate run already
completed Phase 4 or a prior fix iteration), do NOT route this stop through
`workflows/generate/phase-6/index.md` because no valid `Validation Results`
body exists yet. Instead emit the sanctioned terminal handoff below and end the
generate run. When no files have been written yet (for example an
analyze→generate external entry), return control to the user without Phase 6.

#### Pre-Review Warning Handoff

Emit this block only for the file-writing stop path above:

```text
Pre-Review Warning Handoff
Files were already written, but automatic review did not run because you stopped at the inline long-loop warning before any validator, reviewer, or author dispatch.

Suggested next step: run `/cf-analyze` on the written files when you want review coverage.
You may also resume `/cf-generate(mode=fix)` later if you want to continue the review/fix loop from these files.
```

`PROMPT_REVIEW=true` is set on the generate-side when the kit's `artifacts.toml`
marks the kind with `is_prompt_document = true` OR when any written path is a
current prompt/instruction target: `workflows/**`, `skills/**/SKILL.md`,
`skills/studio/**/*.md`, `skills/**/agents/*.md`, `AGENTS.md`, or
agent/workflow prompt config. Intent verbs still route through analyze-side
mode detection.

Before dispatching reviewers, derive typed target sets from the current review
surface (`manifest.paths_written` on normal generate entry, or `target_paths`
on analyze→generate external entry):

- `prompt_targets` = review-surface paths matching prompt/workflow/instruction
  files (`workflows/**`, `skills/**/SKILL.md`, `skills/studio/**/*.md`,
  `skills/**/agents/*.md`, `requirements/**/*.md`, `AGENTS.md`, and prompt
  config files)
- `code_targets` = review-surface paths matching code/test/build files owned by
  the code reviewer methodology, excluding any path already classified into
  `prompt_targets`
- `artifact_targets` = review-surface paths not in `prompt_targets` and not in
  `code_targets`

Prompt reviewers and prompt bug-finders MUST receive only `prompt_targets`.
Code reviewers and code bug-finders MUST receive only `code_targets`. Artifact
reviewers MUST receive only `artifact_targets`.

Decision priority (top-to-bottom; first match wins for the artifact/code axis, plus consistency and bug-finder rows may be additive):

| Condition | Dispatched sub-agent |
|---|---|
| `PROMPT_REVIEW=true` (overrides artifact/code rows) | `cf-semantic-reviewer-prompt` |
| `TARGET_TYPE == artifact` and not `PROMPT_REVIEW` | `cf-semantic-reviewer-artifact` |
| `TARGET_TYPE == code` and not `PROMPT_REVIEW` | `cf-semantic-reviewer-code` |
| `CODE_BUG_REVIEW=true` | `cf-code-bug-finder` (additive on the code branch) |
| `PROMPT_BUG_REVIEW=true` | `cf-prompt-bug-finder` (additive when PROMPT_REVIEW=true; standalone when PROMPT_REVIEW=false) |
| `rules.md` requests consistency review AND `len(target_paths) ≥ 2` | `cf-semantic-reviewer-consistency` (additive on any branch above) |

Consistency precondition: `cf-semantic-reviewer-consistency` requires `len(target_paths) ≥ 2`. When the trigger matches but the precondition is unmet, skip the consistency dispatch and log `consistency-skipped: single-target` to the iteration trace; the other reviewer(s) still run normally.

Each reviewer's dispatch contract lives in its prompt file under `{cf-studio-path}/.core/skills/studio/agents/`. The orchestrator MUST supply the exact JSON fields each reviewer declares (mirrors `workflows/generate/phase-5/phase-5.1-det-gate.md` § validator dispatch). Per-reviewer enumeration:

- `cf-semantic-reviewer-artifact` — supply: `target_paths = artifact_targets`, `kit_rules_path` = resolved from `rules.md` (`null` in RELAXED non-kit), `checklist_path` = `{kit_path}/artifacts/{KIND}/checklist.md` (`null` when no kit applies), `template_path` = `{kit_path}/artifacts/{KIND}/template.md` (`null` when unavailable), `example_path` = `{kit_path}/artifacts/{KIND}/examples/example.md` (`null` when unavailable), `cross_ref_paths` = parent/sibling artifacts identified in `workflows/generate/phase-0.5-clarify.md`, `rules_mode = {STRICT|RELAXED}`, `traceability_mode` from `artifacts.toml`.
- `cf-semantic-reviewer-code` — supply: `design_artifact_path` from `workflows/generate/phase-0.5-clarify.md`, `code_paths = code_targets`, `cross_ref_paths`, `rules_mode`, `traceability_mode` from `artifacts.toml`, `kit_rules_path` resolved from `rules.md`.
- `cf-semantic-reviewer-prompt` — supply: `target_paths = prompt_targets`, `kit_rules_path` resolved from `rules.md` (when loaded), `rules_mode`, `cross_ref_paths`.
- `cf-semantic-reviewer-consistency` — supply: `target_paths = artifact_targets` for artifact-only consistency checks, otherwise the full review surface when the consistency rule explicitly spans prompt/workflow targets; `baseline_path` (always supplied; value is the resolved baseline path from `rules.md` or the user-specified baseline, or `null` when no baseline applies), `kit_rules_path` (when loaded), `rules_mode`, `namespace_prefix = "Rcons"`.
- `cf-code-bug-finder` — supply: `design_artifact_path` from `workflows/generate/phase-0.5-clarify.md`, `code_paths = code_targets`, `cross_ref_paths`, `rules_mode`, `kit_rules_path` resolved from `rules.md`. Only dispatched when `CODE_BUG_REVIEW=true`.
- `cf-prompt-bug-finder` — supply: `target_paths = prompt_targets`, `kit_rules_path` resolved from `rules.md` (when loaded), `rules_mode`, `cross_ref_paths`. Only dispatched when `PROMPT_BUG_REVIEW=true`.

`traceability_mode` resolution: read `[systems.<system>] traceability` from `{cf-studio-path}/config/artifacts.toml`; default to `FULL` when unset. Thread it into every reviewer dispatch whose agent contract declares it.

Reviewer return handling:

- `review_result.type = "VALIDATION_REPORT"`: require the reviewer-owned
  `Validation Report — <Section>` block and findings JSON.
- `checkpoint.type = "PARTIAL_CHECKPOINT"`: require the reviewer-owned
  `Partial Checkpoint — <Section>` block, checkpoint JSON, and findings JSON.
  Store the checkpoint under `semantic_partial_checkpoints`, set
  `SEMANTIC_REVIEW_PARTIAL=true`, and merge only findings backed by already
  covered evidence. Do not require a `Validation Report — <Section>` block for
  that reviewer, and do not treat its absence as a dispatch failure.

`PARTIAL_CHECKPOINT is supported only by reviewers whose contract declares it`.
For reviewers without that contract, return handling is limited to
`VALIDATION_REPORT` or dispatch failure; do not synthesize a checkpoint shape.

When any reviewer returns `PARTIAL_CHECKPOINT`, the iteration has incomplete
coverage. Append the checkpoint to the iteration trace, keep
`semantic_partial_checkpoints` as a distinct state collection, skip author
auto-fix for the checkpoint itself, and hand control to
`workflows/generate/phase-5/phase-5.3-findings.md` with `all_findings`
containing only validator/reviewer findings backed by already covered evidence.
Phase 5.3 / Phase 6 MUST preserve the separate partial-checkpoint state, keep
the run non-clean, and set `remaining_findings` non-empty or otherwise surface
the partial semantic coverage before exit unless the caller immediately resumes
the checkpoint with the provided `resume_inputs`.

Merge findings, namespacing each source: validator findings keep `V-NNN`, artifact-reviewer findings become `Ra-NNN`, code-reviewer `Rc-NNN`, code-bug-finder `Rcb-NNN`, prompt-reviewer `Rp-NNN`, prompt-bug-finder `Rpb-NNN`, consistency-reviewer `Rcons-NNN`. Re-number within each namespace starting from `001` and rewrite the `id` field on every finding before partitioning. After namespacing: `all_findings = det_findings + sum(reviewer findings)`. The `workflows/generate/phase-5/phase-5.4-approval.md` user dialog references these namespaced IDs.

Append one `phase5_dispatch_evidence` record per semantic reviewer dispatch
with `phase = "5.2"`, `agent_id`, `target_paths`, and the returned review
report marker before handing `all_findings` to Phase 5.3. For
`PARTIAL_CHECKPOINT`, set `result_marker` to the `Partial Checkpoint —
<Section>` block name and include `status = "PARTIAL"` plus the reviewer name
from the checkpoint JSON.
