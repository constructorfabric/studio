# Constructor Studio v1.5.9 — Capability Overview

Constructor Studio is an AI-powered development companion that integrates with your existing codebase and toolchain to accelerate the full software lifecycle — from exploration and planning through code, documentation, and skill authoring. It operates through a single entry point (`/cf`) and routes each request to the right workflow automatically, handling the write-review-fix cycle within each workflow without requiring separate commands.

This document covers all 13 capability domains available in v1.5.9. Each domain is presented as a structured CDSL block for quick scanning, followed by concrete scenarios that illustrate how a team member would actually use it.

---

## How to Read This Document

Each capability is described using CDSL (Capability Description and Scenario Language) notation. A `CAPABILITY` block names the domain, identifies the primary actor, states the PM-level purpose, and lists key operations. Inside each block, `SCENARIO` entries follow a Given/When/Then pattern: the starting context, the action a user takes, and what Studio does in response.

The goal is to answer three questions for each capability: **what it does**, **who uses it**, and **what the experience looks like end to end**.

---

## Capability Domains

### 1. Session Entry and Routing

```cdsl
CAPABILITY SessionEntryAndRouting
  ACTOR: Any team member (developer, tech writer, PM)
  PURPOSE: Provides a single activation point for all Studio capabilities. Free-text
    intent is matched to the right workflow automatically, so users never need to
    remember command names.
  KEY_OPERATIONS: [
    "Activate Studio via /cf or cf-studio alias",
    "Route free-text intent to the matching workflow",
    "Route analysis intent to matching workflow (cf-analyze)",
    "Route generation intent to matching workflow (cf-generate)",
    "Set session mode: assistant (guided), normal, or debug",
    "Offer companion sequences for cross-domain tasks",
    "Apply Brave New World overlay to auto-answer safe choices"
  ]
  NOTE: cf-analyze and cf-generate are lightweight entry-point routers — they match the user's intent to the right concrete workflow but perform no analysis or generation themselves.

  SCENARIO FirstTimeActivation
    GIVEN: A developer opens a new project and types /cf for the first time
    WHEN: They describe their intent in plain English ("I want to add a retry
      mechanism to the HTTP client")
    THEN: Studio identifies the intent as a coding task, selects cf-coding,
      confirms the session mode, and begins the workflow

  SCENARIO CrossDomainTask
    GIVEN: A tech writer needs to both refactor a module and update its
      documentation in one session
    WHEN: They describe both goals at the entry prompt
    THEN: Studio detects that two domains are involved, proposes a sequential
      companion skill sequence (cf-coding then cf-write-docs), and walks through
      them in order

  SCENARIO DebugModeSession
    GIVEN: A Studio author suspects a skill is misbehaving and wants to trace
      execution step by step
    WHEN: They activate /cf and choose debug mode at the session prompt
    THEN: Studio attaches the debug overlay, enabling breakpoints and step-through
      inspection for the entire session
```

---

### 2. Context Discovery

```cdsl
CAPABILITY ContextDiscovery
  ACTOR: Developer, tech writer, or any contributor starting a complex task
  PURPOSE: Scans the project read-only to find every file and artifact relevant
    to the current task, producing a structured resource map before any changes
    are made.
  KEY_OPERATIONS: [
    "Scan project for task-relevant files and artifacts",
    "Return a resource map with paths, summaries, and suggested slices",
    "Run standalone or as an automatic pre-dispatch gate",
    "Partition large codebases across parallel agents",
    "Save context as result.json + resource-map.md + summary.md (optional, prompted after standalone runs)"
  ]

  SCENARIO PreFlightBeforeCoding
    GIVEN: A developer is about to refactor an authentication module
    WHEN: cf-coding invokes cf-explore automatically before generating any code
    THEN: Studio returns a resource map (resource-map.md + summary.md) listing
      the auth module, its tests, related config files, and any documentation
      that references it, so the coding workflow has full context before writing
      a single line

  SCENARIO StandaloneExploration
    GIVEN: A PM wants to understand which files are touched by a specific feature
      area before scoping a sprint
    WHEN: They invoke cf-explore directly with a description of the feature
    THEN: Studio produces summary.md listing relevant paths and a plain-language
      summary of what it found, without making any changes

  SCENARIO LargeMonorepoScan
    GIVEN: A workspace contains dozens of packages and thousands of files
    WHEN: cf-explore is triggered on a cross-cutting concern
    THEN: Studio partitions the scan across parallel agents, merges results into
      a single resource map (resource-map.md + summary.md), and flags which
      packages are most relevant

  SCENARIO CrossRepoContextGathering
    GIVEN: A developer needs to understand how a shared library is used across three
      separate repositories in the workspace before adding a breaking API change
    WHEN: They invoke cf-explore with the workspace sources included
    THEN: Studio dispatches partitioned explorers across all workspace sources in parallel,
      aggregates the resource maps into a single deduplicated context, and surfaces every
      file, artifact, and @cpt-* marker that references the shared library — giving the
      developer a federated impact picture before writing a single line
```

