# Constructor Studio v1.5.9 — User Journeys

## Introduction

This document describes the twenty-two primary cross-cutting user journeys in Constructor Studio v1.5.9. Each journey traces the full path a user takes from intent to outcome, showing how Studio's monolithic workflows chain together.

**How to read ALGORITHM blocks**

Each block follows a fixed schema:

- `ACTOR` — the role that initiates the journey
- `GOAL` — the outcome they are trying to reach
- `INPUTS` — what must already exist before the journey begins
- `OUTPUTS` — what is produced when the journey ends
- `STEPS` — the ordered sequence of actions and workflow invocations
- `DECISION_POINTS` — named forks where the user or Studio chooses a path
- `GUARDS` — invariants that must hold throughout; violation halts the journey
- `NEXT` — optional handoff to a downstream journey or external process

**v1.5.9 architecture note**

All workflows in v1.5.9 are monolithic. Each workflow owns its full lifecycle — intent capture, exploration gate, brainstorm gate, authoring, CI, review, fix, and git finalization — internally. There are no standalone sub-workflows for individual phases (e.g., no `cf-coding-gen`, `cf-coding-ci`, `cf-git-commit`). Git finalization is embedded inside each workflow that produces file artifacts.

---

## Journey Index

| # | Journey | Actor | Goal | AI Workflows (cf-*) | CLI Commands (cfs *) |
|---|---------|-------|------|---------------------|----------------------|
| 1 | Plan and implement a new feature | Developer | Ship a working, reviewed, committed feature | `cf-explore` → `cf-brainstorm` → `cf-plan` → `cf-coding` | — |
| 2 | Onboard a brownfield project to Studio | Tech lead / DevOps | Configure Studio rules and agents for an existing codebase | `cf-auto-config` | `cfs init` → `cfs generate-agents` → `cfs validate-kits` |
| 3 | Brainstorm and write an architectural decision record | Architect / Tech lead | Produce a persisted, reviewed ADR from a structured brainstorm | `cf-brainstorm` → `cf-write-docs` | — |
| 4 | Review and fix existing code | Developer / Reviewer | Identify, approve, and apply fixes for code issues, then commit | `cf-explore` → `cf-coding` (review-first) | — |
| 5 | Create and publish a behavior kit | Platform engineer | Package reusable behaviors into a validated, installable kit | `cf-kit` | `cfs kit install` → `cfs generate-agents` |
| 6 | Generate project documentation | Technical writer / Developer | Produce audience-tuned, reviewed, committed documentation | `cf-explore` → `cf-write-docs` | — |
| 7 | Author a Product Requirements Document (PRD) | Product Manager | Produce a validated PRD with actors, FR/NFR, use cases, success criteria, and cpt-IDs | `cf-sdlc-doc-prd` → `cf-write-docs` | `cfs validate --artifact` |
| 8 | Record an Architecture Decision (ADR) | Architect / Tech Lead | Capture a technology or design decision with context, options, consequences, and a cpt-{system}-adr-* ID | `cf-sdlc-doc-adr` → `cf-write-docs` | `cfs validate --artifact` |
| 9 | Author a System DESIGN Document | Architect / Tech Lead | Document system architecture: components, interfaces, boundaries, principles, constraints | `cf-sdlc-doc-design` → `cf-write-docs` | `cfs validate --artifact` |
| 10 | Decompose DESIGN into Feature List (DECOMPOSITION) | Tech Lead / PM | Break a DESIGN into an ordered, dependency-linked FEATURE list with PRD/DESIGN coverage | `cf-sdlc-decompose` → `cf-write-docs` | `cfs validate --artifact` |
| 11 | Author a FEATURE Specification | Tech Lead / Developer | Write a precise, implementable FEATURE spec with CDSL flows, algorithms, states, and test scenarios | `cf-sdlc-doc-feature` → `cf-write-docs` | `cfs validate --artifact` |
| 12 | Implement a FEATURE with Traceability | Developer | Write production code implementing a FEATURE spec with @cpt-* markers linking code to FEATURE IDs | `cf-sdlc-implement` → `cf-coding` | `cfs validate --artifact` |
| 13 | Analyze Change Impact Across the Artifact Pipeline | Tech Lead / PM / Release Manager | Understand which downstream artifacts and code markers are affected by a change to an upstream artifact | `cf-sdlc-change-impact-analysis` | `cfs where-used` → `cfs spec-coverage` |
| 14 | Review a GitHub Pull Request | Tech Lead / Reviewer / Team Lead | Get a structured, checklist-based review of a GitHub PR against code and artifact quality standards | `cf-sdlc-pr-review` | — |
| 15 | Reconstruct SDLC Artifacts from Existing Code | Tech Lead / Architect | Reconstruct missing PRD/DESIGN/DECOMPOSITION/FEATURE artifacts from existing code using @cpt-* markers as evidence | `cf-sdlc-reverse-engineer` → `cf-write-docs` | `cfs validate --artifact` |
| 16 | Full SDLC Pipeline End-to-End | Product Manager, Architect, Developer | Deliver a fully traced feature from product requirement to production code with all artifacts linked by CPT IDs | `cf-sdlc-doc-prd` → `cf-sdlc-doc-adr` → `cf-sdlc-doc-design` → `cf-sdlc-decompose` → `cf-sdlc-doc-feature` → `cf-sdlc-implement` | `cfs validate --artifact` → `cfs spec-coverage` |
| 17 | Release Readiness Estimation | Release Manager, Tech Lead | Assess downstream impact of artifact changes and get a version bump recommendation before a release | `cf-sdlc-change-impact-analysis` | `cfs where-used` → `cfs spec-coverage` |
| 18 | PR Status Monitoring | Team Lead, PM, Release Manager | Get a current status snapshot of one or all open GitHub PRs — CI state, open comments, severity, resolved-comment audit | `cf-sdlc-pr-status` | — |
| 19 | Spec Coverage Gate in CI | Tech Lead, Developer, DevOps | Enforce a minimum @cpt-* marker coverage threshold as a quality gate in the CI pipeline | — | `cfs spec-coverage` |
| 20 | Cross-Repo Traceability Navigation | Tech Lead, Architect | Trace a CPT ID from its definition in one repo to all usages across all registered workspace sources | `cf-sdlc-change-impact-analysis` | `cfs workspace-info` → `cfs list-ids` → `cfs where-defined` → `cfs where-used` → `cfs get-content` |
| 21 | Interactive Kit Update Cycle | Developer, Tech Lead | Update an installed kit to the latest version, reviewing each changed file individually before accepting changes | — | `cfs kit check-updates` → `cfs kit update` → `cfs generate-agents` → `cfs validate-kits` |
| 22 | CDSL ID Navigation Workflow | Developer, Architect | Enumerate CPT IDs for a feature area, find definitions and usages, read content — before making a change | `cf-sdlc-change-impact-analysis` | `cfs list-id-kinds` → `cfs list-ids` → `cfs where-defined` → `cfs where-used` → `cfs get-content` |

---

## Journeys

### Journey 1: Plan and Implement a New Feature

