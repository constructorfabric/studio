---
cf: true
type: workflow-phase
name: plan-phase-3-compile
description: "Invoke when cf-plan enters Phase 3 to write the plan manifest, generate compilation briefs, present the post-brief choice menu, produce phase files or phase-generation prompts, and validate compiled phase files."
loaded_by: workflows/plan.md
version: 1.0
---

# Plan Phase 3: Compile

```pdsl
UNIT Phase3Init
PURPOSE: Load plan template requirements before compilation.
DO:
  - RUN OPEN {cf-studio-path}/.core/requirements/plan-template.md
  - RUN FOLLOW plan-template.md
NOTES:
  Phase 3 minimizes context: write manifest, write briefs, stop for user choice on phase-file production.
  Manifest and all brief-* files are mandatory outputs of cf-plan.
```

```pdsl
UNIT Phase3WriteManifest
PURPOSE: Write plan.toml before phase compilation begins.
DO:
  - SET CF_PHASE_GATE = released_for_orchestrator_write
    scope = {cf-studio-path}/.plans/{task-slug}/plan.toml
  - RUN WRITE {cf-studio-path}/.plans/{task-slug}/plan.toml with content:
    [meta]
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
  - SET CF_PHASE_GATE = armed
RULES:
  - ALWAYS write plan.toml after decomposition and lifecycle selection, BEFORE phase compilation
  - ALWAYS reopen CF_PHASE_GATE = released_for_orchestrator_write scope=plan.toml for any later mutation of plan.toml
  - ALWAYS reset CF_PHASE_GATE = armed immediately after each mutation completes or fails
NOTES:
  input_dir, input_manifest, input_signature: omit or set "" when no raw-input package was created.
```

```pdsl
UNIT Phase3GenerateBriefs
PURPOSE: Write a compilation brief for each phase (~50-80 lines each).
DO:
  - RUN OPEN {cf-studio-path}/.core/requirements/brief-template.md
  - RUN FOLLOW brief-template.md
  - RUN FOR each phase:
    - SET CF_PHASE_GATE = released_for_orchestrator_write
      scope = {cf-studio-path}/.plans/{task-slug}/brief-*.md
    ESTIMATE kit file sizes with wc -l
    LIST examples with ls
    FILL brief from plan.toml
    WRITE {cf-studio-path}/.plans/{task-slug}/brief-{NN}-{slug}.md
      containing: context boundary, phase metadata, load instructions,
                  phase file structure, context budget
      - NEVER including copied kit content or the phase file itself
    - SET CF_PHASE_GATE = armed
RULES:
  - ALWAYS IF plan.input_chunks non-empty: ALWAYS include assigned input/*.md chunks in input_files metadata
    and Load Instructions with runtime-read steps for every listed chunk
  - ALWAYS treat phase.inputs entries as execution-time dependencies by default
  - ALWAYS IF a phase.inputs entry points under out/: ALWAYS describe it as a runtime artifact from an earlier phase,
    ALWAYS preserve it in phase metadata and runtime Task reads,
    NEVER require it to exist at brief-generation or phase-compilation time
```