---

### 3. Dependency Mapping

```cdsl
CAPABILITY DependencyMapping
  ACTOR: Tech lead, architect, or PM assessing impact of a refactor
  PURPOSE: Builds a visual and queryable map of how CPT traceability IDs connect
    across markdown and source code, making it easy to spot broken or missing
    links after a refactor.
  KEY_OPERATIONS: [
    "Scan markdown and source for CPT traceability IDs",
    "Generate an interactive HTML dependency graph or JSON export",
    "Detect dangling and phantom references",
    "Support single-repo, workspace-wide, or markdown-only scope",
    "Assist with md-map.toml category rule configuration"
  ]

  SCENARIO PostRefactorAudit
    GIVEN: A team has just renamed several modules as part of a restructuring
    WHEN: A tech lead runs cfs map on the repository
    THEN: Studio produces an HTML graph and flags every CPT ID that now points
      to a path that no longer exists (dangling references), plus any IDs
      referenced in source but absent from documentation (phantom references)

  SCENARIO CrossRepoTraceability
    GIVEN: A workspace spans three Git repositories that share a common spec
    WHEN: The architect runs cfs map with-workspace scope
    THEN: Studio resolves CPT IDs across all three repos and renders a unified
      graph showing which implementation files satisfy which spec requirements

  SCENARIO CategoryRuleSetup
    GIVEN: A new team member is configuring the project's md-map.toml for the
      first time and is unsure which categories to define
    WHEN: They invoke cf-map and, after generation completes, they select
      'config-assist' from cf-map's next-steps menu
    THEN: Studio scans existing markdown, infers likely category groupings, and
      proposes a starter md-map.toml for the user to review and approve

  SCENARIO RefactorSafetyCheck
    GIVEN: A developer is about to rename or split a core module that many artifacts reference
    WHEN: They invoke cf-map before starting the refactor
    THEN: Studio builds the full CPT dependency graph, highlights every artifact and code file
      that references the affected module's IDs, flags any already-dangling references,
      and exports the map as JSON so the developer can script targeted updates — giving
      a complete blast-radius picture before a single line of code changes
```

---

### 4. Design Exploration

```cdsl
CAPABILITY DesignExploration
  ACTOR: Developer, architect, or PM evaluating design options before committing
  PURPOSE: Runs a structured expert panel discussion on any design topic, surfacing
    diverse perspectives and open questions so the team can make informed decisions
    before writing code or specs.
  KEY_OPERATIONS: [
    "Assemble a panel of 3–6 domain experts for a given topic",
    "Run topic rounds followed by optional challenge rounds",
    "Present questions one at a time at the user's pace",
    "Run in inline, single-agent, or fan-out parallel mode",
    "Produce a decisions block and open-questions block; hand off to the next workflow"
  ]

  SCENARIO ApiDesignReview
    GIVEN: A team is debating two approaches for a public API versioning strategy
    WHEN: A developer invokes cf-brainstorm with the versioning topic and their
      two candidate designs
    THEN: Studio assembles a panel (e.g., API designer, security reviewer, DevEx
      lead), walks through topic rounds, presents each question in turn, and
      produces a summary of the panel's consensus and unresolved questions

  SCENARIO ArchitecturePreliminary
    GIVEN: A PM wants to pressure-test a proposed microservices split before it
      enters planning
    WHEN: They start a brainstorm session in fan-out parallel mode
    THEN: Multiple expert agents respond simultaneously, their outputs are
      merged, and Studio surfaces the strongest objections and agreements in a
      single decisions block

  SCENARIO HandoffToPlan
    GIVEN: A brainstorm session has concluded with a preferred design approach
    WHEN: The user signals they are ready to move to planning
    THEN: Studio presents the option to hand off directly to cf-plan, carrying
      the decisions block and open questions as input context
```

---

### 5. Planning

