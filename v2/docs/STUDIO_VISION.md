---
marp: true
theme: rose-pine-moon
paginate: true
size: 16:9
---

<!--
Investor-first rewrite of Studio vision deck.
Source basis: user's Marp draft, refined for investor narrative, wedge, moat, ROI, and competitive positioning.
-->

> NOTE: Constructor Studio is one of the 3 main Elements of Constructor Fabric. Please read @CONSTRUCTOR_FABRIC_VISION.md first!

# Studio

## AI control plane for Software Engineering

AI made code generation faster.

Studio helps professional software development teams safely move from **product intent to production**.

Constructor Studio is an integrated workspace – bringing together all scenarios in one place.
- It is implemented as:
  - A web application in a browser
  - A desktop application for macOS, Linux, Windows, iOS/Android
  - A CLI that can be used from other tools (less beneficial because all the existing tools were created for developers and will not benefit all other roles)
- It is intended for:
  - Product Management (CPO, Product Owner, Product Manager, Program Manager)
  - UX Team (UX designers, UI designers)
  - R&D  (CDO, CTO, Chief Architect, Dev Manager, Developer)
  - QA (QA engineers, performance engineers)
  - DevOps /DCO (SRE, DevOps)
  - GTM (CRO, CMO, Regional GM, Marketing Manager, Marketing Communications Manager)


<div class="accent">
For 5–500 person SaaS and service-provider teams adopting AI, but unwilling to lose control, security, traceability, or delivery quality.
</div>

---

# Executive Summary

- **Market shift:** AI coding agents are making code generation cheap and fast
- **New bottleneck:** validation, coordination, governance, and production readiness
- **Product:** Studio is an open-core control plane over existing SDLC systems
- **How it works:** Studio builds a shadow SDLC graph and runs validated actions over it
- **Moat:** Open core adoption + Insight data + Studio automation + Gears kits + custom AI models and World Model
- **Customer promise:** no migration, no vendor lock-in, own your SDLC graph and workflows

---

# The Problem

AI coding tools help teams generate more code faster.
But complex software delivery still breaks across handoffs:

- Modern AI tools were created with the R&D in mind. Other organizations and functions - Product Management, GTM - are having a hard time adopting AI using R&D-centric tools (IDEs - such as Cursor or GitHub are not the native Product Management tools for example and they require a very steep learning curve and do not provide convinient and efficient collaboration capabilities).
- Which AI work creates value vs. cost
- Which agents, models, and prompts are efficient
- Whether requirements, architecture, decisions, tests, and releases stay connected
- Whether production feedback updates future decisions

<div class="accent">
The strategic problem is controlling the full AI-assisted delivery system: value, cost, architecture, decisions, validation, and production readiness.
</div>

---

# Why Now

The entire software industry is adjusting to AI-assisted delivery. Automation will emerge across many categories of software development:

- Business research
  - **Identify the opportunity** - Understand what changes in the market, customer behavior, technology, or business creates an opportunity. 
  - **Understand the problem** - Determine which problems are worth solving.
  - **Define target customers** - Decide who the product is for.  
  - **Quantify the value** - Estimate whether solving the problem matters.
  - **Explore solution space** - Evaluate possible approaches without committing.
  - **Define strategic positioning** - Decide why the product should win - identify the "magic sauce" - unique differentiators (special skills, key people, relationships, ecosystem, channel)
  - **Formulate intent** - Convert research into a clear decision - should we do it or not and why
- Product and requirements work
- Architecture and design
- Coding and code review
- Testing and validation
- Release and operations
- Cost, quality, and governance control

<div class="accent">
We bring 20+ years of experience building highly scalable and secure SaaS platforms — and see a major opportunity to turn AI momentum into governed, validated, production-grade SaaS software delivery.
</div>

---

# Initial Customer Segment

## AI-assisted SaaS and service-provider teams

5–500 person engineering teams that:

