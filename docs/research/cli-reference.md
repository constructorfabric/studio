# Constructor Studio v1.5.9 — CLI Reference

Constructor Studio ships a command-line tool called `cfs`. You invoke every feature as `cfs <command>`, optionally followed by flags. This reference covers all 30 commands available in v1.5.9, organized by the workflow stage they serve. The audience is product managers who need to understand what the tool can do, not how to implement it.

---

## Command Categories

| # | Category | Commands | Purpose |
|---|---|---|---|
| 1 | Setup & Configuration | `init`, `update`, `info`, `resolve-vars` | Bootstrap and maintain a Studio-enabled project |
| 2 | Agent Integrations | `agents`, `generate-agents` | Connect Studio to AI coding assistants (Claude, Cursor, Copilot, etc.) |
| 3 | Validation | `validate`, `validate-kits`, `validate-toc`, `spec-coverage`, `check-language` | Ensure structure, traceability, and content quality |
| 4 | Traceability Navigation | `list-ids`, `list-id-kinds`, `get-content`, `where-defined`, `where-used` | Explore and query CPT traceability IDs across a project |
| 5 | Kit Management | `kit install`, `kit update`, `kit normalize`, `kit check-updates` | Manage reusable skill/rule packages (kits) |
| 6 | Document Utilities | `toc`, `pdsl`, `chunk-input` | Author and process structured documents |
| 7 | Visualization | `map` | Build interactive dependency maps |
| 8 | Workspace Management | `workspace-init`, `workspace-add`, `workspace-info`, `workspace-sync` | Coordinate multi-repo workspaces |
| 9 | Delegation & Diagnostics | `delegate`, `doctor` | Remote execution and environment health |

---

## Command Reference

```text
COMMAND_GROUP Setup & Configuration
  PURPOSE: Bootstrap a new Studio project, keep it current, and inspect its active configuration.
  COMMANDS:
    COMMAND init
      USER_ACTION: Run once when adopting Studio in a repository; re-run with --force to reset. Preserves existing configuration fragments when re-running on an already-initialized project (use --force to replace).
      PRODUCES: Studio config directory scaffold (default: .cf-studio/; configurable via cf-studio-path in CLAUDE.md), core config files, gitignore entries; optionally migrates a legacy CyPilot project.
      OPTIONS: [--force (overwrite existing), --migrate-yes (auto-accept CyPilot migration), --from-dir <path> (seed from another directory)]

    COMMAND update
      USER_ACTION: Run after upgrading the Studio version or when .core/ assets need refreshing.
      PRODUCES: Replaces .core/ content from the local cache, regenerates .gen/ aggregate files; optionally refreshes installed kits.
      OPTIONS: [--with-kits yes (also update all kits), --dry-run (preview without writing)]

    COMMAND info
      USER_ACTION: Run to audit the current Studio setup or share config details in a support request.
      PRODUCES: Human-readable report of project root, studio directory, registered kits, and registry status.
      OPTIONS: [--json (machine-readable output)]

    COMMAND resolve-vars
      USER_ACTION: Run when a workflow needs guaranteed absolute file paths for template variable substitution.
      PRODUCES: Resolved paths printed to stdout; used internally by other workflows to avoid relative-path ambiguity.
      OPTIONS: []
```

```text
COMMAND_GROUP Agent Integrations
  PURPOSE: Generate and inspect integration files that let AI coding assistants (Claude, Cursor, Windsurf, Copilot, OpenAI) work with Studio conventions.
  COMMANDS:
    COMMAND agents
      USER_ACTION: Run to check which agent integration files exist and whether they are up to date.
      PRODUCES: Status report listing each supported agent (Windsurf, Cursor, Claude, Copilot, OpenAI) and the state of its integration file; read-only, no files are changed.
      OPTIONS: []

    COMMAND generate-agents
      USER_ACTION: Run after init or when onboarding a new AI assistant to the project.
      PRODUCES: Creates or updates IDE/agent integration files so each assistant can discover Studio rules and skills.
      OPTIONS: [--yes (skip confirmation prompts), --dry-run (preview changes without writing)]
```