```cdsl
CAPABILITY Planning
  ACTOR: Tech lead or senior developer breaking a large initiative into
    executable phases
  PURPOSE: Decomposes a large task into a sequenced set of self-contained phases,
    each with its own brief, so that execution can proceed incrementally without
    losing scope.
  KEY_OPERATIONS: [
    "Phase 0: runtime discovery, explore gate, brainstorm gate",
    "Phase 1: scope assessment and decomposition",
    "Phase 2: generate a brief per phase",
    "Phase 3: compile to plan.toml and individual phase files",
    "Store plan artifacts in .cf-studio/.plans/ (directory name is configurable via cf-studio-path; default shown) for execution handoff"
  ]

  SCENARIO LargeFeaturePlanning
    GIVEN: A tech lead needs to ship a new billing integration across three
      services, estimated at several weeks of work
    WHEN: They invoke cf-plan and describe the feature goal
    THEN: Studio runs the explore gate to understand the codebase, decomposes
      the work into numbered phases, generates a brief for each, and writes
      plan.toml plus individual phase files to .cf-studio/.plans/

  SCENARIO PlanWithPriorBrainstorm
    GIVEN: A brainstorm session has already produced a decisions block for the
      same initiative
    WHEN: cf-plan detects the prior brainstorm output in the handoff context
    THEN: Studio skips the brainstorm gate (already satisfied) and proceeds
      directly to scope assessment, using the decisions block to inform phase
      boundaries

  SCENARIO IncrementalExecution
    GIVEN: A plan has been compiled and the team is ready to start execution
    WHEN: A developer picks up Phase 2 from plan.toml
    THEN: Studio reads the Phase 2 brief as the input context for cf-coding,
      providing bounded, well-defined scope without re-running discovery
```

---

### 6. Source Code Work

```cdsl
CAPABILITY SourceCodeWork
  ACTOR: Developer (all seniority levels)
  PURPOSE: Handles the complete write-review-fix lifecycle for source code in
    a single workflow — authoring new code, refactoring existing code, reviewing
    for bugs and consistency, and applying approved fixes.
  KEY_OPERATIONS: [
    "Explore gate (automatic context discovery before writing)",
    "Brainstorm gate (optional design check for complex tasks)",
    "Author dispatch: codegen / smart / casual by task complexity",
    "Deterministic CI: tests, lint, typecheck, build",
    "Semantic review: code-checklist, bug-finding, consistency-checklist",
    "Findings gated: user approves which findings to fix before fixes are applied",
    "Git finalization: commit / stage / none, chosen once per session"
  ]

  SCENARIO NewFeatureFromScratch
    GIVEN: A developer needs to implement a rate-limiter for an existing HTTP
      client module
    WHEN: They invoke cf-coding and describe the feature
    THEN: Studio runs the explore gate to map relevant files, selects the smart
      author mode for a medium-complexity task, writes the implementation,
      runs CI (tests, lint, typecheck, build), performs a full semantic review,
      presents findings, waits for the user to approve which to fix, applies
      fixes, and offers to stage or commit the result

  SCENARIO BugFixWithReview
    GIVEN: A bug report points to a race condition in a concurrency module
    WHEN: The developer invokes cf-coding in fix mode with the bug description
    THEN: Studio scans the module and related tests, generates a targeted fix,
      runs CI to confirm the fix does not break other tests, and presents any
      secondary findings for the user to approve before applying

  SCENARIO LegacyRefactor
    GIVEN: A senior developer wants to refactor a 2,000-line legacy class into
      smaller, testable units
    WHEN: They invoke cf-coding in refactor mode
    THEN: Studio runs the explore gate for full context, breaks the refactor
      into logical sub-steps, applies each in sequence with CI validation
      after each step, and presents a per-layer review at the end

  SCENARIO CodeReviewWithMethodologyDepth
    GIVEN: A tech lead wants a thorough review of a complex refactor beyond a quick pass
    WHEN: They invoke cf-coding in review mode and choose per-layer granularity
    THEN: Studio dispatches reviewers in parallel for each methodology layer
      (code-checklist, bug-finding, consistency-checklist), aggregates deduplicated
      findings, lets the user select which to fix, and dispatches a fix agent only
      for the approved finding set before re-running CI

  SCENARIO TestFirstWorkflow
    GIVEN: A developer is starting a new feature and wants to write tests before code
    WHEN: They invoke cf-coding and describe the feature behavior to test
    THEN: Studio authors test files only (unit tests and/or e2e tests) against the
      feature description, runs the test suite to confirm tests are red, then hands
      off to the implementation path — ensuring tests exist before any production code
```

---

### 7. Documentation Work

