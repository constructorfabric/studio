# .core — Constructor Studio Core Files

**Do NOT edit files in this directory.**

These files are copied from the Constructor Studio cache (`~/.cf-studio/cache/`) during
`cfs init` or `cfs kit install`. They are the read-only reference copies of:

- `skills/` — Constructor Studio skill scripts and CLI entry points
- `workflows/` — workflow definitions
- `requirements/` — validation requirements
- `schemas/` — JSON schemas for configuration files
- `architecture/specs/` — traceability, CDSL, PDSL, CLI, and kit specifications

To update these files, run `cfs init --force` or `cfs kit update`.
Any manual changes **will be overwritten** on the next update.