- Already use AI coding tools and agents
- Have fragmented delivery systems and context
- Build production-grade, multi-tenant SaaS apps & platforms
- Need security, governance, approvals, and auditability
- Prefer open standards and no vendor lock-in

## Buyer

CTO, VP Engineering, Head of Platform, Head of R&D.

---

# Studio Positioning

Studio is **not** the primary system of record.

It is the **open-core control plane for AI-native software delivery**.

Core graph, connectors, actions, validators, and SDKs are open-source; enterprise teams can extend them without lock-in.

```text
Existing tools stay in place
Jira | ADO | GitHub | GitLab | Bitbucket | Confluence | Office | Teams | CI | Cloud | IDEs
        |
        | sync / events / connectors
        v
Studio shadow SDLC graph
Objects | attributes | relationships | states | history | evidence
        |
        | recommendations / validated actions / approved automation
        v
Controlled write-back
create ticket | update doc | open PR | run CI | assign owner | create release task
```

---

# Core Idea

## Shadow objects. Validated actions. Human-controlled automation.

Studio mirrors work from existing systems, links it into a graph, and applies registered actions to move work forward.

```text
PRD -> Design -> Decomposition -> Agent / Human Work -> Validation -> Release -> Operations
```

Every transition can be:

- Deterministic script
- AI-assisted transformation
- Human task

Every transition can be validated before the next step.

---

# Shadow SDLC Graph

Studio mirrors SDLC objects, intent, context, and attributes.

<div class="cols">
<div>

**Objects**

- Requirement / PRD / Design / ADR
- Task / Epic / Bug / Decision
- Repo / File / Branch / Commit / PR
- Test / Build / Release / Deployment
- Alert / Incident / Runbook / Postmortem
- Person / Team / Role / Approval

</div>
<div>

**Tracked attributes**

- Source system and external ID
- Owner, team, state, version
- Last sync and change history
- Related objects and dependencies
- Validation status and evidence
- Staleness and risk signals

</div>
</div>

---

# Actions Are Executable Edges

Objects are nodes. Actions are executable edges.

```text
PRD -------- create_design() --------> Design
Design ----- decompose_feature() ----> Tasks
Task ------- implement_code() -------> Pull Request
Bug -------- create_repro_test() ----> Failing Test
PR --------- run_ci() ---------------> Build Result
Release ---- deploy() ---------------> Deployment
Incident --- create_postmortem() ----> Postmortem + Prevention Tasks
```

Studio is not only an analytics layer. It can recommend, prepare, validate, and execute approved actions through connectors.

---

# Validated Action Graph

Studio combines objects, relationships, actions, validators, policies, and evidence.

```text
Object(s) + Context + Rules
          |
          v
Action / Transformation
          |
          v
Candidate Object(s) + Evidence
          |
          v
Validators
          |
   pass / fail / retry / escalate
```

Studio does not just generate artifacts. It validates whether work is ready to move to the next state.

---

# Validator Loops

```text
              Candidate artifact
                      |
                      v
                 Validators
                      |
            pass      |      fail
          +-----------+-----------+
          |                       |
          v                       v
      Next task              Fix / retry
                                  |
                            retry < limit?
                            /          \
                         yes            no
                          |              |
                          v              v
                    Candidate       Human escalation
                                    or abort
```

Validator loops create trust, auditability, and bounded automation.

---

# First Killer Workflow

## Bug report → reproduction → failing test → fix PR

This is the best first demo because success is measurable.

```text
Bug report
  -> validate bug description
  -> find suspected component
  -> deploy test environment
  -> reproduce bug
  -> create failing test
  -> confirm test fails on baseline
  -> implement fix
  -> confirm test passes after fix
  -> run CI
  -> create PR
```

---

# Second Killer Workflow

## PRD → Design → Tasks → PR validation

