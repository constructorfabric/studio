# Project-Level Extensibility Guide


<!-- toc -->

- [1. What This Guide Is For](#1-what-this-guide-is-for)
- [2. The Current Model](#2-the-current-model)
- [3. Register a Local Kit](#3-register-a-local-kit)
- [4. Recommended Local Kit Layout](#4-recommended-local-kit-layout)
- [5. What Belongs in a Project Kit](#5-what-belongs-in-a-project-kit)
- [6. Register Mode vs Copy Mode](#6-register-mode-vs-copy-mode)
- [7. Multi-Repository Projects](#7-multi-repository-projects)
- [8. Updating and Validating](#8-updating-and-validating)
- [9. Migrating from Old Manifest-Based Extensibility](#9-migrating-from-old-manifest-based-extensibility)
- [Further Reading](#further-reading)

<!-- /toc -->

This guide explains how to extend Constructor Studio for one project or organization.

> **Convention**: 🖥 = run in a terminal. 💬 = paste into your artificial intelligence (AI) coding tool chat.

## 1. What This Guide Is For

Use project-level extensibility when the default Constructor Studio setup is not enough for your repository or organization.

Typical reasons:

- your team needs project-specific skills, templates, rules, or review checklists
- your organization wants the same delivery process across many repositories
- product, architecture, quality, security, operations, and development teams need shared artifact formats
- the built-in Software Development Life Cycle (SDLC) kit is a good starting point, but your organization needs stricter rules or different document structure

The current recommended mechanism is a **local kit registered in place**.

## 2. The Current Model

Project-level extensibility is now kit-based.

Instead of declaring project skills and agents through a standalone project `manifest.toml`, put those resources into a local kit and register it:

🖥 Register a local kit in place:

```bash
cfs kit install --path <path> --install-mode register
```

Register mode keeps the kit files where they already live in the project. Constructor Studio records the effective resource bindings in `core.toml`, then `cfs generate-agents`, `cfs validate`, and skill routing can use them.

This gives you one clear unit of extension:

- the kit contains your project or organization rules
- the repository keeps the kit source visible in git
- generated Studio runtime files and generated AI tool files stay repairable and ignored by git by default
- reviewers can inspect the kit changes like any other project change

## 3. Register a Local Kit

Put the kit under the project root. A common path is `kits/<kit-name>/`.

🖥 Preview or normalize the kit first:

```bash
cfs kit normalize ./kits/company-sdlc
```

🖥 Register the kit in place:

```bash
cfs kit install --path ./kits/company-sdlc --install-mode register
```

🖥 Regenerate AI coding tool integration files:

```bash
cfs generate-agents
```

🖥 Validate the kit configuration:

```bash
cfs validate-kits
```

🖥 Validate the repository:

```bash
cfs validate
```

Register mode requires the local kit path to stay inside the project root after symlink resolution. This prevents a project from silently depending on arbitrary files elsewhere on the machine.

## 4. Recommended Local Kit Layout

A small project kit can look like this:

```text
kits/company-sdlc/
├── .cf-studio-kit.toml
├── skills/
│   └── company-review/SKILL.md
├── rules/
│   ├── architecture.md
│   ├── security.md
│   └── testing.md
├── templates/
│   ├── PRD.md
│   ├── ADR.md
│   ├── DESIGN.md
│   └── FEATURE.md
├── checklists/
│   ├── design-review.md
│   ├── code-review.md
│   └── release-readiness.md
└── constraints/
    └── FEATURE/constraints.toml
```

Use names that match the organization vocabulary. For example, a security-heavy company may have `threat-model.md`, `data-handling.md`, and `security-review.md`; a platform team may have service templates and deployment checklists.

## 5. What Belongs in a Project Kit

Good kit contents:

- document templates for Product Requirements Documents, Architecture Decision Records, DESIGN documents, FEATURE specifications, and release documents
- rules for architecture, security, testing, performance, observability, operations, and code style
- review checklists for product, architecture, code, quality assurance, security, performance, and deployment readiness
- constraints for required headings, identifiers, cross-references, and Canonical Provenance Trace ID (CPT ID) structure
- skills for project-specific workflows, review behavior, or domain knowledge
- workflow resources that change how a skill gathers context, asks questions, writes files, or validates output
- scripts that support deterministic checks or repeatable project tasks

Do not put generated runtime files in a kit. Generated Studio files and generated AI coding tool integration files should remain repairable outputs.

When a kit provides workflow resources, treat shared Studio gates as part of the contract. Context discovery should flow through the workflow-prep gate, brainstorming should remain an explicit choice, plan-first should run before substantive multi-step work, and review fixes should go through the findings browser and fix-scope approval. Project kits can add domain-specific prompts and checks around those gates, but should not silently bypass them.

## 6. Register Mode vs Copy Mode

Use register mode when the kit is part of the project or workspace and should remain editable in place.

🖥 Register local kit resources in place:

```bash
cfs kit install --path ./kits/company-sdlc --install-mode register
```

Use copy mode when you want to copy local kit resources into the Constructor Studio setup directory.

🖥 Copy local kit resources:

```bash
cfs kit install --path ./kits/company-sdlc --install-mode copy
```

Use a Git or GitHub kit when the kit is published and reused across repositories.

🖥 Install a GitHub kit:

```bash
cfs kit install <owner/repo[@ref]>
```

🖥 Install a kit from a generic Git source:

```bash
cfs kit install git/<url>[//<subdir>][@<kit>] --version <ref>
```

For project-level extensibility, prefer `--install-mode register` unless you have a clear reason to copy the files into the setup directory.

## 7. Multi-Repository Projects

For multi-repository work, keep the extension point explicit.

Common pattern:

- one documentation or architecture repository owns Product Requirements Documents, Architecture Decision Records, DESIGN documents, and shared kits
- one user interface repository owns frontend code
- one backend repository or several service repositories own implementation code
- a workspace connects those repositories for validation, maps, and cross-repository traceability

Use workspace commands for the repository graph:

🖥 Create a workspace:

```bash
cfs workspace-init
```

🖥 Add a documentation repository:

```bash
cfs workspace-add --name docs --path ../docs-repo --role artifacts
```

🖥 Add a service repository:

```bash
cfs workspace-add --name services --path ../services-repo --role codebase
```

Use a registered local kit when the kit source lives inside the main project or workspace repository:

🖥 Register the shared local kit:

```bash
cfs kit install --path ./kits/company-sdlc --install-mode register
```

If each repository needs its own generated AI tool files, run `cfs generate-agents` in each repository after the kit or workspace configuration changes.

## 8. Updating and Validating

After changing a registered local kit, regenerate and validate.

🖥 Regenerate AI coding tool files:

```bash
cfs generate-agents
```

🖥 Validate kits:

```bash
cfs validate-kits
```

🖥 Validate project artifacts and traceability:

```bash
cfs validate
```

🖥 Render the dependency map:

```bash
cfs map
```

Registered local kits are normal project files. Review them in pull requests, run deterministic checks in continuous integration, and keep changes small enough that product, architecture, quality, security, operations, and development reviewers can understand what changed.

For workflow or review changes, include one manual chat dry run in addition to deterministic checks. Confirm that the route captures the target before discovery, offers optional explore/brainstorm when appropriate, asks for a plan on multi-step work, and shows review findings before any fix approval. These are user-facing behavior checks, not just file-format checks.

## 9. Migrating from Old Manifest-Based Extensibility

Older project-level extensibility designs used project `manifest.toml` files, include chains, and orchestrator-layer discovery as the main mechanism for custom skills, agents, workflows, and rules.

Use the kit model instead:

1. Move project-specific skills, rules, templates, checklists, constraints, scripts, and workflow resources into a local kit directory.
2. Add or normalize the kit manifest.
3. Register the kit in place.
4. Regenerate AI coding tool files.
5. Validate the kit and repository.

🖥 Register the migrated kit:

```bash
cfs kit install --path ./kits/company-sdlc --install-mode register
```

🖥 Regenerate integration files:

```bash
cfs generate-agents
```

The old manifest hierarchy should not be the first choice for new project-level extension work. Kits provide a clearer review boundary and match the installation, update, validation, and distribution model used by Constructor Studio.

## Further Reading

- [Configuration guide](CONFIGURATION.md) - kit management, artifacts, templates, rules, checklists, constraints, and validation
- [Usage guide](USAGE-GUIDE.md) - workflow selection, workspaces, dependency map, and practical operating guidance
- [Constructor Studio README](../README.md)
