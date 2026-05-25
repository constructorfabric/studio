---
cf: true
type: project-rule
topic: project-structure
generated-by: auto-config
version: 1.0
---

# Project Structure



<!-- toc -->

- [Adapter Layout](#adapter-layout)
- [Canonical Source Layout](#canonical-source-layout)
- [Skill Package Layout](#skill-package-layout)
- [High-Value Files](#high-value-files)

<!-- /toc -->

Repo layout rules for the self-hosted Constructor Studio project.

## Adapter Layout

`.bootstrap/` is the active adapter directory for this repo.

```
.bootstrap/
  .core/      # Read-only mirror of canonical sources
  .gen/       # Generated aggregate files only
  config/     # User-editable config, rules, registry, and installed kit outputs
```

Never edit `.bootstrap/.core/` or `.bootstrap/.gen/` directly. Edit canonical sources at repo root, then sync with `make update` when you intend to refresh the mirror.

## Canonical Source Layout

```
src/studio_proxy/                    # Thin globally installed proxy
skills/cypilot/scripts/cypilot/      # Skill engine package
architecture/                        # PRD, DESIGN, ADRs, specs, features
requirements/                        # Methodologies and validation guidance
schemas/                             # JSON schemas
tests/                               # 44 pytest modules + shared helpers
scripts/                             # Maintenance/check scripts
```

Treat `src/studio_proxy/` and `skills/cypilot/scripts/cypilot/` as separate layers: proxy routing vs skill-engine business logic.

## Skill Package Layout

```
skills/cypilot/scripts/cypilot/
  cli.py          # Main command router
  commands/       # 23 command modules (one per command family)
  utils/          # 20 shared utility modules
  __main__.py     # python -m studio_proxy entry
  constants.py    # Shared constants and regexes
```

Add new CLI behavior in `commands/{name}.py`, wire it through `cli.py`, and put reusable helpers in `utils/` only when shared by multiple commands.

## High-Value Files

| File | Use |
|------|-----|
| `AGENTS.md` | Root managed block that declares `cf-studio-path` |
| `.bootstrap/config/AGENTS.md` | Project navigation rules, including auto-config sections |
| `.bootstrap/config/artifacts.toml` | Source of truth for systems, artifacts, and codebases |
| `pyproject.toml` | Proxy package metadata and `cpt` console entry point |
| `src/studio_proxy/cli.py` | Proxy command forwarding |
| `skills/cypilot/scripts/cypilot/cli.py` | Skill-engine dispatch hub |
| `skills/cypilot/scripts/cypilot/commands/init.py` | Init / force-reinit behavior |
| `Makefile` | Canonical local test, validate, and sync commands |