```text
ALGORITHM PlanAndImplementFeature
  ACTOR: Developer
  GOAL: Deliver a working, reviewed, and committed feature implementation
        with optional upfront exploration and design brainstorm
  INPUTS: [
    Studio activated in project directory,
    Feature intent described (natural language or issue reference),
    Codebase accessible to Studio agents
  ]
  OUTPUTS: [
    Committed feature code on the target branch,
    Review findings report (embedded in cf-coding run),
    CI pass confirmation
  ]
  STEPS:
    1. Activate Studio in the project root (Studio reads Studio config,
       loads rule files, resolves agent kit).
    2. DECISION: Explore first?
       - YES (target area unclear): invoke cf-explore to map relevant
         modules, surfaces, and dependencies; receive exploration summary.
       - NO (target known): skip to step 3.
    3. DECISION: Brainstorm first?
       - YES (design is ambiguous or multiple approaches exist): invoke
         cf-brainstorm; panel of agents proposes and challenges approaches;
         wrap produces a design summary persisted to disk or session-only.
       - NO: skip to step 4.
    4. DECISION: Plan first?
       - YES (feature spans multiple files, layers, or sub-tasks): invoke
         cf-plan; plan decomposes intent into ordered implementation tasks
         with acceptance criteria; user reviews and confirms plan.
       - NO (single-scope change): skip to step 5.
    5. Invoke cf-coding with confirmed intent (and plan artifact if produced).
       cf-coding begins its internal lifecycle:
         5a. Intent capture — cf-coding reads user intent, prior exploration
             summary, and plan artifact (if any).
         5b. DECISION: Sub-agent dispatch mode?
             - NATIVE: Studio dispatches sub-agents using native agent
               protocol; parallel execution where tasks are independent.
             - INLINE: Sub-agent logic runs in the primary agent thread
               sequentially.
         5c. DECISION: Coding classification?
             - WRITE-FIRST: generate implementation, then run CI, then review.
             - REVIEW-FIRST: review existing code first, collect findings,
               then generate targeted fix implementation (see Journey 4
               for full review-first detail).
         5d. Author phase — agent writes or modifies files per the plan.
         5e. CI phase — Studio runs configured linters, type-checkers, and
             test suites internally; failures fed back into fix phase.
         5f. Review phase — agent inspects authored output.
             DECISION: Review granularity?
             - SINGLE-PASS: one unified review over all changes.
             - PER-METHODOLOGY: separate review pass per configured
               methodology (e.g., correctness, security, style).
             - PER-LAYER: separate review pass per architectural layer
               (e.g., API, business logic, persistence).
         5g. Findings browser — user sees structured findings list.
             DECISION: Fix scope?
             - ALL FINDINGS: apply all fixes automatically.
             - SUBSET: user approves per-finding; selected findings applied.
             - NONE: accept code as-is, close findings.
         5h. Fix phase — agent applies approved fixes; re-runs CI if fixes
             touch tested surfaces.
         5i. Git finalization — embedded inside cf-coding.
             DECISION: Git action?
             - COMMIT: stage all changes and create a commit with
               generated message.
             - STAGE ONLY: stage changes, leave commit to user.
             - NONE: leave working tree as-is.
  DECISION_POINTS:
    - ExploreFirst: skip (target known) / run cf-explore (target unclear)
    - BrainstormFirst: skip (clear design) / run cf-brainstorm (ambiguous)
    - PlanFirst: skip (single-scope) / run cf-plan (multi-step)
    - SubAgentDispatch: native (parallel) / inline (sequential)
    - CodingClassification: write-first / review-first
    - ReviewGranularity: single-pass / per-methodology / per-layer
    - FixScope: all findings / subset (per-finding approval) / none
    - GitAction: commit / stage-only / none
  GUARDS: [
    Studio must be activated before any workflow is invoked,
    cf-plan output must be confirmed by user before cf-coding starts,
    CI must pass (or all failures acknowledged) before git finalization,
    Fix phase must not introduce new CI failures without user acknowledgment
  ]
  NEXT: Feature branch ready for pull request or merge (external to Studio)
```

---

### Journey 2: Onboard a Brownfield Project to Studio

```text
ALGORITHM OnboardBrownfieldProject
  ACTOR: Tech lead or DevOps engineer
  GOAL: Bring an existing codebase under Studio governance by generating
        accurate rule files, agent kits, and validated configurations
  INPUTS: [
    Existing source repository accessible on disk,
    User has write access to repository root,
    Optional: existing CyPilot project configuration
  ]
  OUTPUTS: [
    .cf-studio/ directory (configurable via cf-studio-path) populated with Studio config and rule files,
    Generated agent kit(s) appropriate to detected stack,
    Validation report confirming kits are consistent with codebase
  ]
  STEPS:
    1. Run `cfs init` in the repository root.
       Studio creates the .cf-studio/ scaffold and reads any existing
       configuration fragments.
    2. DECISION: Existing CyPilot project detected?
       - YES: Studio offers migration path; user accepts to import
         CyPilot rules as Studio rule files, or declines to start fresh.
       - NO: proceed to step 3.
    3. Invoke cf-auto-config. cf-auto-config runs its internal phases:
         3a. Precheck — validate that prerequisites are met (repo root
             found, .cf-studio/ scaffold present, required tools available).
         3b. Scan — agent traverses the repository; collects language,
             framework, toolchain, and structural signals.
         3c. Detect — agent classifies detected stack; identifies applicable
             rule topic areas (coding standards, testing conventions,
             documentation conventions, security posture).
         3d. Generate — agent produces proposed rule files per topic area.
             DECISION: Rules exist already?
             - REFRESH: overwrite all existing rule files with new
               generated versions.
             - SELECTIVE: user chooses which topic areas to regenerate;
               others left intact.
             - REPORT-ONLY: generate a diff report of proposed changes
               without writing files.
             - CANCEL: abort; leave existing rules unchanged.
         3e. Integrate — agent writes accepted rule files into .cf-studio/;
             updates Studio manifest to reference new files.
             DECISION: Accept proposed rule files or edit per-topic?
             - ACCEPT ALL: all proposed files written as generated.
             - EDIT PER-TOPIC: user reviews and edits each topic area
               interactively before it is written.
         3f. Validate — agent re-reads written rule files and checks
             internal consistency; reports any contradictions or gaps.
    4. DECISION: Which IDE integrations to enable?
       - User selects from detected available integrations (e.g., VS Code,
         JetBrains, Cursor); Studio writes corresponding integration
         config files.
       - User may skip all IDE integrations.
    5. Run `cfs generate-agents` to instantiate agent kit(s) based on
       the finalized rule files and detected stack profile.
    6. Run `cfs validate-kits` to confirm that all generated agent kits
       are internally consistent and reference only resolvable rule files
       and workflow definitions.
    7. User reviews validation report; any kit errors must be resolved
       (edit rules or re-run cf-auto-config selective) before the
       project is considered onboarded.
  DECISION_POINTS:
    - CyPilotMigration: accept migration offer / start fresh
    - RulesExistPolicy: refresh / selective / report-only / cancel
    - RuleFileAcceptance: accept all / edit per-topic
    - IDEIntegrations: one or more integrations / skip all
  GUARDS: [
    `cfs init` must complete before cf-auto-config is invoked,
    Precheck phase must pass before scan begins,
    Rule files may not be written until user has accepted or edited proposals,
    `cfs validate-kits` must report no errors before onboarding is declared complete
  ]
  NEXT: Project ready for day-to-day Studio workflows (Journeys 1, 3, 4, 5, 6)
```

---

### Journey 3: Brainstorm and Write an Architectural Decision Record

```text
ALGORITHM BrainstormAndWriteADR
  ACTOR: Architect or Tech lead
  GOAL: Produce a structured, persisted, and reviewed Architectural
        Decision Record (ADR) grounded in a facilitated multi-agent
        brainstorm
  INPUTS: [
    Studio activated in project directory,
    ADR topic or decision question stated by the user,
    Optional: existing ADRs or context documents for reference
  ]
  OUTPUTS: [
    Persisted brainstorm session summary (disk artifact),
    Reviewed and committed ADR document in the project docs tree,
    Review findings report (embedded in cf-write-docs run)
  ]
  STEPS:
    1. Invoke cf-brainstorm with the ADR topic as the driving question.
       cf-brainstorm runs its internal lifecycle:
         1a. Panel proposal — Studio proposes a panel of agent personas
             (e.g., pragmatist, security advocate, scalability thinker,
             domain expert).
             DECISION: Panel size and composition?
             - ACCEPT PROPOSED: use Studio's suggested panel as-is.
             - EDIT: user adjusts panel size or replaces personas before
               brainstorm begins.
         1b. DECISION: Brainstorm execution mode?
             - INLINE: all panel agent reasoning runs in the primary
               thread sequentially; simpler, lower parallelism.
             - SINGLE-AGENT: one synthesizing agent plays all panel roles
               in sequence, producing a unified output.
             - FAN-OUT: each panel persona runs as a parallel sub-agent;
               outputs collected and merged by a synthesis agent.
         1c. Topic rounds — each panel persona presents its analysis of
             the decision question: options, trade-offs, risks, and
             recommendations.
         1d. DECISION: Challenge round?
             - YES: each persona critiques the strongest proposal from
               another persona; sharpens the recommendation.
             - NO: skip challenge round; move directly to wrap.
         1e. Wrap — synthesis agent aggregates panel outputs into a
             structured session summary (decision options, trade-offs
             matrix, recommended option with rationale).
             DECISION: Session persistence?
             - PERSIST TO DISK: session summary written to a brainstorm
               artifact file in the project docs tree.
             - SESSION-ONLY: summary held in context only; not written
               to disk.
    2. User reviews brainstorm summary and confirms the recommended option
       (or selects an alternative) as the basis for the ADR.
    3. Invoke cf-write-docs with the brainstorm summary as the primary
       input and "ADR" as the document type.
       cf-write-docs runs its internal lifecycle:
         3a. Intent capture — cf-write-docs reads document type, topic,
             brainstorm summary, and any reference ADRs.
         3b. DECISION: Audience dimension?
             - DEVELOPER: technical depth, implementation consequences
               emphasized.
             - PM: business impact, risk, timeline consequences emphasized.
             - NEWCOMER: background context, glossary, rationale emphasized.
             - MIXED: balanced treatment; sidebar callouts for specialist
               content.
         3c. Author phase — agent writes the ADR using the Studio ADR
             template (context, decision, status, consequences).
         3d. CI phase — Studio runs documentation validators (link check,
             template conformance, front-matter schema) internally.
         3e. Review phase — agent reviews the authored ADR for clarity,
             completeness, and alignment with the brainstorm recommendation.
         3f. Findings browser — user sees structured findings list.
             DECISION: Fix scope — approve findings before applying?
             - APPROVE ALL: all findings applied without per-finding review.
             - PER-FINDING APPROVAL: user approves or rejects each finding
               individually before the fix is applied.
             - NONE: accept ADR as-is.
         3g. Fix phase — agent applies approved findings; re-runs CI.
         3h. Git finalization — embedded inside cf-write-docs.
             DECISION: Git action?
             - COMMIT: stage ADR and brainstorm artifact; create commit.
             - STAGE ONLY: stage files, leave commit to user.
             - NONE: leave working tree unchanged.
  DECISION_POINTS:
    - PanelComposition: accept proposed / edit personas and size
    - BrainstormMode: inline / single-agent / fan-out
    - ChallengeRound: yes / no
    - SessionPersistence: persist to disk / session-only
    - AudienceDimension: developer / PM / newcomer / mixed
    - FixScopeApproval: approve all / per-finding approval / none
    - GitAction: commit / stage-only / none
  GUARDS: [
    Brainstorm wrap must produce a session summary before cf-write-docs starts,
    User must confirm the recommended decision option before authoring begins,
    ADR template conformance CI check must pass before git finalization,
    Persisted brainstorm artifact path must not conflict with existing files
  ]
  NEXT: ADR committed; team review via pull request (external to Studio)
```