```text
PRD in Confluence / Office / Git
      | create_design(PRD, repo, SaaS kit, templates, rules)
      v
Candidate Design
      | validators: coverage, architecture, security, multi-tenancy, RBAC/ABAC
      v
Approved Design
      | decompose_feature(Design, PRD, repo, team capacity)
      v
Candidate Tasks
      | validators: missing requirements, duplicates, ownership, task size
      v
Jira / ADO / Linear tasks
      | validate PRs against design and acceptance criteria
      v
Release-ready implementation
```

---

# Studio Flow Library

Studio ships with smart predefined flows.

<div class="cols">
<div>

- Gap analysis
- Traceability analysis
- Contradiction detection
- Bloat detection
- Stale artifact detection
- Ownership-gap analysis
- Duplicate-work detection

</div>
<div>

- Architecture-drift detection
- Security-impact analysis
- Test-gap detection
- Release-readiness review
- Incident-to-postmortem automation
- Operations metrics analysis
- AI-cost efficiency analysis

</div>
</div>

---

# Example: Gap Detection

```text
Requirement R-17 exists
      |
      v
No design section references R-17
      |
      v
No task implements R-17
      |
      v
No test covers R-17
      |
      v
Studio recommends:
- update design
- create task
- add test case
- assign owner
```

---

# Human-Centric Automation

Studio is designed to **assist and advise people**, not blindly replace them.

<div class="cols">
<div>

**Studio can**

- Detect gaps
- Recommend fixes
- Explain risks
- Prepare actions
- Validate artifacts
- Summarize context
- Automate approved changes

</div>
<div>

**Humans control**

- Product intent
- Strategic direction
- Architecture tradeoffs
- Security exceptions
- Release approvals
- Risk acceptance
- Customer-impacting actions

</div>
</div>

---

# Platform Architecture

```text
┌──────────────────────────────────────────────┐
│                 Studio UI                    │
│ Dashboards | Graph | Recommendations | Flows │
└─────────────────────┬────────────────────────┘
                      │
┌─────────────────────v────────────────────────┐
│            Studio Control Plane              │
│ Shadow Graph | Actions | Validators | SDKs   │
└─────────────────────┬────────────────────────┘
                      │
┌─────────────────────v────────────────────────┐
│   Insight: operational intelligence layer    │
│ Connectors | Data | Analytics | Benchmarking │
└─────────────────────┬────────────────────────┘
                      │
┌─────────────────────v────────────────────────┐
│              Existing Systems                │
│ Jira | Git | CI | Docs | Teams | IDE | Cloud │
└──────────────────────────────────────────────┘
```

---

# Insight Integration Advantage

Studio integrates with **Insight**, the connector, analytics, and benchmarking layer.

Insight can collect data from hundreds of systems:

- Git, GitHub, GitLab, Bitbucket
- MS Office, Teams, Zoom
- Jira, ADO, Linear, Confluence
- Jenkins, GitHub Actions, GitLab CI
- Claude Code, Windsurf, IDE tools
- Cloud, observability, security, and analytics tools

<div class="accent">
Insight provides cross-vendor data. Studio turns it into SDLC intelligence, recommendations, and validated actions.
</div>

---

# SaaS Development Kits

Studio includes predefined kits for serious SaaS development.

Kits package reusable delivery knowledge:

- Reference architecture
- Templates and examples
- Actions and validators
- Rules and policies
- Recommended flows
- Deployment patterns
- Gears building blocks

Kits can be **open-source defaults** or proprietary vendor/team packs — extensible without platform lock-in.

---

# Gears Building Blocks

Gears are reusable OSS/BSS modules, platform engines, and developer/SRE tooling.

<div class="three">
<div class="box"><b>Identity</b><br/>IdP, SSO, tenant identity, user lifecycle</div>
<div class="box"><b>Authorization</b><br/>RBAC, ABAC, granular roles, delegated administration</div>
<div class="box"><b>Events</b><br/>event bus, schemas, routing, audit events</div>
<div class="box"><b>Serverless</b><br/>functions, workflows, safe runtime, connectors</div>
<div class="box"><b>GenAI</b><br/>model gateway, routing, prompts, evaluation</div>
<div class="box"><b>Platform</b><br/>audit, billing, notifications, APIs, integrations</div>
</div>

