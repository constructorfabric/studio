# <p align="center"><img src="images/constructor.png" alt="Constructor Studio Banner" width="100%" /></p>

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
![Version](https://img.shields.io/github/v/release/constructorfabric/studio?label=version)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=constructorfabric_studio&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=constructorfabric_studio)
[![Code Smells](https://sonarcloud.io/api/project_badges/measure?project=constructorfabric_studio&metric=code_smells)](https://sonarcloud.io/summary/new_code?id=constructorfabric_studio)
[![Duplicated Lines (%)](https://sonarcloud.io/api/project_badges/measure?project=constructorfabric_studio&metric=duplicated_lines_density)](https://sonarcloud.io/summary/new_code?id=constructorfabric_studio)
<!-- [![Bugs](https://sonarcloud.io/api/project_badges/measure?project=constructorfabric_studio&metric=bugs)](https://sonarcloud.io/summary/new_code?id=constructorfabric_studio) -->
<!--[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=constructorfabric_studio&metric=coverage)](https://sonarcloud.io/summary/new_code?id=constructorfabric_studio) -->

**Status**: Active

**Convention**: 🖥 = run in a terminal. 💬 = paste into your artificial intelligence (AI) coding tool chat.

## 1. What It Is

Constructor Studio is an organizational workflow layer for AI-assisted software delivery. A workflow is a repeatable work process with known inputs, steps, checks, and outputs.

**Align cross-functional delivery.** It is built for companies where software work crosses many expert groups: product managers, architects, development teams, quality assurance (QA), performance engineering, development and operations (DevOps), security, delivery coordination office (DCO), platform teams, and reviewers who each read different parts of the same system. The main bottleneck is usually not raw code writing. It is keeping people, documents, code, decisions, tests, and operational constraints aligned while the work moves between teams.

**Keep AI process-backed.** Constructor Studio helps an organization put AI into its existing delivery process instead of replacing that process with unstructured chat. It gives teams repository-backed artifacts, templates, skills, checklists, deterministic validation rules, and traceability through Canonical Provenance Trace IDs (CPT IDs). Traceability means you can follow a requirement, decision, or task through later documents, code, tests, and reviews. An artifact is a reviewable project document such as a requirement, design, decision record, feature specification, or plan. Deterministic validation means the same files and rules produce the same check result. A CPT ID can connect a requirement to a design decision, a feature specification, implementation code, tests, and review evidence.

**Separate focused AI roles.** Constructor Studio is sub-agent driven where the AI coding tool supports sub-agents. It separates work into focused roles such as context discovery, planning, writing, review, and validation, so one long chat does not have to hold every responsibility at once.

**Make collaboration inspectable.** The core idea is simple: make collaboration inspectable. Product Requirements Documents (PRDs), Architecture Decision Records (ADRs), DESIGN documents, decompositions, FEATURE specifications, code markers, checklists, and validation outputs can all become part of one connected set of files and checks. Different experts can review the part they own, while `cfs` checks structure, links, required sections, and configured consistency rules.

**Package team delivery rules.** Constructor Studio is also customizable. Teams can change document templates, artifact formats, review checklists, deterministic rules, skill behavior, and skill selection rules. Organizations can package those decisions into kits. A kit is an installable bundle of skills, templates, validation checklists, process instructions, and rules, so one team can standardize a delivery model and scale it across many repositories.

Details:

- [Usage guide](guides/USAGE-GUIDE.md) - workflow selection, first moves, skill message examples, delegation, workspaces, dependency map, and common mistakes
- [Configuration guide](guides/CONFIGURATION.md) - CPT IDs, artifacts, templates, checklists, deterministic validation, kits, dependency map, mirrors, and quick references
- [Agent tools guide](guides/AGENT-TOOLS.md) - how Constructor Studio maps into Claude Code, Cursor, Codex, Copilot, Windsurf, and other AI coding tools
- [Project extensibility guide](guides/PROJECT-EXTENSIBILITY.md) - organization-level composition, multi-repository patterns, configuration manifests, and extensibility

## 2. Install and Connect a Repository

🖥 Install the command-line interface (CLI):

```bash
pipx install git+https://github.com/constructorfabric/studio.git
```

🖥 Check that the install works:

```bash
cfs --version
```

🖥 Initialize the repository:

```bash
cfs init
```

When `cfs init` offers to install the Software Development Life Cycle (SDLC) kit, accept it. The SDLC kit is the usual starting point for product-to-code traceability.

🖥 Generate integration files for your AI coding tool:

```bash
cfs generate-agents
```

`cfs init` creates the repository-local Studio setup directory, normally `.cf-studio/`. The repository footprint is intentionally small: generated Studio runtime files, the local `cfs` support files, and generated AI coding tool agent configuration files are gitignored by default. `cfs generate-agents` writes those tool integration files when needed, and they can be repaired or regenerated. Project configuration and any kit content you choose to track are the parts your organization reviews and evolves.

If a repository already contains Constructor Studio setup files, you can usually skip the install and initialization steps. Open that repository in your AI coding tool and activate Studio in chat:

💬 Activate Studio:

```text
cf
```

Then start with a concrete skill, for example:

💬 Open help:

```text
cf-help
```

💬 Explore the repository:

```text
cf-explore: find the main artifacts and code paths for the billing workflow
```

💬 Work on code:

```text
cf-coding: implement the next safe phase of this migration
```

Install kits manually when you skipped the SDLC kit during `cfs init`, need to add it later, or want another predefined delivery model:

🖥 Install the SDLC kit:

```bash
cfs kit install constructorfabric/studio-kit-sdlc
```

🖥 Regenerate integration files after installing a kit:

```bash
cfs generate-agents
```

Other kit installation options exist for different organizational needs:

🖥 Install a kit from GitHub:

```bash
cfs kit install <owner/repo[@ref]>
```

🖥 Install a kit from a generic Git source:

```bash
cfs kit install git/<url>[//<subdir>][@<kit>] --version <ref>
```

🖥 Copy a local kit into the setup directory:

```bash
cfs kit install --path <path> --install-mode copy
```

🖥 Register a local kit in place:

```bash
cfs kit install --path <path> --install-mode register
```

Use a GitHub or generic Git kit when a platform or architecture team publishes a shared standard. Use `copy` when you want the kit resources copied into the setup directory. Use `register` when the kit source should stay in place inside the project or workspace.

Run validation locally and in continuous integration (CI):

🖥 Validate configured artifacts and traceability:

```bash
cfs validate
```

🖥 Validate guide tables of contents:

```bash
cfs validate-toc guides/USAGE-GUIDE.md guides/CONFIGURATION.md guides/AGENT-TOOLS.md
```

🖥 Check allowed document languages:

```bash
cfs check-language README.md guides/USAGE-GUIDE.md guides/CONFIGURATION.md guides/AGENT-TOOLS.md
```

More setup detail:

- [Installation and setup reference](guides/USAGE-GUIDE.md#2-installation-and-setup-reference)
- [Kit management](guides/CONFIGURATION.md#8-kit-management)
- [AI-tool-specific setup and tradeoffs](guides/AGENT-TOOLS.md)
- [Mirror overrides](guides/CONFIGURATION.md#10-mirror-overrides-cfs-mirror)
- [Contributing](CONTRIBUTING.md)

## 3. Success Story

A typical organization starts by installing the SDLC kit in the repository that owns delivery artifacts. If the organization works across several repositories, a lead or architect can set up a workspace: one repository for product and architecture documents, one for the user interface, one for backend services, and more for microservices or shared libraries.

The product manager starts with discovery and brainstorming:

💬 Gather context:

```text
cf-explore: gather existing product notes, customer constraints, and related artifacts
```

💬 Explore options:

```text
cf-brainstorm: map the options for the new billing workflow
```

💬 Write the product requirements:

```text
cf-sdlc-doc-prd: write the Product Requirements Document for the billing workflow
```

The Product Requirements Document is reviewed against the configured methodology and checklist. Deterministic validation checks the artifact shape, required sections, references, and CPT ID structure:

🖥 Validate the repository:

```bash
cfs validate
```

The architect reads the Product Requirements Document, records technical decisions, and writes the design:

💬 Record a technical decision:

```text
cf-sdlc-doc-adr: record the architecture decision for payment provider isolation
```

💬 Write the design:

```text
cf-sdlc-doc-design: write the DESIGN document from the approved Product Requirements Document and Architecture Decision Records
```

💬 Decompose the design into features:

```text
cf-sdlc-decompose: decompose the DESIGN document into reviewable FEATURE work
```

Development teams then implement scoped features. The implementation preserves CPT traceability in code and tests, so reviewers can see which code implements which approved requirement or design element:

💬 Write a feature specification:

```text
cf-sdlc-doc-feature: write the FEATURE spec for invoice retry handling
```

💬 Implement the feature:

```text
cf-sdlc-implement: implement the approved FEATURE specification with CPT markers and unit tests
```

💬 Review the code:

```text
cf-coding: review the changed code for correctness, regression risk, and missing tests
```

Quality assurance, performance, security, DevOps, and delivery coordination teams use the same connected files and checks. They can review artifacts, create focused test plans, inspect deployment constraints, check operational risks, and validate whether the implementation still matches approved scope. They do not need to read the same document in the same way; each team can use the skill and checklist that matches its responsibility.

Architects and leads can render a dependency map across documents and code:

🖥 Render the dependency map:

```bash
cfs map
```

💬 Review the map for broken references:

```text
cf-map: find dangling references
```

💬 Inspect one feature's links:

```text
cf-map: show which artifacts and code markers connect to the billing retry FEATURE specification
```

The result is not "AI wrote the project." The result is a reviewable delivery system: Product Requirements Document to Architecture Decision Record to DESIGN document to DECOMPOSITION document to FEATURE specification to code to tests, linked by CPT IDs, customizable by kit, and usable by the different teams that already own the software process.

## Skills and Workflows

Base Constructor Studio skills:

| Skill | Use |
|---|---|
| `cf-help` | See what Constructor Studio can do and where to start. |
| `cf-explore: ...` | Find relevant files, artifacts, rules, and project context. |
| `cf-brainstorm: ...` | Explore options before scope is fixed. |
| `cf-auto-config` | Infer or refresh project rules and setup for an existing repository. |
| `cf-plan: ...` | Split large or risky work into reviewable phases. |
| `cf-coding: ...` | Write, refactor, fix, or review source code. |
| `cf-write-docs: ...` | Write, revise, or review guides, reports, and README files. |
| `cf-write-skills: ...` | Write or review skills, prompts, workflows, and agent instructions. |
| `cf-explain: ...` | Walk through a document, pull request, code area, or decision. |
| `cf-map: ...` | Render or inspect the dependency map across documents and code. |
| `cf-workspace: ...` | Configure or work across multiple repositories. |
| `cf-kit: ...` | Create, validate, or update kit configuration. |
| `cf-debug-prompts: ...` | Step through skill or workflow behavior while debugging instructions. |
| `cf-brave-new-world` | Let Studio choose safe, reversible workflow defaults during a session. |

Software Development Life Cycle (SDLC) kit skills from [`constructorfabric/studio-kit-sdlc`](https://github.com/constructorfabric/studio-kit-sdlc):

| Skill | Use |
|---|---|
| `cf-sdlc-doc-prd: ...` | Write or revise a Product Requirements Document. |
| `cf-sdlc-doc-adr: ...` | Record an Architecture Decision Record. |
| `cf-sdlc-doc-design: ...` | Write or revise a DESIGN document. |
| `cf-sdlc-decompose: ...` | Break a design into ordered feature work. |
| `cf-sdlc-doc-feature: ...` | Write or revise a FEATURE specification. |
| `cf-sdlc-implement: ...` | Implement an approved FEATURE in code with traceability. |
| `cf-sdlc-change-impact-analysis: ...` | Analyze downstream impact from changed artifacts or code. |
| `cf-sdlc-reverse-engineer: ...` | Reconstruct SDLC artifacts from existing code and markers. |
| `cf-sdlc-migrate-openspec: ...` | Convert OpenSpec material into Constructor Studio SDLC artifacts. |
| `cf-sdlc-pr-review: ...` | Review a pull request against project and SDLC expectations. |
| `cf-sdlc-pr-status: ...` | Summarize pull request state, checks, and unresolved review work. |

## Roadmap

Implemented:

- [x] Repository-local `cfs` command-line interface.
- [x] Minimal repository footprint with generated Studio and agent integration files ignored by git by default.
- [x] AI coding tool integration generation.
- [x] Concrete `cf-*` skill routing instead of generic prompts.
- [x] Sub-agent driven workflows where the AI coding tool supports sub-agents.
- [x] Core skills for help, exploration, brainstorming, planning, coding, documentation, skill authoring, explanation, maps, kits, workspaces, and prompt debugging.
- [x] Software Development Life Cycle (SDLC) kit with Product Requirements Document, Architecture Decision Record, DESIGN, DECOMPOSITION, FEATURE, implementation, impact analysis, reverse engineering, OpenSpec migration, pull request review, and pull request status skills.
- [x] Customizable templates, rules, checklists, artifact formats, and skill behavior.
- [x] Canonical Provenance Trace ID (CPT ID) traceability across documents, code, tests, and reviews.
- [x] Deterministic validation for configured artifacts, structure, references, language policy, and guide tables of contents.
- [x] Dependency map across documents and code.
- [x] Multi-repository workspace support.
- [x] Kit installation from GitHub, generic Git sources, and local paths.
- [x] Mirror overrides for replacing official source locations with forks or internal mirrors.

Planned:

- [ ] Official and custom kit store: publish, register, discover, and distribute organization-specific kits.
- [ ] Dependency manager for kits when the kit store is available.
- [ ] Package distribution through Homebrew, Python Package Index (PyPI), and Scoop.
- [ ] Template-based, extensible prompts generated by the `cfs` tool.
- [ ] Visual Studio Code plugin for configuration, document visualization, kit management, and validation.
- [ ] Web application and hosted service with tight [Cyber Wiki](https://github.com/constructorfabric/cyber-wiki) integration for document and code visualization, pull request work, configuration, team collaboration, and chat with skills.
- [ ] Global installation at the operating system level. Today Constructor Studio is installed per repository or workspace.
- [ ] Deterministic workflows with tight [Kitsoki](https://github.com/constructorfabric/Kitsoki) integration.

## References

- [Usage guide](guides/USAGE-GUIDE.md) - first moves, skill selection, prompt patterns, workspaces, delegation, and common mistakes
- [Installation and setup reference](guides/USAGE-GUIDE.md#2-installation-and-setup-reference)
- [Configuration guide](guides/CONFIGURATION.md) - artifacts, CPT IDs, templates, checklists, validation, kits, and dependency maps
- [Kit management](guides/CONFIGURATION.md#8-kit-management)
- [Dependency map](guides/USAGE-GUIDE.md#17-dependency-map-cfs-map--cf-map)
- [AI agent tools guide](guides/AGENT-TOOLS.md) - Claude Code, Cursor, Codex, Copilot, Windsurf, and host tradeoffs
- [Project extensibility guide](guides/PROJECT-EXTENSIBILITY.md) - organization-level composition and multi-repository patterns
- [Migration from Cypilot](guides/MIGRATING-FROM-CYPILOT.md)

## Feedback

Feedback, bug reports, use cases, and documentation fixes are welcome. Open an issue or discussion in the repository when something is unclear, broken, or missing.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for local development, validation, and contribution rules.

## License

Constructor Studio is licensed under the [Apache License 2.0](LICENSE).
