# Constructor Studio Adapter: Constructor Studio

**Version**: 3.0

---

## Project Overview

Constructor Studio is a workflow-centered methodology framework for AI-assisted software development with design-to-code traceability. This adapter configures Constructor Studio for the Constructor Studio framework itself (self-hosted).

---

## Navigation Rules

### Schema & Registry

ALWAYS open and follow `{cf-studio-path}/.core/schemas/artifacts.schema.json` WHEN working with artifacts.toml

ALWAYS open and follow `{cf-studio-path}/.core/requirements/artifacts-registry.md` WHEN working with artifacts.toml

### Project Rules

ALWAYS open and follow `{cf-studio-path}/config/rules/tech-stack.md` WHEN writing code, choosing technologies, or adding dependencies

ALWAYS open and follow `{cf-studio-path}/config/rules/conventions.md` WHEN writing code, naming files/functions/variables, or reviewing code

ALWAYS open and follow `{cf-studio-path}/config/rules/project-structure.md` WHEN creating files, adding modules, or navigating codebase

ALWAYS open and follow `{cf-studio-path}/config/rules/domain-model.md` WHEN working with entities, data structures, or business logic

ALWAYS open and follow `{cf-studio-path}/config/rules/testing.md` WHEN writing tests, reviewing test coverage, or debugging

ALWAYS open and follow `{cf-studio-path}/config/rules/build-deploy.md` WHEN building, deploying, or configuring CI/CD

ALWAYS open and follow `{cf-studio-path}/config/rules/architecture.md` WHEN modifying architecture, adding components, or refactoring module boundaries

ALWAYS open and follow `{cf-studio-path}/config/rules/patterns.md` WHEN implementing features or writing business logic

ALWAYS open and follow `{cf-studio-path}/config/rules/anti-patterns.md` WHEN reviewing code or refactoring

---

## Development Rules

NEVER edit files inside `{cf-studio-path}/.core/` or `{cf-studio-path}/.gen/` directly — they are read-only copies. ALWAYS edit the canonical source files under project root (`skills/`, `kits/`, `schemas/`, etc.) and then run `cfs update --source . --force` to sync changes into `{cf-studio-path}/`.

### Specs-First Development Workflow

ALWAYS update specs and documentation in `architecture/` FIRST BEFORE writing any code.

**Mandatory sequence for any code change**:

1. **Update specs** — modify or create relevant artifacts in `architecture/`:
   - `architecture/PRD.md` — for new requirements or use cases
   - `architecture/DESIGN.md` — for architectural changes or new components
   - `architecture/DECOMPOSITION.md` — for new features or work breakdown
   - `architecture/features/*.md` — for feature-level specs
   - `architecture/specs/*.md` — for technical specs (CDSL, CLISPEC, etc.)
   - `architecture/ADR/*.md` — for architecture decisions

2. **Validate specs** — run `cfs validate` to ensure artifact integrity

3. **Generate code via Constructor Studio** — use `/cf-generate` workflow to implement code from specs with traceability markers

NEVER write code directly without first updating the corresponding specs. This ensures design-to-code traceability and prevents implementation drift from design intent.

---

## Project Documentation (auto-configured)

<!-- auto-config:docs:start -->

ALWAYS open and follow `architecture/specs/CLISPEC.md` WHEN writing CLI commands, modifying command dispatch, or adding new subcommands

ALWAYS open and follow `CONTRIBUTING.md#development-setup` WHEN setting up development environment or onboarding

ALWAYS open and follow `CONTRIBUTING.md#project-architecture-self-hosted-bootstrap` WHEN editing bootstrap files or understanding the .bootstrap/ directory structure

ALWAYS open and follow `CONTRIBUTING.md#versioning` WHEN bumping versions, releasing, or tagging

ALWAYS open and follow `CONTRIBUTING.md#commit-requirements-dco` WHEN committing code or preparing commits

ALWAYS open and follow `CONTRIBUTING.md#running-ci-locally` WHEN running CI checks locally via act or debugging CI failures

ALWAYS open and follow `CONTRIBUTING.md#makefile-targets` WHEN looking up available make commands

ALWAYS open and follow `CONTRIBUTING.md#github-actions` WHEN modifying CI workflow or understanding CI jobs

ALWAYS open and follow `CONTRIBUTING.md#making-changes` WHEN making code changes, architecture changes, or kit blueprint changes

ALWAYS open and follow `CONTRIBUTING.md#pull-request-process` WHEN creating or reviewing pull requests

ALWAYS open and follow `CONTRIBUTING.md#code-style-and-conventions` WHEN writing or reviewing code

<!-- auto-config:docs:end -->
