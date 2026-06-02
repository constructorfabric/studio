---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the deterministic gate is PASS (or SKIPPED with proof) and the matched semantic reviewer(s) must be dispatched for the current iteration.
---

# Generate Phase 5.2: Semantic Reviewers

```pdsl
UNIT Phase52SemanticReviewers

PURPOSE:
  Select and dispatch matched semantic reviewer(s) in parallel based on KIND
  and current rules' preferences.

DO:
  REQUIRE `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md` loaded before dispatch

  DERIVE typed target sets from current review surface
    (manifest.paths_written on normal generate entry; target_paths on
     analyze→generate external entry):
    prompt_targets = paths matching: workflows/**, skills/**/SKILL.md,
      skills/studio/**/*.md, skills/**/agents/*.md, requirements/**/*.md,
      **/AGENTS.md, AGENTS.md, and prompt config files
    code_targets = paths matching code/test/build files owned by code reviewer
      methodology, EXCLUDING any path already in prompt_targets
    artifact_targets = paths NOT in prompt_targets and NOT in code_targets

  DETERMINE PROMPT_REVIEW:
    SET PROMPT_REVIEW = true WHEN:
      KIND's artifacts.toml marks kind with is_prompt_document = true
      OR any written path is: workflows/**, skills/**/SKILL.md,
        skills/studio/**/*.md, skills/**/agents/*.md, AGENTS.md,
        or agent/workflow prompt config

  RESOLVE traceability_mode:
    READ [systems.<system>] traceability from {cf-studio-path}/config/artifacts.toml
    DEFAULT to FULL when unset

  DISPATCH reviewers in parallel per target-set routing:
    1. PROMPT_REVIEW=true AND prompt_targets non-empty:
         LOAD and USE contract for cf-semantic-reviewer-prompt before synthesis;
         fail-closed if missing/unread/unused
         DISPATCH cf-semantic-reviewer-prompt WITH prompt_targets
    2. artifact_targets non-empty:
         LOAD and USE contract for cf-semantic-reviewer-artifact before synthesis;
         fail-closed if missing/unread/unused
         DISPATCH cf-semantic-reviewer-artifact WITH artifact_targets
    3. code_targets non-empty:
         LOAD and USE contract for cf-semantic-reviewer-code before synthesis;
         fail-closed if missing/unread/unused
         DISPATCH cf-semantic-reviewer-code WITH code_targets
    4. CODE_BUG_REVIEW=true (additive on code branch):
         LOAD and USE contract for cf-code-bug-finder before synthesis;
         fail-closed if missing/unread/unused
         DISPATCH cf-code-bug-finder WITH code_targets
    5. PROMPT_BUG_REVIEW=true (additive when PROMPT_REVIEW=true;
         standalone when PROMPT_REVIEW=false):
         LOAD and USE contract for cf-prompt-bug-finder before synthesis;
         fail-closed if missing/unread/unused
         DISPATCH cf-prompt-bug-finder WITH prompt_targets
    6. rules.md requests consistency review AND len(target_paths) >= 2 (additive):
         LOAD and USE contract for cf-semantic-reviewer-consistency before synthesis;
         fail-closed if missing/unread/unused
         DISPATCH cf-semantic-reviewer-consistency
         IF len(target_paths) < 2:
           SKIP consistency dispatch
           LOG "consistency-skipped: single-target" to iteration trace

RULES:
  - Prompt reviewers and prompt bug-finders MUST receive ONLY prompt_targets
  - Code reviewers and code bug-finders MUST receive ONLY code_targets
  - Artifact reviewers MUST receive ONLY artifact_targets
  - Mixed prompt/code/artifact target sets MUST be reviewed by every applicable
    reviewer; PROMPT_REVIEW must not suppress code or artifact review for
    non-prompt targets in the same iteration
  - Each reviewer's dispatch contract lives in its prompt file under
    {cf-studio-path}/.core/skills/studio/agents/
  - MUST apply sub-agent-dispatch.md § SubAgentContractReadGate before every
    reviewer DISPATCH or parallel reviewer dispatch
  - MUST supply exact JSON fields each reviewer declares
  - MUST NOT skip dispatch for registered reviewers when trigger condition matches
```

