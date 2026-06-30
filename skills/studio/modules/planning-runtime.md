# Planning Runtime

Use this module when a thin planning skill or preset must build an integrable
phase plan from declared artifacts, prerequisites, and phase-checklist
contracts instead of compiling standalone plan packages.

```pdsl
UNIT PlanningRuntimeContractLoad
PURPOSE: Load the shared runtime contracts required by thin integrable planning skills.
DO:
  RUN PlanningRuntimeCoreLoad
  RUN PlanningRuntimePhaseLoad
RULES:
  ALWAYS use this load unit before a thin planning skill evaluates prerequisite artifacts or emits planning outputs
  NEVER treat this load unit as permission to invoke producer skills automatically

```

```pdsl
UNIT PlanningRuntimeCoreLoad
PURPOSE: Load the prerequisite and context contracts for planning, then run the IO contract.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/skill-io-contract-load.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/resource-context-check.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/design-input-check.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/missing-inputs-report.md
  RUN SkillIoContractLoad

```

```pdsl
UNIT PlanningRuntimePhaseLoad
PURPOSE: Load the phase-tracking and artifact-linking contracts for planning.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/handoff-suggestions.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/phase-artifact-linking.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/phase-status-mark.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/artifact-dod-check.md
```

```pdsl
UNIT PlanningInputContract
PURPOSE: Define the caller-owned contract surface for integrable planning.
STATE:
  SET PLANNING_DOMAIN: generic | code | docs | skills | kits | unset (default unset, scope workflow_run)
  SET AVAILABLE_ARTIFACTS: list | unset (default unset, scope workflow_run)
  SET RESOURCE_CONTEXT_REQUIREMENT: required | optional | not-needed | unset (default unset, scope workflow_run)
  SET DESIGN_REQUIRED_INPUT_SPECS: list | unset (default unset, scope workflow_run)
  SET PHASE_CHECKLIST_CONTRACT: list | unset (default unset, scope workflow_run)
  SET PHASE_OUTPUT_CONTRACT: list | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE PLANNING_DOMAIN != unset
  REQUIRE AVAILABLE_ARTIFACTS is provided
  REQUIRE PHASE_CHECKLIST_CONTRACT is provided
DO:
  SET RESOURCE_CONTEXT_REQUIREMENT = optional WHEN RESOURCE_CONTEXT_REQUIREMENT == unset
NOTES:
  The 'generic' domain value is reserved for future use; no preset currently binds it.
RULES:
  ALWAYS require the caller or preset to declare what every planned phase must contain through PHASE_CHECKLIST_CONTRACT
  ALWAYS allow PHASE_OUTPUT_CONTRACT to remain unset when the caller relies on planning defaults
  ALWAYS keep AVAILABLE_ARTIFACTS as artifact descriptors or refs, not copied artifact bodies
  NEVER compile standalone briefs, plan.toml manifests, or phase files in this runtime
```

```pdsl
UNIT PlanningPrerequisiteResolution
PURPOSE: Resolve design and context prerequisites for integrable planning.
STATE:
  SET DESIGN_INPUT_STATUS: ready | blocked | unset (default unset, scope unit_run)
  SET RESOURCE_CONTEXT_STATUS: ready | blocked | skipped | unset (default unset, scope unit_run)
  SET suggested_next_skills: list | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE AVAILABLE_ARTIFACTS is provided
DO:
  RUN DesignInputCheckContract
  RUN ResourceContextCheckContract WHEN RESOURCE_CONTEXT_REQUIREMENT != unset
  RUN HandoffSuggestionsContract WHEN DESIGN_INPUT_STATUS == blocked OR RESOURCE_CONTEXT_STATUS == blocked
RULES:
  ALWAYS block planning when required design intent is insufficient
  ALWAYS block planning when required resource-context style inputs are absent or out of scope
  ALWAYS leave blocked recovery explicit through suggested_next_skills
  NEVER invoke brainstorm, write-docs, or explore automatically from this unit
  NEVER use Bash, Grep, Read, Glob, or any inline tool call as a substitute for a missing required resource-context input; ALWAYS treat missing required resource-context as a hard block and route to PlanningBlocked
```