```text
COMMAND_GROUP Validation
  PURPOSE: Verify that kit structures, artifact cross-references, CDSL markers, table of contents, and content language all meet project standards.
  COMMANDS:
    COMMAND validate
      USER_ACTION: Run as a CI gate or before a release to confirm the full traceability pipeline is healthy.
      PRODUCES: Sequenced report covering kit structure, artifact structure, cross-references, CDSL marker scan, coverage check, and optional language check; exits non-zero on failure.
      OPTIONS: [--artifact <id> (scope to one artifact), --source <path> (restrict source scope), --output <file> (write report to file), --local-only (skip remote lookups)]

    COMMAND validate-kits
      USER_ACTION: Run when a kit has been modified to confirm its internal structure is intact before sharing it.
      PRODUCES: Pass/fail report for each kit covering directory layout, conf.toml, constraints.toml, and manifest bindings.
      OPTIONS: [aliases: validate-rules, self-check]

    COMMAND validate-toc
      USER_ACTION: Run after editing Markdown documents to confirm the Table of Contents is still accurate.
      PRODUCES: Report listing any TOC entries whose anchors do not match headings, are missing, or are stale.
      OPTIONS: [--warn-only (non-zero exit only on errors, not warnings), --verbose (show all checked files)]

    COMMAND spec-coverage
      USER_ACTION: Run to measure how thoroughly the codebase is annotated with CDSL markers.
      PRODUCES: Per-file and aggregate coverage percentages plus granularity score; can enforce a minimum threshold.
      OPTIONS: [--min-coverage <0-100> (fail below threshold), --output <file> (write JSON report)]

    COMMAND check-language
      USER_ACTION: Run to detect characters from unexpected scripts in Markdown content (e.g., stray Cyrillic in an English document).
      PRODUCES: List of files and line numbers containing characters outside the allowed Unicode script set.
      OPTIONS: [--languages <list> (allowed script codes), --ignore <glob> (exclude paths), --quiet (suppress passing files)]
```

```text
COMMAND_GROUP Traceability Navigation
  PURPOSE: Explore, query, and retrieve content associated with CPT (Canonical Provenance Trace) IDs throughout a project.
  COMMANDS:
    COMMAND list-ids
      USER_ACTION: Run to get a full inventory of traceability IDs, or to find all IDs of a particular kind.
      PRODUCES: Grouped list of CPT IDs discovered across all artifact and code files.
      OPTIONS: [--kind <token> (filter by ID kind), --pattern <regex> (filter by pattern), --dedup (suppress duplicates)]

    COMMAND list-id-kinds
      USER_ACTION: Run to understand which ID taxonomies are in use in the project.
      PRODUCES: Table of all ID kind tokens with occurrence counts.
      OPTIONS: []

    COMMAND get-content
      USER_ACTION: Run to read the exact text block associated with a known Studio ID without opening the file manually.
      PRODUCES: Extracted text block for the requested ID from the relevant artifact or code file.
      OPTIONS: [--code (retrieve from source code rather than artifact), --inst (retrieve instruction variant)]

    COMMAND where-defined
      USER_ACTION: Run to locate where a specific Studio ID is declared.
      PRODUCES: File path(s) and line number(s) that contain the definition of the given ID.
      OPTIONS: []

    COMMAND where-used
      USER_ACTION: Run to understand the impact of changing a specific Studio ID — who references it.
      PRODUCES: List of all files and locations that reference the given ID.
      OPTIONS: []
```

```text
COMMAND_GROUP Kit Management
  PURPOSE: Install, update, and inspect reusable skill and rule packages (kits) within a Studio project.
  COMMANDS:
    COMMAND kit install
      USER_ACTION: Run to add a new kit to the project from a local path, a GitHub repository, or any Git URL.
      PRODUCES: Kit files placed under the project's kit directory; registered in Studio config. Supports copy mode (files inlined) or register mode (reference only).
      OPTIONS: [<source> (local path, GitHub slug, or Git URL), --mode copy|register]

    COMMAND kit update
      USER_ACTION: Run when an upstream kit has new changes and you want to selectively adopt them.
      PRODUCES: Interactive diff session per changed file; user accepts, declines, or modifies each change before it is written.
      OPTIONS: []

    COMMAND kit normalize
      USER_ACTION: Run after manually adding or rearranging files in a kit to keep manifest.toml consistent.
      PRODUCES: Generated or updated manifest.toml that reflects the current kit file layout.
      OPTIONS: [--dry-run (preview manifest without writing)]

    COMMAND kit check-updates
      USER_ACTION: Run to find out whether any installed kits have newer upstream versions available.
      PRODUCES: Comparison report of installed vs upstream kit versions for each registered kit.
      OPTIONS: []
```

```text
COMMAND_GROUP Document Utilities
  PURPOSE: Author structured documents, validate prompt contracts, and split large inputs for AI-assisted processing.
  COMMANDS:
    COMMAND toc
      USER_ACTION: Run after adding or renaming headings in a Markdown file to regenerate its Table of Contents.
      PRODUCES: Inserts or replaces the TOC block in the target Markdown file with anchor links derived from current headings.
      OPTIONS: [--dry-run (print TOC without writing), --max-level <n> (deepest heading level to include), --indent-size <n> (spaces per indent level)]

    COMMAND pdsl
      USER_ACTION: Run to verify that a skill or workflow file's PDSL prompt blocks satisfy their declared contracts.
      PRODUCES: Validation report indicating which PDSL blocks pass or fail their contract constraints; accepts a file path or stdin.
      OPTIONS: [<file> (path to skill/workflow file), --stdin (read from stdin), --verbose (show passing blocks)]

    COMMAND chunk-input
      USER_ACTION: Run before feeding a large Markdown document into an AI workflow that has context-length limits.
      PRODUCES: A manifest file and a set of numbered chunk files that together represent the original input split at safe boundaries.
      OPTIONS: [--stdin (read from stdin), --dry-run (preview chunk boundaries without writing)]
```