```pdsl
UNIT Phase52InlineFallbackWarning

PURPOSE:
  Emit long-loop context-exhaustion warning when inline mode detected with
  high MAX_ITER.

DO:
  IF INLINE_FALLBACK == true AND MAX_ITER > INLINE_LOOP_WARNING_THRESHOLD (2):
    EMIT exactly (before first iteration of this phase runs):
---
Inline mode detected with MAX_ITER={MAX_ITER}. Sequential inline review may
exhaust context (each iteration loads the full reviewer prompt set + per-target
reads in this orchestrator's context window). Recommend reducing MAX_ITER to 2
or splitting the run. Reply `reduce: N` (1 <= N <= current MAX_ITER) to lower
MAX_ITER, or `continue` to proceed at risk.
---
    WAIT user.reply
    STOP_TURN

MENU InlineFallbackWarningMenu:
  TITLE: Inline mode long-loop warning
  OPTIONS:
    reduce: N (1 <= N <= current MAX_ITER, valid) ->
      SET MAX_ITER = N
      CONTINUE
    reduce: N (out-of-range) ->
      EMIT "reduce: N must satisfy 1 <= N <= {current MAX_ITER}; reply again or `continue`."
      WAIT user.reply
      STOP_TURN
    continue ->
      CONTINUE with original MAX_ITER
    stop_token ->
      LOAD {cf-studio-path}/.core/workflows/shared/stop-token-policy.md
      CANCEL current Phase 5 entry before any validator/reviewer/author dispatch
      IF manifest.paths_written is non-empty (file-writing generate run with Phase 4 complete):
        EMIT Pre-Review Warning Handoff block (below)
      IF no files written (e.g. analyze→generate external entry):
        RETURN control to user without Phase 6
```

## Pre-Review Warning Handoff

```pdsl
UNIT Phase52PreReviewWarningHandoff

PURPOSE:
  Emit terminal handoff when user stops at inline warning after files were written.

DO:
  EMIT exactly:
---
Pre-Review Warning Handoff
Files were already written, but automatic review did not run because you stopped
at the inline long-loop warning before any validator, reviewer, or author dispatch.

Suggested next step: Invoke skill `cf-analyze` on the written files when you want review coverage.
You may also resume Invoke skill `cf-generate` with mode=fix later if you want to continue the review/fix loop from these files.
---

RULES:
  - MUST emit ONLY on the file-writing stop path (manifest.paths_written non-empty)
  - MUST NOT route through workflows/generate/phase-6/index.md
    (no valid Validation Results body exists yet)
  - This is the canonical source of the Pre-Review Warning Handoff text
```