```pdsl
UNIT PlanningPhaseContract
PURPOSE: Define the canonical shape of an integrable phase plan.
RULES:
  ALWAYS represent each planned phase with phase_id, goal, prerequisites, skill_sequence, checklist, expected_outputs, and completion_signal
  ALWAYS keep prerequisites artifact-oriented and skill_sequence skill-oriented
  ALWAYS require skill_sequence to use explicit standalone skill names rather than hidden workflow prose
  ALWAYS keep checklist entries aligned to PHASE_CHECKLIST_CONTRACT and expected_outputs aligned to PHASE_OUTPUT_CONTRACT or caller defaults
  NEVER compile a phase into a standalone prompt package in this contract
```

```pdsl
UNIT PlanningChecklistContract
PURPOSE: Define the minimum machine-readable shape for caller-owned phase checklist contracts.
RULES:
  ALWAYS require each PHASE_CHECKLIST_CONTRACT entry to include section_key, required, and summary
  ALWAYS allow each entry to include expected_skills, expected_artifacts, and completion_hint
  ALWAYS keep the contract generic so presets may define code, docs, or skills phase checklists without changing the planning engine
  NEVER hardcode one universal phase template in this module
```

```pdsl
UNIT PlanningLegacySeparationContract
PURPOSE: Keep integrable planning distinct from the legacy standalone planner lifecycle.
RULES:
  ALWAYS keep integrable planning focused on reusable phase-plan and phase-dod outputs
  ALWAYS leave standalone plan packaging, chunk package persistence, and compiled phase-file orchestration to the backward-compatible cf-plan workflow
  NEVER write plan.toml, brief files, or compiled phase files from an integrable planning skill
```

```pdsl
UNIT PlanSaveGateContract
PURPOSE: Offer to save the synthesized plan as a Markdown file before execution begins.
STATE:
  SET PLAN_SAVE_MODE: unset | save | skip (default unset, scope workflow_run)
  SET PLAN_FILE_PATH: string | unset (default unset, scope workflow_run)
  SET PLAN_FILE_SLUG: string | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE PLAN_SAVE_MODE == unset
DO:
  SET PLAN_FILE_SLUG = derive from ORIGINAL_INTENT: lowercase, spaces to hyphens, non-ASCII stripped, truncated to 40 chars
  SET PLAN_FILE_PATH = {cf-studio-path}/.cache/planning/{PLAN_FILE_SLUG}-{ISO-date}.md
  EMIT_MENU PlanSaveGateMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS run this gate after the plan is synthesized and before any phase execution or dispatch begins
  ALWAYS also write a copy to {cf-studio-path}/.cache/planning/current.md WHEN PLAN_SAVE_MODE == save
  ALWAYS add plan_file = PLAN_FILE_PATH to the dispatch payload of every phase WHEN PLAN_SAVE_MODE == save
  NEVER block phase execution when PLAN_SAVE_MODE == skip
MENU PlanSaveGateMenu
TITLE: Save this plan as a Markdown file before execution? The file will be updated with checkboxes as each phase completes.
OPTIONS:
  1 save (suggested) — recommended — saves progress as checkboxes you can resume if context is lost -> SET PLAN_SAVE_MODE = save
  2 skip — skip if you prefer no disk writes -> SET PLAN_SAVE_MODE = skip
  INVALID -> EMIT_MENU PlanSaveGateMenu
```

```pdsl
UNIT PlanMarkdownWriteContract
PURPOSE: Write the synthesized plan as a Markdown file with H2 phase headings and task checkboxes.
WHEN:
  REQUIRE PLAN_SAVE_MODE == save
  REQUIRE PLAN_FILE_PATH != unset
DO:
  RUN derive Markdown content: H1 title from ORIGINAL_INTENT, then for each phase an H2 heading "## Phase N: {phase title}" followed by "- [ ] {task}" lines
  RUN ensure parent directory of PLAN_FILE_PATH exists
  WRITE derived Markdown content to PLAN_FILE_PATH
  WRITE derived Markdown content to {cf-studio-path}/.cache/planning/current.md
  EMIT "Plan saved to {PLAN_FILE_PATH}"
RULES:
  ALWAYS use "- [ ]" for uncompleted tasks and "- [x]" for completed tasks
  ALWAYS add "✓ " prefix to an H2 phase heading when all tasks in that phase are marked [x]
  NEVER overwrite a current.md that belongs to a different active plan without confirmation
  NEVER write plan.toml, brief files, or compiled phase files from this contract (PlanningLegacySeparationContract applies)
```
