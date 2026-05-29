---
cf: true
type: workflow-phase
name: plan-phase-3-compile
description: "Invoke when /cf-plan enters Phase 3 to write the plan manifest, generate compilation briefs, present the post-brief choice menu, produce phase files or phase-generation prompts, and validate compiled phase files."
loaded_by: workflows/plan.md
version: 1.0
---

# Phase 3: Compile Phase Files

<!-- toc -->

- [3.1 Write Plan Manifest](#31-write-plan-manifest)
- [3.2 Generate Compilation Briefs (from Template)](#32-generate-compilation-briefs-from-template)
- [3.2A Stop After Briefs & Ask For Next Step](#32a-stop-after-briefs--ask-for-next-step)
- [3.3 Produce Phase Files Or Phase-Generation Prompts](#33-produce-phase-files-or-phase-generation-prompts)
- [3.4 Validate Phase Files](#34-validate-phase-files)

<!-- /toc -->

```text
UNIT Phase3Init

PURPOSE:
  Load plan template requirements before compilation.

DO:
  OPEN {cf-studio-path}/.core/requirements/plan-template.md
  FOLLOW plan-template.md

NOTES:
  Phase 3 is split to minimize context: write the manifest, write briefs, then stop
  for an explicit user choice about how phase files should be produced.
  The manifest and all brief-* files are mandatory outputs of /cf-plan.
```

## 3.1 Write Plan Manifest

```text
UNIT Phase3WriteManifest

PURPOSE:
  Write plan.toml before phase compilation begins.

DO:
  SET CF_PHASE_GATE = released_for_orchestrator_write
    scope = {cf-studio-path}/.plans/{task-slug}/plan.toml

  WRITE {cf-studio-path}/.plans/{task-slug}/plan.toml with content:

    [meta]
    # Variables resolved in Phase 0 from `{cfs_cmd} --json info`.
    # Persisted here so the runtime can read them on resume after context compaction
    # without re-deriving them; refresh by re-running `{cfs_cmd} --json info` if stale.
    cfs_cmd = "{resolved cfs_cmd value}"
    cf_studio_path = "{absolute cf_studio_path}"
    project_root = "{absolute project_root}"
    # variables = "{path to JSON snapshot}"  # OPTIONAL

    [plan]
    task = "{task description}"
    type = "{generate|analyze|implement}"
    target = "{artifact kind}"
    target_key = "{canonical target identity}"
    kit_path = "{absolute path to kit}"
    created = "{ISO 8601 timestamp}"
    lifecycle = "{gitignore|cleanup|archive|manual}"
    execution_status = "not_started"
    lifecycle_status = "pending"
    plan_dir = "{cf-studio-path}/.plans/{task-slug}"
    active_plan_dir = "{cf-studio-path}/.plans/{task-slug}"
    input_dir = "{cf-studio-path}/.plans/{task-slug}/input"
    input_manifest = "{cf-studio-path}/.plans/{task-slug}/input/manifest.json"
    input_signature = "{sha256 of direct prompt + provided file contents}"
    input_chunks = []
    total_phases = {N}

    [[phases]]
    number = 1
    title = "{phase title}"
    slug = "{short-slug}"
    file = "phase-01-{slug}.md"
    brief_file = "brief-01-{slug}.md"
    status = "pending"
    kind = "delivery"
    depends_on = []
    input_files = []
    output_files = ["{target file}"]
    outputs = ["out/phase-01-{what}.md"]
    inputs = []
    template_sections = [1, 2, 3]
    checklist_sections = []

  SET CF_PHASE_GATE = armed  (immediately after write completes or fails)

RULES:
  - MUST write plan.toml after decomposition and lifecycle selection, BEFORE phase compilation
  - MUST reopen CF_PHASE_GATE = released_for_orchestrator_write with scope = plan.toml
    for any later mutation of plan.toml in this phase (e.g. setting execution_status)
  - MUST reset CF_PHASE_GATE = armed immediately after each such mutation completes or fails

NOTES:
  plan.execution_status tracks aggregate phase execution independently from plan-file handling.
  plan.lifecycle_status tracks whether plan storage actions are still pending, in progress,
  complete, or awaiting manual resolution.
  input_dir, input_manifest, input_signature: omit or set "" when no raw-input package was created.
```

## 3.2 Generate Compilation Briefs (from Template)

```text
UNIT Phase3GenerateBriefs

PURPOSE:
  Write a compilation brief for each phase (~50-80 lines each).

DO:
  ALWAYS OPEN {cf-studio-path}/.core/requirements/brief-template.md
  FOLLOW brief-template.md

  FOR each phase:
    SET CF_PHASE_GATE = released_for_orchestrator_write
      scope = {cf-studio-path}/.plans/{task-slug}/brief-*.md
    ESTIMATE kit file sizes with wc -l
    LIST examples with ls
    FILL brief from plan.toml
    WRITE {cf-studio-path}/.plans/{task-slug}/brief-{NN}-{slug}.md
      containing: context boundary, phase metadata, load instructions,
                  phase file structure, context budget
      FORBID including copied kit content or the phase file itself
    SET CF_PHASE_GATE = armed  (immediately after write completes or fails)

RULES:
  - IF plan.input_chunks is non-empty:
      MUST include specific input/*.md chunk files assigned to that phase in
      both input_files metadata and Load Instructions with runtime-read steps
      for every listed chunk
  - MUST treat `phase.inputs` entries as execution-time dependencies by default
  - IF a `phase.inputs` entry points under `out/`:
      MUST describe it in the brief as a runtime artifact from an earlier phase,
      MUST preserve it in phase metadata and runtime Task reads,
      and MUST NOT require it to exist at brief-generation or phase-compilation time
```

## 3.2A Stop After Briefs & Ask For Next Step

```text
UNIT Phase3BriefCheckpointMenu

PURPOSE:
  Pause after briefs are on disk and obtain user choice for phase file production.

WHEN:
  plan.toml AND every brief-* file exist on disk

DO:
  EMIT_MENU BriefCheckpointChoiceMenu
  WAIT user.reply
  STOP_TURN

MENU BriefCheckpointChoiceMenu:
  TITLE: Brief package prepared — choose how to produce phase files
  PREAMBLE:
    Brief package prepared: {cf-studio-path}/.plans/{task-slug}/
      Manifest: plan.toml
      Briefs: {N}
      Compiled phase files: 0/{N}

    What would you like to do next?

    The manifest and briefs are ready on disk. Choose how to produce the phase files:

      [1] Generate phase files here — compile phases in the current chat from the briefs
      [2] Generate phase-compilation prompts — emit one self-contained prompt per brief for downstream chats
      [3] Run phase-compiler subagents — invoke `cf-phase-compiler` for each brief
      [4] Stop here — keep the manifest and briefs without compiling phase files yet

    [1] Suggested when you want to keep working in this chat and compile phase files now.
    [2] Emit downstream prompts instead of compiling phase files here.
    [3] Use dedicated phase-compiler subagents for compilation.
    [4] Stop after the brief package and resume later.

    Reply with `1`, `2`, `3`, or `4`.
  OPTIONS:
    1 -> CONTINUE Phase3ProducePhaseFilesInline
    2 -> CONTINUE Phase3ProduceDownstreamPrompts
    3 -> CONTINUE Phase3ProduceViaSubagents
    4 ->
      SET CF_PHASE_GATE = released_for_orchestrator_write
        scope = {cf-studio-path}/.plans/{task-slug}/plan.toml
      SET plan.execution_status = "briefs_only"  in plan.toml
      SET CF_PHASE_GATE = armed
      STOP_TURN  (valid plan state; resume in a new chat by reading plan.toml and re-presenting [1]-[4])
  INVALID:
    EMIT "Reply with 1, 2, 3, or 4."
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST wait for user choice before entering Phase 3.3
  - MUST NOT emit "Plan created" at this checkpoint
```

## 3.3 Produce Phase Files Or Phase-Generation Prompts

```text
UNIT Phase3ContextBoundary

PURPOSE:
  Reset context before reading each brief for phase compilation.

DO:
  EMIT:
    --- CONTEXT BOUNDARY ---
    Disregard previous workflow context except plan.toml metadata and recorded user decisions.
    The brief below is self-contained.
    Read ONLY the files listed in the brief. Follow its instructions exactly.
    ---
```

```text
UNIT Phase3ProducePhaseFilesInline

PURPOSE:
  Compile phase files in the current chat from briefs (option [1]).

DO:
  FOR each phase:
    CONTINUE Phase3ContextBoundary
    READ brief FROM DISK at {cf-studio-path}/.plans/{task-slug}/{brief_file}
    IF brief not on disk:
      GO BACK to Phase3GenerateBriefs
    SET CF_PHASE_GATE = released_for_orchestrator_write
      scope = {cf-studio-path}/.plans/{task-slug}/phase-*.md
    COMPILE exactly one phase-* file from that brief
    VALIDATE compiled file against the brief
    EMIT "Phase {N} compiled inline → {filename} ({lines} lines)"
    SET CF_PHASE_GATE = armed  (immediately after write completes or fails)

RULES:
  - MUST read brief FROM DISK; using a brief not read from disk is INVALID
  - MUST reset CF_PHASE_GATE = armed immediately after each write completes or fails

CONTINUE Phase3ValidatePhaseFiles
```

```text
UNIT Phase3ProduceDownstreamPrompts

PURPOSE:
  Emit one self-contained downstream prompt per brief (option [2]).

DO:
  FOR each phase:
    CONTINUE Phase3ContextBoundary
    READ brief FROM DISK at {cf-studio-path}/.plans/{task-slug}/{brief_file}
    EMIT exactly one self-contained downstream prompt for that brief
      (prompt MUST instruct downstream worker to read brief from disk,
       apply context boundary, and compile exactly one phase file)
    EMIT "Phase {N} prompt prepared → {brief_file}"

  AFTER all downstream prompts emitted (one per brief):
    SET CF_PHASE_GATE = released_for_orchestrator_write
      scope = {cf-studio-path}/.plans/{task-slug}/plan.toml
    SET plan.execution_status = "prompts_emitted"
    SET CF_PHASE_GATE = armed

RULES:
  - MUST NOT write phase-* files in this mode
  - The emitted prompts are the deliverable for option [2]
```

```text
UNIT Phase3ProduceViaSubagents

PURPOSE:
  Route phase compilation to cf-phase-compiler subagents (option [3]).

DO:
  REQUIRE Session Sub-Agent Approval Gate ({cf-studio-path}/.core/skills/studio/SKILL.md) is resolved before this option runs
  OPEN {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md
  FOLLOW {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md

  IF INLINE_FALLBACK == true:
    EMIT "Option [3] is unavailable for this run (INLINE_FALLBACK=true)."
    EMIT_MENU InlineFallbackRerouteMenu
    WAIT user.reply
    STOP_TURN

MENU InlineFallbackRerouteMenu:
  TITLE: Option [3] unavailable — choose an alternative production method
  OPTIONS:
    1 -> CONTINUE Phase3ProducePhaseFilesInline
    2 -> CONTINUE Phase3ProduceDownstreamPrompts
  INVALID:
    EMIT "Reply with 1 or 2."
    WAIT user.reply
    STOP_TURN

  IF SUB_AGENT_SESSION_APPROVED == true AND INLINE_FALLBACK == false:
    FOR each phase:
      CONTINUE Phase3ContextBoundary
      READ brief FROM DISK at {cf-studio-path}/.plans/{task-slug}/{brief_file}
      SET CF_PHASE_GATE = released_for_dispatch
      DISPATCH {cf-studio-path}/.core/skills/studio/agents/cf-phase-compiler.md
        with payload:
          brief_file = {cf-studio-path}/.plans/{task-slug}/{brief_file}
          git_commit_mode = GIT_COMMIT_MODE
          contributing_guide = CONTRIBUTING_GUIDE
          git_constraint = mode-matched constraint block from workflows/generate/phase-4-write.md § Git constraint blocks
      ACCEPT result only IF it reports: compile summary, phase identity, output file path, compile-time validation outcome
      EMIT "Phase {N} compiled via subagent → {filename} ({lines} lines)"
      SET CF_PHASE_GATE = armed  (immediately after subagent returns — success, error, or no-response)

RULES:
  - MUST NOT dispatch before Sub-Agent Approval Gate is resolved
  - MUST set CF_PHASE_GATE = released_for_dispatch immediately before each dispatch
  - MUST reset CF_PHASE_GATE = armed immediately after each subagent returns
  - Payload MUST include git_commit_mode, contributing_guide, and git_constraint

CONTINUE Phase3ValidatePhaseFiles

NOTES:
  The planner remains responsible for decomposition, manifest creation, and brief generation.
  Phase-file production may happen inline, via downstream prompts, or through the dedicated
  phase compiler subagent depending on the user's post-brief choice.
```

## 3.4 Validate Phase Files

```text
UNIT Phase3ValidatePhaseFiles

PURPOSE:
  Validate all compiled phase files before handoff to Phase 4.

WHEN:
  User chose option [1] or [3] AND phase files were generated in this run

DO:
  AFTER all phases compiled, verify ALL of:
    1. Every brief_file exists on disk
    2. Each phase file matches its brief's load instructions
    3. Unresolved {...} variables outside code fences = zero
    4. Phase file size <= 1000 lines; IF oversized: SPLIT
    5. Rules completeness: every applicable MUST / MUST NOT from rules.md is present
       IF adding missing rules breaks budget: RE-SPLIT
       NEVER drop rules to meet budget
    6. Context budget: phase_file_lines + input_files + inputs + output_lines <= 2000
       IF oversized: SPLIT
    7. After final phase: union of all Rules sections covers 100% of applicable rules
```
