---
studio: true
type: spec
name: Project Rules and Root Navigation Specification
version: 2.0
purpose: Define the project-owned prompt-asset surfaces under {cf-studio-path}/config/, the managed root navigation blocks, and the read vs repair lifecycle observed by the CLI
drivers:
  - cpt-studio-fr-core-config
  - cpt-studio-fr-core-workflows
  - cpt-studio-fr-core-init
  - cpt-studio-fr-core-agents
---

# Project Rules and Root Navigation Specification

<!-- toc -->

- [Overview](#overview)
- [Runtime Contract](#runtime-contract)
- [Project-Owned Prompt Assets](#project-owned-prompt-assets)
- [Root Managed Blocks](#root-managed-blocks)
- [Read vs Repair Lifecycle](#read-vs-repair-lifecycle)
- [config/AGENTS.md](#configagentsmd)
- [Rule Files](#rule-files)
- [Validation and Error Handling](#validation-and-error-handling)
- [References](#references)

<!-- /toc -->

## Overview

This spec defines the current project-extension model used by Constructor
Studio.

The legacy `config/sysprompts/` model is obsolete for this repository's
documented runtime. Project-owned instruction assets now live primarily in:

- `{cf-studio-path}/config/AGENTS.md`
- `{cf-studio-path}/config/rules/*.md`
- `{cf-studio-path}/config/SKILL.md`

`config/AGENTS.md` declares action-scoped `ALWAYS open and follow ... WHEN ...`
rules. Those rules point at project rule files and selected architecture or
contributor docs. Root `AGENTS.md` and `CLAUDE.md` contain only the managed
`cf-studio-path` handoff block and are not general-purpose prompt bundles.

## Runtime Contract

```pdsl
UNIT ProjectRuleClassification

PURPOSE:
  Define project-owned prompt assets as controller-loaded instruction surfaces.

DO:
  - LOAD {cf-studio-path}/.core/architecture/specs/shared-context-pack.md
  - CONTINUE SharedContextPackLifecycle

RULES:
  - ALWAYS treat `{cf-studio-path}/config/AGENTS.md`,
    `{cf-studio-path}/config/rules/*.md`, and selected project docs referenced
    from AGENTS rules as the project prompt-asset family
  - ALWAYS record those assets with `origin = "project"` when loaded into
    `SHARED_CONTEXT_PACK`
```

```pdsl
UNIT ProjectRuleLoading

PURPOSE:
  Make project-rule selection explicit and controller-owned.

DO:
  - REQUIRE operation context is resolved
  - REQUIRE controller reads `{cf-studio-path}/config/AGENTS.md`
  - REQUIRE controller evaluates action-based `WHEN` rules in declaration order
  - REQUIRE controller loads the referenced rule or doc files for matching rules
  - REQUIRE controller publishes matched instruction text into `SHARED_CONTEXT_PACK`

RULES:
  - ALWAYS keep controller-owned prompt loading separate from target task files
  - ALWAYS load only the rule and doc assets relevant to the active operation
  - NEVER allow prompt-consuming sub-agents to reopen those prompt files directly
```

## Project-Owned Prompt Assets

```text
{cf-studio-path}/
  config/
    AGENTS.md                # Project navigation rules
    SKILL.md                 # Project skill extensions
    core.toml
    artifacts.toml
    rules/
      tech-stack.md
      conventions.md
      project-structure.md
      domain-model.md
      testing.md
      build-deploy.md
      architecture.md
      patterns.md
      anti-patterns.md
      ...
```

Typical division of responsibility:

| Concern | Location |
|---------|----------|
| Project-level action routing | `{cf-studio-path}/config/AGENTS.md` |
| Topic-focused project guidance | `{cf-studio-path}/config/rules/*.md` |
| Project-specific skill extensions | `{cf-studio-path}/config/SKILL.md` |
| Artifact structure and validation rules | kit files under `config/kits/<slug>/` |

## Root Managed Blocks

Constructor Studio injects a managed block into project-root `AGENTS.md` and
`CLAUDE.md`:

````markdown
<!-- @cf:root-agents -->
```toml
cf-studio-path = ".bootstrap"
```
<!-- /@cf:root-agents -->
````

Rules:

- The managed payload is only the TOML fence declaring `cf-studio-path`.
- The block is inserted at the beginning of the file.
- Missing root files may be created by setup or migration flows.
- Manual edits inside the managed markers are discarded when a setup or repair
  flow rewrites the block.
- Project-skill routing reads this block; ordinary read-only commands do not
  silently rewrite it.

## Read vs Repair Lifecycle

Observed CLI behavior splits cleanly into two modes.

**Read-only / inspect flows**

- `cfs info`
- `cfs agents`
- `cfs validate-toc`
- ordinary project-skill routing

These commands read root metadata and project config but are expected to leave
the filesystem unchanged when no explicit write action was requested.

**Repair / write flows**

- `cfs init`
- repeat `cfs init` repair mode
- `cfs update`
- legacy migration flows

These flows may refresh or recreate:

- root `AGENTS.md` managed block
- root `CLAUDE.md` managed block
- `{cf-studio-path}/.core/`
- `{cf-studio-path}/.gen/AGENTS.md`
- managed `.gitignore` block
- generated agent integration outputs

The architecture contract is therefore:

- root managed blocks are refreshed by explicit setup/repair commands
- root managed blocks are not silently repaired by unrelated read-only commands

## config/AGENTS.md

`{cf-studio-path}/config/AGENTS.md` is the project navigation file. It declares
which rule or doc files the controller should load for a given activity.

Example:

```markdown
# Constructor Studio Adapter: Constructor Studio

ALWAYS open and follow `{cf-studio-path}/config/rules/tech-stack.md` WHEN writing code, choosing technologies, or adding dependencies
ALWAYS open and follow `{cf-studio-path}/config/rules/conventions.md` WHEN writing code, naming files/functions/variables, or reviewing code
ALWAYS open and follow `{cf-studio-path}/config/rules/architecture.md` WHEN modifying architecture, adding components, or refactoring module boundaries
ALWAYS open and follow `CONTRIBUTING.md#making-changes` WHEN making code changes, architecture changes, or kit blueprint changes
```

Requirements:

- Rules must be action-based.
- Paths may target project rule files or other project docs.
- Declaration order matters for load order.
- Kit workflow entry points are not declared here; they are exposed through
  generated agent surfaces.

## Rule Files

Rule files are plain Markdown guidance documents under
`{cf-studio-path}/config/rules/`.

Recommended topics match the auto-config output model:

- `tech-stack.md`
- `conventions.md`
- `project-structure.md`
- `domain-model.md`
- `testing.md`
- `build-deploy.md`
- `architecture.md`
- `patterns.md`
- `anti-patterns.md`

These files are project-owned guidance, not generated runtime-only shims.

## Validation and Error Handling

Validation expectations:

- `{cf-studio-path}/config/AGENTS.md` must exist in initialized projects.
- Referenced `config/rules/*.md` files should exist for active project rules.
- Missing rule files are configuration defects, not permission for a sub-agent to
  read unrelated files directly.

Relevant observed error/read contracts:

- read-only commands such as `info` return `FOUND` / `NOT_FOUND` style statuses
  without mutating root files
- `agents` returns `OK`, `NOT_FOUND`, or `CONFIG_ERROR` and remains read-only
- setup/update flows own the responsibility for root-block repair

## References

- [cli.md](./cli.md)
- [shared-context-pack.md](./shared-context-pack.md)
- [kit/kit.md](./kit/kit.md)
- [../DESIGN.md](../DESIGN.md)