```pdsl
UNIT Phase3BriefCheckpointMenu
PURPOSE: Pause after briefs are on disk and obtain user choice for phase file production.
WHEN:
  - REQUIRE plan.toml AND every brief-* file exist on disk
DO:
  - EMIT_MENU BriefCheckpointChoiceMenu
  - WAIT user.reply
  - STOP_TURN

MENU BriefCheckpointChoiceMenu:
  TITLE: Brief package prepared — choose how to produce phase files
  PREAMBLE:
    Brief package prepared: {cf-studio-path}/.plans/{task-slug}/
      Manifest: plan.toml
      Briefs: {N}
      Compiled phase files: 0/{N}

    [1] Generate phase files here — compile phases in the current chat from the briefs
    [2] Generate phase-compilation prompts — emit one self-contained prompt per brief for downstream chats
    [3] Run phase-compiler subagents — invoke cf-phase-compiler for each brief
    [4] Stop here — keep the manifest and briefs without compiling phase files yet

    Reply with 1, 2, 3, or 4.
  OPTIONS:
    1 -> CONTINUE Phase3ProducePhaseFilesInline
    2 ->
      SET PHASE_3_4_VALIDATION = skipped
      EMIT "WARNING: Phase 3.4 validation is bypassed in prompt-generation mode. Phase files will not be validated in this run."
      CONTINUE Phase3ProduceDownstreamPrompts
    3 -> CONTINUE Phase3ProduceViaSubagents
    4 ->
      SET CF_PHASE_GATE = released_for_orchestrator_write
        scope = {cf-studio-path}/.plans/{task-slug}/plan.toml
      SET plan.execution_status = "briefs_only" in plan.toml
      SET CF_PHASE_GATE = armed
      STOP_TURN
  INVALID:
    EMIT "Reply with 1, 2, 3, or 4."
    WAIT user.reply
    STOP_TURN
RULES:
  - ALWAYS wait for user choice before entering Phase 3.3
  - NEVER emit "Plan created" at this checkpoint
```

```pdsl
UNIT Phase3ContextBoundary
PURPOSE: Reset context before reading each brief for phase compilation.
DO:
  - EMIT:
    --- CONTEXT BOUNDARY ---
    Disregard previous workflow context except plan.toml metadata and recorded user decisions.
    The brief below is self-contained.
    Read ONLY the files listed in the brief. Follow its instructions exactly.
    ---
```

```pdsl
UNIT Phase3ProducePhaseFilesInline
PURPOSE: Compile phase files in the current chat from briefs (option [1]).
DO:
  - RUN FOR each phase:
    - CONTINUE Phase3ContextBoundary
    READ brief FROM DISK at {cf-studio-path}/.plans/{task-slug}/{brief_file}
    IF brief not on disk: GO BACK to Phase3GenerateBriefs
    - SET CF_PHASE_GATE = released_for_orchestrator_write
      scope = {cf-studio-path}/.plans/{task-slug}/phase-*.md
    COMPILE exactly one phase-* file from that brief
    VALIDATE compiled file against the brief
    - EMIT "Phase {N} compiled inline → {filename} ({lines} lines)"
    - SET CF_PHASE_GATE = armed
RULES:
  - ALWAYS read brief FROM DISK; using a brief not read from disk is INVALID
  - ALWAYS reset CF_PHASE_GATE = armed immediately after each write completes or fails
- ALWAYS CONTINUE Phase3ValidatePhaseFiles
```

```pdsl
UNIT Phase3ProduceDownstreamPrompts
PURPOSE: Emit one self-contained downstream prompt per brief (option [2]).
DO:
  - RUN FOR each phase:
    - CONTINUE Phase3ContextBoundary
    READ brief FROM DISK at {cf-studio-path}/.plans/{task-slug}/{brief_file}
    - EMIT exactly one self-contained downstream prompt for that brief
      (prompt ALWAYS instruct downstream worker to read brief from disk,
       apply context boundary, and compile exactly one phase file)
    - EMIT "Phase {N} prompt prepared → {brief_file}"
  - RUN AFTER all downstream prompts emitted:
    - SET CF_PHASE_GATE = released_for_orchestrator_write
      scope = {cf-studio-path}/.plans/{task-slug}/plan.toml
    - SET plan.execution_status = "prompts_emitted"
    - SET CF_PHASE_GATE = armed
RULES:
  - NEVER write phase-* files in this mode
  - ALWAYS Emitted prompts are the deliverable for option [2]
  - ALWAYS PHASE_3_4_VALIDATION remains skipped; NEVER run Phase3ValidatePhaseFiles
```

