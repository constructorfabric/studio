---
cf: true
type: skill
name: cf-migrate-from-cypilot
description: "Post-deterministic migration cleanup orchestrator. Coordinates four sub-agents (scanner, planner, migrator, verifier) to find and resolve residual cypilot/cpt/Cypilot/Cyber Pilot references that the mechanical cfs init --migrate-from-cypilot=yes did NOT touch (source code, CI, docs, agent configs, workspaces, build files). Asks the user before each sub-agent dispatch; loops migrator ↔ verifier until clean or until the iteration cap (3) is hit. Migrates directly to Constructor Studio (one-step migration, no intermediate Cyber Constructor layout)."
version: 1.0
purpose: Migrate from cypilot directly to Constructor Studio after the deterministic mechanical run
---

# Migrate from Cypilot — Post-Deterministic Cleanup Orchestrator


<!-- toc -->

- [Goal](#goal)
- [Preconditions](#preconditions)
- [Hard Rules](#hard-rules)
- [Phases](#phases)
  - [E0: Preconditions check](#e0-preconditions-check)
  - [E1: Scanner dispatch (user-gated)](#e1-scanner-dispatch-user-gated)
  - [E2: Planner dispatch (user-gated)](#e2-planner-dispatch-user-gated)
  - [E3: Migrator dispatch (user-gated, plan-aware)](#e3-migrator-dispatch-user-gated-plan-aware)
  - [E4: Verifier dispatch (user-gated)](#e4-verifier-dispatch-user-gated)
  - [E5: Migrator ↔ Verifier loop](#e5-migrator--verifier-loop)
  - [E6: Final report](#e6-final-report)
- [Sub-agent dispatch contract](#sub-agent-dispatch-contract)
- [Validation Criteria](#validation-criteria)

<!-- /toc -->

ALWAYS open and follow `{cf-studio-path}/.core/skills/studio/SKILL.md` FIRST WHEN `{cfs_mode}` is `off`

**Type**: Orchestrator skill (loaded by the workflow-routing keyword `migrate from cypilot` / `migrate-from-cypilot`)

## Goal

```text
NOTES:
  After cfs init --migrate-from-cypilot=yes (or cfs update --migrate-from-cypilot=yes)
  runs the deterministic mechanical migration — directory copy, root managed-block swap
  (@cpt:root-agents -> @cf:root-agents), config TOML/Markdown rewrites in a fixed list —
  this skill picks up everything ELSE and produces a Constructor Studio target directly
  (one-step migration, no intermediate layout).

  Residual targets this skill addresses:
  - Source code files (*.py, *.ts, *.js, *.go, etc.) referencing cypilot/cpt/Cypilot/Cyber Pilot
  - CI configurations (.github/workflows/*.yml, .gitlab-ci.yml, .circleci/, azure-pipelines.yml)
  - Build files (pyproject.toml, package.json, Makefile, Dockerfile)
  - Documentation outside the deterministic fixed list (CONTRIBUTING.md, ARCHITECTURE.md,
    CHANGELOG.md, docs/)
  - Shell scripts, .envrc, direnv configs
  - Agent integration directories (.agents/, .claude/, .cursor/, .codex/, .windsurf/)
    — typically need cfs generate-agents to regenerate
  - Multi-repo workspaces (.studio-workspace.toml; member repos may need cascading migration)

  The orchestrator coordinates four sub-agents:
  1. Scanner  — read-only; scans the project and emits a structured findings list
  2. Planner  — read-only; categorizes findings into A/B/C
  3. Migrator — write-capable; applies the plan with Constructor Studio as the target
  4. Verifier — read-only; re-scans and compares to the manifest, reporting residue
```

## Preconditions

```text
UNIT PreconditionsCheck

PURPOSE:
  Verify that the deterministic migration has completed before this skill runs.

REQUIRE:
  - Root AGENTS.md contains <!-- @cf:root-agents --> (not <!-- @cpt:root-agents -->)
  - {cf-studio-path}/config/core.toml exists

DO:
  WHEN preconditions are unclear:
    EMIT "Has the deterministic migration (cfs init --migrate-from-cypilot=yes or equivalent)
completed successfully? [y/N]"
    WAIT user.reply
    STOP_TURN

ON_ERROR:
  preconditions_fail ->
    EMIT:
      "The deterministic migration has not completed (or was not detected).
Run one of:
    cfs init --migrate-from-cypilot=yes              # fresh install
    cfs update --migrate-from-cypilot=yes            # existing install
Then re-invoke this skill: cf migrate from cypilot"
    STOP_TURN
```

## Hard Rules

```text
UNIT HardRules

PURPOSE:
  Define orchestrator-level invariants that apply across all phases.

INVARIANTS:
  - MUST ask the user before EACH sub-agent dispatch (E1, E2, E3, E4, and each E5 loop iteration)
  - MUST_NOT dispatch any sub-agent silently
  - MUST_NOT dispatch the Migrator (write-capable) without explicit user approval AND a Plan
    from the Planner — skipping straight from Scanner to Migrator is forbidden
  - MUST present the Planner's plan to the user IN FULL before asking for Migrator approval
  - MUST cap the migrator <-> verifier loop at 3 verifier iterations; after that, halt and
    surface remaining issues for human review
  - MUST_NOT modify files outside the project root
  - MUST_NOT modify files inside {cf-studio-path}/.core/ (kit-managed; cfs update owns them)
  - MUST respect project memories:
    project_markdown_rewriter_conservative.md (preserve cpt. / line-start cpt in
      constructor-studio source — conservative rewriter strictness is input-side logic,
      not target-identifier logic)
    project_cypilot_lifecycle.md (cypilot EOL at 3.10.0; frozen support set is final)
    project_json_mode_fixture.md (existing fixture is correct)
  - MUST treat @cpt-* / @cpt:* markers in source code as needs-review by default
    (per v1.0.0 design they're intentionally preserved in constructor-studio's own source code)
  - MUST rewrite format = "Cypilot" inside [kits.<slug>] (or [kit.<slug>]) TOML tables
    to format = "CFS" — this is a targeted kit-format identifier rename and part of the
    mechanical migration; format = "CFS" is the canonical post-migration value

NOTES:
  Target identifiers for all migrator output (what the migrator writes, not what it detects):
  - target marker file: .studio-workspace.toml
  - target skill dir: skills/studio/
  - target console-script hint: cfs
  - target cache dir hint: ~/.cf-studio/cache/
  - target registry URL: constructorfabric/studio (and constructorfabric/studio-kit-sdlc for kits)
```

## Phases

### E0: Preconditions check

```text
UNIT E0_PreconditionsCheck

PURPOSE:
  Gate entry to the migration workflow on verified deterministic migration completion.

DO:
  Read root AGENTS.md
  Confirm <!-- @cf:root-agents --> is present (not <!-- @cpt:root-agents -->)
  Confirm {cf-studio-path}/config/core.toml exists
  WHEN both pass:
    EMIT "- [migrate-from-cypilot]: E0 preconditions PASS"
    CONTINUE E1
  WHEN either fails:
    EMIT preconditions_fail message (see HardRules ON_ERROR)
    STOP_TURN
```

### E1: Scanner dispatch (user-gated)

```text
UNIT E1_ScannerDispatch

PURPOSE:
  Obtain a structured findings list of residual cypilot references via read-only scan.

DO:
  EMIT_MENU E1_ScannerMenu
  WAIT user.reply
  STOP_TURN

MENU E1_ScannerMenu:
  TITLE: Phase E1 — Scanner
  OPTIONS:
    y ->
      DISPATCH cf-migrate-scanner with:
        prompt = content of {cf-studio-path}/.core/skills/studio/agents/cf-migrate-scanner.md
                 + ## Task Inputs section with:
                   project_root: absolute path
                   studio_path: absolute path
                   exclude_dirs: [".git", "{cf-studio-path}", ".studio-workspace", build caches]
      SET scan_findings = agent output
      CONTINUE E2
    N ->
      EMIT "E1 declined. Re-invoke when you want to scan."
      STOP_TURN
  INVALID:
    EMIT "Reply with y or N."
    WAIT user.reply
    STOP_TURN

NOTES:
  Scanner is read-only. It scans the project for residual cypilot/cpt/Cypilot/Cyber Pilot
  references in: source code, CI configs, build files, docs outside the deterministic fixed list,
  shell scripts, agent configs (.agents/ .claude/ .cursor/ .codex/ .windsurf/),
  workspaces (.studio-workspace.toml + member repos). No files are modified.
  Suggested reply: y
```

### E2: Planner dispatch (user-gated)

```text
UNIT E2_PlannerDispatch

PURPOSE:
  Categorize scan findings into auto-fixable, needs-review, and cascade groups.

REQUIRE:
  scan_findings is set (E1 completed)

DO:
  EMIT_MENU E2_PlannerMenu
  WAIT user.reply
  STOP_TURN

MENU E2_PlannerMenu:
  TITLE: Phase E2 — Planner
    (Scanner returned {scan_findings.count} findings. Planner is read-only.
     Produces structured plan grouped by A/B/C. No files modified.)
  OPTIONS:
    y ->
      DISPATCH cf-migrate-planner with:
        prompt = content of cf-migrate-planner.md + ## Task Inputs with:
                   scan_findings: full output of Scanner phase
      SET plan = agent output
      CONTINUE E3
    N ->
      EMIT "E2 declined. Re-invoke to run Planner."
      STOP_TURN
  INVALID:
    EMIT "Reply with y or N."
    WAIT user.reply
    STOP_TURN

NOTES:
  Categories:
    A. Auto-fixable — well-defined string substitutions with no ambiguity
    B. Needs-review — substitutions where context matters
    C. Cascade — non-substitution operations (rename to .studio-workspace.toml,
       cascade cfs init --migrate-from-cypilot=yes to workspace members,
       run cfs generate-agents to regenerate IDE integrations)
  Suggested reply: y
```

### E3: Migrator dispatch (user-gated, plan-aware)

```text
UNIT E3_MigratorDispatch

PURPOSE:
  Apply the Planner's plan to disk with Constructor Studio as the target.

REQUIRE:
  plan is set (E2 completed)

DO:
  EMIT plan IN FULL (the entire output from Planner)
  EMIT_MENU E3_MigratorMenu
  WAIT user.reply
  STOP_TURN

MENU E3_MigratorMenu:
  TITLE: Phase E3 — Migrator
    (Review the plan above. Migrator applies changes to disk.
     Target: Constructor Studio — direct migration, no intermediate layout.)
  OPTIONS:
    1 ->
      SET selection = "A"
      CONTINUE E3_RunMigrator
    2 ->
      SET selection = "AB"
      CONTINUE E3_RunMigrator
    3 ->
      SET selection = "ABC"
      CONTINUE E3_RunMigrator
    4 ->
      SET selection = "select"
      CONTINUE E3_RunMigrator
    N ->
      EMIT "E3 skipped. Plan remains in memory for this session only (re-invoke E2 to regenerate)."
      STOP_TURN
  INVALID:
    EMIT "Reply with 1, 2, 3, 4, or N."
    WAIT user.reply
    STOP_TURN

UNIT E3_RunMigrator

PURPOSE:
  Dispatch the Migrator sub-agent with the approved selection.

DO:
  DISPATCH cf-migrate-migrator with:
    prompt = content of cf-migrate-migrator.md + ## Task Inputs with:
      plan: full Planner output
      selection: which categories/items the user approved (A / AB / ABC / explicit list)
      project_root, studio_path
      target_workspace_file: ".studio-workspace.toml"
      target_skill_dir: "skills/studio/"
      target_cli: "cfs"
      target_cache_dir: "~/.cf-studio/cache/"
      target_registry_url: "constructorfabric/studio"
      target_kit_sdlc_url: "constructorfabric/studio-kit-sdlc"
      git_commit_mode: GIT_COMMIT_MODE (MUST be included; set from session-scoped flag)
      contributing_guide: CONTRIBUTING_GUIDE (MUST be included; null when not found)
      git_constraint: mode-matched constraint block from workflows/generate/phase-4-write.md
                      Git constraint blocks
  SET migration_manifest = agent output
  CONTINUE E4

RULES:
  - MUST_NOT dispatch Migrator without explicit user approval from E3_MigratorMenu
  - MUST_NOT dispatch Migrator without plan set from E2
  - MUST include git_commit_mode in dispatch inputs
  - MUST include contributing_guide in dispatch inputs

NOTES:
  Menu options:
    1. y       — apply category A (auto-fixable) only
    2. y+B     — apply A AND walk through B interactively
    3. y+C     — apply A AND walk B AND start C (cascade — prints commands;
                  does not auto-execute cross-repo operations)
    4. select  — interactively pick specific items from A/B/C
    N          — skip Migrator; plan stays in memory for this session only
  Suggested reply: 1
```

### E4: Verifier dispatch (user-gated)

```text
UNIT E4_VerifierDispatch

PURPOSE:
  Re-scan and diff against the migration manifest to detect residue.

REQUIRE:
  migration_manifest is set (E3 completed)

DO:
  EMIT_MENU E4_VerifierMenu
  WAIT user.reply
  STOP_TURN

MENU E4_VerifierMenu:
  TITLE: Phase E4 — Verifier
    (Migrator applied {migration_manifest.count} changes. Verifier is read-only.
     Re-runs Scanner patterns and diffs against migration manifest.)
  OPTIONS:
    y ->
      DISPATCH cf-migrate-verifier with:
        prompt = content of cf-migrate-verifier.md + ## Task Inputs with:
                   plan: full Planner output
                   migration_manifest: Migrator's output
                   project_root, studio_path
      SET verification_result = agent output
      CONTINUE E5
    N ->
      EMIT "E4 declined. Continuing to final report without verification."
      CONTINUE E6
  INVALID:
    EMIT "Reply with y or N."
    WAIT user.reply
    STOP_TURN

NOTES:
  Verifier output is either "All clean" or a residue list (findings not fixed, or new findings).
  Suggested reply: y
```

### E5: Migrator ↔ Verifier loop

```text
UNIT E5_MigratorVerifierLoop

PURPOSE:
  Iterate Migrator and Verifier until clean or until the iteration cap is hit.

STATE:
  verifier_iteration: number
    default: 1 (after E4)
    reset: never (monotonically increments within a session)

WHEN:
  verification_result reports residue

DO:
  INCREMENT verifier_iteration by 1
  WHEN verifier_iteration >= 3:
    EMIT "Verifier-loop iteration cap (3) reached"
    EMIT residue list
    CONTINUE E6

  EMIT_MENU E5_MigratorMenu
  WAIT user.reply
  STOP_TURN

MENU E5_MigratorMenu:
  TITLE: Phase E5 — Migrator (iteration {verifier_iteration})
    (Verifier found {verification_result.residue_count} unresolved issues:
     <truncated preview, max 10 items>)
  OPTIONS:
    y ->
      DISPATCH cf-migrate-migrator with verifier's residue as new task
      SET migration_manifest = agent output
      CONTINUE E4
    N ->
      EMIT residue list
      CONTINUE E6
  INVALID:
    EMIT "Reply with y or N."
    WAIT user.reply
    STOP_TURN

WHEN:
  verification_result reports all clean

DO:
  CONTINUE E6

INVARIANTS:
  - MUST_NOT exceed 3 verifier iterations
  - MUST continue to E6 after hitting iteration cap
```

### E6: Final report

```text
UNIT E6_FinalReport

PURPOSE:
  Emit a structured migration summary regardless of E5 outcome.

DO:
  EMIT:
    ## Migrate from Cypilot — Final Report

    Phases run:
      E0 preconditions:  PASS
      E1 scanner:        {N findings}
      E2 planner:        {A_count auto-fixable / B_count needs-review / C_count cascade}
      E3 migrator:       {M applied / Q skipped} (selection: {A|AB|ABC|select})
      E4 verifier (x{T iterations}): {clean | K residue}
      E5 loop:           {hit iteration cap | resolved on iteration N | not needed}

    Outstanding work (if any):
      - {file:line -- description -- recommended manual action}
      ...

    Cascade operations to run manually (if any):
      - {command}
      ...

    Suggested next steps:
      - {context-appropriate}

RULES:
  - MUST emit final report regardless of whether E5 hit clean or cap
  - MUST list outstanding work when residue remains
  - MUST list cascade operations when any C-category items were not applied
```

## Sub-agent dispatch contract

```text
UNIT SubAgentDispatchContract

PURPOSE:
  Define the standard dispatch mechanism for all four sub-agents.

RULES:
  - MUST use Agent tool for all sub-agent dispatches
  - MUST use subagent_type matching the phase:
      E1: "cf-migrate-scanner"
      E2: "cf-migrate-planner"
      E3: "cf-migrate-migrator"
      E4/E5: "cf-migrate-verifier" / "cf-migrate-migrator"
    (use the dedicated registered type; each is registered in agents.toml with role-scoped prompts)
  - MUST construct prompt as: {role-file-content} + \n\n## Task Inputs\n\n{role-specific JSON}
  - MUST run in foreground (default) so orchestrator can chain to next phase

NOTES:
  Each role file is self-contained: it declares purpose, expected inputs, procedure,
  output format, and hard rules. The orchestrator does not interpret the agent's internal
  logic; it passes inputs and consumes the structured output.
```

## Validation Criteria

- [ ] Preconditions verified at E0 (legitimate deterministic migration completed)
- [ ] User explicitly approved EACH sub-agent dispatch (E1, E2, E3, E4, every E5 iteration)
- [ ] Migrator never dispatched without a Planner-produced plan in hand
- [ ] Plan presented to user IN FULL before asking for Migrator approval
- [ ] Migrator ↔ Verifier loop respects the 3-iteration cap
- [ ] Final report emitted (E6) regardless of whether E5 hit clean or cap
- [ ] No files modified outside `project_root`
- [ ] No files modified inside `{cf-studio-path}/.core/` (kit-managed)
- [ ] Project memories respected (conservative markdown rewriter input-side logic unchanged, cypilot lifecycle, json_mode fixture)
- [ ] `@cpt-*` markers in source code treated as needs-review (per v1.0.0 rebrand design)
- [ ] Migrator target identifiers use Constructor Studio forms (.studio-workspace.toml, skills/studio/, cfs, ~/.cf-studio/cache/, constructorfabric/studio)
