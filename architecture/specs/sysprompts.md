---
studio: true
type: spec
name: Project Extension Specification
version: 1.0
purpose: Define how projects extend Constructor Studio behavior through {cf-studio-path}/config/sysprompts and config/AGENTS.md with operation-scoped system prompts
drivers:
  - cpt-studio-fr-core-config
  - cpt-studio-fr-core-workflows
---

# Project Extension Specification


<!-- toc -->

- [Overview](#overview)
- [Runtime Contract](#runtime-contract)
- [Extension Directory](#extension-directory)
- [Root AGENTS.md Entry](#root-agentsmd-entry)
- [config/AGENTS.md](#configagentsmd)
  - [Required Structure](#required-structure)
  - [WHEN Rule Format](#when-rule-format)
- [System Prompt Files](#system-prompt-files)
  - [Format](#format)
  - [Standard System Prompts](#standard-system-prompts)
  - [Content Principles](#content-principles)
- [System Prompt Loading](#system-prompt-loading)
  - [When Prompts Are Loaded](#when-prompts-are-loaded)
  - [Loading Algorithm](#loading-algorithm)
  - [Interaction with Kit Prompts](#interaction-with-kit-prompts)
- [System Prompt Discovery](#system-prompt-discovery)
- [Validation](#validation)
  - [AGENTS.md Validation](#agentsmd-validation)
  - [System Prompt File Validation](#system-prompt-file-validation)
- [Error Handling](#error-handling)
  - [System Prompt Not Found](#system-prompt-not-found)
  - [AGENTS.md Not Found](#agentsmd-not-found)
  - [Invalid WHEN Format](#invalid-when-format)
- [Example](#example)
- [References](#references)

<!-- /toc -->

---
---

## Overview

Projects extend Constructor Studio behavior by placing **system prompts** in `{cf-studio-path}/config/sysprompts/` and registering them via `{cf-studio-path}/config/AGENTS.md`. These prompts are loaded by workflows during generate, analyze, and code operations, providing project-specific context without modifying kit files or core configuration.

**Key properties**:
- System prompts live in `{cf-studio-path}/config/sysprompts/*.md` — plain Markdown files
- `AGENTS.md` at `{cf-studio-path}/config/AGENTS.md` maps prompts to operations via `WHEN` rules
- Prompts are loaded at runtime — no code generation, no build step
- Project-specific: conventions, tech stack, domain model, patterns, etc.
- Complementary to kit files: kit rules define artifact structure, project system prompts define project context

## Runtime Contract

```text
UNIT SyspromptClassification

PURPOSE:
  Define project sysprompt surfaces as prompt assets with controller-owned
  loading authority.

RULES:
  - `{cf-studio-path}/config/AGENTS.md` and
    `{cf-studio-path}/config/sysprompts/*.md` are prompt assets when used as
    operating instructions
  - A dispatching controller MAY load those prompt assets from disk
  - When loaded into `SHARED_CONTEXT_PACK`, those assets MUST be recorded with
    `origin = "project"`
  - Prompt-consuming sub-agents MUST receive the selected prompt text through
    the controller-synthesized final dispatch prompt
  - Prompt-consuming sub-agents MUST_NOT reopen project sysprompt files
    directly from disk
```

```text
UNIT SyspromptLoading

PURPOSE:
  Make project sysprompt selection explicit and shared-context-pack aware.

DO:
  REQUIRE operation context is resolved
  REQUIRE controller reads `{cf-studio-path}/config/AGENTS.md`
  REQUIRE controller evaluates action-based `WHEN` rules against the current context
  REQUIRE controller loads matching system prompt files in declaration order
  REQUIRE controller publishes matched prompt text into `SHARED_CONTEXT_PACK`
  REQUIRE controller synthesizes a final dispatch prompt for any
    prompt-consuming sub-agent dispatch

RULES:
  - MUST keep kit prompts and project sysprompts separate prompt-asset families
  - MUST load only the prompt assets required by the active operation
  - MUST treat missing required prompt context as a controller error rather than
    a license for direct file reads
```

```text
UNIT SyspromptValidationAndErrors

PURPOSE:
  Define deterministic validation and warning behavior for project sysprompts.

ON_ERROR:
  orphaned_when_rule ->
    EMIT "Orphaned WHEN rule: sysprompts/{name}.md not found"
    CONTINUE without that rule

  missing_project_agents ->
    EMIT "Project AGENTS.md not found: {cf-studio-path}/config/AGENTS.md"
    CONTINUE with kit-level prompts only

  invalid_when_rule ->
    EMIT "Invalid WHEN rule format in AGENTS.md"
    CONTINUE after skipping the invalid rule
```

**What goes here vs. in kit files**:

| Concern | Location |
|---------|----------|
| Artifact structure, ID kinds, heading rules | Kit files (`rules.md`, `constraints.toml`, `template.md`) |
| Project tech stack, naming conventions | `{cf-studio-path}/config/sysprompts/tech-stack.md` |
| Domain model, entity relationships | `{cf-studio-path}/config/sysprompts/domain-model.md` |
| API contract format | `{cf-studio-path}/config/sysprompts/api-contracts.md` |

---

## Extension Directory

```
{cf-studio-path}/             # Install directory (default: .cf/)
└── config/
    ├── AGENTS.md              # Navigation rules (WHEN → spec file)
    ├── core.toml              # Core config
    ├── artifacts.toml         # Artifact registry
    └── sysprompts/            # Project-specific system prompts
        ├── tech-stack.md
        ├── conventions.md
        ├── domain-model.md
        ├── patterns.md
        ├── testing.md
        └── ...
```

All sysprompt files are optional. Only files referenced in `AGENTS.md` are loaded.

---

## Root AGENTS.md Entry

Constructor Studio injects the same managed block into the **project root** `AGENTS.md` and `CLAUDE.md`, exposing only the configured install path:

````markdown
<!-- @cf:root-agents -->
```toml
cf-path = ".cf"
```
<!-- /@cf:root-agents -->
````

**Behavior**:
- Inserted at the **beginning** of the root `AGENTS.md` and `CLAUDE.md` files
- If a file does not exist, it is created
- The path reflects the actual install directory via `cf-path`
- Content between the `<!-- @cf:root-agents -->` and `<!-- /@cf:root-agents -->` markers is **fully managed** by Constructor Studio — overwritten on every check
- Manual edits inside the block are discarded

**Integrity check**: every Constructor Studio CLI invocation (not just `init`) verifies both blocks exist and the path is correct. If a block is missing or stale, it is silently re-injected. This ensures any agent that opens the project is immediately routed to Constructor Studio's navigation entry point.

---

## config/AGENTS.md

**Location**: `{cf-studio-path}/config/AGENTS.md`

`{cf-studio-path}/config/AGENTS.md` is the project-level navigation file. It declares which system prompts to load for which operations. Agents reach this file via the root `AGENTS.md` entry above.

Kit workflow commands are **not** placed here — they are exposed via agent entry points (e.g., `.windsurf/workflows/cf-*.md`) generated from kit workflow files (see [kit.md](kit/kit.md)).

### Required Structure

```markdown
# Constructor Studio: {Project Name}

ALWAYS open and follow `{cf-studio-path}/config/sysprompts/tech-stack.md` WHEN writing code, choosing technologies, or adding dependencies
ALWAYS open and follow `{cf-studio-path}/config/sysprompts/conventions.md` WHEN writing code, naming files/functions/variables, or reviewing code
ALWAYS open and follow `{cf-studio-path}/config/sysprompts/domain-model.md` WHEN working with entities, data structures, or business logic
ALWAYS open and follow `{cf-studio-path}/config/sysprompts/testing.md` WHEN writing tests, reviewing test coverage, or debugging
```

### WHEN Rule Format

```
ALWAYS open and follow `{sysprompt-path}` WHEN {action-description}
```

- `{sysprompt-path}` — relative to `{cf-studio-path}/config/` (e.g., `sysprompts/tech-stack.md`)
- `{action-description}` — action-based description of WHEN to load the system prompt

**Rules MUST be action-based** — they describe what the agent is doing, not which artifact kind is active:

| Correct | Incorrect |
|---------|-----------|
| `WHEN writing code, choosing technologies` | `WHEN generating DESIGN` |
| `WHEN working with entities, data structures` | `WHEN Constructor Studio uses kit sdlc` |
| `WHEN writing tests, reviewing coverage` | `WHEN working on project` |

---

## System Prompt Files

System prompt files are plain Markdown documents in `{cf-studio-path}/config/sysprompts/`. Each file provides project-specific context that agents load during operations.

### Format

```markdown
# {Spec Name}

## Overview
{Brief description of what this spec covers and why it matters}

## {Content Sections}
{Domain-specific directives, constraints, and examples}

---
**Source**: {Where this knowledge was discovered — DESIGN.md, ADRs, codebase, etc.}
**Last Updated**: {Date}
```

### Standard System Prompts

| System Prompt | WHEN Rule | Contains |
|-----------|-----------|----------|
| `tech-stack.md` | writing code, choosing technologies, adding dependencies | Languages, frameworks, databases, infrastructure constraints |
| `conventions.md` | writing code, naming files/functions/variables, reviewing code | Naming conventions, code style, file organization |
| `project-structure.md` | creating files, adding modules, navigating codebase | Directory layout, module organization, entry points |
| `domain-model.md` | working with entities, data structures, business logic | Core concepts, entity relationships, invariants |
| `testing.md` | writing tests, reviewing test coverage, debugging | Test frameworks, patterns, coverage requirements |
| `patterns.md` | implementing features, designing components, refactoring | Architecture patterns, design patterns, state management |
| `api-contracts.md` | creating/consuming APIs, defining endpoints, handling requests | Contract format, endpoint patterns, protocols |
| `build-deploy.md` | building, deploying, configuring CI/CD | Build commands, CI/CD pipeline, deployment procedures |
| `security.md` | handling authentication, authorization, sensitive data | Auth mechanisms, data classification, encryption |
| `performance.md` | optimizing, caching, working with high-load components | SLAs, caching strategy, optimization patterns |
| `reliability.md` | handling errors, implementing retries, adding health checks | Error handling, recovery, circuit breakers |

Not all system prompts apply to all projects. Create only what is relevant.

### Content Principles

- **Actionable**: not just descriptions, but what to do
- **Project-specific**: conventions that differ from kit defaults
- **Source-referenced**: note where knowledge came from (DESIGN.md, ADRs, codebase)
- **No artifact content**: no PRD requirements, no ADR rationale — those belong in artifacts

---

## System Prompt Loading

### When Prompts Are Loaded

Workflows load project system prompts at specific points:

| Operation | Loaded System Prompts (via WHEN matching) |
|-----------|-------------------------------------------|
| `cf generate PRD` | Prompts matching "working with entities", "writing requirements" |
| `cf generate DESIGN` | Prompts matching "designing components", "choosing technologies" |
| `{cfs_cmd} validate` | Prompts matching relevant artifact content |
| Code generation/review | `tech-stack.md`, `conventions.md`, `patterns.md` |

### Loading Algorithm

1. Determine current operation context (generate, analyze, code, etc.)
2. Read `{cf-studio-path}/config/AGENTS.md`
3. For each `WHEN` rule, match the action description against current context
4. Load matching system prompt files in declaration order
5. Publish matching prompt text into `SHARED_CONTEXT_PACK` as `origin = "project"` assets
6. Synthesize the final dispatch prompt for any prompt-consuming sub-agent

### Interaction with Kit Prompts

Project system prompts are **additive** — they don't replace kit-level prompts. Loading order:

1. Kit rules and prompts (from `rules.md`, `SKILL.md`) — artifact-kind-level directives
2. Project `{cf-studio-path}/config/sysprompts/*.md` (from AGENTS.md WHEN rules) — project-level context

If a project system prompt contradicts a kit prompt, the project system prompt takes precedence (project-specific overrides generic).

Prompt-consuming sub-agents receive the relevant project context through the
controller-synthesized final dispatch prompt; they MUST NOT reopen project
sysprompt files directly.

---

## System Prompt Discovery

For existing projects, Constructor Studio can auto-discover system prompt candidates:

```bash
{cfs_cmd} init --discover
```

**Discovery process**:
1. Scan project for signals (config files, package manifests, CI configs, test directories)
2. Propose system prompt files based on findings
3. Generate draft system prompts with discovered information
4. User reviews and confirms

**Discovery signals**:

| Signal | Produces |
|--------|----------|
| `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml` | `tech-stack.md` |
| `.eslintrc`, `.prettierrc`, `ruff.toml`, `.editorconfig` | `conventions.md` |
| Test directories, `pytest.ini`, `jest.config.js` | `testing.md` |
| `Makefile`, `.github/workflows/`, `Dockerfile` | `build-deploy.md` |
| `openapi.yml`, `*.proto` | `api-contracts.md` |
| Schema/model directories, DESIGN.md domain section | `domain-model.md` |
| Auth middleware, security configs | `security.md` |

---

## Validation

### AGENTS.md Validation

| # | Check | Required | How to Verify |
|---|-------|----------|---------------|
| A.1 | `{cf-studio-path}/config/AGENTS.md` exists | YES | File exists |
| A.2 | Has project name heading | YES | `# Constructor Studio: {name}` present |
| A.3 | All WHEN rules use action-based format | YES | Pattern: `WHEN {verb}ing ...` |
| A.4 | No orphaned WHEN rules | YES | All referenced system prompt files exist |

### System Prompt File Validation

| # | Check | Required | How to Verify |
|---|-------|----------|---------------|
| S.1 | Has H1 heading | YES | `# {name}` present |
| S.2 | Has Overview section | YES | `## Overview` present |
| S.3 | Has Source reference | YES | `**Source**:` present |
| S.4 | No artifact content (PRD, ADR rationale) | YES | No requirement IDs, no decision rationale |
| S.5 | Content is actionable | YES | Contains directives, not just descriptions |

**Validation command**:
```bash
{cfs_cmd} validate --sysprompts
```

---

## Error Handling

### System Prompt Not Found

```
⚠️ Orphaned WHEN rule: sysprompts/{name}.md not found
→ Referenced in: {cf-studio-path}/config/AGENTS.md
→ Fix: Create the sysprompt file OR remove the WHEN rule
```
**Action**: WARN — workflow continues without the missing spec.

### AGENTS.md Not Found

```
⚠️ Project AGENTS.md not found: {cf-studio-path}/config/AGENTS.md
→ No project-level system prompts will be loaded
→ Fix: Run `cfs init` to create AGENTS.md
```
**Action**: WARN — workflows proceed with kit-level system prompts only.

### Invalid WHEN Format

```
⚠️ Invalid WHEN rule format in AGENTS.md
→ Line: "ALWAYS open and follow `specs/tech-stack.md` WHEN working on project"
→ Expected: action-based description (WHEN writing code, WHEN designing, etc.)
→ Fix: Use specific action verbs
```
**Action**: WARN — rule is skipped during loading.

---

## Example

A complete project extension for a TypeScript web application:

`{cf-studio-path}/config/AGENTS.md`:
```markdown
# Constructor Studio: MyApp

ALWAYS open and follow `{cf-studio-path}/config/sysprompts/tech-stack.md` WHEN writing code, choosing technologies, or adding dependencies
ALWAYS open and follow `{cf-studio-path}/config/sysprompts/conventions.md` WHEN writing code, naming files/functions/variables, or reviewing code
ALWAYS open and follow `{cf-studio-path}/config/sysprompts/domain-model.md` WHEN working with entities, data structures, or business logic
ALWAYS open and follow `{cf-studio-path}/config/sysprompts/testing.md` WHEN writing tests, reviewing test coverage, or debugging
ALWAYS open and follow `{cf-studio-path}/config/sysprompts/api-contracts.md` WHEN creating/consuming APIs, defining endpoints, or handling requests
```

`{cf-studio-path}/config/sysprompts/tech-stack.md`:
```markdown
# Tech Stack

## Overview
MyApp is a TypeScript monorepo using Next.js for the frontend and Fastify for the API.

## Languages
- **TypeScript** 5.x — all application code
- **SQL** — database migrations (raw SQL, no ORM)

## Frameworks
- **Next.js** 14 — frontend (App Router, Server Components)
- **Fastify** 4 — API server
- **Drizzle ORM** — database access

## Database
- **PostgreSQL** 16 — primary datastore
- **Redis** 7 — caching and sessions

## Infrastructure
- **Docker** — local development
- **Vercel** — frontend deployment
- **Fly.io** — API deployment

---
**Source**: DESIGN.md (Section 2.1 Technology Stack)
**Last Updated**: 2026-02-23
```

---

## References

- **Kit specification**: `specs/kit/kit.md` — kit structure, file reference, update model
- **Rules format**: `specs/kit/rules.md` — workflow entry point
- **CLI**: `specs/cli.md` — `init`, `agents`, `validate --sysprompts` commands