---

### Journey 4: Review and Fix Existing Code

```text
ALGORITHM ReviewAndFixExistingCode
  ACTOR: Developer or Reviewer
  GOAL: Systematically identify issues in existing code, obtain per-finding
        approval, apply fixes, confirm CI passes, and commit the result
  INPUTS: [
    Studio activated in project directory,
    Target code scope identified (file, module, or directory),
    Optional: specific review criteria or methodology names
  ]
  OUTPUTS: [
    Structured findings report with per-finding status (applied / skipped),
    Fixed codebase with CI-passing state,
    Committed changes on the target branch
  ]
  STEPS:
    1. Invoke cf-explore scoped to the target code area.
       cf-explore maps the module structure, dependency graph, and surfaces
       relevant architectural context needed to make review findings
       actionable.
    2. Invoke cf-coding in review-first classification mode, passing the
       exploration summary and target scope.
       cf-coding (review-first) runs its internal lifecycle:
         2a. Intent capture — cf-coding reads target scope, exploration
             summary, and any user-specified review criteria.
         2b. DECISION: Review granularity?
             - SINGLE-PASS: one unified review agent inspects all changes
               or all files in scope in a single pass; produces a flat
               findings list.
             - PER-METHODOLOGY: a separate review pass is executed for
               each configured methodology (e.g., correctness, security,
               performance, style); findings tagged by methodology.
             - PER-LAYER: a separate review pass is executed for each
               architectural layer present in scope (e.g., API surface,
               business logic, data access); findings tagged by layer.
         2c. Findings browser — user sees the complete structured findings
             list with severity, location, methodology/layer tag (if
             applicable), and suggested fix description.
             DECISION: Which findings to fix?
             - ALL: all findings marked for fix application.
             - SUBSET (per-finding approval): user reviews each finding
               individually and marks it approved or skipped.
             - NONE: no fixes applied; findings report saved only.
         2d. Fix phase — agent generates and applies fixes for all
             approved findings. Each fix is scoped to the specific
             location identified in the finding; agent avoids touching
             unapproved areas.
         2e. CI phase — Studio runs configured linters, type-checkers,
             and test suites.
             DECISION: Re-run CI after fix?
             - YES (default): CI runs after fix phase completes; any
               new failures are surfaced and must be acknowledged.
             - NO: skip post-fix CI (user accepts responsibility for
               CI state).
         2f. If post-fix CI introduces new failures, a secondary fix
             loop is offered. User may approve additional targeted fixes
             or accept the CI failures.
         2g. Git finalization — embedded inside cf-coding.
             DECISION: Git action?
             - COMMIT: stage all approved-fix changes; create commit with
               message referencing the findings count and scope.
             - STAGE ONLY: stage changes, leave commit to user.
             - NONE: leave working tree as-is.
  DECISION_POINTS:
    - ReviewGranularity: single-pass / per-methodology / per-layer
    - FindingsFixScope: all / subset (per-finding approval) / none
    - RerunCIAfterFix: yes / no
    - GitAction: commit / stage-only / none
  GUARDS: [
    cf-explore must complete before cf-coding review-first begins,
    Fix phase must only touch locations referenced by approved findings,
    Per-finding approval must be recorded before any fix is applied in subset mode,
    Secondary fix loop must not auto-approve new findings without user review
  ]
  NEXT: Fixed branch ready for pull request or merge (external to Studio)
```

---

### Journey 5: Create and Publish a Behavior Kit

```text
ALGORITHM CreateAndPublishBehaviorKit
  ACTOR: Platform engineer
  GOAL: Package reusable Studio behaviors into a validated, installable
        behavior kit that downstream projects can adopt
  INPUTS: [
    Studio activated in the kit source directory,
    Behavior definitions, rule files, and workflow fragments to be packaged,
    Optional: existing kit manifest for update scenario
  ]
  OUTPUTS: [
    Validated kit artifact with manifest, rule files, and workflow definitions,
    Kit registered or installed in one or more consumer projects,
    Consumer project agent kits regenerated to incorporate new behaviors
  ]
  STEPS:
    1. Invoke cf-kit in the kit source directory.
       cf-kit runs its internal lifecycle:
         1a. Detect state — cf-kit inspects the directory for an existing
             kit manifest. Reports: new kit, update to existing kit, or
             no kit context found.
             DECISION: Kit target path?
             - CURRENT DIRECTORY: kit is built from and into the current
               directory.
             - CUSTOM PATH: user specifies an alternative directory; cf-kit
               operates there.
         1b. Discovery — cf-kit scans the target directory; identifies all
             candidate behaviors, rule files, workflow definitions, and
             skill fragments eligible for inclusion in the kit manifest.
         1c. Manifest proposal — cf-kit generates a proposed kit manifest
             listing all discovered components with metadata (name, version,
             dependencies, exposed entry points).
             DECISION: Manifest approval?
             - APPROVE DEFAULT: accept the proposed manifest as-is.
             - SHOW PREVIEW: display a rendered preview of the manifest
               before approving.
             - EDIT: user edits the manifest interactively (add, remove,
               or annotate components) before approving.
             - RERUN DISCOVERY: discard proposed manifest; re-run discovery
               (useful after the user adds or removes files).
             - CANCEL: abort cf-kit; no manifest written.
         1d. Write phase — cf-kit writes the approved manifest and any
             required packaging metadata to the kit target directory.
         1e. Validate — cf-kit runs internal validation: checks manifest
             schema, resolves all declared component references, and
             confirms no dangling dependencies. Reports validation result.
    2. Kit artifact is ready. User chooses the publication path.
    3. In the consumer project, run `cfs kit install`.
       DECISION: Install mode?
       - COPY: kit files are copied into the consumer project's .cf-studio/
         directory; consumer owns a local copy.
       - REGISTER: kit is registered by reference (path or URL); consumer
         project resolves kit at runtime without copying files.
       - GITHUB: kit is installed from a GitHub repository reference;
         Studio fetches and caches the kit.
    4. During install, Studio checks for conflicts with existing consumer
       project files.
       DECISION: Interactive update decisions per changed file?
       - For each file that would be overwritten: user chooses overwrite /
         keep existing / diff and decide.
    5. Run `cfs generate-agents` in the consumer project to regenerate
       agent kits incorporating the newly installed behavior kit's
       behaviors, rule files, and workflow definitions.
    6. Consumer project agents are now aware of the kit's behaviors and
       can invoke them within Studio workflows.
  DECISION_POINTS:
    - KitTargetPath: current directory / custom path
    - ManifestApproval: approve default / show preview / edit / rerun discovery / cancel
    - InstallMode: copy / register / GitHub
    - PerFileUpdateDecision: overwrite / keep existing / diff and decide
  GUARDS: [
    Discovery must complete before manifest proposal is generated,
    Manifest must be approved (not cancelled) before write phase begins,
    Kit validation must pass before the artifact is considered publishable,
    `cfs generate-agents` must run after install to ensure agent coherence,
    Consumer project must have Studio initialized before kit install
  ]
  NEXT: Consumer project teams begin using kit behaviors in their Studio workflows
```

