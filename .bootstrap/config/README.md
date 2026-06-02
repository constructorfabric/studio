# config — User Configuration

This directory contains **user-editable** configuration files.

## Files

- `core.toml` — project settings (system name, slug, kit references)
- `artifacts.toml` — artifacts registry (systems, ignore patterns)
- `AGENTS.md` — custom agent navigation rules (add your own WHEN rules here)
- `SKILL.md` — custom skill extensions (add your own skill instructions here)

## Directories

- `kits/{slug}/` — editable installed kit content: templates, rules,
  checklists, constraints, workflows, scripts, and skill surfaces.
  Modify these files directly when you need project-local customization.

## Tips

- `AGENTS.md` and `SKILL.md` start empty. Add any project-specific rules or
  skill instructions here — they will be picked up alongside installed kit content.
- Use `cfs kit update` to update installed kit files from their registered source.
  Inspect the diff before accepting upstream changes over local customizations.
