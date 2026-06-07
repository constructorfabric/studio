# config — User Configuration

This directory contains **user-editable** configuration files.

## Files

- `core.toml` — project settings, install tracking policy, and kit references
- `artifacts.toml` — artifacts registry (systems, ignore patterns)
- `AGENTS.md` — custom agent navigation rules (add your own WHEN rules here)
- `SKILL.md` — custom skill extensions (add your own skill instructions here)

## Directories

- `kits/{slug}/` — kit files (SKILL.md, AGENTS.md, artifacts/, codebase/, workflows/, scripts/).
  Each kit has its own git tracking policy. Tracked kits are editable repository
  content. Ignored kits are generated local content and may be overwritten by
  Studio repair/update flows.

## Tips

- `AGENTS.md` and `SKILL.md` start empty. Add any project-specific rules or
  skill instructions here — they will be picked up alongside the kit ones.
- Kit files can be edited directly when that kit is tracked. `cfs kit update`
  shows a diff for tracked kit changes. Top-level `cfs update` does not update
  kit files unless called with `--with-kits yes`.