---

### Journey 6: Generate Project Documentation

```text
ALGORITHM GenerateProjectDocumentation
  ACTOR: Technical writer or Developer
  GOAL: Produce audience-tuned, reviewed, and committed project documentation
        grounded in an exploration of the actual codebase
  INPUTS: [
    Studio activated in project directory,
    Documentation scope defined (module, API, architecture, onboarding, etc.),
    Optional: existing documentation files for incremental update
  ]
  OUTPUTS: [
    New or updated documentation files committed to the project docs tree,
    TOC validation report,
    Language complexity check report,
    Review findings report (embedded in cf-write-docs run)
  ]
  STEPS:
    1. Invoke cf-explore scoped to the target documentation area.
       cf-explore maps modules, public APIs, architectural layers, and
       existing documentation coverage. Exploration summary becomes the
       factual basis for the authored documentation.
    2. Invoke cf-write-docs with the exploration summary and documentation
       scope as inputs.
       cf-write-docs runs its internal lifecycle:
         2a. Intent capture — cf-write-docs reads scope, exploration
             summary, document type, and any existing docs for incremental
             update.
         2b. DECISION: Audience dimension?
             - DEVELOPER: technical depth; code examples, API signatures,
               and implementation details emphasized.
             - PM: business context, feature descriptions, and impact
               emphasized; implementation detail minimized.
             - NEWCOMER: progressive disclosure; prerequisite concepts
               explained, glossary included, setup steps explicit.
             - MIXED: balanced treatment; specialist sections clearly
               labeled; navigation aids provided.
         2c. DECISION: Narrator dimension?
             - FIRST-PERSON: documentation written as "we" or "I" (team
               or author voice).
             - THIRD-PERSON: documentation written in third person
               (system or component as subject).
             - NEUTRAL: passive or impersonal constructions; no personal
               pronouns.
         2d. DECISION: Diagram dimension?
             - AUTO-EMBED: Studio generates and embeds diagrams (e.g.,
               Mermaid) inline in the documentation automatically where
               structural content is detected.
             - SUGGEST: Studio identifies locations where diagrams would
               help and inserts placeholder comments; user creates diagrams.
             - SKIP: no diagrams generated or suggested.
         2e. Author phase — agent writes documentation files per the
             audience, narrator, and diagram settings. References
             exploration summary for accuracy.
         2f. Validate TOC — Studio checks that all section headings are
             consistent with the declared table of contents; reports
             missing or orphaned sections.
         2g. Check language complexity — Studio runs a language complexity
             analysis calibrated to the chosen audience dimension; flags
             sentences or passages that exceed the target reading level.
         2h. CI phase — Studio runs documentation validators (link check,
             template conformance, front-matter schema) internally.
         2i. Review phase — agent reviews authored documentation for
             accuracy (against exploration summary), completeness,
             and audience alignment.
         2j. Findings browser — user sees structured findings list
             covering accuracy issues, complexity violations, broken links,
             and structural gaps.
             DECISION: Fix scope approval?
             - APPROVE ALL: all findings applied automatically.
             - PER-FINDING APPROVAL: user reviews and approves or skips
               each finding before it is applied.
             - NONE: accept documentation as-is; findings recorded only.
         2k. Fix phase — agent applies approved findings; re-runs TOC
             validation and language complexity check.
         2l. Git finalization — embedded inside cf-write-docs.
             DECISION: Git action?
             - COMMIT: stage all documentation files; create commit with
               message referencing scope and audience.
             - STAGE ONLY: stage files, leave commit to user.
             - NONE: leave working tree unchanged.
  DECISION_POINTS:
    - AudienceDimension: developer / PM / newcomer / mixed
    - NarratorDimension: first-person / third-person / neutral
    - DiagramDimension: auto-embed / suggest / skip
    - FixScopeApproval: approve all / per-finding approval / none
    - GitAction: commit / stage-only / none
  GUARDS: [
    cf-explore must complete before cf-write-docs begins authoring,
    Audience, narrator, and diagram dimensions must be set before author phase,
    TOC validation must pass before git finalization,
    Fix phase must not alter factual content without re-running exploration
      verification if significant structural changes are made
  ]
  NEXT: Documentation committed; deployment or publishing pipeline (external to Studio)
```

---

### Journey 7: Author a Product Requirements Document (PRD)

```text
ALGORITHM AuthorPRD
  ACTOR: Product Manager
  GOAL: Produce a validated PRD with actors, FR/NFR, use cases, success
        criteria, and cpt-IDs that can gate downstream SDLC artifact authoring
  INPUTS: [
    Product concept or problem description,
    Stakeholder context
  ]
  OUTPUTS: [
    Validated PRD markdown file with cpt-{system}-fr-* and cpt-{system}-nfr-* IDs,
    cfs validate --artifact PASS
  ]
  STEPS:
    1. Invoke cf-sdlc-doc-prd and describe the product or feature area.
    2. Studio binds PRD template + rules + checklist + example from the
       SDLC kit before any authoring begins.
    3. DECISION: Explore context first?
       - YES: Studio discovers existing docs or related artifacts for
         grounding; exploration summary flows into authoring.
       - SKIP: proceed directly to authoring with user-supplied context.
    4. DECISION: Brainstorm requirements framing?
       - YES: Studio explores actors and requirements framing options;
         panel produces a structured framing summary.
       - SKIP: proceed to authoring with stated intent.
    5. Studio authors PRD sections via cf-write-docs engine:
         5a. Overview — product context and problem statement.
         5b. Actors — all user and system roles.
         5c. Goals — business and user goals.
         5d. Functional Requirements — each FR assigned a unique
             cpt-{system}-fr-* ID; written in RFC 2119 MUST/SHALL language.
         5e. Non-Functional Requirements — each NFR assigned a unique
             cpt-{system}-nfr-* ID.
         5f. Use Cases — actor-goal-scenario triples referencing FR IDs.
         5g. Success Criteria — measurable acceptance conditions per FR.
    6. Deterministic gate: run `cfs validate --artifact` on the PRD file.
       Validation fails halt authoring; findings must be resolved.
    7. Semantic review using PRD checklist; structured findings presented
       to user with severity and location.
    8. DECISION: Fix which findings?
       - Per-finding selection: user approves or skips each finding
         individually before fixes are applied.
    9. Re-validate after fixes; iterate until `cfs validate --artifact`
       returns PASS and user marks the PRD done.
  DECISION_POINTS:
    - ExploreContextFirst: yes (discover existing docs) / skip
    - BrainstormRequirementsFraming: yes / skip
    - FixWhichFindings: per-finding selection
  GUARDS: [
    PRD template and rules must be loaded before authoring begins,
    cpt-IDs must be unique within the system namespace,
    All FRs must be written in RFC 2119 MUST/SHALL/SHOULD language,
    cfs validate --artifact must return PASS before PRD is considered complete
  ]
  NEXT: cf-sdlc-doc-design or cf-sdlc-doc-adr
```

---

### Journey 8: Record an Architecture Decision (ADR)

```text
ALGORITHM RecordADR
  ACTOR: Architect or Tech Lead
  GOAL: Capture a technology or design decision with context, options,
        consequences, and a cpt-{system}-adr-* ID that can be cross-referenced
        in the system DESIGN document
  INPUTS: [
    Decision description,
    Considered alternatives,
    DESIGN artifact (optional, for cross-reference)
  ]
  OUTPUTS: [
    ADR markdown file with cpt-{system}-adr-* ID,
    ADR ID registered and cross-referenced in DESIGN
  ]
  STEPS:
    1. Invoke cf-sdlc-doc-adr and describe the decision to capture.
    2. Studio binds ADR template + rules + checklist + example from the
       SDLC kit before any authoring begins.
    3. Studio authors the ADR via cf-write-docs engine:
         3a. Context and Problem Statement — what situation forces this
             decision; constraints and forces in play.
         3b. Decision Drivers — criteria used to evaluate options.
         3c. Considered Options — at least two alternatives with
             pros/cons analysis for each.
         3d. Decision Outcome — chosen option with rationale.
         3e. Consequences — positive, negative, and neutral effects;
             risks introduced; follow-on actions.
         3f. cpt-{system}-adr-* ID — assigned and embedded in front-matter.
    4. Deterministic gate: run `cfs validate --artifact` on the ADR file.
    5. Semantic review against ADR checklist; findings presented by severity.
    6. DECISION: Fix which findings?
       - Per-finding selection: user approves or skips each finding.
    7. Re-validate after fixes; iterate until PASS.
  DECISION_POINTS:
    - FixWhichFindings: per-finding selection
  GUARDS: [
    Decision must have at least two considered options before authoring is complete,
    cpt-{system}-adr-* ID must be assigned before the ADR file is written,
    Consequences section must be non-empty,
    cfs validate --artifact must return PASS before the ADR is considered complete
  ]
  NEXT: Register ADR ID in DESIGN § Architecture Drivers
```