```cdsl
CAPABILITY DocumentationWork
  ACTOR: Tech writer, developer authoring READMEs or ADRs, or PM authoring specs
  PURPOSE: Handles the complete write-review-fix lifecycle for all documentation
    artifacts — guides, READMEs, specs, ADRs, and reports — in a single workflow,
    with automatic language complexity enforcement on all output.
  KEY_OPERATIONS: [
    "Explore gate and brainstorm gate before authoring",
    "Audience, narrator, and diagram dimension configuration",
    "Language complexity enforcement on all generated text",
    "Deterministic CI: artifact structure validation, TOC check, language policy",
    "Semantic review: consistency-checklist and artifact-checklist",
    "Findings gated: user approves fixes before applied"
  ]

  SCENARIO NewApiGuide
    GIVEN: A developer has shipped a new API and needs an integration guide for
      external partners
    WHEN: They invoke cf-write-docs, specify the audience as external developers,
      and point to the API source files
    THEN: Studio runs the explore gate to read the API, configures the audience
      and narrator dimensions, generates the guide, runs CI (structure, TOC,
      language policy), performs a semantic review, presents findings, and applies
      approved fixes

  SCENARIO AdrAuthoring
    GIVEN: An architect needs to document a significant architectural decision
      with full context and consequences
    WHEN: They invoke cf-write-docs in ADR mode with a description of the decision
    THEN: Studio generates a structured ADR following the team's artifact template,
      validates it against the artifact checklist, and flags any missing sections
      before presenting the draft for review

  SCENARIO ExistingDocRevision
    GIVEN: A README has grown stale after a major refactor and contains
      incorrect CLI examples
    WHEN: A tech writer invokes cf-write-docs in revise mode on the file
    THEN: Studio diffs the current doc against the codebase via the explore gate,
      identifies outdated sections, proposes targeted revisions, and presents
      them as findings for the user to approve before writing

  SCENARIO MultiAudienceDocumentReview
    GIVEN: A senior engineer wants to verify that existing architecture docs are still accurate
    WHEN: They invoke cf-write-docs in review-first mode on an existing DESIGN document
    THEN: Studio runs a semantic review using the artifact checklist and consistency
      methodology, presents findings categorized by severity, and gates any fixes on
      explicit per-finding approval before applying changes

  SCENARIO LanguagePolicyEnforcement
    GIVEN: A team maintains English-only documentation but suspects a recent commit
      introduced non-English characters
    WHEN: They invoke cf-write-docs or cfs check-language on the affected files
    THEN: Studio scans for characters outside the allowed Unicode script set,
      reports violations with exact file and line references, and prompts the author
      to resolve them before the document passes validation
```

---

### 8. Skill and Workflow Authoring

```cdsl
CAPABILITY SkillAndWorkflowAuthoring
  ACTOR: Studio author (developer or prompt engineer building or maintaining
    Studio skills, workflows, agent instructions, or system prompts)
  PURPOSE: Handles the complete write-review-fix lifecycle for Studio's own
    prompt and workflow artifacts, with PDSL syntax validation integrated at
    every step to prevent prompt-level bugs from reaching production.
  KEY_OPERATIONS: [
    "Write, revise, or review Studio skills, workflows, and agent instructions",
    "PDSL syntax validation via cfs pdsl validate",
    "Semantic review: prompt-engineering, prompt-bug-finding, consistency-checklist",
    "Review depth: single-pass / per-methodology / per-layer (parallel reviewers)",
    "Findings gated before fixes applied",
    "PDSL re-validated after every fix"
  ]

  SCENARIO NewSkillAuthoring
    GIVEN: A Studio author needs to create a new skill for a domain not yet
      covered by Studio
    WHEN: They invoke cf-write-skills with a description of the skill's purpose
      and target actor
    THEN: Studio scaffolds the skill using PDSL conventions, validates syntax,
      runs all three review methodologies, presents findings by layer, and
      re-validates after each approved fix

  SCENARIO ExistingWorkflowRevision
    GIVEN: A prompt engineer identifies a reliability issue in an existing
      workflow's review step
    WHEN: They invoke cf-write-skills in revise mode pointing to the affected
      workflow file
    THEN: Studio reads the current workflow, applies prompt-bug-finding review,
      surfaces the suspected issue as a finding, and applies the fix only after
      the author approves — then re-validates PDSL to confirm no syntax
      regressions

  SCENARIO SkillConsistencyAudit
    GIVEN: A team has authored several related skills over time and suspects
      inconsistent terminology
    WHEN: They invoke cf-write-skills in review-only mode across the skill set
    THEN: Studio runs the consistency-checklist methodology across all files in
      parallel per-layer mode and produces a findings report without making
      any changes until the author approves each one

  SCENARIO NewStudioSkillCreation
    GIVEN: A Studio developer wants to add a new custom workflow to their project kit
    WHEN: They invoke cf-write-skills and describe the skill's purpose and gate structure
    THEN: Studio authors a PDSL-formatted skill file, validates it with cfs pdsl validate,
      runs a prompt-engineering semantic review (checking routing logic, missing cases,
      unclear gates), applies approved fixes, and re-validates PDSL after each fix cycle

  SCENARIO WorkflowBugInvestigation
    GIVEN: A workflow behaved unexpectedly — a gate fired when it should not have
    WHEN: The developer invokes cf-debug-prompts, arms the debugger, then triggers
      the faulty workflow
    THEN: The debugger intercepts each PDSL instruction, shows the current location
      (file:line:unit), displays the active state, and pauses for approval — allowing
      the developer to step through the exact gate condition and identify the root cause
```