---

# Higher Segment Than Lovable

Studio targets higher Lovable-customers' segments where teams need:

- Production-grade multi-tenant SaaS
- Multi-tier service-provider platforms
- Rich RBAC and ABAC
- Tenant isolation
- Granular roles and delegated administration
- Auditability and governance
- Public cloud, private cloud, and on-prem options
- Integration-heavy delivery automation

<div class="accent">
Studio competes above the prototype segment: scalable, secure, governed SaaS.
</div>

---

# AI Cost Efficiency

Studio is designed for AI cost control, not just AI usage.

- Model routing by task type
- Small models for classification and extraction
- Non-GPU models for simple checks
- Large models only for hard reasoning
- Own models for repeated enterprise tasks
- Prompt/version A/B testing
- Incremental analysis & revalidation
- Quality/cost benchmarking

<div class="accent">
Goal: lower AI cost per accepted change, not just more AI activity.
</div>

---

# Developer Experience

Studio starts close to developer workflows.

- CLI tools
- IDE plugins
- MCP servers
- Notifications & dashboards
- Review and acceptance assistance

<div class="accent">
No migration first. Read-only analysis first. Recommendations next. Approved write-back after trust is built.
</div>

---

# ROI Metrics

Studio should be measured by delivery outcomes.

<div class="cols">
<div>

**Speed**

- Faster PRD-to-task cycle
- Faster bug-to-PR cycle
- Faster release readiness review
- Less reviewer time wasted

</div>
<div>

**Quality and control**

- Higher requirement-to-test coverage
- Fewer stale design/code mismatches
- Fewer rejected AI-generated artficats
- Lower AI cost per accepted change

</div>
</div>

Use these as customer proof points and pilot success metrics.

---

# Business Model

Open-core model:

- Core graph, actions, validators, connectors, and SDKs are open-source
- SaaS subscription per active R&D user
- Platform fee for team/company workspace
- Enterprise/private deployment premium
- Proprietary connector, kit, policy, and benchmark packs
- AI usage optimization or usage margin
- Professional services for proprietary kits and workflow rollout

Expansion path:

```text
Read-only insights -> recommendations -> approved automation -> enterprise control plane
```

---

# Moat Flywheel

```text
Open-source core adoption
   -> more connectors and community flows
   -> richer shadow SDLC graph
   -> better validators
   -> better recommendations
   -> more accepted automations
   -> more workflow evidence
   -> stronger kits, benchmarks, and enterprise pull
```

<div class="accent">
The moat is not one model or one agent. It is open-core distribution plus the SDLC graph, validated workflows, reusable kits, and accumulated evidence.
</div>

---

<!-- _class: table-md -->

# Competitor Landscape

| Category | Examples | Main strength | Studio angle |
|---|---|---|---|
| AI app builders | Lovable, Bolt, v0 | Fast prototypes | Higher segment: secure SaaS, no lock-in |
| AI coding tools | Cursor, Claude Code, Windsurf | Developer productivity | Govern across tools, keep user choice |
| Repo platforms | GitHub Copilot, GitLab Duo | Code, PR, DevSecOps | Cross-vendor graph and validation |
| Work systems | Atlassian Rovo | Jira/work-item centered execution | Tool-agnostic open control plane |
| DevOps platforms | GitLab, Harness, GitHub | CI/CD, security, deployment | Improve work across systems |
| Autonomous agents | Devin-like systems | Task execution | Evidence, validators, human control |

---

# Competitive Map

```text
                          Production / Governance Focused
                                      ^
                                      |
             GitLab / Harness         |           Studio
             GitHub / Atlassian       |   cross-SDLC control plane
                                      |
Single-tool / ecosystem --------------+-------------- Cross-tool / vendor-neutral
                                      |
             Cursor / Windsurf        |           emerging gap
             Claude Code              |
                                      |
             Lovable / Bolt / v0      |
                                      v
                              Prototype Focused
```