---

### Journey 9: Author a System DESIGN Document

```text
ALGORITHM AuthorSystemDesign
  ACTOR: Architect or Tech Lead
  GOAL: Document system architecture covering components, interfaces,
        boundaries, principles, and constraints, with IDs that downstream
        decomposition and implementation can reference
  INPUTS: [
    PRD (for FRs and NFRs to satisfy),
    ADRs (for architecture drivers),
    High-level architecture knowledge
  ]
  OUTPUTS: [
    DESIGN markdown with cpt-{system}-component-*, cpt-{system}-principle-*, and
    cpt-{system}-constraint-* IDs,
    cfs validate --artifact PASS
  ]
  STEPS:
    1. Invoke cf-sdlc-doc-design.
    2. Studio binds DESIGN template + rules + checklist + example from
       the SDLC kit before any authoring begins.
    3. Studio authors the DESIGN via cf-write-docs engine:
         3a. Architecture Vision — purpose, scope, and quality attributes.
         3b. Architecture Drivers — links to ADR IDs and PRD NFR IDs.
         3c. Principles and Constraints — each assigned a unique
             cpt-{system}-principle-* or cpt-{system}-constraint-* ID.
         3d. Component Model — each component assigned a unique
             cpt-{system}-component-* ID; responsibilities and
             boundaries described.
         3e. Interfaces — contracts between components; input/output
             schemas, protocols, error semantics.
         3f. DECISION: Include sequence diagrams?
             - YES: Studio generates Mermaid sequence diagrams for key
               interaction flows and embeds them inline.
             - SKIP: diagram placeholders inserted; user authors separately.
    4. Deterministic gate: run `cfs validate --artifact` on the DESIGN file.
    5. Semantic review against DESIGN checklist; findings presented.
    6. DECISION: Fix which findings?
       - Per-finding selection: user approves or skips each finding.
    7. Re-validate after fixes; iterate until PASS.
  DECISION_POINTS:
    - IncludeSequenceDiagrams: yes (auto-embed Mermaid) / skip (placeholders)
    - FixWhichFindings: per-finding selection
  GUARDS: [
    All cpt-{system}-component-* IDs must be unique within the system namespace,
    DESIGN must reference existing ADR IDs for every major technology choice,
    PRD FR coverage must be noted in the component model or interface descriptions,
    cfs validate --artifact must return PASS before DESIGN is considered complete
  ]
  NEXT: cf-sdlc-decompose
```

---

### Journey 10: Decompose DESIGN into Feature List (DECOMPOSITION)

```text
ALGORITHM DecomposeDesign
  ACTOR: Tech Lead or PM
  GOAL: Break a DESIGN into an ordered, dependency-linked FEATURE list
        with full PRD and DESIGN coverage so that implementation can
        proceed feature by feature
  INPUTS: [
    DESIGN document (for components and interfaces to decompose),
    PRD (for coverage links back to FRs)
  ]
  OUTPUTS: [
    DECOMPOSITION markdown with cpt-{system}-feature-* IDs, ordering,
    dependency graph, and coverage links,
    cfs validate --artifact PASS
  ]
  STEPS:
    1. Invoke cf-sdlc-decompose with the DESIGN document as primary input.
    2. Studio binds DECOMPOSITION template + rules + checklist + example
       from the SDLC kit before any authoring begins.
    3. Studio authors the DECOMPOSITION via cf-write-docs engine:
         3a. Feature entries — for each deliverable unit of work:
             - Assign a unique cpt-{system}-feature-* ID.
             - Write a one-paragraph description of scope and boundaries.
             - Record dependency links to other cpt-{system}-feature-* IDs.
             - Record coverage links to PRD cpt-{system}-fr-* IDs and DESIGN
               cpt-{system}-component-* IDs.
             - Set initial status (planned).
             - Define a measurable Definition of Done.
         3b. DECISION: Ordering strategy?
             - DEPENDENCY: features ordered by dependency graph
               (no feature before its dependencies).
             - RISK: high-risk or high-uncertainty features pulled forward.
             - VALUE: highest business value features prioritized first.
    4. Deterministic gate: run `cfs validate --artifact` on the
       DECOMPOSITION file.
    5. Semantic review for completeness, ordering correctness, and
       coverage gaps; findings presented.
    6. DECISION: Fix which findings?
       - Per-finding selection: user approves or skips each finding.
    7. Re-validate after fixes; iterate until PASS.
  DECISION_POINTS:
    - OrderingStrategy: dependency / risk / value priority
    - FixWhichFindings: per-finding selection
  GUARDS: [
    Every cpt-{system}-feature-* entry must reference at least one PRD cpt-{system}-fr-* ID,
    Dependency graph must have no cycles,
    All features must have a non-empty Definition of Done,
    cfs validate --artifact must return PASS before DECOMPOSITION is complete
  ]
  NEXT: cf-sdlc-doc-feature (per feature entry)
```

---

### Journey 11: Author a FEATURE Specification

```text
ALGORITHM AuthorFeatureSpec
  ACTOR: Tech Lead or Developer
  GOAL: Write a precise, implementable FEATURE specification with CDSL
        flows, algorithms, state diagrams, and test scenarios that
        developers can implement with full traceability
  INPUTS: [
    DECOMPOSITION entry (cpt-{system}-feature-* ID and description),
    DESIGN (for interface contracts),
    PRD (for acceptance criteria)
  ]
  OUTPUTS: [
    FEATURE markdown with cpt-{system}-flow-*, cpt-{system}-algo-*, and cpt-{system}-state-* IDs
    and test scenarios,
    cfs validate --artifact PASS
  ]
  STEPS:
    1. Invoke cf-sdlc-doc-feature with the target cpt-{system}-feature-* ID.
    2. Studio binds FEATURE template + rules + checklist + example from
       the SDLC kit before any authoring begins.
    3. Studio authors the FEATURE spec via cf-write-docs engine:
         3a. Overview — feature purpose, scope, and link to DECOMPOSITION
             entry.
         3b. CDSL Flows — each flow assigned a unique cpt-{system}-flow-*
             ID; written as GIVEN/WHEN/THEN scenarios covering the nominal
             path and primary alternates.
         3c. Algorithms — each algorithm assigned a unique
             cpt-{system}-algo-* ID; pseudocode or CDSL ALGORITHM block.
         3d. DECISION: Include state diagrams?
             - YES: Studio generates Mermaid state diagrams for stateful
               entities; each state assigned a cpt-{system}-state-* ID.
             - SKIP: state diagram section omitted.
         3e. Test Scenarios — at least one happy-path scenario and one
             error/edge-case scenario per cpt-{system}-flow-* ID.
         3f. Definition of Done — measurable, checkable criteria derived
             from PRD acceptance conditions.
    4. Deterministic gate: run `cfs validate --artifact` on the FEATURE file.
    5. Semantic review against FEATURE checklist for implementability,
       test coverage, and completeness; findings presented.
    6. DECISION: Fix which findings?
       - Per-finding selection: user approves or skips each finding.
    7. Re-validate after fixes; iterate until PASS.
  DECISION_POINTS:
    - IncludeStateDiagrams: yes (Mermaid state diagrams) / skip
    - FixWhichFindings: per-finding selection
  GUARDS: [
    Every cpt-{system}-flow-* ID must be unique within the system namespace,
    Test scenarios must cover at least one happy-path and one error case
      per flow,
    Definition of Done must be measurable and checkable,
    cfs validate --artifact must return PASS before FEATURE spec is complete
  ]
  NEXT: cf-sdlc-implement
```

---

### Journey 12: Implement a FEATURE with Traceability

