# Studio Skill Engine

Deterministic agent tool for structured workflows, artifact validation, traceability, kit management, and multi-agent integration.

Public CLI entrypoints: `cfs` and `constructor-studio`. Both route through the same proxy entrypoint; examples below use `cfs`.

## Commands

### Setup & Configuration

| Command | Description |
|---------|-------------|
| `init` | Initialize Studio config directory (`.core/`, `.gen/`, `config/`) and root `AGENTS.md` |
| `update` | Update `.core/`, migrate config when needed, refresh `.gen`, and regenerate agent entry points; kit files are updated separately with `kit update` |
| `info` | Discover Studio configuration and show project status |
| `resolve-vars` | Resolve configured template/resource variables to absolute paths |
| `generate-agents` | Generate agent-specific entry points for supported agents (Windsurf, Cursor, Claude, Copilot, OpenAI) |
| `agents` | Show generated agent integration status without writing files |

### Validation

| Command | Description |
|---------|-------------|
| `validate` | Validate artifacts against templates (structure, IDs, cross-references) and code traceability markers (pairing, coverage, orphans) |
| `validate-kits` | Validate registered kits or a standalone kit path (`[path]`, `--kit/--rule`, `--verbose`) |
| `validate-toc` | Validate Table of Contents in Markdown files (anchors, coverage, staleness) |
| `check-language` | Check Markdown artifacts for disallowed Unicode scripts (LANG001) |
| `self-check` | Legacy alias for `validate-kits` |
| `spec-coverage` | Measure CDSL marker coverage in codebase files, including per-file thresholds and repeated `--system` filters |

### Search & Navigation

| Command | Description |
|---------|-------------|
| `list-ids` | List all Studio IDs from registered artifacts (filterable by pattern, kind) |
| `list-id-kinds` | List ID kinds that exist in artifacts with counts and template mappings |
| `get-content` | Get content block for a specific Studio ID from artifacts or code |
| `where-defined` | Find where a Studio ID is defined |
| `where-used` | Find all references to a Studio ID |

### Kit Management

| Command | Description |
|---------|-------------|
| `kit install <owner/repo[@ref]>` | Install a kit from GitHub |
| `kit install --path <dir>` | Install a kit from a local directory |
| `kit update [slug|--path <dir>]` | Update registered kit files from their source or from a local directory |
| `kit validate` | Validate kit structure and examples |
| `kit migrate` | Deprecated alias; the public CLI warns and fails, and `kit update` is the supported replacement |
| `generate-resources` | Deprecated failing stub retained for compatibility; use `kit update` |

### Utility

| Command | Description |
|---------|-------------|
| `toc` | Generate or update Table of Contents in Markdown files |
| `chunk-input` | Chunk oversized workflow input into line-bounded Markdown files |
| `pdsl` | Validate-only PDSL command family (`pdsl validate`) |

### Workspace, Delegation & Diagnostics

| Command | Description |
|---------|-------------|
| `workspace-init` | Initialize a multi-repo workspace |
| `workspace-add` | Add a source to workspace config |
| `workspace-info` | Show workspace config and source status |
| `workspace-sync` | Fetch and update Git URL source worktrees |
| `delegate` | Compile and delegate a plan to RalphEx |
| `doctor` | Run environment health checks |
| `map` | Build an interactive markdown/source dependency map |
| `mirror` | Proxy-local URL mirror override command family |

### Legacy Aliases

| Alias | Maps to |
|-------|---------|
| `validate-code` | `validate` |
| `validate-rules` | `validate-kits` |
| `self-check` | `validate-kits` |

## Usage

### Via public CLI entrypoints

```bash
# run init without --json
cfs init
constructor-studio --help
cfs validate
cfs validate --artifact architecture/PRD.md
cfs validate-kits kits/sdlc
cfs spec-coverage --system api --system web
cfs check-language
cfs kit install constructorfabric/studio-kit-sdlc
cfs kit install --path ../my-kit
cfs kit update
cfs generate-agents --agent windsurf
cfs agents --agent windsurf
cfs pdsl validate workflows/generate.md
cfs map --local-only
cfs mirror sources
# run update without --json
cfs update
```

### More CLI examples

```bash
cfs validate
cfs validate --artifact architecture/PRD.md
cfs spec-coverage --min-coverage 80
cfs list-ids --pattern "-actor-"
cfs where-defined --id cpt-myapp-fr-auth
cfs kit update --dry-run
cfs toc architecture/DESIGN.md
cfs self-check --kit cf-sdlc
```

Human-readable output is the default. Use the global `--json` flag when an
automation or agent needs machine-readable output.

> **Note**: `studio auto-config` and `studio configure` are **AI prompts** (typed in the IDE chat), not CLI commands. They route through the `generate.md` workflow.

## Testing

```bash
make test
make test-coverage
```

## Documentation

- `SKILL.md` — complete skill definition with mandatory instructions, workflow routing, and command reference
- `studio.clispec` — CLI specification (commands, flags, output formats)