---

### 9. Kit Management

```cdsl
CAPABILITY KitManagement
  ACTOR: Developer or Studio administrator managing reusable behavior packages
    across projects
  PURPOSE: Provides a structured lifecycle for kits — reusable packages of rules,
    templates, scripts, and agents — including discovery, installation, updates,
    and manifest normalization.
  KEY_OPERATIONS: [
    "Initialize: detect project type, propose manifest, user approves, write and validate",
    "Install from GitHub, generic Git URL, or local path (copy or register mode)",
    "Interactive update: accept / decline / modify per changed file",
    "Normalize: generate or update manifest.toml with dry-run preview",
    "CLI: cfs kit install / update / normalize / check-updates"
  ]

  SCENARIO InstallingASharedKit
    GIVEN: A new project needs the team's standard linting and rule kit, which
      lives in a shared GitHub repository
    WHEN: A developer runs cfs kit install with the GitHub URL
    THEN: Studio clones or copies the kit into the project, registers it in the
      manifest, and validates the installed structure before confirming success

  SCENARIO InteractiveKitUpdate
    GIVEN: The shared linting kit has released a new version with changes to
      three rule files, one of which the local project has customized
    WHEN: The developer runs cfs kit update
    THEN: Studio presents each changed file one at a time, shows a diff, and
      asks the developer to accept, decline, or modify the change — preserving
      their local customization where they decline

  SCENARIO NewKitInitialization
    GIVEN: A team wants to package their project-specific templates and agents
      as a reusable kit for other projects in the organization
    WHEN: They run cfs kit normalize in the target folder
    THEN: Studio scans the folder, detects whether it is a canonical, legacy, or
      greenfield layout, proposes a manifest.toml with a dry-run preview, and
      writes the manifest after user approval

  SCENARIO KitUpdateWithPerFileDiffReview
    GIVEN: The SDLC kit has a new upstream version with updated workflow files
    WHEN: The developer runs cfs kit check-updates then cfs kit update
    THEN: Studio presents the version diff summary, then walks through each changed file
      one at a time — showing a diff and asking accept/decline/modify per file; declined
      files are kept as-is, modified files use the developer's merged version; at the end
      cfs validate-kits confirms the updated kit structure is valid
```

---

### 10. Multi-Repo Workspace

```cdsl
CAPABILITY MultiRepoWorkspace
  ACTOR: Tech lead or architect managing a federation of related Git repositories
  PURPOSE: Federates multiple Git repositories under one Studio workspace so that
    cross-repo CPT traceability, validation, and dependency mapping work as if
    the repos were a single project.
  KEY_OPERATIONS: [
    "Initialize a workspace federating multiple repos",
    "Add sources by local path or Git URL",
    "Inspect workspace health and sync remote repos",
    "Resolve CPT traceability IDs across repo boundaries",
    "Run workspace-scoped validation and map generation",
    "CLI: cfs workspace-init / add / info / sync",
    "Invoke Studio workflow: cf-workspace (wraps all workspace CLI operations with guided prompts and confirmations)"
  ]

  SCENARIO WorkspaceInitialization
    GIVEN: A platform team maintains four microservice repos and a shared spec
      repo that must all stay in sync
    WHEN: A tech lead runs cfs workspace-init and adds all five repos
    THEN: Studio registers each repo in the workspace manifest, verifies
      connectivity, and makes cross-repo CPT resolution available for subsequent
      map and validation commands

  SCENARIO CrossRepoImpactAssessment
    GIVEN: A change to the shared spec repo may affect multiple downstream
      service repos
    WHEN: The architect runs cfs map with-workspace scope after the spec change
    THEN: Studio resolves CPT IDs across all registered repos and surfaces
      every downstream reference that may be impacted by the spec change

  SCENARIO RemoteRepoSync
    GIVEN: Two of the workspace repos have received upstream commits overnight
    WHEN: A developer runs cfs workspace sync at the start of the day
    THEN: Studio pulls the latest commits for all remote-backed repos in the
      workspace and reports any repos that could not be synced cleanly

  SCENARIO WorkspaceSyncForDistributedTeam
    GIVEN: A team works across three Git-hosted repositories federated in a workspace,
      and the shared architecture repo was updated by another team member
    WHEN: They run cfs workspace-sync (or cfs workspace-sync --source arch-repo)
    THEN: Studio fetches and updates the Git worktree for the URL-based source,
      reports sync results per source (updated / already-current / failed), and
      makes the updated cross-repo CPT IDs immediately available for cfs where-used
      and cfs validate queries — no manual git pull required
```