```text
ALGORITHM ImplementFeatureWithTraceability
  ACTOR: Developer
  GOAL: Write production code that implements a FEATURE specification,
        with @cpt-* markers in source linking every code unit back to
        the FEATURE flow and algorithm IDs it satisfies
  INPUTS: [
    FEATURE spec (cpt-{system}-feature-* ID and cpt-{system}-flow-* IDs),
    Codebase rules (codebase_rules),
    Codebase checklist (codebase_checklist)
  ]
  OUTPUTS: [
    Production code with @cpt-{kind}:{id}:p{N} markers,
    cfs validate --artifact PASS (traceability check),
    CI green (project tests, lint, typecheck, build)
  ]
  STEPS:
    1. Invoke cf-sdlc-implement with the source FEATURE spec.
    2. Studio binds CODE artifact kind + codebase_rules +
       codebase_checklist + source FEATURE before authoring begins.
    3. cf-coding explore gate: Studio discovers relevant files, modules,
       and interfaces in the codebase that the FEATURE will touch.
    4. DECISION: Write tests first?
       - YES (test-first): developer (or Studio) writes failing tests
         for each cpt-{system}-flow-* scenario before implementation code.
       - NO: implementation code written first; tests follow.
    5. Author dispatch — cf-coding writes implementation with
       @cpt-{kind}:{id}:p{N} markers on every function, class, or
       block that satisfies a cpt-{system}-flow-* or cpt-{system}-algo-* ID per
       codebase_rules.
    6. Deterministic gate: run project tests + lint + typecheck + build
       + `cfs validate --artifact` (traceability check). Any failure
       halts and feeds back into the fix phase.
    7. Semantic review: code-checklist + bug-finding review +
       consistency-checklist against the FEATURE contract; findings
       presented by severity.
    8. DECISION: Fix which review findings?
       - Per-finding selection: user approves or skips each finding.
    9. Re-validate after fixes; iterate until `cfs validate --artifact`
       returns PASS and CI is green.
  DECISION_POINTS:
    - TestFirstPath: yes (test-first) / no (implementation-first)
    - FixWhichFindings: per-finding selection
  GUARDS: [
    @cpt-* markers must be present for all cpt-{system}-flow-* IDs declared
      in the FEATURE spec,
    cfs validate --artifact must return PASS before implementation is done,
    CI (tests + lint + typecheck + build) must be green before done,
    No @cpt-* marker may reference an ID not declared in the source FEATURE
  ]
  NEXT: cf-sdlc-pr-review or cf-sdlc-change-impact-analysis
```

---

### Journey 13: Analyze Change Impact Across the Artifact Pipeline

```text
ALGORITHM AnalyzeChangeImpact
  ACTOR: Tech Lead, PM, or Release Manager
  GOAL: Understand which downstream artifacts and @cpt-* code markers
        are affected by a change to an upstream artifact, and surface
        stale or uncovered dependencies before they reach production
  INPUTS: [
    Changed artifact ID (e.g. cpt-{system}-fr-login),
    Baseline ref (prior tag or main branch HEAD),
    Current ref (HEAD or feature branch)
  ]
  OUTPUTS: [
    Impact report at .change-impact/{ID}/report.md containing:
    cascade tree of affected artifacts, coverage gaps, stale @cpt-*
    flags, and optional version bump recommendation
  ]
  STEPS:
    1. Invoke cf-sdlc-change-impact-analysis with the changed artifact ID,
       baseline ref, and current ref.
    2. DECISION: Analysis mode?
       - CASCADE-TRACKING: Studio flags all artifacts and code markers
         downstream of the changed ID as affected or stale; no scoring.
       - RELEASE-READINESS-ESTIMATION: Studio additionally scores
         completeness and produces a version bump recommendation
         (patch / minor / major) based on the breadth and depth of impact.
    3. Studio diffs the upstream artifact between baseline ref and current
       ref; identifies which IDs, sections, or contracts changed.
    4. Studio runs `cfs where-used` on the changed ID to trace all
       downstream dependents, bounded by cascade depth rules per artifact
       type (PRD → DESIGN → DECOMPOSITION → FEATURE → CODE).
    5. Studio runs `cfs spec-coverage` on the affected downstream artifact
       set to identify coverage gaps introduced by the upstream change.
    6. Studio flags stale @cpt-* markers: any code marker referencing an
       ID whose upstream artifact changed more recently than the code was
       last updated (within the configured staleness threshold).
    7. Studio aggregates findings into the impact report and emits a
       structured summary to the user.
  DECISION_POINTS:
    - AnalysisMode: cascade-tracking / release-readiness-estimation
  GUARDS: [
    Read-only operation — Studio must never edit artifacts or code files
      during this workflow,
    Report must be written only under .change-impact/ and not overwrite
      any artifact in the main docs tree,
    cfs where-used and cfs spec-coverage must complete before the report
      is written
  ]
  NEXT: Update affected downstream artifacts, or cf-sdlc-pr-review
```

---

### Journey 14: Review a GitHub Pull Request

```text
ALGORITHM ReviewGitHubPullRequest
  ACTOR: Tech Lead, Reviewer, or Team Lead
  GOAL: Obtain a structured, checklist-based review of a GitHub PR
        against code quality, design, ADR, and PRD standards, with
        severity-rated findings persisted for the team
  INPUTS: [
    GitHub PR number or URL (or "ALL" to review all open PRs),
    Access to the GitHub repository (read-only)
  ]
  OUTPUTS: [
    Structured review report at .prs/{ID}/review.md with findings
    grouped by domain (code, design, ADR, PRD) and rated by severity
    (critical / major / minor / info)
  ]
  STEPS:
    1. Invoke cf-sdlc-pr-review with a PR number, URL, or "ALL".
    2. DECISION: Single PR or all open PRs?
       - SINGLE: Studio fetches the specified PR diff and metadata.
       - ALL: Studio fetches all open PRs in the repository and reviews
         each in sequence, producing a report per PR.
    3. Studio fetches PR diff and metadata fresh from GitHub; prior run
       data is never reused.
    4. Studio analyzes the diff against each configured review domain:
         4a. Code review — correctness, security, performance, style per
             codebase_rules and codebase_checklist.
         4b. Design review — consistency with DESIGN component model,
             interface contracts, and principles.
         4c. ADR review — implementation choices consistent with recorded
             ADR decisions; no silent overrides of decided options.
         4d. PRD review — changed behavior traceable to PRD FRs; no
             scope creep or uncovered requirements.
    5. Studio applies severity classification to each finding:
       critical (blocks merge) / major (should fix before merge) /
       minor (can fix post-merge) / info (observation only).
    6. Studio writes the structured report to .prs/{ID}/review.md.
  DECISION_POINTS:
    - ReviewScope: single PR / all open PRs
  GUARDS: [
    Read-only operation — Studio must never modify local files during
      this workflow,
    PR diff must always be re-fetched from GitHub; cached or prior run
      data must not be used,
    Report must be written only under .prs/ and must not modify any
      artifact in the main docs or source tree
  ]
  NEXT: cf-sdlc-pr-status or address findings in a fix branch
```

---

### Journey 15: Reconstruct SDLC Artifacts from Existing Code

