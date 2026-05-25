---
description: Invoke when loading the shared Content Production Rules for Constructor Studio author workers — single source of truth for content-production constraints applied before any file is written.
---

<!-- toc -->

- [Content Production Rules](#content-production-rules)

<!-- /toc -->


This file is a shared content-production rules module loaded by author worker agents via `Open and follow {cf-studio-path}/.core/skills/studio/agents/author-production-rules.md`. It is NOT a dispatchable agent (intentionally absent from agents.toml). Author worker agents (junior/middle/senior/lead, coder-casual/smart, prompt-engineer-casual/smart, and any future worker) MUST include this load directive in their dispatch flow.

## Content Production Rules

The author MUST satisfy every rule below before returning. These rules are the
single source of truth for content-production constraints.

- No placeholder markers (`TODO`, `TBD`, `[Description]`, `FIXME`, etc.) in
  any written file.
- All IDs are valid (format matches the kind's ID schema) and unique within
  the target file.
- Every template H2 section is filled (no empty sections, no "see above"
  punts).
- Parent artifacts are referenced correctly (registered paths, matching kind,
  no dangling links).
- Conventions defined in the kit's `rules.md` are followed (naming, ordering,
  casing).
- All approved `inputs` are implemented in the generated content; nothing is
  silently dropped.
- Tests are emitted when the kind / rules require them.
- Traceability markers (e.g. `@cpt-...`) are emitted when `to_code="true"` on
  the kind.
- Behavioral sections use CDSL (Constructor Domain-Specific Language) per the
  kit's rules; no free-form prose where CDSL is required.
- `DESIGN.md` artifacts contain no executable code examples (CDSL only).
- Markdown quality: empty lines between headings / paragraphs / lists; fenced
  code blocks include a language tag.