```pdsl
UNIT Phase3ProduceViaSubagents
PURPOSE: Route phase compilation to cf-phase-compiler subagents (option [3]).
DO:
  - REQUIRE Session Sub-Agent Approval Gate ({cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md) is resolved
  - RUN OPEN {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md
  - RUN FOLLOW {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md
  - REQUIRE INLINE_FALLBACK == true:
    - EMIT "Option [3] is unavailable for this run (INLINE_FALLBACK=true)."
    - EMIT_MENU InlineFallbackRerouteMenu
    - WAIT user.reply
    - STOP_TURN

MENU InlineFallbackRerouteMenu:
  TITLE: Option [3] unavailable — choose an alternative production method
  OPTIONS:
    1 -> CONTINUE Phase3ProducePhaseFilesInline
    2 ->
      SET PHASE_3_4_VALIDATION = skipped
      EMIT "WARNING: Phase 3.4 validation is bypassed in prompt-generation mode. Phase files will not be validated in this run."
      CONTINUE Phase3ProduceDownstreamPrompts
  INVALID:
    EMIT "Reply with 1 or 2."
    WAIT user.reply
    STOP_TURN

  IF SUB_AGENT_SESSION_APPROVED == true AND INLINE_FALLBACK == false:
    FOR each phase:
      CONTINUE Phase3ContextBoundary
      READ brief FROM DISK at {cf-studio-path}/.plans/{task-slug}/{brief_file}
      LOAD {cf-studio-path}/.core/skills/studio/agents/cf-phase-compiler.md as compiler source contract
      RESOLVE prompt_engineering_context from SHARED_CONTEXT_PACK slice
        `{cf-studio-path}/.core/requirements/prompt-engineering.md`
      REQUIRE prompt_engineering_context slice is present and complete
      SYNTHESIZE final dispatch prompt from compiler contract,
        SHARED_CONTEXT_PACK prompt_context_view slices, prompt_engineering_context,
        and payload below
      IF compiler source contract is not loaded, unreadable, ambiguous, or not reflected in final dispatch prompt:
        FAIL per {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md § SubAgentContractReadGate
        NEVER dispatch
      SET CF_PHASE_GATE = released_for_dispatch
      DISPATCH cf-phase-compiler with synthesized final prompt including:
          brief_file = {cf-studio-path}/.plans/{task-slug}/{brief_file}
          git_commit_mode = GIT_COMMIT_MODE
          contributing_guide = CONTRIBUTING_GUIDE
          git_constraint = mode-matched constraint block from {cf-studio-path}/.core/workflows/generate/phase-4-write.md § Git constraint blocks
      ACCEPT result only IF it reports: compile summary, phase identity, output file path, compile-time validation outcome
      EMIT "Phase {N} compiled via subagent → {filename} ({lines} lines)"
      SET CF_PHASE_GATE = armed
RULES:
  - NEVER dispatch before Sub-Agent Approval Gate is resolved
  - ALWAYS set CF_PHASE_GATE = released_for_dispatch immediately before each dispatch
  - ALWAYS reset CF_PHASE_GATE = armed immediately after each subagent returns
  - ALWAYS Payload ALWAYS include git_commit_mode, contributing_guide, and git_constraint
  - ALWAYS provide prompt_engineering_context through prompt_context_view before
    dispatch; NEVER dispatch if the slice is missing or incomplete
  - ALWAYS cf-phase-compiler NEVER reopen prompt-engineering.md or workflow prompt
    assets from disk
- ALWAYS CONTINUE Phase3ValidatePhaseFiles
NOTES:
  Planner remains responsible for decomposition, manifest creation, and brief generation.
```

```pdsl
UNIT Phase3ValidatePhaseFiles
PURPOSE: Validate all compiled phase files before handoff to Phase 4.
WHEN:
  - REQUIRE PHASE_3_4_VALIDATION != skipped AND user chose option [1] or [3] AND phase files generated this run
DO:
  - RUN AFTER all phases compiled, verify ALL of:
    - Every brief_file exists on disk
    - Each phase file matches its brief's load instructions
    - Unresolved {...} variables outside code fences = zero
    - Phase file size <= 1000 lines; IF oversized: SPLIT
    - Rules completeness: every applicable ALWAYS/NEVER from rules.md present;
       IF adding missing rules breaks budget: RE-SPLIT; NEVER drop rules to meet budget
    - Context budget: phase_file_lines + input_files + inputs + output_lines <= 2000; IF oversized: SPLIT
    - After final phase: union of all Rules sections covers 100% of applicable rules
```