```text
ALGORITHM ReconstructSDLCArtifacts
  ACTOR: Tech Lead or Architect (working with legacy or undocumented code)
  GOAL: Reconstruct missing PRD, DESIGN, DECOMPOSITION, and FEATURE
        artifacts from existing code, using @cpt-* markers as primary
        evidence and flagging gaps where evidence is insufficient
  INPUTS: [
    Code scope (directory or file list),
    Existing @cpt-* markers in code (or structural patterns if none exist)
  ]
  OUTPUTS: [
    Reconstructed SDLC artifact files with IDs grounded in actual code
    behavior,
    @cpt-gap flags in artifacts where code evidence is missing or
    ambiguous,
    cfs validate --artifact PASS on each reconstructed artifact
  ]
  STEPS:
    1. Invoke cf-sdlc-reverse-engineer with the code scope.
    2. DECISION: Marker strategy?
       - MARKER-FIRST: Studio extracts existing @cpt-* markers from
         the code scope as the primary source of artifact structure;
         marker IDs become the skeleton of reconstructed artifacts.
       - PATTERN-INFERENCE: Studio infers artifact structure from code
         patterns (module boundaries, function names, test names) when
         no @cpt-* markers exist or are insufficient.
    3. DECISION: Execution mode?
       - SUBAGENTS: Studio dispatches parallel sub-agents per artifact
         kind for higher throughput.
       - PLAN: Studio produces a reconstruction plan for user review
         before executing.
       - PLAN-RALPHEX: Studio produces a plan, executes it, then runs
         a senior-reviewer pass (ralphex) to validate the reconstruction.
    4. Studio extracts @cpt-* markers from the code scope; builds a
       marker-to-location index.
    5. DECISION: Target artifact kinds?
       - FEATURE ONLY (default): reconstruct FEATURE specs only,
         grounded directly in code behavior.
       - FULL PIPELINE: reconstruct PRD, DESIGN, DECOMPOSITION, and
         FEATURE artifacts in pipeline order, each grounded in the
         artifact below it and ultimately in code.
    6. Studio delegates artifact authoring to cf-write-docs under the
       reverse-engineering methodology for each targeted artifact kind:
         6a. For each artifact: Studio authors content grounded in code
             evidence (marker locations, function signatures, test cases,
             module interfaces).
         6b. Where code evidence is absent or ambiguous, Studio inserts
             a @cpt-gap flag with a description of what is missing and
             why it could not be inferred.
    7. Deterministic gate: run `cfs validate --artifact` on each
       reconstructed artifact file.
    8. Semantic review of reconstructed content for accuracy,
       completeness, and gap coverage; findings presented.
    9. DECISION: Fix which findings?
       - Per-finding selection: user approves or skips each finding.
   10. Re-validate after fixes; iterate until PASS on all artifacts.
  DECISION_POINTS:
    - MarkerStrategy: marker-first / pattern-inference
    - ExecutionMode: subagents / plan / plan-ralphex
    - TargetArtifactKinds: FEATURE only (default) / full pipeline
      (PRD + DESIGN + DECOMPOSITION + FEATURE)
    - FixWhichFindings: per-finding selection
  GUARDS: [
    Every reconstructed requirement or flow must be grounded in actual
      code behavior observable in the code scope,
    Discrepancies between inferred spec and actual code must be flagged
      explicitly as @cpt-gap or a finding — never silently omitted,
    cfs validate --artifact must return PASS on each artifact before
      reconstruction is declared complete,
    Studio must never delete or overwrite existing SDLC artifacts without
      explicit user confirmation
  ]
  NEXT: Register reconstructed artifacts in artifacts.toml; run
        cfs validate for full pipeline traceability check
```

---

### Journey 16: Full SDLC Pipeline End-to-End

```text
ALGORITHM FullSDLCPipelineEndToEnd
  ACTOR: Product Manager, Architect, Developer (team)
  GOAL: Deliver a fully traced feature from product requirement to
        production code, with every artifact linked by CPT IDs and
        validated at each stage
  INPUTS: [
    Product idea or problem statement,
    Constructor Studio initialized with SDLC kit,
    Codebase accessible
  ]
  OUTPUTS: [
    PRD + ADR(s) + DESIGN + DECOMPOSITION + FEATURE spec(s) +
    production code with @cpt-* markers,
    all artifacts passing cfs validate --artifact,
    CI green
  ]
  STEPS:
    1. PM invokes cf-sdlc-doc-prd — authors PRD with cpt-{system}-fr-* and
       cpt-{system}-nfr-* IDs; cfs validate --artifact PASS.
    2. Architect invokes cf-sdlc-doc-adr for each major technology
       decision — ADRs with cpt-{system}-adr-* IDs cross-referenced in DESIGN.
    3. Architect invokes cf-sdlc-doc-design — DESIGN with
       cpt-{system}-component-*, cpt-{system}-principle-*, cpt-{system}-constraint-* IDs;
       cfs validate --artifact PASS.
    4. Tech lead invokes cf-sdlc-decompose — DECOMPOSITION with ordered
       cpt-{system}-feature-* IDs linking back to PRD FRs and DESIGN components.
    5. For each feature: developer invokes cf-sdlc-doc-feature — FEATURE
       spec with cpt-{system}-flow-*, cpt-{system}-algo-*, cpt-{system}-state-* IDs and test
       scenarios.
    6. Developer invokes cf-sdlc-implement — code written with @cpt-*
       markers; cfs validate --artifact + CI gate PASS.
    7. cfs spec-coverage run to confirm marker coverage meets project
       threshold.
    8. cf-sdlc-pr-review run on the implementation PR; findings
       addressed.
  DECISION_POINTS:
    - ADRCount: one ADR per major decision (architecture, library
      choice, API design)
    - FeatureGranularity: split or merge DECOMPOSITION entries based on
      estimated effort
    - TestFirst: write FEATURE test scenarios before implementation?
  GUARDS: [
    Every FEATURE references its parent DECOMPOSITION entry,
    Every @cpt-* marker in code traces to a cpt-{system}-flow-* in a FEATURE
      spec,
    cfs validate --artifact PASS at every artifact stage,
    CI green before PR review
  ]
  NEXT: cf-sdlc-change-impact-analysis (for future changes),
        cf-sdlc-pr-status (ongoing monitoring)
```

---

### Journey 17: Release Readiness Estimation

```text
ALGORITHM ReleaseReadinessEstimation
  ACTOR: Release Manager, Tech Lead
  GOAL: Before a release, assess the downstream impact of all artifact
        changes and get a version bump recommendation
        (major / minor / patch)
  INPUTS: [
    Upstream artifact ID that changed,
    Baseline ref (prior release tag),
    Current ref (HEAD or release branch)
  ]
  OUTPUTS: [
    Impact report at .change-impact/{ID}/report.md: cascade tree,
    stale @cpt-* flags, coverage gaps, version bump recommendation
  ]
  STEPS:
    1. Identify the upstream artifact that changed most significantly
       (e.g. a PRD FR was revised).
    2. Invoke cf-sdlc-change-impact-analysis, choose mode:
       release-readiness-estimation.
    3. Studio diffs upstream artifact between baseline tag and HEAD.
    4. Studio runs cfs where-used to trace all downstream dependents
       (bounded per artifact type).
    5. Studio runs cfs spec-coverage on affected downstream set.
    6. Studio flags stale @cpt-* markers (not updated within threshold
       since the upstream change).
    7. Studio aggregates cascade tree, coverage gaps, and stale flags.
    8. Studio derives version bump recommendation from impact severity
       (breaking → major, new behavior → minor, fix → patch).
    9. Release manager reviews report and decides go / no-go.
  DECISION_POINTS:
    - BaselineRef: prior release tag vs main branch tip
    - MultipleChangedArtifacts: run analysis per artifact or pick
      highest-impact one
  GUARDS: [
    Read-only — report only, never edits artifacts or code,
    Report written under .change-impact/ only
  ]
  NEXT: Update stale downstream artifacts, then re-run analysis to
        confirm clean; proceed to release
```

---

### Journey 18: PR Status Monitoring

```text
ALGORITHM PRStatusMonitoring
  ACTOR: Team Lead, PM, Release Manager
  GOAL: Get a current status snapshot of one or all open GitHub PRs —
        CI state, open comments, severity of unresolved feedback,
        resolved-comment audit
  INPUTS: [
    GitHub PR number or "ALL",
    Access to GitHub repo
  ]
  OUTPUTS: [
    Status report at .prs/{ID}/status.md per PR: CI status, open
    comment count, severity assessment, resolved-comment audit
  ]
  STEPS:
    1. Invoke cf-sdlc-pr-status with PR number or ALL.
    2. Studio re-fetches PR data from GitHub fresh (never reuses prior
       run).
    3. Studio generates status report: CI checks, open vs resolved
       comments, severity of open feedback (critical / major / minor).
    4. Studio audits resolved comments: flags any that were resolved
       without a corresponding code change.
    5. Studio emits report to .prs/{ID}/status.md.
    6. Team lead reviews: decide to merge, request changes, or escalate.
  DECISION_POINTS:
    - ReviewScope: single PR or all open PRs?
    - ResolvedCommentAudit: surface all or only suspicious resolutions?
  GUARDS: [
    Always re-fetched from scratch — never reuses prior conversation
      data,
    Read-only: no local file modifications
  ]
  NEXT: cf-sdlc-pr-review (for deeper review of a specific PR),
        or merge / close decision
```

---

### Journey 19: Spec Coverage Gate in CI

```text
ALGORITHM SpecCoverageGateInCI
  ACTOR: Tech Lead, Developer, DevOps
  GOAL: Enforce a minimum @cpt-* marker coverage threshold as a quality
        gate — fail the pipeline if coverage or granularity drops below
        the configured floor
  INPUTS: [
    Configured min-coverage and min-granularity thresholds in project
    config,
    Codebase with @cpt-* markers
  ]
  OUTPUTS: [
    Coverage report (JSON or human-readable): per-file coverage %,
    aggregate coverage %, granularity score;
    exit code 0 (PASS) or non-zero (FAIL)
  ]
  STEPS:
    1. Developer adds or modifies code with @cpt-* markers after
       implementing a FEATURE.
    2. CI pipeline (or developer locally) runs
       cfs spec-coverage --min-coverage 80 --min-granularity 0.7.
    3. Studio scans codebase for @cpt-* markers; computes per-file and
       aggregate coverage.
    4. Studio computes granularity score (ratio of instruction-level
       markers to block-level markers).
    5. Studio compares results against thresholds; emits PASS or FAIL
       with per-file breakdown.
    6. On FAIL: developer identifies uncovered files, adds missing
       @cpt-* markers, re-runs.
    7. Optional: cfs spec-coverage --output report.json for CI artifact
       storage.
  DECISION_POINTS:
    - ScanScope: run against full codebase or specific system
      (--source filter)?
    - FailMode: fail pipeline or warn only?
      (--min-* flags control hard failure)
  GUARDS: [
    Thresholds configured before enforcement,
    Report always emitted even on failure for diagnosis
  ]
  NEXT: Add missing markers → re-run → merge when PASS
```