---

### 11. Narrative Explanation

```cdsl
CAPABILITY NarrativeExplanation
  ACTOR: Developer onboarding to a new codebase, or any team member who needs
    to understand a complex artifact or decision
  PURPOSE: Delivers a source-grounded, portion-by-portion walkthrough of any
    codebase area, artifact, or architectural decision, paced by the user and
    exportable as a portable Markdown package.
  KEY_OPERATIONS: [
    "E0 preflight: resolve input access tier, check for prior session",
    "E1 gates: mode, disposition, audience, and plan — set sequentially",
    "E2 delivery: read context once, deliver portions of up to 200 words each",
    "7-slot navigator for moving between portions",
    "E5 wrap: optional export as Markdown package under .cache/explain/packages/ (top-level project cache directory, separate from the Studio config dir)"
  ]

  SCENARIO OnboardingWalkthrough
    GIVEN: A new developer joins a team with a large, unfamiliar codebase and
      needs to understand the authentication flow
    WHEN: They invoke cf-explain pointing at the auth module
    THEN: Studio sets up an audience-appropriate plan, walks through the module
      portion by portion (each under 200 words), and lets the developer navigate
      forward, back, or jump to a specific section at any time

  SCENARIO AdDecisionExplanation
    GIVEN: A PM wants to understand why a significant architectural decision was
      made six months ago, documented in an ADR
    WHEN: They invoke cf-explain on the ADR file in plain-language mode
    THEN: Studio reads the ADR and any referenced source files, delivers a
      narrative explanation in non-technical language portion by portion, and
      answers follow-up questions grounded in the source

  SCENARIO ExportForSharing
    GIVEN: A tech lead has walked through a complex subsystem with a contractor
      who needs to take the explanation offline
    WHEN: The tech lead triggers the E5 export at the end of the session
    THEN: Studio packages the full walkthrough as a self-contained Markdown
      bundle under .cache/explain/packages/, ready to share or commit
```

---

### 12. Project Setup and Brownfield Onboarding

```cdsl
CAPABILITY ProjectSetupAndBrownfieldOnboarding
  ACTOR: Developer or tech lead initializing Studio on an existing or new project
  PURPOSE: Scans an existing codebase, generates grounded configuration and rule
    files, and integrates Studio with the team's preferred IDE and toolchain —
    including migration support for legacy CyPilot projects.
  KEY_OPERATIONS: [
    "Precheck: verify Studio is initialized and source code exists",
    "Scan: cf-explore discovers project structure",
    "Detect: identify systems and topics, propose rule files",
    "Generate: per-topic rule files grounded in file:line evidence",
    "Integrate: write AGENTS.md and artifacts.toml",
    "Validate: structural and quality checks",
    "Migrate: legacy CyPilot projects via --migrate-yes flag",
    "IDE integrations: Claude, Copilot, Cursor, OpenAI, Windsurf",
    "CLI: cfs init / update / generate-agents"
  ]

  SCENARIO GreenFieldInit
    GIVEN: A developer starts a new project and wants Studio configured from day
      one
    WHEN: They run cfs init in the project root
    THEN: Studio scans the (mostly empty) project, generates starter rule files,
      writes AGENTS.md with IDE integration stubs, and validates the output
      structure before completing

  SCENARIO BrownfieldOnboarding
    GIVEN: An existing production service with 50,000 lines of code has never
      used Studio before
    WHEN: A tech lead runs cfs init on the repo
    THEN: Studio runs cf-explore to discover the project structure, identifies
      distinct system areas (e.g., API layer, data layer, background jobs),
      generates a grounded rule file for each area with file:line citations,
      writes AGENTS.md and artifacts.toml, and validates all outputs

  SCENARIO LegacyCyPilotMigration
    GIVEN: A team previously used CyPilot and has existing configuration files
      they want to preserve
    WHEN: They run cfs init --migrate-yes
    THEN: Studio detects the legacy CyPilot layout, maps legacy configuration
      to the current Studio format, generates updated rule files, and reports
      any constructs that could not be migrated automatically

  SCENARIO AutoConfigRefreshAfterReorg
    GIVEN: A team reorganized their codebase into new modules six months after initial Studio onboarding
    WHEN: They invoke cf-auto-config again on the evolved project
    THEN: Studio detects existing rule files and offers a refresh menu (refresh all /
      selective / report-only / cancel); in selective mode, the developer picks which
      topics to regenerate, Studio re-scans only those areas and proposes updated rule
      files grounded in the new file:line evidence — without touching topics that did not change

  SCENARIO IdeIntegrationSetupAfterKitInstall
    GIVEN: A team installed a new behavior kit (e.g. the SDLC kit) and wants their
      Cursor and Windsurf IDEs to know about the new workflows
    WHEN: They run cfs generate-agents after the kit install
    THEN: Studio discovers the kit's public skills and agent proxies, composes an updated
      SKILL.md from all kit @cpt:skill sections, generates proxy agent files for each
      configured IDE target (Cursor, Windsurf, Claude, Copilot, OpenAI), updates the
      managed gitignore block, and reports which files were written or updated — all
      verified via cfs agents afterward
```

