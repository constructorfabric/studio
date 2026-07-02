# Constructor Studio v1.5.9 — User Journeys

## Introduction

This document describes the six primary cross-cutting user journeys in Constructor Studio v1.5.9 using CDSL (Constructor Domain Specification Language) algorithms. Each journey traces the full path a user takes from intent to outcome, showing how Studio's monolithic workflows chain together.

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

---

## Journeys

### Journey 1: Plan and Implement a New Feature

```cdsl
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

```cdsl
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

```cdsl
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

```cdsl
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

```cdsl
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

```cdsl
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