```text
COMMAND_GROUP Visualization
  PURPOSE: Produce an interactive visual map of how Studio artifacts and IDs depend on each other.
  COMMANDS:
    COMMAND map
      USER_ACTION: Run to generate a shareable dependency map for review, onboarding, or architecture documentation.
      PRODUCES: HTML page (or JSON data file) showing nodes for CPT IDs and edges for cross-references; highlights dangling references; supports multi-repo workspace federation.
      OPTIONS: [--inline-data (embed JSON into HTML for single-file sharing), --output <file> (path for HTML or JSON), --json (output raw JSON instead of HTML)]
```

```text
COMMAND_GROUP Workspace Management
  PURPOSE: Initialize and maintain a federated multi-repo workspace so Studio commands can span multiple repositories.
  COMMANDS:
    COMMAND workspace-init
      USER_ACTION: Run once at the root of a mono-repo or workspace directory to register all Studio-enabled sub-projects.
      PRODUCES: .cf-workspace.toml listing all discovered Studio project sources.
      OPTIONS: [--inline (embed source configs directly), --output <path> (custom output path), --force (overwrite existing), --max-depth <n> (scan depth), --dry-run]

    COMMAND workspace-add
      USER_ACTION: Run to register an additional project (local path or Git URL) into an existing workspace.
      PRODUCES: Updated .cf-workspace.toml with the new source entry appended.
      OPTIONS: [--force (overwrite if already present), --inline (embed config inline)]

    COMMAND workspace-info
      USER_ACTION: Run to audit which sources are registered and whether they are currently reachable.
      PRODUCES: Table of workspace sources with reachability status (online/offline/missing).
      OPTIONS: []

    COMMAND workspace-sync
      USER_ACTION: Run to pull or update Git worktrees for any URL-based sources in the workspace.
      PRODUCES: Local worktree directories synchronized to the declared Git refs for each URL source.
      OPTIONS: [--source <name> (sync one source only), --dry-run, --force (reset diverged worktrees)]
```

```text
COMMAND_GROUP Delegation & Diagnostics
  PURPOSE: Delegate Studio plans to remote execution and verify that the local environment meets all prerequisites.
  COMMANDS:
    COMMAND delegate
      USER_ACTION: Run to compile a plan.toml into the ralphex (remote execution layer) format and send it for execution.
      PRODUCES: Compiled execution plan dispatched to ralphex; in tasks-only mode prints the task list; in review mode shows the plan without executing.
      OPTIONS: [--mode execute|tasks-only|review, --dry-run (compile without dispatching), --json (output plan as JSON)]

    COMMAND doctor
      USER_ACTION: Run to diagnose environment setup issues before using Studio features that depend on external tools.
      PRODUCES: Health check report with PASS / WARN / FAIL status for each checked component (e.g., ralphex availability, required binaries).
      OPTIONS: []
```

---

## Notes

**CPT** — Canonical Provenance Trace ID. A structured identifier (e.g., `CPT-FEAT-001`) embedded in source code and artifact files to create a bidirectional traceability link. Commands in the Traceability Navigation category operate on these IDs.

**PDSL** — Prompt Domain Specification Language. A contract syntax used inside skill and workflow Markdown files to declare what an AI prompt block expects as input and produces as output. The `pdsl` command validates these contracts.

**CDSL** — Constructor Domain Specification Language — used both as structured document notation (CAPABILITY, ALGORITHM, COMMAND_GROUP blocks in research and spec documents) and as inline code markers (@cpt-*) scanned by cfs validate and cfs spec-coverage for traceability.

**Kits** — Reusable packages of Studio skills, rules, and configuration. A kit is a directory with a `conf.toml`, `constraints.toml`, and `manifest.toml`. The `kit` subcommands manage their lifecycle.

**ralphex** — The remote execution layer that Studio's `delegate` command targets. It accepts compiled plans and runs them outside the local environment.

**--json flag** — Several commands (`info`, `spec-coverage`, `map`, `delegate`) accept `--json` to produce machine-readable output suitable for scripting or CI pipelines.

**Command aliases** — `validate-kits` also responds to `validate-rules` and `self-check`. All three are equivalent.