```pdsl
UNIT Phase52ReviewerDispatchContracts

PURPOSE:
  Define per-reviewer orchestrator-supplied dispatch values.

NOTES:
  cf-semantic-reviewer-artifact:
    target_paths = artifact_targets
    kit_rules_path = resolved from rules.md (null in RELAXED non-kit)
    checklist_path = {kit_path}/artifacts/{KIND}/checklist.md (null when no kit)
    template_path = {kit_path}/artifacts/{KIND}/template.md (null when unavailable)
    example_path = {kit_path}/artifacts/{KIND}/examples/example.md (null when unavailable)
    cross_ref_paths = parent/sibling artifacts from phase-0.5-clarify.md
    rules_mode = {STRICT|RELAXED}
    traceability_mode = from artifacts.toml

  cf-semantic-reviewer-code:
    design_artifact_path = from phase-0.5-clarify.md
    code_paths = code_targets
    diff_scope = Phase 0 diff scope when present
    cross_ref_paths, rules_mode, traceability_mode
    kit_rules_path = resolved from rules.md

  cf-semantic-reviewer-prompt:
    target_paths = prompt_targets
    kit_rules_path = resolved from rules.md (when loaded)
    rules_mode, cross_ref_paths

  cf-semantic-reviewer-consistency:
    target_paths = artifact_targets for artifact-only checks;
                   full review surface when consistency rule explicitly spans
                   prompt/workflow targets
    baseline_path = resolved baseline from rules.md or user-specified or null
    kit_rules_path (when loaded), rules_mode
    namespace_prefix = "Rcons"

  cf-code-bug-finder:
    design_artifact_path = from phase-0.5-clarify.md
    code_paths = code_targets
    cross_ref_paths, rules_mode
    kit_rules_path = resolved from rules.md
    Only dispatched when CODE_BUG_REVIEW=true

  cf-prompt-bug-finder:
    target_paths = prompt_targets
    kit_rules_path = resolved from rules.md (when loaded)
    rules_mode, cross_ref_paths
    Only dispatched when PROMPT_BUG_REVIEW=true
```

```pdsl
UNIT Phase52ReviewerReturnHandling

PURPOSE:
  Handle reviewer returns and merge findings with namespacing.

DO:
  FOR each reviewer return:
    SET SEMANTIC_REVIEW_PARTIAL = false
    Normalize the returned discriminator into reviewer_return.type from either
      review_result.type or checkpoint.type; if both are present or neither is
      present, fail closed as malformed reviewer output.
    IF reviewer_return.type == "VALIDATION_REPORT":
      REQUIRE the reviewer-owned Validation Report — <Section> block and findings JSON
    IF reviewer_return.type == "PARTIAL_CHECKPOINT":
      REQUIRE reviewer-owned Partial Checkpoint — <Section> block,
        checkpoint JSON, and findings JSON
      STORE checkpoint under semantic_partial_checkpoints[reviewer_name]
      SET SEMANTIC_REVIEW_PARTIAL = true
      MERGE only findings backed by already-covered evidence
      MUST NOT require Validation Report — <Section> block for that reviewer
      MUST NOT treat its absence as dispatch failure
      NOTE: PARTIAL_CHECKPOINT only supported by reviewers whose contract declares it

  IF any reviewer returns PARTIAL_CHECKPOINT:
    APPEND each checkpoint to iteration trace without overwriting other reviewer checkpoints
    SKIP author auto-fix for the checkpoint itself
    HAND control to phase-5.3-findings.md WITH all_findings containing only
      validator/reviewer findings backed by already-covered evidence
    NOTE: Phase 5.3 / Phase 6 MUST preserve separate partial-checkpoint state,
          keep run non-clean, set remaining_findings non-empty or surface partial
          semantic coverage before exit

  NAMESPACE findings:
    validator: V-NNN
    artifact-reviewer: Ra-NNN
    code-reviewer: Rc-NNN
    code-bug-finder: Rcb-NNN
    prompt-reviewer: Rp-NNN
    prompt-bug-finder: Rpb-NNN
    consistency-reviewer: Rcons-NNN
  RE-NUMBER within each namespace starting from 001
  REWRITE id field on every finding before partitioning
  SET all_findings = det_findings + sum(reviewer findings)

  APPEND one phase5_dispatch_evidence record per semantic reviewer dispatch:
    phase = "5.2"
    agent_id = reviewer agent id
    target_paths = reviewer target_paths
    result_marker = returned review report marker
    FOR PARTIAL_CHECKPOINT: also set
      result_marker = "Partial Checkpoint — <Section>" block name
      status = "PARTIAL"
      reviewer name from checkpoint JSON

RULES:
  - MUST NOT synthesize PARTIAL_CHECKPOINT shape for reviewers without that contract
  - MUST merge findings with namespacing before handing to Phase 5.3
  - MUST append dispatch evidence record per reviewer dispatch before handing to Phase 5.3
```