Studio should not fight every tool directly. It should orchestrate and govern across them — with open-core trust and no vendor lock-in.

---

<!-- _class: table-md -->

# Studio vs Lovable

| Dimension | Lovable-style tools | Studio |
|---|---|---|
| Prototype speed | Strong | Good |
| Production SaaS | Partial | Core focus |
| Multi-tenancy | Limited | Core focus |
| RBAC / ABAC | Basic | Rich model |
| Service providers | Not primary | Core focus |
| Existing tool control | Limited | Core focus |
| On-prem/private deployment | Limited | Supported |
| Open core / no lock-in | Limited | Core focus |
| SDLC graph | Limited | Core architecture |
| Validators | Basic | Core architecture |

**Studio competes above prototypes: production SaaS, extensible core, no lock-in.**

---

<!-- _class: table-md -->

# Studio vs AI Coding Tools

| Dimension | Cursor / Windsurf / Claude Code | Studio |
|---|---|---|
| Developer coding | Strong | Integrated |
| Local context | Strong | Strong via plugins |
| Cross-tool SDLC graph | Limited | Core |
| Product-to-code flow | Partial | Core |
| Validation loops | Partial | Core |
| Management visibility | Limited | Core |
| Governance | Limited | Core |
| Connector write-back | Limited | Core |
| Open workflow layer | Limited | Open core |

Studio should integrate with these tools, not replace them — users keep their IDE and model choices.

---

<!-- _class: table-md -->

# Studio vs DevOps Platforms

| Dimension | GitHub / GitLab / Harness | Studio |
|---|---|---|
| CI/CD | Strong | Integrates |
| Repo / PR workflows | Strong | Integrates |
| Product and design context | Partial | Strong |
| Cross-vendor graph | Limited | Core |
| SaaS kits | Limited | Core |
| AI cost routing | Partial | Core |
| Shadow object model | Limited | Core |
| Human recommendation layer | Partial | Core |
| Vendor lock-in | High ecosystem pull | Avoided by open core |

Studio does not need to beat them at CI/CD. Studio improves work across them while reducing ecosystem lock-in.

---

# Credible Wedge

#### Phase 1: Studio CLI PoC

- Repo-local CLI setup and IDE agent integration
- SDLC kit: PRD → DESIGN → decomposition → FEATURE → implementation
- Deterministic checks for artifacts, traceability, language, and links
- Dependency map across documents, code, tests, and reviews

#### Phase 2: Validated actions

- Gap analysis
- Contradiction detection
- Autonomous bug-fixing
- PR validation

---

# Expansion Roadmap

#### Phase 3: Centralized automation

- Team and role-based workspaces and collaboration
- Visual workflow builder and flow catalog
- UI/UX for workflows, approvals, exceptions, evidence, and handoffs
- Notifications and alerts for gaps, risks, stale work, and failures
- Dashboards for delivery health, AI cost, and release readiness

#### Phase 4: Enterprise control plane

- Insight integration at scale
- Private/on-prem deployment
- Advanced AI and world model
- Operations automation

---

# Key Investor Objections

## “This is too broad.”

Start with one wedge: validated workflows over existing tools for AI-assisted SaaS teams.

## “GitHub, GitLab, Atlassian will build this.”

They optimize their own ecosystems. Studio is open-core, cross-vendor, and integrates with Insight and Gears to complete development automation.

## “How do you prove ROI?”

Measure accepted PR rate, AI cost per accepted change, PRD-to-task cycle time, test coverage, release-readiness time, and review time saved.

---

# Closing

Studio is the **AI control plane for Software Engineering**.

It works with existing tools, not against them.

Its open core gives teams ownership, extensibility, and no vendor lock-in.

It mirrors the SDLC, detects gaps, recommends improvements, and runs validated actions across the lifecycle.

<div class="accent">
Studio helps serious SaaS and service-provider teams build faster — without losing control, security, traceability, or production quality.
</div>