---

### 13. Session Overlays

```cdsl
CAPABILITY SessionOverlays
  ACTOR: Any Studio user (Brave New World) or Studio author / debugger
    (Debug Prompts)
  PURPOSE: Provides two cross-cutting session-level behaviors: Brave New World
    accelerates throughput by auto-answering safe, reversible choices; Debug
    Prompts gives Studio authors a full step-through debugger for tracing skill
    and workflow execution.
  KEY_OPERATIONS: [
    "Brave New World: auto-answer safe reversible choices without pausing",
    "Brave New World: announce each auto-decision as it is made",
    "Brave New World: hard-block on destructive, git, security, or credential prompts",
    "Debug Prompts: step / over / back / continue navigation",
    "Debug Prompts: breakpoints by file, line, unit, or condition",
    "Debug Prompts: run mode for uninterrupted execution",
    "Debug Prompts: trace export to .debug-skill/ (top-level project-root directory for debug trace files)"
  ]

  SCENARIO BraveNewWorldDuringCoding
    GIVEN: A developer is running a long cf-coding session and wants to minimize
      interruptions for routine confirmations
    WHEN: They activate cf-brave-new-world at the start of the session
    THEN: Studio auto-answers every safe, reversible prompt (e.g., "should I
      create this test file?"), announces each decision inline, and pauses only
      when a prompt involves a destructive action, a git operation, or any
      security or credential concern

  SCENARIO DebugBreakpoint
    GIVEN: A Studio author suspects that a specific unit in a skill is producing
      incorrect output
    WHEN: They set a breakpoint on that unit using the Debug Prompts overlay and
      run the skill
    THEN: Studio executes the skill normally until it reaches the breakpoint,
      then pauses and presents the current state, allowing the author to inspect
      inputs and outputs before deciding to step, continue, or back up

  SCENARIO TraceExport
    GIVEN: A Studio author has debugged a tricky skill issue and wants to share
      the trace with a colleague for review
    WHEN: They trigger trace export from the debug overlay
    THEN: Studio writes the full execution trace to .debug-skill/ as a structured
      file that the colleague can inspect without needing to reproduce the
      session
```

---

### 14. SDLC Artifact Pipeline

