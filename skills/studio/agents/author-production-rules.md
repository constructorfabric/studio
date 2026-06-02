---
description: Invoke when loading the shared Content Production Rules for Constructor Studio author workers — single source of truth for content-production constraints applied before any file is written.
---

<!-- toc -->

- [Content Production Rules](#content-production-rules)

<!-- /toc -->

```pdsl
UNIT AuthorProductionRules

PURPOSE:
  Single source of truth for content-production constraints that every author
  worker agent must satisfy before returning.

NOTES:
  This file is a shared module selected by the controller from
  `SHARED_CONTEXT_PACK` and injected into the final dispatch prompt as
  `author_production_rules`.

  It is NOT a dispatchable agent (intentionally absent from agents.toml).
  Applies to: cf-generate-author-{junior,middle,senior,lead},
  cf-generate-coder-{casual,smart}, cf-generate-prompt-engineer-{casual,smart},
  and any future author worker.
```

## Content Production Rules

```pdsl
RULES:
  - NEVER leave placeholder markers (TODO, TBD, [Description], FIXME, etc.)
    in any written file
  - ALWAYS ensure all IDs are valid (format matches kind's ID schema) and unique
    within the target file
  - ALWAYS fill every template H2 section — no empty sections, no "see above" punts
  - ALWAYS reference parent artifacts correctly (registered paths, matching kind,
    no dangling links)
  - ALWAYS follow conventions defined in the kit's rules.md (naming, ordering, casing)
  - ALWAYS implement all approved inputs in generated content — nothing silently dropped
  - ALWAYS emit tests when the kind/rules require them
  - ALWAYS emit traceability markers (e.g. @cpt-...) when to_code="true" on the kind
  - ALWAYS use CDSL (Constructor Domain-Specific Language) per kit's rules in
    behavioral sections — no free-form prose where CDSL is required
  - NEVER include executable code examples in DESIGN.md artifacts (CDSL only)
  - ALWAYS apply Markdown quality: empty lines between headings/paragraphs/lists;
    fenced code blocks include a language tag
```
