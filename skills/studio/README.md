# Studio Skill Engine

Deterministic agent tool for structured workflows, artifact validation, traceability, kit management, and multi-agent integration.

## Commands

### Setup & Configuration

| Command | Description |
|---------|-------------|
| `init` | Initialize Studio config directory (`.core/`, `.gen/`, `config/`) and root `AGENTS.md` |
| `update` | Update `.core/` from cache, regenerate `.gen/` from user blueprints, ensure `config/` scaffold |
| `info` | Discover Studio configuration and show project status |
| `generate-agents` | Generate agent-specific entry points for supported agents (Windsurf, Cursor, Claude, Copilot, OpenAI) |

### Validation

| Command | Description |
|---------|-------------|
| `validate` | Validate artifacts against templates (structure, IDs, cross-references) and code traceability markers (pairing, coverage, orphans) |
| `validate-kits` | Validate kit configuration, blueprint markers, and constraints |
| `validate-toc` | Validate Table of Contents in Markdown files (anchors, coverage, staleness) |
| `self-check` | Validate kit examples against their own templates (template QA) |
| `spec-coverage` | Measure CDSL marker coverage in codebase files (coverage %, granularity score) |

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
| `kit install` | Install a kit from source directory (copies blueprints, scripts, generates resources) |
| `kit update` | Update kit reference copies from cache and regenerate `.gen/` outputs |
| `kit migrate` | Three-way merge of kit blueprints with interactive per-marker decisions |
| `generate-resources` | Regenerate `.gen/` outputs from user blueprints |

### Utility

| Command | Description |
|---------|-------------|
| `toc` | Generate or update Table of Contents in Markdown files |

### Legacy Aliases

| Alias | Maps to |
|-------|---------|
| `validate-code` | `validate` |
| `validate-rules` | `validate-kits` |

## Usage

### Via global CLI (recommended)

```bash
# run init without --json
cfs init
cfs validate
cfs validate --artifact architecture/PRD.md
cfs spec-coverage
cfs kit migrate
cfs generate-agents --agent windsurf
# run update without --json
cfs update
```

### Via direct script invocation

```bash
python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py validate
python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py validate --artifact architecture/PRD.md
python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py spec-coverage --min-coverage 80
python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py list-ids --pattern "-actor-"
python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py where-defined --id cpt-myapp-fr-auth
python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py kit migrate --dry-run
python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py toc architecture/DESIGN.md
```

All commands output JSON to stdout.

> **Note**: `studio auto-config` and `studio configure` are **AI prompts** (typed in the IDE chat), not CLI commands. They route through the `generate.md` workflow.

## Testing

```bash
make test
make test-coverage
```

## Documentation

- `SKILL.md` — complete skill definition with mandatory instructions, workflow routing, and command reference
- `studio.clispec` — CLI specification (commands, flags, output formats)