```cdsl
CAPABILITY SdlcArtifactPipeline
  ACTOR: Product Manager, Tech Lead, Architect, Developer
  PURPOSE: The SDLC kit adds a structured artifact pipeline on top of Constructor
    Studio: PRD → ADR + DESIGN → DECOMPOSITION → FEATURE → CODE, with templates,
    checklists, and traceability enforcement at every stage. Each artifact kind
    has a dedicated authoring workflow that delegates to cf-write-docs or cf-coding
    and enforces deterministic validation plus semantic review.
  KEY_OPERATIONS:
    - Author a PRD with actors, FR/NFR, use cases, and success criteria (cf-sdlc-doc-prd)
    - Record an Architecture Decision Record — context/options/decision/consequences (cf-sdlc-doc-adr)
    - Author a system DESIGN — components, interfaces, boundaries, architecture drivers (cf-sdlc-doc-design)
    - Break down a DESIGN into an ordered FEATURE list with dependency links (cf-sdlc-decompose)
    - Author a FEATURE spec with CDSL flows, algorithms, states, and test scenarios (cf-sdlc-doc-feature)
    - Implement a FEATURE in code with @cpt-* traceability markers (cf-sdlc-implement)
    - Analyze downstream impact of an upstream artifact change — cascade tracking or release-readiness estimation (cf-sdlc-change-impact-analysis)
    - Review a GitHub PR against artifact checklists and code review prompts (cf-sdlc-pr-review)
    - Generate a PR status report with severity assessment and resolved-comment audit (cf-sdlc-pr-status)
    - Reconstruct SDLC artifacts from existing code using @cpt-* markers — marker-first strategy (cf-sdlc-reverse-engineer)
    - Migrate OpenSpec artifacts to Studio SDLC format in 8 phases with code verification (cf-sdlc-migrate-openspec)
  SCENARIO PrdAuthoringFromScratch
    GIVEN: A PM has a new product idea and needs a formal requirements document
    WHEN: They invoke cf-sdlc-doc-prd and describe their product concept
    THEN: Studio guides them through the PRD template (actors, functional requirements
      with cpt-IDs, non-functional requirements, use cases, success criteria), runs
      cfs validate --artifact on the result, and performs a semantic review against
      the PRD checklist before the document is considered done
  SCENARIO ArchitectureDecisionRecord
    GIVEN: A tech lead chose a specific database technology and must document why
    WHEN: They invoke cf-sdlc-doc-adr and describe the decision context
    THEN: Studio authors an ADR with context, considered options, the chosen option,
      consequences, and a unique cpt-adr-* traceability ID; the ADR is validated
      and cross-referenced into the DESIGN artifact automatically
  SCENARIO ChangeImpactAnalysis
    GIVEN: A product requirement (PRD FR) was updated to change behavior
    WHEN: They invoke cf-sdlc-change-impact-analysis with the changed artifact ID
    THEN: Studio traces the blast radius downstream (PRD → DESIGN → DECOMPOSITION
      → FEATURE → CODE markers), flags stale @cpt-* markers in code, reports
      coverage gaps, and — in release-readiness mode — recommends a version bump
      based on impact severity
  SCENARIO PrReviewWithChecklists
    GIVEN: A developer opened a GitHub PR with code and a FEATURE implementation
    WHEN: They invoke cf-sdlc-pr-review with the PR number
    THEN: Studio fetches the diff from GitHub, analyzes it against the codebase
      checklist and per-domain review prompts (code, design, ADR, PRD), and
      produces a structured review report at .prs/{ID}/review.md with severity-rated
      findings — without modifying any local files
  SCENARIO ReverseEngineerFeatureFromCode
    GIVEN: A team has legacy code with @cpt-* markers but no FEATURE spec documents
    WHEN: They invoke cf-sdlc-reverse-engineer with the code scope
    THEN: Studio extracts all @cpt-* markers, reconstructs FEATURE specs with
      CDSL flows and test scenarios grounded in the actual code behavior,
      and flags @cpt-gap markers where evidence is missing
  SCENARIO OpenSpecMigration
    GIVEN: A team has existing OpenSpec proposals, specs, and design documents
    WHEN: They invoke cf-sdlc-migrate-openspec with the OpenSpec root directory
    THEN: Studio runs an 8-phase migration (inventory → PRD → DESIGN → ADRs →
      DECOMPOSITION → FEATURE specs → @cpt-* code markers → registration + validation),
      verifies every claim against actual source code, and flags discrepancies where
      the spec contradicts the implementation
```

---

## Summary Table

| Capability | Primary Actor | Workflow / Command | Key CLI |
|---|---|---|---|
| Session Entry and Routing | Any team member | cf-studio, cf-analyze, cf-generate | `/cf` |
| Context Discovery | Developer, tech writer, PM | cf-explore | `cfs explore` |
| Dependency Mapping | Tech lead, architect, PM | cf-map | `cfs map` |
| Design Exploration | Developer, architect, PM | cf-brainstorm | `/cf brainstorm` |
| Planning | Tech lead, senior developer | cf-plan | `/cf plan` |
| Source Code Work | Developer | cf-coding (monolithic) | `/cf code` |
| Documentation Work | Tech writer, developer, PM | cf-write-docs (monolithic) | `/cf docs` |
| Skill and Workflow Authoring | Studio author, prompt engineer | cf-write-skills (monolithic) | `/cf skills` |
| Kit Management | Developer, Studio admin | cf-kit | `cfs kit install / update / normalize` |
| Multi-Repo Workspace | Tech lead, architect | cf-workspace | `cfs workspace-init / add / sync` |
| Narrative Explanation | Developer, any team member | cf-explain | `/cf explain` |
| Project Setup and Brownfield Onboarding | Developer, tech lead | cf-auto-config | `cfs init / update / generate-agents` |
| Session Overlays | Any user / Studio author | cf-brave-new-world, cf-debug-prompts | (activated at session start) |
| 14 | SDLC Artifact Pipeline | PM, Tech Lead, Architect, Developer | cf-sdlc-doc-prd, cf-sdlc-doc-adr, cf-sdlc-doc-design, cf-sdlc-decompose, cf-sdlc-doc-feature, cf-sdlc-implement, cf-sdlc-change-impact-analysis, cf-sdlc-pr-review, cf-sdlc-pr-status, cf-sdlc-reverse-engineer, cf-sdlc-migrate-openspec | cfs validate --artifact, cfs spec-coverage |