---

### Journey 20: Cross-Repo Traceability Navigation

```text
ALGORITHM CrossRepoTraceabilityNavigation
  ACTOR: Tech Lead, Architect
  GOAL: In a multi-repo workspace, trace a CPT ID from its definition
        in one repo to all its usages across all registered workspace
        sources
  INPUTS: [
    Initialized multi-repo workspace (.cf-workspace.toml),
    CPT ID to investigate,
    All sources reachable
  ]
  OUTPUTS: [
    Definition location (file:line in source repo),
    All usage locations across workspace repos,
    Content of the ID's text block
  ]
  STEPS:
    1. Confirm workspace is initialized and sources are synced
       (cfs workspace-info, cfs workspace-sync if needed).
    2. Run cfs list-ids to enumerate all CPT IDs across the workspace
       (or filter by kind with --kind).
    3. Run cfs where-defined <ID> --source <workspace-source> to find
       the definition file and line.
    4. Run cfs where-used <ID> across all workspace sources to find
       downstream references.
    5. Run cfs get-content <ID> to read the full text block associated
       with that ID.
    6. Assess blast radius: how many files and repos reference this ID.
    7. DECISION: Planning a change?
       - YES: run cf-sdlc-change-impact-analysis on the upstream
         artifact containing this ID.
       - NO: navigation complete; use findings for review or
         documentation.
  DECISION_POINTS:
    - NavigationScope: single ID deep-dive vs scan all IDs of a kind?
    - IncludeCodeScan: include code file scan in where-used
      (--code flag)?
  GUARDS: [
    All workspace sources must be reachable before cross-repo query,
    Queries are read-only
  ]
  NEXT: cf-sdlc-change-impact-analysis (if change is planned),
        or update artifact referencing this ID
```

---

### Journey 21: Interactive Kit Update Cycle

```text
ALGORITHM InteractiveKitUpdateCycle
  ACTOR: Developer, Tech Lead
  GOAL: Update an installed kit to the latest version, reviewing each
        changed file individually before accepting changes
  INPUTS: [
    Installed kit (copy or register mode),
    Upstream kit source (local path, GitHub, or Git)
  ]
  OUTPUTS: [
    Updated kit files on disk (only accepted files),
    Preserved files for declined changes,
    .cf-studio-kit.toml reflecting new version
  ]
  STEPS:
    1. Run cfs kit check-updates to see which installed kits have
       upstream changes available.
    2. Review the update summary (new version, changed files, breaking
       changes noted).
    3. Run cfs kit update for the target kit.
    4. For each changed file, Studio presents a diff and asks:
       accept / decline / modify.
         - accept: upstream version replaces local file.
         - decline: local file kept as-is.
         - modify: user edits the merged result before writing.
    5. After all files reviewed, Studio writes only accepted / modified
       files.
    6. Run cfs generate-agents to refresh IDE agent integrations
       reflecting kit changes.
    7. Run cfs validate-kits to confirm updated kit structure is valid.
  DECISION_POINTS:
    - PerFileDecision: accept / decline / modify (per changed file)
    - RegenerateAgents: regenerate agent integrations after update?
      (recommended yes)
  GUARDS: [
    Declined files are never overwritten,
    Modified files written only after user confirms edit,
    validate-kits run after update
  ]
  NEXT: cfs generate-agents, then test updated kit behavior in a
        workflow run
```

---

### Journey 22: CDSL ID Navigation Workflow

```text
ALGORITHM CDSLIDNavigationWorkflow
  ACTOR: Developer, Architect
  GOAL: Understand the full traceability picture for a given feature
        area — enumerate IDs, find definitions, find usages, read
        content — before making a change
  INPUTS: [
    Feature area or subsystem of interest,
    Constructor Studio initialized with registered artifacts
  ]
  OUTPUTS: [
    List of all CPT IDs in the area,
    Definition locations,
    Usage locations across artifacts and code,
    Content of relevant ID blocks
  ]
  STEPS:
    1. Run cfs list-id-kinds to understand what ID kinds exist in the
       project (feature, flow, component, etc.).
    2. Run cfs list-ids --kind feature --pattern <area> to enumerate all
       feature IDs in the subsystem.
    3. For each ID of interest: run cfs where-defined <ID> to locate the
       defining artifact and line.
    4. Run cfs where-used <ID> to find all artifacts and code that
       reference this ID.
    5. Run cfs get-content <ID> to read the full specification block for
       that ID.
    6. DECISION: Include code-level inspection?
       - YES: run cfs get-content <ID> --code --inst to read
         instruction-level marker content.
       - NO: artifact-level navigation complete.
    7. Build a mental map of the subsystem's artifact → code
       traceability before deciding what to change.
  DECISION_POINTS:
    - NavigationDepth: single ID deep-dive vs breadth scan of all IDs
      in an area?
    - IncludeCodeScan: include code file scan? (adds --code flag to
      where-used and get-content)
  GUARDS: [
    All commands are read-only,
    No files modified
  ]
  NEXT: cf-sdlc-change-impact-analysis (to assess impact of planned
        change), or cf-sdlc-implement (to add missing markers)
```

---

## Cross-Journey Patterns

The six journeys above share a set of recurring structural patterns. Understanding these patterns helps product managers reason about how Studio workflows compose.

### Explore Gate

Journeys 1, 4, and 6 all begin with an optional or mandatory invocation of `cf-explore`. The explore gate exists because authoring agents (cf-coding, cf-write-docs) need grounded factual context about the codebase to produce accurate output. When the target is already known and narrow, explore can be skipped (Journey 1 decision point). When the target is a review or documentation exercise over unfamiliar territory, explore is always warranted. The exploration summary artifact flows forward as an input to the subsequent workflow.

### Brainstorm Gate

Journeys 1 and 3 offer a brainstorm gate before authoring begins. The brainstorm gate is triggered when design intent is ambiguous or when multiple implementation or architectural options need structured comparison. cf-brainstorm's panel-and-challenge model produces a session summary that serves as a structured design input to cf-coding or cf-write-docs. The gate is optional in Journey 1 and mandatory in Journey 3 (since the brainstorm output is the ADR's primary source material).

### Plan-First Pattern

Journey 1 introduces the plan-first pattern: when a feature spans multiple files, layers, or sub-tasks, cf-plan decomposes the intent into ordered tasks with acceptance criteria before cf-coding is invoked. This prevents cf-coding from making ad-hoc scope decisions during implementation. The plan artifact is explicitly confirmed by the user, making scope boundaries an explicit agreement rather than an implicit inference.

### Sub-Agent Dispatch Modes

Journeys 1 and 3 expose the sub-agent dispatch decision (native parallel vs. inline sequential vs. single-agent). In v1.5.9, this dispatch mode is selected at the start of the workflow that uses sub-agents (cf-coding for implementation tasks, cf-brainstorm for panel personas). The dispatch mode affects latency and observability but not the logical content of the output. Users who need full visibility into intermediate outputs should prefer inline or single-agent mode.

### Review-Fix Loop

Every workflow that produces file artifacts (cf-coding, cf-write-docs) embeds an internal review-fix loop. The loop always produces a findings list before any fix is applied. The fix scope decision — approve all, per-finding approval, or none — is a consistent gate that prevents unreviewed changes from being written. After fixes are applied, CI (or documentation validators) re-run to confirm the fixed state is clean. If new failures arise, a secondary fix opportunity is offered before git finalization.

### Git Finalization

In v1.5.9, git finalization is embedded inside each workflow that produces committed artifacts (cf-coding, cf-write-docs, cf-kit). There is no standalone `cf-git-commit` workflow. The git action decision (commit / stage-only / none) is the last decision in every such workflow. This means that users who want to batch changes across multiple workflow runs should choose stage-only on all but the final run, then commit manually or invoke a new workflow run scoped to the final commit.
