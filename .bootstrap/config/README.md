# config -- User Configuration

This directory contains **user-editable** configuration files.

## Files

- `core.toml` — project settings (system name, slug, kit references)
- `artifacts.toml` — artifacts registry (systems, ignore patterns)
- `AGENTS.md` — custom agent navigation rules (add your own WHEN rules here)
- `SKILL.md` — custom skill extensions (add your own skill instructions here)

## Directories

- `kits/{slug}/` — kit files (SKILL.md, AGENTS.md, artifacts/, codebase/, workflows/, scripts/).
  These are updated via `cfs update` or `cfs kit update`.

## Tips

- `AGENTS.md` and `SKILL.md` start empty. Add any project-specific rules or
  skill instructions here — they will be picked up alongside the kit ones.
- Kit files can be edited directly; `cfs kit update` shows a diff for changes.
