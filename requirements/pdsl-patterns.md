---
cf: true
type: requirement
name: PDSL Patterns Registry
version: 0.1
purpose: Canonical named-pattern registry for the PDSL matches() operator
---

# PDSL Patterns Registry

This file is the canonical registry for named patterns used by the PDSL
`matches(<value>, <pattern-name>)` condition operator.

Patterns are referenced in PDSL `WHEN` clauses across workflows, skills, and
requirements.

```pdsl
UNIT PatternRegistryEntry
PURPOSE: Govern when and how named patterns are added to this registry.
STATE:
  - SET registry: empty
WHEN:
  - REQUIRE a PDSL UNIT needs a named pattern via matches() operator
DO:
  - EMIT entry declaring: name, regex-or-matcher-spec, usage-description
RULES:
  - ALWAYS declare name, regex or matcher specification, and description of usage per entry
  - NEVER register a pattern until a PDSL UNIT requires it
NOTES:
  Local PATTERNS: blocks in individual PDSL files may declare file-scoped patterns
  without registering them here, per {cf-studio-path}/.core/architecture/specs/PDSL.md §PATTERNS Block.
```

## Registered Patterns

_None yet._
